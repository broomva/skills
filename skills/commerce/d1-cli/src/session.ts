/**
 * Authentication and local session storage.
 *
 * ## Why there is no password flow
 *
 * D1's VTEX ID endpoint advertises both `showClassicAuthentication` (email +
 * password) and `showAccessKeyAuthentication` (emailed one-time code). Only the
 * second is implemented here. A one-time code is worth strictly less if it
 * leaks, expires on its own, and never asks the user to type a reusable secret
 * into a terminal that may be logged, screen-shared, or driven by an agent.
 * Supporting passwords would add credential surface and buy nothing.
 *
 * ## What is stored
 *
 * A storefront session token — the same `VtexIdclientAutCookie_d1tiendas` value
 * a browser holds. It grants exactly what the website grants a logged-in
 * shopper: their own profile, their own orders, their own cart. It is not an
 * admin key and cannot read other customers. It is written to a 0600 file under
 * the user's config directory and is never logged, printed, or included in
 * error messages.
 */

import { chmodSync, existsSync, mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { homedir } from "node:os";
import { dirname, join } from "node:path";
import type { D1Client } from "./client.ts";
import { ACCOUNT, D1Error, ORIGIN } from "./types.ts";

export interface StoredSession {
  /** VTEX storefront session token. Sensitive. */
  token: string;
  /** Whose session this is, so `d1 whoami` can answer without a round trip. */
  email?: string;
  /** Sticky cart id. */
  orderFormId?: string;
  /**
   * Proof this CLI obtained `orderFormId` itself. An id present without a
   * verifying fingerprint is treated as EXTERNAL and refused for writes —
   * see `ownership.ts` for why that distinction exists.
   */
  orderFormOwn?: string;
  /** Last resolved delivery point, so search defaults to somewhere real. */
  region?: { id: string; lat: number; lng: number; sellerId?: string };
  savedAt: string;
}

export function sessionPath(): string {
  const base =
    process.env.D1_CONFIG_DIR ?? process.env.XDG_CONFIG_HOME ?? join(homedir(), ".config");
  return join(base, "d1-cli", "session.json");
}

export function loadSession(path = sessionPath()): StoredSession | undefined {
  try {
    if (!existsSync(path)) return undefined;
    return JSON.parse(readFileSync(path, "utf8")) as StoredSession;
  } catch {
    // A corrupt session file should degrade to "logged out", not crash every
    // command including the ones that would let the user fix it.
    return undefined;
  }
}

/** Persist the session with owner-only permissions. */
export function saveSession(s: StoredSession, path = sessionPath()): void {
  mkdirSync(dirname(path), { recursive: true, mode: 0o700 });
  writeFileSync(path, JSON.stringify(s, null, 2), { mode: 0o600 });
  // writeFileSync's mode is ignored when the file already exists, so the
  // permissions are asserted explicitly rather than assumed.
  chmodSync(path, 0o600);
}

export function clearSession(path = sessionPath()): void {
  if (existsSync(path)) writeFileSync(path, "{}", { mode: 0o600 });
}

// ---------------------------------------------------------------------------
// Access-key (one-time code) login
// ---------------------------------------------------------------------------

/**
 * Begin authentication. Returns the opaque `authenticationToken` that ties the
 * "send me a code" and "here is my code" calls together.
 */
export async function startAuth(client: D1Client): Promise<string> {
  const w = await client.request<{
    authenticationToken?: string;
    showAccessKeyAuthentication?: boolean;
  }>("/api/vtexid/pub/authentication/start", {
    query: { scope: ACCOUNT, callbackUrl: `${ORIGIN}/` },
  });
  if (!w.authenticationToken) {
    throw new D1Error("D1 did not return an authentication token.");
  }
  if (w.showAccessKeyAuthentication === false) {
    throw new D1Error(
      "D1 has disabled one-time-code sign-in. Sign in at d1.com.co in a browser and use `d1 login --from-cookie` instead.",
    );
  }
  return w.authenticationToken;
}

/** Ask D1 to email a one-time code. */
export async function sendAccessKey(
  client: D1Client,
  authToken: string,
  email: string,
): Promise<void> {
  await client.request("/api/vtexid/pub/authentication/accesskey/send", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      authenticationToken: authToken,
      email,
    }).toString(),
  });
}

/**
 * Exchange the emailed code for a session token.
 *
 * VTEX signals a bad code with HTTP 200 and `authStatus: "WrongCredentials"`
 * rather than an error status, so the status check in the transport layer will
 * not catch it — the body has to be inspected.
 */
export async function validateAccessKey(
  client: D1Client,
  authToken: string,
  email: string,
  code: string,
): Promise<{ token: string; email: string }> {
  const w = await client.request<{
    authStatus?: string;
    authCookie?: { Name?: string; Value?: string };
  }>("/api/vtexid/pub/authentication/accesskey/validate", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      login: email,
      accesskey: code,
      authenticationToken: authToken,
    }).toString(),
  });

  if (w.authStatus && w.authStatus !== "Success") {
    throw new D1Error(
      w.authStatus === "WrongCredentials"
        ? "That code was not accepted. Codes expire quickly — request a new one."
        : `Sign-in failed (${w.authStatus}).`,
    );
  }
  const token = w.authCookie?.Value;
  if (!token) throw new D1Error("Sign-in succeeded but D1 returned no session token.");
  return { token, email };
}

// ---------------------------------------------------------------------------
// Identity
// ---------------------------------------------------------------------------

export interface Identity {
  userId: string;
  email: string;
  account: string;
}

/** Confirm a token is live and whose it is. Returns undefined when signed out. */
export async function whoami(client: D1Client): Promise<Identity | undefined> {
  try {
    const w = await client.request<{
      userId?: string;
      user?: string;
      account?: string;
    }>("/api/vtexid/pub/authenticated/user");
    if (!w?.userId) return undefined;
    return {
      userId: w.userId,
      email: w.user ?? "",
      account: w.account ?? ACCOUNT,
    };
  } catch {
    return undefined;
  }
}

/**
 * Validate a token pasted from a browser session.
 *
 * The escape hatch for accounts where one-time codes are unavailable (social
 * sign-in, corporate SSO). The token is checked against the live endpoint
 * before it is stored, so a mistyped paste fails now rather than on the next
 * command.
 */
export async function adoptToken(client: D1Client, token: string): Promise<Identity> {
  const trimmed = token.trim().replace(/^VtexIdclientAutCookie[^=]*=/, "");
  client.authToken = trimmed;
  const id = await whoami(client);
  if (!id) {
    throw new D1Error(
      "That token is not a valid D1 session. Copy the full value of the `VtexIdclientAutCookie_d1tiendas` cookie from a signed-in browser.",
    );
  }
  return id;
}
