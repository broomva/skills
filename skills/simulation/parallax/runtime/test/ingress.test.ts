import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { mkdtempSync, realpathSync, rmSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { parseArgs, runCli } from "../src/cli";
import { proposeOntology } from "../src/core/ontology";

/**
 * The `business-data` ingress.
 *
 * This file exists because the ingress had TWO tests, both reaching it through
 * the hub, and one of those only asserted that omitting `tables` is a typed
 * error. The consequence was measurable: changing `columns` from `string[]` to
 * an array of objects -- a breaking change to a shape three surfaces speak --
 * left the suite 203-green. A suite that does not notice a breaking change to a
 * contract was not testing that contract.
 *
 * So the defects this ingress shipped are pinned here as tests, phrased as the
 * behaviour rather than the implementation:
 *
 *   1. `columns` was announced as required, never checked, then never read.
 *   2. Every table proposed ZERO rows, so forty records and none produced a
 *      byte-identical proposal.
 *   3. Every column was born untyped, so every table raised a blocking question
 *      the proposer had the information to answer.
 */

const observedString = { type: "string", origin: "observed" } as const;

describe("business-data: the boundary enforces what its message claimed", () => {
  test("a table with no columns is refused", () => {
    // The boundary said "needs at least one table with its columns" and only
    // counted tables, so this returned ok. A message describing a check that
    // does not exist is read as a guarantee.
    const r = proposeOntology({
      kind: "business-data",
      tables: [{ name: "leads", columns: [] }],
    });
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error.code).toBe("COLUMNS_REQUIRED");
      expect(r.error.detail).toMatchObject({ table: "leads" });
    }
  });

  test("no tables at all is still SOURCE_EMPTY, not the new code", () => {
    // Guards against the new check swallowing the older, different condition.
    const r = proposeOntology({ kind: "business-data", tables: [] });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("SOURCE_EMPTY");
  });

  test("a row count that is not a whole number >= 0 is refused", () => {
    for (const rowCount of [-1, 1.5, Number.NaN]) {
      const r = proposeOntology({
        kind: "business-data",
        tables: [{ name: "leads", columns: [{ name: "company" }], rowCount }],
      });
      expect(r.ok, `rowCount ${rowCount} should be refused`).toBe(false);
      if (!r.ok) expect(r.error.code).toBe("INVALID_ROW_COUNT");
    }
  });

  test("claiming rows without saying where they came from is refused", () => {
    const r = proposeOntology({
      kind: "business-data",
      tables: [
        {
          name: "leads",
          rowCount: 40,
          columns: [
            { name: "company", type: "string" },
            { name: "nit", ...observedString },
          ],
        },
      ],
    });
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error.code).toBe("ORIGIN_REQUIRED");
      // Names the offenders, so the caller does not have to diff two lists.
      expect(r.error.detail).toMatchObject({ table: "leads", columns: ["company"] });
    }
  });

  test("a schema with NO row count needs no origins", () => {
    // Describing a shape is not claiming knowledge of the world, so this stays
    // cheap to write. The gate is on the claim, not on the description.
    const r = proposeOntology({
      kind: "business-data",
      tables: [{ name: "leads", columns: [{ name: "company", type: "string" }] }],
    });
    expect(r.ok).toBe(true);
  });

  test("rowCount 0 is a claim about an empty table, and needs no origins", () => {
    // Zero rows is a legitimate, terminal answer -- and there is nothing whose
    // provenance could be stated. Refusing it would make "we found nothing"
    // unrepresentable, which is the failure mode this rule exists to prevent.
    const r = proposeOntology({
      kind: "business-data",
      tables: [{ name: "leads", columns: [{ name: "company", type: "string" }], rowCount: 0 }],
    });
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.initial.leads_rows).toBe(0);
  });
});

