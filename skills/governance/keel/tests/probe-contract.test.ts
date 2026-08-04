/**
 * The probe contract — the mechanism that keeps `unknown` unshoppable.
 *
 *   A probe may NEVER return `unknown`. `unknown` is a claim about the world and
 *   only the agent makes it. A probe that cannot tell abstains (`null`).
 *
 * There are exactly two enforcement points, and both are tested here:
 *
 *   COMPILE TIME — `ProbeVerdict.class` is `Exclude<GroundingClass,'unknown'>`,
 *     so a probe written in TypeScript cannot even express the verdict. Proved
 *     below with `@ts-expect-error`, which FAILS `bunx tsc --noEmit` if the
 *     error ever stops happening. (This one is invisible to `bun test`, which
 *     does not typecheck — it is checked by the second half of the acceptance
 *     command, and by CI.)
 *
 *   ASSESS-CALL TIME — a probe can be plain JS and lie to the compiler, so the
 *     sandbox child re-checks the returned object at the only moment it exists.
 *     Proved below by writing a lying probe to disk and RUNNING it.
 *
 * There is deliberately NO load-time test: a probe's return value is only
 * knowable by calling it, and calling it may only happen inside the sandbox.
 * "Rejected at load time" is not implementable, so it is not asserted.
 */

import { afterAll, describe, expect, test } from 'bun:test';
import { join } from 'node:path';
import type { ProbeVerdict } from '../schemas/keel.ts';
import { runSandbox } from '../scripts/probe-sandbox.ts';
import { cleanupTrees, tree } from './helpers/tree.ts';

afterAll(cleanupTrees);

// ---------------------------------------------------------------------------
// Compile-time enforcement.
// ---------------------------------------------------------------------------

const legal: ProbeVerdict = {
  class: 'self_referential',
  writeBoundary: {
    producer: 'the test suite',
    actorCanWrite: true,
    argument: 'a legal probe verdict, present so the illegal one below is a contrast',
  },
  evidence: ['tests/probe-contract.test.ts'],
  confidence: 1,
};

const illegal = {
  // @ts-expect-error — `unknown` is excluded from ProbeVerdict at the TYPE
  // level. If this line ever compiles, the contract has been widened and the
  // typecheck must fail loudly rather than the class quietly becoming
  // shoppable. TS2322.
  class: 'unknown',
  writeBoundary: {
    producer: 'a probe that should not be able to say this',
    actorCanWrite: null,
    argument: 'this object exists only to be rejected by the compiler',
  },
  evidence: [],
  confidence: 1,
} satisfies ProbeVerdict;

// ---------------------------------------------------------------------------
// Runtime enforcement, at assess-call time, inside the sandbox child.
// ---------------------------------------------------------------------------

const NODES = [
  'abstain',
  'good',
  'liar',
  'notacheck',
  'sloppy',
  'thrower',
  'matchthrower',
  'undef',
].map((n) => ({
  id: n,
  kind: 'ci_step' as const,
  name: n,
  source: `synthetic/${n}.yml:1`,
  raw: `- run: ${n}`,
}));

/** A probe that fires on exactly one node id, returning `body`. */
function targeted(id: string, body: string): string {
  return `const probe = {
  id: ${JSON.stringify(id)},
  version: 1,
  mintedAt: '2026-07-24T00:00:00.000Z',
  mintedFrom: 'synthetic#test',
  description: 'probe-contract test probe',
  match(node) { return node.id === ${JSON.stringify(id)}; },
  assess(node) { ${body} },
};
export default probe;
`;
}

function verdictLiteral(cls: string, extra = ''): string {
  return `return {
    class: ${JSON.stringify(cls)},
    writeBoundary: {
      producer: 'the test suite',
      actorCanWrite: ${cls === 'anchored' ? 'false' : 'true'},
      argument: 'a synthetic verdict emitted by the keel probe-contract test',
    },
    evidence: [node.source],
    confidence: 0.9${extra},
  };`;
}

const PROBE_DIR = tree({
  // abstains — recognizes the shape, cannot establish the fork point
  'abstain.v1.ts': targeted('abstain', 'return null;'),
  // a well-behaved probe
  'good.v1.ts': targeted('good', verdictLiteral('self_referential')),
  // ...and one asserting the other legal non-anchored class
  'notacheck.v1.ts': targeted('notacheck', verdictLiteral('not_a_check')),
  // plain-JS liar: asserts `unknown` in defiance of the type
  'liar.v1.ts': targeted('liar', verdictLiteral('unknown')),
  // structurally malformed verdict (confidence out of range)
  'sloppy.v1.ts': targeted('sloppy', verdictLiteral('anchored').replace('0.9', '4')),
  // throws inside assess
  'thrower.v1.ts': targeted('thrower', 'throw new Error("assess blew up");'),
  // throws inside match
  'matchthrower.v1.ts': `const probe = {
  id: 'matchthrower', version: 1,
  mintedAt: '2026-07-24T00:00:00.000Z', mintedFrom: 'synthetic#test',
  description: 'a probe whose match() throws',
  match(node) { if (node.id === 'matchthrower') throw new Error('match blew up'); return false; },
  assess() { return null; },
};
export default probe;
`,
  // returns undefined rather than null — also an abstention
  'undef.v1.ts': targeted('undef', 'return undefined;'),
  // fires only on a node id that is not in this run's node list
  'orphan.v1.ts': targeted('orphan', verdictLiteral('anchored')),
  // recognizes nothing at all — the "no probe library" path, per node
  'nevermatches.v1.ts': `const probe = {
  id: 'nevermatches', version: 1,
  mintedAt: '2026-07-24T00:00:00.000Z', mintedFrom: 'synthetic#test',
  description: 'a probe that recognizes nothing',
  match() { return false; },
  assess() { return { class: 'anchored', writeBoundary: { producer: 'x', actorCanWrite: false, argument: 'this must never be reached because match() is false' }, evidence: [], confidence: 1 }; },
};
export default probe;
`,
});

