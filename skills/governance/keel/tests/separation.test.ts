/**
 * THE SEPARATION TEST.
 *
 * One edge in Keel must stay open, and this file is the executed proof that it
 * is: the router receives *verdicts* — what is ungrounded and why — and never
 * the *ratio as an objective*. The moment the score becomes something to
 * optimize it becomes a selection signal, and the number dies while still
 * rising.
 *
 * Directory layout asserts nothing about that. Two files in one skill can have
 * a strictly one-way dependency and two separate packages can have a feedback
 * loop, so a test that checked for the absence of an import would be checking
 * paperwork. This checks behaviour instead:
 *
 *   measure a target → fabricate an adversarial bindings file claiming every
 *   check is routable, anchored, and already applied → measure the SAME target
 *   again → assert the verdicts and the grounding ratio are identical.
 *
 * Both measurements run the real path — `gather()` walks real files on disk,
 * `classify()` spawns the real probe sandbox as a child process, and
 * `groundingRatio()` counts the verdicts that came back. Nothing here asserts a
 * constant; a test that did would be `self_referential` by this repo's own
 * definition and would be worthless as evidence for exactly this claim.
 *
 * The probe directory is pinned to the shipped one, so a probe sitting in the
 * developer's `~/.config/keel/probes/` cannot change what this test measures.
 */

import { afterAll, beforeAll, describe, expect, test } from 'bun:test';
import { createHash } from 'node:crypto';
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import { classify, resolveOptions } from '../scripts/classify.ts';
import { gather } from '../scripts/gather.ts';
import {
  type GroundingRatio,
  type Report,
  type Verdict,
  groundingRatio,
} from '../schemas/keel.ts';
import {
  type Binding,
  type RouteProposal,
  type UngroundedClass,
  projectRatio,
} from '../schemas/route.ts';
import {
  bind,
  buildDispatch,
  checkAnchor,
  externalRefs,
  indexReport,
  loadStyles,
  rankBindings,
  renderBindingsHtml,
  run,
} from '../scripts/route.ts';

const ROOT = resolve(import.meta.dir, '..');
const SHIPPED_PROBES = join(ROOT, 'probes');
const FIXTURE = join(ROOT, 'tests', 'fixtures', 'report.sample.json');

/**
 * A small target with a real verification surface: one CI step whose verdict is
 * produced by a language model reading the work (the shipped probe decides it
 * `self_referential`), one that runs a test binary, and a Makefile. Written to
 * disk, not mocked — `gather()` reads bytes.
 */
function writeTarget(dir: string): void {
  mkdirSync(join(dir, '.github', 'workflows'), { recursive: true });
  writeFileSync(
    join(dir, '.github', 'workflows', 'ci.yml'),
    `name: ci
on: [pull_request]
jobs:
  check:
    runs-on: ubuntu-latest
    steps:
      - name: Gate on model judgment
        run: npx @anthropic-ai/claude-code -p "review the diff and fail if it is wrong"
      - name: Unit tests
        run: pytest -q --exitfirst
`,
  );
  writeFileSync(
    join(dir, 'Makefile'),
    `test: ## run the suite
\tpytest -q

lint: ## static analysis
\truff check .
`,
  );
  writeFileSync(
    join(dir, 'package.json'),
    `${JSON.stringify({ name: 'sep-target', scripts: { test: 'pytest -q' } }, null, 2)}\n`,
  );
}

interface Measurement {
  nodeIds: string[];
  verdicts: Verdict[];
  grounding: GroundingRatio;
  pendingIds: string[];
}

let scratch = '';
let target = '';

/** gather → classify (real sandbox child) → groundingRatio. The whole path. */
async function measure(): Promise<Measurement> {
  const nodes = gather(target);
  // The node payload lives OUTSIDE the target: writing it inside would change
  // the surface being measured, which is the very confound this file exists to
  // rule out.
  const nodesPath = join(scratch, 'nodes.json');
  writeFileSync(nodesPath, JSON.stringify(nodes));
  const out = await classify(
    resolveOptions({ nodesPath, probeDirs: [SHIPPED_PROBES], timeoutMs: 20_000 }),
    nodes,
  );
  return {
    nodeIds: nodes.map((n) => n.id).sort(),
    verdicts: out.decided,
    grounding: groundingRatio(out.decided),
    pendingIds: out.pending.map((n) => n.id).sort(),
  };
}

/**
 * The hostile artifact. Every ungrounded check is claimed routable, anchored,
 * and — a thing no agent may ever emit — already applied. It also carries
 * forged `verdicts` and a forged `grounding` block reading 1.0, so that any
 * code path that so much as merged this file into a measurement would show up
 * as a perfect score rather than as a subtle drift.
 */
