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

import { type BasketLine, type BasketPlan, FILLED, type LineStatus } from "./basket.ts";
import { bestOffer, priced } from "./catalog.ts";
import { formatUnitPrice } from "./measure.ts";
import { discountPercent, formatCOP, sum } from "./money.ts";
import type { SubstituteResult } from "./substitute.ts";
import type {
  Cart,
  Category,
  Facet,
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
  lines.push(
    `Nothing was added to your cart. To take one:  d1 cart add ${sanitize(
      r.candidates[0].product.skuId,
    )}`,
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
export function renderBasket(plan: BasketPlan, opts: { regionId?: string } = {}): string {
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
  out.push(footerFor(filled));
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
function footerFor(filled: readonly BasketLine[]): string {
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
  return `${parts.join(" — ")}. Raise --count to widen it.`;
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
    return `. ${n} cheaper ${s} of those searched would fit — run \`d1 substitute ${sanitize(l.replaces.skuId)}\` to choose one`;
  }
  const s = n === 1 ? "match" : "matches";
  return `. ${n} cheaper ${s} for this term would fit — run \`d1 search "${sanitize(l.term)}" --sort per-unit\` to choose one`;
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
