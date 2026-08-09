// Broomva × the AI SDK · the wire contract.
// Data structures follow the Vercel AI SDK UIMessage shape (v5/v6):
// a message is { id, role, metadata, parts[] } where parts are
//   text · reasoning · tool-NAME · data-NAME
// and streaming follows the UI Message Stream Protocol · SSE chunks
// (start, text-start/delta/end, reasoning-*, tool-input-*,
// tool-output-available, data-*, finish) so any backend that speaks it
// plugs straight into this UI: streamText().toUIMessageStreamResponse()
// for claude/openai, or a custom ChatTransport for the agentic harness
// (x-vercel-ai-ui-message-stream: v1).
//
// Our gen-UI is data parts: the tick receipt is data-tick (id "tick-log",
// same id replaces → the card updates in place), the gate stopgaps are
// data-gate parts reconciled by id across the transcript.

const bvSleep = (ms) => new Promise((r) => setTimeout(r, ms));
let bvUidN = 0;
const bvUid = (p) => p + "_" + Date.now().toString(36) + (bvUidN++);

// Wall-clock label for a user turn · "Jun 14 · 1:23 PM". Stamped on every
// input so the conversation minimap can show when each one happened.
function bvFmtClock(ts) {
  const d = new Date(ts);
  const mon = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][d.getMonth()];
  let h = d.getHours();
  const ap = h < 12 ? "AM" : "PM";
  h = h % 12; if (h === 0) h = 12;
  const m = String(d.getMinutes()).padStart(2, "0");
  return mon + " " + d.getDate() + " · " + h + ":" + m + " " + ap;
}

// ── Seed state · the maestro session, as UIMessages ──────────────────────
const MCC_ML_GATE = [
  {
    id: "g1", kind: "gate",
    title: "Persist run transcripts on the Run record",
    meta: "ran 2h 14m unsupervised · judge passed · 14 tests",
    ask: "Approve the branch and tonight's phase 2 builds on it.",
    look: [
      ["changed", "run/7c2f1a · +412 −38 across 9 files"],
      ["decided", "transcripts persist on the Run record · replay covered by 14 tests"],
      ["asks", "merge the branch; tonight's phase 2 builds on it"],
    ],
    hint: "a 90-second look",
    actions: [["Approve", "primary"], ["Send back", "secondary"]],
    t: "12m",
  },
  {
    id: "g2", kind: "warn",
    title: "Linear import needs an API scope",
    meta: "worker paused 41m · 3 queued items wait on it",
    ask: "Grant read access to Linear cycles, or park the import.",
    look: [
      ["changed", "nothing merged · the worker paused itself at Linear auth"],
      ["decided", "it won't retry without a granted scope"],
      ["asks", "grant read on cycles, or park the import"],
    ],
    hint: "unblocks 1 worker",
    actions: [["Grant access", "primary"], ["Park it", "secondary"]],
    t: "41m",
  },
];

const BV_TICK_ROWS = [
  { g: "▷", cause: "interval 15m", causeColor: "var(--bv-gray-500)", label: "No-op · at capacity (2/2 worktrees)", t: "32m" },
  { g: "▶", cause: "worker returned", causeColor: "var(--bv-blue)", label: "run/7c2f1a judged clean → queued to your gate", t: "12m" },
  { g: "▷", cause: "interval 15m", causeColor: "var(--bv-gray-500)", label: "Holding · 2 decisions open at your gate", t: "2m" },
];

const BV_SEED_MESSAGES = [
  {
    id: "seed-1", role: "assistant", metadata: { model: "broomva/maestro-loop" },
    parts: [
      { type: "text", state: "done", text: "Morning. The loop ran all night: the digest went out at 02:00 and genesis is still live on the phase machine. Two decisions wait below; the second frees three queued items." },
      { type: "data-tick", id: "tick-log", data: { rows: BV_TICK_ROWS } },
      { type: "data-gate", id: "g1", data: MCC_ML_GATE[0] },
      { type: "data-gate", id: "g2", data: MCC_ML_GATE[1] },
    ],
  },
  {
    id: "seed-2", role: "user", metadata: { time: "Jun 14 · 9:02 AM" },
    parts: [{ type: "text", text: "what's blocking the relay handoff?" }],
  },
  {
    id: "seed-3", role: "assistant", metadata: { model: "anthropic/claude-sonnet-4.6" },
    parts: [
      { type: "text", state: "done", text: "Nothing but capacity: it's third in the queue. Clear the Linear scope below and I'll park the import, which frees a worktree on the next tick; the relay dispatches right after." },
    ],
  },
  {
    id: "seed-4", role: "user", metadata: { time: "Jun 14 · 9:05 AM" },
    parts: [{ type: "text", text: "park the import for now and clear the Linear scope" }],
  },
  {
    id: "seed-5", role: "assistant", metadata: { model: "anthropic/claude-sonnet-4.6" },
    parts: [
      { type: "text", state: "done", text: "Done. Import parked, scope released. A worktree frees on the next tick (≈13m) and the relay handoff moves to first in line. I'll dispatch it the moment capacity opens." },
    ],
  },
  {
    id: "seed-6", role: "user", metadata: { time: "Jun 14 · 9:14 AM" },
    parts: [{ type: "text", text: "show me what genesis touched overnight" }],
  },
  {
    id: "seed-7", role: "assistant", metadata: { model: "broomva/maestro-loop" },
    parts: [
      { type: "text", state: "done", text: "Genesis ran 6h 24m unsupervised on the projection layer. It reduced the NDJSON stream into the phase machine, landed 9 green tests, and opened run/4fd028 with the diff staged. No human gate tripped; it stayed inside the budget you set." },
    ],
  },
  {
    id: "seed-8", role: "user", metadata: { time: "Jun 14 · 9:21 AM" },
    parts: [{ type: "text", text: "approve the transcripts gate, phase 2 can build on it" }],
  },
  {
    id: "seed-9", role: "assistant", metadata: { model: "broomva/maestro-loop" },
    parts: [
      { type: "text", state: "done", text: "Approved. The branch is merged to the Run record and phase 2 is queued behind the relay. That clears one of your two decisions; one left." },
    ],
  },
  {
    id: "seed-10", role: "user", metadata: { time: "Jun 14 · 9:36 AM" },
    parts: [{ type: "text", text: "why did run/7c2f1a stall before the judge last night?" }],
  },
  {
    id: "seed-11", role: "assistant", metadata: { model: "anthropic/claude-sonnet-4.6" },
    parts: [
      { type: "reasoning", state: "done", text: "pulling the run log · it halted at the judge step, not the build" },
      { type: "text", state: "done", text: "It didn't fail; it blocked on capacity. Both worktrees were busy when the judge wanted a clean checkout, so it parked itself rather than evict a running peer. The build artifacts are intact; it only needs a slot." },
    ],
  },
  {
    id: "seed-12", role: "user", metadata: { time: "Jun 14 · 9:44 AM" },
    parts: [{ type: "text", text: "rerun it with capacity bumped to 3 worktrees" }],
  },
  {
    id: "seed-13", role: "assistant", metadata: { model: "broomva/maestro-loop" },
    parts: [
      { type: "text", state: "done", text: "Capacity raised to 3 for this layer. run/7c2f1a is re-dispatched into the new slot and the relay takes the one after. Both are live now; receipts will land here as they pass the judge." },
    ],
  },
  {
    id: "seed-14", role: "user", metadata: { time: "Jun 14 · 9:58 AM" },
    parts: [{ type: "text", text: "good. ping me the moment the relay lands" }],
  },
  {
    id: "seed-15", role: "assistant", metadata: { model: "broomva/maestro-loop" },
    parts: [
      { type: "text", state: "done", text: "Will do. I'll surface it at your gate the instant the judge clears it, and hold everything downstream until you've seen it." },
    ],
  },
];

