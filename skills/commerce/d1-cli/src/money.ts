/**
 * COP money handling.
 *
 * VTEX reports every price as an integer number of *hundredths* of the store
 * currency. D1 trades in Colombian pesos, which are quoted without cents, so
 * the wire value 350000 means COP 3,500 — a factor of 100 away from what a
 * reader expects. Every price crossing this module is converted exactly once,
 * with integer arithmetic, so no basket total ever picks up float drift.
 */

import type { PriceHundredths } from "./types.ts";

/** Convert VTEX hundredths to whole pesos. Rounds half away from zero. */
export function toPesos(v: PriceHundredths): number {
  if (!Number.isFinite(v)) return 0;
  return Math.round(v / 100);
}

/** Convert whole pesos to VTEX hundredths. */
export function toHundredths(pesos: number): PriceHundredths {
  if (!Number.isFinite(pesos)) return 0;
  return Math.round(pesos * 100);
}

/**
 * Format a wire price as Colombian currency: `$ 3.500`.
 *
 * Colombian convention uses `.` as the thousands separator, which is the
 * opposite of the en-US default, so the grouping is applied explicitly rather
 * than left to the ambient locale of whatever machine the CLI runs on.
 */
export function formatCOP(v: PriceHundredths): string {
  const pesos = toPesos(v);
  const sign = pesos < 0 ? "-" : "";
  const grouped = Math.abs(pesos)
    .toString()
    .replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  return `${sign}$ ${grouped}`;
}

/**
 * Percentage off list price, rounded to a whole percent. Returns 0 when there
 * is no discount, when list price is missing, or when the "discount" is
 * negative — upstream occasionally reports a selling price above list, and
 * surfacing that as a negative saving would be actively misleading.
 */
export function discountPercent(price: PriceHundredths, listPrice: PriceHundredths): number {
  if (!listPrice || listPrice <= 0 || price >= listPrice) return 0;
  return Math.round(((listPrice - price) / listPrice) * 100);
}

/** Sum wire prices without leaving integer arithmetic. */
export function sum(values: PriceHundredths[]): PriceHundredths {
  return values.reduce((a, b) => a + (Number.isFinite(b) ? b : 0), 0);
}
