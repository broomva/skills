/**
 * `assemble` — the merge that refuses.
 *
 * The tool has exactly two jobs and this suite is split along them: produce a
 * Report that the downstream consumers and CI's own recompute gate accept, and
 * REFUSE every input shape that would produce a plausible number over the wrong
 * world. The refusals carry most of the weight — a merge that succeeds is easy
 * to eyeball, whereas a silently dropped node is invisible in the artifact and
 * shows up only as a ratio nobody can reproduce.
 *
 * Everything runs the real CLI in a child process and asserts on its exit code
 * and its stderr. The exit code is the product here: assemble is meant to be
 * called from a run script, so "refuses" means "exits non-zero", not "returns a
 * value some caller may ignore". `groundingRatio` is re-imported from the
 * frozen schema and recomputed over the written file — the same check
 * `.github/workflows/test.yml` runs against the committed fixture, applied to
 * this tool's output.
 */

import { afterAll, describe, expect, test } from 'bun:test';
import { readdirSync } from 'node:fs';
import { join } from 'node:path';
import type { Node, Report, Verdict } from '../schemas/keel.ts';
import { groundingRatio } from '../schemas/keel.ts';
import { cleanupTrees, run, tree } from './helpers/tree.ts';

afterAll(cleanupTrees);

const ASSEMBLE = join(import.meta.dir, '..', 'scripts', 'assemble.ts');

const NODES: Node[] = [
  { id: 'Makefile#test', kind: 'script', name: 'test', source: 'Makefile:10', raw: 'test:\n\tbun test' },
  { id: 'Makefile#help', kind: 'script', name: 'help', source: 'Makefile:14', raw: 'help:\n\t@grep -hE' },
  {
    id: '.github/workflows/ci.yml#4-bun-test',
    kind: 'ci_step',
    name: 'bun test',
    source: '.github/workflows/ci.yml:4',
    raw: '- run: bun test',
  },
];

function verdict(nodeId: string, cls: Verdict['class'], over: Partial<Verdict> = {}): Verdict {
  return {
    nodeId,
    class: cls,
    writeBoundary: {
      producer: 'the bun test process exit code',
      actorCanWrite: cls === 'anchored' ? false : cls === 'unknown' ? null : true,
      argument:
        'the runtime executes the assertions and the exit code is what the job reads; the author cannot write that byte without changing what the code does',
    },
    evidence: ['tests/assemble.test.ts:1'],
    confidence: 0.9,
    decidedBy: 'agent',
    ...over,
  };
}

const VERDICTS: Verdict[] = [
  verdict('Makefile#test', 'anchored'),
  verdict('Makefile#help', 'not_a_check'),
  verdict('.github/workflows/ci.yml#4-bun-test', 'self_referential', { decidedBy: 'probe' }),
];

/** Materialize a set of JSON files and return a path resolver into that dir. */
function files(entries: Record<string, unknown>): (name: string) => string {
  const dir = tree(
    Object.fromEntries(
      Object.entries(entries).map(([name, value]) => [name, JSON.stringify(value, null, 2)]),
    ),
  );
  return (name: string) => join(dir, name);
}

async function assemble(args: string[]) {
  return run([process.execPath, ASSEMBLE, ...args]);
}

