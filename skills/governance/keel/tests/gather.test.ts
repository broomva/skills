/**
 * `gather` — the mechanical stage. It finds surfaces; it may not judge them.
 *
 * Every test here EXECUTES `gather()` against a real directory on disk and
 * asserts over what came back. None of them assert a constant.
 *
 * The first block is a regression pin for a bug that SHIPPED: the
 * interesting-step regex was `/(^|\n)\s*(run|uses)\s*:/`, which cannot cross the
 * list dash in `- uses: x`, so every single-line step in a workflow was dropped.
 * One node was reported where there were four. It was invisible to reading and
 * obvious on execution.
 */

import { afterAll, describe, expect, test } from 'bun:test';
import { gather } from '../scripts/gather.ts';
import { cleanupTrees, tree } from './helpers/tree.ts';

afterAll(cleanupTrees);

const WORKFLOW = `name: test
on: [push]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: oven-sh/setup-bun@v2
        with:
          bun-version: latest
      - name: Install
        run: bun install --frozen-lockfile
      - name: Test and typecheck
        run: |
          bun test
          bunx tsc --noEmit
`;

describe('gather · workflow steps (regression: the dropped single-line step)', () => {
  const dir = tree({ '.github/workflows/test.yml': WORKFLOW });
  const nodes = gather(dir);
  const names = nodes.map((n) => n.name).sort();

  test('single-line `- uses:` steps survive alongside multi-line steps', () => {
    // Four steps in, four steps out. With the `-?` removed from the
    // interesting-step regex the two bare `- uses:` steps vanish and this
    // drops to 2 — which is exactly the shipped bug.
    expect(nodes).toHaveLength(4);
    expect(names).toEqual([
      'Install',
      'Test and typecheck',
      'actions/checkout@v4',
      'oven-sh/setup-bun@v2',
    ]);
  });

  test('every gathered step carries its literal text, not a summary', () => {
    // A summary produced by the gatherer is already a judgment. The agent must
    // reason over the snippet, so the snippet has to survive intact.
    const install = nodes.find((n) => n.name === 'Install');
    expect(install?.raw).toContain('bun install --frozen-lockfile');

    const multi = nodes.find((n) => n.name === 'Test and typecheck');
    expect(multi?.raw).toContain('bun test');
    expect(multi?.raw).toContain('bunx tsc --noEmit');

    const checkout = nodes.find((n) => n.name === 'actions/checkout@v4');
    expect(checkout?.raw.trim()).toBe('- uses: actions/checkout@v4');
  });

  test('a `with:` block stays attached to the step it configures', () => {
    const setup = nodes.find((n) => n.name === 'oven-sh/setup-bun@v2');
    expect(setup?.raw).toContain('bun-version: latest');
    expect(setup?.hints?.action).toBe('oven-sh/setup-bun@v2');
  });

  test('steps are ci_step, and source cites file:line', () => {
    for (const n of nodes) {
      expect(n.kind).toBe('ci_step');
      expect(n.source).toMatch(/^\.github\/workflows\/test\.yml:\d+$/);
      expect(n.id.startsWith('.github/workflows/test.yml#')).toBe(true);
    }
    // Line numbers are 1-based and distinct — a cite that points nowhere is
    // worse than no cite.
    const lines = nodes.map((n) => Number(n.source.split(':')[1]));
    expect(new Set(lines).size).toBe(nodes.length);
    expect(Math.min(...lines)).toBeGreaterThan(0);
  });
});

