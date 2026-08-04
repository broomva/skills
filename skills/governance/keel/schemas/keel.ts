/**
 * Keel — core contracts.
 *
 * One idea, stated once:
 *   A check is only a check if the signal it reads comes from somewhere the
 *   thing being checked cannot write to.
 *
 * Everything below is bookkeeping for that sentence.
 */

// ---------------------------------------------------------------------------
// Nodes — candidate verification edges gathered from a target.
// Gathering is mechanical (find the surfaces). Judging is not (see Verdict).
// ---------------------------------------------------------------------------

export type NodeKind =
  | 'ci_step' //  a step in a pipeline
  | 'script' //  a package/make/task script
  | 'test_target' //  a declared test suite
  | 'review_gate' //  human or bot review requirement
  | 'deploy_gate' //  promotion / release condition
  | 'doc_claim' //  a doc asserting something is verified
  | 'integration' //  an external system wired in
  | 'other';

export interface Node {
  /** stable id: `${source}#${slug}` */
  id: string;
  kind: NodeKind;
  /** human name, e.g. "test (unit)" */
  name: string;
  /** where it was found — repo-relative path (+ line if known) */
  source: string;
  /** the literal snippet. The agent reasons over this, not over our summary. */
  raw: string;
  /** free-form extras the gatherer happened to learn. Never authoritative. */
  hints?: Record<string, string>;
}

// ---------------------------------------------------------------------------
// Verdicts — the classification.
// ---------------------------------------------------------------------------

/**
 * anchored        the signal is produced by something the target's agents /
 *                 authors cannot write to. Execution, external systems,
 *                 physical reality, third parties.
 *
 * self_referential the signal is produced inside the write boundary. An LLM
 *                 judging its own output, a doc checked against a doc, a
 *                 status field the actor sets.
 *
 * unknown         we could not establish the fork point.
 *                 FAILS CLOSED. Counts against the ratio. Never a default
 *                 green, and never settable by the thing being measured.
 *
 * not_a_check     the gatherer surfaced it, but it does not assert anything
 *                 about correctness (a dev server, a help target, a formatter
 *                 that only rewrites). EXCLUDED from the ratio entirely.
 *
 *                 This class is SHOPPABLE and must be watched: mis-filing a
 *                 real check here shrinks the denominator and inflates the
 *                 score. So it carries the same burden of argument as any
 *                 other verdict, the report surfaces its count next to the
 *                 ratio, and the audit samples it like everything else. If you
 *                 are tempted to use it because a node is hard to classify,
 *                 the honest answer is `unknown`.
 */
export type GroundingClass =
  | 'anchored'
  | 'self_referential'
  | 'unknown'
  | 'not_a_check';

export interface WriteBoundaryArgument {
  /** what actually emits the signal ("vitest process exit code", "an LLM") */
  producer: string;
  /**
   * Can the actor being verified write to that producer's output?
   * true  -> self_referential
   * false -> anchored
   * null  -> unknown (fails closed)
   */
  actorCanWrite: boolean | null;
  /** one or two sentences. Must name the causal path, not restate the class. */
  argument: string;
}

export interface Verdict {
  nodeId: string;
  class: GroundingClass;
  writeBoundary: WriteBoundaryArgument;
  /** concrete citations — file:line, config keys, command names. */
  evidence: string[];
  /** 0..1 — how sure. Low confidence + anchored is a smell; surface it. */
  confidence: number;
  /** provenance of the decision itself */
  decidedBy: 'probe' | 'agent';
  probeId?: string;
  /** set when an ε-audit re-decided this node agentically */
  audit?: {
    agentClass: GroundingClass;
    agreed: boolean;
    at: string;
  };
}

// ---------------------------------------------------------------------------
// Classify dispatch — the contract between plumbing and judgment.
// ---------------------------------------------------------------------------

/**
 * Output of the probe-dispatch stage. Probe code executes ONLY inside the
 * sandboxed child process (see docs/plans/00-orchestration.md, "The sandbox
 * contract") — a synchronous `while(true)` in-process cannot be preempted in
 * JS, so in-process probe execution is forbidden, not discouraged.
 *
 * `pending` carries FULL nodes (including `raw`) — the agent judges over the
 * literal text. Batch pending nodes 10–20 per judgment call; one node per
 * call does not survive a 15-repo corpus night.
 */
export interface ClassifyOutput {
  decided: Verdict[];
  pending: Node[];
  /** non-fatal problems: skipped probes, load rejections, timeouts. Never silent. */
  warnings: string[];
}

// ---------------------------------------------------------------------------
// Probes — crystallized judgment. Code, because code is reviewable.
// ---------------------------------------------------------------------------

