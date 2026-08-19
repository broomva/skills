# Evidence map — what is documented, hypothesized, and refuted

Every claim below carries the grade it earned. Provenance: `broomva/workspace` BRO-2145
(PR #376, merged `195a9e54`), 2026-08-12. Recheck after **2027-02-12**.

**Grades.** `[HIGH]` = primary artifact loaded and the supporting string read or grepped
directly. `[MED]` = bibliographic record confirmed across independent databases, figures
secondary. `[LOW]` = single secondary source. Nothing is graded HIGH on a search summary.

---

## 1. Documented — the operator publishes this

**Retrieval is nearest-neighbour over item embeddings.** `[HIGH]` Meta's Instagram Explore
engineering writeup, fetched and grepped live:

> "Let's say that a user liked/saved/shared some items. Given that we have embeddings of
> those items, we can find a list of similar items to each of them and combine them into a
> single list."

Item embeddings are precomputed offline and served from ANN search (FAISS, HNSW).
Source: `engineering.fb.com/2023/08/09/ml-applications/scaling-instagram-explore-recommendations-system/`

**Ranking is a weighted sum of predicted engagement.** `[HIGH]` Same source:

> "predicted probabilities for P(click), P(like), P(see less), etc. could be combined with
> weights W_click, W_like, and W_see_less using a formula that we call value model (VM)"

Note the negative term on `see less`. **Scope: Explore only.** Reels publishes no formula.

**Content similarity is a named input signal.** `[HIGH]` The Reels Chaining system card
(Transparency Center, updated 2025-11-11) lists `"similarity to other reels"` explicitly,
alongside `"the length of the reel"`. It publishes **no numeric weights**.
Source: `transparency.meta.com/features/explaining-ranking/ig-reels-chaining/`

**Each surface has its own algorithm.** `[HIGH]` Mosseri, `about.instagram.com`:

> "Each part of the app – Feed, Stories, Explore, Reels, Search and more – uses its own
> algorithm tailored to how people use it."

Do not transport a formula across surfaces.

**One real account-level gate exists, keyed to originality.** `[HIGH]` Published 2026-04-30:

> "accounts that publish primarily non-original content in photo posts or carousel posts,
> plus reels, will no longer be shown in places where we recommend content"

Crucially: *"This update does not affect the way we show people content from accounts they
follow"*, and it is reversible if the majority of the last 30 days is original. It is
**eligibility, not ranking**, and it is keyed to reposting — **not** to format choice.

**Signal ordering is conditional.** `[HIGH]` Mosseri, 2025-01-21 — the only primary
ranking of signals located:

> "the top three signals that matter most for ranking are watch time, likes and sends…
> One nuance: likes are slightly more important for connected content, and sends are
> slightly more important for unconnected content."

The word is *slightly*, and the asymmetry runs **both** directions.

**~90% of viewed videos come from non-followed accounts.** `[HIGH]` Zannettou et al.,
CHI '24, 347 users / 9.2M recommendations, verified by pdftotext grep:

> "we find that only 10.3% of the video views in the dataset are actually for videos
> originating from accounts that the participants followed in advance"

**Bounds:** measures video *origin*, not delivery path. TikTok, not Instagram. Sample is
347 compensated, self-selected US adults recruited via social ads. The paper's abstract
states a figure inconsistent with its own body definition; that figure is not cited here.

---

## 2. Hypothesis — plausible, unestablished

<!-- format-lint: allow=embedding-variance-asserted -->
**That format consistency lowers embedding variance and thereby improves retrieval.**

Since content similarity is a documented retrieval signal, it is *plausible* that
structurally consistent items sit near one another in the learned representation. But **no
source establishes** that "format" is a dimension of that representation, that consistency
measurably reduces variance, or that any of it produces a reach effect of a given size.
The similarity space is trained on engagement, not on human-legible production style.

**Format-level clustering is documented nowhere.** No Meta source describes format
(talking-head vs b-roll, hook style, cut rate) as a clustering dimension or ranking
feature. The nearest published item is `"the length of the reel"` — a scalar.

**How you would test it:** hold topic constant across structurally-identical vs varied
items and compare per-item reach variance. Not done here.

---

## 3. Refuted — traced and found false or unlocatable

These six are encoded in `claims-ledger.json` and enforced by `scripts/format_lint.py`.

<!-- format-lint: disable -->

| Claim | Finding |
|---|---|
| Sends weighted 3–5x likes | No primary source located in any venue searched. A search tool returned the fabrication *in quote form*; it traces to an SEO blog. |
| "The polished aesthetic is dead" (Mosseri memo) | Real post, materially distorted. A public Threads essay, not a memo. The line is *"That feed is dead"* about personal sharing moving to DMs. Announces **no** ranking change and explicitly defers. |
| Bornstein meta-analysis of "208 studies" | It is **134 studies reporting 208 contrasts** (Grybinas, Kantner & Dobbins 2019, *Memory & Cognition* 47:1314–1327). ~55% inflation. |
| Mere-exposure `r = 0.26` | Not found in the paywalled article, its abstract, Crossref, PubMed, Google Books, or a full-text search across 41 open-access papers. Proximate source: **Wikipedia**. |
| "Subliminal exposure is stronger" | Faithfully reports Bornstein 1989, but contradicted by later work with awareness controls (Fox & Burns 1993, *a failure to replicate*; de Zilva et al. 2013). Cite as history, never mechanism. |
| The algorithm's "favorites / excluded list" of formats | No format-keyed favor or penalty state in any documented architecture. |

<!-- format-lint: enable -->

<!-- format-lint: disable -->
**Also unevidenced** (WARN-grade in the linter): the 3-second hook rule, posting-daily as
a growth strategy, and anthropomorphic "the algorithm punishes you" framing.
<!-- format-lint: enable --> A targeted
search for peer-reviewed work on what *structurally* predicts short-form retention
returned only content farms and vendor marketing.

---

## 4. Psychology — confirmed, and materially qualified

**Curiosity as an information gap.** `[HIGH]` Loewenstein (1994), *Psychological Bulletin*
116(1), 75–98, p. 87:

> "the information-gap theory views curiosity as arising when attention becomes focused on
> a gap in one's knowledge. Such information gaps produce the feeling of deprivation
> labeled curiosity."

**The qualification that matters operationally:** a gap alone does not produce curiosity.
Loewenstein, p. 89 — *"curiosity is unlikely to arise in the absence of an existing
knowledge base."* Kang et al. (2009), *Psychological Science* 20(8), find an inverted-U:
curiosity peaks at **moderate** confidence. So a hook must be calibrated to what the
audience already knows; generic hooks fail on cold audiences structurally.

**The habit loop.** `[HIGH]` Cue/routine/reward is Duhigg (2012), *The Power of Habit*,
p. 19 — a journalist popularizing Graybiel's MIT work (Jog et al. 1999, *Science*
286:1745, task bracketing). The dopamine claim is right: Schultz, Dayan & Montague (1997),
*Science* 275:1593 — dopamine neurons shift phasic activation from reward delivery to cue
onset. **Qualification:** the field defines habit by *insensitivity to outcome devaluation*
(Wood & Rünger 2016), which the loop diagram obscures — reward builds the association,
then behaviour runs largely independent of it.