describe('assemble · the happy path', () => {
  test('nodes + verdicts round-trip into a Report whose grounding recomputes', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const out = at('report.json');

    const { code, stderr } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--target',
      'keel',
      '--revision',
      'ad47c37008cd1f3d12430ff1a45e943d84913f32',
      '-o',
      out,
    ]);
    expect(code).toBe(0);
    expect(stderr).toContain(`wrote ${out}`);

    const report = (await Bun.file(out).json()) as Report;
    expect(report.target).toBe('keel');
    expect(report.revision).toBe('ad47c37008cd1f3d12430ff1a45e943d84913f32');
    expect(report.nodes).toHaveLength(3);
    expect(report.verdicts).toHaveLength(3);
    expect(Date.parse(report.generatedAt)).toBeGreaterThan(0);

    // The gate `.github/workflows/test.yml` runs against the committed fixture,
    // run here against this tool's output: stored grounding must equal a
    // recomputation, and no verdict may travel without its causal path.
    expect(report.grounding).toEqual(groundingRatio(report.verdicts));
    expect(report.verdicts.filter((v) => !v.writeBoundary?.argument?.trim())).toHaveLength(0);

    // 1 anchored / (1 anchored + 1 self_referential + 0 unknown); not_a_check
    // is excluded from the denominator, and reported beside it.
    expect(report.grounding).toEqual({
      anchored: 1,
      selfReferential: 1,
      unknown: 0,
      notACheck: 1,
      ratio: 0.5,
    });
  });

  test('the committed fixture round-trips: same grounding, same order', async () => {
    // The strongest check here, because the oracle was not authored by this
    // test: `tests/fixtures/report.sample.json` is the output of a real
    // 15-verdict run over this repo, and it is the contract every consumer
    // reads. Split it back into its inputs, re-assemble, and the grounding
    // block must come out identical — if it does not, either the fixture or
    // this tool is wrong, and both matter.
    const fixture = (await Bun.file(
      join(import.meta.dir, 'fixtures', 'report.sample.json'),
    ).json()) as Report;
    const at = files({ 'nodes.json': fixture.nodes, 'verdicts.json': fixture.verdicts });
    const out = at('report.json');

    const { code } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--target',
      fixture.target,
      '--revision',
      fixture.revision,
      '-o',
      out,
    ]);
    expect(code).toBe(0);

    const report = (await Bun.file(out).json()) as Report & { warnings?: string[] };
    expect(report.grounding).toEqual(fixture.grounding);
    expect(report.verdicts.map((v) => v.nodeId)).toEqual(fixture.verdicts.map((v) => v.nodeId));
    expect(report.economics.decidedByAgent).toBe(fixture.economics.decidedByAgent);
    // Not one verdict in a real run contradicts its own write boundary.
    expect(report.warnings).toBeUndefined();
  });

  test('the grounding block is computed, never taken from the input', async () => {
    // A caller hands us a ratio of 1.0 alongside verdicts that do not support
    // it. A number the measured thing can write to is not a measurement.
    const at = files({
      'nodes.json': NODES,
      'verdicts.json': VERDICTS,
      'liar.json': {
        target: 'keel',
        grounding: { anchored: 3, selfReferential: 0, unknown: 0, notACheck: 0, ratio: 1 },
        decided: VERDICTS,
      },
    });
    const out = at('report.json');
    const { code } = await assemble([at('nodes.json'), at('liar.json'), '-o', out]);
    expect(code).toBe(0);

    const report = (await Bun.file(out).json()) as Report;
    expect(report.grounding.ratio).toBe(0.5);
    expect(report.grounding.anchored).toBe(1);
  });

  test('economics are counted from decidedBy, and token counts stay zero', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const out = at('report.json');
    const { code, stdout } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '-o',
      out,
      '--json',
    ]);
    expect(code).toBe(0);

    const summary = JSON.parse(stdout) as { economics: Report['economics'] };
    expect(summary.economics).toEqual({
      nodesTotal: 3,
      nodesSampled: 3,
      decidedByProbe: 1,
      decidedByAgent: 2,
      probesMinted: 0,
      probeLibrarySize: 0,
      tokensIn: 0,
      tokensOut: 0,
      tokensEstimated: true,
      wallClockMs: 0,
    });
  });

  test('--probes counts DISTINCT probe ids, not files, across every dir given', async () => {
    // The number the crystallization curve is plotted against. Probe files are
    // `<id>.v<n>.ts` and the loader takes the highest version per id, so
    // counting files would show a library growing every time one probe is
    // revised. Six files here; four distinct ids; one of them lives in both
    // dirs and must not be counted twice.
    const probesA = tree({
      'llm-review-gate.v1.ts': 'export const probe = 1;\n',
      'llm-review-gate.v2.ts': 'export const probe = 2;\n',
      'coverage-threshold.v1.ts': 'export const probe = 3;\n',
      'unversioned.ts': 'export const probe = 4;\n',
      'types.d.ts': 'declare const x: number;\n',
      'README.md': 'not a probe\n',
    });
    const probesB = tree({
      'llm-review-gate.v3.ts': 'export const probe = 5;\n',
      'deploy-gate.v1.ts': 'export const probe = 6;\n',
    });

    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const out = at('report.json');
    const { code } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--probes',
      probesA,
      '--probes',
      probesB,
      '-o',
      out,
    ]);
    expect(code).toBe(0);

    const report = (await Bun.file(out).json()) as Report;
    expect(report.economics.probeLibrarySize).toBe(4);
    // Minted is a delta across a run this process did not watch. It stays 0.
    expect(report.economics.probesMinted).toBe(0);
  });

  test("--probes over Keel's own probe directory reports the library that is there", async () => {
    // The report Keel publishes about itself is regenerated through this tool.
    // The count has to come from the directory, because a hardcoded zero makes
    // the committed artifact assert something false about the shipped library.
    const probeDir = join(import.meta.dir, '..', 'probes');
    const shipped = new Set(
      readdirSync(probeDir)
        .filter((f) => f.endsWith('.ts') && !f.endsWith('.d.ts'))
        .map((f) => f.match(/^(.*)\.v\d+\.ts$/)?.[1] ?? f.slice(0, -3)),
    );
    expect(shipped.size).toBeGreaterThan(0); // else this test proves nothing

    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const out = at('report.json');
    const { code } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--probes',
      probeDir,
      '-o',
      out,
    ]);
    expect(code).toBe(0);
    const report = (await Bun.file(out).json()) as Report;
    expect(report.economics.probeLibrarySize).toBe(shipped.size);
  });

  test('--probe-library-size states the count when the dirs are not reachable', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const out = at('report.json');
    const { code } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--probe-library-size',
      '7',
      '-o',
      out,
    ]);
    expect(code).toBe(0);
    const report = (await Bun.file(out).json()) as Report;
    expect(report.economics.probeLibrarySize).toBe(7);
  });

  test('an unreadable --probes dir refuses rather than counting it as zero', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const out = at('report.json');
    const { code, stderr } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--probes',
      join(at('nodes.json'), '..', 'no-such-probe-dir'),
      '-o',
      out,
    ]);
    expect(code).toBe(1);
    expect(stderr).toContain('cannot read it');
    expect(stderr).toContain('understate the library');
    expect(await Bun.file(out).exists()).toBe(false);
  });

  test('--probes together with --probe-library-size refuses instead of picking one', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const { code, stderr } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--probes',
      tree({ 'a.v1.ts': 'export const probe = 1;\n' }),
      '--probe-library-size',
      '9',
    ]);
    expect(code).toBe(1);
    expect(stderr).toContain('they answer the same question');
  });

  test('a non-integer --probe-library-size refuses rather than coercing', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const { code, stderr } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--probe-library-size',
      '3.5',
    ]);
    expect(code).toBe(1);
    expect(stderr).toContain('must be a non-negative integer');
  });

  test('verdicts are ordered by the node file, not by the order they arrived', async () => {
    // Reports get committed and diffed. Two runs over the same judgments must
    // produce the same bytes whichever file was passed first.
    const at = files({
      'nodes.json': NODES,
      'a.json': [VERDICTS[2]],
      'b.json': [VERDICTS[0], VERDICTS[1]],
    });
    const out = at('report.json');
    const { code } = await assemble([at('nodes.json'), at('a.json'), at('b.json'), '-o', out]);
    expect(code).toBe(0);

    const report = (await Bun.file(out).json()) as Report;
    expect(report.verdicts.map((v) => v.nodeId)).toEqual(NODES.map((n) => n.id));
  });

  test('warnings from a ClassifyOutput travel into the report', async () => {
    const at = files({
      'nodes.json': NODES,
      'verdicts.json': VERDICTS,
      'classify.json': {
        decided: [],
        pending: [],
        warnings: ['probe dir /nope is unreadable — 0 probes loaded'],
      },
    });
    const out = at('report.json');
    const { code, stderr } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--warnings',
      at('classify.json'),
      '--revision',
      'deadbee',
      '-o',
      out,
    ]);
    expect(code).toBe(0);
    expect(stderr).toContain('probe dir /nope is unreadable');

    const report = (await Bun.file(out).json()) as Report & { warnings?: string[] };
    expect(report.warnings).toContain('probe dir /nope is unreadable — 0 probes loaded');
  });

  test('a ClassifyOutput passed as a verdicts file carries its own warnings', async () => {
    // The ordinary invocation: classify --json IS the verdicts file. Its
    // warnings say how much of that run's machinery ran, and requiring the same
    // path to be repeated as --warnings to keep them made the report quieter
    // than its run by default.
    const at = files({
      'nodes.json': NODES,
      'classify.json': {
        decided: VERDICTS,
        pending: [],
        warnings: ['probe `example-llm-review-gate` was skipped — sandbox child died'],
      },
    });
    const out = at('report.json');
    const { code, stderr } = await assemble([
      at('nodes.json'),
      at('classify.json'),
      '--revision',
      'deadbee',
      '-o',
      out,
    ]);
    expect(code).toBe(0);
    expect(stderr).toContain('sandbox child died');

    const report = (await Bun.file(out).json()) as Report & { warnings?: string[] };
    expect(report.warnings).toEqual([
      'probe `example-llm-review-gate` was skipped — sandbox child died',
    ]);
  });

  test('the same ClassifyOutput as verdicts AND --warnings does not double its warnings', async () => {
    const at = files({
      'nodes.json': NODES,
      'classify.json': {
        decided: VERDICTS,
        pending: [],
        warnings: ['probe dir /nope is unreadable — 0 probes loaded'],
      },
    });
    const out = at('report.json');
    const { code } = await assemble([
      at('nodes.json'),
      at('classify.json'),
      '--warnings',
      at('classify.json'),
      '--revision',
      'deadbee',
      '-o',
      out,
    ]);
    expect(code).toBe(0);
    const report = (await Bun.file(out).json()) as Report & { warnings?: string[] };
    expect(report.warnings).toHaveLength(1);
  });

  test('a clean run carries no warnings key at all', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const out = at('report.json');
    const { code } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--revision',
      'deadbee',
      '-o',
      out,
    ]);
    expect(code).toBe(0);
    const report = (await Bun.file(out).json()) as Record<string, unknown>;
    expect(Object.keys(report)).toEqual([
      'target',
      'revision',
      'generatedAt',
      'nodes',
      'verdicts',
      'grounding',
      'economics',
    ]);
  });

  test('--dir with no --revision names the target and reads the sha from git', async () => {
    // The repo itself: assemble is being asked what it is measuring, and the
    // answer has to come from the checkout rather than from a flag someone may
    // forget to update.
    const repo = join(import.meta.dir, '..');
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const out = at('report.json');
    const { code } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--dir',
      repo,
      '-o',
      out,
    ]);
    expect(code).toBe(0);

    const report = (await Bun.file(out).json()) as Report;
    expect(report.target).toBe('keel');
    expect(report.revision).toMatch(/^[0-9a-f]{40}$/);
  });

  test('no revision anywhere is recorded as "unknown" and said out loud', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const out = at('report.json');
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json'), '-o', out]);
    expect(code).toBe(0);
    expect(stderr).toContain('revision "unknown"');

    const report = (await Bun.file(out).json()) as Report & { warnings?: string[] };
    expect(report.revision).toBe('unknown');
    expect(report.warnings?.join(' ')).toContain('cannot be compared against a later run');
  });
});

