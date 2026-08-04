/**
 * THE ε-AUDIT TEST.
 *
 * `audit.ts` exists to answer one question about Keel itself: does the probe
 * library still mean what it meant when each probe was reviewed? The answer is
 * only worth something if the re-decision was made without sight of the cached
 * one — so blindness is the property under test here, and it is tested the only
 * way a blindness claim can be: on the serialized bytes the judging agent is
 * handed. A comment saying "we do not include the class" is not evidence.
 *
 * Six things are asserted, all by execution:
 *
 *   BLIND, AND NOT MERELY EMPTY. The pending file contains no class name, no
 *   probeId, no confidence and no write-boundary argument, and neither does the
 *   node section of the printed payload. Each assertion is paired with its
 *   non-vacuous twin — the same strings ARE in the report — because "substring
 *   absent" is trivially true of a payload that is empty or of a fixture that
 *   never had them. The other half of that pairing is the harder one: the
 *   payload must still carry the LITERAL SNIPPET, and every such assertion reads
 *   its expected value out of the REPORT's node, never out of the payload node
 *   being checked. A payload asserted to contain its own fields is a tautology,
 *   and it is satisfied by one that starves the judging agent or that hands over
 *   the wrong node's text under the right node's id — which is why every fixture
 *   node's `raw`, `source` and `hints` are distinct.
 *
 *   HONEST ABOUT ITS OWN COVERAGE. The disclosed percentage is `compared /
 *   population` — the size of the evidence, not the size of the draw. Computing
 *   it over `sampled` would let a run that printed forty nodes and got two back
 *   claim it covered the forty, which is rate-padding one level up from the rate
 *   this script exists to report honestly.
 *
 *   ALL-OR-NOTHING ON BAD INPUT. A rejected batch writes nothing. Every fixture
 *   that asserts this is MIXED — one entry that a partial apply WOULD record,
 *   beside the one that must sink the batch — because "the bytes did not change"
 *   is not a claim when there was nothing valid to write.
 *
 *   DETERMINISTIC. The same seed draws the same nodes, in this process, in a
 *   fresh process, and after the report's verdicts have been shuffled. A sample
 *   nobody can re-derive makes the audit unreviewable: a reader cannot tell a
 *   draw from a choice.
 *
 *   ARITHMETIC, NOT ASSERTION. `agreed` is computed by comparing the two
 *   classes, so a re-decision that CLAIMS agreement while naming a different
 *   class is recorded as a disagreement. And `render.ts` — a module with no
 *   knowledge of this one — is used as the independent reader of every block
 *   this file writes: `auditIsWellFormed` rejects exactly the self-contradictory
 *   shapes, so its acceptance is a signal `audit.ts` cannot produce by agreeing
 *   with itself.
 *
 *   NON-DESTRUCTIVE. No verdict's class moves and the grounding ratio is
 *   byte-identical afterwards. An audit that edited the measurement it audits
 *   would be the failure this project is named for.
 *
 * Nothing below asserts a constant. Every number comes back from running the
 * real functions or spawning the real CLI over files on disk — a test that
 * asserted a literal would be `self_referential` by this repo's own definition.
 */

import { afterAll, describe, expect, test } from 'bun:test';
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import {
  type GroundingClass,
  type Node,
  type Report,
  type Verdict,
  groundingRatio,
} from '../schemas/keel.ts';
import {
  type AuditPending,
  applyAudit,
  buildPending,
  probeDecided,
  readRedecisions,
  renderPayload,
  renderResult,
  sampleIds,
} from '../scripts/audit.ts';
import { auditIsWellFormed, auditTally } from '../scripts/render.ts';
import { cleanupTrees, run as spawn, tree } from './helpers/tree.ts';

const ROOT = resolve(import.meta.dir, '..');
const AUDIT = join(ROOT, 'scripts', 'audit.ts');

const CLASSES: GroundingClass[] = ['anchored', 'self_referential', 'unknown', 'not_a_check'];

/** Strings that must never reach the judging agent, and are easy to spot if they do. */
const PROBE_MARKER = 'probe-marker';
const ARGUMENT_MARKER = 'CACHED-ARGUMENT-SENTINEL';
const CONFIDENCE = 0.87;

afterAll(cleanupTrees);

// ---------------------------------------------------------------------------
// Fixture — a report whose cached verdicts are deliberately conspicuous.
//
// The node text is ordinary CI YAML and contains none of the four class names,
// so a class appearing in the payload can only have come from a verdict. That
// is what makes the blindness assertions below mean something.
// ---------------------------------------------------------------------------

interface Spec {
  id: string;
  cls: GroundingClass;
  decidedBy?: 'probe' | 'agent';
}

/**
 * Every field the judging agent reads is made UNIQUE per node.
 *
 * That is load-bearing, not decoration. If `raw`, `source` and `hints` were the
 * same string on every node, `buildPending` could hand the agent node 7's
 * snippet under node 3's id and the assertions below would still pass — the
 * payload would look full and be lying about which node it describes. Uniqueness
 * is what turns "the payload carries a raw" into "the payload carries THIS
 * node's raw".
 */
function nodeOf(spec: Spec, i: number): Node {
  return {
    id: spec.id,
    kind: 'ci_step',
    name: `step ${i}`,
    source: `.github/workflows/ci-${i}.yml:${10 + i}`,
    raw: `- name: step ${i}\n  run: pytest -q --exitfirst tests/suite_${i}.py\n`,
    hints: { job: `job-${i}`, shard: `shard-${i}` },
  };
}

