/**
 * Order history.
 *
 * Reads through `/api/oms/user/orders`, which is scoped by the session token to
 * the signed-in customer. Note that D1's saved addresses and profile record are
 * *not* reachable: the Master Data endpoints a VTEX admin would use answer 403
 * "Cannot filter by private fields" for a storefront token. Addresses surface
 * only as part of an order or the live cart, so that is where the CLI reads
 * them from.
 */

import type { D1Client } from "./client.ts";
import { D1Error, type OrderSummary } from "./types.ts";

/** Human-readable labels for the VTEX order lifecycle, in Colombian Spanish. */
const STATUS_LABELS: Record<string, string> = {
  "order-created": "Creado",
  "on-order-completed": "Confirmado",
  "payment-pending": "Pago pendiente",
  "payment-approved": "Pago aprobado",
  "ready-for-handling": "En preparación",
  handling: "En preparación",
  "start-handling": "En preparación",
  invoiced: "Facturado / enviado",
  canceled: "Cancelado",
  cancel: "Cancelado",
};

export function statusLabel(status: string): string {
  return STATUS_LABELS[status] ?? status;
}

interface WireOrderList {
  list?: Array<{
    orderId: string;
    status?: string;
    creationDate?: string;
    totalValue?: number;
    items?: unknown[];
    ItemsQuantity?: number;
  }>;
  paging?: { total?: number; pages?: number; currentPage?: number };
}

export async function listOrders(
  client: D1Client,
  opts: { page?: number; perPage?: number } = {},
): Promise<{ orders: OrderSummary[]; total: number; pages: number }> {
  if (!client.authenticated) {
    throw new D1Error("Order history needs a signed-in session. Run `d1 login`.");
  }
  const w = await client.request<WireOrderList>("/api/oms/user/orders", {
    query: {
      page: Math.max(1, opts.page ?? 1),
      per_page: Math.min(50, Math.max(1, opts.perPage ?? 15)),
    },
  });

  const orders: OrderSummary[] = (w.list ?? []).map((o) => ({
    orderId: o.orderId,
    status: o.status ?? "",
    statusLabel: statusLabel(o.status ?? ""),
    creationDate: o.creationDate ?? "",
    total: o.totalValue ?? 0,
    itemCount: o.ItemsQuantity ?? o.items?.length ?? 0,
  }));

  return {
    orders,
    total: w.paging?.total ?? orders.length,
    pages: w.paging?.pages ?? 1,
  };
}

/** Full detail for one order, including its delivery address and line items. */
export async function getOrder(client: D1Client, orderId: string): Promise<unknown> {
  if (!client.authenticated) {
    throw new D1Error("Order detail needs a signed-in session. Run `d1 login`.");
  }
  return client.request(`/api/oms/user/orders/${encodeURIComponent(orderId)}`);
}
