import { DEFAULTS } from "./constants.ts";

/**
 * Cookie jar.
 *
 * Two ways to get a session:
 *
 *  - `bootstrap()` — fetch the public storefront page once and keep the cookies the
 *    server sets. That mints an *implicit guest* session, which is enough for every
 *    read operation (deals, collections, item lookup). No login, no personal data.
 *
 *  - `importCookieHeader()` — paste your own browser's `Cookie:` header. Needed only
 *    for operations bound to your account (cart, lists, orders).
 *
 * Session material is written 0600 and is gitignored. It is never logged.
 */
export type Jar = Record<string, string>;

const SESSION_PATH = () =>
  `${process.env.HOME}/.config/cub-cli/session.json`;

export function parseSetCookie(headers: Headers): Jar {
  const jar: Jar = {};
  // getSetCookie() preserves multiple Set-Cookie headers; a joined string would corrupt
  // cookies whose values contain commas (Expires dates do).
  const raw = typeof (headers as any).getSetCookie === "function"
    ? (headers as any).getSetCookie()
    : [];
  for (const line of raw as string[]) {
    const pair = line.split(";")[0];
    const i = pair.indexOf("=");
    if (i > 0) jar[pair.slice(0, i).trim()] = pair.slice(i + 1).trim();
  }
  return jar;
}

export function jarToHeader(jar: Jar): string {
  return Object.entries(jar)
    .map(([k, v]) => `${k}=${v}`)
    .join("; ");
}

export function parseCookieHeader(header: string): Jar {
  const jar: Jar = {};
  for (const part of header.split(";")) {
    const i = part.indexOf("=");
    if (i > 0) jar[part.slice(0, i).trim()] = part.slice(i + 1).trim();
  }
  return jar;
}

export async function loadSession(): Promise<Jar | null> {
  try {
    const f = Bun.file(SESSION_PATH());
    if (!(await f.exists())) return null;
    return (await f.json()) as Jar;
  } catch {
    return null;
  }
}

export async function saveSession(jar: Jar): Promise<void> {
  const path = SESSION_PATH();
  await Bun.write(path, JSON.stringify(jar, null, 1));
  // Session material is credentials. Do not leave it world-readable.
  await Bun.$`chmod 600 ${path}`.quiet().nothrow();
}

/** Mint a guest session by loading the public storefront once. */
export async function bootstrap(): Promise<Jar> {
  const res = await fetch(`${DEFAULTS.origin}/store/${DEFAULTS.retailerSlug}/storefront`, {
    headers: { "user-agent": DEFAULTS.userAgent, accept: "text/html" },
    redirect: "follow",
  });
  if (!res.ok) throw new Error(`bootstrap failed: HTTP ${res.status}`);
  const jar = parseSetCookie(res.headers);
  await res.arrayBuffer(); // drain
  if (Object.keys(jar).length === 0) throw new Error("bootstrap set no cookies");
  await saveSession(jar);
  return jar;
}

/** Return a usable session, minting a guest one if none is stored. */
export async function ensureSession(): Promise<Jar> {
  return (await loadSession()) ?? (await bootstrap());
}
