/**
 * `keel route` — from verdicts to proposals.
 *
 *   Independence cannot be manufactured, but it can be routed.
 *
 * A `Report` says which verification edges are ungrounded and why. That is a
 * number nobody can act on. This mode turns it into: *"four of your ungrounded
 * checks can read a signal you already own, here is the exact change for each,
 * and here are the ones that cannot — those need a decision, not a rewiring."*
 *
 * ---------------------------------------------------------------------------
 * WHAT THIS FILE IS AND IS NOT
 * ---------------------------------------------------------------------------
 * It is PLUMBING. It indexes the `anchored` nodes in one report, assembles the
 * candidate pairs, validates what comes back, projects a hypothetical ratio,
 * and renders a page. It contains no mapping from check-shape to fix, and no
 * mapping from node text to a class. Both would be the ungrounded artifact Keel
 * exists to detect, and either one would make the tool a rule table wearing our
 * logo. `--dispatch` emits the judgment payload; the ARGUMENT is the agent's.
 *
 * Four properties are held mechanically, not by good intentions:
 *
 *  1. `anchoredOn` is RESOLVED, never trusted. It must name a node id that is
 *     present in the source report and whose verdict class is `anchored`.
 *     Anything else is rewritten to `null` with a `noRouteReason` that names
 *     the rejection. A hallucinated anchor cannot be emitted from here.
 *  2. `null` is first-class. "No route found" is the correct answer whenever
 *     the fix needs a policy decision rather than a rewiring, and `unroutable`
 *     is reported beside `routable` on every surface. A run where nothing is
 *     routable is a result, not a failure.
 *  3. The router receives VERDICTS, never a target. There is no input to this
 *     file that is a ratio, no comparison against a desired ratio, and nothing
 *     is ranked by ratio impact — ranking is by `effort`, cheapest first. The
 *     moment the score becomes something to optimize it becomes a selection
 *     signal and dies while still rising.
 *  4. `status` is always `'proposed'`, forced here regardless of input.
 *     Applying a change is out of scope for this mode and for any agent.
 *
 * "Mechanically" is a strong word and it was once doing more work here than the
 * tests were. Each of the four is now an executed assertion in
 * `tests/separation.test.ts`, and property 3 — the one the whole unit rests on,
 * and the one whose direction is hardest to test — is held by three:
 *
 *   - the `RouteDispatch` the agent judges from is walked field by field, and
 *     every number in it must be a confidence measured in the source report;
 *     a `currentRatio`, a `targetRatio` or a `nodesNeededToHitTarget` fails;
 *   - `buildDispatch` and `bind` are run against a report whose `grounding`
 *     block has been forged to 1.0, and the requests, the candidate list and
 *     every binding must come back byte-identical — the ratio is not merely
 *     unused, it is unreachable;
 *   - `rankBindings` is run over the same bindings with every `from` permuted,
 *     and the order must not move — an ordering that consulted ratio impact
 *     would change; and a fixture where the CHEAPEST route has the SMALLEST
 *     ratio impact asserts the cheap one still sorts first.
 *
 * The source `Report` is opened READ-ONLY and is never rewritten. That is
 * enforced in `run()`, not asserted: `--out`/`--html` pointed at the input exit
 * 1 having written nothing. The projection has no path back into the
 * measurement layer; `tests/separation.test.ts` executes the measurement path
 * with and without an adversarial bindings file and asserts the verdicts are
 * identical.
 *
 * ---------------------------------------------------------------------------
 * USAGE SHAPE
 * ---------------------------------------------------------------------------
 *   1. `route.ts <report.json> --dispatch > requests.json`   plumbing locates
 *   2. the agent reads `requests.json` and writes `RouteProposal[]`   judgment
 *   3. `route.ts <report.json> --proposals p.json --out b.json --html b.html`
 *
 * Step 3 with no `--proposals` is legal and honest: every in-scope node comes
 * back `anchoredOn: null` with a reason saying no route was proposed. It fails
 * closed, exactly like `unknown` does in the measurement layer.
 */

import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs';
import { dirname, join, resolve } from 'node:path';
import {
  type GroundingClass,
  type Node,
  type Report,
  type Verdict,
  groundingRatio,
} from '../schemas/keel.ts';
import {
  type Binding,
  type BindingReport,
  EFFORT_ORDER,
  type RatioProjection,
  ROUTE_EFFORTS,
  type RouteCandidate,
  type RouteDispatch,
  type RouteEffort,
  type RouteProposal,
  type RouteRequest,
  type UngroundedClass,
  projectRatio,
} from '../schemas/route.ts';

const HERE = import.meta.dir;

/** The classes that sit in the ratio's denominator without being anchored. */
const IN_RATIO_UNGROUNDED: UngroundedClass[] = ['self_referential', 'unknown'];

/**
 * The accept-list, derived from the same array the dispatch advertises. Not
 * restated: a hand-written copy here is exactly how the advertised values and
 * the accepted values drift apart, and a dropped `effort` is a silent
 * un-ranking rather than a loud failure.
 */
const EFFORTS: RouteEffort[] = ROUTE_EFFORTS.map((e) => e.value);

// ---------------------------------------------------------------------------
// Indexing — the mechanical half
// ---------------------------------------------------------------------------

export interface ReportIndex {
  nodes: Map<string, Node>;
  verdicts: Map<string, Verdict>;
  /** ids whose verdict class is exactly `anchored`. The closed world of routes. */
  anchoredIds: string[];
  warnings: string[];
}

/**
 * Build the lookup the validator resolves against.
 *
 * Two honesty checks run here rather than being assumed:
 *
 *  - a verdict for a node id that is not in `nodes` is recorded as a warning
 *    (it can still be routed ONTO, because its class was measured — but the
 *    inconsistency belongs on the record, not in a shrug);
 *  - the report's own `grounding.ratio` is recomputed from its verdicts and any
 *    disagreement is a warning. A bindings file derived from a report whose
 *    headline number does not match its own verdicts would inherit the lie.
 */
