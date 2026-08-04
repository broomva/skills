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
    // ASSUMED hundredths, matching every other checkout-side field. NOT
    // empirically confirmed: the account this was built against has no D1
    // order history, so there was no real `totalValue` to check. Every other
    // unit claim in this codebase was verified against live data; this one is
    // inference from the surrounding API. If order totals ever read 100x high,
    // this line is why.
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

/**
 * The leaf fields of a VTEX order that `d1 order` may print.
 *
 * ## Why an allowlist, and why the blocklist had to go
 *
 * This was a `SENSITIVE_KEYS` blocklist: it named `document`, `phone`, `street`
 * and a dozen more, redacted those, and printed everything else. That is an
 * **allowlist by omission** — every key the author did not think of prints in
 * full, and the author cannot think of the keys they have never seen. The
 * account this was built against has no completed D1 order, so the real payload
 * has *never been observed*; the blocklist was a guess about the contents of an
 * envelope nobody had opened, and every wrong guess failed towards disclosure.
 *
 * `test/safety.test.ts` was rewritten to eliminate exactly this shape for
 * endpoints. It survived here.
 *
 * Inverted, the failure direction flips: an unanticipated key is redacted. A
 * field missing from this list costs a reader one `--raw`; a field missing from
 * a blocklist costs the customer their national ID. Only one of those is
 * recoverable.
 *
 * ## Paths, not bare key names
 *
 * Matching bare names would let an allowlisted `name` or `value` print wherever
 * it appeared, including under a key added later that happens to nest one. Each
 * entry is a full dotted path with array indices collapsed to `[]`, so
 * `items[].name` prints and `clientProfileData.name` would not.
 *
 * ## This list is provisional
 *
 * Derived from VTEX's documented OMS order schema, not from an observed D1
 * order — BRO-2077 wants one real payload to confirm the useful fields are
 * actually reachable. Being wrong here now means over-redacting, which is the
 * survivable direction and what `--raw` is for.
 *
 * Note what is deliberately absent: **all of `clientProfileData`**. Nothing in
 * it — not the first name, not the corporate name — is needed to answer "where
 * is my order?", so none of it is worth the risk of printing by default.
 */
const PRINTABLE_PATHS = new Set([
  // The order's own identity and lifecycle.
  "orderId",
  "sequence",
  "status",
  "statusDescription",
  "creationDate",
  "lastChange",
  "orderGroup",
  "salesChannel",
  "origin",
  "isCompleted",
  "allowCancellation",
  "allowEdition",
  "cancelReason",
  "currencyCode",
  "value",
  // Money, broken out.
  "totals[].id",
  "totals[].name",
  "totals[].value",
  // What was bought.
  "items[].id",
  "items[].uniqueId",
  "items[].productId",
  "items[].refId",
  "items[].ean",
  "items[].name",
  "items[].skuName",
  "items[].quantity",
  "items[].seller",
  "items[].price",
  "items[].listPrice",
  "items[].sellingPrice",
  "items[].measurementUnit",
  "items[].unitMultiplier",
  "items[].imageUrl",
  "items[].detailUrl",
  "items[].isGift",
  "items[].additionalInfo.brandName",
  "items[].additionalInfo.categories[].id",
  "items[].additionalInfo.categories[].name",
  // Delivery, to the resolution a shopper needs — a city, never a doorstep.
  "shippingData.address.city",
  "shippingData.address.state",
  "shippingData.address.country",
  "shippingData.address.addressType",
  "shippingData.logisticsInfo[].itemIndex",
  "shippingData.logisticsInfo[].selectedSla",
  "shippingData.logisticsInfo[].deliveryChannel",
  "shippingData.logisticsInfo[].shippingEstimate",
  "shippingData.logisticsInfo[].shippingEstimateDate",
  "shippingData.logisticsInfo[].price",
  "shippingData.logisticsInfo[].slas[].id",
  "shippingData.logisticsInfo[].slas[].name",
  "shippingData.logisticsInfo[].slas[].shippingEstimate",
  "shippingData.logisticsInfo[].slas[].price",
  "shippingData.logisticsInfo[].slas[].deliveryChannel",
  // How it was paid — the instrument's NAME, never its digits.
  "paymentData.transactions[].payments[].paymentSystem",
  "paymentData.transactions[].payments[].paymentSystemName",
  "paymentData.transactions[].payments[].value",
  "paymentData.transactions[].payments[].installments",
  "paymentData.transactions[].payments[].referenceValue",
  // Where the parcel is.
  "packageAttachment.packages[].courier",
  "packageAttachment.packages[].invoiceNumber",
  "packageAttachment.packages[].invoiceValue",
  "packageAttachment.packages[].issuanceDate",
  "packageAttachment.packages[].trackingNumber",
  "packageAttachment.packages[].trackingUrl",
  // Store-level formatting, which carries nothing personal.
  "storePreferencesData.countryCode",
  "storePreferencesData.currencyCode",
  "storePreferencesData.currencyLocale",
  "storePreferencesData.timeZone",
]);

