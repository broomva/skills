# Evidence behind the citable thresholds

Confidence tags: `[HIGH]` read verbatim from the primary study · `[MED]`
practitioner claim with a plausible mechanism, primary source not opened ·
`[LOW]` secondhand, uncorroborated.

Every quantified effect the skill reports must name its study. There is a test
enforcing that (`test_effects_carry_a_source`), because a number without
provenance is exactly the failure this skill exists to prevent.

---

## Primary source 1 — Scrunch

**"LinkedIn posts that robots can't resist: What the data says about ChatGPT
citations"**, Michael Iannelli, Principal Data Scientist, published 2026-05-06.
<https://scrunch.com/blog/linkedin-posts-robots-cant-resist-what-data-says-about-chatgpt-citations>

**Methodology** `[HIGH]`

- 12,000 LinkedIn post observations from ChatGPT, 2026-01-15 → 2026-04-15.
- Critically, the sample **includes posts ChatGPT considered relevant and chose
  not to cite**. That control arm is what makes the estimates meaningful rather
  than descriptive.
- ~4,000 posts analysed for citations and reactions, controlling for author
  audience size and post age.
- 21 content dimensions annotated by `gpt-5-mini` at high reasoning effort.
- Causal estimates via **double machine learning** (Chernozhukov et al.), which
  estimates each dimension's effect while controlling for every other measured
  dimension.

**Effects used by the linter** `[HIGH]`

| Dimension | Citation | Reactions |
|---|---|---|
| Technical details | +77% | ~0 (not distinguishable from zero) |
| Named entities | +33% | +5% |
| Topic specificity | +18% | +13% |
| Link-in-comments | −31% | +11% |
| Unicode formatting | −58% | +12% |
| FAQ-structured post | 0 | −9% |
| Follow-for-more CTA | 0 | +22% |
| Originality / first-person authority / anecdote / step-by-step / line-break rhythm | 0 | +13 / +12 / +11 / +7 / +6% |

**Engagement does not drive citation** `[HIGH]` — after controlling for content
dimensions, post age, and prompt difficulty, reaction count has near-zero
predictive power. A post with 100 reactions is cited at essentially the same rate
as one with 10,000.

**The unicode mechanism** `[HIGH]` — LinkedIn's editor has no native bold, so
authors substitute Mathematical Alphanumeric Symbols (U+1D400–U+1D7FF).
ChatGPT's retriever does not apply **NFKD** (Normalization Form Compatibility
Decomposition), so `𝗗𝗮𝘁𝗮 𝗟𝗲𝗮𝗱𝗲𝗿` never decomposes to `Data Leader`. Scrunch
isolates the penalty to ChatGPT: Perplexity showed no significant penalty, and
Google AI Mode had zero unicode in snippets across 390K observations. The effect
is large enough that a confounder would need to be ~4.6× stronger than anything
else measured to explain it away.

It applies to **any page the retriever fetches**, not only posts — headlines,
bios, About sections, press releases pasted from formatted sources.

**Link-in-comments transfers citability** `[HIGH]` — the post drops to 13%
citation, but URLs in the comments are cited 47% of the time against a ~24%
baseline, and when both the post and its linked source appear in the same
retrieval set, the source jumps 24% → 59%. So it is a deliberate trade, correct
when the destination is the asset you own. The linter WARNs rather than FAILs for
exactly this reason.

**Volume** `[HIGH]` — ~8M LinkedIn citations per week in the US for
industry/commercial prompts, growing 13% month over month as of Q1 2026.

---

## Primary source 2 — Semrush

**LinkedIn AI visibility study**, 2026.
<https://www.semrush.com/blog/linkedin-ai-visibility-study/>

**Methodology** `[HIGH]` — 325,000 unique prompts across ChatGPT Search, Google
AI Mode, and Perplexity, January–February 2026, spanning 12 major industry
categories; 89,000 unique cited LinkedIn URLs.

**Findings used** `[HIGH]`

- LinkedIn is the **#2 most-cited domain**, ahead of Wikipedia, YouTube, and
  every major news publisher.
- Appears in **11% of AI responses** on average (Perplexity 5.3%, Google AI Mode
  13.5%, ChatGPT Search 14.3%).
- **Articles are 50–66% of cited LinkedIn content** across all three models.
  Sweet spot 500–2,000 words; feed posts 50–299 words. Reshares are rarely
  referenced.
- Most cited posts have **15–25 reactions and one comment**.
- ~75% of cited authors post 5+ times in a four-week window.
- Individuals with **under 500 followers** beyond their connections are cited as
  often or more than larger accounts. This corroborates Scrunch's
  engagement-null result via a different dataset and method.
- Placement splits by engine: Perplexity cites Company Pages 59% of the time;
  ChatGPT Search and Google AI Mode cite individual creators 59% of the time.
- Semantic similarity between cited source and AI response runs 0.57–0.60, which
  is why holding a consistent vocabulary works.

---

## Supporting context — the distribution model

LinkedIn replaced five independent retrieval pipelines with one LLM. The
foundation model is **360Brew**, a 150B-parameter decoder-only model trained on
LinkedIn data, solving 30+ predictive tasks without task-specific fine-tuning.
arXiv 2501.16450, LinkedIn Foundation AI Technologies, submitted 2025-01-27.
<https://arxiv.org/abs/2501.16450> `[HIGH]`

Made public 2026-03-12 via LinkedIn's engineering blog, a corporate
announcement, and a post from the VP of Engineering. `[MED — corroborated by
independent reporting; LinkedIn's own post not opened directly]`

Two corollaries the linter does not enforce but the skill's judgement section
uses:

- Only five author fields travel with a post into another member's feed: Name,
  Headline, Company, Industry, Title. `[MED]`
- The retrieval model truncates to roughly the first 60 tokens (~45–50 words)
  when deciding candidate-pool inclusion. `[MED — practitioner reading of
  published material, consistent with the architecture, not verified in a
  primary source]`

---

## Not verified

- That LinkedIn's UI truncates on a **pixel** budget rather than a character
  count (a capital `W` being ~4× the width of a capital `I`, ~110 width units per
  line on mobile) is a practitioner finding with a plausible and testable
  mechanism, and no primary source. `[MED]` The skill states the general
  principle — find out what a surface truncates *on* — rather than the specific
  number, deliberately.

## Known decay

ChatGPT's LinkedIn citation rate **dipped in April 2026**, apparently an
algorithm change, and the dip was not mirrored on Google's surfaces. `[HIGH]`

Everything here is a snapshot of two studies over one platform inside a single
measurement window. The coefficients will move. The structural finding — two
selection surfaces, partially anti-correlated, one selecting on substance rather
than popularity — is the part worth building on.
