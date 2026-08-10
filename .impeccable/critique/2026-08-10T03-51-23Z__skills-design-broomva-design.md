---
target: Broomva Design skill
total_score: 29
max_score: 40
na_heuristics: 
p0_count: 0
p1_count: 2
timestamp: 2026-08-10T03-51-23Z
slug: skills-design-broomva-design
---
# Broomva Design — Impeccable Critique

## Design Health Score

| Nielsen heuristic | Score | Assessment |
|---|---:|---|
| Visibility of system status | 3/4 | Strong verification, receipts, and lifecycle states; dry-run lacks grouped context. |
| Match between system and real world | 3/4 | Product language is grounded; materializer terminology assumes system knowledge. |
| User control and freedom | 3/4 | Safe dry-run, overwrite refusal, pruning authorization, Escape, and focus return; no rollback receipt. |
| Consistency and standards | 3/4 | Cohesive tokens and vocabulary; portable overrides plus system fallbacks create two perceived authorities. |
| Error prevention | 3/4 | Materialization is unusually defensive; public form contracts can still permit inaccessible output. |
| Recognition rather than recall | 2/4 | Operators must remember profile semantics and the manifest-to-contract-to-implementation path. |
| Flexibility and efficiency | 3/4 | Profiles and keyboard-aware primitives serve experts; no target preflight or profile recommendation. |
| Aesthetic and minimalist design | 3/4 | Calm, focused compositions; dark primary actions lose emphasis and CLI previews become noisy. |
| Error recognition and recovery | 3/4 | Conflicts are explicit with safe next steps; no post-write restoration path. |
| Help and documentation | 3/4 | Extensive, task-oriented guidance is fragmented across several authorities. |
| **Total** | **29/40** | **Strong foundation with material operator and accessibility friction.** |

## Design Specificity Verdict

Authored and recognizably Broomva. The blue-axis monochrome, Cal Sans display moments, blackhole-derived imagery, matte surfaces, scarce glow, restrained radii, and deliberate elevation form a coherent thesis. Commerce, editorial, work-console, and decision-receipt examples retain one identity through genuinely different compositions; this is not a generic component library painted blue.

Specificity weakens in ordinary operational UI. Small system text, pale borders, gray pills, familiar card grids, and neutral controls can become category-interchangeable once display typography and the blackhole motif recede. Dark-theme primary actions especially resemble disabled controls. The system is most distinctive at the brand and composition layers and less distinctive at the interaction-state layer.

The deterministic detector reported 39 warnings across 23 files: 33 slop and 6 quality findings. All were confined to hash-pinned `assets/system/` archive evidence; none occurred in `assets/portable/`. Several are contextual false positives—compact catalog-card hierarchy, generated `_ds_bundle.js`, Helvetica resolving from the canonical system stack, and an animation named `bv-bounce` that uses `ease-in-out`. Genuine archive-level findings remain: overshooting bounce curves, six layout transitions, two pages with heavy em-dash use, and occasional decorative glow/pulse patterns. These do not establish active portable-layer drift.

## Overall Impression

Broomva Design already succeeds at the hard conceptual problem: it carries a recognizable visual and interaction philosophy across unrelated digital-product domains without importing agentic-product vocabulary into neutral products. Its materializer is safer than most design-system installers, and its agentic state semantics are unusually honest.

The next quality frontier is not more visual ornament. It is making the system’s promises executable at its public boundary: accessible-by-default form APIs, clearer profile selection, a self-explanatory portable source model, and interaction states whose hierarchy remains unmistakable in dark mode.

## What’s Working

1. **Cross-domain portability is real.** Commerce and editorial specimens use materially different information architectures while preserving the same blue-axis identity. The reader avoids becoming a card dashboard; commerce does not inherit orchestration language.
2. **Materialization safety embodies the product promise.** Conflict refusal, dry-run, closed-world pruning, boundary checks, idempotent verification, and explicit authorization for modified-file deletion create credible operational trust.
3. **Agentic state semantics are excellent.** `Running`, `Needs you`, lifecycle stages, receipts, and intervention copy communicate real state without fabricated progress; evidence stays close to decisions.

## Priority Issues

### P1 — Accessibility requirements are documented but not enforced by core contracts

`Field.jsx` renders its visible label as a `span` without binding it to the child control. Hint and error text are not connected with `aria-describedby`, errors do not set `aria-invalid`, and `Switch` relies on callers to provide an external accessible name. `Dialog` can silently fall back to the generic name `Dialog`.

Make `Field` generate or accept control, hint, and error IDs; bind compatible children; propagate `aria-describedby` and `aria-invalid`; require a label contract for `Switch`; and remove the generic Dialog naming fallback in favor of a development warning or failure. Encode these requirements in declarations, prompt contracts, and rendered interaction tests. Suggested follow-up: `$impeccable audit`.

