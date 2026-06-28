# Format Discernment — Reference

Companion to the `Format Discernment (P18 · Audience)` section in `SKILL.md`.
The SKILL holds the rule; this file holds worked examples, design rationale,
and the observation-period success criteria.

## Why three categories?

Markdown won the LLM-output era because tokens were precious and context
windows tiny. That constraint is gone (May 2026). HTML is now viable for
human-read artifacts because the harness loop is fast enough and context
windows large enough that the extra tokens cost nothing meaningful.

But HTML is not a universal replacement. The agent-substrate use case —
grep, lint, score, score-and-promote, diff-review, line-by-line PR review —
still requires plain text. So the workspace splits into three categories,
not two formats.

## Examples drawn from the workspace

### Category A (MD-only)

```
research/entities/concept/agent-loop-silicon.md
research/notes/2026-05-12-prompt-patterns-raw.md
CLAUDE.md
AGENTS.md
docs/superpowers/specs/2026-05-12-format-discernment-p6-render-design.md
skills/bookkeeping/SKILL.md
```

What they have in common: another agent (or you, with grep) will read this
as text. The artifact's primary consumer is *not* a browser.

### Category B (MD canonical + HTML on demand)

```
research/notes/2026-05-08-egri-calibration-synthesis.md   ← canonical
research/notes/2026-05-08-egri-calibration-synthesis.html ← projected
```

The synthesis is authored, edited, reviewed, and scored as MD. When you
sit down to *read* it (decide whether to publish, share with a colleague,
turn into a blog post), `bookkeeping render` produces the HTML. The HTML
is gitignored — it's a snapshot of a moment, not source-of-truth.

### Category C (HTML-native, frontmatter-carried)

```
research/notes/2026-05-12-consistent-hashing-demo.html
```

This artifact is *intrinsically* interactive — sliders, animated demos,
linked screens. There's no useful MD source: the MD version would lose the
thing that makes the artifact valuable. The HTML carries frontmatter
(HTML-comment YAML) so it can still be a graph member if it deserves one.

**Generatively authored, never templated.** Category C is the workspace's
rich-HTML surface: architecture docs, decision documents, explainers, and
dashboards where diagrams, interaction, and multiple data-representation
modalities carry knowledge prose can't. The agent **generates each one
bespoke** — fit to the specific content, the session context, and the relevant
`research/entities/` — using the generation menu in `SKILL.md` (inline SVG,
inlined Mermaid, sortable tables, decision matrices, timelines, tier stacks,
collapsibles/tabs, charts). There is deliberately **no component or template
library**. Two reasons:

1. **A template ossifies; generation adapts.** A fixed kit forces every
   artifact toward the shapes the kit anticipated. Generative authoring lets the
   artifact's *structure* follow its *content* — the architecture doc gets a
   tier diagram, the decision doc gets an interactive matrix, because the agent
   reasons about what *this* knowledge needs, not what a template offers.
2. **The model is the engine.** Producing self-contained HTML (inline CSS/JS/SVG,
   no CDN) on demand is exactly what a current model does well. The skill's job
   is to *direct* that capacity (menu + constraints), not to pre-bake outputs.

The floor is `bookkeeping render` (Category B, lossless MD→HTML). The ceiling
is generatively authored Category C. Both carry graph frontmatter; only B has
an MD twin.

**Rich-by-default + design-craft composition.** Generative authoring is not
license to stop at "clears the predicate." A C artifact is authored *to the
ceiling*: rich diagrams + flows, purposeful motion/interaction, content-driven
depth, and **multiple linked HTML pages** when one page can't hold the arc
(`docs/<arc>/index.html` + relative-linked siblings). Length and structure
follow the content — no cap, and no gratuitous complexity either.

The four binding constraints in `SKILL.md` are a *correctness* floor (portable,
accessible, graph-integrated), not a *visual-craft* bar. Craft is deliberately
**not** machine-checked — the workspace declined to promote "premium/best-in-class"
to an invariant (no lint gate; Ritual-vs-Substance table in `CLAUDE.md`), so it
stays a **convention**. But it's a *named, discoverable* convention: when
authoring Category C, compose with the design layer — `ui-ux-pro-max` (styles /
palettes / font pairings / chart types), `impeccable` (hierarchy / IA /
cognitive load / tasteful effects), `make-interfaces-feel-better` &
`emil-design-eng` (interaction + motion polish), `arcan-glass` (Broomva brand
tokens, when brand-facing). These set the craft bar; the constraints set the
correctness floor. A C artifact never *fails lint* for being plain — but the
standing instruction is author rich, not plain.

## Frontmatter carriers by format

| Format | Carrier | Example |
|--------|---------|---------|
| `.md`, `.markdown` | YAML between `---` lines | `---\ntype: synthesis\n---\n` |
| `.html` | YAML in leading HTML comment | `<!DOCTYPE html>\n<!--\n---\n...\n---\n-->` |
| `.ipynb` | Notebook `metadata` key | `"metadata": { "type": "synthesis", ... }` |
| Binaries (PDF, PNG, …) | Sidecar `.meta.yaml` | `foo.pdf` + `foo.pdf.meta.yaml` |

All carriers must encode at least: `type`, `slug`. Layer 4 artifacts also
encode: `score`, `status`, `source_extracts`, `related_entities`, and (for
projections) `canonical`.

## Wikilink carriers by format

| Format | Carrier | Edge typing |
|--------|---------|-------------|
| `.md` | `[[type/slug]]`, optional `\|alias` | implicit "references" (no edge typing) |
| `.html` | `<a href="../type/slug.md" data-relation="…">alias</a>` | explicit via `data-relation` |

When `bookkeeping render` projects MD → HTML, `[[type/slug]]` becomes
`<a href="../type/slug.md" data-relation="references">slug</a>` (or `.html`
target with `--link-html`). The `data-relation` defaults to `references`
since MD has no edge typing.

## Observation period

For 30 days after the format-discernment rule lands (PR-merge date), the
workspace tracks:

- Number of `bookkeeping render` invocations
- HTML projections actually opened (manual log entry)
- Format-discernment lint warnings/errors fired in CI
- Category-C native artifacts created organically (any `.html` under
  `research/notes/` not produced by `render`)

If, after 30 days:

- ≥10 Category-B renders consumed across ≥5 distinct sessions, AND
- ≥3 Category-C native artifacts emerged organically

…the format-discernment rule crystallizes into a primitive.

> **Resolved.** It crystallized as **P18 — Audience: Format-Follows-Audience
> Discipline**, now live in the bstack primitives table in `CLAUDE.md` /
> `AGENTS.md` (P17 was assigned to **Lens**). The format-discernment A/B/C model
> here is the skill-level operationalization of P18. The current refinement
> (this revision) is the **generative-authoring direction for Category C** in
> `SKILL.md`: rich human-read artifacts are generated bespoke per session, not
> projected from MD and not assembled from templates.

## Why not just emit both formats every time?

That was the obvious naive answer and it's wrong:

1. **Wastes work.** Most artifacts don't benefit from HTML; the projection
   adds storage, review surface, and confusion.
2. **Conflates categories.** Category A artifacts have no HTML twin; Category
   C artifacts have no MD twin. Only Category B has both.
3. **Burns L3 stability budget.** A workspace-wide "emit both" rule is a
   reflexive discipline change; L3 (governance) has λ₃ ≈ 0.006 in the
   composite stability calculation. Reversible single-category rules are
   cheaper.

The three-category test fits in a sentence each. The agent applies it the
same way it currently picks JSON vs YAML vs TOML for any output.
