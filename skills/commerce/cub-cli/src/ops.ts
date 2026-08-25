import opsData from "../data/ops.json" with { type: "json" };

export type Operation = {
  sha256Hash: string;
  sampleVariables: Record<string, unknown>;
  capturedFrom: string;
};

type Registry = {
  _provenance: Record<string, string>;
  operations: Record<string, Operation>;
};

const HARVEST_PATH = () => `${process.env.HOME}/.config/cub-cli/harvested-ops.json`;

let cache: Record<string, Operation> | null = null;

/**
 * The operation registry IS the capability surface.
 *
 * The endpoint is persisted-query-only — it rejects raw queries and introspection with
 * PERSISTED_QUERY_NOT_SUPPORTED — so this client can call exactly the operations whose
 * sha256 hashes have been observed in real traffic, and no others. Shipped hashes come
 * from the storefront's own SSR record; more are added with `cub harvest`.
 */
export async function registry(): Promise<Record<string, Operation>> {
  if (cache) return cache;
  const base = { ...(opsData as Registry).operations };
  try {
    const f = Bun.file(HARVEST_PATH());
    if (await f.exists()) Object.assign(base, await f.json());
  } catch {
    /* harvested file is optional */
  }
  cache = base;
  return base;
}

export async function getOp(name: string): Promise<Operation> {
  const reg = await registry();
  const op = reg[name];
  if (!op) {
    throw new Error(
      `No captured hash for operation "${name}".\n` +
        `The endpoint only accepts persisted queries, so this operation cannot be called ` +
        `until its hash is observed in real traffic.\n` +
        `Fix: reproduce the action in your browser with DevTools open, save the Network ` +
        `tab as a .har, then run:  cub harvest --har <file.har>`,
    );
  }
  return op;
}

export async function saveHarvested(ops: Record<string, Operation>): Promise<void> {
  const path = HARVEST_PATH();
  let existing: Record<string, Operation> = {};
  try {
    const f = Bun.file(path);
    if (await f.exists()) existing = await f.json();
  } catch {
    /* fresh file */
  }
  const merged = { ...existing, ...ops };
  await Bun.write(path, JSON.stringify(merged, null, 1));
  cache = null; // force reload
}

export function provenance(): Record<string, string> {
  return (opsData as Registry)._provenance;
}