describe('gather · the same segmenter reads CircleCI and GitLab', () => {
  test('.circleci/ is descended into and its `- run:` steps are found', () => {
    // The whole Ruby corpus scored near-zero because `.circleci/` is a dot-dir
    // and the walker skipped it. Non-coverage is Keel's own shoppable class.
    const dir = tree({
      '.circleci/config.yml': `version: 2.1
jobs:
  build:
    steps:
      - checkout
      - run: bundle exec rspec
      - run:
          name: lint
          command: bundle exec rubocop
`,
    });
    const nodes = gather(dir);
    expect(nodes.map((n) => n.name).sort()).toEqual(['bundle exec rspec', 'lint']);
    expect(nodes.every((n) => n.source.startsWith('.circleci/config.yml:'))).toBe(true);
  });

  /**
   * KNOWN NON-COVERAGE, recorded rather than hidden (reported to the
   * orchestrator; `gather.ts` is not this unit's file to fix).
   *
   * `.gitlab-ci.yml` is routed to the workflow segmenter, but a GitLab job's
   * commands are bare strings under `script:` — there is no `run:` or `uses:`
   * key for the interesting-step filter to see, so a GitLab repo gathers ~0
   * nodes. That is the same shape as the two bugs already fixed here (the
   * `.circleci/` dot-dir skip and Travis's non-`run:` keys), and it is exactly
   * Keel's own shoppable class: a surface the gatherer cannot read is silently
   * ABSENT rather than `unknown`.
   *
   * `test.failing` is the honest encoding — it passes while the gap exists and
   * turns red the moment `gather` learns GitLab, forcing this note to be
   * revisited instead of quietly becoming a false claim of coverage.
   */
  test.failing('GAP: .gitlab-ci.yml `script:` items are not gathered', () => {
    const dir = tree({
      '.gitlab-ci.yml': `test:
  script:
    - make test
  rules:
    - if: $CI_COMMIT_BRANCH
`,
    });
    const nodes = gather(dir);
    expect(nodes.some((n) => n.raw.includes('make test'))).toBe(true);
  });

  test('a GitLab file using the `- run:` shape IS segmented', () => {
    // Proves the routing works and isolates the gap above to the step filter,
    // not to file discovery.
    const dir = tree({
      '.gitlab-ci.yml': `test:
  steps:
    - run: make test
`,
    });
    expect(gather(dir).some((n) => n.raw.includes('make test'))).toBe(true);
  });
});

describe('gather · Travis', () => {
  const dir = tree({
    '.travis.yml': `language: ruby
rvm:
  - 3.2
before_script:
  - bundle install
  - bundle exec rake db:setup
script: bundle exec rspec
after_script: echo done
`,
  });
  const nodes = gather(dir);

  test('both scalar and list command keys are gathered', () => {
    expect(nodes.map((n) => n.name).sort()).toEqual([
      'after_script',
      'before_script',
      'script',
    ]);
  });

  test('a list-form key carries every one of its items', () => {
    const before = nodes.find((n) => n.name === 'before_script');
    expect(before?.raw).toContain('bundle install');
    expect(before?.raw).toContain('bundle exec rake db:setup');
    // ...and stops at the next top-level key.
    expect(before?.raw).not.toContain('rspec');
  });

  test('non-command keys (language, rvm) are not verification edges', () => {
    expect(nodes.some((n) => n.name === 'language' || n.name === 'rvm')).toBe(false);
  });
});

describe('gather · package.json scripts', () => {
  test('each script becomes one node carrying its command', () => {
    const dir = tree({
      'package.json': JSON.stringify(
        { name: 'x', scripts: { test: 'bun test', dev: 'bun --watch run serve.ts' } },
        null,
        2,
      ),
    });
    const nodes = gather(dir);
    expect(nodes.map((n) => n.name).sort()).toEqual(['dev', 'test']);
    expect(nodes.every((n) => n.kind === 'script')).toBe(true);
    expect(nodes.find((n) => n.name === 'test')?.raw).toBe('"test": "bun test"');
    // `dev` is surfaced, NOT filtered. Deciding a dev server asserts nothing is
    // a judgment (`not_a_check`), and the gatherer does not judge.
    expect(nodes.find((n) => n.name === 'dev')?.raw).toContain('--watch');
  });

  test('no scripts, and unparseable JSON, both yield nothing and do not throw', () => {
    expect(gather(tree({ 'package.json': '{"name":"x"}' }))).toHaveLength(0);
    expect(gather(tree({ 'package.json': '{ this is not json' }))).toHaveLength(0);
  });

  test('node_modules is not part of the target under measurement', () => {
    const dir = tree({
      'package.json': JSON.stringify({ scripts: { test: 'bun test' } }),
      'node_modules/left-pad/package.json': JSON.stringify({ scripts: { test: 'tape' } }),
    });
    expect(gather(dir).map((n) => n.source)).toEqual(['package.json']);
  });
});

describe('gather · Makefile', () => {
  const dir = tree({
    Makefile: `BUN := bun

.PHONY: test lint help

test: ## run the suite
\t$(BUN) test
\t$(BUN)x tsc --noEmit

lint:
\tbiome check .

help:
\t@echo targets
`,
  });
  const nodes = gather(dir);

  test('targets are gathered with their whole recipe', () => {
    expect(nodes.map((n) => n.name).sort()).toEqual(['help', 'lint', 'test']);
    const t = nodes.find((n) => n.name === 'test');
    expect(t?.raw).toContain('$(BUN) test');
    expect(t?.raw).toContain('tsc --noEmit');
    expect(t?.kind).toBe('script');
  });

  test('.PHONY is a directive, not a target', () => {
    // Parsing, not judging: `.PHONY` cannot be a verification edge in any repo,
    // in the way that `deploy` might be in some and not others.
    expect(nodes.some((n) => n.name === '.PHONY')).toBe(false);
    expect(nodes.some((n) => n.name.startsWith('.'))).toBe(false);
  });

  test('a `:=` assignment is not a target', () => {
    expect(nodes.some((n) => n.name === 'BUN')).toBe(false);
  });
});

