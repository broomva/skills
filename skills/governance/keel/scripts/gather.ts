#!/usr/bin/env bun
/**
 * keel gather — locate candidate verification edges in a target.
 *
 * This step is MECHANICAL. It finds surfaces; it does not judge them.
 * Judgment is agentic (see SKILL.md §2) and happens over `raw`, never over a
 * summary produced here — a summary is already a judgment, and a judgment made
 * by the gatherer is a rule table by another name.
 *
 * Deliberately dependency-free. We do not fully parse YAML: we locate steps and
 * carry their literal text forward. Faithful beats clever here.
 *
 *   bun scripts/gather.ts <target-dir> [--json] [--coverage <file>]
 */

import {
  readdirSync,
  readFileSync,
  statSync,
  existsSync,
  mkdirSync,
  writeFileSync,
} from 'node:fs';
import { join, relative, basename, dirname, resolve } from 'node:path';
import type { Node, NodeKind } from '../schemas/keel.ts';

const SKIP_DIRS = new Set([
  '.git', 'node_modules', 'dist', 'build', 'target', 'vendor',
  '__pycache__', '.venv', 'venv', '.next', '.turbo', 'coverage',
]);

/**
 * Dot-directories we descend into anyway. Everything else beginning with `.`
 * is skipped, so a CI provider that hides its config in one is INVISIBLE until
 * it is listed here — which is how the whole Ruby ecosystem was being scored
 * near-zero (`.circleci/`) while its checks sat in plain sight.
 */
const DOT_DIRS_ALLOWED = new Set(['.github', '.circleci']);

const MAX_DEPTH = 6;

/** A directory the walk started on and did not finish. Absolute path. */
interface WalkFailure {
  dir: string;
  reason: string;
}

interface WalkState {
  /** every file reached */
  files: string[];
  /**
   * Dot-directories the walk declined to enter. They are the only surfaces
   * that never reach the file loop at all, so a blind spot inside one is
   * invisible unless it is recorded at the moment of the refusal.
   */
  refused: string[];
  /**
   * Failures the walk would otherwise SWALLOW: a directory it could not
   * enumerate (including a target that is not a directory at all), and the
   * depth cutoff.
   *
   * Both used to `return` quietly, and a quiet return is indistinguishable
   * downstream from a clean sweep — point this at a file, or at a tree it
   * cannot open, and it gathered nothing, found nothing unread, and printed
   * "no recognised verification surface was left unread" about a tree it never
   * saw. That is the fail-open shape this whole record exists to close,
   * reproduced inside the fix. Silence about a directory you could not open is
   * exactly what must not happen, so the failure is recorded where it occurs
   * and while the path is still known.
   */
  failed: WalkFailure[];
}

function walk(dir: string, st: WalkState, depth = 0): void {
  if (depth > MAX_DEPTH) {
    st.failed.push({
      dir,
      reason: `walk depth limit (${MAX_DEPTH}) reached — nothing at or below this path was visited`,
    });
    return;
  }
  let entries;
  try {
    entries = readdirSync(dir, { withFileTypes: true });
  } catch (err) {
    st.failed.push({ dir, reason: (err as Error).message });
    return;
  }
  for (const e of entries) {
    if (e.name.startsWith('.') && !DOT_DIRS_ALLOWED.has(e.name)) {
      if (e.isDirectory()) {
        st.refused.push(join(dir, e.name));
        continue;
      }
    }
    if (e.isDirectory()) {
      if (SKIP_DIRS.has(e.name)) continue;
      walk(join(dir, e.name), st, depth + 1);
    } else {
      st.files.push(join(dir, e.name));
    }
  }
}

function mkId(source: string, slug: string): string {
  const clean = slug.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '');
  return `${source}#${clean || 'step'}`;
}

// ---------------------------------------------------------------------------
// GitHub Actions / GitLab CI — step-level extraction.
//
// We segment on list items and carry each step's literal block. No YAML parse:
// a workflow that we half-understand is worse than a workflow we quote exactly.
// ---------------------------------------------------------------------------

