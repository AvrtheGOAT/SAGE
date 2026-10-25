// SAGE family dashboard: live data for the Stitch design.
// ---- Settings (edit these) ----
// Names, phones and medical details come from the patient / guardian profiles (click a name to edit them).
const GREET = "guardian";   // "guardian" = "Good morning, Rohan"; "patient" = "Hello Kamala, good morning"
// Which elder this dashboard shows (from /?p=<id>) and that elder's own devices (loaded from their profile)
const PID = new URLSearchParams(location.search).get("p");
let WEARABLE_ID = "wearable1";         // the band's id (firmware device_id)
let VOICE_ID = "sage-home-01";         // the voice assistant's DEVICE_ID
const DEVS = () => encodeURIComponent(`${WEARABLE_ID},${VOICE_ID}`);
const STALE_SECONDS = 30;              // wearable counts as offline after this
const FAST_MS = 2000, SLOW_MS = 10000;

// ---- State ----
const S = { patient: {}, guardian: {}, me: null, up: null, latest: null, recent: [], alerts: [], history: [], reminders: [], events: [], memory: null, metric: "hr" };
const $ = (id) => document.getElementById(id);

// ---- Helpers ----
async function api(url, opts = {}) {
  const r = await fetch(url, { cache: "no-store", ...opts });
  if (r.status === 401) { location.href = "/login"; throw new Error("signed out"); }
  return r;
}
async function getJSON(url) {
  const r = await api(url);
  if (!r.ok) throw new Error(`${url} ${r.status}`);
  return r.json();
}
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const num = (v) => (typeof v === "number" && v > 0 ? v : null); // sensor sends 0 / -1 with no finger
function ago(iso) {
  if (!iso) return "";
  const s = Math.max(0, Math.round((Date.now() - new Date(iso)) / 1000));
  if (s < 60) return `${s}s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}
const clock = (iso) => new Date(iso).toLocaleTimeString([], { hour: "numeric", minute: "2-digit" });
function when(iso) {
  const d = new Date(iso), today = new Date().toDateString();
  const y = new Date(Date.now() - 864e5).toDateString();
  if (d.toDateString() === today) return `Today ${clock(iso)}`;
  if (d.toDateString() === y) return `Yesterday ${clock(iso)}`;
  return d.toLocaleDateString([], { day: "numeric", month: "short" }) + `, ${clock(iso)}`;
}
const wearableAge = () => (S.latest?.timestamp ? (Date.now() - new Date(S.latest.timestamp)) / 1000 : Infinity);
const wearableLive = () => wearableAge() <= STALE_SECONDS;
const isUrgent = (a) => a.kind === "fall" || a.kind === "emergency";

const TONES = {
  ok: "bg-ok-soft text-ok border-ok/30",
  warn: "bg-warn-soft text-warn border-warn/30",
  danger: "bg-danger-soft text-danger border-danger/30",
  info: "bg-info-soft text-info border-info/30",
  muted: "bg-raise text-ink-2 border-line",
};
const DOTS = { ok: "bg-ok", warn: "bg-warn", danger: "bg-danger", info: "bg-info", muted: "bg-ink-3" };
function pill(tone, text, pulse = false) {
  return `<span class="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold border whitespace-nowrap ${TONES[tone]}">
    <span class="w-1.5 h-1.5 rounded-full ${DOTS[tone]} ${pulse ? "animate-pulse" : ""}"></span>${esc(text)}</span>`;
}

// Vitals rules (simple thresholds for alerts, not medical advice)
function hrTone(v) { return v == null ? ["muted", "No reading"] : v < 50 ? ["danger", "Low"] : v > 110 ? ["danger", "High"] : ["ok", "Normal"]; }
function spo2Tone(v) { return v == null ? ["muted", "No reading"] : v < 90 ? ["danger", "Very low"] : v < 95 ? ["warn", "A little low"] : ["ok", "Normal"]; }

// ---- Chart ----
let chart;
// Theme colour from the CSS variables, e.g. token("accent", 0.5) -> "rgb(92 200 236 / 0.5)"
const token = (name, a = 1) => `rgb(${getComputedStyle(document.documentElement).getPropertyValue(`--${name}`).trim()} / ${a})`;
function themeChart() {
  if (!chart) return;
  Chart.defaults.color = token("ink-3");
  const ds = chart.data.datasets[0];
  ds.borderColor = token("accent"); ds.backgroundColor = token("accent", 0.12); ds.pointBorderColor = token("surface");
  chart.options.scales.y.grid.color = token("line");
  chart.options.scales.x.ticks.color = chart.options.scales.y.ticks.color = token("ink-3");
  renderChart();
}
function makeChart() {
  if (typeof Chart === "undefined") return;
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  Chart.defaults.font.size = 12;
  chart = new Chart($("vitals-chart"), {
    type: "line",
    data: { labels: [], datasets: [{ data: [], fill: true, tension: 0.35, borderWidth: 2.5, pointRadius: [], pointBackgroundColor: [], pointBorderWidth: 2 }] },
    options: {
      animation: false, maintainAspectRatio: false, plugins: { legend: { display: false } },
      interaction: { mode: "index", intersect: false },
      scales: { x: { grid: { display: false }, ticks: { maxTicksLimit: 6 } }, y: { grid: {}, ticks: {} } },
    },
  });
  themeChart();
}
function renderChart() {
  $("chart-empty").classList.toggle("hidden", S.recent.length > 0);
  if (!chart) return;
  const key = S.metric === "hr" ? "heart_rate" : "spo2";
  const ds = chart.data.datasets[0];
  chart.data.labels = S.recent.map((r) => clock(r.timestamp));
  ds.data = S.recent.map((r) => num(r[key]));
  ds.pointRadius = S.recent.map((r) => (r.fall ? 6 : 0));            // red dot where a fall was reported
  ds.pointBackgroundColor = S.recent.map((r) => (r.fall ? token("danger") : token("accent")));
  chart.options.scales.y.suggestedMin = S.metric === "hr" ? 50 : 88;
  chart.options.scales.y.suggestedMax = S.metric === "hr" ? 110 : 100;
  chart.update();
}
document.querySelectorAll(".metric-btn").forEach((b) => b.addEventListener("click", () => {
  S.metric = b.dataset.metric;
  document.querySelectorAll(".metric-btn").forEach((x) => {
    const on = x === b;
    x.classList.toggle("bg-raise", on); x.classList.toggle("text-accent", on);
    x.classList.toggle("text-ink-2", !on);
  });
  renderChart();
}));

// ---- Renderers ----
function renderHeader() {
  const urgent = S.alerts.some(isUrgent);
  const hr = num(S.latest?.heart_rate), o2 = num(S.latest?.spo2);
  // only judge readings that actually exist (the band may not measure SpO2 yet)
  const vitalsOff = wearableLive() && ((hr != null && hrTone(hr)[0] !== "ok") || (o2 != null && spo2Tone(o2)[0] !== "ok"));
  let tone, text;
  if (S.up === false) [tone, text] = ["muted", "Server not reachable"];
  else if (urgent) [tone, text] = ["danger", "Needs help now"];
  else if (S.alerts.length || vitalsOff) [tone, text] = ["warn", "Needs attention"];
  else if (!wearableLive()) [tone, text] = ["muted", "Wearable offline"];
  else [tone, text] = ["ok", "All good"];
  $("status-badge").outerHTML = `<span id="status-badge">${pill(tone, text, tone === "danger" || tone === "warn")}</span>`;

  $("presence-dot").className = `absolute bottom-0 right-0 w-3.5 h-3.5 rounded-full border-2 border-surface ${wearableLive() ? "bg-ok" : "bg-ink-3"}`;
  $("last-synced").textContent = S.latest ? `· last reading ${ago(S.latest.timestamp)}` : "· waiting for the wearable";
  $("wearable-pill").innerHTML = wearableLive()
    ? `<span class="material-symbols-outlined text-[15px]">wifi</span>Wearable online`
    : `<span class="material-symbols-outlined text-[15px]">wifi_off</span>${S.latest ? "Wearable offline" : "Wearable not seen yet"}`;
  $("wearable-pill").className = `hidden sm:inline-flex items-center gap-1 font-medium ${wearableLive() ? "text-ok" : "text-ink-3"}`;

  const n = S.alerts.length;
  for (const id of ["bell-count", "nav-alert-count"]) { $(id).textContent = n; $(id).classList.toggle("hidden", n === 0); }

  const ok = S.up !== false;
  $("footer-dot").className = `w-2 h-2 rounded-full ${ok && wearableLive() ? "bg-ok" : ok ? "bg-warn" : "bg-danger"}`;
  $("footer-text").textContent = !ok ? "Backend offline" : wearableLive() ? "All connected" : "Backend online · wearable offline";
}

let bannerAlertId = null, bannerAlert = null;
const ackedHere = new Set();
function renderBanner() {
  const a = S.alerts.find(isUrgent);
  const b = $("alert-banner");
  if (bannerAlertId && (!a || a.id !== bannerAlertId)) noticeClosed(bannerAlertId);   // it was handled somewhere
  b.classList.toggle("hidden", !a); b.classList.toggle("flex", !!a);
  bannerAlert = a || null;
  siren(!!a);
  if (!a) { bannerAlertId = null; return; }
  bannerAlertId = a.id;
  const who = shortName();
  $("alert-icon").textContent = a.kind === "fall" ? "personal_injury" : "sos";
  $("alert-title").textContent = `${a.kind === "fall" ? `${who} may have fallen` : `${who} pressed SOS`} at ${clock(a.created_at)}`;
  $("alert-desc").textContent = a.kind === "emergency"
    ? `${a.message}, ${ago(a.created_at)}. ${who} pressed SOS and didn't cancel it within 5 seconds. The wearable is beeping.`
    : `${a.message}, ${ago(a.created_at)}. The wearable detected an impact followed by stillness.`;
  $("alert-steps").innerHTML = (a.escalation || []).map((s) =>
    `<li class="flex gap-1.5"><span class="material-symbols-outlined text-base text-danger">${s.step === "services" ? "local_hospital" : "forward_to_inbox"}</span><span>${clock(s.at)}: ${esc(s.detail)}</span></li>`).join("");
  tickCountdown();
}
function tickCountdown() {
  const a = bannerAlert;
  if (!a) return;
  const done = new Set((a.escalation || []).map((s) => s.step));
  const left = (iso) => Math.max(0, Math.ceil((new Date(iso) - Date.now()) / 1000));
  const mmss = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const backup = S.guardian.secondary_name;
  let text = "";
  if (!done.has("secondary") && a.secondary_at && backup) text = `${backup} (backup contact) will be alerted in ${mmss(left(a.secondary_at))}. `;
  if (!done.has("services") && a.services_at) text += `Emergency services will be called in ${mmss(left(a.services_at))} unless someone responds.`;
  else if (done.has("services")) text = "The emergency services step has been reached. Respond below once someone is with her.";
  $("alert-countdown").textContent = text;
}
setInterval(tickCountdown, 1000);
async function noticeClosed(id) {
  if (ackedHere.has(id)) return;
  try {
    const hist = await getJSON(`/api/alerts/history?limit=10&devices=${DEVS()}`);
    const a = hist.find((x) => x.id === id);
    if (!a) return;
    if (a.outcome === "cancelled_by_patient") toast(`${shortName()} cancelled the SOS by pressing the button twice. The siren is off.`, "info");
    else if (a.acknowledged) toast(`The alert was handled: ${OUTCOMES[a.outcome] || "handled by family"}.`, "ok");
  } catch {}
}
document.querySelectorAll(".alert-action").forEach((el) => el.addEventListener("click", () => {
  if (bannerAlertId) { ackedHere.add(bannerAlertId); ack(bannerAlertId, el.dataset.outcome); } // the ambulance link still dials
}));
async function ack(id, outcome) {
  try { await api(`/api/alerts/${id}/ack`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ outcome }) }); } catch {}
  fastTick(); slowTick();
}

