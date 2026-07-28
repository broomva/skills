# Adjudication — deciding what actually goes

The article's guidance is "delete the rules the model has outgrown." That is
correct and insufficient: it gives no way to tell an outgrown rule from a
load-bearing one, and the obvious predicate is wrong in an instructive way.

## The predicate that fails

The first form tried was two-way:

> Governance prose whose only enforcement is the agent reading it is a deletion
> candidate. Governance backed by an independent check is a keep.

**This inverts under measurement.** Run it and it deletes exactly the rules the
prose is load-bearing for, and preserves the ones that need no prose at all.

A rule enforced by a `PreToolUse` hook fires whether or not any document
describes it — *that is what "anchored" means*. So the prose describing it is
the free deletion, not the protected one. Meanwhile a discipline whose only
carrier is the document is the one where deleting the prose deletes the
behavior.

The predicate had it exactly backwards.

## The predicate that holds

| Class | Test | Prose is… | Action |
|---|---|---|---|
| **anchored** | a hook / CI job / runtime produces the signal, and the actor being governed cannot write to that producer | decorative — it fires regardless | **delete the prose, keep the mechanism.** Free, zero behavior change |
| **not_a_check** | descriptive, filesystem-derivable, or self-assessment | reference material | **relocate** behind progressive disclosure. Free |
| **self_referential, high value** | the document is the only carrier, and the behavior matters | the sole carrier | **keep** — relabel "heuristic", not "invariant". Or spend the effort to anchor it |
| **self_referential, redundant** | duplicated elsewhere, or unused in practice | noise | **delete** |

Tiers 1 and 2 are typically most of the volume and cost nothing. Tier 3 is a
real behavioral bet — neither the article nor this skill licenses cutting it.

## Two ways to get tier 1 wrong

**A citation is not an anchor.** A section that mentions `AGENTS.md` is prose
pointing at prose. Only executable or machine-read surfaces can produce an
independent signal — which is why `context_audit.py` excludes `.md` from
mechanism references and marks only `.sh` / `.py` / `.yaml` / `.toml` / source
files as anchored candidates.

**Existence is not enforcement.** The script checks that a referenced file
exists, nothing more. A hook file that exists but is unregistered, or a `make`
target that only checks another file exists, is not an anchor. Two real
examples found in this workspace's own audit:

- `make control-audit` — a file-existence test. It passes because `CLAUDE.md`
  exists. It asserts nothing about the contents.
- `make bstack-primitive-lint` — a presence/count contract on table rows. It
  never inspects row *contents*, so it cannot detect governance being hollowed
  out — which is precisely the defect that slipped past it on the first attempt
  at this cut.

When the call is close, `keel` is the tool that answers it properly: it asks
whether the actor being verified can write to the signal's producer.

## The receipt this was derived from

A `keel` grounding audit of this workspace's governance surface, 2026-07-25:

**23 rule-nodes — 5 anchored / 18 self-referential / 0 unknown → grounding
ratio 0.22.**

Anchored: the Stop hook (session capture), the PreToolUse control gate, GitHub
Actions check conclusions, the SessionStart freshness nudge, the
UserPromptSubmit lens injection. All five are harness-fired; the agent cannot
decline them.

Self-referential: everything whose trigger is the agent deciding to act —
filing a ticket, running the janitor, gathering evidence, writing its own
dependency enumeration, reporting its own snapshot. The *evidence* such a
discipline gathers can be anchored (exit codes, screenshots); the decision to
gather it, and the claim of having gathered it, are agent-authored.

A subtlety worth carrying: cross-model review where the second opinion is the
same model class in a fresh context is **decorrelated, not independent**.

The free tiers came to roughly two-thirds of the surface's tokens.

## The honest limit

Unhobbling applies to the **prose that instructs**, not to the **mechanisms
that verify**. A model cannot be its own independent verifier no matter how
good its judgement gets, so a verification mechanism is not something judgement
outgrows. Conflating the two deletes the load-bearing half.

Stated the other way: where prose is the only carrier and you *cannot* add an
independent check, the prose was never doing control work — but it may still be
doing useful *communication* work. Demote it, disclose it progressively, and
stop calling it an invariant.
