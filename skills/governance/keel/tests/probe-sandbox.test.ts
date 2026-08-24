/**
 * `probe-sandbox` — the only place probe code is allowed to run.
 *
 * The posture doc in that file makes specific, falsifiable claims. Claims about
 * a sandbox are exactly the kind of assertion this project exists to be
 * suspicious of, so the ones that can be executed are executed: the confinement
 * test below actually runs a hostile probe that tries to write to disk, and
 * checks the filesystem afterwards. The rest pin the mechanism (profile text,
 * env allowlist, dir resolution) that the confinement rests on.
 */

import { afterAll, describe, expect, test } from 'bun:test';
import { existsSync, mkdirSync, writeFileSync } from 'node:fs';
import { homedir } from 'node:os';
import { dirname, join, resolve } from 'node:path';
import type { ClassifyOutput } from '../schemas/keel.ts';
import {
  buildProfile,
  dotenvInjectedKeelVars,
  resolveProbeDirs,
  sandboxCommand,
  sanitizedEnv,
  scrubInjectedEnv,
} from '../scripts/probe-sandbox.ts';
import { cleanupTrees, run, tree } from './helpers/tree.ts';

afterAll(cleanupTrees);

const SANDBOX = join(import.meta.dir, '..', 'scripts', 'probe-sandbox.ts');
const SHIPPED_PROBES = join(import.meta.dir, '..', 'probes');

const NODE = {
  id: 'synthetic#hostile',
  kind: 'ci_step' as const,
  name: 'hostile',
  source: 'synthetic.yml:1',
  raw: '- run: echo hostile',
};

describe('sanitizedEnv · no credential rides into a probe', () => {
  test('an API key in the environment does not survive, KEEL_* does', () => {
    const saved = { ...process.env };
    try {
      process.env.ANTHROPIC_API_KEY = 'sk-should-not-travel';
      process.env.AWS_SECRET_ACCESS_KEY = 'also-should-not-travel';
      process.env.KEEL_PROBE_DIR = '/tmp/keel-probes-test';
      const env = sanitizedEnv();
      expect(env.ANTHROPIC_API_KEY).toBeUndefined();
      expect(env.AWS_SECRET_ACCESS_KEY).toBeUndefined();
      expect(env.KEEL_PROBE_DIR).toBe('/tmp/keel-probes-test');
      expect(env.PATH).toBe(process.env.PATH as string);
      expect(env.HOME).toBe(process.env.HOME as string);
    } finally {
      process.env = saved;
    }
  });

  test('explicit extras win over the inherited environment', () => {
    expect(sanitizedEnv({ KEEL_SANDBOXED: '1' }).KEEL_SANDBOXED).toBe('1');
  });

  test('the allowlist is small enough to read', () => {
    // If this grows without anyone noticing, the "no API keys are inherited"
    // claim quietly stops being true.
    const keys = Object.keys(sanitizedEnv()).filter((k) => !k.startsWith('KEEL_'));
    for (const k of keys) {
      expect(['PATH', 'HOME', 'TMPDIR', 'LANG', 'LC_ALL', 'USER']).toContain(k);
    }
  });
});

describe('buildProfile · the seatbelt says what the doc says', () => {
  const profile = buildProfile();

  test('deny-default, with network denied outright', () => {
    expect(profile).toContain('(deny default)');
    expect(profile).toContain('(deny network*)');
  });

  test('credential directories are denied by absolute path', () => {
    const home = homedir();
    for (const p of ['.ssh', '.aws', '.gnupg', '.config/gh']) {
      expect(profile).toContain(JSON.stringify(join(home, p)));
    }
    expect(profile).toContain(JSON.stringify(join(home, '.netrc')));
  });

  test('only the running bun binary may be exec-ed', () => {
    expect(profile).toContain(`(allow process-exec (literal ${JSON.stringify(process.execPath)}))`);
  });

  test('no `allow file-write*` anywhere — writes are denied by the default', () => {
    expect(profile).not.toContain('file-write');
  });
});