function renderVitals() {
  const live = wearableLive();
  const hr = live ? num(S.latest?.heart_rate) : null, o2 = live ? num(S.latest?.spo2) : null;
  $("hr-value").textContent = hr ?? "–";
  $("spo2-value").textContent = o2 ?? "–";
  const [ht, hl] = live ? hrTone(hr) : ["muted", "Offline"];
  const [ot, ol] = live ? spo2Tone(o2) : ["muted", "Offline"];
  $("hr-badge").innerHTML = pill(ht, hl);
  $("spo2-badge").innerHTML = pill(ot, ol);
  $("spo2-bar").style.width = `${o2 ? Math.max(0, Math.min(100, (o2 - 80) * 5)) : 0}%`; // 80% → empty, 100% → full

  const hrs = S.recent.map((r) => num(r.heart_rate)).filter((v) => v != null);
  const o2s = S.recent.map((r) => num(r.spo2)).filter((v) => v != null);
  $("hr-minmax").textContent = hrs.length ? `Min ${Math.min(...hrs)} • Max ${Math.max(...hrs)}` : "–";
  $("spo2-range").textContent = o2s.length ? `Range ${Math.min(...o2s)}–${Math.max(...o2s)}%` : "–";
  if (hrs.length > 1) {
    const lo = Math.min(...hrs) - 3, hi = Math.max(...hrs) + 3;
    $("hr-spark").setAttribute("d", hrs.map((v, i) => `${i ? "L" : "M"}${(i / (hrs.length - 1)) * 100},${22 - ((v - lo) / (hi - lo)) * 20}`).join(" "));
  } else $("hr-spark").setAttribute("d", "");

  const fallActive = S.alerts.some((a) => a.kind === "fall");
  const lastFall = S.history.find((a) => a.kind === "fall");
  if (fallActive) { $("fall-value").textContent = "Fall detected"; $("fall-badge").innerHTML = pill("danger", "Alert", true); }
  else if (live) { $("fall-value").textContent = "No fall"; $("fall-badge").innerHTML = pill("ok", "Monitoring"); }
  else { $("fall-value").textContent = "–"; $("fall-badge").innerHTML = pill("muted", "Offline"); }
  $("fall-last").textContent = lastFall ? when(lastFall.created_at) : "None";
}

function safetyItem(icon, tone, title, sub) {
  const ring = { ok: "bg-ok-soft text-ok border-ok/30", warn: "bg-warn-soft text-warn border-warn/30",
    danger: "bg-danger-soft text-danger border-danger/30", muted: "bg-raise text-ink-3 border-line", info: "bg-info-soft text-info border-info/30" }[tone];
  return `<div class="py-3.5 flex items-start gap-3"><div class="w-8 h-8 rounded-full border flex items-center justify-center shrink-0 mt-0.5 ${ring}">
    <span class="material-symbols-outlined text-lg">${icon}</span></div><div class="flex-1"><div class="text-sm font-semibold text-ink">${esc(title)}</div>
    <div class="text-sm mt-0.5 ${tone === "ok" ? "text-ok" : tone === "danger" ? "text-danger" : tone === "warn" ? "text-warn" : "text-ink-2"}">${esc(sub)}</div></div></div>`;
}
function todayReminders(type) {
  const today = new Date().toDateString();
  return S.reminders.filter((r) => (!type || r.type === type) && new Date(r.scheduled_at).toDateString() === today)
    .sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));
}
function renderSafety() {
  const live = wearableLive();
  const lastVoice = S.events[0];
  const checkin = todayReminders("checkin").at(-1);
  const items = [
    live ? safetyItem("check_circle", "ok", "Fall detection", "Active on the wearable accelerometer")
         : safetyItem("sensors_off", "muted", "Fall detection", "Wearable offline, so falls can't be detected"),
    lastVoice ? safetyItem("record_voice_over", "info", "Voice assistant", `Last activity ${ago(lastVoice.timestamp || lastVoice.received_at)}`)
              : safetyItem("record_voice_over", "muted", "Voice assistant", "Not heard from yet"),
    !checkin ? safetyItem("wb_sunny", "muted", "Morning check-in", "Not answered or missed yet today")
      : checkin.status === "missed" ? safetyItem("wb_sunny", "warn", "Morning check-in", "Missed today, family notified")
      : safetyItem("wb_sunny", "ok", "Morning check-in", `Completed at ${clock(checkin.responded_at || checkin.scheduled_at)} (voice reply)`),
    live ? safetyItem("shield", "ok", "Help button", "Armed on the wearable") : safetyItem("shield", "muted", "Help button", "Wearable offline"),
  ];
  $("safety-list").innerHTML = items.join("");
}

