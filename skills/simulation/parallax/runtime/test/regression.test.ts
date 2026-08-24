import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { mkdirSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { activate, proposeOntology } from "../src/core/ontology";
import { propose } from "../src/tools/handlers";

/**
 * Regressions for two blockers found by adversarial review, not by the suite.
 *
 * Both were guards that existed, read correctly, and did not hold. Each test
 * below is paired with a CONTROL that must PASS, because a guard which refuses
 * everything is indistinguishable from a working one on the refusal case alone
 * -- which is precisely how both of these survived the tests written beside them.
 */

const ROOT = join(tmpdir(), `parallax-regression-${process.pid}`);
const DOTONLY = join(ROOT, "dotonly");
const WS = join(ROOT, "ws");
const OUTSIDE = join(ROOT, "outside");
const cwd0 = process.cwd();

beforeAll(() => {
  rmSync(ROOT, { recursive: true, force: true });
  // A workspace whose entries are ALL dot entries. This is not contrived: a
  // freshly provisioned tenant directory contains only `.claude`.
  mkdirSync(DOTONLY, { recursive: true });
  writeFileSync(join(DOTONLY, ".env"), "SECRET=1\n");
  writeFileSync(join(DOTONLY, ".gitignore"), "x\n");

  // A workspace containing a symlink that leaves it.
  mkdirSync(join(WS, "real_sub"), { recursive: true });
  writeFileSync(join(WS, "real_sub", "a.ts"), "x\n");
  writeFileSync(join(WS, "note.md"), "y\n");
  mkdirSync(join(OUTSIDE, "customer_pii"), { recursive: true });
  writeFileSync(join(OUTSIDE, "private.key"), "k");
  symlinkSync(OUTSIDE, join(WS, "data"));
});

afterAll(() => {
  process.chdir(cwd0);
  rmSync(ROOT, { recursive: true, force: true });
});

describe("regression: an empty reading of the context must not walk the accept gate", () => {
  test("a dot-only workspace is refused at propose", () => {
    const r = proposeOntology({ kind: "filesystem", root: DOTONLY });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("DEGENERATE_CONTEXT");
  });

  test("CONTROL: a workspace with visible entries still proposes", () => {
    const r = proposeOntology({ kind: "filesystem", root: WS });
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.actions.length).toBeGreaterThan(0);
  });

  test("activate refuses an empty action space however the proposal arrived", () => {
    // Defence in depth: even if a proposer produced one, a domain with no
    // actions has no action space, so nothing can happen and there is nothing
    // to simulate. Without this, zero actions means zero blocking questions,
    // which means every downstream gate is vacuously satisfied.
    const empty = {
      id: "x",
      source: { kind: "filesystem" as const, root: DOTONLY },
      slug: "empty",
      title: "empty",
      initial: {},
      actions: [],
      invariants: [],
      evidence: [],
      openQuestions: [],
    };
    const r = activate(empty, {
      transition: (s) => s,
      invariants: [{ name: "n", kind: "conservation", check: () => null }],
      acceptedBy: "anyone",
      at: 0,
    });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("NO_ACTIONS");
  });

  test("CONTROL: a proposal with actions still activates once answered", () => {
    const p = proposeOntology({ kind: "filesystem", root: WS });
    if (!p.ok) throw new Error("control proposal failed");
    const answered = p.value.openQuestions.filter((q) => q.blocking).map((q) => q.slot);
    const r = activate(p.value, {
      transition: (s) => s,
      invariants: [{ name: "n", kind: "conservation", check: () => null }],
      answered,
      acceptedBy: "carlos",
      at: 1,
    });
    expect(r.ok).toBe(true);
  });
});

describe("regression: confine() must resolve symlinks, not just prefixes", () => {
  beforeAll(() => process.chdir(WS));

  test("a symlink out of the workspace is refused", () => {
    const r = propose({ within: "data" });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("PATH_ESCAPES_WORKSPACE");
  });

  test("nothing outside the workspace is read before the refusal", () => {
    const r = propose({ within: "data" });
    // The failure mode was that an outside directory's listing reached the
    // human-facing message and the persisted record. Assert on the value, not
    // just the code.
    expect(r.ok).toBe(false);
    expect(JSON.stringify(r)).not.toContain("customer_pii");
    expect(JSON.stringify(r)).not.toContain("private.key");
  });

  test.each([
    ["..", "PATH_ESCAPES_WORKSPACE"],
    ["../..", "PATH_ESCAPES_WORKSPACE"],
    ["real_sub/../..", "PATH_ESCAPES_WORKSPACE"],
    ["/etc", "PATH_ABSOLUTE"],
    ["nope", "PATH_NOT_FOUND"],
  ])("%p is refused with %p", (within, code) => {
    const r = propose({ within });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(String(r.error.code)).toBe(code);
  });

  test("CONTROL: a real subdirectory inside the workspace is allowed", () => {
    const r = propose({ within: "real_sub" });
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.slug).toBe("real_sub");
  });

  test("CONTROL: no `within` reads the workspace itself", () => {
    const r = propose({});
    expect(r.ok).toBe(true);
    if (r.ok) expect(r.value.stateFields.length).toBeGreaterThan(0);
  });
});
