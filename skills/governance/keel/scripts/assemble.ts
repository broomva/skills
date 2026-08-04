#!/usr/bin/env bun
/**
 * keel assemble — stage 3: turn nodes + verdicts into a Report, or refuse.
 *
 *   bun scripts/assemble.ts <nodes.json> <verdicts.json>... -o <report.json>
 *
 * This is the step that had no tooling, and it is the one with the most to lose.
 * `classify` emits `{decided, pending, warnings}`; `render`, `route` and `curve`
 * all consume a `Report`. Between them sat a 260-line frozen schema, no
 * template, no example and no validator — so the agent hand-authored JSON and
 * the first thing that told it otherwise was `render` rejecting the file, long
 * after the judgments were made and the context that produced them was gone.
 *
 * ---------------------------------------------------------------------------
 * What this file is NOT
 * ---------------------------------------------------------------------------
 * It merges and validates. It CLASSIFIES NOTHING. Every class in the output was
 * authored upstream by a probe or by the agent; nothing here reads a node's name
 * and decides anything about it. A lookup table from check-name to class is the
 * exact ungrounded artifact Keel exists to detect, and it would be no less one
 * for living in the assembler.
 *
 * ---------------------------------------------------------------------------
 * Why each refusal exists (they are failure modes, not tidiness)
 * ---------------------------------------------------------------------------
 *  - A node with NO verdict is fatal, not skipped. A report computed over a
 *    subset publishes a ratio over fewer edges than were gathered while the
 *    node list says otherwise, and nothing in the artifact says so. That is
 *    precisely the shape Keel exists to detect, and shipping it from Keel's own
 *    assembler would be the joke telling itself. When a run really did judge a
 *    sample, `--gathered` makes the cap VISIBLE (economics.nodesSampled <
 *    nodesTotal, which render prints beside the ratio) instead of invisible.
 *  - A verdict for an unknown node is fatal because the likeliest cause is two
 *    files from two different runs, and the second-likeliest is a typo'd id
 *    whose real node is therefore also unjudged. Both produce a plausible
 *    number over the wrong world.
 *  - Two verdicts for one node is fatal because whichever we kept would be an
 *    arbitrary choice between two classifications — and the one that lost would
 *    disappear without trace.
 *  - A verdict with a blank `writeBoundary.argument` is fatal. A class without
 *    its causal path is an unaccountable green check: unreviewable, and
 *    indistinguishable from a guess. (`.github/workflows/test.yml` already
 *    enforces this against the committed fixture; enforcing it here means the
 *    file never gets written in that state.)
 *  - The grounding block is COMPUTED, always, by `groundingRatio()` from the
 *    frozen schema — never read from the input. A ratio a caller can hand us is
 *    a number the thing being measured can write to.
 *  - An EMPTY node list is fatal. `groundingRatio([])` returns `ratio: 0`, which
 *    reads as "nothing here is anchored" when the truth is "nothing was
 *    measured". SKILL.md § Output: *a target with zero gathered nodes gets an
 *    explicit "nothing gathered" state, never a ratio* — and `corpus.ts` already
 *    implements that state by writing NO report. So assemble refuses rather than
 *    minting the one artifact that state is defined by its absence.
 *
 * Every problem found is reported in ONE run. A validator that dies on the
 * first bad verdict turns a forty-verdict file into forty invocations, and the
 * agent fixing them one at a time is the failure mode that made hand-authoring
 * expensive in the first place.
 *
 * ---------------------------------------------------------------------------
 * `warnings` and the frozen schema
 * ---------------------------------------------------------------------------
 * `classify` produces warnings — skipped probes, dead sandbox children, load
 * rejections — and they describe how much of the run's machinery actually ran.
 * `Report` (frozen) has nowhere to put them. Dropping them would make the
 * artifact quieter than the run that produced it, so `--warnings` carries them
 * as a top-level `warnings` array, and the key is OMITTED when empty — a report
 * assembled from a clean run is byte-identical to a schema-exact `Report`.
 * Consumers ignore unknown keys today; if the schema should carry this field,
 * that is the orchestrator's call, not this file's.
 *
 * A ClassifyOutput passed as a POSITIONAL verdicts file carries its warnings the
 * same way — the warnings describe the run that produced those verdicts, and
 * making the caller pass the same file twice to keep them was a trap.
 *
 * ---------------------------------------------------------------------------
 * Which economics are zero, and why that is not uniform
 * ---------------------------------------------------------------------------
 * `tokensIn/Out`, `wallClockMs` and `probesMinted` are zero because nothing in
 * this process measured them; inventing them would put an unmeasured number in
 * the artifact whose subject is unmeasured numbers. `probeLibrarySize` is NOT in
 * that class — it is one `readdir` away — so it is derived from `--probes <dir>`
 * (counted exactly as `corpus.ts` counts it: distinct ids, not files) or handed
 * over explicitly with `--probe-library-size`. Publishing zero for a run that
 * loaded probes is not a floor, it is a false statement.
 */

