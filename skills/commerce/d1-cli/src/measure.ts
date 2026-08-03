/**
 * Unit pricing — the difference between "cheapest pack" and "cheapest".
 *
 * Colombian law requires retailers to publish a *precio por unidad de medida*
 * (PUM), and D1 carries it on ~95% of products as two properties:
 *
 *   Unidad De Medida = "Gr"
 *   Valor de Medida  = "500"
 *
 * That matters because pack price and value routinely disagree. Ranking rice by
 * pack price puts `ARROZ ESTÁNDAR 500 GRS` first at $1,550 — which is $3,100/kg.
 * The best value in the same result set is $2,775/kg, in a $5,550 bag that does
 * not appear anywhere in the pack-price top five. An agent shopping for
 * "the cheapest rice" without this gets a worse answer while looking correct.
 */

/** What a product is measured in, normalized. */
export type Measure = "kg" | "L" | "unit";

export interface UnitSize {
  measure: Measure;
  /** Quantity in the normalized unit: kg, litres, or count. */
  amount: number;
}

/**
 * Colombian labels as D1 writes them. Case varies between products, so
 * comparison is lowercased rather than relying on a canonical spelling.
 */
const UNITS: Record<string, { measure: Measure; perBase: number }> = {
  gr: { measure: "kg", perBase: 1000 },
  g: { measure: "kg", perBase: 1000 },
  gramo: { measure: "kg", perBase: 1000 },
  gramos: { measure: "kg", perBase: 1000 },
  kg: { measure: "kg", perBase: 1 },
  kgs: { measure: "kg", perBase: 1 },
  ml: { measure: "L", perBase: 1000 },
  cc: { measure: "L", perBase: 1000 },
  lt: { measure: "L", perBase: 1 },
  lts: { measure: "L", perBase: 1 },
  l: { measure: "L", perBase: 1 },
  litro: { measure: "L", perBase: 1 },
  litros: { measure: "L", perBase: 1 },
  un: { measure: "unit", perBase: 1 },
  und: { measure: "unit", perBase: 1 },
  unidad: { measure: "unit", perBase: 1 },
  unidades: { measure: "unit", perBase: 1 },
};

/**
 * Read a product's declared size.
 *
 * Returns undefined rather than guessing when the data is absent or
 * unrecognized: a fabricated size produces a confidently wrong $/kg, which is
 * worse than admitting the comparison cannot be made. Callers surface the gap.
 */
export function parseUnitSize(unit?: string, value?: string): UnitSize | undefined {
  if (!unit || !value) return undefined;
  const u = UNITS[unit.trim().toLowerCase()];
  if (!u) return undefined;
  // Colombian decimals may use a comma, and thousands a dot ("1.000").
  const raw = String(value)
    .trim()
    .replace(/\.(?=\d{3}\b)/g, "")
    .replace(",", ".");
  const n = Number(raw);
  if (!Number.isFinite(n) || n <= 0) return undefined;
  return { measure: u.measure, amount: n / u.perBase };
}

/**
 * Price per kg / L / unit, in the same hundredths the rest of the CLI uses.
 * Undefined when the size is unknown — never a guess.
 */
export function unitPrice(price: number, size?: UnitSize): number | undefined {
  if (!size || size.amount <= 0) return undefined;
  return Math.round(price / size.amount);
}

/** `$ 2.775/kg` */
export function formatUnitPrice(formatted: string, measure: Measure): string {
  return `${formatted}/${measure}`;
}
