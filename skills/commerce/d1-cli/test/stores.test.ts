import { describe, expect, test } from "bun:test";
import { D1Client } from "../src/client.ts";
import { assertAllowedQuery, isAllowedPath } from "../src/endpoints.ts";
import { renderStores } from "../src/present.ts";
import {
  MAX_PAGES,
  MAX_REACHABLE,
  PAGE_SIZE,
  hoursOn,
  nearbyStores,
  vtexDay,
} from "../src/stores.ts";
import { D1Error } from "../src/types.ts";

const AT = { lat: 4.75068, lng: -74.03532 };

const point = (id: string, distance: number, over: Record<string, unknown> = {}) => ({
  distance,
  pickupPoint: {
    id,
    friendlyName: `BOG ${id}`,
    isActive: true,
    address: {
      street: `CRA ${id}`,
      neighborhood: "TOBERIN",
      city: "BOGOTA, D.C.",
      state: "BOGOTA",
      postalCode: "110131",
    },
    businessHours: [
      { DayOfWeek: 1, OpeningTime: "06:00:00", ClosingTime: "21:00:00" },
      { DayOfWeek: 7, OpeningTime: "08:00:00", ClosingTime: "18:00:00" },
    ],
    ...over,
  },
});

/** A client that serves canned pages and records which pages were asked for. */
function paged(pages: unknown[][]) {
  const asked: number[] = [];
  const impl = (async (url: string) => {
    const u = new URL(String(url));
    const p = Number(u.searchParams.get("page") ?? "1");
    asked.push(p);
    return new Response(JSON.stringify(pages[p - 1] ?? []), { status: 200 });
  }) as unknown as typeof fetch;
  return { client: new D1Client({ fetchImpl: impl }), asked };
}

