"""
nodus_bridge.py: runs SAGE's missed-reminder pattern check on Nodus, with a local fallback.

  1. The backend turns an elder's reminder history into plain dicts.
  2. It calls the deployed Nodus function  Function.from_name("sage", "pattern_check").remote(...)
  3. If that fails (not deployed, no login, no internet, no credits), it runs the very same
     pattern_check_logic() locally, so the dashboard always has a result.
  Every result records where it ran ("nodus" or "local"), so the dashboard never claims Nodus
  usage that didn't happen.

It runs in a background thread and only when the elder's reminder history changes.

.env (backend):
    NODUS_ENABLED=1     try Nodus first (default). 0 = always run locally (e.g. offline demo).
Setup: pip install nodus-compute, nodus login, nodus deploy nodus_jobs/sage_nodus.py
"""
import os
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))   # so "nodus_jobs" is importable
os.environ["SAGE_NODUS_LOGIC_ONLY"] = "1"        # import just the logic; don't build the Nodus app here
from nodus_jobs.sage_nodus import pattern_check_logic  # noqa: E402

import db  # noqa: E402

ENABLED = os.getenv("NODUS_ENABLED", "1") == "1"
APP_NAME, FUNCTION_NAME = "sage", "pattern_check"
runs = db._db["nodus_runs"]          # history of every check (handy to show judges real usage)
_latest = {}                         # device -> latest result
_busy = set()
_lock = threading.Lock()


def _records(device):
    out = []
    for r in db.reminders.find({"device": device}).sort("scheduled_at", 1):
        sched, reply = r.get("scheduled_at"), r.get("responded_at")
        delay = None
        if reply and sched and r.get("status") != "missed":
            delay = round((reply - sched).total_seconds() / 60, 1)
        out.append({"scheduled_at": sched.isoformat() if sched else None, "status": r.get("status"),
                    "delay_min": delay, "attempt": r.get("attempt") or 1})
    return out


def _call_nodus(records):
    import nodus                                   # imported here so a missing SDK just means "run locally"
    fn = nodus.Function.from_name(APP_NAME, FUNCTION_NAME)
    return fn.remote(records)


def _run(device, sig):
    started = time.time()
    records = _records(device)
    ran_on, error = "local", None
    try:
        if not ENABLED:
            raise RuntimeError("NODUS_ENABLED=0")
        result = _call_nodus(records)
        if not isinstance(result, dict):
            raise RuntimeError(f"unexpected reply from Nodus: {type(result).__name__}")
        ran_on = "nodus"
    except Exception as e:
        error = f"{e.__class__.__name__}: {e}"[:300]
        result = pattern_check_logic(records)
    entry = {"device": device, "sig": sig, "ran_on": ran_on, "error": error, "result": result,
             "duration_ms": int((time.time() - started) * 1000), "at": datetime.now(timezone.utc)}
    _latest[device] = entry
    try:
        runs.insert_one(dict(entry))
    except Exception:
        pass
    print(f"[nodus] pattern check for {device}: ran on {ran_on} in {entry['duration_ms']} ms -> {result.get('status')}"
          + (f"  (Nodus not used: {error})" if error and ENABLED else ""))
    with _lock:
        _busy.discard(device)


def request(device, sig):
    """Start a check in the background if the reminder history changed since the last one."""
    prev = _latest.get(device)
    if prev and prev["sig"] == sig:
        return
    with _lock:
        if device in _busy:
            return
        _busy.add(device)
    threading.Thread(target=_run, args=(device, sig), name="sage-nodus", daemon=True).start()


def status(device):
    e = _latest.get(device)
    if not e:
        return {"ran_on": None, "busy": device in _busy}
    return {"ran_on": e["ran_on"], "busy": device in _busy, "at": e["at"].isoformat(), "duration_ms": e["duration_ms"],
            "error": e["error"] if e["ran_on"] == "local" else None, "result": e["result"]}


def usage_count():
    """How many checks actually ran on Nodus (for the judges / submission)."""
    return runs.count_documents({"ran_on": "nodus"})