function renderMeds() {
  const meds = todayReminders("medicine");
  const taken = meds.filter((m) => m.status !== "missed").length;
  $("meds-count").textContent = `${taken}/${meds.length} taken`;
  const missed = meds.length - taken;
  $("ov-meds-value").textContent = meds.length ? `${taken}/${meds.length}` : "–";
  $("ov-meds-badge").innerHTML = !meds.length ? pill("muted", "None yet") : missed ? pill("warn", `${missed} missed`) : pill("ok", "On track");
  const last = meds.at(-1);
  $("ov-meds-sub").textContent = last ? `Latest: ${last.text}, ${({ confirmed: "taken", late: "taken late", missed: "missed" })[last.status] || last.status} (${clock(last.scheduled_at)})` : "Confirmed by voice with SAGE.";
  const look = {
    confirmed: ["bg-ok text-black", "check", "ok", (m) => `Taken at ${clock(m.responded_at)}`],
    late: ["bg-warn text-black", "schedule", "warn", (m) => `Taken late, ${clock(m.responded_at)}`],
    missed: ["bg-danger text-on-status", "priority_high", "danger", () => "Missed, family notified"],
  };
  $("meds-list").innerHTML = meds.length ? meds.map((m) => {
    const [dot, icon, tone, label] = look[m.status] || look.confirmed;
    return `<div class="relative flex items-start justify-between gap-4">
      <div class="absolute -left-6 top-1 w-4 h-4 rounded-full flex items-center justify-center ${dot}"><span class="material-symbols-outlined text-xs font-semibold">${icon}</span></div>
      <div><div class="text-sm font-semibold text-ink">${esc(m.text)}</div><div class="text-sm text-ink-2">Scheduled ${clock(m.scheduled_at)}</div></div>
      <span class="shrink-0 inline-flex items-center px-2.5 py-0.5 rounded text-xs font-semibold border ${TONES[tone]}">${esc(label(m))}</span></div>`;
  }).join("") : `<p class="text-sm text-ink-2 -ml-6">No medicine reminders answered or missed yet today.</p>`;
}

function missRate(fromDays, toDays) { // days ago window [fromDays, toDays)
  const now = Date.now();
  const rs = S.reminders.filter((r) => { const a = (now - new Date(r.scheduled_at)) / 864e5; return a >= fromDays && a < toDays; });
  return { n: rs.length, rate: rs.length ? rs.filter((r) => r.status === "missed").length / rs.length : 0 };
}
// Agent37 care agent: plain-language summary of the model's findings for the family
function careSummaryHtml(m) {
  const cs = m && m.care_summary;
  if (!m || !m.level || !cs || !cs.configured) return "";
  if (cs.text) {
    return `<div class="mt-3 p-3 rounded-lg bg-surface border border-line text-ink text-sm leading-relaxed">${esc(cs.text)}
      <span class="flex flex-wrap items-center gap-x-2 mt-2 text-xs text-ink-3">Care agent summary · Agent37 · ${esc(ago(cs.created_at))}
      ${cs.busy ? "· writing a new one…" : `<button type="button" data-refresh-summary class="text-accent font-medium hover:underline">Write a fresh one</button>`}</span></div>`;
  }
  const msg = cs.busy ? "The care agent is writing a summary for the family…"
    : cs.error ? `The care agent couldn't write a summary: ${cs.error}` : "Waiting for the care agent…";
  return `<p class="mt-3 text-xs text-ink-3">${esc(msg)}</p>`;
}
$("cog-flag-text").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-refresh-summary]");
  if (!b) return;
  b.disabled = true; b.textContent = "Asking the care agent…";
  try { await api(`/api/memory-summary/refresh?device=${VOICE_ID}`, { method: "POST" }); toast("The care agent is writing a fresh summary. It appears here in under a minute.", "info"); } catch {}
  setTimeout(slowTick, 15000); setTimeout(slowTick, 40000);
});

function renderCognitive() {
  renderCalendar();

  const week = missRate(0, 7), base = missRate(7, 42), month = missRate(0, 30);
  $("cog-index").textContent = week.n ? `${Math.round(100 * (1 - week.rate))}%` : "–";
  $("cog-month").textContent = month.n ? Math.round(month.rate * month.n) : "0";

  let tone = "muted", icon = "info", title, text;
  const m = S.memory;
  let reasons = [], footnote = "";
  if (m && m.level) {                       // the SAGE memory-decline model (flagging_model/)
    tone = m.level === "concern" ? "danger" : m.level === "watch" ? "warn" : "ok";
    icon = tone === "ok" ? "check_circle" : "psychology_alt";
    title = m.title || ({ normal: "Routine looks steady", watch: "Worth keeping an eye on", concern: "A change worth mentioning to her doctor" }[m.level]);
    text = m.summary || m.detail || "";
    reasons = m.reasons || [];
    footnote = `SAGE memory model · compared with her own first month · risk ${Math.round((m.risk ?? 0) * 100)}% this week`;
  } else if (m && m.learning) {             // model running, but not enough history yet
    title = "Building her baseline";
    text = m.message;
    footnote = "SAGE memory model";
  } else if (base.n < 10) {
    title = "Building her baseline";
    text = "The pattern appears once SAGE has a few weeks of reminder history.";
  } else {
    const w = Math.round(week.rate * 100), b = Math.round(base.rate * 100);
    if (w - b >= 15) {
      tone = "warn"; icon = "psychology_alt";
      title = "Missing more reminders than usual";
      text = `${w}% missed this week, compared with her usual ${b}%. Shared with family. Worth mentioning at the next doctor visit.`;
    } else {
      tone = "ok"; icon = "check_circle";
      title = "Routine looks steady";
      text = `${w}% missed this week, in line with her usual ${b}%.`;
    }
  }
  const box = { ok: "bg-ok-soft border-ok/30", warn: "bg-warn-soft border-warn/30", danger: "bg-danger-soft border-danger/30", muted: "bg-raise border-line" }[tone];
  const txt = { ok: ["text-ok", "text-ok", "text-ok"], warn: ["text-warn", "text-warn", "text-warn"],
    danger: ["text-danger", "text-danger", "text-danger"], muted: ["text-ink-2", "text-ink-2", "text-ink-3"] }[tone];
  $("cog-flag").className = `mt-4 p-3.5 rounded-lg border flex items-start gap-3 ${box}`;
  $("cog-flag-icon").className = `material-symbols-outlined text-xl shrink-0 mt-0.5 ${txt[2]}`;
  $("cog-flag-icon").textContent = icon;
  $("cog-flag-title").className = `text-sm font-semibold ${txt[0]}`; $("cog-flag-title").textContent = title;
  $("ov-mem").textContent = tone === "muted" ? "Building baseline" : title;
  $("cog-flag-text").className = `text-sm mt-0.5 ${txt[1]}`;
  $("cog-flag-text").innerHTML = esc(text)
    + (reasons.length ? `<ul class="mt-2 flex flex-col gap-0.5">${reasons.map((r) => `<li>· ${esc(r.replace("->", "→"))}</li>`).join("")}</ul>` : "")
    + (footnote ? `<span class="block mt-2 text-xs text-ink-3">${esc(footnote)}</span>` : "")
    + careSummaryHtml(m);
}

const ALERT_NAMES = { fall: "Fall detected", emergency: "Help requested", reminder_missed: "Missed medicine", checkin_missed: "Missed morning check-in", vitals: "Vitals out of range", memory: "Memory pattern" };
const OUTCOMES = { checking: "Family checking on her", false_alarm: "Marked false alarm", ambulance: "Ambulance called by family", handled: "Handled by family", cancelled_by_patient: "Cancelled by the patient (pressed twice)" };
function renderHistory() {
  $("alert-rows").innerHTML = S.history.length ? S.history.map((a) => {
    const [tone, sev] = isUrgent(a) ? ["danger", "High"] : a.kind.endsWith("missed") ? ["warn", "Medium"] : ["info", "Info"];
    return `<tr class="hover:bg-raise">
      <td class="py-3 ${a.acknowledged ? "text-ink" : "font-semibold text-ink"}">${esc(when(a.created_at))}</td>
      <td class="py-3"><div class="font-semibold ${isUrgent(a) ? "text-danger" : "text-ink"}">${esc(ALERT_NAMES[a.kind] || a.kind)}</div><div class="text-ink-2">${esc(a.message)}</div>${(a.escalation || []).map((s) => `<div class="text-xs text-ink-3 mt-0.5">${clock(s.at)} · ${esc(s.detail)}</div>`).join("")}</td>
      <td class="py-3"><span class="px-2 py-0.5 rounded border font-semibold text-xs ${TONES[tone]}">${sev}</span></td>
      <td class="py-3 ${a.acknowledged ? "text-ink-2" : "text-danger font-semibold"}">${a.acknowledged ? esc(OUTCOMES[a.outcome] || "Handled by family") : "Waiting for family"}</td>
      <td class="py-3 text-right">${a.acknowledged ? "" : `<button data-ack="${esc(a.id)}" class="text-accent font-semibold hover:underline">Mark handled</button>`}</td></tr>`;
  }).join("") : `<tr><td colspan="5" class="py-4 text-ink-2">No alerts yet.</td></tr>`;
}
$("alert-rows").addEventListener("click", (e) => { const b = e.target.closest("button[data-ack]"); if (b) { b.disabled = true; ack(b.dataset.ack, "handled"); } });

