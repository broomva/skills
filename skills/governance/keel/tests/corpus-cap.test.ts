/**
 * THE DECLARED-VS-EFFECTIVE CAP TEST.
 *
 * `corpus.ts`'s header promises "NO SILENT ANYTHING. The node cap is
 * disclosed". The published summary broke that promise in the quietest way
 * available: it recorded `nodeCap: 40` — the value corpus.json *declares* —
 * above fifteen entries that had each sampled under a `--cap 25`. `next`
 * computed the effective cap correctly and then `record` and `status` reached
 * past it for the declared one. Nothing crashed, nothing warned, and the only
 * machine-readable statement of how the corpus was produced disagreed with the
 * measurements underneath it.
 *
 * The first repair took the cap from the INVOCATION, and that is the bug this
 * file now spends most of its length on. An invocation is not a measurement: a
 * bare `bun corpus.ts next` over a finished corpus clones nothing, samples
 * nothing and binds no node — and then stamped its declared 40 straight back
 * over the same entries. The cap in force is a fact about what was WRITTEN, so
 * it is recovered from the entries: `entry.cap` when present, and otherwise
 * from truncation, because the sampler stops at exactly the cap and a
 * `capped: true` entry's `nodesSampled` therefore IS the cap it was drawn
 * under. That second clause is what reaches the entries written before
 * `entry.cap` existed — the ones a stale header contradicts.
 *
 * The committed distribution those legacy entries actually have, and which the
 * fixture below reproduces literally, is
 *   nodesSampled { 25: 12, 12: 1, 21: 1, 0: 1 }
 * — twelve targets truncated at 25, tiktoken complete at 12 of 12, commander-js
 * complete at 21 of 21, and anthropic-courses with nothing gathered at all.
 * Only the twelve truncated ones prove a cap; the other three prove that the
 * cap was at least as large as their surface, which is not a value, and they
 * are disclosed as indeterminate rather than guessed at.
 *
 * Two kinds of test live here. The first three DRIVE THE REAL STEPPER end to
 * end — clone, gather, sample, judge, record — against a git repository built
 * on disk, then read the bytes corpus.ts wrote; the bug lived in the seam
 * between two commands run in two separate processes, and only running both
 * processes crosses that seam. The rest SEED a summary in the exact shape of
 * the committed one and then run a real command over it, because the
 * regression is specifically about what a later command does to entries it did
 * not write.
 *
 * The fixture repo is built in a temp dir rather than committed, for the reason
 * `tests/helpers/tree.ts` gives: `gather` walks whatever it is pointed at, and a
 * committed tree of fake workflows would enlarge the surface Keel publishes a
 * number about.
 */

import { afterAll, beforeAll, describe, expect, test } from 'bun:test';
import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import type { Node } from '../schemas/keel.ts';
import { cleanupTrees, run, tree } from './helpers/tree.ts';

const CORPUS_TS = resolve(import.meta.dir, '../scripts/corpus.ts');

/** Four interesting steps — comfortably more than the caps used below. */
const WORKFLOW = `name: ci
on: [push]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install
        run: bun install --frozen-lockfile
      - name: Test
        run: bun test
      - name: Typecheck
        run: bunx tsc --noEmit
`;

/** Declared cap. Every run below overrides it, and that override is the subject. */
const DECLARED_CAP = 40;

/** A pinned-looking sha for seeded targets nothing ever clones. */
const FAKE_SHA = 'a'.repeat(40);

let sourceRepo = '';
let revision = '';

/** `git` with identity forced inline — the test must not depend on the host's config. */
async function git(args: string[], cwd: string) {
  const r = await run(
    ['git', '-c', 'user.email=keel@example.invalid', '-c', 'user.name=keel test', '-c', 'commit.gpgsign=false', ...args],
    { cwd },
  );
  if (r.code !== 0) throw new Error(`git ${args.join(' ')} failed: ${r.stderr || r.stdout}`);
  return r.stdout.trim();
}

interface SummaryEntry {
  name: string;
  cap?: number | null;
  capped: boolean;
  nodesSampled: number | null;
  nodesJudged: number | null;
}
interface Summary {
  nodeCap: number;
  nodeCapDeclared: number;
  corpusFile: string;
  runOrder: string[];
  entries: SummaryEntry[];
  notes: string[];
}