describe('assemble · refusals', () => {
  test('a node with no verdict refuses, names the id, and writes nothing', async () => {
    const at = files({ 'nodes.json': NODES, 'partial.json': [VERDICTS[0]] });
    const out = at('report.json');
    const { code, stderr } = await assemble([at('nodes.json'), at('partial.json'), '-o', out]);
    expect(code).toBe(1);
    expect(stderr).toContain('2 node(s) have no verdict');
    expect(stderr).toContain('`Makefile#help`');
    expect(stderr).toContain('`.github/workflows/ci.yml#4-bun-test`');
    // A refusal that still wrote the file would be worse than no refusal: the
    // next stage reads the file, not the exit code.
    expect(await Bun.file(out).exists()).toBe(false);
  });

  test('the missing-id list is capped and says how many more', async () => {
    const many: Node[] = Array.from({ length: 30 }, (_, i) => ({
      id: `synthetic#n${i}`,
      kind: 'ci_step',
      name: `n${i}`,
      source: `synthetic.yml:${i}`,
      raw: `- run: n${i}`,
    }));
    const at = files({ 'nodes.json': many, 'verdicts.json': [] });
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json')]);
    expect(code).toBe(1);
    expect(stderr).toContain('30 node(s) have no verdict');
    expect(stderr).toContain('…and 22 more');
  });

  test('--gathered turns a judged sample into a visible cap instead of a refusal', async () => {
    const at = files({
      'gathered.json': NODES,
      'sample.json': NODES.slice(0, 2),
      'verdicts.json': VERDICTS.slice(0, 2),
    });
    const out = at('report.json');
    const { code } = await assemble([
      at('sample.json'),
      at('verdicts.json'),
      '--gathered',
      at('gathered.json'),
      '-o',
      out,
    ]);
    expect(code).toBe(0);

    const report = (await Bun.file(out).json()) as Report;
    expect(report.economics.nodesSampled).toBe(2);
    expect(report.economics.nodesTotal).toBe(3);
  });

  test('a sample larger than the gather it claims to come from refuses', async () => {
    const at = files({
      'gathered.json': NODES.slice(0, 1),
      'nodes.json': NODES,
      'verdicts.json': VERDICTS,
    });
    const { code, stderr } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--gathered',
      at('gathered.json'),
    ]);
    expect(code).toBe(1);
    expect(stderr).toContain('not a subset of the gather it claims to come from');
  });

  test('a same-sized sample drawn from a different gather refuses', async () => {
    // The cardinality test this replaced accepted this file pair: three judged,
    // three gathered, not one id in common. The report would have named one
    // gather while describing another, and nodesTotal would have looked right.
    const other: Node[] = NODES.map((n) => ({ ...n, id: `elsewhere${n.id}` }));
    const at = files({
      'gathered.json': other,
      'nodes.json': NODES,
      'verdicts.json': VERDICTS,
    });
    const out = at('report.json');
    const { code, stderr } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--gathered',
      at('gathered.json'),
      '-o',
      out,
    ]);
    expect(code).toBe(1);
    expect(stderr).toContain('not a subset of the gather it claims to come from');
    expect(stderr).toContain('`Makefile#test`');
    expect(await Bun.file(out).exists()).toBe(false);
  });

  test('zero gathered nodes refuses — "nothing gathered" is a state, never ratio 0', async () => {
    // groundingRatio([]) is ratio 0, which reads as "nothing here is anchored"
    // when the truth is "nothing was measured". SKILL.md § Output requires the
    // explicit state; corpus.ts implements it by writing no report at all.
    const at = files({ 'nodes.json': [], 'verdicts.json': [] });
    const out = at('report.json');
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json'), '-o', out]);
    expect(code).toBe(1);
    expect(stderr).toContain('nothing gathered');
    expect(await Bun.file(out).exists()).toBe(false);
  });

  test('zero judged out of a non-empty gather refuses as "nothing judged"', async () => {
    const at = files({ 'gathered.json': NODES, 'sample.json': [], 'verdicts.json': [] });
    const { code, stderr } = await assemble([
      at('sample.json'),
      at('verdicts.json'),
      '--gathered',
      at('gathered.json'),
    ]);
    expect(code).toBe(1);
    expect(stderr).toContain('nothing judged');
  });

  test('a verdict for an id that is not in the node file refuses and names it', async () => {
    const at = files({
      'nodes.json': NODES,
      'verdicts.json': [...VERDICTS, verdict('Makefile#typo', 'anchored')],
    });
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json')]);
    expect(code).toBe(1);
    expect(stderr).toContain('not in the node file');
    expect(stderr).toContain('`Makefile#typo`');
  });

  test('two verdicts for one node refuse and name both classes', async () => {
    const at = files({
      'probe.json': { decided: [verdict('Makefile#test', 'anchored')], pending: [], warnings: [] },
      'nodes.json': NODES,
      'agent.json': [
        verdict('Makefile#test', 'self_referential'),
        VERDICTS[1],
        VERDICTS[2],
      ],
    });
    const { code, stderr } = await assemble([
      at('nodes.json'),
      at('probe.json'),
      at('agent.json'),
    ]);
    expect(code).toBe(1);
    expect(stderr).toContain('`Makefile#test` has two verdicts');
    expect(stderr).toContain('anchored');
    expect(stderr).toContain('self_referential');
  });

  test('an empty writeBoundary.argument refuses — a class with no causal path', async () => {
    const naked = verdict('Makefile#help', 'not_a_check');
    naked.writeBoundary.argument = '   ';
    const at = files({
      'nodes.json': NODES,
      'verdicts.json': [VERDICTS[0], naked, VERDICTS[2]],
    });
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json')]);
    expect(code).toBe(1);
    expect(stderr).toContain('`writeBoundary.argument` is empty');
    expect(stderr).toContain('Makefile#help');
  });

  test('an empty writeBoundary.producer refuses — nothing is named as emitting the signal', async () => {
    // `actorCanWrite` is a claim ABOUT the producer. With no producer named,
    // the boolean is unreviewable: there is nothing to check the actor against.
    const nameless = verdict('Makefile#test', 'anchored');
    nameless.writeBoundary.producer = '  ';
    const at = files({
      'nodes.json': NODES,
      'verdicts.json': [nameless, VERDICTS[1], VERDICTS[2]],
    });
    const out = at('report.json');
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json'), '-o', out]);
    expect(code).toBe(1);
    expect(stderr).toContain('`writeBoundary.producer` is empty');
    expect(stderr).toContain('Makefile#test');
    expect(await Bun.file(out).exists()).toBe(false);
  });

  test('a non-boolean writeBoundary.actorCanWrite refuses', async () => {
    // "maybe" is not one of the three answers. null already MEANS "could not
    // establish the fork point"; a string smuggles a fourth state past every
    // consumer that switches on the three.
    const at = files({
      'nodes.json': NODES,
      'verdicts.json': [
        {
          ...VERDICTS[0],
          writeBoundary: { ...VERDICTS[0].writeBoundary, actorCanWrite: 'maybe' },
        },
        VERDICTS[1],
        VERDICTS[2],
      ],
    });
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json')]);
    expect(code).toBe(1);
    expect(stderr).toContain('`writeBoundary.actorCanWrite` must be true, false or null');
  });

  test('evidence that is not a string[] refuses — missing, and with a non-string in it', async () => {
    const missing = files({
      'nodes.json': NODES,
      'verdicts.json': [
        { ...VERDICTS[0], evidence: undefined },
        VERDICTS[1],
        VERDICTS[2],
      ],
    });
    const a = await assemble([missing('nodes.json'), missing('verdicts.json')]);
    expect(a.code).toBe(1);
    expect(a.stderr).toContain('`evidence` must be a string[] of citations');

    // A citation that is not a string cites nothing a reviewer can open.
    const wrong = files({
      'nodes.json': NODES,
      'verdicts.json': [
        { ...VERDICTS[0], evidence: ['Makefile:10', { file: 'Makefile', line: 10 }] },
        VERDICTS[1],
        VERDICTS[2],
      ],
    });
    const b = await assemble([wrong('nodes.json'), wrong('verdicts.json')]);
    expect(b.code).toBe(1);
    expect(b.stderr).toContain('`evidence` must be a string[] of citations');
  });

  test('a confidence outside 0..1 refuses, and so does one that is not a number', async () => {
    // route.ts ranks by confidence and render.ts rings anchored verdicts below
    // 0.5; both default a missing number to 0. Refusing here is the last place
    // the difference between "unstated" and "lowest possible" is still visible.
    const high = files({
      'nodes.json': NODES,
      'verdicts.json': [{ ...VERDICTS[0], confidence: 1.5 }, VERDICTS[1], VERDICTS[2]],
    });
    const a = await assemble([high('nodes.json'), high('verdicts.json')]);
    expect(a.code).toBe(1);
    expect(a.stderr).toContain('`confidence` is 1.5 — must be in 0..1');

    const negative = files({
      'nodes.json': NODES,
      'verdicts.json': [{ ...VERDICTS[0], confidence: -0.2 }, VERDICTS[1], VERDICTS[2]],
    });
    const b = await assemble([negative('nodes.json'), negative('verdicts.json')]);
    expect(b.code).toBe(1);
    expect(b.stderr).toContain('`confidence` is -0.2 — must be in 0..1');

    const absent = files({
      'nodes.json': NODES,
      'verdicts.json': [{ ...VERDICTS[0], confidence: undefined }, VERDICTS[1], VERDICTS[2]],
    });
    const c = await assemble([absent('nodes.json'), absent('verdicts.json')]);
    expect(c.code).toBe(1);
    expect(c.stderr).toContain('`confidence` must be a number in 0..1');

    // 0 and 1 are legal — the bound is inclusive, and a test that only proved
    // rejection would not notice the check swallowing the honest extremes.
    const edges = files({
      'nodes.json': NODES,
      'verdicts.json': [
        { ...VERDICTS[0], confidence: 0 },
        { ...VERDICTS[1], confidence: 1 },
        VERDICTS[2],
      ],
    });
    const ok = await assemble([edges('nodes.json'), edges('verdicts.json')]);
    expect(ok.code).toBe(0);
  });

  test('an illegal class refuses and lists the four legal ones', async () => {
    const at = files({
      'nodes.json': NODES,
      'verdicts.json': [
        { ...VERDICTS[0], class: 'grounded' },
        VERDICTS[1],
        VERDICTS[2],
      ],
    });
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json')]);
    expect(code).toBe(1);
    expect(stderr).toContain('`class` is "grounded"');
    expect(stderr).toContain('anchored, self_referential, unknown, not_a_check');
  });

  test('an illegal decidedBy refuses — the economics are counted from it', async () => {
    const at = files({
      'nodes.json': NODES,
      'verdicts.json': [
        { ...VERDICTS[0], decidedBy: 'vibes' },
        VERDICTS[1],
        VERDICTS[2],
      ],
    });
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json')]);
    expect(code).toBe(1);
    expect(stderr).toContain("must be 'probe' or 'agent'");
  });

  test('every problem is reported in one run, not one per invocation', async () => {
    const at = files({
      'nodes.json': NODES,
      'verdicts.json': [
        { ...VERDICTS[0], class: 'grounded' },
        { ...VERDICTS[1], confidence: 7 },
        { ...VERDICTS[2], decidedBy: 'vibes' },
      ],
    });
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json')]);
    expect(code).toBe(1);
    expect(stderr).toContain('3 problem(s)');
    expect(stderr).toContain('`class` is "grounded"');
    expect(stderr).toContain('`confidence` is 7');
    expect(stderr).toContain("must be 'probe' or 'agent'");
  });

  test('duplicate node ids refuse before anything is judged against them', async () => {
    const at = files({
      'nodes.json': [...NODES, NODES[0]],
      'verdicts.json': VERDICTS,
    });
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json')]);
    expect(code).toBe(1);
    expect(stderr).toContain('duplicate node id(s)');
    expect(stderr).toContain('`Makefile#test`');
  });

  test('a class contradicting its own actorCanWrite warns but does not refuse', async () => {
    // The two halves of the verdict disagree. The reviewer decides which half is
    // wrong; the assembler is not entitled to discard a night of judgments over
    // it — but it may not stay quiet either.
    const contradictory = verdict('Makefile#test', 'anchored');
    contradictory.writeBoundary.actorCanWrite = true;
    const at = files({
      'nodes.json': NODES,
      'verdicts.json': [contradictory, VERDICTS[1], VERDICTS[2]],
    });
    const out = at('report.json');
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json'), '-o', out]);
    expect(code).toBe(0);
    expect(stderr).toContain('is anchored but writeBoundary.actorCanWrite is true');

    const report = (await Bun.file(out).json()) as Report & { warnings?: string[] };
    expect(report.warnings?.join(' ')).toContain('one of the two is wrong');
    // The class is what the ratio was computed from, and it stayed that way.
    expect(report.grounding.anchored).toBe(1);
  });
});