function device(icon, name, tone, right, sub) {
  return `<div class="pt-2 first:pt-0 border-t first:border-t-0 border-line"><div class="flex justify-between items-center">
    <span class="font-medium text-ink flex items-center gap-2"><span class="material-symbols-outlined text-xl text-accent">${icon}</span>${esc(name)}</span>
    <span class="font-semibold text-xs px-1.5 py-0.5 rounded border ${TONES[tone]}">${esc(right)}</span></div>
    <span class="text-xs text-ink-3 mt-0.5 block">${esc(sub)}</span></div>`;
}
function renderDevices() {
  const ev = S.events[0];
  $("device-list").innerHTML = [
    device("watch", "SAGE wearable", wearableLive() ? "ok" : "muted", wearableLive() ? "Online" : "Offline",
      S.latest ? `Last reading ${ago(S.latest.timestamp)}` : "No readings received yet"),
    device("record_voice_over", "Voice assistant", ev ? "ok" : "muted", ev ? "Active" : "Not seen",
      ev ? `Last event ${ago(ev.timestamp || ev.received_at)}` : "No events received yet"),
    device("dns", "Backend server", S.up === false ? "danger" : "ok", S.up === false ? "Offline" : "Online",
      S.up === false ? "Start app.py on the laptop" : "Flask + MongoDB Atlas"),
  ].join("");
}


// ---- Memory & routine calendar ----
const pad = (n) => String(n).padStart(2, "0");
const dayKey = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
const CAL_MAX_MONTHS_BACK = 6;
const cal = { y: new Date().getFullYear(), m: new Date().getMonth(), selected: dayKey(new Date()) };
const STATUS_LABEL = { confirmed: "Answered", late: "Answered late", missed: "Missed" };
const STATUS_TONE = { confirmed: "ok", late: "warn", missed: "danger" };

function remindersByDay() {
  const map = {};
  for (const r of S.reminders) (map[dayKey(new Date(r.scheduled_at))] ||= []).push(r);
  return map;
}
function monthsBack() {
  const now = new Date();
  return (now.getFullYear() - cal.y) * 12 + (now.getMonth() - cal.m);
}
function renderCalendar() {
  const map = remindersByDay();
  const first = new Date(cal.y, cal.m, 1);
  const days = new Date(cal.y, cal.m + 1, 0).getDate();
  const offset = (first.getDay() + 6) % 7;               // Monday-first grid
  const todayK = dayKey(new Date());
  $("cal-title").textContent = first.toLocaleDateString([], { month: "long", year: "numeric" });

  let html = "<div></div>".repeat(offset), total = 0, missed = 0;
  for (let d = 1; d <= days; d++) {
    const date = new Date(cal.y, cal.m, d), k = dayKey(date);
    const rs = map[k] || [], n = rs.length, mi = rs.filter((r) => r.status === "missed").length;
    const future = k > todayK;
    total += n; missed += mi;
    const pct = n ? (n - mi) / n : null;
    const tone = pct == null ? "border border-line text-ink-2 hover:border-line"
      : pct === 1 ? "bg-ok-soft text-ok border border-ok/35" : pct >= 0.5 ? "bg-warn-soft text-warn border border-warn/40" : "bg-danger-soft text-danger border border-danger/40";
    const sel = k === cal.selected ? "ring-2 ring-white ring-offset-2 ring-offset-surface" : "";
    const today = k === todayK ? "outline outline-2 outline-accent outline-offset-1" : "";
    const label = `${date.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long" })}: ${n ? `${n - mi} of ${n} answered` : "no reminders"}`;
    html += `<button type="button" data-day="${k}" ${future ? "disabled" : ""} aria-label="${esc(label)}" aria-pressed="${k === cal.selected}"
      class="aspect-square rounded-lg flex flex-col items-center justify-center gap-0.5 transition-colors ${tone} ${sel} ${today} ${future ? "opacity-25 cursor-default" : "cursor-pointer"}">
      <span class="text-sm font-semibold leading-none">${d}</span>${n ? `<span class="hidden sm:block text-xs font-semibold leading-none opacity-90">${n - mi}/${n}</span>` : ""}</button>`;
  }
  $("cal-grid").innerHTML = html;
  $("cal-month-summary").textContent = total ? `This month: ${total - missed} of ${total} answered, ${missed} missed` : "No reminders this month";
  $("cal-prev").disabled = monthsBack() >= CAL_MAX_MONTHS_BACK;
  $("cal-next").disabled = monthsBack() <= 0;
  renderWeek(map);
  renderDay(map);
}
// minutes between due time and reply (null if missed)
const replyMins = (r) => (r.responded_at && r.status !== "missed" ? Math.max(0, Math.round((new Date(r.responded_at) - new Date(r.scheduled_at)) / 60000)) : null);
const fmtMins = (m) => (m == null ? "–" : m < 60 ? `${m} min` : `${Math.floor(m / 60)} h ${m % 60} min`);
const parseKey = (k) => { const [y, m, d] = k.split("-").map(Number); return new Date(y, m - 1, d); };
function statTile(label, value, sub = "", tone = "") {
  const c = { ok: "text-ok", warn: "text-warn", danger: "text-danger" }[tone] || "text-ink";
  return `<div class="rounded-lg bg-inset border border-line p-3"><div class="text-sm text-ink-2">${esc(label)}</div>
    <div class="font-display text-h3 font-semibold mt-1 ${c}">${esc(value)}</div>${sub ? `<div class="text-xs text-ink-3 mt-0.5">${esc(sub)}</div>` : ""}</div>`;
}

// ---- Weekly analytics (Mon–Sun week of the selected date) ----
let weekChart;
function weekStart(k) { const d = parseKey(k); d.setDate(d.getDate() - ((d.getDay() + 6) % 7)); return d; }
function weekStats(start, map) {
  const days = [];
  for (let i = 0; i < 7; i++) {
    const d = new Date(start); d.setDate(start.getDate() + i);
    const rs = map[dayKey(d)] || [];
    const mins = rs.map(replyMins).filter((m) => m != null);
    days.push({ date: d, total: rs.length, onTime: rs.filter((r) => r.status === "confirmed").length,
      late: rs.filter((r) => r.status === "late").length, missed: rs.filter((r) => r.status === "missed").length,
      avgReply: mins.length ? Math.round(mins.reduce((a, b) => a + b, 0) / mins.length) : null });
  }
  const sum = (f) => days.reduce((a, d) => a + d[f], 0);
  const replies = days.flatMap((d) => (map[dayKey(d.date)] || []).map(replyMins).filter((m) => m != null));
  return { days, total: sum("total"), missed: sum("missed"), late: sum("late"),
    avgReply: replies.length ? Math.round(replies.reduce((a, b) => a + b, 0) / replies.length) : null };
}
function makeWeekChart() {
  if (typeof Chart === "undefined" || weekChart) return;
  weekChart = new Chart($("week-chart"), {
    data: { labels: [], datasets: [
      { type: "bar", label: "On time", data: [], stack: "r", borderRadius: 4, maxBarThickness: 44 },
      { type: "bar", label: "Late", data: [], stack: "r", borderRadius: 4, maxBarThickness: 44 },
      { type: "bar", label: "Missed", data: [], stack: "r", borderRadius: 4, maxBarThickness: 44 },
      { type: "line", label: "Avg reply time (min)", data: [], yAxisID: "mins", tension: 0.35, borderWidth: 2.5, pointRadius: 3, spanGaps: true },
    ] },
    options: {
      animation: false, maintainAspectRatio: false, interaction: { mode: "index", intersect: false },
      plugins: { legend: { position: "bottom", labels: { boxWidth: 12, boxHeight: 12, padding: 16 } },
        tooltip: { callbacks: { label: (c) => ` ${c.dataset.label}: ${c.raw ?? "–"}${c.dataset.yAxisID === "mins" && c.raw != null ? " min" : ""}` } } },
      scales: {
        x: { stacked: true, grid: { display: false } },
        y: { stacked: true, beginAtZero: true, ticks: { precision: 0 }, title: { display: true, text: "Reminders" } },
        mins: { position: "right", beginAtZero: true, grid: { display: false }, title: { display: true, text: "Reply time (min)" } },
      },
    },
  });
  themeWeekChart();
}
function themeWeekChart() {
  if (!weekChart) return;
  const [a, b, c, d] = weekChart.data.datasets;
  a.backgroundColor = token("ok", 0.75); b.backgroundColor = token("warn", 0.75); c.backgroundColor = token("danger", 0.75);
  d.borderColor = token("accent"); d.backgroundColor = token("accent"); d.pointBorderColor = token("surface");
  for (const ax of ["x", "y", "mins"]) { weekChart.options.scales[ax].ticks = { ...(weekChart.options.scales[ax].ticks || {}), color: token("ink-3") };
    if (weekChart.options.scales[ax].title) weekChart.options.scales[ax].title.color = token("ink-3"); }
  weekChart.options.scales.y.grid = { color: token("line") };
  weekChart.options.plugins.legend.labels.color = token("ink-2");
  weekChart.update();
}
function renderWeek(map = remindersByDay()) {
  const start = weekStart(cal.selected), end = new Date(start); end.setDate(start.getDate() + 6);
  const prevStart = new Date(start); prevStart.setDate(start.getDate() - 7);
  const w = weekStats(start, map), p = weekStats(prevStart, map);
  const same = start.getMonth() === end.getMonth();
  $("wk-title").textContent = `Week of ${start.getDate()}${same ? "" : " " + start.toLocaleDateString([], { month: "short" })}–${end.getDate()} ${end.toLocaleDateString([], { month: "short", year: "numeric" })}`;
  const pct = w.total ? Math.round((100 * (w.total - w.missed)) / w.total) : null;
  const ppct = p.total ? Math.round((100 * (p.total - p.missed)) / p.total) : null;
  const delta = pct != null && ppct != null ? pct - ppct : null;
  $("wk-stats").innerHTML = [
    statTile("Answered", pct == null ? "–" : `${pct}%`, w.total ? `${w.total - w.missed} of ${w.total} reminders` : "No reminders", pct == null ? "" : pct >= 90 ? "ok" : pct >= 70 ? "warn" : "danger"),
    statTile("Vs previous week", delta == null ? "–" : `${delta > 0 ? "+" : ""}${delta} pts`, ppct == null ? "Not enough history" : `Previous week: ${ppct}%`, delta == null ? "" : delta >= 0 ? "ok" : delta <= -10 ? "danger" : "warn"),
    statTile("Average reply time", fmtMins(w.avgReply), p.avgReply != null ? `Previous week: ${fmtMins(p.avgReply)}` : ""),
    statTile("Missed", String(w.missed), `${w.late} answered late`, w.missed ? "danger" : "ok"),
  ].join("");
  $("week-empty").classList.toggle("hidden", w.total > 0);
  if (!weekChart) makeWeekChart();
  if (!weekChart) return;
  weekChart.data.labels = w.days.map((d) => d.date.toLocaleDateString([], { weekday: "short", day: "numeric" }));
  weekChart.data.datasets[0].data = w.days.map((d) => d.onTime);
  weekChart.data.datasets[1].data = w.days.map((d) => d.late);
  weekChart.data.datasets[2].data = w.days.map((d) => d.missed);
  weekChart.data.datasets[3].data = w.days.map((d) => d.avgReply);
  const maxReply = Math.max(0, ...w.days.map((d) => d.avgReply ?? 0));
  weekChart.options.scales.mins.suggestedMax = Math.max(10, Math.ceil(maxReply * 1.5));   // headroom above the line
  weekChart.options.scales.y.suggestedMax = Math.max(...w.days.map((d) => d.total), 1) + 1;
  weekChart.update();
}

