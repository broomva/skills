/**
 * The demo, driven against the DEPLOYED hub.
 *
 * `demo:whatsapp` proves the runtime works. This proves the deployed thing
 * works, which is a different claim, and the one anyone deciding whether to
 * trust it is actually owed.
 *
 * Three properties it is built to hold when it runs live:
 *
 *   1. It opens by reading `/health`, which reports the commit the server is
 *      running. A deploy-status API and a static `version` field both stay
 *      green on a stale image; the commit is the only field that cannot.
 *   2. The client sends `{from, text, threadId}` -- a WhatsApp message, nothing
 *      more. Every ontology, every run and every receipt is authored server
 *      side. There is deliberately no path by which this process hands the hub
 *      content to publish.
 *   3. It GETs the receipt before naming it. A link is printed only once a
 *      server has been observed serving it.
 *
 * Run with: bun run demo:live      (add --fast to drop the pacing)
 */
export {}; // top-level await needs this file to be a module

const HUB = (process.env.PARALLAX_HUB ?? "https://parallax-hub.onrender.com").replace(/\/+$/, "");
const FAST = process.argv.includes("--fast") || process.env.PARALLAX_PACE === "0";
/** Dial the whole demo up or down: PARALLAX_PACE=1.6 bun run demo:live */
const PACE = FAST ? 0 : Math.max(0, Number(process.env.PARALLAX_PACE ?? "1")) || 1;
const FROM = "+57 301 775 8620";

const C = {
  b: "\x1b[1m",
  dim: "\x1b[2m",
  blue: "\x1b[34m",
  g: "\x1b[32m",
  r: "\x1b[31m",
  y: "\x1b[33m",
  off: "\x1b[0m",
};

/** \r only erases on a terminal; in a captured log it would just add noise. */
const clearLine = () => {
  if (process.stdout.isTTY) process.stdout.write(`\r${" ".repeat(120)}\r`);
  else process.stdout.write("\n");
};
const sleep = (ms: number) => new Promise((r) => setTimeout(r, Math.round(ms * PACE)));
const rule = (t: string) => console.log(`\n${C.b}${t}${C.off}\n${"-".repeat(t.length)}`);

/** Type a string out at a human cadence, so a thread reads as a thread. */
async function type(prefix: string, s: string, perChar: number): Promise<void> {
  process.stdout.write(prefix);
  if (FAST) {
    process.stdout.write(`${s}\n`);
    return;
  }
  for (const ch of s) {
    process.stdout.write(ch);
    if (ch !== " ") await sleep(perChar);
  }
  process.stdout.write("\n");
}

const inbound = (s: string) => type(`\n${C.dim}   ${FROM} >${C.off} `, s, 22);

/** Bot messages arrive as a block, then land line by line -- like a phone. */
async function bot(s: string): Promise<void> {
  process.stdout.write(`${C.blue}   Parallax >${C.off} `);
  const lines = s.split("\n");
  for (const [i, line] of lines.entries()) {
    process.stdout.write(`${i === 0 ? "" : " ".repeat(14)}${line}\n`);
    await sleep(line.trim() === "" ? 45 : 85);
  }
}

interface HubMessage {
  readonly text: string;
  readonly part: number;
  readonly of: number;
}

/** Every failure here happens in front of an audience, so none of them throw. */
async function hub(
  path: string,
  init?: RequestInit,
): Promise<{ ok: true; body: unknown; ms: number } | { ok: false; why: string }> {
  const started = Date.now();
  try {
    const res = await fetch(`${HUB}${path}`, {
      ...init,
      signal: AbortSignal.timeout(120_000),
    });
    const text = await res.text();
    if (!res.ok) return { ok: false, why: `${path} -> HTTP ${res.status}: ${text.slice(0, 200)}` };
    try {
      return { ok: true, body: JSON.parse(text), ms: Date.now() - started };
    } catch {
      return { ok: false, why: `${path} -> not JSON: ${text.slice(0, 200)}` };
    }
  } catch (e) {
    return { ok: false, why: `${path} -> ${e instanceof Error ? e.message : String(e)}` };
  }
}

function messagesOf(body: unknown): HubMessage[] {
  if (typeof body !== "object" || body === null) return [];
  const raw = (body as { messages?: unknown }).messages;
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((m) =>
    typeof m === "object" && m !== null && typeof (m as HubMessage).text === "string"
      ? [m as HubMessage]
      : [],
  );
}

