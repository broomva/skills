/**
 * Fixture trees, built on disk at run time.
 *
 * Deliberately NOT committed under `tests/fixtures/`: `gather` walks whatever it
 * is pointed at, and Keel's headline artifact is a measurement of THIS repo. A
 * committed tree of fake workflows, Makefiles and pyproject files would enlarge
 * Keel's own gathered surface with edges nobody ever judged — i.e. it would move
 * the number this project publishes about itself. A temp dir keeps the fixture
 * literal (it is right here in the test that asserts on it) and keeps the
 * measured repo honest.
 */

import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { dirname, join } from 'node:path';

const created: string[] = [];

/** Materialize `{ 'rel/path': contents }` into a fresh temp dir; returns its path. */
export function tree(files: Record<string, string>): string {
  const root = mkdtempSync(join(tmpdir(), 'keel-test-'));
  created.push(root);
  for (const [rel, body] of Object.entries(files)) {
    const path = join(root, rel);
    mkdirSync(dirname(path), { recursive: true });
    writeFileSync(path, body, 'utf8');
  }
  return root;
}

/** Every tree this process made. Call from `afterAll`. */
export function cleanupTrees(): void {
  for (const dir of created.splice(0)) {
    rmSync(dir, { recursive: true, force: true });
  }
}

/** Run a command to completion, capturing both streams. No shell, no network. */
export async function run(
  cmd: string[],
  opts: { cwd?: string; env?: Record<string, string> } = {},
): Promise<{ code: number; stdout: string; stderr: string }> {
  const proc = Bun.spawn(cmd, {
    cwd: opts.cwd,
    env: opts.env ?? (process.env as Record<string, string>),
    stdout: 'pipe',
    stderr: 'pipe',
  });
  const [stdout, stderr, code] = await Promise.all([
    new Response(proc.stdout).text(),
    new Response(proc.stderr).text(),
    proc.exited,
  ]);
  return { code, stdout, stderr };
}
