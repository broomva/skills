#!/usr/bin/env bun
/**
 * `d1` — command-line access to Tiendas D1 (Colombia).
 *
 * Designed to be driven by an agent as much as by a person: every command takes
 * `--json`, exit codes are meaningful (0 ok, 1 D1 failed, 2 usage, 3 no result),
 * and nothing prompts unless it has to.
 *
 * The CLI can find products, price a basket against a real store, and quote
 * delivery. It cannot pay — `d1 cart checkout` prints the URL where a human
 * finishes. See `cart.ts` for why that line is drawn where it is.
 */

import {
  type BasketLine,
  type BasketOptions,
  buildBasket,
  isFilled,
  parseBudget,
} from "./basket.ts";
import {
  addItems,
  checkoutUrl,
  clearCart,
  ensureDeliveryPoint,
  getCart,
  listAddresses,
  setDeliveryPoint,
  setQuantity,
  simulate,
  undeliverable,
  useSavedAddress,
} from "./cart.ts";
import { assertSkuId, categoryTree, facets, search, suggest, topSearches } from "./catalog.ts";
import { D1Client } from "./client.ts";
import { formatCOP } from "./money.ts";
import { getOrder, listOrders, orderForDisplay } from "./orders.ts";
import { fingerprint, isMutating, isOwned, isScratch } from "./ownership.ts";
import {
  json,
  renderAddresses,
  renderBasket,
  renderCart,
  renderCategories,
  renderFacets,
  renderOrders,
  renderRegion,
  renderSearch,
  renderShipping,
  renderStores,
  renderSubstitutes,
  shellQuote,
} from "./present.ts";
import { deliverable, primarySeller, resolveRegion } from "./region.ts";
import {
  adoptToken,
  clearSession,
  loadSession,
  saveSession,
  sendAccessKey,
  startAuth,
  validateAccessKey,
  whoami,
} from "./session.ts";
import { MAX_REACHABLE, nearbyStores, vtexDay } from "./stores.ts";
import { type SubstituteOptions, findSubstitutes } from "./substitute.ts";
import { D1Error, DEFAULT_SALES_CHANNEL, type LatLng, UsageError } from "./types.ts";

// ---------------------------------------------------------------------------
// Argument parsing
// ---------------------------------------------------------------------------

interface Args {
  positional: string[];
  flags: Record<string, string | boolean>;
}

export function parseArgs(argv: string[]): Args {
  const positional: string[] = [];
  const flags: Record<string, string | boolean> = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith("--")) {
      positional.push(a);
      continue;
    }
    const body = a.slice(2);
    const eq = body.indexOf("=");
    if (eq !== -1) {
      flags[body.slice(0, eq)] = body.slice(eq + 1);
    } else if (i + 1 < argv.length && !argv[i + 1].startsWith("--")) {
      flags[body] = argv[++i];
    } else {
      flags[body] = true;
    }
  }
  return { positional, flags };
}

/**
 * Parse a `sku` or `sku:qty` basket spec.
 *
 * Rejects a malformed quantity rather than defaulting to 1. `d1 quote 262:abc`
 * silently quoting a single unit is worse than an error: the caller asked about
 * a specific quantity and would be shown a total for a different basket.
 */
export function parseSpec(spec: string): { skuId: string; quantity: number } {
  const parts = spec.split(":");
  if (parts.length > 2) {
    throw new UsageError(`Malformed item "${spec}". Expected <sku> or <sku>:<qty>.`);
  }
  const [skuId, rawQty] = parts;
  if (!skuId) throw new UsageError(`Malformed item "${spec}". Missing SKU.`);

  if (rawQty === undefined) return { skuId, quantity: 1 };
  const quantity = Number(rawQty);
  if (!Number.isInteger(quantity) || quantity < 1) {
    throw new UsageError(`Quantity in "${spec}" must be a positive whole number, got "${rawQty}".`);
  }
  return { skuId, quantity };
}

/**
 * Read a `--qty` flag strictly.
 *
 * Absent means 1. Anything else must parse as a positive whole number — an
 * unparseable value is rejected rather than falling back to 1. This is the
 * same rule `parseSpec` applies to `sku:qty`, and for the same reason, except
 * that here it governs a MUTATION: `d1 cart add 262 --qty abc` silently adding
 * one unit puts the wrong thing in a real basket, not just on a screen.
 */
export function quantityFlag(v: string | boolean | undefined): number {
  if (v === undefined) return 1;
  if (typeof v !== "string" || v.trim() === "") {
    throw new UsageError("--qty needs a positive whole number, e.g. --qty 3.");
  }
  const n = Number(v);
  if (!Number.isInteger(n) || n < 1) {
    throw new UsageError(`--qty must be a positive whole number, got "${v}".`);
  }
  return n;
}

/**
 * Read an optional count-shaped flag strictly, the same way `--qty` is read.
 *
 * Absent means the caller's default. Anything else must be a positive whole
 * number: clamping instead meant `--limit 0` and `--limit -3` both quietly
 * returned exactly one proposal and exited 0, answering a question nobody
 * asked — and `--count 0` did the same over a live request.
 */
export function positiveIntFlag(name: string, v: string | boolean | undefined): number | undefined {
  if (v === undefined) return undefined;
  if (typeof v !== "string" || v.trim() === "") {
    throw new UsageError(`--${name} needs a positive whole number, e.g. --${name} 5.`);
  }
  const n = Number(v);
  if (!Number.isInteger(n) || n < 1) {
    throw new UsageError(`--${name} must be a positive whole number, got "${v}".`);
  }
  return n;
}

