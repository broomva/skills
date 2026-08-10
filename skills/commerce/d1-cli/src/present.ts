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

import {
  type BasketComparison,
  type BasketLine,
  type BasketPlan,
  type BrandMiss,
  type CrossBasket,
  FILLED,
  type LineStatus,
  normalizeBrand,
} from "./basket.ts";
import { MAX_COUNT, bestOffer, pageCount, priced } from "./catalog.ts";
import { formatUnitPrice } from "./measure.ts";
import { discountPercent, formatCOP, sum } from "./money.ts";
import { MAX_REACHABLE, type StoresResult, hoursOn } from "./stores.ts";
import type { SubstituteResult } from "./substitute.ts";
import type {
  Cart,
  Category,
  Facet,
  LatLng,
  OrderSummary,
  Product,
  Region,
  SavedAddress,
  SearchPage,
  ShippingOption,
} from "./types.ts";

// Defined in `catalog.ts` — choosing which seller's offer represents a product
// is a catalogue decision, and `substitute.ts` needs it without rendering
// anything. Re-exported because this was its original home.
export { bestOffer };

export function json(value: unknown): string {
  return JSON.stringify(value, null, 2);
}

/**
 * Neutralize terminal control characters in upstream text.
 *
 * Every string rendered here — product names, brands, warning KEY NAMES, the
 * category path — is attacker-adjacent data from D1's catalogue, and
 * `asSearchShape` widened the warning source to any top-level key in the
 * payload. A name carrying `ESC[2J` clears the screen, erasing the
 * "Nothing was added to your cart" line above it; `ESC]0;…BEL` retitles the
 * window. In an agent-driven CLI the injected text also lands verbatim in a
 * transcript. `\s` does not cover ESC or BEL, so trimming was never enough.
 *
 * C0/C1 alone was not enough either. Three further classes defeat the same
 * stated purpose and are in range here:
 *
 *   U+2028 U+2029        line/paragraph separators. Many terminals and log
 *                        viewers break a line on these, so a product name can
 *                        forge an output line -- exactly what the newline case
 *                        guards against, reached by a different codepoint.
 *   U+202A-U+202E        bidi overrides. These visually REORDER the rendered
 *   U+2066-U+2069        line, so a name can make a price or a warning read as
 *                        something other than what it says.
 *   U+200B-U+200F U+FEFF zero-width and BOM. Invisible, and they break the
 *                        column arithmetic `pad` does on string length.
 */
/**
 * Written as `\u` escapes rather than literal bytes: a regex holding a raw ESC
 * is invisible in a diff and unreviewable.
 *
 * The suppression sits directly above the LITERAL, not above the `const`. The
 * escaped form is long enough that the formatter puts it on its own line, and a
 * `biome-ignore` one line further up silently stops applying — which is how the
 * rule ends up firing on a line everyone believes is suppressed.
 */
const CONTROL_CHARS =
  // biome-ignore lint/suspicious/noControlCharactersInRegex: neutralizing them is the point
  /[\u0000-\u001f\u007f-\u009f\u200b-\u200f\u2028\u2029\u202a-\u202e\u2060-\u2064\u2066-\u2069\ufeff]/g;

export function sanitize(s: string): string {
  return s.replace(CONTROL_CHARS, " ");
}

/** Pad to a display width, truncating with an ellipsis when too long. */
function pad(s: string, width: number): string {
  const clean = sanitize(s).replace(/\s+/g, " ").trim();
  if (clean.length <= width) return clean.padEnd(width);
  return `${clean.slice(0, Math.max(0, width - 1))}…`;
}

