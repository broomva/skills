/**
 * Cart (VTEX "orderForm") operations, and the boundary where this CLI stops.
 *
 * ## Where this stops
 *
 * The CLI builds a basket, prices it against a real store, and quotes shipping.
 * It does not pay. There is no code path here that accepts a card number, sends
 * `paymentData`, or calls `gatewayCallback` — the last mile is handed to a human
 * via {@link checkoutUrl}, who finishes in a browser with D1's own payment form.
 *
 * That is a structural choice, not an unfinished one. An agent that can both
 * assemble and settle a purchase can spend real money on a hallucinated basket;
 * an agent that can only assemble one is bounded by a human reading a total
 * before they click pay. `test/safety.test.ts` asserts the payment surface stays
 * absent, so the boundary fails loudly if someone later adds it by reflex.
 */

import type { D1Client } from "./client.ts";
import {
  type Cart,
  type CartItem,
  type CartMessage,
  D1Error,
  DEFAULT_SALES_CHANNEL,
  type LatLng,
  ORIGIN,
  type PriceHundredths,
  type ShippingOption,
} from "./types.ts";

// ---------------------------------------------------------------------------
// Wire shapes (partial)
// ---------------------------------------------------------------------------

interface WireOrderForm {
  orderFormId: string;
  loggedIn?: boolean;
  value?: number;
  items?: Array<{
    id: string;
    name?: string;
    quantity?: number;
    seller?: string;
    sellingPrice?: number;
    priceDefinition?: { total?: number };
  }>;
  totalizers?: Array<{ id: string; value?: number }>;
  messages?: Array<{ text?: string; code?: string; status?: string }>;
  shippingData?: {
    logisticsInfo?: Array<{
      itemIndex?: number;
      slas?: Array<{
        id?: string;
        name?: string;
        price?: number;
        shippingEstimate?: string;
      }>;
    }>;
  };
}

// ---------------------------------------------------------------------------
// Normalization
// ---------------------------------------------------------------------------

/**
 * Collapse the per-line shipping quotes into one row per delivery option.
 *
 * VTEX repeats `logisticsInfo` once per cart line, and each entry's
 * `slas[].price` is that LINE'S SHARE of the option's cost — not the option's
 * cost. Deduplicating by id and showing the first share under-reports shipping
 * by a factor of the line count. Measured at one point, same day, same SLA:
 *
 *   lines   slas[].price   x lines
 *     1        13,500      13,500
 *     2         6,750      13,500
 *     4         3,375      13,500
 *    12         1,125      13,500
 *
 * Shipping is a flat COP 13,500; the CLI was showing 1,125 of it. So the shares
 * are SUMMED per option, which is exact for every n measured and agrees with
 * the orderForm's own `Shipping` totalizer.
 *
 * This is the same trap as `simulation`'s per-unit `price` (README gotcha 4): a
 * VTEX field that reads as a total and is a component. Both are invisible to a
 * fixture with one line, because one share IS the total.
 */
function collapseShipping(
  logisticsInfo: Array<{
    slas?: Array<{ id?: string; name?: string; price?: number; shippingEstimate?: string }>;
  }>,
): ShippingOption[] {
  const byId = new Map<string, ShippingOption>();
  for (const li of logisticsInfo) {
    for (const s of li.slas ?? []) {
      const id = s.id ?? s.name ?? "";
      if (!id) continue;
      const existing = byId.get(id);
      if (existing) {
        existing.price += s.price ?? 0;
      } else {
        byId.set(id, {
          id,
          name: s.name ?? id,
          price: s.price ?? 0,
          estimate: s.shippingEstimate ?? "",
        });
      }
    }
  }
  return [...byId.values()];
}

export function normalizeCart(w: WireOrderForm): Cart {
  const logistics = w.shippingData?.logisticsInfo;
  const items: CartItem[] = (w.items ?? []).map((i, idx) => {
    // Deliverability comes from logisticsInfo, NOT from messages.
    //
    // Proven with both polarities against production, same cart, same item,
    // only the address changed:
    //
    //   deliverable address   -> slas: [["Entrega Programada"]]   messages: []
    //   unserved address      -> slas: [[]]                        messages: [cannotBeDelivered]
    //
    // An EMPTY slas array is the live, recomputed verdict. The message merely
    // correlates — and it is STICKY: it survives `items/removeAll` and a
    // re-add, so a line that is currently fine still carries the old error.
    // Blocking on the message therefore refuses healthy carts, which is how
    // the first version of this guard behaved.
    const li = logistics?.find((l) => l.itemIndex === idx) ?? logistics?.[idx];
    return {
      skuId: i.id,
      name: i.name ?? "(unnamed)",
      quantity: i.quantity ?? 0,
      sellerId: i.seller ?? "",
      sellingPrice: i.sellingPrice ?? 0,
      total: i.priceDefinition?.total ?? (i.sellingPrice ?? 0) * (i.quantity ?? 0),
      deliverable: li ? (li.slas ?? []).length > 0 : undefined,
    };
  });

  const itemsTotal =
    w.totalizers?.find((t) => t.id === "Items")?.value ?? items.reduce((a, i) => a + i.total, 0);

  const shipping = collapseShipping(w.shippingData?.logisticsInfo ?? []);

  // Promotions arrive as their own totalizer. Reading only `Items` and `value`
  // renders a promoted cart as "Items 20.000 / Total 15.000" with nothing
  // accounting for the gap — no wrong number, but an unexplained one on the
  // surface where a shopper checks the arithmetic.
  const discounts = w.totalizers?.find((t) => t.id === "Discounts")?.value ?? 0;

  return {
    orderFormId: w.orderFormId,
    loggedIn: Boolean(w.loggedIn),
    items,
    itemsTotal,
    discounts,
    total: w.value ?? itemsTotal,
    shipping,
    messages: (w.messages ?? [])
      .map((m) => ({
        text: m.text ?? m.code ?? "",
        code: m.code ?? "",
        status: (m.status === "error" || m.status === "warning" ? m.status : "info") as
          | "error"
          | "warning"
          | "info",
      }))
      .filter((m) => m.text),
  };
}