export function limitFlag(v: string | boolean | undefined): number | undefined {
  return positiveIntFlag("limit", v);
}

/**
 * `--count` read as strictly as `--limit`.
 *
 * `num()` alone let `--count 0` and `--count -5` through as real numbers, and
 * `search` then clamped them to 1 — so asking for zero products quietly asked
 * for one, and did it over a live request. Same silent-clamp shape `--limit 0`
 * had, one flag over.
 */
export function countFlag(v: string | boolean | undefined): number | undefined {
  return positiveIntFlag("count", v);
}

/**
 * The options `d1 substitute` derives from its flags.
 *
 * Separate from the command body so the derivation is testable: the region id
 * and `--limit` reaching `findSubstitutes` are load-bearing (drop the region
 * and every shopper silently gets NATIONAL stock) and neither can be observed
 * from a network-free subprocess test of the command itself.
 */
export function substituteOptions(
  flags: Args["flags"],
  region: { id: string } | undefined,
  salesChannel: string,
): SubstituteOptions {
  return {
    regionId: region?.id,
    salesChannel,
    limit: limitFlag(flags.limit),
    count: countFlag(flags.count),
  };
}

/**
 * The options `d1 basket` derives from its flags.
 *
 * Separate from the command body for the same reason `substituteOptions` is:
 * dropping the region id silently prices the whole basket against the NATIONAL
 * catalogue, and no network-free test of the command body can observe it.
 */
export function basketOptions(
  flags: Args["flags"],
  region: { id: string } | undefined,
  salesChannel: string,
): BasketOptions {
  return { regionId: region?.id, salesChannel, count: countFlag(flags.count) };
}

/**
 * What `d1 basket` exits with.
 *
 * **3 when nothing fit**, matching `substitute`: the command succeeded at
 * looking, and "your budget buys none of this list" never becomes false on a
 * retry. A partially filled basket is exit 0 — a real answer, with the lines it
 * could not fit named in the output.
 *
 * **1 when a lookup never answered.** This takes the LINES, not a count, because
 * a count cannot tell the two apart. An earlier version took `filledCount` and
 * so returned 3 for a basket where every replacement lookup had failed — 3
 * being documented CLI-wide as "never worth retrying", which told an agent a
 * transient D1 outage meant its shopping list was definitively unbuyable. An
 * empty answer and an unanswered question are not the same result.
 */
/**
 * The "now run this" line printed after a one-time code is sent.
 *
 * Extracted so the QUOTING is testable. Inline it was reachable only by
 * spawning the CLI with a stubbed VTEX ID endpoint, which is why it sat
 * unquoted through every prior review: `authToken` comes off D1's response and
 * `email` off the command line, neither had even `sanitize` applied, and the
 * line is prefixed "Finish with:" — a literal instruction to run it, in the one
 * flow where an agent is most likely to paste the follow-up unread.
 */
export function loginFollowUp(email: string, authToken: string): string {
  return `A one-time code is on its way to ${email}. Finish with:\n  d1 login --email ${shellQuote(email)} --auth-token ${shellQuote(authToken)} --code <code>`;
}

/**
 * What `d1 stores near` exits with.
 *
 * Extracted so the three-way split is testable without a network stub that
 * serves malformed entries — the same reason `comparisonExit` and
 * `loginFollowUp` exist.
 */
export function storesExit(r: { stores: readonly unknown[]; dropped: number }): number {
  if (r.stores.length) return 0;
  // Exit 3 is "asked, and the answer is genuinely none", documented CLI-wide as
  // never worth retrying. An answer this parser could not read is a failure on
  // our side, and the render already declines to call it an empty neighbourhood.
  return r.dropped ? 1 : 3;
}

export function basketExit(lines: readonly BasketLine[]): number {
  if (lines.some((l) => isFilled(l.status))) return 0;
  if (lines.some((l) => l.status === "replacement-unknown")) return 1;
  return 3;
}

/**
 * What `d1 substitute` exits with once it has an answer.
 *
 * **3, not 1.** The command SUCCEEDED at looking, and an agent needs "I have a
 * replacement for you" apart from "I looked and there is none" — but exit 1 is
 * documented across this CLI as "D1 refused, or could not be reached; a retry
 * may help". An empty category never becomes non-empty on retry, so an agent
 * with a retry-on-1 policy would loop on it forever.
 *
 * Exit 0 with an empty list is the other wrong answer: it reads as success and
 * gets acted on.
 */
export function substituteExit(candidateCount: number): number {
  return candidateCount > 0 ? 0 : 3;
}

/**
 * Did a `cart add` actually land?
 *
 * Scoped by SELLER as well as SKU. The same SKU can occupy two lines under two
 * sellers — after a region change, or with an explicit `--seller` — and a
 * SKU-only lookup reads the wrong line: a cart holding 262@sellerA×10 answers
 * "10 >= 3, success" for a request against sellerB that upstream rejected
 * outright. That is the exact false success this check exists to prevent.
 *
 * Quantity is compared against the RESULT, not a delta, because VTEX's
 * POST /items SETS a line rather than adding to it (verified live).
 */
export function addOutcome(
  items: Array<{ skuId: string; sellerId: string; quantity: number }>,
  skuId: string,
  sellerId: string,
  want: number,
): { ok: boolean; got: number } {
  const got = items.find((i) => i.skuId === skuId && i.sellerId === sellerId)?.quantity ?? 0;
  return { ok: got >= want, got };
}

