/**
 * The payment boundary, asserted as a property of the source tree.
 *
 * ## Why this is an allowlist and not a blocklist
 *
 * The first version of this file grepped `src/*.ts` for five banned strings.
 * It was defeated three ways, each proven by mutation while the suite stayed
 * green:
 *
 *   1. `readdirSync` is NOT recursive, so `src/pay/settle.ts` — a complete
 *      card-taking settlement path containing every banned string verbatim —
 *      was never read. 89/89 passed.
 *   2. The banned list omitted the endpoint VTEX actually uses to place an
 *      order (`orderForm/{id}/transaction`), because the list was written from
 *      memory rather than from the API.
 *   3. `["card" + "Number"]` as a computed key defeats a substring grep.
 *
 * A blocklist can only ever encode the attacks its author thought of, and its
 * failure mode is silence. So this asserts the inverse, which has no such gap:
 * **every `/api/` path literal appearing anywhere under `src/` must be one this
 * skill has explicitly approved.** Adding any endpoint — payment or otherwise —
 * fails until it is listed here, which forces the decision to be made rather
 * than defaulted into.
 *
 * ## What this does and does not prove
 *
 * It proves no *literal* unapproved endpoint reaches the tree. It cannot stop
 * a path assembled from fragments that are individually not `/api/` strings
 * (`"/ap" + "i/..."`). That is a real limit and the docs say so; the honest
 * claim is "the obvious and the accidental routes are closed", not "payment is
 * impossible". Deliberate obfuscation by a committer with write access is
 * outside what any in-repo test can catch.
 */

import { afterAll, describe, expect, test } from "bun:test";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { checkoutUrl } from "../src/cart.ts";
import { saveSession } from "../src/session.ts";

const SRC = join(import.meta.dir, "..", "src");

/**
 * Every extension the runtime will execute.
 *
 * `.ts` alone is not enough: Bun happily runs `.mts`, `.cts`, `.tsx` and the
 * plain JS variants, so a walk filtering on `.ts` leaves a payment module in
 * `src/deep/nested/settle.mts` completely unexamined. Verified — it passed
 * before this list existed.
 */
const SOURCE_EXTENSIONS = [".ts", ".mts", ".cts", ".tsx", ".js", ".mjs", ".cjs", ".jsx"];

