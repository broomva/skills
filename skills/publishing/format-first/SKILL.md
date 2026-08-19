---
name: format-first
description: >
  Decide WHAT SHAPE of content to make, and refuse the platform folklore that
  circulates as fact. Encodes a claim set traced to primary sources — Meta's own
  engineering writeup and Transparency Center system cards, Mosseri's actual posts,
  and the psychology literature behind "hooks" and repetition — separating what is
  documented, what is hypothesis, and what is unsupported. Ships a linter that GRADES
  each claim — refuted, contested, unverified, folklore — and errors only on the ones
  contradicted by a primary source that was actually loaded, because "no source found"
  is a statement about a search, not about the world. The core move is choosing a FORMAT (visual grammar x script
  structure) as the invariant and letting topic vary, rather than the reverse.
  Use when, PRE-PRODUCTION: (1) choosing what shape a piece should take before it
  is written, (2) deciding how often to repeat a format and when to rotate it,
  (3) verifying a platform/algorithm claim from a course, thread, or guru,
  (4) auditing a draft or strategy doc for recommender folklore and untraceable
  statistics. NOT FOR: producing the artifact (use content-creation), generating
  visuals (use content-engine), page markup (use seo-llmeo), running an engagement
  loop (use social-intelligence), or **anything about a finished piece's reach,
  length, or citation by AI answer engines — that is citable, including the
  short-post-vs-long-article decision.** Triggers on "what format should I use",
  "is the algorithm punishing me", "should I post daily", "does this algorithm
  claim hold up", "which format should I repeat", "3-second hook", "verify this platform
  claim".
---

# format-first

Most content advice optimizes the wrong variable. It picks a **topic** and varies the
shape. This inverts that: pick a **format** and let the topic vary.

A format is *visual grammar* (how it is shot, framed, paced) x *script structure*
(where the beats land). It is the thing a viewer recognizes before they process a
single word — and it is the thing almost nobody chooses deliberately.

## Epistemic stance (read this before quoting anything)

This skill separates these grades, and the separation is the point:

| Grade | Meaning | Example |
|---|---|---|
| **Documented** | The operator publishes it | ANN retrieval over item embeddings; `"similarity to other reels"` is a named input signal |
| **Hypothesis** | Plausible, no source establishes it | that format consistency lowers embedding variance and thereby improves retrieval | <!-- format-lint: allow=embedding-variance-asserted -->
| **Refuted** | Contradicted by a primary source that was loaded | the misquoted "polished aesthetic" line |
| **Contested** | The literature genuinely disagrees | whether subliminal exposure is stronger | <!-- format-lint: allow=subliminal-stronger -->
| **Unverified** | Origin could not be located — **not** proof of falsity | the 3–5x sends weighting; a widely-quoted effect size |

The single most important line: **no source in the set searched here describes
format-level clustering.** That set is Meta's own published material — the Explore
engineering writeup, the Reels Chaining system card, `about.instagram.com`, Mosseri's
accounts, the Transparency Center — enumerated in `references/evidence-map.md` §1.

By this skill's own grades that is `unverified`, not `refuted`. Absence from an operator's
own description of its system is real evidence and stronger than a failed keyword search,
because those pages exist to enumerate ranking inputs. It is not proof: the systems are
proprietary and nothing obliges the published descriptions to be complete. The positive
mechanism — that consistency improves retrieval — is a working hypothesis with a
plausibility argument. Say so, in both directions.

## The loop

1. **Choose a format, not a topic.** Highest-leverage decision, almost never made
   deliberately.
2. **Probe, do not guess.** Watch several instances of a candidate format through to the
   end, then see whether the feed serves you more of that shape. If it does, the shape has
   a resident audience the recommender already serves. This is a *behavioural* test —
   valid regardless of whether the embedding hypothesis holds. (No source specifies how
   many instances; a handful is enough to notice the shift.)
3. **Copy the skeleton, supply your own substance.** Structure is fair game; content
   is not — and reposting others' content is the one thing that triggers a real
   account-level gate (Instagram's originality policy de-recommends primarily
   non-original accounts; it does not touch followers).
4. **Repeat it.** The counterintuitive part — and the part resting on the hypothesis
   above, not on a measured result. The argument is that consistent items are easier for
   a similarity-based retriever to match to an audience that already engaged. Treat it
   as the best available guess, and watch your own numbers.
5. **Hold more than one format; rotate on measured decay.** No source supports a specific
   count or interval — rotate on your own numbers. The wearout literature is *laboratory
   stimulus* research and transporting it to platform formats is an analogy, not a
   finding; what it does support is that liking rises then falls with repetition, and that
   the curve differs by modality (**visual inverted-U; auditory came out U-shaped**), so
   do not port repetition advice from video to audio.
6. **Calibrate the hook to existing knowledge.** A curiosity gap only fires if the
   viewer already has enough context to perceive it as a gap. This is why generic hooks
   fail on cold audiences — structurally, not for craft reasons.
7. **Match the signal to the goal.** Likes weigh slightly more for *connected* reach,
   sends slightly more for *unconnected*. "Would someone send this?" is the growth
   question; "was that satisfying?" is the retention question.

## Expectations, calibrated

- **Expect a heavy tail, not a hit rate.** The operator whose method seeded this skill
  reported most of their own posts underperforming even after a breakthrough. That is one
  self-reported account, not a measured base rate — do not quote a ratio.