describe("business-data: the proposal reflects what was supplied", () => {
  test("the row count reaches the proposal", () => {
    const r = proposeOntology({
      kind: "business-data",
      tables: [{ name: "leads", columns: [{ name: "company", ...observedString }], rowCount: 40 }],
    });
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.initial.leads_rows).toBe(40);
  });

  test("forty rows and zero rows are DIFFERENT proposals", () => {
    // The headline defect, stated as the thing a human would notice: the accept
    // gate showed the same document either way and asked someone to sign it.
    const of = (rowCount: number) =>
      proposeOntology({
        kind: "business-data",
        tables: [{ name: "leads", columns: [{ name: "company", ...observedString }], rowCount }],
      });
    const empty = of(0);
    const full = of(40);
    expect(empty.ok && full.ok).toBe(true);
    if (empty.ok && full.ok) {
      expect(full.value.id).not.toBe(empty.value.id);
      expect(full.value.initial.leads_rows).toBe(40);
      expect(empty.value.initial.leads_rows).toBe(0);
    }
  });

  test("each column becomes a typed slot, and says what it was read from", () => {
    const r = proposeOntology({
      kind: "business-data",
      tables: [
        {
          name: "leads",
          rowCount: 3,
          columns: [
            { name: "company", type: "string", origin: "observed" },
            { name: "score", type: "number", origin: "simulated" },
          ],
        },
      ],
    });
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.value.initial["leads.company"]).toBe("");
    expect(r.value.initial["leads.score"]).toBe(0);
    const from = (slot: string) => r.value.evidence.find((e) => e.slot === slot)?.from ?? "";
    // Provenance is visible in the evidence a human reads, not only in a type.
    expect(from("state.leads.company")).toContain("observed");
    expect(from("state.leads.score")).toContain("simulated");
  });

  test("an undeclared column is left null and raises a blocking question", () => {
    // Not coerced to "". A slot that silently became empty-string would RUN,
    // and running on a guess is the thing this product refuses.
    //
    // `null` rather than `undefined` because the slot has to survive
    // JSON.stringify, which deletes undefined-valued keys outright -- see the
    // round-trip test in the identity block.
    const r = proposeOntology({
      kind: "business-data",
      tables: [{ name: "leads", columns: [{ name: "company" }] }],
    });
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.value.initial["leads.company"]).toBeNull();
    const q = r.value.openQuestions.find((x) => x.slot === "state.leads.company");
    expect(q?.blocking).toBe(true);
  });

  test("supplying a row count answers the units question instead of asking it", () => {
    // The proposer used to ask "what unit is n?" for every table, including
    // tables whose supplier had already said n counts rows.
    const withRows = proposeOntology({
      kind: "business-data",
      tables: [{ name: "leads", columns: [{ name: "company", ...observedString }], rowCount: 7 }],
    });
    const without = proposeOntology({
      kind: "business-data",
      tables: [{ name: "leads", columns: [{ name: "company", type: "string" }] }],
    });
    const unitQ = (r: typeof withRows) =>
      r.ok ? r.value.openQuestions.filter((q) => q.slot === "action.insert_leads.n") : [];
    expect(unitQ(withRows)).toHaveLength(0);
    expect(unitQ(without)).toHaveLength(1);
  });
});