/**
 * A workspace is a corpus file, a reports dir and a place for stepper state.
 * Every corpus invocation is pointed at it via KEEL_REPO_ROOT; without that the
 * script would resolve its workspace from the skill's location and write into
 * the repo running the test.
 */
function workspace(files: Record<string, string>) {
  // --probe-dir REPLACES the defaults, so an empty dir isolates the run from
  // whatever probes the developer's machine happens to carry.
  const root = tree({ ...files, 'probes/.keep': '' });
  const probes = join(root, 'probes');
  return {
    root,
    probes,
    corpus(...args: string[]) {
      return run(['bun', CORPUS_TS, '--corpus', join(root, 'corpus.json'), ...args], {
        cwd: root,
        env: { ...(process.env as Record<string, string>), KEEL_REPO_ROOT: root },
      });
    },
    summaryPath: join(root, 'reports', 'corpus-summary.json'),
    summary(): Summary {
      const p = join(root, 'reports', 'corpus-summary.json');
      expect(existsSync(p)).toBe(true);
      return JSON.parse(readFileSync(p, 'utf8')) as Summary;
    },
    /** Write a summary that some earlier version of corpus.ts left behind. */
    seedSummary(summary: unknown) {
      mkdirSync(join(root, 'reports'), { recursive: true });
      writeFileSync(join(root, 'reports', 'corpus-summary.json'), `${JSON.stringify(summary, null, 2)}\n`);
    },
    /**
     * Stand in for the agent: read the batch corpus.ts left pending and answer
     * every node with `unknown`. `unknown` is the honest verdict for a synthetic
     * node nobody argued about, and it fails closed — a fixture that answered
     * `anchored` would be modelling exactly the default this project calls a bug.
     */
    judgePending(name: string): number {
      const pendingPath = join(root, '.keel-corpus', `${name}.pending.json`);
      expect(existsSync(pendingPath)).toBe(true);
      const pending = JSON.parse(readFileSync(pendingPath, 'utf8')) as { nodes: Node[] };
      const verdicts = pending.nodes.map((n) => ({
        nodeId: n.id,
        class: 'unknown',
        writeBoundary: {
          producer: 'test fixture',
          actorCanWrite: null,
          argument: 'synthetic node in a cap-provenance fixture; nobody argued the boundary',
        },
        evidence: [],
        confidence: 0.5,
        decidedBy: 'agent',
      }));
      writeFileSync(join(root, '.keel-corpus', `${name}.verdicts.json`), JSON.stringify(verdicts, null, 2));
      return verdicts.length;
    },
  };
}

function corpusFile(nodeCap: number, targets: { name: string; url: string; revision: string }[]): string {
  return `${JSON.stringify({ nodeCap, targets }, null, 2)}\n`;
}

/**
 * An entry in the shape corpus.ts wrote BEFORE `entry.cap` existed: no `cap`
 * key at all, and `capped` + `nodesSampled` as the only surviving trace of what
 * bound the sample. Faithful to reports/corpus-summary.json — anything that
 * quietly added a `cap` here would test the easy half of the problem.
 */
function legacyEntry(name: string, nodesSampled: number, nodesTotal: number, at: string) {
  const gatheredNothing = nodesTotal === 0;
  return {
    name,
    url: `https://github.com/example/${name}.git`,
    revision: FAKE_SHA,
    status: gatheredNothing ? 'nothing_gathered' : 'ok',
    runIndex: null,
    recordedAt: at,
    ratio: gatheredNothing ? null : 0.5,
    anchored: gatheredNothing ? null : 1,
    selfReferential: gatheredNothing ? null : 1,
    unknown: gatheredNothing ? null : 0,
    notACheck: gatheredNothing ? null : 0,
    nodesTotal,
    nodesSampled,
    nodesJudged: nodesSampled,
    nodesUnjudged: 0,
    partial: false,
    judgedFraction: gatheredNothing ? null : 1,
    capped: nodesSampled < nodesTotal,
    coverageGathered: {},
    coverageJudged: {},
    probeShare: 0,
    economics: null,
    warnings: [],
  };
}

/**
 * The committed corpus, entry for entry: twelve targets truncated at 25, two
 * that finished under the cap (12 of 12 and 21 of 21) and one that gathered
 * nothing. Only the twelve prove a cap.
 */
