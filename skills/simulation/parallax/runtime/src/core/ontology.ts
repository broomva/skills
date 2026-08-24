import { readdirSync, statSync } from "node:fs";
import { basename, extname, join } from "node:path";
import type { Origin } from "./provenance";
import { fail, ok, type ParallaxError, type Result } from "./result";
import type { ActionSpec, InvariantSpec, State, TypeRecord } from "./types";

/**
 * A system arrives as data. You point Parallax at a context, it proposes an
 * ontology built from what is actually there, and a human accepts it before it
 * becomes active.
 *
 * The accept step is the product, not a formality. A proposal is a draft with
 * open questions attached; an ActiveOntology is a thing that has been looked at
 * by someone accountable. The type system enforces the difference: `activate`
 * is the only way to mint an ActiveOntology, and the brand is a module-private
 * symbol, so a caller cannot forge one by writing the object literal. A
 * structural `__brand: true` field would be forgeable by anyone who reads the
 * type definition, which makes it documentation rather than a gate.
 */

const ACCEPTED: unique symbol = Symbol("parallax.accepted");

export interface ActiveOntology {
  readonly [ACCEPTED]: true;
  readonly world: TypeRecord;
  readonly acceptedBy: string;
  readonly acceptedAt: number;
  /** Hash of the exact proposal that was accepted. Edits after this are a new proposal. */
  readonly proposalId: string;
}

/** The three context classes. Each is a different way of finding out what is there. */
export type ContextSource =
  | { kind: "filesystem"; root: string }
  /**
   * The tenant's own workspace. `root` defaults to process.cwd() and you should
   * almost always let it: the session is spawned with cwd already set to the
   * tenant directory, and the confinement keys off exactly that. A hardcoded
   * absolute path that disagrees with cwd by even a trailing component is
   * DENIED rather than redirected -- and a denied read surfaces as an empty
   * directory, so it looks like "the workspace has nothing in it" instead of
   * an error. Passing a derived path is the failure that does not announce
   * itself.
   */
  | { kind: "agent-workspace"; root?: string }
  | { kind: "business-data"; tables: TableSpec[] };

/**
 * What a column is declared to hold. Deliberately small: these four are what a
 * proposer can turn into a typed slot without guessing. An unrecognised type is
 * not coerced into `string` -- it stays unknown and raises a blocking question,
 * because a wrong type that runs is worse than a question that stops.
 */
export type ColumnType = "string" | "number" | "boolean" | "date";

export interface ColumnSpec {
  readonly name: string;
  /** Absent means "not declared", which is a blocking question, not a default. */
  readonly type?: ColumnType;
  /**
   * Where this column's VALUES came from. Absent is legal for a schema sketch
   * and illegal once `rowCount` claims rows exist -- see `TableSpec.rowCount`.
   *
   * This is on the column and not derived later because `provenance.ts` types
   * values at birth: there is no operator that adds provenance afterwards, so a
   * supplier that omits it has destroyed the distinction permanently.
   */
  readonly origin?: Origin;
}

export interface TableSpec {
  readonly name: string;
  readonly columns: ColumnSpec[];
  /**
   * How many rows the supplier actually has. Absent means "a schema, no data
   * yet" and proposes zero; present means the supplier is making a claim about
   * the world, and every column must then carry an `origin`. Claiming rows
   * without saying where they came from is refused at the boundary rather than
   * defaulted -- a default there is a lie with a safe-sounding name.
   */
  readonly rowCount?: number;
}

/** A question the proposer could not answer and a human must. */
export interface OpenQuestion {
  readonly slot: string;
  readonly question: string;
  /** Blocking questions prevent acceptance. Units are always blocking. */
  readonly blocking: boolean;
}

export interface OntologyProposal {
  readonly id: string;
  readonly source: ContextSource;
  readonly slug: string;
  readonly title: string;
  readonly initial: State;
  readonly actions: ActionSpec[];
  readonly invariants: InvariantSpec[];
  /** What in the context each proposed element was read from. */
  readonly evidence: Array<{ slot: string; from: string }>;
  readonly openQuestions: OpenQuestion[];
}

export type ProposeError = ParallaxError<
  | "SOURCE_UNREADABLE"
  | "SOURCE_EMPTY"
  | "UNSUPPORTED_SOURCE"
  | "DEGENERATE_CONTEXT"
  | "COLUMNS_REQUIRED"
  | "INVALID_ROW_COUNT"
  | "ORIGIN_REQUIRED"
