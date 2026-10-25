"""
memory.py: connects the SAGE memory-decline flagging model (../flagging_model) to the live backend.

The model was built around a "reminder_events" schema. The backend stores reminders in its own
"reminders" collection, so this file translates between them and turns the model's output into
what the dashboard's Memory & routine tab shows.

If flag_model.joblib doesn't exist yet, it is trained in the background when the backend starts
(about 30 s on a laptop). Until then /api/memory-status says the model is getting ready.
"""
import sys
import threading
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so "flagging_model" is importable
from flagging_model import model as fm  # noqa: E402

import db  # noqa: E402
import agent37  # noqa: E402

STATUS_MAP = {"confirmed": "taken", "late": "late", "missed": "missed"}
_clf = None
_training = False
_cache = {}          # device -> (signature, result, time)


def _load_or_train():
    global _clf, _training
    try:
        _clf = fm.joblib.load(fm.MODEL_PATH)
        print(f"[memory] flagging model loaded ({fm.MODEL_PATH.name})")
        return
    except FileNotFoundError:
        pass
    _training = True
    print("[memory] flag_model.joblib not found: training it now in the background (~30 s)...")
    try:
        _clf = fm.train()
    except Exception as e:
        print(f"[memory] training failed: {e.__class__.__name__}: {e}")
    finally:
        _training = False


def start():
    threading.Thread(target=_load_or_train, name="sage-memory-model", daemon=True).start()


def _ts(v):
    """Mongo datetime -> plain pandas timestamp (UTC, no timezone), or NaT."""
    if v is None:
        return pd.NaT
    t = pd.Timestamp(v)
    return t.tz_convert(None) if t.tzinfo else t


MAX_REPLY_MINUTES = 89   # the model's training data never has a reply later than this (after 90 min = missed)


def _capped_reply(r):
    sched, reply = _ts(r["scheduled_at"]), _ts(r.get("responded_at"))
    if reply is pd.NaT or pd.isna(reply):
        return pd.NaT
    return min(reply, sched + pd.Timedelta(minutes=MAX_REPLY_MINUTES))


def _events_for(device):
    """Backend reminders -> the model's reminder_events format."""
    rows = []
    for r in db.reminders.find({"device": device}).sort("scheduled_at", 1):
        status = STATUS_MAP.get(r.get("status"))
        if not status:
            continue
        attempt = r.get("attempt")
        if attempt is None:                       # older records without the re-ask count
            attempt = {"taken": 1, "late": 2, "missed": 3}[status]
        rows.append({
            "user_id": device,
            "type": r.get("type", "medicine"),
            "scheduled_at": _ts(r["scheduled_at"]),
            "responded_at": _capped_reply(r),
            "status": status,
            "repeat_prompts": max(0, min(3, int(attempt) - 1)),
            "duplicate_confirm": bool(r.get("duplicate_confirm", False)),
        })
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    # The model works in whole weeks counted from the first reminder. Leave out the current week
    # until it has at least 3 days of data, so a half-finished week isn't judged like a full one.
    start = df["scheduled_at"].min().normalize()
    week = (df["scheduled_at"] - start).dt.days // 7
    last = int(week.max())
    days_in_last = (df["scheduled_at"].max().normalize() - (start + pd.Timedelta(days=7 * last))).days + 1
    if last > 0 and days_in_last < 3:
        df = df[week < last]
    return df


LEVEL = {"flag": "concern", "watch": "watch", "normal": "normal"}
TITLE = {"concern": "A change worth mentioning to her doctor",
         "watch": "An unusual week, still watching",
         "normal": "Routine looks steady"}


def status(device="sage-home-01"):
    """What the dashboard's Memory & routine tab shows."""
    if _clf is None:
        return {"level": None, "learning": True, "source": "model", "care_summary": agent37.status_block(db.patient_for_device(device).get("id")),
                "message": "The memory model is getting ready (first start trains it, about 30 s)." if _training
                else "The memory model isn't available. Check the backend window for the reason."}
    sig = (db.reminders.count_documents({"device": device}),
           (db.reminders.find_one({"device": device}, sort=[("_id", -1)]) or {}).get("_id"))
    hit = _cache.get(device)
    if hit and hit[0] == sig and time.time() - hit[2] < 300:
        return {**hit[1], "care_summary": agent37.status_block(db.patient_for_device(device).get("id"))}

    events = _events_for(device)
    if events.empty:
        result = {"level": None, "learning": True, "source": "model", "message": "No reminder history yet."}
    else:
        out = fm.assess_user(events, clf=_clf)
        if out["status"] == "learning_baseline":
            result = {"level": None, "learning": True, "source": "model", "message": out["message"].replace("this person's", "her")}
        else:
            level = LEVEL[out["status"]]
            result = {
                "level": level, "title": TITLE[level], "source": "model",
                "summary": out["message"].replace("this person's", "her").replace("their doctor", "her doctor"),
                "reasons": out.get("reasons", []),
                "risk": out.get("risk"),
                "weekly": out.get("weekly", []),
                "weeks_of_history": len(out.get("weekly", [])) + fm.BASELINE_WEEKS,
            }
    _cache[device] = (sig, result, time.time())
    pid = db.patient_for_device(device).get("id")
    if result.get("level"):
        agent37.request_summary(_facts(result, device))      # background; only when the findings changed
    return {**result, "care_summary": agent37.status_block(pid)}


def _facts(result, device="sage-home-01"):
    patient, guardian = db.patient_for_device(device), db.get_profile("guardian")
    weekly = result.get("weekly", [])
    return {
        "patient_id": patient.get("id"),
        "name": patient.get("preferred_name") or (patient.get("name") or "Kamala").split(" ")[0],
        "guardian": f"{(guardian.get('name') or 'her son').split(' ')[0]} ({(guardian.get('relation') or 'family').lower()})",
        "level": result["level"],
        "risk_this_week": result.get("risk"),
        "reasons": [r.replace("->", "changed to") for r in result.get("reasons", [])],
        "weekly_risk": [{"week": w["week"], "risk": w["risk"], "missed_share": w["miss_rate"]} for w in weekly[-4:]],
        "weeks_above_her_normal": sum(1 for w in weekly[-4:] if w["risk"] >= 0.6),
    }


def refresh_summary(device="sage-home-01"):
    result = status(device)
    if not result.get("level"):
        return "no_verdict_yet"
    return agent37.request_summary(_facts(result, device), force=True)
