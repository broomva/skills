/**
 * HTTP transport for the D1 storefront.
 *
 * Everything the CLI does goes through VTEX's *public* (`/pub/`) storefront
 * endpoints — the same ones the website calls from the browser. There is no
 * admin API key anywhere in this codebase: a storefront session token is the
 * highest privilege it ever holds, which caps the blast radius of a leaked
 * config file at "can see my own orders".
 */

import { assertAllowedPath } from "./endpoints.ts";
import { ACCOUNT, D1Error, ORIGIN } from "./types.ts";

/** Presented to upstream so D1 can identify (and if it wishes, throttle) us. */
const USER_AGENT =
  "d1-cli/0.1.0 (+https://github.com/broomva/skills; broomva/skills commerce/d1-cli)";

export interface ClientOptions {
  /**
   * VTEX storefront session token — the value of the
   * `VtexIdclientAutCookie_d1tiendas` cookie. Absent for anonymous use, which
   * covers the entire catalogue and cart surface.
   */
  authToken?: string;
  /** Sticky cart id, sent as the `checkout.vtex.com` cookie. */
  orderFormId?: string;
  /** Per-request timeout. */
  timeoutMs?: number;
  /** Override for tests. Defaults to the global `fetch`. */
  fetchImpl?: typeof fetch;
}

export class D1Client {
  private readonly timeoutMs: number;
  private readonly doFetch: typeof fetch;
  authToken?: string;
  orderFormId?: string;

  constructor(opts: ClientOptions = {}) {
    this.authToken = opts.authToken;
    this.orderFormId = opts.orderFormId;
    this.timeoutMs = opts.timeoutMs ?? 30_000;
    this.doFetch = opts.fetchImpl ?? globalThis.fetch;
  }

  get authenticated(): boolean {
    return Boolean(this.authToken);
  }

  private cookieHeader(): string | undefined {
    const jar: string[] = [];
    if (this.authToken) {
      // VTEX accepts the token under both the account-scoped and generic names;
      // sending the account-scoped one alone is what the storefront does.
      jar.push(`VtexIdclientAutCookie_${ACCOUNT}=${this.authToken}`);
    }
    if (this.orderFormId) {
      jar.push(`checkout.vtex.com=__ofid=${this.orderFormId}`);
    }
    return jar.length ? jar.join("; ") : undefined;
  }

  /**
   * Issue a request and parse JSON.
   *
   * `path` is relative to the storefront origin. Non-2xx responses are turned
   * into `D1Error` carrying the upstream status and, when VTEX supplies one,
   * its error code — those codes are the only reliable way to distinguish
   * "you typed a bad address" from "this store is closed".
   */
  async request<T>(
    path: string,
    init: RequestInit & { query?: Record<string, string | number | undefined> } = {},
  ): Promise<T> {
    const url = new URL(path, ORIGIN);

    // Enforce the endpoint allowlist HERE, on the resolved pathname, because
    // this is the last point before the request leaves and the only place that
    // sees what will actually be sent. `new URL()` has already collapsed any
    // `..`, so a facet or channel argument crafted to climb out of its
    // endpoint — which really did reach the order-settlement endpoint from
    // `d1 search --facets ../../../..` — is caught here even though every
    // string literal in the source was approved.
    assertAllowedPath(url.pathname, path);

    for (const [k, v] of Object.entries(init.query ?? {})) {
      if (v !== undefined && v !== "") url.searchParams.set(k, String(v));
    }

    const headers = new Headers(init.headers);
    headers.set("Accept", "application/json");
    headers.set("User-Agent", USER_AGENT);
    // VTEX's router rejects some checkout mutations without a same-origin
    // referer, so it is set for every call rather than only where it is known
    // to matter.
    headers.set("Referer", `${ORIGIN}/`);
    if (init.body && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    const cookie = this.cookieHeader();
    if (cookie) headers.set("Cookie", cookie);

    const ctrl = new AbortController();
    const timer = setTimeout(() => ctrl.abort(), this.timeoutMs);
    let res: Response;
    try {
      res = await this.doFetch(url.toString(), {
        ...init,
        headers,
        signal: ctrl.signal,
      });
    } catch (err) {
      const aborted = err instanceof Error && err.name === "AbortError";
      throw new D1Error(
        aborted
          ? `Timed out after ${this.timeoutMs}ms calling ${path}`
          : `Network failure calling ${path}: ${err}`,
        { url: url.toString() },
      );
    } finally {
      clearTimeout(timer);
    }

    const text = await res.text();
    let parsed: unknown;
    try {
      parsed = text ? JSON.parse(text) : null;
    } catch {
      parsed = null;
    }

    if (!res.ok) {
      throw new D1Error(describeFailure(res.status, parsed, path), {
        status: res.status,
        code: errorCode(parsed),
        url: url.toString(),
      });
    }
    return parsed as T;
  }
}

/** Pull VTEX's machine-readable error code out of an error body, if present. */
export function errorCode(body: unknown): string | undefined {
  if (body && typeof body === "object") {
    const e = (body as { error?: { code?: string } }).error;
    if (e?.code) return e.code;
  }
  return undefined;
}

/**
 * Turn an upstream failure into something a human can act on.
 *
 * The generic status-code text is kept as a suffix so nothing is hidden, but
 * the cases we have actually hit in practice get a specific remedy, because
 * "403" on its own tells the user nothing about which of the several possible
 * causes they are looking at.
 */
export function describeFailure(status: number, body: unknown, path: string): string {
  const code = errorCode(body);
  const upstream =
    body && typeof body === "object"
      ? ((body as { error?: { message?: string }; Message?: string }).error?.message ??
        (body as { Message?: string }).Message)
      : undefined;

  if (code === "CHK0119") {
    return "D1 could not resolve that delivery point. Pass coordinates as --lat/--lng, or a Colombian postal code.";
  }
  if (status === 401) {
    return "Not signed in, or the session expired. Run `d1 login` again.";
  }
  if (status === 403) {
    return `D1 refused this request (${path}). Storefront sessions cannot read this data; this is a limit of the public API, not a bug in the CLI.`;
  }
  if (status === 404) {
    return `Not found: ${path}.`;
  }
  if (status === 429) {
    return "D1 is rate-limiting this client. Wait a minute and retry.";
  }
  if (status >= 500) {
    return `D1 returned a server error (${status}). This is upstream; retry shortly.`;
  }
  return `D1 request failed (${status}${code ? ` ${code}` : ""})${upstream ? `: ${upstream}` : ""}`;
}