import {
  existsSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  statSync,
  writeFileSync,
} from 'node:fs';
import { basename, dirname, join, resolve } from 'node:path';
import type {
  ClassifyOutput,
  GroundingClass,
  Node,
  Report,
  RunEconomics,
  Verdict,
} from '../schemas/keel.ts';
import { groundingRatio } from '../schemas/keel.ts';

const CLASSES: readonly GroundingClass[] = [
  'anchored',
  'self_referential',
  'unknown',
  'not_a_check',
];

const DECIDED_BY: readonly Verdict['decidedBy'][] = ['probe', 'agent'];

/** How many ids a single problem line names before it summarizes the rest. */
const MAX_NAMED = 8;
/** How many problem lines are printed before the tail is summarized. */
const MAX_PROBLEMS = 25;

/**
 * A `Report` plus the run's non-fatal problems. See the header: the schema is
 * frozen and has no field for them, and losing them is worse than carrying them
 * in a key consumers ignore.
 */
export type AssembledReport = Report & { warnings?: string[] };

// ---------------------------------------------------------------------------
// Small utilities
// ---------------------------------------------------------------------------

function errText(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function quoted(s: string): string {
  return `\`${s}\``;
}

/** Name things in an error, but never print a hundred of them. */
function nameSome(labels: string[], cap = MAX_NAMED): string {
  const shown = labels.slice(0, cap).join(', ');
  return labels.length <= cap ? shown : `${shown} …and ${labels.length - cap} more`;
}

function isObject(v: unknown): v is Record<string, unknown> {
  return typeof v === 'object' && v !== null && !Array.isArray(v);
}

function nonEmpty(v: unknown): v is string {
  return typeof v === 'string' && v.trim() !== '';
}

function readJson(path: string): unknown | { error: string } {
  let text: string;
  try {
    text = readFileSync(path, 'utf8');
  } catch (e) {
    return { error: `cannot read ${path}: ${errText(e)}` };
  }
  try {
    return JSON.parse(text);
  } catch (e) {
    return { error: `${path} is not valid JSON: ${errText(e)}` };
  }
}

function isError(v: unknown): v is { error: string } {
  return isObject(v) && typeof v.error === 'string';
}

/** Order-preserving dedupe. Two files may carry the same warning verbatim. */
function uniq(items: string[]): string[] {
  return [...new Set(items)];
}

// ---------------------------------------------------------------------------
// Probe library size
//
// Same counting rule as `corpus.ts` (probeLibrarySize, ~line 391): probe files
// are `<id>.v<version>.ts` and the loader takes the highest version per id, so
// counting FILES would inflate the library size that the crystallization curve
// is plotted against. Distinct ids is the number, and it must be the same number
// on both sides or two runs of the same library disagree about its size.
//
// Divergence from corpus on ONE point, deliberately: corpus resolves a default
// set and treats a missing directory as "no probes", because it is discovering
// what happens to be installed. Here the directory was NAMED by the caller, and
// silently counting an unreadable one as zero would understate the library in a
// report — so it is fatal.
// ---------------------------------------------------------------------------

function probeLibrarySize(dirs: string[]): number | { error: string } {
  const ids = new Set<string>();
  for (const dir of dirs) {
    let entries: string[];
    try {
      entries = readdirSync(dir);
    } catch (e) {
      return {
        error: `--probes ${dir}: cannot read it (${errText(e)}) — counting it as zero would understate the library the report claims to describe`,
      };
    }
    for (const f of entries) {
      if (!f.endsWith('.ts') || f.endsWith('.d.ts')) continue;
      const m = f.match(/^(.*)\.v\d+\.ts$/);
      ids.add(m ? (m[1] as string) : f.slice(0, -3));
    }
  }
  return ids.size;
}

// ---------------------------------------------------------------------------
// Input
// ---------------------------------------------------------------------------

function loadNodes(path: string): Node[] | { error: string } {
  const parsed = readJson(path);
  if (isError(parsed)) return parsed;
  if (!Array.isArray(parsed)) {
    return {
      error: `${path} must contain a Node[] array — this is gather's \`--json\` output`,
    };
  }
  const seen = new Set<string>();
  const duplicates: string[] = [];
  for (const [i, n] of parsed.entries()) {
    if (!isObject(n) || !nonEmpty(n.id)) {
      return { error: `${path}[${i}] has no string \`id\`` };
    }
    // Two nodes sharing an id make "does every node have a verdict" ambiguous
    // and double-count in coverage — gather's ids are `${source}#${slug}`, so a
    // collision means two edges were flattened into one.
    if (seen.has(n.id)) duplicates.push(n.id);
    seen.add(n.id);
  }
  if (duplicates.length > 0) {
    return {
      error: `${path} contains duplicate node id(s): ${nameSome(duplicates.map(quoted))} — ids must be unique; re-run gather or disambiguate the source`,
    };
  }
  return parsed as Node[];
}

/** A verdict plus the file it came from, so every problem line names a file. */
export interface SourcedVerdict {
  verdict: Verdict;
  from: string;
  index: number;
}

/**
 * Accepts a `Verdict[]` OR a `ClassifyOutput` (taking `decided`).
 *
 * Both, because a real run produces verdicts in at least two places: the probe
 * cache decided some (`classify --json`, a ClassifyOutput) and the agent judged
 * the rest (a bare array). Requiring the caller to reshape one into the other
 * puts hand-edited JSON back on the path this tool exists to remove.
 */
function loadVerdicts(
  path: string,
): { sourced: SourcedVerdict[]; warnings: string[] } | { error: string } {
  const parsed = readJson(path);
  if (isError(parsed)) return parsed;

  const co = parsed as Partial<ClassifyOutput>;
  let list: unknown;
  if (Array.isArray(parsed)) list = parsed;
  else if (isObject(parsed) && Array.isArray(co.decided)) list = co.decided;
  else {
    return {
      error: `${path} must contain a Verdict[] array, or a ClassifyOutput with a \`decided\` array`,
    };
  }

  // A ClassifyOutput's warnings say how much of the run that produced these
  // verdicts actually ran (probes skipped, sandbox children killed, loads
  // rejected). Dropping them here — and only carrying them when the SAME file is
  // passed a second time as `--warnings` — made the report quieter than its run
  // for the most ordinary invocation there is.
  const warnings = Array.isArray(co.warnings)
    ? co.warnings.map((w) => (typeof w === 'string' ? w : JSON.stringify(w)))
    : [];

  return {
    sourced: (list as unknown[]).map((v, index) => ({
      verdict: v as Verdict,
      from: path,
      index,
    })),
    warnings,
  };
}

/**
 * `--warnings` takes a ClassifyOutput, or the array on its own — `jq .warnings`
 * is the obvious way to get at them and refusing it would be pedantry.
 */
function loadWarnings(path: string): string[] | { error: string } {
  const parsed = readJson(path);
  if (isError(parsed)) return parsed;
  const co = parsed as Partial<ClassifyOutput>;
  const list = Array.isArray(parsed)
    ? parsed
    : isObject(parsed) && Array.isArray(co.warnings)
      ? co.warnings
      : null;
  if (list === null) {
    return {
      error: `${path} must contain a ClassifyOutput (with a \`warnings\` array) or a string[]`,
    };
  }
  return list.map((w) => (typeof w === 'string' ? w : JSON.stringify(w)));
}

// ---------------------------------------------------------------------------
// Validation
//
// Structural only. Every check below asks "is this a well-formed statement",
// never "is this statement true" — the truth of a verdict is the reviewer's
// question and the ε-audit's, not the assembler's.
// ---------------------------------------------------------------------------

/** Problems with ONE verdict. Empty means well-formed, not means correct. */
function verdictProblems(sv: SourcedVerdict): string[] {
  const at = `${sv.from}[${sv.index}]`;
  const v = sv.verdict as unknown;
  if (!isObject(v)) return [`${at}: not an object`];

  const who = nonEmpty(v.nodeId) ? `${at} (\`${v.nodeId}\`)` : at;
  const p: string[] = [];

  if (!nonEmpty(v.nodeId)) p.push(`${at}: \`nodeId\` must be a non-empty string`);

  if (!CLASSES.includes(v.class as GroundingClass)) {
    p.push(
      `${who}: \`class\` is ${JSON.stringify(v.class)} — must be one of ${CLASSES.join(', ')}`,
    );
  }

  if (!DECIDED_BY.includes(v.decidedBy as Verdict['decidedBy'])) {
    p.push(
      `${who}: \`decidedBy\` is ${JSON.stringify(v.decidedBy)} — must be 'probe' or 'agent'; it is the provenance of the decision, and the economics are counted from it`,
    );
  }

  const wb = v.writeBoundary;
  if (!isObject(wb)) {
    p.push(
      `${who}: \`writeBoundary\` is missing — a class without {producer, actorCanWrite, argument} is an unaccountable green check`,
    );
  } else {
    // The one this exists for. A class with no causal path cannot be reviewed,
    // cannot be audited, and cannot be told apart from a guess.
    if (!nonEmpty(wb.argument)) {
      p.push(
        `${who}: \`writeBoundary.argument\` is empty — name the causal path from the actor to the signal, not the class`,
      );
    }
    if (!(typeof wb.actorCanWrite === 'boolean' || wb.actorCanWrite === null)) {
      p.push(
        `${who}: \`writeBoundary.actorCanWrite\` must be true, false or null (null = could not establish the fork point)`,
      );
    }
    if (!nonEmpty(wb.producer)) {
      p.push(
        `${who}: \`writeBoundary.producer\` is empty — name what actually emits the signal`,
      );
    }
  }

  if (!Array.isArray(v.evidence) || v.evidence.some((e) => typeof e !== 'string')) {
    p.push(
      `${who}: \`evidence\` must be a string[] of citations (file:line, config key, command). Pass [] only if you genuinely cited nothing`,
    );
  }

  // route.ts ranks by confidence and render.ts rings anchored verdicts asserted
  // below 0.5. Both defend themselves by defaulting a missing number to 0 —
  // which silently turns an unstated confidence into the lowest possible one.
  // Refusing here is the only place that difference is still visible.
  if (typeof v.confidence !== 'number' || !Number.isFinite(v.confidence)) {
    p.push(`${who}: \`confidence\` must be a number in 0..1`);
  } else if (v.confidence < 0 || v.confidence > 1) {
    p.push(`${who}: \`confidence\` is ${v.confidence} — must be in 0..1`);
  }

  return p;
}

/**
 * Contradictions between a verdict's own two statements: the schema maps
 * actorCanWrite true→self_referential, false→anchored, null→unknown.
 *
 * A WARNING, not a refusal, and the asymmetry is deliberate. `not_a_check` says
 * the node asserts nothing, so its write boundary is a fact about a
 * non-assertion and any value is defensible. For the other three the pair is a
 * self-contradiction worth surfacing — but refusing would let a wording
 * disagreement discard a night of judgments, and the reviewer, not the
 * assembler, is who should read the argument and decide which half is wrong.
 */
function contradictionWarnings(verdicts: Verdict[]): string[] {
  const expected: Record<string, boolean | null> = {
    anchored: false,
    self_referential: true,
    unknown: null,
  };
  const out: string[] = [];
  for (const v of verdicts) {
    if (!(v.class in expected)) continue;
    const want = expected[v.class];
    if (v.writeBoundary.actorCanWrite !== want) {
      out.push(
        `\`${v.nodeId}\` is ${v.class} but writeBoundary.actorCanWrite is ${JSON.stringify(v.writeBoundary.actorCanWrite)} (${v.class} implies ${JSON.stringify(want)}) — one of the two is wrong; the ratio was computed from the class`,
      );
    }
  }
  return out;
}

// ---------------------------------------------------------------------------
// Assembly
// ---------------------------------------------------------------------------

export interface AssembleInput {
  nodes: Node[];
  /** Every verdict source, already tagged with the file it came from. */
  sourced: SourcedVerdict[];
  target: string;
  revision: string;
  /**
   * The FULL gathered node list (`--gathered`), or `nodes` itself when the run
   * judged everything it gathered. The LIST, not a count: "the sample is a
   * subset of the gather" is a statement about ids, and comparing cardinalities
   * accepts a sample of the same size drawn from a different world.
   */
  gathered: Node[];
  warnings: string[];
  /** Distinct loadable probes — from `--probes` / `--probe-library-size`. */
  probeLibrarySize: number;
  /** Overridable so a test can assert on a fixed artifact. */
  generatedAt?: string;
}

export function assemble(
  input: AssembleInput,
): { report: AssembledReport; warnings: string[] } | { problems: string[] } {
  const problems: string[] = [];

  for (const sv of input.sourced) problems.push(...verdictProblems(sv));
  // Everything below dereferences nodeId/class, so structural problems are
  // fatal before identity problems are even looked at. Reporting "orphan
  // verdict `undefined`" on top of "nodeId must be a string" is noise.
  if (problems.length > 0) return { problems };

  // Zero nodes is "nothing gathered", and "nothing gathered" is a state, not a
  // ratio of 0 — see the header. Checked before identity, because every message
  // below would otherwise describe an empty world at length.
  if (input.nodes.length === 0) {
    return {
      problems: [
        input.gathered.length > 0
          ? `the judged node file is empty while --gathered lists ${input.gathered.length} node(s) — that is "nothing judged", and a report over it would publish ratio 0 as if nothing were anchored. Judge a sample (\`unknown\` is a legitimate verdict) or record the target as unjudged.`
          : 'the node file is empty — a target with zero gathered nodes gets an explicit "nothing gathered" state, never a ratio (SKILL.md § Output; corpus.ts records that state by writing no report). Refusing rather than publishing ratio 0 over nothing.',
      ],
    };
  }

  const byId = new Map<string, Node>(input.nodes.map((n) => [n.id, n]));

  const seen = new Map<string, SourcedVerdict>();
  const orphans: string[] = [];
  for (const sv of input.sourced) {
    const id = sv.verdict.nodeId;
    if (!byId.has(id)) {
      orphans.push(`${quoted(id)} (${sv.from}[${sv.index}])`);
      continue;
    }
    const first = seen.get(id);
    if (first) {
      problems.push(
        `\`${id}\` has two verdicts — ${first.from}[${first.index}] says ${first.verdict.class}, ${sv.from}[${sv.index}] says ${sv.verdict.class}. Keeping either would be an arbitrary choice between two classifications; delete one.`,
      );
      continue;
    }
    seen.set(id, sv);
  }
  if (orphans.length > 0) {
    problems.push(
      `verdict(s) for node id(s) that are not in the node file: ${nameSome(orphans)} — either the two files are from different runs, or an id is misspelled (in which case its real node is unjudged too)`,
    );
  }

  const unjudged = input.nodes.filter((n) => !seen.has(n.id)).map((n) => n.id);
  if (unjudged.length > 0) {
    problems.push(
      `${unjudged.length} node(s) have no verdict: ${nameSome(unjudged.map(quoted))} — a report computed over a subset publishes a ratio over fewer edges than it lists, and says nothing about it. Judge them (\`unknown\` is a legitimate verdict with an argument), or pass the judged sample as <nodes.json> with \`--gathered <full-nodes.json>\` so the cap is visible.`,
    );
  }

  // Subset by ID, not by count. Same-size-but-different-ids is the failure this
  // is for: a sample drawn from another run passes any cardinality test, and the
  // report then names one gather while describing another.
  const gatheredIds = new Set(input.gathered.map((n) => n.id));
  const notGathered = input.nodes.filter((n) => !gatheredIds.has(n.id)).map((n) => n.id);
  if (notGathered.length > 0) {
    problems.push(
      `${notGathered.length} judged node id(s) are absent from --gathered (${input.gathered.length} node(s) there, ${input.nodes.length} judged): ${nameSome(notGathered.map(quoted))} — the sample is not a subset of the gather it claims to come from; the two files are from different runs, or the ids were rewritten between them`,
    );
  }

  if (problems.length > 0) return { problems };

  // Node order, not file order. Reports get committed (reports/keel-current.json)
  // and diffed; the same inputs must produce the same bytes no matter which
  // order the probe file and the agent batches were passed in.
  const verdicts = input.nodes.map((n) => (seen.get(n.id) as SourcedVerdict).verdict);

  const decidedByProbe = verdicts.filter((v) => v.decidedBy === 'probe').length;
  const economics: RunEconomics = {
    nodesTotal: input.gathered.length,
    nodesSampled: input.nodes.length,
    decidedByProbe,
    decidedByAgent: verdicts.length - decidedByProbe,
    // `probesMinted` is a delta across a run this process did not watch, and the
    // token counts and wall clock were measured by nobody here. Zero is the
    // honest floor for those: an invented number would be exactly the artifact
    // Keel exists to detect. `probeLibrarySize` is NOT one of them — it is a
    // readdir, so it comes from --probes / --probe-library-size and defaults to
    // zero only when the caller genuinely said nothing about a probe library.
    probesMinted: 0,
    probeLibrarySize: input.probeLibrarySize,
    tokensIn: 0,
    tokensOut: 0,
    tokensEstimated: true,
    wallClockMs: 0,
  };

  const warnings = [...input.warnings, ...contradictionWarnings(verdicts)];

  const report: AssembledReport = {
    target: input.target,
    revision: input.revision,
    generatedAt: input.generatedAt ?? new Date().toISOString(),
    nodes: input.nodes,
    verdicts,
    // Computed. Never read from an input: a ratio a caller can hand us is a
    // number the thing being measured can write to.
    grounding: groundingRatio(verdicts),
    economics,
  };
  if (warnings.length > 0) report.warnings = warnings;

  return { report, warnings };
}

// ---------------------------------------------------------------------------
// Revision
// ---------------------------------------------------------------------------

interface GitRevision {
  sha: string;
  dirty: boolean;
}

/**
 * The sha of whatever `--dir` is checked out at, or null if it is not a git
 * checkout. `dirty` matters: a sha names a tree, and if the working tree has
 * uncommitted changes then the sha does not describe what was measured. That is
 * surfaced as a warning rather than smuggled into the string, because
 * downstream (the drift gate in test.yml) slices the first 7 characters and
 * expects a sha there.
 */
function gitRevision(dir: string): GitRevision | null {
  const head = Bun.spawnSync(['git', '-C', dir, 'rev-parse', 'HEAD'], {
    stdout: 'pipe',
    stderr: 'pipe',
  });
  if (head.exitCode !== 0) return null;
  const sha = head.stdout.toString().trim();
  if (!/^[0-9a-f]{7,40}$/.test(sha)) return null;
  const status = Bun.spawnSync(['git', '-C', dir, 'status', '--porcelain'], {
    stdout: 'pipe',
    stderr: 'pipe',
  });
  return { sha, dirty: status.exitCode === 0 && status.stdout.toString().trim() !== '' };
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

const USAGE = `usage: bun scripts/assemble.ts <nodes.json> <verdicts.json>... [options] -o <report.json>

  <nodes.json>      the Node[] that was judged (gather --json)
  <verdicts.json>   a Verdict[], or a ClassifyOutput whose \`decided\` is taken.
                    REPEATABLE — pass the probe-decided file and each agent
                    batch; assemble merges them and refuses duplicates.

  -o, --out <path>  write the Report here (default: stdout)
  --target <name>   what was measured (default: basename of --dir, else "target")
  --dir <path>      the measured directory; --revision is read from it when it
                    is a git checkout
  --revision <sha>  commit sha of what was measured
  --gathered <file> the FULL gather output, when <nodes.json> is a judged sample.
                    Sets economics.nodesTotal so the cap is visible beside the
                    ratio instead of silently shrinking the denominator. The
                    judged nodes must be a SUBSET of it, by id.
  --probes <dir>    a probe directory the run loaded. REPEATABLE. Sets
                    economics.probeLibrarySize to the number of DISTINCT probe
                    ids across the dirs (\`<id>.v<n>.ts\` counts once), the same
                    way corpus.ts counts it.
  --probe-library-size <n>
                    the count directly, when the run knows it and the dirs are
                    not reachable from here. Mutually exclusive with --probes.
  --warnings <file> a ClassifyOutput (or a string[]) whose warnings travel into
                    the report. A ClassifyOutput passed as a positional
                    <verdicts.json> already carries its own warnings.
  --json            machine-readable summary on stdout (requires -o)

assemble MERGES and VALIDATES. It classifies nothing: every class in the output
was authored upstream by a probe or by the agent. The grounding block is always
recomputed from the verdicts, never taken from an input.`;

interface Args {
  nodesPath: string;
  verdictPaths: string[];
  out: string;
  target: string;
  dir: string;
  revision: string;
  gatheredPath: string;
  warningsPath: string;
  probeDirs: string[];
  /** -1 = not stated. Distinguishes "the caller said zero" from "unstated". */
  probeLibrarySize: number;
  json: boolean;
}

function parseArgs(argv: string[]): Args | { error: string } {
  const a: Args = {
    nodesPath: '',
    verdictPaths: [],
    out: '',
    target: '',
    dir: '',
    revision: '',
    gatheredPath: '',
    warningsPath: '',
    probeDirs: [],
    probeLibrarySize: -1,
    json: false,
  };

  // A flag whose value is missing, empty or another flag is an error, not a
  // default — `--revision "$SHA"` with an unset $SHA must not quietly produce a
  // report that claims to describe nothing in particular.
  const need = (i: number, flag: string): string | { error: string } => {
    const v = argv[i + 1];
    if (v === undefined || v === '' || v.startsWith('-')) {
      return { error: `${flag} requires a value` };
    }
    return v;
  };

  const VALUED = [
    '-o',
    '--out',
    '--target',
    '--dir',
    '--revision',
    '--gathered',
    '--warnings',
    '--probes',
    '--probe-library-size',
  ];

  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i] as string;
    if (arg === '--json') {
      a.json = true;
    } else if (VALUED.includes(arg)) {
      const v = need(i, arg);
      if (typeof v !== 'string') return v;
      i++;
      if (arg === '-o' || arg === '--out') a.out = v;
      else if (arg === '--target') a.target = v;
      else if (arg === '--dir') a.dir = v;
      else if (arg === '--revision') a.revision = v;
      else if (arg === '--gathered') a.gatheredPath = v;
      else if (arg === '--warnings') a.warningsPath = v;
      else if (arg === '--probes') a.probeDirs.push(v);
      else {
        // A non-integer here would land in the artifact as a probe library that
        // never existed, so it is refused rather than coerced.
        if (!/^\d+$/.test(v)) {
          return {
            error: `--probe-library-size ${v} — must be a non-negative integer (the count of distinct probes the run could load)`,
          };
        }
        a.probeLibrarySize = Number(v);
      }
    } else if (arg.startsWith('-')) {
      return { error: `unknown flag ${arg}` };
    } else if (a.nodesPath === '') {
      a.nodesPath = arg;
    } else {
      a.verdictPaths.push(arg);
    }
  }

  if (a.nodesPath === '') return { error: 'missing <nodes.json>' };
  if (a.verdictPaths.length === 0) return { error: 'missing <verdicts.json>' };
  // Two JSON documents on one stream is a parse error waiting to happen at the
  // far end of a pipe, so the tool refuses to create one rather than choosing a
  // stream on the caller's behalf.
  if (a.json && a.out === '') {
    return {
      error:
        '--json without -o would put two JSON documents on stdout — pass -o <report.json>, or drop --json and read the report itself',
    };
  }
  // Two answers to one question. Whichever we preferred, the other would be
  // silently ignored in a report that states the number as fact.
  if (a.probeDirs.length > 0 && a.probeLibrarySize >= 0) {
    return {
      error:
        '--probes and --probe-library-size both given — they answer the same question and could disagree; pass the directories, or pass the count',
    };
  }
  return a;
}