const LEGACY_ROWS: [string, number, number][] = [
  ['keel', 25, 32],
  ['anthropic-sdk-python', 25, 41],
  ['openai-python', 25, 95],
  ['vercel-ai', 25, 1014],
  ['aider', 25, 62],
  ['browser-use', 25, 104],
  ['mcp-python-sdk', 25, 121],
  ['simonw-llm', 25, 38],
  ['tiktoken', 12, 12],
  ['requests', 25, 106],
  ['flask', 25, 59],
  ['sinatra', 25, 59],
  ['commander-js', 21, 21],
  ['anthropic-quickstarts', 25, 62],
  ['anthropic-courses', 0, 0],
];

function legacySummary(declared: number, header: number) {
  const entries = LEGACY_ROWS.map(([name, sampled, total], i) =>
    legacyEntry(name, sampled, total, `2026-07-25T0${Math.floor(i / 10)}:${String(i % 10).padStart(2, '0')}:00.000Z`),
  );
  return {
    generatedAt: '2026-07-25T03:59:42.265Z',
    corpusFile: '<repo>/corpus.json',
    // The contradiction as committed: a header naming the DECLARED cap above
    // twelve entries that were each truncated at 25.
    nodeCap: header,
    nodeCapDeclared: declared,
    corpusOrder: LEGACY_ROWS.map(([n]) => n),
    runOrder: LEGACY_ROWS.map(([n]) => n),
    entries,
    totals: null,
    repeatability: [],
    notes: [],
  };
}

beforeAll(async () => {
  sourceRepo = tree({ '.github/workflows/ci.yml': WORKFLOW });
  await git(['init', '-q', '-b', 'main', '.'], sourceRepo);
  await git(['add', '-A'], sourceRepo);
  await git(['commit', '-q', '-m', 'fixture'], sourceRepo);
  revision = await git(['rev-parse', 'HEAD'], sourceRepo);
  expect(revision).toMatch(/^[0-9a-f]{40}$/);
});

afterAll(cleanupTrees);

// ---------------------------------------------------------------------------
// The live stepper: two targets, judged and recorded under two different caps.
// ---------------------------------------------------------------------------

