---
name: cub-cli
version: 0.1.0
source: https://github.com/broomva/skills
description: Shop the Cub grocery storefront (cub.com, Minneapolis-St. Paul) from the command line — sweep the sale collections by depth of discount, browse departments, look up prices, and watch products for price drops. Cub runs Instacart Storefront Pro, whose GraphQL endpoint accepts ONLY persisted queries, so this drives it with operation hashes recovered from the storefront's own server-rendered payload rather than a reverse-engineered schema; `ssr_ops.py` regenerates that registry for any Storefront Pro retailer, and `cub harvest --har` adds the client-side operations (search, cart) from a DevTools HAR. Handles the traps that make naive automation wrong — the endpoint rejects raw queries and introspection outright, every read 401s without a session (a guest one suffices), and "Buy 2 for $6" is not a $6 unit price. Reads need no login; cart and orders take your own imported cookies. USE WHEN the user wants Cub prices, Cub deals or sale sweeps, a Cub basket or price watch, or wants to build a client against an Instacart Storefront Pro retailer. NOT FOR other grocery platforms (D1 and VTEX -> d1-cli; Colombian retail -> alkosto-wait-optimizer), not for crawling, and not for completing a payment.
author: broomva
license: MIT
tier: D
tags: [cub, instacart, storefront-pro, groceries, cli, retail, shopping, graphql, persisted-queries, apq, price-watch, har]
---

# cub-cli — the Cub storefront from the command line

Cub is a Minnesota grocery chain. Its site runs **Instacart Storefront Pro**, so the
storefront's own GraphQL API is what this drives — no scraping of rendered HTML, no
headless browser.

```bash
bun run src/cli.ts deals --min-off 40
```

```
   $2.99 (57% off)  Smithfield Naturally Hickory Smoked Thick Cut Bacon  12 oz was $6.99
   $2.99 (54% off)  Blue Bunny Mini Swirls Vanilla Cones  8 ct was $6.49
   $0.56 (49% off)  Pink Lady Apples  1 each was $1.09
```

## The three traps

**1. The endpoint accepts only persisted queries.** `POST /graphql` with a query string
— or an introspection query — returns `PERSISTED_QUERY_NOT_SUPPORTED`. You cannot
compose a request. A client may call exactly the operations whose sha256 hashes have
been *observed*, and no others. The operation registry **is** the capability surface.

Deriving hashes from the JS bundle does not work either: the bundled GraphQL AST is
stripped to bare `OperationDefinition` names, with selection sets assembled at runtime
from fragments spread across modules. Hashes must be observed, never computed.

**2. Every read needs a session.** Unauthenticated calls to product operations return
`401 Not Authenticated`. An *implicit guest* session is enough, and is minted by
fetching the public storefront once and keeping the cookies (`X-IC-bcx`). No login is
required for prices, deals or browsing — only cart, lists and orders need your account.

**3. `"Buy 2 for $6"` is not a $6 item.** Offer labels and price strings share a field
neighbourhood. Parsing a multi-buy label as a unit price silently understates prices,
so price parsing requires the whole label to be numeric and `percentOff` is derived
from the two prices rather than trusting the badge text.

## Recovering the operation registry

`scripts/ssr_ops.py` is the reusable core, and works for **any** Storefront Pro
retailer, not just Cub:

```bash
curl -s https://www.cub.com/store/cub/storefront > page.html
python3 scripts/ssr_ops.py ssr page.html --json > ops.json
```

It reads `<script id="ssr-query-perf-data">` — the server's own record of the GraphQL
requests it issued while server-rendering — and returns each operation's name, hash and
variable shape, plus the store constants a client must send (`shopId`, `zoneId`,
`retailerId`, `retailerLocationId`, `postalCode`).

Search and cart are fetched client-side and appear in no SSR payload. For those, record
once and harvest:

```
DevTools -> Network -> filter `graphql` -> do the action
  -> right-click -> "Save all as HAR with content"
python3 scripts/ssr_ops.py har capture.har --json     # inspect
bun run src/cli.ts harvest --har capture.har          # install into the CLI
```

Harvesting keeps operation name, hash, and the *shape* of the variables only. A HAR is
a recording of a live session, so concrete values — address ids, coordinates, cart ids
— are replaced with type placeholders and never written to disk. Tested.

## Commands

```
cub deals [--min-off N] [--limit N] [--slug S]   sale items, deepest discount first
cub collections                                  browsable collections (department nav)
cub browse --slug <slug> [--limit N]             items in a collection
cub search <term>                                search (degraded until a hash is harvested)
cub watch add <productId> --below <price>        watch a product
cub watch list | check                           list watches / refresh and report triggers
cub harvest --har <file.har>                     add operations from a DevTools HAR
cub ops                                          callable operations + provenance
cub auth import | guest                          import your session / mint a guest one
--json                                           machine-readable output
```

`search` announces when it is degraded. Until a search hash is harvested there is no
way to query the whole store, so it filters the collections it *can* reach and says so
— rather than returning a confident empty result for an item that is plainly in stock.

## Another retailer on the same platform

`src/constants.ts` holds the Cub-specific ids. Point them at another Storefront Pro
retailer, regenerate the registry with `ssr_ops.py ssr`, and the rest of the client is
unchanged — the transport, session bootstrap and parsing are platform-level, not
Cub-specific.

## Scope and conduct

`cub.com/robots.txt` is an allowlist: named search crawlers get scoped access and the
final rule is `User-Agent: * -> Disallow: /`.

This client is scoped to **personal use on your own session at human pace**. Requests
are serialized behind a fixed 1.1s floor, it fetches only what a command needs, and it
has no bulk-enumeration mode. Keep it that way. Anything commercial or high-volume
belongs on Instacart's partner Developer Platform instead. It deliberately cannot pay.

Session material lives at `~/.config/cub-cli/session.json` mode `0600`, gitignored,
never logged. `*.har` is gitignored for the same reason.

## Tests

```bash
python3 tests/test_ssr_ops.py   # 14 — registry recovery, redaction, HAR harvesting
bun test                        # 16 — price parsing, item extraction, harvest
```