function main(argv: string[]): number {
  const args = argv.slice(2);
  if (args.length === 0 || args.includes('-h') || args.includes('--help')) {
    console.log(USAGE);
    return args.length === 0 ? 1 : 0;
  }

  const parsed = parseArgs(args);
  if ('error' in parsed) {
    console.error(`assemble: ${parsed.error}\n\n${USAGE}`);
    return 1;
  }
  const opts = parsed;

  const nodes = loadNodes(opts.nodesPath);
  if (isError(nodes)) {
    console.error(`assemble: ${nodes.error}`);
    return 1;
  }

  const sourced: SourcedVerdict[] = [];
  let warnings: string[] = [];
  for (const p of opts.verdictPaths) {
    const loaded = loadVerdicts(p);
    if (isError(loaded)) {
      console.error(`assemble: ${loaded.error}`);
      return 1;
    }
    sourced.push(...loaded.sourced);
    warnings.push(...loaded.warnings);
  }

  if (opts.warningsPath) {
    const loaded = loadWarnings(opts.warningsPath);
    if (isError(loaded)) {
      console.error(`assemble: ${loaded.error}`);
      return 1;
    }
    warnings.push(...loaded);
  }
  // The same ClassifyOutput is often both a verdicts file and `--warnings`.
  warnings = uniq(warnings);

  let gathered = nodes;
  if (opts.gatheredPath) {
    const loaded = loadNodes(opts.gatheredPath);
    if (isError(loaded)) {
      console.error(`assemble: --gathered: ${loaded.error}`);
      return 1;
    }
    gathered = loaded;
  }

  // Zero only when nothing was said about a probe library — never as a stand-in
  // for a directory nobody looked in.
  let probeLibrary = opts.probeLibrarySize >= 0 ? opts.probeLibrarySize : 0;
  if (opts.probeDirs.length > 0) {
    const counted = probeLibrarySize(opts.probeDirs);
    if (typeof counted !== 'number') {
      console.error(`assemble: ${counted.error}`);
      return 1;
    }
    probeLibrary = counted;
  }

  // Revision, in order: what the caller said, then what the checkout says.
  let revision = opts.revision;
  if (opts.dir && !existsSync(opts.dir)) {
    console.error(`assemble: --dir ${opts.dir}: no such directory`);
    return 1;
  }
  if (opts.dir && !statSync(opts.dir).isDirectory()) {
    console.error(`assemble: --dir ${opts.dir}: not a directory`);
    return 1;
  }
  if (!revision && opts.dir) {
    const git = gitRevision(opts.dir);
    if (git) {
      revision = git.sha;
      if (git.dirty) {
        warnings.push(
          `the working tree at ${opts.dir} has uncommitted changes — ${git.sha.slice(0, 7)} does not fully describe what was measured`,
        );
      }
    }
  }
  if (!revision) {
    // Not fatal: a target need not be a git checkout. But a report that cannot
    // say what it measured cannot be re-measured or compared, so it says so
    // out loud in both the artifact and the terminal.
    revision = 'unknown';
    warnings.push(
      'no --revision, and no git checkout to read one from — the report records revision "unknown" and cannot be compared against a later run',
    );
  }

  const target =
    opts.target || (opts.dir ? basename(resolve(opts.dir)) : '') || 'target';

  const result = assemble({
    nodes,
    sourced,
    target,
    revision,
    gathered,
    warnings,
    probeLibrarySize: probeLibrary,
  });

  if ('problems' in result) {
    console.error(
      `assemble: refusing to write a report — ${result.problems.length} problem(s):`,
    );
    for (const p of result.problems.slice(0, MAX_PROBLEMS)) console.error(`  ✗ ${p}`);
    if (result.problems.length > MAX_PROBLEMS) {
      console.error(`  …and ${result.problems.length - MAX_PROBLEMS} more`);
    }
    return 1;
  }

  const { report } = result;
  const json = `${JSON.stringify(report, null, 2)}\n`;

  if (opts.out) {
    // `-o build/` is the natural typo and the raw failure is an EISDIR stack
    // trace from deep inside writeFileSync — which reads like a crash in the
    // tool rather than a fixable mistake in the command.
    const abs = resolve(opts.out);
    if (existsSync(abs) && statSync(abs).isDirectory()) {
      console.error(
        `assemble: -o ${opts.out}: is a directory — pass the report FILE to write, e.g. ${join(opts.out, 'report.json')}`,
      );
      return 1;
    }
    try {
      mkdirSync(dirname(abs), { recursive: true });
      writeFileSync(abs, json);
    } catch (e) {
      console.error(`assemble: cannot write ${opts.out}: ${errText(e)}`);
      return 1;
    }
  } else {
    process.stdout.write(json);
  }

  const g = report.grounding;
  const denom = g.anchored + g.selfReferential + g.unknown;
  const e = report.economics;

  if (opts.json) {
    console.log(
      JSON.stringify(
        {
          out: opts.out,
          target: report.target,
          revision: report.revision,
          generatedAt: report.generatedAt,
          nodes: report.nodes.length,
          verdicts: report.verdicts.length,
          grounding: g,
          economics: e,
          warnings: report.warnings ?? [],
        },
        null,
        2,
      ),
    );
  } else {
    // stderr, so `assemble … > report.json` still produces a clean file.
    console.error(
      `${opts.out ? `wrote ${opts.out}` : 'assembled'} — ${report.nodes.length} node(s), ` +
        (denom === 0
          ? 'no denominator'
          : `ratio ${g.ratio.toFixed(2)} (${g.anchored}/${denom} anchored)`) +
        `, ${g.notACheck} not_a_check excluded`,
    );
    console.error(
      `  ${report.verdicts.length} verdict(s): ${e.decidedByProbe} by probe, ${e.decidedByAgent} by agent · ` +
        `${e.nodesSampled}/${e.nodesTotal} judged/gathered · ${report.target} @ ${report.revision.slice(0, 7)}`,
    );
    for (const w of report.warnings ?? []) console.error(`  ! ${w}`);
  }

  return 0;
}

if (import.meta.main) process.exit(main(process.argv));