**Mere exposure and wearout.** `[MED]` Bornstein (1989), *Psych Bulletin* **106**(2),
265–289 (commonly miscited as vol. 116). Repeated **supraliminal, visual** exposure
increases liking, up to a point — Berlyne's two-factor account (habituation early, tedium
late), Berlyne (1970), *Perception & Psychophysics* 8(5), 279–286.

**Two qualifications that change the advice:**
- Montoya et al. (2017), *Psych Bulletin* 143(5) — inverted-U holds for *"all visual, but
  not auditory stimuli"*; the auditory fit is **U-shaped**. **Do not port repetition
  advice to audio.**
- The "peak at 10–20 exposures" number is a narrative summary of two studies, not a
  meta-analytic estimate, and Bornstein concedes the studies *"produced inconsistent
  results."* Rotate on **measured decay**, not a fixed count.
- Boredom-prone audiences show **no exposure effect at all**; complexity extends the
  runway.

---

## 5. The failure mode to guard against

An artifact that performs its claimed mechanism on the audience and offers the sensation
as proof. The source video teaches three persuasion triggers, then pauses to note *you are
still watching because of those three triggers.*

Feeling an effect is evidence that **something** held attention. It is not evidence that
the proposed *explanation* is correct — the observation is consistent with the theory, with
rival theories, and with the artifact simply being well made. The audience is handed a
vivid datum and no discriminating test: not an absent verifier, a **counterfeit** one.
