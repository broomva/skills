/**
 * Integration coverage for `main()`.
 *
 * Round-2 review found that NOTHING in the suite invoked `main()`: the exit-code
 * split and the `cart add` verdict could both be reverted to their original
 * buggy form and every test stayed green. The behaviour was correct and
 * unproven, which is indistinguishable from correct-by-accident.
 *
 * These spawn the real CLI. They exercise only paths that fail BEFORE any
 * network call, so the suite stays network-free and cannot go red because D1 is
 * down.
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
    expect(code).toBeGreaterThan(0);
    expect(stderr).toMatch(/may not contain|not an approved D1 endpoint/);
  }, 20_000);
});
