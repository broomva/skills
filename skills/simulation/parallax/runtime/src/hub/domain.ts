import { governedAgent } from "../actors/policies";
import type { EventLog } from "../core/log";
import type { OntologyProposal } from "../core/ontology";
import type { Policy } from "../core/ops";
import { check, observe, step } from "../core/ops";
import type { ActionSpec, Event, InvariantSpec, State, TypeRecord } from "../core/types";

/**
 * The executable half of an accepted ontology, supplied by the server.
 *
 * `activate` refuses a proposal that has no transition and no invariants,
 * because both are CODE and a proposer cannot write code from a directory
 * listing. So something has to supply them at accept time, and over HTTP that
 * something must be the server.
 *
 * This is a security boundary, not a convenience. The obvious alternative --
 * let the accept request name a module to import -- turns `POST
 * /api/ontology/accept` into remote code execution behind a JSON body. The
 * binder below is chosen by the SHAPE of the proposal and takes nothing from
 * the request. If a future hub grows a second domain, it grows another entry in
 * this file, never a path in a payload.
 *
 * What it binds is deliberately narrow: every proposer in `src/core/ontology.ts`
 * emits the same census shape -- counters read from a context, and actions that
 * move one counter each. That is a real model of a real thing, and it is the
 * only model that follows from what the proposer actually saw. Anything richer
 * would be the hub inventing a world the human never accepted.
 */

/**
 * The one state field the executable model adds beyond the accepted proposal.
 *
 * A conservation invariant needs two quantities that are updated independently,
 * so that agreement between them is evidence rather than a tautology. The
 * proposal supplies one (the counters); this ledger is the other. It is
 * namespaced so it can never collide with a field read from the context, and
 * the accept confirmation says out loud that it was added -- an executable
 * model that quietly carries state the human never saw is the failure this
 * product exists to make visible, and it is reachable from inside the product.
 */
export const LEDGER_KEY = "parallax_applied_total";

/** Which state key an action moves, and which of its params carries the amount. */
interface Target {
  readonly action: string;
  readonly param: string;
  readonly key: string;
}

export interface DomainBinding {
  /** Stable name of the executable domain. Part of the ontology id. */
  readonly name: string;
  readonly transition: TypeRecord["transition"];
  readonly invariants: InvariantSpec[];
  /** A fresh policy instance per run. Policies are stateless here, but sharing one is a habit worth not forming. */
  readonly policy: () => Policy;
  readonly targets: readonly Target[];
}

/**
 * Map a proposal's actions onto the state keys they move.
 *
 * The pairing is derived from the proposer's own naming, which is the only
 * evidence available: `add_to_src` moves `src_count`, `insert_orders` moves
 * `orders_rows`. An action whose target is not present in the proposed state is
 * dropped rather than guessed -- a transition that writes a field nobody
 * accepted is exactly what the accept gate exists to prevent.
 */
function targetsOf(proposal: OntologyProposal): Target[] {
  const out: Target[] = [];
  for (const a of proposal.actions) {
    const param = numericParam(a);
    if (param === null) continue;
    const key = targetKey(a.name);
    if (key === null) continue;
    if (!(key in proposal.initial)) continue;
    out.push({ action: a.name, param, key });
  }
  return out;
}

function numericParam(a: ActionSpec): string | null {
  for (const [name, type] of Object.entries(a.params)) if (type === "number") return name;
  return null;
}

function targetKey(action: string): string | null {
  if (action.startsWith("add_to_")) return `${action.slice("add_to_".length)}_count`;
  if (action.startsWith("insert_")) return `${action.slice("insert_".length)}_rows`;
  return null;
}

/**
 * The census transition. Code, and never a model: an LLM does not compute a
 * ledger. Pure over (state, event) -- it clones, applies one delta, and updates
 * the ledger by the same delta, so the two quantities can only agree if both
 * updates happened.
 */
function censusTransition(targets: readonly Target[]): TypeRecord["transition"] {
  const byAction = new Map(targets.map((t) => [t.action, t]));
  return (state: State, e: Event): State => {
    const t = byAction.get(e.action);
    if (t === undefined) return state;
    const raw = (e.params as Record<string, unknown>)[t.param];
    const delta = typeof raw === "number" && Number.isFinite(raw) ? raw : 0;
    const s = structuredClone(state) as Record<string, unknown>;
    const before = typeof s[t.key] === "number" ? (s[t.key] as number) : 0;
    const ledger = typeof s[LEDGER_KEY] === "number" ? (s[LEDGER_KEY] as number) : 0;
    s[t.key] = before + delta;
    s[LEDGER_KEY] = ledger + delta;
    return s;
  };
}

