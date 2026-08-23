import type { Event, State, TypeRecord } from "../core/types";

/**
 * A WhatsApp storefront. Chosen because it carries a hard accounting identity:
 * conservation invariants are the nearest thing to a free Coq kernel in a
 * business domain, and they catch a drifting generated world faster than any
 * semantic check.
 */
interface Shop extends State {
  inventory: Record<string, number>;
  price: Record<string, number>;
  cash_cents: number;
  payments_cents: number;
  refunds_cents: number;
  promised: Array<{ order: string; sku: string; qty: number }>;
  paid: string[];
  fulfilled: string[];
}

const initial: Shop = {
  inventory: { arepa_kit: 12, cafe_500g: 4, panela: 0 },
  price: { arepa_kit: 32000, cafe_500g: 48000, panela: 9000 },
  cash_cents: 0,
  payments_cents: 0,
  refunds_cents: 0,
  promised: [],
  paid: [],
  fulfilled: [],
};

function transition(state: State, e: Event): State {
  const s = structuredClone(state) as Shop;
  const p = e.params as Record<string, never>;
  const sku = p.sku as unknown as string;
  const order = p.order as unknown as string;
  const qty = (p.qty as unknown as number) ?? 1;

  switch (e.action) {
    case "promise":
      s.promised.push({ order, sku, qty });
      return s;
    case "pay": {
      const cents = (p.cents as unknown as number) ?? 0;
      s.payments_cents += cents;
      s.cash_cents += cents;
      s.paid.push(order);
      return s;
    }
    case "refund": {
      const cents = (p.cents as unknown as number) ?? 0;
      s.refunds_cents += cents;
      s.cash_cents -= cents;
      return s;
    }
    case "fulfill": {
      const promise = s.promised.find((x) => x.order === order);
      if (promise) s.inventory[promise.sku] = (s.inventory[promise.sku] ?? 0) - promise.qty;
      s.fulfilled.push(order);
      return s;
    }
    case "restock":
      s.inventory[sku] = (s.inventory[sku] ?? 0) + qty;
      return s;
    case "reprice":
      s.price[sku] = p.cents as unknown as number;
      return s;
    default:
      return s;
  }
}

export const storefront: TypeRecord = {
  slug: "whatsapp-storefront",
  title: "WhatsApp storefront",
  initial,
  actions: [
    {
      name: "promise",
      actor: "sales-agent",
      params: { order: "string", sku: "string", qty: "number" },
    },
    {
      name: "pay",
      actor: "customer",
      params: { order: "string", cents: "number" },
      units: { cents: "COP_cents" },
    },
    {
      name: "refund",
      actor: "sales-agent",
      params: { order: "string", cents: "number" },
      units: { cents: "COP_cents" },
    },
    { name: "fulfill", actor: "ops", params: { order: "string" } },
    {
      name: "restock",
      actor: "ops",
      params: { sku: "string", qty: "number" },
      units: { qty: "units" },
    },
    {
      name: "reprice",
      actor: "sales-agent",
      params: { sku: "string", cents: "number" },
      units: { cents: "COP_cents" },
    },
  ],
  invariants: [
    {
      name: "inventory_nonneg",
      kind: "conservation",
      check: (st) => {
        const s = st as Shop;
        const bad = Object.entries(s.inventory).filter(([, q]) => q < 0);
        return bad.length === 0 ? null : `oversold ${bad.map(([k, q]) => `${k}:${q}`).join(", ")}`;
      },
    },
    {
      name: "cash_conserved",
      kind: "conservation",
      check: (st) => {
        const s = st as Shop;
        const expected = s.payments_cents - s.refunds_cents;
        return s.cash_cents === expected
          ? null
          : `cash ${s.cash_cents} != payments-refunds ${expected}`;
      },
    },
    {
      name: "no_unpaid_fulfillment",
      kind: "safety",
      check: (st) => {
        const s = st as Shop;
        const unpaid = s.fulfilled.filter((o) => !s.paid.includes(o));
        return unpaid.length === 0 ? null : `fulfilled without payment: ${unpaid.join(", ")}`;
      },
    },
    {
      name: "no_phantom_promise",
      kind: "policy",
      check: (st) => {
        const s = st as Shop;
        const phantom = s.promised.filter((pr) => (s.inventory[pr.sku] ?? 0) < pr.qty);
        return phantom.length === 0
          ? null
          : `promised stock that does not exist: ${phantom.map((x) => `${x.order}/${x.sku}`).join(", ")}`;
      },
    },
  ],
  transition,
};
