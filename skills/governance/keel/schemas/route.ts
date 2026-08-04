/**
 * Keel — the control layer (`keel route`, and later `keel construct` / `keel apply`).
 *
 * One idea, stated once:
 *   Independence cannot be manufactured, but it can be routed.
 *
 * `schemas/keel.ts` is frozen because it is the measurement contract. This file
 * is deliberately NOT frozen: it describes proposals about the world, and a
 * proposal is allowed to be revised. The two must never merge. The measurement
 * layer may not import this file, and nothing here may be written into a
 * `Report` — that one-way edge is what keeps the score from becoming a target
 * (see `tests/separation.test.ts`, which executes the measurement path with and
 * without an adversarial bindings file and asserts the verdicts are identical).
 *
 * The FULL control-layer shape is declared here now, including the fields
 * `keel construct` will fill later, so that adding construction is a code
 * change and not a schema change. `keel route` populates the first group only;
 * the construct fields are rendered visibly empty rather than omitted, because
 * an empty column is legible architecture and an absent one is a promise.
 */

import type { GroundingClass, GroundingRatio, Node, NodeKind } from './keel.ts';

// ---------------------------------------------------------------------------
// Bindings — the artifact.
// ---------------------------------------------------------------------------

/**
 * Every class that is not `anchored`. Written as an `Exclude` rather than a
 * literal union so that a change to `GroundingClass` cannot leave this file
 * quietly describing a world with one fewer class in it.
 *
 * Expands to: `'self_referential' | 'unknown' | 'not_a_check'`.
 */
export type UngroundedClass = Exclude<GroundingClass, 'anchored'>;

/**
 * One legal value of `effort`, carried WITH the distinction that makes it
 * choosable. The semantics live in the data rather than in a comment above the
 * type, because a comment is readable only by whoever opens this file — and the
 * agent authoring proposals judges from the dispatch payload, which is the one
 * place it has no reason to open. An enum whose values are documented somewhere
 * the caller never looks is an undiscoverable enum, and the field gets dropped.
 */
export interface RouteEffortOption {
  /** the literal `effort` a `RouteProposal` may carry */
  readonly value: RouteEffort;
  /** one line: how to tell this effort from the other two */
  readonly means: string;
}

/**
 * How invasive a proposed change is. Used only to RANK — cheapest on top — and
 * never to score. There is deliberately no numeric weight here: a number would
 * invite summing efforts into a "cost", and a cost sits one short step from an
 * objective function over the ratio, which is the failure this whole layer is
 * built to avoid.
 *
 * THE SINGLE SOURCE. The legal values are declared once, here, and everything
 * else is derived from this array: the `RouteEffort` type, the rank order, the
 * validator's accept-list in `scripts/route.ts`, and the list advertised on
 * `RouteDispatch.effortValues`. The values an agent is TOLD are legal and the
 * values the validator ACCEPTS are therefore the same array rather than two
 * lists that agree today — they cannot drift, because there is only one.
 *
 * Declared cheapest-first: the array's own order IS the rank (see
 * `EFFORT_ORDER`), so the ordering cannot disagree with the list either.
 *
 * FROZEN AT RUNTIME, not merely `as const`. `as const` is a compile-time claim
 * and this array is handed out by reference on every `RouteDispatch` — a
 * consumer that pushed onto it would make the dispatch advertise a value the
 * validator still refuses, which is the exact drift this declaration exists to
 * make impossible. "Cannot drift" has to be enforced to be worth writing down;
 * `Object.freeze` is what makes the sentence above true rather than hopeful.
 */
export const ROUTE_EFFORTS = Object.freeze([
  Object.freeze({
    value: 'config',
    means:
      'a value in a file that already exists — a flag, a limit, a `needs:` edge, an existing job\'s `if:`.',
  }),
  Object.freeze({
    value: 'wiring',
    means:
      'new plumbing between things that already exist — a step that reads an artifact another step already produces.',
  }),
  Object.freeze({
    value: 'process',
    means:
      "a change to how people or systems behave — a required check, a branch-protection rule, a third party's involvement.",
  }),
] as const);

/** Expands to: `'config' | 'wiring' | 'process'`. Derived, never restated. */
export type RouteEffort = (typeof ROUTE_EFFORTS)[number]['value'];

export interface Binding {
  /** the node that is not anchored today */
  loop: string;
  /** current class, carried from the Report */
  from: UngroundedClass;

