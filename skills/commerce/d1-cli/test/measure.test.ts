import { describe, expect, test } from "bun:test";
import {
  formatUnitPrice,
  parseUnitSize,
  readPackEvidence,
  resolvePackSize,
  unitPrice,
} from "../src/measure.ts";
import { formatCOP } from "../src/money.ts";

describe("parseUnitSize", () => {
  test("grams normalize to kg", () => {
    expect(parseUnitSize("Gr", "500")).toEqual({ measure: "kg", amount: 0.5 });
    expect(parseUnitSize("g", "2000")).toEqual({ measure: "kg", amount: 2 });
  });

  test("millilitres normalize to litres", () => {
    expect(parseUnitSize("Ml", "900")).toEqual({ measure: "L", amount: 0.9 });
    expect(parseUnitSize("cc", "1500")).toEqual({ measure: "L", amount: 1.5 });
  });

  test("case does not matter — D1 is inconsistent about it", () => {
    expect(parseUnitSize("GR", "500")).toEqual(parseUnitSize("gr", "500"));
  });

  test("a Colombian thousands separator is not a decimal point", () => {
    // "1.000 G" is one kilogram, not one gram. Reading it as 1 would report a
    // price per kg that is 1000x too high and rank it last.
    expect(parseUnitSize("Gr", "1.000")).toEqual({ measure: "kg", amount: 1 });
  });

  test("a decimal comma parses", () => {
    expect(parseUnitSize("Kg", "1,5")).toEqual({ measure: "kg", amount: 1.5 });
  });

  test("unknown or missing data yields undefined, never a guess", () => {
    // A fabricated size produces a confidently wrong $/kg, which is worse than
    // admitting the comparison cannot be made.
    expect(parseUnitSize(undefined, "500")).toBeUndefined();
    expect(parseUnitSize("Gr", undefined)).toBeUndefined();
    expect(parseUnitSize("furlong", "3")).toBeUndefined();
    expect(parseUnitSize("Gr", "0")).toBeUndefined();
    expect(parseUnitSize("Gr", "abc")).toBeUndefined();
  });
});

describe("unitPrice", () => {
  test("reproduces the ranking inversion this feature exists for", () => {
    // Measured live. Ranking by pack price puts the 500 g bag first; by value
    // it is third, and the real winner is a pack three times the price.
    const cheapPack = unitPrice(155_000, parseUnitSize("Gr", "500")); // $1,550
    const bestValue = unitPrice(555_000, parseUnitSize("Gr", "2000")); // $5,550
    expect(cheapPack).toBe(310_000); // $3,100/kg
    expect(bestValue).toBe(277_500); // $2,775/kg
    expect(bestValue ?? 0).toBeLessThan(cheapPack ?? 0);
    // ...while costing more per pack, which is exactly the trap.
    expect(555_000).toBeGreaterThan(155_000);
  });

  test("is undefined when the size is unknown", () => {
    expect(unitPrice(100_000, undefined)).toBeUndefined();
  });

  test("formats with the measure attached", () => {
    const p = unitPrice(555_000, parseUnitSize("Gr", "2000"));
    expect(formatUnitPrice(formatCOP(p ?? 0), "kg")).toBe("$ 2.775/kg");
  });
});

// ---------------------------------------------------------------------------
// Multipacks
// ---------------------------------------------------------------------------

/**
 * Verbatim fragments from D1's live descriptions on 2026-08-03. Paraphrasing
 * them would test the paraphrase: the whole question is whether the shapes D1
 * actually writes are recognized.
 */
const DESC = {
  // Declares ONE item's size. Pack holds 6 x 200 mL = 1.2 L.
  refrescos718: "<li><strong>Contenido Neto:</strong> 6 unidades de 200 mL cada una</li>",
  // Declares ONE item's size, with the count in a separate parenthetical.
  quesoPera510: "<li><strong>Peso:</strong> 114 g por unidad (3 unidades por paquete)</li>",
  // Declares the PACK TOTAL, and mentions the per-item size WITHOUT a count.
  leche897: "<li><strong>Peso:</strong> 600 mL (200 mL por unidad)</li>",
  // Declares the pack total, nothing else.
  tostada738: "<li><strong>Peso:</strong> 150 g</li>",
  // Pack total with a count parenthetical — 15 g is the total, not per bag.
  infusion584: "<li><strong>ContenidoNeto:</strong> 15 g (10 bolsitas)</li>",
  tortilla956: "<li><strong>Cantidad:</strong> 580 g (8 unidades)</li>",
} as const;

