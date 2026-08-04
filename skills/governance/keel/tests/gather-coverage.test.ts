/**
 * GATHERER BLINDNESS — the test that a repo Keel cannot read is distinguishable
 * from a repo with nothing to read.
 *
 * The defect this pins is not a crash. Point the gatherer at a Jenkins shop and
 * it walks past the Jenkinsfile, past `.buildkite/`, picks up the Makefile and
 * the package.json scripts it happens to understand — the two surfaces that skew
 * ungrounded — and publishes a ratio over that. The bytes it emits are identical
 * to the bytes it emits for a repo with no verification at all. One of those two
 * repos is unverified and the other is unread, and a tool whose entire subject is
 * checks that read something other than what they claim to read does not get to
 * confuse them.
 *
 * Every assertion below EXECUTES `gatherWithCoverage()` over a real directory
 * written to disk, or `render()` over a real report, and reads what came back.
 * Nothing asserts a constant, and nothing asserts that a table in `gather.ts`
 * contains a filename — that would be the lookup table checking itself. The
 * fixtures are real Jenkins, Buildkite and GitLab files; the claim under test is
 * what the gatherer does when it meets them.
 *
 * The sharpest test here is `does not claim blindness it does not have`. An
 * unread list that over-reports is its own dishonesty, and it is the shape that
 * rots first: someone teaches the gatherer a new format and the warning about it
 * survives as stale prose. The claim is made downstream of every parser, so it
 * has to disappear on its own — and this asserts that it does.
 */

