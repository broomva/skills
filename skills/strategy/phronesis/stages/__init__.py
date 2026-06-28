"""Engagement stages — 5 modules implementing the Discovery-grade flow.

Each stage:
1. Reads engagement state via journal replay
2. Consumes inputs (interviews, framework selections, prior outputs)
3. Emits typed journal events through Engagement.emit()
4. Enforces its L-rule gate (L1 in intake, L2 in ideate, L4/L5 in roadmap)
5. Requests a STAGE_REVIEW gate at the end (P5)

Stages are PURE WRT the engagement aggregate — they only mutate via emit().
This is the contract that makes replay deterministic.
"""