function adversarialBindings(nodeIds: string[]): string {
  return `${JSON.stringify(
    {
      target,
      revision: 'HEAD',
      generatedAt: new Date().toISOString(),
      sourceReport: 'none — this file is fabricated',
      bindings: nodeIds.map((id) => ({
        loop: id,
        from: 'self_referential',
        anchoredOn: nodeIds[0] ?? 'anything',
        change: 'already done, trust me',
        argument: 'the signal now comes from somewhere else',
        effort: 'config',
        status: 'applied',
      })),
      summary: { currentRatio: 1, projectedRatio: 1, routable: nodeIds.length, unroutable: 0 },
      // forged measurement-layer keys — the trap
      verdicts: nodeIds.map((id) => ({
        nodeId: id,
        class: 'anchored',
        writeBoundary: { producer: 'nothing', actorCanWrite: false, argument: 'trust me' },
        evidence: [],
        confidence: 1,
        decidedBy: 'agent',
      })),
      grounding: {
        anchored: nodeIds.length,
        selfReferential: 0,
        unknown: 0,
        notACheck: 0,
        ratio: 1,
      },
    },
    null,
    2,
  )}\n`;
}

/** Drive the CLI without spraying its diagnostics through the test output. */
function quiet(fn: () => number): { code: number; err: string[]; out: string[] } {
  const origErr = console.error;
  const origOut = console.log;
  const err: string[] = [];
  const out: string[] = [];
  console.error = (...a: unknown[]) => {
    err.push(a.map(String).join(' '));
  };
  console.log = (...a: unknown[]) => {
    out.push(a.map(String).join(' '));
  };
  try {
    return { code: fn(), err, out };
  } finally {
    console.error = origErr;
    console.log = origOut;
  }
}

/** Every primitive in a structure, with its dotted path. Used to audit shapes. */
interface Leaf {
  path: string;
  value: unknown;
}
function leaves(v: unknown, path = '', out: Leaf[] = []): Leaf[] {
  if (Array.isArray(v)) {
    v.forEach((x, i) => leaves(x, `${path}.${i}`, out));
    return out;
  }
  if (v !== null && typeof v === 'object') {
    for (const [k, val] of Object.entries(v)) leaves(val, path === '' ? k : `${path}.${k}`, out);
    return out;
  }
  out.push({ path, value: v });
  return out;
}

const FIXTURE_REPORT = (): Report => JSON.parse(readFileSync(FIXTURE, 'utf8')) as Report;

beforeAll(() => {
  scratch = mkdtempSync(join(tmpdir(), 'keel-separation-'));
  target = join(scratch, 'target');
  mkdirSync(target, { recursive: true });
  writeTarget(target);
});

afterAll(() => {
  if (scratch) rmSync(scratch, { recursive: true, force: true });
});

// ---------------------------------------------------------------------------