function verdictOf(spec: Spec, i: number): Verdict {
  const decidedBy = spec.decidedBy ?? 'probe';
  return {
    nodeId: spec.id,
    class: spec.cls,
    writeBoundary: {
      producer: 'the pytest process',
      actorCanWrite: spec.cls === 'anchored' ? false : spec.cls === 'self_referential' ? true : null,
      argument: `${ARGUMENT_MARKER}-${i}: the exit code is decided by the runtime.`,
    },
    evidence: [`ci.yml:${10 + i}`],
    confidence: CONFIDENCE,
    decidedBy,
    ...(decidedBy === 'probe' ? { probeId: `${PROBE_MARKER}-${i}` } : {}),
  };
}

function reportOf(specs: Spec[]): Report {
  const nodes = specs.map(nodeOf);
  const verdicts = specs.map(verdictOf);
  return {
    target: 'fixture-target',
    revision: 'abc123def456789',
    generatedAt: '2026-07-25T09:00:00.000Z',
    nodes,
    verdicts,
    grounding: groundingRatio(verdicts),
    economics: {
      nodesTotal: nodes.length,
      nodesSampled: nodes.length,
      decidedByProbe: verdicts.filter((v) => v.decidedBy === 'probe').length,
      decidedByAgent: verdicts.filter((v) => v.decidedBy === 'agent').length,
      probesMinted: 0,
      probeLibrarySize: 3,
      tokensIn: 0,
      tokensOut: 0,
      tokensEstimated: true,
      wallClockMs: 1,
    },
  };
}

/** n probe-decided verdicts, classes cycled so the fixture is not one class wide. */
function probeReport(n: number): Report {
  return reportOf(
    Array.from({ length: n }, (_, i) => ({
      id: `.github/workflows/ci.yml#${i}-step`,
      cls: CLASSES[i % CLASSES.length] as GroundingClass,
    })),
  );
}

function writeReport(report: Report): { dir: string; path: string } {
  const dir = tree({ 'report.json': `${JSON.stringify(report, null, 2)}\n` });
  return { dir, path: join(dir, 'report.json') };
}

function readReport(path: string): Report {
  return JSON.parse(readFileSync(path, 'utf8')) as Report;
}

/**
 * The SOURCE node, resolved out of the report by id.
 *
 * Asserting that a payload node contains its own fields is a tautology; the
 * question blindness actually raises is whether the payload starves the judge.
 * So every "the payload carries X" assertion below reads X from here — the
 * report — and never from the payload it is checking.
 */
function sourceNode(report: Report, id: string): Node {
  const n = report.nodes.find((x) => x.id === id);
  if (!n) throw new Error(`fixture is broken: no node ${id} in the report`);
  return n;
}

function sameSet(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const s = new Set(a);
  return b.every((x) => s.has(x));
}

// ---------------------------------------------------------------------------