describe("nearbyStores", () => {
  test("a small request reads ONE page, not the whole registry", async () => {
    // The registry is distance-sorted, so the nearest 5 are on page 1. Fetching
    // all ten pages to show five would be 10 requests to a third party for no
    // information — and this is the property a `for (page of 1..10)` loop
    // silently loses.
    const { client, asked } = paged([
      Array.from({ length: 30 }, (_, i) => point(`p${i}`, i * 0.1)),
      Array.from({ length: 30 }, (_, i) => point(`q${i}`, 5 + i * 0.1)),
    ]);
    const r = await nearbyStores(client, AT, { limit: 5 });
    expect(r.stores).toHaveLength(5);
    expect(asked).toEqual([1]);
  });

  test("it pages on when one page cannot satisfy the limit", async () => {
    const { client, asked } = paged([
      Array.from({ length: 30 }, (_, i) => point(`p${i}`, i * 0.1)),
      Array.from({ length: 30 }, (_, i) => point(`q${i}`, 5 + i * 0.1)),
    ]);
    const r = await nearbyStores(client, AT, { limit: 40 });
    expect(r.stores).toHaveLength(40);
    expect(asked).toEqual([1, 2]);
  });

  test("an empty page ends the sweep and marks it exhausted", async () => {
    const { client } = paged([[point("a", 1)], []]);
    const r = await nearbyStores(client, AT, { limit: 50 });
    expect(r.stores).toHaveLength(1);
    expect(r.stopped).toBe("registry-empty");
  });

  test("a page of nothing but repeats also ends it, rather than looping", async () => {
    // A paged endpoint that starts repeating would otherwise inflate `swept`
    // and make the disclosed radius describe a look that never happened.
    const { client, asked } = paged([[point("a", 1)], [point("a", 1)], [point("b", 2)]]);
    const r = await nearbyStores(client, AT, { limit: 50 });
    expect(r.stores.map((s) => s.id)).toEqual(["a"]);
    expect(r.stopped).toBe("registry-empty");
    // It stopped at page 2 — it did not go on to find `b`.
    expect(asked).toEqual([1, 2]);
  });

  test("reachedKm is the radius of the whole look, not of what is shown", async () => {
    // The disclosure "N found within X km" is a claim about the SWEEP. Deriving
    // it from the truncated list would understate the radius and make the
    // registry look smaller than it is.
    const { client } = paged([[point("a", 1), point("b", 2), point("c", 3)], []]);
    const r = await nearbyStores(client, AT, { limit: 1 });
    expect(r.stores).toHaveLength(1);
    expect(r.swept).toBe(3);
    expect(r.reachedKm).toBe(3);
  });

  test("a point with no distance sorts LAST and never becomes the nearest", async () => {
    // `?? 0` would have made an unplaceable point the closest thing to you.
    const { client } = paged([[point("nodist", Number.NaN), point("real", 4)], []]);
    const r = await nearbyStores(client, AT, { limit: 5 });
    expect(r.stores.map((s) => s.id)).toEqual(["real", "nodist"]);
    // And it does not contaminate the radius claim.
    expect(r.reachedKm).toBe(4);
  });

  test("a malformed entry is dropped rather than rendered as a blank shop", async () => {
    const { client } = paged([[{ distance: 1 }, point("ok", 2)], []]);
    const r = await nearbyStores(client, AT, { limit: 5 });
    expect(r.stores.map((s) => s.id)).toEqual(["ok"]);
  });

  test("an inactive point is kept but flagged, not silently dropped", async () => {
    const { client } = paged([[point("shut", 1, { isActive: false })], []]);
    const r = await nearbyStores(client, AT, { limit: 5 });
    expect(r.stores[0]?.active).toBe(false);
  });

  test("it refuses a coordinate that cannot be a Colombian delivery point", async () => {
    const { client } = paged([[]]);
    await expect(nearbyStores(client, { lat: -74.03, lng: 4.75 })).rejects.toThrow(D1Error);
  });

  test("the limit is clamped to what the registry can actually serve", async () => {
    const { client, asked } = paged(
      Array.from({ length: MAX_PAGES }, (_, p) =>
        Array.from({ length: PAGE_SIZE }, (_, i) => point(`p${p}-${i}`, p + i * 0.01)),
      ),
    );
    const r = await nearbyStores(client, AT, { limit: 99_999 });
    expect(r.stores).toHaveLength(MAX_REACHABLE);
    expect(asked).toHaveLength(MAX_PAGES);
    // Ten full pages is the API's CEILING, not the registry running out. The
    // difference is what the output tells the reader, so it is a distinct value
    // rather than a boolean shared with "the registry had no more".
    expect(r.stopped).toBe("cap");
  });
});

describe("renderStores", () => {
  const result = (over: Record<string, unknown> = {}) => ({
    stores: [
      {
        id: "a",
        name: "BOG TOBERIN",
        distanceKm: 0.88,
        street: "CL 164 # 16 A - 49",
        neighborhood: "TOBERIN",
        city: "BOGOTA, D.C.",
        state: "BOGOTA",
        postalCode: "110131",
        hours: [{ day: 1, opens: "07:00:00", closes: "21:00:00" }],
        active: true,
      },
    ],
    swept: 30,
    reachedKm: 2.56,
    stopped: "limit" as const,
    ...over,
  });

  test("it says these are not collection points", () => {
    // The load-bearing line. A list of street addresses with opening hours
    // reads as a collection offer to anyone who does not already know it is
    // not one, and no simulation has ever offered `pickup-in-point`.
    const out = renderStores(result(), AT, 1);
    expect(out).toContain("not collection points");
    expect(out).toContain("scheduled delivery only");
  });

  test("it states the radius the 'nearest' claim is good for", () => {
    expect(renderStores(result(), AT, 1)).toContain("within 2.6 km");
  });

  test("each of the three endings says a different, true thing", () => {
    // A boolean conflated `cap` with `limit`, so a sweep that hit the API's own
    // ceiling told the reader "the registry holds more further out" — true of
    // the world, false of anything this command can reach.
    expect(renderStores(result(), AT, 1)).toContain("holds more further out");
    expect(renderStores(result({ stopped: "registry-empty" }), AT, 1)).toContain(
      "that is every point the registry returns here",
    );
    expect(renderStores(result({ stopped: "cap" }), AT, 1)).toContain("own ceiling of 300");
    // And the three are mutually exclusive, or a sentence is saying two of them.
    expect(renderStores(result({ stopped: "registry-empty" }), AT, 1)).not.toContain("holds more");
    expect(renderStores(result({ stopped: "cap" }), AT, 1)).not.toContain("holds more");
    expect(renderStores(result({ stopped: "cap" }), AT, 1)).not.toContain("every point");
  });

  test("today's hours print only for the day asked about", () => {
    expect(renderStores(result(), AT, 1)).toContain("open today 07:00–21:00");
    // Day 2 has no entry in the fixture, so nothing is claimed about it.
    expect(renderStores(result(), AT, 2)).not.toContain("open today");
  });

  test("an empty registry answer is not reported as 'no shops here'", () => {
    // The registry lists points D1 configured for logistics. That is not the
    // same set as shops with a door, and saying so is the difference between
    // reporting a lookup and asserting a fact about a neighbourhood.
    const out = renderStores({ stores: [], swept: 0, stopped: "registry-empty" }, AT);
    expect(out).toContain("not a survey of the neighbourhood");
  });

  test("an inactive store is marked in the output", () => {
    const r = result();
    r.stores[0].active = false;
    expect(renderStores(r, AT, 1)).toContain("[inactive]");
  });
});