describe("business-data: identity and contradictions", () => {
  const withOrigin = (origin: "observed" | "simulated") =>
    proposeOntology({
      kind: "business-data",
      tables: [
        { name: "leads", rowCount: 2, columns: [{ name: "company", type: "string", origin }] },
      ],
    });

  test("observed and simulated proposals do NOT share an id", () => {
    // The id is what acceptance is keyed on. While it hashed only
    // {slug, initial, actions}, two proposals differing in that one word were
    // the same document to the gate -- so a human accepting "we read this" also
    // accepted "we guessed this". Widening what a proposal MEANS requires
    // widening what identifies it, in the same change.
    const o = withOrigin("observed");
    const s = withOrigin("simulated");
    expect(o.ok && s.ok).toBe(true);
    if (o.ok && s.ok) {
      expect(o.value.evidence).not.toEqual(s.value.evidence);
      expect(o.value.id).not.toBe(s.value.id);
    }
  });

  test("a duplicate column is refused, not merged", () => {
    // One slot cannot carry two provenances. Declared observed then simulated,
    // the renderer showed only the FIRST, so the contradicting line was
    // invisible and the flattering half won by document order.
    const r = proposeOntology({
      kind: "business-data",
      tables: [
        {
          name: "leads",
          rowCount: 1,
          columns: [
            { name: "company", type: "string", origin: "observed" },
            { name: "company", type: "string", origin: "simulated" },
          ],
        },
      ],
    });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("DUPLICATE_COLUMN");
  });

  test("two DIFFERENT columns that build the same slot are refused", () => {
    // Neither name is a duplicate: table `a` column `b.c`, and table `a.b`
    // column `c`. Both construct `a.b.c`. The duplicate-name checks cannot see
    // this, and without a check on the CONSTRUCTED key one slot carried two
    // evidence lines -- observed first, simulated second, and the renderer shows
    // the first.
    const r = proposeOntology({
      kind: "business-data",
      tables: [
        { name: "a", rowCount: 1, columns: [{ name: "b.c", type: "string", origin: "observed" }] },
        { name: "a.b", rowCount: 1, columns: [{ name: "c", type: "string", origin: "simulated" }] },
      ],
    });
    expect(r.ok).toBe(false);
    if (!r.ok) {
      expect(r.error.code).toBe("SLOT_COLLISION");
      expect(r.error.detail).toMatchObject({ slot: "a.b.c" });
    }
  });

  test("a duplicate table is refused", () => {
    const r = proposeOntology({
      kind: "business-data",
      tables: [
        { name: "leads", columns: [{ name: "a", type: "string" }] },
        { name: "leads", columns: [{ name: "b", type: "string" }] },
      ],
    });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("DUPLICATE_TABLE");
  });

  test("an untyped slot survives being written to disk", () => {
    // It was `undefined`, and JSON.stringify DELETES a key whose value is
    // undefined -- so the slot deliberately left untyped vanished on the way to
    // the pending file, and every later surface saw a proposal that had never
    // mentioned the column. The blocking question survived; the thing it asked
    // about did not.
    const r = proposeOntology({
      kind: "business-data",
      tables: [{ name: "leads", columns: [{ name: "untyped" }] }],
    });
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    const roundTripped = JSON.parse(JSON.stringify(r.value)) as {
      initial: Record<string, unknown>;
    };
    expect(Object.hasOwn(roundTripped.initial, "leads.untyped")).toBe(true);
    expect(roundTripped.initial["leads.untyped"]).toBeNull();
  });

  test("the evidence line does not call a manufactured placeholder a reading", () => {
    // `leads.company = ""` is a placeholder this runtime invented. Writing
    // "-- observed" beside it asserted we had read an empty string we had not.
    const r = withOrigin("observed");
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    const from = r.value.evidence.find((e) => e.slot === "state.leads.company")?.from ?? "";
    expect(from).toContain("placeholder");
    expect(from).toContain("supplier reports its values observed");
  });
});