// ---------------------------------------------------------------------------
// Operations
// ---------------------------------------------------------------------------

/**
 * Fetch the client's current cart, creating one if it has none.
 *
 * `POST` (not `GET`) is what creates-or-returns; a bare `GET` 404s when no cart
 * cookie is present. The resulting id is written back onto the client so
 * subsequent calls in the same process stay on the same cart.
 */
export async function getCart(
  client: D1Client,
  salesChannel = DEFAULT_SALES_CHANNEL,
): Promise<Cart> {
  const w = await client.request<WireOrderForm>("/api/checkout/pub/orderForm", {
    method: "POST",
    body: "{}",
    query: { sc: salesChannel },
  });
  client.orderFormId = w.orderFormId;
  return normalizeCart(w);
}

/**
 * Lines upstream currently offers no way to deliver.
 *
 * Read from each line's own logistics entry, never from `messages` — those are
 * sticky and report conditions that have since been fixed. A line with an empty
 * `slas` array is one D1 will not ship to the selected address right now.
 *
 * Lines with `deliverable === undefined` are NOT included: no delivery point has
 * been set, so nothing has been refused. Treating "not yet quoted" as "refused"
 * would block every cart before `deliver-to` runs.
 */
export function undeliverable(cart: Cart): CartItem[] {
  return cart.items.filter((i) => i.deliverable === false);
}

export interface AddItem {
  skuId: string;
  quantity: number;
  /**
   * Fulfilling seller. For a regionalized basket this is the physical store id
   * from `resolveRegion` (e.g. `d1bon11808cc`), not the notional national
   * seller `1`.
   */
  sellerId: string;
}

export async function addItems(
  client: D1Client,
  orderFormId: string,
  items: AddItem[],
  salesChannel = DEFAULT_SALES_CHANNEL,
): Promise<Cart> {
  if (items.length === 0) throw new D1Error("No items to add.");
  for (const i of items) {
    if (!Number.isInteger(i.quantity) || i.quantity < 1) {
      throw new D1Error(
        `Quantity for SKU ${i.skuId} must be a positive whole number, got ${i.quantity}.`,
      );
    }
  }
  const w = await client.request<WireOrderForm>(
    `/api/checkout/pub/orderForm/${orderFormId}/items`,
    {
      method: "POST",
      query: { sc: salesChannel },
      body: JSON.stringify({
        orderItems: items.map((i) => ({
          id: i.skuId,
          quantity: i.quantity,
          seller: i.sellerId,
        })),
      }),
    },
  );
  return normalizeCart(w);
}

/**
 * Set the quantity of an existing line by its position in the cart.
 *
 * VTEX addresses lines by index, not SKU, so callers must read the cart first —
 * indexes shift whenever a line is removed. Quantity 0 removes the line.
 */
export async function setQuantity(
  client: D1Client,
  orderFormId: string,
  index: number,
  quantity: number,
  salesChannel = DEFAULT_SALES_CHANNEL,
): Promise<Cart> {
  if (!Number.isInteger(index) || index < 0) {
    throw new D1Error(`Item index must be a non-negative integer, got ${index}.`);
  }
  if (!Number.isInteger(quantity) || quantity < 0) {
    throw new D1Error(`Quantity must be zero or a positive whole number, got ${quantity}.`);
  }
  const w = await client.request<WireOrderForm>(
    `/api/checkout/pub/orderForm/${orderFormId}/items/update`,
    {
      method: "POST",
      query: { sc: salesChannel },
      body: JSON.stringify({ orderItems: [{ index, quantity }] }),
    },
  );
  return normalizeCart(w);
}

