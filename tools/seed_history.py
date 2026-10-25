"""
seed_history.py: fills MongoDB with 7 weeks of realistic past data so the calendar, weekly chart,
day details and memory flag have something to show. Everything it adds is tagged demo=True.

Run from C:\\SAGE:
    python tools\\seed_history.py           add the demo history (weeks 1-4 normal, last 3 weeks declining)
    python tools\\seed_history.py --clear   remove everything this script added (your real data stays)
"""
import random
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))
from dotenv import load_dotenv  # noqa: E402

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")
import db  # noqa: E402

VOICE = "sage-home-01"
WEARABLE = "wearable1"
DAYS = 49
SCHEDULE = [("checkin", "Morning check-in", 9, 0), ("medicine", "BP tablet", 9, 30), ("medicine", "Diabetes tablet", 21, 0)]


def clear():
    n = sum(c.delete_many({"demo": True}).deleted_count for c in (db.reminders, db.readings, db.alerts, db.events))
    print(f"Removed {n} demo records.")


def seed():
    random.seed(7)
    now = datetime.now().astimezone()
    reminders, readings, events = [], [], []
    for d in range(DAYS, -1, -1):
        day = (now - timedelta(days=d)).replace(hour=0, minute=0, second=0, microsecond=0)
        declining = d < 21                          # last three weeks drift away from her normal (model needs 2 full weeks)
        p_miss = 0.30 if declining else 0.04
        p_late = 0.25 if declining else 0.08
        for kind, label, hh, mm in SCHEDULE:
            due = day.replace(hour=hh, minute=mm)
            if due > now:
                continue
            r = random.random()
            if r < p_miss:
                status, replied, attempt = "missed", None, 3
            elif r < p_miss + p_late:
                status, attempt = "late", random.choice([2, 3])
                replied = due + timedelta(minutes=random.randint(18, 45) if declining else random.randint(16, 25))
            else:
                status, attempt = "confirmed", 1
                replied = due + timedelta(minutes=random.randint(1, 9 if declining else 5))
            reminders.append({"device": VOICE, "type": kind, "text": label, "status": status, "attempt": attempt,
                              "scheduled_at": due.astimezone(timezone.utc), "responded_at": replied and replied.astimezone(timezone.utc),
                              "source": None if status == "missed" else "voice", "demo": True})
            if kind == "checkin" and status != "missed":
                events.append({"type": "checkin_completed", "device_id": VOICE, "demo": True,
                               "data": {"mood": random.choice(["good", "good", "okay"] if not declining else ["okay", "bad", "good"])},
                               "timestamp": replied.astimezone(timezone.utc), "received_at": replied.astimezone(timezone.utc)})
        for hour in range(7, 22):                   # hourly vitals while she's awake
            t = day.replace(hour=hour, minute=random.randint(0, 59))
            if t > now:
                break
            readings.append({"device": WEARABLE, "heart_rate": random.randint(64, 88), "spo2": random.randint(95, 99),
                             "fall": False, "timestamp": t.astimezone(timezone.utc), "demo": True})
    # two past alerts, already handled by the family
    for days_ago, kind, msg, outcome in [(9, "fall", "Fall detected by wearable", "checking"),
                                         (3, "reminder_missed", "Missed Diabetes tablet (scheduled 21:00)", "handled")]:
        t = (now - timedelta(days=days_ago)).replace(hour=16 if kind == "fall" else 22, minute=12).astimezone(timezone.utc)
        db.alerts.insert_one({"device": WEARABLE if kind == "fall" else VOICE, "kind": kind, "message": msg, "created_at": t,
                              "acknowledged": True, "outcome": outcome, "acknowledged_at": t + timedelta(minutes=3),
                              "escalation": [], "demo": True})
        if kind == "fall":
            readings.append({"device": WEARABLE, "heart_rate": 112, "spo2": 96, "fall": True, "timestamp": t, "demo": True})
    db.reminders.insert_many(reminders)
    db.readings.insert_many(readings)
    if events:
        db.events.insert_many(events)
    missed_recent = sum(1 for r in reminders if r["status"] == "missed" and r["scheduled_at"] > datetime.now(timezone.utc) - timedelta(days=14))
    print(f"Added {len(reminders)} reminders, {len(readings)} readings, {len(events)} check-in moods and 2 past alerts "
          f"over {DAYS} days ({missed_recent} missed in the last 2 weeks). Refresh the dashboard.")


if __name__ == "__main__":
    clear() if "--clear" in sys.argv else seed()
