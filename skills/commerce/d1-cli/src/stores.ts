/**
 * Nearby D1 stores, from VTEX's pickup-point registry.
 *
 * ## This is a locator, not click-and-collect
 *
 * `/api/checkout/pub/pickup-points` returns real, current store data — names,
 * street addresses, opening hours, coordinates — and it is tempting to read
 * that as "you can collect an order here". You cannot, as far as anything
 * measurable says. Every checkout simulation at every delivery point tried,
 * against both the national seller and the regional one, comes back with
 * `deliveryChannels: [{"id": "delivery"}]` and nothing else. No
 * `pickup-in-point` channel has ever been observed.
 *
 * So these are the stores that exist near a point, which is a genuinely useful
 * thing to know and is all this claims. The renderer says so out loud, because
 * a list of addresses with opening hours reads like a collection offer unless
 * it is told not to.
 *
 * ## The registry is paged, capped, and lies about `count`
 *
 * Measured 2026-08-04 against a Bogotá point:
 *
 *   - **30 results per page**, always. `?count=100` is accepted and **silently
 *     ignored** — the same shape as `fq=skuId:` on intelligent-search, where a
 *     dropped filter returns everything with HTTP 200.
 *   - `?page=N` works, results are sorted by ascending distance, and page 11
 *     comes back empty.
 *   - So **300 points is a CEILING, not a total.** At that Bogotá point the
 *     300th is 17 km away; a shop 18 km away is not in the registry's answer
 *     and its absence is not evidence it does not exist.
 *
 * Which is why {@link nearbyStores} reports how far its own look reached. A
 * "nearest N" claim is only as good as the radius behind it.
 */

import type { D1Client } from "./client.ts";
import { assertCoordinate, geoParam } from "./region.ts";
import { D1Error, type LatLng } from "./types.ts";

/** Points per page. Fixed by the API; `count` does not move it. */
export const PAGE_SIZE = 30;

/** Pages the registry will serve before answering empty. */
export const MAX_PAGES = 10;

/** The most points reachable for any one coordinate. */
export const MAX_REACHABLE = PAGE_SIZE * MAX_PAGES;

export interface StoreHours {
  /** 1 = Monday … 7 = Sunday, as VTEX numbers them. */
  day: number;
  opens: string;
  closes: string;
}

export interface Store {
  id: string;
  name: string;
  /** Kilometres from the requested point, as the API computes it. */
  distanceKm: number;
  street: string;
  neighborhood: string;
  city: string;
  state: string;
  postalCode: string;
  hours: StoreHours[];
  /** False for a point the registry lists but marks closed/disabled. */
  active: boolean;
}

export interface StoresResult {
  stores: Store[];
  /**
   * Points that survived normalization and de-duplication, before `limit`.
   *
   * Not "points fetched": a malformed entry is dropped here and must not be
   * counted as something the look found.
   */
  swept: number;
  /**
   * What the registry says it holds for this point, when it says.
   *
   * This is the answer to "is there more?", and it was being inferred from page
   * arithmetic while sitting unread in every response.
   */
  registryTotal?: number;
  /**
   * How far the sweep reached, in km — the radius the "nearest" claim is good
   * for. Undefined when nothing came back.
   */
  reachedKm?: number;
  /**
   * Registry entries fetched but discarded as unreadable.
   *
   * `swept` counts survivors, so a page of 30 entries that all fail
   * {@link normalize} leaves `swept: 0` — which the renderer then reported as
   * "that is the registry's answer" about a registry that had answered with
   * 30. Moving that gate off `stores.length` and onto `swept` fixed the
   * truncation case only; both counts are post-normalization and collapse the
   * same way. This is the count that does not.
   */
  dropped: number;
  /**
   * Why the sweep stopped, because the three reasons mean different things to
   * a reader and a boolean conflated two of them.
   *
   *   - `registry-empty` — the registry genuinely had no more. The list is
   *     everything it knows about this point.
   *   - `cap` — ten full pages, the API's own ceiling. There may well be shops
   *     further out; their absence here is the cap, not the world.
   *   - `limit` — the caller asked for fewer than were available.
   */
  stopped: "registry-empty" | "cap" | "limit";
}

/**
 * What the endpoint actually returns.
 *
 * An OBJECT with `paging` and `items` — never a bare array. Every fixture in
 * `test/stores.test.ts` originally served an array, so the whole suite
 * exercised a branch the API has never produced: deleting the `items` handler
 * left 487 tests green while the command returned nothing at all against live
 * D1 and printed "no store is in the registry near you" to say so.
 */
interface WirePage {
  paging?: { page?: number; pageSize?: number; total?: number; pages?: number };
  items?: WirePoint[];
}

interface WirePoint {
  distance?: number;
  pickupPoint?: {
    id?: string;
    friendlyName?: string;
    isActive?: boolean;
    address?: {
      street?: string;
      neighborhood?: string;
      city?: string;
      state?: string;
      postalCode?: string;
    };
    businessHours?: Array<{ DayOfWeek?: number; OpeningTime?: string; ClosingTime?: string }>;
  };
}

