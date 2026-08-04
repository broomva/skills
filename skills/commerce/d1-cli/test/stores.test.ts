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

/**
 * A client serving canned pages in the shape the endpoint ACTUALLY returns.
 *
 * `{paging, items}` — never a bare array. Every fixture here originally served
 * an array, and a mutation deleting the `items` handler left the whole suite
 * green while the command returned nothing at all against live D1 and printed
 * "no store is in the registry near you" to say so. The tests were exercising a
 * branch the API has never produced.
 */
function paged(pages: unknown[][], total?: number) {
  const asked: number[] = [];
  const all = total ?? pages.reduce((n, p) => n + p.length, 0);
  const impl = (async (url: string) => {
    const u = new URL(String(url));
    const p = Number(u.searchParams.get("page") ?? "1");
    asked.push(p);
    const items = pages[p - 1] ?? [];
    return new Response(
      JSON.stringify({
        paging: { page: p, pageSize: PAGE_SIZE, total: all, pages: Math.ceil(all / PAGE_SIZE) },
        items,
      }),
      { status: 200 },
    );
  }) as unknown as typeof fetch;
  return { client: new D1Client({ fetchImpl: impl }), asked };
}

/** A full page, so a sweep does not stop early on a short one. */
const fullPage = (prefix: string, from: number) =>
  Array.from({ length: PAGE_SIZE }, (_, i) => point(`${prefix}${i}`, from + i * 0.01));

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
    //
    // FULL pages, deliberately: a short page is now definitive exhaustion on its
    // own, so a one-item fixture would stop at page 1 and never reach the
    // repeat guard this test is named for.
    const first = fullPage("p", 1);
    const { client, asked } = paged([first, first, fullPage("q", 9)], 300);
    const r = await nearbyStores(client, AT, { limit: 200 });
    expect(r.swept).toBe(PAGE_SIZE);
    expect(r.stopped).toBe("registry-empty");
    // It stopped at page 2 — it did not go on to find the `q` page.
    expect(asked).toEqual([1, 2]);
  });

  test("a SHORT page is the last page, and is not reported as the API's cap", async () => {
    // 299 stores fill ten pages whose tenth holds 29. Reaching page 10 was
    // treated as hitting the ceiling, so the output said "a shop further out is
    // missing from this answer" about a registry that had just served
    // everything it has.
    const pages = [
      ...Array.from({ length: 9 }, (_, i) => fullPage(`p${i}`, i + 1)),
      fullPage("z", 10).slice(0, 29),
    ];
    const { client } = paged(pages, 299);
    const r = await nearbyStores(client, AT, { limit: 300 });
    expect(r.swept).toBe(299);
    expect(r.registryTotal).toBe(299);
    expect(r.stopped).toBe("registry-empty");
  });

  test("the registry's own total is read rather than inferred", async () => {
    // `paging.total` sat unread in every response while the cap question was
    // being answered by page arithmetic.
    const { client } = paged([fullPage("p", 1)], 300);
    const r = await nearbyStores(client, AT, { limit: 10 });
    expect(r.registryTotal).toBe(300);
  });

  test("a bare array is still tolerated, since that tolerance is deliberate", async () => {
    const impl = (async () =>
      new Response(JSON.stringify([point("a", 1)]), { status: 200 })) as unknown as typeof fetch;
    const r = await nearbyStores(new D1Client({ fetchImpl: impl }), AT, { limit: 5 });
    expect(r.stores.map((s) => s.id)).toEqual(["a"]);
    expect(r.registryTotal).toBeUndefined();
  });

  test("a non-finite limit does not fetch everything and then deny it", async () => {
    // `Math.trunc(NaN)` is NaN and every comparison against it is false, so this
    // read all ten pages and returned zero stores — the command denying the
    // registry it had just read in full.
    const { client, asked } = paged([fullPage("p", 1)], 300);
    const r = await nearbyStores(client, AT, { limit: Number.NaN });
    expect(r.stores.length).toBe(10);
    expect(asked).toEqual([1]);
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
    const { client } = paged([
      // Two different malformations, because the guard does two jobs and a
      // fixture missing `pickupPoint` entirely only exercises one of them: a
      // mutation that kept an id-less point still passed.
      [{ distance: 1 }, { distance: 1.5, pickupPoint: { friendlyName: "NO ID" } }, point("ok", 2)],
      [],
    ]);
    const r = await nearbyStores(client, AT, { limit: 5 });
    expect(r.stores.map((s) => s.id)).toEqual(["ok"]);
    // And it is not counted as something the sweep found, either.
    expect(r.swept).toBe(1);
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
      Array.from({ length: MAX_PAGES }, (_, p) => fullPage(`p${p}-`, p + 1)),
      MAX_REACHABLE,
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
    dropped: 0,
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
    // Without a reported total, "holds more" is an assertion the sweep cannot
    // make: stopping on `limit` after a page that happened to hold exactly the
    // limit proves nothing about what lies beyond it.
    expect(renderStores(result(), AT, 1)).toContain("may hold more further out");
    // WITH a total, the number is known and stated exactly.
    expect(renderStores(result({ registryTotal: 115 }), AT, 1)).toContain(
      "the registry holds 85 more further out",
    );
    // At exactly the ceiling it is not a total at all — `stores.ts` refuses to
    // call it exhaustion for that reason, so this must not turn it into an
    // exact remainder either. 300 is what Bogotá and Medellín both report.
    expect(renderStores(result({ registryTotal: 300 }), AT, 1)).toContain(
      "may hold more further out",
    );
    expect(renderStores(result({ stopped: "registry-empty" }), AT, 1)).toContain(
      "that is every point the registry returns here",
    );
    expect(renderStores(result({ stopped: "cap" }), AT, 1)).toContain("own ceiling of 300");
    // And the three are mutually exclusive, or a sentence is saying two of them.
    expect(renderStores(result({ stopped: "registry-empty" }), AT, 1)).not.toContain("hold more");
    expect(renderStores(result({ stopped: "cap" }), AT, 1)).not.toContain("hold more");
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
    const out = renderStores({ stores: [], swept: 0, dropped: 0, stopped: "registry-empty" }, AT);
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

describe("the short-page rule stands on its own [BRO-2067]", () => {
  test("a short page ends the sweep even when the registry reports no total", async () => {
    // The `paging.total` check masked this one: with a total present, 299 of
    // 299 already ended the sweep, so deleting the short-page rule changed
    // nothing. Without a total — the bare-array shape — only the short page can
    // end it, and its absence sent nine more requests and called the result a
    // cap.
    const asked: number[] = [];
    const impl = (async (url: string) => {
      const page = Number(new URL(String(url)).searchParams.get("page") ?? "1");
      asked.push(page);
      const items = page === 1 ? fullPage("p", 1) : page === 2 ? [point("z", 9)] : [];
      return new Response(JSON.stringify(items), { status: 200 });
    }) as unknown as typeof fetch;
    const r = await nearbyStores(new D1Client({ fetchImpl: impl }), AT, { limit: 300 });
    expect(r.swept).toBe(PAGE_SIZE + 1);
    expect(r.stopped).toBe("registry-empty");
    // Stopped at page 2, not page 10.
    expect(asked).toEqual([1, 2]);
  });
});

describe("the page-10 ceiling stands on its own [BRO-2067]", () => {
  test("ten FULL pages with no reported total is the cap", () => {
    // With `paging.total` present the total check fires first, so the page-10
    // branch is only reachable when the registry reports no total — the
    // bare-array shape. Without this the branch is unfalsifiable: deleting it
    // left the whole suite green.
    return (async () => {
      const impl = (async (url: string) => {
        const page = Number(new URL(String(url)).searchParams.get("page") ?? "1");
        return new Response(JSON.stringify(fullPage(`p${page}-`, page)), { status: 200 });
      }) as unknown as typeof fetch;
      const r = await nearbyStores(new D1Client({ fetchImpl: impl }), AT, { limit: 9_999 });
      expect(r.swept).toBe(MAX_REACHABLE);
      expect(r.registryTotal).toBeUndefined();
      expect(r.stopped).toBe("cap");
    })();
  });
});

describe("renderStores keys its empty branch on the SWEEP [BRO-2067]", () => {
  test("an answer this parser could not read is not 'the registry's answer'", async () => {
    // `swept` counts SURVIVORS of normalization, so 30 unreadable entries leave
    // it at 0 — and the earlier gate on `swept` collapsed exactly like the
    // `stores.length` gate it replaced. Driven end to end, because a hand-built
    // `{stores: [], swept: 3}` is a state `nearbyStores` cannot produce.
    const impl = (async () =>
      new Response(
        JSON.stringify({
          paging: { page: 1, pageSize: PAGE_SIZE, total: 300, pages: 10 },
          items: Array.from({ length: 30 }, () => ({ distance: 1, pickupPoint: { name: "x" } })),
        }),
        { status: 200 },
      )) as unknown as typeof fetch;
    const r = await nearbyStores(new D1Client({ fetchImpl: impl }), AT, { limit: 5 });
    expect(r.swept).toBe(0);
    expect(r.dropped).toBe(30);
    const out = renderStores(r, AT);
    expect(out).toContain("could be read from the pickup registry");
    expect(out).toContain("30 entries");
    expect(out).toContain("a bug here rather than an empty neighbourhood");
    expect(out).not.toContain("not a survey of the neighbourhood");
  });

  test("a genuinely empty registry still says so", () => {
    // The other polarity, or the fix is just a different sentence everywhere.
    const out = renderStores({ stores: [], swept: 0, dropped: 0, stopped: "registry-empty" }, AT);
    expect(out).toContain("not a survey of the neighbourhood");
    expect(out).not.toContain("could be read from the pickup registry");
  });
});

describe("CodeRabbit round [BRO-2067]", () => {
  test("a page nobody could read is not 'every point the registry returns'", async () => {
    // `fresh === 0` fires both for a page of duplicates and for a page this
    // parser could not read a word of. The second is not the registry running
    // out; it is us running out, and claiming completeness from it is the same
    // substitution the `dropped` count exists to prevent.
    const good = fullPage("p", 1);
    const impl = (async (url: string) => {
      const page = Number(new URL(String(url)).searchParams.get("page") ?? "1");
      const items =
        page === 1
          ? good
          : Array.from({ length: PAGE_SIZE }, () => ({ distance: 9, pickupPoint: { name: "x" } }));
      return new Response(
        JSON.stringify({ paging: { page, pageSize: PAGE_SIZE, total: 300, pages: 10 }, items }),
        { status: 200 },
      );
    }) as unknown as typeof fetch;
    const r = await nearbyStores(new D1Client({ fetchImpl: impl }), AT, { limit: 300 });
    expect(r.stopped).toBe("registry-empty");
    expect(r.dropped).toBe(PAGE_SIZE);
    const out = renderStores(r, AT, 1);
    expect(out).toContain("could not be read here, so there may be others");
    expect(out).not.toContain("that is every point the registry returns here");
  });

  test("...and a clean exhaustion still claims completeness", () => {
    // The other polarity, or the fix is a hedge everywhere.
    const out = renderStores(
      {
        stores: [
          {
            id: "a",
            name: "X",
            distanceKm: 1,
            street: "",
            neighborhood: "",
            city: "",
            state: "",
            postalCode: "",
            hours: [],
            active: true,
          },
        ],
        swept: 1,
        reachedKm: 1,
        dropped: 0,
        stopped: "registry-empty",
      },
      AT,
      1,
    );
    expect(out).toContain("that is every point the registry returns here");
  });
});
