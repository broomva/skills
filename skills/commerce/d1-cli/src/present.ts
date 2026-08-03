/**
 * Rendering for the two audiences this CLI has.
 *
 * A human at a terminal wants aligned columns and pesos. An agent wants JSON it
 * can branch on. Every command supports `--json`, and the two paths share the
 * same normalized structs so they can never disagree about what was found.
 *
 * Rendering never invents a number. Where upstream gave us nothing — a price
 * with no region resolved, a cart with no delivery point — that is said plainly
 * rather than shown as zero.
 */

import { discountPercent, formatCOP } from "./money.ts";
import type {
  Cart,
  Category,
  Facet,
  OrderSummary,
  Product,
  Region,
  SearchPage,
  ShippingOption,
} from "./types.ts";

export function json(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

/** Pad to a display width, truncating with an ellipsis when too long. */
function pad(s: string, width: number): string {
  const clean = s.replace(/\s+/g, " ").trim();
  if (clean.length <= width) return clean.padEnd(width);
  return `${clean.slice(0, Math.max(0, width - 1))}…`;
}

/**
 * The cheapest available offer, or the cheapest offer overall when nothing is
 * in stock — so an out-of-stock row still shows what it would cost.
 */
export function bestOffer(p: Product) {
  const available = p.offers.filter((o) => o.available);
  const pool = available.length ? available : p.offers;
  return pool.slice().sort((a, b) => a.price - b.price)[0];
}

export function renderSearch(page: SearchPage, opts: { regionId?: string } = {}): string {
  if (page.products.length === 0) {
    return "No products matched.";
  }
  const lines: string[] = [];
  for (const p of page.products) {
    const o = bestOffer(p);
    const price = o ? formatCOP(o.price) : "—";
    const off = o ? discountPercent(o.price, o.listPrice) : 0;
    const stock = !o ? "no offer" : o.available ? "" : "out of stock";
    const tail = [off > 0 ? `-${off}%` : "", stock].filter(Boolean).join("  ");
    lines.push(
      `${pad(p.skuId, 8)} ${pad(p.name, 52)} ${price.padStart(10)}${tail ? `  ${tail}` : ""}`,
    );
  }

  const shown = page.products.length;
  lines.push("");
  lines.push(
    `${shown} shown · ${page.total} match${page.total === 1 ? "" : "es"}${
      page.truncated ? " (only the first 50 pages are reachable — narrow with --facets)" : ""
    }`,
  );
  if (!opts.regionId) {
    lines.push(
      "Prices are national. Pass --lat/--lng for the availability and price at your nearest store.",
    );
  }
  return lines.join("\n");
}

export function renderRegion(r: Region): string {
  if (r.sellers.length === 0) {
    return `No D1 store serves ${r.at.lat}, ${r.at.lng}. D1 does not deliver to this point.`;
  }
  const lines = [`Region ${r.id}`, `Delivering to ${r.at.lat}, ${r.at.lng} from:`];
  for (const s of r.sellers) lines.push(`  ${s.id}  ${s.name}`);
  return lines.join("\n");
}

export function renderShipping(options: ShippingOption[]): string {
  if (options.length === 0) return "No shipping options quoted.";
  return options
    .map(
      (s) =>
        `  ${pad(s.name, 28)} ${formatCOP(s.price).padStart(10)}  ${humanEstimate(s.estimate)}`,
    )
    .join("\n");
}

/** Turn VTEX's `3bd` / `24h` shorthand into words. */
export function humanEstimate(e: string): string {
  const m = /^(\d+)(bd|d|h|m)$/.exec(e.trim());
  if (!m) return e;
  const n = Number(m[1]);
  const unit = { bd: "business day", d: "day", h: "hour", m: "minute" }[m[2]] ?? m[2];
  return `${n} ${unit}${n === 1 ? "" : "s"}`;
}

export function renderCart(c: Cart): string {
  if (c.items.length === 0) return "Cart is empty.";
  const lines: string[] = [];
  c.items.forEach((i, idx) => {
    lines.push(
      `${String(idx).padStart(2)}  ${pad(i.name, 46)} ×${String(i.quantity).padStart(3)} ${formatCOP(i.total).padStart(11)}`,
    );
  });
  lines.push("");
  lines.push(`Items    ${formatCOP(c.itemsTotal).padStart(11)}`);
  if (c.discounts !== 0) {
    lines.push(`Savings  ${formatCOP(c.discounts).padStart(11)}`);
  }
  if (c.shipping.length > 0) {
    lines.push("Shipping options:");
    lines.push(renderShipping(c.shipping));
  } else {
    lines.push("Shipping not quoted — set a delivery point with `d1 cart deliver-to`.");
  }
  lines.push(`Total    ${formatCOP(c.total).padStart(11)}`);

  // Errors go ABOVE the total, not below it. They used to print last, after the
  // total and the checkout URL, so a cart whose every line D1 had refused to
  // deliver still read as ready to pay.
  // Blocked lines come from the lines themselves, not from `messages` — those
  // are sticky and keep reporting conditions that have since been fixed.
  const blocked = c.items.filter((i) => i.deliverable === false);
  if (blocked.length) {
    lines.splice(
      lines.length - (c.shipping.length ? c.shipping.length + 2 : 1) - 1,
      0,
      "",
      `!! ${blocked.length} line${blocked.length === 1 ? "" : "s"} CANNOT be delivered to this address:`,
      ...blocked.map((i) => `   ${i.name}`),
      "!! This cart is not safe to check out.",
      "",
    );
  }
  // Upstream notices are still shown, but never as the blocking signal. A
  // `cannotBeDelivered` whose line now HAS a delivery option is stale, so it is
  // labelled rather than presented as a live failure.
  const stale = blocked.length === 0;
  for (const m of c.messages) {
    if (lines[lines.length - 1] !== "") lines.push("");
    lines.push(m.status === "error" && stale ? `  (stale notice: ${m.text})` : `! ${m.text}`);
  }
  return lines.join("\n");
}

export function renderCategories(cats: Category[], indent = 0): string {
  const out: string[] = [];
  for (const c of cats) {
    out.push(`${"  ".repeat(indent)}${pad(c.slug, 34 - indent * 2)} ${c.name}`);
    if (c.children.length) out.push(renderCategories(c.children, indent + 1));
  }
  return out.join("\n");
}

export function renderFacets(facets: Facet[]): string {
  const out: string[] = [];
  for (const f of facets) {
    out.push(`${f.label}  (${f.key})`);
    for (const v of f.values.slice(0, 12)) {
      out.push(`  ${pad(`${f.key}/${v.value}`, 46)} ${String(v.quantity).padStart(5)}  ${v.label}`);
    }
    out.push("");
  }
  return out.join("\n").trimEnd();
}

export function renderOrders(orders: OrderSummary[]): string {
  if (orders.length === 0) return "No orders found on this account.";
  return orders
    .map(
      (o) =>
        `${pad(o.orderId, 22)} ${pad(o.creationDate.slice(0, 10), 12)} ${pad(o.statusLabel, 20)} ${formatCOP(o.total).padStart(11)}  ${o.itemCount} item${o.itemCount === 1 ? "" : "s"}`,
    )
    .join("\n");
}