### P1 — Profile selection and dry-run output impose avoidable operator load

Six peer profile choices expose legacy and maintainer-only modes alongside the three product-facing paths. A web dry-run then emits 70 ungrouped paths before its summary. This makes the safe path feel harder than it is and creates four cognitive-load failures: chunking, minimal choices, working memory, and progressive disclosure.

Present `foundation`, `web`, and `agentic-work` as the primary choice; move `full`, `essentials`, and `tokens` under advanced or compatibility guidance. Add target-aware `recommend` or `plan` output, group dry-run changes by asset family, show counts first, and reserve the full path list for verbose output. Suggested follow-up: `$impeccable distill`.

### P2 — “Portable” is not a self-explanatory source boundary

The portable manifest advertises public components while several selected implementations and declarations live under `assets/system/` and are resolved through fallback logic. Materialization is correct, but direct inspection of `assets/portable/` feels incomplete and weakens the clean-boundary story.

Either make the portable tree implementation-complete or name it as an override-and-contract layer. Add source origin, contract path, category, profile, and stability metadata to manifest entries, then generate a neutral inventory showing the exact file selected for every public export. Suggested follow-up: `$impeccable clarify`.

### P2 — Active primary actions look disabled in dark mode

In dark commerce, reader, and work-console specimens, actions such as “Shop the collection,” “Save note,” and “Send” use pale gray fills that resemble disabled controls. This weakens hierarchy at the moment of action.

Define a distinct active-dark primary treatment using stronger foreground contrast, a blue-axis edge, or scarce blue emphasis. Define disabled appearance independently and validate active, hover, pressed, focus, and disabled states together. Suggested follow-up: `$impeccable colorize`.

### P2 — Compact controls do not consistently guarantee adaptive hit areas

Tabs are 28px tall, the default Button is 36px, and Switch is 38×22px. Those dimensions suit dense desktop UI but are risky in responsive products unless an invisible 44×44 target is guaranteed.

Separate visual dimensions from hit areas, supply coarse-pointer recipes or wrappers, mark desktop-only compact sizes, and add mobile specimens for Tabs, Switch, icon buttons, and dense header controls. Suggested follow-up: `$impeccable adapt`.

## Cognitive Load

The core journey—inspect, select, materialize, verify—has a single focus and good semantic grouping. The failure is at choice and inspection boundaries: six equally visible profiles, flat lists of 22 or 31 exports, a 70-line dry-run, and a portable/system fallback model that must be held in working memory. Legacy and archive-maintainer paths should be progressively disclosed, while product-facing choices should be derived from target facts whenever possible.

## Persona Red Flags

- **Alex, impatient power user:** must consult prose before choosing among six profiles; the 70-line preview hides its useful summary; there is no recommendation, concise diff, or current-profile query.
- **Jordan, first-time maintainer:** CLI terms are under-explained, compatibility profiles look equally recommended, and `full` sounds safer even though the intended principle is the smallest sufficient profile.
- **Sam, accessibility-dependent user:** Field semantics, Switch naming, generic Dialog naming, and compact touch targets leave accessible outcomes dependent on caller discipline.
- **Ari, AI design operator:** no structured target preflight returns platform, incumbent authority, conflicts, recommended profile, adapters, and a rendered conformance receipt; the operator must reconcile several documents manually.

## Minor Observations

- The single `CalSans-SemiBold.ttf` asset is mapped across weights 400–700, implying fidelity the file may not provide.
- Global `a { text-decoration: none; }` makes link recognition depend heavily on context and color.
- Mobile specimens preserve layout but make header identity and utilities very small.
- Neutral prompt contracts lack an equally compact recipe for loading, empty, offline, permission-limited, and recoverable-error states.
- The dogfood receipt is credible evidence, but its strongest claims are narrative rather than a generated, scannable conformance matrix.

## Deterministic and Browser Evidence

The detector scanned 94 eligible files and found 39 warnings: 18 `flat-type-hierarchy`, 13 `bounce-easing`, 6 `layout-transition`, and 2 `em-dash-overuse`. Findings were restricted to archived system evidence.

Fresh browser inspection covered `Design System.html`, `Styling Essentials.html`, `guidelines/disclosure.html`, and `components/core/core.card.html` at 1440×1000 in light mode, with dark-theme verification on the main specimen. The browser scanner found expected advisories around compact type, long lines, nested cards, clipped overflow, glow/pulse signatures, and occasional occlusion. Runtime inspection showed no application errors; the only network failure was a favicon 404. The main specimen exposed semantic headings and labeled primary controls. The compact core card had two unnamed buttons, and the main accessibility snapshot contained one unnamed image node.

Overlay injection was successfully demonstrated on all four pages. On the main specimen, 30 visible issue overlays and the yellow summary banner were visually confirmed before cleanup.
