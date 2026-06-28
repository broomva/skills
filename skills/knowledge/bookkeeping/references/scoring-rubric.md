# Bookkeeping Skill — Scoring Rubric

This rubric governs the **Nous gate**: a three-dimension scoring system that decides whether a knowledge item is promoted from Layer 2 (raw extract) to Layer 3 (entity page). It generalizes the gate originally designed for `social-intelligence` into a universal knowledge engine.

---

## 1. The Nous Gate — Three Dimensions

Each dimension is scored 0–3. Maximum raw score: **9**.

### Dimension 1: Novelty (0–3)

Does this item introduce information not already represented in the knowledge graph?

| Score | Criteria |
|-------|----------|
| **0** | Completely familiar. Already captured in an existing entity page, synthesis note, or well-known project-internal pattern. No new information. |
| **1** | Minor variation on a known concept. Small elaboration, different phrasing, a concrete example of something already abstracted. Adds marginal texture but no structural novelty. |
| **2** | Meaningfully extends an existing concept, or introduces a concept adjacent to known ones that hasn't been explicitly named. Would update an existing entity page rather than create a new one. |
| **3** | Genuinely new to the knowledge graph. Introduces a concept, pattern, tool, person, or discovery not yet represented. Would require creating a new entity page. |

**Anti-pattern:** Do not inflate novelty for familiar topics just because the source is respected or the phrasing is clever. Novelty is about the knowledge graph state, not the source's reputation.

---

### Dimension 2: Specificity (0–3)

Is the claim grounded in concrete, verifiable, or actionable detail?

| Score | Criteria |
|-------|----------|
| **0** | Pure generality. "AI is changing everything." No concrete mechanism, example, number, or reference. Could have been written by anyone with no domain knowledge. |
| **1** | Some grounding but still largely abstract. Names a concept or domain without specifying mechanism, evidence, or implementation. "Attention mechanisms are key to transformers." |
| **2** | Clear mechanism, example, or quantitative claim. Enough detail that a practitioner could follow up. "RoPE embeddings extend context by rotating query/key vectors in frequency space." |
| **3** | Highly specific: named implementation, benchmarked result, concrete architecture decision, reproducible finding, or direct quote with attribution. "GPT-4o scores 87.5% on MMLU with chain-of-thought, up from 86.4% for GPT-4." |

**Anti-pattern:** Do not fabricate specificity. If the source is vague, score it 0 or 1 even if the concept is interesting. A high-specificity score means the source itself provides concrete grounding.

---

### Dimension 3: Relevance (0–3)

Does this item connect to Broomva's active work, open questions, or strategic directions?

| Score | Criteria |
|-------|----------|
| **0** | No discernible connection to any active project, research thread, or strategic question. Interesting in isolation but not actionable here. |
| **1** | Tangential connection. Could theoretically inform a project but requires multiple inferential steps. Low priority even if true. |
| **2** | Direct connection to an active project, open architecture question, or known knowledge gap. Would be worth reading before the next relevant design session. |
| **3** | Immediately actionable or directly addresses a named open question in the knowledge graph. Filling a gap in an in-progress design, contradicting a current assumption, or providing implementation detail for a planned feature. |

**Anti-pattern:** Do not score relevance 3 just because the item relates to the current project you're working on today. Relevance should reflect lasting strategic value, not session-level topicality.

---

## 2. Promotion Thresholds

| Raw Score | Decision |
|-----------|----------|
| **≥ 7** | Promote to Layer 3 entity page. Mark as **priority** — synthesis candidate. Flag for blog pipeline review. |
| **5–6** | Promote to Layer 3 entity page. Standard promotion. |
| **3–4** | **Ambiguous band** — trigger LLM-as-judge (see Section 3). Do not auto-promote or auto-discard. |
| **≤ 2** | Discard from Layer 3. May retain in Layer 2 raw extract for archival. Do not create entity page. |

---

## 3. Two-Pass Scoring Protocol

### Pass 1: Heuristic Fast-Path

Apply the rubric manually (or via lightweight heuristic prompt) to each item. This pass should take < 5 seconds per item.

1. Read the item.
2. Score each dimension independently (N, S, R).
3. Sum to raw score.
4. If raw score ≤ 2 or ≥ 7: final decision made. Skip Pass 2.
5. If raw score 3–6: flag as ambiguous, proceed to Pass 2.

**Heuristic shortcuts (fast discard):**

- Contains no named concept, tool, person, or mechanism → Specificity ≤ 1
- Paraphrases something already in `docs/` or an existing entity page → Novelty ≤ 1
- Relates only to a project that is archived or on hold → Relevance ≤ 1
- If all three heuristics fire simultaneously → raw score ≤ 3 → likely discard without LLM judge

### Pass 2: LLM-as-Judge (Ambiguous Band: Score 3–6)

For items in the 3–6 range, invoke the LLM judge using the prompt template below. The judge re-scores independently and provides reasoning. Final decision: use judge score if it differs from Pass 1 by ≥ 2 points; otherwise average and round up.

---

## 4. LLM Judge Prompt Template

### System Prompt

```
You are a knowledge curation judge for a personal knowledge management system. Your job is to score a knowledge item on three dimensions and decide whether it should be promoted to a permanent entity page.

Scoring dimensions (each 0-3):
- Novelty: Is this genuinely new information not already in the knowledge graph?
- Specificity: Is the claim grounded in concrete, verifiable, or actionable detail?
- Relevance: Does this connect to active work, open questions, or strategic directions?

Promotion thresholds:
- Raw score ≥ 5: promote to entity page
- Raw score ≤ 4: do not promote (retain as raw extract only)

You must output valid JSON only. No prose outside the JSON block.
```

