"""
agent37.py: SAGE's always-on care agent, hosted on Agent37 (https://www.agent37.com/docs).

One Agent37 instance (a hosted Hermes agent) is Kamala's care agent. When the memory model's
verdict changes, the backend sends it the model's findings and it writes a short, warm,
non-diagnostic update for the family. All updates go into ONE conversation (session), so the
agent remembers earlier weeks and can say whether things improved or got worse.

Privacy: only her first name and the model's findings are sent. No conditions, medicines,
vitals or audio leave SAGE.

.env (backend):
    AGENT37_API_KEY=sk_live_...        from agent37.com/dashboard/cloud/api-keys
    AGENT37_INSTANCE_ID=ab12cd34ef     created by:  python tools/agent37_setup.py
"""
import json
import os
import threading
import time
from datetime import datetime, timezone

import requests

import db

KEY = os.getenv("AGENT37_API_KEY", "").strip()
INSTANCE = os.getenv("AGENT37_INSTANCE_ID", "").strip()
MIN_GAP_SECONDS = 10 * 60          # don't ask more than every 10 min unless the verdict level changes

summaries = db._db["agent_summaries"]
state = db._db["agent_state"]
_lock = threading.Lock()
_busy = False
last_error = None


def enabled():
    return bool(KEY and INSTANCE)


def latest(patient_id=None):
    doc = summaries.find_one({"patient_id": patient_id} if patient_id else {}, sort=[("created_at", -1)])
    return db._clean(doc) if doc else None


def _session_id(patient_id=None):
    s = state.find_one({"_id": f"care_agent:{patient_id}" if patient_id else "care_agent"})
    return s.get("session_id") if s else None


def ask(text, timeout=240, patient_id=None):
    """One turn with the care agent. Each elder has their own conversation, so it remembers that person."""
    body = {"input": text, "reasoning_effort": "low", "metadata": {"app": "sage", "purpose": "family_summary"}}
    sid = _session_id(patient_id)
    if sid:
        body["session_id"] = sid
    r = requests.post(f"https://{INSTANCE}.agent37.app/v1/responses",
                      headers={"X-Agent37-Key": KEY, "Content-Type": "application/json"},
                      json=body, timeout=(15, timeout))
    if r.status_code != 200:
        raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")
    data = r.json()
    if data.get("status") != "completed":                      # a failed turn still comes back as HTTP 200
        err = data.get("error") or {}
        raise RuntimeError(f"{err.get('code', data.get('status'))}: {err.get('message', '')[:200]}")
    if data.get("session_id"):
        key = f"care_agent:{patient_id}" if patient_id else "care_agent"
        state.update_one({"_id": key}, {"$set": {"session_id": data["session_id"]}}, upsert=True)
    return (data.get("output_text") or "").strip(), data


def _prompt(facts):
    return (
        f"You are SAGE's care agent for {facts['name']}, an older woman who lives alone. "
        f"Her family ({facts['guardian']}) reads what you write on the SAGE dashboard.\n"
        "Rules: do not browse the web or use any tools; use only the facts below. Write 3 to 4 short "
        "sentences of plain, warm English with no bullet points or headings. Say what changed compared with "
        "HER OWN usual routine, and give one gentle, practical suggestion for the family. Never diagnose and "
        "never mention Alzheimer's or dementia. If the level is 'concern', suggest mentioning it at her next "
        "doctor visit. If you wrote earlier updates in this conversation, say briefly whether things look "
        "better, worse or the same since then. Reply with only the update text.\n\n"
        f"Facts from SAGE's memory model this week:\n{json.dumps(facts, indent=1)}"
    )


def _run(facts, sig):
    global _busy, last_error
    try:
        text, data = ask(_prompt({k: v for k, v in facts.items() if k != "patient_id"}), patient_id=facts.get("patient_id"))
        if not text:
            raise RuntimeError("the agent returned an empty reply")
        usage = data.get("usage") or {}
        summaries.insert_one({"text": text, "sig": sig, "level": facts["level"], "patient_id": facts.get("patient_id"),
                              "created_at": datetime.now(timezone.utc),
                              "response_id": data.get("id"), "session_id": data.get("session_id"),
                              "cost_usd": usage.get("cost_usd"), "instance_id": INSTANCE})
        last_error = None
        print(f"[agent37] new family summary ({len(text)} chars, ${usage.get('cost_usd') or 0:.4f})")
    except Exception as e:
        last_error = str(e)
        print(f"[agent37] summary failed: {e}")
    finally:
        with _lock:
            _busy = False


def request_summary(facts, force=False):
    """Ask for a new summary in the background if the findings changed (or force=True)."""
    global _busy
    if not enabled():
        return "not_configured"
    sig = json.dumps([facts.get("level"), facts.get("reasons"), round(facts.get("risk") or 0, 1)])
    prev = latest(facts.get("patient_id"))
    if not force and prev:
        age = (datetime.now(timezone.utc) - db._parse_time(prev["created_at"])).total_seconds()
        if prev.get("sig") == sig or (prev.get("level") == facts.get("level") and age < MIN_GAP_SECONDS):
            return "up_to_date"
    with _lock:
        if _busy:
            return "busy"
        _busy = True
    threading.Thread(target=_run, args=(facts, sig), name="sage-agent37", daemon=True).start()
    return "started"


def status_block(patient_id=None):
    """What the dashboard shows under the model's verdict."""
    s = latest(patient_id)
    return {"configured": enabled(), "busy": _busy, "error": last_error,
            "text": s["text"] if s else None, "created_at": s["created_at"] if s else None,
            "instance_id": INSTANCE or None}
