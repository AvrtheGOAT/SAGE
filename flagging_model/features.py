"""
Turns raw reminder events into weekly features.

Core idea: compare each person to THEIR OWN first month (the baseline), not to a
generic population threshold. Someone who has always missed 1 in 10 doses is not
declining; someone who went from 1 in 50 to 1 in 5 might be.
"""
import numpy as np
import pandas as pd

BASELINE_WEEKS = 4      # first month = "learning their normal"
METRICS = ["miss_rate", "late_rate", "mean_latency", "latency_std",
           "mean_prompts", "dup_rate"]
# Floors so a perfectly consistent baseline doesn't make tiny changes look huge
STD_FLOOR = {"miss_rate": 0.03, "late_rate": 0.03, "mean_latency": 2.0,
             "latency_std": 2.0, "mean_prompts": 0.15, "dup_rate": 0.02}

FEATURE_COLS = (
    [f"z_{m}" for m in METRICS]
    + [f"z3_{m}" for m in METRICS]
    + ["miss_slope_4w", "latency_slope_4w", "weeks_above_baseline"]
)


def weekly_metrics(events: pd.DataFrame) -> pd.DataFrame:
    df = events.copy()
    df["scheduled_at"] = pd.to_datetime(df["scheduled_at"])
    df["responded_at"] = pd.to_datetime(df["responded_at"])
    start = df["scheduled_at"].min().normalize()
    df["week"] = ((df["scheduled_at"] - start).dt.days // 7).astype(int)
    df["latency"] = (df["responded_at"] - df["scheduled_at"]).dt.total_seconds() / 60
    df["missed"] = df["status"].eq("missed")
    df["late"] = df["status"].eq("late")

    g = df.groupby("week")
    wk = pd.DataFrame({
        "miss_rate": g["missed"].mean(),
        "late_rate": g["late"].mean(),
        "mean_latency": g["latency"].mean(),
        "latency_std": g["latency"].std(),
        "mean_prompts": g["repeat_prompts"].mean(),
        "dup_rate": g["duplicate_confirm"].mean(),
        "n_events": g.size(),
    }).fillna(0.0)
    return wk


def _slope(y):
    if len(y) < 2:
        return 0.0
    return float(np.polyfit(np.arange(len(y)), y, 1)[0])


def build_features(events: pd.DataFrame) -> pd.DataFrame:
    """Returns one row per week AFTER the baseline month, with deviation features."""
    wk = weekly_metrics(events)
    if len(wk) <= BASELINE_WEEKS:
        return pd.DataFrame(columns=["week"] + FEATURE_COLS + METRICS)

    base = wk.iloc[:BASELINE_WEEKS]
    mu = base[METRICS].mean()
    sd = pd.Series({m: max(base[m].std(), STD_FLOOR[m]) for m in METRICS})

    z = (wk[METRICS] - mu) / sd
    z3 = z.rolling(3, min_periods=1).mean()       # smooths one-off bad weeks

    rows = []
    above_streak = 0
    for w in wk.index[BASELINE_WEEKS:]:
        hist = wk.loc[max(0, w - 3):w]
        above = (z.loc[w, "miss_rate"] > 1.0) or (z.loc[w, "mean_latency"] > 1.0)
        above_streak = above_streak + 1 if above else 0
        row = {"week": int(w)}
        row.update({f"z_{m}": z.loc[w, m] for m in METRICS})
        row.update({f"z3_{m}": z3.loc[w, m] for m in METRICS})
        row["miss_slope_4w"] = _slope(hist["miss_rate"].values)
        row["latency_slope_4w"] = _slope(hist["mean_latency"].values)
        row["weeks_above_baseline"] = above_streak
        # raw values + baseline, kept for human-readable explanations
        row.update({m: wk.loc[w, m] for m in METRICS})
        row.update({f"base_{m}": mu[m] for m in METRICS})
        rows.append(row)
    return pd.DataFrame(rows)
