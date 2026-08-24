import { describe, expect, test } from "bun:test";
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

  test("an undeclared column is left undefined and raises a blocking question", () => {
    // Not coerced to "". A slot that silently became empty-string would RUN,
    // and running on a guess is the thing this product refuses.
    const r = proposeOntology({
      kind: "business-data",
      tables: [{ name: "leads", columns: [{ name: "company" }] }],
    });
    expect(r.ok).toBe(true);
    if (!r.ok) return;
    expect(r.value.initial["leads.company"]).toBeUndefined();
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

describe("business-data: the CLI grammar", () => {
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