// ---- Day details ----
const MOODS = { good: "good", okay: "okay", bad: "not great" };
let dayReq = 0;
async function renderDay(map = remindersByDay()) {
  const k = cal.selected, date = parseKey(k), isToday = k === dayKey(new Date());
  $("dd-title").textContent = (isToday ? "Today, " : "") + date.toLocaleDateString([], { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  const rs = (map[k] || []).slice().sort((a, b) => new Date(a.scheduled_at) - new Date(b.scheduled_at));

  // server data for that day: vitals, alerts, voice events
  const end = new Date(date); end.setDate(date.getDate() + 1);
  const req = ++dayReq;
  let day = { vitals: null, alerts: [], events: [] };
  try { day = await getJSON(`/api/day?start=${encodeURIComponent(date.toISOString())}&end=${encodeURIComponent(end.toISOString())}&device=${VOICE_ID}&wearable=${WEARABLE_ID}`); } catch {}
  if (req !== dayReq) return; // a newer day was clicked meanwhile

  const answered = rs.filter((r) => r.status !== "missed").length;
  const mins = rs.map(replyMins).filter((m) => m != null);
  const avg = mins.length ? Math.round(mins.reduce((a, b) => a + b, 0) / mins.length) : null;
  const talks = day.events.filter((e) => e.type === "voice_interaction").length;
  $("dd-stats").innerHTML = [
    statTile("Reminders answered", rs.length ? `${answered}/${rs.length}` : "–", rs.length ? `${rs.length - answered} missed` : "No reminders", !rs.length ? "" : answered === rs.length ? "ok" : answered / rs.length >= 0.5 ? "warn" : "danger"),
    statTile("Average reply time", fmtMins(avg), mins.length ? `Slowest: ${fmtMins(Math.max(...mins))}` : ""),
    statTile("Alerts", String(day.alerts.length), day.alerts.length ? `${day.alerts.filter((a) => a.acknowledged).length} handled by family` : "None", day.alerts.length ? "danger" : "ok"),
    statTile("Talked with SAGE", String(talks), talks ? "Voice conversations" : "No conversations"),
  ].join("");

  // one merged, time-ordered timeline
  const items = [];
  for (const r of rs) {
    const m = replyMins(r);
    const detail = r.status === "missed" ? "No reply after reminders and retries. Family was notified."
      : `Replied at ${clock(r.responded_at)} by ${r.source === "button" ? "button" : "voice"} · ${m === 0 ? "right away" : `${fmtMins(m)} after it was due`}`;
    items.push({ t: r.scheduled_at, icon: r.type === "checkin" ? "wb_sunny" : "medication", tone: STATUS_TONE[r.status] || "muted",
      title: `${r.text || r.type} · due ${clock(r.scheduled_at)}`, detail, tag: STATUS_LABEL[r.status] || r.status });
  }
  for (const a of day.alerts) {
    items.push({ t: a.created_at, icon: isUrgent(a) ? "emergency" : "notifications", tone: isUrgent(a) ? "danger" : "warn",
      title: ALERT_NAMES[a.kind] || a.kind, detail: `${a.message}. ${a.acknowledged ? (OUTCOMES[a.outcome] || "Handled by family") + (a.acknowledged_at ? ` at ${clock(a.acknowledged_at)}` : "") : "No family response recorded"}.`,
      tag: a.acknowledged ? "Handled" : "Open" });
  }
  for (const e of day.events) {
    const d = e.data || {};
    if (e.type === "checkin_completed" && d.mood) items.push({ t: e.timestamp, icon: "sentiment_satisfied", tone: "info", title: "Morning check-in mood", detail: `Said she's feeling ${MOODS[d.mood] || d.mood}.`, tag: "Check-in" });
    if (e.type === "emergency") items.push({ t: e.timestamp, icon: "sos", tone: "danger", title: "Asked for help by voice", detail: d.reason ? `Reason: ${d.reason}` : "Emergency phrase detected.", tag: "SOS" });
  }
  items.sort((a, b) => new Date(a.t) - new Date(b.t));
  const dot = { ok: "bg-ok", warn: "bg-warn", danger: "bg-danger", info: "bg-info", muted: "bg-ink-3" };
  $("dd-timeline").innerHTML = items.length ? items.map((i) => `<li class="relative">
      <span class="absolute -left-6 top-1.5 w-3 h-3 rounded-full ring-4 ring-surface ${dot[i.tone]}"></span>
      <div class="flex items-start justify-between gap-3">
        <div class="min-w-0"><div class="text-xs text-ink-3">${clock(i.t)}</div>
          <div class="text-base font-medium text-ink flex items-center gap-2"><span class="material-symbols-outlined text-lg text-ink-3">${i.icon}</span>${esc(i.title)}</div>
          <div class="text-sm text-ink-2 mt-0.5">${esc(i.detail)}</div></div>
        <span class="shrink-0 px-2 py-0.5 rounded border text-xs font-semibold ${TONES[i.tone]}">${esc(i.tag)}</span>
      </div></li>`).join("")
    : `<li class="text-sm text-ink-2 -ml-6">Nothing recorded on this day.</li>`;

  const v = day.vitals;
  $("dd-vitals").innerHTML = v && v.count ? [
    `<div class="rounded-lg bg-inset border border-line p-4"><div class="text-sm text-ink-2">Heart rate</div>
      <div class="font-display text-h2 font-semibold text-ink mt-1">${v.hr_avg ?? "–"} <span class="text-sm font-normal text-ink-2">bpm average</span></div>
      <div class="text-sm text-ink-2 mt-1">Lowest ${v.hr_min ?? "–"} · Highest ${v.hr_max ?? "–"}</div></div>`,
    `<div class="rounded-lg bg-inset border border-line p-4"><div class="text-sm text-ink-2">Blood oxygen</div>
      <div class="font-display text-h2 font-semibold text-ink mt-1">${v.spo2_avg ?? "–"}<span class="text-sm font-normal text-ink-2">% average</span></div>
      <div class="text-sm text-ink-2 mt-1">Lowest ${v.spo2_min ?? "–"}% · Highest ${v.spo2_max ?? "–"}%</div></div>`,
    `<div class="rounded-lg bg-inset border border-line p-4 flex items-center justify-between"><div><div class="text-sm text-ink-2">Falls detected</div>
      <div class="font-display text-h2 font-semibold mt-1 ${v.falls ? "text-danger" : "text-ok"}">${v.falls}</div></div>
      <div class="text-xs text-ink-3 text-right">${v.count.toLocaleString()} readings<br>from the wearable</div></div>`,
  ].join("") : `<div class="rounded-lg border border-dashed border-line p-5 text-center">
      <span class="material-symbols-outlined text-3xl text-ink-3">watch_off</span>
      <p class="text-sm font-medium text-ink mt-1">No wearable readings</p>
      <p class="text-sm text-ink-2 mt-1">The wearable wasn't sending data on this day.</p></div>`;
}

$("cal-grid").addEventListener("click", (e) => {
  const b = e.target.closest("button[data-day]");
  if (!b || b.disabled) return;
  cal.selected = b.dataset.day; renderCalendar();
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  $("day-details").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
  $("day-details").focus({ preventScroll: true });
});
$("dd-back").addEventListener("click", () => {
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  $("cal-grid").scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "center" });
});
$("cal-prev").addEventListener("click", () => { if (--cal.m < 0) { cal.m = 11; cal.y--; } renderCalendar(); });
$("cal-next").addEventListener("click", () => { if (++cal.m > 11) { cal.m = 0; cal.y++; } renderCalendar(); });

