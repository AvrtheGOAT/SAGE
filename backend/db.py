"""
db.py — the ONLY file in SAGE that talks to MongoDB.
Everything else imports these functions, e.g.:
    import db
    db.save_reading({...})
"""
import os
from datetime import datetime, timezone, timedelta

from werkzeug.security import check_password_hash, generate_password_hash

from bson import Binary, ObjectId
from dotenv import load_dotenv
from pymongo import MongoClient, ASCENDING, DESCENDING

load_dotenv()

_client = MongoClient(
    os.environ["MONGO_URI"],
    serverSelectionTimeoutMS=5000,  # fail fast instead of hanging forever
    tz_aware=True,                  # keep all times in UTC, timezone-aware
)
_db = _client["sage"]

readings = _db["readings"]
reminders = _db["reminders"]
alerts = _db["alerts"]
events = _db["events"]   # raw log of everything the voice assistant reports
reports = _db["reports"]  # uploaded medical reports (file stored in the document, max 10 MB)
users = _db["users"]      # family accounts that can open the dashboard
profiles = _db["profiles"]  # the guardian profile (and the original single "patient" profile)
patients = _db["patients"]  # one document per elder this family looks after

# Indexes make the common queries fast (safe to run every startup)
readings.create_index([("device", ASCENDING), ("timestamp", DESCENDING)])
reminders.create_index([("device", ASCENDING), ("scheduled_at", ASCENDING)])
alerts.create_index([("acknowledged", ASCENDING), ("created_at", DESCENDING)])
events.create_index([("received_at", DESCENDING)])


# ---------- helpers ----------

def _now():
    return datetime.now(timezone.utc)


def _clean(doc):
    """Make a Mongo document JSON-friendly: _id -> id string, datetimes -> ISO strings (also inside lists)."""
    if doc is None:
        return None
    def conv(v):
        if isinstance(v, datetime):
            return v.isoformat()
        if isinstance(v, list):
            return [conv(x) for x in v]
        if isinstance(v, dict):
            return {k: conv(x) for k, x in v.items()}
        return v
    out = {}
    for key, value in doc.items():
        if key == "_id":
            out["id"] = str(value)
        elif key == "password_hash":
            continue                 # never send password hashes to the browser
        elif isinstance(value, (bytes, Binary)):
            continue                 # never send raw file bytes as JSON
        else:
            out[key] = conv(value)
    return out


def ping():
    """Raises an error if the database can't be reached."""
    _client.admin.command("ping")
    return True


# ---------- readings (from the ESP32) ----------

READING_EXTRAS = ("finger", "activity", "gps", "mic", "battery")


def save_reading(data):
    doc = {
        "device": data.get("device", "wearable1"),
        "heart_rate": data.get("heart_rate"),
        "spo2": data.get("spo2"),
        "fall": bool(data.get("fall", False)),
        "timestamp": _now(),
    }
    for k in READING_EXTRAS:            # extra telemetry from the band, stored only when sent
        if data.get(k) is not None:
            doc[k] = data[k]
    readings.insert_one(doc)
    return _clean(doc)


def get_latest(device="wearable1"):
    doc = readings.find_one({"device": device}, sort=[("timestamp", DESCENDING)])
    return _clean(doc)


def get_recent_readings(device="wearable1", limit=30):
    """Last `limit` readings, oldest first (ready for a chart)."""
    docs = list(
        readings.find({"device": device}).sort("timestamp", DESCENDING).limit(limit)
    )
    return [_clean(d) for d in reversed(docs)]


# ---------- reminders (medicine, check-ins) ----------

LATE_AFTER_MINUTES = 15    # confirmed after this = "late"
MISSED_AFTER_MINUTES = 30  # no response after this = "missed"


def create_reminder(rtype, text, scheduled_at=None, device="wearable1"):
    doc = {
        "device": device,
        "type": rtype,              # "medicine", "checkin", "checkup"
        "text": text,               # shown on the OLED / spoken aloud
        "scheduled_at": scheduled_at or _now(),
        "responded_at": None,
        "status": "pending",        # pending -> confirmed / late / missed
        "source": None,             # "button" or "voice"
    }
    reminders.insert_one(doc)
    return _clean(doc)