describe('gather · pyproject.toml', () => {
  const dir = tree({
    'pyproject.toml': `[project]
name = "thing"
version = "0.1.0"

[tool.pytest.ini_options]
addopts = "-q --strict-markers"

[tool.ruff]
line-length = 100

[tool.poetry.group.dev.dependencies]
pytest = "^8"
`,
  });
  const nodes = gather(dir);

  test('sections that declare verification are gathered, with their kind', () => {
    const byName = new Map(nodes.map((n) => [n.name, n]));
    expect([...byName.keys()].sort()).toEqual([
      'linter/type-checker config ([tool.ruff])',
      'pytest config ([tool.pytest.ini_options])',
    ]);
    expect(byName.get('pytest config ([tool.pytest.ini_options])')?.kind).toBe('test_target');
    expect(byName.get('linter/type-checker config ([tool.ruff])')?.kind).toBe('ci_step');
  });

  test('a gathered section carries its literal body', () => {
    const pytest = nodes.find((n) => n.kind === 'test_target');
    expect(pytest?.raw).toContain('addopts = "-q --strict-markers"');
    expect(pytest?.raw).not.toContain('line-length');
  });

  test('metadata and dependency sections are not verification edges', () => {
    expect(nodes.some((n) => n.name.includes('[project]'))).toBe(false);
    expect(nodes.some((n) => n.name.includes('poetry'))).toBe(false);
  });
});

describe('gather · Rakefile', () => {
  const dir = tree({
    Rakefile: `require "rake/testtask"

task default: :spec

task :spec do
  sh "bundle exec rspec"
end

RDoc::Task.new do |rd|
  rd.main = "README.md"
end
`,
  });
  const nodes = gather(dir);

  test('both the single-line declaration and the do-block task are gathered', () => {
    expect(nodes.map((n) => n.name).sort()).toEqual(['default', 'spec']);
  });

  test('a do-block task carries its body through its matching end', () => {
    const spec = nodes.find((n) => n.name === 'spec');
    expect(spec?.raw).toContain('bundle exec rspec');
    expect(spec?.raw.trimEnd().endsWith('end')).toBe(true);
  });

  test('a task-defining DSL is left alone rather than guessed at', () => {
    // Guessing what a gem's DSL declares would be judging. Absent is honest;
    // invented is not.
    expect(nodes.some((n) => n.raw.includes('RDoc::Task'))).toBe(false);
  });
});

describe('gather · config files that declare verification', () => {
  test('each known config lands with the kind it actually is', () => {
    const dir = tree({
      CODEOWNERS: '* @team/reviewers\n',
      '.pre-commit-config.yaml': 'repos:\n  - repo: local\n',
      'vitest.config.ts': 'export default { test: { environment: "node" } };\n',
      'netlify.toml': '[build]\n  command = "npm run build"\n',
      'README.md': '# not a check\n',
    });
    const byKind = new Map(gather(dir).map((n) => [n.kind, n.name]));
    expect(byKind.get('review_gate')).toBeDefined();
    expect(byKind.get('test_target')).toContain('vitest.config.ts');
    expect(byKind.get('deploy_gate')).toContain('netlify.toml');
    expect(gather(dir).some((n) => n.source === 'README.md')).toBe(false);
  });
});

describe('gather · the empty target', () => {
  test('a directory with nothing to gather yields zero nodes, not an error', () => {
    // Zero nodes must reach the consumer AS zero. Every surface downstream is
    // required to render that as "nothing gathered", never as a ratio.
    expect(gather(tree({ 'README.md': '# hi\n' }))).toEqual([]);
  });
});

describe('gather · node ids', () => {
  test('ids are unique across a realistic multi-surface target', () => {
    // Verdicts are keyed by node id. A collision silently merges two edges and
    // moves the ratio.
    const dir = tree({
      '.github/workflows/ci.yml': WORKFLOW,
      'package.json': JSON.stringify({ scripts: { test: 'bun test', lint: 'biome ci .' } }),
      Makefile: 'test:\n\tbun test\n\nlint:\n\tbiome check .\n',
      'pyproject.toml': '[tool.ruff]\nline-length = 100\n',
      CODEOWNERS: '* @team\n',
    });
    const nodes = gather(dir);
    expect(nodes.length).toBeGreaterThanOrEqual(9);
    expect(new Set(nodes.map((n) => n.id)).size).toBe(nodes.length);
  });
});