  // ---- W1·R fills these ----
  /**
   * Node id of an `anchored` node IN THE SAME REPORT, or null.
   * null is a first-class answer and is often correct.
   *
   * Validated, not trusted: `route.ts` resolves this against the source
   * report's node ids AND their verdict classes, and rewrites any id that does
   * not resolve to `null` with a `noRouteReason` naming the rejection. A
   * hallucinated anchor is therefore mechanically impossible to emit, rather
   * than discouraged in prose.
   */
  anchoredOn: string | null;
  /** one line: what you would actually change */
  change?: string;
  /** the causal path — why that producer sits outside the write boundary */
  argument: string;
  /** how invasive the change is; used to rank */
  effort?: RouteEffort;
  /** required when anchoredOn is null */
  noRouteReason?: string;

  // ---- `keel construct` fills these later. Declared, not implemented. ----
  /** the counter-metric this route must be read beside */
  pairedWith?: string;
  /** who breaks a tie when the paired metrics disagree */
  arbitratedBy?: string;
  /** the cadence at which the route itself gets re-audited */
  auditEvery?: string;

  /** an agent may NEVER emit 'applied'. */
  status: 'proposed';
}

export interface BindingReport {
  target: string;
  revision: string;
  generatedAt: string;
  /** provenance — which Report this was derived from */
  sourceReport: string;
  bindings: Binding[];
  summary: {
    currentRatio: number;
    /** what the ratio WOULD be if every proposal were applied.
     *  A projection. Labelled as such. NEVER written back to any Report. */
    projectedRatio: number;
    routable: number;
    unroutable: number;
  };
  /**
   * Non-fatal problems: rejected anchors, proposals for nodes that are not in
   * the report, construct fields an upstream proposal tried to set. Never
   * silent — a rejected anchor that vanished quietly would look exactly like a
   * route that was never proposed.
   */
  warnings: string[];
}

// ---------------------------------------------------------------------------
// The dispatch — the contract between plumbing and judgment.
//
// Mirrors `ClassifyOutput` in the measurement layer, and for the same reason:
// the script LOCATES (indexes anchored nodes, assembles candidate pairs, checks
// resolvability) and the agent JUDGES (which candidate, why, what changes, how
// invasive). A table in here mapping "self-referential check" to "canned fix"
// would be the ungrounded artifact Keel exists to detect, wearing our own logo.
// ---------------------------------------------------------------------------

/**
 * One anchored node, offered as a possible producer to read from. Carries the
 * anchored node's OWN write-boundary argument verbatim: the agent's job is to
 * explain why *this* ungrounded check can read *that* producer, and it should
 * be reasoning over the measured argument, not over a summary of it.
 */
export interface RouteCandidate {
  id: string;
  kind: NodeKind;
  name: string;
  source: string;
  /** `writeBoundary.producer` of the candidate's anchored verdict */
  producer: string;
  /** `writeBoundary.argument` of the candidate's anchored verdict */
  argument: string;
  /** the measured confidence. A 0.5 anchor is a weak thing to route onto. */
  confidence: number;
}

/**
 * One routing question. The full `Node` is carried (including `raw`) for the
 * same reason `ClassifyOutput.pending` carries it: the agent reasons over the
 * literal text of the check, never over our paraphrase of it.
 */
export interface RouteRequest {
  node: Node;
  from: UngroundedClass;
  /** why it is ungrounded today, carried from the Report — never re-derived */
  currentProducer: string;
  currentArgument: string;
  currentConfidence: number;
  /**
   * Every `anchored` node in the same report. The closed world of legal
   * answers: an agent that wants to name something outside this list is
   * inventing an anchor, and the validator will turn that into `null`.
   */
  candidates: RouteCandidate[];
}

export interface RouteDispatch {
  target: string;
  revision: string;
  sourceReport: string;
  /** the ids that `anchoredOn` may legally take. Empty means: no routes exist. */
  anchoredIds: string[];
  /**
   * The values `effort` may legally take, each with the distinction that makes
   * it choosable — the same closed-world courtesy `anchoredIds` extends to
   * `anchoredOn`. An agent judging from this payload can author a valid
   * proposal without opening a schema file it has no reason to know about.
   *
   * The semantics travel with the values on purpose. A bare list of three
   * tokens says what is legal but not how to choose, and choosing is precisely
   * the judgment being asked for — so a bare list would push the agent back to
   * guessing, which is the failure this field exists to close.
   *
   * Strings only, and no number anywhere in it. `effort` ranks; it does not
   * weigh. A numeric cost here would be summable into an objective over the
   * ratio, which is the one thing that may never reach the judging agent —
   * `tests/separation.test.ts` walks this payload and fails on any number that
   * is not a confidence measured in the source report.
   */
  readonly effortValues: readonly RouteEffortOption[];
  requests: RouteRequest[];
  warnings: string[];
}

