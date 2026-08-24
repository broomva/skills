import type { Klass } from "./hash";

/** One appended fact. The log of these is the only truth in the system. */
export interface Event {
  seq: number;
  ts: number;
  branch: string;
  actor: string;
  action: string;
  params: Record<string, unknown>;
  /** set when this event came out of a model call; null for scripted/real events */
  derivation: string | null;
  klass: Klass;
}

export type State = Record<string, unknown>;

export interface Violation {
  invariant: string;
  message: string;
  seq: number;
}

/**
 * The five slots. A domain is DATA; the runtime never changes.
 * `transition` and `invariants` are code by design -- an LLM never computes a
 * ledger and never judges whether an invariant held.
 */
export interface TypeRecord {
  slug: string;
  title: string;
  initial: State;
  actions: ActionSpec[];
  transition: (state: State, e: Event) => State;
  invariants: InvariantSpec[];
}

export interface ActionSpec {
  name: string;
  actor: string;
  params: Record<string, "string" | "number" | "boolean">;
  /** unit is mandatory for numeric params; materialisation fails closed without it */
  units?: Record<string, string>;
}

export interface InvariantSpec {
  name: string;
  /** returns null when it holds, else a human-readable reason */
  check: (state: State) => string | null;
  /** conservation invariants are the free oracle -- cheap, domain-general, non-gameable */
  kind: "conservation" | "safety" | "policy";
}