describe('the score is unreachable from routing', () => {
  test('measuring twice, with an adversarial bindings file in between, is identical', async () => {
    const before = await measure();

    // The measurement must be non-trivial, or "identical" would be vacuous:
    // an empty verdict set is trivially equal to another empty verdict set.
    expect(before.nodeIds.length).toBeGreaterThan(2);
    expect(before.verdicts.length).toBeGreaterThan(0);
    expect(before.verdicts.some((v) => v.decidedBy === 'probe')).toBe(true);
    expect(before.grounding.selfReferential).toBeGreaterThan(0);

    // Plant the fabrication everywhere a measurement could plausibly find it:
    // inside the target the gatherer walks, under a dot-dir, in a reports/
    // directory, and in the environment.
    const forged = adversarialBindings(before.nodeIds);
    mkdirSync(join(target, '.keel'), { recursive: true });
    mkdirSync(join(target, 'reports'), { recursive: true });
    writeFileSync(join(target, 'keel.bindings.json'), forged);
    writeFileSync(join(target, '.keel', 'bindings.json'), forged);
    writeFileSync(join(target, 'reports', 'target.bindings.json'), forged);
    writeFileSync(join(scratch, 'bindings.json'), forged);
    process.env.KEEL_BINDINGS = join(scratch, 'bindings.json');
    process.env.KEEL_BINDINGS_DIR = join(target, '.keel');

    try {
      const after = await measure();

      // The claim, stated three ways because each would fail differently.
      expect(after.verdicts).toEqual(before.verdicts);
      expect(after.grounding).toEqual(before.grounding);
      expect(after.pendingIds).toEqual(before.pendingIds);

      // And the ratio specifically — the number the fabrication claimed was 1.
      expect(after.grounding.ratio).toBe(before.grounding.ratio);
      expect(after.grounding.ratio).not.toBe(1);
    } finally {
      delete process.env.KEEL_BINDINGS;
      delete process.env.KEEL_BINDINGS_DIR;
      rmSync(join(target, 'keel.bindings.json'), { force: true });
      rmSync(join(target, '.keel'), { recursive: true, force: true });
      rmSync(join(target, 'reports'), { recursive: true, force: true });
    }
  }, 60_000);

  /**
   * The negative control, and it is not optional. "Identical" is only evidence
   * if the measurement was capable of moving in the first place; without this,
   * the test above would pass just as happily against a `measure()` that
   * returned a constant — which is `self_referential` by this repo's own
   * definition. So: change the target's actual verification surface, and watch
   * the same code path report something different.
   */
  test('the measurement DOES move when the target moves', async () => {
    const workflow = join(target, '.github', 'workflows', 'ci.yml');
    const original = readFileSync(workflow, 'utf8');
    const before = await measure();
    try {
      writeFileSync(
        workflow,
        `${original}      - name: Second opinion
        run: gpt-5 critique the diff and exit nonzero on a finding
`,
      );
      const after = await measure();
      expect(after.nodeIds.length).toBe(before.nodeIds.length + 1);
      expect(after.grounding.selfReferential).toBe(before.grounding.selfReferential + 1);
      expect(after.verdicts).not.toEqual(before.verdicts);
    } finally {
      writeFileSync(workflow, original);
    }
    expect((await measure()).verdicts).toEqual(before.verdicts);
  }, 60_000);

  /**
   * "Opened READ-ONLY, always" was, until this test, a claim about `bind()` and
   * `renderBindingsHtml()` — two pure functions that contain no write call and
   * therefore could not have violated it. The only code that writes is `run()`,
   * so `run()` is what gets driven here, aimed squarely at the report itself.
   */
  test('the CLI refuses to write over the source report', () => {
    const digest = (b: Buffer | string) => createHash('sha256').update(b).digest('hex');
    const victim = join(scratch, 'victim.json');
    writeFileSync(victim, readFileSync(FIXTURE));
    const before = digest(readFileSync(victim));

    for (const flag of ['--out', '--html'] as const) {
      const r = quiet(() => run([victim, flag, victim]));
      expect(r.code).toBe(1);
      expect(r.err.join('\n')).toContain('refusing to write over the source report');
      expect(digest(readFileSync(victim))).toBe(before);
    }

    // ...and via the derived paths, which is the same hazard wearing a flag
    // that does not name the file.
    const derived = join(scratch, 'derived');
    mkdirSync(derived, { recursive: true });
    const asBindings = join(derived, 'keel.bindings.json'); // == the slug route.ts derives
    writeFileSync(asBindings, readFileSync(FIXTURE));
    const derivedBefore = digest(readFileSync(asBindings));
    expect(quiet(() => run([asBindings, '--reports-dir', derived])).code).toBe(1);
    expect(digest(readFileSync(asBindings))).toBe(derivedBefore);

    // The negative control: pointed anywhere else it writes, so the refusal
    // above is a refusal and not an inability.
    const elsewhere = join(scratch, 'elsewhere.bindings.json');
    expect(quiet(() => run([victim, '--out', elsewhere])).code).toBe(0);
    expect(existsSync(elsewhere)).toBe(true);
    expect(digest(readFileSync(victim))).toBe(before);
    expect(digest(readFileSync(FIXTURE))).toBe(before);
  });

  test('the pure routing path writes nothing either', () => {
    const original = readFileSync(FIXTURE);
    const copy = join(scratch, 'report.copy.json');
    writeFileSync(copy, original);
    const digest = (b: Buffer | string) => createHash('sha256').update(b).digest('hex');
    const before = digest(original);

    const report = JSON.parse(original.toString('utf8')) as Report;
    const proposals: RouteProposal[] = report.verdicts
      .filter((v) => v.class === 'self_referential')
      .map((v) => ({
        loop: v.nodeId,
        anchoredOn: 'Makefile#portability-check',
        argument: 'a claim strong enough to be worth refusing if it were false',
        effort: 'config' as const,
      }));

    const bindings = bind(report, proposals, { sourceReport: copy });
    // rendering is the other write path; exercise it too
    renderBindingsHtml(bindings, report);

    expect(digest(readFileSync(copy))).toBe(before);
    expect(digest(readFileSync(FIXTURE))).toBe(before);

    // A BindingReport is not a Report, and must never be mistaken for one.
    const asRecord = bindings as unknown as Record<string, unknown>;
    expect(asRecord.verdicts).toBeUndefined();
    expect(asRecord.nodes).toBeUndefined();
    expect(asRecord.grounding).toBeUndefined();
  });

  test('the projection cannot move the measured ratio', () => {
    const report = JSON.parse(readFileSync(FIXTURE, 'utf8')) as Report;
    const measured = groundingRatio(report.verdicts);

    const everythingRoutable: RouteProposal[] = report.verdicts
      .filter((v) => v.class === 'self_referential' || v.class === 'unknown')
      .map((v) => ({
        loop: v.nodeId,
        anchoredOn: 'Makefile#portability-check',
        argument: 'every one of these is routable, obviously',
        effort: 'config' as const,
      }));

    const bindings = bind(report, everythingRoutable, { sourceReport: FIXTURE });
    expect(bindings.summary.projectedRatio).toBeGreaterThan(measured.ratio);

    // Re-deriving from the same verdicts gives the same number as before the
    // router ran, and the projection is nowhere in it.
    expect(groundingRatio(report.verdicts)).toEqual(measured);
    expect(bindings.summary.currentRatio).toBe(measured.ratio);
  });
});