// A long-running session · for stress-testing the conversation minimap at the
// density real work produces. ~100 user inputs interleaved with short maestro
// replies, timestamped across two days.
function bvMakeStressSeed(count = 100) {
  const userPool = [
    "bump the timeout and retry", "show me the diff for that run", "why is it still queued?",
    "approve it", "send that one back", "what's the test status?", "rerun with 3 worktrees",
    "park the import for now", "ping me when it lands", "summarize the last hour",
    "who's holding the lock?", "restart the sidecar", "good, continue", "pause everything for a sec",
    "what changed since the digest?", "roll back the last commit", "split this into two runs",
    "raise the budget for hawthorne", "is genesis still live?", "tail the run log for me",
  ];
  const asstPool = [
    "On it. Dispatched into the next free slot.", "Done. Receipt's on the Run record.",
    "It's third in line; capacity is 2/2.", "Approved and merged.",
    "Sent back with notes for the worker.", "14 tests green, judge passed.",
    "Capacity raised; both are live now.", "Import parked; a worktree frees next tick.",
    "Will surface it at your gate the moment it clears.", "Last hour: 3 runs, 2 clean, 1 awaiting you.",
    "run/7c2f1a holds it; it'll release on finish.", "Sidecar restarted · PID 14831.",
    "Continuing where we left off.", "Paused. Nothing new will dispatch.",
    "Genesis is live on the projection layer.", "Rolled back; the branch is clean again.",
  ];
  const out = [{
    id: "stress-0", role: "assistant", metadata: { model: "broomva/maestro-loop" },
    parts: [{ type: "text", state: "done", text: "Picking up the long-running session. The overnight digest is in and the loop is warm. Steer away; everything lands here." }],
  }];
  let ts = new Date(2026, 5, 12, 8, 12, 0).getTime();
  for (let i = 0; i < count; i++) {
    ts += (3 + (i * 7) % 23) * 60000;
    out.push({
      id: "su" + i, role: "user", metadata: { time: bvFmtClock(ts) },
      parts: [{ type: "text", text: userPool[i % userPool.length] }],
    });
    out.push({
      id: "sa" + i, role: "assistant",
      metadata: { model: i % 2 ? "anthropic/claude-sonnet-4.6" : "broomva/maestro-loop" },
      parts: [{ type: "text", state: "done", text: asstPool[i % asstPool.length] }],
    });
  }
  return out;
}
const BV_SEED_STRESS = bvMakeStressSeed(100);
const BV_SEED_EXTREME = bvMakeStressSeed(600);

