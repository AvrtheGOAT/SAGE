// SAGE motion kit: small vanilla ports of a few Magic UI / Cult UI ideas (both MIT), fitted to SAGE's
// calm style. No dependencies. Every effect is skipped when the person asks for reduced motion,
// and nothing here hides content unless JavaScript is running.
//   - Theme reveal   (Magic UI "Animated Theme Toggler"): the new theme spreads in a circle from the toggle.
//   - Number ticker  (Magic UI "Number Ticker"): a reading counts to its new value.
//   - Blur fade      (Magic UI "Blur Fade"): sections settle in as they scroll into view.
(function () {
  const reduced = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // ---------- Theme reveal ----------
  // Wraps whatever click handler the page already has on #theme-toggle: the click is re-sent inside
  // a View Transition, so the page's own code still does the switching.
  let replaying = false;
  document.addEventListener("click", (e) => {
    const btn = e.target.closest && e.target.closest("#theme-toggle");
    if (!btn || replaying || reduced() || document.hidden || !document.startViewTransition) return;
    e.stopImmediatePropagation();
    e.preventDefault();
    const r = btn.getBoundingClientRect();
    const x = r.left + r.width / 2, y = r.top + r.height / 2;
    const radius = Math.hypot(Math.max(x, innerWidth - x), Math.max(y, innerHeight - y));
    const vt = document.startViewTransition(() => { replaying = true; try { btn.click(); } finally { replaying = false; } });
    vt.ready.then(() => {
      document.documentElement.animate(
        { clipPath: [`circle(0px at ${x}px ${y}px)`, `circle(${radius}px at ${x}px ${y}px)`] },
        { duration: 420, easing: "cubic-bezier(0.2, 0, 0, 1)", pseudoElement: "::view-transition-new(root)" });
    }).catch(() => {});
  }, true);

  // ---------- Number ticker ----------
  // tick(el, value): counts el from its current number to value. Non-numbers are set as text.
  const running = new WeakMap();
  function tick(el, value) {
    if (!el) return;
    cancelAnimationFrame(running.get(el)); // a newer value always wins over a count still running
    const to = Number(value);
    const from = Number(el.textContent);
    if (value === null || value === undefined || value === "" || !Number.isFinite(to)) { el.textContent = value ?? "–"; return; }
    if (reduced() || !Number.isFinite(from) || from === to) { el.textContent = String(to); return; }
    const start = performance.now(), dur = 600;
    const step = (now) => {
      const t = Math.min(1, (now - start) / dur);
      const eased = 1 - Math.pow(1 - t, 3);
      el.textContent = String(Math.round(from + (to - from) * eased));
      if (t < 1) running.set(el, requestAnimationFrame(step));
    };
    running.set(el, requestAnimationFrame(step));
  }

  // ---------- Blur fade ----------
  // blurFade(selector): elements below the fold start soft and settle in when they reach the viewport.
  // Elements already on screen are left alone, so nothing visible ever blinks.
  // A plain scroll check rather than an IntersectionObserver: a jump (End key, a #link) that skips
  // past an element still reveals it, because anything above the fold line counts as seen.
  // Items that arrive together (a row of steps, ledger rows) come in one after another.
  // With reduced motion it is a plain, gentle opacity fade: no movement, no blur.
  function blurFade(selector) {
    let pending = [...document.querySelectorAll(selector)].filter((el) => el.getBoundingClientRect().top > innerHeight);
    if (!pending.length) return;
    const calm = reduced();
    // hidden state first, with no transition, so nothing animates out on load; then switch the transition on
    pending.forEach((el) => { el.style.transition = "none"; el.classList.add("blur-fade", "is-pending", ...(calm ? ["blur-fade--calm"] : [])); });
    void document.body.offsetHeight;
    pending.forEach((el) => { el.style.transition = ""; });
    const check = () => {
      const line = innerHeight * 0.88;
      const order = new Map(); // stagger within each group (siblings), not across the whole page
      pending = pending.filter((el) => {
        if (el.getBoundingClientRect().top >= line) return true;
        const n = order.get(el.parentElement) || 0;
        order.set(el.parentElement, n + 1);
        el.style.transitionDelay = calm ? "" : `${Math.min(n, 5) * 90}ms`;
        el.classList.remove("is-pending");
        el.addEventListener("transitionend", () => { el.style.transitionDelay = ""; }, { once: true });
        return false;
      });
      if (!pending.length) { removeEventListener("scroll", check); removeEventListener("resize", check); }
    };
    addEventListener("scroll", check, { passive: true });
    addEventListener("resize", check, { passive: true });
  }

  window.SageMotion = { tick, blurFade, reduced };
})();
