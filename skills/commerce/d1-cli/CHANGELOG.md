# Changelog

All notable changes to the **d1-cli** skill are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/); versioning: [SemVer](https://semver.org).

## [0.1.0] — 2026-08-02

Initial release. Reverse-engineered `d1.com.co` and found it runs VTEX IO
(account `d1tiendas`), which turned the task from protocol archaeology into
mapping which of VTEX's public storefront endpoints D1 exposes. All are
verified live except order-detail (no order history on the account used);
catalogue and cart need no credentials at all.

### Added

- `region` — resolve a delivery point to its fulfilling physical store.
- `search`, `suggest`, `trending`, `categories`, `facets` — catalogue reads.
- `quote` — price a basket without mutating the cart.
- `cart` — `show` / `add` / `set` / `clear` / `deliver-to` / `checkout`.
- `login` (one-time emailed code, or adopt a browser token), `whoami`, `logout`.
- `orders`, `order <id>` — order history; detail redacted by default, `--raw` opts in.
- `--json` on every command; exit codes `0` ok, `1` upstream failure, `2` usage.

### Gotchas encoded as tests

- `geoCoordinates` is `{lon};{lat}` — **semicolon**, longitude first. A comma
  fails with `CHK0119`, whose message implicates the wrong parameter.
- Search reports prices in whole pesos while checkout reports hundredths — a
  silent 100×. Normalized to hundredths at the boundary.
- `simulation` returns a per-unit `price`; the line total is
  `priceDefinition.total`. Summing `price` under-reports any quantity > 1.
- An unknown SKU returns `items: []` with HTTP 200, so `every(available)` passes
  vacuously. Unanswered SKUs are tracked and reported.
- `POST /items` **sets** a line's quantity rather than adding to it.
- Search pagination is capped at 50 pages.

### The payment boundary, and what changed about how it is enforced

No payment surface: no card fields, no `paymentData`, no `gatewayCallback`.
`d1 cart checkout` hands a URL to a human.

This shipped first as a **blocklist** — five banned strings greped over a
non-recursive `readdirSync` — and cross-model review defeated it three ways,
each proven by mutation while all 89 tests stayed green:

1. `src/pay/settle.ts`, a complete card-taking settlement path containing every
   banned string verbatim, was never read, because the walk did not recurse.
2. The banned list omitted `orderForm/{id}/transaction` — the endpoint VTEX
   actually uses to place an order — because it was written from memory.
3. `["card" + "Number"]` as a computed key slips past a substring match.

It is now enforced in two places from one list (`src/endpoints.ts`): at runtime
in `D1Client.request` against the resolved `URL.pathname`, and statically over
every `/api/` literal under `src/`.

The runtime half was added in round 2, after review showed a static scan is not
sufficient. Every literal in the source was approved and
`d1 search --facets '../../../../../../api/checkout/pub/orderForm/X/transaction'`
still resolved onto the endpoint VTEX uses to **settle an order**:
`encodeURIComponent` does not escape `.`, so `..` survived and `new URL()`
normalized it. Checking the resolved pathname closes that class and the
fragment-assembly limit a static scan can never cover.

Inverting to an allowlist fixed the enumeration problem, not the coverage
problem. Four further holes were found by attacking the fix: a walk filtering
`.ts` and missing `.mts`/`.tsx`; a comment stripper a `"/*"` string could blind;
and — a regression introduced by the fix for that one — a whole-line rule that
deleted `/**/ const PAY = "..."` along with its live code. Both stripper vectors
are now asserted **together**, because closing either alone reopened the other.

The docs no longer claim more than the tests prove.

Likewise, the `0600` session-file guarantee was a grep for the literal `0o600`
and passed while real saves produced mode `666` — `writeFileSync` ignores its
mode argument when the file already exists, so only the explicit `chmod`
enforces it. It now saves twice and `statSync`s the result.

### Also fixed after review

- `cart add` reported success when a rejected add left an existing line
  unchanged; it now verifies the resulting quantity.
- `--qty abc` silently added one unit — the exact failure `parseSpec` already
  rejected on the read-only path, on the path that mutates a real basket.
- Usage errors exited `1`, indistinguishable from an outage; they now exit `2`.
- `d1 order` printed the customer's national ID, phone, address and card digits
  unredacted.
- The `Discounts` totalizer was dropped, leaving promoted carts with an
  unexplained gap between subtotal and total.
- A test named for the `--lng -74.06` hazard asserted only the `--lng=-74.06`
  form and never exercised the branch it described.
- `main()` was invoked by no test at all, so the `cart add` verdict and the
  exit-code split were correct but unproven — the original bugs could be
  restored verbatim and the suite stayed green. Integration tests now spawn the
  real CLI, and immediately caught `d1 --help` exiting 2 instead of 0.
- `cart add` matched by SKU alone, so a same-SKU line under a different seller
  satisfied a request that upstream had rejected. Now scoped by seller.
- `cart set 0 1.5` and `cart set -1 3` reached cart.ts's guard and exited 1,
  reporting the caller's own malformed input as an upstream refusal.
- The `0600` test did not prove the explicit `chmod` was necessary: deleting it
  stayed green, because the first write creates the file at `0600` and the
  second inherits it. The case it actually protects — a pre-existing loose-mode
  file — is now covered.

### Known gap

`orders.totalValue` is treated as hundredths by inference from the rest of the
checkout API, not from observation — the account this was built against has no
D1 order history. A fixture pins the assumption so a wrong reading is traceable.
