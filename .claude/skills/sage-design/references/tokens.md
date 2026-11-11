# SAGE tokens

## Fonts

| Role | Family | Weights | Why |
|---|---|---|---|
| Display | Newsreader (Google Fonts, optical size) | 500 | A text serif with a letter-writing warmth; its optical sizing keeps 20px titles sturdy. |
| Body / data | Hanken Grotesk (Google Fonts) | 400, 500, 600 | Open humanist grotesk with clear tabular figures for vitals. |
| Mono | IBM Plex Mono | 400 | Code only; never loaded on product screens. |

Fallbacks: `"Newsreader", Georgia, "Times New Roman", serif` and `"Hanken Grotesk", system-ui, -apple-system, "Segoe UI", sans-serif`.

## Type scale (ratio 1.2)

| Token | Size | Line height | Letter spacing | Weight | Use |
|---|---|---|---|---|---|
| `--display` | 34px | 1.1 | -0.01em | 500 serif | Sign-in hero |
| `--heading` | 28px | 1.15 | -0.005em | 500 serif | Screen title |
| `--subheading` | 20px | 1.25 | 0 | 500 serif | Card and panel titles |
| `--body` | 16px | 1.55 | 0 | 400 | Prose, list rows |
| `--body-sm` | 14px | 1.5 | 0 | 400 | Secondary lines, table cells |
| `--caption` | 13px | 1.4 | 0 | 400 | Timestamps, notes |
| `--label` | 13px | 1.3 | 0 | 600 | Field labels, table heads, badges |
| metric | 34px | 1.05 | -0.02em | 500 sans | Vital readings (tabular) |

## Colour

| Token | Light | Dark | Role |
|---|---|---|---|
| `--background` / `--bg` | #F6F2EA | #171513 | Page |
| `--surface1` | #FFFDF8 | #201D1A | Cards |
| `--surface2` | #FBF8F2 | #1B1916 | Inputs, wells |
| `--surface3` | #EFE9DE | #2A2622 | Hover, segmented track |
| `--border` | #E3DCCF | #36312C | Card edges, dividers |
| `--border-visible` | #CFC6B6 | #4A443D | Inputs, secondary buttons |
| `--text1` | #23201B | #EFEAE1 | Headings, body |
| `--text2` | #57514A | #B9B1A6 | Secondary |
| `--text3` | #6B645A | #968D81 | Meta, placeholders |
| `--text4` | #CFC6B6 | #6B645A | Disabled |
| `--accent` | #2D4F9E | #9DB6F2 | Primary action, current nav, links, info |
| `--accent-subtle` | #E4EAF7 | rgba(157,182,242,.13) | Active nav fill, info badge |
| `--success` | #3B7549 | #86C79A | OK |
| `--warning` | #8F570B | #E3AE5B | Attention |
| `--error` | #B3261E | #F0907F | Urgent text |
| `--success-bg` | #E3EEE2 | rgba(134,199,154,.12) | |
| `--warning-bg` | #F6E9D2 | rgba(227,174,91,.13) | |
| `--error-bg` | #F7E0DB | rgba(240,144,127,.14) | |
| error solid | #B3261E | #C0352A | Emergency buttons, white text |

Contrast (measured): text3 on background 5.23 light / 5.57 dark; accent on background 6.91 / 9.03; white on accent 7.71; white on error solid 6.54 / 5.55.

## Spacing

| Token | px | Use |
|---|---|---|
| 2xs | 2 | Icon nudge |
| xs | 4 | Label to field |
| sm | 8 | Inside control groups |
| md | 16 | Between rows |
| lg | 24 | Card padding, grid gap |
| xl | 32 | Between screen sections |
| 2xl | 48 | Landing section padding (mobile) |
| 3xl | 64 | Landing section padding |
| 4xl | 96 | Landing hero |

## Radii

element 4 · control 8 · component 14 · container 20 · pill 999 (badges only).

## Elevation

Subtle. Light: `0 1px 2px rgba(60,44,20,.05), 0 4px 16px -8px rgba(60,44,20,.10)`. Dark: none. Overlays: `0 24px 48px -16px` at .25 (light) / .6 (dark).

## Motion

Smooth. `cubic-bezier(0.2, 0, 0, 1)`, 160ms for hovers, 240ms for panels. Animate opacity, transform and colours only. Reduced motion: no transitions.

## Iconography

Material Symbols Outlined, `'wght' 300, 'opsz' 24`; `FILL 1` only on the emergency and brand mark glyphs.
