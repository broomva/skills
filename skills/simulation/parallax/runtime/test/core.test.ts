import { describe, expect, test } from "bun:test";
import { eagerAgent } from "../src/actors/policies";
import { canonical, effectiveClass, meet } from "../src/core/hash";
import { EventLog } from "../src/core/log";
import { activate, isActive, proposeOntology, worldOf } from "../src/core/ontology";
import type { Policy } from "../src/core/ops";
import {
  certifyPolicy,
  check,
  diff,
  observe,
  rolloutCertified,
  score,
  traceHash,
} from "../src/core/ops";
import { combine, meetOrigin, splitOrigins } from "../src/core/provenance";
import { fail, isOk, ok } from "../src/core/result";
import { storefront as world } from "../src/worlds/storefront";

const PROBE = { state: world.initial, seq: 0, seed: 42 };

function acceptedFromSrc() {
  const p = proposeOntology({ kind: "filesystem", root: "./src" });
  if (!p.ok) throw new Error("proposal failed");
  const answered = p.value.openQuestions.filter((q) => q.blocking).map((q) => q.slot);
  return activate(p.value, {
    transition: (s) => s,
    invariants: [{ name: "n", kind: "conservation", check: () => null }],
    answered,
    acceptedBy: "test",
    at: 1,
  });
}

describe("result", () => {
  test("ok and err are distinguishable without throwing", () => {
    expect(isOk(ok(1))).toBe(true);
    expect(isOk(fail("X", "why"))).toBe(false);
  });
  test("errors carry a stable code", () => {
    expect(fail("SOURCE_EMPTY", "why").error.code).toBe("SOURCE_EMPTY");
  });
});

describe("provenance", () => {
  test("observed only when every input is observed", () => {
    expect(meetOrigin("observed", "observed")).toBe("observed");
    expect(meetOrigin("observed", "simulated")).toBe("simulated");
    expect(meetOrigin("simulated", "simulated")).toBe("simulated");
  });
  test("contamination flows one way through combine", () => {
    const r = combine(
      [
        { value: 1, origin: "observed" },
        { value: 2, origin: "simulated" },
      ],
      (v) => (v[0] ?? 0) + (v[1] ?? 0),
    );
    expect(r.value).toBe(3);
    expect(r.origin).toBe("simulated");
  });
  test("split counts both sides", () => {
    expect(splitOrigins(["observed", "simulated", "simulated"])).toEqual({
      observed: 1,
      simulated: 2,
    });
  });
});

describe("hash", () => {
  test("canonical is key-order independent", () => {
    expect(canonical({ a: 1, b: 2 })).toBe(canonical({ b: 2, a: 1 }));
  });
  test("canonical refuses non-finite numbers rather than silently drifting", () => {
    expect(() => canonical({ x: Number.NaN })).toThrow();
  });
  test("meet returns the weakest class", () => {
    expect(meet("PINNED", "RECORDED")).toBe("RECORDED");
    expect(meet("PINNED", "PINNED")).toBe("PINNED");
  });
  test("a seedless derivation cannot be PINNED however it declares itself", () => {
    const d = {
      kind: "k",
      model: "m",
      params: {},
      seed: null,
      inputs: [],
      declared: "PINNED" as const,
    };
    expect(effectiveClass(d, [])).toBe("STABLE");
  });
  test("but a seeded one is left alone -- the demotion is not unconditional", () => {
    const d = {
      kind: "k",
      model: "m",
      params: {},
      seed: 7,
      inputs: [],
      declared: "PINNED" as const,
    };
    expect(effectiveClass(d, [])).toBe("PINNED");
  });
});

describe("log", () => {
  test("a fork inherits its parent's past up to the fork point and no further", () => {
    const log = new EventLog();
    for (let i = 0; i < 3; i++) {
      log.append({
        ts: 0,
        branch: "main",
        actor: "a",
        action: "restock",
        params: { sku: "panela", qty: 1 },
        derivation: null,
        klass: "PINNED",
      });
    }
    log.fork("alt", "main", 2);
    log.append({
      ts: 0,
      branch: "main",
      actor: "a",
      action: "restock",
      params: { sku: "panela", qty: 99 },
      derivation: null,
      klass: "PINNED",
    });
    expect(log.read("alt").length).toBe(2);
    expect(log.read("main").length).toBe(4);
  });
  test("an unknown branch is refused, not silently empty", () => {
    expect(() => new EventLog().read("nope")).toThrow();
  });
});

