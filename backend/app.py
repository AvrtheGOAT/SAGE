"""
app.py — the SAGE backend. Run:  python app.py
Everything (ESP32, voice assistant, dashboard) talks to this server.
"""
import hmac
import os
import secrets
from datetime import timedelta
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, Response, jsonify, redirect, render_template, request, session

load_dotenv()

import db  # noqa: E402  (after load_dotenv so db sees .env)
import escalation  # noqa: E402
import memory  # noqa: E402
from events_route import events_bp  # noqa: E402
from wearable_route import wearable_bp  # noqa: E402

# The dashboard lives in sage/frontend (one level up from this file)
FRONTEND = Path(__file__).resolve().parent.parent / "frontend"

app = Flask(
    __name__,
    template_folder=str(FRONTEND),   # frontend/index.html
    static_folder=str(FRONTEND),     # frontend/js/... served at /static/js/...
    static_url_path="/static",
)
app.config["MAX_CONTENT_LENGTH"] = 11 * 1024 * 1024   # report uploads up to ~10 MB
app.register_blueprint(events_bp)   # /events  (voice assistant)
app.register_blueprint(wearable_bp)  # /api/wearable  (the band)

# ---------- privacy: who may use which address ----------
# Family members log in (session cookie). The ESP32 and voice assistant can't log in, so they
# send a shared device key in the X-Device-Key header instead.
app.secret_key = os.getenv("SECRET_KEY") or secrets.token_hex(32)
if not os.getenv("SECRET_KEY"):
    print("[auth] SECRET_KEY not set in .env: everyone will be logged out whenever the server restarts.")
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax", PERMANENT_SESSION_LIFETIME=timedelta(days=7))
DEVICE_KEY = os.getenv("DEVICE_KEY", "")
if not DEVICE_KEY:
    print("[auth] DEVICE_KEY not set in .env: device addresses are open to anyone on the network.")

PUBLIC = {"/login", "/api/auth/status", "/api/auth/login", "/api/auth/setup", "/health", "/api/status"}
# The team's firmware doesn't send the key yet. WEARABLE_KEY_OPTIONAL=1 lets POST /readings in without it
# (fine on your own hotspot for the demo; add the header to the firmware to switch this off).
WEARABLE_KEY_OPTIONAL = os.getenv("WEARABLE_KEY_OPTIONAL", "0") == "1"
if WEARABLE_KEY_OPTIONAL:
    print("[auth] WEARABLE_KEY_OPTIONAL=1: the band may post to /readings without the device key.")
DEVICE_ROUTES = [("POST", "/readings"), ("POST", "/api/wearable"), ("POST", "/api/readings"), ("POST", "/api/emergency"), ("GET", "/api/commands/"), ("POST", "/events")]


@app.before_request
def require_login():
    path, method = request.path, request.method
    if path in PUBLIC or path.startswith("/static/"):
        return None
    if any(method == m and path.startswith(p) for m, p in DEVICE_ROUTES):
        sent = request.headers.get("X-Device-Key", "")
        keyless_ok = path == "/readings" and not sent and WEARABLE_KEY_OPTIONAL
        if DEVICE_KEY and not keyless_ok and not hmac.compare_digest(sent, DEVICE_KEY):
            return {"error": "device key missing or wrong"}, 401
        return None
    if session.get("uid") and db.get_user(session["uid"]):
        return None
    if path.startswith("/api/") or path.startswith("/events"):
        return {"error": "Please sign in."}, 401
    return redirect("/login")


@app.get("/login")
def login_page():
    if session.get("uid") and db.get_user(session["uid"]):
        return redirect("/patients")
    return render_template("login.html")


@app.get("/api/auth/status")
def auth_status():
    """Tells the login page whether to show 'sign in' or 'create the family account'."""
    return {"needs_setup": db.user_count() == 0}


@app.post("/api/auth/setup")
def auth_setup():
    if db.user_count() > 0:
        return {"error": "The family account already exists. Sign in instead."}, 409
    d = request.get_json(silent=True) or {}
    name, email, pw = (d.get("name") or "").strip(), (d.get("email") or "").strip(), d.get("password") or ""
    if not name or "@" not in email:
        return {"error": "Enter your name and a valid email address."}, 400
    if len(pw) < 8:
        return {"error": "Use a password of at least 8 characters."}, 400
    user = db.create_user(name, email, pw)
    session.permanent = True
    session["uid"] = user["id"]
    if not db.get_profile("guardian").get("phone"):
        db.save_profile("guardian", {"name": name, "email": email})
    return {"ok": True, "user": user}


