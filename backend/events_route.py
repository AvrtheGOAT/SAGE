"""
events_route.py — lives in backend/, next to db.py.
Receives events from the voice assistant (backend_client.py posts to /events).

Register it in app.py:
    from events_route import events_bp
    app.register_blueprint(events_bp)

What it does with each event:
  1. Stores it in the `events` collection (raw log).
  2. Emergencies / missed reminders  -> creates an alert for the dashboard.
  3. Reminder outcomes              -> writes a row to `reminders`,
                                       which is what the memory-decline model reads.
"""
from flask import Blueprint, jsonify, request

import db

events_bp = Blueprint("events", __name__)

ALERT_TYPES = {"emergency", "reminder_missed", "checkin_missed"}

# event type -> (reminder type, status when answered on first attempt)
REMINDER_EVENTS = {
    "medicine_confirmed": ("medicine", "confirmed"),
    "reminder_missed": ("medicine", "missed"),
    "checkin_completed": ("checkin", "confirmed"),
    "checkin_missed": ("checkin", "missed"),
}


def _alert_message(etype, data):
    if etype == "emergency":
        return f"Emergency: {data.get('reason') or 'help requested'}"
    if etype == "reminder_missed":
        return f"Missed {data.get('label', 'medicine')} (scheduled {data.get('scheduled', '?')})"
    if etype == "checkin_missed":
        return f"Missed {data.get('label', 'check-in')} (scheduled {data.get('scheduled', '?')})"
    return etype


@events_bp.post("/events")
def receive_event():
    e = request.get_json(silent=True)
    if not e or "type" not in e:
        return jsonify(error="missing type"), 400

    etype = e["type"]
    data = e.get("data") or {}
    device = e.get("device_id", "unknown")
    saved = db.save_event(e)

    if etype in ALERT_TYPES:
        db.create_alert(etype, _alert_message(etype, data), device=device)
        print(f"!!! ALERT: {etype} {data}")  # hook SMS/notification here later

    # Only reminder events tied to a schedule count for the memory model.
    # (A spontaneous "I took my tablet" in free chat has no 'scheduled' and is skipped.)
    if etype in REMINDER_EVENTS and data.get("scheduled"):
        rtype, status = REMINDER_EVENTS[etype]
        attempt = int(data.get("attempt", 1) or 1)
        if status == "confirmed" and attempt > 1:
            status = "late"  # needed a retry before they answered
        db.record_reminder_outcome(
            device=device,
            rtype=rtype,
            label=data.get("medicine") or data.get("label") or rtype,
            scheduled_hhmm=data["scheduled"],
            status=status,
            source=data.get("source", "voice"),
            event_time=db._parse_time(e.get("timestamp")),
            attempt=int(data.get("attempts", attempt) or attempt) if status == "missed" else attempt,
        )

    return jsonify(ok=True, id=saved["id"]), 201


@events_bp.get("/events")
def list_events():
    limit = int(request.args.get("limit", 50))
    devices = [d for d in request.args.get("devices", "").split(",") if d] or None
    return jsonify(db.get_events(limit, devices=devices))