>;

export type AcceptError = ParallaxError<
  "BLOCKING_QUESTIONS_OPEN" | "NO_TRANSITION" | "NO_INVARIANTS" | "NO_ACTIONS"
>;

export type OntologyAccessError = ParallaxError<"NOT_ACCEPTED">;

/**
 * Read a context and propose an ontology from what is in it.
 *
 * This is a heuristic and says so. It does not need to be right -- it needs to
 * be a starting point specific enough that a human correcting it is faster than
 * a human authoring it, and honest enough that every element says what it was
 * read from.
 */
export function proposeOntology(source: ContextSource): Result<OntologyProposal, ProposeError> {
  switch (source.kind) {
    case "filesystem":
    case "agent-workspace":
      return proposeFromDirectory(source);
    case "business-data":
      return proposeFromTables(source);
    default:
      return fail("UNSUPPORTED_SOURCE", `no proposer for source kind`, { source });
  }
}

function proposeFromDirectory(
  source: Extract<ContextSource, { kind: "filesystem" | "agent-workspace" }>,
): Result<OntologyProposal, ProposeError> {
  const root = source.root ?? process.cwd();
  let entries: string[];
  try {
    entries = readdirSync(root);
  } catch (e) {
    return fail("SOURCE_UNREADABLE", `cannot read ${root}`, {
      cause: e instanceof Error ? e.message : String(e),
    });
  }
  if (entries.length === 0) {
    return fail("SOURCE_EMPTY", `${root} has no entries to read an ontology from`);
  }

  const dirs: string[] = [];
  const byExt = new Map<string, number>();
  for (const name of entries) {
    if (name.startsWith(".")) continue;
    const full = join(root, name);
    let s: ReturnType<typeof statSync>;
    try {
      s = statSync(full);
    } catch {
      continue;
    }
    if (s.isDirectory()) dirs.push(name);
    else {
      const ext = extname(name) || "(none)";
      byExt.set(ext, (byExt.get(ext) ?? 0) + 1);
    }
  }

  const initial: State = {};
  const evidence: Array<{ slot: string; from: string }> = [];
  for (const d of dirs) {
    initial[`${d}_count`] = 0;
    evidence.push({ slot: `state.${d}_count`, from: `directory ${d}/` });
  }
  for (const [ext, n] of byExt) {
    const key = `files${ext.replace(/\W/g, "_")}`;
    initial[key] = n;
    evidence.push({ slot: `state.${key}`, from: `${n} file(s) with extension ${ext}` });
  }

  const actions: ActionSpec[] = dirs.map((d) => ({
    name: `add_to_${d}`,
    actor: "operator",
    params: { count: "number" },
  }));
  for (const a of actions)
    evidence.push({
      slot: `action.${a.name}`,
      from: `directory ${a.name.replace("add_to_", "")}/`,
    });

  // Every numeric param needs a unit and the proposer cannot invent one.
  // This fails closed: unanswered, it blocks acceptance.
  const openQuestions: OpenQuestion[] = actions.map((a) => ({
    slot: `action.${a.name}.count`,
    question: `What unit is "count" measured in for ${a.name}? Materialisation fails closed without it.`,
    blocking: true,
  }));
  openQuestions.push({
    slot: "invariants",
    question:
      "Which quantity here is conserved? A conservation invariant is the cheapest oracle available and this proposal has none.",
    blocking: false,
  });

  /**
   * Fail closed on a context that yielded nothing.
   *
   * The entries.length check above runs BEFORE dot entries are filtered, so a
   * directory holding only dot entries passes it and then produces a proposal
   * with no state, no actions and -- critically -- no blocking questions. Every
   * downstream gate is keyed on there being something to ask about, so an empty
   * proposal walks through all of them and mints an ontology recording that a
   * named human accepted a model of their own context, with zero human input.
   *
   * This is not a contrived input. A freshly provisioned tenant workspace
   * contains only `.claude`, so the empty reading IS the first-run path.
   */
  if (Object.keys(initial).length === 0 && actions.length === 0) {
    return fail(
      "DEGENERATE_CONTEXT",
      `nothing in ${root} could be read as state or actions; ${entries.length} entr${entries.length === 1 ? "y is" : "ies are"} present but all are hidden or unreadable`,
      { root, entriesSeen: entries.length, visibleEntries: dirs.length + byExt.size },
    );
  }

  const slug = basename(root) || "context";
  const proposal: OntologyProposal = {
    id: "",
    source,
    slug,
    title: `${slug} (proposed from ${source.kind})`,
    initial,
    actions,
    invariants: [],
    evidence,
    openQuestions,
  };
  return ok({ ...proposal, id: proposalId(proposal) });
}

