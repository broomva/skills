/**
 * The payment boundary is a property of this codebase, so it is asserted like
 * one.
 *
 * `d1` assembles and prices baskets; a human pays. That only holds while no
 * payment surface exists to be called — and "we just won't call it" is not a
 * boundary, because the next person to touch checkout will reach for the
 * obvious next endpoint. These tests fail if the capability is ever added,
 * which turns a design intention into something CI enforces.
 */

import { describe, expect, test } from "bun:test";
import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { checkoutUrl } from "../src/cart.ts";

const SRC = join(import.meta.dir, "..", "src");

function sourceFiles(): Array<{ name: string; body: string }> {
  return readdirSync(SRC)
    .filter((f) => f.endsWith(".ts"))
    .map((f) => ({ name: f, body: readFileSync(join(SRC, f), "utf8") }));
}

describe("the CLI cannot pay", () => {
  const files = sourceFiles();

  test("there is source to check (guards against a vacuous pass)", () => {
    expect(files.length).toBeGreaterThan(5);
    expect(files.map((f) => f.name)).toContain("cart.ts");
  });

  /**
   * The VTEX endpoints that move money. Reaching any of them would let an
   * agent settle a transaction with no human in the loop.
   */
  const PAYMENT_ENDPOINTS = [
    "attachments/paymentData",
    "gatewayCallback",
    "/api/pub/transactions",
    "paymentAccountId",
    "startTransaction",
  ];

  for (const endpoint of PAYMENT_ENDPOINTS) {
    test(`no source file calls ${endpoint}`, () => {
      const offenders = files
        .filter((f) => {
          // Ignore this file's own list and prose that names the boundary.
          const code = f.body
            .split("\n")
            .filter((l) => !l.trimStart().startsWith("*") && !l.trimStart().startsWith("//"))
            .join("\n");
          return code.includes(endpoint);
        })
        .map((f) => f.name);
      expect(offenders).toEqual([]);
    });
  }

  test("no source file names a card field", () => {
    const CARD_FIELDS = ["cardNumber", "securityCode", "cardHolder", "expiryDate", "cvv"];
    for (const field of CARD_FIELDS) {
      const offenders = files.filter((f) => f.body.includes(field)).map((f) => f.name);
      expect(offenders).toEqual([]);
    }
  });

  test("checkout hands off a URL instead of transacting", () => {
    const url = checkoutUrl("abc123");
    expect(url).toBe("https://www.d1.com.co/checkout/?orderFormId=abc123#/cart");
    expect(url.startsWith("https://www.d1.com.co/")).toBe(true);
  });
});

describe("credential handling", () => {
  const files = sourceFiles();

  test("no admin API key is read from the environment", () => {
    // A VTEX appKey/appToken pair grants account-wide admin access. The CLI is
    // deliberately limited to a storefront session token, which can only see
    // its own owner's data.
    for (const f of files) {
      expect(f.body).not.toContain("X-VTEX-API-AppKey");
      expect(f.body).not.toContain("X-VTEX-API-AppToken");
    }
  });

  test("the session file is written owner-only", () => {
    const session = files.find((f) => f.name === "session.ts");
    expect(session).toBeDefined();
    expect(session?.body).toContain("0o600");
  });

  test("no password authentication path exists", () => {
    // classic/validate is VTEX's email+password endpoint. Supporting it would
    // mean a reusable secret passing through a terminal; one-time codes do the
    // same job without that.
    for (const f of files) {
      expect(f.body).not.toContain("classic/validate");
    }
  });
});
