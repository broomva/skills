/**
 * `classify` — the parent that dispatches probes and never trusts them.
 *
 * Its whole job is a set difference: a node with no VALID verdict is `pending`,
 * whatever the child said. Every failure mode here therefore has the same
 * correct outcome — "ask the agent" — and none of them may produce a class.
 *
 * The child is swapped for a fake via `--sandbox` in most tests. That is not a
 * mock of the thing under test: the parent's contract is "read a
 * ClassifyOutput off a child's stdout, hold a kill-timer on it, and revalidate
 * everything", and a scripted child is the only way to exercise the paths a
 * well-behaved child never takes. The real child is exercised end-to-end in the
 * last block, and on its own in `probe-sandbox.test.ts`.
 */

import { afterAll, describe, expect, test } from 'bun:test';
import { join } from 'node:path';
import type { ClassifyOutput, Node, Verdict } from '../schemas/keel.ts';
import { batchPending } from '../scripts/classify.ts';
import { cleanupTrees, run, tree } from './helpers/tree.ts';

afterAll(cleanupTrees);

const CLASSIFY = join(import.meta.dir, '..', 'scripts', 'classify.ts');

const NODES: Node[] = ['alpha', 'bravo', 'charlie'].map((n) => ({
  id: `synthetic#${n}`,
  kind: 'ci_step',
  name: n,
  source: `synthetic/${n}.yml:1`,
  raw: `- run: ${n}`,
}));

function verdict(nodeId: string, cls: Verdict['class'], over: Partial<Verdict> = {}): Verdict {
  return {
    nodeId,
    class: cls,
    writeBoundary: {
      producer: 'a scripted child',
      actorCanWrite: cls === 'anchored' ? false : cls === 'self_referential' ? true : null,
      argument: 'a synthetic verdict emitted by the classify test suite',
    },
    evidence: ['tests/classify.test.ts'],
    confidence: 0.9,
    decidedBy: 'probe',
    probeId: 'scripted',
    ...over,
  };
}

/** A child that prints exactly this ClassifyOutput and exits 0. */
function fakeSandbox(out: unknown): string {
  const dir = tree({
    'fake-sandbox.ts': `console.log(${JSON.stringify(JSON.stringify(out, null, 2))});\n`,
  });
  return join(dir, 'fake-sandbox.ts');
}

/** A child that does something else entirely. */
function scriptedSandbox(body: string): string {
  return join(tree({ 'fake-sandbox.ts': body }), 'fake-sandbox.ts');
}

const nodesFile = (nodes: unknown = NODES): string =>
  join(tree({ 'nodes.json': JSON.stringify(nodes, null, 2) }), 'nodes.json');

async function classifyJson(
  nodesPath: string,
  sandbox: string,
  extra: string[] = [],
): Promise<ClassifyOutput> {
  const { code, stdout } = await run([
    process.execPath,
    CLASSIFY,
    nodesPath,
    '--json',
    '--sandbox',
    sandbox,
    ...extra,
  ]);
  // A dead, hung or hostile probe library is a degraded run, not a failed one.
  expect(code).toBe(0);
  return JSON.parse(stdout) as ClassifyOutput;
}

describe('classify · the happy path', () => {
  test('a valid verdict is accepted and the rest stay pending', async () => {
    const out = await classifyJson(
      nodesFile(),
      fakeSandbox({
        decided: [verdict('synthetic#alpha', 'self_referential')],
        pending: NODES.slice(1),
        warnings: ['a warning from the child'],
      }),
    );
    expect(out.decided.map((v) => v.nodeId)).toEqual(['synthetic#alpha']);
    expect(out.pending.map((n) => n.id)).toEqual(['synthetic#bravo', 'synthetic#charlie']);
    expect(out.warnings).toContain('a warning from the child');
  });

  test('pending nodes arrive as FULL nodes, `raw` intact', async () => {
    // The agent judges over the literal text. A pending node stripped to an id
    // would force the judgment to be made from a summary.
    const out = await classifyJson(
      nodesFile(),
      fakeSandbox({ decided: [], pending: [], warnings: [] }),
    );
    expect(out.pending).toHaveLength(3);
    for (const n of out.pending) {
      expect(n.raw.length).toBeGreaterThan(0);
      expect(n.source.length).toBeGreaterThan(0);
    }
  });
});