- **An audience is not a delivery guarantee.** In a study of 347 TikTok users and 9.2M
  recommendations, only 10.3% of *viewed videos originated from followed accounts*
  (https://doi.org/10.1145/3613904.3642433). Note what that does **not** say: it measures
  video origin, not delivery path, and it is TikTok rather than Instagram. It does not
  establish that reach is re-earned per item — it establishes that most of what people
  watch does not come from accounts they follow.

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

Severity follows the ledger's **grade**: of the claim rules, only `refuted` (contradicted
by a primary source that was loaded) exits non-zero. Malformed lint controls — an unclosed
fence, an unclosed/nested/whole-file `disable` — also exit non-zero, because a silently
disabled gate is worse than a noisy one. `contested`, `unverified`, `folklore` and
`hypothesis_as_fact` are WARN — because "I could not find a source" is a statement about a
search, not about the world, and a gate that conflates the two manufactures the false
confidence it exists to prevent. Use `--strict` to fail on warnings too.

Sentences that **negate, correct, or attribute** a claim do not fire, so the linter does
not punish the corrections it exists to promote. Fenced blocks and well-formed YAML
frontmatter are exempt; a leading `---` horizontal rule is not. Suppress narrowly with
`<!-- format-lint: allow=<rule-id> -->` (that line only) or a `disable`/`enable` region —
an unclosed, nested, or whole-file region is itself reported as an ERROR.

**The bypasses, stated plainly**, because a gate whose escape hatches are undocumented is
a gate you cannot reason about:

| Bypass | Scope | Why it exists |
|---|---|---|
| `<!-- format-lint: allow=<id> -->` | that line, that rule | quoting a claim in order to correct it |
| `<!-- format-lint: disable -->` … `enable` | the region | a block quotation; whole-file coverage is itself an ERROR |
| a resolvable URL/DOI within 3 lines | that finding, **WARN grades only** | see below |
| an unclosed fence | everything after it | which is why it is an ERROR |

The third is the one to watch. A WARN-grade rule asserts *"this circulates with no located
source"*, so a sentence that **supplies** a source has already done what the rule asks —
`"According to Instagram, its algorithm demotes primarily non-original accounts:
https://creators.instagram.com/blog/rewarding-original-creators-on-instagram"` is true,
cited, and was flagged as folklore until this existed — the sentence you just read is
itself suppressed by the rule it describes.

The marker must be **scheme-qualified** (`https://…`, `doi.org/10.…`, an arXiv or PubMed
locator). A bare `example.com/page` does not suppress, and neither does a naked `https://`
or the substring `PMC`. Note that `references/evidence-map.md` cites several sources as
backticked bare domains — that house style is *not* a suppression marker, deliberately: a
bypass should be narrower than a citation convention, not wider. The consequence is that
appending any resolvable link within three lines silences every WARN-grade claim near it.
It does **not** silence `refuted`: a misquotation with a link attached is still a
misquotation, and that asymmetry is pinned by a test.

Extend it by editing `references/claims-ledger.json` — pattern, message, and the
correct replacement. Every rule needs both polarities in `tests/`.

**Before you trust it, sweep your own archive.**

```bash
python3 scripts/corpus_sweep.py ~/writing                       # what fires, per rule
python3 scripts/corpus_sweep.py ~/writing --compare old.json    # what a ledger edit changed
```

A rule that fires on a third of your existing work is a rule you will learn to ignore, and
a widened pattern is where the next false positive comes from. `--compare` runs both
ledgers over the same tree and prints only the delta; every *added* finding has to be a
true positive or the coverage was bought with noise. That check is not decorative — the
first draft of the word-form-multiplier rule added three findings across 3,328 files and
**two of them were the enumeration idiom** ("the problem is threefold"), which is why the
rule now requires a measurement context. Rerun the command to regenerate those numbers.

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
load-bearing claim traced to a primary source. **That upstream research arc** was
cross-reviewed over three rounds scoring 2/10 -> 5/10 -> 6/10, catching two genuine errors
in it.

**This skill's own review record is separate and worse:** adversarial rounds scoring
**2/10 -> 5/10 -> 5/10**, plus a dogfood pass against a real unseen article that found two
defects all 47 tests had missed, plus a fourth round that fixed the three findings below.

- **Fence tracking** treated any ` ``` ` or `~~~` as a toggle, so a ` ``` ` inside a
  ` ```` ` block closed it early and the rest was linted as prose. A fence is now a
  character *and* a length, and a closing run must carry no info string.
- **Universal-absence phrasing.** Four sites said format-level clustering is "documented
  nowhere" / absent from "any PUBLIC documentation". Those are claims about a search, which
  is the exact grade this skill defines as `unverified` — it was grading its own claim above
  its evidence. All four now name the source set.
- **Paraphrase coverage**, widened where it was cheap and honest: anthropomorphic verbs
  beyond "punish" (demote/suppress/throttle/shadowban/bury/deprioritise), cadence phrased
  as "each day" or "seven days a week", the variance hypothesis in five more verbs, and
  word-form multipliers. Each widening carries a paired negative fixture and was swept
  against 3,328 real files.

**Still known-open.** The matcher is regex-over-text, so a claim stated in words the ledger
does not list still passes; the widenings above narrow that gap, they do not close it.
Block boundaries are line-structural, not a real Markdown parse. Do not read a clean run as
proof a document is sound; read it as proof it contains none of the specific strings in the
ledger. Full graded claim set: `references/evidence-map.md`.

Recheck the ledger after **2027-02-12** — platform documentation moves.
