# SAGE – Memory-Decline Flagging Model

Flags when a person's responses to reminders (medicine, daily check-in) drift away from
**their own** normal pattern over several weeks. It alerts family only after 2 consecutive
high-risk weeks, and never claims a diagnosis.

## Files
| File | What it does |
|---|---|
| `simulate.py` | Generates synthetic reminder histories (healthy vs. gradually declining users) |
| `features.py` | Weekly metrics compared against each person's first-month baseline |
| `model.py` | Trains the GradientBoosting classifier; `assess_user()` gives risk + reasons |
| `api.py` | Flask blueprint: `GET /risk/<user_id>`, `POST /reminder-event` |
| `demo.py` | Judges' demo: healthy person with a fever week vs. declining person |

## Setup
```bash
pip install scikit-learn pandas joblib flask pymongo
cd flagging_model
python model.py train        # ~10 s, creates flag_model.joblib
python demo.py               # terminal demo
python demo.py --seed-mongo  # also loads demo users into MongoDB (db "sage")
```

## Data
No public dataset exists for reminder-response behaviour labelled with later cognitive
decline, so the model is trained on simulated data (600 users × 16 weeks) built on
assumed decline patterns: more misses, slower responses, more re-prompts, repeated
confirmations. The event schema matches the live `reminder_events` MongoDB collection,
so the model can be retrained on real usage data once deployed.

## Results (held-out simulated users)
- Declining users flagged: ~85%, median ~3 weeks after onset
- Healthy users falsely flagged: 0%

## Disclaimer
This flags a change in routine. It is **not** a medical diagnosis of Alzheimer's or any
other condition. The suggested action is to mention it to a doctor.

## How it's connected in SAGE
- `backend/memory.py` loads this model when the backend starts (and trains it automatically the first
  time, ~30 s, if `flag_model.joblib` doesn't exist).
- It reads the live `reminders` collection (written by the voice assistant) and translates it to the
  schema above: confirmed -> taken, the voice assistant's attempt count -> repeat_prompts.
- The dashboard's **Memory & routine** tab calls `GET /api/memory-status` and shows the verdict,
  the reasons and the weekly risk.
- `tools/seed_history.py` adds 7 weeks of demo history (4 normal, 3 declining) so the flag shows in a demo.
- `api.py` here is the original standalone blueprint; the live backend uses `backend/memory.py` instead.
