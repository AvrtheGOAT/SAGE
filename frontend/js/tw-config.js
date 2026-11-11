// Tailwind (CDN) config shared by every SAGE page. Every colour and font is a CSS variable from
// css/sage.css, so one class works in light and dark mode. Load right after the Tailwind CDN script.
(function () {
  const v = (name) => `rgb(var(--${name}) / <alpha-value>)`;
  if (!window.tailwind) return;
  tailwind.config = {
    theme: { extend: {
      colors: {
        canvas: v("canvas"), surface: v("surface"), inset: v("inset"), raise: v("raise"),
        line: v("line"), "line-strong": v("line-strong"),
        ink: v("ink"), "ink-2": v("ink-2"), "ink-3": v("ink-3"), "ink-4": v("ink-4"),
        accent: v("accent"), "accent-hover": v("accent-hover"), "on-accent": v("on-accent"),
        "on-status": v("on-status"), "on-solid": v("on-solid"), scrim: v("scrim"),
        ok: v("ok"), warn: v("warn"), danger: v("danger"), info: v("info"),
        "danger-solid": v("danger-solid"), "danger-solid-hover": v("danger-solid-hover"),
        "ok-soft": "var(--ok-soft)", "warn-soft": "var(--warn-soft)", "danger-soft": "var(--danger-soft)",
        "info-soft": "var(--info-soft)", "accent-soft": "var(--accent-soft)",
        // Old JS strings still say text-white on solid red; map it to the token.
        white: v("on-solid"),
      },
      fontFamily: { sans: "var(--font-body)", display: "var(--font-display)" },
      // Type scale, ratio 1.2: label/meta 13, secondary 14, body 16, card title 20, section 24, screen 28, metric 34.
      fontSize: {
        xs: ["0.8125rem", { lineHeight: "1.4" }], sm: ["0.875rem", { lineHeight: "1.5" }], base: ["1rem", { lineHeight: "1.55" }],
        h4: ["1.25rem", { lineHeight: "1.25" }], h3: ["1.25rem", { lineHeight: "1.25" }], h2: ["1.5rem", { lineHeight: "1.2" }],
        h1: ["1.75rem", { lineHeight: "1.15", letterSpacing: "-0.005em" }],
        metric: ["2.125rem", { lineHeight: "1.05", letterSpacing: "-0.02em" }],
      },
      borderRadius: { DEFAULT: "4px", lg: "8px", xl: "14px", "2xl": "20px" },
      transitionTimingFunction: { DEFAULT: "cubic-bezier(0.2, 0, 0, 1)" },
    } },
  };
})();
