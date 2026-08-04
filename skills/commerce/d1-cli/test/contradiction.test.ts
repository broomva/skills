/**
 * No two sentences the store locator prints may contradict each other.
 *
 * Enumerated rather than sampled. The comparison half of this property test
 * lives with `d1 basket --brand`, which is not in this change; the locator half
 * is here because the rule is the same and the states are few enough to walk.
 */

import { describe, expect, test } from "bun:test";
import { renderStores } from "../src/present.ts";
import type { StoresResult } from "../src/stores.ts";

describe("no two sentences the store locator prints can contradict each other", () => {
  const at = { lat: 4.75068, lng: -74.03532 };

  test("across every stop reason and total", () => {
    const stops: Array<StoresResult["stopped"]> = ["registry-empty", "cap", "limit"];
    const totals = [undefined, 0, 1, 29, 115, 299, 300, 301];
    const offenders: string[] = [];

    for (const stopped of stops) {
      for (const registryTotal of totals) {
        for (const swept of [0, 1, 30, 299, 300]) {
          const r: StoresResult = {
            stores: Array.from({ length: Math.min(swept, 2) }, (_, i) => ({
              id: `s${i}`,
              name: "BOG X",
              distanceKm: 1 + i,
              street: "CRA 1",
              neighborhood: "N",
              city: "BOGOTA",
              state: "BOG",
              postalCode: "1",
              hours: [],
              active: true,
            })),
            swept,
            reachedKm: swept ? 2 : undefined,
            registryTotal,
            dropped: 0,
            stopped,
          };
          const out = renderStores(r, at, 1);

          // "every point the registry returns" and "may hold more" are opposite
          // claims about the same set.
          if (/every point the registry returns/.test(out) && /hold more/.test(out)) {
            offenders.push(`${stopped}/${registryTotal}/${swept}: exhausted AND more exist`);
          }
          // An exact remainder must never be negative or zero — that is not a
          // remainder, it is a contradiction of `swept`.
          const m = out.match(/holds (\d+) more further out/);
          if (m && Number(m[1]) <= 0) {
            offenders.push(`${stopped}/${registryTotal}/${swept}: non-positive remainder`);
          }
          // A capped sweep must not also claim to be the complete answer.
          if (/own ceiling of/.test(out) && /every point the registry returns/.test(out)) {
            offenders.push(`${stopped}/${registryTotal}/${swept}: capped AND complete`);
          }
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
