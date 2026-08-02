# Changelog

## 0.1.0 — 2026-08-02

Initial release. Reverse-engineered `d1.com.co` and found it runs VTEX IO
(account `d1tiendas`), which turned the task from protocol archaeology into
mapping which of VTEX's public storefront endpoints D1 exposes. All 16 are
verified live; catalogue and cart need no credentials at all.

### Added

- `region` — resolve a delivery point to its fulfilling physical store.
- `search`, `suggest`, `trending`, `categories`, `facets` — catalogue reads.
- `quote` — price a basket without mutating the cart.
- `cart` — `show` / `add` / `set` / `clear` / `deliver-to` / `checkout`.
- `login` (one-time emailed code, or adopt a browser token), `whoami`, `logout`.
- `orders`, `order <id>` — order history.
- `--json` on every command; exit codes `0` ok, `1` failure, `2` usage.

### Gotchas encoded as tests

- `geoCoordinates` is `{lon};{lat}` — **semicolon**, longitude first. A comma
  fails with `CHK0119`, whose message implicates the wrong parameter.
- Search reports prices in whole pesos while checkout reports hundredths — a
  silent 100×. Normalized to hundredths at the boundary.
- `simulation` returns a per-unit `price`; the line total is
  `priceDefinition.total`. Summing `price` under-reports any quantity > 1.
- An unknown SKU returns `items: []` with HTTP 200, so `every(available)` passes
  vacuously. Unanswered SKUs are tracked and reported.
- Search pagination is capped at 50 pages.

### Deliberately absent

No payment surface: no card fields, no `paymentData`, no `gatewayCallback`.
`test/safety.test.ts` fails if any is introduced. Checkout hands a URL to a
human. No VTEX admin key is read; the only stored credential is a storefront
session token in a `0600` file.