/**
 * The empty value for a declared column type.
 *
 * `undefined` for an undeclared column is deliberate and is the whole point of
 * the blocking question raised beside it: an untyped slot that silently became
 * `""` would run, and running on a guess is what this product exists to refuse.
 */
function zeroFor(type: ColumnType | undefined): unknown {
  switch (type) {
    case "number":
      return 0;
    case "boolean":
      return false;
    case "string":
    case "date":
      return "";
    default:
      return undefined;
  }
}

function proposeFromTables(
  source: Extract<ContextSource, { kind: "business-data" }>,
): Result<OntologyProposal, ProposeError> {
  if (source.tables.length === 0) {
    return fail("SOURCE_EMPTY", "no tables supplied");
  }

  // Validated HERE, not per surface. The CLI, the tool surface and the hub all
  // reach the proposer through this function, so one check covers three
  // callers; a copy in each is three chances to drift. These are core codes and
  // propagate to every surface unchanged.
  for (const t of source.tables) {
    if (t.columns.length === 0) {
      // The boundary already SAID this -- "needs at least one table with its
      // columns" -- and then only counted tables. A message describing a check
      // that does not exist is worse than no message: it is read as a guarantee.
      return fail("COLUMNS_REQUIRED", `table ${t.name} has no columns`, { table: t.name });
    }
    if (t.rowCount !== undefined && (!Number.isInteger(t.rowCount) || t.rowCount < 0)) {
      return fail(
        "INVALID_ROW_COUNT",
        `table ${t.name} reports a row count that is not a whole number >= 0`,
        {
          table: t.name,
          given: t.rowCount,
        },
      );
    }
    if (t.rowCount !== undefined && t.rowCount > 0) {
      // Claiming rows is claiming knowledge of the world. `provenance.ts` types
      // values at birth and has no operator that adds provenance later, so a
      // supplier who omits it here has destroyed the distinction permanently --
      // and defaulting to `simulated` would be a lie with a safe-sounding name.
      const untagged = t.columns.filter((c) => c.origin === undefined).map((c) => c.name);
      if (untagged.length > 0) {
        return fail(
          "ORIGIN_REQUIRED",
          `table ${t.name} reports ${t.rowCount} row(s) but ${untagged.length} column(s) do not say whether their values were observed or simulated`,
          { table: t.name, columns: untagged },
        );
      }
    }
  }
  const initial: State = {};
  const evidence: Array<{ slot: string; from: string }> = [];
  const actions: ActionSpec[] = [];
  const openQuestions: OpenQuestion[] = [];

  for (const t of source.tables) {
    // The row count is the supplier's, not a placeholder. This used to be a
    // hardcoded 0, which meant forty judged records and an empty table produced
    // a byte-identical proposal -- so the accept gate showed a human the same
    // thing in both cases and asked them to sign it.
    const rows = t.rowCount ?? 0;
    initial[`${t.name}_rows`] = rows;
    evidence.push({
      slot: `state.${t.name}_rows`,
      from:
        t.rowCount === undefined
          ? `table ${t.name} (schema only -- no row count supplied)`
          : `table ${t.name}, ${rows} row(s) reported by the supplier`,
    });

    // One slot per column. `columns` was required at the boundary and then
    // discarded here; an interface that demands evidence it does not use is a
    // poor look for this product specifically.
    for (const c of t.columns) {
      const slot = `${t.name}.${c.name}`;
      initial[slot] = zeroFor(c.type);
      evidence.push({
        slot: `state.${slot}`,
        from: `column ${c.name} of ${t.name}${c.type ? ` (${c.type})` : ""}${
          c.origin ? ` -- ${c.origin}` : ""
        }`,
      });
      if (c.type === undefined) {
        openQuestions.push({
          slot: `state.${slot}`,
          question: `What type is column "${c.name}" of ${t.name}? Declared types are string, number, boolean, date. It is left untyped rather than guessed.`,
          blocking: true,
        });
      }
    }

    actions.push({ name: `insert_${t.name}`, actor: "system", params: { n: "number" } });
    evidence.push({ slot: `action.insert_${t.name}`, from: `table ${t.name}` });

    // Ask only what cannot be inferred. A supplier that reported a row count has
    // already told us `n` counts rows; asking anyway is the proposer making a
    // human answer a question it held the answer to.
    if (t.rowCount === undefined) {
      openQuestions.push({
        slot: `action.insert_${t.name}.n`,
        question: `What unit is "n" for insert_${t.name}? Rows, items, or currency? Supply a row count on the table and this answers itself.`,
        blocking: true,
      });
    }
  }

  const proposal: OntologyProposal = {
    id: "",
    source,
    slug: "business-data",
    title: "business data (proposed)",
    initial,
    actions,
    invariants: [],
    evidence,
    openQuestions,
  };
  return ok({ ...proposal, id: proposalId(proposal) });
}