def next_pending_reminder(device="wearable1"):
    """The oldest reminder that is due and not yet answered (for the ESP32 to show)."""
    doc = reminders.find_one(
        {"device": device, "status": "pending", "scheduled_at": {"$lte": _now()}},
        sort=[("scheduled_at", ASCENDING)],
    )
    return _clean(doc)


def respond_to_reminder(reminder_id, source="button"):
    """Mark a reminder as answered. Returns the updated reminder, or None."""
    try:
        oid = ObjectId(reminder_id)
    except Exception:
        return None
    r = reminders.find_one({"_id": oid})
    if not r or r["status"] != "pending":
        return None
    now = _now()
    delay_min = (now - r["scheduled_at"]).total_seconds() / 60
    status = "late" if delay_min > LATE_AFTER_MINUTES else "confirmed"
    reminders.update_one(
        {"_id": oid},
        {"$set": {"status": status, "responded_at": now, "source": source}},
    )
    return _clean(reminders.find_one({"_id": oid}))


def mark_missed_reminders():
    """Turn overdue pending reminders into 'missed'. Returns the ones just marked."""
    cutoff = _now() - timedelta(minutes=MISSED_AFTER_MINUTES)
    overdue = list(reminders.find({"status": "pending", "scheduled_at": {"$lt": cutoff}}))
    if overdue:
        reminders.update_many(
            {"_id": {"$in": [r["_id"] for r in overdue]}},
            {"$set": {"status": "missed"}},
        )
    return [_clean({**r, "status": "missed"}) for r in overdue]


def get_reminders(device="wearable1", days=42):
    """Reminder history for the last `days` days, oldest first (for the memory model)."""
    since = _now() - timedelta(days=days)
    docs = reminders.find(
        {"device": device, "scheduled_at": {"$gte": since}}
    ).sort("scheduled_at", ASCENDING)
    return [_clean(d) for d in docs]


# ---------- alerts (falls, bad vitals, missed reminders) ----------

URGENT_KINDS = ("fall", "emergency")
# Escalation timing for urgent alerts (seconds after the alert), overridable in .env
SECONDARY_AFTER = int(os.getenv("NOTIFY_SECONDARY_AFTER_SECONDS", "60"))
SERVICES_AFTER = int(os.getenv("CALL_SERVICES_AFTER_SECONDS", "120"))


def create_alert(kind, message, device="wearable1"):
    now = _now()
    doc = {
        "device": device,
        "kind": kind,               # "fall", "emergency", "reminder_missed", "checkin_missed", ...
        "message": message,
        "created_at": now,
        "acknowledged": False,
    }
    if kind in URGENT_KINDS:
        doc["escalation"] = []      # steps taken while nobody responded
        doc["secondary_at"] = now + timedelta(seconds=SECONDARY_AFTER)
        doc["services_at"] = now + timedelta(seconds=SERVICES_AFTER)
    alerts.insert_one(doc)
    return _clean(doc)


def get_unhandled_urgent():
    """Falls / SOS that nobody has responded to or cancelled yet (oldest first)."""
    docs = alerts.find({"kind": {"$in": list(URGENT_KINDS)}, "acknowledged": False}).sort("created_at", ASCENDING)
    return list(docs)


def add_escalation_step(alert_id, step, detail):
    alerts.update_one({"_id": alert_id}, {"$push": {"escalation": {"step": step, "at": _now(), "detail": detail}}})


def cancel_latest_urgent(device=None):
    """Patient cancelled from the band: cancel the newest open SOS / fall for THIS patient. Returns the alert or None."""
    q = {"kind": {"$in": list(URGENT_KINDS)}, "acknowledged": False}
    if device:
        q["device"] = {"$in": devices_of_patient_with(device)}
    doc = alerts.find_one(q, sort=[("created_at", DESCENDING)])
    if not doc:
        return None
    alerts.update_one({"_id": doc["_id"]}, {"$set": {"acknowledged": True, "outcome": "cancelled_by_patient", "acknowledged_at": _now()}})
    return _clean(alerts.find_one({"_id": doc["_id"]}))


