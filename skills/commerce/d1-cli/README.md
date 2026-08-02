# d1-cli

Command-line access to **Tiendas D1**, Colombia's largest hard-discount grocery
chain, at [d1.com.co](https://www.d1.com.co/).

D1's storefront runs **VTEX IO** — account `d1tiendas`, workspace `master`,
served through CloudFront (Bogotá edge) and VTEX's Janus router. That is the
whole reverse-engineering result: the integration surface is VTEX's documented
public storefront API, not a bespoke protocol and not HTML scraping. This CLI
drives the same endpoints the website calls from a browser.

```bash
bun install
bun run src/cli.ts region --lat 4.6486 --lng=-74.0628
bun run src/cli.ts search leche entera --count 5
bun run src/cli.ts quote 262:2 892:1
```

## Endpoint map

Every endpoint below was verified live against `www.d1.com.co` on 2026-08-02.
The catalogue and cart columns need **no credentials at all**.

| Endpoint | Auth | Used for |
|---|---|---|
| `GET /api/io/_v/api/intelligent-search/product_search/{facets}` | none | `search` |
| `GET /api/io/_v/api/intelligent-search/facets/trade-policy/{sc}` | none | `facets` |
| `GET /api/io/_v/api/intelligent-search/autocomplete_suggestions` | none | `suggest` |
| `GET /api/io/_v/api/intelligent-search/top_searches` | none | `trending` |
| `GET /api/catalog_system/pub/category/tree/{depth}` | none | `categories` |
| `GET /api/checkout/pub/regions` | none | `region` |
| `POST /api/checkout/pub/orderForm` | none | `cart` |
| `POST /api/checkout/pub/orderForm/{id}/items` | none | `cart add` |
| `POST /api/checkout/pub/orderForm/{id}/items/update` | none | `cart set` |
| `POST /api/checkout/pub/orderForm/{id}/items/removeAll` | none | `cart clear` |
| `POST /api/checkout/pub/orderForm/{id}/attachments/shippingData` | none | `cart deliver-to` |
| `POST /api/checkout/pub/orderForms/simulation` | none | `quote` |
| `GET /api/vtexid/pub/authentication/start` | none | `login` |
| `POST /api/vtexid/pub/authentication/accesskey/{send,validate}` | none | `login` |
| `GET /api/vtexid/pub/authenticated/user` | session | `whoami` |
| `GET /api/oms/user/orders` | session | `orders` |

## Gotchas, and why each one matters

### 1. `geoCoordinates` is semicolon-separated, longitude first

```
?country=COL&geoCoordinates=-74.0628;4.6486     ✅  region + store seller
?country=COL&geoCoordinates=-74.0628,4.6486     ❌  CHK0119
```

A comma is the obvious choice — it is what VTEX's own JSON bodies use for the
same coordinate pair — and it fails with `CHK0119`, *"Direcciones deben tener el
código postal o geocoordenadas"*. That message says the parameter is **missing**,
so the natural next move is to add a postal code, which appears to work: the
call returns 200 with a region id. But `sellers` comes back empty, and an empty
seller list is indistinguishable from "D1 doesn't deliver here". This is the
single hardest thing to discover about the API.

### 2. Availability and price are regionalized

Without a region, search reports the national catalogue: seller `1`
("Tiendas D1"), 10,000 units of everything. Run the same SKU through a checkout
simulation for a real address and it can come back `withoutStock` — the physical
store that would ship it does not carry it. A region resolves to a store seller
id like `d1bon11808cc`, and that is what checkout actually prices against.

The CLI prints a warning whenever it is showing national prices, and `d1 region`
refuses to remember a point D1 cannot deliver to.

### 3. Prices arrive in two different units

| API | Field | SKU 262 | Unit |
|---|---|---|---|
| intelligent-search | `Price` | `3500` | whole pesos |
| catalog_system | `Price` | `3500.0` | whole pesos |
| checkout orderForm | `sellingPrice` | `350000` | hundredths |

All three mean **COP 3,500**. Nothing in the payload says which unit you are
looking at, and both readings produce a plausible grocery total — which is what
makes the 100× error dangerous. `catalog.ts` normalizes to hundredths at the
boundary; a test asserts the two sources agree.

### 4. `simulation` reports a per-unit price, not a line total

`items[].price` is the price of **one** unit; the line is
`items[].priceDefinition.total`, and the basket is `totals[].value` where
`id === "Items"`. Summing `price` quietly ignores quantity — this CLI shipped
that bug for about ten minutes and quoted a two-litre basket 35% light.

### 5. An unknown SKU returns an empty list, not an error

Ask `simulation` about a SKU that does not exist and it answers `items: []`
with HTTP 200. Any `every(item => item.available)` check then passes vacuously,
reporting that a nonexistent product is buyable. The CLI tracks which requested
SKUs went unanswered and reports them as `not in catalogue`.

### 6. Pagination stops at 50 pages

Page 51 returns HTTP 400 carrying *"Page should not exceed 50 pages"*. Wide
result sets have to be narrowed with `--facets`, not paged through. `search`
reports `truncated: true` when matches exceed reachable depth.

### 7. Shipping varies with basket composition, and not monotonically

Observed at the same delivery point, same day:

| Basket | Items total | Quoted shipping |
|---|---|---|
| `262 ×1` … `262 ×30` | COP 3,500 – 105,000 | COP 13,500 (flat) |
| `262 ×2 + 892 ×1` | COP 10,090 | COP 9,000 |

A larger basket got *cheaper* shipping, so this is not a simple value tier. The
mechanism is not documented and has not been established here — which is exactly
why the CLI always quotes shipping from upstream rather than modelling it.
Never assume a delivery cost; run `quote` or `cart deliver-to`.

## What the public API will not give you

- **Saved addresses and profile records.** `dataentities/AD` and `dataentities/CL`
  answer `403 Cannot filter by private fields` for a storefront token. Addresses
  are reachable only through the live cart or an existing order.
- **Payment.** Deliberately out of scope — see below.

## Safety boundary

`d1` assembles and prices baskets. It does not pay. No code path accepts a card
number, posts `paymentData`, or calls `gatewayCallback`, and `test/safety.test.ts`
fails if one is added — the boundary is enforced by CI, not by good intentions.
`d1 cart checkout` prints the URL where a human reviews the total and pays.

The only stored credential is a storefront session token (what a signed-in
browser holds, scoped to its owner's own data), written to
`~/.config/d1-cli/session.json` with mode `0600` and never printed. No VTEX
admin `appKey`/`appToken` is read anywhere. Sign-in uses a one-time emailed
code; password authentication is intentionally not implemented.

Override the config location with `D1_CONFIG_DIR`.

## Tests

```bash
bun test           # 89 tests
bun run lint
bun run typecheck
```

The suite is network-free — every test drives an injected `fetch` stub. Notable
cases pin the gotchas above: the semicolon separator, the cross-API price-unit
agreement, quantity surviving a quote, the vacuous unknown-SKU pass, and the
absence of a payment surface.

## Roadmap

- Pickup points (`public.favoritePickup` appears in D1's session whitelist).
- Coupon application (`orderForm/{id}/coupons` is present but unexercised).
- Address-string → coordinate resolution, so `--lat/--lng` becomes optional.
