# Keel design system

Agent-facing. If you are generating a Keel surface — the report artifact, a
page, a slide, a mock — read this file and use these classes. Do not invent a
palette, and do not hand-roll a verdict chip.

```
tokens.css        the canonical values. There is no second copy.
keel.css          element defaults + component classes. Requires tokens.css.
README.md         this file — the component contract.

mark.png          the mark. Primary, 512px.
mark-compact.png  a zoomed crop of the mark for 32px and below. Favicon, tab.
icon.png          1024px tile. OG image, app icon, social preview.
```

Both stylesheets are dependency-free, framework-free, and safe to inline. The
report renderer inlines them verbatim into a single `<style>` block, because
the artifact must open from `file://` and issue zero external requests.

## The five rules

**1. Mono is quoted from the world; sans is Keel talking.** Node names, file
paths, commands, class names, hashes, exit codes → `.k-mono` or a mono
component slot. Prose, headings, arguments, annotations → sans. A reader
should be able to separate evidence from claim without reading a word.

**2. The accent is the narrator; the four verdict hues are the data.** Never
style chrome — a button, a link, a heading — in `--k-anchored`. Never style a
verdict in `--k-accent`. Green here means *classified anchored*, not *good*,
and the moment those blur, Keel is decorating itself with the same green check
it exists to criticize.

**3. No verdict without its argument.** Every `.k-verdict` contains a
`.k-argument` carrying `writeBoundary.argument`. A class shown without its
causal path is an unaccountable green check. `keel.css` renders a visible
defect banner when the argument is missing, and `make design-audit` fails on
one.

**4. No ratio without its denominator.** `.k-ratio__value` never ships without
`.k-ratio__counts`, and `not_a_check` is printed *beside* the ratio using
`.k-ratio__count--excluded`, never folded into it. `not_a_check` is the one
shoppable class — misfiling a real check there shrinks the denominator and
inflates the score — so the accounting stays on screen.

**5. Every artifact that prints a ratio carries `.k-scope`.** Verbatim, not
paraphrased. Keel measures the shape of verification, not its quality.

## Components

### `.k-ratio` — the grounding ratio

The headline number. `not_a_check` sits outside the fraction, visibly.

```html
<div class="k-ratio">
  <span class="k-ratio__value">0.43</span>
  <p class="k-ratio__formula">anchored / (anchored + self_referential + unknown)</p>
  <div class="k-meter">
    <div class="k-meter__seg" data-class="anchored" style="width:43%"></div>
    <div class="k-meter__seg" data-class="self_referential" style="width:37%"></div>
    <div class="k-meter__seg" data-class="unknown" style="width:20%"></div>
  </div>
  <div class="k-ratio__counts">
    <span class="k-ratio__count"><span class="k-class" data-class="anchored">anchored</span> 30</span>
    <span class="k-ratio__count"><span class="k-class" data-class="self_referential">self_referential</span> 26</span>
    <span class="k-ratio__count"><span class="k-class" data-class="unknown">unknown</span> 14</span>
    <span class="k-ratio__count k-ratio__count--excluded">
      <span class="k-class" data-class="not_a_check">not_a_check</span> 9
      <span class="k-meta">excluded from the denominator</span>
    </span>
  </div>
</div>
```

### `.k-class` — a `GroundingClass` chip

Four values, matching `schemas/keel.ts`. Spell the class exactly as the schema
does — `self_referential`, never "Self-Referential". It is an identifier from
the data model, and re-spelling it breaks the reader's ability to grep the
JSON. An unrecognised `data-class` renders unstyled on purpose.

```html
<span class="k-class" data-class="anchored">anchored</span>
<span class="k-class" data-class="anchored" data-smell>anchored</span>  <!-- confidence < 0.5 -->
<span class="k-class" data-class="not_a_check">not_a_check</span>       <!-- dashed: outside the ratio -->
```

`data-smell` is for `anchored` verdicts with `confidence < 0.5`. It rings the
chip in the `unknown` hue: the claim is "this is closer to unknown than its
color suggests". Do not use it on other classes.

### `.k-verdict` — one node's verdict

```html
<div class="k-verdict">
  <div class="k-verdict__name k-mono">.github/workflows/test.yml :: bun test</div>
  <span class="k-verdict__class"><span class="k-class" data-class="anchored">anchored</span></span>
  <div class="k-verdict__source k-mono">ci_step</div>
  <p class="k-argument">The signal is the test runner's exit code, produced by
    a process the target's agents cannot write to during the run.</p>
</div>
```

