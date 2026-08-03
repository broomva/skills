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

Every endpoint below has been exercised live against `www.d1.com.co`, except
`GET /api/oms/user/orders/{orderId}` — the account used has no order history,
so there was no real order to fetch. Everything marked `none` needs **no
credentials at all**.

The one-time-code endpoints (`accesskey/send` + `accesskey/validate`) were
verified on 2026-08-03, later than the rest: sending a code writes to someone's
inbox, so it was deliberately left untested until there was a reason to send
one. Until then this sentence overclaimed, which is worth recording — a doc that
says "all verified" reads identically whether or not it is true.

That verification covered both polarities, since an auth check that only ever
sees the happy path proves nothing:

| Case | Result |
|---|---|
| correct code | signed in, exit 0, token stored `0600` |
| wrong code | `authStatus: WrongCredentials` → exit 1, **no session written** |
| already-consumed code replayed | rejected, exit 1 |

Note that VTEX signals a bad code with **HTTP 200** and `authStatus` in the
body, so the transport-level status check does not catch it — `session.ts`
inspects the body explicitly.

This table is also the allowlist: `test/safety.test.ts` fails if `src/` reaches
any endpoint not on it.

| Endpoint | Auth | Used for |
|---|---|---|
| `GET /api/io/_v/api/intelligent-search/product_search/{facets}` | none | `search` |
| `GET /api/io/_v/api/intelligent-search/facets/trade-policy/{sc}` | none | `facets` |
| `GET /api/io/_v/api/intelligent-search/autocomplete_suggestions` | none | `suggest` |
| `GET /api/io/_v/api/intelligent-search/top_searches` | none | `trending` |
| `GET /api/catalog_system/pub/category/tree/{depth}` | none | `categories` |
| `GET /api/catalog_system/pub/products/search?fq=skuId:{id}` | none | `substitute` |
| `GET /api/checkout/pub/regions` | none | `region` |
| `POST /api/checkout/pub/orderForm` | none | `cart` |
| `POST /api/checkout/pub/orderForm/{id}/items` | none | `cart add` |
| `POST /api/checkout/pub/orderForm/{id}/items/update` | none | `cart set` |
| `POST /api/checkout/pub/orderForm/{id}/items/removeAll` | none | `cart clear` |
| `POST /api/checkout/pub/orderForm/{id}/attachments/shippingData` | none | `cart deliver-to` |
| `POST /api/checkout/pub/orderForms/simulation` | none | `quote` |
| `GET /api/vtexid/pub/authentication/start` | none | `login` |
| `POST /api/vtexid/pub/authentication/accesskey/send` | none | `login` |
| `POST /api/vtexid/pub/authentication/accesskey/validate` | none | `login` |
| `GET /api/vtexid/pub/authenticated/user` | session | `whoami` |
| `GET /api/oms/user/orders` | session | `orders` |
| `GET /api/oms/user/orders/{orderId}` | session | `order <id>` |

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

### 7. A shipping SLA's `price` is that LINE's share, not the option's cost

`logisticsInfo` repeats once per cart line, and each entry's `slas[].price` is
that line's **share** of the delivery cost. Measured at one point, same day,
same SLA:

| Lines | `slas[].price` | × lines |
|---|---|---|
| 1 | 13,500 | 13,500 |
| 2 | 6,750 | 13,500 |
| 4 | 3,375 | 13,500 |
| 12 | 1,125 | 13,500 |

**Delivery is a flat COP 13,500.** Deduplicating the repeated SLA and showing
the first share — the obvious way to stop one option rendering twelve times —
under-reports shipping by the line count. The CLI sums the shares per option,
which is exact for every basket size measured and agrees with the orderForm's
own `Shipping` totalizer.

This is the same trap as gotcha 4, and worth stating once as a rule: **in a
VTEX payload, a field that reads as a total is often a per-unit or per-line
component.** Both instances are invisible to a one-line fixture, because there
the share *is* the total.

