#!/usr/bin/env bun
/**
 * keel mint-probe — crystallize one agent judgment into a reviewable probe.
 *
 *   bun scripts/mint-probe.ts --node <node.json> --verdict <verdict.json> \
 *       (--against <nodes.json> | --negative <nodes.json>) \
 *       [--max-match-rate <0..1>] [--out <dir>] [--id <id>] [--dry-run] [--json]
 *
 * THIS SCRIPT DOES NOT DECIDE ANYTHING. It is plumbing: it takes the node, the
 * agent's verdict, and the agent's own statement of WHICH STRUCTURAL SHAPE the
 * verdict generalizes to, and it renders, validates, versions and installs a
 * probe file. It never infers a class, and it never derives a match rule from
 * the node's text — a script that guessed the generalization would be exactly
 * the ungrounded lookup table Keel exists to detect.
 *
 * What it DOES enforce, because these are mechanical properties:
 *   - a probe may never assert `unknown` (abstention is the only "cannot tell")
 *   - `match` keys on structure, not on a repo name or a path literal, and the
 *     rendered `signature()` never reads `node.source` at all — a path says where
 *     a check lives, not what produces its signal, and it is attacker-adjacent
 *   - the minted file loads and satisfies the interface BEFORE it is installed
 *     (`validateByExecution`, which runs the candidate in the sandbox child)
 *   - an existing probe id is never overwritten — the next version is minted
 *
 * BREADTH — "one probe, one shape", stated as a measurement rather than a claim.
 *
 * An earlier version of this file executed the candidate against five canary
 * nodes and printed "and is not universal" on every successful mint. That claim
 * was unearned: the guard only failed a match that hit ALL FOUR unrelated
 * canaries, and those four share no 3-character substring, so it could not fire
 * for any spec that passes validation. `{"allOf":["run"],"kinds":["ci_step"]}`
 * was minted, certified, and then asserted `anchored` at 0.95 on `- run: exit 0`
 * and on an LLM review gate. Dead code plus a confident success message is how a
 * tool blesses a rule table, which is the one thing this project cannot ship.
 *
 * Breadth is now measured against a corpus the CALLER supplies, and supplying
 * one is REQUIRED — five canaries cannot bound how much of a real repo a match
 * rule swallows:
 *
 *   --against <nodes.json>   the gathered node set. The candidate must match at
 *                            most --max-match-rate of it (default 0.25),
 *                            excluding the node it was minted from. The rate is
 *                            REPORTED either way; the ceiling is enforced only
 *                            at >= 8 nodes, and below that the output says in
 *                            words that nothing was bounded.
 *   --negative <nodes.json>  nodes the caller asserts this probe must NOT
 *                            match. Any hit is a hard failure, with ids named.
 *
 * The canaries still run and are still a floor: a match that fires on the blank
 * node, or on MORE THAN ONE unrelated canary shape, is rejected. Their hit count
 * is printed, not summarized into an adjective.
 *
 * `--verdict` is the agent's Verdict for the node, plus the generalization:
 *
 *   {
 *     "class": "anchored",
 *     "writeBoundary": { "producer": "...", "actorCanWrite": false, "argument": "..." },
 *     "evidence": ["..."],
 *     "confidence": 0.9,
 *     "probe": {
 *       "id": "kebab-case-id",
 *       "description": "the shape, in plain language",
 *       "match": {                            // the cheap STRUCTURAL filter
 *         "kinds":  ["ci_step", "script"],    // optional NodeKind filter
 *         "allOf":  ["tsc"],                  // every token must appear
 *         "anyOf":  ["--noemit", "--project"],// at least one must appear
 *         "noneOf": ["|| true"]               // none may appear
 *       },
 *       "assert": {                           // OPTIONAL confirming stage
 *         "allOf":  ["tsc"],                  // checked against node.raw ONLY
 *         "anyOf":  [],
 *         "noneOf": ["continue-on-error"]
 *       }
 *     }
 *   }
 *
 * (Tokens are trimmed, so a flag is written `"--project"`, not `"-p "` — the
 * trailing space would be stripped and `-p` is below the 3-char floor.)
 *
 * `match` and `assert` are two stages ON PURPOSE. The dispatcher only calls
 * `assess` after `match` returned true, so an `assess` that re-runs the identical
 * predicate has an unreachable `return null` and asserts on 100% of what it
 * matches — which is what the earlier renderer emitted, making the project's
 * "probes abstain, never assert ignorance" invariant structurally inoperative
 * for every probe this tool produced. `assert` is strictly narrower (it reads
 * `node.raw` alone, never the kind or the name), so a matched node can still be
 * handed back to the agent. Omitting `assert` is allowed, and the generated file
 * then SAYS SO in as many words: this probe asserts on every node it matches.
 */

