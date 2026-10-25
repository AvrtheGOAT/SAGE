"""
fake_wearable.py: pretends to be the SAGE wearable (ESP32) so you can test everything without hardware.

Run from C:\\SAGE (backend must be running):
    python tools\\fake_wearable.py

It sends a heart-rate / SpO2 reading every 3 s and shows whether the siren would be on.
Type a letter and press Enter:
    f = fall          s = SOS (single press)      c = cancel SOS (double press)
    h = high heart rate (125)   l = low oxygen (89%)   n = back to normal
    p = pause sending (wearable goes "offline")    q = quit
"""
import os
import random
import sys
import threading
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")
URL = os.getenv("SAGE_URL", "http://127.0.0.1:5000")
HEAD = {"X-Device-Key": os.getenv("DEVICE_KEY", "")}
DEVICE = "wearable1"

state = {"mode": "normal", "paused": False, "quit": False, "hr": 76.0, "spo2": 97.0}
commands = []


def post(path, body):
    try:
        r = requests.post(f"{URL}{path}", json=body, headers=HEAD, timeout=3)
        if r.status_code == 401:
            print("!! Backend rejected the device key. DEVICE_KEY in backend\\.env must be set.")
        return r
    except requests.RequestException as e:
        print(f"!! Can't reach the backend at {URL}: {e.__class__.__name__}. Is app.py running?")
        return None


def reader():
    while not state["quit"]:
        try:
            commands.append(input().strip().lower())
        except EOFError:
            state["quit"] = True


def reading(fall=False):
    m = state["mode"]
    target_hr = 125 if m == "high" else 76
    target_o2 = 89 if m == "low" else 97
    state["hr"] += (target_hr - state["hr"]) * 0.4 + random.uniform(-2, 2)
    state["spo2"] = max(80, min(100, state["spo2"] + (target_o2 - state["spo2"]) * 0.5 + random.uniform(-0.6, 0.6)))
    return {"device": DEVICE, "heart_rate": round(state["hr"]), "spo2": round(state["spo2"]), "fall": fall}


def main():
    print("Fake wearable running. Type a letter and press Enter:\n"
          "  f = fall    s = SOS    c = cancel SOS (double press)\n"
          "  h = high heart rate    l = low oxygen    n = normal    p = pause / resume    q = quit\n")
    threading.Thread(target=reader, daemon=True).start()
    last = 0.0
    while not state["quit"]:
        while commands:
            c = commands.pop(0)
            if c == "q":
                state["quit"] = True
            elif c == "f":
                d = reading(fall=True)
                r = post("/api/readings", d)
                print(f">> FALL sent (HR {d['heart_rate']})", "" if r is None else r.status_code)
            elif c == "s":
                r = post("/api/emergency", {"device": DEVICE})
                print(">> SOS pressed, siren ON locally", "" if r is None else r.status_code)
            elif c == "c":
                r = post("/api/emergency/cancel", {"device": DEVICE})
                print(">> Double press: cancel sent ->", None if r is None else r.json())
            elif c in ("h", "l", "n"):
                state["mode"] = {"h": "high", "l": "low", "n": "normal"}[c]
                print(f">> Vitals now: {state['mode']}")
            elif c == "p":
                state["paused"] = not state["paused"]
                print(">> Sending", "PAUSED (dashboard should show wearable offline after ~30 s)" if state["paused"] else "resumed")
            elif c:
                print("?? Unknown key. Use f s c h l n p q")
        if not state["paused"] and time.time() - last >= 3:
            last = time.time()
            d = reading()
            post("/api/readings", d)
            try:
                siren = requests.get(f"{URL}/api/commands/{DEVICE}", headers=HEAD, timeout=3).json().get("siren")
            except Exception:
                siren = "?"
            print(f"   HR {d['heart_rate']:>3} bpm  SpO2 {d['spo2']:>3}%   siren: {'ON  <<<' if siren is True else 'off' if siren is False else siren}")
        time.sleep(0.2)
    print("Stopped.")


if __name__ == "__main__":
    if not HEAD["X-Device-Key"]:
        print("Note: DEVICE_KEY is empty in backend\\.env, so requests are sent without a key.")
    main()