describe("the pickup-point endpoint is admitted, and narrowly", () => {
  test("the path is on the allowlist", () => {
    expect(isAllowedPath("/api/checkout/pub/pickup-points")).toBe(true);
  });

  test("its query guard accepts what the CLI actually sends", () => {
    const ok = new URLSearchParams({
      geoCoordinates: "-74.03532;4.75068",
      countryCode: "COL",
      page: "3",
    });
    expect(() => assertAllowedQuery("/api/checkout/pub/pickup-points", ok)).not.toThrow();
  });

  test("`count` is REFUSED, because the endpoint ignores it", () => {
    // Accepted upstream, silently dropped, still returns 30 — the same shape as
    // `fq=skuId:` on intelligent-search. Admitting it would let a caller believe
    // it had asked for something.
    const bad = new URLSearchParams({ geoCoordinates: "-74;4.7", count: "100" });
    expect(() => assertAllowedQuery("/api/checkout/pub/pickup-points", bad)).toThrow(/count/);
  });

  test("a malformed coordinate is refused before it leaves", () => {
    // The comma is the mistake that actually happens — VTEX's own JSON bodies
    // use one for the same pair, and this endpoint wants a semicolon.
    const bad = new URLSearchParams({ geoCoordinates: "-74.03532,4.75068" });
    expect(() => assertAllowedQuery("/api/checkout/pub/pickup-points", bad)).toThrow(
      /geoCoordinates/,
    );
  });
});

describe("day numbering", () => {
  test("VTEX counts Monday as 1 and Sunday as 7, JS counts Sunday as 0", () => {
    expect(vtexDay(0)).toBe(7);
    expect(vtexDay(1)).toBe(1);
    expect(vtexDay(6)).toBe(6);
  });

  test("hoursOn refuses a day outside the week rather than answering undefined", () => {
    const store = {
      id: "a",
      name: "",
      distanceKm: 1,
      street: "",
      neighborhood: "",
      city: "",
      state: "",
      postalCode: "",
      hours: [{ day: 1, opens: "07:00:00", closes: "21:00:00" }],
      active: true,
    };
    expect(hoursOn(store, 1)?.opens).toBe("07:00:00");
    expect(hoursOn(store, 2)).toBeUndefined();
    // An out-of-range day is a caller bug, and `undefined` would hide it as
    // "closed today".
    expect(() => hoursOn(store, 0)).toThrow(D1Error);
    expect(() => hoursOn(store, 8)).toThrow(D1Error);
  });
});
