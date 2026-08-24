/**
 * Typed results. The agent is a user, not a client library: every capability a
 * human can reach is reachable programmatically, and every failure is a value
 * with a machine-legible code -- never a thrown string a caller has to parse.
 *
 * Error types are PER-OPERATION, never one global union. A plugin failure
 * inside a rollout carries a partial trajectory; the same failure at
 * registration carries nothing. A single error type with an optional `partial`
 * field cannot express that difference, and a caller cannot recover from what
 * it cannot distinguish.
 */

export type Ok<T> = { readonly ok: true; readonly value: T };
export type Err<E> = { readonly ok: false; readonly error: E };
export type Result<T, E> = Ok<T> | Err<E>;

export function ok<T>(value: T): Ok<T> {
  return { ok: true, value };
}

export function err<E>(error: E): Err<E> {
  return { ok: false, error };
}

export function isOk<T, E>(r: Result<T, E>): r is Ok<T> {
  return r.ok;
}

/** Every error in the system carries a stable code and a human-readable reason. */
export interface ParallaxError<C extends string> {
  readonly code: C;
  /** One sentence, safe to show a human. Never contains a stack trace. */
  readonly reason: string;
  /** Machine-readable specifics. Shape is documented per code. */
  readonly detail?: Record<string, unknown>;
}

export function fail<C extends string>(
  code: C,
  reason: string,
  detail?: Record<string, unknown>,
): Err<ParallaxError<C>> {
  return err(detail === undefined ? { code, reason } : { code, reason, detail });
}
