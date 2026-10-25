"""
Synthetic reminder-event generator for SAGE's memory-decline flagging model.

There is no public dataset of "elderly person's medicine-reminder responses over
months", so we simulate one. Each simulated person gets their OWN normal
(some people always forget the 2pm pill) plus realistic noise and occasional
bad weeks (illness, travel, a wedding in the family). Declining users drift
gradually away from their own normal after an onset week.

Event schema matches what the backend stores in MongoDB (collection: reminder_events):
{
  user_id, type ("medicine" | "checkin"),
  scheduled_at (datetime), responded_at (datetime | None),
  status ("taken" | "late" | "missed"),
  repeat_prompts (int, how many times SAGE had to re-ask),
  duplicate_confirm (bool, user tried to confirm a dose already confirmed)
}
"""
from datetime import datetime, timedelta
import numpy as np
import pandas as pd

# Daily schedule: (type, hour, minute)
SCHEDULE = [
    ("medicine", 8, 0),
    ("checkin", 9, 0),
    ("medicine", 14, 0),
    ("medicine", 21, 0),
]
LATE_THRESHOLD_MIN = 30   # responded, but more than 30 min after the reminder
MISS_THRESHOLD_MIN = 90   # no response within 90 min -> missed
MAX_PROMPTS = 3


def simulate_user(user_id, weeks=16, declining=False, onset_week=None,
                  seed=None, start=datetime(2026, 6, 1)):
    rng = np.random.default_rng(seed)

    # This person's own normal
    base_miss = rng.uniform(0.01, 0.10)
    base_lat = rng.uniform(3, 12)            # typical response latency, minutes
    base_repeat = rng.uniform(0.1, 0.6)      # avg re-prompts needed
    base_dup = rng.uniform(0.0, 0.02)        # duplicate-confirmation rate
    severity = rng.uniform(0.5, 1.5)         # how fast decline progresses

    # 0-2 "bad weeks" for everyone (illness, travel) -> spikes that are NOT decline
    n_bad = rng.integers(0, 3)
    bad_weeks = set(rng.choice(np.arange(4, weeks), size=n_bad, replace=False).tolist())

    events = []
    for day in range(weeks * 7):
        w = day // 7
        d = 0.0
        if declining and onset_week is not None and w >= onset_week:
            d = severity * (w - onset_week + 1) / 8.0   # gradual ramp
        bump = 1.0 if w in bad_weeks else 0.0
        day_noise = rng.normal(0, 0.02)

        for rtype, hh, mm in SCHEDULE:
            sched = start + timedelta(days=day, hours=hh, minutes=mm)
            p_miss = np.clip(base_miss * (1 + 2 * d) + 0.07 * d + 0.15 * bump + day_noise, 0, 0.9)
            missed = rng.random() < p_miss

            if missed:
                responded, status, prompts = None, "missed", MAX_PROMPTS
            else:
                lat = rng.exponential(base_lat * (1 + 1.5 * d + 0.8 * bump))
                lat = min(lat, MISS_THRESHOLD_MIN - 1)
                responded = sched + timedelta(minutes=float(lat))
                status = "late" if lat > LATE_THRESHOLD_MIN else "taken"
                prompts = int(min(rng.poisson(base_repeat * (1 + 2 * d + bump)), MAX_PROMPTS))

            dup = (rtype == "medicine" and not missed
                   and rng.random() < base_dup + 0.06 * d)

            events.append({
                "user_id": user_id, "type": rtype,
                "scheduled_at": sched, "responded_at": responded,
                "status": status, "repeat_prompts": prompts,
                "duplicate_confirm": bool(dup),
            })

    meta = {"user_id": user_id, "declining": declining, "onset_week": onset_week,
            "bad_weeks": sorted(bad_weeks)}
    return pd.DataFrame(events), meta


def simulate_population(n_users=600, weeks=16, decline_frac=0.4, seed=42):
    rng = np.random.default_rng(seed)
    frames, metas = [], []
    for i in range(n_users):
        declining = rng.random() < decline_frac
        onset = int(rng.integers(5, weeks - 3)) if declining else None  # never inside baseline month
        df, meta = simulate_user(f"sim_{i:04d}", weeks, declining, onset,
                                 seed=int(rng.integers(1e9)))
        frames.append(df)
        metas.append(meta)
    return pd.concat(frames, ignore_index=True), pd.DataFrame(metas)