function normalize(w: WirePoint): Store | undefined {
  const p = w.pickupPoint;
  if (!p?.id) return undefined;
  const a = p.address ?? {};
  return {
    id: p.id,
    name: p.friendlyName ?? "",
    // Distance drives the ordering and the disclosed radius. A point without
    // one cannot be placed, so it sorts last rather than to the front, which is
    // where `?? 0` would have put it.
    distanceKm:
      typeof w.distance === "number" && Number.isFinite(w.distance) ? w.distance : Number.NaN,
    street: a.street ?? "",
    neighborhood: a.neighborhood ?? "",
    city: a.city ?? "",
    state: a.state ?? "",
    postalCode: a.postalCode ?? "",
    hours: (p.businessHours ?? [])
      .filter((h) => typeof h.DayOfWeek === "number" && h.OpeningTime && h.ClosingTime)
      .map((h) => ({
        day: h.DayOfWeek as number,
        opens: h.OpeningTime as string,
        closes: h.ClosingTime as string,
      })),
    active: p.isActive !== false,
  };
}

export interface StoresOptions {
  /** How many to return. Pages are fetched until this is met or the registry ends. */
  limit?: number;
}

/**
 * The stores nearest a point, with the reach of the look reported alongside.
 *
 * Fetches only as many pages as `limit` requires. A caller asking for 5 makes
 * one request, not ten — the registry is sorted by distance, so the first page
 * already holds the nearest 30.
 */
export async function nearbyStores(
  client: D1Client,
  at: LatLng,
  opts: StoresOptions = {},
): Promise<StoresResult> {
  assertCoordinate(at);
  // `Math.trunc(NaN)` is NaN and every comparison against it is false, so a NaN
  // limit fetched all ten pages and then returned nothing — the command denying
  // the registry it had just read in full.
  const asked = Math.trunc(opts.limit ?? 10);
  const limit = Number.isFinite(asked) ? Math.max(1, Math.min(MAX_REACHABLE, asked)) : 10;

  const collected: Store[] = [];
  const seen = new Set<string>();
  let dropped = 0;
  let stopped: StoresResult["stopped"] = "limit";

  let registryTotal: number | undefined;

  for (let page = 1; page <= MAX_PAGES; page++) {
    const w = await client.request<WirePage | WirePoint[]>("/api/checkout/pub/pickup-points", {
      query: { geoCoordinates: geoParam(at), countryCode: "COL", page },
    });
    // The live endpoint returns `{paging, items}`. The array arm is tolerated
    // only because a shape assumption is cheaper to keep than to prove absent.
    const raw = Array.isArray(w) ? w : (w.items ?? []);
    if (!Array.isArray(w) && typeof w.paging?.total === "number") {
      registryTotal = w.paging.total;
    }
    if (!raw.length) {
      stopped = "registry-empty";
      break;
    }
    let fresh = 0;
    for (const item of raw) {
      const s = normalize(item);
      // De-duplicated across pages. The registry has not been observed to
      // repeat, but a paged endpoint that starts repeating would otherwise
      // inflate `swept` and make the disclosed radius describe a look that did
      // not happen.
      if (!s) {
        dropped++;
        continue;
      }
      if (seen.has(s.id)) continue;
      seen.add(s.id);
      collected.push(s);
      fresh++;
    }
    if (fresh === 0) {
      stopped = "registry-empty";
      break;
    }
    // A SHORT page is the last page, definitively — and this is checked before
    // the cap, because reaching page 10 is not the same as page 10 being full.
    // A point with 299 stores fills ten pages, the tenth holding 29, and was
    // reported as "the registry's own ceiling of 300, so a shop further out is
    // missing" about a registry that had just served everything it has.
    if (raw.length < PAGE_SIZE) {
      stopped = "registry-empty";
      break;
    }
    if (registryTotal !== undefined && collected.length >= registryTotal) {
      // Everything the registry admits to holding. At exactly MAX_REACHABLE the
      // two readings are indistinguishable — `total` reports 300 at both Bogotá
      // and Medellín, which is too round to be a coincidence — so the ambiguous
      // case takes the more cautious sentence rather than claiming completeness.
      stopped = registryTotal >= MAX_REACHABLE ? "cap" : "registry-empty";
      break;
    }
    if (page === MAX_PAGES) {
      stopped = "cap";
      break;
    }
    if (collected.length >= limit) break;
  }

  // Sorted here rather than trusted from the wire. The API does return ascending
  // distance today, but `reachedKm` below is a claim about the whole set, and a
  // claim should not depend on an ordering nobody checked.
  collected.sort((a, b) => {
    const an = Number.isNaN(a.distanceKm);
    const bn = Number.isNaN(b.distanceKm);
    if (an !== bn) return an ? 1 : -1;
    return an ? 0 : a.distanceKm - b.distanceKm;
  });

  const placed = collected.filter((s) => !Number.isNaN(s.distanceKm));
  return {
    stores: collected.slice(0, limit),
    swept: collected.length,
    reachedKm: placed.length ? placed[placed.length - 1].distanceKm : undefined,
    registryTotal,
    dropped,
    stopped,
  };
}

/** Today's opening hours for a store, in the caller's day numbering (1 = Mon). */
export function hoursOn(store: Store, day: number): StoreHours | undefined {
  if (!Number.isInteger(day) || day < 1 || day > 7) {
    throw new D1Error(`Day must be 1 (Monday) through 7 (Sunday), got ${day}.`);
  }
  return store.hours.find((h) => h.day === day);
}

/** JS `Date.getDay()` (0 = Sunday) in VTEX's numbering (1 = Monday, 7 = Sunday). */
export function vtexDay(jsDay: number): number {
  return jsDay === 0 ? 7 : jsDay;
}