@app.post("/api/auth/login")
def auth_login():
    d = request.get_json(silent=True) or {}
    user = db.check_login(d.get("email"), d.get("password"))
    if not user:
        return {"error": "That email and password don't match. Check them and try again."}, 401
    session.permanent = True
    session["uid"] = user["id"]
    return {"ok": True, "user": user}


@app.post("/api/auth/logout")
def auth_logout():
    session.clear()
    return {"ok": True}


@app.get("/api/me")
def me():
    return jsonify(db.get_user(session["uid"]))


# ---------- elders (one family can look after several) ----------

def _devices_arg():
    raw = request.args.get("devices", "")
    return [d for d in raw.split(",") if d] or None


@app.get("/api/patients")
def list_patients():
    return jsonify([{**p, "status": db.patient_summary(p)} for p in db.list_patients()])


@app.post("/api/patients")
def add_patient():
    p = db.create_patient(request.get_json(silent=True) or {})
    return (jsonify(p), 201) if p else ({"error": "Add the elder's name."}, 400)


@app.get("/api/patients/<pid>")
def get_patient(pid):
    p = db.get_patient(pid)
    return jsonify(p) if p else ({"error": "not found"}, 404)


@app.put("/api/patients/<pid>")
def put_patient(pid):
    if not db.get_patient(pid):
        return {"error": "not found"}, 404
    data = request.get_json(silent=True) or {}
    if "name" in data and not (data.get("name") or "").strip():
        return {"error": "Name can't be empty."}, 400
    return jsonify(db.save_patient(pid, data))


# ---------- patient & guardian profiles ----------

@app.get("/api/profile/<kind>")
def get_profile(kind):
    if kind not in db.PROFILE_FIELDS:
        return {"error": "unknown profile"}, 404
    return jsonify(db.get_profile(kind))


@app.put("/api/profile/<kind>")
def put_profile(kind):
    if kind not in db.PROFILE_FIELDS:
        return {"error": "unknown profile"}, 404
    data = request.get_json(silent=True) or {}
    if not (data.get("name") or "").strip():
        return {"error": "Name can't be empty."}, 400
    return jsonify(db.save_profile(kind, data))


# ---------- health check ----------

@app.get("/")
def dashboard():
    """One elder's dashboard (frontend/index.html). Without ?p=<elder id> go to the profiles page."""
    if not request.args.get("p") or not db.get_patient(request.args["p"]):
        return redirect("/patients")
    return render_template("index.html")


@app.get("/patients")
def patients_page():
    """After sign-in: the elders this family looks after (frontend/patients.html)."""
    return render_template("patients.html")


@app.get("/api/status")
def status():
    return {"status": "SAGE backend running"}


@app.get("/health")
def health():
    try:
        db.ping()
        return {"backend": "ok", "database": "ok"}
    except Exception as e:
        return {"backend": "ok", "database": f"error: {e}"}, 500


# ---------- ESP32 wearable ----------

@app.post("/api/readings")
def post_reading():
    data = request.get_json(silent=True)
    if not data:
        return {"error": "send JSON"}, 400
    saved = db.save_reading(data)
    if saved["fall"]:
        db.create_alert("fall", "Fall detected by wearable", device=saved["device"])
        print("!!! ALERT: fall detected")
    return {"status": "ok"}


@app.post("/api/emergency")
def emergency_button():
    """ESP32 SOS button, single press. The wearable starts its siren straight away."""
    data = request.get_json(silent=True) or {}
    device = data.get("device", "wearable1")
    alert = db.create_alert("emergency", "SOS button pressed on the wearable", device=device)
    print("!!! ALERT: SOS button pressed")
    return {"status": "ok", "alert_id": alert["id"]}


@app.post("/api/emergency/cancel")
def emergency_cancel():
    """ESP32 SOS button pressed twice quickly: the patient cancels a mistaken SOS."""
    data = request.get_json(silent=True) or {}
    cancelled = db.cancel_latest_urgent(data.get("device"))
    if cancelled:
        print("--- SOS cancelled by the patient")
    return {"cancelled": bool(cancelled), "siren": db.siren_on(data.get("device"))}


@app.get("/api/commands/<device>")
def device_commands(device):
    """The wearable asks every few seconds what it should do.
    siren: keep the buzzer going (true while a fall/SOS is still unanswered)."""
    return {"siren": db.siren_on(device)}


# ---------- dashboard ----------

