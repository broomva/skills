# The six reversals, worked

Source: Thariq Shihipar (Anthropic, Claude Code), *The new rules of context
engineering for Claude 5 models*, 2026-07-24 —
<https://claude.com/blog/the-new-rules-of-context-engineering-for-claude-5-generation-models>

Headline result: **over 80% of Claude Code's system prompt removed for Claude 5
models, with no measurable loss on their coding evaluations.**

---

## 1. Rules → judgement

Hard rules were written to stop a weaker model doing a specific dumb thing.
Once judgement exceeds the rule, the rule is a liability: it fires in cases it
was never meant for, and the model burns reasoning reconciling it with the
user's actual request.

> **Then** — "Default to writing no comments. Never write multi-paragraph
> docstrings or multi-line comment blocks — one short line max."
>
> **Now** — "Write code that reads like the surrounding code: match its comment
> density, naming, and idiom."

The rewrite is shorter *and* covers more cases — including the ones the
prohibition got wrong (a codebase whose convention genuinely is thorough
docstrings).

**Detection:** the script's `rules-ratio` per section. A section at 1.0 is pure
prohibition/mandate with no judgement framing anywhere.

**Rewrite move:** name the *goal state* and let the model infer the action.
"Match the surrounding code" rather than an enumeration of what not to write.

---

## 2. Examples → interface design

Examples were a way to communicate a shape. But they also *narrow* the
exploration space — the model anchors on the example rather than reasoning
about the case in front of it.

Prefer making the interface itself expressive: a well-named enum parameter
hints its own correct usage more reliably than three usage samples do. This
applies to tool definitions, function signatures, and schema fields.

**Detection:** the script's `examples` column — fenced blocks plus
example-flavoured table rows per section.

**Rewrite move:** for every example, ask what the example is teaching. If it's
teaching *which parameter to use*, fix the parameter name or type. If it's
teaching *a rare edge case*, keep it — that's what examples are still good for.

---

## 3. Everything upfront → progressive disclosure

Detail that is loaded on every request competes with the request. Move it
behind something the model can *reach for* — a skill it calls when relevant, a
reference file it opens, a tool whose full definition loads on demand.

**Detection:** the script's disclosure flag — a surface over the split
threshold with no `references/` dir and fewer than 3 outbound doc links is
carrying everything upfront.

**Rewrite move:** split long skills across files. Keep the entry file to the
contract and the decision procedure; push worked detail into `references/`.

---

## 4. Repetition → one description

The same instruction in the system prompt, the tool description, and the skill
is not three times as strong. It is three places to drift out of sync, and a
source of the collisions that motivated the whole cut.

Instructions about a tool belong *on* the tool.

**Detection:** the script's near-duplicate clusters (word-shingle Jaccard
across sections and files).

**Rewrite move:** pick the surface closest to the point of use, keep it there,
delete the others.

---

## 5. Manual memory → auto-memory

CLAUDE.md as a memory store was a workaround for not having one. Claude now
saves relevant memories automatically. CLAUDE.md goes back to being a
description of the repo.

**Rewrite move:** anything in CLAUDE.md that reads like session state,
"remember that…", or a running log of past decisions is memory, not
governance. It belongs in auto-memory or a knowledge graph.

---

## 6. Simple specs → rich references

Newer models handle richer inputs, so a spec no longer has to be prose. It can
be an HTML artifact, a test suite, a rubric, or a function in another codebase.
Code references beat prose descriptions for precision.

Anthropic's own extension of this: hand a rubric to verifier agents rather than
describing the quality bar in prose.

**Rewrite move:** replace "the output should look like…" with the actual
artifact. A failing test is a better spec than a paragraph about what should
pass.

---

## Where the surfaces sit

| Surface | Job |
|---|---|
| System prompt | Product context. Only worth tuning if you build your own harness. |
| CLAUDE.md | What the repo is for, then mostly **gotchas**. Not what `ls` already shows. |
| Skills | Lightweight guides encoding team-specific opinion. Over-constrain only where the stakes are genuinely high. Split long ones. |
| References | Prefer artifacts in code. HTML mockup > screenshot > prose description. |

Anthropic also ships `/doctor` in-session to rightsize skills and CLAUDE.md.
It knows nothing about which of your rules are backed by mechanisms — that gap
is what `references/adjudication.md` closes.