// ── The reducer · UIMessageChunk → UIMessage[] ────────────────────────────
function bvApplyChunk(prev, chunk) {
  const msgs = prev.slice();
  const touch = (i) => {
    const m = { ...msgs[i], parts: msgs[i].parts.slice() };
    msgs[i] = m;
    return m;
  };
  const li = msgs.length - 1;
  const t = chunk.type;

  if (t === "start") {
    msgs.push({ id: chunk.messageId || bvUid("msg"), role: "assistant", metadata: chunk.messageMetadata, parts: [] });
    return msgs;
  }
  if (t === "finish" || t === "abort" || t === "start-step" || t === "finish-step") return msgs;

  if (t.startsWith("data-")) {
    if (chunk.transient) return msgs; // surfaced via onData only · never persisted
    for (let i = 0; i < msgs.length; i++) {
      const j = msgs[i].parts.findIndex((p) => p.type === t && chunk.id != null && p.id === chunk.id);
      if (j >= 0) {
        const m = touch(i);
        m.parts[j] = { ...m.parts[j], data: chunk.data };
        return msgs;
      }
    }
    const m = touch(li);
    m.parts.push({ type: t, id: chunk.id, data: chunk.data });
    return msgs;
  }

  const m = touch(li);
  const findBlock = (type, id) => m.parts.findIndex((p) => p.type === type && p.id === id);
  const findCall = (id) => m.parts.findIndex((p) => p.toolCallId === id);

  if (t === "text-start") m.parts.push({ type: "text", id: chunk.id, text: "", state: "streaming" });
  else if (t === "text-delta") {
    const j = findBlock("text", chunk.id);
    if (j >= 0) m.parts[j] = { ...m.parts[j], text: m.parts[j].text + chunk.delta };
  } else if (t === "text-end") {
    const j = findBlock("text", chunk.id);
    if (j >= 0) m.parts[j] = { ...m.parts[j], state: "done" };
  } else if (t === "reasoning-start") m.parts.push({ type: "reasoning", id: chunk.id, text: "", state: "streaming" });
  else if (t === "reasoning-delta") {
    const j = findBlock("reasoning", chunk.id);
    if (j >= 0) m.parts[j] = { ...m.parts[j], text: m.parts[j].text + chunk.delta };
  } else if (t === "reasoning-end") {
    const j = findBlock("reasoning", chunk.id);
    if (j >= 0) m.parts[j] = { ...m.parts[j], state: "done" };
  } else if (t === "tool-input-start") {
    m.parts.push({ type: "tool-" + chunk.toolName, toolCallId: chunk.toolCallId, state: "input-streaming", inputText: "" });
  } else if (t === "tool-input-delta") {
    const j = findCall(chunk.toolCallId);
    if (j >= 0) m.parts[j] = { ...m.parts[j], inputText: (m.parts[j].inputText || "") + chunk.inputTextDelta };
  } else if (t === "tool-input-available") {
    const j = findCall(chunk.toolCallId);
    if (j >= 0) m.parts[j] = { ...m.parts[j], state: "input-available", input: chunk.input };
  } else if (t === "tool-output-available") {
    const j = findCall(chunk.toolCallId);
    if (j >= 0) m.parts[j] = { ...m.parts[j], state: "output-available", output: chunk.output };
  } else if (t === "error") m.parts.push({ type: "error", errorText: chunk.errorText });

  return msgs;
}

// Selectors · derived UI state from the transcript.
function bvSelectGate(messages) {
  const map = new Map();
  for (const m of messages)
    for (const p of m.parts)
      if (p.type === "data-gate") map.set(p.id, p.data);
  return [...map.values()].filter((g) => g && !g.resolved);
}

function bvLastUserText(messages) {
  for (let i = messages.length - 1; i >= 0; i--)
    if (messages[i].role === "user")
      return messages[i].parts.filter((p) => p.type === "text").map((p) => p.text).join(" ");
  return "";
}

// ── Transports · three engines, one chunk protocol ────────────────────────
async function* bvStreamTextBlock(text, delay = 26) {
  const id = bvUid("txt");
  yield { type: "text-start", id };
  for (const w of text.match(/\S+\s*/g) || []) {
    await bvSleep(delay);
    yield { type: "text-delta", id, delta: w };
  }
  yield { type: "text-end", id };
}

class BvChatTransport {
  constructor({ provider, model }) { this.provider = provider; this.model = model; }
  async *stream() { throw new Error("transport must implement stream(messages)"); }
}

class BvAnthropicTransport extends BvChatTransport {
  async *stream(messages) {
    const q = bvLastUserText(messages);
    yield { type: "start", messageId: bvUid("msg"), messageMetadata: { model: this.model } };
    await bvSleep(220);
    yield* bvStreamTextBlock("Noted. I'm holding \u201C" + q + "\u201D against the queue. Nothing dispatches without a free worktree, and your two gate decisions still come first; clear them and the loop picks this up on the very next tick.");
    yield { type: "finish" };
  }
}

class BvOpenAITransport extends BvChatTransport {
  async *stream(messages) {
    const q = bvLastUserText(messages);
    yield { type: "start", messageId: bvUid("msg"), messageMetadata: { model: this.model } };
    const rid = bvUid("r");
    yield { type: "reasoning-start", id: rid };
    for (const w of "checking queue order and the two open stopgaps before committing".match(/\S+\s*/g)) {
      await bvSleep(22);
      yield { type: "reasoning-delta", id: rid, delta: w };
    }
    yield { type: "reasoning-end", id: rid };
    yield* bvStreamTextBlock("Understood. \u201C" + q + "\u201D is registered. Current blockers are your two gate decisions; once cleared, capacity frees on the next tick and this proceeds without supervision.");
    yield { type: "finish" };
  }
}

class BvHarnessTransport extends BvChatTransport {
  async *stream(messages) {
    const q = bvLastUserText(messages);
    yield { type: "start", messageId: bvUid("msg"), messageMetadata: { model: this.model } };
    const rid = bvUid("r");
    yield { type: "reasoning-start", id: rid };
    for (const w of "reading the queue · 2 decisions pending · capacity 2/2 · next tick 13m".match(/\S+\s*/g)) {
      await bvSleep(24);
      yield { type: "reasoning-delta", id: rid, delta: w };
    }
    yield { type: "reasoning-end", id: rid };
    const callId = bvUid("call");
    yield { type: "tool-input-start", toolCallId: callId, toolName: "dispatch" };
    await bvSleep(160);
    yield { type: "tool-input-delta", toolCallId: callId, inputTextDelta: '{"goal":"' + q.slice(0, 36) + '…"' };
    await bvSleep(200);
    yield { type: "tool-input-available", toolCallId: callId, toolName: "dispatch", input: { goal: q, scope: "hawthorne-core", budget: "inherit" } };
    await bvSleep(340);
    yield { type: "tool-output-available", toolCallId: callId, output: { queued: true, position: 3, reason: "capacity 2/2" } };
    await bvSleep(180);
    yield {
      type: "data-tick", id: "tick-log",
      data: { rows: [...BV_TICK_ROWS, { g: "▶", cause: "operator message", causeColor: "var(--bv-blue)", label: "Routed to the queue · position 3, re-evaluated next tick", t: "now" }] },
    };
    yield* bvStreamTextBlock("Routed. It holds position 3; the tick receipt above updated in place. Clear the Linear scope and a worktree frees; the loop re-evaluates in 13m either way.");
    yield { type: "finish" };
  }
}

