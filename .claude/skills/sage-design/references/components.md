# SAGE components

## Buttons

| Variant | Fill | Text | Border | Hover | Use |
|---|---|---|---|---|---|
| Primary | accent | on-accent | none | accent-hover | One per region: upload, sign in |
| Secondary | surface1 | text1 | border-visible | surface3 | "I'm checking on her" |
| Ghost | transparent | text2 | none | surface3 + text1 | Toolbar icons, dismiss |
| Urgent | error solid | white | none | 8% darker | Call family, call ambulance |

Height 40px (44px hit area), padding 0 16px, radius 8, label 14/600. Active: translateY(1px). Disabled: surface3 fill, text3 ink, `cursor: not-allowed`, `disabled` attribute. Focus: 2px accent outline, 2px offset, instant.

## Cards

surface1, 1px border, radius 14, padding 24, light-mode shadow. Title row: subheading serif left, optional icon or badge right, 1px divider below with 12px spacing. Never nest a card in a card; use a surface2 well instead.

## Stat tile

Label (14/500 text2) top left, badge top right; metric 34/500 tabular with unit 14 text2; one supporting visual (sparkline or bar); footer row 13 text3 above a 1px divider.

## Badges

Pill, 2px 10px, label 13/600. Tones: ok, warn, danger, info (accent), neutral. Always text plus tint; never a dot alone.

## Inputs

Height 44, surface2 fill, 1px border-visible, radius 8, 16px text. Label above, 13/600 text1. Focus: accent border + 3px accent ring at 20%. Error: error border, message below in error colour, cleared on next input.

## Navigation

Sidebar rail 76px, expands to 256px on hover/focus; collapses to a slide-in menu under 768px. Item: 44px tall, radius 8, icon + label. Active: accent-subtle fill, accent text and icon, 3px accent bar on the left edge.

## Tables

Head: label 13/600 text3, sentence case, bottom border. Rows 14/400, 12px vertical padding, divider between rows, hover surface2.

## Overlays

Slide-over from the right, max 448px, surface1, overlay shadow, scrim black at 50%. Focus trapped, Escape closes, focus returns to opener.

## States

- **Empty:** one line saying what belongs here, plus the one action that fills it.
- **Loading:** skeleton blocks in surface3 shaped like the content.
- **Error:** what broke, in plain words, and what to do next.
- **Roadmap:** content at 35% opacity with a centred note naming the missing hardware.