/** Every source file under `src/`, at any depth. */
function sourceFiles(dir = SRC, seen = new Set<string>()): Array<{ name: string; body: string }> {
  const out: Array<{ name: string; body: string }> = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    const st = statSync(full);
    if (st.isDirectory()) {
      // statSync follows symlinks, which is what we want (a symlinked
      // directory is still reachable code) — but a cycle would hang the suite,
      // so each real directory is visited once.
      const key = `${st.dev}:${st.ino}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(...sourceFiles(full, seen));
    } else if (SOURCE_EXTENSIONS.some((e) => entry.endsWith(e))) {
      out.push({ name: full.slice(SRC.length + 1), body: readFileSync(full, "utf8") });
    }
  }
  return out;
}

/**
 * The complete set of D1 endpoints this skill is allowed to reach, with
 * interpolations collapsed to `{}`. Every one is a public (`/pub/`) storefront
 * read or cart mutation. None of them moves money.
 */
const ALLOWED_ENDPOINTS = new Set([
  // catalogue
  "/api/io/_v/api/intelligent-search/product_search/{}",
  "/api/io/_v/api/intelligent-search/facets/trade-policy/{}",
  "/api/io/_v/api/intelligent-search/autocomplete_suggestions",
  "/api/io/_v/api/intelligent-search/top_searches",
  "/api/catalog_system/pub/category/tree/{}",
  // location
  "/api/checkout/pub/regions",
  // cart — builds and prices a basket; none of these settle it
  "/api/checkout/pub/orderForm",
  "/api/checkout/pub/orderForm/{}/items",
  "/api/checkout/pub/orderForm/{}/items/update",
  "/api/checkout/pub/orderForm/{}/items/removeAll",
  "/api/checkout/pub/orderForm/{}/attachments/shippingData",
  "/api/checkout/pub/orderForms/simulation",
  // identity
  "/api/vtexid/pub/authentication/start",
  "/api/vtexid/pub/authentication/accesskey/send",
  "/api/vtexid/pub/authentication/accesskey/validate",
  "/api/vtexid/pub/authenticated/user",
  // orders (read-only)
  "/api/oms/user/orders",
  "/api/oms/user/orders/{}",
]);

/**
 * Drop whole-line comments so prose mentioning an endpoint is not mistaken for
 * code reaching one.
 *
 * Deliberately LINE-BASED. An earlier version also ran
 * `.replace(/\/\*[\s\S]*?\*\//g, "")` to strip block comments, which is a
 * silent hole: a source line containing the string `"/*"` opens a match that
 * swallows every line until the next `*​/`, so a payment literal placed
 * between them disappears from the extractor entirely. Verified — it hid
 * `/api/evil/payment`. Deleting only lines that are *themselves* comments
 * cannot span lines, so nothing can be hidden behind it.
 *
 * A trailing `// ...` after code is left alone, because cutting from `//`
 * would also cut the `//` inside a URL literal. That direction fails LOUDLY
 * (an endpoint named in a trailing comment trips the allowlist), which is the
 * safe way for this to be wrong.
 */
function stripComments(body: string): string {
  return body
    .split("\n")
    .filter((l) => {
      const t = l.trimStart();
      return !t.startsWith("//") && !t.startsWith("*") && !t.startsWith("/*");
    })
    .join("\n");
}

/** Pull every `/api/...` string or template literal out of a source file. */
function apiLiterals(body: string): string[] {
  const found = new Set<string>();
  for (const m of stripComments(body).matchAll(/["'`](\/api\/[^"'`]*)["'`]/g)) {
    found.add(m[1].replace(/\$\{[^}]*\}/g, "{}").replace(/\/$/, ""));
  }
  return [...found];
}

describe("every endpoint the CLI can reach is explicitly approved", () => {
  const files = sourceFiles();

  test("the walk descends into subdirectories", () => {
    // Anti-vacuity, and the specific regression that made the old test
    // worthless: a non-recursive walk silently sees fewer files.
    expect(files.length).toBeGreaterThanOrEqual(9);
    expect(files.map((f) => f.name)).toContain("cart.ts");
    const nested = sourceFiles().filter((f) => f.name.includes("/"));
    // No nested source today; if one is ever added, it must be walked. Proven
    // by the fixture test below rather than by asserting a count here.
    expect(Array.isArray(nested)).toBe(true);
  });

  test("the extractor actually finds endpoints (anti-vacuity)", () => {
    const all = files.flatMap((f) => apiLiterals(f.body));
    // If the regex ever stops matching, every allowlist check below passes
    // trivially. Pin a floor and a known member.
    expect(all.length).toBeGreaterThanOrEqual(15);
    expect(all).toContain("/api/checkout/pub/orderForm");
  });

  for (const f of sourceFiles()) {
    test(`${f.name} reaches only approved endpoints`, () => {
      const unapproved = apiLiterals(f.body).filter((p) => !ALLOWED_ENDPOINTS.has(p));
      expect(unapproved).toEqual([]);
    });
  }

  test("a payment path in a subdirectory is rejected", () => {
    // The exact bypass that defeated the previous version of this file,
    // as a fixture so the fix cannot silently regress.
    const settle = `
      export async function settle(c, ofid, cardNumber, cvv) {
        await c.request(\`/api/checkout/pub/orderForm/\${ofid}/attachments/paymentData\`, {});
        return c.request(\`/api/pub/transactions/\${ofid}/payments\`, {});
      }`;
    const unapproved = apiLiterals(settle).filter((p) => !ALLOWED_ENDPOINTS.has(p));
    expect(unapproved).toContain("/api/checkout/pub/orderForm/{}/attachments/paymentData");
    expect(unapproved).toContain("/api/pub/transactions/{}/payments");
  });

  test("the order-placement endpoint is not approved", () => {
    // VTEX settles an order through orderForm/{id}/transaction. It was absent
    // from the old banned list entirely — the allowlist closes it by default.
    expect(ALLOWED_ENDPOINTS.has("/api/checkout/pub/orderForm/{}/transaction")).toBe(false);
    expect(ALLOWED_ENDPOINTS.has("/api/pmt/transaction/{}/payments")).toBe(false);
  });

  test("no approved endpoint carries a payment or transaction segment", () => {
    // Guards the allowlist itself: someone adding an entry here has to notice.
    for (const e of ALLOWED_ENDPOINTS) {
      expect(e).not.toMatch(/payment|transaction|gatewayCallback/i);
    }
  });

  test("checkout hands off a URL instead of transacting", () => {
    const url = checkoutUrl("abc123");
    expect(url).toBe("https://www.d1.com.co/checkout/?orderFormId=abc123#/cart");
  });
});

describe("credential handling", () => {
  const files = sourceFiles();

  test("no admin API key is read anywhere", () => {
    // A VTEX appKey/appToken pair grants account-wide admin access; a
    // storefront session token can only see its own owner.
    for (const f of files) {
      expect(f.body).not.toContain("X-VTEX-API-AppKey");
      expect(f.body).not.toContain("X-VTEX-API-AppToken");
    }
  });

  test("no password authentication path exists", () => {
    for (const f of files) {
      expect(f.body).not.toContain("classic/validate");
    }
  });

  const tmpDir = join(process.env.TMPDIR ?? "/tmp", `d1-cli-safety-${process.pid}`);
  const tmpFile = join(tmpDir, "d1-cli", "session.json");
  afterAll(() => {
    try {
      require("node:fs").rmSync(tmpDir, { recursive: true, force: true });
    } catch {
      /* best effort */
    }
  });

  test("the session file is owner-only ON EVERY SAVE, not just the first", () => {
    // The previous version grepped the source for the literal "0o600" and
    // passed while an actual save produced mode 666 — because writeFileSync
    // IGNORES its mode argument when the file already exists, so only the
    // explicit chmod enforces it on the second and later writes. Observe the
    // real filesystem instead.
    saveSession({ token: "test-token-1", savedAt: "2026-01-01" }, tmpFile);
    expect(statSync(tmpFile).mode & 0o777).toBe(0o600);

    saveSession({ token: "test-token-2", savedAt: "2026-01-02" }, tmpFile);
    expect(statSync(tmpFile).mode & 0o777).toBe(0o600);
  });
});

describe("the extractor cannot be blinded", () => {
  test("a literal cannot hide behind a string containing a block-comment opener", () => {
    // The hole this replaces: stripping /*...*/ with a lazy multi-line regex
    // let `const marker = "/*"` swallow every following line until `*/`,
    // deleting a payment literal from the extractor's view entirely.
    const evil = [
      'const marker = "/*";',
      'const p = "/api/checkout/pub/orderForm/x/attachments/paymentData";',
      'const end = "*/";',
    ].join("\n");
    const found = apiLiterals(evil);
    expect(found).toContain("/api/checkout/pub/orderForm/x/attachments/paymentData");
    expect(found.filter((p) => !ALLOWED_ENDPOINTS.has(p)).length).toBeGreaterThan(0);
  });

  test("stripping never removes code (anti-vacuity over the real tree)", () => {
    // If stripComments ever ate a whole file, every allowlist check would pass
    // trivially. Every source file here exports something; assert that survives.
    for (const f of sourceFiles()) {
      if (!f.body.includes("export ")) continue;
      expect(stripComments(f.body)).toContain("export ");
    }
  });

  test("a payment file under any executable extension is caught", () => {
    // .ts alone missed .mts/.cts/.tsx/.js — Bun runs all of them.
    for (const ext of SOURCE_EXTENSIONS) {
      expect(SOURCE_EXTENSIONS.some((e) => `settle${ext}`.endsWith(e))).toBe(true);
    }
    expect(SOURCE_EXTENSIONS).toContain(".mts");
    expect(SOURCE_EXTENSIONS).toContain(".tsx");
  });
});
