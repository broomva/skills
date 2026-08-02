#!/usr/bin/env bun
/**
 * `d1` — command-line access to Tiendas D1 (Colombia).
 *
 * Designed to be driven by an agent as much as by a person: every command takes
 * `--json`, exit codes are meaningful (0 ok, 1 failure, 2 usage), and nothing
 * prompts unless it has to.
 *
 * The CLI can find products, price a basket against a real store, and quote
 * delivery. It cannot pay — `d1 cart checkout` prints the URL where a human
 * finishes. See `cart.ts` for why that line is drawn where it is.
 */

import {
  addItems,
  checkoutUrl,
  clearCart,
  getCart,
  setDeliveryPoint,
  setQuantity,
  simulate,
} from "./cart.ts";
import { categoryTree, facets, search, suggest, topSearches } from "./catalog.ts";
import { D1Client } from "./client.ts";
import { formatCOP } from "./money.ts";
import { getOrder, listOrders } from "./orders.ts";
import {
  json,
  renderCart,
  renderCategories,
  renderFacets,
  renderOrders,
  renderRegion,
  renderSearch,
  renderShipping,
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
import { D1Error, DEFAULT_SALES_CHANNEL, type LatLng } from "./types.ts";

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
    throw new D1Error(`Malformed item "${spec}". Expected <sku> or <sku>:<qty>.`);
  }
  const [skuId, rawQty] = parts;
  if (!skuId) throw new D1Error(`Malformed item "${spec}". Missing SKU.`);

  if (rawQty === undefined) return { skuId, quantity: 1 };
  const quantity = Number(rawQty);
  if (!Number.isInteger(quantity) || quantity < 1) {
    throw new D1Error(`Quantity in "${spec}" must be a positive whole number, got "${rawQty}".`);
  }
  return { skuId, quantity };
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
    throw new D1Error("--lat and --lng must be given together.");
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
    d1 suggest <partial>       autocomplete terms
    d1 trending                what Colombia is searching for
    d1 categories              department tree      [--depth N]
    d1 facets [query]          filters for a query

  Location  (availability and price are per-store — set this first)
    d1 region --lat --lng      resolve and remember your delivery point

  Basket
    d1 cart                    show the current cart
    d1 cart add <sku>          add a SKU            [--qty N --seller ID]
    d1 cart set <index> <qty>  change a line (qty 0 removes it)
    d1 cart clear              empty the cart
    d1 cart deliver-to         attach the delivery point and quote shipping
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
    --help                     this text

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

  if (!cmd || flags.help === true || cmd === "help") {
    console.log(HELP);
    return cmd ? 0 : 2;
  }

  const stored = loadSession();
  const client = new D1Client({
    authToken: stored?.token,
    orderFormId: stored?.orderFormId,
  });
  const channel = str(flags.sc) ?? DEFAULT_SALES_CHANNEL;

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
          : renderSearch(page, { regionId: region?.id }),
      );
      return 0;
    }

    case "suggest": {
      const q = positional.slice(1).join(" ");
      if (!q) throw new D1Error("Usage: d1 suggest <partial term>");
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
    case "region": {
      const at = pointFrom(flags, stored?.region);
      if (!at) throw new D1Error("Usage: d1 region --lat <lat> --lng <lng>");
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
      let cart = await getCart(client, channel);
      const persistCart = () =>
        saveSession({
          ...(stored ?? { token: "", savedAt: "" }),
          token: stored?.token ?? "",
          orderFormId: cart.orderFormId,
          region: stored?.region,
          savedAt: new Date().toISOString(),
        });

      switch (sub) {
        case "show":
          console.log(asJson ? json(cart) : renderCart(cart));
          return 0;

        case "add": {
          const sku = positional[2];
          if (!sku) throw new D1Error("Usage: d1 cart add <sku> [--qty N]");
          const at = pointFrom(flags, stored?.region);
          const region = await regionFor(at);
          const seller = str(flags.seller) ?? region?.sellerId ?? "1";
          cart = await addItems(
            client,
            cart.orderFormId,
            [{ skuId: sku, quantity: num(flags.qty) ?? 1, sellerId: seller }],
            channel,
          );
          persistCart();
          if (!cart.items.some((i) => i.skuId === sku)) {
            console.error(
              `D1 accepted the request but SKU ${sku} is not in the cart — it is probably unavailable from seller ${seller}.`,
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
            throw new D1Error("Usage: d1 cart set <index> <quantity>");
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
          const at = pointFrom(flags, stored?.region);
          if (!at) throw new D1Error("Usage: d1 cart deliver-to --lat <lat> --lng <lng>");
          cart = await setDeliveryPoint(client, cart.orderFormId, at, {
            postalCode: str(flags["postal-code"]),
            city: str(flags.city),
            state: str(flags.state),
            street: str(flags.street),
          });
          persistCart();
          console.log(asJson ? json(cart) : renderCart(cart));
          return 0;
        }

        case "checkout": {
          const url = checkoutUrl(cart.orderFormId);
          if (asJson) {
            console.log(
              json({
                orderFormId: cart.orderFormId,
                total: cart.total,
                totalFormatted: formatCOP(cart.total),
                itemCount: cart.items.length,
                checkoutUrl: url,
                note: "This CLI does not process payment. Open checkoutUrl to pay.",
              }),
            );
          } else {
            console.log(renderCart(cart));
            console.log("");
            console.log(`Open this to review and pay (${formatCOP(cart.total)}):`);
            console.log(`  ${url}`);
            console.log("");
            console.log("d1 does not handle payment — you complete it in the browser.");
          }
          return 0;
        }

        default:
          throw new D1Error(`Unknown cart subcommand: ${sub}`);
      }
    }

    case "quote": {
      const specs = positional.slice(1);
      if (specs.length === 0) {
        throw new D1Error("Usage: d1 quote <sku>[:qty] [<sku>[:qty] ...] --lat --lng");
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
        throw new D1Error(
          "Usage: d1 login --email <address>   (then: d1 login --email <address> --code <code>)",
        );
      }
      const code = str(flags.code);
      const authToken = str(flags["auth-token"]) ?? (await startAuth(client));

      if (!code) {
        await sendAccessKey(client, authToken, email);
        const msg = `A one-time code is on its way to ${email}. Finish with:\n  d1 login --email ${email} --auth-token ${authToken} --code <code>`;
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

    case "whoami": {
      const id = await whoami(client);
      if (!id) {
        console.log(asJson ? json({ signedIn: false }) : "Not signed in.");
        return 1;
      }
      console.log(asJson ? json({ signedIn: true, ...id }) : `${id.email} (${id.account})`);
      return 0;
    }

    case "logout":
      clearSession();
      console.log(asJson ? json({ signedOut: true }) : "Session cleared.");
      return 0;

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
      if (!id) throw new D1Error("Usage: d1 order <orderId>");
      console.log(json(await getOrder(client, id)));
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
      if (err instanceof D1Error) {
        console.error(err.message);
      } else {
        console.error(`Unexpected failure: ${err instanceof Error ? err.message : err}`);
      }
      process.exit(1);
    });
}

export { main };