export function renderSearch(
  page: SearchPage,
  opts: { regionId?: string; perUnitSorted?: boolean } = {},
): string {
  if (page.products.length === 0) {
    return "No products matched.";
  }
  const lines: string[] = [];
  for (const p of page.products) {
    const o = bestOffer(p);
    // `priced`, not merely present: an offer VTEX reports at 0 has no price
    // here, and `$ 0` next to a real grocery item reads as free.
    const price = priced(o) ? formatCOP(o.price) : "—";
    // Guarded by the SAME predicate as the price beside it. Leaving this on a
    // bare truthiness check meant `{Price: 0, ListPrice: 9300}` rendered as
    // `—    -100%` — a discount computed from the very non-price the column to
    // its left had just declined to print, and a worse lie than the `$ 0` was.
    const off = priced(o) ? discountPercent(o.price, o.listPrice) : 0;
    const stock = !o ? "no offer" : o.available ? "" : "out of stock";
    const per =
      p.unitPrice !== undefined && p.size
        ? formatUnitPrice(formatCOP(p.unitPrice), p.size.measure)
        : "";
    const tail = [off > 0 ? `-${off}%` : "", stock].filter(Boolean).join("  ");
    lines.push(
      `${pad(p.skuId, 8)} ${pad(p.name, 44)} ${price.padStart(10)} ${per.padStart(13)}${tail ? `  ${tail}` : ""}`,
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
  if (opts.perUnitSorted) {
    const measures = new Set(page.products.filter((p) => p.size).map((p) => p.size?.measure));
    if (measures.size > 1) {
      lines.push(
        `Mixed measures in these results (${[...measures].join(", ")}) — only same-measure prices are comparable.`,
      );
    }
    // Said plainly because the alternative is a false superlative: this orders
    // the page that was fetched, not the whole result set.
    lines.push(
      `Sorted by unit price within these ${shown} results — not across all ${page.total}. Raise --count to widen it.`,
    );
  }
  // Counted on `size`, not on `unitPrice`. Since a product VTEX prices at 0
  // now yields no unit price either, counting the latter would report a
  // missing PACK SIZE for a product that publishes one perfectly well and
  // merely has no offer here — a sentence that is simply not true of it.
  const missing = page.products.filter((p) => p.size === undefined).length;
  if (missing > 0) {
    lines.push(`${missing} of ${shown} publish no pack size, so they cannot be compared per unit.`);
  }
  return lines.join("\n");
}

/** `$ 3.889/L`, or empty when D1 publishes no pack size. */
function perUnit(p: Product): string {
  return p.unitPrice !== undefined && p.size
    ? formatUnitPrice(formatCOP(p.unitPrice), p.size.measure)
    : "";
}

/**
 * Render a substitution proposal.
 *
 * The deltas are the point, not the ranking, so they get their own indented
 * lines under each candidate rather than being compressed into a column. A
 * shopper scanning this is deciding whether a 9% saving is worth a different
 * brand and an added sugar warning — that judgement needs the words.
 */
export function renderSubstitutes(r: SubstituteResult): string {
  const lines: string[] = [];
  const src = bestOffer(r.source);
  const srcPer = perUnit(r.source);

  lines.push(`Replacing ${sanitize(r.source.skuId)}  ${sanitize(r.source.name)}`);
  lines.push(
    `          ${[
      priced(src) ? formatCOP(src.price) : "no price at this store",
      srcPer,
      sanitize(r.source.brand),
    ]
      .filter(Boolean)
      .join(" · ")}`,
  );
  lines.push(`          ${sanitize(r.categoryPath)}`);
  if (r.source.warnings.length) {
    lines.push(`          ${r.source.warnings.map(sanitize).join(", ")}`);
  }
  lines.push("");

  // State the source's own stock plainly. It is usually the reason for running
  // this, and when it turns out to be in stock after all that is the single
  // most useful thing the command can say — the mandarin juice that started
  // this feature was available at one store and not another.
  //
  // Availability is a PER-STORE fact, so with no delivery point resolved there
  // is no store to assert it about. Saying "still in stock at your store" and
  // then "stock is NATIONAL and may not reflect your store" four lines later
  // is one output contradicting itself.
  if (!r.regionId) {
    // Deliberately says nothing here. The national-stock caveat belongs in
    // `scope` below, which prints on both the empty and non-empty paths — and
    // saying it in both places produced two near-identical sentences four
    // lines apart, which reads as a rendering bug rather than emphasis.
  } else if (r.sourcePricedNationally) {
    lines.push(
      "Priced from the national catalogue — this SKU was not on the regional page, so its stock here is unknown.",
    );
  } else if (r.sourceAvailable) {
    lines.push("This is still in stock at your store. You may not need a replacement.");
  } else {
    lines.push("D1 cannot supply this at your store right now.");
  }
  lines.push("");

  // The scope of the sweep is stated on BOTH paths.
  //
  // These lines used to sit after an early return, so the empty case made the
  // categorical claim "nothing in this category is in stock" while suppressing
  // the three facts that qualify it — that 3 of 140 products were compared,
  // that the search had widened, that stock was national. A negative asserted
  // over a partial sweep needs its caveats more than a positive does, not less.
  const scope: string[] = [];
  const widened = r.searchedDepth < r.categoryDepth;
  if (widened) {
    scope.push(
      `The leaf category had nothing in stock, so this widened to level ${r.searchedDepth} of ${r.categoryDepth}.`,
    );
  }
  if (r.poolTotal > r.poolProducts) {
    // Same honesty `--sort per-unit` owes its ranking: this ordered what was
    // fetched, not the category. A "closest match" claim — or a "nothing here"
    // claim — over a partial sweep would be false.
    scope.push(
      `That category holds ${r.poolTotal} products — only ${r.poolProducts} were compared. Raise --count to widen it.`,
    );
  }
  if (!r.regionId) {
    scope.push(
      "No delivery point set, so stock is NATIONAL and may not reflect your store. Pass --lat/--lng, or run `d1 region`.",
    );
  }

  if (r.candidates.length === 0) {
    lines.push(`Nothing in ${sanitize(r.categoryPath)} is in stock to replace it.`);
    if (scope.length) {
      lines.push("");
      lines.push(...scope);
    }
    lines.push("");
    lines.push("Widen the search yourself with `d1 search <term> --available --sort per-unit`.");
    return lines.join("\n");
  }

  let tier = r.candidates[0].tier;
  r.candidates.forEach((c, i) => {
    if (c.tier !== tier) {
      tier = c.tier;
      lines.push("");
      lines.push(
        "  — below here the pack is measured differently, so per-unit prices do not compare —",
      );
    }
    const p = c.product;
    const o = bestOffer(p);
    lines.push("");
    lines.push(
      `${String(i + 1).padStart(3)}  ${pad(p.skuId, 7)} ${pad(p.name, 44)} ${
        priced(o) ? formatCOP(o.price).padStart(10) : "—".padStart(10)
      } ${perUnit(p).padStart(13)}`,
    );
    for (const d of c.deltas) {
      lines.push(`          ${sanitize(d.text)}`);
    }
  });

  lines.push("");
  // Counts what was RANKED, not what was fetched. `poolSize` includes the
  // source itself and every out-of-stock item, so "ranked against 3 products"
  // was printed where 2 were actually compared.
  lines.push(
    `${r.rankedCount} in-stock alternative${r.rankedCount === 1 ? "" : "s"} in ${sanitize(
      r.categoryPath,
    )}, from ${r.poolProducts} product${r.poolProducts === 1 ? "" : "s"} swept${
      r.candidates.length < r.rankedCount ? ` — showing the closest ${r.candidates.length}` : ""
    }.`,
  );
  lines.push(...scope);
  lines.push("");
  // Sanitized like every other upstream field. This was the one render path
  // that interpolated a raw upstream value, and it is the worst possible line
  // to leave open: an `ESC[2J` in a SKU id lands LAST, so it clears the screen
  // after everything has printed — erasing this very sentence, which is the
  // one that tells the reader nothing was bought. Verbatim the attack the
  // docstring on `sanitize` names.
  //
  // Control characters were only half of it. The id is decimal per
  // `assertSkuId`, and anything else in a printed command is a second command
  // waiting for someone — or some agent — to paste it. Gated like the
  // `d1 substitute` line, rather than left as the one site that is not.
  const takeSku = r.candidates[0].product.skuId;
  lines.push(
    SKU_ID.test(takeSku)
      ? `Nothing was added to your cart. To take one:  d1 cart add ${takeSku}`
      : "Nothing was added to your cart.",
  );
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

/** Render the customer's saved address book. */
export function renderAddresses(addrs: SavedAddress[]): string {
  if (addrs.length === 0) {
    return "No saved addresses. Add one at d1.com.co — their map picker canonicalizes it in a way free text cannot.";
  }
  const lines: string[] = [];
  const complete = addrs.filter((a) => a.complete);
  const junk = addrs.filter((a) => !a.complete);

  for (const a of complete) {
    const where = [a.street, a.number].filter(Boolean).join(" ");
    lines.push(
      `${a.addressId.slice(0, 12)}  ${pad(where, 26)} ${pad(a.complement ?? "", 30)} ${a.neighborhood ?? ""}`,
    );
  }
  if (junk.length) {
    lines.push("");
    lines.push(
      `${junk.length} incomplete record${junk.length === 1 ? "" : "s"} hidden (no street — usually created by passing bare coordinates).`,
    );
  }
  lines.push("");
  lines.push("Use one with: d1 cart deliver-to --address-id <id>");
  return lines.join("\n");
}

/**
 * A budget basket: what went in, what did not, and why.
 *
 * The unfilled lines are not an appendix. A basket that reports a total while
 * quietly dropping three of eight terms is making a claim about a shop that
 * would not happen, which is the same defect as an empty substitute result
 * asserting "nothing is in stock" without saying it compared 3 of 140.
 */
export function renderBasket(
  plan: BasketPlan,
  opts: { regionId?: string; count?: number } = {},
): string {
  const out: string[] = [];
  // A filled line without a product cannot be rendered as a row, and must not
  // be counted or billed either — dropping it from the body alone produced an
  // empty basket whose summary still read "1 of 1 lines - $ 5.550".
  const filled = plan.lines.filter((l) => FILLED.includes(l.status) && l.product);
  const unfilled = plan.lines.filter((l) => !FILLED.includes(l.status) || !l.product);

  for (const l of filled) {
    const p = l.product;
    if (!p) continue;
    const per = perUnit(p);
    out.push(
      `  ${sanitize(p.skuId).padEnd(7)} ${sanitize(p.name).padEnd(46)} ${formatCOP(l.price ?? 0).padStart(9)}  ${per}`,
    );
    out.push(`          for "${sanitize(l.term)}" · ${scopeOf(l)}`);
    if (l.byPackPrice) {
      // The one path where the CLI knowingly ranks on pack price. Presenting it
      // identically to a value-ranked line is the "cheapest pack is the worst
      // buy" error this whole feature exists to prevent.
      out.push(
        l.anySized
          ? "          chosen on pack price — no two of these are measured the same way"
          : "          chosen on pack price — D1 publishes no size for any of these",
      );
    }
    if (l.replaces) {
      out.push(
        `          replaces ${sanitize(l.replaces.skuId)} ${sanitize(l.replaces.name)}, which D1 cannot supply here`,
      );
    }
    if (p.warnings.length) out.push(`          ${p.warnings.map(sanitize).join(", ")}`);
  }

  if (!filled.length) {
    // Composed from one clause per condition PRESENT, never a single sentence
    // picked by priority.
    //
    // The headline is a causal claim, and four earlier attempts each made it
    // false for whichever lines the losing condition described: blaming the
    // budget over an unanswered lookup (while the same run exited 1, "D1 could
    // not be reached"), then blaming the lookup over lines whose price was
    // known and rejected. Each clause names a condition rather than "others",
    // which reads as a contrast with lines that went in — of which there are
    // none here.
    const has = (st: LineStatus) => plan.lines.some((l) => l.status === st);
    const why: string[] = [];
    if (has("replacement-unknown")) why.push("D1 did not answer");
    if (has("over-budget")) why.push("the budget was short");
    if (has("nothing-in-stock")) why.push("some are not in stock");
    if (has("no-match")) why.push("some matched nothing");
    // Three cases, not two. "Nothing was asked for" is only true of an EMPTY
    // list; a plan carrying lines whose statuses match none of the reasons
    // above still asked for something, and saying otherwise is false about the
    // one thing the reader can see for themselves.
    out.push(
      why.length
        ? `  Nothing could go in the basket — ${why.join("; ")}.`
        : plan.lines.length
          ? "  Nothing could go in the basket."
          : "  Nothing was asked for.",
    );
  }

  out.push("");
  // Billed from the lines actually RENDERED, not from `plan.total`. A plan
  // built by hand — which is how this function is called from tests and from
  // `--json` consumers — could otherwise show zero rows and still charge for
  // one, which is the same body-and-summary disagreement in the other
  // direction.
  const shown = sum(filled.map((l) => l.price ?? 0));
  out.push(
    `${filled.length} of ${plan.lines.length} lines · ${formatCOP(shown)} of ${formatCOP(plan.budget)} · ${formatCOP(plan.budget - shown)} left`,
  );
  // The ceiling is stated, not implied. A reader who assumed best-effort would
  // otherwise read a short basket as "that is all D1 sells".
  out.push(
    "The budget is a hard ceiling — a line that would exceed it is left out, not rounded into.",
  );

  if (unfilled.length) {
    out.push("");
    out.push("Not included:");
    for (const l of unfilled) out.push(`  ${sanitize(l.term)} — ${reasonFor(l)}`);
  }

  if (!opts.regionId) {
    out.push("");
    out.push(
      "No delivery point resolved, so these are NATIONAL prices and stock. Pass --lat/--lng for your store's.",
    );
  }
  out.push("");
  // Ceiling-aware, for the same reason the comparison's is: at `--count 50` the
  // unchecked wording tells the reader to raise a flag `search` has already
  // clamped. `opts.count` is what the command was invoked with, so the render
  // asks the same clamp the request asked.
  out.push(
    footerFor(
      filled,
      pageCount(opts.count) < MAX_COUNT
        ? WIDEN_UNCHECKED
        : ` --count is already at its ceiling of ${MAX_COUNT}.`,
    ),
  );
  return out.join("\n");
}

/**
 * How wide a look this line's choice was made over.
 *
 * Naming the denominator is the point. "best of 20 compared" alone reads as a
 * survey of the shelf; "best of 20 compared, of 143 D1 matched" says plainly
 * that 123 products were never looked at. That gap is what made an empty
 * substitute result claim "nothing in this category is in stock" while
 * concealing it had seen 3 of 140.
 */
function scopeOf(l: BasketLine): string {
  // A substitute line's `compared` counts a CATEGORY sweep, a different
  // population from `matched` (which counts the term's own search). Comparing
  // them was meaningless and, when the sweep was larger, silently suppressed
  // the denominator exactly where the look had drifted furthest from what the
  // shopper typed. So that line says which population it is talking about.
  if (l.substituteSweep) return `best of ${l.compared} in its category${sweepCaveat(l)}`;
  return l.matched > l.compared
    ? `best of ${l.compared} compared, of ${l.matched} D1 matched`
    : `best of ${l.compared} compared`;
}

/**
 * What the basket as a whole is claiming about how its lines were picked.
 *
 * Three different mechanisms can be in play at once, and one sentence cannot
 * cover them: value ranking, the pack-price fallback, and a substitute chosen
 * by similarity from a DIFFERENT category page. The old single sentence said
 * "best value among the products fetched for its term", which was false for the
 * last two.
 */
function footerFor(filled: readonly BasketLine[], widen = WIDEN_UNCHECKED): string {
  const substitutes = filled.filter((l) => l.substituteSweep).length;
  // When EVERY line is a replacement, "the products fetched for its term" is
  // false for the whole basket and the exception swallows the rule.
  const parts = [
    substitutes === filled.length && filled.length
      ? "Every line here is a replacement — the closest match from its category, not a product fetched for the term you typed"
      : "Each line is the best among the products fetched for its term, not across all of D1",
  ];
  if (filled.some((l) => l.byPackPrice)) {
    parts.push("by pack price where D1 publishes no size");
  }
  if (substitutes && substitutes !== filled.length) {
    parts.push(
      "except a replacement, which is the closest match from its category rather than for the term you typed",
    );
  }
  return `${parts.join(" — ")}.${widen}`;
}

/**
 * The widening advice, when the caller has not checked whether widening works.
 *
 * `search` clamps `--count` to {@link MAX_COUNT}, so at 50 this sentence tells
 * the reader to do something the CLI refuses: `--count 50` and `--count 100`
 * produce byte-identical output. {@link widenAdvice} is the checked form, and
 * every caller that knows its own count uses it.
 */
const WIDEN_UNCHECKED = " Raise --count to widen it.";

/**
 * What to tell the reader about widening, given what the run actually did.
 *
 * Two looks, two answers. The SEARCH PAGE takes `--count` and can be widened up
 * to the clamp. The CATEGORY SWEEP does not take it at all — see "The sweep
 * does not take --count" in `basket.ts` — so advice about it would be advice
 * about a flag that no longer reaches it.
 */
function widenAdvice(opts: {
  count: number;
  pagePartial: boolean;
  sweepPartial?: boolean;
}): string {
  const parts: string[] = [];
  if (opts.pagePartial) {
    parts.push(
      opts.count < MAX_COUNT
        ? "raise --count to widen the page look"
        : `--count is already at its ceiling of ${MAX_COUNT}`,
    );
  }
  if (opts.sweepPartial) {
    parts.push("the category sweep reads one page and --count does not widen it");
  }
  if (!parts.length) return "";
  const joined = parts.join("; ");
  return ` ${joined.charAt(0).toUpperCase()}${joined.slice(1)}.`;
}

/**
 * How partial the category sweep was, when it was partial.
 *
 * A categorical claim about a category — "nothing in it is in stock", "this is
 * the best of it" — is only as wide as the sweep behind it, and the sweep reads
 * ONE page capped at 50. `d1 substitute` states this on both its empty and
 * non-empty paths, and SKILL.md sets the rule: a negative over a partial sweep
 * needs the caveat more than a positive does, not less. The basket said neither
 * until this existed.
 */
function sweepCaveat(l: BasketLine): string {
  const { swept, categoryTotal } = l;
  if (!swept || !categoryTotal || categoryTotal <= swept) return "";
  return ` — only ${swept} of ${categoryTotal} in that category were searched`;
}

/**
 * What else would have fitted, when anything would have.
 *
 * Reports, and stops. The line's product is the best value of its set or the
 * closest match from a category; a cheaper one is by definition neither, so
 * choosing it here would be the silent auto-substitution the whole skill is
 * built to refuse. Naming the count and the command hands the judgement to the
 * person — the same shape as `d1 substitute` itself.
 *
 * The wording stays inside the sweep. On a replacement line this sentence sits
 * directly after `— only 2 of 140 in that category were searched`, so it says
 * "of those searched" rather than making a claim about the category entire.
 */
function alternativesNote(l: BasketLine): string {
  const n = l.affordableAlternatives ?? 0;
  if (n <= 0) return "";
  if (l.replaces) {
    const s = n === 1 ? "replacement" : "replacements";
    const said = `. ${n} cheaper ${s} of those searched would fit`;
    // The id comes off VTEX, not off the shopper. `catalog.ts` already refuses
    // to put an unvalidated one in an `fq` filter, for the reason stated there:
    // a value slot that is really a grammar does not narrow the question, it
    // rewrites it. A printed command is another such grammar.
    return SKU_ID.test(l.replaces.skuId)
      ? `${said} — run \`d1 substitute ${l.replaces.skuId}\` to choose one`
      : said;
  }
  const s = n === 1 ? "match" : "matches";
  // `--available` matters: the count came from products that are in stock AND
  // priced, and a bare `d1 search` lists the rest too. Without it the shopper is
  // told "3 would fit" and handed a command that shows a different population.
  return `. ${n} cheaper ${s} for this term would fit — run \`d1 search ${shellQuote(l.term)} --available --sort per-unit\` to choose one`;
}

/** A SKU id is digits. Anything else is not an id and does not go in a command. */
const SKU_ID = /^\d+$/;

/**
 * Quote a value so a printed command stays ONE command.
 *
 * `sanitize` only removes control characters, so a term containing a double
 * quote closed the string and appended a second command. Single quotes have
 * exactly one escape in POSIX sh, and this is it.
 *
 * An earlier version of this comment claimed these were the FIRST lines in this
 * file to interpolate data into something a reader — or an agent, since every
 * command here has a `--json` twin — may run. That was false when written, and
 * the search for what else it was false about turned up two more sites:
 * `renderSubstitutes` printing `d1 cart add <skuId>` with only `sanitize`
 * applied (`test/present.test.ts` had said so all along), and `cli.ts` printing
 * a `--auth-token` follow-up with nothing applied at all. All three are gated
 * now. The claim was worth more as a question than it was as a fact.
 */
export function shellQuote(s: string): string {
  return `'${sanitize(s).replace(/'/g, "'\\''")}'`;
}

/** Why a term did not make the basket, in the reader's terms rather than the enum's. */
function reasonFor(l: BasketLine): string {
  switch (l.status) {
    case "over-budget":
      // Name the replacement here too.
      //
      // This is the one path where a substitution was applied and then not
      // shown. When a term is out of stock its line is resolved to a category
      // replacement; if that replacement then exceeds what is left, the line is
      // downgraded here and printed as `huevos — would cost $ 24.900` — a price
      // belonging to a product the whole render never mentions. The shopper
      // reads it as the price of the thing they typed. `replaces` is documented
      // "Named, never applied silently", and the filled row honours that; this
      // row did not.
      return l.replaces
        ? `D1 cannot supply this, and the closest replacement it has — ${sanitize(l.product?.name ?? "")} — would cost ${formatCOP(l.price ?? 0)}, which does not fit in what is left${sweepCaveat(l)}${alternativesNote(l)}`
        : `would cost ${formatCOP(l.price ?? 0)}, which does not fit in what is left${alternativesNote(l)}`;
    case "nothing-in-stock":
      // "returned", not "carries". The look is one search page plus a bounded
      // category sweep, so a claim about what D1 STOCKS is wider than the
      // evidence; a claim about what it RETURNED is exactly as wide as it.
      //
      // Only claim a category was searched when one actually was. A line
      // downgraded for having no usable price never reached `findSubstitutes`,
      // and saying "its category had no replacement" invents a lookup.
      if (!l.substituteSweep) {
        return "D1 publishes no price for this at your store, so it cannot go in a basket";
      }
      if (l.inStock === undefined) {
        return "nothing D1 returned for this is in stock here, and its category was not reported on";
      }
      return l.inStock
        ? `nothing D1 returned for this is in stock here; ${l.inStock} in its category are, but none is priced at your store${sweepCaveat(l)}`
        : `nothing D1 returned for this is in stock here, and nothing in the part of its category that was searched is either${sweepCaveat(l)}`;
    case "replacement-unknown":
      // Never "nothing is in stock". That claim would be asserted from a
      // request that failed, which is a statement about the network dressed up
      // as a statement about the shelf.
      return "nothing D1 carries for this is in stock here, and the replacement lookup did not answer — unknown, not empty";
    case "no-brand-match":
      // Added with the status, and DEFENSIVE: `--brand` renders through
      // `renderComparison`, which never calls this, so no command reaches this
      // arm today. It exists because without it the status fell to the default,
      // which told the reader the line named no product and the plan was
      // malformed — while the line named the product it had just rejected.
      return l.substituteSweep
        ? `D1 sells this, but nothing of that brand — its category was searched too${sweepCaveat(l)}`
        : "D1 sells this, but nothing of that brand";
    case "no-match":
      return "D1 returned nothing for this term";
    default:
      // Reached only by a filled line carrying no product, which `fillToBudget`
      // makes impossible — so if a reader ever sees this, the plan was built by
      // hand and is malformed. Say that rather than "not included", which reads
      // like a shopping outcome.
      return "not included — this line names no product, which is a bug in whatever built this plan";
  }
}

/**
 * Nearby stores.
 *
 * The last two lines carry the weight. A list of street addresses with opening
 * hours reads as a collection offer to anyone who does not already know it is
 * not one, so it says so — and it states the radius its "nearest" claim is good
 * for, because the registry caps at 300 points and a shop past that edge is
 * missing from the answer without being missing from the world.
 */
export function renderStores(r: StoresResult, at: LatLng, today?: number): string {
  // Gated on the SWEEP. Keying on `stores.length` asserted "that is the
  // registry's answer" whenever the shown list happened to be empty — including
  // when points were fetched and every one was dropped as malformed, which is a
  // statement about this parser rather than about the registry.
  if (!r.stores.length) {
    // The registry ANSWERED, and this parser could not read what it said. That
    // is a fact about this code, and reporting it as the registry's answer
    // would be the same substitution the sentence below exists to avoid.
    if (r.dropped) {
      return [
        `No D1 store near ${fmtCoord(at)} could be read from the pickup registry.`,
        `It returned ${r.dropped} ${r.dropped === 1 ? "entry" : "entries"} and none of them carried the fields this needs, which is a bug here rather than an empty neighbourhood.`,
      ].join("\n");
    }
    return [
      `No D1 store is in the pickup registry near ${fmtCoord(at)}.`,
      "That is the registry's answer, not a survey of the neighbourhood — it lists points D1 has configured for logistics, which is not the same set as shops with a door.",
    ].join("\n");
  }

  const out: string[] = [];
  for (const s of r.stores) {
    const where = [s.street, s.neighborhood, s.city].filter(Boolean).join(", ");
    out.push(
      `  ${fmtKm(s.distanceKm)}  ${pad(sanitize(s.name), 26)}  ${sanitize(where)}${s.active ? "" : "   [inactive]"}`,
    );
    const h = today === undefined ? undefined : hoursOn(s, today);
    if (h) out.push(`${" ".repeat(11)}open today ${h.opens.slice(0, 5)}–${h.closes.slice(0, 5)}`);
  }

  out.push("");
  out.push(`${r.stores.length} shown of ${r.swept} found${scopeLine(r)}`);
  // The load-bearing sentence. Measured, not assumed: no checkout simulation at
  // any point tried has ever offered a `pickup-in-point` delivery channel.
  out.push(
    "These are store locations, not collection points — D1's checkout offers scheduled delivery only, so you cannot have an order sent here to collect.",
  );
  return out.join("\n");
}

/**
 * How wide the look was, and why it stopped where it did.
 *
 * Three endings, three different sentences. A boolean conflated the last two,
 * so a sweep that hit the API's own ceiling said "the registry holds more
 * further out" — true of the world, false of anything this command can reach.
 */
function scopeLine(r: StoresResult): string {
  const reach =
    r.reachedKm === undefined ? "" : ` within ${r.reachedKm.toFixed(1)} km of the point`;
  switch (r.stopped) {
    case "registry-empty":
      // Only claim completeness when everything the registry sent was readable.
      // `fresh === 0` is true both for a page of duplicates and for a page this
      // parser could not read a word of, and the second is not the registry
      // running out — it is us running out.
      return r.dropped
        ? `${reach} — and ${r.dropped} more the registry sent could not be read here, so there may be others`
        : `${reach} — that is every point the registry returns here`;
    case "cap":
      return `${reach} — that is the registry's own ceiling of ${MAX_REACHABLE}, so a shop further out is missing from this answer rather than from D1`;
    default:
      // Hedged when the registry did not report a total. Stopping on `limit`
      // after a page that happened to hold exactly the limit proves nothing
      // about what lies beyond it, and "holds more" is an assertion.
      // An exact remainder needs a total that is a TOTAL. `stores.ts` refuses to
      // treat `registryTotal` as one at exactly MAX_REACHABLE — 300 at both
      // Bogotá and Medellín is too round to be a coincidence — and then this
      // turned the same number into "the registry holds 270 more further out".
      return r.registryTotal !== undefined &&
        r.registryTotal < MAX_REACHABLE &&
        r.registryTotal > r.swept
        ? `${reach} — the registry holds ${r.registryTotal - r.swept} more further out`
        : `${reach} — the registry may hold more further out`;
  }
}

function fmtKm(km: number): string {
  if (Number.isNaN(km)) return "   ?   ";
  return `${km.toFixed(2).padStart(6)} km`;
}

function fmtCoord(at: LatLng): string {
  return `${at.lat}, ${at.lng}`;
}

/**
 * The same list, priced two ways.
 *
 * The rule this render exists to enforce: **the headline delta is computed over
 * the terms BOTH baskets filled, and nothing else.** A brand-constrained basket
 * routinely fills fewer lines, and differencing the two totals then reports the
 * lines it could not fill as a saving — drop the two dearest terms and any
 * brand looks cheap, because it did not buy them. The unfilled terms are named
 * separately, where they read as a gap rather than a discount.
 */
export function renderComparison(c: CrossBasket): string {
  const out: string[] = [];
  const brand = sanitize(c.brand);

  // The two looks a brand verdict rests on, as ONE phrase, each naming its own
  // population and its own span. Round 6 scoped the claims to the page; round 9
  // found that `no-brand-match` is decided by the CATEGORY sweep, whose
  // denominator nothing read — so a complete page look printed no qualifier at
  // all over a sweep of 10 of 41, and exited 3.
  const scope = crossScope(c);
  const widen = widenAdvice({
    count: c.count,
    pagePartial: c.partial !== undefined,
    sweepPartial: c.sweepPartial !== undefined,
  });

  if (c.brandsSeen) {
    // Two different facts, and the code now knows which one it has. `no-brand-match`
    // means nothing of the brand was BUYABLE — it does not mean D1 returned none
    // of it, and saying so was false whenever the brand was on the page at
    // `Price: 0` (live: `--brand COPELIA leche`).
    // Three sentences, and which one is true depends on evidence this now reads.
    //
    // The unqualified negative was false for twelve of twelve real brands tried
    // at default flags: `--count` defaults to 12 against result sets of 25-31,
    // so "Nothing D1 returned for these terms is ALPIN" was a universal over
    // twelve products while ALPIN sat in stock at product 13. `scopeOf`,
    // `sweepCaveat` and `footerFor` hold this line everywhere else in the
    // module; this render called none of them.
    // WHERE the brand was found, named. A boolean here reproduced the round-5
    // blocker one hop over: with the brand only in the category sweep and a
    // complete look, "D1 returned LATTI for these terms" printed directly above
    // "Brands it did return: OTRA." — the list being the page alone, which is
    // round 7's own correct fix. Two sentences answering what reads as one
    // question, with opposite answers. One label, one population applies to the
    // claim as well as to the list.
    const seenIn =
      c.brandReturnedIn === "sweep" ? "in the category around these terms" : "for these terms";
    // ...and the negative half never outruns EITHER look. This arm was round 5's
    // and round 6 never touched it, so "nothing of it can be bought at this
    // store" stayed a universal over `--count` products — twelve of twenty-nine
    // at the default, the exact disease round 6 was about. Round 9 then found
    // the second half of the same sentence: the sweep behind it was partial too,
    // and neither the claim nor the exit code said so.
    const unbuyable = scope
      ? `but nothing of it the look reached can be bought at this store — the look covered ${scope}.${widen}`
      : "but nothing of it can be bought at this store.";
    out.push(
      c.brandReturnedIn
        ? `D1 returned ${brand} ${seenIn}, ${unbuyable}`
        : scope
          ? `Nothing the look reached for these terms is ${brand} — it covered ${scope}.${widen}`
          : `Nothing D1 returned for these terms is ${brand}.`,
    );
    if (c.brandsSeen.length) {
      // Truncated OUT LOUD. A silent `.slice(0, 12)` is the same shape as every
      // partial-sweep claim this module already caveats — and the whole point of
      // the hint is to surface a near-miss, which is exactly what a silent cut
      // would drop.
      // The REQUESTED brand first, whenever the page carried it.
      //
      // The list is sorted alphabetically and cut at twelve, so a near-miss
      // spelling of the very brand asked for could fall past the cut — and did:
      // `--brand "TRADICION 1915"` (no accent) printed "Nothing D1 returned for
      // these terms is TRADICION 1915" above a list that omitted the accented
      // spelling as "and 1 more". The one entry the hint exists to surface was
      // the one entry a fixed-length cut is free to drop, and the omission also
      // emitted the exact pair FORBIDDEN rule 1 forbids. `normalizeBrand` now
      // folds accents so this case fills instead — but a hint that can hide its
      // own subject is wrong for every other near-miss too, so the ordering is
      // the fix and the folding is a separate one.
      const ordered = requestedFirst(c.brandsSeen, c.brand);
      const shown = ordered.slice(0, MAX_BRAND_HINT);
      const more = ordered.length - shown.length;
      // Scoped like the headline above it. This was the same unqualified
      // universal, one line below the sentence that had just been fixed: for
      // `leche` it named one brand of the eleven D1 returns, under a label that
      // reads as the complete set — the exact "typo or absent brand?" confusion
      // the hint exists to remove.
      // The label NAMES its population. "Brands it did return" reads as the
      // complete answer to the question the headline above it just answered,
      // and when the brand came from the category sweep the two disagreed. The
      // list is the term pages and says so, so no reading of it competes with a
      // sentence about the category.
      const label = c.partial
        ? `Brands among the ${c.partial.looked} products looked at across ${c.partial.terms} ${c.partial.terms === 1 ? "term" : "terms"}`
        : "Brands on these terms' own pages";
      out.push(
        `${label}: ${shown.map(sanitize).join(", ")}${more > 0 ? `, and ${more} more` : ""}.`,
      );
    }
    out.push("");
  }

  // The label is NEVER truncated here. `pad` cut at 17 characters, so
  // "aceite de oliva (#2)" rendered as "aceite de oliva (…" — two
  // indistinguishable rows, while the buckets below named "(#2)" precisely. The
  // column widens to fit instead, because the whole point of the label is that
  // the reader can match it to the sentence underneath.
  const width = Math.max(18, ...c.rows.map((r) => sanitize(r.term).length));
  for (const r of c.rows) {
    const basePart = priceCell(r.base);
    const altPart = priceCell(r.alt);
    out.push(`  ${sanitize(r.term).padEnd(width)} ${basePart}   ${altPart}${deltaCell(r)}`);
  }

  // WHAT was bought, by name.
  //
  // The table is four numbers and a term, and every defect round 9 found in the
  // delta was invisible in it. `--brand LATTI leche --count 50` reported LATTI
  // as $ 1.310 cheaper: the unconstrained side had bought
  // `PAN LECHE HORNEADITOS 10 UND 440 G` — bread rolls, best in the page's
  // dominant `$/kg` census — and the branded side `LECHE ENTERA … LATTI 900 ML`,
  // best on `$/L`. Two ranks on two axes, subtracted. Nothing on screen named
  // either product, so no reader could catch it and no amount of hedging in the
  // footer would have helped.
  const bought = boughtLines(c);
  if (bought.length) {
    out.push("");
    out.push("What was bought");
    for (const line of bought) out.push(line);
  }

  out.push("");
  const { terms, baseTotal, altTotal, delta } = c.comparable;
  if (terms === 0) {
    // No shared line means there is no comparison to report. Printing a delta
    // of zero here would read as "the same price", which is the opposite of
    // what happened.
    //
    // The "not an alternative for any line" clause is conditional, because it
    // was false exactly when `onlyAlt` was populated: `chooseBest` ranks by unit
    // price, so the best-value pick is routinely a larger, pricier pack that
    // busts the budget while the branded one fits. The output then said the
    // brand was not an alternative to anything, directly above the line saying
    // it was the only thing that could fill the term.
    // States what happened, and stops.
    //
    // Three rounds each conditioned the old "…is not an alternative for any
    // line above" clause on one more bucket and each left another open —
    // `onlyAlt`, then `altOverBudget`, then `altUnknown`, the last of which
    // asserted a fact about D1's shelf from a lookup that never answered. The
    // clause was an INFERENCE from state this sentence does not inspect, and
    // every fix was another guess at which states it holds for. The buckets
    // below already say, precisely, what happened to each term; this line no
    // longer competes with them.
    out.push("No term was filled by both baskets, so there is no price to compare.");
  } else {
    const dir = delta === 0 ? "the same as" : delta > 0 ? "more than" : "less than";
    out.push(
      `Over the ${terms} ${terms === 1 ? "term" : "terms"} BOTH filled: ${formatCOP(baseTotal)} best-value vs ${formatCOP(altTotal)} in ${brand} — ${formatCOP(Math.abs(delta))} ${dir} best value.`,
    );
    // ...and the delta says so when it is not a like-for-like one. Named right
    // under the number it qualifies, because a reader who reads one line reads
    // this one.
    const mixed = c.rows.filter(mixedMeasure);
    if (mixed.length) {
      out.push(
        `${mixed.length} of those ${mixed.length === 1 ? "rows compares" : "rows compare"} products ranked on DIFFERENT measures (${mixed.map(measurePair).join("; ")}), so that much of the difference is not like for like — see what was bought.`,
      );
    }
  }

  // Named, not netted — and named by CAUSE. One sentence covering every reason a
  // term is missing asserted "no LATTI for this" about a branded product that
  // was found and priced and refused on budget, and about one whose lookup never
  // answered. Those are facts about a wallet and about a network; only the first
  // line below is a fact about D1's shelf.
  // The per-term sentence carries the same scope as the headline, because it
  // makes the same claim and was equally unqualified — it printed
  // "no RED FLAG for: aceite" about a term whose RED FLAG product was on the
  // page one `--count` wider, at $ 8.900.
  // Reads `brandReturnedIn` too, because it names a CAUSE and that is
  // the cause. It printed "no NATURAL FEELING for: leche" six lines under
  // "D1 returned NATURAL FEELING ... but nothing of it can be bought" — the
  // round-5 contradiction, reintroduced in the bucket whose whole design rule
  // is that a term is named by why it is missing.
  // Carries the headline's scope too, for the same reason the headline needed
  // it: "found but not buyable here" is a universal over whatever `--count`
  // happened to fetch.
  // PER TERM, and grouped by the sentence each term's own evidence produces.
  //
  // The single global sentence was the sixth recurrence of one root defect, in
  // the line rounds 7 and 8 each rewrote. `--brand COPELIA --count 50 leche
  // arroz` printed "COPELIA found but not buyable here, for: leche, arroz" —
  // true of `leche`, whose page carries COPELIA at Price 0, and false of
  // `arroz`, which has none of it in either population at a complete look. A
  // list of terms under one clause asserts that clause of every term in it, so
  // the clause has to be computed from the term.
  const missing: Array<[readonly string[], string]> = [
    ...groupMisses(c.onlyBase, brand),
    [c.altOverBudget, `${brand} found but over budget for`],
    [c.altUnknown, `the ${brand} lookup did not answer for`],
    [c.altNoMatch, "D1 returned nothing at all for"],
  ];
  let anyMissing = false;
  for (const [terms, why] of missing) {
    if (!terms.length) continue;
    anyMissing = true;
    out.push(`Not counted — ${why}: ${terms.map(sanitize).join(", ")}.`);
  }
  if (c.onlyAlt.length) {
    out.push(`Not counted — only ${brand} could fill: ${c.onlyAlt.map(sanitize).join(", ")}.`);
  }
  // Only when there ARE two numbers. With nothing shared the line above says
  // there is no price to compare, and this then pointed at numbers that were
  // never printed — while the term's own price WAS on screen, so a reader takes
  // it as a claim about that. Fourth instance of one shape: a sentence
  // asserting something about state it does not read.
  //
  // Moved below `onlyAlt` too: "their" reached backwards over a bucket that
  // printed after it.
  if (anyMissing && terms > 0) out.push("Their cost is in neither number above.");
  if (c.neither.length) {
    // No "that is not about <brand>" clause. It was false whenever the branded
    // line's own status was `no-brand-match` — the brand WAS looked for and
    // missing — and it then sat four lines under a header saying exactly that.
    //
    // Third instance of one shape in this file: a clause that INFERS a cause
    // from state the sentence does not inspect. Each of the previous two was
    // fixed by conditioning it on one more field, and each left another arm
    // open. Stating the fact and pointing at where the reason lives cannot be
    // wrong in any state.
    out.push(
      `Neither basket filled: ${c.neither.map(sanitize).join(", ")}. Run the same list without --brand for the reason.`,
    );
  }
  out.push("Both baskets were fit to the same budget, so each is one a shopper could have bought.");
  // The footer `renderBasket` has had all along, and this render did not call.
  //
  // Two things were wrong with saying nothing. Both prices above are the best
  // of a window, not of D1, and the window moves with `--count`. And a line can
  // be a REPLACEMENT swept from a category — `--brand DULCRALIGHT … arroz`
  // filled `arroz` with `ENDULZANTE FRASCO 180 GRS`, a sweetener, and priced
  // the brand cheaper on it. By construction `brandLine` runs only when the
  // term's own page held nothing of the brand, so a `filled-by-substitute` price
  // here is NEVER "the best among the products fetched for its term" — the one
  // sentence this render was closest to implying. `footerFor` already owns that
  // exception, word for word, and is now asked for it.
  const filledBoth = [...c.base.lines, ...c.alt.lines].filter((l) => FILLED.includes(l.status));
  out.push(footerFor(filledBoth, widen));
  return out.join("\n");
}

/**
 * Whether a row's two sides were ranked on measures that are not comparable.
 *
 * Only for rows that actually contribute to the delta — an unfilled side has no
 * rank to disagree with. `undefined` on one side means a pack-price fallback or
 * a category sweep, which is a different disclosure and is made where it
 * belongs (`footerFor`, and the "replacing" clause below).
 */
function mixedMeasure(r: BasketComparison): boolean {
  if (r.delta === undefined) return false;
  const a = r.base?.rankedOn;
  const b = r.alt?.rankedOn;
  return a !== undefined && b !== undefined && a !== b;
}

/** `leche: per kg vs per L` — the two axes, named. */
function measurePair(r: BasketComparison): string {
  return `${sanitize(r.term)}: per ${sanitize(r.base?.rankedOn ?? "?")} vs per ${sanitize(r.alt?.rankedOn ?? "?")}`;
}

/**
 * The product each side actually bought, per row.
 *
 * Includes the replacement disclosure. `brandLine` runs only when a term's own
 * page held nothing of the brand, so the branded side of a row is routinely a
 * product swept from some category — `arroz` filled with a sweetener, priced,
 * and reported as the brand being cheaper on rice.
 */
function boughtLines(c: CrossBasket): string[] {
  const out: string[] = [];
  for (const r of c.rows) {
    const parts: string[] = [];
    const side = (l: BasketLine | undefined, who: string) => {
      if (!l || !FILLED.includes(l.status) || !l.product) return;
      const measure = l.rankedOn ? `, best per ${sanitize(l.rankedOn)}` : "";
      const replacing = l.replaces
        ? `, replacing ${sanitize(l.replaces.name)} from its category`
        : "";
      parts.push(`${who}: ${sanitize(l.product.name)}${measure}${replacing}`);
    };
    side(r.base, "best value");
    side(r.alt, sanitize(c.brand));
    if (parts.length) out.push(`  ${sanitize(r.term)} — ${parts.join("; ")}`);
  }
  return out;
}

/**
 * The two looks a brand verdict rests on, as one phrase.
 *
 * Empty when both were complete, which is the only state in which a categorical
 * claim needs no qualifier at all.
 */
function crossScope(c: CrossBasket): string {
  const parts: string[] = [];
  if (c.partial) {
    const { looked, matched, terms } = c.partial;
    parts.push(
      `${looked} of the ${matched} D1 matched across ${terms} ${terms === 1 ? "term" : "terms"}`,
    );
  }
  if (c.sweepPartial) {
    const { swept, categoryTotal, terms } = c.sweepPartial;
    parts.push(
      `${swept} of the ${categoryTotal} in ${terms === 1 ? "the category" : "the categories"} around them`,
    );
  }
  return parts.join(", and ");
}

/**
 * The requested brand first, so a fixed-length cut cannot drop it.
 *
 * Comparison is on {@link normalizeBrand}, the same predicate the filter used,
 * so an accent or a case difference still counts as the same brand here.
 */
function requestedFirst(brands: readonly string[], brand: string): string[] {
  const want = normalizeBrand(brand);
  const hit: string[] = [];
  const rest: string[] = [];
  for (const b of brands) (normalizeBrand(b) === want ? hit : rest).push(b);
  return [...hit, ...rest];
}

/**
 * Per-term brand verdicts, grouped by the sentence each one produces.
 *
 * Terms whose evidence is identical share a line — that is the whole benefit of
 * the old global sentence, kept. Terms whose evidence differs get different
 * lines, which is the part that was missing and the part that made the old one
 * false. Order follows first appearance, so the sentences stay in list order.
 */
function groupMisses(misses: readonly BrandMiss[], brand: string): Array<[string[], string]> {
  const byWhy = new Map<string, string[]>();
  for (const m of misses) {
    const why = missWhy(m, brand);
    const bucket = byWhy.get(why);
    if (bucket) bucket.push(m.term);
    else byWhy.set(why, [m.term]);
  }
  return [...byWhy.entries()].map(([why, terms]) => [terms, why]);
}

/**
 * One term's own brand verdict, from that term's own evidence.
 *
 * The widening advice is deliberately NOT repeated here. It is a fact about the
 * run rather than about a term, the headline and the footer both carry it, and
 * a per-term copy would put it on the page once per bucket.
 */
function missWhy(m: BrandMiss, brand: string): string {
  const parts: string[] = [];
  if (m.look) parts.push(`${m.look.looked} of ${m.look.matched} on its page`);
  if (m.sweep) parts.push(`${m.sweep.swept} of ${m.sweep.categoryTotal} in its category`);
  const searched = parts.length ? ` (${parts.join(", ")} searched)` : "";
  if (m.returnedIn) {
    const where = m.returnedIn === "sweep" ? "in the category around it" : "on its own page";
    return searched
      ? `${brand} is ${where} and nothing of it the look reached is buyable${searched}, for`
      : `${brand} is ${where} and nothing of it is buyable here, for`;
  }
  return searched
    ? `no ${brand} in what was searched${searched}, for`
    : `D1 returned no ${brand} at all for`;
}

/** How many brands the near-miss hint lists before saying "and N more". */
const MAX_BRAND_HINT = 12;

/** A price, or why there is not one, in a fixed-width cell. */
function priceCell(l: BasketLine | undefined): string {
  if (!l || !FILLED.includes(l.status) || l.price === undefined) {
    return "—".padStart(9);
  }
  return formatCOP(l.price).padStart(9);
}

function deltaCell(r: BasketComparison): string {
  if (r.delta === undefined) return "";
  if (r.delta === 0) return "   same";
  return r.delta > 0 ? `   +${formatCOP(r.delta)}` : `   -${formatCOP(Math.abs(r.delta))}`;
}
