// Interactive parts of the sign-in page, as two small React islands (React 18 UMD + htm, no build step).
// Everything here is an example played in the browser: nothing is sent to the server.
// The server-rendered markup inside #demo and #sos is the no-JS fallback; React replaces it on mount.
(function () {
  if (!window.React || !window.ReactDOM || !window.htm) return; // CDN unavailable: keep the static page
  const { useState, useEffect, useLayoutEffect, useRef } = React;
  const html = htm.bind(React.createElement);
  const Fragment = React.Fragment;
  const Icon = ({ name, filled }) =>
    html`<span className=${"material-symbols-outlined" + (filled ? " filled" : "")} aria-hidden="true">${name}</span>`;

  // ---------- 1. "What Rohan sees": switch the example day ----------
  const SCENES = {
    calm: {
      tab: "A calm day",
      badge: ["ok", "All good"],
      rows: [
        ["ok", "wb_sunny", "Morning check-in", "All is well"],
        ["ok", "medication", "Medicines", "Taken, confirmed by voice"],
        ["info", "monitor_heart", "Heart rate", "A trend, not a diagnosis"],
      ],
    },
    missed: {
      tab: "A missed medicine",
      badge: ["warn", "Needs attention"],
      rows: [
        ["warn", "medication", "Missed medicine", "No reply after reminders and retries. Family was notified."],
        ["ok", "wb_sunny", "Morning check-in", "All is well"],
        ["info", "monitor_heart", "Heart rate", "A trend, not a diagnosis"],
      ],
    },
    fall: {
      tab: "A fall",
      badge: ["danger", "Needs help now"],
      rows: [
        ["danger", "personal_injury", "Kamala may have fallen", "Impact followed by stillness. The band is sounding a siren."],
        ["warn", "family_restroom", "Family alerted", "The backup contact is next if nobody responds."],
        ["info", "call", "Your choice", "Check on her, call an ambulance, or mark a false alarm."],
      ],
    },
  };
  const ORDER = Object.keys(SCENES);

  function DemoNote({ host }) {
    const [scene, setScene] = useState("calm");
    const tabRefs = useRef([]);
    const rowsRef = useRef(null);
    const mounted = useRef(false);
    const s = SCENES[scene];

    useEffect(() => { host.dataset.scene = scene; }, [scene]);
    // Fade the new rows in: apply the hidden start state, force a reflow, then let them transition.
    useLayoutEffect(() => {
      if (!mounted.current) { mounted.current = true; return; }
      const el = rowsRef.current;
      el.classList.add("is-entering");
      void el.offsetWidth;
      el.classList.remove("is-entering");
    }, [scene]);

    const go = (i, focus) => {
      const n = (i + ORDER.length) % ORDER.length;
      setScene(ORDER[n]);
      if (focus) tabRefs.current[n].focus();
    };
    const onKey = (e, i) => {
      const to = { ArrowRight: i + 1, ArrowLeft: i - 1, Home: 0, End: ORDER.length - 1 }[e.key];
      if (to === undefined) return;
      e.preventDefault();
      go(to, true);
    };

    return html`<${Fragment}>
      <div className="note-head">
        <span className="note-title">What Rohan sees</span>
        <span id="demo-badge" className=${"badge " + s.badge[0]}>${s.badge[1]}</span>
      </div>
      <div className="note-tabs" role="tablist" aria-label="Choose an example day">
        ${ORDER.map((k, i) => html`
          <button key=${k} type="button" role="tab" id=${"demo-tab-" + k} className="note-tab"
            aria-selected=${k === scene} aria-controls="demo-rows" tabIndex=${k === scene ? 0 : -1}
            ref=${(el) => (tabRefs.current[i] = el)}
            onClick=${() => go(i)} onKeyDown=${(e) => onKey(e, i)}>${SCENES[k].tab}</button>`)}
      </div>
      <div id="demo-rows" ref=${rowsRef} className="note-rows" role="tabpanel"
        aria-labelledby=${"demo-tab-" + scene} aria-live="polite">
        ${s.rows.map(([tone, icon, label, value]) => html`
          <div className="note-row" key=${scene + label}>
            <span className=${"note-icon " + tone}><${Icon} name=${icon} /></span>
            <div><div className="note-label">${label}</div><div className="note-value">${value}</div></div>
          </div>`)}
      </div>
      <p className="note-foot">An example of the family dashboard, not live data.</p>
    <//>`;
  }

  // ---------- 2. Try the SOS safety net ----------
  // Demo pacing only. In the product, the backup and services steps wait minutes, not seconds.
  const STEP_MS = 2600;
  const STEPS = [
    ["cancel", null, "Cancel window", "5 seconds to cancel a press by mistake"],
    ["family", "family_restroom", "Family alerted", "The dashboard and the alarm sound"],
    ["backup", "contact_phone", "Backup contact", "If nobody in the family responds"],
    ["services", "local_hospital", "Emergency services", "Only if nobody responds at all"],
  ];
  const LAST = STEPS.length - 1;
  const ESCALATION = [
    null,
    "Family alerted. The dashboard shows the alert and sounds the alarm.",
    "Nobody responded yet, so the backup contact is alerted.",
    "Still no response, so SAGE calls emergency services.",
  ];
  // phase: idle | counting | escalating | cancelled | handled; at = index of the step reached
  const IDLE = { phase: "idle", left: 5, at: -1 };

  function statusText({ phase, left, at }) {
    if (phase === "counting") return left === 5 ? "SOS pressed. 5 seconds to cancel." : `${left} second${left > 1 ? "s" : ""} to cancel.`;
    if (phase === "escalating") return ESCALATION[at];
    if (phase === "cancelled") return "Cancelled. Nobody was disturbed.";
    if (phase === "handled") return "Family is on it, so escalation stops. Family decides first.";
    return "One press starts a 5-second cancel window.";
  }

  function SosDemo({ host }) {
    const [st, setSt] = useState(IDLE);
    const { phase, left, at } = st;
    const refs = { press: useRef(null), cancel: useRef(null), respond: useRef(null), reset: useRef(null) };
    const touched = useRef(false);

    // The clock: one timer per state, cleared automatically when the state moves on.
    useEffect(() => {
      if (phase === "counting") {
        const t = setTimeout(() => setSt((p) => (p.left > 1 ? { ...p, left: p.left - 1 } : { phase: "escalating", left: 0, at: 1 })), 1000);
        return () => clearTimeout(t);
      }
      if (phase === "escalating" && at < LAST) {
        const t = setTimeout(() => setSt((p) => ({ ...p, at: p.at + 1 })), STEP_MS);
        return () => clearTimeout(t);
      }
    }, [st]);

    const settled = phase === "cancelled" || phase === "handled" || (phase === "escalating" && at === LAST);
    // Keep focus on the one control that matters next (never on first load).
    useEffect(() => {
      if (!touched.current) return;
      const next = phase === "idle" ? "press" : phase === "counting" ? "cancel" : settled ? "reset" : "respond";
      refs[next].current && refs[next].current.focus();
    }, [phase, settled]);

    useEffect(() => { host.dataset.state = phase === "handled" ? "handled" : phase === "counting" || phase === "escalating" ? STEPS[at][0] : "idle"; }, [phase, at]);

    const act = (next) => () => { touched.current = true; setSt(next); };
    const stepClass = (i) => {
      const active = (phase === "counting" || phase === "escalating") && i === at;
      const done = (phase === "escalating" && i < at) || (phase === "handled" && i <= at);
      return [active && "is-active", done && "is-done"].filter(Boolean).join(" ") || undefined;
    };
    const count = phase === "counting" ? left : phase === "escalating" || (phase === "handled" && at > 0) ? 0 : 5;

    return html`<${Fragment}>
      <div className="sos-intro">
        <h3>Try the SOS safety net</h3>
        <p>Press the button the way Kamala would. Nothing is sent; this only shows the order things happen in.</p>
        <div className="sos-controls">
          ${phase === "idle" && html`
            <button type="button" ref=${refs.press} className="sos-press" aria-describedby="sos-status"
              onClick=${act({ phase: "counting", left: 5, at: 0 })}><${Icon} name="sos" filled /><span>Press SOS</span></button>`}
          ${phase === "counting" && html`
            <button type="button" ref=${refs.cancel} className="btn btn-secondary"
              onClick=${act({ ...IDLE, phase: "cancelled" })}>Cancel, I’m fine</button>`}
          ${phase === "escalating" && !settled && html`
            <button type="button" ref=${refs.respond} className="btn btn-secondary"
              onClick=${act({ ...st, phase: "handled" })}><${Icon} name="check_circle" />I’m checking on her</button>`}
          ${phase !== "idle" && phase !== "counting" && html`
            <button type="button" ref=${refs.reset} className="btn btn-ghost" onClick=${act(IDLE)}>Start again</button>`}
        </div>
        <p id="sos-status" className="sos-status" role="status" aria-live="polite">${statusText(st)}</p>
      </div>
      <ol className="sos-steps" id="sos-steps">
        ${STEPS.map(([key, icon, title, note], i) => html`
          <li key=${key} data-step=${key} className=${stepClass(i)} aria-current=${i === at && !settled && phase !== "idle" ? "step" : undefined}>
            <span className="sos-dot">${icon ? html`<${Icon} name=${icon} />` : html`<span className="sos-count" id="sos-count">${count}</span>`}</span>
            <div><strong>${title}</strong><span>${note}</span></div>
          </li>`)}
      </ol>
    <//>`;
  }

  // ---------- Mount the islands ----------
  const mount = (id, Component) => {
    const host = document.getElementById(id);
    if (host) ReactDOM.createRoot(host).render(html`<${Component} host=${host} />`);
  };
  mount("demo", DemoNote);
  mount("sos", SosDemo);
})();
