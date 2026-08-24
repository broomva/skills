/**
 * `tests/fixtures/report.sample.json` — the real thing.
 *
 * It is Keel measuring ITSELF: 15 of this repo's 32 gathered edges, every
 * verdict adversarially reviewed. It is the input every downstream consumer
 * (renderer, site, curve) is built against, so if it drifts out of shape those
 * units break silently and late.
 *
 * These tests RECOMPUTE from the fixture's own verdicts rather than restating
 * its stored numbers. A test that asserted `grounding.ratio === 0.444` would be
 * `self_referential` by this repo's own definition: the artifact would be
 * checking a copy of itself. Recomputation forks the signal.
 *
 * NOTE: the fixture contains zero `unknown` verdicts, and that is a RESULT, not
 * a gap — the unpinned out-of-repo dependencies resolve to `self_referential`
 * because the resolution mechanism is itself committed. Nothing here asserts
 * that `unknown` appears; the `unknown` code path is exercised against
 * synthetic verdicts in `grounding-ratio-extended.test.ts` instead.
 */

import { describe, expect, test } from 'bun:test';
import fixture from './fixtures/report.sample.json' with { type: 'json' };
import {
  coverageByKind,
  groundingRatio,
  type GroundingClass,
  type Report,
} from '../schemas/keel.ts';

const report = fixture as unknown as Report;
const CLASSES: readonly GroundingClass[] = [
  'anchored',
  'self_referential',
  'unknown',
  'not_a_check',
];

describe('fixture · shape', () => {
  test('parses as a Report with every required field populated', () => {
    expect(typeof report.target).toBe('string');
    expect(report.target.length).toBeGreaterThan(0);
    expect(report.revision).toMatch(/^[0-9a-f]{7,40}$/);
    expect(Number.isNaN(Date.parse(report.generatedAt))).toBe(false);
    expect(Array.isArray(report.nodes)).toBe(true);
    expect(Array.isArray(report.verdicts)).toBe(true);
    expect(report.nodes.length).toBeGreaterThan(0);
  });

  test('every node is a well-formed Node carrying its literal snippet', () => {
    for (const n of report.nodes) {
      expect(typeof n.id).toBe('string');
      expect(n.id.length).toBeGreaterThan(0);
      expect(typeof n.name).toBe('string');
      expect(typeof n.source).toBe('string');
      expect(n.source.length).toBeGreaterThan(0);
      // `raw` is what the agent reasons over. An empty one means the judgment
      // had nothing to look at.
      expect(n.raw.trim().length).toBeGreaterThan(0);
    }
    expect(new Set(report.nodes.map((n) => n.id)).size).toBe(report.nodes.length);
  });

  test('verdicts and nodes are in one-to-one correspondence', () => {
    const nodeIds = new Set(report.nodes.map((n) => n.id));
    for (const v of report.verdicts) {
      expect(nodeIds.has(v.nodeId)).toBe(true);
    }
    expect(new Set(report.verdicts.map((v) => v.nodeId)).size).toBe(report.verdicts.length);
    expect(report.verdicts).toHaveLength(report.nodes.length);
  });
});

describe('fixture · the stored ratio is the computed ratio', () => {
  const recomputed = groundingRatio(report.verdicts);

  test('grounding recomputes exactly from the verdicts', () => {
    // The single check that would catch a hand-edited number, a dropped verdict,
    // or a consumer being fed a total that no longer matches its parts.
    expect(recomputed).toEqual(report.grounding);
  });

  test('the denominator is anchored + self_referential + unknown, and nothing else', () => {
    const { anchored, selfReferential, unknown, notACheck, ratio } = report.grounding;
    expect(anchored + selfReferential + unknown + notACheck).toBe(report.verdicts.length);
    // not_a_check is excluded — recomputing without it must not move the ratio.
    const withoutNotAChecks = groundingRatio(
      report.verdicts.filter((v) => v.class !== 'not_a_check'),
    );
    expect(withoutNotAChecks.ratio).toBe(ratio);
    expect(ratio).toBe(anchored / (anchored + selfReferential + unknown));
  });

  test('every verdict class is one of the four', () => {
    for (const v of report.verdicts) {
      expect(CLASSES).toContain(v.class);
    }
  });
});

