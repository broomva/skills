# Changelog

All notable changes to the **d1-cli** skill are documented here.
Format: [Keep a Changelog](https://keepachangelog.com/); versioning: [SemVer](https://semver.org).

## [0.8.0] — 2026-08-04

### Changed — `d1 order` redacts by ALLOWLIST, and the customer's name no longer prints

`redactOrder` named the sensitive keys and printed everything else. That is an
allowlist by omission: any PII key the author did not anticipate printed in
full, and nobody has ever seen a real D1 order, so the list was a guess about
the contents of an unopened envelope. `test/safety.test.ts` was rewritten to
remove exactly this shape for endpoints; it survived here.

Inverted. Each printable field is now named by its full dotted path — so
`items[].name` prints and `clientProfileData.name` would not — and anything
unrecognised is redacted. A container with no printable descendant is withheld
whole rather than walked, so neither its keys nor its length is published:
redacting `geoCoordinates` element-by-element still announced there were
exactly two of them, and the length of a value is part of the value.

**This is a behaviour change.** `clientProfileData` is now withheld entirely,
including `firstName`, which used to print. A test asserted that it did — the
blocklist's failure mode written down as a promise. Nothing in that object is
needed to answer "where is my order?". `--raw` still prints the full payload.

The path list is derived from VTEX's documented OMS order schema, not from an
observed D1 order, so it is expected to be incomplete. Being wrong now means
over-redacting, which is the recoverable direction; a blocklist's wrong guess
costs the customer their national ID. BRO-2077 stays open for the one real
payload that would confirm the useful fields are reachable, and for the
`totalValue` unit claim it was always paired with.

### Added — an over-budget basket line says what else would have fitted

When a line does not fit, the basket now reports how many of the runners-up it
actually weighed WOULD have fitted, and names the command that shows them:

```text
leche — would cost $ 3.090, which does not fit in what is left. 3 cheaper
matches for this term would fit — run `d1 search "leche" --sort per-unit` to
choose one
```

It reports and stops. Re-picking the cheapest that fits is the tempting fix and
the wrong one: the line's product is the best VALUE of its set or the CLOSEST
match from a category, and a cheaper one is neither. Swapping it in silently is
the auto-substitution BRO-2076 exists to forbid — "the tostada the CLI ranks
first for `PAN ARTESANAL INTEGRAL` is not bread". Option 1 of the three shapes
BRO-2086 set out; a mutation that implements option 2 as the default now fails
five tests.

Anything that fits is necessarily cheaper than what was refused —
`spent + price > budget >= spent + alt` gives `alt < price` — so "cheaper" is
arithmetic rather than an assumption. On a replacement line the sentence sits
inside the sweep's own `only N of M in that category were searched` caveat and
says "of those searched", so it never claims more than the look behind it.

### Fixed — what the cross-model review round 1 found (6/10, below the gate)

Three of these are defects in *this release's own additions*, found after CI was
green and 420 tests passed.

- **The basket contradicted itself in one screen.** `affordableAlternatives` was
  counted inside the fill loop, against the money left at the moment a line was
  refused — but lines *after* it keep spending. A basket could print
  `$ 1.000 left` and, one line below, "1 cheaper match would fit" about a
  $ 3.000 product. Settled after the loop against the final `remaining`. The
  arithmetic that makes "cheaper" true survives and tightens, because
  `remaining <= budget - spent_at_refusal < price`.
- **The allowlist failed OPEN on a forged path.** Paths were built by string
  concatenation, so a key's own characters were indistinguishable from a nesting
  boundary: a payload with a root key literally named `shippingData.address.city`
  matched and printed. Matching is now segment-by-segment through a tree, so one
  key is one segment and nothing can be forged by naming. This was the single
  direction the change exists to close.
- **A printed command could become two commands.** `alternativesNote` was the
  first place in `present.ts` to interpolate data into something a reader — or an
  agent, since every command has a `--json` twin — may run, and `sanitize` only
  strips control characters. A term containing `"` closed the string. Terms are
  single-quoted with POSIX escaping; a `skuId`, which arrives from VTEX rather
  than the shopper, must match `/^\d+$/` or the command clause is dropped. The
  repo already owned this lesson: `assertSkuId` exists because "a value slot that
  is really a grammar does not narrow the question, it rewrites it".
- A container arriving where a scalar was documented is now withheld whole
  (every leaf path was also registered as its own ancestor, so such a value was
  walked and published its keys and length).
- A `__proto__` key is redacted in place rather than silently vanishing.
- The suggested search carries `--available`, so it shows the same population
  the count was drawn from.
- A `nothing-in-stock` downgrade drops `alternatives`.
- **Two vacuous tests**, both written this release. The order fixture had
  single-element arrays, so "`items[].name` matches at any index" was asserted
  nowhere and a mutation collapsing only index 0 stayed green. And an
  `alternatives` assertion of `toEqual([])` was satisfied by the feature being
  deleted entirely.

### Measured — `Envío D1 Express` is not reachable through the storefront API

BRO-2080 asked for measurement before design. Seven delivery points across five
cities, each resolving to a different D1 store-seller, **no simulation returned
more than one** shipping SLA, and every SLA returned was the scheduled one
(`Entrega Programada`, or `Envio Programado` in Barranquilla). Six of the seven
returned exactly one; Bogotá centro returned none, a seller with no delivery
coverage rather than a second option hiding. Never express, at any coordinate,
on any sales channel — so this is not a coverage gap at one address.

The mechanism is named in D1's own storefront config:
`"activeForDeliveryMethods": {"express": true, "programado": true}`, attached to
homepage *blocks* — banners, shelves, and a `ChangeShippingOption` control that
is `{"desktop": false, "app": true, "mobile": true}`. So `express` is a
client-side rendering mode selected in the app, gating which blocks appear, and
the fulfilment behind it is not served by the VTEX storefront checkout this CLI
speaks to. No storefront API path mentions coverage, shipping or delivery.

Recorded rather than designed against. See gotcha 13.

### Verified — the inconsistent-PUM population is still exactly one product

A fresh census of all 1,599 products (32 requests) re-ran the BRO-2081
measurement. Among unit-measured multipacks, 91 of 92 declare a `Valor de
Medida` matching their pack count; the one exception is still SKU 778
(`PAÑO REUTILIZABLE 30X30 RENDY 25 UND`, `Valor=1` against 25 units), and it
still publishes no description, so there is still no evidence to act on. Among
weight/volume multipacks the split is 37 pack-total to 1 per-item, which is the
same direction that refuted BRO-2081's premise. BRO-2082 stays open as a
watch item, not a defect.

## [0.7.0] — 2026-08-03

### Added — `d1 basket --budget`, which fits a shopping list to what you can spend

Takes a list of TERMS rather than SKUs, resolves each to the best value at the
resolved store, and fills to the target. It waited on substitution for a
structural reason: a basket builder strands on the first out-of-stock line, and
substitution is the thing that un-strands it.

The ticket left two questions open. Both are settled, and both are stated in the
output rather than left for the reader to infer:

- **The budget is a hard ceiling.** A best-effort fit that overshoots is the
  more useful answer about half the time, and which half you are in is not
  knowable from here. Overspending a grocery budget unasked is the worse of the
  two failures. A reader who assumed best-effort would otherwise read a short
  basket as "that is all D1 sells", so the ceiling is named on every basket.
- **What it could not fit is part of the answer.** Every unfilled term carries
  its reason — over budget, nothing in stock, or no match at all. A total that
  quietly omits three of eight lines describes a shop that would not happen.

Lines are chosen by unit price within ONE measure. A `$/unit` bottle must not
beat a `$/L` oil however small its number, and a product with no published size
is used only when nothing in the set publishes one — a comparable answer beats
an incomparable cheaper one.

Each line names both how many products it chose between and how many D1 matched.
`best of 20 compared, of 143 D1 matched` cannot be misread as a survey of the
shelf, which is the omission that let an empty substitute result assert
"nothing in this category is in stock" while concealing it had seen 3 of 140.

A term whose matches are all out of stock falls through to `findSubstitutes`,
and the replacement is NAMED rather than swapped in silently — the CLI proposes
and the person decides, here as everywhere.

Exit `3` when nothing fit, matching `substitute`: the command succeeded at
looking, and a budget that buys none of the list never becomes affordable on a
retry. A partially filled basket is exit `0`. Exit `1` is reserved for the case
where a lookup never answered at all — an empty result and an unasked question
are different answers, and only one of them is worth retrying.

Policy lives in exported pure functions rather than the command body, because
nothing network-free can drive that path — the same reason `substituteOptions`
exists.

### Fixed before release — what a cross-model review gate found after all of that was green

The above passed 363 tests, lint, typecheck, a live dogfood and thirteen
mutation proofs. An adversarial reviewer then scored it **3/10 and failed it**.
The pattern is the useful part, and it is the same one 0.5.0 recorded: the code
was defensible and the OUTPUT was not.

- **A `$/unit` product could beat a `$/L` one after all.** Measures were never
  *blended* — but when two were equally common the winner fell through to Map
  INSERTION order, which is the order `search` returned, which is computed over
  out-of-stock products too. Three sold-out bottles listed first could make
  `unit` dominant for a contest that was really one bottle against one oil, and
  put an empty bottle in the basket as the best value for "aceite". The same set
  in the other array order gave the other answer. Ties now break by an explicit
  measure precedence, with `$/unit` last.
- **A failed replacement lookup was reported as "nothing is in stock".** A bare
  `catch` turned a transport failure into a positive claim about a shelf,
  asserted from zero successful requests, and exited `3` — documented as never
  worth retrying. `substitute.ts` had already reasoned this exact case out for
  its own sweep. There is now a `replacement-unknown` line that says *unknown,
  not empty*.
- **`compared` counted the page, not the choice.** A page of 20 where 18 were
  out of stock reported "best of 20 compared" over a real choice set of 2 — the
  "3 of 140" overstatement this module was written to kill, one module later.
- **A substitute line added a SKU count to a product count** from a different
  population, and when the sum exceeded `matched` the "of N D1 matched" clause
  silently vanished — precisely when the search had drifted furthest from what
  the shopper typed.
- **The pack-price fallback was never disclosed.** `chooseBest` said "saying so
  is the caller's job — see `renderBasket`", and `renderBasket` did not say it,
  while the footer still called the line "best value". A comment asserting a
  disclosure that does not exist.
- **A NaN price defeated the hard ceiling**, because `sum()` coerces NaN to 0
  while `spent` becomes NaN and every later comparison is false. `remaining`
  went negative on the one invariant the function exists to hold.
- **`spent` and `total` disagreed about what "filled" means**, so a priced line
  of any other status consumed budget it was never billed for.
- **A numeric `--budget` bypassed the grammar** the docstring claims to enforce:
  `50.5` returned half a peso while `"50,5"` was refused by name, and `0.004`
  returned a budget of zero from a positive input.
- **`d1 basket` was missing from `--help` entirely**, and the in-binary
  exit-code table still said `3` belonged to `substitute` alone — while SKILL.md
  asserts of its own copy that it "is the only copy of it".

Two more test fixtures could not fail and were rewritten: the fill-order test
priced both lines identically, so a value-sorted fill was indistinguishable from
an in-order one; and the exact-fit boundary — the single boundary this feature
is about — had no fixture at all, so `>` to `>=` shipped green.

An earlier draft of this entry claimed "twelve mutations were run; all twelve
were caught". The boundary mutation above is the counterexample. Retracted.

### And what a SECOND pass found after the fixes for all of that were green

Scored 4/10, and named the reason: **nothing in the suite called `buildBasket`.**
Every fix above that lived in it was revertible with 375 tests passing — eleven
mutations proved it, each killing zero tests. Fixing code without a test that
enters it is not fixing it.

- **A basket where every lookup failed still exited `3`.** Only the prose had
  been fixed; `basketExit` took a COUNT, and a count cannot tell "found nothing"
  from "never got an answer". It takes the lines now and returns `1`.
- **An unbuyable candidate was offered as a replacement, then reported as no
  replacement.** `rankSubstitutes` filters on availability only, and VTEX
  reports `Price: 0` alongside a positive `AvailableQuantity` — so a priceless
  candidate ranked, was downgraded, and rendered "its category had no
  replacement" while the line still carried the product it had just found.
- **`compared` on a substitute line reported the whole swept pool** (40) rather
  than the rankable set (1), and the `nothing-in-stock` path wrote a sweep count
  without the flag that says so, letting `compared` exceed `matched`.
- **`byPackPrice` was never set on a substitute line**, so the undisclosed
  pack-price fallback survived on exactly the path where a substitute is ranked
  by name similarity rather than by value.
- Budgets past `MAX_SAFE_INTEGER / 100` silently became a different number; the
  exit-code call re-spelled the `FILLED` set as a literal; and "Nothing fits
  this budget" was asserted even when nothing had been checked.

**390 tests, thirteen of which drive `buildBasket` against a stubbed D1** — the
substitute path among them, which no test had ever entered.

### And a THIRD pass, because two of the round-2 fixes did not do anything

Scored 5/10. Rounds went 3 → 4 → 5, and the recurring shape is the one this
project already names: fixing in one place opens a hole beside it.

- **The "skip an unbuyable replacement" fix was inert.** `findSubstitutes`
  slices to `limit` *before* returning, and the caller asked for `limit: 1` —
  so skipping the unpriced top candidate skipped the only candidate there was,
  and a buyable runner-up was still reported as an empty category. The list is
  requested unbounded now.
- **The substitute source was the cheapest-per-unit product, not the best
  match.** The page was re-sorted by unit price before `products[0]` was taken
  as the source, so a shopper whose rice was sold out got replacements swept
  from the category of whatever was cheapest per kilo — the line read "replaces
  SAL REFINADA" for a term that was never about salt. The sort is gone;
  `chooseBest` finds its own minimum and never needed it.
- **`byPackPrice` on a substitute line misnamed the mechanism.** Substitutes are
  ranked by name similarity and price *proximity*, never by pack price, and the
  note's "D1 publishes no size for any of these" quantified over a set from a
  predicate that read one product. Removed; the footer now states all three
  mechanisms separately instead of one sentence that was false for two of them.
- **"Nothing fits this budget" was fixed for one case of four.** It is an
  affordability claim, so it is now made only when a line was actually rejected
  on price.
- Two more claims in this file were false and are corrected above: "all eleven
  previously-surviving mutations now die" (two did not), and "twelve tests drive
  `buildBasket`" (eleven did). A fourth vacuous test — an out-of-stock term
  "falls through to a substitute" whose only assertion was a tautology over its
  own fixture — was replaced with one that asserts the REQUEST was made.

### A FOURTH pass — no blockers left, three claims the output still could not support

Scored 6/10. The arc across four rounds was 3 → 4 → 5 → 6, and every round found
that a previous round's fix was incomplete, inert, or unpinned.

- **A substitute line counted candidates it had rejected as unbuyable.**
  `rankedCount` counts everything past the availability filter, but the price
  filter added in round 3 rejects more — so a line read "best of 4 in its
  category" for the only buyable one of four. That is this module's own stated
  invariant ("after dropping the unavailable, the unpriced") broken on the one
  path that did not enforce it.
- **"Nothing fits this budget" outranked an unanswered lookup.** A basket with
  one dear line and one unreachable one blamed the budget while the same run
  exited `1` — "D1 could not be reached, a retry may help". One invocation, two
  outputs, disagreeing about why the basket was empty.
- **The footer's pack-price clause had zero coverage in either polarity.** It
  could be deleted, inverted, or replaced with nonsense on a green suite — while
  a code comment justified dropping a different disclosure on the grounds that
  "the footer covers the rest".

Also: the summary billed `plan.total` while the body rendered only lines with a
product; the `nothing-in-stock` reason claimed "its category had no replacement"
for lines that never reached a category lookup; and an all-replacement basket
called the exception a rule.

**402 tests.** The fifth inert test was replaced: its distinguishing assertion
was unreachable, because the string it checked for is only ever produced for
filled lines and the fixture's line was not one.

### A FIFTH pass — and round 4's own fix had deleted the disclosure it protected

Scored 6/10 again, with no blockers. The one MAJOR was a regression introduced
by round 4: making `compared` count BUYABLE candidates is right on the found
path and wrong on the empty one, where that number is zero **by construction**.
Every empty sweep therefore reported "(0 compared)" — indistinguishable across
an empty category, 140 sold-out SKUs, and four in-stock products carrying no
regional offer — and self-refuting besides, since it drew a conclusion from a
look it described as zero wide. Round 4 had also replaced the only end-to-end
test of that path with a hand-built fixture, so it went unpinned in the same
commit that introduced it.

The empty-basket headline is **composed** now rather than prioritised: picking
one sentence made it false for whichever lines the losing condition described.

Two comments stopped overclaiming. `MEASURE_RANK`'s tie-break is *intent*, not
today's operative rule — `"kg" < "L" < "unit"` alphabetically as well, so
deleting the table changes no current outcome; it earns its place against a
fourth measure, and now says so instead of calling itself "the whole point".

### A SIXTH pass — the basket was making category-wide claims from one page

All four round-5 fixes verified. One MAJOR left, and it cited this project's own
standard against it. `d1 substitute` prints *"that category holds 140 products —
only 3 were compared"* on both its empty and non-empty paths, and SKILL.md sets
the rule for exactly that sentence: a negative over a partial sweep needs the
caveat **more** than a positive does. A basket line made the same categorical
claims — "nothing in its category is either", "best of 2 in its category" — and
dropped the denominator, because the sweep's `poolProducts`/`poolTotal` were
discarded before the line was built. The sweep reads ONE page capped at 50 of a
category that may hold hundreds, so those were universals over a sample.

Both sentences now carry *"only N of M in that category were searched"* when the
look was partial, and say nothing when it was complete.

**404 tests.**

### A SEVENTH pass — the one path where a substitution was applied and not shown

When a term is out of stock its line is resolved to a category replacement. If
that replacement then exceeds what is left, the line is downgraded to
`over-budget`, and it printed only *"huevos — would cost $ 24.900, which does not
fit in what is left"* — a price belonging to a product the entire render never
mentions. The shopper reads a larger tray's price as the price of the eggs they
typed. `replaces` is documented "Named, never applied silently"; the filled row
honoured that and this row did not. It now names the replacement and carries the
same sweep disclosure as everywhere else.

Reachable with nothing exotic: a tight budget — the feature's premise — plus an
out-of-stock term, its other premise.

**406 tests. The gate passed on the eighth pass at 8/10**, with no blockers and
no majors.

### What eight rounds of review actually cost, and bought

The score went **3 → 4 → 5 → 6 → 6 → 6 → 6 → 8**. Two things are worth recording
because neither is visible from the final diff:

**The recurring finding was almost never the same defect twice.** It was that the
*previous round's fix* was inert, unpinned, or had quietly deleted something. The
skip-an-unbuyable-replacement fix never ran, because the caller asked for one
candidate and then skipped it. The count-only-buyable fix was right on one path
and made the other a structural zero. Round 4 removed the end-to-end test of the
path it was changing, in the same commit.

**Six tests that could not fail were found across the eight rounds** — including
three the earlier rounds had *written as fixes*. A green suite said nothing about
them; only mutation did. The lesson this project already had — that a test's
absence hides a defect rather than merely risking one — extends: a test's
*presence* hides one too, when nothing has ever made it fail.

## [0.6.0] — 2026-08-03

### Fixed — a multipack's unit price, measured before it was encoded

It was reported that D1 declares the mandated PUM per unit, so a 3-pack reads
at 3x its real rate, and that the fix was to parse `N UN` out of the product
name and multiply by it.

A census of all 1,600 products says the opposite. Among the multipacks findable
by name, 154 carry a PUM pair, 62 are measured in kg or L — the only ones where
this can go wrong — and of the 46 where D1's description says enough to decide,
**44 declare the pack total**. The proposed fix would have corrupted those 44 in
order to correct 2. The product the report was filed on, SKU 897, states
`Peso: 600 mL (200 mL por unidad)` in its own description: the declared 600 is
already the pack.

So the declared value stays trusted, and `resolvePackSize` overrides it only
where the description states **both** a per-item size and a count:

| SKU | Description says | Was | Is |
|---|---|---|---|
| 718 | `6 unidades de 200 mL cada una` | $ 27.450/L | **$ 4.575/L** |
| 510 | `114 g por unidad (3 unidades por paquete)` | $ 42.544/kg | **$ 14.181/kg** |
| 1008 | `2 unidades de 2.5L` | 2.5 L | **5 L** |

The shipped rule reads descriptions, not names, so it runs over a wider
population than that census: of **1,548** products carrying a PUM, 1,187 are
measured in kg or L, and 10 of those state both a per-item size and a count.
Three are corrected; the other seven are confirmed as already stating the pack.
The remaining 1,177 say nothing decisive and are left exactly as declared.

That is why the census reports 2 exceptions while three SKUs are corrected —
they are different populations. SKU 1008 is the difference: `2 UNDX2.5L` has no
word boundary after `UND`, so no name-based rule could have found it.

A per-item size with no count is deliberately not enough. There is nothing to
multiply by, and taking the count from the name instead is the heuristic this
whole change exists to refuse. Fails **open**: if D1 stops publishing the
prose, the CLI returns to trusting the PUM.

`description` is forwarded through `asSearchShape` by hand, because that
function collects only `string[]` properties. Without it a SKU would be
corrected through `d1 search` and left wrong through `d1 substitute`.

### Fixed — two defects that only mutation testing found

Both were invisible to a green suite of 329 tests.

`unidades?` matches "unidade" and "unidades" but **not the singular "unidad"**.
So the assertion that a stated count of 1 is rejected passed because the
pattern missed, never because the guard fired — flipping `count > 1` to
`count > 0` did not move it.

The "already the pack total" early return could not change an outcome. For a
real multipack `count` is at least 2, so the pack total is at least twice the
per-item size and both cannot be within 3% of the same declared value. Removing
it broke no test because it never decided one; it is gone, and the reasoning
stays where the branch was.

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

### And what a round-2 verify found after *those* were green

Fixing in one place opened holes next to it. That is the shape this codebase
keeps hitting, so it is recorded rather than quietly patched:

- **The control-character fix missed one render path** — the closing
  `d1 cart add <sku>` line interpolated the SKU id raw. It is the worst line to
  leave open, because an `ESC[2J` there lands LAST and clears the screen after
  everything prints, erasing the very sentence that says nothing was bought.
  The test could not see it: its payload was in the name, never the id.
- **The partial-sweep fix reversed its own error.** Comparing SKU counts to
  product counts had *suppressed* the warning; comparing them the other way
  *fabricated* it, so a complete sweep of one product carrying three SKUs
  announced "only 1 of 3 compared". `search` now counts products on both
  branches.
- **The new query guard made a usage error retryable.** `--sc abc` reached
  `assertAllowedQuery` and came back as "This is a bug in d1-cli" with exit 1 —
  the caller's typo, reported as an upstream failure worth retrying. `--sc` is
  validated up front now, and appears in `--help` for the first time.
- `guard.params[key]` resolved `constructor`/`toString` up the prototype chain
  to truthy functions, so `?constructor=x` raised an uncaught `TypeError`
  instead of a `D1Error`. Fail-closed either way, wrong error class.
- The no-region caveat printed twice in two near-identical sentences, and
  `formatSize` rendered a sub-microgram size as `1e-7 kg`.

The sizeless-source ranking branch also had no coverage at all — three
independent mutations left it green, including one that let kg, L and unit
interleave under a single per-unit column.

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