function gatherWorkflow(path: string, rel: string, nodes: Node[]): void {
  const text = readFileSync(path, 'utf8');
  const lines = text.split('\n');

  let cur: string[] = [];
  let curStart = 0;
  let curIndent = -1;

  const flush = () => {
    if (!cur.length) return;
    const raw = cur.join('\n').trimEnd();
    // A step is interesting if it runs something or invokes an action.
    // The `-?` is load-bearing: `- uses: x` puts a list dash between the
    // indent and the key, and \s* cannot cross it.
    if (/(^|\n)\s*-?\s*(run|uses)\s*:/.test(raw)) {
      const nameMatch = raw.match(/^\s*-?\s*name\s*:\s*(.+)$/m);
      const usesMatch = raw.match(/^\s*-?\s*uses\s*:\s*(.+)$/m);
      const runMatch = raw.match(/^\s*-?\s*run\s*:\s*(.+)$/m);
      const name =
        nameMatch?.[1]?.trim().replace(/^["']|["']$/g, '') ??
        usesMatch?.[1]?.trim() ??
        runMatch?.[1]?.trim().slice(0, 60) ??
        'step';
      nodes.push({
        id: mkId(rel, `${curStart}-${name}`),
        kind: 'ci_step',
        name,
        source: `${rel}:${curStart}`,
        raw,
        hints: usesMatch ? { action: usesMatch[1].trim() } : undefined,
      });
    }
    cur = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const m = line.match(/^(\s*)-\s/);
    if (m) {
      const indent = m[1].length;
      if (curIndent === -1 || indent <= curIndent) {
        flush();
        curIndent = indent;
        curStart = i + 1;
      }
      cur.push(line);
    } else if (cur.length) {
      const indent = line.match(/^(\s*)/)![1].length;
      if (line.trim() === '' || indent > curIndent) cur.push(line);
      else {
        flush();
        curIndent = -1;
      }
    }
  }
  flush();
}

// ---------------------------------------------------------------------------
// package.json scripts
// ---------------------------------------------------------------------------

function gatherPackageJson(path: string, rel: string, nodes: Node[]): void {
  let pkg: Record<string, unknown>;
  try {
    pkg = JSON.parse(readFileSync(path, 'utf8'));
  } catch {
    return;
  }
  const scripts = pkg.scripts as Record<string, string> | undefined;
  if (!scripts) return;
  for (const [name, cmd] of Object.entries(scripts)) {
    nodes.push({
      id: mkId(rel, name),
      kind: 'script',
      name,
      source: rel,
      raw: `"${name}": "${cmd}"`,
    });
  }
}

// ---------------------------------------------------------------------------
// Makefile targets
// ---------------------------------------------------------------------------

function gatherMakefile(path: string, rel: string, nodes: Node[]): void {
  const lines = readFileSync(path, 'utf8').split('\n');
  let cur: string[] = [];
  let name = '';
  let start = 0;

  const flush = () => {
    if (name && cur.length) {
      nodes.push({
        id: mkId(rel, name),
        kind: 'script',
        name,
        source: `${rel}:${start}`,
        raw: cur.join('\n').trimEnd(),
      });
    }
    cur = [];
    name = '';
  };

  for (let i = 0; i < lines.length; i++) {
    const t = lines[i].match(/^([a-zA-Z0-9_.-]+)\s*:(?!=)/);
    // `.PHONY` and friends are Make DIRECTIVES, not targets. Skipping them is
    // parsing, not judging — they cannot be a verification edge in any repo.
    if (t && t[1].startsWith('.')) {
      flush();
      continue;
    }
    if (t) {
      flush();
      name = t[1];
      start = i + 1;
      cur.push(lines[i]);
    } else if (name && (lines[i].startsWith('\t') || lines[i].trim() === '')) {
      cur.push(lines[i]);
    } else if (name) {
      flush();
    }
  }
  flush();
}

// ---------------------------------------------------------------------------
// pyproject.toml — where modern Python repos declare their verification.
// Same posture as the workflow gatherer: no TOML parse, locate the sections
// that declare checks and carry the literal block forward.
// ---------------------------------------------------------------------------

const PYPROJECT_SECTIONS: Array<[RegExp, NodeKind, string]> = [
  [/^tool\.pytest(\..*)?$/, 'test_target', 'pytest config'],
  [/^tool\.tox(\..*)?$/, 'test_target', 'tox config'],
  [/^tool\.(ruff|mypy|pyright|flake8|isort)(\..*)?$/, 'ci_step', 'linter/type-checker config'],
  [/^tool\.coverage(\..*)?$/, 'ci_step', 'coverage config'],
];

function gatherPyproject(path: string, rel: string, nodes: Node[]): void {
  const lines = readFileSync(path, 'utf8').split('\n');
  let section = '';
  let cur: string[] = [];
  let start = 0;
  let kind: NodeKind | null = null;
  let label = '';

  const flush = () => {
    if (kind && cur.length) {
      nodes.push({
        id: mkId(rel, section),
        kind,
        name: `${label} ([${section}])`,
        source: `${rel}:${start}`,
        raw: cur.join('\n').trimEnd(),
      });
    }
    cur = [];
    kind = null;
  };

  for (let i = 0; i < lines.length; i++) {
    const h = lines[i].match(/^\[([^\]]+)\]/);
    if (h) {
      flush();
      section = h[1];
      start = i + 1;
      for (const [re, k, l] of PYPROJECT_SECTIONS) {
        if (re.test(section)) {
          kind = k;
          label = l;
          break;
        }
      }
      if (kind) cur.push(lines[i]);
    } else if (kind) {
      cur.push(lines[i]);
    }
  }
  flush();
}

// ---------------------------------------------------------------------------
// Rakefile targets — Ruby's Make. Same role, different surface.
//
// We take `task :name` only. Task-defining DSLs (RDoc::Task.new and friends)
// are deliberately NOT matched: guessing at what a gem's DSL declares would be
// judging, and this file does not judge.
// ---------------------------------------------------------------------------

function gatherRakefile(path: string, rel: string, nodes: Node[]): void {
  const lines = readFileSync(path, 'utf8').split('\n');

  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^(\s*)task\s+:?["']?([A-Za-z0-9_]+)/);
    if (!m) continue;

    const [, indent, name] = m;
    const start = i + 1;
    const cur = [lines[i]];

    // A `do` block runs to its matching `end` at the same indentation.
    // Without one, the task is a single-line declaration (`task default: :spec`).
    if (/\bdo\b/.test(lines[i])) {
      const closer = new RegExp(`^${indent}end\\s*$`);
      for (let j = i + 1; j < lines.length; j++) {
        cur.push(lines[j]);
        if (closer.test(lines[j])) {
          i = j;
          break;
        }
      }
    }

    nodes.push({
      id: mkId(rel, name),
      kind: 'script',
      name,
      source: `${rel}:${start}`,
      raw: cur.join('\n').trimEnd(),
    });
  }
}

// ---------------------------------------------------------------------------
// Travis CI — command keys, scalar or list.
//
// Travis does not use `- run:`, so the workflow segmenter cannot see it: the
// commands hang off well-known top-level keys instead.
// ---------------------------------------------------------------------------

const TRAVIS_KEYS = ['install', 'before_install', 'before_script', 'script', 'after_script'];

function gatherTravis(path: string, rel: string, nodes: Node[]): void {
  const lines = readFileSync(path, 'utf8').split('\n');

  for (let i = 0; i < lines.length; i++) {
    const m = lines[i].match(/^([a-z_]+)\s*:\s*(.*)$/);
    if (!m || !TRAVIS_KEYS.includes(m[1])) continue;

    const key = m[1];
    const start = i + 1;
    const cur = [lines[i]];

    // Scalar form (`script: bundle exec rspec`) ends on its own line; list form
    // continues through the indented `- ` items beneath it.
    if (m[2].trim() === '') {
      for (let j = i + 1; j < lines.length; j++) {
        if (!/^\s+\S/.test(lines[j]) && lines[j].trim() !== '') break;
        cur.push(lines[j]);
        i = j;
      }
    }

    nodes.push({
      id: mkId(rel, key),
      kind: 'ci_step',
      name: key,
      source: `${rel}:${start}`,
      raw: cur.join('\n').trimEnd(),
    });
  }
}

// ---------------------------------------------------------------------------
// Config files that declare verification (test runners, hooks, linters)
// ---------------------------------------------------------------------------

const CONFIG_PATTERNS: Array<[RegExp, NodeKind, string]> = [
  [/^\.pre-commit-config\.ya?ml$/, 'review_gate', 'pre-commit hooks'],
  [/^(vitest|jest|playwright|cypress)\.config\.[jt]s$/, 'test_target', 'test runner config'],
  [/^pytest\.ini$|^tox\.ini$|^conftest\.py$/, 'test_target', 'pytest config'],
  [/^(biome|eslint|ruff)\.(json|jsonc|ya?ml|toml)$/, 'ci_step', 'linter config'],
  [/^\.golangci\.ya?ml$/, 'ci_step', 'linter config'],
  [/^\.rubocop\.ya?ml$/, 'ci_step', 'linter config'],
  [/^\.rspec$/, 'test_target', 'rspec config'],
  [/^codecov\.ya?ml$/, 'ci_step', 'coverage gate'],
  [/^renovate\.json$|^dependabot\.ya?ml$/, 'ci_step', 'dependency automation'],
  [/^CODEOWNERS$/, 'review_gate', 'code owners'],
  [/^(vercel|now)\.json$|^netlify\.toml$|^fly\.toml$|^wrangler\.(toml|jsonc?)$|^render\.ya?ml$/, 'deploy_gate', 'deploy config'],
  [/^\.releaserc(\.(json|ya?ml|js|cjs))?$|^release\.config\.[cm]?js$/, 'deploy_gate', 'release automation'],
];

function gatherConfig(path: string, rel: string, nodes: Node[]): void {
  const base = basename(path);
  for (const [re, kind, label] of CONFIG_PATTERNS) {
    if (!re.test(base)) continue;
    const raw = readFileSync(path, 'utf8').slice(0, 4000);
    nodes.push({
      id: mkId(rel, base),
      kind,
      name: `${label} (${base})`,
      source: rel,
      raw,
    });
    return;
  }
}

// ---------------------------------------------------------------------------
// COVERAGE — what this gatherer recognised and could not read.
//
// The failure this closes is Keel's own shoppable class, and the frozen schema
// names it in as many words (`coverageByKind`): "surfaces the gatherer cannot
// read are silently absent rather than `unknown`". Point Keel at a Jenkins shop
// and it gathers the residue it happens to understand — package.json scripts, a
// Makefile — and publishes a ratio over that. The output is byte-identical to a
// repo with no verification at all, which is the one comparison that must never
// be ambiguous: `unknown` fails closed precisely so that not-looking cannot pass
// as looking, and a surface we never opened is not-looking with the evidence
// removed.
//
// This is recognition, NOT judgment, and the distinction is load-bearing because
// a table in the gatherer is exactly the artifact this tool exists to detect.
// The tables below map a filename to the NAME OF A TOOL — "Jenkinsfile is
// Jenkins" is a fact about a filename, decided by Jenkins, not a claim about
// what the file contains or how well it verifies anything. Nothing here assigns
// a GroundingClass, and nothing here can: an unread surface produces no node, so
// there is nothing for a verdict to attach to. It produces a WARNING beside the
// ratio instead.
//
// The claim is also structurally prevented from over-reporting. A file is only
// tested against `UNREAD_FILES` after every parser has declined it AND
// `gatherConfig` came back empty — so the moment someone teaches this file to
// read Jenkinsfiles, the blindness claim about them disappears on its own rather
// than surviving as stale prose. Claiming blindness you no longer have is its
// own kind of dishonesty, and it degrades the same way an unmaintained lookup
// table does.
// ---------------------------------------------------------------------------

/** A surface recognised by name that no parser here reads. */
export interface UnreadSurface {
  /** relative to the target root */
  path: string;
  kind: 'file' | 'dir';
  /** the tool this filename belongs to. A NAME, not a verdict. */
  tool: string;
}

/**
 * A CI definition a parser DID open and which yielded no node.
 *
 * Distinct from unread, and not a lesser case of it: the file was read, so the
 * gatherer's own parser is what came back empty. `.gitlab-ci.yml` is the live
 * example — it routes to the workflow segmenter, which keys on `run:`/`uses:`,
 * and GitLab spells its commands as a bare `script:` list, so a full GitLab
 * pipeline can pass through and leave nothing behind. Reporting that as "unread"
 * would be false, and reporting it as nothing at all is how the ratio ends up
 * describing a repo's package.json instead of its CI.
 *
 * Only CI-definition parsers are tracked. A `package.json` with no `scripts`
 * block is not a parser failure — it is a file with no verification in it — and
 * counting every such file would bury the signal in noise.
 */
export interface SilentSurface {
  path: string;
  /** the reader that opened it and came back with nothing */
  parser: string;
}

/**
 * A surface the gatherer TRIED to read and could not.
 *
 * Three sources, one category, because the consequence is identical: the walk
 * could not enumerate a directory (a target that is a file, an unreadable
 * tree), the walk hit its depth limit, or a parser threw partway through a
 * file. None of them is `unread` — that class means "recognised by name, no
 * parser exists" — and none of them is `silent`, which means the file was read
 * cleanly and the reader came back empty. A parser that threw filed as `silent`
 * makes the report say two things that are both false: that the file was read,
 * and that the gap is in the parser rather than in the read.
 *
 * `reason` is the errno message or the depth cutoff, carried verbatim. It is a
 * fact about what happened, not a verdict, and like every other entry here it
 * carries no `GroundingClass`.
 */
export interface BlindSurface {
  path: string;
  /** what was attempted: `walk`, or the name of the parser that threw. */
  by: string;
  /** why it stopped. */
  reason: string;
}

export interface GatherCoverage {
  schema: 'keel.gather-coverage.v1';
  target: string;
  nodesGathered: number;
  unread: UnreadSurface[];
  silent: SilentSurface[];
  blind: BlindSurface[];
  note: string;
}

const COVERAGE_NOTE =
  'A ratio computed over the nodes this gatherer could read says nothing about the surfaces listed here. A repo whose real verification lives in an unread surface reads exactly like a repo with no verification at all, and that ambiguity — not a low score — is the failure this list exists to prevent. These paths carry no verdict and no class: an unread surface produces no node, so there is nothing to classify. Read them by hand, or teach gather.ts to read them, before quoting the number.';

/**
 * Filenames that belong to a verification tool this file has no parser for.
 *
 * Deliberately ABSENT, because they are already read and claiming them would be
 * a lie in the other direction: `.travis.yml` (gatherTravis), `.gitlab-ci.yml`
 * and `.github/`+`.circleci/` YAML (gatherWorkflow), `.pre-commit-config.yaml`,
 * `tox.ini`, `pytest.ini` and the rest of CONFIG_PATTERNS, `pyproject.toml`,
 * `Makefile`, `Rakefile`, `package.json`.
 */
const UNREAD_FILES: Array<[RegExp, string]> = [
  [/^Jenkinsfile(\..+)?$/, 'Jenkins'],
  [/^azure-pipelines.*\.ya?ml$/, 'Azure Pipelines'],
  [/^bitbucket-pipelines\.ya?ml$/, 'Bitbucket Pipelines'],
  [/^\.drone\.ya?ml$/, 'Drone CI'],
  [/^\.cirrus\.(ya?ml|star)$/, 'Cirrus CI'],
  [/^\.woodpecker\.ya?ml$/, 'Woodpecker CI'],
  [/^\.?appveyor\.ya?ml$/, 'AppVeyor'],
  [/^cloudbuild\.ya?ml$/, 'Google Cloud Build'],
  [/^buildspec\.ya?ml$/, 'AWS CodeBuild'],
  [/^(BUILD|BUILD\.bazel|WORKSPACE|WORKSPACE\.bazel|MODULE\.bazel)$/, 'Bazel'],
  [/^(build|settings)\.gradle(\.kts)?$/, 'Gradle'],
  [/^pom\.xml$/, 'Maven'],
  [/^Earthfile$/, 'Earthly'],
  [/^dagger\.json$/, 'Dagger'],
  [/^flake\.nix$/, 'Nix flake'],
  [/^[Tt]askfile(\.dist)?\.ya?ml$/, 'Task'],
  [/^[Jj]ustfile$/, 'Just'],
  [/^noxfile\.py$/, 'nox'],
];

/**
 * Dot-directories the walk refuses to enter. Everything inside one is invisible
 * — not skimmed, not partially read — so the directory is reported whole.
 */
const UNREAD_DIRS: Array<[RegExp, string]> = [
  [/^\.buildkite$/, 'Buildkite'],
  [/^\.teamcity$/, 'TeamCity'],
  [/^\.woodpecker$/, 'Woodpecker CI'],
  [/^\.semaphore$/, 'Semaphore CI'],
  [/^\.gitea$/, 'Gitea Actions'],
  [/^\.forgejo$/, 'Forgejo Actions'],
  [/^\.harness$/, 'Harness'],
  [/^\.azure-pipelines$/, 'Azure Pipelines'],
  [/^\.jenkins$/, 'Jenkins'],
  // Local gates. These are verification edges by anyone's definition — a
  // pre-commit hook refuses a commit, and a policy file declares which
  // operations are blocked — and this gatherer reads neither. Naming them is
  // not an admission of a missing feature so much as the difference between
  // "we do not gather local gates" and silence, and silence is the shape this
  // whole list exists to prevent. Keel is its own worst case here: it refuses
  // `.control/` and `.githooks/` while measuring itself, so its own report was
  // clean about surfaces it had never opened.
  [/^\.githooks$/, 'git hooks'],
  [/^\.husky$/, 'Husky'],
  [/^\.control$/, 'policy gates'],
];

/** Readers whose silence means the gatherer failed, not that the file is empty. */
const CI_DEFINITION_PARSERS = new Set(['workflow-steps', 'travis-keys']);

function toolFor(
  name: string,
  table: Array<[RegExp, string]>,
): string | undefined {
  for (const [re, tool] of table) if (re.test(name)) return tool;
  return undefined;
}

// ---------------------------------------------------------------------------

/**
 * The full result of a walk: the nodes, and the record of what was not read.
 *
 * `gather()` stays `Node[]` and stays the entry point every consumer already
 * uses — classify.ts and corpus.ts both parse that array, and widening it would
 * break them for a payload neither one needs. The coverage record is offered
 * beside the nodes to callers that ask for it.
 */
export function gatherWithCoverage(target: string): {
  nodes: Node[];
  coverage: GatherCoverage;
} {
  const nodes: Node[] = [];
  const st: WalkState = { files: [], refused: [], failed: [] };
  walk(target, st);
  const unread: UnreadSurface[] = [];
  const silent: SilentSurface[] = [];
  const blind: BlindSurface[] = [];

  // A path the walk never finished. `.` is the target itself — the shape you
  // get by pointing this at a file, which otherwise gathers zero nodes and
  // reports a clean sweep.
  for (const f of st.failed) {
    blind.push({ path: relative(target, f.dir) || '.', by: 'walk', reason: f.reason });
  }

  for (const d of st.refused) {
    const tool = toolFor(basename(d), UNREAD_DIRS);
    if (tool) unread.push({ path: relative(target, d), kind: 'dir', tool });
  }

  for (const f of st.files) {
    const rel = relative(target, f);
    const base = basename(f);
    const before = nodes.length;
    let parser = '';
    let threw: Error | null = null;

    try {
      if (
        /^\.github\/workflows\/.+\.ya?ml$/.test(rel) ||
        /^\.circleci\/.+\.ya?ml$/.test(rel) ||
        base === '.gitlab-ci.yml'
      ) {
        // CircleCI segments on `- run:` exactly like Actions does, so the same
        // literal-carrying segmenter reads both without special-casing.
        // Glob rather than `config.yml` exactly: .circleci/ can hold more.
        parser = 'workflow-steps';
        gatherWorkflow(f, rel, nodes);
      } else if (base === '.travis.yml') {
        parser = 'travis-keys';
        gatherTravis(f, rel, nodes);
      } else if (base === 'package.json' && !rel.includes('node_modules')) {
        parser = 'package-scripts';
        gatherPackageJson(f, rel, nodes);
      } else if (base === 'pyproject.toml') {
        parser = 'pyproject-sections';
        gatherPyproject(f, rel, nodes);
      } else if (base === 'Makefile' || base === 'makefile') {
        parser = 'make-targets';
        gatherMakefile(f, rel, nodes);
      } else if (base === 'Rakefile' || base === 'rakefile') {
        parser = 'rake-tasks';
        gatherRakefile(f, rel, nodes);
      } else {
        parser = 'config-patterns';
        if (statSync(f).size < 200_000) gatherConfig(f, rel, nodes);
        // Tested here and only here, so the claim "we cannot read this" is made
        // downstream of every parser that might have. A file that produced a
        // node is read by definition and never reaches this branch.
        if (nodes.length === before) {
          const tool = toolFor(base, UNREAD_FILES);
          if (tool) unread.push({ path: rel, kind: 'file', tool });
        }
      }
    } catch (err) {
      // A file we cannot read is not a verification edge we can classify — no
      // node, and certainly no `unknown`, which is for edges we FOUND but
      // cannot trace. But the throw itself is a fact about this run, and
      // swallowing it here is what let a parser that DIED get filed below as
      // "read, and silent about it": the card then stated that the file was
      // read and that the gap was in the reader, and neither was true.
      threw = err as Error;
    }

    if (threw) {
      blind.push({ path: rel, by: parser || 'unrouted', reason: threw.message });
    } else if (nodes.length === before && CI_DEFINITION_PARSERS.has(parser)) {
      silent.push({ path: rel, parser });
    }
  }

  return {
    nodes,
    coverage: {
      schema: 'keel.gather-coverage.v1',
      target,
      nodesGathered: nodes.length,
      unread,
      silent,
      blind,
      note: COVERAGE_NOTE,
    },
  };
}

export function gather(target: string): Node[] {
  return gatherWithCoverage(target).nodes;
}

const USAGE =
  'usage: bun scripts/gather.ts <target-dir> [--json] [--coverage <file>]\n\n' +
  '  --json            print the gathered nodes as JSON (Node[])\n' +
  '  --coverage <file> write the coverage record — the surfaces recognised\n' +
  '                    and NOT read — to <file> as JSON. render.ts picks it up\n' +
  '                    as <report>.coverage.json beside the report.';

/**
 * Why the coverage record goes to a FILE and never onto stdout.
 *
 * `--json` prints `Node[]`, and classify.ts and corpus.ts both parse exactly
 * that. Wrapping it in an envelope to make room for coverage would break both;
 * printing a second document after it would break any consumer reading stdout as
 * one JSON value; and switching the shape of stdout based on which flags are
 * present is how a caller ends up parsing something it did not ask for. So
 * stdout's shape is invariant under every flag combination, and coverage is
 * opt-in through a path the caller names — which is also the path render.ts
 * wants, since it reads the record as a sibling of report.json.
 */
if (import.meta.main) {
  const argv = process.argv.slice(2);
  let target = '';
  let coveragePath = '';
  let json = false;

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i] as string;
    if (a === '--json') {
      json = true;
    } else if (a === '--coverage') {
      const value = argv[i + 1];
      // A flag whose value is missing or is another flag is an error, not a
      // default: silently skipping the write would report success for a file
      // nobody wrote, on the one output that exists to say what went unreported.
      if (value === undefined || value === '' || value.startsWith('-')) {
        console.error(`gather: --coverage requires a path\n\n${USAGE}`);
        process.exit(1);
      }
      coveragePath = value;
      i++;
    } else if (a.startsWith('-')) {
      // A flag we do not know is refused rather than skipped. `--coverge out.json`
      // used to parse as a no-op and a stray positional: exit 0, nothing written,
      // and a caller who believes they have a coverage record. On the one output
      // whose subject is unreported absence, a typo must not read as success.
      console.error(`gather: unknown flag ${a}\n\n${USAGE}`);
      process.exit(1);
    } else {
      target = a;
    }
  }

  if (!target || !existsSync(target)) {
    console.error(USAGE);
    process.exit(1);
  }

  const { nodes, coverage } = gatherWithCoverage(target);

  if (coveragePath) {
    // A write that fails must say so in this tool's own voice and exit non-zero.
    // An uncaught throw here exits 1 too, but it exits 1 with a stack trace and
    // a Bun banner, which reads as a broken tool rather than a refused write.
    try {
      mkdirSync(dirname(resolve(coveragePath)), { recursive: true });
      writeFileSync(coveragePath, `${JSON.stringify(coverage, null, 2)}\n`);
    } catch (err) {
      console.error(`gather: cannot write ${coveragePath} — ${(err as Error).message}`);
      process.exit(1);
    }
    console.error(
      `wrote ${coveragePath} — ${coverage.unread.length} unread, ` +
        `${coverage.silent.length} read-but-silent, ${coverage.blind.length} unreadable`,
    );
  }

  if (json) {
    console.log(JSON.stringify(nodes, null, 2));
  } else {
    const byKind = nodes.reduce<Record<string, number>>((a, n) => {
      a[n.kind] = (a[n.kind] ?? 0) + 1;
      return a;
    }, {});
    console.log(`gathered ${nodes.length} candidate verification edges from ${target}\n`);
    for (const [k, v] of Object.entries(byKind).sort((a, b) => b[1] - a[1])) {
      console.log(`  ${String(v).padStart(4)}  ${k}`);
    }

    // Printed unconditionally, including the empty state. "Nothing was left
    // unread" is a result a reader needs in order to know the count above
    // covers the surface; printing the list only when it is non-empty would
    // make its absence unreadable — silence would mean both "we looked and
    // found nothing" and "nobody checked".
    // `blind` is in this condition and not merely in the list below it. The
    // clean claim is a claim about the whole tree, and a walk that could not
    // open a directory — or stopped at its depth limit — has no standing to
    // make it. Printing "nothing was left unread" on top of a read failure is
    // the exact fail-open this record exists to close.
    if (
      coverage.unread.length === 0 &&
      coverage.silent.length === 0 &&
      coverage.blind.length === 0
    ) {
      console.log('\nno recognised verification surface was left unread.');
    } else {
      if (coverage.unread.length > 0) {
        console.log(
          `\nrecognised but NOT read — ${coverage.unread.length} surface(s) no parser here opens:`,
        );
        for (const u of coverage.unread) {
          console.log(`  ${u.tool.padEnd(20)}  ${u.path}${u.kind === 'dir' ? '/' : ''}`);
        }
      }
      if (coverage.silent.length > 0) {
        console.log(
          `\nread but silent — ${coverage.silent.length} CI definition(s) a parser opened and got nothing from:`,
        );
        for (const s of coverage.silent) {
          console.log(`  ${s.parser.padEnd(20)}  ${s.path}`);
        }
      }
      if (coverage.blind.length > 0) {
        console.log(
          `\ncould not be read — ${coverage.blind.length} surface(s) this gatherer opened and failed on:`,
        );
        for (const b of coverage.blind) {
          console.log(`  ${b.by.padEnd(20)}  ${b.path}\n${' '.repeat(24)}${b.reason}`);
        }
      }
      console.log(
        '\nany ratio computed from the edges above describes what could be read, not this target.',
      );
    }

    console.log('\nnothing here is classified yet — that is the agent\'s job.');
  }
}