import { afterAll, describe, expect, test } from 'bun:test';
import { existsSync, readFileSync, symlinkSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import type { GroundingClass, Node, Report, Verdict } from '../schemas/keel.ts';
import { groundingRatio } from '../schemas/keel.ts';
import {
  type GatherCoverage,
  gather,
  gatherWithCoverage,
} from '../scripts/gather.ts';
import { loadCoverage, render } from '../scripts/render.ts';
import { cleanupTrees, run, tree } from './helpers/tree.ts';

afterAll(cleanupTrees);

const GATHER_TS = join(
  import.meta.dir,
  '..', 'scripts',
  'gather.ts',
);

const RENDER_TS = join(
  import.meta.dir,
  '..', 'scripts',
  'render.ts',
);

// ---------------------------------------------------------------------------
// Fixture contents. Real syntax, not sketches: the whole question is what this
// gatherer does with the files a real target actually carries.
// ---------------------------------------------------------------------------

const JENKINSFILE = `pipeline {
  agent any
  stages {
    stage('Test') {
      steps {
        sh 'make test'
      }
    }
  }
}
`;

const BUILDKITE = `steps:
  - label: ":test_tube: test"
    command: "make test"
`;

/** GitLab's own spelling: a bare \`script:\` list, no \`run:\` and no \`uses:\`. */
const GITLAB = `stages: [test]

unit:
  stage: test
  script:
    - bun install
    - bun test
`;

const TRAVIS = `language: ruby
script: bundle exec rspec
`;

const PRE_COMMIT = `repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.5.0
    hooks:
      - id: ruff
`;

const WORKFLOW = `name: test
on: [push]
jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Test
        run: bun test
`;

const MAKEFILE = 'test:\n\tbun test\n';

const pathsOf = (c: GatherCoverage): string[] => c.unread.map((u) => u.path).sort();

// ---------------------------------------------------------------------------

describe('gather · surfaces recognised and not read', () => {
  const dir = tree({
    Jenkinsfile: JENKINSFILE,
    '.buildkite/pipeline.yml': BUILDKITE,
    '.teamcity/settings.kts': 'project { }\n',
    'azure-pipelines.yml': 'steps:\n  - script: make test\n',
    '.drone.yml': 'kind: pipeline\nsteps:\n  - name: test\n',
    '.cirrus.yml': 'task:\n  test_script: make test\n',
    'bitbucket-pipelines.yml': 'pipelines:\n  default:\n    - step:\n        script:\n          - make test\n',
    'build.gradle.kts': 'plugins { java }\n',
    'pom.xml': '<project><artifactId>x</artifactId></project>\n',
    'BUILD.bazel': 'sh_test(name = "test", srcs = ["t.sh"])\n',
    Earthfile: 'VERSION 0.8\ntest:\n  RUN make test\n',
    'flake.nix': '{ outputs = { self }: { checks.x86_64-linux.test = 1; }; }\n',
    'Taskfile.yml': 'tasks:\n  test:\n    cmds:\n      - make test\n',
    Makefile: MAKEFILE,
  });
  const { nodes, coverage } = gatherWithCoverage(dir);

  test('a Jenkinsfile and a .buildkite/ directory are reported as unread', () => {
    const paths = pathsOf(coverage);
    expect(paths).toContain('Jenkinsfile');
    expect(paths).toContain('.buildkite');

    // The directory case is the one that cannot be recovered later: `walk()`
    // refuses to enter a dot-directory, so `.buildkite/pipeline.yml` never
    // reaches the file loop at all. If the refusal is not recorded where it
    // happens, nothing downstream can know the directory existed.
    const buildkite = coverage.unread.find((u) => u.path === '.buildkite');
    expect(buildkite).toEqual({ path: '.buildkite', kind: 'dir', tool: 'Buildkite' });
    expect(coverage.unread.find((u) => u.path === 'Jenkinsfile')).toEqual({
      path: 'Jenkinsfile',
      kind: 'file',
      tool: 'Jenkins',
    });
  });

  test('the other unread ecosystems come back too, each named by its tool', () => {
    const byPath = new Map(coverage.unread.map((u) => [u.path, u.tool]));
    expect(byPath.get('azure-pipelines.yml')).toBe('Azure Pipelines');
    expect(byPath.get('.drone.yml')).toBe('Drone CI');
    expect(byPath.get('.cirrus.yml')).toBe('Cirrus CI');
    expect(byPath.get('bitbucket-pipelines.yml')).toBe('Bitbucket Pipelines');
    expect(byPath.get('.teamcity')).toBe('TeamCity');
    expect(byPath.get('build.gradle.kts')).toBe('Gradle');
    expect(byPath.get('pom.xml')).toBe('Maven');
    expect(byPath.get('BUILD.bazel')).toBe('Bazel');
    expect(byPath.get('Earthfile')).toBe('Earthly');
    expect(byPath.get('flake.nix')).toBe('Nix flake');
    expect(byPath.get('Taskfile.yml')).toBe('Task');
  });

  test('the residue it CAN read is one Makefile target — the shape of the bug', () => {
    // This is the whole complaint in one assertion: thirteen verification
    // surfaces on disk, one node gathered, and without the coverage record the
    // ratio would be computed over that one node and quoted as the repo's.
    expect(nodes).toHaveLength(1);
    expect(nodes[0]?.source.startsWith('Makefile')).toBe(true);
    expect(coverage.unread.length).toBeGreaterThan(nodes.length);
  });

  test('no unread surface carries a class — there is nothing there to classify', () => {
    // A surface nobody read cannot be `anchored`, and it must not be smuggled
    // in as `unknown` either: `unknown` is a claim about an edge that was
    // FOUND. The record carries paths and tool names, and no grounding class.
    const serialized = JSON.stringify(coverage);
    for (const c of ['anchored', 'self_referential', 'not_a_check'] as GroundingClass[]) {
      expect(serialized).not.toContain(`"${c}"`);
    }
    for (const u of coverage.unread) {
      expect(Object.keys(u).sort()).toEqual(['kind', 'path', 'tool']);
    }
  });
});

describe('gather · does not claim blindness it does not have', () => {
  const dir = tree({
    '.travis.yml': TRAVIS,
    '.pre-commit-config.yaml': PRE_COMMIT,
    '.gitlab-ci.yml': GITLAB,
    'package.json': '{"scripts": {"test": "bun test"}}\n',
    Makefile: MAKEFILE,
  });
  const { nodes, coverage } = gatherWithCoverage(dir);

  test('files a parser DOES read never appear as unread', () => {
    // Verified against the parsers rather than asserted from the task list:
    // `.travis.yml` goes to gatherTravis, `.pre-commit-config.yaml` to
    // gatherConfig, `.gitlab-ci.yml` to the workflow segmenter. Claiming any of
    // them as blindness would be a lie pointing the other way, and it is the
    // lie that rots quietest — nobody re-checks a warning.
    expect(coverage.unread).toEqual([]);
    expect(nodes.length).toBeGreaterThan(0);
  });

  test('a file that produced a node is read by definition', () => {
    const sources = new Set(nodes.map((n) => n.source.split(':')[0]));
    expect(sources.has('.travis.yml')).toBe(true);
    expect(sources.has('.pre-commit-config.yaml')).toBe(true);
    for (const u of coverage.unread) expect(sources.has(u.path)).toBe(false);
  });
});

describe('gather · local gates are recognised, not silently refused', () => {
  // The walk refuses every dot-directory outside DOT_DIRS_ALLOWED. Refusing is
  // right — there is no parser for these — but a refusal that produces no
  // record is the silent non-coverage this whole surface exists to end, and
  // Keel was its own worst case: measuring itself, it reported a clean sweep
  // over a tree containing `.githooks/pre-commit` (which refuses commits) and
  // `.control/policy.yaml` (which declares which operations are blocked).
  const dir = tree({
    '.githooks/pre-commit': '#!/usr/bin/env bash\nexit 1\n',
    '.control/policy.yaml': 'gates:\n  g1: block-force-push\n',
    '.husky/pre-push': '#!/usr/bin/env sh\nnpm test\n',
    '.github/workflows/ci.yml': 'on: [push]\njobs:\n  t:\n    steps:\n      - run: bun test\n',
  });
  const { nodes, coverage } = gatherWithCoverage(dir);

  test('a refused gate directory is reported, with the tool named', () => {
    const byPath = new Map(coverage.unread.map((u) => [u.path, u]));
    for (const [path, tool] of [
      ['.githooks', 'git hooks'],
      ['.control', 'policy gates'],
      ['.husky', 'Husky'],
    ] as const) {
      expect(byPath.get(path)?.tool).toBe(tool);
      expect(byPath.get(path)?.kind).toBe('dir');
    }
  });

  test('recognising them does not turn them into nodes', () => {
    // They are UNREAD. If a gate directory ever starts contributing nodes it is
    // because someone taught the gatherer to parse it, and at that point it must
    // leave this list — an entry that is both read and reported as unread is the
    // over-report the sibling describe() guards against.
    const sources = new Set(nodes.map((n) => n.source.split(':')[0]));
    for (const u of coverage.unread) expect(sources.has(u.path)).toBe(false);
    expect([...sources]).toContain('.github/workflows/ci.yml');
  });

  // REMOVED, and the loss is stated rather than absorbed: a third test here
  // ran the gatherer over the standalone Keel repository — which carried
  // `.githooks/` and `.control/` at its root — and asserted it reported both of
  // its own gates. It was the real-target counterpart to the two tests above,
  // and it earned its place: the bug it pinned was found by Keel measuring
  // itself, not by a fixture.
  //
  // That repository no longer exists. As a skill inside this monorepo there is
  // no tree in reach that carries those directories: the monorepo root has
  // `.github/` only, and `.control/` is gitignored there, so a CI clone would
  // not have it either.
  //
  // The two ways to keep it green were both worse than deleting it. Creating
  // `.githooks/` and `.control/` inside the skill so the assertion passes would
  // manufacture the evidence — the check would then be measuring a tree that
  // exists only to be measured. Pointing it at the monorepo root would make it
  // assert something false about that repo, and couple a skill's suite to its
  // container.
  //
  // So the real-target arm is gone and only the constructed-tree arm remains.
  // `tree()` does write to real disk, so what is lost is not "executes for
  // real" but "executes against a repository nobody built for the test". If a
  // future target in this repo grows those gates, restore it here.
});

describe('gather · read, and silent about it', () => {
  const dir = tree({ '.gitlab-ci.yml': GITLAB });
  const { nodes, coverage } = gatherWithCoverage(dir);

  test('a GitLab pipeline is opened by a reader that comes back with nothing', () => {
    // Not a hypothetical: the workflow segmenter keys on `run:`/`uses:`, and
    // GitLab spells its commands as a bare `script:` list. The file is read and
    // yields nothing, which is a gap in this gatherer — reporting it as
    // "unread" would be false, and reporting nothing at all is how a full CI
    // pipeline turns into a zero.
    expect(nodes).toEqual([]);
    expect(coverage.unread).toEqual([]);
    expect(coverage.silent).toEqual([
      { path: '.gitlab-ci.yml', parser: 'workflow-steps' },
    ]);
  });

  test('a reader that produced nodes is not reported silent', () => {
    const only = gatherWithCoverage(tree({ '.github/workflows/test.yml': WORKFLOW }));
    expect(only.nodes.length).toBeGreaterThan(0);
    expect(only.coverage.silent).toEqual([]);
    expect(only.coverage.unread).toEqual([]);
  });
});

describe('gather · an empty repo and a blind one are different results', () => {
  const empty = gatherWithCoverage(tree({ 'README.md': '# nothing here\n' }));
  const blind = gatherWithCoverage(
    tree({ Jenkinsfile: JENKINSFILE, '.buildkite/pipeline.yml': BUILDKITE }),
  );

  test('both gather zero nodes — which is exactly why nodes cannot be the answer', () => {
    expect(empty.nodes).toEqual([]);
    expect(blind.nodes).toEqual([]);
  });

  test('the coverage record separates them', () => {
    expect(empty.coverage.unread).toEqual([]);
    expect(empty.coverage.silent).toEqual([]);
    expect(pathsOf(blind.coverage)).toEqual(['.buildkite', 'Jenkinsfile']);

    // The pair, stated as the comparison the whole unit exists to make.
    expect(empty.coverage.unread.length).not.toBe(blind.coverage.unread.length);
  });
});

describe('gather · the Node[] contract is unchanged', () => {
  const dir = tree({
    '.github/workflows/test.yml': WORKFLOW,
    Jenkinsfile: JENKINSFILE,
    Makefile: MAKEFILE,
  });

  test('gather() returns exactly what gatherWithCoverage() gathered', () => {
    // classify.ts and corpus.ts both consume `gather()` as `Node[]`. Widening
    // it to carry coverage would break both for a payload neither one needs.
    expect(gather(dir)).toEqual(gatherWithCoverage(dir).nodes);
  });

  test('--json still prints a bare Node[], with or without --coverage', async () => {
    const out = join(dir, 'cov.json');
    const bare = await run(['bun', GATHER_TS, dir, '--json']);
    const withCoverage = await run(['bun', GATHER_TS, dir, '--json', '--coverage', out]);

    expect(bare.code).toBe(0);
    expect(withCoverage.code).toBe(0);
    const parsed = JSON.parse(withCoverage.stdout) as Node[];
    expect(Array.isArray(parsed)).toBe(true);
    // Byte-identical stdout under both flag combinations: the shape a consumer
    // parses must not depend on which flags the caller happened to pass.
    expect(withCoverage.stdout).toBe(bare.stdout);

    const record = JSON.parse(readFileSync(out, 'utf8')) as GatherCoverage;
    expect(record.schema).toBe('keel.gather-coverage.v1');
    expect(record.unread.map((u) => u.path)).toContain('Jenkinsfile');
    expect(record.nodesGathered).toBe(parsed.length);
  });

  test('--coverage without a path is an error, not a skipped write', async () => {
    const r = await run(['bun', GATHER_TS, dir, '--coverage']);
    expect(r.code).toBe(1);
    expect(r.stderr).toContain('--coverage requires a path');
  });

  test('the human output names the unread surfaces, and says so when there are none', async () => {
    const blind = await run(['bun', GATHER_TS, dir]);
    expect(blind.stdout).toContain('Jenkinsfile');
    expect(blind.stdout).toContain('recognised but NOT read');

    const clean = await run([
      'bun',
      GATHER_TS,
      tree({ '.github/workflows/test.yml': WORKFLOW }),
    ]);
    expect(clean.stdout).toContain('no recognised verification surface was left unread');
  });
});

// ---------------------------------------------------------------------------
// render — the number and the caveat, in one place
// ---------------------------------------------------------------------------

function reportOf(target: string, count: number): Report {
  const nodes: Node[] = Array.from({ length: count }, (_, i) => ({
    id: `n${i}`,
    kind: 'script',
    name: `target-${i}`,
    source: `Makefile:${i + 1}`,
    raw: `test:\n\tbun test`,
  }));
  const verdicts: Verdict[] = nodes.map((n) => ({
    nodeId: n.id,
    class: 'anchored' as GroundingClass,
    writeBoundary: {
      producer: 'the bun test runner process exit code',
      actorCanWrite: false,
      argument:
        'The exit code comes from a runtime executing assertions on a runner the author does not control.',
    },
    evidence: ['Makefile:1'],
    confidence: 0.8,
    decidedBy: 'agent',
  }));
  return {
    target,
    revision: 'deadbee',
    generatedAt: '2026-07-25T09:00:00.000Z',
    nodes,
    verdicts,
    grounding: groundingRatio(verdicts),
    economics: {
      nodesTotal: count,
      nodesSampled: count,
      decidedByProbe: 0,
      decidedByAgent: count,
      tokensIn: 100,
      tokensOut: 50,
      tokensEstimated: true,
      wallClockMs: 1000,
      probesMinted: 0,
      probeLibrarySize: 0,
    },
  };
}

const coverageOf = (over: Partial<GatherCoverage> = {}): GatherCoverage => ({
  schema: 'keel.gather-coverage.v1',
  target: '/tmp/clone',
  nodesGathered: 1,
  unread: [{ path: 'Jenkinsfile', kind: 'file', tool: 'Jenkins' }],
  silent: [],
  blind: [],
  note: 'note',
  ...over,
});

describe('render · the caveat sits beside the number', () => {
  const html = render(reportOf('github.com/acme/app', 1), {
    coverage: coverageOf({
      unread: [
        { path: 'Jenkinsfile', kind: 'file', tool: 'Jenkins' },
        { path: '.buildkite', kind: 'dir', tool: 'Buildkite' },
      ],
      silent: [{ path: '.gitlab-ci.yml', parser: 'workflow-steps' }],
    }),
  });

  test('the unread surfaces are named in the document', () => {
    expect(html).toContain('Unread surfaces');
    expect(html).toContain('Jenkinsfile');
    expect(html).toContain('.buildkite/');
    expect(html).toContain('.gitlab-ci.yml');
  });

  test('never-opened and opened-but-empty are counted apart, not summed', () => {
    // Two different facts. A single "3" in the heading would not reconcile
    // against either list below it, and this document's whole posture is that
    // counts a reader can check must add up.
    expect(html).toContain('2 unread, 1 read-but-silent');
  });

  test('it renders before the counter-metric and the graph, not in a footer', () => {
    // "We could not read your Jenkinsfile" changes how the ratio should be
    // read, so a reader must meet it while they are still reading the ratio. A
    // caveat two screens below a number arrives after the impression it was
    // meant to prevent.
    // Searched from the end of the inlined stylesheets, not from byte zero:
    // the document carries tokens.css and keel.css verbatim, and both discuss
    // `.k-ratio__value` and the ε-audit card by name. A whole-document indexOf
    // would be measuring the stylesheet — the exact reading-the-wrong-thing
    // failure this tool exists to name.
    const bodyAt = html.lastIndexOf('</style>');
    const ratio = html.indexOf('k-ratio__value', bodyAt);
    const card = html.indexOf('Unread surfaces', bodyAt);
    const audit = html.indexOf('ε-audit', bodyAt);
    const graph = html.indexOf('Node graph', bodyAt);
    expect(ratio).toBeGreaterThan(-1);
    expect(card).toBeGreaterThan(ratio);
    expect(card).toBeLessThan(audit);
    expect(card).toBeLessThan(graph);
  });

  test('with no coverage record, nothing is claimed either way', () => {
    // Absence of the record is not evidence of coverage. A card reading
    // "nothing unread" drawn from silence would be the fail-open default this
    // repo forbids everywhere else.
    const bare = render(reportOf('github.com/acme/app', 1));
    expect(bare).not.toContain('Unread surfaces');
  });

  test('an empty unread list still prints, because absence must be readable', () => {
    const clean = render(reportOf('github.com/acme/app', 1), {
      coverage: coverageOf({ unread: [], silent: [] }),
    });
    expect(clean).toContain('Unread surfaces');
    expect(clean).toContain('none');
    expect(clean).not.toContain('Jenkinsfile');
  });

  test('a nothing-gathered report still says whether anything was unreadable', () => {
    // The two states that are byte-identical without this: nothing to read, and
    // nothing readable.
    const blind = render(reportOf('github.com/acme/app', 0), {
      coverage: coverageOf({ nodesGathered: 0 }),
    });
    expect(blind).toContain('Nothing gathered');
    expect(blind).toContain('Jenkinsfile');

    const empty = render(reportOf('github.com/acme/app', 0), {
      coverage: coverageOf({ nodesGathered: 0, unread: [], silent: [] }),
    });
    expect(empty).toContain('Nothing gathered');
    expect(empty).not.toContain('Jenkinsfile');
  });

  test('a long unread list is elided, and the elision is disclosed', () => {
    const many = Array.from({ length: 40 }, (_, i) => ({
      path: `pkg/${i}/BUILD.bazel`,
      kind: 'file' as const,
      tool: 'Bazel',
    }));
    const html40 = render(reportOf('github.com/acme/app', 1), {
      coverage: coverageOf({ unread: many }),
    });
    expect(html40).toContain('further unread');
    expect(html40).toContain('28');
  });

  test('a path from the record is escaped, not spliced', () => {
    const nasty = render(reportOf('github.com/acme/app', 1), {
      coverage: coverageOf({
        unread: [{ path: '<script>alert(1)</script>', kind: 'file', tool: 'Jenkins' }],
      }),
    });
    expect(nasty).not.toContain('<script>alert(1)</script>');
    expect(nasty).toContain('&lt;script&gt;');
  });
});

// ---------------------------------------------------------------------------
// The walk itself — the read failure that used to print the CLEAN claim.
//
// Every case below produces zero nodes, zero unread and zero silent, which is
// byte-identical to a spotless run. The gatherer used to answer all of them with
// "no recognised verification surface was left unread": a sentence about a tree
// it never saw. A tool whose subject is checks that read something other than
// what they claim to read does not get to make that claim from a failed read.
// ---------------------------------------------------------------------------

describe('gather · a walk that could not see the tree says so', () => {
  test('a target that is a file, not a directory, is a read failure', async () => {
    const dir = tree({ 'README.md': '# nothing here\n' });
    const asFile = join(dir, 'README.md');
    const { nodes, coverage } = gatherWithCoverage(asFile);

    // The three lists that used to carry the whole answer are all empty here —
    // which is exactly why they could not be the whole answer.
    expect(nodes).toEqual([]);
    expect(coverage.unread).toEqual([]);
    expect(coverage.silent).toEqual([]);

    expect(coverage.blind).toHaveLength(1);
    expect(coverage.blind[0]?.by).toBe('walk');
    expect(coverage.blind[0]?.path).toBe('.');
    expect(coverage.blind[0]?.reason).toContain('ENOTDIR');

    const r = await run(['bun', GATHER_TS, asFile]);
    expect(r.stdout).not.toContain('no recognised verification surface was left unread');
    expect(r.stdout).toContain('could not be read');
    expect(r.stdout).toContain('ENOTDIR');
  });

  test('the depth cutoff is a read failure, not a finished walk', async () => {
    // Eight levels: the walk stops at its limit and never reaches the Makefile.
    // Silence here reads as "this repo has no verification", and the difference
    // between that and "we stopped looking" is the whole unit.
    const dir = tree({ 'a/b/c/d/e/f/g/h/Makefile': MAKEFILE });
    const { nodes, coverage } = gatherWithCoverage(dir);

    expect(nodes).toEqual([]);
    expect(coverage.unread).toEqual([]);
    expect(coverage.silent).toEqual([]);
    expect(coverage.blind).toHaveLength(1);
    expect(coverage.blind[0]?.path).toBe(join('a', 'b', 'c', 'd', 'e', 'f', 'g'));
    expect(coverage.blind[0]?.reason).toContain('depth limit');

    const r = await run(['bun', GATHER_TS, dir]);
    expect(r.stdout).not.toContain('no recognised verification surface was left unread');
    expect(r.stdout).toContain('depth limit');
  });

  test('a walk that saw everything still gets to make the clean claim', async () => {
    // The counter-case, and it is not decoration: a suppression that fires on
    // every run says nothing. This asserts the claim is still reachable.
    const dir = tree({ '.github/workflows/test.yml': WORKFLOW });
    const { coverage } = gatherWithCoverage(dir);
    expect(coverage.blind).toEqual([]);

    const r = await run(['bun', GATHER_TS, dir]);
    expect(r.stdout).toContain('no recognised verification surface was left unread');
  });

  test('a parser that THREW is not filed as read-but-silent', () => {
    // A broken symlink: `walk` hands it to the file loop as a file, and the
    // workflow parser dies on `readFileSync`. It used to land in `silent`,
    // where the card states two things that are both false about it — that the
    // file was read, and that the gap is in the reader rather than the read.
    const dir = tree({ '.github/workflows/keep.yml': WORKFLOW });
    symlinkSync('does-not-exist.yml', join(dir, '.github', 'workflows', 'broken.yml'));

    const { coverage } = gatherWithCoverage(dir);
    const rel = join('.github', 'workflows', 'broken.yml');

    expect(coverage.silent.map((s) => s.path)).not.toContain(rel);
    const failed = coverage.blind.find((b) => b.path === rel);
    expect(failed?.by).toBe('workflow-steps');
    expect(failed?.reason).toContain('ENOENT');
  });
});

describe('gather · the CLI refuses what it cannot do', () => {
  const dir = tree({ Jenkinsfile: JENKINSFILE, Makefile: MAKEFILE });

  test('a typo\'d flag is refused, not ignored', async () => {
    // `--coverge out.json` used to exit 0 having written nothing, leaving the
    // caller holding a coverage record that does not exist.
    const out = join(dir, 'typo.coverage.json');
    const r = await run(['bun', GATHER_TS, dir, '--coverge', out]);
    expect(r.code).toBe(1);
    expect(r.stderr).toContain('unknown flag --coverge');
    expect(existsSync(out)).toBe(false);
  });

  test('a coverage path that cannot be written fails in this tool\'s voice', async () => {
    // The parent is a file, so the write cannot happen. It exited 1 either way
    // — but with a stack trace and a Bun banner, which reads as a broken tool
    // rather than a refused write.
    const r = await run([
      'bun',
      GATHER_TS,
      dir,
      '--coverage',
      join(dir, 'Makefile', 'cov.json'),
    ]);
    expect(r.code).toBe(1);
    expect(r.stderr.startsWith('gather: cannot write')).toBe(true);
    expect(r.stderr).not.toContain('    at ');
  });

  test('the good path still works, and says what it wrote', async () => {
    const out = join(dir, 'ok.coverage.json');
    const r = await run(['bun', GATHER_TS, dir, '--coverage', out]);
    expect(r.code).toBe(0);
    expect(r.stderr).toContain('1 unread, 0 read-but-silent, 0 unreadable');
    expect(existsSync(out)).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// render, driven the way the pipeline drives it: two processes and a file.
//
// `render()` can be exercised in-process all day and prove nothing about the
// CLI, which is the only path by which a coverage record ever reaches a real
// report. These run both binaries and read the bytes off disk.
// ---------------------------------------------------------------------------

describe('render · the CLI carries the record into the written report', () => {
  /** A target, a real coverage record gathered from it, and a report beside it. */
  async function pipeline(files: Record<string, string>) {
    const target = tree(files);
    const report = join(target, 'report.json');
    const cov = join(target, 'report.coverage.json');
    writeFileSync(report, `${JSON.stringify(reportOf(target, 1), null, 2)}\n`);
    const gathered = await run(['bun', GATHER_TS, target, '--coverage', cov]);
    expect(gathered.code).toBe(0);
    return { target, report, cov };
  }

  test('gather --coverage, then render, and the card is in the file', async () => {
    const { target, report } = await pipeline({
      Jenkinsfile: JENKINSFILE,
      Makefile: MAKEFILE,
    });
    const out = join(target, 'report.html');

    // No --coverage flag: the sibling is found by the CLI's own derivation,
    // which is the wiring under test. --no-curve keeps this off the repo's
    // curve.svg, which is not this test's subject.
    const r = await run(['bun', RENDER_TS, report, '-o', out, '--no-curve']);
    expect(r.code).toBe(0);

    const html = readFileSync(out, 'utf8');
    expect(html).toContain('Unread surfaces');
    expect(html).toContain('Jenkinsfile');
    // The tool name, not just the path: the card's second column is what tells
    // a reader which ecosystem went unmeasured.
    expect(html).toContain('Jenkins');
    expect(html).toContain('1 unread');
  });

  test('--no-coverage draws no card at all, and does not claim clean', async () => {
    const { target, report } = await pipeline({
      Jenkinsfile: JENKINSFILE,
      Makefile: MAKEFILE,
    });
    const out = join(target, 'nocov.html');
    const r = await run([
      'bun',
      RENDER_TS,
      report,
      '-o',
      out,
      '--no-curve',
      '--no-coverage',
    ]);
    expect(r.code).toBe(0);

    const html = readFileSync(out, 'utf8');
    expect(html).not.toContain('Unread surfaces');
    // Absence of the record is not evidence of coverage — no card, and no
    // sentence claiming the surface was fully read either.
    expect(html).not.toContain('it also read');
  });

  test('--coverage naming a file that is not there exits non-zero', async () => {
    const { target, report } = await pipeline({ Makefile: MAKEFILE });
    const out = join(target, 'missing.html');
    const r = await run([
      'bun',
      RENDER_TS,
      report,
      '-o',
      out,
      '--no-curve',
      '--coverage',
      join(target, 'not-here.coverage.json'),
    ]);
    expect(r.code).not.toBe(0);
    expect(existsSync(out)).toBe(false);
  });

  test('a walk failure reaches the written report instead of a clean card', async () => {
    // End to end on the fail-open shape: the target is a file, so gather sees
    // nothing at all, and the report must say that rather than say nothing.
    const { target, report } = await pipeline({ 'README.md': '# x\n' });
    const cov = join(target, 'report.coverage.json');
    const g = await run(['bun', GATHER_TS, join(target, 'README.md'), '--coverage', cov]);
    expect(g.code).toBe(0);

    const out = join(target, 'blind.html');
    const r = await run(['bun', RENDER_TS, report, '-o', out, '--no-curve']);
    expect(r.code).toBe(0);

    const html = readFileSync(out, 'utf8');
    expect(html).toContain('1 unreadable');
    expect(html).toContain('ENOTDIR');
    expect(html).not.toContain('Every verification surface this gatherer recognises');
  });
});

describe('render · a read failure suppresses the clean card', () => {
  test('an empty unread list plus a failed walk is not a clean sweep', () => {
    const html = render(reportOf('github.com/acme/app', 1), {
      coverage: coverageOf({
        unread: [],
        silent: [],
        blind: [
          { path: '.', by: 'walk', reason: 'ENOTDIR: not a directory, scandir' },
        ],
      }),
    });
    expect(html).not.toContain('Every verification surface this gatherer recognises');
    expect(html).toContain('Unread surfaces — 1 unreadable');
    expect(html).toContain('ENOTDIR');
    expect(html).toContain('attempted by');
  });

  test('a reason from the record is escaped, not spliced', () => {
    const nasty = render(reportOf('github.com/acme/app', 1), {
      coverage: coverageOf({
        unread: [],
        blind: [
          { path: 'x', by: 'walk', reason: '<script>alert(1)</script>' },
        ],
      }),
    });
    expect(nasty).not.toContain('<script>alert(1)</script>');
    expect(nasty).toContain('&lt;script&gt;');
  });
});

describe('render · a record it cannot read is disclosed, never assumed clean', () => {
  const dir = tree({ 'a.coverage.json': '{"schema":"something-else"}\n' });

  test('loadCoverage rejects a record that is not the shape it expects', () => {
    expect(loadCoverage(join(dir, 'a.coverage.json'))).toEqual({
      rejected: join(dir, 'a.coverage.json'),
    });
    expect(loadCoverage(join(dir, 'missing.coverage.json'))).toBeNull();
  });

  test('an entry missing the fields the card prints is rejected, not published', () => {
    // The defect this pins: validation advertised as "both lists must be arrays
    // of the entries the card will read" that checked one field of one shape.
    // An unread entry with no `tool` sailed through and the card printed the
    // literal text `undefined` in the tool column — on the one table whose
    // subject is what this run could not see.
    const base = {
      schema: 'keel.gather-coverage.v1',
      target: '/tmp/clone',
      nodesGathered: 1,
      unread: [],
      silent: [],
      blind: [],
      note: 'note',
    };
    const bad: Record<string, unknown> = {
      'no-tool.json': { unread: [{ path: 'Jenkinsfile', kind: 'file' }] },
      'no-kind.json': { unread: [{ path: 'Jenkinsfile', tool: 'Jenkins' }] },
      'bad-kind.json': {
        unread: [{ path: 'Jenkinsfile', kind: 'symlink', tool: 'Jenkins' }],
      },
      'no-parser.json': { silent: [{ path: '.gitlab-ci.yml' }] },
      'no-reason.json': { blind: [{ path: '.', by: 'walk' }] },
      'no-blind.json': { blind: undefined },
    };
    const files = Object.fromEntries(
      Object.entries(bad).map(([name, over]) => [
        name,
        `${JSON.stringify({ ...base, ...(over as object) })}\n`,
      ]),
    );
    const d = tree({ ...files, 'good.json': `${JSON.stringify(base)}\n` });

    for (const name of Object.keys(bad)) {
      expect(loadCoverage(join(d, name))).toEqual({ rejected: join(d, name) });
    }
    // The positive control. A rejector that rejects everything proves nothing.
    const good = loadCoverage(join(d, 'good.json'));
    expect(good && 'coverage' in good).toBe(true);
  });

  test('a record with no `tool` publishes a disclosure, never the word undefined', async () => {
    // The consequence, driven through the CLI, which is where it would have
    // shipped. An unread entry with no `tool` used to load, and the card then
    // printed the literal text `undefined` as the ecosystem this run could not
    // read — an artifact stating a fact about the world that came from a
    // dereference of a field nobody checked.
    const target = tree({
      'report.coverage.json': `${JSON.stringify({
        schema: 'keel.gather-coverage.v1',
        target: '/tmp/clone',
        nodesGathered: 1,
        unread: [{ path: 'Jenkinsfile', kind: 'file' }],
        silent: [],
        blind: [],
        note: 'note',
      })}\n`,
    });
    const report = join(target, 'report.json');
    writeFileSync(report, `${JSON.stringify(reportOf(target, 1), null, 2)}\n`);
    const out = join(target, 'report.html');

    const r = await run(['bun', RENDER_TS, report, '-o', out, '--no-curve']);
    expect(r.code).toBe(0);

    const html = readFileSync(out, 'utf8');
    expect(html).toContain('unavailable');
    expect(html).not.toContain('undefined');
    // And it does not quietly half-render the entry it refused.
    expect(html).not.toContain('Jenkinsfile');
  });

  test('loadCoverage accepts a record gather actually wrote', async () => {
    const target = tree({ Jenkinsfile: JENKINSFILE, Makefile: MAKEFILE });
    const out = join(target, 'report.coverage.json');
    const r = await run(['bun', GATHER_TS, target, '--coverage', out]);
    expect(r.code).toBe(0);

    const loaded = loadCoverage(out);
    expect(loaded).not.toBeNull();
    expect(loaded && 'coverage' in loaded).toBe(true);
    if (loaded && 'coverage' in loaded) {
      expect(loaded.coverage.unread.map((u) => u.path)).toContain('Jenkinsfile');
    }
  });

  test('the report says it cannot say, rather than saying nothing', () => {
    const html = render(reportOf('github.com/acme/app', 1), {
      coverageRejectedPath: '/tmp/broken.coverage.json',
    });
    expect(html).toContain('Unread surfaces');
    expect(html).toContain('unavailable');
    expect(html).toContain('/tmp/broken.coverage.json');
  });
});