// ---- Medical reports ----
const KIND_LABEL = { checkup: "Full-body checkup", lab: "Lab test", prescription: "Prescription", other: "Other" };
const fmtSize = (b) => (b > 1048576 ? `${(b / 1048576).toFixed(1)} MB` : `${Math.max(1, Math.round(b / 1024))} KB`);
const fmtDate = (ymd) => new Date(`${ymd}T00:00:00`).toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" });
let reportsCache = [];

async function loadReports() {
  try { reportsCache = await getJSON(`/api/reports?p=${encodeURIComponent(PID)}`); } catch { return; }
  $("report-list").innerHTML = reportsCache.length ? reportsCache.map((r) => `
    <div class="flex items-center justify-between gap-3 p-3 rounded-lg border border-line hover:bg-raise">
      <div class="flex items-center gap-3 min-w-0">
        <span class="material-symbols-outlined text-xl ${r.content_type === "application/pdf" ? "text-danger" : "text-info"}">${r.content_type === "application/pdf" ? "picture_as_pdf" : "image"}</span>
        <div class="min-w-0">
          <div class="text-sm font-semibold text-ink truncate">${esc(r.title)}</div>
          <div class="text-xs text-ink-3">${esc(KIND_LABEL[r.kind] || r.kind)} · ${fmtDate(r.report_date)} · ${fmtSize(r.size)}</div>
          ${r.notes ? `<div class="text-sm text-ink-2 mt-0.5">${esc(r.notes)}</div>` : ""}
        </div>
      </div>
      <div class="flex items-center shrink-0">
        <a href="/api/reports/${esc(r.id)}/file" target="_blank" rel="noopener" class="p-2 text-ink-2 hover:text-accent" title="Open ${esc(r.title)}" aria-label="Open ${esc(r.title)}"><span class="material-symbols-outlined text-lg">open_in_new</span></a>
        <a href="/api/reports/${esc(r.id)}/file?download=1" class="p-2 text-ink-2 hover:text-accent" title="Download ${esc(r.title)}" aria-label="Download ${esc(r.title)}"><span class="material-symbols-outlined text-lg">download</span></a>
        <button data-del="${esc(r.id)}" class="p-2 text-ink-2 hover:text-danger" title="Delete ${esc(r.title)}" aria-label="Delete ${esc(r.title)}"><span class="material-symbols-outlined text-lg">delete</span></button>
      </div>
    </div>`).join("")
    : `<div class="p-6 rounded-lg border border-dashed border-line text-center">
        <span class="material-symbols-outlined text-3xl text-ink-3">upload_file</span>
        <p class="text-sm font-semibold text-ink mt-1">No reports yet</p>
        <p class="text-sm text-ink-2 mt-1">Add her past checkups and lab results with the form, so any doctor can see her history quickly.</p></div>`;

  const lastCheckup = reportsCache.find((r) => r.kind === "checkup");
  if (lastCheckup) {
    const due = new Date(`${lastCheckup.report_date}T00:00:00`); due.setMonth(due.getMonth() + 6);
    const daysLeft = Math.ceil((due - new Date()) / 864e5);
    $("checkup-due").textContent = `Due ${due.toLocaleDateString([], { day: "numeric", month: "short", year: "numeric" })}`;
    $("checkup-due").className = `text-h4 font-semibold mt-1 ${daysLeft < 0 ? "text-danger" : daysLeft <= 30 ? "text-warn" : "text-ink"}`;
    $("checkup-sub").textContent = daysLeft < 0 ? `Overdue by ${-daysLeft} days. Last checkup: ${fmtDate(lastCheckup.report_date)}.`
      : `In ${daysLeft} days. Six months after her last checkup on ${fmtDate(lastCheckup.report_date)}.`;
  }
}

function reportMsg(text, ok) {
  const m = $("report-msg");
  m.textContent = text; m.className = `text-xs ${ok ? "text-ok" : "text-danger"}`;
}
$("report-date").max = dayKey(new Date());
$("report-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const f = e.currentTarget;
  if (!$("report-file").files.length) return reportMsg("Choose the report file to upload.", false), $("report-file").focus();
  if (!$("report-title").value.trim()) return reportMsg("Give the report a title, e.g. 'Full body checkup'.", false), $("report-title").focus();
  if (!$("report-date").value) return reportMsg("Add the date printed on the report.", false), $("report-date").focus();
  $("report-submit").disabled = true; reportMsg("Uploading…", true);
  try {
    const fd = new FormData(f); fd.append("patient_id", PID);
    const r = await api("/api/reports", { method: "POST", body: fd });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || "Upload didn't go through. Check the backend is running and try again.");
    f.reset(); reportMsg(`Added "${body.title}".`, true); loadReports();
  } catch (err) { reportMsg(err.message, false); }
  $("report-submit").disabled = false;
});
$("report-list").addEventListener("click", async (e) => {
  const b = e.target.closest("button[data-del]");
  if (!b) return;
  const r = reportsCache.find((x) => x.id === b.dataset.del);
  if (!confirm(`Delete "${r ? r.title : "this report"}"? This can't be undone.`)) return;
  await api(`/api/reports/${b.dataset.del}`, { method: "DELETE" }).catch(() => {});
  loadReports();
});

// ---- Toast ----
let toastTimer;
function toast(text, tone = "ok") {
  $("toast-text").textContent = text;
  $("toast-icon").textContent = tone === "ok" ? "check_circle" : tone === "danger" ? "error" : "info";
  $("toast-icon").className = `material-symbols-outlined ${tone === "ok" ? "text-ok" : tone === "danger" ? "text-danger" : "text-info"}`;
  $("toast").classList.remove("hidden"); $("toast").classList.add("flex");
  clearTimeout(toastTimer); toastTimer = setTimeout(hideToast, 8000);
}
function hideToast() { $("toast").classList.add("hidden"); $("toast").classList.remove("flex"); }
$("toast-close").addEventListener("click", hideToast);

// ---- Alarm sound on the dashboard while a fall / SOS is open ----
// Browsers only allow sound after you've clicked something on the page, so the first click arms it.
let audioCtx = null, sirenTimer = null;
let soundOn = (() => { try { return localStorage.getItem("sage-sound") !== "off"; } catch { return true; } })();
function armAudio() { try { audioCtx = audioCtx || new (window.AudioContext || window.webkitAudioContext)(); audioCtx.resume(); } catch {} }
document.addEventListener("click", armAudio, { once: true });
function beep() {
  if (!audioCtx || audioCtx.state !== "running") return;
  const t = audioCtx.currentTime, o = audioCtx.createOscillator(), g = audioCtx.createGain();
  o.type = "sine"; o.frequency.setValueAtTime(880, t); o.frequency.setValueAtTime(660, t + 0.25);
  g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.2, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.5);
  o.connect(g).connect(audioCtx.destination); o.start(t); o.stop(t + 0.55);
}
function siren(on) {
  if (on && soundOn && !sirenTimer) { beep(); sirenTimer = setInterval(beep, 1400); }
  if ((!on || !soundOn) && sirenTimer) { clearInterval(sirenTimer); sirenTimer = null; }
}
function renderSoundToggle() {
  $("sound-icon").textContent = soundOn ? "volume_up" : "volume_off";
  $("sound-toggle").setAttribute("aria-pressed", String(soundOn));
  $("sound-toggle").setAttribute("aria-label", soundOn ? "Turn off the alarm sound" : "Turn on the alarm sound");
  $("sound-toggle").title = soundOn ? "Alarm sound on" : "Alarm sound off";
}
$("sound-toggle").addEventListener("click", () => {
  soundOn = !soundOn; try { localStorage.setItem("sage-sound", soundOn ? "on" : "off"); } catch {}
  armAudio(); renderSoundToggle(); siren(!!bannerAlert);
});