describe('the payload is blind', () => {
  test('the pending file carries no cached class, probe, confidence or argument', () => {
    const report = probeReport(20);
    const pending = buildPending(report, '/nowhere/report.json', {
      fraction: 0.1,
      seed: 3,
      all: false,
    });
    const payloadBytes = JSON.stringify(pending);
    const reportBytes = JSON.stringify(report);

    // Non-vacuous first: everything asserted absent below is present upstream,
    // so an empty payload could not pass this test by accident.
    for (const s of [...CLASSES, PROBE_MARKER, ARGUMENT_MARKER, String(CONFIDENCE)]) {
      expect([s, reportBytes.includes(s)]).toEqual([s, true]);
    }
    expect(pending.nodes.length).toBeGreaterThan(0);

    for (const s of [...CLASSES, PROBE_MARKER, ARGUMENT_MARKER, String(CONFIDENCE)]) {
      expect([s, payloadBytes.includes(s)]).toEqual([s, false]);
    }

    // And it does carry the thing the agent has to reason over — checked
    // against the REPORT's node, not against the payload's own copy. Blindness
    // that worked by handing over an empty `raw`, or by handing over the WRONG
    // node's `raw`, would satisfy every absence assertion above.
    for (const pn of pending.nodes) {
      const src = sourceNode(report, pn.id);
      expect([pn.id, pn.raw]).toEqual([pn.id, src.raw]);
      expect([pn.id, pn.source]).toEqual([pn.id, src.source]);
      expect([pn.id, pn.hints]).toEqual([pn.id, src.hints]);
      expect([pn.id, pn.name]).toEqual([pn.id, src.name]);
      expect([pn.id, pn.kind]).toEqual([pn.id, src.kind]);
      // Serialized, because the agent is handed bytes and not an object.
      expect(payloadBytes).toContain(JSON.stringify(src.raw));
      expect(payloadBytes).toContain(JSON.stringify(src.source));
      expect(payloadBytes).toContain(JSON.stringify(src.hints?.shard));
    }
  });

  test('the printed node section carries no class, and the vocabulary block still does', () => {
    const report = probeReport(12);
    const pending = buildPending(report, '/nowhere/report.json', {
      fraction: 1,
      seed: 1,
      all: true,
    });
    const text = renderPayload(pending, '/nowhere/pending.json', '/nowhere/redecisions.json');

    const start = text.indexOf('NODES TO RE-DECIDE');
    const end = text.indexOf('WRITE RE-DECISIONS TO');
    expect(start).toBeGreaterThan(0);
    expect(end).toBeGreaterThan(start);
    const section = text.slice(start, end);

    // The nodes really are in there, with the literal text the agent has to
    // reason over — otherwise "no class in the section" is a statement about an
    // empty string, and a payload that starved the judge would pass this test.
    // Sourced from the report, so printing node 3's snippet under node 7's id
    // fails here too.
    for (const pn of pending.nodes) {
      const src = sourceNode(report, pn.id);
      expect(section).toContain(`id:     ${src.id}`);
      expect(section).toContain(`source: ${src.source}`);
      expect(section).toContain(`name:   ${src.name}`);
      expect(section).toContain(JSON.stringify(src.hints));
      for (const line of src.raw.split('\n').filter((l) => l.trim())) {
        expect([src.id, section.includes(`  | ${line}`)]).toEqual([src.id, true]);
      }
    }

    // No class name is attached to any node...
    for (const c of CLASSES) expect([c, section.includes(c)]).toEqual([c, false]);
    // ...but the agent is still told what the four answers are. Blindness that
    // worked by starving the judge would be a different bug.
    for (const c of CLASSES) expect([c, text.includes(c)]).toEqual([c, true]);

    // These have no legitimate reason to appear anywhere in the payload.
    for (const s of [PROBE_MARKER, ARGUMENT_MARKER, String(CONFIDENCE)]) {
      expect([s, text.includes(s)]).toEqual([s, false]);
    }
  });

  test('the pending file written to disk by the real CLI is blind too', async () => {
    const report = probeReport(20);
    const { dir, path } = writeReport(report);
    const r = await spawn(['bun', AUDIT, path, '--sample', '0.25', '--seed', '5'], { cwd: dir });
    expect([r.code, r.stderr]).toEqual([0, r.stderr]);

    const pendingPath = join(dir, 'report.audit-pending.json');
    expect(existsSync(pendingPath)).toBe(true);
    const bytes = readFileSync(pendingPath, 'utf8');
    for (const s of [...CLASSES, PROBE_MARKER, ARGUMENT_MARKER, String(CONFIDENCE)]) {
      expect([s, bytes.includes(s)]).toEqual([s, false]);
    }
    // Non-vacuous: the file on disk really does carry each drawn node's own
    // literal snippet, sourced from the report rather than from itself.
    const onDisk = JSON.parse(bytes) as AuditPending;
    expect(onDisk.nodes.length).toBe(5);
    for (const pn of onDisk.nodes) {
      const src = sourceNode(report, pn.id);
      expect([pn.id, pn.raw, pn.source, pn.hints]).toEqual([pn.id, src.raw, src.source, src.hints]);
    }
    // The report next to it does have them — the blindness is in the payload,
    // not in the fixture.
    expect(readFileSync(path, 'utf8')).toContain(ARGUMENT_MARKER);
  });
});

describe('the draw is deterministic and re-derivable', () => {
  const report = probeReport(20);
  const ids = probeDecided(report).map((v) => v.nodeId);
  const opts = { fraction: 0.25, seed: 9, all: false };

  test('the same seed draws the same nodes', () => {
    expect(sampleIds(ids, opts)).toEqual(sampleIds(ids, opts));
  });

  test('the drawn set does not depend on the order verdicts happen to be in', () => {
    const reversed = [...ids].reverse();
    expect(sameSet(sampleIds(reversed, opts), sampleIds(ids, opts))).toBe(true);
  });

  test('a different seed is capable of drawing something else', () => {
    const base = sampleIds(ids, opts);
    const moved = Array.from({ length: 20 }, (_, i) => i + 100).some(
      (seed) => !sameSet(sampleIds(ids, { ...opts, seed }), base),
    );
    // Without this the "deterministic" property could be satisfied by a
    // constant selection that ignores the seed entirely.
    expect(moved).toBe(true);
  });

  test('the fraction rounds up, so a live population is never audited zero times', () => {
    expect(sampleIds(ids, { fraction: 0.1, seed: 1, all: false }).length).toBe(
      Math.ceil(ids.length * 0.1),
    );
    expect(sampleIds(ids.slice(0, 3), { fraction: 0.1, seed: 1, all: false }).length).toBe(1);
    expect(sampleIds([], { fraction: 0.5, seed: 1, all: false })).toEqual([]);
  });

  test('--all draws the whole probe-decided population and nothing else', () => {
    const mixed = reportOf([
      { id: 'a#1', cls: 'anchored', decidedBy: 'probe' },
      { id: 'a#2', cls: 'unknown', decidedBy: 'agent' },
      { id: 'a#3', cls: 'not_a_check', decidedBy: 'probe' },
      { id: 'a#4', cls: 'self_referential', decidedBy: 'agent' },
    ]);
    const pending = buildPending(mixed, '/nowhere/report.json', {
      fraction: 0.1,
      seed: 1,
      all: true,
    });
    expect(pending.nodes.map((n) => n.id)).toEqual(['a#1', 'a#3']);
    expect(pending.population).toBe(2);
  });

  test('two fresh processes with the same seed draw the same nodes', async () => {
    const { dir, path } = writeReport(probeReport(20));
    const args = [path, '--sample', '0.25', '--seed', '11'];
    const first = await spawn(['bun', AUDIT, ...args], { cwd: dir });
    expect(first.code).toBe(0);
    const a = (JSON.parse(readFileSync(join(dir, 'report.audit-pending.json'), 'utf8')) as AuditPending)
      .nodes.map((n) => n.id);
    const second = await spawn(['bun', AUDIT, ...args], { cwd: dir });
    expect(second.code).toBe(0);
    const b = (JSON.parse(readFileSync(join(dir, 'report.audit-pending.json'), 'utf8')) as AuditPending)
      .nodes.map((n) => n.id);
    expect(b).toEqual(a);
    expect(a.length).toBe(5);
  });
});

