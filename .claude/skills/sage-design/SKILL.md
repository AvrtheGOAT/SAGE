---
name: sage-design
description: "This skill should be used when the user explicitly says 'SAGE style', 'SAGE design', '/sage-design', or directly asks to use/apply the SAGE design system. NEVER trigger automatically for generic UI or design tasks."
version: 1.0.0
allowed-tools: [Read, Write, Edit, Glob, Grep]
---

# SAGE design language: "Letter from home"

## 0. Philosophy

A letter from home that happens to carry live safety data. Warm paper, ink-dark text, one fountain-pen blue for the things you can act on. The lineage is the handwritten note on the fridge door and the hospital discharge summary: personal in voice, exact in fact. The tension that gives SAGE its character is **calm surface, urgent payload**: the page stays quiet so that the one red banner, when it comes, is impossible to miss.

## 1. Principles

1. **Calm is the default state.** A screen where everything is fine shows no saturated colour except the ink-blue accent on the current nav item and the primary action.
2. **Colour means the person changed.** Green, amber and red appear only beside a reading or an event about the resident; never as decoration, never on chrome.
3. **The serif speaks, the sans reports.** Newsreader carries titles and the person's name; Hanken Grotesk carries every number, label, button and table cell.
4. **Name the person, not the device.** Copy says "Kamala's heart rate", not "Sensor HR". Errors say what to do next.
5. **One ink.** Ink-blue is the only accent and doubles as the info status. No second brand colour exists.
6. **Paper has edges, not glow.** Depth is a 1px warm border plus, in light mode only, a soft warm shadow. Dark mode is borders and surface steps.
7. **Urgent is solid; everything else is tinted.** Only emergency actions (call family, call ambulance) use a solid red fill.

## 2. Craft rules

**Hierarchy layers**

| Layer | Treatment |
|---|---|
| Screen title | Newsreader 28/500, text1 |
| Card title | Newsreader 20/500, text1 |
| Metric | Hanken Grotesk 34/500, tabular figures, text1 |
| Body | Hanken Grotesk 16/400, text1 |
| Secondary | Hanken Grotesk 14/400, text2 |
| Label / meta | Hanken Grotesk 13/600 or 13/400, text3, sentence case |

**Font budget.** Two families per screen, three weights of the sans (400/500/600), one weight of the serif (500). Never italic inside a roman heading.

**Spacing.** 4px base, 8px rhythm: 8 inside a control group, 16 between rows, 24 card padding and grid gap, 32 between screen sections.

**Colour strategy.** 60% paper, 30% surface/ink text, 10% ink-blue and status. If a screen has more than two status colours visible at once, at least one is wrong.

**Composition.** Lead every screen with the thing a worried family member checks first (is she OK right now?), then trends, then history. Tables before cards for history.

**Squint test.** Blur the screen: you should see one dark title, a calm field of cards, and at most one coloured mass. If you see a rainbow, remove colour.

## 3. Anti-patterns

- No gradients, glows, orbit rings or decorative blobs.
- No glassmorphism or backdrop blur.
- No tracked uppercase labels or eyebrows above headings.
- No serif on numbers, buttons, labels or table cells.
- No pure white (#FFF) page or pure black (#000) dark canvas; paper is warm.
- No navy or blue-tinted dark mode; dark is lamp-lit charcoal.
- No solid status fills except the emergency red actions.
- No border-radius above 20px on any container; badges are the only pills.
- No emoji as icons; Material Symbols Outlined only.
- No em-dashes or en-dashes in copy; use a comma, colon or full stop.
- No invented readings: data the prototype does not have is shown as roadmap, greyed, labelled.
- No `transition: all`; animate opacity, transform and colours only.

## 4. Workflow

1. Read `references/tokens.md` and copy the CSS block from `references/platform-mapping.md`.
2. Build with the components in `references/components.md`; every control needs default, hover, active, focus-visible, disabled.
3. Check contrast (all text pairs in the token file pass 4.5:1) and test both themes.
4. Honour `prefers-reduced-motion`.
