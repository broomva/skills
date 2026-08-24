import { h, type Klass, meet } from "./hash";
import type { EventLog } from "./log";
import type { Event, State, TypeRecord, Violation } from "./types";

/** A policy proposes the next action. LLM-backed or scripted -- the runtime does not care. */
export interface Policy {
  name: string;
  klass: Klass;
  propose(state: State, seq: number, seed: number): Promise<Omit<Event, "seq" | "branch"> | null>;
}

/** step -- f. Pure. Never an LLM. */
export function step(world: TypeRecord, state: State, e: Event): State {
  return world.transition(state, e);
}

/** observe -- h. Fold the log into the present. Deterministic by construction. */
export function observe(world: TypeRecord, log: EventLog, branch: string): State {
  return log.read(branch).reduce((s, e) => step(world, s, e), structuredClone(world.initial));
}

/** check -- the verifier. Pure predicates over state. Never an LLM. */
export function check(world: TypeRecord, state: State, seq: number): Violation[] {
  return world.invariants
    .map((inv) => {
      const message = inv.check(state);
      return message === null ? null : { invariant: inv.name, message, seq };
    })
    .filter((v): v is Violation => v !== null);
}

/** rollout -- project the log forward under a policy. The counterfactual engine. */
export async function rollout(
  world: TypeRecord,
  log: EventLog,
  branch: string,
  policy: Policy,
  horizon: number,
  seed: number,
): Promise<{ violations: Violation[]; state: State }> {
  let state = observe(world, log, branch);
  const violations: Violation[] = [];
  for (let i = 0; i < horizon; i++) {
    const proposed = await policy.propose(state, i, seed + i);
    if (proposed === null) break;
    const e = log.append({ ...proposed, branch, klass: meet(proposed.klass, policy.klass) });
    state = step(world, state, e);
    violations.push(...check(world, state, e.seq));
  }
  return { violations, state };
}

/** A branch's identity: same events in, same hash out. Replay becomes a comparison. */
export function traceHash(log: EventLog, branch: string): string {
  return h(
    log.read(branch).map((e) => ({ a: e.actor, n: e.action, p: e.params, d: e.derivation })),
  );
}

/** diff -- what changed between two worlds that shared a past. */
export function diff(a: State, b: State): Array<{ key: string; from: unknown; to: unknown }> {
  const keys = new Set([...Object.keys(a), ...Object.keys(b)]);
  return [...keys]
    .filter((k) => h(a[k] ?? null) !== h(b[k] ?? null))
    .map((k) => ({ key: k, from: a[k], to: b[k] }));
}

// ---------------------------------------------------------------------------
// Certification, scoring, and the trajectory. Appended for BRO-2226.
// ---------------------------------------------------------------------------

import { effectiveClass } from "./hash";
import { meetOrigin, type Origin } from "./provenance";
import { fail, ok, type ParallaxError, type Result } from "./result";

/** One step of a run: what was proposed, what it produced, and where it came from. */
export interface Step {
  readonly event: Event;
  readonly state: State;
  readonly violations: Violation[];
  readonly origin: Origin;
}

export type Trajectory = readonly Step[];

export type CertifyError = ParallaxError<"POLICY_THREW" | "POLICY_EMPTY">;

export interface Certificate {
  readonly policy: string;
  /** What the policy says about itself. */
  readonly declared: Klass;
  /** What it actually demonstrated under a repeated probe. */
  readonly effective: Klass;
  readonly demoted: boolean;
  readonly trials: number;
  readonly reason: string;
}

/**
 * The eviction test.
 *
 * A reproducibility class that a policy declares about itself is not evidence.
 * `effectiveClass` existed in hash.ts from the beginning and nothing ever called
 * it, so until now the lattice took every adapter at its word -- which is
 * precisely the "confident numbers about a world that does not exist" failure
 * this system was built to refuse, reproduced inside the system itself.
 *
 * So: run the policy repeatedly against an identical probe and compare what it
 * produces. A policy that cannot reproduce its own output under a fixed seed is
 * demoted in code however it declares itself.
 *
 * This is a FILTER, not a proof, and its false-negative rate is worth stating
 * rather than hiding. A nondeterministic policy escapes detection whenever all
 * `trials` draws happen to collide: for a policy with k roughly-equiprobable
 * outputs that is about k^-(trials-1) -- 4% at k=5, trials=3. Our own test
 * suite caught this by flaking, which is the correct outcome and the reason the
 * bound is documented here instead of the default being quietly raised.
 *
 * Raise `trials` when the policy's output space is small; the default suits an
 * adapter reaching for a model, a clock, or ambient randomness, where the
 * output space is large and one differing draw is nearly certain. A policy that
 * PASSES certification has not been proven pure -- no finite test can do that.
 * It has only failed to be caught.
 */
