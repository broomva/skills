import type { Product } from "./types.ts";

/**
 * Normalize a free-text product label (from a dataset) or a user alias
 * (from the CLI) to a canonical `Product`. Returns null when unrecognized.
 */
export function normalizeProduct(raw: string): Product | null {
  const s = raw.trim().toUpperCase();
  if (!s) return null;

  // CNG / vehicular natural gas
  if (/(GNCV|CNG|GNV|NATURAL)/.test(s)) return "GNCV";
  // Biodiesel — MUST precede the ACPM/DIESEL check: "BIODIESEL" contains the
  // substring "DIESEL", so a DIESEL-first order silently reclassifies every
  // biodiesel row as ACPM/diesel (observed: 533 "BIODIESEL EXTRA" rows in
  // gjy9-tpph misfiled, and `--product biodiesel` returning nothing).
  if (/BIODIESEL/.test(s)) return "BIODIESEL";
  // Diesel / ACPM
  if (/(ACPM|DIESEL|DIÉSEL|DISEL)/.test(s)) return "ACPM_DIESEL";
  // Extra gasoline
  if (/EXTRA/.test(s)) return "GASOLINA_EXTRA";
  // Corriente / regular gasoline (default gasoline bucket)
  if (/(CORRIENTE|REGULAR|GASOLINA)/.test(s)) return "GASOLINA_CORRIENTE";

  // Short CLI aliases
  if (s === "GAS") return "GNCV";
  if (s === "COR") return "GASOLINA_CORRIENTE";
  return null;
}

/** Human-friendly label for output. */
export function productLabel(p: Product): string {
  return {
    GNCV: "GNCV (gas natural vehicular)",
    GASOLINA_CORRIENTE: "Gasolina corriente",
    GASOLINA_EXTRA: "Gasolina extra",
    ACPM_DIESEL: "ACPM / Diésel",
    BIODIESEL: "Biodiésel",
  }[p];
}

/** Unit label per product (for the price display). */
export function productUnit(p: Product): string {
  return p === "GNCV" ? "m³" : "gal";
}