/**
 * What a probe is allowed to return.
 *
 * `unknown` is EXCLUDED at the type level, not by convention. `unknown` is a
 * claim about the world and only the agent may make it; a probe that cannot
 * tell says so by returning `null` (abstain). This is the mechanism that keeps
 * `unknown` unshoppable — and it must be a type, because "enforce at load time"
 * is not implementable: a probe's return value is only knowable by CALLING it,
 * and calling it is exactly what may only happen inside the sandbox child.
 *
 * Runtime belt-and-braces still applies at assess-call time in the sandbox
 * (a probe can be plain JS and lie to the compiler) — but the contract is here.
 */
export type ProbeVerdict = Omit<
  Verdict,
  'nodeId' | 'decidedBy' | 'probeId' | 'class'
> & {
  class: Exclude<GroundingClass, 'unknown'>;
};

export interface ProbeMeta {
  id: string;
  version: number;
  /** ISO date */
  mintedAt: string;
  /** the node id whose novelty caused this probe to exist */
  mintedFrom: string;
  /** what shape of node this generalizes. Plain language. */
  description: string;
}

export interface Probe extends ProbeMeta {
  /** cheap structural filter. Must be pure and fast. */
  match(node: Node): boolean;
  /**
   * The judgment.
   *
   * Returning `null` is a first-class outcome and means ABSTAIN — the probe
   * recognizes the shape but cannot establish the fork point here. Abstention
   * falls through to the agent.
   *
   * A probe may never return `unknown` as a verdict. `unknown` is a statement
   * about the *world* and only the agent may make it; a probe that cannot tell
   * says so by abstaining. This is what keeps `unknown` unshoppable: the thing
   * being measured can never cause a cheap green, and a lazy probe degrades to
   * "ask the agent" rather than to "looks fine".
   */
  assess(node: Node): ProbeVerdict | null;
}

// ---------------------------------------------------------------------------
// Report — the artifact.
// ---------------------------------------------------------------------------

export interface Report {
  target: string;
  /** commit sha / version of what was measured */
  revision: string;
  generatedAt: string;
  nodes: Node[];
  verdicts: Verdict[];
  grounding: GroundingRatio;
  economics: RunEconomics;
}

export interface GroundingRatio {
  anchored: number;
  selfReferential: number;
  unknown: number;
  /** Excluded from the ratio. Reported anyway — it is the shoppable class. */
  notACheck: number;
  /** anchored / (anchored + selfReferential + unknown). `unknown` counts against. */
  ratio: number;
}

/**
 * The second result: the crystallization curve.
 * Per-run cost, so a sequence of runs shows structure emerging.
 */
export interface RunEconomics {
  nodesTotal: number;
  /** gathered vs judged — when a cap samples nodes, BOTH are reported. No silent caps. */
  nodesSampled: number;
  decidedByProbe: number;
  decidedByAgent: number;
  probesMinted: number;
  probeLibrarySize: number;
  tokensIn: number;
  tokensOut: number;
  /**
   * TRUE whenever token counts are estimates. A skill running inside an agent
   * session has no API for its own token usage, so tonight this is always
   * true: estimate = ceil(chars/4) of judgment payloads + responses. Charts
   * MUST label the axis "estimated tokens". Wall-clock and probe-decided
   * share are measured directly and carry the curve on their own if needed.
   */
  tokensEstimated: boolean;
  wallClockMs: number;
}

/**
 * Coverage — what the gatherer could see, by kind.
 *
 * The ratio must NEVER be displayed without (a) the absolute anchored count
 * and (b) this coverage beside it. A 1.0 over one edge and a 0.7 over fifty
 * are different claims; a bare ratio rewards *deleting* checks; and surfaces
 * the gatherer cannot read are silently absent rather than `unknown` — which
 * makes non-coverage Keel's own shoppable class. A metric must never travel
 * alone. Including ours.
 */
export function coverageByKind(nodes: Node[]): Record<string, number> {
  return nodes.reduce<Record<string, number>>((a, n) => {
    a[n.kind] = (a[n.kind] ?? 0) + 1;
    return a;
  }, {});
}

export function groundingRatio(verdicts: Verdict[]): GroundingRatio {
  const count = (c: GroundingClass) => verdicts.filter((v) => v.class === c).length;
  const anchored = count('anchored');
  const selfReferential = count('self_referential');
  const unknown = count('unknown');
  const notACheck = count('not_a_check');
  // not_a_check is excluded from the denominator: it asserts nothing, so
  // counting it either way would be a lie. It is reported separately instead.
  const total = anchored + selfReferential + unknown;
  return {
    anchored,
    selfReferential,
    unknown,
    notACheck,
    ratio: total === 0 ? 0 : anchored / total,
  };
}