The tell, if it ever recurs: `Items + shipping ≠ Total` on the rendered cart.
An earlier version of this file claimed shipping "varies with basket
composition, and not monotonically" and showed a larger basket getting cheaper
delivery. That was this bug, not a property of D1. Retracted.

### 8. `POST /items` SETS a line's quantity — it does not add to it

`d1 cart add 262 --qty 2` run twice leaves the cart at **2**, not 4. Verified
live. The endpoint reads as "ensure this line is N", which is why `cart add`
verifies the *resulting* quantity rather than a before/after delta — a delta
check reports a false failure on any legitimate repeat.

The check still has to exist: asking only "is this SKU in the cart?" answers
yes whenever the line already existed, so a fully rejected request on an
existing line reported success.

### 9. Pack price and value routinely disagree

D1 publishes Colombia's mandated PUM (*precio por unidad de medida*) as two
product properties — `Unidad De Medida` and `Valor de Medida` — on ~95% of
products. `--sort per-unit` uses them.

It matters more than it sounds. For rice:

| rank by pack price | rank by unit price |
|---|---|
| ESTÁNDAR 500 GRS — $1.550 | ECONÓMICO 2000 GRS — **$2.775/kg** |
| DIANA 500 G — $1.990 | ESTÁNDAR 2500G — $2.996/kg |
| PREMIUM 1000 GRS — $3.990 | ESTÁNDAR 500 GRS — $3.100/kg |

The pack-price winner is $3.100/kg. The actual best value is in a $5.550 bag
that does not appear in that top five at all.

D1's search cannot sort on this — the data lives in product properties, not a
sortable index — so the CLI sorts the fetched page client-side and says so.
A "cheapest" claim over a partial result set would be false.

Products also carry the Ley 2120 front-of-pack warnings (`Exceso en Azúcares`,
`sodio`, `grasas trans`, `grasas saturadas`, `Contiene Edulcorantes`) in
`warnings[]`. Coverage is 70–90% by category, so an empty list means
"not declared", not "safe".

#### 9a. For a multipack, `Valor de Medida` is the pack — with three exceptions

The obvious worry is that `LECHE CHOCOLATE ... 3 UN 600 ML` declaring `600`
means 600 ml *per carton*, making the pack 1.8 L and every multipack's `$/L`
overstated by its pack count. That was reported as a defect and it is wrong.

A census of all 1,600 products settled it. Of the 154 multipacks carrying a PUM
pair, 62 are measured in kg or L — the only ones where this can go wrong — and
of the 46 where D1's description says enough to decide, **44 declare the pack
total**. SKU 897 is one of them: its own description reads
`Peso: 600 mL (200 mL por unidad)`, so 600 is the pack and 200 is the carton.

Parsing `N UN` out of the name and multiplying would therefore have corrupted
44 products to fix 2. **Do not do that.** The count in a name is not evidence
about what the PUM means.

Three products really do declare one item, and D1's own prose is the only thing
that says so:

| SKU | Name | Description says | Was | Is |
|---|---|---|---|---|
| 718 | `REFRESCOS 6 UN ... 200 ML` | `6 unidades de 200 mL cada una` | $27.450/L | **$4.575/L** |
| 510 | `QUESO PERA 3 UND ... 114 GRS` | `114 g por unidad (3 unidades por paquete)` | $42.544/kg | **$14.181/kg** |
| 1008 | `GASEOSA COCA COLA ... 2 UNDX2.5L` | `2 unidades de 2.5L` | 2.5 L | **5 L** |

So `resolvePackSize` trusts the declared value and overrides it only where the
description states **both** a per-item size and a count. A per-item size with no
count is not enough — there is nothing to multiply by, which is precisely why
SKU 897 is left alone. Blast radius across the catalogue: 3 of 1,548 products
carrying a PUM change; 1,545 are untouched.

Note that SKU 1008 is invisible to a name-based search — `2 UNDX2.5L` has no
word boundary after `UND`. Reading the description finds cases that reading the
name cannot.

This fails **open**: if D1 stops publishing the prose, the CLI returns to
trusting the PUM rather than inventing a pack count.

