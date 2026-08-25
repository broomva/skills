# cub-cli

CLI for the Cub grocery storefront — `search`, `deals`, `browse`, and price `watch`
over the store's own GraphQL API.

```bash
bun run src/cli.ts deals --min-off 40
```

```
   $2.99 (57% off)  Smithfield Naturally Hickory Smoked Thick Cut Bacon  12 oz was $6.99
   $2.99 (54% off)  Blue Bunny Mini Swirls Vanilla Cones  8 ct was $6.49
   $0.56 (49% off)  Pink Lady Apples  1 each was $1.09
```

## What this actually talks to

`www.cub.com` runs **Instacart Storefront Pro**. The relevant facts, all verified rather
than assumed:

| | |
|---|---|
| Endpoint | `https://www.cub.com/graphql` |
| Transport | `GET` with `operationName`, `variables`, `extensions.persistedQuery.sha256Hash` (Apollo APQ) |
| Raw queries | **Rejected** — `PERSISTED_QUERY_NOT_SUPPORTED` |
| Introspection | **Disabled** — same rejection |
| Reads | Require a session; an implicit *guest* session is enough |
| Account ops | Require your real logged-in cookies |

Store constants recovered from the storefront's SSR payload: retailer `cub` (id `142`),
`shopId` 9758, `retailerLocationId` 24999, `zoneId` 205, postal 55113. These are
location-specific — see `src/constants.ts`.

## The operation registry is the capability surface

Because the endpoint is persisted-query-only, this client can call **exactly** the
operations whose sha256 hashes have been observed in real traffic, and no others. There
is no way to compose a new query: the server only recognises hashes it has seen.

The 58 shipped hashes in `data/ops.json` were extracted from
`<script id="ssr-query-perf-data">` — the storefront's *own* record of the GraphQL
requests it issued while server-rendering. No browser automation was involved.

Attempting to derive hashes statically from the JS bundle does not work: the bundled
GraphQL AST is stripped to bare `OperationDefinition` names, with selection sets
assembled at runtime from fragments spread across modules. Hashes must be **observed**.

## Adding operations: `cub harvest`

Search and cart operations are fetched client-side, so they never appear in any SSR
payload. To teach the CLI a new operation, record it once:

1. Open cub.com in your browser, DevTools → **Network**, filter `graphql`
2. Perform the action you want (run a search, add something to the cart)
3. Right-click the request list → **Save all as HAR with content**
4. `bun run src/cli.ts harvest --har ~/Downloads/www.cub.com.har`

```
harvested 3 operation(s) from 41 graphql entr(ies):
  SearchResultsPlacements
  ...
```

Harvested operations merge into `~/.config/cub-cli/harvested-ops.json` and become
callable immediately. `cub search` picks up a search hash automatically as soon as one
is present.

Only operation name, hash, and the *shape* of the variables are read. Concrete values
are replaced with type placeholders, so address ids, coordinates and cart ids in the HAR
are never written to disk — enforced by a test.

## Commands

```
cub deals [--min-off N] [--limit N] [--slug S]   items on sale, deepest discount first
cub collections                                  browsable collections (department nav)
cub browse --slug <slug> [--limit N]             items in a collection
cub search <term> [--limit N]                    search (degraded until a hash is harvested)
cub watch add <productId> --below <price>        watch a product
cub watch list | check                           list watches / refresh and report triggers
cub harvest --har <file.har>                     add operations from a DevTools HAR
cub ops                                          show callable operations + provenance
cub auth import | guest                          import your session / mint a guest one
--json                                           machine-readable output
```

### `search` is honest about being degraded

Until a search hash is harvested there is no way to query the whole store. Rather than
return a confident empty result for an item that is plainly in stock, `search` filters
the collections it *can* reach and prints a notice saying so. Real search switches on
the moment a hash is available.

## Sessions

Reads run on a guest session minted automatically on first use (one page fetch, cookies
kept). No login, no personal data.

Account operations — cart, lists, orders — need your own session:

```bash
cub auth import   # paste your Cookie: header for www.cub.com, Ctrl-D
```

Session material is written to `~/.config/cub-cli/session.json` mode `0600`, is
gitignored, and is never logged. `*.har` is gitignored for the same reason.

## Scope and conduct

`cub.com/robots.txt` is an allowlist: named search crawlers get scoped access and the
final rule is `User-Agent: * → Disallow: /`.

This client is therefore scoped to **personal use on your own session at human pace** —
not crawling. It serializes every request behind a fixed floor
(`MIN_REQUEST_INTERVAL_MS`, 1.1s), fetches only what a command needs, and has no
bulk-enumeration mode. Keep it that way. For anything commercial or high-volume, the
sanctioned route is Instacart's partner Developer Platform, not this.

## Tests

```bash
bun test    # 16 tests: price parsing, item extraction, HAR harvesting, redaction
```

Parsing is covered against the real response shapes, including the cases that bite:
`"Buy 2 for $6"` must not parse as a `$6` unit price, `percentOff` is derived from
prices rather than trusting the badge string, and one product appearing under several
collection wrappers must deduplicate.