describe('agreement is computed, and reported with its denominator', () => {
  /** Four probe verdicts with known classes; three re-decided the same way. */
  function fixture() {
    const report = reportOf([
      { id: 'x#1', cls: 'anchored' },
      { id: 'x#2', cls: 'self_referential' },
      { id: 'x#3', cls: 'not_a_check' },
      { id: 'x#4', cls: 'unknown' },
    ]);
    const pending = buildPending(report, '/nowhere/report.json', {
      fraction: 1,
      seed: 1,
      all: true,
    });
    return { report, pending };
  }

  const argue = (s: string) => `${s}: what emits the signal and who can write to it.`;

  test('a hand-checked mix of agreement and disagreement', () => {
    const { report, pending } = fixture();
    const result = applyAudit(
      report,
      pending,
      [
        { nodeId: 'x#1', class: 'anchored', argument: argue('agrees') },
        { nodeId: 'x#2', class: 'self_referential', argument: argue('agrees') },
        { nodeId: 'x#3', class: 'not_a_check', argument: argue('agrees') },
        { nodeId: 'x#4', class: 'anchored', argument: argue('the probe over-matched here') },
      ],
      '2026-07-25T10:00:00.000Z',
    );

    expect([result.compared, result.agreed, result.disagreed, result.pending]).toEqual([4, 3, 1, 0]);
    expect(result.rate).toBeCloseTo(0.75, 10);
    expect(result.disagreements.map((d) => [d.nodeId, d.cached, d.agent, d.probeId])).toEqual([
      ['x#4', 'unknown', 'anchored', `${PROBE_MARKER}-3`],
    ]);

    const text = renderResult(result);
    expect(text).toContain('over 4 compared nodes');
    expect(text).toContain('population: 4 probe-decided verdicts');
    // The probe is named so a human can go read it; it is not retired here.
    expect(text).toContain(`${PROBE_MARKER}-3`);
    expect(text).toContain('NAMED, not retired');
  });

  test('a sampled node nobody re-judged stays pending and is never counted as agreement', () => {
    const { report, pending } = fixture();
    const result = applyAudit(
      report,
      pending,
      [
        { nodeId: 'x#1', class: 'anchored', argument: argue('agrees') },
        { nodeId: 'x#2', class: 'self_referential', argument: argue('agrees') },
        { nodeId: 'x#3', class: 'unknown', argument: argue('disagrees') },
      ],
      '2026-07-25T10:00:00.000Z',
    );
    expect([result.sampled, result.compared, result.pending]).toEqual([4, 3, 1]);
    expect(result.rate).toBeCloseTo(2 / 3, 10);
    const text = renderResult(result);
    expect(text).toContain('over 3 compared nodes');
    expect(text).toContain('still pending re-judgment: 1');
  });

  test('`agreed` is derived from the two classes, not accepted from the file', () => {
    const { report, pending } = fixture();
    // The judging side claims agreement while naming a different class. If the
    // claim were believed, the one number that catches a self-set status field
    // would itself be a self-set status field.
    const raw = [
      { nodeId: 'x#1', class: 'unknown', argument: argue('re-decided'), agreed: true, audit: { agreed: true } },
    ];
    const { decisions, problems } = readRedecisions(raw, new Set(pending.nodes.map((n) => n.id)));
    expect(problems).toEqual([]);
    const result = applyAudit(report, pending, decisions, '2026-07-25T10:00:00.000Z');
    expect(result.agreed).toBe(0);
    expect(result.disagreed).toBe(1);
    const audited = report.verdicts.find((v) => v.nodeId === 'x#1');
    expect(audited?.audit).toEqual({
      agentClass: 'unknown',
      agreed: false,
      at: '2026-07-25T10:00:00.000Z',
    });
  });

  /**
   * THE RATE-PADDING VECTOR.
   *
   * Coverage is `compared / population` — what was actually re-judged over what
   * could have been. Computing it over `sampled` instead discloses the size of
   * the DRAW rather than the size of the evidence, so an audit that printed a
   * payload for forty nodes and got two back would claim it covered the forty.
   * This script's whole job is an honest agreement rate; a disclosure that
   * overstates its own coverage is the same lie one level up.
   */
  test('disclosed coverage is what was compared, not what was drawn', () => {
    const report = probeReport(4);
    const pending = buildPending(report, '/nowhere/report.json', {
      fraction: 1,
      seed: 1,
      all: true,
    });
    const result = applyAudit(
      report,
      pending,
      pending.nodes.slice(0, 2).map((n) => ({
        nodeId: n.id,
        class: 'anchored' as GroundingClass,
        argument: argue('half the draw came back'),
      })),
      '2026-07-25T10:00:00.000Z',
    );
    // 4 drawn, 2 re-judged, over a population of 4: coverage is 50%, not 100%.
    expect([result.population, result.sampled, result.compared]).toEqual([4, 4, 2]);

    const text = renderResult(result);
    expect(text).toContain('population: 4 probe-decided verdicts · 2 audited = 50% of it');
    expect(text).not.toContain('= 100% of it');
    expect(text).toContain('still pending re-judgment: 2');
  });

  test('a full Verdict pasted in is accepted; one with no argument is not', () => {
    const allowed = new Set(['x#1']);
    const pasted = readRedecisions(
      [
        {
          nodeId: 'x#1',
          class: 'anchored',
          writeBoundary: { producer: 'pytest', actorCanWrite: false, argument: argue('thorough') },
        },
      ],
      allowed,
    );
    expect(pasted.problems).toEqual([]);
    expect(pasted.decisions[0]?.argument).toContain('thorough');

    const bare = readRedecisions([{ nodeId: 'x#1', class: 'anchored' }], allowed);
    expect(bare.decisions).toEqual([]);
    expect(bare.problems.join(' ')).toContain('argument is required');

    const foreign = readRedecisions(
      [{ nodeId: 'not-drawn', class: 'anchored', argument: argue('outside') }],
      allowed,
    );
    expect(foreign.problems.join(' ')).toContain("not in this audit's sample");
  });
});

