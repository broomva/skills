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

// ---------------------------------------------------------------------------
// Multipacks
// ---------------------------------------------------------------------------

/**
 * What D1's own description says about how a pack is composed.
 *
 * Only ever populated from an EXPLICIT statement. The pack count in a product
 * NAME is deliberately not a source here — see `resolvePackSize`.
 */
export interface PackEvidence {
  /** Size of ONE item in the pack, as the description states it. */
  perItem: UnitSize;
  /** How many items the pack holds, from the same statement. */
  count: number;
}

/** Descriptions are marketing HTML; this reads prose, not markup. */
function plainText(html: string): string {
  return html
    .replace(/<[^>]*>/g, " ")
    .replace(/&nbsp;/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Longest description this scans. D1's run ~2 kB; this is slack, not a real limit. */
const MAX_DESCRIPTION = 20_000;

const AMOUNT = String.raw`([\d.,]+)`;
const UNIT = "(kg|kgs|grs|gr|gramos|gramo|g|ml|cc|lts|lt|litros|litro|l)";
// `unidades?` would match "unidade" and "unidades" but NOT the singular
// "unidad", which is the form D1 uses for a one-item pack — so the count guard
// below was never reached for exactly the input it exists to reject.
const ITEM_NOUN = String.raw`(?:unidad(?:es)?|bolsita(?:s)?|sobre(?:s)?|pieza(?:s)?|porci(?:ón|on)(?:es)?)`;
const PER_ITEM = String.raw`(?:por\s+unidad|c/u|cada\s+una?)`;

/** "6 unidades de 200 mL cada una" — count and per-item size in one statement. */
const COUNT_THEN_SIZE = new RegExp(
  String.raw`(\d{1,4})\s*${ITEM_NOUN}\s+de\s+${AMOUNT}\s*${UNIT}\b`,
  "i",
);
/** "114 g por unidad" — the per-item size on its own. */
const SIZE_THEN_PER_ITEM = new RegExp(String.raw`${AMOUNT}\s*${UNIT}\b\s*${PER_ITEM}`, "i");
/** "(3 unidades por paquete)" — the count that pairs with the statement above. */
const COUNT_PER_PACK = new RegExp(
  String.raw`(\d{1,4})\s*${ITEM_NOUN}\s*(?:por|en\s+el)\s+(?:paquete|empaque)`,
  "i",
);

/**
 * Read an explicit pack composition out of a product description.
 *
 * D1 writes this two ways, both seen live:
 *
 *   SKU 718   "Contenido Neto: 6 unidades de 200 mL cada una"
 *   SKU 510   "Peso: 114 g por unidad (3 unidades por paquete)"
 *
 * Returns undefined unless BOTH the per-item size and the count come from the
 * description. A per-item size without a count cannot yield a pack total, and
 * taking the count from the product name instead is exactly the heuristic that
 * would corrupt the 44 products whose declared value is already the pack total.
 *
 * Known limit: in the two-statement form the size and the count are matched
 * independently, so prose mentioning an unrelated quantity could in principle
 * pair them wrongly. That stays harmless because `resolvePackSize` acts only
 * when the per-item size also equals the declared PUM — across the whole
 * catalogue this fires on 3 products, and all three were checked by hand.
 */
export function readPackEvidence(description?: string): PackEvidence | undefined {
  if (!description) return undefined;
  const text = plainText(description.slice(0, MAX_DESCRIPTION));

  const paired = text.match(COUNT_THEN_SIZE);
  if (paired) {
    const count = Number(paired[1]);
    const perItem = parseUnitSize(paired[3], paired[2]);
    if (perItem && Number.isFinite(count) && count > 1) return { perItem, count };
  }

  const sized = text.match(SIZE_THEN_PER_ITEM);
  const counted = text.match(COUNT_PER_PACK);
  if (sized && counted) {
    const count = Number(counted[1]);
    const perItem = parseUnitSize(sized[2], sized[1]);
    if (perItem && Number.isFinite(count) && count > 1) return { perItem, count };
  }
  return undefined;
}

const CLOSE = 0.03;
const near = (a: number, b: number) => Math.abs(a - b) / Math.max(a, b) <= CLOSE;

/**
 * Reconcile the declared unit-of-measure against what the description says.
 *
 * A census of all 1,600 D1 products (2026-08-03) found 154 name-matchable
 * multipacks carrying a PUM pair. Of the 62 measured in kg or L — the only ones
 * where this can go wrong — 44 declare the PACK TOTAL, 2 declare ONE ITEM, and
 * 16 say nothing either way. So the declared value is trusted by default,
 * because that is what the data says it is; the override fires only where D1's
 * own prose contradicts it:
 *
 *   SKU 718  REFRESCOS 6 UN ... 200 ML   Valor 200 ml, "6 unidades de 200 mL"
 *            -> pack is 1.2 L, so $ 27.450/L was 6x the real $ 4.575/L
 *
 * The reverse — multiplying by a count parsed out of the NAME — is what this
 * function exists to avoid. It would have "corrected" all 44 correct products
 * into being wrong by their pack count, in order to fix 2.
 */
export function resolvePackSize(
  declared: UnitSize | undefined,
  evidence: PackEvidence | undefined,
): UnitSize | undefined {
  if (!declared || !evidence) return declared;
  const { perItem, count } = evidence;
  if (perItem.measure !== declared.measure) return declared;

  // `0.2 * 6` is 1.2000000000000002. Rounded by RELATIVE precision, not to a
  // fixed number of decimals: a 400 mg sachet is 0.0004 kg, and a fixed round
  // deep enough to keep that would leave the noise on litre-scale packs.
  const packTotal = Number((perItem.amount * count).toPrecision(12));
  // The ONLY case that changes anything: the declared value describes one item,
  // while the pack holds `count` of them.
  //
  // There is deliberately no separate "already the pack total" branch. For any
  // real multipack `count` is at least 2, so `packTotal` is at least twice
  // `perItem`, and the two can never both be within 3% of the declared value.
  // Such a branch would read as protective while never deciding anything — a
  // mutation removing it changed no test, which is how it was found.
  if (near(declared.amount, perItem.amount)) {
    return { measure: declared.measure, amount: packTotal };
  }
  // Already the pack total, or matching neither — either way the description
  // and the PUM are not in conflict about one item, and substituting a
  // different number would be the guess this module refuses to make.
  return declared;
}