// ---------------------------------------------------------------------------

describe('the router never invents an anchor', () => {
  const report = () => JSON.parse(readFileSync(FIXTURE, 'utf8')) as Report;

  test('an anchor that is not in the report collapses to null with a reason', () => {
    const r = report();
    const out = bind(
      r,
      [
        {
          loop: 'package.json#test',
          anchoredOn: '.github/workflows/nightly.yml#the-anchor-i-wish-existed',
          argument: 'a confident-sounding argument for a node that does not exist',
          effort: 'config',
        },
      ],
      { sourceReport: FIXTURE },
    );
    const b = out.bindings.find((x) => x.loop === 'package.json#test');
    expect(b?.anchoredOn).toBeNull();
    expect(b?.noRouteReason).toContain('is not a node in the source report');
    expect(out.warnings.some((w) => w.includes('refused'))).toBe(true);
    expect(out.summary.routable).toBe(0);
  });

  test('an anchor that exists but is not classified anchored collapses to null', () => {
    const r = report();
    const out = bind(
      r,
      [
        {
          loop: 'package.json#test',
          anchoredOn: 'Makefile#bstack-primitive-lint', // self_referential in the fixture
          argument: 'routing one ungrounded check onto another',
        },
      ],
      { sourceReport: FIXTURE },
    );
    const b = out.bindings.find((x) => x.loop === 'package.json#test');
    expect(b?.anchoredOn).toBeNull();
    expect(b?.noRouteReason).toContain('classified self_referential');
  });

  test('a node cannot be its own producer', () => {
    const r = report();
    const out = bind(
      r,
      [{ loop: 'package.json#test', anchoredOn: 'package.json#test', argument: 'circular' }],
      { sourceReport: FIXTURE },
    );
    expect(out.bindings.find((x) => x.loop === 'package.json#test')?.noRouteReason).toContain(
      'is the ungrounded node itself',
    );
  });

  test('a resolvable anchor with no argument is still refused', () => {
    const index = indexReport(report());
    const withArgument = checkAnchor(
      'Makefile#portability-check',
      'package.json#test',
      'the causal path, stated',
      index,
    );
    const without = checkAnchor(
      'Makefile#portability-check',
      'package.json#test',
      '   ',
      index,
    );
    expect(withArgument.anchoredOn).toBe('Makefile#portability-check');
    expect(without.anchoredOn).toBeNull();
    expect(without.rejection).toContain('carries no argument');
  });

  test('every binding is null-with-a-reason or resolves to a measured anchored node', () => {
    const r = report();
    const index = indexReport(r);
    const anchored = new Set(index.anchoredIds);
    const out = bind(
      r,
      [
        {
          loop: 'package.json#test',
          anchoredOn: 'Makefile#portability-check',
          argument: 'the merge-time signal moves from a checkbox to a runner conclusion',
          effort: 'wiring',
        },
        { loop: 'Makefile#bstack-check', anchoredOn: null, argument: '', noRouteReason: 'policy' },
      ],
      { sourceReport: FIXTURE },
    );

    for (const b of out.bindings) {
      expect(b.status).toBe('proposed');
      if (b.anchoredOn === null) {
        expect(b.noRouteReason ?? '').not.toBe('');
      } else {
        expect(anchored.has(b.anchoredOn)).toBe(true);
        expect(r.verdicts.find((v) => v.nodeId === b.anchoredOn)?.class).toBe('anchored');
      }
    }
    expect(out.summary.routable + out.summary.unroutable).toBe(out.bindings.length);
  });

  test("status is forced to 'proposed', whatever the proposal claimed", () => {
    const r = report();
    const hostile = [
      {
        loop: 'package.json#test',
        anchoredOn: 'Makefile#portability-check',
        argument: 'wired into the runner lane',
        status: 'applied',
        pairedWith: 'a counter-metric I invented',
        arbitratedBy: 'me',
        auditEvery: 'never',
      },
    ] as unknown as RouteProposal[];
    const out = bind(r, hostile, { sourceReport: FIXTURE });
    const b = out.bindings.find((x) => x.loop === 'package.json#test');
    expect(b?.status).toBe('proposed');
    expect(b?.pairedWith).toBeUndefined();
    expect(b?.arbitratedBy).toBeUndefined();
    expect(b?.auditEvery).toBeUndefined();
    expect(out.warnings.filter((w) => w.includes('keel construct')).length).toBe(3);
  });
});