describe('the audit annotates the measurement; it never edits it', () => {
  test('no class moves and the grounding ratio is unchanged', () => {
    const report = probeReport(8);
    const before = JSON.parse(JSON.stringify(report)) as Report;
    const pending = buildPending(report, '/nowhere/report.json', {
      fraction: 1,
      seed: 1,
      all: true,
    });
    // Every re-decision disagrees — the most pressure a disagreeing audit could
    // put on the measurement.
    applyAudit(
      report,
      pending,
      pending.nodes.map((n) => ({
        nodeId: n.id,
        class: 'anchored' as GroundingClass,
        argument: 'the runtime emits it.',
      })),
      '2026-07-25T10:00:00.000Z',
    );

    expect(report.verdicts.map((v) => v.class)).toEqual(before.verdicts.map((v) => v.class));
    expect(groundingRatio(report.verdicts)).toEqual(groundingRatio(before.verdicts));
    expect(report.grounding).toEqual(before.grounding);

    // Stripped of the audit blocks, the report is byte-identical to what went in.
    const stripped = JSON.parse(JSON.stringify(report)) as Report;
    for (const v of stripped.verdicts) v.audit = undefined;
    for (const v of stripped.verdicts) delete (v as Partial<Verdict>).audit;
    expect(JSON.stringify(stripped)).toBe(JSON.stringify(before));
  });

  test('render.ts — which knows nothing about audit.ts — accepts every block written', () => {
    const report = reportOf([
      { id: 'y#1', cls: 'anchored' },
      { id: 'y#2', cls: 'not_a_check' },
      { id: 'y#3', cls: 'self_referential' },
    ]);
    const pending = buildPending(report, '/nowhere/report.json', {
      fraction: 1,
      seed: 1,
      all: true,
    });
    const result = applyAudit(
      report,
      pending,
      [
        { nodeId: 'y#1', class: 'anchored', argument: 'agrees.' },
        { nodeId: 'y#2', class: 'anchored', argument: 'disagrees.' },
        { nodeId: 'y#3', class: 'self_referential', argument: 'agrees.' },
      ],
      '2026-07-25T10:00:00.000Z',
    );

    const audited = report.verdicts.filter((v) => v.audit !== undefined);
    expect(audited.length).toBe(3);
    // auditIsWellFormed rejects a block whose `agreed` contradicts its
    // `agentClass`, so this passing is an independent reading of our arithmetic.
    for (const v of audited) expect([v.nodeId, auditIsWellFormed(v)]).toEqual([v.nodeId, true]);

    const tally = auditTally(report.verdicts);
    expect([tally.compared, tally.agreed, tally.malformed]).toEqual([
      result.compared,
      result.agreed,
      0,
    ]);
    expect(tally.probeAudited).toBe(result.compared);
  });
});

describe('an empty population is an outcome, not a rate', () => {
  test('a report with no probe-decided verdicts says so and exits 0', async () => {
    const { dir, path } = writeReport(
      reportOf([
        { id: 'z#1', cls: 'anchored', decidedBy: 'agent' },
        { id: 'z#2', cls: 'unknown', decidedBy: 'agent' },
      ]),
    );
    const r = await spawn(['bun', AUDIT, path], { cwd: dir });
    expect([r.code, r.stderr]).toEqual([0, r.stderr]);
    expect(r.stdout).toContain('nothing to audit');
    expect(r.stdout).toContain('every verdict in this report was agent-decided');
    // No rate, in any shape — not 0.00, not 1.00, not "agreement".
    expect(r.stdout).not.toContain('agreement');
    expect(r.stdout).toEqual(r.stdout.replace(/\b[01]\.\d\d\b/g, '!RATE!'));
    // And nothing was written: there is no sample to record against.
    expect(existsSync(join(dir, 'report.audit-pending.json'))).toBe(false);
  });

  test('record with an empty re-decision file reports no rate rather than a flattering one', () => {
    const report = probeReport(4);
    const pending = buildPending(report, '/nowhere/report.json', {
      fraction: 1,
      seed: 1,
      all: true,
    });
    const result = applyAudit(report, pending, [], '2026-07-25T10:00:00.000Z');
    expect(result.rate).toBeNull();
    const text = renderResult(result);
    expect(text).toContain('nothing was compared');
    expect(text).toEqual(text.replace(/\b[01]\.\d\d\b/g, '!RATE!'));
  });
});

