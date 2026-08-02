---
name: d1-cli
version: 0.1.0
source: https://github.com/broomva/skills
description: Shop Tiendas D1 (Colombia, d1.com.co) from the command line — search the catalogue, resolve your nearest physical store, price a basket against that store's real stock, and quote delivery. D1 runs VTEX IO (account `d1tiendas`), so this drives its public storefront API with no admin key: catalogue and cart work fully anonymously, and a one-time emailed code unlocks order history. Handles the two traps that make naive D1 automation wrong — availability is regionalized (an unregioned query reports a national catalogue nobody can actually buy from) and prices arrive in two different units (search reports whole pesos, checkout reports hundredths, a silent 100x). Builds and prices baskets; it deliberately cannot pay, handing a checkout URL to a human instead. USE WHEN the user wants to find D1 products or prices, check whether D1 delivers somewhere, build or cost a D1 grocery basket, compare D1 items, or review their D1 orders. NOT FOR other Colombian retailers (Éxito, Jumbo, Ara, Alkosto), and not for completing a payment.
author: broomva
license: MIT
tags: [colombia, d1, tiendas-d1, groceries, vtex, vtex-io, ecommerce, cli, retail, shopping, intelligent-search, regionalization]
---

# d1-cli — Tiendas D1 from the command line

D1 is Colombia's largest hard-discount grocery chain. Its storefront runs
**VTEX IO** (account `d1tiendas`), which means the site's own public API is the
integration surface — no scraping, no admin credentials.

## Invoke

```bash
cd skills/commerce/d1-cli

# 1. Resolve your delivery point FIRST — everything else depends on it
bun run src/cli.ts region --lat 4.6486 --lng=-74.0628

# 2. Then search: prices and stock are now your store's, not the country's
bun run src/cli.ts search leche entera --count 5
bun run src/cli.ts search --facets category-1/lacteos-y-huevos --sort price:asc

# 3. Price a basket without touching your cart
bun run src/cli.ts quote 262:2 892:1

# 4. Or build a real one, then hand off to a human to pay
bun run src/cli.ts cart add 262 --qty 2
bun run src/cli.ts cart deliver-to
bun run src/cli.ts cart checkout      # prints a URL; does not pay
```

Add `--json` to any command for agent-readable output. Exit codes are
meaningful: `0` success, `1` failure (undeliverable point, unavailable SKU,
unknown SKU), `2` usage error.

## The two things that make naive D1 automation wrong

**Availability is regionalized.** Query the catalogue with no region and D1
answers from the national catalogue, reporting a comfortable 10,000 units
against the notional seller `1`. Put the same SKU through a checkout simulation
for a real address and it comes back `withoutStock`, because the physical store
that would ship it does not carry it. Always `d1 region` first; the CLI warns
in plain text whenever it is showing you national prices.

Resolving a region is also the single least guessable part of the API: the
coordinates go in as **`geoCoordinates={lon};{lat}` — semicolon-separated,
longitude first**. A comma, which is what VTEX's own JSON bodies use for the
same pair, is rejected with `CHK0119` ("addresses must have a postal code or
geocoordinates") — a message that reads like the parameter is missing rather
than malformed. `test/region.test.ts` pins this so a cleanup cannot undo it.

**Prices arrive in two units.** For SKU 262 (Leche Entera Latti 900 ml, COP
3,500 on the shelf):

| API | Field | Value | Unit |
|---|---|---|---|
| intelligent-search | `Price` | `3500` | whole pesos |
| catalog_system | `Price` | `3500.0` | whole pesos |
| checkout orderForm | `sellingPrice` | `350000` | hundredths |

Neither labels its unit. `catalog.ts` normalizes everything to hundredths at
the boundary so the rest of the code has exactly one unit, and a test asserts a
search-sourced price renders identically to a checkout-sourced one.

## What it will not do

`d1` builds and prices baskets. It does not pay: there is no code path that
accepts a card number, posts `paymentData`, or calls `gatewayCallback`, and
`test/safety.test.ts` fails if one is ever added. `d1 cart checkout` prints the
URL where a human reviews the total and completes payment.

The only credential it stores is a storefront session token — the same thing a
signed-in browser holds, scoped to its owner's own orders and cart — written to
`~/.config/d1-cli/session.json` with mode `0600`. No VTEX admin appKey/appToken
is read anywhere. Sign-in is by one-time emailed code; password authentication
is deliberately not implemented.

## Commands

| Command | What it does |
|---|---|
| `region --lat --lng` | resolve and remember the delivery point |
| `search <query>` | find products (`--facets --sort --count --page --available`) |
| `suggest <partial>` · `trending` | autocomplete · what Colombia is searching |
| `categories` · `facets [query]` | department tree · filters for a query |
| `quote <sku>[:qty]...` | price a basket, no cart mutation |
| `cart [show\|add\|set\|clear\|deliver-to\|checkout]` | build a basket |
| `login --email` / `--from-cookie` · `whoami` · `logout` | account |
| `orders` · `order <id>` | order history |

## Tests

```bash
bun test        # 85 tests: money units, the semicolon gotcha, quantity-in-quote,
                # unknown-SKU vacuity, cart normalization, payment-boundary guards
bun run lint && bun run typecheck
```

See `README.md` for the full endpoint map, the shipping-tier behaviour, and
what the public API will not give you.