describe('classify · the parent does not trust the child', () => {
  test('a verdict for a node that was not in the input is rejected', async () => {
    const out = await classifyJson(
      nodesFile(),
      fakeSandbox({
        decided: [verdict('synthetic#never-gathered', 'anchored')],
        pending: [],
        warnings: [],
      }),
    );
    expect(out.decided).toEqual([]);
    expect(out.pending).toHaveLength(3);
    expect(out.warnings.join('\n')).toContain('was not in the input');
    expect(out.warnings.join('\n')).toContain('falls through to agent judgment');
  });

  test('a probe asserting `unknown` is rejected by the parent as well as the child', async () => {
    // Belt and braces over the type-level exclusion: `unknown` is a claim about
    // the world and only the agent makes it.
    const out = await classifyJson(
      nodesFile(),
      fakeSandbox({
        decided: [verdict('synthetic#alpha', 'unknown')],
        pending: [],
        warnings: [],
      }),
    );
    expect(out.decided).toEqual([]);
    expect(out.pending.map((n) => n.id)).toContain('synthetic#alpha');
    expect(out.warnings.join('\n').toLowerCase()).toContain('unknown');
  });

  test('a duplicate verdict for one node is ignored, and said out loud', async () => {
    const out = await classifyJson(
      nodesFile(),
      fakeSandbox({
        decided: [
          verdict('synthetic#alpha', 'self_referential'),
          verdict('synthetic#alpha', 'anchored', { probeId: 'other' }),
        ],
        pending: [],
        warnings: [],
      }),
    );
    expect(out.decided).toHaveLength(1);
    expect(out.decided[0].class).toBe('self_referential');
    expect(out.warnings.join('\n')).toContain('duplicate verdict');
  });

  test('a structurally malformed verdict is rejected rather than repaired', async () => {
    const out = await classifyJson(
      nodesFile(),
      fakeSandbox({
        decided: [
          { nodeId: 'synthetic#alpha', class: 'anchored', confidence: 7, evidence: 'nope' },
        ],
        pending: [],
        warnings: [],
      }),
    );
    expect(out.decided).toEqual([]);
    expect(out.warnings.join('\n')).toContain('verdict rejected');
  });

  test("the child's pending list is recomputed, not believed", async () => {
    // A child that under-reports pending would silently shrink the denominator.
    const out = await classifyJson(
      nodesFile(),
      fakeSandbox({ decided: [], pending: [NODES[0]], warnings: [] }),
    );
    expect(out.pending).toHaveLength(3);
    expect(out.warnings.join('\n')).toContain("parent's set difference wins");
  });
});

describe('classify · a broken child degrades to "ask the agent"', () => {
  test('a missing sandbox script is a warning, not a crash', async () => {
    const out = await classifyJson(nodesFile(), '/nonexistent/probe-sandbox.ts');
    expect(out.decided).toEqual([]);
    expect(out.pending).toHaveLength(3);
    expect(out.warnings.join('\n')).toContain('probe sandbox not found');
  });

  test('a child that prints garbage yields no verdicts and a warning', async () => {
    const out = await classifyJson(
      nodesFile(),
      scriptedSandbox('console.log("this is not json at all");\n'),
    );
    expect(out.decided).toEqual([]);
    expect(out.pending).toHaveLength(3);
    expect(out.warnings.join('\n')).toContain('no parseable ClassifyOutput');
  });

  test('a child that exits non-zero yields no verdicts and a warning', async () => {
    const out = await classifyJson(
      nodesFile(),
      scriptedSandbox('console.error("child died");\nprocess.exit(3);\n'),
    );
    expect(out.decided).toEqual([]);
    expect(out.pending).toHaveLength(3);
    expect(out.warnings.join('\n')).toContain('exited 3');
  });

  test('a child whose output is not a ClassifyOutput is rejected', async () => {
    const out = await classifyJson(nodesFile(), fakeSandbox({ hello: 'world' }));
    expect(out.warnings.join('\n')).toContain('not a ClassifyOutput');
  });

  test('a HUNG child is killed by the wall-clock timer and the run survives', async () => {
    // The reason probe code may only run in a child: a synchronous loop cannot
    // be preempted in-process, so the only real timeout holds a process handle.
    // Bounded at 20s so a leaked orphan cannot outlive the suite.
    const started = Date.now();
    const out = await classifyJson(
      nodesFile(),
      scriptedSandbox('const t = Date.now();\nwhile (Date.now() - t < 20_000) {}\n'),
      ['--timeout-ms', '900'],
    );
    const elapsed = Date.now() - started;
    expect(out.decided).toEqual([]);
    expect(out.pending).toHaveLength(3);
    expect(out.warnings.join('\n')).toContain('wall-clock budget');
    // The timer must actually fire — not merely be configured.
    expect(elapsed).toBeLessThan(12_000);
  }, 20_000);
});