describe('the stepper, end to end, over real files', () => {
  test('sample → re-decide → record writes the audit into the report on disk', async () => {
    const { dir, path } = writeReport(
      reportOf([
        { id: 'e#1', cls: 'anchored' },
        { id: 'e#2', cls: 'not_a_check' },
        { id: 'e#3', cls: 'self_referential' },
        { id: 'e#4', cls: 'unknown' },
      ]),
    );

    const sample = await spawn(['bun', AUDIT, path, '--all'], { cwd: dir });
    expect([sample.code, sample.stderr]).toEqual([0, sample.stderr]);
    expect(sample.stdout).toContain('NODES TO RE-DECIDE · 4');

    const pendingPath = join(dir, 'report.audit-pending.json');
    const redecisionsPath = join(dir, 'report.audit-redecisions.json');
    const drawn = (JSON.parse(readFileSync(pendingPath, 'utf8')) as AuditPending).nodes.map(
      (n) => n.id,
    );
    expect(drawn.sort()).toEqual(['e#1', 'e#2', 'e#3', 'e#4']);

    // The agent's step. Three match the cache; e#4 does not.
    writeFileSync(
      redecisionsPath,
      `${JSON.stringify(
        [
          { nodeId: 'e#1', class: 'anchored', argument: 'pytest exits non-zero on failure.' },
          { nodeId: 'e#2', class: 'not_a_check', argument: 'it only provisions the runner.' },
          { nodeId: 'e#3', class: 'self_referential', argument: 'a model grades the model.' },
          { nodeId: 'e#4', class: 'anchored', argument: 'the fork point is traceable after all.' },
        ],
        null,
        2,
      )}\n`,
    );

    const record = await spawn(['bun', AUDIT, 'record', pendingPath, redecisionsPath, '--json'], {
      cwd: dir,
    });
    expect([record.code, record.stderr]).toEqual([0, record.stderr]);
    expect(record.stdout).toContain('agreement 0.75 over 4 compared nodes');
    expect(record.stdout).toContain('population: 4 probe-decided verdicts');

    const updated = readReport(path);
    const audited = updated.verdicts.filter((v) => v.audit !== undefined);
    expect(audited.length).toBe(4);
    for (const v of audited) expect([v.nodeId, auditIsWellFormed(v)]).toEqual([v.nodeId, true]);
    expect(auditTally(updated.verdicts).agreed).toBe(3);
    // A disagreement is a measurement, not a build failure — hence exit 0 above.
    expect(updated.verdicts.find((v) => v.nodeId === 'e#4')?.class).toBe('unknown');
  });

  /**
   * REJECTION IS ALL-OR-NOTHING, AND THE FIXTURE HAS TO MAKE THAT TESTABLE.
   *
   * "nothing was written" is only a claim if a partial write had something to
   * write. A re-decision file whose ONLY entry is the bad one leaves `decisions`
   * empty, so even a build that applied before validating would produce
   * byte-identical output — the assertion would be true of every possible
   * implementation. So each file below is MIXED: one entry that would be
   * recorded, and one that must sink the whole batch.
   */
  async function sampleFixture(
    specs: { id: string; cls: GroundingClass }[],
    sampleArgs: string[],
  ): Promise<{ dir: string; path: string; pendingPath: string; drawn: string[] }> {
    const { dir, path } = writeReport(reportOf(specs));
    const sample = await spawn(['bun', AUDIT, path, ...sampleArgs], { cwd: dir });
    expect([sample.code, sample.stderr]).toEqual([0, sample.stderr]);
    const pendingPath = join(dir, 'report.audit-pending.json');
    const drawn = (JSON.parse(readFileSync(pendingPath, 'utf8')) as AuditPending).nodes.map(
      (n) => n.id,
    );
    return { dir, path, pendingPath, drawn };
  }

  test('an off-sample entry sinks the batch, and the valid one beside it is not written', async () => {
    const { dir, path, pendingPath, drawn } = await sampleFixture(
      [
        { id: 'f#1', cls: 'anchored' },
        { id: 'f#2', cls: 'unknown' },
      ],
      ['--sample', '0.5', '--seed', '2'],
    );
    expect(drawn.length).toBe(1);
    const inSample = drawn[0] as string;
    const notDrawn = ['f#1', 'f#2'].find((id) => !drawn.includes(id)) as string;

    const redecisionsPath = join(dir, 'redecisions.json');
    writeFileSync(
      redecisionsPath,
      `${JSON.stringify([
        // Perfectly valid, and in the sample: a partial apply WOULD write this.
        { nodeId: inSample, class: 'anchored', argument: 'the runtime decides the exit code.' },
        { nodeId: notDrawn, class: 'anchored', argument: 'off-sample.' },
      ])}\n`,
    );

    const before = readFileSync(path, 'utf8');
    const record = await spawn(['bun', AUDIT, 'record', pendingPath, redecisionsPath], { cwd: dir });
    expect(record.code).toBe(1);
    expect(record.stderr).toContain('rejected');
    expect(record.stderr).toContain("not in this audit's sample");
    expect(readFileSync(path, 'utf8')).toBe(before);
    // Belt and braces: no audit block reached any verdict, including the good one.
    expect(readReport(path).verdicts.filter((v) => v.audit !== undefined)).toEqual([]);
  });

  test('an entry with no argument sinks the batch, and the valid one beside it is not written', async () => {
    const { dir, path, pendingPath, drawn } = await sampleFixture(
      [
        { id: 'h#1', cls: 'anchored' },
        { id: 'h#2', cls: 'unknown' },
      ],
      ['--all'],
    );
    expect(drawn.sort()).toEqual(['h#1', 'h#2']);

    const redecisionsPath = join(dir, 'redecisions.json');
    writeFileSync(
      redecisionsPath,
      `${JSON.stringify([
        { nodeId: 'h#1', class: 'anchored', argument: 'the runtime decides the exit code.' },
        { nodeId: 'h#2', class: 'unknown' },
      ])}\n`,
    );

    const before = readFileSync(path, 'utf8');
    const record = await spawn(['bun', AUDIT, 'record', pendingPath, redecisionsPath], { cwd: dir });
    expect(record.code).toBe(1);
    expect(record.stderr).toContain('argument is required');
    expect(readFileSync(path, 'utf8')).toBe(before);
    expect(readReport(path).verdicts.filter((v) => v.audit !== undefined)).toEqual([]);
  });

  test('a duplicate re-decision sinks the batch, and the first copy is not written', async () => {
    const { dir, path, pendingPath, drawn } = await sampleFixture(
      [
        { id: 'i#1', cls: 'anchored' },
        { id: 'i#2', cls: 'unknown' },
      ],
      ['--all'],
    );
    expect(drawn.sort()).toEqual(['i#1', 'i#2']);

    const redecisionsPath = join(dir, 'redecisions.json');
    writeFileSync(
      redecisionsPath,
      `${JSON.stringify([
        { nodeId: 'i#1', class: 'anchored', argument: 'the runtime decides the exit code.' },
        { nodeId: 'i#1', class: 'unknown', argument: 'on reflection, the fork point is unclear.' },
      ])}\n`,
    );

    const before = readFileSync(path, 'utf8');
    const record = await spawn(['bun', AUDIT, 'record', pendingPath, redecisionsPath], { cwd: dir });
    expect(record.code).toBe(1);
    expect(record.stderr).toContain('duplicate re-decision');
    expect(readFileSync(path, 'utf8')).toBe(before);
    expect(readReport(path).verdicts.filter((v) => v.audit !== undefined)).toEqual([]);
  });

  test('a report that moved under the audit refuses to be compared across the move', async () => {
    const { dir, path } = writeReport(reportOf([{ id: 'g#1', cls: 'anchored' }]));
    const sample = await spawn(['bun', AUDIT, path, '--all'], { cwd: dir });
    expect(sample.code).toBe(0);

    const moved = readReport(path);
    moved.revision = 'ffffffffffffffff';
    writeFileSync(path, `${JSON.stringify(moved, null, 2)}\n`);

    const redecisionsPath = join(dir, 'redecisions.json');
    writeFileSync(
      redecisionsPath,
      `${JSON.stringify([{ nodeId: 'g#1', class: 'anchored', argument: 'same as before.' }])}\n`,
    );
    const record = await spawn(
      ['bun', AUDIT, 'record', join(dir, 'report.audit-pending.json'), redecisionsPath],
      { cwd: dir },
    );
    expect(record.code).toBe(1);
    expect(record.stderr).toContain('re-run the sample stage');
  });

  test('a fraction that samples nothing is refused, and says what to use instead', async () => {
    const { dir, path } = writeReport(probeReport(4));
    const r = await spawn(['bun', AUDIT, path, '--sample', '0'], { cwd: dir });
    expect(r.code).toBe(1);
    expect(r.stderr).toContain('--sample must be a fraction in (0,1]');
    expect(r.stderr).toContain('--all');
  });
});