function proposalId(p: Omit<OntologyProposal, "id">): string {
  // Imported lazily to keep this module readable; hash.ts owns canonicalisation.
  const { h } = require("./hash") as typeof import("./hash");
  return h({ slug: p.slug, initial: p.initial, actions: p.actions });
}

/**
 * Accept a proposal, optionally with the human's corrections applied, and mint
 * the ActiveOntology that operators will run against.
 *
 * Refuses while any blocking question is open. That is the point of the gate:
 * an ontology nobody answered the hard questions about should not be able to
 * produce numbers that look authoritative.
 */
export function activate(
  proposal: OntologyProposal,
  corrections: {
    transition: TypeRecord["transition"];
    invariants?: InvariantSpec[];
    answered?: string[];
    acceptedBy: string;
    at: number;
  },
): Result<ActiveOntology, AcceptError> {
  const answered = new Set(corrections.answered ?? []);
  const stillOpen = proposal.openQuestions.filter((q) => q.blocking && !answered.has(q.slot));
  if (stillOpen.length > 0) {
    return fail(
      "BLOCKING_QUESTIONS_OPEN",
      `${stillOpen.length} blocking question(s) must be answered before this ontology can run`,
      { slots: stillOpen.map((q) => q.slot) },
    );
  }
  if (typeof corrections.transition !== "function") {
    return fail("NO_TRANSITION", "a domain must supply a transition; it is code, never a model");
  }
  if (proposal.actions.length === 0) {
    return fail(
      "NO_ACTIONS",
      "this domain has an empty action space, so nothing can happen in it and there is nothing to simulate",
      { slug: proposal.slug },
    );
  }
  const invariants = corrections.invariants ?? proposal.invariants;
  if (invariants.length === 0) {
    return fail(
      "NO_INVARIANTS",
      "a domain with no invariants has no verifier, and an unverifiable simulation is the thing this system exists to refuse",
    );
  }

  const world: TypeRecord = {
    slug: proposal.slug,
    title: proposal.title,
    initial: proposal.initial,
    actions: proposal.actions,
    invariants,
    transition: corrections.transition,
  };
  return ok({
    [ACCEPTED]: true,
    world,
    acceptedBy: corrections.acceptedBy,
    acceptedAt: corrections.at,
    proposalId: proposal.id,
  });
}

/**
 * Read the world out of an accepted ontology. The only supported way in.
 *
 * The symbol brand is checked HERE, at runtime, not only by the type system.
 * A compile-time-only brand is documentation: `as any`, plain JS, or a value
 * crossing a deserialisation boundary all walk straight past it. The gate has
 * to execute to be a gate -- the same reason a reproducibility class that is
 * declared rather than verified is decoration.
 */
export function worldOf(active: ActiveOntology): Result<TypeRecord, OntologyAccessError> {
  if (!isActive(active)) {
    return fail(
      "NOT_ACCEPTED",
      "this ontology was never accepted by a human; propose it and accept it before running operators against it",
    );
  }
  return ok(active.world);
}

/** Runtime predicate for the accept brand. Unforgeable: ACCEPTED is module-private. */
export function isActive(value: unknown): value is ActiveOntology {
  return (
    typeof value === "object" &&
    value !== null &&
    (value as Record<PropertyKey, unknown>)[ACCEPTED] === true &&
    typeof (value as ActiveOntology).world === "object"
  );
}
