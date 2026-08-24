/**
 * `loadProbes` — locating and loading crystallized judgment.
 *
 * Loading a probe EXECUTES its file, so this module is the blast radius of the
 * probe library. The properties tested here are all of the "a broken probe must
 * not cost the run, and must not vanish quietly" family: probes are a cache
 * layer over agent judgment, and the pure-agentic path is the product.
 *
 * Every probe below is written to disk and really imported.
 */

import { afterAll, describe, expect, test } from 'bun:test';
import { join } from 'node:path';
import { loadProbes } from '../scripts/probe-loader.ts';
import { cleanupTrees, tree } from './helpers/tree.ts';

afterAll(cleanupTrees);

/** A syntactically valid, structurally complete probe. No imports: it is loaded
 * from a temp dir, and a relative type import would not resolve from there. */
function probeSrc(opts: {
  id: string;
  version: number;
  cls?: string;
  matches?: string;
  exportAs?: 'default' | 'named';
}): string {
  const cls = opts.cls ?? 'self_referential';
  const matches = opts.matches ?? 'true';
  const body = `const probe = {
  id: ${JSON.stringify(opts.id)},
  version: ${opts.version},
  mintedAt: '2026-07-24T00:00:00.000Z',
  mintedFrom: 'synthetic#test',
  description: 'a probe built by the test suite',
  match(node) { return ${matches}; },
  assess(node) {
    return {
      class: ${JSON.stringify(cls)},
      writeBoundary: {
        producer: 'the test suite',
        actorCanWrite: ${cls === 'anchored' ? 'false' : 'true'},
        argument: 'synthetic probe verdict produced by the keel test suite',
      },
      evidence: [node.source],
      confidence: 0.9,
    };
  },
};
`;
  return opts.exportAs === 'named' ? `${body}export { probe };\n` : `${body}export default probe;\n`;
}

describe('loadProbes · the zero-probe path is first-class', () => {
  test('a missing directory is "no probes", never an error', () => {
    // Fan-out isolation points KEEL_PROBE_DIR at a per-worktree dir that may not
    // exist yet. If that were an error, every run in a fresh checkout would
    // fail, and the honest fallback (judge everything agentically) would never
    // be reached.
    return loadProbes([join(tree({}), 'does', 'not', 'exist')]).then((r) => {
      expect(r.probes).toEqual([]);
      expect(r.warnings).toEqual([]);
    });
  });

  test('an empty directory loads cleanly', async () => {
    const { probes, warnings } = await loadProbes([tree({})]);
    expect(probes).toEqual([]);
    expect(warnings).toEqual([]);
  });

  test('no directories at all is not an error', async () => {
    expect(await loadProbes([])).toEqual({ probes: [], warnings: [] });
  });
});

describe('loadProbes · loading', () => {
  test('a valid probe loads through `export default` and through `export const probe`', async () => {
    const dir = tree({
      'alpha.v1.ts': probeSrc({ id: 'alpha', version: 1 }),
      'beta.v1.ts': probeSrc({ id: 'beta', version: 1, exportAs: 'named' }),
    });
    const { probes, warnings } = await loadProbes([dir]);
    expect(probes.map((p) => p.id).sort()).toEqual(['alpha', 'beta']);
    expect(warnings).toEqual([]);
    // The loaded object really is callable — it was executed, not just parsed.
    const node = { id: 'x#1', kind: 'ci_step' as const, name: 'x', source: 'x.yml:1', raw: 'run: x' };
    expect(probes[0].match(node)).toBe(true);
    expect(probes[0].assess(node)?.class).toBe('self_referential');
  });

  test('files that are not probes are skipped without comment', async () => {
    // Skipping a non-probe is not a dropped probe. A warning here would train
    // people to ignore warnings.
    const dir = tree({
      'README.md': '# probes live here\n',
      '_helpers.ts': 'export const x = 1;\n',
      '.hidden.ts': 'export default {};\n',
      'types.d.ts': 'export type X = 1;\n',
      'alpha.test.ts': 'export default {};\n',
      'real.v1.ts': probeSrc({ id: 'real', version: 1 }),
    });
    const { probes, warnings } = await loadProbes([dir]);
    expect(probes.map((p) => p.id)).toEqual(['real']);
    expect(warnings).toEqual([]);
  });
});

