/**
 * Capture a real run of the deployed hub into `content.json`, so the recorded
 * walkthrough is built from responses a server actually sent. A hand-typed
 * script would drift from the product the moment either changed, and a video
 * that shows something the running system does not is worse than no video.
 *
 * Run with: bun run scripts/video/capture.ts
 */
import { writeFileSync } from "node:fs";
import { join } from "node:path";

const HUB = (process.env.PARALLAX_HUB ?? "https://parallax-hub.onrender.com").replace(/\/+$/, "");
const FROM = "+57 301 775 8620";

async function post(path: string, body: unknown): Promise<Record<string, unknown>> {
  const res = await fetch(`${HUB}${path}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
    signal: AbortSignal.timeout(120_000),
  });
  if (!res.ok) throw new Error(`${path} -> HTTP ${res.status}`);
  return (await res.json()) as Record<string, unknown>;
}

function texts(body: Record<string, unknown>): string[] {
  const raw = body.messages;
  if (!Array.isArray(raw)) throw new Error("no messages in response");
  return raw.map((m) => String((m as { text: string }).text));
}

const healthRes = await fetch(`${HUB}/health`, { signal: AbortSignal.timeout(120_000) });
const health = (await healthRes.json()) as { commit?: string };
const commit = String(health.commit ?? "");
if (commit === "") throw new Error("/health did not report a commit");

const threadId = `video-${Date.now()}`;
const openingText = "hola, quiero simular un cambio de precio antes de aplicarlo";
const proposal = texts(
  await post("/api/whatsapp/turn", { from: FROM, text: openingText, threadId }),
);

const blocking = (proposal.join("\n").match(/^\s*\d+\.\s/gm) ?? []).length;
const acceptText = `${Array.from({ length: blocking }, (_, i) => `${i + 1}. unidades`).join("\n")}\nsí, dale`;
const result = texts(await post("/api/whatsapp/turn", { from: FROM, text: acceptText, threadId }));

const receiptUrl = (result.join("\n").match(/https?:\/\/\S+\/r\/[a-f0-9]+/) ?? [])[0];
if (receiptUrl === undefined) throw new Error("no receipt URL came back");

// Name nothing the video cannot show being served.
const receiptRes = await fetch(receiptUrl, { signal: AbortSignal.timeout(60_000) });
const receiptBody = await receiptRes.text();
if (receiptRes.status !== 200 || receiptBody.length === 0) {
  throw new Error(`receipt did not serve: HTTP ${receiptRes.status}, ${receiptBody.length} bytes`);
}

const content = {
  capturedAt: new Date().toISOString(),
  hub: HUB,
  commit,
  from: FROM,
  openingText,
  proposal,
  acceptText,
  result,
  receiptUrl,
  receiptStatus: receiptRes.status,
  receiptBytes: receiptBody.length,
};

const out = join(import.meta.dir, "content.json");
writeFileSync(out, `${JSON.stringify(content, null, 2)}\n`);
console.log(`captured -> ${out}`);
console.log(`  commit  ${commit}`);
console.log(`  receipt ${receiptUrl}  HTTP ${receiptRes.status}, ${receiptBody.length} bytes`);