/**
 * The allowlist as a tree, so a path is matched SEGMENT by segment.
 *
 * The dotted strings above are for reading. Matching them by string comparison
 * would be unsound, because a JSON key may itself contain a `.` or a `[]` and a
 * concatenated path cannot tell a key's own characters from a nesting boundary.
 * A payload with a key literally named `shippingData.address.city` therefore
 * built the path `shippingData.address.city` at the ROOT and printed — the
 * allowlist failing open on the one direction it exists to close.
 *
 * One key is one segment here, so nothing can be forged by naming.
 */
interface PathNode {
  /** A value ending here may print. */
  printable: boolean;
  children: Map<string, PathNode>;
}

/** `items[].name` → `["items", "[]", "name"]`. */
function segmentsOf(path: string): string[] {
  const out: string[] = [];
  for (const part of path.split(".")) {
    if (part.endsWith("[]")) {
      out.push(part.slice(0, -2), "[]");
    } else {
      out.push(part);
    }
  }
  return out;
}

const PRINTABLE_TREE: PathNode = (() => {
  const root: PathNode = { printable: false, children: new Map() };
  for (const path of PRINTABLE_PATHS) {
    let node = root;
    for (const seg of segmentsOf(path)) {
      let next = node.children.get(seg);
      if (!next) {
        next = { printable: false, children: new Map() };
        node.children.set(seg, next);
      }
      node = next;
    }
    node.printable = true;
  }
  return root;
})();

/**
 * Assign without letting a key named `__proto__` be swallowed.
 *
 * Plain `out[k] = v` on `__proto__` sets the prototype instead of defining an
 * own property, so the key vanished from the output entirely — no disclosure,
 * but the operator could not tell it had ever been there, which breaks the
 * "obviously censored rather than mysteriously incomplete" promise below.
 */
function define(out: Record<string, unknown>, key: string, value: unknown): void {
  Object.defineProperty(out, key, {
    value,
    enumerable: true,
    writable: true,
    configurable: true,
  });
}

/**
 * Recursively replace every value not named in {@link PRINTABLE_PATHS} with
 * `"[redacted]"`.
 *
 * Containers are always traversed rather than redacted whole, so the output
 * keeps the payload's shape and stays obviously censored instead of
 * mysteriously incomplete. Only leaves are subject to the allowlist — which
 * means a *new* leaf under an already-known object is redacted too, not just a
 * new top-level key. `d1 order --raw` opts out of all of it.
 *
 * `null` and `undefined` pass through unredacted: they disclose nothing, and
 * turning them into the string `"[redacted]"` would invent a value where the
 * payload said there was none.
 */
function redactAt(value: unknown, node: PathNode | undefined): unknown {
  if (value === null || value === undefined) return value;
  if (typeof value === "object") {
    // Walk only where something printable lies below. A container with no
    // printable descendant — including one sitting where a SCALAR was expected,
    // which is a live risk for a payload nobody has observed — is withheld
    // whole, so neither its keys, its depth, nor its length is published.
    if (!node || node.children.size === 0) return "[redacted]";
    if (Array.isArray(value)) {
      const each = node.children.get("[]");
      return value.map((v) => redactAt(v, each));
    }
    const out: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value as Record<string, unknown>)) {
      define(out, k, redactAt(v, node.children.get(k)));
    }
    return out;
  }
  return node?.printable === true ? value : "[redacted]";
}

export function redactOrder(value: unknown): unknown {
  return redactAt(value, PRINTABLE_TREE);
}

/**
 * Choose what `d1 order` prints.
 *
 * Extracted so the DEFAULT is testable. `redactOrder` was thoroughly tested,
 * but nothing bound it to the CLI: replacing `raw ? detail : redactOrder(detail)`
 * with plain `detail` left all 155 tests green while shipping the customer's
 * national ID, phone, address and card digits to stdout by default.
 */
export function orderForDisplay(detail: unknown, raw: boolean): unknown {
  return raw ? detail : redactOrder(detail);
}
