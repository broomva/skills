---
name: broomva-design
description: Materialize and apply Broomva's calm blue-axis product design system, including its portable DESIGN.md contract, OKLCH tokens, React components, work-state language, templates, and visual specimens. Use when creating or reviewing Broomva interfaces, bringing an app into brand alignment, scaffolding a Broomva design-system bundle, implementing Maestro-like work orchestration UI, or when a request mentions Broomva design, the blackhole mark, Undertow, tidepool, receipts, DESIGN.md, or the Broomva component library.
---

# Broomva Design

Materialize the Broomva visual system into a project, then use `DESIGN.md` as the agent-readable source of truth. The system is calm, matte, monochrome, and subtly blue: clarity before spectacle, visible work before invented progress.

## Start here

1. Read this skill's `DESIGN.md` before changing UI.
2. Inspect the target's existing styles, component primitives, and `DESIGN.md`.
3. Choose a materialization profile. Do not overwrite an incumbent system without an explicit migration request.
4. Implement through semantic tokens and reusable components.
5. Validate behavior, accessibility, both themes, and the target viewports.

Set `SKILL_DIR` to the directory containing this file, then materialize:

```bash
python3 "$SKILL_DIR/scripts/materialize.py" materialize . --profile tokens
python3 "$SKILL_DIR/scripts/materialize.py" verify . --profile tokens
```

Preview without writing:

```bash
python3 "$SKILL_DIR/scripts/materialize.py" materialize . --profile full --dry-run
```

The command writes `DESIGN.md` at the target root and the selected bundle under `design-system/broomva/`. Existing differing files cause a failure. Use `--force` only when the user explicitly authorized replacement.

## Choose the profile

| Profile | Materializes | Use when |
|---|---|---|
| `essentials` | `DESIGN.md`, one-file CSS essentials, blackhole logo | Adding the visual language to a small or non-React surface |
| `tokens` | Essentials plus modular tokens, root CSS, Cal Sans + license, manifest, adherence rules | Building or aligning a production app; this is the default |
| `full` | The complete curated bundle: components, prompt contracts, specimens, guidelines, templates, desktop kit, and Maestro reference app | Developing the system itself or needing exact implementation examples |

Do not copy the bundled Maestro app into production wholesale. Treat it as design evidence and adapt only the patterns the product actually needs.

## Apply the system

### Preserve the visual thesis

- Keep application chrome on the system sans stack. Cal Sans is opt-in for marketing and hero display surfaces only.
- Use blue-axis near-black ink and whisper-chroma cool neutrals. Reserve Resonant AI Blue for focus, links, information, selection, and live signals.
- Keep cards, panels, sidebars, and chrome matte. Glass is earned by elevation: dialogs, command palette, popovers, tooltips, dropdowns, and the composer.
- Use the 4px spacing ladder and restrained radii. Cards are `0.75rem`; dialogs are `1rem`; the composer owns the signature `28px` radius. Pills belong to buttons, avatars, and compact status controls, never generic cards.
- Use Undertow and tidepool as the shared running signal. Motion communicates presence, not percent-complete theater.

### Model agentic work honestly

Use the canonical state vocabulary exactly: `Queued`, `Running`, `Stuck`, `Needs you`, `Done`, `Standing`.

- Prefer receipts, decisions, asks, and lifecycle stages over synthetic completion percentages.
- Use `Needs you` only for a concrete human decision or intervention.
- Pair every state color with text, iconography, or structure. Color cannot carry meaning alone.
- Respect `prefers-reduced-motion`; a static live-state treatment must remain legible.

Read `references/product-model.md` when designing work feeds, run details, autonomy views, lifecycle rails, or command surfaces.

### Reuse before inventing

The full bundle contains 31 exports across core, forms, navigation, overlays, and work primitives. Before creating a new primitive:

1. Check `assets/system/manifest.json` for the public export.
2. Read the matching `assets/system/components/<category>/<Name>.prompt.md` contract.
3. Inspect its `.jsx` and `.d.ts` only when implementation detail is necessary.
4. Import public components through the system entry point, not component internals.

The prompt contracts are compact agent-facing component documentation. Load only the components relevant to the task.

## Agentic design loop

For each meaningful UI change:

1. **Retrieve** — read `DESIGN.md`, the target route, its styles, and relevant prompt contracts.
2. **Frame** — state the user job, information hierarchy, target viewports, and reused primitives.
3. **Implement** — work from semantic tokens toward composed components; keep changes surgical.
4. **Inspect** — render at `375px`, `768px`, and `1440px`; inspect light and dark themes.
5. **Interact** — exercise keyboard navigation, focus, hover, loading, empty, error, and reduced-motion states.
6. **Audit** — verify WCAG 2.2 AA contrast, visible focus, `44px` touch targets where appropriate, semantic HTML, and no horizontal overflow.
7. **Reconcile** — if the implementation changes the system intentionally, update `DESIGN.md` and token/component assets in the same change.

Use browser automation or screenshots when available. A code-only review is not visual validation.

## Adherence checks

Run the deterministic source check at any time:

```bash
python3 "$SKILL_DIR/scripts/materialize.py" verify-source
```

The `tokens` and `full` profiles include `adherence.oxlintrc.json`, which warns on raw color literals, raw pixel literals, private component imports, invalid component props, and invalid enum values. Integrate it only when the target already uses Oxlint; the materializer does not mutate project lint configuration.

Also audit for:

- raw hex values where a semantic token exists;
- new spacing/radius values outside the ladder;
- ambient glass on non-floating surfaces;
- generic gradient hero treatments or decorative blobs unrelated to the blackhole/Undertow language;
- title case, emoji, em dashes, vague status labels, or ornamental eyebrow copy;
- `transition: all`, hover transforms that move layout, or motion without reduced-motion handling;
- icon-only controls without accessible names.

## Voice

Write plain, precise, second-person product copy. Use sentence case. Prefer a short verb phrase over a branded abstraction. Do not use emoji, em dashes, title case, or decorative eyebrow labels. A receipt says what happened; an ask says what the user must decide.

## Boundaries

- Use `broomva-design` for the current Broomva product and work-orchestration language.
- Use `arcan-glass` only when the request explicitly targets the older glass-forward Arcan language or its Next.js integration patterns.
- Use `design-engineering` for general premium design workflows that are not Broomva-branded.
- Use `design-distill` when extracting a new system from external references rather than applying this one.
- Never claim visual fidelity without rendered evidence.

## Resources

- `DESIGN.md` — canonical portable design contract copied to target roots.
- `scripts/materialize.py` — safe, deterministic materializer and verifier.
- `references/product-model.md` — work-state semantics and composition guidance.
- `references/provenance.md` — archive audit, curation decisions, and licensing provenance.
- `references/dogfood-receipt.md` — rendered light/dark evidence for two independently materialized test designs.
- `assets/system/` — curated source bundle and visual specimens.