const BV_PROVIDERS = [
  { id: "anthropic", label: "claude 4.6", model: "anthropic/claude-sonnet-4.6", pkg: "@ai-sdk/anthropic" },
  { id: "openai", label: "gpt-5.2", model: "openai/gpt-5.2", pkg: "@ai-sdk/openai" },
  { id: "harness", label: "maestro harness", model: "broomva/maestro-loop", pkg: "custom ChatTransport" },
];

// ── The effort architecture · three layers, so new providers and gateways
// slot in without UI changes:
//   1. BV_EFFORT_SCALE · ONE canonical ordered scale: the union of every
//      provider's stops (OpenAI's none/minimal … Anthropic's max).
//      Providers snap onto a subset; the UI renders whatever a model declares.
//   2. BV_MODEL_CATALOG · flat, gateway-shaped entries (one per model id,
//      the shape OpenRouter /models or the Vercel AI Gateway returns):
//      provider, reasoning capabilities (supported efforts + default).
//      Swapping in a live gateway = replacing this array with a fetch.
//   3. BV_HARNESSES · the agentic shells. A harness FILTERS the catalog
//      (model-agnostic loops take everything; vendor harnesses take their
//      provider) and may add PRESETS · harness modes like ultracode that
//      compose an effort with extra behavior. Presets are not API effort
//      levels; they require one (ultracode ⇒ xhigh + workflows), so they
//      only surface when the selected model supports that stop.
const BV_EFFORT_SCALE = [
  { id: "none",    label: "None",    bars: 0, ratio: 0,    desc: "answer directly · no reasoning" },
  { id: "minimal", label: "Minimal", bars: 1, ratio: 0.1,  desc: "fastest useful answer" },
  { id: "low",     label: "Low",     bars: 2, ratio: 0.2,  desc: "light reasoning" },
  { id: "medium",  label: "Medium",  bars: 3, ratio: 0.5,  desc: "balanced depth" },
  { id: "high",    label: "High",    bars: 4, ratio: 0.8,  desc: "careful · weighs alternatives" },
  { id: "xhigh",   label: "X-High",  bars: 5, ratio: 0.95, desc: "extended exploration" },
  { id: "max",     label: "Max",     bars: 6, ratio: 1,    desc: "no constraint on thinking" },
];
const bvEffort = (id) => BV_EFFORT_SCALE.find((e) => e.id === id);
// Tolerance: a live gateway may declare a stop the scale doesn't know yet.
// Render it instead of dropping it · flagged, top bars, logged once · so a
// new provider ladder degrades gracefully until the scale is updated.
const bvUnknownEfforts = {};
function bvUnknownEffort(id) {
  if (!bvUnknownEfforts[id]) {
    console.warn('[broomva] unknown effort stop "' + id + '" · not in the canonical scale; rendering as provider-specific');
    bvUnknownEfforts[id] = { id, label: id, bars: 6, ratio: 1, desc: "provider-specific stop · append to the canonical scale", unknown: true };
  }
  return bvUnknownEfforts[id];
}

// How each provider serializes a canonical stop on the wire.
const BV_PROVIDER_INFO = {
  anthropic: { label: "Anthropic",            wire: (effort) => ({ effort }) },
  openai:    { label: "OpenAI",               wire: (effort) => ({ reasoning: { effort } }) },
  google:    { label: "Google · via gateway", wire: (effort) => ({ reasoning: { effort } }) },
  moonshot:  { label: "Moonshot · via gateway", wire: (effort) => ({ reasoning: { effort } }) },
  deepseek:  { label: "DeepSeek · via gateway", wire: (effort) => ({ reasoning: { effort } }) },
};

const BV_MODEL_CATALOG = [
  // Anthropic · effort: low–max; xhigh only on Opus 4.7+; default high
  { id: "anthropic/claude-opus-4.8", label: "claude opus 4.8", provider: "anthropic", glyph: "spark", isNew: true,
    reasoning: { efforts: ["low", "medium", "high", "xhigh", "max"], default: "high" } },
  { id: "anthropic/claude-sonnet-4.6", label: "claude 4.6", provider: "anthropic", glyph: "spark",
    reasoning: { efforts: ["low", "medium", "high", "max"], default: "high" } },
  { id: "anthropic/claude-sonnet-4.6-1m", label: "claude 4.6 · 1M", provider: "anthropic", glyph: "spark",
    reasoning: { efforts: ["low", "medium", "high", "max"], default: "high" } },
  { id: "anthropic/claude-haiku-4.5", label: "claude haiku 4.5", provider: "anthropic", glyph: "spark",
    reasoning: { efforts: ["low", "medium", "high"], default: "medium" } },
  // OpenAI · reasoning.effort: none–high; xhigh on codex-max; defaults vary
  { id: "openai/gpt-5.2", label: "gpt-5.2", provider: "openai", glyph: "ring",
    reasoning: { efforts: ["none", "low", "medium", "high"], default: "medium" } },
  { id: "openai/gpt-5.1-codex-max", label: "gpt-5.1 codex max", provider: "openai", glyph: "ring",
    reasoning: { efforts: ["none", "low", "medium", "high", "xhigh"], default: "medium" } },
  { id: "openai/gpt-5.2-mini", label: "gpt-5.2 mini", provider: "openai", glyph: "ring",
    reasoning: { efforts: ["none", "minimal", "low", "medium"], default: "low" } },
  // Via the gateway · same shape, any provider it lists
  { id: "google/gemini-3.1-pro", label: "gemini 3.1 pro", provider: "google", glyph: "orbit",
    reasoning: { efforts: ["low", "medium", "high"], default: "medium" } },
  { id: "moonshotai/kimi-k2.6", label: "kimi k2.6", provider: "moonshot", glyph: "orbit",
    reasoning: { efforts: ["minimal", "low", "medium", "high", "xhigh"], default: "medium" } },
  // Budget-wire · no native effort param: the stop converts to a
  // thinking-token budget via the scale's ratios (gateway normalization).
  { id: "deepseek/deepseek-r1", label: "deepseek r1", provider: "deepseek", glyph: "orbit",
    reasoning: { efforts: ["minimal", "low", "medium", "high"], default: "medium", wire: "budget", budget: { min: 1024, max: 32768 } } },
];