def siren_on(device=None):
    """The wearable's buzzer sounds while an urgent alert for its own patient is still open."""
    q = {"kind": {"$in": list(URGENT_KINDS)}, "acknowledged": False}
    if device:
        q["device"] = {"$in": devices_of_patient_with(device)}
    return alerts.count_documents(q, limit=1) > 0


def get_active_alerts(limit=20, devices=None):
    q = {"acknowledged": False}
    if devices:
        q["device"] = {"$in": list(devices)}
    docs = alerts.find(q).sort("created_at", DESCENDING).limit(limit)
    return [_clean(d) for d in docs]


def acknowledge_alert(alert_id, outcome="handled"):
    """outcome: "checking" (family is checking on them), "false_alarm", "ambulance", "handled"."""
    try:
        oid = ObjectId(alert_id)
    except Exception:
        return False
    result = alerts.update_one(
        {"_id": oid},
        {"$set": {"acknowledged": True, "outcome": outcome, "acknowledged_at": _now()}},
    )
    return result.modified_count == 1


def get_alert_history(limit=10, devices=None):
    """All alerts (handled or not), newest first, for the audit table."""
    docs = alerts.find({"device": {"$in": list(devices)}} if devices else {}).sort("created_at", DESCENDING).limit(limit)
    return [_clean(d) for d in docs]


# ---------- voice assistant events ----------

def _parse_time(value):
    """ISO string from the voice assistant -> aware datetime (falls back to now)."""
    try:
        dt = datetime.fromisoformat(value)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return _now()


def save_event(event):
    doc = dict(event)
    doc["timestamp"] = _parse_time(event.get("timestamp"))
    doc["received_at"] = _now()
    events.insert_one(doc)
    return _clean(doc)


def get_events(limit=50, devices=None):
    docs = events.find({"device_id": {"$in": list(devices)}} if devices else {}).sort("received_at", DESCENDING).limit(limit)
    return [_clean(d) for d in docs]


def record_reminder_outcome(device, rtype, label, scheduled_hhmm, status,
                            source="voice", event_time=None, attempt=None):
    """Turn a voice-assistant reminder event into a row in `reminders`
    (the collection the memory model reads).

    scheduled_hhmm: "09:30" in the laptop's local time, as the voice assistant sends it.
    status: "confirmed", "late" or "missed".
    """
    event_time = event_time or _now()
    local_event = event_time.astimezone()            # laptop's local timezone (IST)
    hh, mm = (int(x) for x in scheduled_hhmm.split(":"))
    scheduled_local = local_event.replace(hour=hh, minute=mm, second=0, microsecond=0)
    if scheduled_local > local_event:                 # e.g. 23:59 reminder answered after midnight
        scheduled_local -= timedelta(days=1)
    # A reply hours after its slot means the reminder was fired by hand (demo / testing, the "m" key),
    # not that she took hours to answer. Use roughly when it was actually asked instead.
    if local_event - scheduled_local > timedelta(hours=3):
        asked_minutes_ago = 2 + max(0, (attempt or 1) - 1) * 2
        scheduled_local = local_event - timedelta(minutes=asked_minutes_ago)

    doc = {
        "device": device,
        "type": rtype,
        "text": label,
        "scheduled_at": scheduled_local.astimezone(timezone.utc),
        "responded_at": None if status == "missed" else event_time,
        "status": status,
        "source": None if status == "missed" else source,
        "attempt": attempt,          # how many times SAGE asked (1 = first time); a key memory-model signal
    }
    reminders.insert_one(doc)
    return _clean(doc)


# ---------- medical reports ----------

def save_report(title, kind, report_date, notes, filename, content_type, data, patient_id=None):
    """report_date: "YYYY-MM-DD" (the date on the report, not the upload date)."""
    doc = {
        "patient_id": patient_id,
        "title": title, "kind": kind, "report_date": report_date, "notes": notes,
        "filename": filename, "content_type": content_type, "size": len(data),
        "uploaded_at": _now(), "data": Binary(data),
    }
    reports.insert_one(doc)
    doc.pop("data")
    return _clean(doc)