describe('corpus · the summary records the cap that was in force', () => {
  let ws: ReturnType<typeof workspace>;

  beforeAll(() => {
    ws = workspace({
      'corpus.json': corpusFile(DECLARED_CAP, [
        { name: 'alpha', url: `file://${sourceRepo}`, revision },
        { name: 'beta', url: `file://${sourceRepo}`, revision },
        { name: 'gamma', url: `file://${sourceRepo}`, revision },
      ]),
    });
  });

  test('`record` writes the effective cap, not the one corpus.json declares', async () => {
    const next = await ws.corpus('next', '--cap', '2', '--probe-dir', ws.probes);
    expect(next.code).toBe(0);
    expect(next.stdout).toContain('alpha');

    const judged = ws.judgePending('alpha');
    expect(judged).toBe(2); // the cap actually bound the sample

    const rec = await ws.corpus('record', 'alpha', '--probe-dir', ws.probes);
    expect(rec.code).toBe(0);

    const summary = ws.summary();
    const alpha = summary.entries.find((e) => e.name === 'alpha');
    expect(alpha).toBeDefined();

    // The identity that the defect breaks: a capped sample is exactly as large
    // as the cap that produced it. Against the old code this reads 2 vs 40.
    expect(alpha?.capped).toBe(true);
    expect(alpha?.nodesSampled).toBe(summary.nodeCap);

    // ... and both halves of the provenance survive, so a reader can see that
    // an override happened rather than having to infer it.
    expect(summary.nodeCap).toBe(2);
    expect(summary.nodeCapDeclared).toBe(DECLARED_CAP);
    expect(alpha?.cap).toBe(2);
    expect(summary.notes.some((n) => n.includes('OVERRODE THE DECLARED CAP'))).toBe(true);
  }, 60_000);

  test('`status` reports the cap in force and names the declared one beside it', async () => {
    const st = await ws.corpus('status');
    expect(st.code).toBe(0);
    expect(st.stdout).toContain('node cap 2 in force');
    expect(st.stdout).toContain(`declares ${DECLARED_CAP}`);
  }, 30_000);

  test('a second cap does not silently re-describe the first target', async () => {
    const next = await ws.corpus('next', '--cap', '3', '--probe-dir', ws.probes);
    expect(next.code).toBe(0);
    expect(next.stdout).toContain('skip alpha');

    expect(ws.judgePending('beta')).toBe(3);
    const rec = await ws.corpus('record', 'beta', '--probe-dir', ws.probes);
    expect(rec.code).toBe(0);

    const summary = ws.summary();
    const byName = new Map(summary.entries.map((e) => [e.name, e]));
    // Each entry keeps the cap its own sample was drawn under. A header field
    // alone cannot express this, which is why entry.cap exists.
    expect(byName.get('alpha')?.cap).toBe(2);
    expect(byName.get('beta')?.cap).toBe(3);
    expect(byName.get('alpha')?.nodesSampled).toBe(2);
    expect(byName.get('beta')?.nodesSampled).toBe(3);
    // The header follows the most recently recorded entry. A summary that only
    // stamped its cap at creation would still be advertising 2 here — the same
    // staleness as the original bug, one write later.
    expect(summary.nodeCap).toBe(3);
    expect(summary.notes.some((n) => n.includes('NOT ALL RECORDED UNDER THE SAME CAP'))).toBe(true);

    const st = await ws.corpus('status');
    expect(st.stdout).toContain('entries were recorded under different caps (2, 3)');
  }, 60_000);

  test('`record` REFUSES --cap rather than parsing it and dropping it', async () => {
    // A REAL pending run, so the refusal is the only thing that can stop the
    // record. `--cap` used to be parsed here and thrown away: the sample was
    // already drawn at 2, the operator asked for 9, and the entry landed
    // reading 2 with nothing said about the number they typed.
    const next = await ws.corpus('next', '--cap', '2', '--probe-dir', ws.probes);
    expect(next.code).toBe(0);
    expect(next.stdout).toContain('next → gamma');
    expect(ws.judgePending('gamma')).toBe(2);

    const rec = await ws.corpus('record', 'gamma', '--cap', '9', '--probe-dir', ws.probes);
    expect(rec.code).toBe(1);
    expect(rec.stderr).toContain('record does not take --cap');
    // Refused before recording anything, and the header is untouched.
    const summary = ws.summary();
    expect(summary.entries.some((e) => e.name === 'gamma')).toBe(false);
    expect(summary.nodeCap).toBe(3);

    // Without the flag the same pending run records normally, at the cap that
    // actually drew it.
    const ok = await ws.corpus('record', 'gamma', '--probe-dir', ws.probes);
    expect(ok.code).toBe(0);
    expect(ws.summary().entries.find((e) => e.name === 'gamma')?.cap).toBe(2);
  }, 60_000);
});

// ---------------------------------------------------------------------------
// The regression the invocation-sourced fix left behind: a later command that
// measures nothing, run over entries it did not write.
// ---------------------------------------------------------------------------