The argument is the deliverable. Make it scannable, not buried.

### `.k-graph` / `.k-mark` — the node graph

One square per node, on a wrapping grid. Squares, not circles: a circle reads
as a status dot, and the status dot is the thing being audited. The grid wraps
rather than scaling, so 15 nodes and 200 nodes share a mark size and neither
clips.

```html
<div class="k-graph">
  <span class="k-mark" data-class="anchored" title="…"></span>
  <span class="k-mark" data-class="unknown" title="…"></span>
  <span class="k-mark" data-class="not_a_check" title="…"></span>
</div>
```

### `.k-scope` — the mandatory scope note

```html
<p class="k-scope"><strong>Scope.</strong> Keel measures the shape of
verification, not its quality. A repo can be 100% anchored with terrible
tests. Anchoring says the signal comes from outside; it does not say the
signal is sufficient.</p>
```

### Supporting

| Class | Use |
|---|---|
| `.k-page` / `.k-report` | 760px prose shell / 1080px report shell |
| `.k-card` | raised panel — background step + hairline, never a shadow |
| `.k-code` / `.k-code--cmd` | code block; `--cmd` prefixes a `$` |
| `.k-callout` | the accent-ruled pull quote |
| `.k-eyebrow` / `.k-wordmark` | uppercase section label / the Keel wordmark |
| `.k-display` (+ `em`) | hero headline; `em` is the one accented clause |
| `.k-lede` / `.k-meta` / `.k-mono` | subcopy / small meta / quoted material |
| `.k-table` / `.k-table--num` | data table; `--num` sets tabular figures |
| `.k-btn` / `.k-tag` / `.k-legend` | control / static label / graph key |
| `.k-econ` | economics footer — probe vs agent counts, tokens, wall clock |

## Brand

The mark is a faceted keel blade cutting down through a lit waterline. The pale
portion rides above the surface; the luminous portion below is the part doing
the structural work, where you cannot see it. It carries its own near-black
canvas, so it composites onto surfaces Keel does not control.

- **Below 32px, use `mark-compact.png`.** It is a zoomed crop, not a scaled
  copy — the full composition thins to a sliver and the waterline disappears.
- **Clear space is half the mark's height** on every side.
- **Dark surfaces only.** There is no paper variant: the mark's glow has
  nothing to sit on against white, and inverting a rendered emblem does not
  work the way inverting a flat shape does.
- Never stretch, rotate, recolor, or re-render it at another angle.

**This is a bounded exception to the surface rules.** The mark uses glow,
gradient, and faceted shading, all of which `keel.css` forbids on UI surfaces
(rule: elevation is a background step plus a hairline). The emblem is a
rendered object; the interface is not. Nothing in the product chrome may borrow
the treatment — the moment a card or a button grows a glow, the exception has
leaked and the austerity the rest of the system depends on is gone.

**The gate no longer covers the brand palette.** When the marks were SVG,
`make design-audit` verified their inks against `tokens.css` byte for byte.
A PNG cannot be checked that way, so brand-colour agreement is now enforced by
review rather than by a check. That is a real loss of coverage, recorded here
rather than papered over.

## Voice

Sentence case. No emoji, and never a ✅ or ❌ — the unaccountable green check
is the subject of the critique, so Keel does not get to use one.

Say what produced a signal, in the indicative: *"the signal is the test
runner's exit code."* Not *"looks anchored"* or *"probably fine."*

Never call a grounding ratio "passing", "failing", "good", or "healthy". Keel
does not grade; it classifies. Never report a ratio as "well tested" — see
rule 5. `unknown` is not "pending" and not "needs review": it is a traced
failure to find the fork point, and it counts against the score.

Numbers appear with their denominator. Present tense, no hedging adverbs.

## Constraints, stated honestly

**No webfonts, ever.** Not a preference — the report's zero-external-request
invariant forbids hosted faces, and a base64 face would add ~80KB to an
artifact whose argument is that it depends on nothing. Both stacks are system
stacks and will render slightly differently per platform. That is accepted.

**`--k-ink-3` is below 4.5:1 on `--k-bg-0`.** It is for borders, disabled
glyphs, and rules. Never set text in it.

**Elevation is a background step plus a hairline.** There are no shadow
tokens. On a `#07090c` canvas a shadow is a smudge.

**Print inverts the canvas and darkens the verdict hues** rather than swapping
them, so a printed report and a screen report never disagree about what they
show.
