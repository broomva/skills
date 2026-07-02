/**
 * Minimal Socrata SODA client for datos.gov.co.
 *
 * Dependency-free (uses global fetch). Adds an app token from
 * SODA_APP_TOKEN / GASGO_SODA_TOKEN when present to lift the anonymous
 * throttle; works without one for low-volume use.
 */

export const DATOS_GOV_BASE = "https://www.datos.gov.co/resource";

export interface SocrataParams {
  // SoQL clauses, e.g. { $where: "anio_precio='2026'", $limit: "5000" }
  [key: string]: string | number | undefined;
}

export interface SocrataOptions {
  base?: string;
  appToken?: string;
  /** Abort after this many ms (default 20000). */
  timeoutMs?: number;
  /** Injectable fetch for tests. */
  fetchImpl?: typeof fetch;
}

function resolveToken(explicit?: string): string | undefined {
  return (
    explicit ??
    process.env.SODA_APP_TOKEN ??
    process.env.GASGO_SODA_TOKEN ??
    undefined
  );
}

/**
 * Fetch rows from a Socrata dataset resource.
 * @param datasetId 4x4 resource id, e.g. "he3q-86dn"
 */
export async function socrataFetch<T = Record<string, string>>(
  datasetId: string,
  params: SocrataParams = {},
  opts: SocrataOptions = {},
): Promise<T[]> {
  const base = opts.base ?? DATOS_GOV_BASE;
  const url = new URL(`${base}/${datasetId}.json`);
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined) url.searchParams.set(k, String(v));
  }

  const token = resolveToken(opts.appToken);
  const headers: Record<string, string> = { Accept: "application/json" };
  if (token) headers["X-App-Token"] = token;

  const doFetch = opts.fetchImpl ?? fetch;
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? 20000);
  try {
    const res = await doFetch(url.toString(), { headers, signal: controller.signal });
    if (!res.ok) {
      const body = await res.text().catch(() => "");
      throw new Error(`Socrata ${datasetId} HTTP ${res.status}: ${body.slice(0, 200)}`);
    }
    return (await res.json()) as T[];
  } finally {
    clearTimeout(timer);
  }
}
