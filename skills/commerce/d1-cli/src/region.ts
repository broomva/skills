/**
 * Regionalization — resolving a delivery point to a fulfilling D1 store.
 *
 * This is the step that makes D1's catalogue trustworthy. Queried without a
 * region, the search API answers from the national catalogue and reports
 * generous stock (10000 units) for the notional seller `1`. Those numbers are
 * not wrong so much as not about anywhere: put the same SKU through a checkout
 * simulation for a real address and it comes back `withoutStock`, because the
 * physical store that would have to ship it does not carry it.
 *
 * So: resolve the point to a region first, carry the region id through search,
 * and price the basket against the region's actual store seller.
 */

import type { D1Client } from "./client.ts";
import { D1Error, type LatLng, type Region, type Seller } from "./types.ts";

/**
 * Serialize a point for the `geoCoordinates` query parameter.
 *
 * The separator is a **semicolon**, and longitude comes first. This is not
 * documented and not guessable: a comma — the obvious choice, and what VTEX's
 * own JSON bodies use for the same pair — is rejected with `CHK0119`
 * ("addresses must have a postal code or geocoordinates"), which reads like the
 * parameter is missing rather than malformed. Getting this wrong is the
 * difference between per-store availability and silently falling back to a
 * national catalogue that does not reflect what anyone can buy.
 */
export function geoParam(at: LatLng): string {
  assertCoordinate(at);
  return `${trimCoord(at.lng)};${trimCoord(at.lat)}`;
}

/**
 * Six decimal places is ~0.1 m at the equator — far finer than store catchment
 * boundaries — and trimming keeps float artefacts like 4.648600000000001 out
 * of the URL.
 */
function trimCoord(n: number): string {
  return String(Number(n.toFixed(6)));
}

/**
 * Reject coordinates that cannot be a Colombian delivery point.
 *
 * The bounds are deliberately loose (mainland plus the Caribbean islands and
 * territorial waters) — the goal is to catch the two mistakes that actually
 * happen, swapped lat/lng and a zeroed-out default, not to adjudicate borders.
 */
export function assertCoordinate(at: LatLng): void {
  const { lat, lng } = at;
  if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
    throw new D1Error(`Coordinates must be numbers, got lat=${lat} lng=${lng}.`);
  }
  if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
    throw new D1Error(`Coordinates out of range: lat=${lat} lng=${lng}.`);
  }
  const inColombia = lat >= -4.5 && lat <= 16 && lng >= -82 && lng <= -66;
  if (!inColombia) {
    const swapped = lng >= -4.5 && lng <= 16 && lat >= -82 && lat <= -66;
    throw new D1Error(
      swapped
        ? `Coordinates look swapped: lat=${lat} lng=${lng}. D1 delivers in Colombia, where latitude is positive and longitude negative.`
        : `Coordinates lat=${lat} lng=${lng} are outside Colombia. D1 only delivers within Colombia.`,
    );
  }
}

interface WireRegion {
  id: string;
  sellers?: Array<{ id: string; name?: string }>;
}

/**
 * Resolve a delivery point to its fulfilment region.
 *
 * A successful call with an empty `sellers` list is a real answer, not a
 * failure: it means D1 has no store covering that point. The caller decides
 * how loudly to say so, so this returns the empty region rather than throwing.
 */
export async function resolveRegion(
  client: D1Client,
  at: LatLng,
  salesChannel?: string,
): Promise<Region> {
  const wire = await client.request<WireRegion[]>("/api/checkout/pub/regions", {
    query: {
      country: "COL",
      geoCoordinates: geoParam(at),
      sc: salesChannel,
    },
  });

  const first = Array.isArray(wire) ? wire[0] : undefined;
  if (!first?.id) {
    throw new D1Error(
      "D1 returned no region for that point. It may be outside their delivery footprint.",
    );
  }

  const sellers: Seller[] = (first.sellers ?? []).map((s) => ({
    id: s.id,
    name: s.name || s.id,
  }));

  return { id: first.id, sellers, at };
}

/**
 * The seller to price a basket against.
 *
 * D1 returns the nearest covering store first, and that is the one the website
 * checks out against, so first-wins is the right default rather than an
 * arbitrary pick.
 */
export function primarySeller(region: Region): Seller | undefined {
  return region.sellers[0];
}

/** Whether D1 will deliver to the point this region was resolved from. */
export function deliverable(region: Region): boolean {
  return region.sellers.length > 0;
}