export function indexReport(report: Report): ReportIndex {
  const warnings: string[] = [];
  const nodes = new Map<string, Node>();
  for (const n of report.nodes ?? []) nodes.set(n.id, n);

  const verdicts = new Map<string, Verdict>();
  for (const v of report.verdicts ?? []) {
    if (verdicts.has(v.nodeId)) {
      warnings.push(
        `source report holds two verdicts for "${v.nodeId}" — the first is used`,
      );
      continue;
    }
    verdicts.set(v.nodeId, v);
    if (!nodes.has(v.nodeId)) {
      warnings.push(
        `verdict for "${v.nodeId}" has no matching node in the source report`,
      );
    }
  }

  const anchoredIds = [...verdicts.values()]
    .filter((v) => v.class === 'anchored')
    .map((v) => v.nodeId)
    .sort();

  const recomputed = groundingRatio([...verdicts.values()]);
  if (
    report.grounding &&
    Math.abs(recomputed.ratio - report.grounding.ratio) > 1e-9
  ) {
    warnings.push(
      `source report's grounding.ratio (${report.grounding.ratio}) disagrees with its own verdicts (${recomputed.ratio}) — the verdicts are used`,
    );
  }

  return { nodes, verdicts, anchoredIds, warnings };
}

/** The anchored nodes, in the shape the agent is asked to choose from. */
export function candidatesFrom(
  report: Report,
  index: ReportIndex,
): RouteCandidate[] {
  const out: RouteCandidate[] = [];
  for (const id of index.anchoredIds) {
    const v = index.verdicts.get(id);
    if (!v) continue;
    const n = index.nodes.get(id);
    out.push({
      id,
      kind: n?.kind ?? 'other',
      name: n?.name ?? id,
      source: n?.source ?? '(no node record in report)',
      producer: v.writeBoundary?.producer ?? '',
      argument: v.writeBoundary?.argument ?? '',
      confidence: typeof v.confidence === 'number' ? v.confidence : 0,
    });
  }
  return out;
}

export interface ScopeOptions {
  /**
   * Include nodes classified `not_a_check`. Off by default: those nodes are
   * outside the ratio, so routing one adds a check rather than re-grounding an
   * existing one. Different claim, so it takes an explicit ask.
   */
  includeNotACheck?: boolean;
}

/** The classes in scope for routing, given the options. */
export function scopedClasses(opts: ScopeOptions): UngroundedClass[] {
  return opts.includeNotACheck
    ? [...IN_RATIO_UNGROUNDED, 'not_a_check']
    : [...IN_RATIO_UNGROUNDED];
}

/**
 * Assemble one routing question per ungrounded node. Every request carries the
 * SAME candidate list — the whole anchored set — because narrowing it here
 * would be this file quietly making the judgment it is forbidden to make.
 */
export function buildDispatch(
  report: Report,
  sourceReport: string,
  opts: ScopeOptions = {},
): RouteDispatch {
  const index = indexReport(report);
  const candidates = candidatesFrom(report, index);
  const inScope = new Set<GroundingClass>(scopedClasses(opts));

  const requests: RouteRequest[] = [];
  for (const v of index.verdicts.values()) {
    if (!inScope.has(v.class)) continue;
    const node = index.nodes.get(v.nodeId);
    if (!node) continue; // no literal text to reason over; the warning is already recorded
    requests.push({
      node,
      from: v.class as UngroundedClass,
      currentProducer: v.writeBoundary?.producer ?? '',
      currentArgument: v.writeBoundary?.argument ?? '',
      currentConfidence: typeof v.confidence === 'number' ? v.confidence : 0,
      candidates,
    });
  }

  const warnings = [...index.warnings];
  if (candidates.length === 0 && requests.length > 0) {
    warnings.push(
      'no node in this report is classified `anchored`, so no route exists to propose — every binding will be null. That is a finding about the target, not a gap in this run.',
    );
  }

  return {
    target: report.target,
    revision: report.revision,
    sourceReport,
    anchoredIds: index.anchoredIds,
    // Advertised from the same array the validator accepts from, so the legal
    // values reach the agent that has to author them. Carried through, never
    // rebuilt here — a second literal in this file would re-open the drift.
    effortValues: ROUTE_EFFORTS,
    requests,
    warnings,
  };
}

// ---------------------------------------------------------------------------
// Validation — invariant 1, in code
// ---------------------------------------------------------------------------

export interface AnchorCheck {
  anchoredOn: string | null;
  /** set whenever a proposed anchor was refused; becomes the noRouteReason */
  rejection?: string;
}

/**
 * Resolve a proposed anchor against the measured graph. THIS is the invariant:
 * a route may only point at a node that (a) exists in the source report and
 * (b) was classified `anchored` there. Everything else collapses to `null`
 * carrying the reason it collapsed.
 *
 * Note the third refusal. A route with no argument is refused even when the
 * anchor resolves, for the same reason `keel.css` renders a defect banner for a
 * verdict with no `.k-argument`: a class without its causal path is an
 * unaccountable green check, and so is a route.
 */
export function checkAnchor(
  proposed: unknown,
  loop: string,
  argument: string,
  index: ReportIndex,
): AnchorCheck {
  if (proposed === null || proposed === undefined || proposed === '') {
    return { anchoredOn: null };
  }
  if (typeof proposed !== 'string') {
    return {
      anchoredOn: null,
      rejection: `proposed anchor was ${typeof proposed}, not a node id`,
    };
  }
  if (proposed === loop) {
    return {
      anchoredOn: null,
      rejection: `proposed anchor "${proposed}" is the ungrounded node itself — a check cannot be its own producer`,
    };
  }
  const verdict = index.verdicts.get(proposed);
  if (!verdict) {
    return {
      anchoredOn: null,
      rejection: index.nodes.has(proposed)
        ? `proposed anchor "${proposed}" is a node in the source report but carries no verdict, so its class is unmeasured`
        : `proposed anchor "${proposed}" is not a node in the source report`,
    };
  }
  if (verdict.class !== 'anchored') {
    return {
      anchoredOn: null,
      rejection: `proposed anchor "${proposed}" is classified ${verdict.class} in the source report, not anchored`,
    };
  }
  if (argument.trim() === '') {
    return {
      anchoredOn: null,
      rejection: `proposed anchor "${proposed}" resolves, but the proposal carries no argument — a route without its causal path is not a route`,
    };
  }
  return { anchoredOn: proposed };
}