const NODES_JSON = join(tree({ 'nodes.json': JSON.stringify(NODES, null, 2) }), 'nodes.json');

const out = await runSandbox(NODES_JSON, [PROBE_DIR]);
const decidedIds = out.decided.map((v) => v.nodeId).sort();
const pendingIds = out.pending.map((n) => n.id).sort();
const warnings = out.warnings.join('\n');

describe('probe contract · a probe may never assert `unknown`', () => {
  test('a lying probe is rejected at assess-call time and its node stays undecided', () => {
    expect(decidedIds).not.toContain('liar');
    expect(pendingIds).toContain('liar');
  });

  test('the rejection names the rule, not just the shape', () => {
    expect(warnings).toContain("assess() returned class 'unknown'");
    expect(warnings).toContain('abstain (return null) instead');
  });

  test('a lying probe is retired for the rest of the run', () => {
    // A probe that lies once has told us what it is. Leaving it live would let
    // it keep spending the run's warning budget.
    expect(warnings).toContain('skipped for the rest of this run');
  });
});

describe('probe contract · abstention is a first-class outcome', () => {
  test('`null` abstains cleanly — no verdict, no warning, no default class', () => {
    expect(decidedIds).not.toContain('abstain');
    expect(pendingIds).toContain('abstain');
    expect(warnings).not.toContain('abstain.v1.ts');
  });

  test('`undefined` is treated as abstention too, not as a malformed verdict', () => {
    expect(pendingIds).toContain('undef');
    expect(warnings).not.toContain('undef.v1.ts');
  });

  test('an abstaining probe is NOT retired — a lazy probe degrades to "ask"', () => {
    // This is what makes abstention safe to reach for: the probe stays live.
    expect(warnings).not.toContain("probe abstain v1: ");
  });
});

describe('probe contract · what a probe MAY assert', () => {
  test('the two legal non-anchored classes come through as probe-decided verdicts', () => {
    const good = out.decided.find((v) => v.nodeId === 'good');
    expect(good?.class).toBe('self_referential');
    expect(good?.decidedBy).toBe('probe');
    expect(good?.probeId).toBe('good');
    expect(good?.writeBoundary.argument.length).toBeGreaterThan(0);

    const nac = out.decided.find((v) => v.nodeId === 'notacheck');
    expect(nac?.class).toBe('not_a_check');
    expect(nac?.decidedBy).toBe('probe');
  });
});

describe('probe contract · a defective probe costs its node, never the run', () => {
  test('a malformed verdict is rejected and the node falls through to the agent', () => {
    expect(decidedIds).not.toContain('sloppy');
    expect(pendingIds).toContain('sloppy');
    expect(warnings).toContain('confidence outside 0..1');
  });

  test('a throwing assess() is caught, warned, and the probe retired', () => {
    expect(pendingIds).toContain('thrower');
    expect(warnings).toContain('assess() threw');
    expect(warnings).toContain('assess blew up');
  });

  test('a throwing match() is caught too — the filter runs probe code as well', () => {
    expect(pendingIds).toContain('matchthrower');
    expect(warnings).toContain('match() threw');
  });

  test('the run still produced a valid ClassifyOutput', () => {
    expect(Array.isArray(out.decided)).toBe(true);
    expect(Array.isArray(out.pending)).toBe(true);
    expect(Array.isArray(out.warnings)).toBe(true);
  });
});

describe('probe contract · nothing defaults to anchored', () => {
  test('every node is either decided or pending, exactly once', () => {
    expect([...decidedIds, ...pendingIds].sort()).toEqual(NODES.map((n) => n.id).sort());
    expect(new Set([...decidedIds, ...pendingIds]).size).toBe(NODES.length);
  });

  test('no probe in this run produced an `anchored` verdict', () => {
    // Two probes in the library would have asserted `anchored`: the malformed
    // one (rejected) and the one whose match() is false (never called). An
    // absent decision is an absence — it never becomes a cheap green.
    expect(out.decided.some((v) => v.class === 'anchored')).toBe(false);
  });

  test('a probe that matches nothing in this run decides nothing', () => {
    // `orphan` and `nevermatches` both loaded and both would have said
    // `anchored`; neither appears, because `match()` gates `assess()`.
    const gathered = new Set(NODES.map((n) => n.id));
    for (const id of decidedIds) expect(gathered.has(id)).toBe(true);
    expect(decidedIds).not.toContain('orphan');
    expect(decidedIds).not.toContain('nevermatches');
  });

  test('seed warnings from the caller survive into the output', () => {
    // The sandbox reports its own degradation through this channel; losing it
    // would turn "confinement was not enforced" into silence.
    return runSandbox(NODES_JSON, [PROBE_DIR], ['seeded: confinement not enforced']).then((r) => {
      expect(r.warnings[0]).toBe('seeded: confinement not enforced');
    });
  });
});

describe('probe contract · unused imports are load-bearing', () => {
  test('the legal verdict object is a real ProbeVerdict', () => {
    // Keeps `legal`/`illegal` referenced so the compile-time proof above is not
    // dropped as dead code by a future cleanup.
    expect(legal.class).toBe('self_referential');
    expect(illegal.writeBoundary.actorCanWrite).toBeNull();
  });
});