def list_reports(patient_id=None):
    q = {}
    if patient_id:
        first = patients.find_one(sort=[("created_at", ASCENDING)])
        is_first = first is not None and str(first["_id"]) == patient_id
        # reports uploaded before profiles existed belong to the first elder
        q = {"$or": [{"patient_id": patient_id}, {"patient_id": None}]} if is_first else {"patient_id": patient_id}
    docs = reports.find(q, {"data": 0}).sort("report_date", DESCENDING)
    return [_clean(d) for d in docs]


def get_report(report_id):
    """Full document including the file bytes, or None."""
    try:
        return reports.find_one({"_id": ObjectId(report_id)})
    except Exception:
        return None


def delete_report(report_id):
    try:
        return reports.delete_one({"_id": ObjectId(report_id)}).deleted_count == 1
    except Exception:
        return False


# ---------- one day, for the calendar's day details ----------

def get_day(start, end, wearable="wearable1", voice="sage-home-01"):
    """Vitals summary, alerts and voice events between two UTC datetimes (one local day)."""
    rng = {"$gte": start, "$lt": end}
    valid = lambda f: {"$cond": [{"$gt": [f"${f}", 0]}, f"${f}", None]}  # 0 / -1 = no finger on sensor
    agg = list(readings.aggregate([
        {"$match": {"device": wearable, "timestamp": rng}},
        {"$group": {
            "_id": None, "count": {"$sum": 1},
            "hr_avg": {"$avg": valid("heart_rate")}, "hr_min": {"$min": valid("heart_rate")}, "hr_max": {"$max": valid("heart_rate")},
            "spo2_avg": {"$avg": valid("spo2")}, "spo2_min": {"$min": valid("spo2")}, "spo2_max": {"$max": valid("spo2")},
            "falls": {"$sum": {"$cond": ["$fall", 1, 0]}},
        }},
    ]))
    vitals = None
    if agg:
        a = agg[0]
        vitals = {k: (round(v) if isinstance(v, float) else v) for k, v in a.items() if k != "_id"}
    day_alerts = [_clean(d) for d in alerts.find({"created_at": rng}).sort("created_at", ASCENDING)]
    day_events = [_clean(d) for d in events.find({"device_id": voice, "timestamp": rng}).sort("timestamp", ASCENDING).limit(200)]
    return {"vitals": vitals, "alerts": day_alerts, "events": day_events}


# ---------- family accounts ----------

def user_count():
    return users.count_documents({})


def create_user(name, email, password):
    email = email.strip().lower()
    if users.find_one({"email": email}):
        return None
    doc = {"name": name.strip(), "email": email, "password_hash": generate_password_hash(password), "created_at": _now()}
    users.insert_one(doc)
    return _clean(doc)


def check_login(email, password):
    u = users.find_one({"email": (email or "").strip().lower()})
    if u and check_password_hash(u["password_hash"], password or ""):
        return _clean(u)
    return None


def get_user(user_id):
    try:
        return _clean(users.find_one({"_id": ObjectId(user_id)}))
    except Exception:
        return None


# ---------- patient & guardian profiles ----------

PROFILE_FIELDS = {
    "patient": ["name", "preferred_name", "dob", "gender", "blood_group", "phone", "address", "conditions",
                "allergies", "medications", "doctor_name", "doctor_phone", "ambulance_number", "notes"],
    "guardian": ["name", "relation", "phone", "email", "secondary_name", "secondary_relation", "secondary_phone"],
}
PROFILE_DEFAULTS = {
    "patient": {"name": "Kamala Deshpande", "preferred_name": "Kamala", "dob": "1948-03-12", "ambulance_number": "108"},
    "guardian": {"name": "Rohan Deshpande", "relation": "Son"},
}


def get_profile(kind):
    doc = profiles.find_one({"_id": kind}) or {}
    out = {**PROFILE_DEFAULTS.get(kind, {}), **{k: v for k, v in doc.items() if k != "_id"}}
    return _clean(out)


def save_profile(kind, data):
    clean = {k: str(data.get(k, "")).strip()[:2000] for k in PROFILE_FIELDS[kind] if k in data}
    clean["updated_at"] = _now()
    profiles.update_one({"_id": kind}, {"$set": clean}, upsert=True)
    return get_profile(kind)


