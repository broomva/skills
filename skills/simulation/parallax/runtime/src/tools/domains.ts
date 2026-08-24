import { h } from "../core/hash";
import type { TypeRecord } from "../core/types";
import { clinic } from "../worlds/clinic";
import { storefront } from "../worlds/storefront";
import { fail, ok, type ParallaxError, type Result } from "./errors";

/**
 * The executable half of an acceptance, as a FIXED registry keyed by name.
 *
 * `activate` requires a `transition` and a non-empty `invariants` list, and both
 * are functions. Functions do not serialise, so an acceptance can only ever
 * round-trip as a REFERENCE to code plus the answers a human gave -- never as
 * the ontology itself.
 *
 * The reference is a registry KEY, not a filesystem path, and that is a security
 * boundary rather than a convenience. Resolving a caller-supplied path would
 * mean `await import()` of arbitrary code chosen by whoever wrote the request
 * body. Inside a sandboxed agent session that adds no capability the agent
 * lacks; reachable from an HTTP handler it is remote code execution behind a
 * JSON field. One rule, applied at the widest surface: the key comes from this
 * list or the call is refused.
 */
const REGISTRY: Record<string, TypeRecord> = {
  storefront,
  clinic,
};

export const DOMAIN_KEYS: readonly string[] = Object.keys(REGISTRY).sort();

export const DEFAULT_DOMAIN = "storefront";

export type DomainError = ParallaxError<"UNKNOWN_DOMAIN" | "DOMAIN_INVALID">;

export function resolveDomain(key: string): Result<TypeRecord, DomainError> {
  const world = REGISTRY[key];
  if (world === undefined) {
    return fail("UNKNOWN_DOMAIN", `no domain registered as "${key}"`, {
      given: key,
      known: DOMAIN_KEYS,
    });
  }
  return checkDomainShape(key, world);
}

/**
 * Shape-check before anything is accepted against it. `activate` already refuses
 * a missing transition and an empty invariant set, but it cannot see a domain
 * whose invariant has no `check`, and that failure would surface later as a
 * TypeError in the middle of a rollout rather than as a refusal at the gate.
 */
export function checkDomainShape(key: string, world: TypeRecord): Result<TypeRecord, DomainError> {
  if (typeof world.transition !== "function") {
    return fail("DOMAIN_INVALID", `domain "${key}" has no transition function`, {
      export: "transition",
    });
  }
  if (!Array.isArray(world.invariants) || world.invariants.length === 0) {
    return fail("DOMAIN_INVALID", `domain "${key}" declares no invariants`, {
      export: "invariants",
    });
  }
  for (const inv of world.invariants) {
    if (typeof inv?.name !== "string" || typeof inv?.check !== "function") {
      return fail("DOMAIN_INVALID", `domain "${key}" has an invariant with no check`, {
        export: "invariants",
        invariant: inv?.name ?? null,
      });
    }
  }
  if (typeof world.initial !== "object" || world.initial === null) {
    return fail("DOMAIN_INVALID", `domain "${key}" has no initial state`, { export: "initial" });
  }
  if (!Array.isArray(world.actions)) {
    return fail("DOMAIN_INVALID", `domain "${key}" has no action list`, { export: "actions" });
  }
  return ok(world);
}

/**
 * A hash over the domain's DATA and its CODE.
 *
 * Hashing only `initial` and `actions` would let a rewritten transition or a
 * loosened invariant run under an acceptance that predates it -- "accepted"
 * would name something mutable. Function source text is included so a changed
 * rule fails loudly at re-mint (DOMAIN_CHANGED) instead of quietly executing.
 */
export function domainHash(world: TypeRecord): string {
  return h({
    slug: world.slug,
    initial: world.initial,
    actions: world.actions,
    transition: world.transition.toString(),
    invariants: world.invariants.map((i) => ({
      name: i.name,
      kind: i.kind,
      check: i.check.toString(),
    })),
  });
}
