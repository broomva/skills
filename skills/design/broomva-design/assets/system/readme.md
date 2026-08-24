# Broomva Design System

**Calm, monochrome design on a blue axis, built for a work-orchestration agent.** Every "black" is a barely-perceptible dark blue (the Broomva ink), and depth cues — shadows, hovers, the composer halo, focus rings, the Undertow — carry subtle tones of frosted liquid-glass blue. It reads as plain monochrome until you look closely. Then everything is faintly, coolly blue.

This system consolidates the primitives designed for Mission Control, Broomva's work plane: the work-as-noun model, the plain-voice state vocabulary, the disclosure ladder, and the Undertow live signal. These are Broomva's own inventions, not inherited scaffolding — they're the load-bearing ideas.

---

## What Broomva is (product context)

A **chat-first, work-orchestration AI agent product**. Workspaces and agents; each work item is an object with a lifecycle; chat is one projection of a running session, never the owner of the work. The shell never scrolls; inner panels scroll.

---

## The philosophy

Broomva orchestrates loops of agentic workflows under structure: control, governance, and bio-inspired principles of metacognition, persistence, stability and flow. Autonomy is the moat; control is the engine. **The scarce resource is unsupervised hours** — not tokens, not compute: how long an agent runs before a human must look. The design language exists to make that legible and calm.

- **The workspace is the substrate.** An FS + sh environment. A folder is work at any scale — question, task, project, initiative; depth is meaning, not schema. Frontmatter is the orchestration contract (kind, state, owner, budget, gate), living in the files.
- **The session is the verb.** A running agent timeline of events (agent, user, tools). Anything spawns one: you, the orchestrator, another session. Work is the noun; sessions do the work.
- **Chat is a projection.** A session renders the work; it never owns it. The same run can appear in a side panel, a thread, or a handoff page.
- **The orchestrator is an agent.** A session that schedules sessions. It has presence (a live signal in the chrome), a session you can open, and a wake log — never a settings page. Setting a schedule is a sentence.
- **The tick is a prompt.** Wakes have causes: a worker returning, your message, an interval, a self-set routine. The loop is legible — show why it woke.
- **The branch is the receipt.** Evidence over claims: `run/<id>`, diffstats, judge verdicts. Never fake progress percentages.
- **The gate is yours.** No loop can auto-Done. Clean runs wait at "Needs you"; approving is the one human verb. Needing you is a gate, not a failure — mark halts in accent-blue, never red.
- **The look is the transaction.** Hours of agent work compress to: what changed · what it decided · what it asks. Autonomy is bought with good looks — a fast, confident look earns the next longer unsupervised run.
- **Standing loops never close.** Open-ended problems are folders with a cadence (`kind: routine`); the routine is the deliverable. `gate: none` spends zero human hours until a run flags something.
- **Calm is load-bearing.** Live signals breathe, they don't spin for attention. Motion encodes presence, not urgency.

## The primitives

Not generic UI atoms — the specific inventions that make the philosophy legible:

| Primitive | What it does |
|---|---|
| **Work states** | One vocabulary, two registers: plain voice is canon (Queued · Running · Stuck · Needs you · Done · Standing); system enums (Todo/InProgress/Blocked/InReview) are a developer surface only. See `guidelines/work-model.html`. |
| **The disclosure ladder** | Three rungs: ambient (feed, chip, bench, Undertow) → the gate (the look; control is verbs) → receipts (inspector, opt-in). Fully operable from rungs 1–2. See `guidelines/disclosure.html`. |
| **The Undertow** | THE running signal — a contained halo of breathing pools, a counter-phase tide, and a faint orbit, on three overlapping rhythms so it never quite repeats. The tidepool dot is the same weather at dot scale. Presence, not progress. See `guidelines/motion-undertow.html` and `tokens/motion.css`. |
| **The lifecycle rail** | A horizontal stage tracker (proposed → queued → running → review → done) for the work-item inspector. `components/work/LifecycleRail.jsx`; app usage in `apps/maestro/WorkDetail.jsx`. |
| **Receipts** | Evidence blocks — branch, diffstat, judge verdict — that stand in for progress bars. `.mc-receipt-block`, `.mc-receipt`. |
| **The gate / the look** | The narrative overlay and run card that compress a session to what changed · what it decided · what it asks, with Approve / Send back as the only controls. `.mc-overlay`, `.mc-run-card`. |

## Visual foundations