/**
 * BAD INPUT GETS A SENTENCE, NOT A STACK TRACE — AND LEAVES NOTHING BEHIND.
 *
 * Every one of these used to reach a runtime helper and throw from inside it.
 * Two of them also littered: the failure happened after the temp file had been
 * written, so a stray `*.tmp-<pid>` survived the crash. A tool whose subject is
 * disciplined verification cannot fail sloppily on its own arguments.
 */
describe('malformed invocations fail with an actionable message', () => {
  /** Everything in the directory, so a stray temp file cannot hide. */
  function listing(dir: string): string[] {
    return readdirSync(dir).sort();
  }

  test('a dangling -o is a missing value, not an empty one — and writes no temp file', async () => {
    const { dir, path } = writeReport(probeReport(4));
    const before = listing(dir);
    const r = await spawn(['bun', AUDIT, path, '-o'], { cwd: dir });
    expect(r.code).toBe(1);
    // Litter first: the old behaviour took `''`, wrote the temp file, and only
    // then threw ENOENT out of renameSync — so the crash left a `.tmp-<pid>`
    // behind. Asserting the directory is unchanged is the assertion that catches
    // it; the message assertion below would pass even for a tidy crash.
    expect(listing(dir)).toEqual(before);
    expect(r.stderr).not.toContain('ENOENT');
    expect(r.stderr).toContain('-o needs a path');
  });

  test('a dangling --report is refused before anything is read', async () => {
    const { dir, path } = writeReport(probeReport(4));
    const r = await spawn(['bun', AUDIT, 'record', path, path, '--report'], { cwd: dir });
    expect(r.code).toBe(1);
    expect(r.stderr).toContain('--report needs a path');
  });

  test('a report that parses to null gets the same message every other bad input gets', async () => {
    const dir = tree({ 'report.json': 'null\n' });
    const r = await spawn(['bun', AUDIT, join(dir, 'report.json')], { cwd: dir });
    expect(r.code).toBe(1);
    expect(r.stderr).toContain('not a keel report');
    expect(r.stderr).toContain('got null');
    // The crash this replaced.
    expect(r.stderr).not.toContain('TypeError');
    expect(readdirSync(dir).sort()).toEqual(['report.json']);
  });

  test('a report that parses to an array is refused too', async () => {
    const dir = tree({ 'report.json': '[]\n' });
    const r = await spawn(['bun', AUDIT, join(dir, 'report.json')], { cwd: dir });
    expect(r.code).toBe(1);
    expect(r.stderr).toContain('got an array');
    expect(r.stderr).not.toContain('TypeError');
  });

  test('a pending payload with no nodes array is refused rather than crashed through', async () => {
    const { dir, path } = writeReport(probeReport(4));
    const pendingPath = join(dir, 'not-a-payload.json');
    writeFileSync(pendingPath, '{"reportPath":"/nowhere"}\n');
    const redecisionsPath = join(dir, 'redecisions.json');
    writeFileSync(redecisionsPath, '[]\n');
    const r = await spawn(['bun', AUDIT, 'record', pendingPath, redecisionsPath, '--report', path], {
      cwd: dir,
    });
    expect(r.code).toBe(1);
    expect(r.stderr).toContain('not an audit payload');
    expect(r.stderr).not.toContain('TypeError');
  });

  /**
   * A structurally-empty report has an empty population, which is a first-class
   * outcome — but the REASON printed has to be one the data supports. `{}` has
   * no verdicts at all, so "every verdict was agent-decided" is a claim about
   * evidence that is not there, and the target line printed the literal string
   * `undefined`.
   */
  test('an empty report names no target it does not have, and gives the reason it can support', async () => {
    const dir = tree({ 'report.json': '{}\n' });
    const r = await spawn(['bun', AUDIT, join(dir, 'report.json')], { cwd: dir });
    expect([r.code, r.stderr]).toEqual([0, r.stderr]);
    expect(r.stdout).toContain('nothing to audit');
    expect(r.stdout).toContain('carries no verdicts at all');
    expect(r.stdout).not.toContain('every verdict in this report was agent-decided');
    expect(r.stdout).not.toContain('undefined');
    expect(r.stdout).toContain('(no target recorded)');
    expect(r.stdout).toContain('(no revision)');
  });

  test('a report whose verdicts are all agent-decided still says exactly that', async () => {
    const { dir, path } = writeReport(
      reportOf([
        { id: 'k#1', cls: 'anchored', decidedBy: 'agent' },
        { id: 'k#2', cls: 'unknown', decidedBy: 'agent' },
      ]),
    );
    const r = await spawn(['bun', AUDIT, path], { cwd: dir });
    expect([r.code, r.stderr]).toEqual([0, r.stderr]);
    expect(r.stdout).toContain('every verdict in this report was agent-decided');
    expect(r.stdout).not.toContain('carries no verdicts at all');
  });
});

