# Coaching — NOT IMPLEMENTED in v1

**Status:** **NOT IMPLEMENTED.** Placeholder for v2.

In v1, the Health skill is a **substrate**, not a coach. It surfaces measured metrics and validated synthesis. It does **not** issue prescriptions ("take a rest day", "do zone 2 today", "go for the PR attempt this morning"). Coaching is a v2 surface that requires substantially more integration than v1 provides.

## Why v1 deliberately omits this

The agent has access to:
- a trace store with validated synthesis (CTL/ATL/TSB, HRV-CV, VO2max arc)
- vendor opaque scores (Body Battery, Training Readiness) — flagged [LOW]
- prose-grade Markdown in the daily note

The agent does **not** have access to:
- the user's **race calendar** (Telos PROJECTS or external)
- the user's **subjective state** (mood, life stress, sleep quality, soreness)
- the user's **training plan** (block phase, peaking timeline)
- the user's **medical history** (injuries, conditions)
- recent **conversation context** beyond a single turn

Issuing prescriptions from an incomplete picture is unsafe. v1 enforces this by **not exposing a coaching command at all**. The agent can quote the metrics; the human interprets.

## v2 vision

The v2 Coaching workflow will compose:

| Input | Source |
|---|---|
| Today's CTL/ATL/TSB | `RecoveryReview` |
| 7-day HRV-CV trend | `RecoveryReview` |
| VO2max arc | `VO2maxArc` |
| Recent activity types & intensities | Trace DB workout query |
| Active GOALS (e.g. "PR 5k by 2026-08-01") | Telos `GOALS.md` |
| Active MISSION frame (longevity vs performance) | Telos `MISSION.md` |
| Mental models loaded (Attia / Galpin / Sims) | Telos `MODELS.md` |
| Calendar load for the next 48h | (TBD — external) |
| Subjective state | (TBD — daily-note prose section parsed) |

…and synthesize a *recommendation* tagged with confidence + counterfactual ("today is a higher-priority recovery day than a zone-2 day because [X]; but if [Y], invert"). The agent surfaces the recommendation; the user decides.

This is **not** going to be a vendor-style "Recovery 65 — be cautious today" score. It will be transparent, counterfactual, and grounded in the validated synthesis layer.

## Until then

Use the v1 substrate workflows ([RecoveryReview](RecoveryReview.md), [TrainingLoad](TrainingLoad.md), [VO2maxArc](VO2maxArc.md)) and interpret yourself. Document recurring interpretation patterns under `research/notes/YYYY-MM-DD-coaching-patterns-raw.md` — when the rule-of-three pattern emerges (three concrete decisions the agent could have automated correctly), promote into the v2 Coaching design.

Per the bstack engine (CLAUDE.md §Crystallize): primitives are crystallized, not designed-first.