// ---------------------------------------------------------------------------
// Binding
// ---------------------------------------------------------------------------

const NO_PROPOSAL =
  'no route proposed — `--dispatch` emits the judgment payload for this node; the route is the agent\'s to author, and its absence is not evidence that none exists';

const CONSTRUCT_FIELDS = ['pairedWith', 'arbitratedBy', 'auditEvery'] as const;

function isRecord(x: unknown): x is Record<string, unknown> {
  return typeof x === 'object' && x !== null && !Array.isArray(x);
}

/**
 * Name a refused `effort` for the warning, in bounded work and without ever
 * throwing.
 *
 * `JSON.stringify` was the obvious choice and is the wrong one: a proposals
 * file may legally contain a deeply nested value, which parses and then blows
 * the stack on the way back out. The warning path is the FAIL-SAFE path — an
 * exception raised while explaining a refusal turns "warn and drop" into
 * "crash", which is a worse failure than the one being reported. So the shape
 * is named rather than serialised; the agent needs to know its `effort` was
 * refused and why, not to read its own payload back.
 */
function describeEffort(x: unknown): string {
  if (typeof x === 'string') {
    // Bounded. The value is echoed so the author can see exactly what was
    // refused, but a 100 KB string proves nothing a clipped one does not, and
    // an unbounded echo makes the diagnostic harder to read than the defect it
    // is reporting.
    return JSON.stringify(x.length > 60 ? `${x.slice(0, 60)}…` : x);
  }
  if (x === null) return 'null';
  if (Array.isArray(x)) return 'an array';
  if (typeof x === 'number' || typeof x === 'boolean') return String(x);
  const t = typeof x;
  return `${/^[aeiou]/.test(t) ? 'an' : 'a'} ${t}`;
}

/**
 * Accept the several honest shapes a proposals file arrives in:
 * a bare array, `{ proposals: [...] }`, or a whole `BindingReport`
 * (`{ bindings: [...] }`) being re-validated against a report.
 */
export function readProposals(text: string, path: string): RouteProposal[] {
  let parsed: unknown;
  try {
    parsed = JSON.parse(text);
  } catch (err) {
    throw new Error(`${path}: not valid JSON — ${(err as Error).message}`);
  }
  const list = Array.isArray(parsed)
    ? parsed
    : isRecord(parsed) && Array.isArray(parsed.proposals)
      ? parsed.proposals
      : isRecord(parsed) && Array.isArray(parsed.bindings)
        ? parsed.bindings
        : null;
  if (!list) {
    throw new Error(
      `${path}: expected RouteProposal[], { proposals: [...] } or a BindingReport { bindings: [...] }`,
    );
  }
  return list as RouteProposal[];
}

/**
 * Rank cheapest-first. Ranking consults `effort` and the node id; it does NOT
 * consult the projected ratio, the current class, or anything that would make
 * the ordering an optimization over the score.
 */
export function rankBindings(bindings: Binding[]): Binding[] {
  const key = (b: Binding): [number, number, string] => [
    b.anchoredOn === null ? 1 : 0,
    b.effort ? EFFORT_ORDER[b.effort] : EFFORTS.length,
    b.loop,
  ];
  return [...bindings].sort((a, b) => {
    const ka = key(a);
    const kb = key(b);
    return (
      ka[0] - kb[0] || ka[1] - kb[1] || (ka[2] < kb[2] ? -1 : ka[2] > kb[2] ? 1 : 0)
    );
  });
}

export interface BindOptions extends ScopeOptions {
  sourceReport: string;
  generatedAt?: string;
}

/**
 * One `Binding` per in-scope ungrounded node — always, whether or not a
 * proposal arrived for it. The full accounting is the deliverable: a page that
 * listed only the routable nodes would be a scoreboard, and a scoreboard is
 * what turns a measurement into a target.
 */