### User Prompt

```
Score the following knowledge item. Consider only what is explicitly stated in the item text and context — do not infer unstated specificity or relevance.

## Knowledge Graph Context
Active projects: {active_projects_list}
Open questions: {open_questions_list}
Existing entity slugs (sample): {existing_entity_slugs}

## Item to Score
Source type: {source_type}
Source: {source_url_or_id}
Extraction date: {date}

Text:
"""
{item_text}
"""

## Heuristic Pass 1 Score
Novelty: {h_novelty}/3
Specificity: {h_specificity}/3
Relevance: {h_relevance}/3
Raw: {h_raw}/9
Scorer notes: {h_notes}

## Required Output (JSON)
{
  "novelty": <0-3>,
  "specificity": <0-3>,
  "relevance": <0-3>,
  "raw_score": <0-9>,
  "decision": "promote" | "discard",
  "confidence": "high" | "medium" | "low",
  "reasoning": {
    "novelty": "<1-2 sentence justification>",
    "specificity": "<1-2 sentence justification>",
    "relevance": "<1-2 sentence justification>",
    "overall": "<1-2 sentence synthesis>"
  },
  "suggested_entity_types": ["concept"|"pattern"|"tool"|"person"|"project"|"discovery"|"question"|"org"],
  "suggested_slug": "<kebab-case-slug>",
  "contradicts_existing": ["<entity-slug>"] | []
}
```

### Handling Judge Output

- If `confidence: "low"` and `decision: "promote"`: promote but tag entity with `status: candidate` (not `entity`) pending human review.
- If `contradicts_existing` is non-empty: create the entity page AND open a contradiction resolution task per the protocol in `promotion-workflow.md`.
- If `suggested_entity_types` contains multiple types: use the first as primary, add others as tags.

---

## 5. Source Taxonomy

Different source types have characteristic novelty ranges due to their nature. Use this as a calibration baseline — do not mechanically apply these ranges; they are priors, not rules.

| Source Type | Typical Novelty Range | Notes |
|-------------|----------------------|-------|
| **Moltbook threads** | 1–2 | Conversational, often recaps known ideas. Occasionally surfaces novel framings or early-stage concepts before they appear elsewhere. |
| **X (Twitter) replies** | 1–3 | High variance. Expert replies on niche topics can score 3. Most viral takes score 0–1 (familiar ideas dressed up). |
| **Web articles (mainstream)** | 0–2 | Rarely novel for practitioners. Often useful for specificity (benchmark numbers, product releases). |
| **Web articles (specialist / preprint)** | 2–3 | High novelty if from primary researchers. Check publication recency. |
| **Conversation extracts (session logs)** | 1–3 | Own session discoveries can be highly novel to the graph even if not novel to the world. Score against internal graph state. |
| **Research papers** | 2–3 | Typically high novelty if outside mainstream ML. Check whether you've already extracted from this paper. |
| **GitHub READMEs / code comments** | 1–2 | Implementation specifics score high on specificity; novelty depends on whether the technique is already known. |
| **Internal docs / architecture notes** | 0–1 | Usually not novel to the graph — they may have generated the graph entries. Extract only genuinely new sub-insights. |

---

## 6. Blog Candidate Criteria

An entity page or synthesis note becomes a **blog candidate** when any of the following conditions are met:

1. **Promoted item density**: ≥ 3 promoted items (raw score ≥ 5) share a common theme or entity cluster.
2. **Engagement signal**: The source had ≥ 5 replies, quote-tweets, or substantive reactions (for social sources).
3. **Independent invention convergence**: ≥ 2 independent sources (different authors, different platforms) arrive at the same concept or mechanism without citing each other.
4. **Synthesis novelty**: A synthesis note (Layer 4) yields a compound insight not present in any single entity — the compound is the blog angle.
5. **Contradiction resolution**: When two entity pages with conflicting claims are resolved, the resolution itself is often publishable.

When a blog candidate is flagged, set `blog_candidate: true` in the entity or synthesis frontmatter and pass the slug to the `content-creation` skill handoff process described in `promotion-workflow.md`.

---

## 7. Anti-Patterns Reference

Agents applying this rubric must actively guard against the following failure modes:

| Anti-Pattern | Description | Corrective |
|--------------|-------------|------------|
| **Specificity fabrication** | Scoring specificity 2–3 based on what you infer the source *implies*, rather than what it explicitly states. | Score only what is explicitly in the text. If you have to infer it, it's a 0 or 1. |
| **Novelty inflation for respected sources** | Giving Novelty: 3 to a Karpathy tweet that restates well-known backprop intuitions, because the author is respected. | Novelty is about graph state, not source prestige. Ask: "Does a `[[concept]]` already exist?" |
| **Relevance tunnel vision** | Scoring Relevance: 3 only for items relating to the project currently being worked on, ignoring other active threads. | Check all active projects and open questions listed in the graph context, not just today's focus. |
| **Session-topicality bias** | Promoting items because they're on your mind right now, not because they're strategically valuable. | Apply the rubric 24 hours later or ask: "Would this be worth reading in 3 months?" |
| **Ambiguous band lazy discard** | Skipping the LLM judge for 3–4 scores and discarding by default to save time. | Always invoke Pass 2 for scores 3–6. The judge exists precisely for this band. |
| **Compound claim splitting** | Treating a multi-claim item as a single entity and averaging scores across claims. | Split multi-claim items into separate scored items. Each claim gets its own score. |

---

*Self-maintenance rule: When modifying this rubric, verify that all threshold values (promote ≥5, priority ≥7, ambiguous band 3–6) remain consistent with `promotion-workflow.md` and `SKILL.md`. The thresholds must match exactly across all three files.*
