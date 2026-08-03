/**
 * The write guard, tested from the incident that produced it.
 *
 * A verification run of an unrelated fix executed `cart add 1287 1000 262`
 * against a customer's LIVE cart, because the config directory already held
 * that cart's id. A carton of milk sat in the basket, deliverable and priced,
 * until the customer asked why. Care did not prevent it — the person who did it
 * was actively being careful about this exact class of problem — so the guard
 * has to be structural.
 */

import { describe, expect, test } from "bun:test";
import {
  MUTATING_CART_SUBCOMMANDS,
  fingerprint,
  isMutating,
  isOwned,
  isScratch,
} from "../src/ownership.ts";

describe("ownership fingerprint", () => {
  test("a cart the CLI obtained verifies as owned", () => {
    const id = "756cf316a0054803b021add75d299f9f";
    expect(isOwned(id, fingerprint(id))).toBe(true);
  });

  test("an id written into the config by hand is NOT owned", () => {
    // This is the incident, reduced: someone puts a real cart id into
    // session.json without the fingerprint, and every mutation then lands on
    // a stranger's basket in silence.
    expect(isOwned("756cf316a0054803b021add75d299f9f", undefined)).toBe(false);
    expect(isOwned("756cf316a0054803b021add75d299f9f", "")).toBe(false);
  });

  test("a fingerprint from a DIFFERENT cart does not transfer", () => {
    // Copying session.json between config dirs must not launder ownership.
    expect(isOwned("cart-a", fingerprint("cart-b"))).toBe(false);
  });

  test("the fingerprint is deterministic and does not leak the id", () => {
    const id = "756cf316a0054803b021add75d299f9f";
    expect(fingerprint(id)).toBe(fingerprint(id));
    expect(fingerprint(id)).not.toContain(id);
  });

  test("no cart means nothing to own", () => {
    expect(isOwned(undefined, "whatever")).toBe(false);
  });
});

describe("which commands are guarded", () => {
  test("every cart-mutating subcommand is covered", () => {
    for (const sub of ["add", "set", "clear", "deliver-to"]) {
      expect(isMutating(sub)).toBe(true);
    }
  });

  test("reads are NOT guarded", () => {
    // Blocking reads would train people to reach for --yes reflexively, which
    // would defeat the guard on the writes that matter.
    for (const sub of ["show", "checkout"]) {
      expect(isMutating(sub)).toBe(false);
    }
  });

  test("the guarded list matches the cart subcommands that write", () => {
    // Anti-drift: a new mutating subcommand must be added here deliberately.
    expect([...MUTATING_CART_SUBCOMMANDS].sort().join(",")).toBe("add,clear,deliver-to,set");
  });
});

describe("scratch mode", () => {
  test("recognises the documented values", () => {
    expect(isScratch({ D1_SCRATCH: "1" })).toBe(true);
    expect(isScratch({ D1_SCRATCH: "true" })).toBe(true);
  });

  test("is OFF by default, and off for anything else", () => {
    // Fail-safe direction: an unset or odd value must not silently make a real
    // run ephemeral, which would look like the cart mysteriously emptying.
    expect(isScratch({})).toBe(false);
    expect(isScratch({ D1_SCRATCH: "0" })).toBe(false);
    expect(isScratch({ D1_SCRATCH: "" })).toBe(false);
    expect(isScratch({ D1_SCRATCH: "yes" })).toBe(false);
  });
});