export function bind(
  report: Report,
  proposals: RouteProposal[],
  opts: BindOptions,
): BindingReport {
  const index = indexReport(report);
  const warnings = [...index.warnings];
  const inScope = new Set<GroundingClass>(scopedClasses(opts));

  // ---- proposals in, keyed by loop, deduplicated loudly -------------------
  const byLoop = new Map<string, RouteProposal>();
  for (const raw of proposals) {
    if (!isRecord(raw) || typeof raw.loop !== 'string' || raw.loop === '') {
      warnings.push('a proposal was dropped: no `loop` node id');
      continue;
    }
    const loop = raw.loop;
    const verdict = index.verdicts.get(loop);
    if (!verdict) {
      warnings.push(
        `proposal for "${loop}" dropped: that node carries no verdict in the source report`,
      );
      continue;
    }
    if (!inScope.has(verdict.class)) {
      warnings.push(
        `proposal for "${loop}" dropped: it is classified ${verdict.class}, which is not in scope for this run`,
      );
      continue;
    }
    if (byLoop.has(loop)) {
      warnings.push(`duplicate proposal for "${loop}" ignored (the first is kept)`);
      continue;
    }
    for (const f of CONSTRUCT_FIELDS) {
      if (raw[f] !== undefined) {
        warnings.push(
          `proposal for "${loop}" set \`${f}\`, which \`keel construct\` fills — dropped, this mode does not emit it`,
        );
      }
    }
    byLoop.set(loop, raw as unknown as RouteProposal);
  }

  // ---- one binding per in-scope node -------------------------------------
  const bindings: Binding[] = [];
  for (const v of index.verdicts.values()) {
    if (!inScope.has(v.class)) continue;
    const from = v.class as UngroundedClass;
    const p = byLoop.get(v.nodeId);

    if (!p) {
      bindings.push({
        loop: v.nodeId,
        from,
        anchoredOn: null,
        argument: '',
        noRouteReason: NO_PROPOSAL,
        status: 'proposed',
      });
      continue;
    }

    const argument = typeof p.argument === 'string' ? p.argument : '';
    const checked = checkAnchor(p.anchoredOn, v.nodeId, argument, index);
    if (checked.rejection) {
      warnings.push(`route for "${v.nodeId}" refused — ${checked.rejection}`);
    }

    const binding: Binding = {
      loop: v.nodeId,
      from,
      anchoredOn: checked.anchoredOn,
      argument,
      // `status` is set here and nowhere else. Whatever a proposal claimed is
      // discarded: an agent may never emit 'applied'.
      status: 'proposed',
    };

    if (typeof p.change === 'string' && p.change.trim() !== '') {
      binding.change = p.change;
    }
    // PRESENT-BUT-INVALID is the condition, not present-and-a-string. Gating on
    // `typeof === 'string'` let `42`, `true`, `null` and `{}` through the other
    // side in silence — dropped with no warning at all, which is a worse
    // version of the very failure this field's discoverability was fixed to
    // stop. Absent stays legal and silent; anything present that is not an
    // advertised value is named and refused.
    //
    // OWN property, not `!== undefined`. `p` is parsed from a proposals file
    // the agent wrote, but `bind` is exported and runs in whatever process the
    // host provides, and `p.effort` walks the prototype chain: with an ambient
    // `Object.prototype.effort = 'process'`, a proposal that declared no effort
    // at all silently acquired one and was RANKED by it, with no warning —
    // verified by executing `bind` under that pollution. An effort nobody
    // authored steering the order is the same defect class as a verdict nobody
    // argued: a value arriving from outside the record and being treated as
    // part of it.
    if (Object.hasOwn(p, 'effort') && p.effort !== undefined) {
      if (typeof p.effort === 'string' && (EFFORTS as string[]).includes(p.effort)) {
        binding.effort = p.effort;
      } else {
        // Warn and drop — never coerce. Picking a default here would be this
        // file inventing `config` because an agent said `low`, which is a
        // judgment plumbing is not allowed to make, and it would silently
        // corrupt the very ordering the field exists to produce. The legal
        // values come from the accept-list itself, so this message cannot name
        // a vocabulary the validator does not actually hold.
        warnings.push(
          // The consequence clause has to hold for BOTH outcomes. An earlier
          // version said "ranks last among the routable", which is a claim
          // about a route that may well have come back null — the warning
          // would then assert a ranking the binding never entered. What is
          // true either way is the tier: no effort sorts behind every effort.
          `proposal for "${v.nodeId}" gave effort ${describeEffort(p.effort)}, which is not ${EFFORTS.join('|')} — dropped, and an unstated effort sorts behind every stated one`,
        );
      }
    }

    if (binding.anchoredOn === null) {
      const given =
        typeof p.noRouteReason === 'string' && p.noRouteReason.trim() !== ''
          ? p.noRouteReason
          : '';
      binding.noRouteReason =
        checked.rejection && given
          ? `${checked.rejection}. Proposal also said: ${given}`
          : (checked.rejection ?? given);
      if (!binding.noRouteReason) {
        binding.noRouteReason =
          'null route with no reason supplied by the proposal — recorded as unroutable, unexamined';
        warnings.push(
          `proposal for "${v.nodeId}" returned a null route with no reason; a placeholder reason was recorded`,
        );
      }
      // effort describes a change; there is no change here.
      delete binding.effort;
    }

    bindings.push(binding);
  }

  const ranked = rankBindings(bindings);
  const routable = ranked.filter((b) => b.anchoredOn !== null).length;
  const current = groundingRatio([...index.verdicts.values()]);
  const projected = projectRatio(current, ranked);

  return {
    target: report.target,
    revision: report.revision,
    generatedAt: opts.generatedAt ?? new Date().toISOString(),
    sourceReport: opts.sourceReport,
    bindings: ranked,
    summary: {
      currentRatio: current.ratio,
      projectedRatio: projected.ratio,
      routable,
      unroutable: ranked.length - routable,
    },
    warnings,
  };
}

// ---------------------------------------------------------------------------
// The page
//
// HTML lives here as string literals rather than in `skills/keel/templates/`
// because that directory belongs to the renderer unit and a second file in it
// would be a merge conflict by construction. The markup should move into a
// governed template once both land — recorded here rather than left implicit.
// ---------------------------------------------------------------------------