### 10. `intelligent-search` has no SKU filter, and ignores the one you pass

There is no way to ask intelligent-search about a specific SKU. What makes this
a gotcha rather than a limitation is *how* it declines:

| Request | Result |
|---|---|
| `product_search?fq=skuId:262` | **HTTP 200, all 1,600 products** — `fq` silently ignored |
| `product_search/skuId/262` (facet path) | HTTP 200, 0 products |
| `catalog_system/pub/products/search?fq=skuId:262` | HTTP 200, the one product |

The first row is the dangerous one. A filter that is dropped rather than
rejected returns a large, entirely plausible result set, and a caller that
believed the filter applied would treat the whole catalogue as "products
matching this SKU". Only `catalog_system` genuinely filters.

**And SKU ids are not product ids, though they overlap.** SKU `1686` belongs to
product `1687`:

```
fq=skuId:1686  →  product 1687   PAPAS EN CASCO TOASTATAS 500 G
fq=skuId:1687  →  product 1688   SALCHICHA PARRILLA MINI VIANDE 200 G
```

Passing a product id where a SKU is expected therefore returns **a different
grocery item**, with one result and HTTP 200. `productBySku` never takes
`items[0]`; it requires an item whose `itemId` equals the SKU asked for, and
returns undefined otherwise.

`catalog_system` also disagrees with search about *shape*: it carries
`Unidad De Medida` and the `Exceso en …` warnings as top-level keys, where
search nests them under `properties[]`. Both go through one normalizer, because
two would drift and the drift reads as "D1 publishes no pack size for this one".

Finally, `catalog_system` takes **no region**, so its prices are national. That
is why `d1 substitute` re-reads the source through the regional search before
computing any delta — comparing regional candidates against a national baseline
reports a saving that is partly just the two catalogues disagreeing.

### 11. An approved path is not an approved request

Every allowlist entry before `catalog_system/pub/products/search` carried its
risk in the **path** — that is what the `..`-to-order-settlement incident was
about, and why checking the resolved pathname was enough. This one is
different: `fq` is a query language. `fq=C:/1/`, `fq=alternateIds_RefId:x`,
`fq=P:[0 TO 9999]` and `_from`/`_to` paging all reach the same approved path.

So the constraint had to move to where the risk is. `assertAllowedQuery` in
`endpoints.ts` pins `fq` to `^skuId:\d+$` and refuses **unknown parameters
outright** — `_from`/`_to` are the whole-catalogue enumeration lever and would
not have tripped a check that only validated `fq`. And `client.ts` now runs the
guard *after* the query is applied, so it inspects the URL `fetch` will actually
send rather than the one the caller wrote.

The reason this is a guard and not a convention: `assertSkuId` protects the one
function that builds the call today, but a second call site would inherit the
approved path and none of the constraint. That was demonstrated, not assumed —
a plausible future caller passing an arbitrary `fq` sailed straight through the
static source scan.

### 12. A price of `0` means "no offer here", not "free"

VTEX reports `Price: 0` for a product it has no offer for in the current region
or channel. Taken at face value it renders as a real number:

```
1687   SALCHICHA PARRILLA MINI VIANDE 200 G     $ 0     $ 0/kg    out of stock
```

and, worse, it *compares*: an early build of `d1 substitute` printed
`$ 0/kg → $ 40.435/kg` — a per-kilo rise measured from free. `priced()` in
`catalog.ts` is the single predicate for this, no unit price is derived from a
non-price, and both renderers show `—` instead.

## What the public API will not give you

- **Saved addresses and profile records.** `dataentities/AD` and `dataentities/CL`
  answer `403 Cannot filter by private fields` for a storefront token. Addresses
  are reachable only through the live cart or an existing order.
- **Payment.** Deliberately out of scope — see below.

## Safety boundary

`d1` assembles and prices baskets. It does not pay. `d1 cart checkout` prints the
URL where a human reviews the total and pays.

It is enforced in **two places, from one list** (`src/endpoints.ts`):

