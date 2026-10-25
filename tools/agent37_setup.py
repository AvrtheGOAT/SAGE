"""
agent37_setup.py: creates SAGE's care agent on Agent37 (run once).

    1. Get an API key at  https://www.agent37.com/dashboard/cloud/api-keys
    2. Put it in backend\\.env as   AGENT37_API_KEY=sk_live_...
    3. From C:\\SAGE run:           python tools\\agent37_setup.py

It creates one Hermes agent instance with a small AI budget ($2/month cap), waits until it's
ready, sends a test message, and writes AGENT37_INSTANCE_ID into backend\\.env.
For the Agent37 challenge submission you need that instance id and a dashboard screenshot.
"""
import sys
import time
from pathlib import Path

import requests
from dotenv import dotenv_values

ENV = Path(__file__).resolve().parent.parent / "backend" / ".env"
cfg = dotenv_values(ENV)
KEY = (cfg.get("AGENT37_API_KEY") or "").strip()
INSTANCE = (cfg.get("AGENT37_INSTANCE_ID") or "").strip()
API = "https://api.agent37.com/v1"
MONTHLY_CAP_MICROS = 2_000_000          # $2/month ceiling for the agent's AI calls

if not KEY.startswith("sk_"):
    sys.exit(f"Put AGENT37_API_KEY=sk_live_... in {ENV} first (from agent37.com/dashboard/cloud/api-keys).")
hub = {"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
box = lambda iid: {"X-Agent37-Key": KEY, "Content-Type": "application/json"}


def save_instance_id(iid):
    text = ENV.read_text(encoding="utf-8") if ENV.exists() else ""
    lines = [l for l in text.splitlines() if not l.startswith("AGENT37_INSTANCE_ID=")]
    lines.append(f"AGENT37_INSTANCE_ID={iid}")
    ENV.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Saved AGENT37_INSTANCE_ID={iid} to backend\\.env")


if INSTANCE:
    print(f"Using existing instance {INSTANCE} from .env")
else:
    print("Creating SAGE's care agent on Agent37 (this can take a minute)...")
    body = {"template": "agent37-hermes", "name": "sage-care-agent-kamala",
            "budget": {"monthly_cap_micros": MONTHLY_CAP_MICROS}, "auto_sleep": True}
    r = requests.post(f"{API}/instances", headers=hub, json=body, timeout=300)
    if r.status_code == 400 and "auto_sleep" in r.text:            # older API without auto-sleep: create without it
        body.pop("auto_sleep")
        r = requests.post(f"{API}/instances", headers=hub, json=body, timeout=300)
    if r.status_code not in (200, 201):
        sys.exit(f"Couldn't create the instance (HTTP {r.status_code}):\n  {r.text[:400]}\n"
                 "  401 = wrong key; 402 = add funds / credit in the Agent37 billing dashboard.")
    inst = r.json()
    INSTANCE = inst["id"]
    print(f"Created instance {INSTANCE} (status: {inst.get('status')})")
    save_instance_id(INSTANCE)

# make sure the agent may spend a little on AI (the default cap is $0, which refuses every model call)
try:
    b = requests.get(f"{API}/instances/{INSTANCE}/budget", headers=hub, timeout=30).json()
    if (b.get("monthly_cap_micros") or 0) < MONTHLY_CAP_MICROS:
        requests.patch(f"{API}/instances/{INSTANCE}/budget", headers=hub, json={"monthly_cap_micros": MONTHLY_CAP_MICROS}, timeout=30)
        print("Raised the agent's monthly AI budget cap to $2")
except Exception as e:
    print(f"(couldn't check the budget: {e})")

print("Waiting for the agent to be ready...", end="", flush=True)
for _ in range(60):
    try:
        h = requests.get(f"https://{INSTANCE}.agent37.app/v1/health", headers=box(INSTANCE), timeout=200)
        if h.ok and h.json().get("healthy"):
            print(" ready")
            break
    except Exception:
        pass
    print(".", end="", flush=True)
    time.sleep(5)
else:
    sys.exit("\nThe agent didn't report healthy in 5 minutes. Check it in the Agent37 dashboard, then run this again.")

print("Sending a test message...")
r = requests.post(f"https://{INSTANCE}.agent37.app/v1/responses", headers=box(INSTANCE),
                  json={"input": "Without using any tools, reply with exactly: SAGE care agent ready.", "reasoning_effort": "low"},
                  timeout=(15, 240))
d = r.json() if r.ok else {}
if d.get("status") == "completed":
    print(f"Agent replied: {d.get('output_text', '').strip()}   (cost ${((d.get('usage') or {}).get('cost_usd') or 0):.4f})")
    print(f"\nDone. Restart app.py. For the Agent37 submission: instance id = {INSTANCE}, "
          "plus a screenshot of this instance in the Agent37 dashboard.")
else:
    err = (d.get("error") or {}) if d else {}
    print(f"Test message failed: HTTP {r.status_code} {err.get('code', '')} {err.get('message', r.text[:300])}")
    print("If it mentions budget or balance: top up the wallet at agent37.com/dashboard/cloud/billing.")
