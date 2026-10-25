"""
Demo for judges: two simulated people over 14 weeks.
  - Person A: healthy, but has a bad week (fever) -> SAGE should NOT alert family
  - Person B: gradual decline starting week 7     -> SAGE should flag it

  python demo.py              # print the comparison in the terminal
  python demo.py --seed-mongo # also write both histories into MongoDB for the dashboard
"""
import sys
import numpy as np
import pandas as pd

try:
    from .simulate import simulate_user
    from .model import assess_user
except ImportError:
    from simulate import simulate_user
    from model import assess_user


def make_demo_people():
    healthy, _ = simulate_user("demo_healthy", weeks=14, declining=False, seed=7)
    # inject a fever week (week 9): many misses, slow responses
    wk = (healthy.scheduled_at - healthy.scheduled_at.min()).dt.days // 7
    rng = np.random.default_rng(1)
    fever = (wk == 9) & (rng.random(len(healthy)) < 0.35)
    healthy.loc[fever, ["status", "responded_at", "repeat_prompts"]] = ["missed", None, 3]

    declining, _ = simulate_user("demo_declining", weeks=14, declining=True,
                                 onset_week=7, seed=11)
    return healthy, declining


def show(name, result):
    print(f"\n=== {name} ===")
    for w in result["weekly"]:
        bar = "#" * int(w["risk"] * 30)
        flag = "  <-- FAMILY ALERTED" if w["flagged"] else ""
        print(f"week {w['week']:>2} | miss {w['miss_rate']*100:4.0f}% | risk {w['risk']:.2f} {bar}{flag}")
    print(f"STATUS: {result['status'].upper()} - {result['message']}")
    for r in result.get("reasons", []):
        print(f"  - {r}")


def seed_mongo(*dfs, uri="mongodb://localhost:27017", db_name="sage"):
    from pymongo import MongoClient
    col = MongoClient(uri)[db_name]["reminder_events"]
    for df in dfs:
        col.delete_many({"user_id": df.user_id.iloc[0]})
        recs = df.astype(object).where(pd.notna(df), None).to_dict("records")
        col.insert_many(recs)
        print(f"Seeded {len(recs)} events for {df.user_id.iloc[0]}")


if __name__ == "__main__":
    healthy, declining = make_demo_people()
    show("Person A - healthy, one fever week", assess_user(healthy))
    show("Person B - gradual decline from week 7", assess_user(declining))
    if "--seed-mongo" in sys.argv:
        seed_mongo(healthy, declining)
