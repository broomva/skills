import { describe, expect, test } from "bun:test";
import { D1Client } from "../src/client.ts";
import {
  assertCoordinate,
  deliverable,
  geoParam,
  primarySeller,
  resolveRegion,
} from "../src/region.ts";
import { D1Error } from "../src/types.ts";

const CHAPINERO = { lat: 4.6486, lng: -74.0628 };

describe("geoParam — the separator that is not a comma", () => {
  test("serializes as longitude;latitude", () => {
    expect(geoParam(CHAPINERO)).toBe("-74.0628;4.6486");
  });

  test("uses a semicolon, not a comma", () => {
    // A comma is what VTEX's own JSON bodies use for the same pair, and it is
    // rejected here with CHK0119 — a message that reads like the parameter is
    // missing rather than malformed. This assertion exists so nobody
    // "normalizes" the separator during a cleanup.
    const p = geoParam(CHAPINERO);
    expect(p).toContain(";");
    expect(p).not.toContain(",");
  });

  test("puts longitude first", () => {
    const [first, second] = geoParam(CHAPINERO).split(";").map(Number);
    expect(first).toBe(CHAPINERO.lng);
    expect(second).toBe(CHAPINERO.lat);
    expect(first).toBeLessThan(0); // Colombia is west of Greenwich
    expect(second).toBeGreaterThan(0); // and north of the equator
  });

  test("trims float artefacts", () => {
    // Built at runtime rather than written as a literal: the excess digits are
    // the point of the test, and a literal that loses precision at parse time
    // would be testing nothing.
    const drifted = Number("4.6486000000000015");
    expect(geoParam({ lat: drifted, lng: -74.0628 })).toBe("-74.0628;4.6486");
  });
});

describe("assertCoordinate", () => {
  test("accepts a Colombian point", () => {
    expect(() => assertCoordinate(CHAPINERO)).not.toThrow();
  });

  test("catches swapped lat/lng and says so", () => {
    expect(() => assertCoordinate({ lat: -74.0628, lng: 4.6486 })).toThrow(/swapped/i);
  });

  test("rejects a zeroed default", () => {
    expect(() => assertCoordinate({ lat: 0, lng: 0 })).toThrow(D1Error);
  });

  test("rejects non-numbers", () => {
    expect(() => assertCoordinate({ lat: Number.NaN, lng: -74 })).toThrow(/must be numbers/);
  });

  test("rejects points outside Colombia", () => {
    expect(() => assertCoordinate({ lat: 40.7, lng: -74.0 })).toThrow(/outside Colombia/);
  });
});

describe("resolveRegion", () => {
  /** A fetch stub that records the URL it was called with. */
  function stub(body: unknown, status = 200) {
    const calls: string[] = [];
    const impl = (async (url: string) => {
      calls.push(String(url));
      return new Response(JSON.stringify(body), {
        status,
        headers: { "Content-Type": "application/json" },
      });
    }) as unknown as typeof fetch;
    return { impl, calls };
  }

  test("sends the semicolon-separated point and returns the store seller", async () => {
    const { impl, calls } = stub([
      {
        id: "v2.574CC4356A93931779272F7A26AA8EB6",
        sellers: [{ id: "d1bon11808cc", name: "D1 Bogota" }],
      },
    ]);
    const region = await resolveRegion(new D1Client({ fetchImpl: impl }), CHAPINERO);

    expect(calls[0]).toContain("geoCoordinates=-74.0628%3B4.6486");
    expect(region.id).toBe("v2.574CC4356A93931779272F7A26AA8EB6");
    expect(primarySeller(region)?.id).toBe("d1bon11808cc");
    expect(deliverable(region)).toBe(true);
  });

  test("an empty seller list is a real answer, not an error", async () => {
    // D1 covers a minority of Colombian territory. "We don't deliver here" has
    // to be reportable without throwing, or the CLI cannot say it cleanly.
    const { impl } = stub([{ id: "v2.EMPTY", sellers: [] }]);
    const region = await resolveRegion(new D1Client({ fetchImpl: impl }), CHAPINERO);
    expect(deliverable(region)).toBe(false);
    expect(primarySeller(region)).toBeUndefined();
  });

  test("throws when upstream returns no region at all", async () => {
    const { impl } = stub([]);
    await expect(resolveRegion(new D1Client({ fetchImpl: impl }), CHAPINERO)).rejects.toThrow(
      D1Error,
    );
  });

  test("CHK0119 is translated into an actionable message", async () => {
    const { impl } = stub({ error: { code: "CHK0119", message: "..." } }, 400);
    await expect(resolveRegion(new D1Client({ fetchImpl: impl }), CHAPINERO)).rejects.toThrow(
      /could not resolve that delivery point/i,
    );
  });

  test("refuses to call upstream with a bad coordinate", async () => {
    const { impl, calls } = stub([]);
    await expect(
      resolveRegion(new D1Client({ fetchImpl: impl }), { lat: 0, lng: 0 }),
    ).rejects.toThrow(D1Error);
    expect(calls).toHaveLength(0);
  });
});