describe("operators", () => {
  test("observe folds the log and check finds the oversell the storefront allows", () => {
    const log = new EventLog();
    log.append({
      ts: 0,
      branch: "main",
      actor: "s",
      action: "promise",
      params: { order: "O1", sku: "panela", qty: 1 },
      derivation: null,
      klass: "PINNED",
    });
    log.append({
      ts: 0,
      branch: "main",
      actor: "o",
      action: "fulfill",
      params: { order: "O1" },
      derivation: null,
      klass: "PINNED",
    });
    const st = observe(world, log, "main") as Record<string, unknown>;
    expect((st.inventory as Record<string, number>).panela).toBe(-1);
    expect(check(world, st, 2).map((v) => v.invariant)).toContain("inventory_nonneg");
  });
  test("diff reports only what changed", () => {
    expect(diff({ a: 1, b: 2 }, { a: 1, b: 3 })).toEqual([{ key: "b", from: 2, to: 3 }]);
  });
  test("traceHash is stable across logs with identical content", () => {
    const mk = () => {
      const l = new EventLog();
      l.append({
        ts: 0,
        branch: "main",
        actor: "a",
        action: "restock",
        params: { sku: "x", qty: 1 },
        derivation: null,
        klass: "PINNED",
      });
      return l;
    };
    expect(traceHash(mk(), "main")).toBe(traceHash(mk(), "main"));
  });
  test("traceHash separates logs whose content differs", () => {
    const l1 = new EventLog();
    l1.append({
      ts: 0,
      branch: "main",
      actor: "a",
      action: "restock",
      params: { sku: "x", qty: 1 },
      derivation: null,
      klass: "PINNED",
    });
    const l2 = new EventLog();
    l2.append({
      ts: 0,
      branch: "main",
      actor: "a",
      action: "restock",
      params: { sku: "x", qty: 2 },
      derivation: null,
      klass: "PINNED",
    });
    expect(traceHash(l1, "main")).not.toBe(traceHash(l2, "main"));
  });
});

describe("policy certification -- the gate that used to be dead code", () => {
  test("an honest seeded policy keeps its declared class", async () => {
    const c = await certifyPolicy(eagerAgent("PINNED"), PROBE);
    expect(c.ok).toBe(true);
    if (c.ok) {
      expect(c.value.effective).toBe("PINNED");
      expect(c.value.demoted).toBe(false);
    }
  });

  test("a nondeterministic policy declaring PINNED is demoted", async () => {
    const liar: Policy = {
      name: "liar",
      klass: "PINNED",
      async propose(_s, i) {
        return {
          ts: 0,
          actor: "s",
          action: "promise",
          params: { order: `O${i}`, sku: "panela", nonce: crypto.randomUUID() },
          derivation: null,
          klass: "PINNED",
        };
      },
    };
    const c = await certifyPolicy(liar, PROBE);
    expect(c.ok).toBe(true);
    if (c.ok) {
      expect(c.value.demoted).toBe(true);
      expect(c.value.effective).toBe("STABLE");
    }
  });

  test("the demotion reaches the branch, not just the certificate", async () => {
    const liar: Policy = {
      name: "liar",
      klass: "PINNED",
      async propose(_s, _i) {
        return {
          ts: 0,
          actor: "s",
          action: "restock",
          // A large output space: a false negative here is ~2^-104, not the 4% a
          // five-value draw gives at three trials. This test asserts that the
          // demotion PROPAGATES, so it must not sit on top of the filter's bound.
          params: { sku: "panela", qty: 1, nonce: crypto.randomUUID() },
          derivation: null,
          klass: "PINNED",
        };
      },
    };
    const cert = await certifyPolicy(liar, PROBE);
    if (!cert.ok) throw new Error("cert failed");
    const log = new EventLog();
    await rolloutCertified(world, log, "main", liar, cert.value, 4, 42);
    expect(log.branchClass("main")).toBe("STABLE");
  });

  test("a small output space is a real false-negative bound, not a bug", async () => {
    // Documents the limit rather than pretending it is absent: with two possible
    // outputs and three trials, a nondeterministic policy escapes about a
    // quarter of the time. Certification filters; it does not prove.
    let escaped = 0;
    for (let i = 0; i < 40; i++) {
      const coin: Policy = {
        name: "coin",
        klass: "PINNED",
        async propose() {
          return {
            ts: 0,
            actor: "s",
            action: "restock",
            params: { sku: "panela", qty: Math.random() < 0.5 ? 1 : 2 },
            derivation: null,
            klass: "PINNED",
          };
        },
      };
      const c = await certifyPolicy(coin, PROBE);
      if (c.ok && !c.value.demoted) escaped++;
    }
    expect(escaped).toBeGreaterThan(0);
    expect(escaped).toBeLessThan(40);
  });

  test("raising trials tightens that bound", async () => {
    const coin: Policy = {
      name: "coin",
      klass: "PINNED",
      async propose() {
        return {
          ts: 0,
          actor: "s",
          action: "restock",
          params: { sku: "panela", qty: Math.random() < 0.5 ? 1 : 2 },
          derivation: null,
          klass: "PINNED",
        };
      },
    };
    let escaped20 = 0;
    for (let i = 0; i < 40; i++) {
      const c = await certifyPolicy(coin, PROBE, 20);
      if (c.ok && !c.value.demoted) escaped20++;
    }
    expect(escaped20).toBe(0);
  });

  test("a throwing policy is a typed error, not an exception at the call site", async () => {
    const boom: Policy = {
      name: "boom",
      klass: "PINNED",
      async propose() {
        throw new Error("x");
      },
    };
    const c = await certifyPolicy(boom, PROBE);
    expect(c.ok).toBe(false);
    if (!c.ok) expect(c.error.code).toBe("POLICY_THREW");
  });
});

