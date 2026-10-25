"""
wearable_route.py: the receiver for the SAGE band. One address for everything the band sends.

    POST /api/wearable   or   POST /readings   (the team firmware's address)
    header  X-Device-Key: <DEVICE_KEY from .env>   (optional on /readings if WEARABLE_KEY_OPTIONAL=1)

Body (every field optional except device; send whatever the band has):
    {
      "device":   "wearable1",     also accepted: "device_id" ("sage-01" is shown as Kamala's band)
      "bpm":      76,              also accepted: "heart_rate".  0 or missing = no reading
      "spo2":     97,              0 or missing = no reading
      "finger":   true,            finger on the sensor
      "activity": 0.42,            the firmware's "act" value (movement level)
      "gps":      {"fix": true, "lat": 19.13, "lng": 72.84, "sats": 7},   or flat "lat"/"lon"/"sats"/"gps_fix"
      "mic":      1200,            microphone level
      "battery":  87,              percent
      "event":    "FALL",          the firmware's events all work: FALL, SOS, SOS_CANCEL, ACK, TALK, DEMO
                                   (also "FALL!", "DEMO FALL", "SOS SENT", "I'M OK", "OK NOTED"; case doesn't matter)
      "event_id": 17               optional: increase it for every new event; a resent packet with the same
                                   id is recognised and not counted twice
    }

Reply:
    {"ok": true, "siren": true, "event": "sos", "result": "alert created"}
    siren = keep the buzzer going (true while a fall / SOS is still unanswered on the dashboard).
    The band can use this instead of polling /api/commands.
"""
from flask import Blueprint, request

import db

wearable_bp = Blueprint("wearable", __name__)

EVENT_ALIASES = {
    "fall": "fall", "fall!": "fall", "fall_detected": "fall",
    "demo_fall": "demo_fall", "demo fall": "demo_fall", "demofall": "demo_fall",
    "sos": "sos", "sos sent": "sos", "sos_sent": "sos", "help": "sos",
    "cancel": "cancel", "sos cancel": "cancel", "sos_cancel": "cancel", "i'm ok": "cancel", "im ok": "cancel",
    "i am ok": "cancel", "double_tap": "cancel",
    "ok": "ok", "ok noted": "ok", "ok_noted": "ok", "ack": "ok",
    "talk": "talk", "listening": "talk",
    "demo": "demo_walk", "demo walk": "demo_walk", "demo_walk": "demo_walk",
}

# The team's firmware calls the band "sage-01"; the dashboard knows Kamala's band as "wearable1".
# Add more pairs here if you build a second band.
DEVICE_ALIASES = {"sage-01": "wearable1"}


def _num(v, lo=None, hi=None, places=3):
    """Number or None. Out-of-range or junk values become None instead of breaking the dashboard."""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return None
    if (lo is not None and x < lo) or (hi is not None and x > hi):
        return None
    return round(x) if x.is_integer() else round(x, places)


def _gps(d):
    g = d.get("gps") if isinstance(d.get("gps"), dict) else {}
    # 6 decimals = about 10 cm; fewer would blur the demo walk's ~33 m steps
    lat = _num(g.get("lat", d.get("lat")), -90, 90, places=6)
    lng = _num(g.get("lng", g.get("lon", d.get("lng", d.get("lon")))), -180, 180, places=6)
    fix = g.get("fix", d.get("gps_fix"))
    sats = _num(g.get("sats", d.get("sats")), 0, 99)
    if lat is None and lng is None and fix is None and sats is None:
        return None
    has_pos = lat is not None and lng is not None and (lat, lng) != (0, 0)   # 0,0 = module has no fix yet
    out = {"fix": bool(fix) and has_pos if fix is not None else has_pos, "sats": sats}
    if has_pos:
        out.update(lat=lat, lng=lng)
    return out


@wearable_bp.post("/api/wearable")
@wearable_bp.post("/readings")          # the address the team's firmware posts to (guide section 9)
def receive():
    d = request.get_json(silent=True)
    if not isinstance(d, dict):
        return {"ok": False, "error": "send a JSON object"}, 400
    raw_device = str(d.get("device") or d.get("device_id") or "wearable1")[:40]
    device = DEVICE_ALIASES.get(raw_device, raw_device)
    raw_event = str(d.get("event") or "").strip().lower()
    event = EVENT_ALIASES.get(raw_event) if raw_event else None
    event_id = d.get("event_id")

    hr = _num(d.get("bpm", d.get("heart_rate")), 25, 250)
    spo2 = _num(d.get("spo2"), 50, 100)
    reading = {
        "device": device,
        "heart_rate": hr if hr else None,
        "spo2": spo2 if spo2 else None,
        "fall": event in ("fall", "demo_fall"),
        "finger": bool(d["finger"]) if "finger" in d else None,
        "activity": _num(d.get("activity", d.get("act")), 0, 1000),
        "gps": _gps(d),
        "mic": _num(d.get("mic"), 0),
        "battery": _num(d.get("battery"), 0, 100),
    }

    result = None
    if raw_event and not event:
        result = f"unknown event '{raw_event}' ignored"
    elif event and db.seen_event_id(device, event_id):
        result = "duplicate (already handled)"
        reading["fall"] = False
    elif event in ("fall", "demo_fall", "sos"):
        kind = "emergency" if event == "sos" else "fall"
        if db.recent_open_urgent(device, kind):
            result = "duplicate (alert already open)"          # a retry of the same emergency
            reading["fall"] = False
        else:
            msg = {"fall": "Fall detected by the wearable", "demo_fall": "Fall detected by the wearable (demo button)",
                   "sos": "SOS sent from the wearable"}[event]
            db.create_alert(kind, msg, device=device)
            result = "alert created"
        db.save_device_event(device, event, event_id)
    elif event == "cancel":
        cancelled = db.cancel_latest_urgent(device)
        result = "cancelled" if cancelled else "nothing open to cancel"
        db.save_device_event(device, "cancel", event_id)
    elif event == "ok":
        db.save_device_event(device, "button_ok", event_id)      # "I'm OK / took my medicine" tap
        result = "noted"
    elif event == "talk":
        db.save_device_event(device, "button_talk", event_id)    # placeholder until voice upload exists
        result = "noted (voice upload not built yet)"
    elif event == "demo_walk":
        db.save_device_event(device, "demo_walk", event_id)      # demo button: fake GPS walk-out started
        result = "noted"

    # store a reading only when the packet carries telemetry (an event-only packet shouldn't blank the vitals)
    telemetry = ("bpm", "heart_rate", "spo2", "finger", "activity", "act", "gps", "lat", "lng", "mic", "battery")
    if reading["fall"] or any(k in d for k in telemetry):
        db.save_reading(reading)
    siren = db.siren_on(device)

    # one readable line per packet, so whoever is debugging the band can see exactly what arrived
    g = reading["gps"]
    print(f"[wearable] {device} bpm={hr or '-'} spo2={spo2 or '-'} finger={reading['finger']} "
          f"act={reading['activity']} gps={'fix' if g and g.get('fix') else 'no'} mic={reading['mic']} "
          f"event={event or raw_event or '-'}{f' ({result})' if result else ''} -> siren={siren}")
    return {"ok": True, "siren": siren, "event": event, "result": result}
