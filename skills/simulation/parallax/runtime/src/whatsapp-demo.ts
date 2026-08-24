/**
 * The whole product as one WhatsApp thread.
 *
 * A message arrives. The runtime reads the sender's own workspace, proposes an
 * ontology from what is in it, and asks the human to accept. The human answers
 * on their phone. Only then does anything run -- and what comes back is an
 * answer plus a link to the proof.
 *
 * Run with: bun run src/whatsapp-demo.ts
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { eagerAgent, governedAgent } from "./actors/policies";
import { renderReceipt } from "./artifact/receipt";
import { parseReply, renderProposal, resolveAccept } from "./channel/conversation";
import { h } from "./core/hash";
import { EventLog } from "./core/log";
import { activate, proposeOntology, worldOf } from "./core/ontology";
import {
  certifyPolicy,
  check,
  diff,
  observe,
  rolloutCertified,
  score,
  step,
  traceHash,
} from "./core/ops";
import type { Event } from "./core/types";
import { storefront } from "./worlds/storefront";

const C = {
  b: "\x1b[1m",
  dim: "\x1b[2m",
  blue: "\x1b[34m",
  g: "\x1b[32m",
  r: "\x1b[31m",
  off: "\x1b[0m",
};
const inbound = (s: string) => console.log(`\n${C.dim}   +57 301 775 8620 >${C.off} ${s}`);
const bot = (s: string) =>
  console.log(`${C.blue}   Parallax >${C.off} ${s.split("\n").join(`\n              `)}`);
const rule = (t: string) => console.log(`\n${C.b}${t}${C.off}\n${"-".repeat(t.length)}`);

// ---------------------------------------------------------------- 1. inbound
rule("A message arrives");
inbound("hola, quiero simular un cambio de precio antes de aplicarlo");

// ---------------------------------------------------------------- 2. propose
rule("The runtime reads the sender's own workspace");
const proposed = proposeOntology({ kind: "agent-workspace" }); // root defaults to cwd, on purpose
if (!proposed.ok) {
  bot(`no pude leer tu espacio de trabajo (${proposed.error.code})`);
  process.exit(1);
}
const proposal = proposed.value;
for (const m of renderProposal(proposal)) {
  bot(`${m.of > 1 ? `(${m.part}/${m.of})\n` : ""}${m.text}`);
}

// ---------------------------------------------------------------- 3. accept
rule("The human accepts, on their phone");
const blocking = proposal.openQuestions.filter((q) => q.blocking);
const reply = `${blocking.map((_, i) => `${i + 1}. unidades`).join("\n")}\nsí, dale`;
inbound(reply);

const intent = parseReply(reply, proposal.openQuestions);
const resolved = resolveAccept(intent, proposal);
if (!resolved.ok) {
  bot(`faltan respuestas: ${(resolved.error.detail?.questions as string[])?.join(" / ")}`);
  process.exit(1);
}

// transition and invariants are CODE. A model never computes a ledger and never
// judges whether a constraint held. Here the accepted domain is the storefront.
const active = activate(proposal, {
  transition: storefront.transition,
  invariants: storefront.invariants,
  answered: resolved.value.answered,
  acceptedBy: "+57 301 775 8620",
  at: Date.parse("2026-08-23T02:00:00Z"),
});
if (!active.ok) {
  bot(`no puedo activar: ${active.error.reason}`);
  process.exit(1);
}
const w = worldOf(active.value);
if (!w.ok) process.exit(1);
const world = { ...w.value, initial: storefront.initial, actions: storefront.actions };
bot(`aceptado. nada corrió hasta ahora.`);

// ------------------------------------------------------- 4. certify + run
rule("Certify the policy before trusting anything it says about itself");
const cert = await certifyPolicy(eagerAgent("PINNED"), { state: world.initial, seq: 0, seed: 42 });
if (!cert.ok) process.exit(1);
console.log(
  `   declared ${cert.value.declared}  ->  demonstrated ${cert.value.effective}   ${cert.value.demoted ? `${C.r}DEMOTED${C.off}` : `${C.g}holds${C.off}`}`,
);
console.log(`   ${C.dim}${cert.value.reason}${C.off}`);

const log = new EventLog();
const base = await rolloutCertified(world, log, "main", eagerAgent("PINNED"), cert.value, 12, 42);
const baseState = observe(world, log, "main") as Record<string, unknown>;
bot(`corrí 12 pasos. ${base.violations.length} violaciones.`);
for (const v of base.violations)
  console.log(`      ${C.r}${v.invariant}${C.off} @seq${v.seq}: ${v.message}`);

// ------------------------------------------------------- 5. fork the change
rule("Fork the history and change one thing");
log.fork("governed", "main", 0);
const shield = (e: Omit<Event, "seq" | "branch">) =>
  check(
    world,
    step(world, observe(world, log, "governed"), { ...e, seq: -1, branch: "governed" }),
    -1,
  ).length > 0;
const gov = governedAgent(eagerAgent("PINNED"), shield);
const govCert = await certifyPolicy(gov, { state: world.initial, seq: 0, seed: 42 });
if (!govCert.ok) process.exit(1);
const alt = await rolloutCertified(world, log, "governed", gov, govCert.value, 12, 42);
const altState = observe(world, log, "governed") as Record<string, unknown>;
for (const d of diff(baseState, altState)) {
  console.log(`   ${d.key}: ${C.dim}${JSON.stringify(d.from)}${C.off} -> ${JSON.stringify(d.to)}`);
}
bot(`con el gobernador: ${base.violations.length} -> ${alt.violations.length} violaciones.`);

// ------------------------------------------------------- 6. score + receipt
rule("Score it, then hand back the proof");
const objectives = [
  {
    name: "orders_promised",
    of: (t: typeof alt.trajectory) => t.filter((s) => s.event.action === "promise").length,
  },
  {
    name: "violations",
    of: (t: typeof alt.trajectory) => t.reduce((n, s) => n + s.violations.length, 0),
    direction: "minimize" as const,
  },
];
const scores = objectives
  .map((o) => score(alt.trajectory, o))
  .filter((s) => s.ok)
  .map((s) => s.value);

const runId = h({ branch: "governed", seed: 42, at: active.value.acceptedAt });
const html = renderReceipt({
  runId,
  ontology: active.value,
  certificate: govCert.value,
  trajectory: alt.trajectory,
  scores,
  traceHash: traceHash(log, "governed"),
  branchClass: log.branchClass("governed"),
  baseline: { traceHash: traceHash(log, "main"), violations: base.violations.length },
});

mkdirSync("out", { recursive: true });
const path = `out/run-${runId.slice(0, 8)}.html`;
writeFileSync(path, html);

// The receipt this run produced is a FILE, and that is what gets named. The
// hosted form of the same artifact is `GET /r/<runId>` on a hub that actually
// ran the flow -- see `bun run demo:live`. Naming a URL here that no server was
// asked to serve would be the exact failure this product exists to refuse: a
// confident-looking answer nobody checked.
bot(`listo. el recibo: ${C.b}${path}${C.off}`);
console.log(
  `\n   ${C.dim}${(html.length / 1024).toFixed(1)} KB, self-contained, opens with no server${C.off}`,
);
console.log(
  `   ${C.dim}trace main=${traceHash(log, "main").slice(0, 12)}  governed=${traceHash(log, "governed").slice(0, 12)}${C.off}\n`,
);
