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
  type SavedAddress,
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
    availableAddresses?: Array<Record<string, unknown>>;
    selectedAddresses?: Array<Record<string, unknown>>;
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
 * The parts of a Colombian address VTEX stores separately.
 *
 * `street` alone is not enough for an apartment. A courier needs the unit in
 * `complement` and the building/conjunto name somewhere it will be read —
 * `neighborhood` or `reference` — or the parcel arrives at the gate with
 * nowhere to go.
 */
/**
 * Read the customer's saved address book off an orderForm.
 *
 * `availableAddresses` is empty on a FRESHLY CREATED orderForm — which is why
 * probing a new cart reports zero even for an account that has addresses. Pass
 * the customer's existing cart id.
 */
export async function listAddresses(
  client: D1Client,
  orderFormId: string,
): Promise<SavedAddress[]> {
  const w = await client.request<WireOrderForm>(`/api/checkout/pub/orderForm/${orderFormId}`);
  return (w.shippingData?.availableAddresses ?? []).map((a) => {
    const g = (k: string) => {
      const v = a[k];
      return typeof v === "string" && v !== "" ? v : undefined;
    };
    return {
      addressId: String(a.addressId ?? ""),
      addressType: g("addressType"),
      receiverName: g("receiverName"),
      street: g("street"),
      number: g("number"),
      complement: g("complement"),
      neighborhood: g("neighborhood"),
      city: g("city"),
      state: g("state"),
      postalCode: g("postalCode"),
      geoCoordinates: Array.isArray(a.geoCoordinates) ? (a.geoCoordinates as number[]) : undefined,
      // A record with no street is one VTEX minted from bare coordinates —
      // the CLI itself used to create one on every deliver-to call.
      complete: Boolean(g("street")),
    };
  });
}

/**
 * Attach one of the customer's OWN saved addresses to a cart.
 *
 * Looks the record up in `availableAddresses` and posts it back whole. Sending
 * just the `addressId` does not work — VTEX ignores it and selects a fresh
 * empty address, which is both wrong and another junk record. Verified live.
 *
 * Preferred over supplying an address by hand: D1 canonicalizes through its own
 * map picker, so the stored record carries a resolved street/number, the real
 * neighborhood, a postal code and D1's own coordinates. Free text gets none of
 * that.
 */
export async function useSavedAddress(
  client: D1Client,
  orderFormId: string,
  addressId: string,
): Promise<Cart> {
  const saved = await listAddresses(client, orderFormId);
  const hit = saved.find((a) => a.addressId === addressId || a.addressId.startsWith(addressId));
  if (!hit) {
    throw new D1Error(
      `No saved address matches "${addressId}". Run \`d1 addresses\` to list them.`,
    );
  }
  if (!hit.complete) {
    throw new D1Error(
      `Saved address ${hit.addressId.slice(0, 12)} has no street — it is an incomplete record, not a usable address.`,
    );
  }
  const w = await client.request<WireOrderForm>(
    `/api/checkout/pub/orderForm/${orderFormId}/attachments/shippingData`,
    {
      method: "POST",
      body: JSON.stringify({
        selectedAddresses: [
          {
            addressId: hit.addressId,
            addressType: hit.addressType ?? "residential",
            country: "COL",
            receiverName: hit.receiverName,
            street: hit.street,
            number: hit.number,
            complement: hit.complement,
            neighborhood: hit.neighborhood,
            city: hit.city,
            state: hit.state,
            postalCode: hit.postalCode,
            geoCoordinates: hit.geoCoordinates,
          },
        ],
      }),
    },
  );
  return normalizeCart(w);
}

/**
 * Make the cart's delivery point correct before an add, WITHOUT minting a
 * new address record.
 *
 * Two constraints pull against each other here:
 *
 *  - VTEX evaluates deliverability at ADD time against whatever address the
 *    orderForm holds, and a stale one leaves permanent `cannotBeDelivered`
 *    errors that no later correction clears. So the address must be right
 *    beforehand.
 *  - Posting an address without an `addressId` MINTS a new record in the
 *    customer's address book. Doing that on every add produced one junk entry
 *    per item.
 *
 * The resolution: if the cart already carries an address at the intended
 * point, leave it alone — it is already correct, and re-posting it would only
 * create litter. Re-post only when the address is absent or somewhere else,
 * and reuse its `addressId` when there is one so VTEX updates instead of
 * minting.
 */
export async function ensureDeliveryPoint(
  client: D1Client,
  orderFormId: string,
  at: LatLng,
): Promise<Cart | undefined> {
  const current = await client.request<WireOrderForm>(`/api/checkout/pub/orderForm/${orderFormId}`);
  const sel = (current.shippingData?.selectedAddresses ?? [])[0];
  const geo = Array.isArray(sel?.geoCoordinates) ? (sel?.geoCoordinates as number[]) : undefined;

  // ~11 m at this latitude — far tighter than a store catchment, loose enough
  // that float round-tripping through JSON does not read as a move.
  const SAME = 1e-4;
  if (geo && Math.abs(geo[0] - at.lng) < SAME && Math.abs(geo[1] - at.lat) < SAME) {
    return undefined; // already correct; touching it would only mint
  }

  const existingId = typeof sel?.addressId === "string" ? sel.addressId : undefined;
  return setDeliveryPoint(client, orderFormId, at, { addressId: existingId });
}

export interface DeliveryAddress {
  /**
   * Reuse an existing saved address instead of minting a new one.
   *
   * Sending this id ALONE is not enough — verified against a live account:
   * VTEX ignored it and selected a fresh empty record. The whole saved record
   * has to be posted back, which is what `useSavedAddress` does. Callers
   * should prefer that helper over setting this by hand.
   */
  addressId?: string;
  postalCode?: string;
  city?: string;
  state?: string;
  /** Street line, e.g. `Cra 13 # 172a-51`. */
  street?: string;
  /** House/building number, when it is not already in `street`. */
  number?: string;
  /** Tower + apartment, e.g. `Torre 1 Apto 2102`. */
  complement?: string;
  neighborhood?: string;
  /** Free-text landmark or conjunto name for the courier. */
  reference?: string;
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
  at: LatLng | undefined,
  opts: DeliveryAddress = {},
): Promise<Cart> {
  if (!at && !opts.addressId) {
    throw new D1Error("A delivery point needs coordinates or a saved --address-id.");
  }
  const w = await client.request<WireOrderForm>(
    `/api/checkout/pub/orderForm/${orderFormId}/attachments/shippingData`,
    {
      method: "POST",
      body: JSON.stringify({
        selectedAddresses: [
          {
            addressId: opts.addressId,
            addressType: "residential",
            country: "COL",
            // VTEX takes [longitude, latitude] here — the reverse of how the
            // regions endpoint is usually read, and the opposite order from
            // every mapping UI. See region.ts for the matching gotcha.
            //
            // Omitted entirely when reusing a saved address: the stored record
            // already carries D1's own canonical coordinates, which are better
            // than any we could supply, and overwriting them with ours would
            // undo the canonicalization that made the record worth reusing.
            geoCoordinates: at ? [at.lng, at.lat] : undefined,
            postalCode: opts.postalCode,
            city: opts.city,
            state: opts.state,
            street: opts.street,
            number: opts.number,
            // Where an apartment actually goes. Cramming "T1-2102" into
            // `street` puts it on the address line, but couriers and D1's own
            // checkout read `complement` for the unit — without it a delivery
            // reaches the building and stops.
            complement: opts.complement,
            neighborhood: opts.neighborhood,
            reference: opts.reference,
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