import {
  copyFileSync,
  existsSync,
  mkdirSync,
  mkdtempSync,
  readdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from 'node:fs';
import { homedir, tmpdir } from 'node:os';
import { basename, join, resolve } from 'node:path';
import type { GroundingClass, Node, WriteBoundaryArgument } from '../schemas/keel.ts';
import { sandboxCommand, sanitizedEnv } from './probe-sandbox.ts';

const ASSERTABLE: ReadonlySet<string> = new Set<GroundingClass>([
  'anchored',
  'self_referential',
  'not_a_check',
]);

interface MatchSpec {
  kinds: string[];
  allOf: string[];
  anyOf: string[];
  noneOf: string[];
}

/**
 * The optional CONFIRMING stage, evaluated against `node.raw` alone. It is what
 * makes abstention reachable: `match` is the cheap structural filter the
 * dispatcher uses to decide whether to call `assess` at all, and `assert` is the
 * narrower check `assess` can fail. `null` means the agent supplied none.
 */
type AssertSpec = { allOf: string[]; anyOf: string[]; noneOf: string[] } | null;

/** Breadth measurement inputs. Both optional individually, at least one required. */
interface Corpora {
  /** the gathered node set: a match-RATE ceiling applies */
  against: Node[] | null;
  againstPath?: string;
  /** nodes the caller asserts must not match: ANY hit fails */
  negative: Node[] | null;
  negativePath?: string;
  maxMatchRate: number;
}

/** Below this many nodes a rate bounds nothing, and we say so instead of pretending. */
const MIN_CORPUS_FOR_CEILING = 8;
const DEFAULT_MAX_MATCH_RATE = 0.25;

interface MintSpec {
  id: string;
  description: string;
  version: number;
  mintedFrom: string;
  mintedAt: string;
  class: Exclude<GroundingClass, 'unknown'>;
  writeBoundary: WriteBoundaryArgument;
  evidence: string[];
  confidence: number;
  match: MatchSpec;
  assert: AssertSpec;
}

/**
 * Canary nodes. These are NOT classification rules — nothing here says what
 * anything means. They exist to execute a candidate `match` against shapes it
 * has no business recognizing, so a probe that matches everything is caught by
 * observation rather than by inspection. The blank node is the sharpest one: a
 * `match` that fires on an empty node is a rule table in costume.
 */
const CANARIES: Node[] = [
  { id: 'canary#blank', kind: 'other', name: '', source: '', raw: '' },
  { id: 'canary#dev-server', kind: 'script', name: 'dev', source: 'package.json', raw: '"dev": "vite"' },
  {
    id: 'canary#doc-claim',
    kind: 'doc_claim',
    name: 'verified before merge',
    source: 'README.md',
    raw: 'Every change is verified before it is merged.',
  },
  {
    id: 'canary#review-gate',
    kind: 'review_gate',
    name: 'CODEOWNERS',
    source: '.github/CODEOWNERS',
    raw: '* @some-team',
  },
  {
    id: 'canary#noop-step',
    kind: 'ci_step',
    name: 'noop',
    source: '.github/workflows/x.yml',
    raw: '- run: echo ok',
  },
];

class MintError extends Error {}

function fail(m: string): never {
  throw new MintError(m);
}

function msg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

function readJson(path: string): Record<string, unknown> {
  if (!existsSync(path)) fail(`no such file: ${path}`);
  try {
    const v: unknown = JSON.parse(readFileSync(path, 'utf8'));
    if (typeof v !== 'object' || v === null || Array.isArray(v)) fail(`${path} is not a JSON object`);
    return v as Record<string, unknown>;
  } catch (e) {
    if (e instanceof MintError) throw e;
    fail(`${path} is not valid JSON: ${msg(e)}`);
  }
}

// ---------------------------------------------------------------------------
// Validation of the agent's input. Mechanical checks only.
// ---------------------------------------------------------------------------

function strArray(v: unknown, where: string): string[] {
  if (v === undefined) return [];
  if (!Array.isArray(v) || v.some((x) => typeof x !== 'string')) fail(`${where} must be string[]`);
  return (v as string[]).map((s) => s.trim()).filter(Boolean);
}

function validateNode(n: Record<string, unknown>): Node {
  for (const k of ['id', 'kind', 'name', 'source', 'raw']) {
    if (typeof n[k] !== 'string') fail(`node.${k} must be a string (is the --node file a gathered Node?)`);
  }
  return n as unknown as Node;
}

/**
 * Reject a `match` keyed on the repo it was minted from. A probe that
 * recognizes one project is a hardcoded answer wearing a probe's clothes.
 */
function rejectRepoLiterals(tokens: string[], node: Node): void {
  const src = node.source.toLowerCase();
  const segments = new Set(
    src
      .split(/[/\\.]/)
      .map((s) => s.trim())
      .filter((s) => s.length >= 3),
  );
  segments.add(basename(src).toLowerCase());
  segments.add(node.id.toLowerCase());
  for (const t of tokens) {
    const lc = t.toLowerCase();
    if (lc.startsWith('/') || lc.startsWith('~/')) {
      fail(`match token ${JSON.stringify(t)} is an absolute path — match on structure, not on a location`);
    }
    if (segments.has(lc)) {
      fail(
        `match token ${JSON.stringify(t)} is a path literal from ${node.source} — match on structure, not on this repo`,
      );
    }
    if (lc.includes('/') && src.includes(lc)) {
      fail(`match token ${JSON.stringify(t)} is a path fragment of ${node.source} — match on structure, not on this repo`);
    }
  }
}

/**
 * A probe decides MANY nodes, so it cannot carry ONE node's coordinates.
 *
 * `rejectRepoLiterals` above stops a path literal getting into `match`. This is
 * the symmetric guard for `evidence`, and it was added after a minted probe
 * baked `.github/workflows/CICD.yml:64` — the line it was minted FROM — into its
 * verdict, then decided a different node at line 81. The class was right and the
 * citation pointed at the wrong place, which in a tool whose whole claim is
 * "the argument is the evidence" is worse than citing nothing: a reader who
 * follows the reference finds a command that is not there and correctly stops
 * trusting the report.
 *
 * A probe's evidence must describe the SHAPE it recognised. Node-specific
 * citations belong to the agent verdict that minted it, which is preserved in
 * `mintedFrom` and in the file header.
 */
function rejectNodeSpecificEvidence(evidence: string[], node: Node): void {
  const src = node.source.toLowerCase();
  for (const e of evidence) {
    const lc = e.toLowerCase();
    if (/^[\w./\\-]+:\d+$/.test(e.trim())) {
      fail(
        `evidence ${JSON.stringify(e)} is a file:line citation. A probe decides many nodes and would ` +
          `carry this one's coordinates onto all of them — describe the SHAPE it recognises instead ` +
          `(the originating citation is kept in mintedFrom).`,
      );
    }
    if (src && lc.includes(src)) {
      fail(
        `evidence ${JSON.stringify(e)} names ${node.source}, the node this was minted from. ` +
          `Evidence must describe the shape, not the origin.`,
      );
    }
  }
}

function buildSpec(node: Node, verdict: Record<string, unknown>, idOverride?: string): MintSpec {
  const cls = verdict.class;
  if (cls === 'unknown') {
    fail(
      "verdict.class is 'unknown': a probe may never assert unknown. `unknown` is a claim about the world and only the agent makes it — do not crystallize it.",
    );
  }
  if (typeof cls !== 'string' || !ASSERTABLE.has(cls)) {
    fail(`verdict.class must be one of ${[...ASSERTABLE].join(', ')} (got ${JSON.stringify(cls)})`);
  }

  const wb = verdict.writeBoundary as Record<string, unknown> | undefined;
  if (typeof wb !== 'object' || wb === null) fail('verdict.writeBoundary is required');
  if (typeof wb.producer !== 'string' || !wb.producer.trim()) fail('verdict.writeBoundary.producer is required');
  if (typeof wb.argument !== 'string' || wb.argument.trim().length < 24) {
    fail('verdict.writeBoundary.argument must name the causal path (>=24 chars), not restate the class');
  }
  if (!(typeof wb.actorCanWrite === 'boolean' || wb.actorCanWrite === null)) {
    fail('verdict.writeBoundary.actorCanWrite must be boolean or null');
  }

  const confidence = verdict.confidence === undefined ? 0.8 : verdict.confidence;
  if (typeof confidence !== 'number' || !(confidence >= 0 && confidence <= 1)) {
    fail('verdict.confidence must be a number in 0..1');
  }

  const p = (verdict.probe ?? {}) as Record<string, unknown>;
  const id = (idOverride ?? p.id) as unknown;
  if (typeof id !== 'string' || !/^[a-z0-9]+(-[a-z0-9]+)*$/.test(id) || id.length < 3 || id.length > 64) {
    fail('probe.id must be kebab-case, 3..64 chars (pass --id to override)');
  }
  const description = p.description;
  if (typeof description !== 'string' || description.trim().length < 12) {
    fail('probe.description must say, in plain language, what SHAPE this generalizes (>=12 chars)');
  }

  const m = (p.match ?? {}) as Record<string, unknown>;
  const match: MatchSpec = {
    kinds: strArray(m.kinds, 'probe.match.kinds'),
    allOf: strArray(m.allOf, 'probe.match.allOf').map((s) => s.toLowerCase()),
    anyOf: strArray(m.anyOf, 'probe.match.anyOf').map((s) => s.toLowerCase()),
    noneOf: strArray(m.noneOf, 'probe.match.noneOf').map((s) => s.toLowerCase()),
  };
  if (match.allOf.length + match.anyOf.length === 0) {
    fail('probe.match needs allOf and/or anyOf tokens — a kind filter alone matches everything of that kind');
  }
  const positive = [...match.allOf, ...match.anyOf];
  for (const t of positive) {
    if (t.length < 3) fail(`match token ${JSON.stringify(t)} is too short to be a shape (>=3 chars)`);
  }
  rejectRepoLiterals(positive, node);

  // The optional confirming stage. Same token discipline — it is match rules all
  // the way down, and a path literal is no more acceptable here than in `match`.
  let assertSpec: AssertSpec = null;
  const a = p.assert;
  if (a !== undefined) {
    if (typeof a !== 'object' || a === null || Array.isArray(a)) {
      fail('probe.assert must be an object with allOf / anyOf / noneOf');
    }
    const ao = a as Record<string, unknown>;
    const spec = {
      allOf: strArray(ao.allOf, 'probe.assert.allOf').map((s) => s.toLowerCase()),
      anyOf: strArray(ao.anyOf, 'probe.assert.anyOf').map((s) => s.toLowerCase()),
      noneOf: strArray(ao.noneOf, 'probe.assert.noneOf').map((s) => s.toLowerCase()),
    };
    if (spec.allOf.length + spec.anyOf.length + spec.noneOf.length === 0) {
      fail('probe.assert was supplied but is empty — omit it, or give it tokens that can actually fail');
    }
    for (const t of [...spec.allOf, ...spec.anyOf]) {
      if (t.length < 3) fail(`assert token ${JSON.stringify(t)} is too short to be a shape (>=3 chars)`);
    }
    rejectRepoLiterals([...spec.allOf, ...spec.anyOf], node);
    assertSpec = spec;
  }

  return {
    id,
    description: description.trim(),
    version: 0, // assigned at install time
    mintedFrom: node.id,
    mintedAt: new Date().toISOString(),
    class: cls as Exclude<GroundingClass, 'unknown'>,
    writeBoundary: {
      producer: wb.producer.trim(),
      actorCanWrite: wb.actorCanWrite as boolean | null,
      argument: wb.argument.trim(),
    },
    evidence: (() => {
      const ev = strArray(verdict.evidence, 'verdict.evidence');
      rejectNodeSpecificEvidence(ev, node);
      return ev;
    })(),
    confidence,
    match,
    assert: assertSpec,
  };
}

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

function block(text: string, indent = ' * '): string {
  return text
    .replace(/\*\//g, '*\\/')
    .split('\n')
    .map((l) => `${indent}${l}`)
    .join('\n');
}

function renderProbe(s: MintSpec): string {
  const j = (v: unknown) => JSON.stringify(v);

  // Two stages, or one and an honest note about it. See the header: an `assess`
  // that re-runs `match` has an unreachable abstention, and a probe that can
  // never abstain is a probe that always asserts.
  const confirmBlock = s.assert
    ? `
const ASSERT_ALL = ${j(s.assert.allOf)};
const ASSERT_ANY = ${j(s.assert.anyOf)};
const ASSERT_NONE = ${j(s.assert.noneOf)};

/**
 * The CONFIRMING stage — strictly narrower than \`signature\`, and reading
 * \`node.raw\` alone. \`match\` is a cheap structural filter; this is the check
 * that can fail, which is what makes the abstention below reachable. A node that
 * matches but does not confirm goes back to the agent.
 */
function confirms(node) {
  const raw = String(node.raw == null ? '' : node.raw).toLowerCase();
  if (!ASSERT_ALL.every((t) => raw.includes(t))) return false;
  if (ASSERT_ANY.length && !ASSERT_ANY.some((t) => raw.includes(t))) return false;
  if (ASSERT_NONE.some((t) => raw.includes(t))) return false;
  return true;
}
`
    : '';

  const assessBody = s.assert
    ? `    // Two-stage: \`match\` filtered on structure, this confirms on the literal
    // text. Abstention (\`null\`) is REACHABLE here — a node this probe matched
    // can still fail \`confirms\` and fall through to the agent. Abstention is
    // the ONLY way a probe says "I cannot tell"; it may never say 'unknown'.
    if (!signature(node)) return null;
    if (!confirms(node)) return null;`
    : `    // NO CONFIRMING STAGE was supplied when this probe was minted, so read the
    // next line for what it is: the dispatcher only calls \`assess\` after
    // \`match\` returned true, so \`signature\` is already known true here and this
    // guard fires only for a direct caller. In the dispatcher THIS PROBE ASSERTS
    // ON EVERY NODE IT MATCHES — it never abstains. If that is too strong for
    // the shape, re-mint it with a \`probe.assert\` spec (see mint-probe.ts).
    if (!signature(node)) return null;`;

  return `/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          ${s.id} (v${s.version})
 * minted from: ${s.mintedFrom}
 * minted at:   ${s.mintedAt}
 * shape:
${block(s.description)}
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      ${s.writeBoundary.producer}
 *   actorCanWrite: ${String(s.writeBoundary.actorCanWrite)}
${block(s.writeBoundary.argument, ' *   ')}
 *
 * Contract: skills/keel/schemas/keel.ts (\`Probe\`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate \`probe\` with \`: Probe\` so the compiler holds the contract.
 */

const KINDS = ${j(s.match.kinds)};
const ALL_OF = ${j(s.match.allOf)};
const ANY_OF = ${j(s.match.anyOf)};
const NONE_OF = ${j(s.match.noneOf)};

/**
 * The shape, keyed on structure. Not on a repo, not on a path.
 *
 * \`node.source\` is deliberately NOT in the haystack. A file path says where a
 * check lives, never what produces its signal, and a path is attacker-adjacent
 * input: a repo that names a workflow \`claude-review.yml\` would otherwise have
 * every step in it — \`pytest\`, \`cargo build\` — match a probe about LLM review
 * gates. \`mint-probe\`'s \`rejectRepoLiterals()\` refuses path literals as tokens;
 * excluding \`source\` from the text being searched is the other half of that.
 */
function signature(node) {
  if (KINDS.length && !KINDS.includes(node.kind)) return false;
  const hay = [node.name, node.raw].join('\\n').toLowerCase();
  if (!ALL_OF.every((t) => hay.includes(t))) return false;
  if (ANY_OF.length && !ANY_OF.some((t) => hay.includes(t))) return false;
  if (NONE_OF.some((t) => hay.includes(t))) return false;
  return true;
}
${confirmBlock}
const probe = {
  id: ${j(s.id)},
  version: ${s.version},
  mintedAt: ${j(s.mintedAt)},
  mintedFrom: ${j(s.mintedFrom)},
  description: ${j(s.description)},
  match(node) {
    return signature(node);
  },
  assess(node) {
${assessBody}
    return {
      class: ${j(s.class)},
      writeBoundary: ${j(s.writeBoundary)},
      evidence: ${j(s.evidence)},
      confidence: ${s.confidence},
    };
  },
};

export default probe;
export { probe };
`;
}

// ---------------------------------------------------------------------------
// Validation by EXECUTION — inside the sandbox, because it is probe code.
// ---------------------------------------------------------------------------

const VALIDATOR = `// keel mint-probe validator. Runs INSIDE the sandbox: it executes freshly
// minted probe code, and freshly minted probe code is executed nowhere else.
//
// It MEASURES and reports; it never summarizes a measurement into an adjective.
// Every number it produces is printed by the CLI verbatim, so a reader can see
// what was actually bounded and what was not.
const [probePath, inputPath] = process.argv.slice(2);
const {
  node, canaries, expectClass, against, negative, maxMatchRate, minCorpus,
} = JSON.parse(require('node:fs').readFileSync(inputPath, 'utf8'));
const errors = [];
const stats = {
  canaryHits: null, canaryTotal: canaries.length - 1,
  againstSize: 0, againstHits: 0, againstRate: null, againstEnforced: false,
  negativeSize: 0, negativeHits: 0, negativeHitIds: [],
};
try {
  const mod = await import(probePath);
  const p = mod.default ?? mod.probe;
  if (!p || typeof p !== 'object') errors.push('no default export object');
  else {
    for (const k of ['id', 'mintedAt', 'mintedFrom', 'description'])
      if (typeof p[k] !== 'string') errors.push('missing ' + k);
    if (typeof p.version !== 'number') errors.push('missing version');
    if (typeof p.match !== 'function') errors.push('match is not a function');
    if (typeof p.assess !== 'function') errors.push('assess is not a function');
    if (!errors.length) {
      const hit = (c) => { try { return p.match(c) === true; } catch { return false; } };

      if (p.match(node) !== true) errors.push('match() does not match the node it was minted from');

      // --- floor: the canaries. canaries[0] is blank; the rest are unrelated.
      if (hit(canaries[0])) errors.push('match() fires on a blank node — it matches everything');
      const unrelated = canaries.slice(1);
      stats.canaryHits = unrelated.filter(hit).length;
      // >1, not "all". Requiring ALL FOUR was unreachable: the four unrelated
      // canaries share no 3-char substring, and every positive token must be
      // >=3 chars, so the old guard could never fire on a valid spec.
      if (stats.canaryHits > 1) {
        errors.push(
          'match() fires on ' + stats.canaryHits + ' of ' + unrelated.length +
          ' unrelated canary shapes — one probe, one shape',
        );
      }

      // --- measurement: the caller's corpus.
      if (Array.isArray(negative)) {
        stats.negativeSize = negative.length;
        for (const n of negative) {
          if (hit(n)) { stats.negativeHits++; if (stats.negativeHitIds.length < 5) stats.negativeHitIds.push(String(n && n.id)); }
        }
        if (stats.negativeHits > 0) {
          errors.push(
            'match() fires on ' + stats.negativeHits + ' of ' + stats.negativeSize +
            ' nodes the caller said it must NOT match: ' + stats.negativeHitIds.join(', '),
          );
        }
      }
      if (Array.isArray(against)) {
        const others = against.filter((n) => n && n.id !== node.id);
        stats.againstSize = others.length;
        stats.againstHits = others.filter(hit).length;
        stats.againstRate = others.length ? stats.againstHits / others.length : null;
        stats.againstEnforced = others.length >= minCorpus;
        if (stats.againstEnforced && stats.againstRate > maxMatchRate) {
          errors.push(
            'match() fires on ' + stats.againstHits + ' of ' + stats.againstSize + ' corpus nodes (' +
            (stats.againstRate * 100).toFixed(1) + '%), above the ' + (maxMatchRate * 100).toFixed(1) +
            '% ceiling — this is a rule table, not a shape (raise it with --max-match-rate if you mean it)',
          );
        }
      }

      // --- the verdict side.
      const v = p.assess(node);
      if (v === null || v === undefined) errors.push('assess() abstains on the node it was minted from');
      else if (v.class === 'unknown') errors.push("assess() returns 'unknown'; probes may only abstain");
      else if (v.class !== expectClass) errors.push('assess() returns ' + v.class + ', expected ' + expectClass);
      else if (p.assess(canaries[0]) !== null) errors.push('assess() does not abstain on a blank node');
    }
  }
} catch (e) {
  errors.push('failed to load: ' + (e && e.message ? e.message : String(e)));
}
console.log(JSON.stringify({ ok: errors.length === 0, errors, stats }));
`;

/** What the validator measured. Printed verbatim; never compressed to a claim. */
interface BreadthStats {
  canaryHits: number | null;
  canaryTotal: number;
  againstSize: number;
  againstHits: number;
  againstRate: number | null;
  againstEnforced: boolean;
  negativeSize: number;
  negativeHits: number;
  negativeHitIds: string[];
}

async function validateByExecution(
  probePath: string,
  node: Node,
  expectClass: string,
  corpora: Corpora,
): Promise<BreadthStats> {
  const dir = mkdtempSync(join(tmpdir(), 'keel-mint-check-'));
  try {
    const vPath = join(dir, 'validate.ts');
    const iPath = join(dir, 'input.json');
    writeFileSync(vPath, VALIDATOR, 'utf8');
    writeFileSync(
      iPath,
      JSON.stringify({
        node,
        canaries: CANARIES,
        expectClass,
        against: corpora.against,
        negative: corpora.negative,
        maxMatchRate: corpora.maxMatchRate,
        minCorpus: MIN_CORPUS_FOR_CEILING,
      }),
      'utf8',
    );

    const { cmd, sandboxed, reason } = sandboxCommand([vPath, probePath, iPath]);
    if (!sandboxed) {
      console.error(`keel: validating minted probe WITHOUT sandbox confinement (${reason})`);
    }
    const proc = Bun.spawn(cmd, { env: sanitizedEnv({ KEEL_SANDBOXED: '1' }), stdout: 'pipe', stderr: 'pipe' });
    const [out, err, code] = await Promise.all([
      new Response(proc.stdout).text(),
      new Response(proc.stderr).text(),
      proc.exited,
    ]);
    if (code !== 0) fail(`minted probe failed to run (exit ${code}): ${err.trim() || out.trim()}`);
    let parsed: { ok?: boolean; errors?: string[]; stats?: BreadthStats };
    try {
      parsed = JSON.parse(out.trim().split('\n').pop() ?? '{}');
    } catch {
      fail(`validator produced no verdict: ${out.trim()} ${err.trim()}`);
    }
    if (!parsed.ok) fail(`minted probe does not satisfy the contract:\n  - ${(parsed.errors ?? []).join('\n  - ')}`);
    if (!parsed.stats) fail('validator returned no breadth measurement — refusing to install an unmeasured probe');
    return parsed.stats;
  } finally {
    rmSync(dir, { recursive: true, force: true });
  }
}

/**
 * Read a `Node[]` (or `{ nodes: Node[] }`) corpus. Deliberately permissive about
 * node CONTENT — a corpus is something to run `match` against, not something to
 * validate — but strict about being a list, because a silently-empty corpus
 * would turn a required measurement back into the unearned claim we just removed.
 */
function readCorpus(path: string, flag: string): Node[] {
  if (!existsSync(path)) fail(`no such file: ${path} (${flag})`);
  let parsedJson: unknown;
  try {
    parsedJson = JSON.parse(readFileSync(path, 'utf8'));
  } catch (e) {
    fail(`${flag} ${path} is not valid JSON: ${msg(e)}`);
  }
  const arr = Array.isArray(parsedJson) ? parsedJson : (parsedJson as { nodes?: unknown })?.nodes;
  if (!Array.isArray(arr)) fail(`${flag} ${path} is not a Node[] (nor { nodes: Node[] })`);
  if (arr.length === 0) fail(`${flag} ${path} is empty — an empty corpus measures nothing`);
  return arr as Node[];
}

/** Human-readable rendering of what was measured, including what was NOT. */
function breadthReport(stats: BreadthStats, corpora: Corpora): string[] {
  const lines: string[] = [];
  lines.push(
    `  breadth: fires on ${stats.canaryHits}/${stats.canaryTotal} unrelated canary shapes, and not on a blank node.`,
  );
  if (corpora.negative) {
    lines.push(
      `  breadth: 0/${stats.negativeSize} hits on the --negative corpus (${corpora.negativePath}).`,
    );
  }
  if (corpora.against) {
    const pct = stats.againstRate === null ? 'n/a' : `${(stats.againstRate * 100).toFixed(1)}%`;
    lines.push(
      `  breadth: matches ${stats.againstHits}/${stats.againstSize} of --against (${corpora.againstPath}) = ${pct}` +
        (stats.againstEnforced
          ? `, at or under the ${(corpora.maxMatchRate * 100).toFixed(1)}% ceiling.`
          : `. NOT ENFORCED: ${stats.againstSize} nodes is below the ${MIN_CORPUS_FOR_CEILING}-node floor, so this rate bounds nothing.`),
    );
  }
  return lines;
}

// ---------------------------------------------------------------------------
// Versioning + install
// ---------------------------------------------------------------------------

/**
 * Probe files are `<id>.v<n>.ts`. An existing id is never overwritten: the next
 * version is minted beside it, and the loader takes the highest version per id.
 * A probe that silently replaced its predecessor would erase the only record of
 * what a human once reviewed.
 */
export function nextVersion(dir: string, id: string): number {
  if (!existsSync(dir)) return 1;
  let max = 0;
  const re = new RegExp(`^${id.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\.v(\\d+)\\.ts$`);
  for (const f of readdirSync(dir)) {
    const m = re.exec(f);
    if (m) max = Math.max(max, Number(m[1]));
  }
  return max + 1;
}

function outDir(flag?: string): string {
  return resolve(flag ?? process.env.KEEL_PROBE_DIR ?? join(homedir(), '.config', 'keel', 'probes'));
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

function parseArgs(argv: string[]): Record<string, string | boolean> {
  const out: Record<string, string | boolean> = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i] as string;
    if (!a.startsWith('--')) continue;
    const eq = a.indexOf('=');
    if (eq > 0) {
      out[a.slice(2, eq)] = a.slice(eq + 1);
    } else if (argv[i + 1] && !(argv[i + 1] as string).startsWith('--')) {
      out[a.slice(2)] = argv[++i] as string;
    } else {
      out[a.slice(2)] = true;
    }
  }
  return out;
}

async function main(): Promise<number> {
  const args = parseArgs(process.argv.slice(2));
  const nodePath = args.node;
  const verdictPath = args.verdict;
  if (typeof nodePath !== 'string' || typeof verdictPath !== 'string') {
    console.error(
      'usage: bun scripts/mint-probe.ts --node <node.json> --verdict <verdict.json>\n' +
        '         (--against <nodes.json> | --negative <nodes.json>)\n' +
        '         [--max-match-rate <0..1>] [--out <dir>] [--id <id>] [--dry-run] [--json]',
    );
    return 2;
  }

  const node = validateNode(readJson(nodePath));
  const verdict = readJson(verdictPath);
  const spec = buildSpec(node, verdict, typeof args.id === 'string' ? args.id : undefined);

  // Breadth corpus. REQUIRED, and required BEFORE anything is rendered, so the
  // failure reads as "you have not measured this" rather than as a late abort.
  const againstPath = typeof args.against === 'string' ? args.against : undefined;
  const negativePath = typeof args.negative === 'string' ? args.negative : undefined;
  if (!againstPath && !negativePath && !args['dry-run']) {
    fail(
      'no breadth corpus. Pass --against <nodes.json> (the gathered node set; the probe must match at most ' +
        `${(DEFAULT_MAX_MATCH_RATE * 100).toFixed(0)}% of it) and/or --negative <nodes.json> (nodes it must not match at all). ` +
        'Five canary nodes cannot bound how much of a real repo a match rule swallows, and an earlier version of this ' +
        'tool printed "is not universal" on the strength of exactly that — so the measurement is now mandatory.',
    );
  }
  let maxMatchRate = DEFAULT_MAX_MATCH_RATE;
  if (args['max-match-rate'] !== undefined) {
    const n = Number(args['max-match-rate']);
    if (!Number.isFinite(n) || n <= 0 || n > 1) fail('--max-match-rate must be a number in (0, 1]');
    maxMatchRate = n;
  }
  const corpora: Corpora = {
    against: againstPath ? readCorpus(againstPath, '--against') : null,
    againstPath,
    negative: negativePath ? readCorpus(negativePath, '--negative') : null,
    negativePath,
    maxMatchRate,
  };

  const dir = outDir(typeof args.out === 'string' ? args.out : undefined);
  spec.version = nextVersion(dir, spec.id);
  const target = join(dir, `${spec.id}.v${spec.version}.ts`);
  if (existsSync(target)) fail(`${target} already exists — refusing to overwrite a reviewed probe`);

  const source = renderProbe(spec);

  if (args['dry-run']) {
    process.stdout.write(source);
    // Say what this did NOT do. `--dry-run` renders and stops: the probe was
    // never executed and its breadth was never measured, so redirecting this
    // stdout into a probe dir installs an UNVALIDATED probe. Every guarantee in
    // the header is earned by `validateByExecution`, which only runs on a real
    // mint, and a message that read "would install" without saying so would be
    // the same unearned certification this tool had to have removed once.
    console.error(
      `keel: dry run — rendered only. NOT executed, NOT breadth-measured, NOT installed (${target}). ` +
        'Re-run without --dry-run, with --against/--negative, to get a checked probe.',
    );
    return 0;
  }

  // Render to a staging path, prove it loads and satisfies the interface by
  // EXECUTING it in the sandbox, and only then move it into place.
  const staging = mkdtempSync(join(tmpdir(), 'keel-mint-'));
  const stagedPath = join(staging, `${spec.id}.v${spec.version}.ts`);
  let stats: BreadthStats;
  try {
    writeFileSync(stagedPath, source, 'utf8');
    // The fourth argument is the breadth corpus the caller supplied. It is not
    // optional: the validator runs `match` against it and returns the RATE, and
    // that number is the only thing standing between this tool and certifying a
    // rule table as "one shape". Passing it here is what makes the printed
    // measurement below a measurement rather than a slogan.
    stats = await validateByExecution(stagedPath, node, spec.class, corpora);
    mkdirSync(dir, { recursive: true });
    if (existsSync(target)) fail(`${target} appeared during minting — refusing to overwrite`);
    copyFileSync(stagedPath, target);
  } finally {
    rmSync(staging, { recursive: true, force: true });
  }

  if (args.json) {
    process.stdout.write(
      `${JSON.stringify({
        path: target,
        id: spec.id,
        version: spec.version,
        mintedFrom: spec.mintedFrom,
        class: spec.class,
        abstains: spec.assert !== null,
        breadth: stats,
      })}\n`,
    );
  } else {
    console.log(`minted ${spec.id} v${spec.version}  ->  ${target}`);
    console.log(`  from ${spec.mintedFrom}  class=${spec.class}`);
    // Report what was executed and what was measured. NOT an adjective: the
    // predecessor of these lines said "and is not universal" on the strength of
    // a guard that could not fire, which is how a tool blesses a rule table.
    console.log('  checked by EXECUTING it: it loads, satisfies the interface, matches its origin');
    console.log('  node, and abstains on a blank node.');
    for (const line of breadthReport(stats, corpora)) console.log(line);
    console.log(
      spec.assert
        ? '  abstention: REACHABLE — a matched node that fails the `assert` stage goes to the agent.'
        : '  abstention: NONE — no `probe.assert` was supplied, so this probe asserts on every node\n    it matches. Re-mint with `probe.assert` if the shape needs a confirming stage.',
    );
  }
  return 0;
}

if (import.meta.main) {
  try {
    process.exit(await main());
  } catch (e) {
    if (e instanceof MintError) {
      console.error(`keel mint-probe: ${e.message}`);
      process.exit(1);
    }
    throw e;
  }
}