function died(why: string): never {
  console.log(`\n${C.r}   the hub did not answer${C.off}\n   ${C.dim}${why}${C.off}`);
  console.log(
    `\n   ${C.dim}fall back to ${C.off}bun run demo:whatsapp${C.dim} -- same flow, no network${C.off}\n`,
  );
  process.exit(1);
}

// -------------------------------------------------- 0. is it even the right code
rule("Before anything: is the deployed code the code in the repo?");
process.stdout.write(`${C.dim}   GET ${HUB}/health ...${C.off}`);
const health = await hub("/health");
if (!health.ok) died(health.why);
const commit = String((health.body as { commit?: unknown }).commit ?? "");
clearLine();
console.log(`   commit  ${C.b}${commit}${C.off}   ${C.dim}(${health.ms} ms)${C.off}`);
console.log(
  `   ${C.dim}version is a source constant and the deploy API reports intent; the commit is`,
);
console.log(`   the only field on this response that a stale image cannot fake.${C.off}`);
await sleep(1400);

// -------------------------------------------------- 1. a message arrives
rule("A message arrives");
const threadId = `demo-${commit.slice(0, 7)}-${Math.floor(Date.now() / 1000)}`;
await inbound("hola, quiero simular un cambio de precio antes de aplicarlo");
await sleep(500);

// -------------------------------------------------- 2. the hub reads the context
rule("The hub reads the context and proposes -- nothing has run");
const turn1 = await hub("/api/whatsapp/turn", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ from: FROM, text: "hola, quiero simular un cambio de precio", threadId }),
});
if (!turn1.ok) died(turn1.why);
const proposal = messagesOf(turn1.body);
if (proposal.length === 0) died("the hub returned no messages for the opening turn");
for (const m of proposal) await bot(m.of > 1 ? `(${m.part}/${m.of})\n${m.text}` : m.text);

/** The blocking questions are numbered in the message the human just received. */
const blocking = (
  proposal
    .map((m) => m.text)
    .join("\n")
    .match(/^\s*\d+\.\s/gm) ?? []
).length;
await sleep(900);

// -------------------------------------------------- 3. the human accepts
rule("The human answers and accepts, on their phone");
const reply = `${Array.from({ length: blocking }, (_, i) => `${i + 1}. unidades`).join("\n")}\nsí, dale`;
await inbound(reply.split("\n").join(" / "));
await sleep(400);

const turn2 = await hub("/api/whatsapp/turn", {
  method: "POST",
  headers: { "content-type": "application/json" },
  body: JSON.stringify({ from: FROM, text: reply, threadId }),
});
if (!turn2.ok) died(turn2.why);
const answered = messagesOf(turn2.body);
if (answered.length === 0) died("the hub returned no messages for the accept turn");
for (const m of answered) await bot(m.of > 1 ? `(${m.part}/${m.of})\n${m.text}` : m.text);

// -------------------------------------------------- 4. the link, once it resolves
rule("The receipt, checked before it is handed over");
const receiptUrl = (answered
  .map((m) => m.text)
  .join("\n")
  .match(/https?:\/\/\S+\/r\/[a-f0-9]+/) ?? [])[0];
if (receiptUrl === undefined) died("no receipt URL came back on the accept turn");

process.stdout.write(`${C.dim}   GET ${receiptUrl} ...${C.off}`);
let status = 0;
let bytes = 0;
try {
  const res = await fetch(receiptUrl, { signal: AbortSignal.timeout(60_000) });
  status = res.status;
  bytes = (await res.text()).length;
} catch (e) {
  died(`receipt fetch failed: ${e instanceof Error ? e.message : String(e)}`);
}
clearLine();

if (status !== 200 || bytes === 0) {
  console.log(
    `   ${C.r}HTTP ${status}, ${bytes} bytes -- not naming a link that does not serve${C.off}\n`,
  );
  process.exit(1);
}
console.log(`   ${C.g}HTTP 200${C.off}  ${bytes} bytes  ${C.dim}served, not asserted${C.off}`);
await sleep(1600);
await bot(`listo. el recibo: ${receiptUrl}`);
console.log(
  `\n   ${C.dim}Every value on it is typed observed or simulated, and the trace hash re-runs it.${C.off}\n`,
);
