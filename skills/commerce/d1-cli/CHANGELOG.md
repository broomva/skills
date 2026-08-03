# Changelog

All notable changes to the **d1-cli** skill are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/); versioning: [SemVer](https://semver.org).

## [0.5.0] — 2026-08-03

### Added — `d1 substitute <sku>`, because a basket that strands is not repaired by pricing it better

Two real sessions stopped dead on a line D1 could not supply: a mandarin juice
out of stock at the customer's store but present at the test one, and
`PAN ARTESANAL INTEGRAL` sold out overnight mid-basket. The CLI could price a
basket and refuse to check out a broken one; it had no way to fix one.

`substitute` resolves the SKU, sweeps its own leaf category at the resolved
region, ranks what is actually in stock, and prints **what changes** per
candidate — brand, pack size, `$/kg` or `$/L`, pack price, and any Ley 2120
warning gained or lost. The deltas are the output; the score only orders them.

It **proposes and never replaces**. Nothing here writes to a cart; it prints the
`d1 cart add` a human may choose to run. The customer twice preferred a line
*removed* over a wrong substitute and said so explicitly, and a ranker that
knows a name and a price cannot see what made them right.

Two design points that are not obvious:

- **Measure is a grouping, not a score.** A candidate sold by the unit can match
  the source's name exactly and still must not lead a list of `$/L` figures,
  because those prices cannot be compared at all. Blending them is what once
  ranked an $8,900 bottle among the per-litre prices under `--sort per-unit`.
- **A missing pack size redistributes weight rather than scoring zero.** About
  5% of the catalogue publishes no size, and charging those products for the
  absence buries them for a fact about D1's data rather than about the product.

When the leaf category has nothing in stock the search widens one level at a
time and **says which level answered** — a suggestion from two levels up is a
looser kind of answer, and quietly returning one would hide that.

### Fixed — a price of `0` is "no offer here", not "free"

VTEX reports `Price: 0` for a product it has no offer for in the current region.
`d1 search` had been rendering that as `$ 0` and `$ 0/kg` since 0.1.0, and the
first build of `substitute` went further and *compared* against it, printing
`$ 0/kg → $ 40.435/kg` — a per-kilo rise measured from free. Found by running
the new command against SKU 1687, not by reading the code.

Fixed at the root: `priced()` in `catalog.ts` is the one predicate, no unit
price is derived from a non-price, and both renderers now show `—`. The
"publishes no pack size" note in `search` now counts pack sizes rather than unit
prices, which stopped being the same question.

### Also fixed — what three adversarial reviewers found after all of the above was green

Every item here passed 270 tests, lint and typecheck first. They are listed
because the pattern is the useful part: in each case the code was defensible
and the OUTPUT was not.

- **An approved path is not an approved request.** `fq` is a query language, and
  the allowlist checked pathnames — so `fq=C:/1/` or `_from`/`_to` paging would
  have reached D1 with the session cookie attached from any second call site.
  `assertAllowedQuery` now pins the parameters, and `client.ts` runs the guard
  *after* the query is applied so it sees the URL `fetch` will send.
- **`d1 substitute <garbage> --lat/--lng` called D1 before validating**, so a
  typo's exit code depended on D1 being reachable — the same shape as
  `d1 cart bogus` creating an orderForm before deciding the command was invalid.
- **Exit 1 collided with its own meaning.** "I looked and there is none" now
  exits **3**; `1` stays "D1 refused or was unreachable, a retry may help". An
  agent retrying on 1 would have looped forever on an empty category.
- **`—  -100%`**: `discountPercent` was still reading the very price the column
  beside it had just declined to print. Both fixtures had pinned `listPrice: 0`,
  so the guard was only exercised where it could not fail.
- **A pack price and a `$/L` from two different sellers.** Two predicates
  answered "which offer represents this product" and diverged precisely when
  nothing was in stock — the case `substitute` exists for. One `pickOffer` now.
- **`Nothing in this category is in stock`** was asserted while suppressing that
  3 of 140 products were compared, that the search had already widened, and that
  stock was national. A negative over a partial sweep needs its caveats *more*
  than a positive does.
- **A sizeless source disabled every measure safety at once**, stacking `$/kg`,
  `$/unit` and `$/L` in one column with nothing saying they do not compare.
- Plus: terminal control characters from upstream product names are neutralized;
  the category walk is depth-capped (a 40-segment category issued 41 requests);
  `searchedDepth` reports the depth *searched* rather than the depth asked for;
  `--limit 0` is rejected instead of silently clamped to 1; and a `0 kg` shown
  for a real 400 mg sachet now prints its actual size.

The endpoint tripwire was also strengthened: it counted entries, which meant
widening an existing pattern *in place* was invisible to it. Patterns are now
pinned by source. Known and filed rather than fixed here: BRO-2081, a multipack's
unit price is overstated by the pack count, since D1 publishes PUM per unit.

### Discovered — the SKU lookup traps

`intelligent-search` has no SKU filter and **silently ignores** the one you
pass: `?fq=skuId:262` returns all 1,600 products with HTTP 200, which is
indistinguishable from a successful narrow query. Only
`catalog_system/pub/products/search` genuinely filters.

And SKU ids overlap product ids without being them — SKU `1686` belongs to
product `1687`, so asking for skuId `1687` returns product `1688`, a different
grocery item entirely. The lookup requires an item whose `itemId` matches and
never takes `items[0]`.

## [0.4.0] — 2026-08-03

### Added — unit pricing, the axis "cheapest" actually means

`--sort per-unit` ranks by price per kg / L using the PUM data Colombian law
requires D1 to publish (`Unidad De Medida` + `Valor de Medida`, present on ~95%
of products). Products also expose Colombia's Ley 2120 front-of-pack warnings
in `warnings[]`.

The two rankings genuinely disagree. For rice, the cheapest PACK is
`ARROZ ESTÁNDAR 500 GRS` at $1.550 — which is $3.100/kg. The best value in the
same results is $2.775/kg, in a $5.550 bag that appears nowhere in the
pack-price top five. Ranking by pack price gives a worse answer while looking
correct.

D1's search cannot sort on this — the data lives in product properties, not a
sortable index — so the CLI sorts the fetched page client-side and SAYS SO,
along with how many results publish no size and therefore cannot be compared.
A "cheapest" claim over a partial result set would be false.

A missing or unrecognized size yields `undefined`, never a guess: a fabricated
size produces a confidently wrong price-per-kg, which is worse than admitting
the comparison cannot be made.

### Documented — the checkout gate

SKILL.md now states the discipline rather than leaving it implicit: finish every
basket with `cart checkout` and act on the exit code. It is the only command
that re-checks the whole cart against D1 as it is now, and all three of these
happened to a real basket while the cart still rendered a payable total —
a line sold out overnight (total silently 6.490 light), an address change
stranded every line, and shipping was under-reported 12x.

## [0.3.0] — 2026-08-03

### Added — a guard against writing to someone else's cart

The CLI twice made unrequested writes to a real account, and both times the
operation looked read-shaped to the operator. The clearer one: a verification
run of an unrelated fix executed `cart add 1287 1000 262` against the
customer's LIVE cart, because the config directory already held that cart's id
and pointing at it was convenient. A carton of milk sat in the basket,
deliverable and priced, until the customer asked why it was there.

Nothing distinguished "the cart this CLI created for me" from "a cart id that
happens to be in the config file".

- **Ownership provenance.** A cart the CLI obtains itself is stored with a
  keyed fingerprint. An id whose fingerprint does not verify is EXTERNAL —
  which is exactly what a hand-edited or injected id looks like.
- **`cart add|set|clear|deliver-to` refuse an external cart** unless `--yes`,
  and the refusal names the cart, its line count and its total, so the operator
  sees what they nearly wrote to.
- **`D1_SCRATCH=1`** ignores any stored cart, uses a throwaway, and persists
  nothing. A verification run pointed at a populated config directory then
  *cannot* reach real state rather than merely being unlikely to.
- Reads stay unguarded. Blocking them would train people to reach for `--yes`
  reflexively, defeating the guard on the writes that matter.

This is not a security boundary — anyone reading `ownership.ts` can forge a
fingerprint, which is fine. It exists to stop an accident, not an adversary.
The person it protects against is the author, in a hurry.

## [0.2.1] — 2026-08-03

### Fixed

- **`cart add` minted an address record per item.** The 0.1.2 fix asserts the
  delivery point BEFORE adding (VTEX judges deliverability at add time), but it
  re-posted the address unconditionally — and posting without an `addressId`
  mints. So the fix for one address bug caused another: one junk record per
  `cart add`, thirteen accumulated on a live account.

  `ensureDeliveryPoint` now reads the cart first and writes only when the
  address is absent or somewhere else, reusing the existing `addressId` when it
  re-points. Verified live: three consecutive adds left the address book
  unchanged, while a genuine region change still re-points.

  Two constraints pull against each other here and both have to hold: the
  address must be correct before an add, and re-posting a correct address is
  itself harmful.

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