# ---------- wearable receiver helpers ----------

def recent_open_urgent(device, kind, seconds=60):
    """An open fall/SOS from this device in the last `seconds`: used to ignore retried packets."""
    since = _now() - timedelta(seconds=seconds)
    return alerts.find_one({"device": device, "kind": kind, "acknowledged": False, "created_at": {"$gte": since}})


def seen_event_id(device, event_id):
    """True if this event_id was already handled (the band resent a packet whose reply got lost)."""
    if not event_id:
        return False
    return events.find_one({"device_id": device, "event_id": str(event_id)}) is not None


def save_device_event(device, etype, event_id=None, data=None):
    doc = {"device_id": device, "type": etype, "data": data or {}, "timestamp": _now(), "received_at": _now()}
    if event_id:
        doc["event_id"] = str(event_id)
    events.insert_one(doc)
    return _clean(doc)


# ---------- several elders per family ----------
# Each elder has their own profile plus the ids of their own devices, so vitals, alerts,
# reminders, the memory model and the care agent are all kept per person.

PATIENT_FIELDS = PROFILE_FIELDS["patient"] + ["wearable_id", "voice_id"]


def _ensure_first_patient():
    """First run after the upgrade: turn the original single patient profile into the first elder."""
    if patients.count_documents({}) == 0:
        p = get_profile("patient")
        doc = {k: p.get(k, "") for k in PROFILE_FIELDS["patient"]}
        doc.update(wearable_id="wearable1", voice_id="sage-home-01", created_at=_now())
        patients.insert_one(doc)


def list_patients():
    _ensure_first_patient()
    return [_clean(d) for d in patients.find().sort("created_at", ASCENDING)]


def get_patient(patient_id):
    _ensure_first_patient()
    try:
        return _clean(patients.find_one({"_id": ObjectId(patient_id)}))
    except Exception:
        return None


def create_patient(data):
    doc = {k: str(data.get(k, "")).strip()[:2000] for k in PATIENT_FIELDS}
    if not doc["name"]:
        return None
    n = patients.count_documents({}) + 1
    doc["wearable_id"] = doc["wearable_id"] or f"wearable{n}"
    doc["voice_id"] = doc["voice_id"] or f"sage-home-{n:02d}"
    doc["preferred_name"] = doc["preferred_name"] or doc["name"].split(" ")[0]
    doc["ambulance_number"] = doc["ambulance_number"] or "108"
    doc["created_at"] = _now()
    patients.insert_one(doc)
    return _clean(doc)


def save_patient(patient_id, data):
    clean = {k: str(data.get(k, "")).strip()[:2000] for k in PATIENT_FIELDS if k in data}
    for k in ("wearable_id", "voice_id"):          # never blank a device id by accident
        if k in clean and not clean[k]:
            clean.pop(k)
    clean["updated_at"] = _now()
    patients.update_one({"_id": ObjectId(patient_id)}, {"$set": clean})
    return get_patient(patient_id)


def patient_for_device(device):
    """The elder a band or voice device belongs to (falls back to the first elder)."""
    _ensure_first_patient()
    doc = patients.find_one({"$or": [{"wearable_id": device}, {"voice_id": device}]}) if device else None
    return _clean(doc or patients.find_one(sort=[("created_at", ASCENDING)]))


def devices_of_patient_with(device):
    p = patients.find_one({"$or": [{"wearable_id": device}, {"voice_id": device}]})
    return [x for x in (p.get("wearable_id"), p.get("voice_id")) if x] if p else [device]


def patient_summary(p):
    """Live status for the profiles page."""
    devs = [x for x in (p.get("wearable_id"), p.get("voice_id")) if x]
    open_alerts = list(alerts.find({"device": {"$in": devs}, "acknowledged": False}))
    last = readings.find_one({"device": p.get("wearable_id")}, sort=[("timestamp", DESCENDING)])
    return {
        "urgent": sum(1 for a in open_alerts if a["kind"] in URGENT_KINDS),
        "open_alerts": len(open_alerts),
        "last_reading": _clean({"t": last["timestamp"]})["t"] if last else None,
        "heart_rate": last.get("heart_rate") if last else None,
    }
