# Agentic-work extension

Load this extension only when the product models autonomous or long-running work, agent runs, lifecycle views, or human-in-the-loop decisions. It is not part of the platform-neutral Broomva foundation.

## The primary object is work

An agentic Broomva interface should answer four questions quickly:

1. What is happening?
2. What changed?
3. What evidence exists?
4. What, if anything, do you need from me?

Do not substitute decorative dashboard metrics for those answers.

## Canonical states

| State | Meaning | UI treatment |
|---|---|---|
| `Queued` | Accepted but not started | Quiet neutral label; no motion |
| `Running` | Actively executing | Undertow around the work surface or a tidepool dot in compact rows |
| `Stuck` | Cannot progress without a system or dependency change | Warning treatment plus a concrete blocker |
| `Needs you` | A specific human choice or intervention is required | Tidepool Cyan accent, direct ask, and explicit actions |
| `Done` | The intended outcome is complete and verified | Resolved green plus receipts or verification evidence |
| `Standing` | Alive and listening between events | Quiet pulse or static live mark; never shown as active execution |

Keep labels exact so components, copy, and automation share one vocabulary.

## Evidence hierarchy

Prefer this order inside a run detail:

1. Outcome or current state
2. Decided: decisions the system made and why
3. Asks: choices only the user can make
4. Receipts: commands, artifacts, checks, links, or observed effects
5. Lifecycle: passed, current, warning, and upcoming stages

A receipt must describe something observable. It is not a celebratory activity message.

## Composition patterns

- Use `RunCard` for a bounded unit of work with state, agent, duration, decisions, asks, and receipts.
- Use `WorkState` for compact status text; use its chip variant only where spatial grouping helps.
- Use `Receipt` and `ReceiptRow` for proof, commands, artifacts, and checks.
- Use `LifecycleRail` for ordered stages, not a fake numeric completion model.
- Use `AutonomyScoreboard` only when the underlying receipts justify the summary.
- Use `Composer` for the next instruction or intervention when a persistent control surface is central to the product.

## Human attention

`Needs you` is expensive. Use it only when autonomous options are exhausted or policy requires human judgment. State the decision, the consequences of each option, and the safest default. Never use urgency styling merely to increase engagement.

## Extension boundary

Undertow, tidepool, canonical work states, receipts, Maestro patterns, the signature composer, and work-specific components belong here. They may reuse the foundation palette, typography, spacing, glass, and accessibility rules. They must not become mandatory vocabulary or composition rules for commerce, editorial, analytics, settings, communication, or other unrelated products.
