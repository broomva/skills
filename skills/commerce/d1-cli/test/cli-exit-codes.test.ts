/**
 * Integration coverage for `main()`.
 *
 * Round-2 review found that NOTHING in the suite invoked `main()`: the exit-code
 * split and the `cart add` verdict could both be reverted to their original
 * buggy form and every test stayed green. The behaviour was correct and
 * unproven, which is indistinguishable from correct-by-accident.
 *
 * These spawn the real CLI and exercise only paths that fail BEFORE any network
 * call. That property was CLAIMED here once before and was false: `case "cart"`
 * fetched the cart ahead of the subcommand switch, so `d1 cart bogus` issued a
 * live POST that created an orderForm on D1's production storefront before
 * deciding the command was invalid — 531ms versus 51ms for a genuinely offline
 * usage error. Every test run wrote to a third party, and every one of these
 * assertions silently depended on egress.
 *
 * `validateCartArgs` now runs first, and `no cart command touches the network
 * before validating` below MEASURES the property rather than asserting it in a
 * comment.
 */

import { describe, expect, test } from "bun:test";
import { join } from "node:path";

const CLI = join(import.meta.dir, "..", "src", "cli.ts");
const CONFIG = join(process.env.TMPDIR ?? "/tmp", `d1-exit-${process.pid}`);

async function run(args: string[]): Promise<{ code: number; stderr: string }> {
  const p = Bun.spawn(["bun", "run", CLI, ...args], {
    env: { ...process.env, D1_CONFIG_DIR: CONFIG },
    stdout: "pipe",
    stderr: "pipe",
  });
  const stderr = await new Response(p.stderr).text();
  await new Response(p.stdout).text();
  return { code: await p.exited, stderr };
}

describe("exit codes are a contract an agent can branch on", () => {
  test("a usage error exits 2, never 1", async () => {
    // 1 means "D1 refused or was unreachable" and invites a retry; 2 means the
    // call itself was wrong and retrying it verbatim can never help. Collapsing
    // them leaves a caller retrying a typo forever.
    for (const args of [
      ["suggest"],
      ["quote"],
      ["order"],
      ["region"],
      ["search", "--lat", "4.65"],
      ["cart", "add"],
      ["cart", "set", "0"],
      ["cart", "bogus-subcommand"],
      ["totally-unknown-command"],
    ]) {
      const { code } = await run(args);
      expect({ args, code }).toEqual({ args, code: 2 });
    }
  }, 60_000);

  test("a malformed --qty exits 2 and says why", async () => {
    const { code, stderr } = await run(["cart", "add", "262", "--qty", "abc"]);
    expect(code).toBe(2);
    expect(stderr).toMatch(/positive whole number/);
  }, 20_000);

  test("a non-integer cart index exits 2, not 1", async () => {
    // These reach cart.ts's own guard, which raises a plain D1Error — exit 1,
    // i.e. "D1 refused", about the caller's own malformed input.
    expect((await run(["cart", "set", "0", "1.5"])).code).toBe(2);
    expect((await run(["cart", "set", "-1", "3"])).code).toBe(2);
  }, 30_000);

  test("--help exits 0 and bare invocation exits 2", async () => {
    expect((await run(["--help"])).code).toBe(0);
    expect((await run([])).code).toBe(2);
  }, 20_000);

  test("a refused endpoint fails closed rather than being requested", async () => {
    // The runtime allowlist. This must NOT reach the network, so it is safe in
    // a network-free suite.
    const { code, stderr } = await run([
      "search",
      "--facets",
      "../../../../../../api/checkout/pub/orderForm/OF1/transaction",
    ]);
    // Pinned to 2, not `> 0`: a malformed --facets is a USAGE error. The loose
    // form was the only imprecise assertion in a file whose entire job is
    // pinning exit codes, and it papered over this exact case returning 1.
    expect(code).toBe(2);
    expect(stderr).toMatch(/may not contain/);
  }, 20_000);
});

describe("a usage error costs nothing and does not depend on D1", () => {
  /**
   * Measures the network-free property instead of asserting it in prose.
   *
   * A usage error that reaches the network is wrong twice: it writes to a third
   * party's production storefront on every typo (and every test run), and it
   * makes the exit code depend on D1's availability — with the network down the
   * caller saw 1 ("D1 refused, retry may help") for its own malformed input.
   *
   * Timing is the observable available to a subprocess test. A live orderForm
   * POST to Bogotá measured ~530ms against ~50ms for a purely local failure, so
   * the threshold sits well clear of both.
   */
  const NETWORK_FREE_MS = 350;

  test("no cart usage error makes a request", async () => {
    for (const args of [
      ["cart", "bogus-subcommand"],
      ["cart", "add"],
      ["cart", "add", "262", "--qty", "abc"],
      ["cart", "set", "0"],
      ["cart", "set", "0", "1.5"],
      ["cart", "set", "-1", "3"],
    ]) {
      const t0 = Bun.nanoseconds();
      const { code } = await run(args);
      const ms = (Bun.nanoseconds() - t0) / 1e6;
      expect({ args, code }).toEqual({ args, code: 2 });
      expect({ args, networkFree: ms < NETWORK_FREE_MS }).toEqual({ args, networkFree: true });
    }
  }, 60_000);
});