describe("business-data: the CLI grammar", () => {
  // `runCli` writes pending proposals into `.parallax/` in the CURRENT directory.
  // Left alone, this suite wrote them into the repository -- gitignored, so
  // invisible, but it made the tests stateful across runs and made them fail
  // outright in a read-only checkout. Each test gets its own directory instead.
  let cwd = "";
  let scratch = "";
  beforeEach(() => {
    cwd = process.cwd();
    scratch = realpathSync(mkdtempSync(join(tmpdir(), "parallax-ingress-")));
    process.chdir(scratch);
  });
  afterEach(() => {
    process.chdir(cwd);
    rmSync(scratch, { recursive: true, force: true });
  });

  const propose = (table: string) => {
    const parsed = parseArgs(["propose", "--kind", "business-data", "--table", table, "--json"]);
    return parsed;
  };

  test("<name>:<col,col> parses as a schema", () => {
    expect(propose("leads:company,nit").ok).toBe(true);
  });

  test("<name>#<rows>:<col:type:origin> carries all three", async () => {
    // Driven through runCli rather than the parser alone, so the assertion
    // covers the path a person actually types.
    const out: string[] = [];
    const code = await runCli(
      [
        "propose",
        "--kind",
        "business-data",
        "--table",
        "leads#2:company:string:observed,score:number:simulated",
        "--json",
      ],
      { out: (t) => out.push(t), err: (t) => out.push(t) },
    );
    expect(code).toBe(0);
    const printed = JSON.parse(out.join("")) as {
      ok: boolean;
      value: { stateFields: Array<{ key: string; value: unknown; from: string }> };
    };
    expect(printed.ok).toBe(true);
    const field = (key: string) => printed.value.stateFields.find((f) => f.key === key);
    expect(field("leads_rows")?.value).toBe(2);
    expect(field("leads.score")?.value).toBe(0);
    // The provenance a human reads is on the line they read, not only in a type.
    expect(field("leads.company")?.from).toContain("observed");
    expect(field("leads.score")?.from).toContain("simulated");
  });

  test("a row count that is not digits is refused by the flag, not the core", async () => {
    const out: string[] = [];
    const code = await runCli(
      ["propose", "--kind", "business-data", "--table", "leads#many:company", "--json"],
      { out: (t) => out.push(t), err: (t) => out.push(t) },
    );
    expect(code).toBe(2);
    expect(out.join("")).toContain("BAD_FLAG_VALUE");
  });

  test("an unknown column type is refused rather than silently dropped", async () => {
    const out: string[] = [];
    const code = await runCli(
      ["propose", "--kind", "business-data", "--table", "leads:company:uuid", "--json"],
      { out: (t) => out.push(t), err: (t) => out.push(t) },
    );
    expect(code).toBe(2);
    expect(out.join("")).toContain("BAD_FLAG_VALUE");
  });

  test("an empty column between commas is refused, not skipped", async () => {
    // `leads:company,,nit` used to yield TWO columns and say nothing, so a typo
    // produced a table with a column missing and no way to notice. This file
    // already refuses an unknown flag for the same reason.
    const out: string[] = [];
    const code = await runCli(
      ["propose", "--kind", "business-data", "--table", "leads:company,,nit", "--json"],
      { out: (t) => out.push(t), err: (t) => out.push(t) },
    );
    expect(code).toBe(2);
    expect(out.join("")).toContain("empty column");
  });

  test("a fourth positional part is refused, not dropped", async () => {
    // `company:string:observed:GARBAGE` parsed happily and threw GARBAGE away.
    const out: string[] = [];
    const code = await runCli(
      [
        "propose",
        "--kind",
        "business-data",
        "--table",
        "leads#1:company:string:observed:GARBAGE",
        "--json",
      ],
      { out: (t) => out.push(t), err: (t) => out.push(t) },
    );
    expect(code).toBe(2);
    expect(out.join("")).toContain("BAD_FLAG_VALUE");
  });

  test("an origin CAN be given without a type, with an empty middle segment", () => {
    // `name::observed` is legal and meaningful: "I read this, but I could not
    // determine its type". The type question still blocks; the provenance is not
    // thrown away to keep the string tidy.
    const parsed = parseArgs([
      "propose",
      "--kind",
      "business-data",
      "--table",
      "leads#2:company::observed",
      "--json",
    ]);
    expect(parsed.ok).toBe(true);
  });

  test("a CLI-typed row count with no origins is refused by the CORE, not the flag", async () => {
    // The two layers do different jobs and this pins the split: the flag checks
    // grammar, `proposeOntology` checks whether the claim is legal. Both
    // surfaces inherit the second one, which is why it is not duplicated.
    const out: string[] = [];
    const code = await runCli(
      ["propose", "--kind", "business-data", "--table", "leads#5:company:string", "--json"],
      { out: (t) => out.push(t), err: (t) => out.push(t) },
    );
    expect(code).toBe(2);
    expect(out.join("")).toContain("ORIGIN_REQUIRED");
  });
});