/** The `cart` subcommands, so an unknown one is rejected without a round trip. */
const CART_SUBCOMMANDS = ["show", "add", "set", "clear", "deliver-to", "checkout"] as const;

/**
 * Reject a malformed `cart` invocation before any request is made.
 *
 * Every check here duplicates one performed later in the command body. That is
 * deliberate: the later ones run after the cart has been fetched, and the whole
 * point is that a usage error must cost nothing and must not depend on D1 being
 * reachable. Keeping both means the command body stays readable on its own and
 * a check added there is still enforced, just one round trip later.
 */
export function validateCartArgs(sub: string, positional: string[], flags: Args["flags"]): void {
  if (!(CART_SUBCOMMANDS as readonly string[]).includes(sub)) {
    throw new UsageError(
      `Unknown cart subcommand: ${sub}. Expected one of ${CART_SUBCOMMANDS.join(", ")}.`,
    );
  }
  if (sub === "add") {
    if (!positional[2]) throw new UsageError("Usage: d1 cart add <sku> [--qty N]");
    quantityFlag(flags.qty);
  }
  if (sub === "set") {
    const idx = num(positional[2]);
    const qty = num(positional[3]);
    if (idx === undefined || qty === undefined) {
      throw new UsageError("Usage: d1 cart set <index> <quantity>");
    }
    if (!Number.isInteger(idx) || idx < 0) {
      throw new UsageError(
        `Item index must be a non-negative whole number, got "${positional[2]}".`,
      );
    }
    if (!Number.isInteger(qty) || qty < 0) {
      throw new UsageError(
        `Quantity must be zero or a positive whole number, got "${positional[3]}".`,
      );
    }
  }
  if (sub === "deliver-to" && !flags["address-id"]) {
    // Called for its THROW, not its value: `pointFrom` rejects a half-given
    // pair (`--lat` without `--lng`) itself. Returning undefined is the valid
    // "no flags, fall back to the saved region" case, so it must NOT be
    // treated as an error here — a user with a saved delivery point would be
    // blocked before the command could read it.
    //
    // Skipped entirely with --address-id: a saved record already carries its
    // own coordinates, so requiring lat/lng there would reject the better path.
    pointFrom(flags, undefined);
  }
}

function num(v: string | boolean | undefined): number | undefined {
  if (typeof v !== "string" || v.trim() === "") return undefined;
  const n = Number(v);
  return Number.isFinite(n) ? n : undefined;
}

function str(v: string | boolean | undefined): string | undefined {
  return typeof v === "string" && v !== "" ? v : undefined;
}

/**
 * Resolve the delivery point for this invocation: explicit flags first, then
 * whatever the last `d1 region` saved. Returns undefined when neither exists,
 * which callers treat as "national catalogue, say so".
 */
function pointFrom(flags: Args["flags"], saved?: { lat: number; lng: number }): LatLng | undefined {
  const lat = num(flags.lat);
  const lng = num(flags.lng);
  if (lat !== undefined && lng !== undefined) return { lat, lng };
  if (lat !== undefined || lng !== undefined) {
    throw new UsageError("--lat and --lng must be given together.");
  }
  return saved ? { lat: saved.lat, lng: saved.lng } : undefined;
}

// ---------------------------------------------------------------------------
// Help
// ---------------------------------------------------------------------------

const HELP = `d1 — Tiendas D1 (Colombia) from the command line

  Catalogue
    d1 search <query>          find products        [--lat --lng --facets --page
                                                     --count --sort --available]
                               --sort per-unit ranks by price per kg/L, which is
                               what "cheapest" usually means for groceries
    d1 substitute <sku>        what to buy instead   [--lat --lng --limit
                                                     --count]
                               ranks in-stock products from the same category
                               and names what changes: brand, pack size, $/kg,
                               and any warning label gained or lost. Proposes
                               only — it never touches your cart.
    d1 basket --budget <cop> <term> [term ...]      [--lat --lng --count]
                               build a shopping list to a spending target, by
                               VALUE rather than pack price. The budget is a
                               hard ceiling; every term it could not fit is
                               named, with the reason. Prints a basket — it
                               never touches your cart.
    d1 suggest <partial>       autocomplete terms
    d1 trending                what Colombia is searching for
    d1 categories              department tree      [--depth N]
    d1 facets [query]          filters for a query

  Location  (availability and price are per-store — set this first)
    d1 region --lat --lng      resolve and remember your delivery point
    d1 stores near             D1 shops near a point [--lat --lng --limit]
                               (locations only — D1 does not offer collection)

  Basket
    d1 cart                    show the current cart
    d1 cart add <sku>          set a line to --qty N [--qty N --seller ID]
    d1 cart set <index> <qty>  change a line (qty 0 removes it)
    d1 cart clear              empty the cart
    d1 addresses               your saved addresses (canonical, from D1)

  Safety
    --yes                      write to a cart this session did not create
    D1_SCRATCH=1               ignore the stored cart; use a throwaway (for tests)
    d1 cart deliver-to         attach the delivery point and quote shipping
                               [--address-id <id> to reuse a saved one]
                               [--street --number --complement --neighborhood
                                --reference --city --state --postal-code]
    d1 cart checkout           print the URL where YOU complete payment
    d1 quote <sku:qty>...      price a basket without touching the cart

  Account
    d1 login --email <addr>    email a one-time code, then --code <code>
    d1 login --from-cookie <t> adopt a browser session token
    d1 whoami                  who is signed in
    d1 logout                  forget the stored session
    d1 orders                  order history        [--page N]
    d1 order <id>              full order detail

  Global
    --json                     machine-readable output
    --sc <n>                   sales channel (trade policy); D1's public one is 1
    --help                     this text

  Exit codes
    0  it worked
    1  D1 refused, or could not be reached — a retry may help
    2  the command was called wrong — a retry never helps
    3  the command worked and the answer is "none"
       (substitute found nothing; basket fit nothing)

This CLI never handles payment. It builds and prices a basket; a human opens
the checkout URL and pays. Stored credentials are limited to one storefront
session token in a 0600 file (~/.config/d1-cli/session.json).`;