### Color
- **Monochrome by default**, on a cool axis. Whites, cool grays (hue 265, chroma ≤ 0.01), dark-blue ink `oklch(0.175 0.022 265)`. Never pure `#000`; never pure-white text in dark mode.
- **Color earns its place.** It appears in exactly five situations: (1) the Undertow / running-card glow, (2) status pills, (3) agent avatar accents, (4) inline assistant link pills, (5) the frosted-blue interaction layer (hover, selected, focus, glow shadows).
- **One hue family.** ai-blue (260) everywhere; accent-blue (235) only when two accents must coexist — it owns "Needs you". No decorative color, no gradient washes, no colored left-border strips.
- **All colors are OKLCH.** Tint with `color-mix(in oklab, …)` or alpha; never invent hexes.

### Backgrounds
- Flat white canvas; cool-gray `--bv-canvas-soft` sidebar. No imagery in chrome, no textures, no grain, no gradient washes.
- Dark mode: deep blue-purple `oklch(0.135 0.02 272)` canvas, sidebar one step deeper. Atmospheric orbs (huge blurred circles) are allowed **only** on marketing/hero surfaces, never in app chrome.

### Borders
- Whisper-soft, blue-black: `--bv-border-5` for dividers, `--bv-border-15` for edges that must be seen, `--bv-border-25` for emphasis only. In dark mode borders are translucent cool-white. A solid opaque border looks wrong in this system.

### Shadows — two tiers, all blue-tinted
1. **Edge** — `--bv-shadow-edge` (1px, 6% blue-black) for cards and rows at rest. The default depth cue.
2. **The composer halo** — `--bv-shadow-composer`, the single dramatic depth cue: a wide 80px frosted-blue bloom + tight 1px ring. Used on the composer only.
- Hover cards lift to `--bv-shadow-card-hover` (16px diffuse, faintly blue). Active surfaces may add `--bv-shadow-glow`.
- No inner shadows except the glass light line. No dense single-layer shadows.

### Glass
Glass appears in **exactly three places**: overlays (dialogs, command palette), popovers (menus, dropdowns, tooltips), and the composer. Utilities: `.bv-glass`, `.bv-glass-heavy`, `.bv-glass-composer`, scrim `.bv-scrim`. Every glass surface carries the **inner light line** `inset 0 1px 0 var(--glass-light-line)` — that's what makes it glass and not a gray panel. Cards, boards, sidebars, headers: matte, always.

### Corner radii
A deliberate ladder: chips `0.25rem` → inputs `0.375rem` → icon buttons/rows `0.5rem` → cards `0.75rem` → dialogs `1rem` → composer `28px` → pills full. Pill radius is reserved for buttons and avatars — never cards.

### Typography
- System stack default; regular 400 default weight; medium 500 for buttons/section headers; semibold 600 reserved for empty-state titles.
- Tight scale: 12 / 14 / 16 / 18 / 22 / 24 / 28. Nothing else.
- CalSans (`--bv-font-display`) is opt-in for hero/marketing headings only — set `data-display-font="calsans"` on the surface root. App chrome never uses it.

### Motion
- Interaction feedback under 300ms; 200ms common, `--bv-ease-standard`. Enter `opacity:0, y:8 → 1, 0`; exit `y:-8`.
- Morph transitions (panel resize, theme change) 500ms `--bv-ease-morph`.
- Signature live signals: the Undertow (card scale) and the tidepool dot (dot scale), `typing-bounce` (3 staggered dots), `tool-pulse`.
- No bouncy entrances. Spring is for layout reorder, never for flourish.

### Hover / pressed states
- **Hover = frosted blue fill** (`--bv-frost-8`) on ghost/soft elements; one-step lighten (`--bv-ink-hover`) on primary buttons; shadow lift on cards. No scale, no rotation.
- **Pressed = one step deeper frost** (`--bv-frost-12`). Buttons stay still.
- No hover-only affordances.

### Cards
- Matte white (light) / `--card` (dark), `--bv-radius-xl`, whisper border, edge shadow at rest, diffuse blue-tinted shadow on hover.
- Running state wears the Undertow, not a colored border.

### Layout
- 200px fixed sidebar + 52px header + flex main. Chat column max 768px. Right panel ~45% viewport, 380px min. 4px spacing base. The shell never scrolls.

## Iconography

- **Lucide only.** The Maestro app renders inline Lucide path data (`McIcon` in `apps/maestro/WorkData.jsx`) — no CDN dependency. New artifacts may use the CDN, **pinned to an exact version** (e.g. `https://unpkg.com/lucide@0.525.0` — never `@latest`; path data drifts between releases). Production code: `lucide-react`, pinned. 20px standard, 16px inline, 24px empty-state. Stroke 2px (1.5px in chips), round caps, `currentColor`. No fill icons, no mixed libraries, no emoji-as-icons.
- **Brand mark:** the Broomva blackhole glyph — `assets/broomva-blackhole-logo.png`. Use on a dark or frosted surface; it carries its own glow. Don't recolor it.