describe('corpus · a command that sampled nothing does not speak for the header', () => {
  let ws: ReturnType<typeof workspace>;

  beforeAll(() => {
    ws = workspace({
      'corpus.json': corpusFile(
        DECLARED_CAP,
        LEGACY_ROWS.map(([name]) => ({
          name,
          url: `https://github.com/example/${name}.git`,
          revision: FAKE_SHA,
        })),
      ),
    });
    // Exactly the committed artifact: header 40, twelve entries truncated at 25.
    ws.seedSummary(legacySummary(DECLARED_CAP, DECLARED_CAP));
  });

  test('`status` recovers the real cap from the entries without waiting for a write', async () => {
    const before = await ws.corpus('status');
    expect(before.code).toBe(0);
    expect(before.stdout).toContain('node cap 25 in force');
    expect(before.stdout).toContain(`declares ${DECLARED_CAP}`);
    // Untouched on disk — status is a read. The stale header is still there.
    expect(JSON.parse(readFileSync(ws.summaryPath, 'utf8')).nodeCap).toBe(DECLARED_CAP);
  }, 30_000);

  test('a bare `next` over a finished corpus derives the cap from the entries', async () => {
    // Every target is already recorded, so this clones nothing and judges
    // nothing. It is the command that used to restore `nodeCap: 40`.
    const next = await ws.corpus('next', '--probe-dir', ws.probes);
    expect(next.code).toBe(0);
    expect(next.stdout).toContain('nothing left to run');

    const summary = ws.summary();
    // 25 is nowhere in the invocation, nowhere in corpus.json and nowhere in
    // the seeded header. It comes from the twelve truncated entries.
    expect(summary.nodeCap).toBe(25);
    expect(summary.nodeCapDeclared).toBe(DECLARED_CAP);
    expect(summary.notes.some((n) => n.includes('OVERRODE THE DECLARED CAP'))).toBe(true);
    // The three that prove nothing are disclosed, not guessed at: tiktoken
    // (12 of 12), commander-js (21 of 21) and anthropic-courses (0 gathered).
    expect(
      summary.notes.some((n) => n.includes(`3 of ${LEGACY_ROWS.length} entries do not state the cap`)),
    ).toBe(true);
    // Nothing was re-measured, so no entry moved.
    expect(summary.entries.length).toBe(LEGACY_ROWS.length);
    expect(summary.entries.find((e) => e.name === 'tiktoken')?.nodesSampled).toBe(12);
    expect(summary.entries.find((e) => e.name === 'commander-js')?.nodesSampled).toBe(21);
  }, 60_000);

  test('a header no entry can prove is left alone, not overwritten by the invocation', async () => {
    // Only the entries that prove NOTHING — both complete under whatever cap
    // was in force. The header is the sole surviving record of that cap, and a
    // command that enforced nothing must not replace it with its own number.
    const rows: [string, number, number][] = [
      ['tiktoken', 12, 12],
      ['commander-js', 21, 21],
    ];
    const ws = workspace({
      'corpus.json': corpusFile(
        DECLARED_CAP,
        rows.map(([name]) => ({ name, url: `https://github.com/example/${name}.git`, revision: FAKE_SHA })),
      ),
    });
    ws.seedSummary({
      ...legacySummary(DECLARED_CAP, 25),
      corpusOrder: rows.map(([n]) => n),
      runOrder: rows.map(([n]) => n),
      entries: rows.map(([name, sampled, total], i) =>
        legacyEntry(name, sampled, total, `2026-07-25T01:0${i}:00.000Z`),
      ),
    });

    // --cap 9 is loud, deliberate, and binds nothing: both targets are already
    // recorded. Handing 9 (or the declared 40) to the header would be a
    // provenance field invented by a shell.
    const next = await ws.corpus('next', '--cap', '9', '--probe-dir', ws.probes);
    expect(next.code).toBe(0);
    expect(next.stdout).toContain('nothing left to run');

    const summary = ws.summary();
    expect(summary.nodeCap).toBe(25);
    expect(summary.nodeCapDeclared).toBe(DECLARED_CAP);
    expect(summary.notes.some((n) => n.includes('2 of 2 entries do not state the cap'))).toBe(true);
  }, 60_000);

  test('a write from a different corpus file discloses that it repointed the provenance', async () => {
    const ws = workspace({
      'corpus.json': corpusFile(DECLARED_CAP, [
        { name: 'tiktoken', url: 'https://github.com/example/tiktoken.git', revision: FAKE_SHA },
      ]),
    });
    ws.seedSummary({
      ...legacySummary(DECLARED_CAP, 25),
      corpusOrder: ['tiktoken'],
      runOrder: ['tiktoken'],
      entries: [legacyEntry('tiktoken', 12, 12, '2026-07-25T01:00:00.000Z')],
    });

    const next = await ws.corpus('next', '--probe-dir', ws.probes);
    expect(next.code).toBe(0);
    const summary = ws.summary();
    // The seeded summary was created from '<repo>/corpus.json'; this write came
    // from the workspace's own path. Repointing is fine — doing it silently was
    // not, because the entries below still came from the other file.
    expect(summary.corpusFile).toBe(join(ws.root, 'corpus.json'));
    expect(summary.notes.some((n) => n.includes('REPOINTED corpusFile'))).toBe(true);
    expect(summary.notes.some((n) => n.includes('<repo>/corpus.json'))).toBe(true);
  }, 60_000);
});

// ---------------------------------------------------------------------------
// Mixed-cap disclosure over entries that predate `entry.cap`.
// ---------------------------------------------------------------------------

