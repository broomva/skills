import { eagerAgent, governedAgent } from "./actors/policies";
import { EventLog } from "./core/log";
import { check, diff, observe, rollout, step, traceHash } from "./core/ops";
import type { Event } from "./core/types";
import { storefront as world } from "./worlds/storefront";

const HORIZON = 12;
const SEED = 42;

const C = {
  b: "[1m",
  red: "[31m",
  green: "[32m",
  dim: "[2m",
  off: "[0m",
};
const line = (s = "") => console.log(s);
const rule = (t: string) => line(`\n${C.b}${t}${C.off}\n${"-".repeat(t.length)}`);

// ---------------------------------------------------------------- RUN
rule("RUN - the business operates, ungoverned");
const log = new EventLog();
await rollout(world, log, "main", eagerAgent(), HORIZON, SEED);
line(`events: ${log.read("main").length}   branch class: ${log.branchClass("main")}`);

// ---------------------------------------------------------------- OBSERVE
rule("OBSERVE - state is a projection of the log, never a stored value");
const now = observe(world, log, "main") as Record<string, unknown>;
line(`inventory   ${JSON.stringify(now.inventory)}`);
line(
  `cash_cents  ${now.cash_cents}  ${C.dim}(payments ${now.payments_cents} - refunds ${now.refunds_cents})${C.off}`,
);

// ---------------------------------------------------------------- CHECK
rule("CHECK - code predicates over state, never a model's opinion");
const violations = check(world, now, log.head("main"));
if (violations.length === 0) line("all invariants hold");
for (const v of violations) {
  line(`${C.red}VIOLATED${C.off} ${v.invariant} @seq${v.seq}: ${v.message}`);
}

// ---------------------------------------------------------------- FORK
rule("FORK - same history, one thing changed: a governor is installed");
const forkAt = 0;
log.fork("governed", "main", forkAt);
const shield = (e: Omit<Event, "seq" | "branch">) => {
  const probe = step(world, observe(world, log, "governed"), {
    ...e,
    seq: -1,
    branch: "governed",
  });
  return check(world, probe, -1).length > 0;
};
const alt = await rollout(
  world,
  log,
  "governed",
  governedAgent(eagerAgent(), shield),
  HORIZON,
  SEED,
);
const altState = observe(world, log, "governed") as Record<string, unknown>;
line(`forked at seq ${forkAt}, replayed ${HORIZON} steps under the governed policy`);
for (const d of diff(now, altState)) {
  line(`  ${d.key}: ${JSON.stringify(d.from)} -> ${JSON.stringify(d.to)}`);
}
line(`violations   main ${violations.length}  ->  governed ${alt.violations.length}`);

// ---------------------------------------------------------------- PROVE
rule("PROVE - replay is a hash comparison, not a claim");
const log2 = new EventLog();
await rollout(world, log2, "main", eagerAgent(), HORIZON, SEED);
const a = traceHash(log, "main");
const b = traceHash(log2, "main");
line(`same seed   ${a}`);
line(`            ${b}   ${a === b ? `${C.green}IDENTICAL${C.off}` : `${C.red}DIVERGED${C.off}`}`);

const log3 = new EventLog();
await rollout(world, log3, "main", eagerAgent(), HORIZON, SEED + 1);
const c = traceHash(log3, "main");
line(
  `seed + 1    ${c}   ${a === c ? `${C.red}IDENTICAL (bad)${C.off}` : `${C.green}DIVERGED (correct)${C.off}`}`,
);

const log4 = new EventLog();
await rollout(world, log4, "main", eagerAgent("STABLE"), HORIZON, SEED);
line(
  `\nunpinned actor -> branch class ${log4.branchClass("main")} - the replay claim is withdrawn automatically`,
);
line();