const BV_HARNESSES = [
  { id: "maestro", label: "maestro", glyph: "tide", transport: "harness", def: true,
    desc: "the loop · dispatch · judge · gate",
    models: "*", // model-agnostic: the whole catalog, via the gateway
    defaultModel: "anthropic/claude-opus-4.8",
    presets: [] },
  { id: "claude-code", label: "claude code", glyph: "spark", transport: "anthropic",
    desc: "Anthropic's coding agent",
    models: { provider: "anthropic" },
    defaultModel: "anthropic/claude-opus-4.8",
    presets: [
      { id: "ultracode", label: "ultracode", sub: "xhigh + workflows", effort: "xhigh",
        desc: "sends xhigh, plus auto workflow orchestration" },
    ] },
  { id: "codex", label: "codex", glyph: "ring", transport: "openai",
    desc: "OpenAI's coding agent",
    models: { provider: "openai" },
    defaultModel: "openai/gpt-5.2",
    presets: [] },
];

const bvHarness = (id) => BV_HARNESSES.find((h) => h.id === id) || BV_HARNESSES[0];
// Harness model filters are DECLARATIVE ("*" or a field-match object), so
// harness configs can live in a DB or come down the wire · compiled here.
const bvPickFn = (spec) => (spec === "*" || spec == null)
  ? () => true
  : (m) => Object.entries(spec).every(([k, v]) => m[k] === v);
const bvHarnessModels = (h) => BV_MODEL_CATALOG.filter(bvPickFn(h.models));
const bvHarnessModel = (h, id) => {
  const list = bvHarnessModels(h);
  return list.find((m) => m.id === id) || list.find((m) => m.id === h.defaultModel) || list[0];
};
const bvModelEfforts = (m) => m.reasoning.efforts.map((id) => bvEffort(id) || bvUnknownEffort(id));
const bvPresets = (h, m) => (h.presets || []).filter((p) => m.reasoning.efforts.includes(p.effort));

// Resolve a requested effort id (scale stop OR harness preset) against the
// current harness+model pair · the clamping cascade. Always returns
// something the pair supports, falling back to the model's own default.
function bvResolveEffort(h, m, effortId) {
  const p = bvPresets(h, m).find((x) => x.id === effortId);
  if (p) return { kind: "preset", preset: p, effort: bvEffort(p.effort) };
  const supported = bvModelEfforts(m);
  const e = supported.find((x) => x.id === effortId);
  if (e) return { kind: "effort", effort: e };
  // Fallback order: the harness's default override (if this model supports
  // it) → the model's own declared default → the model's first stop.
  const fb = (h.defaultEffort && supported.find((x) => x.id === h.defaultEffort))
    || supported.find((x) => x.id === m.reasoning.default)
    || supported[0];
  return { kind: "effort", effort: fb };
}
const bvSelEffortId = (r) => (r.kind === "preset" ? r.preset.id : r.effort.id);
// What actually goes on the wire for a selection. Budget-wire models have
// no native effort param: the stop converts to a thinking-token budget via
// its ratio (the same normalization gateways apply), clamped to the
// model's declared budget range. maxTokens is the request's output cap.
function bvWireEffort(m, sel, maxTokens = 32000) {
  const r = m.reasoning;
  if (r.wire === "budget") {
    if (sel.effort.ratio === 0) return { reasoning: { enabled: false } };
    const n = Math.round(maxTokens * sel.effort.ratio);
    return { reasoning: { max_tokens: Math.max(r.budget.min, Math.min(n, r.budget.max)) } };
  }
  return (BV_PROVIDER_INFO[m.provider] || BV_PROVIDER_INFO.anthropic).wire(sel.effort.id);
}

const bvTransportCache = {};
function bvGetTransport(harnessId, modelId) {
  const h = bvHarness(harnessId);
  const m = bvHarnessModel(h, modelId);
  const key = h.id + "/" + m.id;
  if (!bvTransportCache[key]) {
    const Cls = h.transport === "harness" ? BvHarnessTransport
      : m.provider === "anthropic" ? BvAnthropicTransport
      : BvOpenAITransport;
    bvTransportCache[key] = new Cls({ provider: m.provider, model: m.id });
  }
  return bvTransportCache[key];
}

const BV_TRANSPORTS = {
  anthropic: new BvAnthropicTransport({ provider: "anthropic", model: "anthropic/claude-sonnet-4.6" }),
  openai: new BvOpenAITransport({ provider: "openai", model: "openai/gpt-5.2" }),
  harness: new BvHarnessTransport({ provider: "harness", model: "broomva/maestro-loop" }),
};

