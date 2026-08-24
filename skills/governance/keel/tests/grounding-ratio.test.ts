/**
 * Pre-flight smoke test — ORCHESTRATOR-OWNED (see 00-orchestration.md).
 *
 * Exists for two reasons:
 *   1. `bun test` must exit 0 before fan-out, or every dispatched unit reads a
 *      pre-existing failure as damage it caused and burns iterations on it.
 *   2. `groundingRatio` is the headline number. The three properties below are
 *      the ones whose breakage would silently INFLATE it, which is the only
 *      direction that matters for a tool arguing about honest measurement.
 *
 * W1-E owns `tests/**` generally and should build on this file, not replace it.
 */

import { expect, test, describe } from 'bun:test';
import { groundingRatio, type Verdict, type GroundingClass } from '../schemas/keel.ts';

function v(cls: GroundingClass, i: number): Verdict {
  return {
    nodeId: `n${i}`,
    class: cls,
    writeBoundary: { producer: 'test', actorCanWrite: null, argument: 'fixture' },
    evidence: [],
    confidence: 1,
    decidedBy: 'agent',
  };
}

describe('groundingRatio', () => {
  test('not_a_check is excluded from the denominator', () => {
    const without = groundingRatio([v('anchored', 1), v('self_referential', 2)]);
    const with_ = groundingRatio([
      v('anchored', 1),
      v('self_referential', 2),
      v('not_a_check', 3),
      v('not_a_check', 4),
    ]);
    // Same ratio: not_a_check asserts nothing, so counting it either way lies.
    expect(with_.ratio).toBe(without.ratio);
    expect(with_.ratio).toBe(0.5);
    // ...but it is still REPORTED, because it is the shoppable class.
    expect(with_.notACheck).toBe(2);
  });

  test('unknown counts AGAINST the ratio — it fails closed', () => {
    const r = groundingRatio([v('anchored', 1), v('unknown', 2)]);
    expect(r.ratio).toBe(0.5);
    expect(r.unknown).toBe(1);
  });

  test('no verdicts yields 0, never 1 — an empty target is not a perfect one', () => {
    expect(groundingRatio([]).ratio).toBe(0);
    expect(groundingRatio([v('not_a_check', 1)]).ratio).toBe(0);
  });
});