function esc(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/** The design system this unit inlines. Owned by another unit; read, never written. */
export const DESIGN_DIR = join(HERE, '..', 'design');

/**
 * Verbatim, per the design contract. Both files are written to be inlined.
 *
 * THROWS when the design system is not readable. That is deliberate and the CLI
 * handles it rather than swallowing it here: a page rendered without the tokens
 * would look like a page, so the honest degradation is to skip the page and say
 * so — which only the caller that knows whether the JSON already landed can
 * decide. See `run()`.
 */
export function loadStyles(dir = DESIGN_DIR): string {
  const tokens = readFileSync(join(dir, 'tokens.css'), 'utf8');
  const keel = readFileSync(join(dir, 'keel.css'), 'utf8');
  return `${tokens}\n${keel}`;
}

/**
 * Layout-only additions. No colour that is not a token, and nothing in a
 * verdict hue — the four hues are the data, and a projection is not data.
 * Candidate for promotion into `keel.css`; proposed, not taken, because the
 * design system is not this unit's to edit.
 */
const ROUTE_CSS = `
.k-route__pair { display: flex; flex-wrap: wrap; align-items: flex-end; gap: var(--k-space-6); }
.k-route__side { display: flex; flex-direction: column; gap: var(--k-space-1); }
.k-route__sep { font-size: var(--k-fs-h1); color: var(--k-ink-3); line-height: 1; }
.k-route__projected { color: var(--k-ink-1); }
.k-route__none { color: var(--k-ink-2); }
.k-route__arrow { color: var(--k-ink-3); }
.k-route__empty { color: var(--k-ink-3); font-family: var(--k-font-mono); }
.k-route__table { table-layout: fixed; }
.k-route__table td { padding-right: var(--k-space-4); }
.k-route__table .k-argument { margin-top: 0; }
.k-route__col--loop   { width: 24%; }
.k-route__col--anchor { width: 17%; }
.k-route__col--why    { width: 48%; }
.k-route__col--effort { width: 11%; }
`;

const SCOPE_NOTE = `<p class="k-scope"><strong>Scope.</strong> Keel measures the shape of
verification, not its quality. A repo can be 100% anchored with terrible
tests. Anchoring says the signal comes from outside; it does not say the
signal is sufficient.</p>`;

function meter(counts: RatioProjection | ReturnType<typeof groundingRatio>): string {
  const total = counts.anchored + counts.selfReferential + counts.unknown;
  if (total === 0) return '';
  const pct = (n: number) => `${((n / total) * 100).toFixed(1)}%`;
  const seg = (cls: GroundingClass, n: number) =>
    n === 0
      ? ''
      : `<div class="k-meter__seg" data-class="${cls}" style="width:${pct(n)}"></div>`;
  return `<div class="k-meter">${seg('anchored', counts.anchored)}${seg(
    'self_referential',
    counts.selfReferential,
  )}${seg('unknown', counts.unknown)}</div>`;
}

function counts(c: RatioProjection | ReturnType<typeof groundingRatio>): string {
  const one = (cls: GroundingClass, n: number) =>
    `<span class="k-ratio__count"><span class="k-class" data-class="${cls}">${cls}</span> ${n}</span>`;
  return `<div class="k-ratio__counts">
  ${one('anchored', c.anchored)}
  ${one('self_referential', c.selfReferential)}
  ${one('unknown', c.unknown)}
  <span class="k-ratio__count k-ratio__count--excluded">
    <span class="k-class" data-class="not_a_check">not_a_check</span> ${c.notACheck}
    <span class="k-meta">excluded from the denominator</span>
  </span>
</div>`;
}

function bindingRow(b: Binding, index: ReportIndex): string {
  const node = index.nodes.get(b.loop);
  const cur = index.verdicts.get(b.loop);
  const name = node?.name ?? b.loop;
  const producer = cur?.writeBoundary?.producer ?? '';

  const left = `<div class="k-mono">${esc(b.loop)}</div>
      <div class="k-meta">${esc(node?.kind ?? '')} · ${esc(name)}</div>
      <div class="k-meta">today the signal comes from ${esc(producer)}</div>
      <div><span class="k-class" data-class="${b.from}">${b.from}</span></div>`;

  if (b.anchoredOn === null) {
    // The causal path is shown even when the answer is "no route": a refusal
    // without its reasoning is as unaccountable as a green check without one.
    return `<tr class="k-route__none">
    <td>${left}</td>
    <td><span class="k-route__empty">no route</span></td>
    <td>${b.argument.trim() === '' ? '' : `<p class="k-argument">${esc(b.argument)}</p>`}
      <p class="k-meta">why not: ${esc(b.noRouteReason ?? '')}</p></td>
    <td><span class="k-route__empty">—</span></td>
  </tr>`;
  }

  const anchor = index.verdicts.get(b.anchoredOn);
  const anchorNode = index.nodes.get(b.anchoredOn);
  return `<tr>
    <td>${left}</td>
    <td><div class="k-mono">${esc(b.anchoredOn)}</div>
      <div><span class="k-class" data-class="anchored"${
        (anchor?.confidence ?? 1) < 0.5 ? ' data-smell' : ''
      }>anchored</span></div>
      <div class="k-meta">${esc(anchorNode?.source ?? '')}</div></td>
    <td><p class="k-argument">${esc(b.argument)}</p>${
      b.change
        ? `<p class="k-meta">change: ${esc(b.change)}</p>`
        : '<p class="k-meta">no change described</p>'
    }
      <p class="k-meta">that producer: ${esc(anchor?.writeBoundary?.producer ?? '')}</p></td>
    <td>${b.effort ? `<span class="k-tag">${b.effort}</span>` : '<span class="k-route__empty">unstated</span>'}</td>
  </tr>`;
}

export function renderBindingsHtml(
  rep: BindingReport,
  report: Report,
  styles = loadStyles(),
): string {
  const index = indexReport(report);
  const current = groundingRatio([...index.verdicts.values()]);
  const projected = projectRatio(current, rep.bindings);
  const n2 = (x: number) => x.toFixed(2);

  // Two different claims, so two tables. A re-grounding moves an existing
  // check's signal outside the write boundary; a construction turns a
  // `not_a_check` node INTO a check. Both raise the ratio and only one of them
  // re-grounds anything, so merging them under a single "routes" heading would
  // let six new checks read as six repaired ones. The second table appears only
  // when `--include-not-a-check` put such nodes in scope.
  const regroundBindings = rep.bindings.filter((b) => b.from !== 'not_a_check');
  const constructedBindings = rep.bindings.filter((b) => b.from === 'not_a_check');
  const rows = regroundBindings.map((b) => bindingRow(b, index)).join('\n');
  const builtRows = constructedBindings.map((b) => bindingRow(b, index)).join('\n');
  const regroundRoutable = regroundBindings.filter((b) => b.anchoredOn !== null).length;
  const builtRoutable = constructedBindings.filter((b) => b.anchoredOn !== null).length;

  const table = (body: string) => `<table class="k-table k-route__table">
    <colgroup>
      <col class="k-route__col--loop">
      <col class="k-route__col--anchor">
      <col class="k-route__col--why">
      <col class="k-route__col--effort">
    </colgroup>
    <thead><tr>
      <th>what's ungrounded</th>
      <th>route to</th>
      <th>why that's anchored</th>
      <th>effort</th>
    </tr></thead>
    <tbody>
${body}
    </tbody>
  </table>`;

  const constructedSection =
    constructedBindings.length === 0
      ? ''
      : `<section>
  <p class="k-eyebrow">Construction — ${builtRoutable} of ${constructedBindings.length} not_a_check nodes could become checks</p>
  <p class="k-lede">These nodes are <span class="k-mono">not_a_check</span> today, so they sit
    outside the ratio entirely. Routing one does not re-ground an existing check —
    it <em>builds a new one</em>, which enters the denominator as well as the
    numerator. Different claim, different cost, counted apart from the routes
    above and never folded into them.</p>
  ${table(builtRows)}
</section>

`;

  const constructRows = rep.bindings
    .filter((b) => b.anchoredOn !== null)
    .map(
      (b) => `<tr>
    <td class="k-mono">${esc(b.loop)}</td>
    <td><span class="k-route__empty">—</span></td>
    <td><span class="k-route__empty">—</span></td>
    <td><span class="k-route__empty">—</span></td>
  </tr>`,
    )
    .join('\n');

  const warnings =
    rep.warnings.length === 0
      ? ''
      : `<section>
  <p class="k-eyebrow">Warnings</p>
  <ul>${rep.warnings.map((w) => `<li class="k-meta">${esc(w)}</li>`).join('')}</ul>
</section>`;

  const body = `<header>
  <p class="k-wordmark">Keel</p>
  <p class="k-eyebrow">keel route</p>
  <h1 class="k-display">Independence cannot be manufactured<em>, but it can be routed.</em></h1>
  <p class="k-lede">Every ungrounded verification edge in
    <span class="k-mono">${esc(rep.target)}</span>, paired — where a pairing
    exists — with an <span class="k-mono">anchored</span> producer <em>already
    present in the same measurement</em>. Nothing here invents an anchor, and
    nothing here has been applied.</p>
  <table class="k-table">
    <tr><th>target</th><td class="k-mono">${esc(rep.target)}</td></tr>
    <tr><th>revision</th><td class="k-mono">${esc(rep.revision)}</td></tr>
    <tr><th>source report</th><td class="k-mono">${esc(rep.sourceReport)}</td></tr>
    <tr><th>generated</th><td class="k-mono">${esc(rep.generatedAt)}</td></tr>
    <tr><th>status</th><td class="k-mono">proposed (all ${rep.bindings.length})</td></tr>
  </table>
</header>

<section class="k-ratio">
  <div class="k-route__pair">
    <div class="k-route__side">
      <span class="k-ratio__value">${n2(rep.summary.currentRatio)}</span>
      <p class="k-meta">today — measured</p>
    </div>
    <span class="k-route__sep">·</span>
    <div class="k-route__side">
      <span class="k-ratio__value k-route__projected">${n2(rep.summary.projectedRatio)}</span>
      <p class="k-meta"><span class="k-tag">projection</span> if applied —
        ${projected.regrounded} re-grounded · ${projected.constructed} constructed</p>
    </div>
  </div>
  <p class="k-ratio__formula">anchored / (anchored + self_referential + unknown)</p>
  ${meter(current)}
  ${counts(current)}
  <p class="k-callout">The second number is a <strong>projection</strong>: the ratio
    this target would carry if a human applied every route below and the applied
    routes measured as anchored on re-measurement. It is arithmetic on a
    hypothetical. It is not written to any report, it is not fed back into the
    grounding ratio, and no proposal on this page has been applied. Projected
    counts, for the same conditional:
    <span class="k-mono">anchored ${projected.anchored} · self_referential ${projected.selfReferential} · unknown ${projected.unknown} · not_a_check ${projected.notACheck}</span>.
    The delta is two different claims and is reported as two:
    <strong>${projected.regrounded} re-grounded</strong> — an existing check whose
    signal moves outside the write boundary, the proposition it asserts unchanged —
    and <strong>${projected.constructed} constructed</strong> — a
    <span class="k-mono">not_a_check</span> node that becomes a check, entering the
    denominator as well as the numerator. Only the first repairs something that was
    already being claimed.</p>
  ${SCOPE_NOTE}
</section>

<section>
  <p class="k-eyebrow">Routes — ${regroundRoutable} routable · ${regroundBindings.length - regroundRoutable} unroutable</p>
  <p class="k-lede">Existing checks whose signal could come from somewhere they cannot
    write. Cheapest effort on top. <span class="k-mono">no route</span> is a
    first-class answer: it means the fix needs a policy decision rather than a
    rewiring, and it is reported here rather than dropped.</p>
  ${table(rows)}
</section>

${constructedSection}<section>
  <p class="k-eyebrow">Construct — not yet.</p>
  <p class="k-lede">A route makes a check read a signal from outside itself. It does
    not pair that check with a counter-metric, name who arbitrates when the pair
    disagrees, or set a cadence at which the route is re-audited. Those three
    fields are declared in <span class="k-mono">schemas/route.ts</span> and are
    filled by <span class="k-mono">keel construct</span>, which is not built.
    The columns are empty by construction, not by omission.</p>
  <table class="k-table">
    <thead><tr>
      <th>route</th>
      <th>pairedWith</th>
      <th>arbitratedBy</th>
      <th>auditEvery</th>
    </tr></thead>
    <tbody>
${constructRows || `<tr><td colspan="4" class="k-meta">no routes on this run</td></tr>`}
    </tbody>
  </table>
</section>

${warnings}

<footer class="k-econ">
  <div class="k-econ__stat"><span class="k-econ__value">${rep.bindings.length}</span><span>ungrounded edges considered</span></div>
  <div class="k-econ__stat"><span class="k-econ__value">${rep.summary.routable}</span><span>routable</span></div>
  <div class="k-econ__stat"><span class="k-econ__value">${rep.summary.unroutable}</span><span>unroutable</span></div>
  <div class="k-econ__stat"><span class="k-econ__value">${index.anchoredIds.length}</span><span>anchored producers available</span></div>
</footer>`;

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>keel route — ${esc(rep.target)}</title>
<style>
${styles}
${ROUTE_CSS}
</style>
</head>
<body>
<main class="k-report">
${body}
</main>
</body>
</html>
`;
}

// ---------------------------------------------------------------------------
// The zero-external-request invariant, checked rather than claimed
// ---------------------------------------------------------------------------

const STRIP_CSS_COMMENTS = /\/\*[\s\S]*?\*\//g;
const STRIP_HTML_COMMENTS = /<!--[\s\S]*?-->/g;
const STYLE_BLOCK = /<style\b[^>]*>([\s\S]*?)<\/style>/gi;
const STYLE_ATTR = /\sstyle\s*=\s*("[^"]*"|'[^']*')/gi;
/** A `>` and everything up to the next `<`: one run of rendered TEXT. */
const TEXT_RUN = />[^<]*/g;

/**
 * The document must fetch nothing.
 *
 * The distinction this function has to hold, and got wrong once: a page may
 * legitimately *mention* a URL — a gathered `raw` often does, a node can be
 * named `build css: @import bundles`, and a write-boundary argument frequently
 * has to say which host a signal is pulled from — while the document itself
 * fetches nothing. So the probes never read rendered text. They read only the
 * two places a browser will actually act on:
 *
 *  - the MARKUP SKELETON (tags and attributes, every text run removed), where
 *    `<script src>`, `<link href>` and media `src` would have to live;
 *  - the CSS the browser executes (`<style>` bodies and `style=` attributes),
 *    where `@import` and `url()` would have to live.
 *
 * Removing the text runs is exact rather than heuristic because `esc()` turns
 * every `<` and `>` in content into an entity, so a run between a `>` and the
 * next `<` cannot contain markup. CSS comments are stripped from style bodies
 * only: `tokens.css` explains in prose why the system is *not* split behind an
 * `@import`, and a check that read that sentence as a violation would be
 * measuring text about text — the exact error this file exists to detect.
 */
export function externalRefs(html: string): string[] {
  const live = html.replace(STRIP_HTML_COMMENTS, '');

  const css: string[] = [];
  const skeleton = live.replace(STYLE_BLOCK, (_m, body: string) => {
    css.push(String(body).replace(STRIP_CSS_COMMENTS, ''));
    return '<style></style>';
  });
  const markup = skeleton.replace(TEXT_RUN, '>');
  for (const m of markup.matchAll(STYLE_ATTR)) css.push(m[1] ?? '');
  const styles = css.join('\n');

  const found: string[] = [];
  const probes: Array<[RegExp, string, string]> = [
    [/<script[^>]*\ssrc=/i, markup, '<script src=>'],
    [/<link[^>]*\shref=/i, markup, '<link href=>'],
    [/<(img|iframe|video|audio|source|embed|object)[^>]*\ssrc=/i, markup, 'embedded media src'],
    [/@import/i, styles, '@import'],
    [/url\(\s*['"]?(?!data:|#)/i, styles, 'css url()'],
  ];
  for (const [re, text, label] of probes) if (re.test(text)) found.push(label);
  return found;
}

// ---------------------------------------------------------------------------
// CLI
// ---------------------------------------------------------------------------

/** `https://github.com/broomva/keel` -> `keel`; used for default filenames. */
export function targetSlug(target: string): string {
  const tail = target.replace(/\/+$/, '').split(/[/\\]/).pop() ?? 'target';
  const slug = tail.replace(/[^a-zA-Z0-9._-]+/g, '-').replace(/^-+|-+$/g, '');
  return slug === '' ? 'target' : slug;
}

const USAGE = `usage: bun scripts/route.ts <report.json> [options]

  <report.json>          a Report (schemas/keel.ts). Opened READ-ONLY, always.

  --dispatch             emit the RouteDispatch judgment payload on stdout and stop.
                         This is the plumbing half: ungrounded nodes, each with the
                         full set of anchored candidates, plus the values \`effort\`
                         may take and what each one means. The argument is yours.
  --proposals <file>     RouteProposal[], { proposals: [...] }, or a BindingReport
                         being re-validated. Every anchor is resolved against the
                         report; one that does not resolve to an \`anchored\` node
                         becomes null with a reason. An \`effort\` outside the
                         dispatched vocabulary is warned about and dropped — never
                         coerced — and that route then ranks last.
  --out <file>           write the BindingReport JSON here
  --html <file>          write the standalone page here (zero external requests)
  --reports-dir <dir>    write <dir>/<target-slug>.bindings.{json,html}
  --design-dir <dir>     read tokens.css + keel.css from here (default: ../design).
                         If they are unreadable the JSON is still written and the
                         page is skipped with a message; the run does not crash.
  --include-not-a-check  also route nodes classified not_a_check. Off by default:
                         those sit outside the ratio, so routing one adds a check
                         rather than re-grounding one. Different claim.
  --strict               exit 1 if any warning was recorded
  --generated-at <iso>   fix the timestamp (for reproducible artifacts)

With no --out/--html/--reports-dir the BindingReport goes to stdout.
With no --proposals every binding is null with a reason: it fails closed.`;

export interface Args {
  input: string;
  proposals: string;
  out: string;
  html: string;
  reportsDir: string;
  designDir: string;
  dispatch: boolean;
  includeNotACheck: boolean;
  strict: boolean;
  generatedAt: string;
}

export function parseArgs(argv: string[]): Args | { error: string } {
  const a: Args = {
    input: '',
    proposals: '',
    out: '',
    html: '',
    reportsDir: '',
    designDir: '',
    dispatch: false,
    includeNotACheck: false,
    strict: false,
    generatedAt: '',
  };
  for (let i = 0; i < argv.length; i++) {
    const arg = argv[i] as string;
    const value = (flag: string): string | { error: string } => {
      const v = argv[i + 1];
      if (v === undefined || v.startsWith('--')) return { error: `${flag} requires a value` };
      i++;
      return v;
    };
    if (arg === '--dispatch') a.dispatch = true;
    else if (arg === '--include-not-a-check') a.includeNotACheck = true;
    else if (arg === '--strict') a.strict = true;
    else if (
      arg === '--proposals' ||
      arg === '--out' ||
      arg === '-o' ||
      arg === '--html' ||
      arg === '--reports-dir' ||
      arg === '--design-dir' ||
      arg === '--generated-at'
    ) {
      const v = value(arg);
      if (typeof v !== 'string') return v;
      if (arg === '--proposals') a.proposals = v;
      else if (arg === '--html') a.html = v;
      else if (arg === '--reports-dir') a.reportsDir = v;
      else if (arg === '--design-dir') a.designDir = v;
      else if (arg === '--generated-at') a.generatedAt = v;
      else a.out = v;
    } else if (arg.startsWith('-')) {
      return { error: `unknown flag ${arg}` };
    } else if (a.input === '') {
      a.input = arg;
    } else {
      return { error: `unexpected second input ${arg}` };
    }
  }
  return a;
}

function writeOut(path: string, text: string): void {
  const dir = dirname(resolve(path));
  if (!existsSync(dir)) mkdirSync(dir, { recursive: true });
  writeFileSync(path, text);
}

/**
 * The whole CLI, as a function that returns an exit code instead of taking one.
 *
 * Exported on purpose: every write in this unit happens below this line, so a
 * test that drove only the pure functions would be asserting the read-onlyness
 * of code that structurally cannot write. `tests/separation.test.ts` drives
 * THIS.
 *
 * Takes the arguments, not `process.argv` — the slice belongs to the caller.
 */
export function run(args: string[]): number {
  if (args.length === 0 || args.includes('-h') || args.includes('--help')) {
    console.log(USAGE);
    return args.length === 0 ? 1 : 0;
  }

  const parsed = parseArgs(args);
  if ('error' in parsed) {
    console.error(`route: ${parsed.error}\n\n${USAGE}`);
    return 1;
  }
  if (parsed.input === '') {
    console.error(`route: no report given\n\n${USAGE}`);
    return 1;
  }
  if (!existsSync(parsed.input)) {
    console.error(`route: ${parsed.input}: no such file`);
    return 1;
  }

  let report: Report;
  try {
    report = JSON.parse(readFileSync(parsed.input, 'utf8')) as Report;
  } catch (err) {
    console.error(`route: ${parsed.input}: not valid JSON — ${(err as Error).message}`);
    return 1;
  }
  if (!Array.isArray(report.nodes) || !Array.isArray(report.verdicts)) {
    console.error(
      `route: ${parsed.input}: not a Report — \`nodes\` and \`verdicts\` must both be arrays`,
    );
    return 1;
  }

  const scope: ScopeOptions = { includeNotACheck: parsed.includeNotACheck };

  if (parsed.dispatch) {
    const dispatch = buildDispatch(report, parsed.input, scope);
    for (const w of dispatch.warnings) console.error(`route: ${w}`);
    console.log(JSON.stringify(dispatch, null, 2));
    return parsed.strict && dispatch.warnings.length > 0 ? 1 : 0;
  }

  let proposals: RouteProposal[] = [];
  if (parsed.proposals) {
    if (!existsSync(parsed.proposals)) {
      console.error(`route: ${parsed.proposals}: no such file`);
      return 1;
    }
    try {
      proposals = readProposals(readFileSync(parsed.proposals, 'utf8'), parsed.proposals);
    } catch (err) {
      console.error(`route: ${(err as Error).message}`);
      return 1;
    }
  } else {
    console.error(
      'route: no --proposals given — every binding will be null with a reason. Run --dispatch first.',
    );
  }

  const bindings = bind(report, proposals, {
    ...scope,
    sourceReport: parsed.input,
    ...(parsed.generatedAt ? { generatedAt: parsed.generatedAt } : {}),
  });
  for (const w of bindings.warnings) console.error(`route: ${w}`);

  const json = `${JSON.stringify(bindings, null, 2)}\n`;
  let wroteSomething = false;

  const outPath = parsed.out || (parsed.reportsDir ? join(parsed.reportsDir, `${targetSlug(report.target)}.bindings.json`) : '');
  const htmlPath = parsed.html || (parsed.reportsDir ? join(parsed.reportsDir, `${targetSlug(report.target)}.bindings.html`) : '');

  // "Opened READ-ONLY, always" is an invariant, so it is enforced rather than
  // asserted. Without this, `--out <the report>` replaced a 30 KB measurement
  // with a 2 KB BindingReport, exit 0, no warning — `nodes` and `verdicts` gone
  // and unrecoverable. A projection destroying the measurement it was derived
  // from is the worst version of the failure this whole unit is built against.
  const source = resolve(parsed.input);
  for (const [flag, path] of [
    ['--out', outPath],
    ['--html', htmlPath],
  ] as const) {
    if (path && resolve(path) === source) {
      console.error(
        `route: refusing to write over the source report — ${flag} points at ${parsed.input}, which is opened read-only. Nothing was written.`,
      );
      return 1;
    }
  }

  if (outPath) {
    writeOut(outPath, json);
    console.error(`route: wrote ${outPath}`);
    wroteSomething = true;
  }
  if (htmlPath) {
    const designDir = parsed.designDir || DESIGN_DIR;
    let styles: string;
    try {
      styles = loadStyles(designDir);
    } catch (err) {
      // Degradation, per the plan's ladder: ship the JSON without the page.
      // A page rendered without the tokens would still look like a page.
      console.error(
        `route: design system not readable at ${designDir} — ${(err as Error).message}`,
      );
      if (wroteSomething) {
        console.error('route: JSON written, page skipped');
        return parsed.strict && bindings.warnings.length > 0 ? 1 : 0;
      }
      console.error('route: nothing was written');
      return 1;
    }
    const html = renderBindingsHtml(bindings, report, styles);
    const refs = externalRefs(html);
    if (refs.length > 0) {
      console.error(
        `route: refusing to write ${htmlPath} — it would fetch: ${refs.join(', ')}`,
      );
      return 1;
    }
    writeOut(htmlPath, html);
    console.error(`route: wrote ${htmlPath} (self-contained, 0 external references)`);
    wroteSomething = true;
  }
  if (!wroteSomething) console.log(json.trimEnd());

  return parsed.strict && bindings.warnings.length > 0 ? 1 : 0;
}

if (import.meta.main) {
  process.exit(run(process.argv.slice(2)));
}