// ── useBvChat · useChat-shaped state over any transport ──────────────────
function useBvChat({ transport, initialMessages, onData }) {
  const [messages, setMessages] = React.useState(initialMessages || []);
  const [status, setStatus] = React.useState("ready");
  const msgsRef = React.useRef(messages);
  msgsRef.current = messages;
  const tRef = React.useRef(transport);
  tRef.current = transport;
  const onDataRef = React.useRef(onData);
  onDataRef.current = onData;

  const sendMessage = React.useCallback(async ({ text }) => {
    if (!text || !text.trim()) return;
    const user = { id: bvUid("msg"), role: "user", metadata: { time: bvFmtClock(Date.now()) }, parts: [{ type: "text", text: text.trim() }] };
    setMessages((m) => [...m, user]);
    setStatus("submitted");
    try {
      for await (const chunk of tRef.current.stream([...msgsRef.current, user])) {
        if (chunk.type.startsWith("data-") && chunk.transient) {
          if (onDataRef.current) onDataRef.current(chunk);
          continue;
        }
        setStatus("streaming");
        setMessages((m) => bvApplyChunk(m, chunk));
      }
    } finally {
      setStatus("ready");
    }
  }, []);

  return { messages, status, sendMessage };
}

// ── The renderer · part type → Broomva component ─────────────────────────
function MccToolPart({ part }) {
  const name = part.type.slice(5);
  const state = part.state;
  return (
    <div className="mcc-toolpart" data-screen-label={"Tool part · " + name}>
      <div className="mcc-toolpart-head">
        <McIcon size={13}><rect width="18" height="18" x="3" y="3" rx="2"></rect><path d="m8 12 2 2 4-4"></path></McIcon>
        <b>{name}</b>
        <span className={"mcc-toolpart-state" + (state === "output-available" ? " is-done" : "")}>
          {state === "output-available" ? "done" : state === "input-available" ? "running" : "streaming input…"}
        </span>
      </div>
      {part.input
        ? <code className="mcc-toolpart-line">input&nbsp;&nbsp;{JSON.stringify(part.input)}</code>
        : part.inputText
          ? <code className="mcc-toolpart-line">input&nbsp;&nbsp;{part.inputText}</code>
          : null}
      {part.output && <code className="mcc-toolpart-line">output&nbsp;{JSON.stringify(part.output)}</code>}
    </div>
  );
}

function MccMessage({ msg }) {
  if (msg.role === "user") {
    return (
      <div className="bv-msg bv-msg--user" data-bv-user="1"
        data-bv-time={(msg.metadata && msg.metadata.time) || ""}>
        {msg.parts.filter((p) => p.type === "text").map((p) => p.text).join("")}
      </div>
    );
  }
  return (
    <>
      {msg.parts.map((p, i) => {
        if (p.type === "text")
          return <div key={i} className={"bv-msg bv-msg--assistant" + (p.state === "streaming" ? " mcc-msg-streaming" : "")}>{p.text}</div>;
        if (p.type === "reasoning")
          return <div key={i} className="mcc-reasoning"><span aria-hidden="true">✻</span><span>{p.text}</span></div>;
        if (p.type === "data-tick")
          return <MccTickCard key={i} rows={p.data.rows} />;
        if (p.type === "error")
          return <div key={i} className="mcc-reasoning"><span aria-hidden="true">!</span><span>{p.errorText}</span></div>;
        if (p.type.startsWith("data-")) return null; // rendered by selectors (gate queue)
        if (p.type.startsWith("tool-")) return <MccToolPart key={i} part={p} />;
        return null;
      })}
    </>
  );
}

// The dispatch menus · three chips, one popover pattern: harness (the
// agentic shell) → model (the LLM beneath it, scoped to the harness) →
// effort (capability-gated by the model). Esc or outside-click closes,
// ✦ marks the default, the check marks the active row.
function MccModelGlyph({ kind, size = 13 }) {
  if (kind === "tide") return <span className="mcc-dot-tide" style={{ width: 12, height: 12 }}></span>;
  if (kind === "ring") return <McIcon size={size}><circle cx="12" cy="12" r="8"></circle><circle cx="12" cy="12" r="2.5"></circle></McIcon>;
  if (kind === "orbit") return <McIcon size={size}><circle cx="12" cy="13" r="7"></circle><circle cx="19" cy="5" r="2"></circle></McIcon>;
  return <IcxSpark size={size} />;
}

function useMccMenu() {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);
  return { open, setOpen, ref };
}

