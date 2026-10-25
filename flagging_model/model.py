"""
SAGE memory-decline flagging model.

  python model.py train      -> trains on simulated users, prints evaluation, saves flag_model.joblib

Usage from Flask:
  from flagging_model.model import assess_user
  result = assess_user(events_df)   # events for ONE user, from MongoDB
"""
import sys
from pathlib import Path
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import GradientBoostingClassifier
from sklearn.metrics import roc_auc_score, classification_report

try:
    from .features import build_features, FEATURE_COLS, BASELINE_WEEKS
    from .simulate import simulate_population
except ImportError:  # running as a script
    from features import build_features, FEATURE_COLS, BASELINE_WEEKS
    from simulate import simulate_population

MODEL_PATH = Path(__file__).with_name("flag_model.joblib")
RISK_THRESHOLD = 0.6
CONSECUTIVE_WEEKS = 2     # must stay high 2 weeks running before family is alerted
DETECTION_LAG = 2         # label positive from onset+2 weeks (early drift is invisible)

EXPLAIN = {
    "miss_rate": ("Missed reminders", "pct"),
    "late_rate": ("Late responses (>30 min)", "pct"),
    "mean_latency": ("Average response time", "min"),
    "mean_prompts": ("Times SAGE had to repeat a reminder", "num"),
    "dup_rate": ("Tried to confirm a dose already taken", "pct"),
}


def _dataset(events, meta):
    rows = []
    for _, m in meta.iterrows():
        f = build_features(events[events.user_id == m.user_id])
        f["user_id"] = m.user_id
        f["label"] = 0
        if m.declining:
            f.loc[f.week >= m.onset_week + DETECTION_LAG, "label"] = 1
        rows.append(f)
    return pd.concat(rows, ignore_index=True)


def _apply_persistence(risks):
    flags, streak = [], 0
    for r in risks:
        streak = streak + 1 if r >= RISK_THRESHOLD else 0
        flags.append(streak >= CONSECUTIVE_WEEKS)
    return flags


def train(n_users=600, seed=42):
    print(f"Simulating {n_users} users...")
    events, meta = simulate_population(n_users=n_users, seed=seed)
    data = _dataset(events, meta)

    users = meta.user_id.values
    rng = np.random.default_rng(seed)
    test_users = set(rng.choice(users, size=len(users) // 4, replace=False))
    tr = data[~data.user_id.isin(test_users)]
    te = data[data.user_id.isin(test_users)]

    clf = GradientBoostingClassifier(n_estimators=200, max_depth=3,
                                     learning_rate=0.05, random_state=seed)
    clf.fit(tr[FEATURE_COLS], tr.label)

    p = clf.predict_proba(te[FEATURE_COLS])[:, 1]
    print(f"\nWeek-level ROC-AUC (held-out users): {roc_auc_score(te.label, p):.3f}")
    print(classification_report(te.label, p >= RISK_THRESHOLD,
                                target_names=["normal", "drifting"], digits=3))

    # User-level evaluation: what the family actually experiences
    te = te.assign(risk=p)
    tm = meta[meta.user_id.isin(test_users)].set_index("user_id")
    false_alarm, detected, lags = 0, 0, []
    for uid, g in te.groupby("user_id"):
        g = g.sort_values("week")
        flags = _apply_persistence(g.risk.values)
        first = next((wk for wk, fl in zip(g.week, flags) if fl), None)
        if tm.loc[uid, "declining"]:
            if first is not None:
                detected += 1
                lags.append(first - tm.loc[uid, "onset_week"])
        elif first is not None:
            false_alarm += 1
    n_dec = int(tm.declining.sum()); n_ok = len(tm) - n_dec
    print("User-level (with 2-consecutive-week rule):")
    print(f"  Declining users flagged:  {detected}/{n_dec} ({detected/n_dec:.0%})")
    print(f"  Healthy users false-flag: {false_alarm}/{n_ok} ({false_alarm/n_ok:.0%})")
    if lags:
        print(f"  Median weeks from onset to flag: {np.median(lags):.1f}")

    importances = sorted(zip(FEATURE_COLS, clf.feature_importances_), key=lambda x: -x[1])
    print("\nTop features:", ", ".join(f"{n} ({v:.2f})" for n, v in importances[:5]))

    joblib.dump(clf, MODEL_PATH)
    print(f"\nSaved model -> {MODEL_PATH}")
    return clf


def _fmt(v, kind):
    return f"{v*100:.0f}%" if kind == "pct" else (f"{v:.0f} min" if kind == "min" else f"{v:.1f}")


def _reasons(row, top=3):
    cands = []
    for m, (label, kind) in EXPLAIN.items():
        zv = row[f"z3_{m}"]
        if zv > 1.0:
            cands.append((zv, f"{label}: {_fmt(row[f'base_{m}'], kind)} -> {_fmt(row[m], kind)}"))
    return [t for _, t in sorted(cands, reverse=True)[:top]]


def assess_user(events: pd.DataFrame, clf=None) -> dict:
    """Weekly risk for ONE user. Needs > 4 weeks of data (baseline month)."""
    clf = clf or joblib.load(MODEL_PATH)
    feats = build_features(events)
    if feats.empty:
        n_weeks = 0 if events.empty else (pd.to_datetime(events.scheduled_at).max()
                                          - pd.to_datetime(events.scheduled_at).min()).days // 7 + 1
        return {"status": "learning_baseline",
                "message": f"Learning this person's normal routine ({n_weeks}/{BASELINE_WEEKS + 1} weeks).",
                "weekly": []}

    feats["risk"] = clf.predict_proba(feats[FEATURE_COLS])[:, 1]
    feats["flagged"] = _apply_persistence(feats.risk.values)
    last = feats.iloc[-1]

    if last.flagged:
        status = "flag"
        message = ("Reminder responses have drifted from this person's usual pattern for "
                   f"{CONSECUTIVE_WEEKS}+ weeks. This is not a diagnosis, but it may be worth "
                   "mentioning to their doctor at the next visit.")
    elif last.risk >= RISK_THRESHOLD:
        status = "watch"
        message = "Unusual week. SAGE will keep watching before alerting family."
    else:
        status = "normal"
        message = "Reminder responses are within this person's usual range."

    return {
        "status": status,
        "risk": round(float(last.risk), 3),
        "message": message,
        "reasons": _reasons(last) if status != "normal" else [],
        "weekly": [{"week": int(r.week), "risk": round(float(r.risk), 3),
                    "flagged": bool(r.flagged), "miss_rate": round(float(r.miss_rate), 3)}
                   for r in feats.itertuples()],
    }


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "train":
        train()
    else:
        print("usage: python model.py train")
