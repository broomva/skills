/**
 * Which cart is this CLI allowed to write to?
 *
 * ## The failure this exists to stop
 *
 * Twice this CLI made unrequested writes to a real customer account, and both
 * times the operation looked read-shaped to the operator. The second was the
 * clearer one: a verification run of an unrelated fix executed
 * `cart add 1287 1000 262` against the customer's LIVE cart, because the config
 * directory already had that cart's id stored and pointing at it was
 * convenient. A carton of milk sat in the basket, deliverable and priced, until
 * the customer asked why it was there. They would have paid for it.
 *
 * Nothing distinguished "the cart this CLI created for me" from "a cart id that
 * happens to be sitting in the config file". `session.json` is a plain file:
 * any id written into it by any means was honoured in silence.
 *
 * ## Why a guard rather than more care
 *
 * The failure mode is *forgetting to isolate*, and it happens precisely when
 * attention is on something else — both incidents were committed by someone
 * actively being careful about this class of problem. A convention is only as
 * strong as the operator's attention at the moment it lapses; a structural
 * check does not depend on remembering.
 *
 * ## How ownership is decided
 *
 * When the CLI obtains a cart itself it stores a keyed fingerprint next to the
 * id. On load, an id whose fingerprint does not verify is EXTERNAL — which is
 * exactly what a hand-edited or injected id looks like, because whoever wrote
 * it did not compute the fingerprint.
 *
 * This is not a security boundary. Anyone who reads this file can forge a
 * fingerprint, and that is fine: it is here to stop an accident, not an
 * adversary. The person it protects against is the author, in a hurry.
 */

import { createHmac } from "node:crypto";

/**
 * Fixed key. Deliberately not a secret — see the note above about accidents
 * versus adversaries. It exists so that an id written by something other than
 * this CLI is *distinguishable*, not unforgeable.
 */
const OWNERSHIP_KEY = "d1-cli/cart-ownership/v1";

/** Fingerprint proving this CLI obtained the cart itself. */
export function fingerprint(orderFormId: string): string {
  return createHmac("sha256", OWNERSHIP_KEY).update(orderFormId).digest("hex").slice(0, 32);
}

export function isOwned(orderFormId: string | undefined, stored: string | undefined): boolean {
  if (!orderFormId || !stored) return false;
  return stored === fingerprint(orderFormId);
}

/** Commands that change a cart. Reads are deliberately not guarded. */
export const MUTATING_CART_SUBCOMMANDS = ["add", "set", "clear", "deliver-to"] as const;

export function isMutating(sub: string): boolean {
  return (MUTATING_CART_SUBCOMMANDS as readonly string[]).includes(sub);
}

/**
 * True when this run must not touch persistent state at all.
 *
 * The mode verification runs should use: any stored cart is ignored, a fresh
 * one is created, and nothing is written back. A test pointed at a populated
 * config directory then *cannot* reach the real cart, rather than merely being
 * unlikely to.
 */
export function isScratch(env: NodeJS.ProcessEnv = process.env): boolean {
  const v = env.D1_SCRATCH;
  return v === "1" || v === "true";
}