// ---------------------------------------------------------------------------
// INVARIANT 3, IN THE DIRECTION IT IS STATED.
//
// The tests above prove the constructor cannot reach the scorer. That is the
// easy direction. The stated invariant is the other one — "nothing in this unit
// may take the ratio as an input to optimize" — and prose in a doc-comment is
// not a mechanism. These four run the direction that matters: they fail if a
// ratio, a target, or a ranking by ratio impact ever reaches the routing path.
// ---------------------------------------------------------------------------

const ANCHOR = 'Makefile#portability-check';

describe('the ratio is unreachable from routing', () => {
  test('the dispatch the agent judges from carries no ratio and no objective', () => {
    const report = FIXTURE_REPORT();
    const dispatch = buildDispatch(report, FIXTURE);

    // Non-vacuous: there is something to leak into, and something to leak.
    expect(dispatch.requests.length).toBeGreaterThan(0);
    expect(dispatch.requests[0]?.candidates.length).toBeGreaterThan(0);
    expect(report.grounding?.ratio).toBeGreaterThan(0);

    // Exhaustive on purpose: a field added to the dispatch has to be declared
    // here, which is what forces every new field through the walks below.
    // `effortValues` is the vocabulary `effort` may take — strings only, and
    // subject to exactly the same numeric and lexical checks as everything
    // else the agent sees.
    expect(Object.keys(dispatch).sort()).toEqual(
      [
        'anchoredIds',
        'effortValues',
        'requests',
        'revision',
        'sourceReport',
        'target',
        'warnings',
      ].sort(),
    );

    const all = leaves(dispatch);
    expect(all.length).toBeGreaterThan(50);

    // 1. No field ANYWHERE is named for a score or an objective. `target` is
    //    the repository under measurement and is checked separately below; it
    //    is not in this list because it is not a number and never becomes one.
    const forbiddenKey =
      /ratio|grounding|score|threshold|goal|objective|budget|needed|desired|improve|quota|optimi[sz]/i;
    for (const leaf of all) {
      for (const seg of leaf.path.split('.')) {
        if (/^\d+$/.test(seg)) continue;
        expect([leaf.path, seg]).toEqual([leaf.path, seg.replace(forbiddenKey, '!LEAK!')]);
      }
    }

    // 2. Every NUMBER the agent sees is a confidence measured in the source
    //    report. Nothing else numeric survives — not a count of nodes still to
    //    route, not a projected delta, not the ratio itself. This is the check
    //    that catches `nodesNeededToHitTarget: 4` and `targetRatio: 0.8`.
    const confidences = new Set(
      report.verdicts.map((v) => v.confidence).filter((c) => typeof c === 'number'),
    );
    const numbers = all.filter((l) => typeof l.value === 'number');
    expect(numbers.length).toBeGreaterThan(0);
    for (const n of numbers) {
      expect([n.path, /(^|\.)(currentConfidence|confidence)$/.test(n.path)]).toEqual([n.path, true]);
      expect([n.path, confidences.has(n.value as number)]).toEqual([n.path, true]);
    }
    const measured = groundingRatio(report.verdicts).ratio;
    for (const n of numbers) expect(n.value).not.toBe(measured);
    for (const n of numbers) expect(n.value).not.toBe(report.grounding?.ratio);

    // 3. No instruction. The dispatch's own scaffolding may not talk about a
    //    ratio, a threshold or an optimisation — that is how "route as many as
    //    needed to reach targetRatio" would arrive. Text carried verbatim OUT
    //    of the report (node `raw`, the measured write-boundary arguments) and
    //    the warnings are excluded: those are the world's words, not ours, and
    //    a target repo is allowed to have a check with "ratio" in its name.
    const carried =
      /^requests\.\d+\.(node|current(Producer|Argument))\b|^requests\.\d+\.candidates\.\d+\.(argument|producer|name|source|id)$|^warnings\b/;
    const strings = all.filter((l) => typeof l.value === 'string' && !carried.test(l.path));
    expect(strings.length).toBeGreaterThan(0);
    for (const s of strings) {
      const v = s.value as string;
      expect([s.path, v]).toEqual([s.path, v.replace(/ratio|threshold|objective|optimi[sz]e/gi, '!LEAK!')]);
    }

    // 4. `effortValues` is held to a STRICTER vocabulary than the rest. The
    //    regex above has to stay narrow because most strings here are the
    //    world's words — a target repo is allowed to own a check called
    //    `grounding-score`, and `sourceReport` is a path the caller chose. But
    //    `effortValues` is ours, written in this repo and carried verbatim to
    //    the judging agent, so it is the one string surface where a
    //    score-flavoured verb could be introduced deliberately and pass. It
    //    gets the wider list precisely because there is no risk of colliding
    //    with something the target legitimately named.
    const ours = all.filter((l) => /^effortValues\./.test(l.path));
    expect(ours.length).toBeGreaterThan(0);
    for (const s of ours) {
      const v = String(s.value);
      expect([s.path, v]).toEqual([
        s.path,
        // `cost|weight|reward|utility` and a bare digit are in the list because
        // `means` is PROSE, and prose is where a numeric weight can be smuggled
        // past a check that only looks at JSON leaves. "relative cost 1; prefer
        // the lowest aggregate cost" contains no numeric leaf and would have
        // passed the earlier list while stating precisely the objective this
        // payload may never carry. The digit clause is the load-bearing half:
        // effort ranks, and a rank the agent can do arithmetic on is a weight.
        v.replace(
          /ratio|grounding|score|objective|target|cost|weight|reward|utilit|\d|maximi[sz]|minimi[sz]|optimi[sz]/gi,
          '!LEAK!',
        ),
      ]);
    }
  });

  test('forging the report grounding block changes nothing the router does', () => {
    const honest = FIXTURE_REPORT();
    const forged = FIXTURE_REPORT();
    forged.grounding = {
      anchored: 999,
      selfReferential: 0,
      unknown: 0,
      notACheck: 0,
      ratio: 1,
    };

    const a = buildDispatch(honest, FIXTURE);
    const b = buildDispatch(forged, FIXTURE);
    expect(b.requests).toEqual(a.requests);
    expect(b.anchoredIds).toEqual(a.anchoredIds);
    // The forgery was genuinely seen — otherwise "unchanged" would be vacuous.
    expect(b.warnings.some((w) => w.includes('disagrees with its own verdicts'))).toBe(true);
    expect(a.warnings.some((w) => w.includes('disagrees with its own verdicts'))).toBe(false);

    const proposals: RouteProposal[] = honest.verdicts
      .filter((v) => v.class === 'self_referential')
      .map((v) => ({
        loop: v.nodeId,
        anchoredOn: ANCHOR,
        argument: 'the exit code comes from the runner, which the author cannot author',
        effort: 'wiring' as const,
      }));
    const at = '2026-07-24T00:00:00.000Z';
    const ba = bind(honest, proposals, { sourceReport: FIXTURE, generatedAt: at });
    const bb = bind(forged, proposals, { sourceReport: FIXTURE, generatedAt: at });
    expect(bb.bindings).toEqual(ba.bindings);
    expect(bb.summary).toEqual(ba.summary);
    // The summary is recomputed from the verdicts, so it reports the measured
    // ratio and not the forged one — 1 is what the forgery claimed.
    expect(bb.summary.currentRatio).toBe(groundingRatio(honest.verdicts).ratio);
    expect(bb.summary.currentRatio).not.toBe(1);
  });

  test('ranking does not consult the class, so it cannot be ranking by ratio impact', () => {
    const b = (loop: string, from: UngroundedClass, effort: Binding['effort'], anchored: boolean): Binding => ({
      loop,
      from,
      anchoredOn: anchored ? ANCHOR : null,
      argument: anchored ? 'a causal path' : '',
      status: 'proposed',
      ...(effort && anchored ? { effort } : {}),
      ...(anchored ? {} : { noRouteReason: 'needs a decision, not a rewiring' }),
    });

    const bindings: Binding[] = [
      b('n-process', 'unknown', 'process', true),
      b('n-config', 'self_referential', 'config', true),
      b('n-wiring', 'not_a_check', 'wiring', true),
      b('n-null', 'self_referential', undefined, false),
      b('a-unstated', 'unknown', undefined, true),
    ];

    const order = rankBindings(bindings).map((x) => x.loop);
    // Cheapest first, unstated effort after the stated ones, nulls last, ties
    // broken by node id. Stated concretely so the permutation below is a claim
    // about a real ordering rather than about an accident.
    expect(order).toEqual(['n-config', 'n-wiring', 'n-process', 'a-unstated', 'n-null']);

    // Now rotate every `from` through all three ungrounded classes. Ratio
    // impact changes on every rotation (a not_a_check route enters the
    // denominator, the other two do not); the order must not.
    const classes: UngroundedClass[] = ['self_referential', 'unknown', 'not_a_check'];
    for (const shift of [1, 2]) {
      const permuted = bindings.map((x) => ({
        ...x,
        from: classes[(classes.indexOf(x.from) + shift) % classes.length] as UngroundedClass,
      }));
      expect(permuted.map((x) => x.from)).not.toEqual(bindings.map((x) => x.from));
      expect(rankBindings(permuted).map((x) => x.loop)).toEqual(order);
    }

    // And permuting the anchor target — same class, same effort, different
    // node — must not move anything either.
    const reversed = rankBindings([...bindings].reverse()).map((x) => x.loop);
    expect(reversed).toEqual(order);
  });

  test('the cheapest route sorts first even when its ratio impact is the smallest', () => {
    const report = FIXTURE_REPORT();
    const current = groundingRatio(report.verdicts);

    // A not_a_check route is the smallest possible gain: it adds one to the
    // numerator AND one to the denominator. A self_referential route only moves
    // a node across. So this pair has cheap-effort/small-gain against
    // dear-effort/large-gain — exactly the case where a ranking that optimised
    // the score would invert.
    const cheap: Binding = {
      loop: 'Makefile#help',
      from: 'not_a_check',
      anchoredOn: ANCHOR,
      argument: 'a one-line change',
      effort: 'config',
      status: 'proposed',
    };
    const dear: Binding = {
      loop: 'package.json#test',
      from: 'self_referential',
      anchoredOn: ANCHOR,
      argument: 'a branch-protection change and a conversation',
      effort: 'process',
      status: 'proposed',
    };

    const gainCheap = projectRatio(current, [cheap]).ratio - current.ratio;
    const gainDear = projectRatio(current, [dear]).ratio - current.ratio;
    expect(gainCheap).toBeGreaterThan(0);
    expect(gainCheap).toBeLessThan(gainDear); // the premise, measured not assumed

    expect(rankBindings([dear, cheap]).map((x) => x.loop)).toEqual([cheap.loop, dear.loop]);
    expect(rankBindings([cheap, dear]).map((x) => x.loop)).toEqual([cheap.loop, dear.loop]);
  });

  test('the projection reports re-grounding and construction apart', () => {
    const report = FIXTURE_REPORT();
    const current = groundingRatio(report.verdicts);
    const proposals: RouteProposal[] = [
      {
        loop: 'Makefile#help',
        anchoredOn: ANCHOR,
        argument: 'this would be a new check, not a repaired one',
        effort: 'config',
      },
      {
        loop: 'package.json#test',
        anchoredOn: ANCHOR,
        argument: 'the merge-time signal moves to the runner conclusion',
        effort: 'wiring',
      },
    ];
    const out = bind(report, proposals, { sourceReport: FIXTURE, includeNotACheck: true });
    const projected = projectRatio(current, out.bindings);

    expect(projected.regrounded).toBe(1);
    expect(projected.constructed).toBe(1);
    expect(projected.regrounded + projected.constructed).toBe(out.summary.routable);

    // The page must show the split, not one merged headline number.
    const html = renderBindingsHtml(out, report);
    expect(html).toContain('1 re-grounded · 1 constructed');
    expect(html).toContain('Construction —');
    // and a run with no not_a_check nodes in scope shows no construction table
    const plain = bind(report, [proposals[1] as RouteProposal], { sourceReport: FIXTURE });
    expect(renderBindingsHtml(plain, report)).not.toContain('Construction —');
  });
});

