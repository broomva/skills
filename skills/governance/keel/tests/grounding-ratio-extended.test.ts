/**
 * `groundingRatio` — the properties the pre-flight file does not cover.
 *
 * `tests/grounding-ratio.test.ts` (orchestrator-owned) pins the three
 * headline invariants. This file extends them in the direction that matters:
 * the ways the number could be made to go UP without any check improving.
 *
 * Everything here calls the real function. Nothing asserts a literal that the
 * function did not produce.
 */

import { describe, expect, test } from 'bun:test';
import {
  coverageByKind,
  groundingRatio,
  type GroundingClass,
  type Node,
  type Verdict,
} from '../schemas/keel.ts';

let seq = 0;
function v(cls: GroundingClass, confidence = 1): Verdict {
  seq += 1;
  return {
    nodeId: `n${seq}`,
    class: cls,
    writeBoundary: {
      producer: 'synthetic',
      actorCanWrite: cls === 'anchored' ? false : cls === 'self_referential' ? true : null,
      argument: 'synthetic verdict built by the test, not gathered from a target',
    },
    evidence: ['tests/grounding-ratio-extended.test.ts'],
    confidence,
    decidedBy: 'agent',
  };
}

const many = (cls: GroundingClass, n: number): Verdict[] =>
  Array.from({ length: n }, () => v(cls));

describe('groundingRatio · unknown fails closed', () => {
  test('unknown drags the ratio down exactly as self_referential does', () => {
    // The two classes mean different things but cost the same. That is the
    // whole point of failing closed: not knowing is never cheaper than knowing
    // the answer is bad.
    const withUnknown = groundingRatio([...many('anchored', 3), ...many('unknown', 2)]);
    const withSelfRef = groundingRatio([...many('anchored', 3), ...many('self_referential', 2)]);
    expect(withUnknown.ratio).toBe(withSelfRef.ratio);
    expect(withUnknown.ratio).toBeCloseTo(0.6, 12);
  });

  test('an all-unknown target scores 0, not 1 and not NaN', () => {
    const r = groundingRatio(many('unknown', 7));
    expect(r.ratio).toBe(0);
    expect(Number.isNaN(r.ratio)).toBe(false);
    expect(r.unknown).toBe(7);
  });

  test('resolving an unknown to anchored is the only way the ratio rises', () => {
    const before = groundingRatio([...many('anchored', 1), ...many('unknown', 1)]);
    const after = groundingRatio(many('anchored', 2));
    expect(after.ratio).toBeGreaterThan(before.ratio);
  });
});

describe('groundingRatio · not_a_check is the shoppable class', () => {
  test('re-filing a self_referential edge as not_a_check inflates the score', () => {
    // Demonstrated, not asserted in prose: this is precisely why `not_a_check`
    // carries the same burden of argument as any other verdict and why its
    // count is reported next to the ratio.
    const honest = groundingRatio([...many('anchored', 1), ...many('self_referential', 1)]);
    const shopped = groundingRatio([...many('anchored', 1), ...many('not_a_check', 1)]);
    expect(honest.ratio).toBe(0.5);
    expect(shopped.ratio).toBe(1);
    // The evidence of shopping survives in the output — the count is right
    // there, so a consumer can show 1.0 over one edge with one thing excluded.
    expect(shopped.notACheck).toBe(1);
    expect(shopped.anchored).toBe(1);
  });

  test('a report of nothing but not_a_check is "nothing to judge", scored 0', () => {
    const r = groundingRatio(many('not_a_check', 20));
    expect(r.ratio).toBe(0);
    expect(r.notACheck).toBe(20);
    expect(r.anchored + r.selfReferential + r.unknown).toBe(0);
  });

  test('adding not_a_check verdicts never moves the ratio in either direction', () => {
    const base = [...many('anchored', 3), ...many('self_referential', 4), ...many('unknown', 1)];
    const start = groundingRatio(base).ratio;
    for (let i = 1; i <= 5; i++) {
      expect(groundingRatio([...base, ...many('not_a_check', i)]).ratio).toBe(start);
    }
  });
});

describe('groundingRatio · nothing defaults to anchored', () => {
  test('classes are counted, never inferred', () => {
    const counts = groundingRatio([
      ...many('anchored', 2),
      ...many('self_referential', 3),
      ...many('unknown', 5),
      ...many('not_a_check', 7),
    ]);
    expect(counts.anchored).toBe(2);
    expect(counts.selfReferential).toBe(3);
    expect(counts.unknown).toBe(5);
    expect(counts.notACheck).toBe(7);
    expect(counts.ratio).toBe(2 / 10);
  });

  test('the empty target is 0 with every count at 0', () => {
    const r = groundingRatio([]);
    expect(r).toEqual({
      anchored: 0,
      selfReferential: 0,
      unknown: 0,
      notACheck: 0,
      ratio: 0,
    });
  });

  test('ratio is always a finite number in 0..1 across random mixes', () => {
    // Property sweep rather than a single case: any input the engine can
    // produce must yield a number a chart can render.
    const classes: GroundingClass[] = ['anchored', 'self_referential', 'unknown', 'not_a_check'];
    for (let trial = 0; trial < 200; trial++) {
      const verdicts: Verdict[] = [];
      const n = trial % 13;
      for (let i = 0; i < n; i++) {
        verdicts.push(v(classes[(trial * 7 + i * 3) % 4] as GroundingClass));
      }
      const r = groundingRatio(verdicts);
      expect(Number.isFinite(r.ratio)).toBe(true);
      expect(r.ratio).toBeGreaterThanOrEqual(0);
      expect(r.ratio).toBeLessThanOrEqual(1);
    }
  });

  test('the ratio is invariant under shuffling — order carries no information', () => {
    const base = [
      ...many('anchored', 5),
      ...many('self_referential', 3),
      ...many('unknown', 2),
      ...many('not_a_check', 4),
    ];
    const expected = groundingRatio(base).ratio;
    for (let s = 0; s < 25; s++) {
      const shuffled = base
        .map((x, i) => ({ x, k: (i * 2654435761 + s * 40503) % 1013 }))
        .sort((a, b) => a.k - b.k)
        .map((o) => o.x);
      expect(groundingRatio(shuffled).ratio).toBe(expected);
    }
  });
});

describe('coverageByKind', () => {
  const node = (kind: Node['kind'], i: number): Node => ({
    id: `${kind}-${i}`,
    kind,
    name: `${kind} ${i}`,
    source: `synthetic:${i}`,
    raw: `synthetic ${kind}`,
  });

  test('counts partition the input exactly', () => {
    const nodes = [
      node('ci_step', 1),
      node('ci_step', 2),
      node('script', 3),
      node('review_gate', 4),
    ];
    const cov = coverageByKind(nodes);
    expect(cov).toEqual({ ci_step: 2, script: 1, review_gate: 1 });
    expect(Object.values(cov).reduce((a, b) => a + b, 0)).toBe(nodes.length);
  });

  test('an empty target reports no coverage rather than a fabricated zero row', () => {
    // "Nothing gathered" and "gathered nothing of this kind" are different
    // claims; only the first is true of an empty target.
    expect(coverageByKind([])).toEqual({});
  });
});
