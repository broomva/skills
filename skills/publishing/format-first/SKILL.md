---
name: format-first
description: >
  Decide WHAT SHAPE of content to make, and refuse the platform folklore that
  circulates as fact. Encodes a claim set traced to primary sources — Meta's own
  engineering writeup and Transparency Center system cards, Mosseri's actual posts,
  and the psychology literature behind "hooks" and repetition — separating what is
  documented, what is hypothesis, and what is refuted. Ships a linter that fails a
  draft repeating any of six debunked claims or asserting a precise figure with no
  loadable source. The core move is choosing a FORMAT (visual grammar x script
  structure) as the invariant and letting topic vary, rather than the reverse.
  Use when: (1) deciding what to post or what shape a piece should take,
  (2) diagnosing why content is not reaching people, (3) auditing a draft or a
  strategy doc for algorithm folklore and unsourced statistics, (4) choosing how
  often to repeat a format and when to rotate, (5) evaluating a course, thread, or
  guru claim about how a recommender works. NOT FOR: producing the artifact
  (use content-creation), generating visuals (use content-engine), optimizing a
  finished piece for AI citation (use citable), page markup (use seo-llmeo), or
  running an engagement loop (use social-intelligence). Triggers on "what should I
  post", "content strategy", "why is my content not getting views", "is the
  algorithm punishing me", "hook", "should I post daily", "how do I grow",
  "format", "does this claim about the algorithm hold up".
---

# format-first

Most content advice optimizes the wrong variable. It picks a **topic** and varies the
shape. This inverts that: pick a **format** and let the topic vary.

A format is *visual grammar* (how it is shot, framed, paced) x *script structure*
(where the beats land). It is the thing a viewer recognizes before they process a
single word — and it is the thing almost nobody chooses deliberately.

## Epistemic stance (read this before quoting anything)

This skill separates three grades, and the separation is the point:

| Grade | Meaning | Example |
|---|---|---|
| **Documented** | The operator publishes it | ANN retrieval over item embeddings; `"similarity to other reels"` is a named input signal |
| **Hypothesis** | Plausible, no source establishes it | that format consistency lowers embedding variance and thereby improves retrieval | <!-- format-lint: allow=embedding-variance-asserted -->
| **Refuted** | Traced and found false or unlocatable | six claims in `references/claims-ledger.json` |

The single most important line: **format-level clustering is not documented anywhere.**
The negative claim (no format-keyed favor state exists) is well supported. The positive
mechanism is a working hypothesis with a plausibility argument. Say so.

## The loop

1. **Choose a format, not a topic.** Highest-leverage decision, almost never made
   deliberately.
2. **Probe, do not guess.** Watch 3-5 instances of a candidate format to completion.
   If the feed fills with it, there is a resident audience for that shape. This is a
   *behavioural* test — valid regardless of whether the embedding hypothesis holds.
3. **Copy the skeleton, supply your own substance.** Structure is fair game; content
   is not — and reposting others' content is the one thing that triggers a real
   account-level gate (Instagram's originality policy de-recommends primarily
   non-original accounts; it does not touch followers).
4. **Repeat it.** The counterintuitive part. Consistency buys findability; scattering
   makes every post start cold.
5. **Hold more than one format; rotate on measured decay.** No source supports a
   specific count. Complex formats last longer than simple ones. **If the channel is
   audio, the visual inverted-U does not transfer** — the meta-analysis found auditory
   stimuli go U-shaped.
6. **Calibrate the hook to existing knowledge.** A curiosity gap only fires if the
   viewer already has enough context to perceive it as a gap. This is why generic hooks
   fail on cold audiences — structurally, not for craft reasons.
7. **Match the signal to the goal.** Likes weigh slightly more for *connected* reach,
   sends slightly more for *unconnected*. "Would someone send this?" is the growth
   question; "was that satisfying?" is the retention question.

## Expectations, calibrated

- **Roughly 19 of 20 pieces underperform**, even for operators who know what they are
  doing. Plan for a heavy tail, not a hit rate.
- **An audience is not a delivery guarantee.** In a study of 347 TikTok users and 9.2M
  recommendations, only 10.3% of viewed videos originated from followed accounts. Reach
  is re-earned per item.

## When the audience can verify

The default law is that reach selects for the *legibility* of expertise rather than its
correctness — **because most audiences cannot check**. If yours can (technical,
professional, scientific), that inverts: correctness stops being a moat choice and
becomes closer to a distribution requirement. You cannot out-polish a full-time creator,
and you do not need to. The differentiated format for a builder is usually the one that
*shows the work*: take a claim everyone repeats, traverse to the primary source, report
what survives.

Guard against the failure that pairs with it: an artifact that performs its own claimed
mechanism on you and offers the sensation as proof. Feeling an effect is not evidence
that the proposed explanation of it is correct.

## The gate (deterministic)

```bash
python3 scripts/format_lint.py DRAFT.md            # ERROR on refuted claims
python3 scripts/format_lint.py DRAFT.md --strict   # warnings fail too
python3 scripts/format_lint.py - --json            # stdin, machine-readable
```

Fails a draft that repeats a refuted claim, asserts a hypothesis as mechanism, or states
a precise figure with no citation marker within three lines. Fenced code blocks are
exempt, so a document can quote a bad claim in order to correct it.

Extend it by editing `references/claims-ledger.json` — pattern, message, and the
correct replacement. Every rule needs both polarities in `tests/`.

## Anti-rationalization

| Excuse | Reality |
|---|---|
| "I'll pick a format once I know what to say." | Backwards. The format is the container; topic fills it. Choosing topic-first is why output scatters. |
| "This creator posts daily, so cadence works." | Survivorship. Volume-as-strategy is unevidenced and is precisely what the source case study spent two years disproving. |
| "The 3-second hook is settled." | It has no peer-reviewed basis. Every source is a content farm or a platform vendor. | <!-- format-lint: allow=three-second-hook -->
| "A precise number makes it credible." | Precision is rhetorical and freely available. It does not entail that a measurement happened — run the linter. |
| "The algorithm is punishing my account." | No documented per-format punitive state exists. There is one real account-level gate and it is about originality. | <!-- format-lint: allow=algorithm-punishes -->
| "It worked on me, so the explanation is right." | That is the counterfeit-verifier move. Sensation is not a discriminating test between hypotheses. |

## Provenance

Derived from `broomva/workspace` BRO-2145 (PR #376, merged `195a9e54`): a full ingest of
a paid-acquisition funnel plus its 36:56 sales video, transcribed locally, with every
load-bearing claim traced to a primary source. Cross-reviewed adversarially over three
rounds (2/10 -> 5/10 -> 6/10), which caught two genuine errors in the original writeup.
Full graded claim set: `references/evidence-map.md`.

Recheck the ledger after **2027-02-12** — platform documentation moves.
