/**
 * Provenance -- the observed/simulated axis.
 *
 * This is deliberately NOT the same axis as the reproducibility class in
 * hash.ts. They answer different questions and collapsing them loses one:
 *
 *   origin  -- did this come from the referent, or did we generate it?
 *   klass   -- if we run it again, do we get the same thing?
 *
 * A real customer message is `observed` and unrepeatable (RECORDED). A seeded
 * scripted actor is `simulated` and perfectly repeatable (PINNED). Neither axis
 * predicts the other.
 *
 * The typing happens at BIRTH. An untagged value can never be separated later,
 * because the information required to do it was discarded at the moment the
 * value was created -- so there is no "add provenance afterwards" path, by
 * construction rather than by discipline.
 */

export type Origin = "observed" | "simulated";

/**
 * Contamination flows one way. A value derived from anything simulated is
 * simulated, however much observed data went in beside it. This is a meet on
 * the two-element lattice observed > simulated -- the same shape as the
 * reproducibility meet, for the same reason: a derived answer is only as real
 * as its least real input.
 */
export function meetOrigin(...origins: Origin[]): Origin {
  return origins.includes("simulated") ? "simulated" : "observed";
}

/** A value that knows where it came from. */
export interface Tagged<T> {
  readonly value: T;
  readonly origin: Origin;
}

export function observed<T>(value: T): Tagged<T> {
  return { value, origin: "observed" };
}

export function simulated<T>(value: T): Tagged<T> {
  return { value, origin: "simulated" };
}

/**
 * Combine tagged values. The result is observed only if every input was.
 * Use this rather than reading `.value` directly, or the tag stops propagating
 * and the guarantee quietly becomes decoration.
 */
export function combine<T, R>(inputs: Tagged<T>[], f: (values: T[]) => R): Tagged<R> {
  return {
    value: f(inputs.map((i) => i.value)),
    origin: meetOrigin(...inputs.map((i) => i.origin)),
  };
}

/** Split a trajectory's answer into what was measured and what was produced. */
export interface OriginSplit {
  readonly observed: number;
  readonly simulated: number;
}

export function splitOrigins(origins: Origin[]): OriginSplit {
  let obs = 0;
  for (const o of origins) if (o === "observed") obs++;
  return { observed: obs, simulated: origins.length - obs };
}
