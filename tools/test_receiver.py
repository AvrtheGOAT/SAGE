"""
test_receiver.py: send sample band packets to the SAGE receiver, from any laptop on the same WiFi.
Use it to check the backend side before (or while) the band's WiFi code is being written.

    python test_receiver.py http://192.168.43.20:5000 your-device-key
(first argument = the laptop running app.py, second = DEVICE_KEY from backend/.env)
"""
import sys
import time

import requests

url = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/") + "/api/wearable"
key = sys.argv[2] if len(sys.argv) > 2 else ""
H = {"X-Device-Key": key}

steps = [
    ("vitals", {"device": "wearable1", "bpm": 76, "finger": True, "activity": 0.4, "mic": 900}),
    ("vitals + GPS", {"device": "wearable1", "bpm": 78, "finger": True, "gps": {"fix": True, "lat": 19.13, "lng": 72.84, "sats": 6}}),
    ("SOS SENT", {"device": "wearable1", "bpm": 92, "event": "SOS SENT", "event_id": int(time.time())}),
    ("SOS resent (should say duplicate)", {"device": "wearable1", "bpm": 92, "event": "SOS SENT", "event_id": int(time.time())}),
    ("I'M OK (double tap)", {"device": "wearable1", "event": "I'M OK", "event_id": int(time.time()) + 1}),
]
print(f"Sending to {url}\n")
for label, body in steps:
    try:
        r = requests.post(url, json=body, headers=H, timeout=5)
        print(f"{label:<36} {r.status_code}  {r.text.strip()[:140]}")
        if r.status_code == 401:
            print("  -> wrong or missing device key"); break
    except requests.RequestException as e:
        print(f"{label:<36} FAILED: {e.__class__.__name__}. Is app.py running, same WiFi, firewall allowing Python?"); break
    time.sleep(1.5)
print("\nAll 200s with siren true after SOS and false after I'M OK = the receiver works.")