describe("readPackEvidence", () => {
  test("reads the count-and-size-in-one-sentence form", () => {
    expect(readPackEvidence(DESC.refrescos718)).toEqual({
      perItem: { measure: "L", amount: 0.2 },
      count: 6,
    });
  });

  test("reads the size-here-count-there form", () => {
    expect(readPackEvidence(DESC.quesoPera510)).toEqual({
      perItem: { measure: "kg", amount: 0.114 },
      count: 3,
    });
  });

  test("a per-item size with NO count is not evidence", () => {
    // SKU 897 is the example the bug report was filed on. Its description says
    // "600 mL (200 mL por unidad)" — the 600 is already the pack. Without a
    // count there is no pack total to compute, and guessing one from the "3 UN"
    // in the name is the heuristic that would corrupt the 44 correct products.
    expect(readPackEvidence(DESC.leche897)).toBeUndefined();
  });

  test("a plain pack total is not evidence", () => {
    expect(readPackEvidence(DESC.tostada738)).toBeUndefined();
    expect(readPackEvidence(DESC.infusion584)).toBeUndefined();
    expect(readPackEvidence(DESC.tortilla956)).toBeUndefined();
  });

  test("absent or unparseable descriptions yield undefined", () => {
    expect(readPackEvidence(undefined)).toBeUndefined();
    expect(readPackEvidence("")).toBeUndefined();
    expect(readPackEvidence("<p>Delicioso producto colombiano.</p>")).toBeUndefined();
    // A count of one is not a multipack. Both phrasings use the SINGULAR noun,
    // which is the point: the earlier `unidades?` pattern did not match
    // "unidad" at all, so this assertion passed without ever reaching the
    // count guard it is here to pin.
    expect(readPackEvidence("Contenido: 1 unidad de 500 g")).toBeUndefined();
    expect(readPackEvidence("Contenido: 1 sobre de 25 g")).toBeUndefined();
    expect(readPackEvidence("Peso: 500 g por unidad (1 unidad por paquete)")).toBeUndefined();
  });
});

describe("resolvePackSize", () => {
  test("corrects a PUM that describes one item — SKU 718", () => {
    // $5,490 for 6 x 200 mL. Declared as 200 ml, so the CLI reported
    // $ 27.450/L for juice that actually costs $ 4.575/L, and ranked it last.
    const declared = parseUnitSize("Ml", "200");
    const size = resolvePackSize(declared, readPackEvidence(DESC.refrescos718));
    expect(size).toEqual({ measure: "L", amount: 1.2 });
    expect(unitPrice(549_000, size)).toBe(457_500);
    expect(unitPrice(549_000, declared)).toBe(2_745_000); // what it used to say
  });

  test("corrects the separate-count form — SKU 510", () => {
    const size = resolvePackSize(parseUnitSize("Gr", "114"), readPackEvidence(DESC.quesoPera510));
    expect(size?.measure).toBe("kg");
    expect(size?.amount).toBeCloseTo(0.342, 6);
  });

  test("leaves the pack total alone — the 44-product majority", () => {
    // The census found 44 of 46 decidable multipacks already declare the pack.
    // Any change here is a regression against the common case.
    const leche = parseUnitSize("Ml", "600");
    expect(resolvePackSize(leche, readPackEvidence(DESC.leche897))).toEqual(leche);
    const tostada = parseUnitSize("Gr", "150");
    expect(resolvePackSize(tostada, readPackEvidence(DESC.tostada738))).toEqual(tostada);
    const tortilla = parseUnitSize("Gr", "580");
    expect(resolvePackSize(tortilla, readPackEvidence(DESC.tortilla956))).toEqual(tortilla);
  });

  test("does not fire when the declared value is already the pack total", () => {
    // Same evidence as 718, but a PUM that already states 1.2 L. Multiplying
    // again would report 7.2 L and understate the price sixfold.
    const declared = { measure: "L", amount: 1.2 } as const;
    const evidence = readPackEvidence(DESC.refrescos718);
    expect(resolvePackSize(declared, evidence)).toEqual(declared);
  });

  test("does not cross measures", () => {
    // A weight PUM against a volume statement is not a comparison.
    const declared = parseUnitSize("Gr", "200");
    expect(resolvePackSize(declared, readPackEvidence(DESC.refrescos718))).toEqual(declared);
  });

  test("matching neither the item nor the pack changes nothing", () => {
    const declared = parseUnitSize("Ml", "750");
    expect(resolvePackSize(declared, readPackEvidence(DESC.refrescos718))).toEqual(declared);
  });

  test("passes undefined through rather than inventing a size", () => {
    expect(resolvePackSize(undefined, readPackEvidence(DESC.refrescos718))).toBeUndefined();
    const declared = parseUnitSize("Ml", "200");
    expect(resolvePackSize(declared, undefined)).toEqual(declared);
  });
});