## Content fundamentals

The voice is the **plain-language, capable assistant**:

- **Plain over technical.** "Needs you" not "In Review". "New mission" not "Create task".
- **Second person, never first.** The product speaks to *you*.
- **Short, declarative sentences. Lead with the verb.** "Connect both apps, then come back."
- **No filler.** No "Welcome!", no "Let's get started!", no celebration.
- **Sentence case everywhere.** Never Title Case Buttons. Never UPPERCASE LABELS. Never wide letterspacing — no uppercase eyebrow labels.
- **No em dashes** in user-facing copy. No marketing superlatives.
- **Emoji are banned** from UI chrome. Avatars may render Unicode a user typed, as data, never as decoration.
- Bold real-world nouns ("Reply **Google** or **Microsoft**"), not UI elements.

Vibe: quiet, capable, calm. The agent has done a thousand of these.

---

## Index

| Path | Purpose |
|---|---|
| `styles.css` | Root entry — `@import`s every token file. Link this one file. |
| `tokens/colors.css` | Ink, grays, accents, frost, borders, status, shadows, semantic tokens, dark theme. |
| `tokens/typography.css` | Font stacks (+ CalSans `@font-face`), scale, weights. |
| `tokens/spacing.css` | Radii ladder, 4px spacing, heights, motion. |
| `tokens/glass.css` | Glass tokens + `.bv-glass*` utilities + scrim. |
| `tokens/motion.css` | The Undertow, the tidepool dot, and the standing pulse — Broomva's live-signal language. |
| `tokens/base.css` | Element defaults: body, headings, links, code, focus ring, scrollbars. |
| `assets/` | Broomva blackhole logo. |
| `fonts/` | CalSans SemiBold. |
| `components/core/` | Reusable atoms: Button, IconButton, Input, Card, StatusBadge, Avatar, Composer, DotComet. |
| `components/forms/` | Form controls: Select, Checkbox, Radio, Switch, Textarea, Field. |
| `components/navigation/` | Tabs (frost pills), Segmented (settings pattern), CommandPalette (earned glass). |
| `components/overlays/` | Dialog, ConfirmDialog, Menu, MenuItem, MenuDivider, Tooltip, Toast — the glass-earning floating surfaces. |
| `components/work/` | The load-bearing inventions as importables: WorkState, LifecycleRail, Receipt, ReceiptRow, Undertow, RunCard, AutonomyScoreboard. |
| `templates/app-shell/` | Starting point: the Mission Control scaffold (sidebar, header, plane, docked composer), light/dark. |
| `templates/landing-page/` | Starting point: marketing page — dark hero with orbs + CalSans, principles, scoreboard, footer. |
| `guidelines/` | Foundation + primitive specimen cards — start with `work-model.html`, `disclosure.html`, `motion-undertow.html`. |
| `apps/maestro/` | **Maestro — the Broomva app.** The active implementation (formerly the Mission Control kit), wired to the standard components via `ds-adapter.jsx`. Work here. |
| `broomva-look-spec.md` | Curated source-facing visual canon: geometry, typography, interaction, and system invariants. |
| `manifest.json` | Machine-readable component, template, asset, and adherence inventory; curation decisions are documented by the skill's provenance reference. |

## Components

All importable from the compiled bundle; each directory carries a specimen card showing light and dark.

- **core/** — Button, IconButton, Input, Card, StatusBadge, Avatar, Composer, DotComet
- **forms/** — Select, Checkbox, Radio, Switch, Textarea, Field
- **navigation/** — Tabs, Segmented, CommandPalette
- **overlays/** — Dialog, ConfirmDialog, Menu, MenuItem, MenuDivider, Tooltip, Toast
- **work/** — WorkState, LifecycleRail, Receipt, ReceiptRow, Undertow, RunCard, AutonomyScoreboard

Composition rules: RunCard wraps in Undertow while running; WorkState renders only the plain-voice vocabulary; Receipt replaces every progress indicator; glass components (Dialog, Menu, Tooltip, Toast, CommandPalette) are the only ones allowed frost — everything else stays matte.

## Caveats

- CalSans ships in SemiBold only; the `@font-face` declares a 400–700 range so it renders at any weight, but it is always semibold-drawn.
- The blackhole logo is a raster PNG. A vector version would help for small sizes — ask Broomva for the SVG.
- `apps/maestro` depends on `ui_kits/desktop/styles.css` for its base app-shell classes (`.bv-app`, `.bv-sidebar`, `.bv-card`, etc.) — keep that file alongside it.