describe('corpus · the mixed-cap warning reaches entries written before entry.cap existed', () => {
  test('recording one new target over the committed summary warns about all of them', async () => {
    const ws = workspace({
      'corpus.json': corpusFile(DECLARED_CAP, [{ name: 'alpha', url: `file://${sourceRepo}`, revision }]),
    });
    ws.seedSummary(legacySummary(DECLARED_CAP, DECLARED_CAP));

    const next = await ws.corpus('next', '--cap', '2', '--probe-dir', ws.probes);
    expect(next.code).toBe(0);
    expect(ws.judgePending('alpha')).toBe(2);
    const rec = await ws.corpus('record', 'alpha', '--probe-dir', ws.probes);
    expect(rec.code).toBe(0);

    const summary = ws.summary();
    expect(summary.entries.length).toBe(LEGACY_ROWS.length + 1);
    expect(summary.entries.find((e) => e.name === 'alpha')?.cap).toBe(2);
    // The header follows the newest measurement — and it now contradicts twelve
    // rows sampled at 25. That contradiction is exactly what the warning is
    // for, and filtering entries on `typeof cap === 'number'` dropped every one
    // of the rows that needed it, leaving the first new record silent.
    expect(summary.nodeCap).toBe(2);
    const mixed = summary.notes.find((n) => n.includes('NOT ALL RECORDED UNDER THE SAME CAP'));
    expect(mixed).toBeDefined();
    expect(mixed).toContain('(2, 25)');

    const st = await ws.corpus('status');
    expect(st.stdout).toContain('entries were recorded under different caps (2, 25)');
  }, 60_000);
});

/**
 * ONE CORPUS FILE, ONE SUMMARY.
 *
 * `--corpus <path>` exists so a differently-constituted corpus can be run —
 * agent-maintained targets against the human-maintained fifteen, which is the
 * whole point of the flag. The summary path was a module CONSTANT, so the second
 * run appended into the first one's artifact: two populations and two
 * methodologies averaged into one pooled ratio that describes neither.
 *
 * It is the quietest possible corruption. The file stays valid JSON, every entry
 * is individually true, and the only symptom is that a published number moves.
 * The original corpus additionally depends on a recorded ORDER — the
 * crystallization curve is a claim about cost falling as the probe library
 * grows — so interleaving a second corpus's entries destroys a result that
 * cannot be recovered from the merged file.
 *
 * Derivation is the fix rather than a flag, because a flag can be forgotten and
 * a derivation cannot.
 */
describe('corpus · a second corpus file cannot write into the first summary', () => {
  const workspace = tree({
    'corpus.json': JSON.stringify({ nodeCap: 25, targets: [] }),
    'corpus-agentic.json': JSON.stringify({ nodeCap: 25, targets: [] }),
    // A summary in the shape the committed one has, belonging to corpus.json.
    'reports/corpus-summary.json': JSON.stringify({
      generatedAt: '2026-07-25T00:00:00.000Z',
      corpusFile: '<repo>/corpus.json',
      nodeCap: 25,
      corpusOrder: ['alpha'],
      runOrder: ['alpha'],
      entries: [
        {
          name: 'alpha',
          url: 'https://example.invalid/alpha.git',
          revision: 'a'.repeat(40),
          status: 'ok',
          runIndex: 0,
          ratio: 1,
          anchored: 3,
          selfReferential: 0,
          unknown: 0,
          notACheck: 1,
          nodesTotal: 4,
          nodesSampled: 4,
          nodesJudged: 4,
          capped: false,
          cap: 25,
        },
      ],
      totals: {},
      notes: [],
    }),
  });
  const env = { ...(process.env as Record<string, string>), KEEL_REPO_ROOT: workspace };

  test('the second corpus starts empty instead of inheriting the first run order', async () => {
    const r = await run([process.execPath, CORPUS_TS, 'status', '--corpus', 'corpus-agentic.json'], {
      cwd: workspace,
      env,
    });
    expect(r.code).toBe(0);
    // The failure this guards: "run order so far: alpha".
    expect(r.stdout).not.toContain('alpha');
    expect(r.stdout).toContain('(none)');
  }, 60_000);

  test('the original corpus still reads its own summary, unmoved', async () => {
    const r = await run([process.execPath, CORPUS_TS, 'status'], { cwd: workspace, env });
    expect(r.code).toBe(0);
    expect(r.stdout).toContain('alpha');
  }, 60_000);

  test('the derived path keeps the existing artifact exactly where it is', () => {
    // corpus.json -> corpus-summary.json is the identity the repo already has on
    // disk; if this mapping ever changes, reports/corpus-summary.json is orphaned
    // and every published link to it breaks.
    expect(existsSync(join(workspace, 'reports', 'corpus-summary.json'))).toBe(true);
    expect(existsSync(join(workspace, 'reports', 'corpus-agentic-summary.json'))).toBe(false);
  });
});