describe('assemble · bad invocations', () => {
  test('no arguments prints usage and exits 1', async () => {
    const { code, stdout } = await assemble([]);
    expect(code).toBe(1);
    expect(stdout).toContain('usage: bun scripts/assemble.ts');
  });

  test('--help exits 0', async () => {
    const { code, stdout } = await assemble(['--help']);
    expect(code).toBe(0);
    expect(stdout).toContain('It classifies nothing');
  });

  test('a missing <verdicts.json> is an error, not an empty merge', async () => {
    const at = files({ 'nodes.json': NODES });
    const { code, stderr } = await assemble([at('nodes.json')]);
    expect(code).toBe(1);
    expect(stderr).toContain('missing <verdicts.json>');
  });

  test('a flag with no value refuses instead of defaulting', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const { code, stderr } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '--revision',
      '-o',
      at('report.json'),
    ]);
    expect(code).toBe(1);
    expect(stderr).toContain('--revision requires a value');
  });

  test('--json without -o refuses rather than putting two JSON docs on stdout', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json'), '--json']);
    expect(code).toBe(1);
    expect(stderr).toContain('two JSON documents on stdout');
  });

  test('a verdicts file that is neither a Verdict[] nor a ClassifyOutput refuses', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': { pending: [] } });
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json')]);
    expect(code).toBe(1);
    expect(stderr).toContain('must contain a Verdict[] array');
  });

  test('a missing file names the file', async () => {
    const at = files({ 'verdicts.json': VERDICTS });
    const { code, stderr } = await assemble([at('nope.json'), at('verdicts.json')]);
    expect(code).toBe(1);
    expect(stderr).toContain('cannot read');
    expect(stderr).toContain('nope.json');
  });

  test('-o pointed at a directory says so instead of raising EISDIR from inside', async () => {
    // `-o build/` is the natural typo, and the unguarded failure is a stack
    // trace out of writeFileSync that reads like a crash in the tool.
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const dir = tree({ 'keep.txt': 'a directory, not a file\n' });
    const { code, stderr } = await assemble([
      at('nodes.json'),
      at('verdicts.json'),
      '-o',
      dir,
    ]);
    expect(code).toBe(1);
    expect(stderr).toContain('is a directory');
    expect(stderr).toContain('report.json');
    // The actionable message, not a stack.
    expect(stderr).not.toContain('EISDIR');
    expect(stderr).not.toContain('at <anonymous>');
  });

  test('an unwritable -o path reports the path instead of throwing', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    // A file where a parent directory has to be: mkdirSync cannot create it.
    const blocked = join(at('nodes.json'), 'sub', 'report.json');
    const { code, stderr } = await assemble([at('nodes.json'), at('verdicts.json'), '-o', blocked]);
    expect(code).toBe(1);
    expect(stderr).toContain('cannot write');
    expect(stderr).toContain(blocked);
  });

  test('with no -o the report goes to stdout and stays parseable', async () => {
    const at = files({ 'nodes.json': NODES, 'verdicts.json': VERDICTS });
    const { code, stdout } = await assemble([at('nodes.json'), at('verdicts.json')]);
    expect(code).toBe(0);
    const report = JSON.parse(stdout) as Report;
    expect(report.grounding).toEqual(groundingRatio(report.verdicts));
  });
});
