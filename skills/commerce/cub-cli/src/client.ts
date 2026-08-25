import { DEFAULTS, MIN_REQUEST_INTERVAL_MS } from "./constants.ts";
import { getOp } from "./ops.ts";
import { ensureSession, jarToHeader, parseSetCookie, saveSession, type Jar } from "./session.ts";

export class GraphQLError extends Error {
  constructor(message: string, readonly status: number, readonly body: unknown) {
    super(message);
  }
}

let lastRequestAt = 0;

/** Serialize requests with a floor on the gap between them. Personal-use pacing. */
async function pace(): Promise<void> {
  const wait = lastRequestAt + MIN_REQUEST_INTERVAL_MS - Date.now();
  if (wait > 0) await Bun.sleep(wait);
  lastRequestAt = Date.now();
}

export type CallOptions = { retryOnAuth?: boolean };

/**
 * Call a captured operation via Apollo APQ.
 *
 * Transport is GET with three query params: operationName, variables, and
 * extensions.persistedQuery.sha256Hash — mirroring exactly what the storefront sends.
 */
export async function call<T = unknown>(
  operationName: string,
  variables: Record<string, unknown>,
  opts: CallOptions = {},
): Promise<T> {
  const op = await getOp(operationName);
  let jar: Jar = await ensureSession();

  const send = async (cookieJar: Jar) => {
    const url = new URL(DEFAULTS.endpoint);
    url.searchParams.set("operationName", operationName);
    url.searchParams.set("variables", JSON.stringify(variables));
    url.searchParams.set(
      "extensions",
      JSON.stringify({ persistedQuery: { version: 1, sha256Hash: op.sha256Hash } }),
    );
    await pace();
    return fetch(url, {
      headers: {
        accept: "*/*",
        "content-type": "application/json",
        "user-agent": DEFAULTS.userAgent,
        cookie: jarToHeader(cookieJar),
        referer: `${DEFAULTS.origin}/store/${DEFAULTS.retailerSlug}/storefront`,
      },
    });
  };

  let res = await send(jar);

  // A stale guest session reads as 401. Re-mint once, then give up — an authenticated
  // operation cannot be rescued by a guest session, and retrying would just loop.
  if (res.status === 401 && opts.retryOnAuth !== false) {
    const { bootstrap } = await import("./session.ts");
    jar = await bootstrap();
    res = await send(jar);
  }

  // Keep any refreshed cookies.
  const refreshed = parseSetCookie(res.headers);
  if (Object.keys(refreshed).length) {
    await saveSession({ ...jar, ...refreshed });
  }

  const text = await res.text();
  let body: any;
  try {
    body = JSON.parse(text);
  } catch {
    throw new GraphQLError(
      `${operationName}: non-JSON response (HTTP ${res.status})`,
      res.status,
      text.slice(0, 300),
    );
  }

  if (body?.errors?.length) {
    const msg = body.errors.map((e: any) => e.message).join("; ");
    if (/not authenticated/i.test(msg)) {
      throw new GraphQLError(
        `${operationName}: Not Authenticated.\n` +
          `This operation is bound to a logged-in account. Import your browser session:\n` +
          `  cub auth import   (then paste your Cookie: header)`,
        res.status,
        body,
      );
    }
    throw new GraphQLError(`${operationName}: ${msg}`, res.status, body);
  }

  if (!res.ok) throw new GraphQLError(`${operationName}: HTTP ${res.status}`, res.status, body);
  return body.data as T;
}
