# Probes

Crystallized judgment. Each probe generalizes one *shape* of verification edge
that the agent has already reasoned about once.

This directory ships with the skill. Runtime-minted probes go to
`~/.config/keel/probes/` instead, so a skill update never destroys them.

Both directories are loaded at classify time; shipped probes are tried first.

## Contract

See `../schemas/keel.ts`. A probe implements:

```ts
match(node: Node): boolean
assess(node: Node): Omit<Verdict, 'nodeId' | 'decidedBy' | 'probeId'> | null
```

## Rules

1. **Abstain when unsure.** `assess` returns `null` and the agent decides. A
   probe may never return `unknown` — `unknown` is a claim about the world and
   only the agent makes it. This is what keeps `unknown` unshoppable and makes
   a lazy probe degrade to "ask" rather than to "looks fine."
2. **Generalize the shape, not the repo.** `match` keys on structure. A probe
   that recognizes one project is a hardcoded answer.
3. **One probe, one shape.** A probe that matches everything is a rule table in
   costume, and it will rot silently.
4. **Small enough to review in a minute.** Probes are code specifically so a
   human can reject them.

## Contributing

Copy a probe you minted from `~/.config/keel/probes/` into this directory and
open a PR. Include the node it was minted from and the reasoning that produced
it. The library compounds across everyone who runs Keel — that is the whole
point.

Probes are audited: Keel re-decides a sample of probe-classified nodes
agentically and retires probes that disagree. A probe earning its place is one
that keeps agreeing with fresh judgment.