// Popovers anchored to the prompt rail must NOT render inside the composer:
// the composer carries its own backdrop-filter, and a backdrop-filter nested
// inside another one can't sample the page behind it · so the menu's frost
// dies and content leaks through sharp. Portal to <body> so the blur samples
// the real page, and position it (fixed) above the anchoring chip.
function MccPopover({ open, anchorRef, onClose, className, children, ...rest }) {
  const popRef = React.useRef(null);
  const [pos, setPos] = React.useState(null);
  React.useLayoutEffect(() => {
    if (!open) { setPos(null); return; }
    const calc = () => {
      const a = anchorRef.current;
      if (!a) return;
      const r = a.getBoundingClientRect();
      const w = popRef.current ? popRef.current.offsetWidth : 240;
      const maxLeft = window.innerWidth - w - 8;
      const left = Math.max(8, Math.min(r.left, maxLeft));
      setPos({ left: Math.round(left), bottom: Math.round(window.innerHeight - r.top + 8) });
    };
    calc();
    const id = requestAnimationFrame(calc);
    window.addEventListener("resize", calc);
    return () => { cancelAnimationFrame(id); window.removeEventListener("resize", calc); };
  }, [open]);
  React.useEffect(() => {
    if (!open) return;
    const onDown = (e) => {
      if (anchorRef.current && anchorRef.current.contains(e.target)) return;
      if (popRef.current && popRef.current.contains(e.target)) return;
      onClose();
    };
    const onKey = (e) => { if (e.key === "Escape") onClose(); };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  if (!open) return null;
  return ReactDOM.createPortal(
    <div ref={popRef} className={className}
      style={{ position: "fixed", top: "auto", left: pos ? pos.left : -9999,
        bottom: pos ? pos.bottom : 0, visibility: pos ? "visible" : "hidden" }}
      {...rest}>{children}</div>,
    document.body
  );
}

function MccMenuChip({ open, onClick, title, children }) {
  return (
    <button type="button" className="mcc-prompt-chip mcc-prompt-chip--model"
      title={title} aria-expanded={open} aria-haspopup="menu" onClick={onClick}>
      {children}
      <IcxChevDown size={11} className={"mcc-prompt-chev" + (open ? " is-open" : "")} />
    </button>
  );
}

function MccHarnessMenu({ value, onChange }) {
  const { open, setOpen, ref } = useMccMenu();
  const cur = bvHarness(value);
  return (
    <div className="mcc-modelmenu" ref={ref}>
      <MccMenuChip open={open} onClick={() => setOpen(!open)} title={"harness: " + cur.desc}>
        <MccModelGlyph kind={cur.glyph} size={14} />
        <span className="mcc-prompt-chip-label">{cur.label}</span>
      </MccMenuChip>
      <MccPopover open={open} anchorRef={ref} onClose={() => setOpen(false)} className="mcc-mm-pop" role="menu" data-screen-label="Harness picker">
          <div className="mcc-mm-gl">Harness</div>
          {BV_HARNESSES.map((h) => (
            <button key={h.id} type="button" role="menuitemradio" aria-checked={h.id === cur.id}
              className={"mcc-mm-row mcc-mm-row--tall" + (h.id === cur.id ? " is-active" : "")}
              onClick={() => { onChange(h.id); setOpen(false); }}>
              <MccModelGlyph kind={h.glyph} />
              <span className="mcc-mm-body">
                <span className="mcc-mm-name">{h.label}</span>
                <span className="mcc-mm-desc">{h.desc}</span>
              </span>
              {h.def && <span className="mcc-mm-def" title="The default">✦</span>}
              {h.id === cur.id && <IcCheck size={13} className="mcc-mm-check" />}
            </button>
          ))}
      </MccPopover>
    </div>
  );
}

function MccModelMenu({ harness, value, onChange }) {
  const { open, setOpen, ref } = useMccMenu();
  const h = harness || bvHarness();
  const cur = bvHarnessModel(h, value);
  // Group the harness's slice of the catalog by provider.
  const groups = [];
  bvHarnessModels(h).forEach((m) => {
    const label = (BV_PROVIDER_INFO[m.provider] || { label: m.provider }).label;
    let g = groups.find((x) => x.label === label);
    if (!g) groups.push((g = { label, models: [] }));
    g.models.push(m);
  });
  return (
    <div className="mcc-modelmenu" ref={ref}>
      <MccMenuChip open={open} onClick={() => setOpen(!open)} title={cur.id}>
        <MccModelGlyph kind={cur.glyph} size={14} />
        <span className="mcc-prompt-chip-label">{cur.label}</span>
      </MccMenuChip>
      <MccPopover open={open} anchorRef={ref} onClose={() => setOpen(false)} className="mcc-mm-pop" role="menu" data-screen-label="Model picker">
          {groups.map((g) => (
            <div key={g.label} className="mcc-mm-group">
              <div className="mcc-mm-gl">{g.label}</div>
              {g.models.map((m) => (
                <button key={m.id} type="button" role="menuitemradio" aria-checked={m.id === cur.id}
                  className={"mcc-mm-row" + (m.id === cur.id ? " is-active" : "")}
                  title={m.id}
                  onClick={() => { onChange(m.id); setOpen(false); }}>
                  <MccModelGlyph kind={m.glyph} />
                  <span className="mcc-mm-name">{m.label}</span>
                  {m.isNew && <span className="mcc-mm-new">new</span>}
                  {m.id === h.defaultModel && <span className="mcc-mm-def" title="The default">✦</span>}
                  {m.id === cur.id && <IcCheck size={13} className="mcc-mm-check" />}
                </button>
              ))}
            </div>
          ))}
      </MccPopover>
    </div>
  );
}

function MccEffortMenu({ harness, model, value, onChange }) {
  const { open, setOpen, ref } = useMccMenu();
  const h = harness || bvHarness();
  const m = model || bvHarnessModel(h);
  const efforts = bvModelEfforts(m);
  const presets = bvPresets(h, m);
  const sel = bvResolveEffort(h, m, value);
  return (
    <div className="mcc-modelmenu" ref={ref}>
      <MccMenuChip open={open} onClick={() => setOpen(!open)} title={"effort · what " + m.label + " supports"}>
        <MccEffortBars level={sel.effort.bars} />
        <span className="mcc-prompt-chip-label">{sel.kind === "preset" ? sel.preset.label : sel.effort.label}</span>
      </MccMenuChip>
      <MccPopover open={open} anchorRef={ref} onClose={() => setOpen(false)} className="mcc-mm-pop" role="menu" data-screen-label="Effort picker">
          <div className="mcc-mm-group">
            <div className="mcc-mm-gl">Effort · {m.label}</div>
            {efforts.map((e) => (
              <button key={e.id} type="button" role="menuitemradio"
                aria-checked={sel.kind === "effort" && e.id === sel.effort.id}
                className={"mcc-mm-row" + (sel.kind === "effort" && e.id === sel.effort.id ? " is-active" : "")}
                title={e.desc}
                onClick={() => { onChange(e.id); setOpen(false); }}>
                <MccEffortBars level={e.bars} />
                <span className="mcc-mm-name">{e.label}</span>
                {e.id === m.reasoning.default && <span className="mcc-mm-def" title="The model's default">✦</span>}
                {sel.kind === "effort" && e.id === sel.effort.id && <IcCheck size={13} className="mcc-mm-check" />}
              </button>
            ))}
          </div>
          {presets.length > 0 && (
            <div className="mcc-mm-group">
              <div className="mcc-mm-gl">{h.label} modes</div>
              {presets.map((p) => (
                <button key={p.id} type="button" role="menuitemradio"
                  aria-checked={sel.kind === "preset" && p.id === sel.preset.id}
                  className={"mcc-mm-row mcc-mm-row--tall" + (sel.kind === "preset" && p.id === sel.preset.id ? " is-active" : "")}
                  title={p.desc}
                  onClick={() => { onChange(p.id); setOpen(false); }}>
                  <MccEffortBars level={(bvEffort(p.effort) || { bars: 0 }).bars} />
                  <span className="mcc-mm-body">
                    <span className="mcc-mm-name">{p.label}</span>
                    <span className="mcc-mm-desc">{p.sub}</span>
                  </span>
                  {sel.kind === "preset" && p.id === sel.preset.id && <IcCheck size={13} className="mcc-mm-check" />}
                </button>
              ))}
            </div>
          )}
          <div className="mcc-mm-note">
            {m.label} · {efforts[0].label.toLowerCase()}–{efforts[efforts.length - 1].label.toLowerCase()} of the canonical scale
          </div>
      </MccPopover>
    </div>
  );
}

// useMccDispatch · one piece of state for the rail: harness → model →
// effort, re-clamped on every change to what the layer beneath supports.
function useMccDispatch(initial = {}) {
  const [sel, setSel] = React.useState(() => {
    const h = bvHarness(initial.harness);
    const m = bvHarnessModel(h, initial.model);
    return { harness: h.id, model: m.id, effort: bvSelEffortId(bvResolveEffort(h, m, initial.effort || m.reasoning.default)) };
  });
  const setHarness = React.useCallback((id) => setSel((s) => {
    const h = bvHarness(id);
    const m = bvHarnessModel(h, s.model);
    return { harness: h.id, model: m.id, effort: bvSelEffortId(bvResolveEffort(h, m, s.effort)) };
  }), []);
  const setModel = React.useCallback((id) => setSel((s) => {
    const h = bvHarness(s.harness);
    const m = bvHarnessModel(h, id);
    return { ...s, model: m.id, effort: bvSelEffortId(bvResolveEffort(h, m, s.effort)) };
  }), []);
  const setEffort = React.useCallback((id) => setSel((s) => ({ ...s, effort: id })), []);
  return { ...sel, setHarness, setModel, setEffort };
}

function MccDispatchRail({ d, quiet }) {
  const h = bvHarness(d.harness);
  const m = bvHarnessModel(h, d.model);
  // Quiet (the default): the harness is the only choice surfaced · model and
  // effort ride the harness defaults, per "plain over technical". The full
  // rail is a Tweak for people tuning dispatch.
  if (quiet) {
    return <MccHarnessMenu value={h.id} onChange={d.setHarness} />;
  }
  return (
    <>
      <MccHarnessMenu value={h.id} onChange={d.setHarness} />
      <MccModelMenu harness={h} value={m.id} onChange={d.setModel} />
      <MccEffortMenu harness={h} model={m} value={d.effort} onChange={d.setEffort} />
    </>
  );
}

// The self-contained rail · for plates that don't lift the state.
function MccDefaultRail(props) {
  const d = useMccDispatch(props);
  return <MccDispatchRail d={d} quiet={props.rail !== "full"} />;
}

// The provider chip · cycles claude → gpt → harness in the prompt rail.
function MccRailProvider({ value, onChange }) {
  const i = Math.max(0, BV_PROVIDERS.findIndex((p) => p.id === value));
  const cur = BV_PROVIDERS[i];
  const next = BV_PROVIDERS[(i + 1) % BV_PROVIDERS.length];
  return (
    <button type="button" className="mcc-prompt-chip mcc-prompt-chip--model"
      title={cur.model + " · click for " + next.label}
      onClick={() => onChange(next.id)}>
      <IcxSpark size={14} />
      <span className="mcc-prompt-chip-label">{cur.label}</span>
      <IcxChevDown size={11} className="mcc-prompt-chev" />
    </button>
  );
}

Object.assign(window, {
  MCC_ML_GATE, BV_TICK_ROWS, BV_SEED_MESSAGES, BV_SEED_STRESS, BV_SEED_EXTREME,
  bvApplyChunk, bvSelectGate, bvLastUserText, bvUid,
  BvChatTransport, BvAnthropicTransport, BvOpenAITransport, BvHarnessTransport,
  BV_PROVIDERS, BV_TRANSPORTS, BV_EFFORT_SCALE, BV_MODEL_CATALOG, BV_PROVIDER_INFO, BV_HARNESSES,
  bvHarness, bvHarnessModels, bvHarnessModel, bvModelEfforts, bvPresets, bvResolveEffort, bvWireEffort, bvGetTransport,
  useBvChat, MccMessage, MccToolPart, MccRailProvider, MccModelMenu, MccModelGlyph,
  MccHarnessMenu, MccEffortMenu, useMccDispatch, MccDispatchRail, MccDefaultRail,
});