/**
 * THE `THEN:` LINE IS A COMMAND, SO A SHELL HAS TO ACCEPT IT.
 *
 * It is printed to be pasted. Under `~/My Projects/` the unquoted form
 * word-split into four arguments and the second stage failed on a path nobody
 * typed. This is checked the only way a shell-quoting claim can be: by handing
 * the printed line to a real shell and looking at what it exits with.
 */
describe('the printed THEN: command survives a path with spaces', () => {
  test('a real shell runs the line as printed, over a directory with a space in it', async () => {
    const dir = tree({
      'audit dir/report.json': `${JSON.stringify(
        reportOf([
          { id: 'q#1', cls: 'anchored' },
          { id: 'q#2', cls: 'unknown' },
        ]),
        null,
        2,
      )}\n`,
    });
    const path = join(dir, 'audit dir', 'report.json');

    const sample = await spawn(['bun', AUDIT, path, '--all'], { cwd: dir });
    expect([sample.code, sample.stderr]).toEqual([0, sample.stderr]);

    const then = sample.stdout.split('\n').find((l) => l.startsWith('THEN: ')) as string;
    expect(then).toBeTruthy();

    // The agent's step, at the exact path the THEN: line will hand the shell.
    writeFileSync(
      join(dir, 'audit dir', 'report.audit-redecisions.json'),
      `${JSON.stringify([
        { nodeId: 'q#1', class: 'anchored', argument: 'the runtime decides the exit code.' },
        { nodeId: 'q#2', class: 'unknown', argument: 'the fork point is not established.' },
      ])}\n`,
    );

    // Only the interpreter reference is rewritten (the printed line names the
    // skill-relative `scripts/audit.ts`); both PATH ARGUMENTS are passed to the
    // shell exactly as printed, which is the thing under test.
    const cmd = then.slice('THEN: '.length).replace('bun scripts/audit.ts', `bun '${AUDIT}'`);
    expect(cmd).toContain('audit dir');
    const shell = await spawn(['sh', '-c', cmd], { cwd: dir });
    expect([shell.code, shell.stderr]).toEqual([0, shell.stderr]);
    expect(shell.stdout).toContain('over 2 compared nodes');

    // And it really did the work, in the real file.
    const updated = readReport(path);
    expect(updated.verdicts.filter((v) => v.audit !== undefined).length).toBe(2);
  });
});