describe("ontology accept gate", () => {
  test("proposes state and actions from what is actually in the directory", () => {
    const p = proposeOntology({ kind: "filesystem", root: "./src" });
    expect(p.ok).toBe(true);
    if (p.ok) {
      expect(p.value.actions.length).toBeGreaterThan(0);
      expect(p.value.evidence.length).toBeGreaterThan(0);
      expect(p.value.evidence[0]?.from).toContain("directory");
    }
  });

  test("an unreadable source is a typed error", () => {
    const p = proposeOntology({ kind: "filesystem", root: "/nonexistent-parallax-probe" });
    expect(p.ok).toBe(false);
    if (!p.ok) expect(p.error.code).toBe("SOURCE_UNREADABLE");
  });

  test("refuses to activate while a blocking unit question is open", () => {
    const p = proposeOntology({ kind: "filesystem", root: "./src" });
    if (!p.ok) throw new Error("proposal failed");
    const r = activate(p.value, {
      transition: (s) => s,
      invariants: [{ name: "n", kind: "conservation", check: () => null }],
      acceptedBy: "t",
      at: 0,
    });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("BLOCKING_QUESTIONS_OPEN");
  });

  test("refuses a domain with no invariants", () => {
    const p = proposeOntology({ kind: "filesystem", root: "./src" });
    if (!p.ok) throw new Error("proposal failed");
    const answered = p.value.openQuestions.filter((q) => q.blocking).map((q) => q.slot);
    const r = activate(p.value, {
      transition: (s) => s,
      invariants: [],
      answered,
      acceptedBy: "t",
      at: 0,
    });
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("NO_INVARIANTS");
  });

  test("accepts when the questions are answered -- the control against a vacuous gate", () => {
    const r = acceptedFromSrc();
    expect(r.ok).toBe(true);
    if (r.ok) expect(worldOf(r.value).ok).toBe(true);
  });

  test("a forged object literal cannot pass as accepted", () => {
    const forged = {
      world: { slug: "pwned" },
      acceptedBy: "attacker",
      acceptedAt: 0,
      proposalId: "x",
    };
    expect(isActive(forged)).toBe(false);
    // biome-ignore lint/suspicious/noExplicitAny: deliberately probing the runtime gate
    const r = worldOf(forged as any);
    expect(r.ok).toBe(false);
    if (!r.ok) expect(r.error.code).toBe("NOT_ACCEPTED");
  });

  test("a same-named symbol cannot forge the brand", () => {
    const fake = Symbol("parallax.accepted");
    // biome-ignore lint/suspicious/noExplicitAny: deliberately probing the runtime gate
    expect(worldOf({ [fake]: true, world: {} } as any).ok).toBe(false);
  });

  test("trust does not survive a JSON round-trip", () => {
    const r = acceptedFromSrc();
    if (!r.ok) throw new Error("accept failed");
    expect(worldOf(JSON.parse(JSON.stringify(r.value))).ok).toBe(false);
  });
});

describe("score", () => {
  test("folds a trajectory and carries the origin of the answer", async () => {
    const cert = await certifyPolicy(eagerAgent("PINNED"), PROBE);
    if (!cert.ok) throw new Error("cert failed");
    const log = new EventLog();
    const r = await rolloutCertified(world, log, "main", eagerAgent("PINNED"), cert.value, 6, 42);
    const s = score(r.trajectory, { name: "steps", of: (t) => t.length });
    expect(s.ok).toBe(true);
    if (s.ok) {
      expect(s.value.value).toBe(6);
      expect(s.value.origin).toBe("simulated");
    }
  });

  test("an empty trajectory is a typed error, not zero", () => {
    const s = score([], { name: "x", of: () => 1 });
    expect(s.ok).toBe(false);
    if (!s.ok) expect(s.error.code).toBe("EMPTY_TRAJECTORY");
  });

  test("a run that violated an invariant is inadmissible", async () => {
    const cert = await certifyPolicy(eagerAgent("PINNED"), PROBE);
    if (!cert.ok) throw new Error("cert failed");
    const log = new EventLog();
    const r = await rolloutCertified(world, log, "main", eagerAgent("PINNED"), cert.value, 12, 42);
    const s = score(r.trajectory, { name: "steps", of: (t) => t.length });
    if (s.ok) expect(s.value.admissible).toBe(false);
  });
});
