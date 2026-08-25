import { expect, test, describe } from "bun:test";
import { harvestFromHar } from "../src/harvest.ts";

const getEntry = (name: string, hash: string, vars: unknown = { shopId: "9758" }) => ({
  request: {
    method: "GET",
    url:
      `https://www.cub.com/graphql?operationName=${name}` +
      `&variables=${encodeURIComponent(JSON.stringify(vars))}` +
      `&extensions=${encodeURIComponent(JSON.stringify({ persistedQuery: { version: 1, sha256Hash: hash } }))}`,
  },
});

describe("harvestFromHar", () => {
  test("extracts operation name and hash from GET entries", () => {
    const r = harvestFromHar({ log: { entries: [getEntry("SearchResults", "abc123")] } });
    expect(r.operations.SearchResults.sha256Hash).toBe("abc123");
    expect(r.scanned).toBe(1);
  });

  test("extracts from POST bodies too", () => {
    const r = harvestFromHar({
      log: {
        entries: [
          {
            request: {
              method: "POST",
              url: "https://www.cub.com/graphql",
              postData: {
                text: JSON.stringify({
                  operationName: "AddToCart",
                  variables: { itemId: "1" },
                  extensions: { persistedQuery: { version: 1, sha256Hash: "deadbeef" } },
                }),
              },
            },
          },
        ],
      },
    });
    expect(r.operations.AddToCart.sha256Hash).toBe("deadbeef");
  });

  test("ignores non-graphql entries", () => {
    const r = harvestFromHar({
      log: { entries: [{ request: { method: "GET", url: "https://www.cub.com/logo.png" } }] },
    });
    expect(Object.keys(r.operations)).toHaveLength(0);
    expect(r.scanned).toBe(0);
  });

  test("skips graphql entries with no persisted-query hash", () => {
    const r = harvestFromHar({
      log: { entries: [{ request: { method: "GET", url: "https://www.cub.com/graphql?operationName=X" } }] },
    });
    expect(Object.keys(r.operations)).toHaveLength(0);
    expect(r.skipped).toBe(1);
  });

  test("does not retain concrete variable values", () => {
    // A HAR carries real session data. Only the shape should survive harvesting.
    const r = harvestFromHar({
      log: { entries: [getEntry("Op", "h", { addressId: "SECRET-ADDRESS-42", first: 5 })] },
    });
    const serialized = JSON.stringify(r.operations);
    expect(serialized).not.toContain("SECRET-ADDRESS-42");
  });

  test("first occurrence of an operation wins", () => {
    const r = harvestFromHar({
      log: { entries: [getEntry("Dup", "first"), getEntry("Dup", "second")] },
    });
    expect(r.operations.Dup.sha256Hash).toBe("first");
  });

  test("tolerates malformed entries without throwing", () => {
    const r = harvestFromHar({
      log: { entries: [{ request: { method: "GET", url: "https://www.cub.com/graphql?variables=%7Bbroken" } }] },
    });
    expect(r.skipped).toBeGreaterThan(0);
  });
});