function censusInvariants(targets: readonly Target[]): InvariantSpec[] {
  const counted = new Set(targets.map((t) => t.key));
  return [
    {
      name: "counts_nonneg",
      kind: "conservation",
      /**
       * A census counts things that exist. Nothing in the proposal says the
       * amount on an action has to be positive -- the proposer asked what unit
       * `count` is measured in and could not think to ask about its sign -- so
       * a policy is free to propose a negative one and this is what catches it.
       */
      check: (st) => {
        const bad = Object.entries(st).filter(
          ([, v]) => typeof v === "number" && Number.isFinite(v) && v < 0,
        );
        return bad.length === 0
          ? null
          : `negative count: ${bad.map(([k, v]) => `${k}:${String(v)}`).join(", ")}`;
      },
    },
    {
      name: "ledger_matches_counts",
      kind: "conservation",
      /**
       * The accounting identity. Every counter the actions can move, summed,
       * must equal the ledger -- and the ledger is updated by a separate line
       * of the transition. A transition that drops an update, double-applies
       * one, or writes to the wrong key breaks this and nothing else does. It
       * is the cheapest oracle available on a domain this thin, which is the
       * same argument the storefront's `cash_conserved` makes.
       */
      check: (st) => {
        let sum = 0;
        for (const key of counted) {
          const v = (st as Record<string, unknown>)[key];
          if (typeof v === "number" && Number.isFinite(v)) sum += v;
        }
        const raw = (st as Record<string, unknown>)[LEDGER_KEY];
        const ledger = typeof raw === "number" ? raw : 0;
        return sum === ledger ? null : `counters sum to ${sum} but the ledger says ${ledger}`;
      },
    },
  ];
}

/**
 * Seeded PRNG. Determinism is the product, so randomness is never ambient.
 * The same generator lives in `src/actors/policies.ts`; it is not exported
 * there, and copying eight lines is cheaper than widening that module's
 * surface for a demo actor.
 */
function rng(seed: number): () => number {
  let a = seed >>> 0;
  return () => {
    a = (a + 0x6d2b79f5) >>> 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

/**
 * The candidate decision the hub rolls forward.
 *
 * A scripted, seeded actor. It is not a model of how anyone behaves and the
 * receipt tags every step it produces `simulated`; its only job is to move the
 * counters far enough to find out whether the invariants can be broken. It
 * proposes only actions the human accepted, in the order the human saw them.
 *
 * PINNED because it is seeded and pure -- and the class it declares is still
 * measured before it is believed, by `certifyPolicy` in the run path.
 */
function censusPolicy(actions: readonly ActionSpec[], targets: readonly Target[]): Policy {
  const usable = actions.filter((a) => targets.some((t) => t.action === a.name));
  return {
    name: "census-agent",
    klass: "PINNED",
    async propose(_state: State, i: number, seed: number) {
      const a = usable[i % usable.length];
      if (a === undefined) return null;
      const r = rng(seed);
      // -3..+5. Centred above zero so a run mostly grows, with room to go
      // under -- which is the only way the non-negativity invariant is ever
      // exercised rather than merely asserted.
      const delta = Math.floor(r() * 9) - 3;
      const params: Record<string, unknown> = {};
      for (const [name, type] of Object.entries(a.params)) {
        if (type === "number") params[name] = delta;
        else if (type === "boolean") params[name] = i % 2 === 0;
        else params[name] = `${a.name}-${String(i)}`;
      }
      return { ts: 0, actor: a.actor, action: a.name, params, derivation: null, klass: "PINNED" };
    },
  };
}

/** Bind the executable half. Chosen by the proposal's shape; nothing comes from the request. */
export function bindDomain(proposal: OntologyProposal): DomainBinding {
  const targets = targetsOf(proposal);
  return {
    name: "census/v1",
    transition: censusTransition(targets),
    invariants: censusInvariants(targets),
    policy: () => censusPolicy(proposal.actions, targets),
    targets,
  };
}

/**
 * The governor: refuse any action whose post-state would violate an invariant.
 *
 * Identical in shape to the shield in `src/demo.ts` -- it probes the transition
 * one step ahead and lets `check` decide, so the governor never holds an
 * opinion of its own about what is safe.
 */
export function shieldedPolicy(
  world: TypeRecord,
  log: EventLog,
  branch: string,
  inner: Policy,
): Policy {
  const wouldViolate = (e: Omit<Event, "seq" | "branch">): boolean => {
    const probe = step(world, observe(world, log, branch), { ...e, seq: -1, branch });
    return check(world, probe, -1).length > 0;
  };
  return governedAgent(inner, wouldViolate);
}