export async function certifyPolicy(
  policy: Policy,
  probe: { state: State; seq: number; seed: number },
  trials = 3,
): Promise<Result<Certificate, CertifyError>> {
  const seen: string[] = [];
  for (let i = 0; i < trials; i++) {
    let proposed: Awaited<ReturnType<Policy["propose"]>>;
    try {
      proposed = await policy.propose(structuredClone(probe.state), probe.seq, probe.seed);
    } catch (e) {
      return fail("POLICY_THREW", `${policy.name} threw during certification`, {
        cause: e instanceof Error ? e.message : String(e),
        trial: i,
      });
    }
    if (proposed === null) {
      return fail("POLICY_EMPTY", `${policy.name} proposed nothing on the probe state`);
    }
    seen.push(h({ a: proposed.actor, n: proposed.action, p: proposed.params }));
  }

  const reproducible = seen.every((x) => x === seen[0]);
  // A seedless or non-reproducible policy can never be PINNED, whatever it declares.
  const effective = effectiveClass(
    {
      kind: "policy",
      model: policy.name,
      params: {},
      seed: reproducible ? probe.seed : null,
      inputs: [],
      declared: policy.klass,
    },
    [],
  );
  const demoted = effective !== policy.klass;
  return ok({
    policy: policy.name,
    declared: policy.klass,
    effective,
    demoted,
    trials,
    reason: reproducible
      ? `produced an identical proposal across ${trials} trials at seed ${probe.seed}`
      : `produced ${new Set(seen).size} distinct proposals across ${trials} identical trials`,
  });
}

/**
 * rollout, with the certificate rather than the declaration.
 *
 * Identical to `rollout` except the class written onto each event comes from a
 * certificate produced by `certifyPolicy`, so a policy cannot enter the log
 * carrying a claim it has not demonstrated.
 */
export async function rolloutCertified(
  world: TypeRecord,
  log: EventLog,
  branch: string,
  policy: Policy,
  cert: Certificate,
  horizon: number,
  seed: number,
): Promise<{ violations: Violation[]; state: State; trajectory: Trajectory }> {
  let state = observe(world, log, branch);
  const violations: Violation[] = [];
  const trajectory: Step[] = [];
  for (let i = 0; i < horizon; i++) {
    const proposed = await policy.propose(state, i, seed + i);
    if (proposed === null) break;
    const e = log.append({ ...proposed, branch, klass: meet(proposed.klass, cert.effective) });
    state = step(world, state, e);
    const v = check(world, state, e.seq);
    violations.push(...v);
    // A branch is observed only while nothing simulated has entered it.
    const origin: Origin = cert.effective === "RECORDED" ? "observed" : "simulated";
    trajectory.push({ event: e, state, violations: v, origin });
  }
  return { violations, state, trajectory };
}

export type ScoreError = ParallaxError<"EMPTY_TRAJECTORY" | "OBJECTIVE_THREW">;

export interface Objective {
  readonly name: string;
  /** Any fold over a trajectory. Nothing about it is domain-specific. */
  readonly of: (t: Trajectory) => number;
  /** Higher is better unless this says otherwise. */
  readonly direction?: "maximize" | "minimize";
}

export interface Score {
  readonly objective: string;
  readonly value: number;
  /** A run that violated an invariant scores nothing. Constraints are hard. */
  readonly admissible: boolean;
  /** The provenance of the answer, not of the run. */
  readonly origin: Origin;
}

/**
 * score -- fold a trajectory into a number, and carry how real that number is.
 *
 * This is `observe` with a numeric codomain over a trajectory rather than a
 * log, which is why it does not need a seventh operator: an objective needs
 * intermediate states (time-integrated cost, peak drawdown, violations along
 * the way), so what widens is the observation operator's DOMAIN, not the
 * operator set.
 */
export function score(trajectory: Trajectory, objective: Objective): Result<Score, ScoreError> {
  if (trajectory.length === 0) {
    return fail("EMPTY_TRAJECTORY", "nothing to score: the rollout produced no steps");
  }
  let value: number;
  try {
    value = objective.of(trajectory);
  } catch (e) {
    return fail("OBJECTIVE_THREW", `objective ${objective.name} threw`, {
      cause: e instanceof Error ? e.message : String(e),
    });
  }
  const admissible = trajectory.every((s) => s.violations.length === 0);
  return ok({
    objective: objective.name,
    value,
    admissible,
    origin: meetOrigin(...trajectory.map((s) => s.origin)),
  });
}