// ---------------------------------------------------------------------------
// Commands
// ---------------------------------------------------------------------------

async function main(argv: string[]): Promise<number> {
  const { positional, flags } = parseArgs(argv);
  const asJson = flags.json === true || flags.json === "true";
  const cmd = positional[0];

  const askedForHelp = flags.help === true || cmd === "help";
  if (!cmd || askedForHelp) {
    console.log(HELP);
    // Asking for help SUCCEEDED, even with no other argument — `d1 --help`
    // exiting 2 tells a caller its invocation was wrong when it was not.
    // A bare `d1` with nothing at all is still a usage error.
    return askedForHelp ? 0 : 2;
  }

  // Validated here, before any command body runs.
  //
  // `--sc` is user input that travels straight into a query parameter, and the
  // new `assertAllowedQuery` refuses a non-numeric one — correctly, but as a
  // D1Error carrying "This is a bug in d1-cli", which exits 1 ("D1 refused,
  // retry may help"). That is wrong twice over: it is the caller's typo, not a
  // bug and not retryable. The guard stays fail-closed for anything that
  // reaches it internally; this makes the user-facing path say 2.
  const rawChannel = str(flags.sc);
  if (rawChannel !== undefined && !/^\d+$/.test(rawChannel)) {
    throw new UsageError(
      `--sc must be a sales channel number, got "${rawChannel}". D1 serves its public catalogue on 1.`,
    );
  }

  const stored = loadSession();
  const scratch = isScratch();
  const client = new D1Client({
    authToken: stored?.token,
    // In scratch mode the stored cart is ignored entirely, so a verification
    // run pointed at a populated config directory creates its own throwaway
    // cart instead of reaching the real one.
    orderFormId: scratch ? undefined : stored?.orderFormId,
  });
  const channel = rawChannel ?? DEFAULT_SALES_CHANNEL;

  /** Resolve the point in play, and its region id, without re-asking upstream. */
  const regionFor = async (at?: LatLng) => {
    if (!at) return undefined;
    if (stored?.region && stored.region.lat === at.lat && stored.region.lng === at.lng) {
      return { id: stored.region.id, sellerId: stored.region.sellerId };
    }
    const r = await resolveRegion(client, at, channel);
    return { id: r.id, sellerId: primarySeller(r)?.id };
  };

  switch (cmd) {
    // -- catalogue ---------------------------------------------------------
    case "search": {
      const at = pointFrom(flags, stored?.region);
      const region = await regionFor(at);
      const page = await search(client, {
        query: positional.slice(1).join(" ") || str(flags.query),
        facets: str(flags.facets),
        page: num(flags.page),
        count: num(flags.count),
        sort: str(flags.sort),
        regionId: region?.id,
        salesChannel: channel,
        onlyAvailable: flags.available === true,
      });
      console.log(
        asJson
          ? json({ ...page, regionId: region?.id })
          : renderSearch(page, {
              regionId: region?.id,
              perUnitSorted: str(flags.sort) === "per-unit",
            }),
      );
      return 0;
    }

    case "substitute": {
      const sku = positional[1];
      if (!sku) throw new UsageError("Usage: d1 substitute <sku> [--limit N] [--lat --lng]");
      // Validate BEFORE anything touches the network.
      //
      // `pointFrom`/`regionFor` below issue a live region lookup, so validating
      // inside `findSubstitutes` meant `d1 substitute abc --lat .. --lng ..`
      // called D1 to resolve a region for a SKU that was never going to parse —
      // and with D1 unreachable the caller got exit 1 ("retry may help") for
      // its own typo instead of 2. This is the same shape as `d1 cart bogus`
      // POSTing a real orderForm before deciding the command was invalid, which
      // is why `validateCartArgs` exists.
      assertSkuId(sku);
      // Built and decided by exported pure functions rather than inline here.
      // Nothing in a network-free suite can drive this command's SUCCESS path —
      // the origin is pinned to d1.com.co by construction, so there is no stub
      // to point a subprocess at — and a mutation sweep found the consequences:
      // the exit code could be made constant, `--limit` dropped, and the region
      // never forwarded, all with the suite green. Moving the policy out leaves
      // only the two call sites below unpinned instead of the whole case body.
      // Called for its THROW, not its value, and BEFORE the region lookup.
      // `substituteOptions` validates `--limit` too, but its arguments are
      // evaluated first — so passing `await regionFor(...)` inline put a live
      // request ahead of the validation and `d1 substitute 262 --limit 0
      // --lat .. --lng ..` went to the network before rejecting. Same idiom,
      // and same reason, as `validateCartArgs`.
      limitFlag(flags.limit);
      countFlag(flags.count);
      const region = await regionFor(pointFrom(flags, stored?.region));
      const result = await findSubstitutes(client, sku, substituteOptions(flags, region, channel));
      console.log(asJson ? json(result) : renderSubstitutes(result));
      return substituteExit(result.candidates.length);
    }

    case "basket": {
      const terms = positional.slice(1).filter(Boolean);
      if (!terms.length) {
        throw new UsageError(
          "Usage: d1 basket --budget <pesos> <term> [term ...] [--count N] [--lat --lng]",
        );
      }
      // Validate BEFORE the network, exactly as `substitute` does: `regionFor`
      // below issues a live lookup, so a bad --budget or --count would
      // otherwise cost a request and return exit 1 ("retry may help") for what
      // is really the caller's typo.
      const budget = parseBudget(flags.budget);
      countFlag(flags.count);
      const region = await regionFor(pointFrom(flags, stored?.region));
      const plan = await buildBasket(client, terms, budget, basketOptions(flags, region, channel));
      console.log(
        asJson
          ? json({ ...plan, regionId: region?.id })
          : renderBasket(plan, { regionId: region?.id }),
      );
      return basketExit(plan.lines);
    }

    case "suggest": {
      const q = positional.slice(1).join(" ");
      if (!q) throw new UsageError("Usage: d1 suggest <partial term>");
      const s = await suggest(client, q);
      console.log(
        asJson ? json(s) : s.map((x) => `${String(x.count).padStart(7)}  ${x.term}`).join("\n"),
      );
      return 0;
    }

    case "trending": {
      const s = await topSearches(client);
      console.log(
        asJson ? json(s) : s.map((x) => `${String(x.count).padStart(7)}  ${x.term}`).join("\n"),
      );
      return 0;
    }

    case "categories": {
      const t = await categoryTree(client, num(flags.depth) ?? 2);
      console.log(asJson ? json(t) : renderCategories(t));
      return 0;
    }

    case "facets": {
      const at = pointFrom(flags, stored?.region);
      const region = await regionFor(at);
      const f = await facets(client, {
        query: positional.slice(1).join(" ") || str(flags.query),
        regionId: region?.id,
        salesChannel: channel,
      });
      console.log(asJson ? json(f) : renderFacets(f));
      return 0;
    }

    // -- location ----------------------------------------------------------
    case "stores": {
      // `near` is the only subcommand, and it is required rather than optional
      // so that `d1 stores <something-else>` is a usage error today instead of
      // silently meaning "near" and then changing meaning later.
      const sub = positional[1];
      if (sub !== "near") {
        throw new UsageError("Usage: d1 stores near --lat <lat> --lng <lng> [--limit N]");
      }
      const at = pointFrom(flags, stored?.region);
      if (!at) {
        throw new UsageError("Usage: d1 stores near --lat <lat> --lng <lng> [--limit N]");
      }
      const limit = num(flags.limit);
      if (flags.limit !== undefined && (limit === undefined || limit < 1)) {
        throw new UsageError("--limit must be a positive whole number.");
      }
      const result = await nearbyStores(client, at, { limit });
      console.log(
        asJson
          ? json({ ...result, at, maxReachable: MAX_REACHABLE, collection: false })
          : renderStores(result, at, vtexDay(new Date().getDay())),
      );
      // Exit 3 is "asked, and the answer is genuinely none" — documented CLI-wide
      // as never worth retrying. An answer this parser could not read is not
      // that: the render already refuses to call it an empty neighbourhood, and
      // an agent branching on 3 would record the false fact the prose declines
      // to state. That is a failure on our side, so it is 1.
      return storesExit(result);
    }

    case "region": {
      const at = pointFrom(flags, stored?.region);
      if (!at) throw new UsageError("Usage: d1 region --lat <lat> --lng <lng>");
      const r = await resolveRegion(client, at, channel);
      // Only remember a point D1 can actually deliver to. Persisting an
      // undeliverable one would make every later command fail against a place
      // the user merely asked about, and the failure would name the stale
      // point rather than the mistake.
      if (deliverable(r)) {
        saveSession({
          ...(stored ?? { token: "", savedAt: "" }),
          token: stored?.token ?? "",
          region: { id: r.id, lat: at.lat, lng: at.lng, sellerId: primarySeller(r)?.id },
          savedAt: new Date().toISOString(),
        });
      }
      // Warn when an existing cart was built against a DIFFERENT point.
      //
      // Items already in the cart were judged deliverable at ADD time, against
      // the address the orderForm held then. Those verdicts — including any
      // `cannotBeDelivered` errors — do not re-evaluate when the region moves,
      // and nothing the CLI does afterwards clears them. The only reliable fix
      // is to rebuild, so say that rather than leave a cart that is quietly
      // pinned to somewhere the user no longer is.
      const movedFrom = stored?.region;
      if (
        deliverable(r) &&
        movedFrom &&
        (movedFrom.lat !== at.lat || movedFrom.lng !== at.lng) &&
        !asJson
      ) {
        try {
          const existing = await getCart(client, channel);
          if (existing.items.length > 0) {
            console.error("");
            console.error(
              `Your cart still holds ${existing.items.length} line${existing.items.length === 1 ? "" : "s"} added for ${movedFrom.lat}, ${movedFrom.lng}.`,
            );
            console.error(
              "D1 judged those deliverable at the OLD address and will not re-judge them.",
            );
            console.error("Run `d1 cart clear` and re-add, or check `d1 cart` for errors.");
          }
        } catch {
          // Advisory only — never fail `region` because the cart lookup did.
        }
      }

      console.log(asJson ? json(r) : renderRegion(r));
      if (!deliverable(r) && stored?.region && !asJson) {
        console.error(
          `Keeping your saved delivery point (${stored.region.lat}, ${stored.region.lng}).`,
        );
      }
      return deliverable(r) ? 0 : 1;
    }

    // -- basket ------------------------------------------------------------
    case "cart": {
      const sub = positional[1] ?? "show";

      // Validate BEFORE touching the network.
      //
      // `getCart` used to run first, so `d1 cart bogus-subcommand` — a pure
      // usage error — issued a live POST that CREATES AN ORDERFORM on D1's
      // production storefront before deciding the command was invalid.
      // Measured: 531ms versus 51ms for a genuinely offline usage error.
      //
      // Two costs, neither acceptable. The obvious one is writing to a third
      // party every time someone types a command wrong, including on every
      // test run. The subtler one is that it made this CLI's exit codes depend
      // on D1's availability: with the network down, a usage error surfaced as
      // exit 1 ("D1 refused, retry may help") instead of 2 ("you called this
      // wrong"), which is exactly the confusion the two codes exist to prevent.
      validateCartArgs(sub, positional, flags);

      // Refuse to WRITE to a cart this CLI did not obtain itself.
      //
      // A cart id sitting in session.json is honoured silently, so a test run
      // in a populated config directory once added a stray SKU to a real
      // customer's basket. Reads stay open — blocking them would only train
      // people to reach for --yes.
      if (
        !scratch &&
        isMutating(sub) &&
        stored?.orderFormId &&
        !isOwned(stored.orderFormId, stored.orderFormOwn) &&
        flags.yes !== true
      ) {
        const foreign = await getCart(client, channel);
        console.error(
          `Refusing to modify cart ${foreign.orderFormId} — this session did not create it.`,
        );
        console.error(
          `  It holds ${foreign.items.length} line${foreign.items.length === 1 ? "" : "s"}, ${formatCOP(foreign.total)}.`,
        );
        console.error(
          "  Pass --yes to write to it anyway, or set D1_SCRATCH=1 to work on a throwaway cart.",
        );
        return 2;
      }

      let cart = await getCart(client, channel);
      const persistCart = () => {
        // Scratch runs leave no trace: that is the whole point of the mode.
        if (scratch) return;
        saveSession({
          ...(stored ?? { token: "", savedAt: "" }),
          token: stored?.token ?? "",
          orderFormId: cart.orderFormId,
          orderFormOwn: fingerprint(cart.orderFormId),
          region: stored?.region,
          savedAt: new Date().toISOString(),
        });
      };

      switch (sub) {
        case "show":
          console.log(asJson ? json(cart) : renderCart(cart));
          return 0;

        case "add": {
          const sku = positional[2];
          if (!sku) throw new UsageError("Usage: d1 cart add <sku> [--qty N]");
          const at = pointFrom(flags, stored?.region);
          const region = await regionFor(at);
          const seller = str(flags.seller) ?? region?.sellerId ?? "1";
          const want = quantityFlag(flags.qty);

          // Assert the delivery point BEFORE adding, not after.
          //
          // VTEX evaluates deliverability AT ADD TIME against whatever address
          // the orderForm currently holds, and the resulting
          // `cannotBeDelivered` errors persist even once the address is later
          // corrected — leaving a cart with valid SLAs, a computed total, and
          // an error on every line. Re-asserting afterwards does NOT clear
          // them; only being correct beforehand avoids them. Proven by
          // ordering alone: add-then-deliver-to gave 9 errors where
          // deliver-to-then-add gave none, on the same items and region.
          if (at) {
            try {
              // Only writes when the cart's address is absent or elsewhere.
              // Re-posting a correct address would mint a junk record per add.
              const moved = await ensureDeliveryPoint(client, cart.orderFormId, at);
              if (moved) cart = moved;
            } catch {
              // Not fatal — `cart deliver-to` can still be run explicitly, and
              // failing the add over a transient shipping hiccup is worse.
            }
          }

          cart = await addItems(
            client,
            cart.orderFormId,
            [{ skuId: sku, quantity: want, sellerId: seller }],
            channel,
          );
          persistCart();

          // Verify against the RESULTING quantity, not a delta.
          //
          // VTEX's POST /items SETS the line to the requested quantity when the
          // SKU is already present — it does not add to it. Verified live:
          // `add 262 --qty 2` twice leaves the cart at 2, not 4. So the check
          // is "did the line reach what was asked for", and a delta-based check
          // reports a false failure on any legitimate repeat.
          //
          // Checking the outcome at all still matters: the previous version
          // asked only "is this SKU in the cart", which answers yes whenever
          // the line already existed, so a fully rejected request on an
          // existing line reported success.
          const { ok, got } = addOutcome(cart.items, sku, seller, want);
          if (!ok) {
            console.error(
              got <= 0
                ? `D1 accepted the request but SKU ${sku} is not in the cart — it is probably unavailable from seller ${seller}.`
                : `D1 set SKU ${sku} to ${got}, not the ${want} requested (stock limit, or seller ${seller} cannot supply the rest).`,
            );
            console.log(asJson ? json(cart) : renderCart(cart));
            return 1;
          }
          console.log(asJson ? json(cart) : renderCart(cart));
          return 0;
        }

        case "set": {
          const idx = num(positional[2]);
          const qty = num(positional[3]);
          if (idx === undefined || qty === undefined) {
            throw new UsageError("Usage: d1 cart set <index> <quantity>");
          }
          // Validate shape HERE so a bad argument exits 2. Left to cart.ts it
          // raises a plain D1Error and exits 1, which tells an agent "D1
          // refused, maybe retry" about its own malformed input.
          if (!Number.isInteger(idx) || idx < 0) {
            throw new UsageError(
              `Item index must be a non-negative whole number, got "${positional[2]}".`,
            );
          }
          if (!Number.isInteger(qty) || qty < 0) {
            throw new UsageError(
              `Quantity must be zero or a positive whole number, got "${positional[3]}".`,
            );
          }
          cart = await setQuantity(client, cart.orderFormId, idx, qty, channel);
          persistCart();
          console.log(asJson ? json(cart) : renderCart(cart));
          return 0;
        }

        case "clear":
          cart = await clearCart(client, cart.orderFormId);
          persistCart();
          console.log(asJson ? json(cart) : renderCart(cart));
          return 0;

        case "deliver-to": {
          const savedId = str(flags["address-id"]);
          const at = pointFrom(flags, stored?.region);
          if (!at && !savedId) {
            throw new UsageError(
              "Usage: d1 cart deliver-to --lat <lat> --lng <lng>   (or --address-id <id>; see `d1 addresses`)",
            );
          }
          if (savedId) {
            // Reuse the customer's own canonical record. D1 resolves addresses
            // through its map picker, so a saved entry carries a real
            // street/number, neighborhood, postal code and D1's own
            // coordinates — none of which free text acquires.
            cart = await useSavedAddress(client, cart.orderFormId, savedId);
          } else {
            if (!asJson) {
              // Posting an address without an id makes VTEX MINT a new record
              // in the customer's address book. Nine junk entries accumulated
              // that way before `--address-id` existed, so warn at the write.
              console.error(
                "Note: this creates a new address record in your D1 account. `d1 addresses` lists saved ones; --address-id reuses one.",
              );
            }
            cart = await setDeliveryPoint(client, cart.orderFormId, at, {
              postalCode: str(flags["postal-code"]),
              city: str(flags.city),
              state: str(flags.state),
              street: str(flags.street),
              number: str(flags.number),
              complement: str(flags.complement),
              neighborhood: str(flags.neighborhood),
              reference: str(flags.reference),
            });
          }
          persistCart();
          console.log(asJson ? json(cart) : renderCart(cart));
          return undeliverable(cart).length > 0 ? 1 : 0;
        }

        case "checkout": {
          const url = checkoutUrl(cart.orderFormId);
          const blocked = undeliverable(cart);
          if (asJson) {
            console.log(
              json({
                orderFormId: cart.orderFormId,
                total: cart.total,
                totalFormatted: formatCOP(cart.total),
                itemCount: cart.items.length,
                undeliverable: blocked.map((i) => ({ skuId: i.skuId, name: i.name })),
                readyToCheckout: blocked.length === 0,
                checkoutUrl: url,
                note: "This CLI does not process payment. Open checkoutUrl to pay.",
              }),
            );
          } else if (blocked.length > 0) {
            // Do NOT present a checkout URL as ready when D1 has said it cannot
            // deliver these lines. The URL is still printed — the cart is real
            // and the user may want to fix it in the browser — but it is framed
            // as broken, and the exit code says so.
            console.log(renderCart(cart));
            console.log("");
            console.log(
              `NOT ready to check out: D1 cannot deliver ${blocked.length} line${blocked.length === 1 ? "" : "s"} to this address.`,
            );
            console.log("Fix with `d1 cart deliver-to`, or remove the affected lines.");
            console.log(`  ${url}`);
          } else {
            console.log(renderCart(cart));
            console.log("");
            console.log(`Open this to review and pay (${formatCOP(cart.total)}):`);
            console.log(`  ${url}`);
            console.log("");
            console.log("d1 does not handle payment — you complete it in the browser.");
          }
          return blocked.length > 0 ? 1 : 0;
        }

        default:
          throw new UsageError(`Unknown cart subcommand: ${sub}`);
      }
    }

    case "quote": {
      const specs = positional.slice(1);
      if (specs.length === 0) {
        throw new UsageError("Usage: d1 quote <sku>[:qty] [<sku>[:qty] ...] --lat --lng");
      }
      const at = pointFrom(flags, stored?.region);
      if (!at)
        throw new D1Error(
          "`d1 quote` needs a delivery point: --lat/--lng, or run `d1 region` first.",
        );
      const region = await regionFor(at);
      const seller = str(flags.seller) ?? region?.sellerId;
      if (!seller) {
        throw new D1Error(
          `No D1 store serves ${at.lat}, ${at.lng}, so nothing can be quoted. Set a deliverable point with \`d1 region --lat <lat> --lng <lng>\`.`,
        );
      }
      const items = specs.map((s) => ({ ...parseSpec(s), sellerId: seller }));
      const result = await simulate(client, items, at, {
        regionId: region?.id,
        salesChannel: channel,
      });
      if (asJson) {
        console.log(json({ ...result, regionId: region?.id, sellerId: seller }));
      } else {
        for (const i of result.items) {
          const qty = `×${String(i.quantity).padStart(3)}`;
          console.log(
            `${i.skuId.padEnd(10)} ${qty} ${
              i.available ? formatCOP(i.total).padStart(11) : "unavailable".padStart(11)
            }`,
          );
        }
        for (const sku of result.unknownSkus) {
          console.log(`${sku.padEnd(10)}      ${"not in catalogue".padStart(11)}`);
        }
        console.log("");
        console.log(`Items    ${formatCOP(result.itemsTotal).padStart(11)}`);
        console.log("Shipping:");
        console.log(renderShipping(result.shipping));
      }
      // An empty or partial answer must not report success: `every` on an empty
      // list is vacuously true, which would tell a caller that a SKU D1 has
      // never heard of is buyable.
      const allPresent = result.unknownSkus.length === 0 && result.items.length > 0;
      return allPresent && result.items.every((i) => i.available) ? 0 : 1;
    }

    // -- account -----------------------------------------------------------
    case "login": {
      const cookie = str(flags["from-cookie"]);
      if (cookie) {
        const id = await adoptToken(client, cookie);
        saveSession({
          token: client.authToken ?? "",
          email: id.email,
          orderFormId: stored?.orderFormId,
          region: stored?.region,
          savedAt: new Date().toISOString(),
        });
        console.log(asJson ? json(id) : `Signed in as ${id.email}.`);
        return 0;
      }

      const email = str(flags.email);
      if (!email) {
        throw new UsageError(
          "Usage: d1 login --email <address>   (then: d1 login --email <address> --code <code>)",
        );
      }
      const code = str(flags.code);
      const authToken = str(flags["auth-token"]) ?? (await startAuth(client));

      if (!code) {
        await sendAccessKey(client, authToken, email);
        const msg = loginFollowUp(email, authToken);
        console.log(asJson ? json({ sent: true, email, authToken }) : msg);
        return 0;
      }

      const { token } = await validateAccessKey(client, authToken, email, code);
      client.authToken = token;
      const id = await whoami(client);
      saveSession({
        token,
        email: id?.email ?? email,
        orderFormId: stored?.orderFormId,
        region: stored?.region,
        savedAt: new Date().toISOString(),
      });
      console.log(
        asJson
          ? json({ signedIn: true, email: id?.email ?? email })
          : `Signed in as ${id?.email ?? email}.`,
      );
      return 0;
    }

    case "addresses": {
      const cart = await getCart(client, channel);
      const addrs = await listAddresses(client, cart.orderFormId);
      console.log(asJson ? json(addrs) : renderAddresses(addrs));
      return 0;
    }

    case "whoami": {
      const id = await whoami(client);
      if (!id) {
        console.log(asJson ? json({ signedIn: false }) : "Not signed in.");
        return 1;
      }
      console.log(asJson ? json({ signedIn: true, ...id }) : `${id.email} (${id.account})`);
      return 0;
    }

    case "logout": {
      // Clearing wipes the delivery point and the cart id along with the
      // token — all three are personal, so that is the right default. But a
      // basket built before signing out becomes unreachable from the CLI, and
      // saying nothing about that reads as data loss. Hand back the URL first.
      const orphanedCart = stored?.orderFormId;
      clearSession();
      if (asJson) {
        console.log(
          json({
            signedOut: true,
            forgot: ["session token", "delivery point", "cart id"],
            recoverCartUrl: orphanedCart ? checkoutUrl(orphanedCart) : null,
          }),
        );
      } else {
        console.log("Signed out. Forgot the session token, delivery point, and cart id.");
        if (orphanedCart) {
          console.log("");
          console.log("Your basket still exists in the browser:");
          console.log(`  ${checkoutUrl(orphanedCart)}`);
        }
      }
      return 0;
    }

    case "orders": {
      const { orders, total, pages } = await listOrders(client, {
        page: num(flags.page),
        perPage: num(flags["per-page"]),
      });
      console.log(
        asJson
          ? json({ orders, total, pages })
          : `${renderOrders(orders)}\n\n${total} order${total === 1 ? "" : "s"} · page ${num(flags.page) ?? 1} of ${pages}`,
      );
      return 0;
    }

    case "order": {
      const id = positional[1];
      if (!id) throw new UsageError("Usage: d1 order <orderId>");
      const detail = await getOrder(client, id);
      // Redacted by default: the payload carries a national ID, phone, full
      // address, and card first/last digits that nothing about "where is my
      // order?" requires. --raw opts in deliberately.
      const raw = flags.raw === true || flags.raw === "true";
      const shown = orderForDisplay(detail, raw);
      // JSON is the only sensible rendering of an arbitrary upstream payload,
      // so --json changes nothing about the body — but the advisory line is a
      // human aid and would corrupt a consumer parsing stdout, so it is
      // suppressed under --json (and goes to stderr regardless).
      console.log(json(shown));
      if (!raw && !asJson) {
        console.error("Personal fields redacted. Pass --raw for the full payload.");
      }
      return 0;
    }

    default:
      console.error(`Unknown command: ${cmd}\n`);
      console.error(HELP);
      return 2;
  }
}

if (import.meta.main) {
  main(process.argv.slice(2))
    .then((code) => process.exit(code))
    .catch((err) => {
      if (err instanceof UsageError) {
        // 2 = "you called this wrong"; retrying verbatim will never help.
        console.error(err.message);
        process.exit(2);
      }
      if (err instanceof D1Error) {
        // 1 = "D1 said no, or could not be reached" — a retry may help.
        console.error(err.message);
        process.exit(1);
      }
      console.error(`Unexpected failure: ${err instanceof Error ? err.message : err}`);
      process.exit(1);
    });
}

export { main };