// ---------------------------------------------------------------------------
// The self-containment guard, which must measure the document and not the text.
// ---------------------------------------------------------------------------

describe('the page fetches nothing, and says so about the page and not about its text', () => {
  const page = (head: string, body: string) =>
    `<!doctype html><html><head><style>${head}</style></head><body>${body}</body></html>`;

  test('real fetching constructs are caught', () => {
    expect(externalRefs(page('', '<script src="https://cdn.example.com/x.js"></script>'))).toContain(
      '<script src=>',
    );
    expect(externalRefs(page('', '<link href="https://fonts.example.com/x.css" rel="stylesheet">'))).toContain(
      '<link href=>',
    );
    expect(externalRefs(page('', '<img src="https://example.com/x.png">'))).toContain(
      'embedded media src',
    );
    expect(externalRefs(page('@import url("https://example.com/x.css");', ''))).toContain('@import');
    expect(externalRefs(page('body { background: url(https://example.com/x.png); }', ''))).toContain(
      'css url()',
    );
  });

  test('content that merely mentions them is not a fetch', () => {
    const mentions = [
      'a build step named build css: @import bundles',
      'the runner pulls url(https://example.com/x) from outside the write boundary',
      'see &lt;script src=&quot;x.js&quot;&gt; in the workflow',
      '&lt;link href=&quot;y&quot;&gt; and &lt;img src=&quot;z&quot;&gt;',
    ].join(' ');
    expect(externalRefs(page('', `<p>${mentions}</p><td>${mentions}</td>`))).toEqual([]);
    // in an attribute the page actually uses, too
    expect(externalRefs(page('', '<div data-class="@import url(https://x)"></div>'))).toEqual([]);
  });

  test('a CSS comment explaining @import is not an @import', () => {
    expect(externalRefs(page('/* not split behind an @import, see url(x) */ p { color: red }', ''))).toEqual(
      [],
    );
    // data: and fragment urls are inlined, not fetched
    expect(externalRefs(page('p { background: url(data:image/svg+xml,<svg/>) } q { fill: url(#g) }', ''))).toEqual(
      [],
    );
  });

  test('the real rendered page is clean even when the report is full of urls', () => {
    const report = FIXTURE_REPORT();
    // The two reproductions from review, planted in the two places content
    // reaches the page: a node name and an agent's causal argument.
    const victimNode = report.nodes.find((n) => n.id === 'Makefile#bstack-check');
    expect(victimNode).toBeDefined();
    if (victimNode) victimNode.name = 'build css: @import bundles';
    const out = bind(
      report,
      [
        {
          loop: 'package.json#test',
          anchoredOn: ANCHOR,
          argument:
            'the merge-time signal moves to the runner, which pulls url(https://example.com/x) from outside the write boundary; today a <script src="local.js"> shim sets it',
          effort: 'wiring',
        },
      ],
      { sourceReport: FIXTURE },
    );
    const html = renderBindingsHtml(out, report);

    // The text really is in the document — otherwise this proves nothing.
    expect(html).toContain('@import bundles');
    expect(html).toContain('url(https://example.com/x)');
    expect(externalRefs(html)).toEqual([]);
  });

  test('the shipped design system inlines clean', () => {
    const report = FIXTURE_REPORT();
    const out = bind(report, [], { sourceReport: FIXTURE });
    expect(externalRefs(renderBindingsHtml(out, report, loadStyles()))).toEqual([]);
  });
});