@app.get("/api/latest")
def latest():
    device = request.args.get("device", "wearable1")
    return jsonify(db.get_latest(device) or {})


@app.get("/api/readings/recent")
def recent():
    device = request.args.get("device", "wearable1")
    limit = int(request.args.get("limit", 30))
    return jsonify(db.get_recent_readings(device, limit))


@app.get("/api/alerts")
def get_alerts():
    return jsonify(db.get_active_alerts(devices=_devices_arg()))


@app.get("/api/alerts/history")
def alert_history():
    limit = int(request.args.get("limit", 10))
    return jsonify(db.get_alert_history(limit, devices=_devices_arg()))


@app.post("/api/alerts/<alert_id>/ack")
def ack_alert(alert_id):
    outcome = (request.get_json(silent=True) or {}).get("outcome", "handled")
    ok = db.acknowledge_alert(alert_id, outcome)
    return ({"status": "ok"}, 200) if ok else ({"error": "not found"}, 404)


@app.get("/api/reminders")
def get_reminders():
    device = request.args.get("device", "sage-home-01")
    days = int(request.args.get("days", 42))
    return jsonify(db.get_reminders(device, days))


# ---------- memory-decline model ----------

@app.get("/api/memory-status")
def memory_status():
    """The flagging model's verdict for the Memory & routine tab."""
    return jsonify(memory.status(request.args.get("device", "sage-home-01")))


@app.post("/api/memory-summary/refresh")
def memory_summary_refresh():
    """Ask the Agent37 care agent for a fresh family summary."""
    return {"result": memory.refresh_summary(request.args.get("device", "sage-home-01"))}


# ---------- calendar day details ----------

@app.get("/api/day")
def day_details():
    """start/end: ISO timestamps for the start and end of the local day (sent by the dashboard)."""
    start, end = request.args.get("start"), request.args.get("end")
    if not start or not end:
        return {"error": "start and end are required"}, 400
    return jsonify(db.get_day(
        db._parse_time(start.replace("Z", "+00:00")), db._parse_time(end.replace("Z", "+00:00")),
        wearable=request.args.get("wearable", "wearable1"), voice=request.args.get("device", "sage-home-01"),
    ))


# ---------- medical reports ----------

ALLOWED_REPORT_TYPES = ("application/pdf", "image/")


@app.get("/api/reports")
def get_reports():
    return jsonify(db.list_reports(request.args.get("p")))


@app.post("/api/reports")
def upload_report():
    f = request.files.get("file")
    title = (request.form.get("title") or "").strip()
    report_date = request.form.get("report_date") or ""
    if not f or not f.filename:
        return {"error": "Choose a PDF or photo of the report."}, 400
    if not f.mimetype.startswith(ALLOWED_REPORT_TYPES):
        return {"error": "Only PDF files and photos can be uploaded."}, 400
    if not title or len(report_date) != 10:
        return {"error": "Add a title and the date on the report."}, 400
    data = f.read()
    if len(data) > 10 * 1024 * 1024:
        return {"error": "That file is over 10 MB. Try a smaller scan or photo."}, 413
    saved = db.save_report(title, request.form.get("kind", "other"), report_date,
                           (request.form.get("notes") or "").strip(), f.filename, f.mimetype, data,
                           patient_id=request.form.get("patient_id") or None)
    return saved, 201


@app.get("/api/reports/<report_id>/file")
def report_file(report_id):
    r = db.get_report(report_id)
    if not r:
        return {"error": "not found"}, 404
    disposition = "attachment" if request.args.get("download") else "inline"
    return Response(bytes(r["data"]), mimetype=r["content_type"],
                    headers={"Content-Disposition": f'{disposition}; filename="{r["filename"]}"'})


@app.delete("/api/reports/<report_id>")
def remove_report(report_id):
    return ({"status": "ok"}, 200) if db.delete_report(report_id) else ({"error": "not found"}, 404)


@app.errorhandler(413)
def too_large(_e):
    return {"error": "That file is over 10 MB. Try a smaller scan or photo."}, 413


if __name__ == "__main__":
    # With debug=True Flask runs the file twice (a watcher + the real server); only start the checker in the real one.
    DEBUG = os.getenv("FLASK_DEBUG", "1") == "1"
    if not DEBUG or os.environ.get("WERKZEUG_RUN_MAIN") == "true":
        escalation.start()
        memory.start()
    # host 0.0.0.0 so the ESP32 and other laptops on the hotspot can reach it
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", "5000")), debug=DEBUG)
