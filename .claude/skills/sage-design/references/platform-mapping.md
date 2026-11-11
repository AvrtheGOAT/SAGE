# SAGE platform mapping

## CSS custom properties

The product stores colours as RGB triplets so Tailwind can apply alpha (`rgb(var(--accent) / .2)`). The canonical Hue names are aliases.

```css
:root, :root[data-theme="light"] {
  color-scheme: light;
  --canvas: 246 242 234; --surface: 255 253 248; --inset: 251 248 242; --raise: 239 233 222;
  --line: 227 220 207; --line-strong: 207 198 182;
  --ink: 35 32 27; --ink-2: 87 81 74; --ink-3: 107 100 90; --ink-4: 207 198 182;
  --accent: 45 79 158; --accent-hover: 36 66 134; --on-accent: 255 255 255;
  --ok: 59 117 73; --warn: 143 87 11; --danger: 179 38 30; --info: 45 79 158; --danger-solid: 179 38 30;
  --ok-soft: #E3EEE2; --warn-soft: #F6E9D2; --danger-soft: #F7E0DB; --info-soft: #E4EAF7; --accent-soft: #E4EAF7;
  --shadow-card: 0 1px 2px rgb(60 44 20 / .05), 0 4px 16px -8px rgb(60 44 20 / .10);
  --shadow-overlay: 0 24px 48px -16px rgb(60 44 20 / .25);

  --font-display: "Newsreader", Georgia, "Times New Roman", serif;
  --font-body: "Hanken Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif;
  --font-mono: "IBM Plex Mono", ui-monospace, monospace;

  --radius-element: 4px; --radius-control: 8px; --radius-component: 14px; --radius-container: 20px; --radius-pill: 999px;
  --ease: cubic-bezier(0.2, 0, 0, 1); --dur-micro: 160ms; --dur-short: 240ms;

  /* Hue canonical aliases */
  --background: rgb(var(--canvas)); --bg: var(--background);
  --surface1: rgb(var(--surface)); --surface2: rgb(var(--inset)); --surface3: rgb(var(--raise));
  --border: rgb(var(--line)); --border-visible: rgb(var(--line-strong));
  --text1: rgb(var(--ink)); --text2: rgb(var(--ink-2)); --text3: rgb(var(--ink-3)); --text4: rgb(var(--ink-4));
  --accent-subtle: var(--accent-soft);
  --success: rgb(var(--ok)); --warning: rgb(var(--warn)); --error: rgb(var(--danger));
  --success-bg: var(--ok-soft); --warning-bg: var(--warn-soft); --error-bg: var(--danger-soft);
}
:root[data-theme="dark"] {
  color-scheme: dark;
  --canvas: 23 21 19; --surface: 32 29 26; --inset: 27 25 22; --raise: 42 38 34;
  --line: 54 49 44; --line-strong: 74 68 61;
  --ink: 239 234 225; --ink-2: 185 177 166; --ink-3: 150 141 129; --ink-4: 107 100 90;
  --accent: 157 182 242; --accent-hover: 204 216 241; --on-accent: 20 33 63;
  --ok: 134 199 154; --warn: 227 174 91; --danger: 240 144 127; --info: 157 182 242; --danger-solid: 192 53 42;
  --ok-soft: rgb(134 199 154 / .12); --warn-soft: rgb(227 174 91 / .13); --danger-soft: rgb(240 144 127 / .14);
  --info-soft: rgb(157 182 242 / .13); --accent-soft: rgb(157 182 242 / .13);
  --shadow-card: none; --shadow-overlay: 0 24px 48px -16px rgb(0 0 0 / .6);
}
```

## Tailwind (CDN config)

```js
const v = (n) => `rgb(var(--${n}) / <alpha-value>)`;
tailwind.config = { theme: { extend: {
  colors: { canvas: v("canvas"), surface: v("surface"), inset: v("inset"), raise: v("raise"), line: v("line"),
    "line-strong": v("line-strong"), ink: v("ink"), "ink-2": v("ink-2"), "ink-3": v("ink-3"),
    accent: v("accent"), "accent-hover": v("accent-hover"), "on-accent": v("on-accent"),
    ok: v("ok"), warn: v("warn"), danger: v("danger"), info: v("info"), "danger-solid": v("danger-solid"),
    "ok-soft": "var(--ok-soft)", "warn-soft": "var(--warn-soft)", "danger-soft": "var(--danger-soft)",
    "info-soft": "var(--info-soft)", "accent-soft": "var(--accent-soft)" },
  fontFamily: { sans: "var(--font-body)", display: "var(--font-display)" },
  fontSize: { xs: ["0.8125rem", { lineHeight: "1.4" }], sm: ["0.875rem", { lineHeight: "1.5" }],
    base: ["1rem", { lineHeight: "1.55" }], h4: ["1.25rem", { lineHeight: "1.25" }],
    h3: ["1.25rem", { lineHeight: "1.25" }], h2: ["1.5rem", { lineHeight: "1.2" }],
    h1: ["1.75rem", { lineHeight: "1.15" }], metric: ["2.125rem", { lineHeight: "1.05", letterSpacing: "-0.02em" }] },
  borderRadius: { lg: "8px", xl: "14px", "2xl": "20px" }
} } };
```

## SwiftUI

```swift
extension Color {
  static let sageBackground = Color(light: 0xF6F2EA, dark: 0x171513)
  static let sageSurface    = Color(light: 0xFFFDF8, dark: 0x201D1A)
  static let sageText1      = Color(light: 0x23201B, dark: 0xEFEAE1)
  static let sageText2      = Color(light: 0x57514A, dark: 0xB9B1A6)
  static let sageAccent     = Color(light: 0x2D4F9E, dark: 0x9DB6F2)
  static let sageSuccess    = Color(light: 0x3B7549, dark: 0x86C79A)
  static let sageWarning    = Color(light: 0x8F570B, dark: 0xE3AE5B)
  static let sageError      = Color(light: 0xB3261E, dark: 0xF0907F)
}
extension Font {
  static func sageHeading(_ s: CGFloat = 28) -> Font { .custom("Newsreader", size: s).weight(.medium) }
  static func sageBody(_ s: CGFloat = 16) -> Font { .custom("HankenGrotesk-Regular", size: s) }
}
```