// ---- Patient & guardian profiles ----
const shortName = () => S.patient.preferred_name || (S.patient.name || "Kamala").split(" ")[0];
const initials = (n) => (n || "?").split(" ").filter(Boolean).map((p) => p[0]).join("").slice(0, 2).toUpperCase();
function ageFrom(dob) {
  if (!dob) return null;
  const d = new Date(`${dob}T00:00:00`), n = new Date();
  let a = n.getFullYear() - d.getFullYear();
  if (n.getMonth() < d.getMonth() || (n.getMonth() === d.getMonth() && n.getDate() < d.getDate())) a--;
  return a;
}
function greetingWord() { const h = new Date().getHours(); return h < 12 ? "Good morning" : h < 17 ? "Good afternoon" : "Good evening"; }
function applyProfiles() {
  const p = S.patient, g = S.guardian, who = shortName();
  const viewer = (S.me?.name || g.name || "").split(" ")[0];
  $("greeting").textContent = GREET === "patient" ? `Hello ${who}, ${greetingWord().toLowerCase()}` : `${greetingWord()}${viewer ? `, ${viewer}` : ""}`;
  const age = ageFrom(p.dob);
  $("patient-name").textContent = `${p.name || who}${age != null ? `, ${age}` : ""}`;
  $("patient-name").setAttribute("aria-label", `Open ${who}'s profile`);
  $("patient-open").setAttribute("aria-label", `Open ${who}'s profile`);
  $("resident-initials").textContent = initials(p.name || who);
  $("caregiver-name").textContent = g.name || S.me?.name || "Guardian";
  $("caregiver-role").textContent = g.relation ? `${g.relation} (primary guardian)` : "Primary guardian";
  $("caregiver-initials").textContent = initials(g.name || S.me?.name);
  $("call-contact").href = p.phone ? `tel:${p.phone.replace(/\s+/g, "")}` : "#";
  $("call-contact-label").textContent = `Call ${who}`;
  $("call-contact").title = p.phone ? `Call ${who} (${p.phone})` : `Add ${who}'s phone in her profile to call her from here`;
  const amb = p.ambulance_number || "108";
  $("ambulance-link").href = `tel:${amb}`;
  $("ambulance-label").textContent = `Call ambulance (${amb})`;
  document.querySelectorAll("[data-outcome='checking']").forEach((b) => { b.lastChild.textContent = `I'm checking on ${who}`; });
}
async function loadProfiles() {
  try {
    [S.patient, S.guardian, S.me] = await Promise.all([getJSON(`/api/patients/${encodeURIComponent(PID)}`), getJSON("/api/profile/guardian"), getJSON("/api/me")]);
    if (S.patient.wearable_id) WEARABLE_ID = S.patient.wearable_id;
    if (S.patient.voice_id) VOICE_ID = S.patient.voice_id;
  } catch {}
  applyProfiles();
}
$("call-contact").addEventListener("click", (e) => {
  if (!S.patient.phone) { e.preventDefault(); openProfile("patient", true); toast(`Add ${shortName()}'s phone number to call her from here.`, "info"); }
});

// [key, label, type ("text"|"tel"|"email"|"date"|"area"|[options]), required, placeholder]
const FIELDS = {
  patient: [
    ["Basics", [["name", "Full name", "text", true], ["preferred_name", "What she likes to be called", "text"], ["dob", "Date of birth", "date"],
      ["gender", "Gender", "text"], ["blood_group", "Blood group", ["", "A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-"]]]],
    ["Health", [["conditions", "Pre-existing conditions", "area", false, "e.g. Type 2 diabetes, high blood pressure"],
      ["allergies", "Allergies", "area", false, "e.g. Penicillin"], ["medications", "Regular medicines", "area", false, "e.g. Metformin 500 mg, twice a day"]]],
    ["Contacts", [["phone", "Her phone", "tel"], ["address", "Home address", "area"], ["doctor_name", "Family doctor", "text"],
      ["doctor_phone", "Doctor's phone", "tel"], ["ambulance_number", "Emergency number", "tel", false, "108"]]],
    ["For responders", [["notes", "Notes", "area", false, "e.g. Spare key with the neighbour at flat 302"]]],
    ["Devices", [["wearable_id", "Band ID", "text", false, "wearable1"], ["voice_id", "Voice device ID", "text", false, "sage-home-01"]]],
  ],
  guardian: [
    ["You", [["name", "Full name", "text", true], ["relation", "Relation to her", "text", false, "e.g. Son"], ["phone", "Phone", "tel"], ["email", "Email", "email"]]],
    ["Backup contact", [["secondary_name", "Name", "text"], ["secondary_relation", "Relation", "text", false, "e.g. Daughter, neighbour"], ["secondary_phone", "Phone", "tel"]]],
  ],
};
let panelKind = null, panelEditing = false, lastFocus = null;
function fieldValue(kind, key) {
  const v = (S[kind] || {})[key];
  if (key === "dob" && v) return `${fmtDate(v)} (age ${ageFrom(v)})`;
  return v;
}
function renderPanel() {
  const kind = panelKind, data = S[kind] || {}, who = shortName();
  $("panel-kicker").textContent = kind === "patient" ? "Patient profile" : "Guardian profile";
  $("panel-title").textContent = data.name || (kind === "patient" ? who : "Guardian");
  if (!panelEditing) {
    let html = "";
    if (kind === "patient") {
      const age = ageFrom(data.dob);
      const conds = (data.conditions || "").split(/[,\n]/).map((c) => c.trim()).filter(Boolean);
      html += `<div class="flex items-center gap-4 mb-6"><span class="w-14 h-14 rounded-full border-2 border-accent bg-raise text-accent flex items-center justify-center font-semibold text-h4">${esc(initials(data.name))}</span>
        <div><div class="text-base text-ink">${age != null ? `${age} years old` : "Age not added"}${data.blood_group ? ` · Blood group ${esc(data.blood_group)}` : ""}</div>
        <div class="text-sm text-ink-2">${conds.length ? esc(conds[0]) + (conds.length > 1 ? ` and ${conds.length - 1} more` : "") : "No conditions added yet"}</div></div></div>`;
    }
    for (const [section, fields] of FIELDS[kind]) {
      html += `<h3 class="font-display text-h4 font-semibold text-ink mt-2 mb-2">${section}</h3><dl class="divide-y divide-line border-y border-line mb-5">`;
      for (const [key, label] of fields) {
        if (key === "name") continue;
        const v = fieldValue(kind, key);
        html += `<div class="py-2.5 grid grid-cols-5 gap-3"><dt class="col-span-2 text-sm text-ink-2">${label}</dt>
          <dd class="col-span-3 text-sm ${v ? "text-ink" : "text-ink-3"} whitespace-pre-line break-words">${v ? esc(v) : "Not added yet"}</dd></div>`;
      }
      html += `</dl>`;
    }
    if (kind === "guardian" && S.me) html += `<p class="text-sm text-ink-3">Signed in as ${esc(S.me.email)}</p>`;
    $("panel-body").innerHTML = html;
    $("panel-foot").innerHTML = (kind === "guardian" ? `<button id="sign-out" type="button" class="mr-auto px-4 py-2 rounded-lg text-sm font-medium text-danger hover:bg-danger-soft">Sign out</button>` : "")
      + `<button id="panel-edit" type="button" class="px-4 py-2 rounded-lg bg-accent text-on-accent text-sm font-medium hover:brightness-110">Edit profile</button>`;
    $("panel-edit").onclick = () => { panelEditing = true; renderPanel(); };
    if ($("sign-out")) $("sign-out").onclick = async () => { await fetch("/api/auth/logout", { method: "POST" }).catch(() => {}); location.href = "/login"; };
    return;
  }
  let html = `<form id="profile-form" class="flex flex-col gap-5" novalidate>`;
  for (const [section, fields] of FIELDS[kind]) {
    html += `<fieldset class="flex flex-col gap-3"><legend class="font-display text-h4 font-semibold text-ink mb-1">${section}</legend>`;
    for (const [key, label, type, required, ph] of fields) {
      const id = `pf-${key}`, v = esc(data[key] || ""), base = "rounded-lg bg-inset border border-line text-ink text-base px-3 py-2 focus:border-accent focus:ring-0 placeholder:text-ink-3";
      let input;
      if (Array.isArray(type)) input = `<select id="${id}" name="${key}" class="${base}">${type.map((o) => `<option value="${o}" ${o === (data[key] || "") ? "selected" : ""}>${o || "Not set"}</option>`).join("")}</select>`;
      else if (type === "area") input = `<textarea id="${id}" name="${key}" rows="2" placeholder="${esc(ph || "")}" class="${base}">${v}</textarea>`;
      else input = `<input id="${id}" name="${key}" type="${type}" value="${v}" placeholder="${esc(ph || "")}" ${required ? "required" : ""} ${type === "date" ? `max="${dayKey(new Date())}"` : ""} class="${base}">`;
      html += `<div class="flex flex-col gap-1.5"><label for="${id}" class="text-sm font-medium text-ink">${label}${required ? "" : ' <span class="font-normal text-ink-3">(optional)</span>'}</label>${input}</div>`;
    }
    html += `</fieldset>`;
  }
  html += `<p id="profile-error" class="hidden text-sm text-danger" role="alert"></p></form>`;
  $("panel-body").innerHTML = html;
  $("panel-foot").innerHTML = `<button id="panel-cancel" type="button" class="px-4 py-2 rounded-lg text-sm font-medium text-ink-2 hover:bg-raise">Cancel</button>
    <button id="panel-save" type="button" class="px-4 py-2 rounded-lg bg-accent text-on-accent text-sm font-medium hover:brightness-110 disabled:opacity-50">Save profile</button>`;
  $("panel-cancel").onclick = () => { panelEditing = false; renderPanel(); };
  $("panel-save").onclick = saveProfile;
  $("profile-form").onsubmit = (e) => { e.preventDefault(); saveProfile(); };
  $("pf-name").focus();
}
async function saveProfile() {
  const form = $("profile-form"), err = $("profile-error");
  const data = Object.fromEntries(new FormData(form).entries());
  if (!data.name.trim()) { err.textContent = "Add a name before saving."; err.classList.remove("hidden"); $("pf-name").focus(); return; }
  $("panel-save").disabled = true;
  try {
    const url = panelKind === "patient" ? `/api/patients/${encodeURIComponent(PID)}` : `/api/profile/${panelKind}`;
    const r = await api(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });
    const body = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(body.error || "Couldn't save. Check the backend is running and try again.");
    S[panelKind] = body; panelEditing = false;
    if (panelKind === "patient") { WEARABLE_ID = body.wearable_id || WEARABLE_ID; VOICE_ID = body.voice_id || VOICE_ID; }
    applyProfiles(); renderPanel(); toast("Profile saved.");
  } catch (e) { err.textContent = e.message; err.classList.remove("hidden"); $("panel-save").disabled = false; }
}
function openProfile(kind, edit = false) {
  panelKind = kind; panelEditing = edit; lastFocus = document.activeElement;
  renderPanel();
  $("panel").classList.remove("translate-x-full", "invisible"); $("panel").setAttribute("aria-hidden", "false");
  $("panel-scrim").classList.remove("hidden");
  if (!edit) $("panel-close").focus();
}
function closeProfile() {
  $("panel").classList.add("translate-x-full"); $("panel").setAttribute("aria-hidden", "true");
  $("panel-scrim").classList.add("hidden");
  setTimeout(() => { if (!panelKind) $("panel").classList.add("invisible"); }, 200);
  panelKind = null;
  if (lastFocus) lastFocus.focus();
}
$("patient-open").addEventListener("click", () => openProfile("patient"));
$("patient-name").addEventListener("click", () => openProfile("patient"));
$("guardian-open").addEventListener("click", () => openProfile("guardian"));
$("panel-close").addEventListener("click", closeProfile);
$("panel-scrim").addEventListener("click", closeProfile);
document.addEventListener("keydown", (e) => {
  if (!panelKind) return;
  if (e.key === "Escape") { closeProfile(); return; }
  if (e.key === "Tab") {           // keep keyboard focus inside the open panel
    const f = [...$("panel").querySelectorAll("button, input, select, textarea, a[href]")].filter((x) => !x.disabled && x.offsetParent);
    if (!f.length) return;
    if (e.shiftKey && document.activeElement === f[0]) { e.preventDefault(); f.at(-1).focus(); }
    else if (!e.shiftKey && document.activeElement === f.at(-1)) { e.preventDefault(); f[0].focus(); }
  }
});

