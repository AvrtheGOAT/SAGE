"""
Flask blueprint for the memory-decline flagging model.

In backend/app.py:
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).resolve().parent.parent))   # adds SAGE/ to the path

    from flagging_model.api import create_flagging_blueprint
    app.register_blueprint(create_flagging_blueprint(db))           # db = your PyMongo database

Endpoints:
    GET  /risk/<user_id>             -> risk status, reasons, weekly history
    POST /reminder-event             -> log one reminder response (from ESP32 / voice assistant)
"""
from datetime import datetime
import joblib
import pandas as pd
from flask import Blueprint, jsonify, request

from .model import assess_user, MODEL_PATH


def create_flagging_blueprint(db):
    bp = Blueprint("flagging", __name__)
    events_col = db["reminder_events"]

    try:
        clf = joblib.load(MODEL_PATH)
    except FileNotFoundError:
        clf = None
        print("[flagging] flag_model.joblib not found - run: python flagging_model/model.py train")

    @bp.get("/risk/<user_id>")
    def risk(user_id):
        if clf is None:
            return jsonify({"error": "model not trained"}), 503
        docs = list(events_col.find({"user_id": user_id}, {"_id": 0}))
        if not docs:
            return jsonify({"status": "no_data", "message": "No reminder history yet.", "weekly": []})
        return jsonify(assess_user(pd.DataFrame(docs), clf=clf))

    @bp.post("/reminder-event")
    def log_event():
        data = request.get_json(force=True)
        required = {"user_id", "type", "scheduled_at", "status"}
        missing = required - data.keys()
        if missing:
            return jsonify({"error": f"missing fields: {sorted(missing)}"}), 400

        doc = {
            "user_id": data["user_id"],
            "type": data["type"],                                   # "medicine" | "checkin"
            "scheduled_at": datetime.fromisoformat(data["scheduled_at"]),
            "responded_at": (datetime.fromisoformat(data["responded_at"])
                             if data.get("responded_at") else None),
            "status": data["status"],                               # "taken" | "late" | "missed"
            "repeat_prompts": int(data.get("repeat_prompts", 0)),
            "duplicate_confirm": bool(data.get("duplicate_confirm", False)),
        }
        events_col.insert_one(doc)
        return jsonify({"ok": True}), 201

    return bp