describe('loadProbes · a broken probe is skipped WITH A WARNING', () => {
  test('a syntax error does not take down the run', async () => {
    const dir = tree({
      'broken.v1.ts': 'export default { this is not typescript\n',
      'good.v1.ts': probeSrc({ id: 'good', version: 1 }),
    });
    const { probes, warnings } = await loadProbes([dir]);
    expect(probes.map((p) => p.id)).toEqual(['good']);
    expect(warnings.some((w) => w.includes('broken.v1.ts') && w.includes('failed to load'))).toBe(
      true,
    );
  });

  test('a module that throws at import time is skipped, not fatal', async () => {
    const dir = tree({
      'angry.v1.ts': 'throw new Error("probe module body exploded");\n',
      'good.v1.ts': probeSrc({ id: 'good', version: 1 }),
    });
    const { probes, warnings } = await loadProbes([dir]);
    expect(probes.map((p) => p.id)).toEqual(['good']);
    expect(warnings.some((w) => w.includes('exploded'))).toBe(true);
  });

  test('a module with no probe export is named in a warning', async () => {
    const dir = tree({ 'nothing.v1.ts': 'export const unrelated = 1;\n' });
    const { probes, warnings } = await loadProbes([dir]);
    expect(probes).toEqual([]);
    expect(warnings).toHaveLength(1);
    expect(warnings[0]).toContain('no `export default`');
  });

  test('a probe missing `assess` is rejected and says which field is missing', async () => {
    const dir = tree({
      'half.v1.ts': `export default {
  id: 'half', version: 1, mintedAt: 'x', mintedFrom: 'y', description: 'z',
  match() { return true; },
};
`,
    });
    const { probes, warnings } = await loadProbes([dir]);
    expect(probes).toEqual([]);
    expect(warnings[0]).toContain('missing `assess(node)`');
  });

  test('a probe with no metadata is rejected with every problem listed', async () => {
    const dir = tree({
      'bare.v1.ts': 'export default { match() { return true; }, assess() { return null; } };\n',
    });
    const { warnings } = await loadProbes([dir]);
    expect(warnings).toHaveLength(1);
    for (const field of ['id', 'mintedAt', 'mintedFrom', 'description', 'version']) {
      expect(warnings[0]).toContain(field);
    }
  });
});

describe('loadProbes · versioning', () => {
  test('the highest version wins and the shadowed one is named', async () => {
    // A probe that silently replaced its predecessor would erase the only
    // record of what a human once reviewed.
    const dir = tree({
      'dup.v1.ts': probeSrc({ id: 'dup', version: 1 }),
      'dup.v2.ts': probeSrc({ id: 'dup', version: 2 }),
      'dup.v3.ts': probeSrc({ id: 'dup', version: 3 }),
    });
    const { probes, warnings } = await loadProbes([dir]);
    expect(probes).toHaveLength(1);
    expect(probes[0].version).toBe(3);
    expect(warnings).toHaveLength(2);
    expect(warnings.join('\n')).toContain('shadowed by v3');
  });

  test('a later directory wins a version tie — a user probe overrides a shipped one', async () => {
    const shipped = tree({ 'same.v1.ts': probeSrc({ id: 'same', version: 1, cls: 'anchored' }) });
    const user = tree({ 'same.v1.ts': probeSrc({ id: 'same', version: 1, cls: 'not_a_check' }) });
    const { probes, warnings } = await loadProbes([shipped, user]);
    expect(probes).toHaveLength(1);
    const node = { id: 'n', kind: 'script' as const, name: 'n', source: 's', raw: 'r' };
    expect(probes[0].assess(node)?.class).toBe('not_a_check');
    expect(warnings.some((w) => w.includes('shadowed'))).toBe(true);
  });

  test('a filename that disagrees with the metadata warns and defers to the metadata', async () => {
    const dir = tree({ 'wrongname.v9.ts': probeSrc({ id: 'realid', version: 2 }) });
    const { probes, warnings } = await loadProbes([dir]);
    expect(probes[0].id).toBe('realid');
    expect(probes[0].version).toBe(2);
    expect(warnings.some((w) => w.includes('filename id "wrongname"'))).toBe(true);
    expect(warnings.some((w) => w.includes('filename version v9'))).toBe(true);
  });

  test('the same directory passed twice loads each probe once', async () => {
    const dir = tree({ 'solo.v1.ts': probeSrc({ id: 'solo', version: 1 }) });
    const { probes, warnings } = await loadProbes([dir, dir]);
    expect(probes).toHaveLength(1);
    expect(warnings).toEqual([]);
  });
});

describe('loadProbes · the shipped contract-reference probe', () => {
  test('the probe that ships with Keel loads and can only lower a ratio', async () => {
    // A shipped probe that could hand out cheap greens is exactly the artifact
    // this project argues against, so this asserts the direction it can move
    // the number — by executing it, not by reading it.
    const shipped = join(import.meta.dir, '..', 'probes');
    const { probes, warnings } = await loadProbes([shipped]);
    expect(warnings).toEqual([]);
    expect(probes.map((p) => p.id)).toContain('example-llm-review-gate');

    const probe = probes.find((p) => p.id === 'example-llm-review-gate');
    const llmGate = {
      id: '.github/workflows/ci.yml#claude-review',
      kind: 'ci_step' as const,
      name: 'Claude review',
      source: '.github/workflows/ci.yml:12',
      raw: '- name: Claude review\n  uses: anthropics/claude-code-action@v1\n  with:\n    prompt: review the diff',
    };
    expect(probe?.match(llmGate)).toBe(true);
    expect(probe?.assess(llmGate)?.class).toBe('self_referential');

    // ...and it abstains rather than guessing on a shape it does not recognize.
    const unrelated = {
      id: 'Makefile#test',
      kind: 'script' as const,
      name: 'test',
      source: 'Makefile:3',
      raw: 'test:\n\tbun test',
    };
    expect(probe?.match(unrelated)).toBe(false);
    expect(probe?.assess(unrelated)).toBeNull();
  });
});