// ---- Polling ----
async function fastTick() {
  try {
    const [latest, alerts, recent] = await Promise.all([
      getJSON(`/api/latest?device=${WEARABLE_ID}`), getJSON(`/api/alerts?devices=${DEVS()}`),
      getJSON(`/api/readings/recent?device=${WEARABLE_ID}&limit=40`),
    ]);
    S.up = true; S.latest = latest?.timestamp ? latest : null; S.alerts = alerts; S.recent = recent;
  } catch { S.up = false; }
  renderHeader(); renderBanner(); renderVitals(); renderChart(); renderSafety(); renderDevices();
}
async function slowTick() {
  const safe = async (url, fallback) => { try { return await getJSON(url); } catch { return fallback; } };
  [S.reminders, S.history, S.events, S.memory] = await Promise.all([
    safe(`/api/reminders?device=${VOICE_ID}&days=200`, S.reminders),
    safe(`/api/alerts/history?limit=8&devices=${DEVS()}`, S.history),
    safe(`/events?limit=20&devices=${DEVS()}`, S.events),
    safe(`/api/memory-status?device=${VOICE_ID}`, null),   // fine if the memory model isn't wired yet
  ]);
  renderMeds(); renderCognitive(); renderHistory(); renderSafety(); renderDevices(); renderVitals();
}

// ---- Start ----
// ---- Tabs (each sidebar item shows its own panel; the URL hash remembers the tab) ----
const TABS = { overview: "Overview", vitals: "Vitals", reminders: "Reminders", memory: "Memory & routine",
  alerts: "Alerts", location: "Location & home", reports: "Reports" };
const ACTIVE = ["bg-raise", "border-accent", "text-ink", "font-medium"];
const INACTIVE = ["border-transparent", "text-ink-2"];
function showTab(name) {
  if (!TABS[name]) name = "overview";
  document.querySelectorAll("[data-panel]").forEach((p) => p.classList.toggle("hidden", p.dataset.panel !== name));
  document.querySelectorAll(".nav-link").forEach((a) => {
    const on = a.dataset.tab === name;
    ACTIVE.forEach((c) => a.classList.toggle(c, on));
    INACTIVE.forEach((c) => a.classList.toggle(c, !on));
    a.querySelector(".nav-icon").classList.toggle("filled", on);
    a.querySelector(".nav-icon").classList.toggle("text-accent", on);
    on ? a.setAttribute("aria-current", "page") : a.removeAttribute("aria-current");
  });
  $("tab-title").textContent = TABS[name];
  document.title = `SAGE | ${TABS[name]}`;
  closeMenu();
  if (name === "vitals" && chart) requestAnimationFrame(() => chart.resize()); // canvas was hidden
  if (name === "memory" && weekChart) requestAnimationFrame(() => weekChart.resize());
  window.scrollTo({ top: 0 });
}
window.addEventListener("hashchange", () => showTab(location.hash.slice(1)));

// ---- Mobile menu (sidebar slides in under 768px) ----
function openMenu() {
  $("sidebar").classList.remove("-translate-x-full"); $("backdrop").classList.remove("hidden");
  $("menu-btn").setAttribute("aria-expanded", "true");
}
function closeMenu() {
  if (window.matchMedia("(min-width: 768px)").matches) return;
  $("sidebar").classList.add("-translate-x-full"); $("backdrop").classList.add("hidden");
  $("menu-btn").setAttribute("aria-expanded", "false");
}
$("menu-btn").addEventListener("click", openMenu);
$("menu-close").addEventListener("click", closeMenu);
$("backdrop").addEventListener("click", closeMenu);
document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeMenu(); });


// ---- Light / dark mode ----
function applyTheme(t, save) {
  document.documentElement.setAttribute("data-theme", t);
  const next = t === "dark" ? "light" : "dark";
  $("theme-icon").textContent = t === "dark" ? "light_mode" : "dark_mode";
  $("theme-toggle").setAttribute("aria-label", `Switch to ${next} mode`);
  $("theme-toggle").title = `Switch to ${next} mode`;
  if (save) { try { localStorage.setItem("sage-theme", t); } catch {} }
  themeChart(); themeWeekChart();
}
$("theme-toggle").addEventListener("click", () =>
  applyTheme(document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark", true));

if (!PID) location.replace("/patients");
renderSoundToggle();
makeChart();
applyTheme(document.documentElement.getAttribute("data-theme"), false);
showTab(location.hash.slice(1));
(async () => {
  await loadProfiles();          // sets this elder's band + voice device ids before anything is fetched
  loadReports();
  fastTick(); slowTick();
  setInterval(fastTick, FAST_MS); setInterval(slowTick, SLOW_MS);
})();
