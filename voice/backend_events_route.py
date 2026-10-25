"""Drop-in Flask route for the SAGE backend: receives voice-assistant events and stores them
in MongoDB. Register it in your existing app:

    from backend_events_route import events_bp
    app.register_blueprint(events_bp)

Emergency / missed events get an 'alert' flag so the Streamlit dashboard can show a banner.
"""
from datetime import datetime

from flask import Blueprint, jsonify, request
from pymongo import MongoClient

db = MongoClient("mongodb://localhost:27017")["sage"]
events_bp = Blueprint("events", __name__)

ALERT_TYPES = {"emergency", "reminder_missed", "checkin_missed"}


@events_bp.post("/events")
def receive_event():
    e = request.get_json(force=True)
    if not e or "type" not in e:
        return jsonify(error="missing type"), 400
    e["received_at"] = datetime.utcnow()
    e["alert"] = e["type"] in ALERT_TYPES
    e["acknowledged"] = False
    db.events.insert_one(e)
    if e["alert"]:
        print(f"!!! ALERT: {e['type']} {e.get('data')}")  # hook SMS/notification here
    return jsonify(ok=True), 201


@events_bp.get("/events")
def list_events():
    limit = int(request.args.get("limit", 50))
    docs = list(db.events.find({}, {"_id": 0}).sort("received_at", -1).limit(limit))
    return jsonify(docs)