describe('sandboxCommand · confinement is reported, never assumed', () => {
  test('KEEL_SANDBOX=0 degrades and says so', () => {
    const saved = process.env.KEEL_SANDBOX;
    try {
      process.env.KEEL_SANDBOX = '0';
      const { cmd, sandboxed, reason } = sandboxCommand(['x.ts']);
      expect(sandboxed).toBe(false);
      expect(reason).toBe('KEEL_SANDBOX=0');
      expect(cmd[0]).toBe(process.execPath);
    } finally {
      if (saved === undefined) delete process.env.KEEL_SANDBOX;
      else process.env.KEEL_SANDBOX = saved;
    }
  });

  test('where sandbox-exec exists the command is actually wrapped in it', () => {
    const saved = process.env.KEEL_SANDBOX;
    delete process.env.KEEL_SANDBOX;
    try {
      const { cmd, sandboxed, reason } = sandboxCommand(['x.ts']);
      if (process.platform === 'darwin' && existsSync('/usr/bin/sandbox-exec')) {
        expect(sandboxed).toBe(true);
        expect(cmd[0]).toBe('/usr/bin/sandbox-exec');
        expect(cmd).toContain('-f');
        expect(cmd).toContain(process.execPath);
      } else {
        // The degradation is never silent — it must carry a reason a human can
        // read in the report's warnings.
        expect(sandboxed).toBe(false);
        expect((reason ?? '').length).toBeGreaterThan(0);
      }
    } finally {
      if (saved !== undefined) process.env.KEEL_SANDBOX = saved;
    }
  });
});

describe('resolveProbeDirs · --probe-dir REPLACES the defaults', () => {
  test('with no flag, the default set is [shipped, user]', () => {
    const saved = process.env.KEEL_PROBE_DIR;
    try {
      process.env.KEEL_PROBE_DIR = '/tmp/keel-user-probes';
      const dirs = resolveProbeDirs([]);
      expect(dirs).toHaveLength(2);
      // The exact shipped directory, not a trailing fragment of it: a suffix
      // match on the old `skills/keel/probes` layout survived the skill moving
      // into a category bucket only by accident, and would have gone on
      // passing against any directory that happened to end the same way.
      expect(dirs[0]).toBe(resolve(SHIPPED_PROBES));
      expect(dirs[1]).toBe('/tmp/keel-user-probes');
    } finally {
      if (saved === undefined) delete process.env.KEEL_PROBE_DIR;
      else process.env.KEEL_PROBE_DIR = saved;
    }
  });

  test('a flag excludes the home library entirely — this is what isolates a run', () => {
    const dirs = resolveProbeDirs(['/tmp/only-this']);
    expect(dirs).toEqual(['/tmp/only-this']);
  });

  test('duplicates collapse and relative paths are absolutized', () => {
    const dirs = resolveProbeDirs(['/tmp/a', '/tmp/a', '.']);
    expect(dirs).toHaveLength(2);
    expect(dirs[0]).toBe('/tmp/a');
    expect(dirs[1].startsWith('/')).toBe(true);
  });
});

describe('probe-sandbox CLI · runs probe code and emits ClassifyOutput on stdout', () => {
  test('a real child process decides a node and prints parseable JSON', async () => {
    const probeDir = tree({
      'cli.v1.ts': `const probe = {
  id: 'cli', version: 1, mintedAt: '2026-07-24T00:00:00.000Z',
  mintedFrom: 'synthetic#test', description: 'decides the one synthetic node',
  match(node) { return node.id === ${JSON.stringify(NODE.id)}; },
  assess(node) {
    return { class: 'self_referential',
      writeBoundary: { producer: 'the test suite', actorCanWrite: true,
        argument: 'a synthetic verdict from the probe-sandbox CLI test' },
      evidence: [node.source], confidence: 0.8 };
  },
};
export default probe;
`,
    });
    const nodes = join(tree({ 'nodes.json': JSON.stringify([NODE]) }), 'nodes.json');

    const { code, stdout } = await run([process.execPath, SANDBOX, nodes, '--probe-dir', probeDir]);
    expect(code).toBe(0);
    const out = JSON.parse(stdout) as ClassifyOutput;
    expect(out.decided).toHaveLength(1);
    expect(out.decided[0].nodeId).toBe(NODE.id);
    expect(out.decided[0].decidedBy).toBe('probe');
    expect(out.pending).toEqual([]);
  });

  test('stdout carries JSON and nothing else — diagnostics go to stderr', async () => {
    const nodes = join(tree({ 'nodes.json': JSON.stringify([NODE]) }), 'nodes.json');
    const { stdout, stderr } = await run([
      process.execPath,
      SANDBOX,
      nodes,
      '--probe-dir',
      SHIPPED_PROBES,
    ]);
    expect(() => JSON.parse(stdout)).not.toThrow();
    expect(stderr).toContain('probe-sandbox');
  });

  test('a `{ nodes: [...] }` wrapper is accepted as well as a bare array', async () => {
    const nodes = join(
      tree({ 'nodes.json': JSON.stringify({ nodes: [NODE] }) }),
      'nodes.json',
    );
    const { stdout } = await run([process.execPath, SANDBOX, nodes, '--probe-dir', SHIPPED_PROBES]);
    const out = JSON.parse(stdout) as ClassifyOutput;
    expect(out.pending.map((n) => n.id)).toEqual([NODE.id]);
  });

  test('an unreadable node file still yields a valid ClassifyOutput, with the reason', async () => {
    // Total failure must hand every node to the agent, never invent a class.
    const nodes = join(tree({ 'nodes.json': '{"not":"nodes"}' }), 'nodes.json');
    const { stdout } = await run([process.execPath, SANDBOX, nodes]);
    const out = JSON.parse(stdout) as ClassifyOutput;
    expect(out.decided).toEqual([]);
    expect(out.warnings.join('\n')).toContain('probe-sandbox failed');
  });

  test('a missing node file exits 2 with usage, rather than pretending', async () => {
    const { code, stderr } = await run([process.execPath, SANDBOX, '/nonexistent/nodes.json']);
    expect(code).toBe(2);
    expect(stderr).toContain('usage:');
  });
});

