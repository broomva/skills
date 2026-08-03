# Changelog

All notable changes to the **d1-cli** skill are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/); versioning: [SemVer](https://semver.org).

## [0.2.0] — 2026-08-03

### Added

- `d1 addresses` — the customer's own saved address book, with ids.
- `cart deliver-to --address-id <id>` — reuse a saved address instead of
  synthesizing one. Short id prefixes resolve.

### Fixed

- **The CLI was writing junk into the customer's address book.**
  `setDeliveryPoint` posted an address with no `addressId`, so VTEX minted a NEW
  record on EVERY call. Measured on a live account: **9 junk entries**, all
  carrying the CLI's geocoded coordinates, all with null street — visible to the
  customer under "Mis direcciones". A read-shaped command had a persistent write
  side effect.

### Why a saved address is better than ours

D1 canonicalizes through a map picker the CLI cannot drive. The same address:

  typed by us   street "Cra 13 # 172a-51", no postal code, OSM coordinates
  D1 canonical  street "KR 15" + number "170 - 84",
                neighborhood "SAN JOSE DE USAQUEN", postal 110141660,
                D1's own coordinates

Free text is never canonicalized — it just adds another uncanonical record.

Note that sending the `addressId` ALONE does not work: VTEX ignores it and
selects a fresh empty address. The whole record has to be posted back, which is
what `useSavedAddress` does. Found by trying the obvious thing first and
watching it fail against a live account.

## [0.1.4] — 2026-08-03

### Verified

- The one-time-code sign-in path (`accesskey/send` + `accesskey/validate`) is
  now exercised live, including its failure modes: a wrong code and a replayed
  already-consumed code are both rejected with exit 1 and no session written.
  VTEX reports a bad code with HTTP **200** and `authStatus: WrongCredentials`,
  so the body check in `session.ts` is what catches it, not the status code.

### Fixed (documentation)

- README claimed every endpoint but order-detail had been verified live. The
  two access-key endpoints had not been — sending a code writes to someone's
  inbox, so they were deliberately left untested. The claim is true as of this
  release; the correction is recorded because "all verified" reads the same
  whether or not it holds.

## [0.1.3] — 2026-08-03

### Added

- `cart deliver-to` now takes `--number`, `--complement`, `--neighborhood` and
  `--reference` alongside `--street`. An apartment could not previously be
  expressed at all: everything went on the street line, and couriers and D1's
  checkout read the unit from `complement`, so a delivery would reach the
  building and stop. Found on a real order to a tower/apartment address.

## [0.1.2] — 2026-08-03

### Fixed

- **A cart D1 refused to deliver still read as ready to pay.** VTEX reports
  `cannotBeDelivered` with `status: "error"` while STILL returning a valid SLA
  per line and a computed total, and the CLI printed those messages BELOW the
  total and the checkout URL. Observed live: nine lines, nine errors, and a
  cart presenting "$95.930 ready to pay".

  Three defences, because no single one is sufficient:

  1. `cart add` asserts the delivery point BEFORE adding. VTEX judges
     deliverability at ADD time against whatever address the orderForm then
     holds; re-asserting afterwards does NOT clear the resulting errors. Proven
     by ordering alone — add-then-deliver-to gave 9 errors where
     deliver-to-then-add gave 0, same items, same region, same account.
  2. `d1 region` warns when a non-empty cart was built against a different
     point. Items already added keep their old verdict and nothing clears it,
     so the only real fix is to rebuild — the CLI now says so instead of
     leaving a cart quietly pinned to somewhere the user no longer is.
  3. `cart checkout` **exits 1** and refuses the ready-to-pay framing when any
     line is undeliverable. Message severity now travels with the text
     (`CartMessage.status`) instead of being flattened to a string, and errors
     render ABOVE the total.

### Changed

- `Cart.messages` is now `CartMessage[]` (`text`/`code`/`status`) rather than
  `string[]`. Severity could not survive as prose.

## [0.1.1] — 2026-08-02

### Fixed

- **Shipping was under-reported by the number of cart lines.** VTEX repeats
  `logisticsInfo` per line and each entry's `slas[].price` is that line's
  SHARE. Deduplicating the repeated SLA and showing the first share displayed
  COP 1,125 on a 12-line basket whose delivery actually cost COP 13,500.
  Now summed per option; agrees with the orderForm's `Shipping` totalizer.

  The tell was on screen and nearly missed: `Items 109.870` + `Shipping 1.125`
  against `Total 123.370`. Items + shipping ≠ total.

  Found by building the first realistic grocery basket. Every prior fixture used
  1–2 lines, where a share is indistinguishable from the total — the same
  blind spot as the quantity bug that was invisible to quantity-1 fixtures.

### Retracted

- README gotcha 7 claimed shipping "varies with basket composition, and not
  monotonically", with a table showing a larger basket getting cheaper delivery.
  That was this bug, not a property of D1. Delivery is a flat COP 13,500.

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

The runtime half pins the **origin first, then the path**. Checking the path
alone was itself a hole, and a worse one than the traversal it closed:

    new URL("//evil.example/api/checkout/pub/regions", ORIGIN)
      -> host evil.example, pathname /api/checkout/pub/regions   <- APPROVED

`new URL()` resolves a protocol-relative path by REPLACING THE HOST, so an
approved-looking pathname would have carried the session cookie to a foreign
origin. Found by attacking the round-2 fix rather than by review.

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

### Found in round 3

- **The exit-code test harness was not network-free, and said it was.**
  `case "cart"` fetched the cart BEFORE the subcommand switch, so
  `d1 cart bogus` issued a live POST creating an orderForm on D1's production
  storefront before deciding the command was invalid — 531ms versus 51ms for a
  genuinely offline usage error. Every test run wrote to a third party, six
  assertions silently depended on egress, and with the network down a usage
  error surfaced as exit 1 instead of 2. Two shipped comments asserted the
  opposite property. `validateCartArgs` now runs first, and the test MEASURES
  network-freedom rather than claiming it.
- A malformed `--facets` threw `D1Error`, so it exited 1 — the same class fixed
  for `cart set` and missed on its sibling. Now `UsageError` -> 2. The test that
  should have caught it asserted `code > 0`, the one loose assertion in a file
  whose entire job is pinning exit codes.
- `--sc` was the only path interpolation left unencoded, so `%2F` passed a
  `[^/]+` guard. Now `encodeURIComponent`d.
- The redaction DEFAULT was unbound: replacing the selection with plain `detail`
  left all 155 tests green while shipping national IDs to stdout. Extracted as
  `orderForDisplay` with both arms tested.

### Known gap

`orders.totalValue` is treated as hundredths by inference from the rest of the
checkout API, not from observation — the account this was built against has no
D1 order history. A fixture pins the assumption so a wrong reading is traceable.
