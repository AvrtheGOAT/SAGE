"""SAGE voice assistant - entry point.

Controls (laptop stand-in for the ESP32 push button):
  Enter        -> talk to SAGE
  m + Enter    -> fire the first medicine reminder now (demo)
  c + Enter    -> fire the morning check-in now (demo)
  q + Enter    -> quit
"""
import queue
import threading

import audio_io
import backend_client
import brain
import config
from phrases import t
from reminders import ReminderScheduler

events: queue.Queue = queue.Queue()


def keyboard_loop():
    while True:
        cmd = input().strip().lower()
        events.put(("key", cmd))


def handle_talk():
    audio_io.speak(t("yes"))
    text = audio_io.listen(config.LISTEN_WAIT_SECONDS)
    if not text:
        audio_io.speak(t("not_heard"))
        return

    # Conversation mode: after each reply, keep the mic on for FOLLOWUP_SECONDS so the
    # person can keep talking without pressing the button again. Silence ends the conversation.
    while text:
        print(f"YOU : {text}")
        backend_client.post_event("voice_interaction")  # just "it happened" - no content stored

        if brain.is_obvious_emergency(text):
            backend_client.post_event("emergency", reason="emergency phrase detected", source="voice")
            audio_io.speak(t("alerting"))
            return
        audio_io.speak(brain.respond(text))

        if config.FOLLOWUP_SECONDS <= 0:
            return
        text = audio_io.listen(config.FOLLOWUP_SECONDS)


def handle_reminder(scheduler: ReminderScheduler, r, attempt: int):
    if r.kind == "checkin":
        audio_io.speak(t("checkin"))
        text = audio_io.listen(config.REMINDER_LISTEN_SECONDS)
        if text:
            print(f"YOU : {text}")
            if brain.is_obvious_emergency(text):
                backend_client.post_event("emergency", reason="during check-in", source="voice")
                audio_io.speak(t("alerting"))
                return
            audio_io.speak(brain.respond(text, context="This is the morning check-in. Log their mood."))
            return
    else:  # medicine
        audio_io.speak(t("med_ask", label=r.label))
        text = audio_io.listen(config.REMINDER_LISTEN_SECONDS)
        if text:
            print(f"YOU : {text}")
            answer = brain.classify_confirmation(text)
            if answer == "yes":
                backend_client.post_event("medicine_confirmed", medicine=r.label,
                                          attempt=attempt, scheduled=r.time, source="reminder")
                audio_io.speak(t("med_thanks"))
                return
            if answer == "no":
                audio_io.speak(t("med_take_now", label=r.label))

    # No answer, "no", or unclear -> retry, then escalate
    if attempt < config.REMINDER_MAX_ATTEMPTS:
        scheduler.retry_later(r, attempt + 1)
    else:
        event = "checkin_missed" if r.kind == "checkin" else "reminder_missed"
        backend_client.post_event(event, label=r.label, scheduled=r.time, attempts=attempt)
        audio_io.speak(t("tell_family"))


def drop_stray_enters():
    """Enter presses made while SAGE was busy talking/listening would otherwise
    start a new conversation each. Throw them away; keep reminders and other keys."""
    kept = []
    while not events.empty():
        e = events.get()
        if e != ("key", ""):
            kept.append(e)
    for e in kept:
        events.put(e)


def main():
    audio_io.load_models()
    scheduler = ReminderScheduler(events)
    scheduler.start()
    threading.Thread(target=keyboard_loop, daemon=True).start()

    audio_io.speak(t("ready"))
    print(__doc__)

    while True:
        kind, *payload = events.get()
        if kind == "key":
            cmd = payload[0]
            if cmd == "q":
                break
            elif cmd == "m":
                meds = [r for r in config.REMINDERS if r.kind == "medicine"]
                if meds: scheduler.fire_now(meds[0])
            elif cmd == "c":
                checks = [r for r in config.REMINDERS if r.kind == "checkin"]
                if checks: scheduler.fire_now(checks[0])
            else:
                handle_talk()
                drop_stray_enters()
        elif kind == "reminder":
            r, attempt = payload
            handle_reminder(scheduler, r, attempt)
            drop_stray_enters()


if __name__ == "__main__":
    main()