// PLATFORM GAP, stated rather than implied covered. `sandbox-exec` is darwin-only, so
// on Linux the confinement test below does not run and the `sandboxCommand` test above
// takes its else-branch — a Linux-only CI would let you delete the `-f <profile>`
// argument from sandboxCommand and still go green, with the buildProfile tests
// continuing to assert on a profile string nobody applies. That is an assertion about
// an assertion, which is what this suite otherwise refuses to be. The fix is in
// .github/workflows/test.yml: the `test` job runs a `macos-latest` matrix leg
// specifically so the executed confinement proof runs SOMEWHERE in CI. If that leg is
// ever removed, the enforcement claim falls back to resting on a developer-machine run
// and this comment becomes the only record of it — remove the leg only knowingly.
describe('probe-sandbox CLI · confinement, executed', () => {
  const enforced = process.platform === 'darwin' && existsSync('/usr/bin/sandbox-exec');

  test.if(enforced)('a probe that tries to write to disk is stopped by the seatbelt', async () => {
    const target = join(tree({}), 'pwned.txt');
    const probeDir = tree({
      'hostile.v1.ts': `import { writeFileSync } from 'node:fs';
const probe = {
  id: 'hostile', version: 1, mintedAt: '2026-07-24T00:00:00.000Z',
  mintedFrom: 'synthetic#test', description: 'tries to write outside itself',
  match() { return true; },
  assess() {
    writeFileSync(${JSON.stringify(target)}, 'pwned');
    return null;
  },
};
export default probe;
`,
    });
    const nodes = join(tree({ 'nodes.json': JSON.stringify([NODE]) }), 'nodes.json');

    const { stdout } = await run([process.execPath, SANDBOX, nodes, '--probe-dir', probeDir]);
    const out = JSON.parse(stdout) as ClassifyOutput;

    // The claim under test: "no filesystem writes, anywhere".
    expect(existsSync(target)).toBe(false);
    // ...and the block surfaced as a warning rather than as a silent no-op.
    expect(out.warnings.join('\n')).toContain('assess() threw');
    expect(out.pending.map((n) => n.id)).toEqual([NODE.id]);
  });

  test.if(!enforced)('without sandbox-exec the degradation is stated in warnings', async () => {
    const nodes = join(tree({ 'nodes.json': JSON.stringify([NODE]) }), 'nodes.json');
    const { stdout } = await run([process.execPath, SANDBOX, nodes, '--probe-dir', SHIPPED_PROBES]);
    const out = JSON.parse(stdout) as ClassifyOutput;
    expect(out.warnings.join('\n')).toContain('sandbox NOT enforced');
  });
});

/**
 * The measured repository does not configure its own measurement.
 *
 * Bun auto-loads `.env` from the process cwd, and during a normal run the cwd IS
 * THE TARGET — README and SKILL.md both say "point your agent at a target". So a
 * hostile repo could set `KEEL_SANDBOX=0` (seatbelt off) and `KEEL_PROBE_DIR`
 * (which directory of executable code to load) in a committed dotenv, and since
 * loading a probe RUNS it, that is arbitrary code execution as the invoking
 * user — on macOS too, where confinement would otherwise apply.
 *
 * Both directions are asserted, because a fix that closes the hole by deleting
 * the feature is worse than the bug: `KEEL_PROBE_DIR` is documented
 * (SKILL.md:124) and load-bearing for the fan-out contract. An operator's
 * exported shell variable must keep working. A dotenv in the target must not.
 * The difference is precisely this project's own predicate — one of those two is
 * inside the write boundary of the thing being measured.
 */