// ---------------------------------------------------------------------------
// Degradation: R sits low in the plan's ladder, so it must fail small.
// ---------------------------------------------------------------------------

describe('the CLI degrades rather than crashing', () => {
  test('an unreadable design system skips the page and keeps the JSON', () => {
    const missing = join(scratch, 'no-such-design');
    expect(() => loadStyles(missing)).toThrow();

    const out = join(scratch, 'degraded.bindings.json');
    const html = join(scratch, 'degraded.bindings.html');
    const r = quiet(() => run([FIXTURE, '--out', out, '--html', html, '--design-dir', missing]));
    expect(r.code).toBe(0);
    expect(existsSync(out)).toBe(true);
    expect(existsSync(html)).toBe(false);
    expect(r.err.join('\n')).toContain('design system not readable');
    expect(r.err.join('\n')).toContain('JSON written, page skipped');

    // With nothing else written there is nothing to be pleased about: exit 1.
    const only = join(scratch, 'only.bindings.html');
    const r2 = quiet(() => run([FIXTURE, '--html', only, '--design-dir', missing]));
    expect(r2.code).toBe(1);
    expect(existsSync(only)).toBe(false);
  });

  test('the design system that ships does render a page', () => {
    const html = join(scratch, 'ok.bindings.html');
    const r = quiet(() => run([FIXTURE, '--html', html]));
    expect(r.code).toBe(0);
    expect(externalRefs(readFileSync(html, 'utf8'))).toEqual([]);
  });
});