describe('fixture · the argument is the product', () => {
  test('every verdict carries a non-empty writeBoundary argument', () => {
    // The class is a label; the argument is the claim. A verdict without one is
    // an assertion nobody can check — which is the thing this tool exists to
    // detect.
    for (const v of report.verdicts) {
      expect(typeof v.writeBoundary.argument).toBe('string');
      expect(v.writeBoundary.argument.trim().length).toBeGreaterThan(0);
      expect(v.writeBoundary.producer.trim().length).toBeGreaterThan(0);
    }
  });

  test('the argument names a causal path rather than restating the class', () => {
    for (const v of report.verdicts) {
      const arg = v.writeBoundary.argument.trim();
      // Cheap structural floor, not a quality judgment: one sentence minimum.
      expect(arg.length).toBeGreaterThanOrEqual(40);
      expect(arg.toLowerCase()).not.toBe(v.class.replace(/_/g, ' '));
    }
  });

  test('actorCanWrite agrees with the class it produced', () => {
    // `actorCanWrite` IS the fork point. If it disagrees with the class, one of
    // the two was typed rather than derived.
    for (const v of report.verdicts) {
      if (v.class === 'anchored') expect(v.writeBoundary.actorCanWrite).toBe(false);
      if (v.class === 'self_referential') expect(v.writeBoundary.actorCanWrite).toBe(true);
      if (v.class === 'unknown') expect(v.writeBoundary.actorCanWrite).toBeNull();
    }
  });

  test('every verdict cites concrete evidence and a calibrated confidence', () => {
    for (const v of report.verdicts) {
      expect(Array.isArray(v.evidence)).toBe(true);
      expect(v.evidence.length).toBeGreaterThan(0);
      for (const e of v.evidence) expect(e.trim().length).toBeGreaterThan(0);
      expect(v.confidence).toBeGreaterThan(0);
      expect(v.confidence).toBeLessThanOrEqual(1);
      expect(['probe', 'agent']).toContain(v.decidedBy);
    }
  });
});

describe('fixture · the confidence smell', () => {
  /**
   * Low confidence on `anchored` is the one asymmetric error: it is the only
   * class that can raise the ratio, so an unsure one is where an inflated score
   * would come from. The threshold is `< 0.6` (orchestrator ruling — the
   * fixture's honest minimum is 0.5, so `< 0.5` could never fire on real data).
   */
  const smells = report.verdicts.filter((v) => v.class === 'anchored' && v.confidence < 0.6);

  test('the smell set is computable and non-vacuous on real data', () => {
    // If this ever hits zero, either the fixture changed or the threshold has
    // drifted back to something that cannot fire — both worth knowing.
    expect(smells.length).toBeGreaterThan(0);
    expect(smells.length).toBeLessThan(report.grounding.anchored);
  });

  test('a flagged verdict still argues its case — low confidence is not an excuse', () => {
    for (const v of smells) {
      expect(v.writeBoundary.argument.trim().length).toBeGreaterThanOrEqual(40);
      expect(v.evidence.length).toBeGreaterThan(0);
    }
  });
});

describe('fixture · economics disclose the cap', () => {
  const e = report.economics;

  test('nodesSampled and nodesTotal are both present and consistent', () => {
    expect(e.nodesSampled).toBeLessThanOrEqual(e.nodesTotal);
    expect(e.nodesSampled).toBe(report.verdicts.length);
    // This fixture IS a stratified sample. The difference is the disclosure
    // path — a consumer that renders only one of these hides a cap.
    expect(e.nodesSampled).toBeLessThan(e.nodesTotal);
  });

  test('provenance adds up to the number of verdicts', () => {
    expect(e.decidedByProbe + e.decidedByAgent).toBe(report.verdicts.length);
    const byProbe = report.verdicts.filter((v) => v.decidedBy === 'probe').length;
    expect(e.decidedByProbe).toBe(byProbe);
    expect(e.decidedByAgent).toBe(report.verdicts.length - byProbe);
  });

  test('token counts are marked as estimates', () => {
    // No API exposes a skill's own session usage, so any chart axis fed by this
    // must read "estimated". Flipping this to false without a real counter
    // would be the quietest lie in the report.
    expect(e.tokensEstimated).toBe(true);
    expect(e.tokensIn).toBeGreaterThan(0);
    expect(e.tokensOut).toBeGreaterThan(0);
    expect(e.wallClockMs).toBeGreaterThan(0);
  });

  test('a probe-free run reports an honest zero rather than an absent field', () => {
    expect(e.probesMinted).toBeGreaterThanOrEqual(0);
    expect(e.probeLibrarySize).toBeGreaterThanOrEqual(0);
    expect(e.decidedByProbe).toBe(0);
  });
});

describe('fixture · coverage travels with the ratio', () => {
  test('coverageByKind partitions the judged nodes exactly', () => {
    const cov = coverageByKind(report.nodes);
    const total = Object.values(cov).reduce((a, b) => a + b, 0);
    expect(total).toBe(report.nodes.length);
    expect(Object.keys(cov).length).toBeGreaterThan(1);
    for (const n of report.nodes) expect(cov[n.kind]).toBeGreaterThan(0);
  });

  test('the absolute anchored count is available beside the ratio', () => {
    // The ratio never travels alone: 1.0 over one edge and 0.7 over fifty are
    // different claims, and a bare ratio rewards deleting checks.
    expect(report.grounding.anchored).toBe(
      report.verdicts.filter((v) => v.class === 'anchored').length,
    );
  });
});