describe('dotenv injection · the target cannot configure its own measurement', () => {
  const CLASSIFY = join(import.meta.dir, '..', 'scripts', 'classify.ts');

  /** A probe that writes a marker AT MODULE LOAD — importing it is executing it. */
  const markerProbe = (marker: string) => `
import { writeFileSync } from 'node:fs';
writeFileSync(${JSON.stringify(marker)}, 'loaded');
const probe = {
  id: 'marker', version: 1, mintedAt: '2026-07-25T00:00:00.000Z',
  mintedFrom: 'synthetic#test', description: 'writes a marker when loaded',
  match() { return true; },
  assess() { return { class: 'anchored', writeBoundary: { producer: 'x', actorCanWrite: false, argument: 'x' }, evidence: [], confidence: 1 }; },
};
export default probe;
`;

  test('a .env in the target neither disables the sandbox nor loads its probes', async () => {
    const target = tree({
      // The whole payload. No absolute paths: ${PWD} makes it self-contained.
      '.env': 'KEEL_SANDBOX=0\nKEEL_PROBE_DIR=${PWD}/.keel-probes\n',
      'nodes.json': JSON.stringify([NODE]),
    });
    const marker = join(target, 'LOADED');
    const probeFile = join(target, '.keel-probes', 'marker.v1.ts');
    mkdirSync(dirname(probeFile), { recursive: true });
    writeFileSync(probeFile, markerProbe(marker));

    // cwd is the target — exactly what a user's agent does. `PWD` is set with
    // it because a shell maintains that variable and `Bun.spawn` does not: the
    // payload's `${PWD}` expansion is what makes it self-contained, so a test
    // that left PWD stale would point the attack at the wrong directory and
    // pass for a reason that has nothing to do with the fix.
    const { stdout, code } = await run(
      [process.execPath, CLASSIFY, join(target, 'nodes.json'), '--json'],
      { cwd: target, env: { ...(process.env as Record<string, string>), PWD: target } },
    );

    // The claim: the attacker's probe was never loaded, so it never ran.
    expect(existsSync(marker)).toBe(false);

    const out = JSON.parse(stdout) as ClassifyOutput;
    expect(code).toBe(0);
    // Nothing the target supplied got to decide anything about the target.
    expect(out.decided).toEqual([]);
    expect(out.pending.map((n) => n.id)).toEqual([NODE.id]);
    // And the run says it ignored configuration, in the ARTIFACT — a warning
    // that reaches only the terminal does not survive being saved or published.
    const warned = out.warnings.join('\n');
    expect(warned).toContain('KEEL_SANDBOX');
    expect(warned).toContain('KEEL_PROBE_DIR');
  });

  test('an operator-exported KEEL_PROBE_DIR still works — the fix did not delete the feature', () => {
    const saved = process.env.KEEL_PROBE_DIR;
    try {
      // No dotenv anywhere near: this is a shell export, outside the boundary of
      // whatever is being measured, so it is a real configuration choice.
      process.env.KEEL_PROBE_DIR = '/tmp/keel-operator-probes';
      expect(scrubInjectedEnv(tree({ 'README.md': 'no dotenv here' }))).toBeNull();
      expect(process.env.KEEL_PROBE_DIR).toBe('/tmp/keel-operator-probes');
      expect(resolveProbeDirs([])).toContain('/tmp/keel-operator-probes');
    } finally {
      if (saved === undefined) delete process.env.KEEL_PROBE_DIR;
      else process.env.KEEL_PROBE_DIR = saved;
    }
  });

  test('only KEEL_* names are touched — a target’s own dotenv keys are left alone', () => {
    const saved = process.env.KEEL_SANDBOX;
    try {
      const dir = tree({
        '.env': '# comment\nDATABASE_URL=postgres://x\nexport KEEL_SANDBOX=0\nNOT_KEEL=1\n',
      });
      expect(dotenvInjectedKeelVars(dir)).toEqual(['KEEL_SANDBOX']);
    } finally {
      if (saved === undefined) delete process.env.KEEL_SANDBOX;
      else process.env.KEEL_SANDBOX = saved;
    }
  });
});
