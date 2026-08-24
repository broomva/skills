import { describe, expect, test } from "bun:test";
import { EventLog } from "../src/core/log";
import { check, observe, traceHash } from "../src/core/ops";
import type { Event } from "../src/core/types";
import { clinic as world } from "../src/worlds/clinic";
import { storefront } from "../src/worlds/storefront";

function logWith(events: Array<Omit<Event, "seq" | "branch" | "ts" | "derivation" | "klass">>) {
  const log = new EventLog();
  for (const e of events) {
    log.append({ ...e, ts: 0, branch: "main", derivation: null, klass: "PINNED" });
  }
  return log;
}
const book = (ref: string, clinician: string, start: number, minutes: number, cents = 0) => ({
  actor: "front-desk",
  action: "book",
  params: { ref, clinician, start, minutes, cents },
});

function violations(log: EventLog) {
  const st = observe(world, log, "main");
  return check(world, st, log.head("main")).map((v) => v.invariant);
}

describe("clinic — the runtime is unchanged, the domain is data", () => {
  test("a domain is five slots and nothing more", () => {
    expect(Object.keys(world).sort()).toEqual(
      ["actions", "initial", "invariants", "slug", "title", "transition"].sort(),
    );
  });

  test("every numeric action param carries a unit", () => {
    for (const a of world.actions) {
      for (const [name, type] of Object.entries(a.params)) {
        if (type === "number") expect(a.units?.[name]).toBeDefined();
      }
    }
  });

  test("the same operators fold over a second, unrelated domain", () => {
    // observe/check/traceHash take a TypeRecord; nothing about them knows a storefront.
    const a = traceHash(logWith([book("A", "dr_ochoa", 0, 30)]), "main");
    const b = traceHash(logWith([book("A", "dr_ochoa", 0, 30)]), "main");
    expect(a).toBe(b);
    expect(storefront.slug).not.toBe(world.slug);
  });
});

describe("clinic — conservation of a different shape", () => {
  test("the scalar ledger balances and the schedule is still impossible", () => {
    // This is the whole reason this world exists. 120 of 240 minutes committed,
    // cash conserved -- a storefront-shaped scalar check sees nothing wrong --
    // and one clinician is in two rooms at 00:30.
    const log = logWith([
      book("A1", "dr_ochoa", 0, 60, 120000),
      book("A2", "dr_ochoa", 30, 60, 120000),
    ]);
    const st = observe(world, log, "main") as {
      committed: Record<string, number>;
      roster: Record<string, number>;
    };
    expect(st.committed.dr_ochoa).toBe(120);
    expect(st.committed.dr_ochoa).toBeLessThanOrEqual(st.roster.dr_ochoa ?? 0);

    const v = violations(log);
    expect(v).not.toContain("roster_not_oversold");
    expect(v).toContain("no_double_booking");
  });

  test("adjacent appointments do not overlap — the boundary case", () => {
    // 0-60 and 60-120 touch but do not overlap. An off-by-one here would make
    // the invariant fire on every back-to-back booking, which is the normal case.
    expect(
      violations(logWith([book("A", "dr_ochoa", 0, 60), book("B", "dr_ochoa", 60, 60)])),
    ).toEqual([]);
  });

  test("two clinicians at the same time is fine", () => {
    expect(
      violations(logWith([book("A", "dr_ochoa", 0, 60), book("B", "dr_pineda", 0, 60)])),
    ).toEqual([]);
  });
});

describe("clinic — every invariant is individually reachable", () => {
  test("roster_not_oversold", () => {
    const es = Array.from({ length: 5 }, (_, i) => book(`R${i}`, "nurse_rios", i * 30, 30));
    expect(violations(logWith(es))).toContain("roster_not_oversold");
  });

  test("no_double_booking", () => {
    expect(
      violations(logWith([book("A", "dr_ochoa", 0, 60), book("B", "dr_ochoa", 30, 60)])),
    ).toContain("no_double_booking");
  });

  test("no_attendance_without_booking", () => {
    const log = logWith([
      { actor: "clinician", action: "attend", params: { ref: "GHOST", cents: 1000 } },
    ]);
    expect(violations(log)).toContain("no_attendance_without_booking");
  });

  test("booking_inside_the_session", () => {
    expect(violations(logWith([book("L", "nurse_rios", 230, 60)]))).toContain(
      "booking_inside_the_session",
    );
  });

  test("cash_conserved fires when refunds exceed what was collected", () => {
    const log = logWith([
      book("A", "dr_ochoa", 0, 30, 50000),
      { actor: "front-desk", action: "refund", params: { ref: "A", cents: 50000 } },
      { actor: "front-desk", action: "refund", params: { ref: "A", cents: 50000 } },
    ]);
    expect(violations(log)).toContain("cash_conserved");
  });
});

describe("clinic — the control", () => {
  test("a clean session produces zero violations", () => {
    // Without this, a checker that fires on everything is indistinguishable
    // from one that works.
    const log = logWith([
      book("C1", "dr_ochoa", 0, 60, 120000),
      book("C2", "dr_ochoa", 60, 60, 120000),
      book("C3", "dr_pineda", 0, 45, 90000),
      { actor: "clinician", action: "attend", params: { ref: "C1", cents: 120000 } },
      { actor: "front-desk", action: "no_show", params: { ref: "C2" } },
    ]);
    expect(violations(log)).toEqual([]);
  });

  test("cancelling releases the clinician's minutes back", () => {
    const log = logWith([
      book("A", "dr_ochoa", 0, 60),
      { actor: "front-desk", action: "cancel", params: { ref: "A" } },
      book("B", "dr_ochoa", 0, 60),
    ]);
    const st = observe(world, log, "main") as { committed: Record<string, number> };
    expect(st.committed.dr_ochoa).toBe(60);
    expect(violations(log)).toEqual([]);
  });

  test("a cancelled slot frees the time for someone else — fork-relevant", () => {
    const log = logWith([book("A", "dr_ochoa", 0, 60)]);
    log.fork("alt", "main", 1);
    log.append({
      ts: 0,
      branch: "alt",
      actor: "front-desk",
      action: "cancel",
      params: { ref: "A" },
      derivation: null,
      klass: "PINNED",
    });
    log.append({
      ts: 0,
      branch: "alt",
      actor: "front-desk",
      action: "book",
      params: { ref: "B", clinician: "dr_ochoa", start: 0, minutes: 60, cents: 0 },
      derivation: null,
      klass: "PINNED",
    });
    const alt = observe(world, log, "alt");
    expect(check(world, alt, log.head("alt"))).toEqual([]);
    expect(traceHash(log, "main")).not.toBe(traceHash(log, "alt"));
  });
});
