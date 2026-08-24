import type { Klass } from "../core/hash";
import type { Policy } from "../core/ops";
import type { Event, State } from "../core/types";

/** Seeded PRNG. Determinism is the product, so randomness is never ambient. */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

const SKUS = ["arepa_kit", "cafe_500g", "panela"];

/**
 * The ungoverned sales agent: eager to please. Vending-Bench found agents fail
 * from helpfulness rather than reasoning -- this reproduces that failure mode
 * deterministically, so the demo can show the governor catching it.
 *
 * PINNED because it is seeded and pure. Swap in an LLM here and the class
 * drops to STABLE automatically -- the lattice does not need to be told.
 */
export function eagerAgent(klass: Klass = "PINNED"): Policy {
  return {
    name: "eager-agent",
    klass,
    async propose(state: State, i: number, seed: number) {
      const r = rng(seed);
      const s = state as { price: Record<string, number> };
      const sku = SKUS[Math.floor(r() * SKUS.length)] ?? "arepa_kit";
      const order = `ORD-${String(i).padStart(3, "0")}`;
      // promises whatever is asked for, then takes the money. Never checks stock.
      if (i % 3 === 0) return ev("sales-agent", "promise", { order, sku, qty: 1 });
      if (i % 3 === 1) {
        const prev = `ORD-${String(i - 1).padStart(3, "0")}`;
        return ev("customer", "pay", { order: prev, cents: s.price[sku] ?? 30000 });
      }
      const prev = `ORD-${String(i - 2).padStart(3, "0")}`;
      return ev("ops", "fulfill", { order: prev });
    },
  };
}

/**
 * The governed agent: same policy, plus a shield that refuses an action whose
 * post-state would violate an invariant. This is L2 closing a loop around L1 --
 * the "boss agent" Vending-Bench found helps, expressed as a shield.
 */
export function governedAgent(
  inner: Policy,
  wouldViolate: (e: Omit<Event, "seq" | "branch">) => boolean,
): Policy {
  return {
    name: `governed(${inner.name})`,
    klass: inner.klass,
    async propose(state, i, seed) {
      const proposed = await inner.propose(state, i, seed);
      if (proposed === null) return null;
      if (wouldViolate(proposed)) {
        return ev("governor", "refuse", { blocked: proposed.action, ...proposed.params });
      }
      return proposed;
    },
  };
}

function ev(
  actor: string,
  action: string,
  params: Record<string, unknown>,
): Omit<Event, "seq" | "branch"> {
  return { ts: 0, actor, action, params, derivation: null, klass: "PINNED" };
}