/**
 * What an agent hands back, one per `RouteRequest` it answers. UNTRUSTED —
 * every field is validated in `route.ts` before it becomes a `Binding`.
 * `status` is absent on purpose: it is not the agent's to set.
 *
 * A `BindingReport` is itself a valid proposals input (`{ bindings: [...] }`),
 * so a bindings file can always be re-validated against a fresh Report — which
 * is how a route that referenced a node whose class has since changed gets
 * caught instead of aging into a lie.
 */
export interface RouteProposal {
  loop: string;
  anchoredOn: string | null;
  change?: string;
  argument: string;
  effort?: RouteEffort;
  noRouteReason?: string;
}

// ---------------------------------------------------------------------------
// The projection.
// ---------------------------------------------------------------------------

/**
 * Counts as they WOULD stand if every routable proposal were applied.
 *
 * This is arithmetic on a hypothetical, and the type name says so. It is never
 * a `GroundingRatio`, is never written to a `Report`, and is never passed to
 * `groundingRatio()` — the projection has no path back into the measurement
 * layer, and `tests/separation.test.ts` is the executed proof of that.
 */
export interface RatioProjection {
  anchored: number;
  selfReferential: number;
  unknown: number;
  notACheck: number;
  ratio: number;
  /**
   * How many of the applied routes were RE-GROUNDINGS: an existing check whose
   * signal moves to a producer outside the write boundary. The proposition the
   * check asserts is unchanged; only its producer moves.
   */
  regrounded: number;
  /**
   * How many were CONSTRUCTIONS: a `not_a_check` node that becomes a check.
   * A different claim with a different cost, so it is counted separately and
   * rendered separately. Merging the two into one headline delta would let a
   * run that built six new checks read as if six checks had been re-grounded.
   */
  constructed: number;
}

/**
 * Move every routed node into `anchored` and recompute.
 *
 * `not_a_check` deserves a word, because it is the shoppable class. Routing a
 * `not_a_check` node does not re-ground an existing check — it turns a
 * non-check into a check, so it enters the DENOMINATOR as well as the
 * numerator. That is a different claim from re-grounding, which is why
 * `route.ts` leaves those nodes out of scope unless asked for them explicitly.
 * When they are in scope the arithmetic here keeps them honest rather than
 * letting them arrive as free numerator.
 *
 * The two kinds are counted apart (`regrounded` / `constructed`) and counted
 * HERE rather than re-derived by the renderer, so the split can never drift
 * from the arithmetic it describes: both come out of the same loop, including
 * the `> 0` floors, so a binding the projection declined to apply is not
 * reported to a reader as though it had been.
 */
export function projectRatio(
  current: Pick<
    GroundingRatio,
    'anchored' | 'selfReferential' | 'unknown' | 'notACheck'
  >,
  bindings: Binding[],
): RatioProjection {
  let { anchored, selfReferential, unknown, notACheck } = current;
  let regrounded = 0;
  let constructed = 0;

  for (const b of bindings) {
    if (b.anchoredOn === null) continue;
    if (b.from === 'self_referential' && selfReferential > 0) {
      selfReferential--;
      anchored++;
      regrounded++;
    } else if (b.from === 'unknown' && unknown > 0) {
      unknown--;
      anchored++;
      regrounded++;
    } else if (b.from === 'not_a_check' && notACheck > 0) {
      // leaves the excluded bucket and enters the ratio as a real check
      notACheck--;
      anchored++;
      constructed++;
    }
  }

  const total = anchored + selfReferential + unknown;
  return {
    anchored,
    selfReferential,
    unknown,
    notACheck,
    ratio: total === 0 ? 0 : anchored / total,
    regrounded,
    constructed,
  };
}

/**
 * Rank order for `effort`. Cheapest first; an unstated effort sorts last
 * because "we did not say" is not cheap, it is unmeasured.
 *
 * Derived from position in `ROUTE_EFFORTS` rather than restated, so the rank
 * and the list of legal values cannot disagree about which efforts exist.
 *
 * Frozen for the same reason the table is: this map is exported, and it is what
 * `rankBindings` reads. Left mutable, one write to `EFFORT_ORDER.config` would
 * silently reorder every bindings page while the dispatch went on advertising
 * cheapest-first — a derived value is only as trustworthy as the thing it is
 * derived from, so it inherits the freeze rather than just the arithmetic.
 */
export const EFFORT_ORDER: Readonly<Record<RouteEffort, number>> = Object.freeze(
  Object.fromEntries(ROUTE_EFFORTS.map((e, i) => [e.value, i])) as Record<
    RouteEffort,
    number
  >,
);
