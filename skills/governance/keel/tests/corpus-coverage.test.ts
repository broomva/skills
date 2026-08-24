/**
 * THE CORPUS CARRIES ITS OWN BLINDNESS.
 *
 * `gather` learned to record surfaces it recognises and cannot read, and
 * `render` learned to show them beside the ratio. `corpus.ts` imported plain
 * `gather()` and threw the record away, so the one artifact that most needed the
 * disclosure — a published corpus number — was the only one that never carried
 * it.
 *
 * The worked example is aspect-cli, measured at 1.000. Its
 * `.buildkite/pipeline.yaml` holds `bazelrc-e2e`, a gate the repository's own
 * comment says exists nowhere else *by design*: "intentionally NOT ported
 * here… It stays a Buildkite-only test on main." Keel has no Buildkite parser
 * and no Bazel parser, so that gate cannot appear in any verdict, and the 1.000
 * was published with nothing beside it saying which provider had been skipped.
 * Re-gathered, that repository reports 43 unread surfaces.
 *
 * The record travels as a SIBLING (`<report>.coverage.json`) rather than a
 * Report field, because `schemas/keel.ts` is frozen — and the sibling is the
 * channel `render.ts` already reads when no `--coverage` is passed, so a corpus
 * artifact and a hand-rendered one disclose blindness identically.
 *
 * These tests drive the real stepper against a git repository built on disk,
 * because the bug lived in the seam between two commands in two processes.
 */

import { afterAll, beforeAll, describe, expect, test } from 'bun:test';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join, resolve } from 'node:path';
import type { Node } from '../schemas/keel.ts';
import { cleanupTrees, run, tree } from './helpers/tree.ts';

const CORPUS_TS = resolve(import.meta.dir, '../scripts/corpus.ts');

const WORKFLOW = `name: ci
on: [push]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - run: pytest -q
`;

/** A pipeline in a provider this gatherer has no parser for. */
const BUILDKITE = `steps:
  - label: ":bazel: e2e"
    command: "bazel test //..."
`;

let sourceRepo: string;
let revision: string;

/**
 * Identity is passed per-invocation, never assumed. A fresh CI runner has no
 * `user.email`, so a bare `git commit` fails there and succeeds on any developer
 * machine — which is the shape that gets a test merged green and then breaks the
 * lane. Signing is disabled for the same reason: a maintainer with `gpgsign`
 * on globally would otherwise be prompted by a unit test.
 */
async function git(args: string[], cwd: string): Promise<string> {
  const r = await run(
    [
      'git',
      '-c',
      'user.email=keel@example.invalid',
      '-c',
      'user.name=keel test',
      '-c',
      'commit.gpgsign=false',
      ...args,
    ],
    { cwd },
  );
  expect(r.code).toBe(0);
  return r.stdout.trim();
}

beforeAll(async () => {
  sourceRepo = tree({
    '.github/workflows/ci.yml': WORKFLOW,
    '.buildkite/pipeline.yml': BUILDKITE,
  });
  await git(['init', '-q', '-b', 'main', '.'], sourceRepo);
  await git(['add', '-A'], sourceRepo);
  await git(['commit', '-q', '-m', 'fixture'], sourceRepo);
  revision = await git(['rev-parse', 'HEAD'], sourceRepo);
  expect(revision).toMatch(/^[0-9a-f]{40}$/);
});

afterAll(cleanupTrees);

describe('corpus · the coverage record reaches the published report', () => {
  let root: string;

  const corpus = (...args: string[]) =>
    run(['bun', CORPUS_TS, '--corpus', join(root, 'corpus.json'), ...args], {
      cwd: root,
      env: { ...(process.env as Record<string, string>), KEEL_REPO_ROOT: root },
    });

  beforeAll(async () => {
    root = tree({
      'probes/.keep': '',
      'corpus.json': `${JSON.stringify(
        { nodeCap: 25, targets: [{ name: 'alpha', url: `file://${sourceRepo}`, revision }] },
        null,
        2,
      )}\n`,
    });
    const next = await corpus('next');
    expect(next.code).toBe(0);

    // Stand in for the agent: `unknown` on every node. It is the honest verdict
    // for a synthetic node nobody argued about, and it fails closed — a fixture
    // answering `anchored` would model the default this project calls a bug.
    const pending = JSON.parse(
      readFileSync(join(root, '.keel-corpus', 'alpha.pending.json'), 'utf8'),
    ) as { nodes: Node[] };
    writeFileSync(
      join(root, '.keel-corpus', 'alpha.verdicts.json'),
      JSON.stringify(
        pending.nodes.map((n) => ({
          nodeId: n.id,
          class: 'unknown',
          writeBoundary: {
            producer: 'test fixture',
            actorCanWrite: null,
            argument: 'synthetic node in a coverage fixture; nobody argued the boundary',
          },
          evidence: [],
          confidence: 0.5,
          decidedBy: 'agent',
        })),
        null,
        2,
      ),
    );
    const rec = await corpus('record', 'alpha');
    expect(rec.code).toBe(0);
  }, 120_000);

  test('record writes a coverage sibling beside the report', () => {
    expect(existsSync(join(root, 'reports', 'alpha.json'))).toBe(true);
    expect(existsSync(join(root, 'reports', 'alpha.coverage.json'))).toBe(true);
  });

  test('the sibling names the provider the gatherer could not read', () => {
    const c = JSON.parse(readFileSync(join(root, 'reports', 'alpha.coverage.json'), 'utf8'));
    // The schema tag is load-bearing: render.ts refuses an unlabelled blob, so a
    // sibling written without it would be silently ignored and this whole
    // mechanism would be decorative.
    expect(c.schema).toBe('keel.gather-coverage.v1');
    const unread = (c.unread as Array<{ path: string; tool: string }>).map((u) => u.tool);
    expect(unread).toContain('Buildkite');
  });

  test('the surface it CAN read is not reported as blindness', () => {
    // An unread list that over-reports is its own dishonesty, and it is the
    // shape that rots quietest — nobody re-checks a warning.
    const c = JSON.parse(readFileSync(join(root, 'reports', 'alpha.coverage.json'), 'utf8'));
    const paths = (c.unread as Array<{ path: string }>).map((u) => u.path);
    expect(paths.some((p) => p.includes('.github'))).toBe(false);

    const report = JSON.parse(readFileSync(join(root, 'reports', 'alpha.json'), 'utf8'));
    const sources = new Set((report.nodes as Node[]).map((n) => n.source.split(':')[0]));
    expect([...sources].some((s) => s.startsWith('.github/workflows'))).toBe(true);
  });

  test('the rendered page carries the disclosure beside the ratio', async () => {
    // End to end, because the sibling existing proves nothing if the renderer
    // never finds it: render with NO --coverage flag and let it resolve the
    // sibling the way a reader would.
    const RENDER_TS = resolve(import.meta.dir, '../scripts/render.ts');
    const out = join(root, 'alpha.html');
    const r = await run(['bun', RENDER_TS, join(root, 'reports', 'alpha.json'), '-o', out]);
    expect(r.code).toBe(0);
    const html = readFileSync(out, 'utf8');
    expect(html).toContain('Buildkite');
    expect(html.toLowerCase()).toContain('unread');
  }, 60_000);
});