- **At runtime**, `D1Client.request` checks the RESOLVED URL against
  the approved patterns and refuses anything else *before the request leaves the
  process*. This is the load-bearing check.
- **Statically**, `test/safety.test.ts` extracts every `/api/` literal from the
  whole `src/` tree, at any depth, and fails unless each is approved.

The runtime check exists because a static scan of source literals is not
sufficient, and the way that was discovered is worth recording: every literal in
the source was approved, and

```
d1 search --facets '../../../../../../api/checkout/pub/orderForm/OF1/transaction'
```

still resolved to `/api/checkout/pub/orderForm/OF1/transaction` — the endpoint
VTEX uses to **settle an order**. `encodeURIComponent` does not escape `.`, so
`..` survived into the path and `new URL()` normalized it. Checking the resolved
pathname closes that class, along with the fragment-assembly limit a static scan
can never cover, because it inspects what will actually be sent rather than what
was written.

### How this got here, because the history is the argument

The first version was a **blocklist** — five banned strings, greped over a
non-recursive `readdirSync`. Cross-model review defeated it three ways, each
proven by executing the mutation while all 89 tests stayed green: a payment
module in `src/pay/` was never read at all; the banned list omitted
`orderForm/{id}/transaction`; and `["card" + "Number"]` slips past a substring
match. A blocklist encodes only the attacks its author imagined and fails
silently.

Inverting to an allowlist fixed the enumeration problem but not the coverage
problem, and the next two rounds found four more holes — a walk filtering
`.ts` and missing `.mts`; a comment stripper a `"/*"` string could blind; a
whole-line rule that deleted `/**/ const PAY = "..."` along with its live code;
and the runtime traversal above. Each is now a mutation/control pair in the
suite, and the two stripper vectors are asserted **together**, because fixing
either one alone reopened the other.

What this proves: no unapproved endpoint is reached at runtime, and no literal
unapproved endpoint sits in the source. What it still cannot do: stop a
determined committer with write access from rewriting the allowlist itself. No
in-repo test can.

The only stored credential is a storefront session token (what a signed-in
browser holds, scoped to its owner's own data), written to
`~/.config/d1-cli/session.json` with mode `0600` and never printed. The test for
this calls `saveSession` twice and `statSync`s the result, because
`writeFileSync` **ignores its mode argument when the file already exists** — an
earlier version greped the source for the literal `0o600` and passed while real
saves produced mode `666`.

No VTEX admin `appKey`/`appToken` is read anywhere. Sign-in uses a one-time
emailed code; password authentication is intentionally not implemented.

`d1 order <id>` **redacts by default**. VTEX's order-detail payload carries the
customer's national ID, phone, full delivery address and the card's first/last
digits — none of it needed to answer "where is my order?", all of it otherwise
landing in a terminal, a shell history, or an agent's context. `--raw` opts in.

Override the config location with `D1_CONFIG_DIR`.

## Tests

```bash
bun test
bun run lint
bun run typecheck
```

The suite is network-free. Most tests drive an injected `fetch` stub; the
subprocess exit-code tests reach only paths that fail before any request, and
one of them *measures* that rather than asserting it — an earlier version
claimed network-freedom while `d1 cart bogus` was creating real orderForms on
D1's production storefront.

No exact test count appears in this file on purpose: it drifted four times in
one arc, which is the "canonical string copied into N docs" failure. Run
`bun test` for the number.

Notable cases pin the gotchas above: the semicolon separator, the cross-API price-unit
agreement, quantity surviving a quote, the vacuous unknown-SKU pass, and the
absence of a payment surface.

## Roadmap

- Budget baskets (`d1 basket --budget`), now that unit pricing and substitution
  both exist — a builder strands on the first out-of-stock line without the latter.
- Cross-basket comparison ("what would this cost in store brands"), which is
  substitution with a brand constraint rather than a stock one.
- Pickup points (`public.favoritePickup` appears in D1's session whitelist).
- Coupon application (`orderForm/{id}/coupons` is present but unexercised).
- Address-string → coordinate resolution, so `--lat/--lng` becomes optional.
