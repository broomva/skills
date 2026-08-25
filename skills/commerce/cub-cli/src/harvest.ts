import type { Operation } from "./ops.ts";

/**
 * Harvest persisted-query hashes from a HAR file.
 *
 * The endpoint accepts only persisted queries, so the set of callable operations is
 * exactly the set of hashes observed in real traffic. A HAR export from Chrome DevTools
 * is the most robust way to observe them: it needs no extension, no automation, and no
 * credentials beyond the session you are already logged into.
 *
 *   1. Open cub.com, DevTools → Network, filter `graphql`
 *   2. Perform the action you want the CLI to support (a search, an add-to-cart)
 *   3. Right-click the request list → "Save all as HAR with content"
 *   4. cub harvest --har <file.har>
 *
 * Only operationName + hash + variable *shape* are read. Cookies, auth headers and
 * response bodies in the HAR are ignored and never stored.
 */
export type HarvestResult = {
  operations: Record<string, Operation>;
  scanned: number;
  skipped: number;
};

/**
 * Reduce variables to their *shape*, discarding every concrete value.
 *
 * A HAR is a recording of a real session: its variables carry address ids, coordinates,
 * user ids and cart ids. Only the key structure is useful for documenting an operation,
 * so scalars are replaced by a type placeholder and never written to disk.
 */
function shapeOf(value: unknown, depth = 0): unknown {
  if (depth > 4) return "<…>";
  if (value === null) return null;
  if (Array.isArray(value)) return value.length ? [shapeOf(value[0], depth + 1)] : [];
  if (typeof value === "object") {
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value)) out[k] = shapeOf(v, depth + 1);
    return out;
  }
  return `<${typeof value}>`;
}

export function harvestFromHar(har: unknown): HarvestResult {
  const entries: any[] = (har as any)?.log?.entries ?? [];
  const operations: Record<string, Operation> = {};
  let scanned = 0;
  let skipped = 0;

  for (const entry of entries) {
    const url: string = entry?.request?.url ?? "";
    if (!url.includes("/graphql")) continue;
    scanned++;

    let operationName: string | null = null;
    let variables: Record<string, unknown> = {};
    let hash: string | null = null;

    try {
      if (entry.request.method === "GET") {
        const u = new URL(url);
        operationName = u.searchParams.get("operationName");
        const v = u.searchParams.get("variables");
        if (v) variables = JSON.parse(v);
        const ext = u.searchParams.get("extensions");
        if (ext) hash = JSON.parse(ext)?.persistedQuery?.sha256Hash ?? null;
      } else {
        const body = JSON.parse(entry.request?.postData?.text ?? "{}");
        const one = Array.isArray(body) ? body[0] : body;
        operationName = one?.operationName ?? null;
        variables = one?.variables ?? {};
        hash = one?.extensions?.persistedQuery?.sha256Hash ?? null;
      }
    } catch {
      skipped++;
      continue;
    }

    if (!operationName || !hash) {
      skipped++;
      continue;
    }
    // First occurrence wins — later ones carry the same hash by definition.
    operations[operationName] ??= {
      sha256Hash: hash,
      sampleVariables: shapeOf(variables) as Record<string, unknown>,
      capturedFrom: "har",
    };
  }

  return { operations, scanned, skipped };
}