describe('classify · zero nodes is "nothing gathered"', () => {
  test('an empty input is never rendered as a clean bill of health', async () => {
    const { code, stdout } = await run([
      process.execPath,
      CLASSIFY,
      nodesFile([]),
      '--sandbox',
      '/nonexistent/probe-sandbox.ts',
    ]);
    expect(code).toBe(0);
    expect(stdout).toContain('nothing gathered');
    expect(stdout).toContain('not a passing result');
  });

  test('no child is spawned for an empty input', async () => {
    // Spawning a process to say "nothing to do" would be theatre — and it would
    // charge the crystallization curve for work that never happened.
    const out = await classifyJson(
      nodesFile([]),
      scriptedSandbox('process.exit(9);\n'),
    );
    expect(out.warnings).toEqual([]);
    expect(out.decided).toEqual([]);
    expect(out.pending).toEqual([]);
  });
});

describe('classify · batching is a caller concern', () => {
  test('batchPending groups without losing or reordering a node', () => {
    const many = Array.from({ length: 47 }, (_, i) => ({ ...NODES[0], id: `n${i}` }));
    const batches = batchPending(many, 15);
    expect(batches.map((b) => b.length)).toEqual([15, 15, 15, 2]);
    expect(batches.flat().map((n) => n.id)).toEqual(many.map((n) => n.id));
  });

  test('an empty pending list produces no batches, not one empty batch', () => {
    expect(batchPending([], 10)).toEqual([]);
  });

  test('a nonsense batch size cannot produce a zero-length stride', () => {
    expect(batchPending([NODES[0], NODES[1]], 0).flat()).toHaveLength(2);
    expect(batchPending([NODES[0], NODES[1]], -5)).toHaveLength(2);
  });

  test('--batches prints the same grouping the human summary claims', async () => {
    const { stdout } = await run([
      process.execPath,
      CLASSIFY,
      nodesFile(),
      '--batches',
      '--batch-size',
      '2',
      '--sandbox',
      '/nonexistent/probe-sandbox.ts',
    ]);
    const printed = JSON.parse(stdout) as Node[][];
    expect(printed.map((b) => b.length)).toEqual([2, 1]);
    expect(printed.flat().map((n) => n.id)).toEqual(NODES.map((n) => n.id));
  });
});

describe('classify · end to end against the real sandbox child', () => {
  test('a real probe in a real child decides a real node', async () => {
    const probeDir = tree({
      'e2e.v1.ts': `const probe = {
  id: 'e2e', version: 1, mintedAt: '2026-07-24T00:00:00.000Z',
  mintedFrom: 'synthetic#test', description: 'decides one synthetic node end to end',
  match(node) { return node.id === 'synthetic#alpha'; },
  assess(node) {
    return { class: 'self_referential',
      writeBoundary: { producer: 'the test suite', actorCanWrite: true,
        argument: 'an end-to-end synthetic verdict through the real sandbox child' },
      evidence: [node.source], confidence: 0.7 };
  },
};
export default probe;
`,
    });
    const { code, stdout } = await run([
      process.execPath,
      CLASSIFY,
      nodesFile(),
      '--json',
      '--probe-dir',
      probeDir,
    ]);
    expect(code).toBe(0);
    const out = JSON.parse(stdout) as ClassifyOutput;
    expect(out.decided).toHaveLength(1);
    expect(out.decided[0].nodeId).toBe('synthetic#alpha');
    expect(out.decided[0].decidedBy).toBe('probe');
    expect(out.decided[0].probeId).toBe('e2e');
    expect(out.pending.map((n) => n.id)).toEqual(['synthetic#bravo', 'synthetic#charlie']);
  }, 15_000);

  test('--probe-dir REPLACES the defaults, so a run can be isolated from $HOME', async () => {
    // Fan-out isolation depends on this: an append-only flag could never exclude
    // a user's home probe library from a measured run.
    const { stdout } = await run([
      process.execPath,
      CLASSIFY,
      nodesFile(),
      '--json',
      '--probe-dir',
      tree({}),
    ]);
    const out = JSON.parse(stdout) as ClassifyOutput;
    expect(out.decided).toEqual([]);
    expect(out.pending).toHaveLength(3);
  }, 15_000);
});

describe('classify · argument errors are loud', () => {
  test('an unknown flag exits 1 with usage', async () => {
    const { code, stderr } = await run([process.execPath, CLASSIFY, nodesFile(), '--nope']);
    expect(code).toBe(1);
    expect(stderr).toContain('unknown flag');
    expect(stderr).toContain('usage:');
  });

  test('a missing nodes file exits 1 rather than classifying nothing', async () => {
    const { code, stderr } = await run([process.execPath, CLASSIFY, '/nonexistent/nodes.json']);
    expect(code).toBe(1);
    expect(stderr.length).toBeGreaterThan(0);
  });
});
