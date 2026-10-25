"""
escalation.py: what happens when a fall or SOS alert gets no response.

  t = 0      alert appears on the family dashboard, wearable siren on
  t = 60 s   backup contact (from the guardian profile) is alerted
  t = 120 s  emergency services are called

The family can stop this at any point ("I'm checking on her", "Call ambulance", "False alarm"),
and the patient can cancel by pressing the SOS button twice.

ESCALATION_MODE in .env:
  demo (default)  every step is recorded and shown on the dashboard, but no SMS is sent and
                  no real call is placed. Use this for the hackathon: an automatic call to 108
                  during a demo would be a real false emergency call.
  live            calls place_call() / send_sms() below. They need a telephony provider
                  (e.g. Twilio, Exotel) wired in before they do anything.
"""
import os
import threading
import time
from datetime import datetime, timezone

import db

MODE = os.getenv("ESCALATION_MODE", "demo").lower()
CHECK_EVERY_SECONDS = 5


def send_sms(phone: str, text: str) -> bool:
    """Plug a provider in here for live mode. Returns True if the message was sent."""
    print(f"[escalation] SMS provider not configured; would text {phone}: {text}")
    return False


def place_call(number: str, text: str) -> bool:
    """Plug a provider in here for live mode. Returns True if the call was placed."""
    print(f"[escalation] Call provider not configured; would call {number}: {text}")
    return False


def _aware(dt):
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def run_once():
    now = datetime.now(timezone.utc)
    guardian = db.get_profile("guardian")
    for a in db.get_unhandled_urgent():
        patient = db.patient_for_device(a.get("device"))          # the elder this alert is about
        who = patient.get("preferred_name") or patient.get("name") or "the patient"
        done = {s["step"] for s in a.get("escalation", [])}
        what = "a fall" if a["kind"] == "fall" else "an SOS"

        if "secondary" not in done and a.get("secondary_at") and now >= _aware(a["secondary_at"]):
            name, phone = guardian.get("secondary_name"), guardian.get("secondary_phone")
            primary = guardian.get("name", "the primary guardian")
            if name and phone:
                text = f"SAGE: {who} has {what} alert and {primary} hasn't responded. Please check on {who} now."
                sent = MODE == "live" and send_sms(phone, text)
                detail = f"No response from {primary}. " + (f"Texted {name} ({phone})." if sent
                         else f"Alerted backup contact {name} ({phone}){' (demo mode, no SMS sent)' if MODE != 'live' else ' (SMS provider not set up)'}.")
            else:
                detail = f"No response from {primary}, and no backup contact is saved in the guardian profile."
            db.add_escalation_step(a["_id"], "secondary", detail)
            print(f"[escalation] {detail}")

        if "services" not in done and a.get("services_at") and now >= _aware(a["services_at"]):
            number = patient.get("ambulance_number") or "108"
            mins = round(db.SERVICES_AFTER / 60, 1)
            text = f"Emergency at the home of {patient.get('name', who)}, {patient.get('address', 'address not saved')}. {what.capitalize()} alert with no family response."
            called = MODE == "live" and place_call(number, text)
            detail = (f"No family response in {mins:g} min. Called emergency services ({number})." if called
                      else f"No family response in {mins:g} min. Would call emergency services ({number}) now"
                           f"{' (demo mode, no real call placed)' if MODE != 'live' else ', but the call provider is not set up'}.")
            db.add_escalation_step(a["_id"], "services", detail)
            print(f"[escalation] {detail}")


def _loop():
    while True:
        try:
            run_once()
        except Exception as e:  # never let the checker die; the database may be briefly unreachable
            print(f"[escalation] check failed: {e.__class__.__name__}: {e}")
        time.sleep(CHECK_EVERY_SECONDS)


_started = False


def start():
    global _started
    if _started:
        return
    _started = True
    threading.Thread(target=_loop, name="sage-escalation", daemon=True).start()
    print(f"[escalation] running in {MODE} mode (backup contact after {db.SECONDARY_AFTER}s, services after {db.SERVICES_AFTER}s)")