/** Remove every line. */
export async function clearCart(client: D1Client, orderFormId: string): Promise<Cart> {
  const w = await client.request<WireOrderForm>(
    `/api/checkout/pub/orderForm/${orderFormId}/items/removeAll`,
    { method: "POST", body: "{}" },
  );
  return normalizeCart(w);
}

/**
 * Attach a delivery point so upstream will quote shipping.
 *
 * Until this is set, `shippingData` is null and the cart carries no SLAs — the
 * total shown is items-only and will not be what the customer pays.
 */
export async function setDeliveryPoint(
  client: D1Client,
  orderFormId: string,
  at: LatLng,
  opts: { postalCode?: string; city?: string; state?: string; street?: string } = {},
): Promise<Cart> {
  const w = await client.request<WireOrderForm>(
    `/api/checkout/pub/orderForm/${orderFormId}/attachments/shippingData`,
    {
      method: "POST",
      body: JSON.stringify({
        selectedAddresses: [
          {
            addressType: "residential",
            country: "COL",
            // VTEX takes [longitude, latitude] here — the reverse of how the
            // regions endpoint is usually read, and the opposite order from
            // every mapping UI. See region.ts for the matching gotcha.
            geoCoordinates: [at.lng, at.lat],
            postalCode: opts.postalCode,
            city: opts.city,
            state: opts.state,
            street: opts.street,
          },
        ],
      }),
    },
  );
  return normalizeCart(w);
}

export interface SimulatedItem {
  skuId: string;
  quantity: number;
  available: boolean;
  /** Price for one unit. */
  unitPrice: PriceHundredths;
  /** Price for the whole line — `unitPrice * quantity`, net of promotions. */
  total: PriceHundredths;
}

export interface SimulationResult {
  items: SimulatedItem[];
  /**
   * SKUs that were asked for but that upstream did not answer for at all —
   * they do not exist in D1's catalogue. Distinct from a SKU that exists but
   * is out of stock, which appears in `items` with `available: false`.
   */
  unknownSkus: string[];
  /** What checkout would charge for the goods, before shipping. */
  itemsTotal: PriceHundredths;
  shipping: ShippingOption[];
}

/**
 * Price a hypothetical basket without touching the customer's cart.
 *
 * This is the honest way to answer "what would this cost?" — it runs the same
 * availability and pricing logic as checkout but leaves no state behind.
 */
export async function simulate(
  client: D1Client,
  items: AddItem[],
  at: LatLng,
  opts: { regionId?: string; salesChannel?: string } = {},
): Promise<SimulationResult> {
  const w = await client.request<{
    items?: Array<{
      id: string;
      availability?: string;
      quantity?: number;
      price?: number;
      priceDefinition?: { total?: number };
    }>;
    totals?: Array<{ id: string; value?: number }>;
    logisticsInfo?: Array<{
      slas?: Array<{
        id?: string;
        name?: string;
        price?: number;
        shippingEstimate?: string;
      }>;
    }>;
  }>("/api/checkout/pub/orderForms/simulation", {
    method: "POST",
    query: {
      sc: opts.salesChannel ?? DEFAULT_SALES_CHANNEL,
      regionId: opts.regionId,
    },
    body: JSON.stringify({
      items: items.map((i) => ({
        id: i.skuId,
        quantity: i.quantity,
        seller: i.sellerId,
      })),
      country: "COL",
      geoCoordinates: [at.lng, at.lat],
    }),
  });

  const shipping = collapseShipping(w.logisticsInfo ?? []);

  const returned = new Set((w.items ?? []).map((i) => i.id));
  // A SKU upstream simply omits does not exist in this catalogue. Left
  // unreported it becomes an empty result that every availability check passes
  // vacuously — "is this buyable?" would answer yes for a product D1 has never
  // heard of.
  const unknownSkus = items.map((i) => i.skuId).filter((id) => !returned.has(id));

  const simItems = (w.items ?? []).map((i) => {
    const quantity = i.quantity ?? 1;
    const unitPrice = i.price ?? 0;
    return {
      skuId: i.id,
      quantity,
      available: i.availability === "available",
      unitPrice,
      // `price` is per unit; the line total lives in priceDefinition. Summing
      // the unit prices would silently ignore quantity — a basket of 2x milk
      // would be quoted as 1x.
      total: i.priceDefinition?.total ?? unitPrice * quantity,
    };
  });

  return {
    items: simItems,
    unknownSkus,
    // Prefer upstream's own Items totalizer; it is what checkout will charge,
    // and it already accounts for promotions our per-line sum cannot see.
    itemsTotal:
      w.totals?.find((t) => t.id === "Items")?.value ??
      simItems.filter((i) => i.available).reduce((a, i) => a + i.total, 0),
    shipping,
  };
}

/**
 * The URL a human opens to review and pay for this cart.
 *
 * This is the handoff point. Everything up to here is automatable; what happens
 * on the other side of this link is deliberately not.
 */
export function checkoutUrl(orderFormId: string): string {
  return `${ORIGIN}/checkout/?orderFormId=${orderFormId}#/cart`;
}
