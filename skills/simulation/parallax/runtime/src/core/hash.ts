import { createHash } from "node:crypto";

/**
 * Canonical JSON (RFC 8785 flavour, trimmed to what we need).
 * Keys sorted, no whitespace, floats as decimal strings, undefined dropped.
 * If this is wrong, two identical requests get different ids and the cache
 * silently misses -- so it is the one function that must not drift.
 */
export function canonical(value: unknown): string {
  if (value === null) return "null";
  if (typeof value === "boolean") return value ? "true" : "false";
  if (typeof value === "number") {
    if (!Number.isFinite(value)) throw new Error(`non-finite number in derivation: ${value}`);
    // decimal string, never IEEE repr -- 0.1+0.2 must not become a new cache key
    return Number.isInteger(value) ? String(value) : value.toFixed(12).replace(/0+$/, "");
  }
  if (typeof value === "string") return JSON.stringify(value.normalize("NFC"));
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (typeof value === "object") {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonical(v)}`).join(",")}}`;
  }
  throw new Error(`uncanonicalizable value of type ${typeof value}`);
}

export function h(value: unknown): string {
  return createHash("sha256").update(canonical(value)).digest("hex").slice(0, 32);
}

/** Reproducibility lattice. A node is only as reproducible as its weakest input. */
export const CLASS = { PINNED: 2, STABLE: 1, RECORDED: 0 } as const;
export type Klass = keyof typeof CLASS;

export function meet(...classes: Klass[]): Klass {
  let worst: Klass = "PINNED";
  for (const c of classes) if (CLASS[c] < CLASS[worst]) worst = c;
  return worst;
}

export interface Derivation {
  kind: string;
  model: string;
  params: Record<string, unknown>;
  seed: number | null;
  inputs: string[];
  declared: Klass;
}

export function derivationId(d: Derivation): string {
  return h({ kind: d.kind, model: d.model, params: d.params, seed: d.seed, inputs: d.inputs });
}

/**
 * Effective class of a derivation given its inputs' classes.
 * A seedless derivation can never be PINNED no matter what it declares --
 * the gate refuses the declaration rather than trusting it.
 */
export function effectiveClass(d: Derivation, inputClasses: Klass[]): Klass {
  const own: Klass = d.seed === null && d.declared === "PINNED" ? "STABLE" : d.declared;
  return meet(own, ...inputClasses);
}
