"""Sends events to the Flask backend. Never crashes the assistant if the backend is down:
failed events are queued to a local file and flushed on the next successful send.

Privacy: only event types + small structured fields are sent. No audio, ever.
"""
import json
import threading
from datetime import datetime, timezone
from pathlib import Path

import requests

import config

_QUEUE_FILE = Path(__file__).with_name("offline_events.jsonl")
_lock = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _send(event: dict) -> bool:
    try:
        headers = {"X-Device-Key": config.DEVICE_KEY} if config.DEVICE_KEY else {}
        r = requests.post(f"{config.BACKEND_URL}/events", json=event, headers=headers, timeout=3)
        if r.status_code == 401:
            print("[backend] rejected: DEVICE_KEY in voice/.env doesn't match backend/.env")
        return r.ok
    except requests.RequestException:
        return False


def _flush_queue():
    if not _QUEUE_FILE.exists():
        return
    pending = [json.loads(l) for l in _QUEUE_FILE.read_text().splitlines() if l.strip()]
    remaining = [e for e in pending if not _send(e)]
    if remaining:
        _QUEUE_FILE.write_text("".join(json.dumps(e) + "\n" for e in remaining))
    else:
        _QUEUE_FILE.unlink()


def post_event(event_type: str, **data) -> bool:
    """event_type examples: emergency, medicine_confirmed, reminder_missed,
    checkin_completed, checkin_missed, voice_interaction"""
    event = {
        "device_id": config.DEVICE_ID,
        "type": event_type,
        "timestamp": _now_iso(),
        "data": data,
    }
    with _lock:
        ok = _send(event)
        if ok:
            _flush_queue()
        else:
            with _QUEUE_FILE.open("a") as f:
                f.write(json.dumps(event) + "\n")
            print(f"[backend] offline, queued '{event_type}'")
        return ok
