"""
SAGE on Nodus: the missed-reminder pattern check, run as a Nodus function that the Flask backend calls.

    nodus run    nodus_jobs/sage_nodus.py    # test once (the app is removed afterwards)
    nodus deploy nodus_jobs/sage_nodus.py    # keep it running so the backend can call it

The backend (backend/nodus_bridge.py) calls it with Function.from_name("sage", "pattern_check").
If Nodus can't be reached, the backend runs the same pattern_check_logic() locally, so the demo never
breaks, and the dashboard says where it actually ran.

Input: a plain list of dicts (oldest first), one per reminder:
    {"scheduled_at": "2026-10-20T04:00:00+00:00", "status": "confirmed" | "late" | "missed",
     "delay_min": 6.0 or None, "attempt": 1}
Pure Python on purpose: no pandas / numpy, so the Nodus function needs no extra packages.
"""
from datetime import datetime

BASELINE_WEEKS = 4          # her "normal" = her first four weeks, like the ML model
MAX_DELAY_MIN = 89          # after 90 min a reminder counts as missed


def _mean(xs):
    return sum(xs) / len(xs) if xs else 0.0


def pattern_check_logic(reminders):
    rows = []
    for r in reminders or []:
        try:
            t = datetime.fromisoformat(str(r["scheduled_at"]).replace("Z", "+00:00"))
        except (KeyError, ValueError):
            continue
        rows.append((t, r.get("status"), r.get("delay_min"), int(r.get("attempt") or 1)))
    if not rows:
        return {"status": "no_data", "records": 0}
    rows.sort(key=lambda x: x[0])
    start = rows[0][0].date()

    weeks = {}
    for t, status, delay, attempt in rows:
        w = (t.date() - start).days // 7
        weeks.setdefault(w, []).append((t, status, delay, attempt))
    # leave out a final week with under 3 days of data (a half week isn't a fair comparison)
    last = max(weeks)
    if last > 0 and len({x[0].date() for x in weeks[last]}) < 3:
        weeks.pop(last)

    def summary(items):
        delays = [min(float(d), MAX_DELAY_MIN) for _, s, d, _ in items if s != "missed" and d is not None]
        return {
            "reminders": len(items),
            "missed_rate": round(_mean([1.0 if s == "missed" else 0.0 for _, s, _, _ in items]), 3),
            "late_rate": round(_mean([1.0 if s == "late" else 0.0 for _, s, _, _ in items]), 3),
            "avg_delay_min": round(_mean(delays), 1),
            "avg_repeats": round(_mean([max(0, a - 1) for _, _, _, a in items]), 2),
        }

    ordered = [summary(weeks[w]) | {"week": w} for w in sorted(weeks)]
    if len(ordered) <= BASELINE_WEEKS:
        return {"status": "learning_baseline", "records": len(rows), "weeks": len(ordered),
                "message": f"Needs {BASELINE_WEEKS + 1}+ weeks of history; has {len(ordered)}."}

    base_items = [x for w in sorted(weeks)[:BASELINE_WEEKS] for x in weeks[w]]
    base = summary(base_items)
    # a week is "above her normal" if misses, delay or repeats clearly rose against her own baseline
    for wk in ordered:
        wk["above_normal"] = bool(
            wk["missed_rate"] >= base["missed_rate"] + 0.15
            or wk["avg_delay_min"] >= max(base["avg_delay_min"] * 2, base["avg_delay_min"] + 10)
            or wk["avg_repeats"] >= base["avg_repeats"] + 0.5
        )
    recent = ordered[BASELINE_WEEKS:]
    streak = 0
    for wk in reversed(recent):
        if not wk["above_normal"]:
            break
        streak += 1
    current = recent[-1]
    return {
        "status": "flag" if streak >= 2 else ("watch" if streak == 1 else "normal"),
        "records": len(rows),
        "weeks": len(ordered),
        "weeks_above_normal_in_a_row": streak,
        "baseline": base,
        "this_week": current,
        "weekly": recent[-4:],
    }


# ---- the Nodus app ----
# The backend imports this file only for pattern_check_logic() (its local fallback). It sets
# SAGE_NODUS_LOGIC_ONLY=1 first, so the Nodus app below is only built by `nodus run` / `nodus deploy`,
# and nothing here can stop the backend from starting.
import os

nodus = None
if not os.getenv("SAGE_NODUS_LOGIC_ONLY"):
    import nodus  # noqa: F811  (`nodus run` needs the SDK: pip install nodus-compute)

if nodus is not None:
    app = nodus.App("sage")

    @app.function(timeout="5m", max_cost=0.5)
    def pattern_check(reminders: list) -> dict:
        return pattern_check_logic(reminders)

    @app.local_entrypoint()
    def main():
        from datetime import timedelta, timezone
        now = datetime.now(timezone.utc)
        demo = []
        for d in range(49, -1, -1):            # 7 weeks: 4 normal, then 3 drifting
            drifting = d < 21
            for slot, hour in enumerate((4, 16)):
                missed = drifting and (d + slot) % 3 == 0
                demo.append({"scheduled_at": (now - timedelta(days=d)).replace(hour=hour, minute=0).isoformat(),
                             "status": "missed" if missed else "confirmed",
                             "delay_min": None if missed else (25 if drifting else 4),
                             "attempt": 3 if missed else (2 if drifting else 1)})
        print(pattern_check.remote(demo))
