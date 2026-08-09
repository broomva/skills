/* @ds-bundle: {"format":4,"namespace":"BroomvaDesignSystem_5727d9","components":[{"name":"Avatar","sourcePath":"components/core/Avatar.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"Composer","sourcePath":"components/core/Composer.jsx"},{"name":"DotComet","sourcePath":"components/core/DotComet.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"Input","sourcePath":"components/core/Input.jsx"},{"name":"StatusBadge","sourcePath":"components/core/StatusBadge.jsx"},{"name":"Checkbox","sourcePath":"components/forms/Checkbox.jsx"},{"name":"Field","sourcePath":"components/forms/Field.jsx"},{"name":"Radio","sourcePath":"components/forms/Radio.jsx"},{"name":"Select","sourcePath":"components/forms/Select.jsx"},{"name":"Switch","sourcePath":"components/forms/Switch.jsx"},{"name":"Textarea","sourcePath":"components/forms/Textarea.jsx"},{"name":"CommandPalette","sourcePath":"components/navigation/CommandPalette.jsx"},{"name":"Segmented","sourcePath":"components/navigation/Segmented.jsx"},{"name":"Tabs","sourcePath":"components/navigation/Tabs.jsx"},{"name":"Dialog","sourcePath":"components/overlays/Dialog.jsx"},{"name":"ConfirmDialog","sourcePath":"components/overlays/Dialog.jsx"},{"name":"Menu","sourcePath":"components/overlays/Menu.jsx"},{"name":"MenuItem","sourcePath":"components/overlays/Menu.jsx"},{"name":"MenuDivider","sourcePath":"components/overlays/Menu.jsx"},{"name":"Toast","sourcePath":"components/overlays/Toast.jsx"},{"name":"Tooltip","sourcePath":"components/overlays/Tooltip.jsx"},{"name":"AutonomyScoreboard","sourcePath":"components/work/AutonomyScoreboard.jsx"},{"name":"LifecycleRail","sourcePath":"components/work/LifecycleRail.jsx"},{"name":"Receipt","sourcePath":"components/work/Receipt.jsx"},{"name":"ReceiptRow","sourcePath":"components/work/Receipt.jsx"},{"name":"RunCard","sourcePath":"components/work/RunCard.jsx"},{"name":"Undertow","sourcePath":"components/work/Undertow.jsx"},{"name":"WorkState","sourcePath":"components/work/WorkState.jsx"}],"sourceHashes":{"apps/maestro/AiProtocol.jsx":"f42bd4cb9498","apps/maestro/ConceptAttention.jsx":"6df82a3a7b20","apps/maestro/ConceptFeedback.jsx":"60a0c8d8a707","apps/maestro/ConceptFsTabs.jsx":"0ed168181861","apps/maestro/ConceptHistory.jsx":"a98fbff42ec4","apps/maestro/ConceptKnowledge.jsx":"4424c0217dd5","apps/maestro/ConceptMaestroLoop.jsx":"4c6cfe5761df","apps/maestro/ConceptMcDock.jsx":"a8940eb740ef","apps/maestro/ConceptNavIA.jsx":"4bc559c663a0","apps/maestro/ConceptSettings.jsx":"aa73d93e1b22","apps/maestro/ConceptTreeClick.jsx":"751574716d51","apps/maestro/ConceptUser.jsx":"7ad106e3e152","apps/maestro/KgGraph.jsx":"656bee1e4856","apps/maestro/KnowledgeApp.jsx":"3308ba899c6f","apps/maestro/LiveCommand.jsx":"4f54962688ae","apps/maestro/MaestroApp.jsx":"f7712ba8f672","apps/maestro/MobileShell.jsx":"b6dff7c281e7","apps/maestro/PromptPlate.jsx":"6b6f9b9496dd","apps/maestro/WorkData.jsx":"0b5e7880e900","apps/maestro/WorkDetail.jsx":"6375bdb5900b","apps/maestro/WorkFeed.jsx":"869baa6fc729","apps/maestro/WorkPanel.jsx":"86f88dd4ba4f","apps/maestro/WorkPlanes.jsx":"8cbfbd582f8e","apps/maestro/WorkShell.jsx":"dea196e8e44f","apps/maestro/ds-adapter.jsx":"d0000c200dfe","apps/maestro/tweaks-panel.jsx":"6591467622ed","components/core/Avatar.jsx":"edc2c9651caa","components/core/Button.jsx":"33e0258e5dc9","components/core/Card.jsx":"ba353c59953f","components/core/Composer.jsx":"5ce7c554df26","components/core/DotComet.jsx":"9d03dc5858db","components/core/IconButton.jsx":"2a1802fcac3a","components/core/Input.jsx":"3ae50d355d65","components/core/StatusBadge.jsx":"87265c568b9e","components/forms/Checkbox.jsx":"64525f9da25a","components/forms/Field.jsx":"969487843b81","components/forms/Radio.jsx":"96fedfa25341","components/forms/Select.jsx":"86d89893ea9e","components/forms/Switch.jsx":"9f2c2bda0acd","components/forms/Textarea.jsx":"a6dc8ce4d347","components/navigation/CommandPalette.jsx":"d40e007e4ff7","components/navigation/Segmented.jsx":"e0974ae8cc24","components/navigation/Tabs.jsx":"5b7e52256a09","components/overlays/Dialog.jsx":"654e1682d5e0","components/overlays/Menu.jsx":"58c01a8d7d3e","components/overlays/Toast.jsx":"02140dcf02d6","components/overlays/Tooltip.jsx":"a0bea3405b1e","components/work/AutonomyScoreboard.jsx":"6308faacc5ba","components/work/LifecycleRail.jsx":"2a04c6940e3a","components/work/Receipt.jsx":"7d756919df64","components/work/RunCard.jsx":"88c07132ba8f","components/work/Undertow.jsx":"69d4afd8307d","components/work/WorkState.jsx":"74f1f38011aa"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.BroomvaDesignSystem_5727d9 = window.BroomvaDesignSystem_5727d9 || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// apps/maestro/AiProtocol.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
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

const bvSleep = ms => new Promise(r => setTimeout(r, ms));
let bvUidN = 0;
const bvUid = p => p + "_" + Date.now().toString(36) + bvUidN++;

// Wall-clock label for a user turn · "Jun 14 · 1:23 PM". Stamped on every
// input so the conversation minimap can show when each one happened.
function bvFmtClock(ts) {
  const d = new Date(ts);
  const mon = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][d.getMonth()];
  let h = d.getHours();
  const ap = h < 12 ? "AM" : "PM";
  h = h % 12;
  if (h === 0) h = 12;
  const m = String(d.getMinutes()).padStart(2, "0");
  return mon + " " + d.getDate() + " · " + h + ":" + m + " " + ap;
}

// ── Seed state · the maestro session, as UIMessages ──────────────────────
const MCC_ML_GATE = [{
  id: "g1",
  kind: "gate",
  title: "Persist run transcripts on the Run record",
  meta: "ran 2h 14m unsupervised · judge passed · 14 tests",
  ask: "Approve the branch and tonight's phase 2 builds on it.",
  look: [["changed", "run/7c2f1a · +412 −38 across 9 files"], ["decided", "transcripts persist on the Run record · replay covered by 14 tests"], ["asks", "merge the branch; tonight's phase 2 builds on it"]],
  hint: "a 90-second look",
  actions: [["Approve", "primary"], ["Send back", "secondary"]],
  t: "12m"
}, {
  id: "g2",
  kind: "warn",
  title: "Linear import needs an API scope",
  meta: "worker paused 41m · 3 queued items wait on it",
  ask: "Grant read access to Linear cycles, or park the import.",
  look: [["changed", "nothing merged · the worker paused itself at Linear auth"], ["decided", "it won't retry without a granted scope"], ["asks", "grant read on cycles, or park the import"]],
  hint: "unblocks 1 worker",
  actions: [["Grant access", "primary"], ["Park it", "secondary"]],
  t: "41m"
}];
const BV_TICK_ROWS = [{
  g: "▷",
  cause: "interval 15m",
  causeColor: "var(--bv-gray-500)",
  label: "No-op · at capacity (2/2 worktrees)",
  t: "32m"
}, {
  g: "▶",
  cause: "worker returned",
  causeColor: "var(--bv-blue)",
  label: "run/7c2f1a judged clean → queued to your gate",
  t: "12m"
}, {
  g: "▷",
  cause: "interval 15m",
  causeColor: "var(--bv-gray-500)",
  label: "Holding · 2 decisions open at your gate",
  t: "2m"
}];
const BV_SEED_MESSAGES = [{
  id: "seed-1",
  role: "assistant",
  metadata: {
    model: "broomva/maestro-loop"
  },
  parts: [{
    type: "text",
    state: "done",
    text: "Morning. The loop ran all night: the digest went out at 02:00 and genesis is still live on the phase machine. Two decisions wait below; the second frees three queued items."
  }, {
    type: "data-tick",
    id: "tick-log",
    data: {
      rows: BV_TICK_ROWS
    }
  }, {
    type: "data-gate",
    id: "g1",
    data: MCC_ML_GATE[0]
  }, {
    type: "data-gate",
    id: "g2",
    data: MCC_ML_GATE[1]
  }]
}, {
  id: "seed-2",
  role: "user",
  metadata: {
    time: "Jun 14 · 9:02 AM"
  },
  parts: [{
    type: "text",
    text: "what's blocking the relay handoff?"
  }]
}, {
  id: "seed-3",
  role: "assistant",
  metadata: {
    model: "anthropic/claude-sonnet-4.6"
  },
  parts: [{
    type: "text",
    state: "done",
    text: "Nothing but capacity: it's third in the queue. Clear the Linear scope below and I'll park the import, which frees a worktree on the next tick; the relay dispatches right after."
  }]
}, {
  id: "seed-4",
  role: "user",
  metadata: {
    time: "Jun 14 · 9:05 AM"
  },
  parts: [{
    type: "text",
    text: "park the import for now and clear the Linear scope"
  }]
}, {
  id: "seed-5",
  role: "assistant",
  metadata: {
    model: "anthropic/claude-sonnet-4.6"
  },
  parts: [{
    type: "text",
    state: "done",
    text: "Done. Import parked, scope released. A worktree frees on the next tick (≈13m) and the relay handoff moves to first in line. I'll dispatch it the moment capacity opens."
  }]
}, {
  id: "seed-6",
  role: "user",
  metadata: {
    time: "Jun 14 · 9:14 AM"
  },
  parts: [{
    type: "text",
    text: "show me what genesis touched overnight"
  }]
}, {
  id: "seed-7",
  role: "assistant",
  metadata: {
    model: "broomva/maestro-loop"
  },
  parts: [{
    type: "text",
    state: "done",
    text: "Genesis ran 6h 24m unsupervised on the projection layer. It reduced the NDJSON stream into the phase machine, landed 9 green tests, and opened run/4fd028 with the diff staged. No human gate tripped; it stayed inside the budget you set."
  }]
}, {
  id: "seed-8",
  role: "user",
  metadata: {
    time: "Jun 14 · 9:21 AM"
  },
  parts: [{
    type: "text",
    text: "approve the transcripts gate, phase 2 can build on it"
  }]
}, {
  id: "seed-9",
  role: "assistant",
  metadata: {
    model: "broomva/maestro-loop"
  },
  parts: [{
    type: "text",
    state: "done",
    text: "Approved. The branch is merged to the Run record and phase 2 is queued behind the relay. That clears one of your two decisions; one left."
  }]
}, {
  id: "seed-10",
  role: "user",
  metadata: {
    time: "Jun 14 · 9:36 AM"
  },
  parts: [{
    type: "text",
    text: "why did run/7c2f1a stall before the judge last night?"
  }]
}, {
  id: "seed-11",
  role: "assistant",
  metadata: {
    model: "anthropic/claude-sonnet-4.6"
  },
  parts: [{
    type: "reasoning",
    state: "done",
    text: "pulling the run log · it halted at the judge step, not the build"
  }, {
    type: "text",
    state: "done",
    text: "It didn't fail; it blocked on capacity. Both worktrees were busy when the judge wanted a clean checkout, so it parked itself rather than evict a running peer. The build artifacts are intact; it only needs a slot."
  }]
}, {
  id: "seed-12",
  role: "user",
  metadata: {
    time: "Jun 14 · 9:44 AM"
  },
  parts: [{
    type: "text",
    text: "rerun it with capacity bumped to 3 worktrees"
  }]
}, {
  id: "seed-13",
  role: "assistant",
  metadata: {
    model: "broomva/maestro-loop"
  },
  parts: [{
    type: "text",
    state: "done",
    text: "Capacity raised to 3 for this layer. run/7c2f1a is re-dispatched into the new slot and the relay takes the one after. Both are live now; receipts will land here as they pass the judge."
  }]
}, {
  id: "seed-14",
  role: "user",
  metadata: {
    time: "Jun 14 · 9:58 AM"
  },
  parts: [{
    type: "text",
    text: "good. ping me the moment the relay lands"
  }]
}, {
  id: "seed-15",
  role: "assistant",
  metadata: {
    model: "broomva/maestro-loop"
  },
  parts: [{
    type: "text",
    state: "done",
    text: "Will do. I'll surface it at your gate the instant the judge clears it, and hold everything downstream until you've seen it."
  }]
}];

// A long-running session · for stress-testing the conversation minimap at the
// density real work produces. ~100 user inputs interleaved with short maestro
// replies, timestamped across two days.
function bvMakeStressSeed(count = 100) {
  const userPool = ["bump the timeout and retry", "show me the diff for that run", "why is it still queued?", "approve it", "send that one back", "what's the test status?", "rerun with 3 worktrees", "park the import for now", "ping me when it lands", "summarize the last hour", "who's holding the lock?", "restart the sidecar", "good, continue", "pause everything for a sec", "what changed since the digest?", "roll back the last commit", "split this into two runs", "raise the budget for hawthorne", "is genesis still live?", "tail the run log for me"];
  const asstPool = ["On it. Dispatched into the next free slot.", "Done. Receipt's on the Run record.", "It's third in line; capacity is 2/2.", "Approved and merged.", "Sent back with notes for the worker.", "14 tests green, judge passed.", "Capacity raised; both are live now.", "Import parked; a worktree frees next tick.", "Will surface it at your gate the moment it clears.", "Last hour: 3 runs, 2 clean, 1 awaiting you.", "run/7c2f1a holds it; it'll release on finish.", "Sidecar restarted · PID 14831.", "Continuing where we left off.", "Paused. Nothing new will dispatch.", "Genesis is live on the projection layer.", "Rolled back; the branch is clean again."];
  const out = [{
    id: "stress-0",
    role: "assistant",
    metadata: {
      model: "broomva/maestro-loop"
    },
    parts: [{
      type: "text",
      state: "done",
      text: "Picking up the long-running session. The overnight digest is in and the loop is warm. Steer away; everything lands here."
    }]
  }];
  let ts = new Date(2026, 5, 12, 8, 12, 0).getTime();
  for (let i = 0; i < count; i++) {
    ts += (3 + i * 7 % 23) * 60000;
    out.push({
      id: "su" + i,
      role: "user",
      metadata: {
        time: bvFmtClock(ts)
      },
      parts: [{
        type: "text",
        text: userPool[i % userPool.length]
      }]
    });
    out.push({
      id: "sa" + i,
      role: "assistant",
      metadata: {
        model: i % 2 ? "anthropic/claude-sonnet-4.6" : "broomva/maestro-loop"
      },
      parts: [{
        type: "text",
        state: "done",
        text: asstPool[i % asstPool.length]
      }]
    });
  }
  return out;
}
const BV_SEED_STRESS = bvMakeStressSeed(100);
const BV_SEED_EXTREME = bvMakeStressSeed(600);

// ── The reducer · UIMessageChunk → UIMessage[] ────────────────────────────
function bvApplyChunk(prev, chunk) {
  const msgs = prev.slice();
  const touch = i => {
    const m = {
      ...msgs[i],
      parts: msgs[i].parts.slice()
    };
    msgs[i] = m;
    return m;
  };
  const li = msgs.length - 1;
  const t = chunk.type;
  if (t === "start") {
    msgs.push({
      id: chunk.messageId || bvUid("msg"),
      role: "assistant",
      metadata: chunk.messageMetadata,
      parts: []
    });
    return msgs;
  }
  if (t === "finish" || t === "abort" || t === "start-step" || t === "finish-step") return msgs;
  if (t.startsWith("data-")) {
    if (chunk.transient) return msgs; // surfaced via onData only · never persisted
    for (let i = 0; i < msgs.length; i++) {
      const j = msgs[i].parts.findIndex(p => p.type === t && chunk.id != null && p.id === chunk.id);
      if (j >= 0) {
        const m = touch(i);
        m.parts[j] = {
          ...m.parts[j],
          data: chunk.data
        };
        return msgs;
      }
    }
    const m = touch(li);
    m.parts.push({
      type: t,
      id: chunk.id,
      data: chunk.data
    });
    return msgs;
  }
  const m = touch(li);
  const findBlock = (type, id) => m.parts.findIndex(p => p.type === type && p.id === id);
  const findCall = id => m.parts.findIndex(p => p.toolCallId === id);
  if (t === "text-start") m.parts.push({
    type: "text",
    id: chunk.id,
    text: "",
    state: "streaming"
  });else if (t === "text-delta") {
    const j = findBlock("text", chunk.id);
    if (j >= 0) m.parts[j] = {
      ...m.parts[j],
      text: m.parts[j].text + chunk.delta
    };
  } else if (t === "text-end") {
    const j = findBlock("text", chunk.id);
    if (j >= 0) m.parts[j] = {
      ...m.parts[j],
      state: "done"
    };
  } else if (t === "reasoning-start") m.parts.push({
    type: "reasoning",
    id: chunk.id,
    text: "",
    state: "streaming"
  });else if (t === "reasoning-delta") {
    const j = findBlock("reasoning", chunk.id);
    if (j >= 0) m.parts[j] = {
      ...m.parts[j],
      text: m.parts[j].text + chunk.delta
    };
  } else if (t === "reasoning-end") {
    const j = findBlock("reasoning", chunk.id);
    if (j >= 0) m.parts[j] = {
      ...m.parts[j],
      state: "done"
    };
  } else if (t === "tool-input-start") {
    m.parts.push({
      type: "tool-" + chunk.toolName,
      toolCallId: chunk.toolCallId,
      state: "input-streaming",
      inputText: ""
    });
  } else if (t === "tool-input-delta") {
    const j = findCall(chunk.toolCallId);
    if (j >= 0) m.parts[j] = {
      ...m.parts[j],
      inputText: (m.parts[j].inputText || "") + chunk.inputTextDelta
    };
  } else if (t === "tool-input-available") {
    const j = findCall(chunk.toolCallId);
    if (j >= 0) m.parts[j] = {
      ...m.parts[j],
      state: "input-available",
      input: chunk.input
    };
  } else if (t === "tool-output-available") {
    const j = findCall(chunk.toolCallId);
    if (j >= 0) m.parts[j] = {
      ...m.parts[j],
      state: "output-available",
      output: chunk.output
    };
  } else if (t === "error") m.parts.push({
    type: "error",
    errorText: chunk.errorText
  });
  return msgs;
}

// Selectors · derived UI state from the transcript.
function bvSelectGate(messages) {
  const map = new Map();
  for (const m of messages) for (const p of m.parts) if (p.type === "data-gate") map.set(p.id, p.data);
  return [...map.values()].filter(g => g && !g.resolved);
}
function bvLastUserText(messages) {
  for (let i = messages.length - 1; i >= 0; i--) if (messages[i].role === "user") return messages[i].parts.filter(p => p.type === "text").map(p => p.text).join(" ");
  return "";
}

// ── Transports · three engines, one chunk protocol ────────────────────────
async function* bvStreamTextBlock(text, delay = 26) {
  const id = bvUid("txt");
  yield {
    type: "text-start",
    id
  };
  for (const w of text.match(/\S+\s*/g) || []) {
    await bvSleep(delay);
    yield {
      type: "text-delta",
      id,
      delta: w
    };
  }
  yield {
    type: "text-end",
    id
  };
}
class BvChatTransport {
  constructor({
    provider,
    model
  }) {
    this.provider = provider;
    this.model = model;
  }
  async *stream() {
    throw new Error("transport must implement stream(messages)");
  }
}
class BvAnthropicTransport extends BvChatTransport {
  async *stream(messages) {
    const q = bvLastUserText(messages);
    yield {
      type: "start",
      messageId: bvUid("msg"),
      messageMetadata: {
        model: this.model
      }
    };
    await bvSleep(220);
    yield* bvStreamTextBlock("Noted. I'm holding \u201C" + q + "\u201D against the queue. Nothing dispatches without a free worktree, and your two gate decisions still come first; clear them and the loop picks this up on the very next tick.");
    yield {
      type: "finish"
    };
  }
}
class BvOpenAITransport extends BvChatTransport {
  async *stream(messages) {
    const q = bvLastUserText(messages);
    yield {
      type: "start",
      messageId: bvUid("msg"),
      messageMetadata: {
        model: this.model
      }
    };
    const rid = bvUid("r");
    yield {
      type: "reasoning-start",
      id: rid
    };
    for (const w of "checking queue order and the two open stopgaps before committing".match(/\S+\s*/g)) {
      await bvSleep(22);
      yield {
        type: "reasoning-delta",
        id: rid,
        delta: w
      };
    }
    yield {
      type: "reasoning-end",
      id: rid
    };
    yield* bvStreamTextBlock("Understood. \u201C" + q + "\u201D is registered. Current blockers are your two gate decisions; once cleared, capacity frees on the next tick and this proceeds without supervision.");
    yield {
      type: "finish"
    };
  }
}
class BvHarnessTransport extends BvChatTransport {
  async *stream(messages) {
    const q = bvLastUserText(messages);
    yield {
      type: "start",
      messageId: bvUid("msg"),
      messageMetadata: {
        model: this.model
      }
    };
    const rid = bvUid("r");
    yield {
      type: "reasoning-start",
      id: rid
    };
    for (const w of "reading the queue · 2 decisions pending · capacity 2/2 · next tick 13m".match(/\S+\s*/g)) {
      await bvSleep(24);
      yield {
        type: "reasoning-delta",
        id: rid,
        delta: w
      };
    }
    yield {
      type: "reasoning-end",
      id: rid
    };
    const callId = bvUid("call");
    yield {
      type: "tool-input-start",
      toolCallId: callId,
      toolName: "dispatch"
    };
    await bvSleep(160);
    yield {
      type: "tool-input-delta",
      toolCallId: callId,
      inputTextDelta: '{"goal":"' + q.slice(0, 36) + '…"'
    };
    await bvSleep(200);
    yield {
      type: "tool-input-available",
      toolCallId: callId,
      toolName: "dispatch",
      input: {
        goal: q,
        scope: "hawthorne-core",
        budget: "inherit"
      }
    };
    await bvSleep(340);
    yield {
      type: "tool-output-available",
      toolCallId: callId,
      output: {
        queued: true,
        position: 3,
        reason: "capacity 2/2"
      }
    };
    await bvSleep(180);
    yield {
      type: "data-tick",
      id: "tick-log",
      data: {
        rows: [...BV_TICK_ROWS, {
          g: "▶",
          cause: "operator message",
          causeColor: "var(--bv-blue)",
          label: "Routed to the queue · position 3, re-evaluated next tick",
          t: "now"
        }]
      }
    };
    yield* bvStreamTextBlock("Routed. It holds position 3; the tick receipt above updated in place. Clear the Linear scope and a worktree frees; the loop re-evaluates in 13m either way.");
    yield {
      type: "finish"
    };
  }
}
const BV_PROVIDERS = [{
  id: "anthropic",
  label: "claude 4.6",
  model: "anthropic/claude-sonnet-4.6",
  pkg: "@ai-sdk/anthropic"
}, {
  id: "openai",
  label: "gpt-5.2",
  model: "openai/gpt-5.2",
  pkg: "@ai-sdk/openai"
}, {
  id: "harness",
  label: "maestro harness",
  model: "broomva/maestro-loop",
  pkg: "custom ChatTransport"
}];

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
const BV_EFFORT_SCALE = [{
  id: "none",
  label: "None",
  bars: 0,
  ratio: 0,
  desc: "answer directly · no reasoning"
}, {
  id: "minimal",
  label: "Minimal",
  bars: 1,
  ratio: 0.1,
  desc: "fastest useful answer"
}, {
  id: "low",
  label: "Low",
  bars: 2,
  ratio: 0.2,
  desc: "light reasoning"
}, {
  id: "medium",
  label: "Medium",
  bars: 3,
  ratio: 0.5,
  desc: "balanced depth"
}, {
  id: "high",
  label: "High",
  bars: 4,
  ratio: 0.8,
  desc: "careful · weighs alternatives"
}, {
  id: "xhigh",
  label: "X-High",
  bars: 5,
  ratio: 0.95,
  desc: "extended exploration"
}, {
  id: "max",
  label: "Max",
  bars: 6,
  ratio: 1,
  desc: "no constraint on thinking"
}];
const bvEffort = id => BV_EFFORT_SCALE.find(e => e.id === id);
// Tolerance: a live gateway may declare a stop the scale doesn't know yet.
// Render it instead of dropping it · flagged, top bars, logged once · so a
// new provider ladder degrades gracefully until the scale is updated.
const bvUnknownEfforts = {};
function bvUnknownEffort(id) {
  if (!bvUnknownEfforts[id]) {
    console.warn('[broomva] unknown effort stop "' + id + '" · not in the canonical scale; rendering as provider-specific');
    bvUnknownEfforts[id] = {
      id,
      label: id,
      bars: 6,
      ratio: 1,
      desc: "provider-specific stop · append to the canonical scale",
      unknown: true
    };
  }
  return bvUnknownEfforts[id];
}

// How each provider serializes a canonical stop on the wire.
const BV_PROVIDER_INFO = {
  anthropic: {
    label: "Anthropic",
    wire: effort => ({
      effort
    })
  },
  openai: {
    label: "OpenAI",
    wire: effort => ({
      reasoning: {
        effort
      }
    })
  },
  google: {
    label: "Google · via gateway",
    wire: effort => ({
      reasoning: {
        effort
      }
    })
  },
  moonshot: {
    label: "Moonshot · via gateway",
    wire: effort => ({
      reasoning: {
        effort
      }
    })
  },
  deepseek: {
    label: "DeepSeek · via gateway",
    wire: effort => ({
      reasoning: {
        effort
      }
    })
  }
};
const BV_MODEL_CATALOG = [
// Anthropic · effort: low–max; xhigh only on Opus 4.7+; default high
{
  id: "anthropic/claude-opus-4.8",
  label: "claude opus 4.8",
  provider: "anthropic",
  glyph: "spark",
  isNew: true,
  reasoning: {
    efforts: ["low", "medium", "high", "xhigh", "max"],
    default: "high"
  }
}, {
  id: "anthropic/claude-sonnet-4.6",
  label: "claude 4.6",
  provider: "anthropic",
  glyph: "spark",
  reasoning: {
    efforts: ["low", "medium", "high", "max"],
    default: "high"
  }
}, {
  id: "anthropic/claude-sonnet-4.6-1m",
  label: "claude 4.6 · 1M",
  provider: "anthropic",
  glyph: "spark",
  reasoning: {
    efforts: ["low", "medium", "high", "max"],
    default: "high"
  }
}, {
  id: "anthropic/claude-haiku-4.5",
  label: "claude haiku 4.5",
  provider: "anthropic",
  glyph: "spark",
  reasoning: {
    efforts: ["low", "medium", "high"],
    default: "medium"
  }
},
// OpenAI · reasoning.effort: none–high; xhigh on codex-max; defaults vary
{
  id: "openai/gpt-5.2",
  label: "gpt-5.2",
  provider: "openai",
  glyph: "ring",
  reasoning: {
    efforts: ["none", "low", "medium", "high"],
    default: "medium"
  }
}, {
  id: "openai/gpt-5.1-codex-max",
  label: "gpt-5.1 codex max",
  provider: "openai",
  glyph: "ring",
  reasoning: {
    efforts: ["none", "low", "medium", "high", "xhigh"],
    default: "medium"
  }
}, {
  id: "openai/gpt-5.2-mini",
  label: "gpt-5.2 mini",
  provider: "openai",
  glyph: "ring",
  reasoning: {
    efforts: ["none", "minimal", "low", "medium"],
    default: "low"
  }
},
// Via the gateway · same shape, any provider it lists
{
  id: "google/gemini-3.1-pro",
  label: "gemini 3.1 pro",
  provider: "google",
  glyph: "orbit",
  reasoning: {
    efforts: ["low", "medium", "high"],
    default: "medium"
  }
}, {
  id: "moonshotai/kimi-k2.6",
  label: "kimi k2.6",
  provider: "moonshot",
  glyph: "orbit",
  reasoning: {
    efforts: ["minimal", "low", "medium", "high", "xhigh"],
    default: "medium"
  }
},
// Budget-wire · no native effort param: the stop converts to a
// thinking-token budget via the scale's ratios (gateway normalization).
{
  id: "deepseek/deepseek-r1",
  label: "deepseek r1",
  provider: "deepseek",
  glyph: "orbit",
  reasoning: {
    efforts: ["minimal", "low", "medium", "high"],
    default: "medium",
    wire: "budget",
    budget: {
      min: 1024,
      max: 32768
    }
  }
}];
const BV_HARNESSES = [{
  id: "maestro",
  label: "maestro",
  glyph: "tide",
  transport: "harness",
  def: true,
  desc: "the loop · dispatch · judge · gate",
  models: "*",
  // model-agnostic: the whole catalog, via the gateway
  defaultModel: "anthropic/claude-opus-4.8",
  presets: []
}, {
  id: "claude-code",
  label: "claude code",
  glyph: "spark",
  transport: "anthropic",
  desc: "Anthropic's coding agent",
  models: {
    provider: "anthropic"
  },
  defaultModel: "anthropic/claude-opus-4.8",
  presets: [{
    id: "ultracode",
    label: "ultracode",
    sub: "xhigh + workflows",
    effort: "xhigh",
    desc: "sends xhigh, plus auto workflow orchestration"
  }]
}, {
  id: "codex",
  label: "codex",
  glyph: "ring",
  transport: "openai",
  desc: "OpenAI's coding agent",
  models: {
    provider: "openai"
  },
  defaultModel: "openai/gpt-5.2",
  presets: []
}];
const bvHarness = id => BV_HARNESSES.find(h => h.id === id) || BV_HARNESSES[0];
// Harness model filters are DECLARATIVE ("*" or a field-match object), so
// harness configs can live in a DB or come down the wire · compiled here.
const bvPickFn = spec => spec === "*" || spec == null ? () => true : m => Object.entries(spec).every(([k, v]) => m[k] === v);
const bvHarnessModels = h => BV_MODEL_CATALOG.filter(bvPickFn(h.models));
const bvHarnessModel = (h, id) => {
  const list = bvHarnessModels(h);
  return list.find(m => m.id === id) || list.find(m => m.id === h.defaultModel) || list[0];
};
const bvModelEfforts = m => m.reasoning.efforts.map(id => bvEffort(id) || bvUnknownEffort(id));
const bvPresets = (h, m) => (h.presets || []).filter(p => m.reasoning.efforts.includes(p.effort));

// Resolve a requested effort id (scale stop OR harness preset) against the
// current harness+model pair · the clamping cascade. Always returns
// something the pair supports, falling back to the model's own default.
function bvResolveEffort(h, m, effortId) {
  const p = bvPresets(h, m).find(x => x.id === effortId);
  if (p) return {
    kind: "preset",
    preset: p,
    effort: bvEffort(p.effort)
  };
  const supported = bvModelEfforts(m);
  const e = supported.find(x => x.id === effortId);
  if (e) return {
    kind: "effort",
    effort: e
  };
  // Fallback order: the harness's default override (if this model supports
  // it) → the model's own declared default → the model's first stop.
  const fb = h.defaultEffort && supported.find(x => x.id === h.defaultEffort) || supported.find(x => x.id === m.reasoning.default) || supported[0];
  return {
    kind: "effort",
    effort: fb
  };
}
const bvSelEffortId = r => r.kind === "preset" ? r.preset.id : r.effort.id;
// What actually goes on the wire for a selection. Budget-wire models have
// no native effort param: the stop converts to a thinking-token budget via
// its ratio (the same normalization gateways apply), clamped to the
// model's declared budget range. maxTokens is the request's output cap.
function bvWireEffort(m, sel, maxTokens = 32000) {
  const r = m.reasoning;
  if (r.wire === "budget") {
    if (sel.effort.ratio === 0) return {
      reasoning: {
        enabled: false
      }
    };
    const n = Math.round(maxTokens * sel.effort.ratio);
    return {
      reasoning: {
        max_tokens: Math.max(r.budget.min, Math.min(n, r.budget.max))
      }
    };
  }
  return (BV_PROVIDER_INFO[m.provider] || BV_PROVIDER_INFO.anthropic).wire(sel.effort.id);
}
const bvTransportCache = {};
function bvGetTransport(harnessId, modelId) {
  const h = bvHarness(harnessId);
  const m = bvHarnessModel(h, modelId);
  const key = h.id + "/" + m.id;
  if (!bvTransportCache[key]) {
    const Cls = h.transport === "harness" ? BvHarnessTransport : m.provider === "anthropic" ? BvAnthropicTransport : BvOpenAITransport;
    bvTransportCache[key] = new Cls({
      provider: m.provider,
      model: m.id
    });
  }
  return bvTransportCache[key];
}
const BV_TRANSPORTS = {
  anthropic: new BvAnthropicTransport({
    provider: "anthropic",
    model: "anthropic/claude-sonnet-4.6"
  }),
  openai: new BvOpenAITransport({
    provider: "openai",
    model: "openai/gpt-5.2"
  }),
  harness: new BvHarnessTransport({
    provider: "harness",
    model: "broomva/maestro-loop"
  })
};

// ── useBvChat · useChat-shaped state over any transport ──────────────────
function useBvChat({
  transport,
  initialMessages,
  onData
}) {
  const [messages, setMessages] = React.useState(initialMessages || []);
  const [status, setStatus] = React.useState("ready");
  const msgsRef = React.useRef(messages);
  msgsRef.current = messages;
  const tRef = React.useRef(transport);
  tRef.current = transport;
  const onDataRef = React.useRef(onData);
  onDataRef.current = onData;
  const sendMessage = React.useCallback(async ({
    text
  }) => {
    if (!text || !text.trim()) return;
    const user = {
      id: bvUid("msg"),
      role: "user",
      metadata: {
        time: bvFmtClock(Date.now())
      },
      parts: [{
        type: "text",
        text: text.trim()
      }]
    };
    setMessages(m => [...m, user]);
    setStatus("submitted");
    try {
      for await (const chunk of tRef.current.stream([...msgsRef.current, user])) {
        if (chunk.type.startsWith("data-") && chunk.transient) {
          if (onDataRef.current) onDataRef.current(chunk);
          continue;
        }
        setStatus("streaming");
        setMessages(m => bvApplyChunk(m, chunk));
      }
    } finally {
      setStatus("ready");
    }
  }, []);
  return {
    messages,
    status,
    sendMessage
  };
}

// ── The renderer · part type → Broomva component ─────────────────────────
function MccToolPart({
  part
}) {
  const name = part.type.slice(5);
  const state = part.state;
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-toolpart",
    "data-screen-label": "Tool part · " + name
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-toolpart-head"
  }, /*#__PURE__*/React.createElement(McIcon, {
    size: 13
  }, /*#__PURE__*/React.createElement("rect", {
    width: "18",
    height: "18",
    x: "3",
    y: "3",
    rx: "2"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m8 12 2 2 4-4"
  })), /*#__PURE__*/React.createElement("b", null, name), /*#__PURE__*/React.createElement("span", {
    className: "mcc-toolpart-state" + (state === "output-available" ? " is-done" : "")
  }, state === "output-available" ? "done" : state === "input-available" ? "running" : "streaming input…")), part.input ? /*#__PURE__*/React.createElement("code", {
    className: "mcc-toolpart-line"
  }, "input\xA0\xA0", JSON.stringify(part.input)) : part.inputText ? /*#__PURE__*/React.createElement("code", {
    className: "mcc-toolpart-line"
  }, "input\xA0\xA0", part.inputText) : null, part.output && /*#__PURE__*/React.createElement("code", {
    className: "mcc-toolpart-line"
  }, "output\xA0", JSON.stringify(part.output)));
}
function MccMessage({
  msg
}) {
  if (msg.role === "user") {
    return /*#__PURE__*/React.createElement("div", {
      className: "bv-msg bv-msg--user",
      "data-bv-user": "1",
      "data-bv-time": msg.metadata && msg.metadata.time || ""
    }, msg.parts.filter(p => p.type === "text").map(p => p.text).join(""));
  }
  return /*#__PURE__*/React.createElement(React.Fragment, null, msg.parts.map((p, i) => {
    if (p.type === "text") return /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "bv-msg bv-msg--assistant" + (p.state === "streaming" ? " mcc-msg-streaming" : "")
    }, p.text);
    if (p.type === "reasoning") return /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "mcc-reasoning"
    }, /*#__PURE__*/React.createElement("span", {
      "aria-hidden": "true"
    }, "\u273B"), /*#__PURE__*/React.createElement("span", null, p.text));
    if (p.type === "data-tick") return /*#__PURE__*/React.createElement(MccTickCard, {
      key: i,
      rows: p.data.rows
    });
    if (p.type === "error") return /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "mcc-reasoning"
    }, /*#__PURE__*/React.createElement("span", {
      "aria-hidden": "true"
    }, "!"), /*#__PURE__*/React.createElement("span", null, p.errorText));
    if (p.type.startsWith("data-")) return null; // rendered by selectors (gate queue)
    if (p.type.startsWith("tool-")) return /*#__PURE__*/React.createElement(MccToolPart, {
      key: i,
      part: p
    });
    return null;
  }));
}

// The dispatch menus · three chips, one popover pattern: harness (the
// agentic shell) → model (the LLM beneath it, scoped to the harness) →
// effort (capability-gated by the model). Esc or outside-click closes,
// ✦ marks the default, the check marks the active row.
function MccModelGlyph({
  kind,
  size = 13
}) {
  if (kind === "tide") return /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 12,
      height: 12
    }
  });
  if (kind === "ring") return /*#__PURE__*/React.createElement(McIcon, {
    size: size
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "8"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "2.5"
  }));
  if (kind === "orbit") return /*#__PURE__*/React.createElement(McIcon, {
    size: size
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "13",
    r: "7"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "19",
    cy: "5",
    r: "2"
  }));
  return /*#__PURE__*/React.createElement(IcxSpark, {
    size: size
  });
}
function useMccMenu() {
  const [open, setOpen] = React.useState(false);
  const ref = React.useRef(null);
  return {
    open,
    setOpen,
    ref
  };
}

// Popovers anchored to the prompt rail must NOT render inside the composer:
// the composer carries its own backdrop-filter, and a backdrop-filter nested
// inside another one can't sample the page behind it · so the menu's frost
// dies and content leaks through sharp. Portal to <body> so the blur samples
// the real page, and position it (fixed) above the anchoring chip.
function MccPopover({
  open,
  anchorRef,
  onClose,
  className,
  children,
  ...rest
}) {
  const popRef = React.useRef(null);
  const [pos, setPos] = React.useState(null);
  React.useLayoutEffect(() => {
    if (!open) {
      setPos(null);
      return;
    }
    const calc = () => {
      const a = anchorRef.current;
      if (!a) return;
      const r = a.getBoundingClientRect();
      const w = popRef.current ? popRef.current.offsetWidth : 240;
      const maxLeft = window.innerWidth - w - 8;
      const left = Math.max(8, Math.min(r.left, maxLeft));
      setPos({
        left: Math.round(left),
        bottom: Math.round(window.innerHeight - r.top + 8)
      });
    };
    calc();
    const id = requestAnimationFrame(calc);
    window.addEventListener("resize", calc);
    return () => {
      cancelAnimationFrame(id);
      window.removeEventListener("resize", calc);
    };
  }, [open]);
  React.useEffect(() => {
    if (!open) return;
    const onDown = e => {
      if (anchorRef.current && anchorRef.current.contains(e.target)) return;
      if (popRef.current && popRef.current.contains(e.target)) return;
      onClose();
    };
    const onKey = e => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);
  if (!open) return null;
  return ReactDOM.createPortal(/*#__PURE__*/React.createElement("div", _extends({
    ref: popRef,
    className: className,
    style: {
      position: "fixed",
      top: "auto",
      left: pos ? pos.left : -9999,
      bottom: pos ? pos.bottom : 0,
      visibility: pos ? "visible" : "hidden"
    }
  }, rest), children), document.body);
}
function MccMenuChip({
  open,
  onClick,
  title,
  children
}) {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-prompt-chip mcc-prompt-chip--model",
    title: title,
    "aria-expanded": open,
    "aria-haspopup": "menu",
    onClick: onClick
  }, children, /*#__PURE__*/React.createElement(IcxChevDown, {
    size: 11,
    className: "mcc-prompt-chev" + (open ? " is-open" : "")
  }));
}
function MccHarnessMenu({
  value,
  onChange
}) {
  const {
    open,
    setOpen,
    ref
  } = useMccMenu();
  const cur = bvHarness(value);
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-modelmenu",
    ref: ref
  }, /*#__PURE__*/React.createElement(MccMenuChip, {
    open: open,
    onClick: () => setOpen(!open),
    title: "harness: " + cur.desc
  }, /*#__PURE__*/React.createElement(MccModelGlyph, {
    kind: cur.glyph,
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-prompt-chip-label"
  }, cur.label)), /*#__PURE__*/React.createElement(MccPopover, {
    open: open,
    anchorRef: ref,
    onClose: () => setOpen(false),
    className: "mcc-mm-pop",
    role: "menu",
    "data-screen-label": "Harness picker"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-mm-gl"
  }, "Harness"), BV_HARNESSES.map(h => /*#__PURE__*/React.createElement("button", {
    key: h.id,
    type: "button",
    role: "menuitemradio",
    "aria-checked": h.id === cur.id,
    className: "mcc-mm-row mcc-mm-row--tall" + (h.id === cur.id ? " is-active" : ""),
    onClick: () => {
      onChange(h.id);
      setOpen(false);
    }
  }, /*#__PURE__*/React.createElement(MccModelGlyph, {
    kind: h.glyph
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-mm-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-mm-name"
  }, h.label), /*#__PURE__*/React.createElement("span", {
    className: "mcc-mm-desc"
  }, h.desc)), h.def && /*#__PURE__*/React.createElement("span", {
    className: "mcc-mm-def",
    title: "The default"
  }, "\u2726"), h.id === cur.id && /*#__PURE__*/React.createElement(IcCheck, {
    size: 13,
    className: "mcc-mm-check"
  })))));
}
function MccModelMenu({
  harness,
  value,
  onChange
}) {
  const {
    open,
    setOpen,
    ref
  } = useMccMenu();
  const h = harness || bvHarness();
  const cur = bvHarnessModel(h, value);
  // Group the harness's slice of the catalog by provider.
  const groups = [];
  bvHarnessModels(h).forEach(m => {
    const label = (BV_PROVIDER_INFO[m.provider] || {
      label: m.provider
    }).label;
    let g = groups.find(x => x.label === label);
    if (!g) groups.push(g = {
      label,
      models: []
    });
    g.models.push(m);
  });
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-modelmenu",
    ref: ref
  }, /*#__PURE__*/React.createElement(MccMenuChip, {
    open: open,
    onClick: () => setOpen(!open),
    title: cur.id
  }, /*#__PURE__*/React.createElement(MccModelGlyph, {
    kind: cur.glyph,
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-prompt-chip-label"
  }, cur.label)), /*#__PURE__*/React.createElement(MccPopover, {
    open: open,
    anchorRef: ref,
    onClose: () => setOpen(false),
    className: "mcc-mm-pop",
    role: "menu",
    "data-screen-label": "Model picker"
  }, groups.map(g => /*#__PURE__*/React.createElement("div", {
    key: g.label,
    className: "mcc-mm-group"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-mm-gl"
  }, g.label), g.models.map(m => /*#__PURE__*/React.createElement("button", {
    key: m.id,
    type: "button",
    role: "menuitemradio",
    "aria-checked": m.id === cur.id,
    className: "mcc-mm-row" + (m.id === cur.id ? " is-active" : ""),
    title: m.id,
    onClick: () => {
      onChange(m.id);
      setOpen(false);
    }
  }, /*#__PURE__*/React.createElement(MccModelGlyph, {
    kind: m.glyph
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-mm-name"
  }, m.label), m.isNew && /*#__PURE__*/React.createElement("span", {
    className: "mcc-mm-new"
  }, "new"), m.id === h.defaultModel && /*#__PURE__*/React.createElement("span", {
    className: "mcc-mm-def",
    title: "The default"
  }, "\u2726"), m.id === cur.id && /*#__PURE__*/React.createElement(IcCheck, {
    size: 13,
    className: "mcc-mm-check"
  })))))));
}
function MccEffortMenu({
  harness,
  model,
  value,
  onChange
}) {
  const {
    open,
    setOpen,
    ref
  } = useMccMenu();
  const h = harness || bvHarness();
  const m = model || bvHarnessModel(h);
  const efforts = bvModelEfforts(m);
  const presets = bvPresets(h, m);
  const sel = bvResolveEffort(h, m, value);
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-modelmenu",
    ref: ref
  }, /*#__PURE__*/React.createElement(MccMenuChip, {
    open: open,
    onClick: () => setOpen(!open),
    title: "effort · what " + m.label + " supports"
  }, /*#__PURE__*/React.createElement(MccEffortBars, {
    level: sel.effort.bars
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-prompt-chip-label"
  }, sel.kind === "preset" ? sel.preset.label : sel.effort.label)), /*#__PURE__*/React.createElement(MccPopover, {
    open: open,
    anchorRef: ref,
    onClose: () => setOpen(false),
    className: "mcc-mm-pop",
    role: "menu",
    "data-screen-label": "Effort picker"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-mm-group"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-mm-gl"
  }, "Effort \xB7 ", m.label), efforts.map(e => /*#__PURE__*/React.createElement("button", {
    key: e.id,
    type: "button",
    role: "menuitemradio",
    "aria-checked": sel.kind === "effort" && e.id === sel.effort.id,
    className: "mcc-mm-row" + (sel.kind === "effort" && e.id === sel.effort.id ? " is-active" : ""),
    title: e.desc,
    onClick: () => {
      onChange(e.id);
      setOpen(false);
    }
  }, /*#__PURE__*/React.createElement(MccEffortBars, {
    level: e.bars
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-mm-name"
  }, e.label), e.id === m.reasoning.default && /*#__PURE__*/React.createElement("span", {
    className: "mcc-mm-def",
    title: "The model's default"
  }, "\u2726"), sel.kind === "effort" && e.id === sel.effort.id && /*#__PURE__*/React.createElement(IcCheck, {
    size: 13,
    className: "mcc-mm-check"
  })))), presets.length > 0 && /*#__PURE__*/React.createElement("div", {
    className: "mcc-mm-group"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-mm-gl"
  }, h.label, " modes"), presets.map(p => /*#__PURE__*/React.createElement("button", {
    key: p.id,
    type: "button",
    role: "menuitemradio",
    "aria-checked": sel.kind === "preset" && p.id === sel.preset.id,
    className: "mcc-mm-row mcc-mm-row--tall" + (sel.kind === "preset" && p.id === sel.preset.id ? " is-active" : ""),
    title: p.desc,
    onClick: () => {
      onChange(p.id);
      setOpen(false);
    }
  }, /*#__PURE__*/React.createElement(MccEffortBars, {
    level: (bvEffort(p.effort) || {
      bars: 0
    }).bars
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-mm-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-mm-name"
  }, p.label), /*#__PURE__*/React.createElement("span", {
    className: "mcc-mm-desc"
  }, p.sub)), sel.kind === "preset" && p.id === sel.preset.id && /*#__PURE__*/React.createElement(IcCheck, {
    size: 13,
    className: "mcc-mm-check"
  })))), /*#__PURE__*/React.createElement("div", {
    className: "mcc-mm-note"
  }, m.label, " \xB7 ", efforts[0].label.toLowerCase(), "\u2013", efforts[efforts.length - 1].label.toLowerCase(), " of the canonical scale")));
}

// useMccDispatch · one piece of state for the rail: harness → model →
// effort, re-clamped on every change to what the layer beneath supports.
function useMccDispatch(initial = {}) {
  const [sel, setSel] = React.useState(() => {
    const h = bvHarness(initial.harness);
    const m = bvHarnessModel(h, initial.model);
    return {
      harness: h.id,
      model: m.id,
      effort: bvSelEffortId(bvResolveEffort(h, m, initial.effort || m.reasoning.default))
    };
  });
  const setHarness = React.useCallback(id => setSel(s => {
    const h = bvHarness(id);
    const m = bvHarnessModel(h, s.model);
    return {
      harness: h.id,
      model: m.id,
      effort: bvSelEffortId(bvResolveEffort(h, m, s.effort))
    };
  }), []);
  const setModel = React.useCallback(id => setSel(s => {
    const h = bvHarness(s.harness);
    const m = bvHarnessModel(h, id);
    return {
      ...s,
      model: m.id,
      effort: bvSelEffortId(bvResolveEffort(h, m, s.effort))
    };
  }), []);
  const setEffort = React.useCallback(id => setSel(s => ({
    ...s,
    effort: id
  })), []);
  return {
    ...sel,
    setHarness,
    setModel,
    setEffort
  };
}
function MccDispatchRail({
  d,
  quiet
}) {
  const h = bvHarness(d.harness);
  const m = bvHarnessModel(h, d.model);
  // Quiet (the default): the harness is the only choice surfaced · model and
  // effort ride the harness defaults, per "plain over technical". The full
  // rail is a Tweak for people tuning dispatch.
  if (quiet) {
    return /*#__PURE__*/React.createElement(MccHarnessMenu, {
      value: h.id,
      onChange: d.setHarness
    });
  }
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(MccHarnessMenu, {
    value: h.id,
    onChange: d.setHarness
  }), /*#__PURE__*/React.createElement(MccModelMenu, {
    harness: h,
    value: m.id,
    onChange: d.setModel
  }), /*#__PURE__*/React.createElement(MccEffortMenu, {
    harness: h,
    model: m,
    value: d.effort,
    onChange: d.setEffort
  }));
}

// The self-contained rail · for plates that don't lift the state.
function MccDefaultRail(props) {
  const d = useMccDispatch(props);
  return /*#__PURE__*/React.createElement(MccDispatchRail, {
    d: d,
    quiet: props.rail !== "full"
  });
}

// The provider chip · cycles claude → gpt → harness in the prompt rail.
function MccRailProvider({
  value,
  onChange
}) {
  const i = Math.max(0, BV_PROVIDERS.findIndex(p => p.id === value));
  const cur = BV_PROVIDERS[i];
  const next = BV_PROVIDERS[(i + 1) % BV_PROVIDERS.length];
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-prompt-chip mcc-prompt-chip--model",
    title: cur.model + " · click for " + next.label,
    onClick: () => onChange(next.id)
  }, /*#__PURE__*/React.createElement(IcxSpark, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-prompt-chip-label"
  }, cur.label), /*#__PURE__*/React.createElement(IcxChevDown, {
    size: 11,
    className: "mcc-prompt-chev"
  }));
}
Object.assign(window, {
  MCC_ML_GATE,
  BV_TICK_ROWS,
  BV_SEED_MESSAGES,
  BV_SEED_STRESS,
  BV_SEED_EXTREME,
  bvApplyChunk,
  bvSelectGate,
  bvLastUserText,
  bvUid,
  BvChatTransport,
  BvAnthropicTransport,
  BvOpenAITransport,
  BvHarnessTransport,
  BV_PROVIDERS,
  BV_TRANSPORTS,
  BV_EFFORT_SCALE,
  BV_MODEL_CATALOG,
  BV_PROVIDER_INFO,
  BV_HARNESSES,
  bvHarness,
  bvHarnessModels,
  bvHarnessModel,
  bvModelEfforts,
  bvPresets,
  bvResolveEffort,
  bvWireEffort,
  bvGetTransport,
  useBvChat,
  MccMessage,
  MccToolPart,
  MccRailProvider,
  MccModelMenu,
  MccModelGlyph,
  MccHarnessMenu,
  MccEffortMenu,
  useMccDispatch,
  MccDispatchRail,
  MccDefaultRail
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/AiProtocol.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/ConceptAttention.jsx
try { (() => {
// Concepts canvas · the architect's attention.
// One operator, many projects, many loops. Three jobs compete for the
// center of the screen:
//   command · text in (the chat is the key input interface)
//   observe · the live feed of session loops
//   decide  · the gate: approvals, unblocks, the human calls
// Three frames, each making a different job primary. The other two never
// disappear · they become a rail, a dock, or a summon.

// ── Shared demo data ──────────────────────────────────────────────────────
const MCC_AT_LOOPS = [{
  kind: "live",
  title: "@genesis/projection",
  line: "Edit reducer.ts · 9 tests passed",
  t: "2h 14m"
}, {
  kind: "live",
  title: "bookkeeping",
  line: "Reconciling May invoices · cloud sandbox",
  t: "6m"
}, {
  kind: "gate",
  title: "hawthorne-core",
  line: "run/7c2f1a judged clean · awaiting your approve",
  t: "12m"
}, {
  kind: "warn",
  title: "hawthorne-db",
  line: "Stuck · needs a Linear API scope",
  t: "41m"
}, {
  kind: "standing",
  title: "nightly-digest",
  line: "Standing · nightly 02:00 · last run 31m",
  t: "8h"
}];
function MccLoopDot({
  kind
}) {
  if (kind === "live") return /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 13,
      height: 13
    }
  });
  if (kind === "standing") return /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot bv-dot--pulse",
    style: {
      background: "var(--bv-info)"
    }
  });
  if (kind === "queued") return /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      background: "var(--bv-gray-400)"
    }
  });
  return /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      background: kind === "warn" ? "var(--bv-warning)" : "var(--bv-blue-accent)"
    }
  });
}

// The loops, as a rail · observation made peripheral but always present.
function MccLoopsRail() {
  return /*#__PURE__*/React.createElement("aside", {
    className: "mcc-loops",
    "data-screen-label": "Loops rail"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-loops-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-panel-label"
  }, "Loops"), /*#__PURE__*/React.createElement("span", {
    className: "mcc-loops-count"
  }, "2 live \xB7 2 need you \xB7 1 standing")), /*#__PURE__*/React.createElement("div", {
    className: "mcc-sess-list"
  }, MCC_AT_LOOPS.map(l => /*#__PURE__*/React.createElement("button", {
    key: l.title,
    className: "mcc-sess",
    type: "button"
  }, /*#__PURE__*/React.createElement(MccLoopDot, {
    kind: l.kind
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-sess-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-sess-label"
  }, l.title), /*#__PURE__*/React.createElement("span", {
    className: "mcc-sess-meta" + (l.kind === "live" ? " mcc-caret" : "")
  }, l.line)), /*#__PURE__*/React.createElement("span", {
    className: "mcc-loops-t"
  }, l.t)))));
}

// The docked plate · command demoted to one keystroke away, never gone.
function MccCmdDock({
  placeholder = "Tell the workspace what's next · it routes through maestro…"
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-dock"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-dock-inner"
  }, /*#__PURE__*/React.createElement(MccPromptPlate, {
    className: "mcc-prompt--glass",
    placeholder: placeholder
  })));
}
function MccAttnFrame({
  children,
  screenLabel
}) {
  const noop = () => {};
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-fill"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-app"
  }, /*#__PURE__*/React.createElement(MccTcSidebar, {
    scope: "root",
    setScope: noop
  }), /*#__PURE__*/React.createElement("div", {
    className: "bv-main",
    "data-screen-label": screenLabel
  }, /*#__PURE__*/React.createElement(McvTopBar, {
    theme: "light",
    onToggleTheme: noop,
    onOpenMaestro: noop,
    onWake: noop,
    waking: false,
    canWake: true,
    onShowIdea: noop,
    counts: {
      needYou: 1,
      stuck: 1
    },
    workers: ["claude", "bookkeeper"],
    wakes: MCC_TICK_WAKES,
    items: WK_ITEMS,
    onAttention: noop,
    onCommand: noop
  }), children)));
}

// ── S · The matrix · what each layout makes primary ──────────────────────
function MccAttnSchema() {
  const cell = v => /*#__PURE__*/React.createElement("span", {
    className: "mcc-mx-badge" + (v === "primary" ? " is-primary" : "")
  }, v);
  const rows = [{
    name: "V1 · The console",
    sub: "chat-first",
    c: "primary",
    o: "rail",
    d: "inline in chat"
  }, {
    name: "V2 · The tower",
    sub: "loops-first",
    c: "docked plate",
    o: "primary",
    d: "strip actions"
  }, {
    name: "V3 · The gate",
    sub: "decisions-first",
    c: "docked plate",
    o: "rail",
    d: "primary"
  }];
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-pad"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-mx"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-mx-row mcc-mx-head"
  }, /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("span", null, "command \xB7 text in"), /*#__PURE__*/React.createElement("span", null, "observe \xB7 the loops"), /*#__PURE__*/React.createElement("span", null, "decide \xB7 the gate")), rows.map(r => /*#__PURE__*/React.createElement("div", {
    key: r.name,
    className: "mcc-mx-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-mx-name"
  }, r.name, /*#__PURE__*/React.createElement("span", {
    className: "mcc-mx-sub"
  }, r.sub)), cell(r.c), cell(r.o), cell(r.d)))), /*#__PURE__*/React.createElement("p", {
    className: "mcc-caption"
  }, "The architect runs three loops, but a screen has one center. The honest move is to pick \xB7 and keep the other two one glance or one keystroke away. The philosophy leans V3: unsupervised hours are the score, so the human's screen should be sorted by the decisions only a human can make."));
}

// ── V1 · The console · the conversation is the control surface ───────────
function MccAttnConsole() {
  const w3 = WK_ITEMS.find(i => i.id === "w3");
  return /*#__PURE__*/React.createElement(MccAttnFrame, {
    screenLabel: "Console \xB7 chat-first"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-attn-row",
    style: {
      gridTemplateColumns: "minmax(0, 1fr) 360px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-console",
    "data-screen-label": "Maestro console"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-chat-feed mcc-console-feed"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-msg bv-msg--assistant"
  }, "Morning. Overnight: the nightly digest ran 31m unsupervised. Two things wait at your gate \xB7 transcripts (clean, 14 tests) and the Linear import (needs a scope from you)."), /*#__PURE__*/React.createElement("div", {
    className: "bv-msg bv-msg--user"
  }, "prioritize the API work, and show me what genesis is doing"), /*#__PURE__*/React.createElement(McRunCard, {
    msg: w3.chat[1]
  }), /*#__PURE__*/React.createElement("div", {
    className: "bv-msg bv-msg--assistant"
  }, "Queue reordered \xB7 the relay handoff moves up. Genesis is live above: reducing the NDJSON stream to the phase machine, 9 tests green so far. Approve the transcripts branch when you have a minute and I'll build phase 2 on top of it tonight.")), /*#__PURE__*/React.createElement("div", {
    className: "bv-chat-composer-wrap",
    style: {
      padding: "8px 20px 16px"
    }
  }, /*#__PURE__*/React.createElement(MccPromptPlate, {
    className: "mcc-prompt--glass",
    placeholder: "Message maestro \xB7 dispatch, ask, steer\u2026"
  }))), /*#__PURE__*/React.createElement(MccLoopsRail, null)));
}

// ── V2 · The tower · the loops are the screen ────────────────────────────
const MCC_AT_STRIPS = [{
  group: "Needs you",
  hint: "The only rows a human must touch",
  rows: [{
    kind: "gate",
    title: "Persist run transcripts",
    crumb: "hawthorne-core",
    line: "run/7c2f1a · judge passed · 14 tests",
    t: "12m",
    action: "Approve"
  }, {
    kind: "warn",
    title: "Import Linear cycles",
    crumb: "hawthorne-db",
    line: "Worker paused · needs a Linear API scope",
    t: "41m",
    action: "Grant"
  }]
}, {
  group: "Running",
  hint: "Live loops · narration updates in place",
  rows: [{
    kind: "live",
    title: "Reduce the NDJSON stream",
    crumb: "@genesis/projection",
    line: "Edit reducer.ts · bun test 9 passed",
    t: "2h 14m",
    live: true
  }, {
    kind: "live",
    title: "Reconcile May invoices",
    crumb: "bookkeeping",
    line: "Matching 41 of 63 · cloud sandbox",
    t: "6m",
    live: true
  }]
}, {
  group: "Holding",
  hint: "Maestro's queue · touches itself on the next tick",
  rows: [{
    kind: "queued",
    title: "Resume sessions (Phase 2)",
    crumb: "@genesis/projection",
    line: "Holding at capacity · 2/2 worktrees",
    t: "2h"
  }, {
    kind: "queued",
    title: "Maestro relay, phase 1b",
    crumb: "hawthorne-engine",
    line: "First action attached · any session can pick it up",
    t: "1d"
  }]
}];
function MccAttnTower() {
  return /*#__PURE__*/React.createElement(MccAttnFrame, {
    screenLabel: "Tower \xB7 loops-first"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-tower",
    "data-screen-label": "Session strips"
  }, MCC_AT_STRIPS.map(g => /*#__PURE__*/React.createElement(React.Fragment, {
    key: g.group
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-list-group"
  }, g.group, /*#__PURE__*/React.createElement("span", {
    className: "mc-group-hint"
  }, g.hint)), g.rows.map(r => /*#__PURE__*/React.createElement("div", {
    key: r.title,
    className: "mcc-strip"
  }, /*#__PURE__*/React.createElement(MccLoopDot, {
    kind: r.kind === "queued" ? "queued" : r.kind
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-strip-title"
  }, r.title), /*#__PURE__*/React.createElement("span", {
    className: "mcc-strip-crumb"
  }, r.crumb), /*#__PURE__*/React.createElement("span", {
    className: "mcc-strip-line" + (r.live ? " mcc-caret" : "")
  }, r.line), /*#__PURE__*/React.createElement("span", {
    className: "mcc-loops-t"
  }, r.t), r.action ? /*#__PURE__*/React.createElement(DsButton, {
    size: "sm"
  }, r.action) : /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    variant: "secondary"
  }, "Open")))))), /*#__PURE__*/React.createElement(MccCmdDock, null));
}

// ── V3 · The gate · sorted by what only a human can do ───────────────────
function MccAttnGate() {
  return /*#__PURE__*/React.createElement(MccAttnFrame, {
    screenLabel: "Gate \xB7 decisions-first"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-attn-row",
    style: {
      gridTemplateColumns: "minmax(0, 1fr) 360px"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-gatecol",
    "data-screen-label": "Decision queue"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-gate-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-plane-title"
  }, "Your gate"), /*#__PURE__*/React.createElement("span", {
    className: "mcc-plane-sub"
  }, "2 decisions \xB7 everything else is maestro's problem")), /*#__PURE__*/React.createElement("div", {
    className: "bv-card mcc-gatecard"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-card-top"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-breadcrumb"
  }, /*#__PURE__*/React.createElement("b", null, "hawthorne"), " \u203A hawthorne-core"), /*#__PURE__*/React.createElement("span", {
    className: "mc-card-time"
  }, "12m")), /*#__PURE__*/React.createElement("div", {
    className: "mc-card-title"
  }, "Persist run transcripts on the Run record"), /*#__PURE__*/React.createElement("div", {
    className: "mcc-look-ran"
  }, "ran ", /*#__PURE__*/React.createElement("b", null, "2h 14m unsupervised"), " \xB7 41 events \xB7 judge passed \xB7 14 tests added"), /*#__PURE__*/React.createElement("ul", {
    className: "mcc-look-list"
  }, /*#__PURE__*/React.createElement("li", null, "Persisted on the Run record, not the session \xB7 survives restarts"), /*#__PURE__*/React.createElement("li", null, "Replay covered by tests instead of snapshotting live state")), /*#__PURE__*/React.createElement("div", {
    className: "mc-detail-actions"
  }, /*#__PURE__*/React.createElement(DsButton, {
    size: "sm"
  }, /*#__PURE__*/React.createElement(IcCheck, {
    size: 16
  }), "Approve"), /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    variant: "secondary"
  }, "Send back"), /*#__PURE__*/React.createElement("span", {
    className: "mcc-look-timer"
  }, "a 90-second look"))), /*#__PURE__*/React.createElement("div", {
    className: "bv-card mcc-gatecard"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-card-top"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-breadcrumb"
  }, /*#__PURE__*/React.createElement("b", null, "hawthorne"), " \u203A hawthorne-db"), /*#__PURE__*/React.createElement("span", {
    className: "mc-card-time"
  }, "41m")), /*#__PURE__*/React.createElement("div", {
    className: "mc-card-title"
  }, "Import Linear cycles into the object model"), /*#__PURE__*/React.createElement("div", {
    className: "mcc-look-ran"
  }, "worker paused \xB7 ", /*#__PURE__*/React.createElement("b", null, "needs a Linear API scope"), " before the import can run"), /*#__PURE__*/React.createElement("div", {
    className: "mc-detail-actions"
  }, /*#__PURE__*/React.createElement(DsButton, {
    size: "sm"
  }, "Grant access"), /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    variant: "secondary"
  }, "Park it"), /*#__PURE__*/React.createElement("span", {
    className: "mcc-look-timer"
  }, "unblocks 1 worker"))), /*#__PURE__*/React.createElement("div", {
    className: "mcc-allclear"
  }, /*#__PURE__*/React.createElement(IcCheck, {
    size: 14
  }), "Nothing else needs you \xB7 maestro holds 2 live loops and the queue \xB7 next tick 13m")), /*#__PURE__*/React.createElement(MccLoopsRail, null)), /*#__PURE__*/React.createElement(MccCmdDock, {
    placeholder: "Anything beyond approve/deny \xB7 say it, maestro routes it\u2026"
  }));
}
Object.assign(window, {
  MccAttnSchema,
  MccAttnConsole,
  MccAttnTower,
  MccAttnGate,
  MccLoopsRail,
  MccCmdDock,
  MccLoopDot,
  MCC_AT_LOOPS
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/ConceptAttention.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/ConceptFeedback.jsx
try { (() => {
// Feedback · handed to the loop, not fired into a void.
// The product's thesis is that the loop CLOSES: work is a noun with a state
// and a receipt, and the living signal is the Undertow/tidepool. So feedback
// is a tracked THREAD you can watch. One has already been pulled into a live
// maestro session (Undertow treatment) · the moment that proves the thesis.
// A right-docked drawer over the dimmed app. Reuses globals (McIcon, IcX,
// IcCheck, IcArrowRight if present).

const IcBulb2 = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M9 18h6"
}), /*#__PURE__*/React.createElement("path", {
  d: "M10 22h4"
}), /*#__PURE__*/React.createElement("path", {
  d: "M12 2a7 7 0 0 0-4 12.7c.6.5 1 1.3 1 2.1V17h6v-.2c0-.8.4-1.6 1-2.1A7 7 0 0 0 12 2Z"
}));
const IcBug2 = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("rect", {
  x: "8",
  y: "6",
  width: "8",
  height: "12",
  rx: "4"
}), /*#__PURE__*/React.createElement("path", {
  d: "M8 10H4M8 14H3M16 10h4M16 14h5M12 4V2M9 5 7.5 3.5M15 5l1.5-1.5"
}));
const IcHeart2 = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M19 14c1.5-1.5 3-3.3 3-5.5A4.5 4.5 0 0 0 12 6 4.5 4.5 0 0 0 2 8.5C2 12 5 14 12 20c2.5-2.1 4.6-3.9 6-5.5Z"
}));
const IcSend = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "m22 2-7 20-4-9-9-4Z"
}), /*#__PURE__*/React.createElement("path", {
  d: "M22 2 11 13"
}));
const IcMsg2 = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"
}));
const IcArrow = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M5 12h14M13 6l6 6-6 6"
}));
const FB_TYPES2 = [{
  id: "idea",
  label: "Idea",
  icon: /*#__PURE__*/React.createElement(IcBulb2, null),
  ph: "What would make the loop work better for you?"
}, {
  id: "issue",
  label: "Issue",
  icon: /*#__PURE__*/React.createElement(IcBug2, null),
  ph: "What went wrong · and what did you expect instead?"
}, {
  id: "praise",
  label: "Praise",
  icon: /*#__PURE__*/React.createElement(IcHeart2, null),
  ph: "What's landing well? maestro likes to know too."
}];

// Your feedback so far · each a noun with a state, newest first.
const FB_THREADS_SEED = [{
  id: "fb-live",
  live: true,
  type: "idea",
  title: "Auto-retry blocked imports once I grant the scope",
  status: "live",
  statusLabel: "maestro picked this up",
  detail: "drafting in ops / feedback-triage · 6m unsupervised",
  time: "1h"
}, {
  id: "fb2",
  type: "idea",
  title: "Let the gate queue group by folder, not just by time",
  status: "triage",
  statusLabel: "With the team",
  detail: "Theo replied 2d ago",
  time: "3d"
}, {
  id: "fb3",
  type: "issue",
  title: "Dark mode washed out the run timeline ticks",
  status: "ship",
  statusLabel: "Shipped",
  detail: "v4.2 · last week",
  time: "1w"
}, {
  id: "fb4",
  type: "idea",
  title: "A shortcut to jump straight to “Needs you”",
  status: "log",
  statusLabel: "Logged",
  detail: "in the backlog",
  time: "2w"
}];
function FbDot({
  status
}) {
  if (status === "live") return /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide fb-thread-dot",
    style: {
      width: 12,
      height: 12
    }
  });
  const color = status === "ship" ? "var(--bv-success)" : status === "triage" ? "var(--bv-blue)" : "var(--bv-gray-400)";
  return /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot fb-thread-dot",
    style: {
      width: 9,
      height: 9,
      background: color
    }
  });
}
function FbThread({
  t,
  fresh
}) {
  const inner = /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "fb-thread" + (t.live ? " fb-thread--live" : "") + (fresh ? " fb-thread--fresh" : "")
  }, /*#__PURE__*/React.createElement(FbDot, {
    status: t.status
  }), /*#__PURE__*/React.createElement("span", {
    className: "fb-thread-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "fb-thread-top"
  }, /*#__PURE__*/React.createElement("span", {
    className: "fb-thread-title"
  }, t.title), /*#__PURE__*/React.createElement("span", {
    className: "fb-thread-time"
  }, t.time)), /*#__PURE__*/React.createElement("span", {
    className: "fb-thread-meta"
  }, /*#__PURE__*/React.createElement("span", {
    className: "fb-thread-status fb-thread-status--" + t.status
  }, t.statusLabel), /*#__PURE__*/React.createElement("span", {
    className: "fb-thread-detail"
  }, t.detail)), t.live && /*#__PURE__*/React.createElement("span", {
    className: "fb-live-link"
  }, "Open session", /*#__PURE__*/React.createElement(IcArrow, null))));
  // The live thread wears the Undertow · the product's hero living signal.
  if (t.live) {
    return /*#__PURE__*/React.createElement(DsUndertow, {
      style: {
        margin: "4px 0"
      }
    }, inner);
  }
  return inner;
}
function MccFeedback({
  open,
  onClose,
  context = "Maestro"
}) {
  const [type, setType] = React.useState("idea");
  const [text, setText] = React.useState("");
  const [attach, setAttach] = React.useState(true);
  const [threads, setThreads] = React.useState(FB_THREADS_SEED);
  const [freshId, setFreshId] = React.useState(null);
  const taRef = React.useRef(null);
  React.useEffect(() => {
    if (!open) return;
    setText("");
    setType("idea");
    setAttach(true);
    setThreads(FB_THREADS_SEED);
    setFreshId(null);
    const t = setTimeout(() => taRef.current && taRef.current.focus(), 80);
    const onKey = e => {
      if (e.key === "Escape") onClose && onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => {
      clearTimeout(t);
      window.removeEventListener("keydown", onKey);
    };
  }, [open]);
  if (!open) return null;
  const active = FB_TYPES2.find(t => t.id === type) || FB_TYPES2[0];
  const send = () => {
    const body = text.trim();
    if (!body) {
      taRef.current && taRef.current.focus();
      return;
    }
    const id = "fb-new-" + Date.now();
    // Lands as a tracked thread · logging, with the tidepool · then settles.
    const fresh = {
      id,
      type,
      title: body.length > 78 ? body.slice(0, 77) + "…" : body,
      status: "live",
      statusLabel: "Routing to the team",
      detail: attach ? "maestro is reading it · " + context : "maestro is reading it",
      time: "now"
    };
    setThreads(prev => [fresh, ...prev]);
    setFreshId(id);
    setText("");
    // It settles into "Logged" · the loop acknowledged it.
    setTimeout(() => {
      setThreads(prev => prev.map(t => t.id === id ? {
        ...t,
        status: "log",
        statusLabel: "Logged",
        detail: "the team has it · maestro tagged it " + type
      } : t));
    }, 1700);
  };
  const onKeyDown = e => {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      send();
    }
  };
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "fb-scrim",
    onClick: onClose
  }), /*#__PURE__*/React.createElement("aside", {
    className: "fb-drawer",
    "data-screen-label": "Feedback drawer",
    role: "dialog",
    "aria-modal": "true",
    "aria-label": "Feedback"
  }, /*#__PURE__*/React.createElement("header", {
    className: "fb-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "fb-head-glyph"
  }, /*#__PURE__*/React.createElement(IcMsg2, {
    size: 18
  })), /*#__PURE__*/React.createElement("div", {
    className: "fb-head-main"
  }, /*#__PURE__*/React.createElement("div", {
    className: "fb-title"
  }, "Feedback"), /*#__PURE__*/React.createElement("div", {
    className: "fb-sub"
  }, "Hand it to the loop \xB7 the team reads it, and so does maestro.")), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "fb-x",
    "aria-label": "Close",
    onClick: onClose
  }, /*#__PURE__*/React.createElement(IcX, {
    size: 17
  }))), /*#__PURE__*/React.createElement("div", {
    className: "fb-body"
  }, /*#__PURE__*/React.createElement("div", {
    className: "fb-compose"
  }, /*#__PURE__*/React.createElement("div", {
    className: "fb-compose-field"
  }, /*#__PURE__*/React.createElement("textarea", {
    ref: taRef,
    className: "fb-text",
    value: text,
    placeholder: active.ph,
    onChange: e => setText(e.target.value),
    onKeyDown: onKeyDown
  }), /*#__PURE__*/React.createElement("div", {
    className: "fb-tray"
  }, /*#__PURE__*/React.createElement("div", {
    className: "fb-types"
  }, FB_TYPES2.map(t => /*#__PURE__*/React.createElement("button", {
    key: t.id,
    type: "button",
    className: "fb-type" + (type === t.id ? " is-active" : ""),
    onClick: () => setType(t.id)
  }, React.cloneElement(t.icon, {
    size: 14
  }), t.label))), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "fb-send",
    "aria-label": "Send feedback",
    disabled: !text.trim(),
    onClick: send
  }, /*#__PURE__*/React.createElement(IcSend, {
    size: 16
  })))), /*#__PURE__*/React.createElement("label", {
    className: "fb-ctx"
  }, /*#__PURE__*/React.createElement("span", {
    className: "fb-ctx-check" + (attach ? " is-on" : ""),
    onClick: () => setAttach(!attach),
    role: "checkbox",
    "aria-checked": attach
  }, /*#__PURE__*/React.createElement(IcCheck, {
    size: 12
  })), /*#__PURE__*/React.createElement("span", {
    className: "fb-ctx-label"
  }, "Attach this screen \xB7 a snapshot + ", /*#__PURE__*/React.createElement("code", null, context), " context"))), /*#__PURE__*/React.createElement("div", {
    className: "fb-threads"
  }, /*#__PURE__*/React.createElement("div", {
    className: "fb-threads-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "fb-threads-label"
  }, "Your feedback"), /*#__PURE__*/React.createElement("span", {
    className: "fb-threads-note"
  }, threads.length, " threads \xB7 1 in a session")), threads.map(t => /*#__PURE__*/React.createElement(FbThread, {
    key: t.id,
    t: t,
    fresh: t.id === freshId
  }))))));
}
Object.assign(window, {
  MccFeedback
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/ConceptFeedback.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/ConceptFsTabs.jsx
try { (() => {
// Concepts canvas · the filesystem surfaces: tabs + the file pane.
// The workspace root IS a location on the FS, but nothing in the UI lets
// you walk it as files. Two placements for the missing pair (a tab strip
// where chats live and files open, plus a browsable file pane):
//   A · inside the right panel · the session keeps its geography
//   B · in the chrome · app-level tabs under the header, FS pane at the
//       layout's right edge, the session panel untouched.

const IcFtChev = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "m9 18 6-6-6-6"
}));

// ── The documents · every file is a contract or a receipt ────────────────
const MCC_FS_DOCS = {
  "broomva.md": {
    crumb: "~ / Broomva / broomva.md",
    title: "Broomva · the workspace contract",
    chips: ["kind: workspace", "runner: claude", "gate: human-approve"],
    body: ["The meta-workspace. Every folder below this file is work at some scale; what's written here cascades down the tree until a deeper contract overrides it.", {
      list: ["Defaults: worktree-per-run, judge on every exit", "Budgets are granted at spawn · never ambient", "Receipts land beside the work, sessions in the engine room"]
    }]
  },
  "hawthorne.md": {
    crumb: "~ / Broomva / hawthorne / hawthorne.md",
    title: "Hawthorne · durable agent infrastructure",
    chips: ["kind: initiative", "owner: you", "budget: 24h/wk unsupervised"],
    body: ["North star: an agent session you can leave overnight and trust in the morning. The unsupervised hour is the unit of progress.", {
      list: ["Current focus: persist run transcripts (at the gate)", "Unblock the Linear import · needs an API scope", "Spec the TunnelRunner relay protocol (V2)"]
    }]
  },
  "spec.md": {
    crumb: "~ / Broomva / hawthorne / hawthorne-core / spec.md",
    title: "Persist run transcripts on the Run record",
    chips: ["kind: project", "owner: maestro", "budget: 8h unsupervised", "gate: human-approve"],
    body: ["Reviews should never need the live session. Persist the full transcript on each Run so any session · yours or a worker's · can replay it cold.", {
      list: ["Persist on the Run record, not the session · survives worker restarts", "Replay covered by 14 tests instead of snapshotting live state", "Compression deferred · transcripts stay small until multi-day runs land"]
    }]
  },
  "prior-art.md": {
    crumb: "… / hawthorne-core / notes / prior-art.md",
    title: "Survey · resumable sessions in OSS agents",
    chips: ["written by: scout", "47m unsupervised"],
    body: ["Six frameworks surveyed. The durable pattern everywhere: event-sourced transcripts plus idempotent tool replay · snapshots rot, logs don't.", {
      list: ["Replay beats snapshot in all six", "Fork-at-event needs stable event ids from day one", "Folded into the reducer design by claude"]
    }]
  },
  "api-decisions.md": {
    crumb: "… / hawthorne-core / notes / api-decisions.md",
    title: "Resume API · decisions",
    chips: ["decided with: you", "2 looks"],
    body: ["Two surfaces only. resume(sessionId) rehydrates from the persisted transcript; fork(sessionId, at) branches a new session at any event.", {
      list: ["Forks share the parent's budget, capped · your call", "No partial rehydration: all or nothing", "Fork is the undo · there is no rewind"]
    }]
  },
  "run-7c2f1a.md": {
    crumb: "… / hawthorne-core / runs / run-7c2f1a.md",
    title: "Receipt · run/7c2f1a",
    chips: ["judge: checks passed", "14 tests added", "2h 14m unsupervised"],
    body: ["Ran to the gate. The branch is the receipt · the worktree was reclaimed after the run; this file is what the judge saw.", {
      list: ["41 events · 2 looks requested, 0 needed", "Branch run/7c2f1a awaiting your approve", "Transcript persisted on the Run record (dogfood)"]
    }]
  }
};
function MccFsDoc({
  path
}) {
  const d = MCC_FS_DOCS[path];
  if (!d) return null;
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-doc"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-doc-inner"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-doc-crumb"
  }, d.crumb), /*#__PURE__*/React.createElement("h1", {
    className: "mcc-doc-title"
  }, d.title), /*#__PURE__*/React.createElement("div", {
    className: "mcc-fm-chips"
  }, d.chips.map(c => /*#__PURE__*/React.createElement("span", {
    key: c,
    className: "mc-receipt"
  }, c))), d.body.map((b, i) => typeof b === "string" ? /*#__PURE__*/React.createElement("p", {
    key: i,
    className: "mcc-doc-p"
  }, b) : /*#__PURE__*/React.createElement("ul", {
    key: i,
    className: "mcc-doc-list"
  }, b.list.map(l => /*#__PURE__*/React.createElement("li", {
    key: l
  }, l))))));
}

// ── The file pane ─────────────────────────────────────────────────────────
function MccFilePane({
  entries,
  openPath,
  onOpen,
  label,
  location,
  worktree
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-ftree",
    "data-screen-label": "File pane"
  }, label && /*#__PURE__*/React.createElement("div", {
    className: "mcc-ftree-label"
  }, label), location && /*#__PURE__*/React.createElement("div", {
    className: "mcc-ftree-loc"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-ftree-loc-path"
  }, location), worktree && /*#__PURE__*/React.createElement("span", {
    className: "mc-receipt"
  }, worktree)), entries.map(e => /*#__PURE__*/React.createElement("button", {
    key: e.path || e.name + e.depth,
    type: "button",
    className: "mcc-ftree-row" + (e.path && e.path === openPath ? " is-active" : "") + (e.path ? "" : " is-folder"),
    style: {
      paddingLeft: 8 + e.depth * 14
    },
    onClick: e.path ? () => onOpen(e.path) : undefined
  }, e.kind === "folder" ? /*#__PURE__*/React.createElement(IcFolderOpen, {
    size: 13
  }) : /*#__PURE__*/React.createElement(IcDoc, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-ftree-name"
  }, e.name), e.live && /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 11,
      height: 11,
      marginLeft: "auto"
    }
  }))));
}
const MCC_FT_CORE = [{
  name: "spec.md",
  path: "spec.md",
  depth: 0,
  kind: "file"
}, {
  name: "notes",
  depth: 0,
  kind: "folder"
}, {
  name: "prior-art.md",
  path: "prior-art.md",
  depth: 1,
  kind: "file"
}, {
  name: "api-decisions.md",
  path: "api-decisions.md",
  depth: 1,
  kind: "file"
}, {
  name: "runs",
  depth: 0,
  kind: "folder"
}, {
  name: "run-7c2f1a.md",
  path: "run-7c2f1a.md",
  depth: 1,
  kind: "file"
}];
const MCC_FT_ROOT = [{
  name: "broomva.md",
  path: "broomva.md",
  depth: 0,
  kind: "file"
}, {
  name: "hawthorne",
  depth: 0,
  kind: "folder"
}, {
  name: "hawthorne.md",
  path: "hawthorne.md",
  depth: 1,
  kind: "file"
}, {
  name: "hawthorne-core",
  depth: 1,
  kind: "folder"
}, {
  name: "spec.md",
  path: "spec.md",
  depth: 2,
  kind: "file"
}, {
  name: "prior-art.md",
  path: "prior-art.md",
  depth: 2,
  kind: "file"
}, {
  name: "api-decisions.md",
  path: "api-decisions.md",
  depth: 2,
  kind: "file"
}, {
  name: "run-7c2f1a.md",
  path: "run-7c2f1a.md",
  depth: 2,
  kind: "file"
}, {
  name: "hawthorne-db",
  depth: 1,
  kind: "folder"
}, {
  name: "genesis",
  depth: 0,
  kind: "folder",
  live: true
}, {
  name: "ops",
  depth: 0,
  kind: "folder",
  live: true
}];

// ── The tab strip ─────────────────────────────────────────────────────────
function MccFTabs({
  tabs,
  act,
  setAct,
  onClose,
  onNew
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-ftabs",
    "data-screen-label": "Tab strip"
  }, tabs.map((t, i) => /*#__PURE__*/React.createElement("button", {
    key: t.key,
    type: "button",
    className: "mcc-ftab" + (i === act ? " is-active" : ""),
    onClick: () => setAct(i),
    title: t.title
  }, t.glyph, /*#__PURE__*/React.createElement("span", {
    className: "mcc-ftab-name"
  }, t.label), t.closable && /*#__PURE__*/React.createElement("span", {
    className: "mcc-ftab-x",
    role: "button",
    "aria-label": "Close " + t.label,
    onClick: e => {
      e.stopPropagation();
      onClose(i);
    }
  }, /*#__PURE__*/React.createElement(IcX, {
    size: 11
  })))), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-prompt-iconbtn",
    style: {
      width: 26,
      height: 26
    },
    "aria-label": "New chat",
    title: "New chat",
    onClick: onNew
  }, /*#__PURE__*/React.createElement(IcxPlus, {
    size: 14
  })));
}

// Tab-state helper shared by both frames.
function useMccFTabs(baseTabs) {
  const [open, setOpen] = React.useState([]); // file paths + chat ids
  const [act, setAct] = React.useState(0);
  const tabs = [...baseTabs, ...open.map(o => o.kind === "file" ? {
    key: o.path,
    kind: "file",
    path: o.path,
    label: o.path.split("/").pop(),
    glyph: /*#__PURE__*/React.createElement(IcDoc, {
      size: 13
    }),
    closable: true,
    title: MCC_FS_DOCS[o.path] ? MCC_FS_DOCS[o.path].crumb : o.path
  } : {
    key: o.id,
    kind: "chat",
    label: "new chat",
    glyph: /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot bv-dot--pulse",
      style: {
        background: "var(--bv-info)"
      }
    }),
    closable: true,
    title: "A fresh session in this folder"
  })];
  const openFile = path => {
    const idx = tabs.findIndex(t => t.kind === "file" && t.path === path);
    if (idx >= 0) {
      setAct(idx);
      return;
    }
    setOpen(o => [...o, {
      kind: "file",
      path
    }]);
    setAct(tabs.length);
  };
  const newChat = () => {
    setOpen(o => [...o, {
      kind: "chat",
      id: "chat-" + Date.now()
    }]);
    setAct(tabs.length);
  };
  const close = i => {
    const oi = i - baseTabs.length;
    if (oi < 0) return;
    setOpen(o => o.filter((_, j) => j !== oi));
    setAct(a => a === i ? Math.max(0, i - 1) : a > i ? a - 1 : a);
  };
  return {
    tabs,
    act,
    setAct,
    openFile,
    newChat,
    close
  };
}
function MccFsNewChat() {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-newchat"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-newchat-inner"
  }, /*#__PURE__*/React.createElement("span", {
    className: "bv-greeting-title"
  }, "A fresh session in this folder"), /*#__PURE__*/React.createElement("span", {
    className: "bv-greeting-sub"
  }, "It inherits the contract \xB7 budget, gate, scope \xB7 from the folder it starts in."), /*#__PURE__*/React.createElement(MccPromptPlate, {
    className: "mcc-prompt--glass",
    placeholder: "Tell this folder what's next\u2026"
  })));
}

// ── A · Tabs inside the right panel ──────────────────────────────────────
function MccFsTabsPanel() {
  const noop = () => {};
  const w1 = WK_ITEMS.find(i => i.id === "w1");
  const base = [{
    key: "chat",
    kind: "chat-w1",
    label: "persist run transcripts",
    closable: false,
    glyph: /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: "var(--bv-blue-accent)"
      }
    }),
    title: "The work item's session"
  }];
  const {
    tabs,
    act,
    setAct,
    openFile,
    newChat,
    close
  } = useMccFTabs(base);
  const cur = tabs[act] || tabs[0];
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-fill"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-app"
  }, /*#__PURE__*/React.createElement(MccTcSidebar, {
    scope: "core",
    setScope: noop
  }), /*#__PURE__*/React.createElement("div", {
    className: "bv-main"
  }, /*#__PURE__*/React.createElement(McvTopBar, {
    theme: "light",
    onToggleTheme: noop,
    onOpenMaestro: noop,
    onWake: noop,
    waking: false,
    canWake: true,
    onShowIdea: noop,
    counts: {
      needYou: 1,
      stuck: 1
    },
    workers: ["claude", "bookkeeper"],
    wakes: MCC_TICK_WAKES,
    items: WK_ITEMS,
    onAttention: noop,
    onCommand: noop
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-merged-row",
    style: {
      gridTemplateColumns: "minmax(0, 1fr) 680px"
    }
  }, /*#__PURE__*/React.createElement(MccTcPlane, {
    scope: "core"
  }), /*#__PURE__*/React.createElement("aside", {
    className: "mcc-live-panel",
    "data-screen-label": "Tabbed panel + file pane"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-head",
    style: {
      paddingBottom: 10
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-detail-breadcrumb"
  }, "hawthorne / hawthorne-core")), /*#__PURE__*/React.createElement(MccFTabs, {
    tabs: tabs,
    act: act,
    setAct: setAct,
    onClose: close,
    onNew: newChat
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-ftab-row"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-ftab-main"
  }, cur.kind === "chat-w1" && /*#__PURE__*/React.createElement(McChat, {
    item: w1,
    extra: {},
    typing: false,
    onSend: noop
  }), cur.kind === "file" && /*#__PURE__*/React.createElement(MccFsDoc, {
    path: cur.path
  }), cur.kind === "chat" && /*#__PURE__*/React.createElement(MccFsNewChat, null)), /*#__PURE__*/React.createElement(MccFilePane, {
    entries: MCC_FT_CORE,
    label: "hawthorne-core/",
    openPath: cur.kind === "file" ? cur.path : null,
    onOpen: openFile
  })))))));
}

// ── B · Tabs in the chrome, FS pane at the layout edge ───────────────────
function MccFsTabsChrome() {
  const noop = () => {};
  const base = [{
    key: "mc",
    kind: "mc",
    label: "Maestro",
    closable: false,
    glyph: /*#__PURE__*/React.createElement(IcBoard, {
      size: 13
    }),
    title: "The plane · work grouped by attention"
  }];
  const {
    tabs,
    act,
    setAct,
    openFile,
    newChat,
    close
  } = useMccFTabs(base);
  const cur = tabs[act] || tabs[0];
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-fill"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-app"
  }, /*#__PURE__*/React.createElement(MccTcSidebar, {
    scope: "core",
    setScope: noop
  }), /*#__PURE__*/React.createElement("div", {
    className: "bv-main"
  }, /*#__PURE__*/React.createElement(McvTopBar, {
    theme: "light",
    onToggleTheme: noop,
    onOpenMaestro: noop,
    onWake: noop,
    waking: false,
    canWake: true,
    onShowIdea: noop,
    counts: {
      needYou: 1,
      stuck: 1
    },
    workers: ["claude", "bookkeeper"],
    wakes: MCC_TICK_WAKES,
    items: WK_ITEMS,
    onAttention: noop,
    onCommand: noop
  }), /*#__PURE__*/React.createElement(MccFTabs, {
    tabs: tabs,
    act: act,
    setAct: setAct,
    onClose: close,
    onNew: newChat
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-fsrow"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-fsmain"
  }, cur.kind === "mc" && /*#__PURE__*/React.createElement("div", {
    className: "mcc-merged-row",
    style: {
      gridTemplateColumns: "minmax(0, 1fr) 400px"
    }
  }, /*#__PURE__*/React.createElement(MccTcPlane, {
    scope: "core"
  }), /*#__PURE__*/React.createElement(MccTcPanel, {
    scope: "core",
    setScope: noop
  })), cur.kind === "file" && /*#__PURE__*/React.createElement(MccFsDoc, {
    path: cur.path
  }), cur.kind === "chat" && /*#__PURE__*/React.createElement(MccFsNewChat, null)), /*#__PURE__*/React.createElement(MccFilePane, {
    entries: MCC_FT_ROOT,
    label: "Broomva/",
    openPath: cur.kind === "file" ? cur.path : null,
    onOpen: openFile
  })))));
}
Object.assign(window, {
  MccFsTabsPanel,
  MccFsTabsChrome,
  MccFilePane,
  MccFsDoc,
  MccFsNewChat,
  MccFTabs,
  useMccFTabs,
  MCC_FT_ROOT,
  MCC_FT_CORE
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/ConceptFsTabs.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/ConceptHistory.jsx
try { (() => {
// Concept · the History page. The full list of sessions: yours AND the loop's.
// Philosophy: a session is a projection of work, so History is the one place the
// session-list inheritance belongs. One live frame, four organizing axes
// (day · work · agent · lineage) + a you/autonomous filter · the axes ARE the
// variations. Built on the canonical BvNav so the chrome matches the app.

// agent → avatar colour
const HIST_AGENT = {
  maestro: {
    color: "var(--bv-info)",
    face: "orch"
  },
  claude: {
    color: "var(--bv-blue)"
  },
  bookkeeper: {
    color: "var(--bv-purple, #7c6cf0)"
  },
  scout: {
    color: "var(--bv-gray-500)"
  },
  you: {
    color: "var(--bv-gray-600)"
  }
};

// state → dot tone
const HIST_STATE = {
  live: {
    color: "var(--bv-info)",
    plain: "running"
  },
  done: {
    color: "var(--bv-success)",
    plain: "done"
  },
  halt: {
    color: "var(--bv-blue-accent)",
    plain: "needed you"
  },
  blocked: {
    color: "var(--bv-warning)",
    plain: "stuck"
  }
};
const HIST_SESSIONS = [{
  id: "s1",
  title: "Implement resumable sessions",
  kind: "auto",
  state: "live",
  agent: "claude",
  parent: "maestro",
  folder: "hawthorne / hawthorne-core",
  dur: "2h 14m",
  unsup: true,
  events: 41,
  day: "Today",
  time: "2m"
}, {
  id: "s2",
  title: "Review the API design",
  kind: "you",
  state: "halt",
  agent: "claude",
  parent: "you",
  folder: "hawthorne / hawthorne-core",
  dur: "halted · 2 looks",
  unsup: false,
  events: 38,
  day: "Today",
  time: "18m"
}, {
  id: "s3",
  title: "Reconcile May invoices",
  kind: "auto",
  state: "live",
  agent: "bookkeeper",
  parent: "maestro",
  folder: "ops / bookkeeping",
  dur: "1h 02m",
  unsup: true,
  events: 27,
  day: "Today",
  time: "6m",
  where: "cloud sandbox"
}, {
  id: "s4",
  title: "Survey prior art on resumability",
  kind: "auto",
  state: "done",
  agent: "scout",
  parent: "claude",
  parentSession: "s1",
  folder: "hawthorne / hawthorne-core",
  dur: "47m",
  unsup: true,
  events: 61,
  day: "Today",
  time: "1h"
}, {
  id: "s5",
  title: "What's blocking the launch?",
  kind: "you",
  state: "done",
  agent: "claude",
  parent: "you",
  folder: "hawthorne",
  dur: "4m",
  unsup: false,
  events: 12,
  day: "Today",
  time: "1h"
}, {
  id: "s6",
  title: "Import Linear cycles into the store",
  kind: "auto",
  state: "blocked",
  agent: "claude",
  parent: "maestro",
  folder: "hawthorne / hawthorne-db",
  dur: "41m · missing scope",
  unsup: false,
  events: 19,
  day: "Today",
  time: "41m"
}, {
  id: "s7",
  title: "Nightly digest",
  kind: "auto",
  state: "done",
  agent: "maestro",
  parent: "maestro",
  folder: "ops / nightly-digest",
  dur: "31m",
  unsup: true,
  events: 33,
  day: "Today",
  time: "02:00",
  routine: true
}, {
  id: "s8",
  title: "Morning briefing",
  kind: "auto",
  state: "done",
  agent: "maestro",
  parent: "maestro",
  folder: "meta · across workspaces",
  dur: "8m",
  unsup: true,
  events: 14,
  day: "Today",
  time: "07:30",
  routine: true
}, {
  id: "s9",
  title: "Draft the relay protocol spec",
  kind: "you",
  state: "done",
  agent: "claude",
  parent: "you",
  folder: "hawthorne / hawthorne-core",
  dur: "22m",
  unsup: false,
  events: 22,
  day: "Yesterday",
  time: "16:10"
}, {
  id: "s10",
  title: "Reduce the NDJSON stream to a phase machine",
  kind: "you",
  state: "done",
  agent: "claude",
  parent: "you",
  folder: "genesis / projection",
  dur: "1h 18m",
  unsup: false,
  events: 54,
  day: "Yesterday",
  time: "14:02"
}, {
  id: "s11",
  title: "Close the single-stage execution loop (M1b)",
  kind: "auto",
  state: "done",
  agent: "claude",
  parent: "maestro",
  folder: "hawthorne / hawthorne-engine",
  dur: "3h 50m",
  unsup: true,
  events: 88,
  day: "Yesterday",
  time: "11:20"
}, {
  id: "s12",
  title: "Linear import · credential retry",
  kind: "auto",
  state: "done",
  agent: "maestro",
  parent: "maestro",
  folder: "ops",
  dur: "3m",
  unsup: true,
  events: 6,
  day: "Mon",
  time: "09:14",
  routine: true
}];
function HistDot({
  s
}) {
  if (s.state === "live") return /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 13,
      height: 13
    }
  });
  return /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      width: 9,
      height: 9,
      background: HIST_STATE[s.state].color
    }
  });
}
function HistRow({
  s,
  selected,
  onSelect,
  depth = 0,
  showFolder = true,
  showAgent = true
}) {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-hrow" + (selected ? " is-sel" : ""),
    style: {
      paddingLeft: 16 + depth * 24
    },
    onClick: () => onSelect(s.id)
  }, depth > 0 && /*#__PURE__*/React.createElement("span", {
    className: "mcc-lin-elbow",
    style: {
      marginRight: 2
    }
  }), /*#__PURE__*/React.createElement(HistDot, {
    s: s
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-hrow-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-hrow-title"
  }, s.title), /*#__PURE__*/React.createElement("span", {
    className: "mcc-hrow-meta"
  }, showAgent && /*#__PURE__*/React.createElement("span", {
    className: "mcc-hrow-who"
  }, s.parent === s.agent ? s.agent : s.parent + " → " + s.agent), showFolder && /*#__PURE__*/React.createElement("span", {
    className: "mcc-hrow-crumb"
  }, s.folder), /*#__PURE__*/React.createElement("span", {
    className: "mcc-hrow-dur"
  }, s.unsup ? s.dur + " unsupervised" : s.dur, " \xB7 ", s.events, " events"))), s.routine ? /*#__PURE__*/React.createElement("span", {
    className: "mc-receipt"
  }, "routine") : /*#__PURE__*/React.createElement("span", {
    className: "mcc-hrow-kind mcc-hrow-kind--" + s.kind
  }, s.kind === "you" ? "you" : "loop"), /*#__PURE__*/React.createElement("span", {
    className: "mcc-hrow-time"
  }, s.time));
}
function HistGroupLabel({
  icon,
  children,
  count
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-hgroup"
  }, icon, /*#__PURE__*/React.createElement("span", null, children), count != null && /*#__PURE__*/React.createElement("span", {
    className: "mcc-hgroup-count"
  }, count));
}
function MccHistory({
  onOpenView,
  theme,
  onToggleTheme
}) {
  const noop = () => {};
  const [axis, setAxis] = React.useState("day");
  const [filter, setFilter] = React.useState("all");
  const [sel, setSel] = React.useState("s1");
  const [qq, setQq] = React.useState("");
  const rows = HIST_SESSIONS.filter(s => (filter === "all" || s.kind === filter) && (!qq.trim() || (s.title + " " + s.folder + " " + s.agent).toLowerCase().includes(qq.trim().toLowerCase())));
  const onSelect = setSel;
  let body;
  if (axis === "day") {
    const days = ["Today", "Yesterday", "Mon"];
    body = days.map(d => {
      const list = rows.filter(s => s.day === d);
      if (!list.length) return null;
      return /*#__PURE__*/React.createElement(React.Fragment, {
        key: d
      }, /*#__PURE__*/React.createElement(HistGroupLabel, {
        count: list.length
      }, d), list.map(s => /*#__PURE__*/React.createElement(HistRow, {
        key: s.id,
        s: s,
        selected: s.id === sel,
        onSelect: onSelect
      })));
    });
  } else if (axis === "work") {
    const folders = [...new Set(rows.map(s => s.folder))];
    body = folders.map(f => {
      const list = rows.filter(s => s.folder === f);
      return /*#__PURE__*/React.createElement(React.Fragment, {
        key: f
      }, /*#__PURE__*/React.createElement(HistGroupLabel, {
        icon: /*#__PURE__*/React.createElement(IcFolder, {
          size: 13
        }),
        count: list.length
      }, f), list.map(s => /*#__PURE__*/React.createElement(HistRow, {
        key: s.id,
        s: s,
        selected: s.id === sel,
        onSelect: onSelect,
        showFolder: false
      })));
    });
  } else if (axis === "agent") {
    const order = ["maestro", "claude", "bookkeeper", "scout"];
    body = order.map(ag => {
      const list = rows.filter(s => s.agent === ag);
      if (!list.length) return null;
      const c = HIST_AGENT[ag].color;
      return /*#__PURE__*/React.createElement(React.Fragment, {
        key: ag
      }, /*#__PURE__*/React.createElement(HistGroupLabel, {
        count: list.length,
        icon: ag === "maestro" ? /*#__PURE__*/React.createElement("span", {
          className: "mcc-dot-comet",
          style: {
            width: 14,
            height: 14
          }
        }, /*#__PURE__*/React.createElement("span", {
          className: "mcc-dot-comet-core"
        })) : /*#__PURE__*/React.createElement(McAvatar, {
          name: ag,
          color: c,
          size: 17
        })
      }, ag === "maestro" ? "maestro · the loop" : ag), list.map(s => /*#__PURE__*/React.createElement(HistRow, {
        key: s.id,
        s: s,
        selected: s.id === sel,
        onSelect: onSelect,
        showAgent: false
      })));
    });
  } else {
    // lineage
    // two roots: the loop (maestro) and you. Build parent→children.
    const renderTree = (rootLabel, rootIcon, predicate) => {
      const roots = rows.filter(predicate);
      if (!roots.length) return null;
      return /*#__PURE__*/React.createElement(React.Fragment, {
        key: rootLabel
      }, /*#__PURE__*/React.createElement(HistGroupLabel, {
        icon: rootIcon
      }, rootLabel), roots.map(s => /*#__PURE__*/React.createElement(React.Fragment, {
        key: s.id
      }, /*#__PURE__*/React.createElement(HistRow, {
        s: s,
        selected: s.id === sel,
        onSelect: onSelect,
        showAgent: true
      }), rows.filter(c => c.parentSession === s.id).map(c => /*#__PURE__*/React.createElement(HistRow, {
        key: c.id,
        s: c,
        selected: c.id === sel,
        onSelect: onSelect,
        depth: 1,
        showAgent: true
      })))));
    };
    body = /*#__PURE__*/React.createElement(React.Fragment, null, renderTree("The loop · maestro spawned", /*#__PURE__*/React.createElement("span", {
      className: "mcc-dot-comet",
      style: {
        width: 14,
        height: 14
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "mcc-dot-comet-core"
    })), s => s.parent === "maestro" && s.agent !== "scout"), renderTree("You started", /*#__PURE__*/React.createElement(McAvatar, {
      name: "Ana Diaz",
      color: "var(--bv-gray-600)",
      size: 17
    }), s => s.parent === "you"));
  }
  const axes = [["day", "By day"], ["work", "By work"], ["agent", "By agent"], ["lineage", "By lineage"]];
  const filters = [["all", "All"], ["you", "You"], ["auto", "Autonomous"]];
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-fill"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-app",
    style: {
      gridTemplateColumns: bvNavGrid()
    }
  }, /*#__PURE__*/React.createElement(BvNavTree, {
    active: "history",
    inApp: true,
    onNav: onOpenView
  }), /*#__PURE__*/React.createElement("div", {
    className: "bv-main"
  }, /*#__PURE__*/React.createElement(McvTopBar, {
    theme: theme,
    onToggleTheme: onToggleTheme || noop,
    onOpenMaestro: () => onOpenView && onOpenView("app"),
    onWake: noop,
    waking: false,
    canWake: true,
    onShowIdea: noop,
    counts: {
      needYou: 1,
      stuck: 1
    },
    workers: ["claude", "bookkeeper"],
    wakes: MCC_TICK_WAKES,
    items: WK_ITEMS,
    onAttention: () => onOpenView && onOpenView("app"),
    onCommand: () => window.dispatchEvent(new CustomEvent("bv:command-open"))
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-hist",
    "data-screen-label": "History page"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-hist-bar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-hsearch"
  }, /*#__PURE__*/React.createElement(IcSearch, {
    size: 14
  }), /*#__PURE__*/React.createElement("input", {
    value: qq,
    onChange: e => setQq(e.target.value),
    placeholder: "Search sessions\u2026"
  })), /*#__PURE__*/React.createElement(DsSegmented, {
    value: axis,
    onChange: setAxis,
    options: axes.map(([id, label]) => ({
      value: id,
      label
    }))
  }), /*#__PURE__*/React.createElement("div", {
    className: "mc-chips",
    style: {
      marginLeft: "auto"
    }
  }, filters.map(([id, label]) => /*#__PURE__*/React.createElement("button", {
    key: id,
    type: "button",
    className: "mc-chip" + (filter === id ? " is-active" : ""),
    onClick: () => setFilter(id)
  }, label)))), /*#__PURE__*/React.createElement("div", {
    className: "mcc-hist-list"
  }, body, /*#__PURE__*/React.createElement("div", {
    className: "mcc-hist-end"
  }, "312 sessions \xB7 the conversation bridge writes each one back as an Obsidian doc"))))));
}

// ── H0 · Session anatomy ──────────────────────────────────────────────────
function MccHistAnatomy() {
  const s = HIST_SESSIONS[0];
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-pad",
    style: {
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-anat"
  }, /*#__PURE__*/React.createElement(HistRow, {
    s: s,
    selected: true,
    onSelect: () => {}
  })), /*#__PURE__*/React.createElement("div", {
    className: "mcc-anat-grid"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-anat-cell"
  }, /*#__PURE__*/React.createElement("b", null, "The dot"), /*#__PURE__*/React.createElement("span", null, "state at a glance \xB7 the tidepool for live, a flat dot for done \xB7 needed-you \xB7 stuck.")), /*#__PURE__*/React.createElement("div", {
    className: "mcc-anat-cell"
  }, /*#__PURE__*/React.createElement("b", null, "Lineage"), /*#__PURE__*/React.createElement("span", null, "who \u2192 whom. ", /*#__PURE__*/React.createElement("code", null, "maestro \u2192 claude"), " reads the spawn, not just the worker.")), /*#__PURE__*/React.createElement("div", {
    className: "mcc-anat-cell"
  }, /*#__PURE__*/React.createElement("b", null, "The folder"), /*#__PURE__*/React.createElement("span", null, "the work it touched \xB7 a session is a projection ", /*#__PURE__*/React.createElement("i", null, "of"), " a folder, never free-floating.")), /*#__PURE__*/React.createElement("div", {
    className: "mcc-anat-cell"
  }, /*#__PURE__*/React.createElement("b", null, "Unsupervised"), /*#__PURE__*/React.createElement("span", null, "the number that matters: how long it ran before a human had to look.")), /*#__PURE__*/React.createElement("div", {
    className: "mcc-anat-cell"
  }, /*#__PURE__*/React.createElement("b", null, "you / loop"), /*#__PURE__*/React.createElement("span", null, "did you start it, or did the orchestrator? The filter toggles between them."))), /*#__PURE__*/React.createElement("p", {
    className: "mcc-caption"
  }, "Every row encodes the same five facts in the same places, so the eye learns them once and the axis switcher only re-groups \xB7 it never re-teaches. Halts read accent-blue, not red: needing you is a gate, not a failure."));
}
Object.assign(window, {
  MccHistory,
  MccHistAnatomy,
  HIST_SESSIONS,
  HIST_AGENT,
  HIST_STATE
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/ConceptHistory.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/ConceptKnowledge.jsx
try { (() => {
// Concept · the Knowledge page. The context engine made visible as a graph that
// is itself the filesystem: every file with frontmatter is a node, every related:
// link an edge, and every FOLDER is a node you can enter · descending re-scopes
// the graph to that folder's own knowledge. Navigation reuses the workspace tree
// in the sidebar (no separate header); clicking a folder there, a folder node in
// the graph, or a breadcrumb crumb all morph the graph between scopes.

// ── The workspace, as a tree of knowledge scopes ───────────────────────────
// Folder nodes carry scopeRef (the child scope id) and share that id, so a parent
// always holds the node the child morphs out of.
const KG_SCOPES = {
  broomva: {
    id: "broomva",
    crumb: "Broomva",
    kind: "vault",
    desc: "governance · the bstack contract",
    parent: null,
    nodes: [{
      id: "hawthorne",
      label: "hawthorne",
      type: "initiative",
      scopeRef: "hawthorne",
      claim: "The agent platform · multi-turn work with a lifecycle.",
      related: ["p6", "genesis"]
    }, {
      id: "genesis",
      label: "genesis",
      type: "project",
      scopeRef: "genesis",
      claim: "The walking-skeleton repo: observe, decide, act, judge, commit.",
      related: ["hawthorne", "p1"]
    }, {
      id: "ops",
      label: "ops",
      type: "initiative",
      scopeRef: "ops",
      claim: "Recurring ops · bookkeeping, nightly digests.",
      related: ["p2"]
    }, {
      id: "agents",
      label: "AGENTS.md",
      type: "doc",
      claim: "Reflexive trigger rules every agent loads at session start.",
      related: ["p6", "p2", "policy", "p1"]
    }, {
      id: "policy",
      label: ".control/policy.yaml",
      type: "doc",
      claim: "L3 governance · gates, budgets, scopes. The controller of last resort.",
      related: ["p2", "rcs", "agents"]
    }, {
      id: "p6",
      label: "Bookkeeping (P6)",
      type: "primitive",
      claim: "Knowledge graphs without quality control degrade into noise.",
      score: [3, 3, 3],
      sources: ["primitives.md#p6", "bookkeeping.py"],
      related: ["agents", "nous", "engine"]
    }, {
      id: "p2",
      label: "Control Gate (P2)",
      type: "primitive",
      claim: "Blocks destructive ops the model didn't authorize · gates G1–G11.",
      score: [3, 2, 3],
      sources: ["primitives.md#p2"],
      related: ["policy", "agents"]
    }, {
      id: "p1",
      label: "Conversation Bridge (P1)",
      type: "primitive",
      claim: "Closes session amnesia · each session writes back an Obsidian doc.",
      score: [3, 3, 2],
      sources: ["primitives.md#p1"],
      related: ["agents"]
    }, {
      id: "nous",
      label: "Nous gate",
      type: "concept",
      claim: "Novelty + specificity + relevance, each 0–3. Items < 2/9 are discarded.",
      score: [2, 3, 3],
      sources: ["bookkeeping.py"],
      related: ["p6"]
    }, {
      id: "rcs",
      label: "RCS L3 stability",
      type: "concept",
      claim: "Governance margin λ = 0.006 · the contract evolves slowly on purpose.",
      sources: ["recursive-controlled-systems"],
      related: ["policy"]
    }, {
      id: "engine",
      label: "bstack-engine",
      type: "pattern",
      claim: "The candidate ledger · where primitives are born and gated.",
      sources: ["bstack-engine.md"],
      related: ["p6"]
    }]
  },
  hawthorne: {
    id: "hawthorne",
    crumb: "hawthorne",
    kind: "initiative",
    desc: "the agent platform · multi-turn object model",
    parent: "broomva",
    nodes: [{
      id: "hawthorne-core",
      label: "hawthorne-core",
      type: "project",
      scopeRef: "hawthorne-core",
      claim: "The object model · persist run transcripts, at your gate.",
      related: ["worknoun", "hawthorne-db"]
    }, {
      id: "hawthorne-db",
      label: "hawthorne-db",
      type: "project",
      scopeRef: "hawthorne-db",
      claim: "Imports + the store · Linear cycles land as work items.",
      related: ["hawthorne-core"]
    }, {
      id: "worknoun",
      label: "work-as-noun",
      type: "concept",
      claim: "Folders are work at any scale; sessions are the verb acting on them.",
      score: [3, 3, 3],
      sources: ["work-model.md"],
      related: ["mc", "autonomy"]
    }, {
      id: "mc",
      label: "Maestro",
      type: "concept",
      claim: "The plane that sorts your screen by the decisions only a human can make.",
      related: ["worknoun", "gate"]
    }, {
      id: "autonomy",
      label: "unsupervised hours",
      type: "concept",
      claim: "The scarce resource: how long an agent runs before a human must look.",
      score: [3, 3, 3],
      sources: ["decision-log"],
      related: ["look", "worknoun"]
    }, {
      id: "look",
      label: "the look",
      type: "concept",
      claim: "Hours compressed to what changed · decided · asks · a 90-second look.",
      related: ["autonomy", "gate"]
    }, {
      id: "gate",
      label: "the gate",
      type: "concept",
      claim: "A clean run still lands at your gate · needing you is a gate, not a failure.",
      related: ["mc", "look"]
    }, {
      id: "maestro",
      label: "maestro",
      type: "person",
      claim: "The orchestrator is just a session that schedules sessions.",
      sources: ["symphony skill"],
      related: ["hawthorne-core", "gate"]
    }]
  },
  genesis: {
    id: "genesis",
    crumb: "genesis",
    kind: "project",
    desc: "one repo · its own .git + contract",
    parent: "broomva",
    nodes: [{
      id: "projection",
      label: "@genesis/projection",
      type: "session",
      live: true,
      claim: "Reduce the NDJSON stream to a phase machine · 1h 18m.",
      related: ["phase", "reducer"]
    }, {
      id: "phase",
      label: "phase machine",
      type: "concept",
      claim: "Reduce the NDJSON stream to running · awaiting · blocked · done.",
      related: ["ndjson", "reducer", "uimsg"]
    }, {
      id: "ndjson",
      label: "NDJSON stream",
      type: "concept",
      claim: "Append-only event timeline · the session's source of truth.",
      related: ["phase"]
    }, {
      id: "reducer",
      label: "projection/reducer.ts",
      type: "tool",
      claim: "Folds tool_use events into the live phase the chat renders.",
      related: ["phase", "uimsg"]
    }, {
      id: "uimsg",
      label: "UIMessage parts",
      type: "concept",
      claim: "text · reasoning · tool-NAME · data-NAME · the AI SDK contract.",
      score: [3, 2, 3],
      sources: ["ai-sdk docs"],
      related: ["aisdk", "reducer"]
    }, {
      id: "aisdk",
      label: "UI Message Stream",
      type: "paper",
      claim: "Gen-UI stops being bespoke when every part speaks the same chunks.",
      sources: ["sdk.vercel.ai"],
      related: ["uimsg"]
    }, {
      id: "metr",
      label: "METR Time Horizon 1.1",
      type: "paper",
      claim: "80%-reliability deployable horizon ~1h on Opus 4.6 · above it, persist.",
      sources: ["metr.org · Jan 2026"],
      related: ["phase"]
    }]
  },
  "hawthorne-core": {
    id: "hawthorne-core",
    crumb: "hawthorne-core",
    kind: "project",
    desc: "persist run transcripts · worktree-per-run",
    parent: "hawthorne",
    nodes: [{
      id: "objmodel",
      label: "object model",
      type: "concept",
      claim: "Work item → lifecycle: proposed → running → review → done.",
      score: [3, 2, 3],
      sources: ["hawthorne-core"],
      related: ["multiturn", "relay"]
    }, {
      id: "multiturn",
      label: "multi-turn",
      type: "concept",
      claim: "A work item outlives any single session that touches it.",
      related: ["objmodel"]
    }, {
      id: "relay",
      label: "Maestro relay",
      type: "concept",
      claim: "Handoff protocol · any session can pick up the work from here.",
      related: ["objmodel"]
    }, {
      id: "spec3",
      label: "spec.md",
      type: "doc",
      claim: "kind: project · owner: maestro · budget: 8h · gate: human-approve.",
      related: ["drun", "notes", "run7c"]
    }, {
      id: "drun",
      label: "persist transcript on Run",
      type: "decision",
      claim: "Not the session · survives restarts; 14 tests cover replay.",
      score: [3, 3, 3],
      sources: ["run/7c2f1a", "PR #214"],
      related: ["spec3", "run7c", "notes"]
    }, {
      id: "ddefer",
      label: "defer compression",
      type: "decision",
      claim: "Transcripts stay small until multi-day runs land · revisit then.",
      score: [2, 3, 2],
      sources: ["decision-log 2026-06-06"],
      related: ["spec3"]
    }, {
      id: "notes",
      label: "notes/prior-art.md",
      type: "doc",
      claim: "Survey of resumability approaches, written from scout's 47m run.",
      related: ["scout", "drun"]
    }, {
      id: "run7c",
      label: "run/7c2f1a",
      type: "session",
      claim: "claude · 2h 14m unsupervised · 41 events · ran to the gate.",
      live: true,
      related: ["drun", "spec3", "judge"]
    }, {
      id: "scout",
      label: "scout · survey",
      type: "session",
      claim: "claude → scout · 47m unsupervised · done.",
      related: ["notes"]
    }, {
      id: "judge",
      label: "judge verdict",
      type: "concept",
      claim: "Checks passed · 14 tests added · a clean run, still your gate.",
      related: ["run7c", "drun"]
    }, {
      id: "review",
      label: "you → review API",
      type: "session",
      claim: "Halted · needed you (2 looks).",
      related: ["spec3"]
    }]
  },
  "hawthorne-db": {
    id: "hawthorne-db",
    crumb: "hawthorne-db",
    kind: "project",
    desc: "imports + the store",
    parent: "hawthorne",
    nodes: [{
      id: "linear",
      label: "Linear import",
      type: "decision",
      claim: "Blocked · needs a LINEAR_API_KEY read scope before it can run.",
      sources: ["run/b91e44"],
      related: ["runb91", "cycles"]
    }, {
      id: "runb91",
      label: "run/b91e44",
      type: "session",
      claim: "claude · 41m · paused · waiting on the credential grant.",
      related: ["linear"]
    }, {
      id: "cycles",
      label: "linear-cycles.md",
      type: "doc",
      claim: "Map Linear cycles → work items · the import contract.",
      related: ["linear"]
    }]
  },
  ops: {
    id: "ops",
    crumb: "ops",
    kind: "initiative",
    desc: "recurring ops",
    parent: "broomva",
    nodes: [{
      id: "nightly",
      label: "nightly-digest",
      type: "routine",
      scopeRef: "nightly",
      claim: "A standing loop: the routine is the deliverable, gate: none.",
      related: ["finance"]
    }, {
      id: "bookkeeping",
      label: "bookkeeping",
      type: "task",
      scopeRef: "bookkeeping",
      claim: "Reconcile May invoices in a cloud sandbox.",
      related: ["finance", "reconcile"]
    }, {
      id: "finance",
      label: "finance-substrate",
      type: "tool",
      claim: "Bookkeeper reconciles invoices and pushes digests each month.",
      sources: ["finance-substrate skill"],
      related: ["nightly", "bookkeeping"]
    }, {
      id: "reconcile",
      label: "reconciliation",
      type: "concept",
      claim: "Match receipts to invoices; flag the gaps for a look.",
      related: ["bookkeeping"]
    }]
  },
  nightly: {
    id: "nightly",
    crumb: "nightly-digest",
    kind: "routine",
    desc: "a loop that never closes",
    parent: "ops",
    nodes: [{
      id: "cadence",
      label: "cadence: 02:00",
      type: "doc",
      claim: "kind: routine · cadence: nightly 02:00 · gate: none.",
      related: ["digest", "run0610"]
    }, {
      id: "digest",
      label: "digest template",
      type: "doc",
      claim: "What landed, what's stuck, what needs a look by morning.",
      related: ["cadence"]
    }, {
      id: "run0610",
      label: "Thu 02:00 run",
      type: "session",
      claim: "31m · digest pushed + flagged a stuck import.",
      related: ["cadence", "digest"]
    }, {
      id: "run0609",
      label: "Wed 02:00 run",
      type: "session",
      claim: "19m · digest pushed · /h/digest-0610.",
      related: ["cadence"]
    }]
  },
  bookkeeping: {
    id: "bookkeeping",
    crumb: "bookkeeping",
    kind: "task",
    desc: "May reconciliation · cloud sandbox",
    parent: "ops",
    nodes: [{
      id: "may",
      label: "may-invoices.md",
      type: "doc",
      claim: "36 invoices, 38 receipts · the month's ledger.",
      related: ["bk", "reconciled"]
    }, {
      id: "bk",
      label: "bookkeeper run",
      type: "session",
      claim: "Bookkeeper · cloud sandbox · 31 of 36 reconciled.",
      live: true,
      related: ["may", "reconciled"]
    }, {
      id: "receipts",
      label: "drive: /receipts/2026-05",
      type: "doc",
      claim: "38 source documents pulled from the drive.",
      related: ["bk"]
    }, {
      id: "reconciled",
      label: "5 unmatched",
      type: "decision",
      claim: "Five invoices have no receipt · flagged for your look.",
      score: [2, 3, 3],
      sources: ["run/c30a9d"],
      related: ["may", "bk"]
    }]
  }
};
function kgScore(arr) {
  return arr ? arr[0] + arr[1] + arr[2] : null;
}
function kgPath(id) {
  const out = [];
  let s = KG_SCOPES[id];
  while (s) {
    out.unshift(s);
    s = s.parent ? KG_SCOPES[s.parent] : null;
  }
  return out;
}

// ── The inspector · an entity page rendered from a node ────────────────────
function KgInspector({
  node,
  scope,
  onSelect,
  big
}) {
  if (!node) {
    const folders = scope.nodes.filter(n => n.scopeRef).length;
    return /*#__PURE__*/React.createElement("div", {
      className: "kg-inspect kg-inspect--empty"
    }, /*#__PURE__*/React.createElement("div", {
      className: "mcc-panel-label"
    }, scope.crumb, "/ \xB7 ", scope.kind), /*#__PURE__*/React.createElement("p", {
      className: "mcc-doc-p",
      style: {
        color: "var(--muted-foreground)"
      }
    }, scope.nodes.length, " entities", folders > 0 ? " · " + folders + " sub-folder" + (folders > 1 ? "s" : "") : "", " \xB7 ", scope.desc, "."), /*#__PURE__*/React.createElement("p", {
      className: "mcc-doc-p",
      style: {
        color: "var(--muted-foreground)"
      }
    }, "Click an entity to open its page. The ", /*#__PURE__*/React.createElement("b", {
      style: {
        color: "var(--foreground)"
      }
    }, "gold folder nodes"), " are sub-scopes \xB7 click one to dive into its graph."), /*#__PURE__*/React.createElement("div", {
      className: "kg-empty-hint"
    }, /*#__PURE__*/React.createElement(IcGraph, {
      size: 15
    }), "Drag to pan \xB7 drag a node to pull it \xB7 /kg to filter"));
  }
  const t = KG_TYPE[node.type] || KG_TYPE.concept;
  const total = kgScore(node.score);
  const backlinks = scope.nodes.filter(n => (n.related || []).includes(node.id) || (node.related || []).includes(n.id));
  const subs = [["novelty", node.score && node.score[0]], ["specificity", node.score && node.score[1]], ["relevance", node.score && node.score[2]]];
  return /*#__PURE__*/React.createElement("div", {
    className: "kg-inspect" + (big ? " kg-inspect--big" : "")
  }, /*#__PURE__*/React.createElement("div", {
    className: "kg-ent-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "kg-ent-kind",
    style: {
      color: t.color,
      borderColor: "color-mix(in oklch, " + t.color + " 42%, transparent)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "kg-legend-dot",
    style: {
      background: t.color
    }
  }), t.label), node.live && /*#__PURE__*/React.createElement("span", {
    className: "mc-badge"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-comet",
    style: {
      width: 12,
      height: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-comet-core"
  })), "live")), /*#__PURE__*/React.createElement("div", {
    className: "kg-ent-title"
  }, node.label, node.type !== "session" && !node.scopeRef ? /*#__PURE__*/React.createElement("span", {
    className: "kg-ent-ext"
  }, ".md") : null), /*#__PURE__*/React.createElement("p", {
    className: "kg-ent-claim"
  }, "\u201C", node.claim, "\u201D"), total != null && /*#__PURE__*/React.createElement("div", {
    className: "kg-score"
  }, /*#__PURE__*/React.createElement("div", {
    className: "kg-score-top"
  }, /*#__PURE__*/React.createElement("span", null, "Nous score"), /*#__PURE__*/React.createElement("b", null, total, /*#__PURE__*/React.createElement("i", null, "/9")), /*#__PURE__*/React.createElement("span", {
    className: "kg-score-verdict"
  }, total >= 7 ? "fast-path promote" : total >= 3 ? "second opinion" : "discard")), subs.map(([k, v]) => /*#__PURE__*/React.createElement("div", {
    key: k,
    className: "kg-score-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "kg-score-k"
  }, k), /*#__PURE__*/React.createElement("span", {
    className: "kg-score-bar"
  }, /*#__PURE__*/React.createElement("i", {
    style: {
      width: v / 3 * 100 + "%"
    }
  })), /*#__PURE__*/React.createElement("span", {
    className: "kg-score-v"
  }, v)))), node.sources && /*#__PURE__*/React.createElement("div", {
    className: "kg-ent-sec"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label"
  }, "sources"), /*#__PURE__*/React.createElement("div", {
    className: "kg-src-list"
  }, node.sources.map((s, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    className: "mc-receipt"
  }, s)))), /*#__PURE__*/React.createElement("div", {
    className: "kg-ent-sec"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label"
  }, "related \xB7 ", backlinks.length), /*#__PURE__*/React.createElement("div", {
    className: "kg-back-list"
  }, backlinks.map(n => {
    const bt = KG_TYPE[n.type] || KG_TYPE.concept;
    return /*#__PURE__*/React.createElement("button", {
      key: n.id,
      type: "button",
      className: "kg-back",
      onClick: () => onSelect && onSelect(n.id)
    }, /*#__PURE__*/React.createElement("span", {
      className: "kg-legend-dot",
      style: {
        background: bt.color
      }
    }), n.label);
  }))));
}

// ── The workspace tree in the sidebar · the graph's navigator ──────────────
function KnowScopeRows({
  parentId,
  depth,
  activeId,
  pathSet,
  onNav
}) {
  const kids = Object.values(KG_SCOPES).filter(s => s.parent === parentId);
  return kids.map(sc => {
    const has = Object.values(KG_SCOPES).some(s => s.parent === sc.id);
    const live = sc.nodes.some(n => n.live);
    const open = has && pathSet.has(sc.id);
    return /*#__PURE__*/React.createElement(React.Fragment, {
      key: sc.id
    }, /*#__PURE__*/React.createElement("button", {
      className: "bv-sb-item" + (sc.id === activeId ? " is-active" : ""),
      type: "button",
      style: {
        paddingLeft: 10 + depth * 15
      },
      onClick: () => onNav(sc.id)
    }, live ? /*#__PURE__*/React.createElement("span", {
      className: "mcc-dot-tide",
      style: {
        width: 13,
        height: 13
      }
    }) : open ? /*#__PURE__*/React.createElement(IcFolderOpen, {
      size: 14
    }) : /*#__PURE__*/React.createElement(IcFolder, {
      size: 14
    }), /*#__PURE__*/React.createElement("span", {
      className: "mcc-sb-text"
    }, sc.crumb), /*#__PURE__*/React.createElement("span", {
      className: "mc-init-progress"
    }, sc.nodes.length)), has && /*#__PURE__*/React.createElement(KnowScopeRows, {
      parentId: sc.id,
      depth: depth + 1,
      activeId: activeId,
      pathSet: pathSet,
      onNav: onNav
    }));
  });
}
function KnowTree({
  activeId,
  onNav
}) {
  const pathSet = new Set(kgPath(activeId).map(s => s.id));
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-sb-col"
  }, /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item" + (activeId === "broomva" ? " is-active" : ""),
    type: "button",
    onClick: () => onNav("broomva")
  }, /*#__PURE__*/React.createElement(IcLayers, {
    size: 15
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-sb-text"
  }, "Broomva"), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, "vault")), /*#__PURE__*/React.createElement(KnowScopeRows, {
    parentId: "broomva",
    depth: 1,
    activeId: activeId,
    pathSet: pathSet,
    onNav: onNav
  }));
}

// ── K0 · A node is a file · frontmatter builds the graph ───────────────────
function MccKnowNode() {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-pad",
    style: {
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "kg-node-spec"
  }, /*#__PURE__*/React.createElement("pre", {
    className: "mcc-fm",
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("code", null, `---
kind: decision
core_claim: >
  Persist the transcript on the Run,
  not the session · survives restarts.
nous: { novelty: 3, specificity: 3, relevance: 3 }
sources: [run/7c2f1a, PR #214]
related:
  - resumable-sessions
  - ndjson-stream
  - judge-verdict
---

# persist on the Run

14 tests cover replay instead of
snapshotting live session state…`)), /*#__PURE__*/React.createElement("span", {
    className: "mcc-prim-arrow",
    style: {
      alignSelf: "center"
    }
  }, "becomes"), /*#__PURE__*/React.createElement("div", {
    className: "kg-node-demo"
  }, /*#__PURE__*/React.createElement("svg", {
    viewBox: "0 0 200 180",
    className: "kg-node-demo-svg"
  }, /*#__PURE__*/React.createElement("line", {
    x1: "100",
    y1: "90",
    x2: "40",
    y2: "40",
    className: "kg-edge",
    style: {
      opacity: 0.5
    }
  }), /*#__PURE__*/React.createElement("line", {
    x1: "100",
    y1: "90",
    x2: "165",
    y2: "55",
    className: "kg-edge",
    style: {
      opacity: 0.5
    }
  }), /*#__PURE__*/React.createElement("line", {
    x1: "100",
    y1: "90",
    x2: "150",
    y2: "150",
    className: "kg-edge",
    style: {
      opacity: 0.5
    }
  }), /*#__PURE__*/React.createElement("g", null, /*#__PURE__*/React.createElement("circle", {
    cx: "40",
    cy: "40",
    r: "8",
    fill: "var(--bv-blue)",
    stroke: "var(--background)",
    strokeWidth: "2"
  }), /*#__PURE__*/React.createElement("text", {
    x: "40",
    y: "26",
    textAnchor: "middle",
    className: "kg-label"
  }, "resumable")), /*#__PURE__*/React.createElement("g", null, /*#__PURE__*/React.createElement("circle", {
    cx: "165",
    cy: "55",
    r: "8",
    fill: "var(--bv-blue)",
    stroke: "var(--background)",
    strokeWidth: "2"
  }), /*#__PURE__*/React.createElement("text", {
    x: "165",
    y: "41",
    textAnchor: "middle",
    className: "kg-label"
  }, "ndjson")), /*#__PURE__*/React.createElement("g", null, /*#__PURE__*/React.createElement("circle", {
    cx: "150",
    cy: "150",
    r: "8",
    fill: "var(--bv-info)",
    stroke: "var(--background)",
    strokeWidth: "2"
  }), /*#__PURE__*/React.createElement("text", {
    x: "150",
    y: "170",
    textAnchor: "middle",
    className: "kg-label"
  }, "judge")), /*#__PURE__*/React.createElement("g", null, /*#__PURE__*/React.createElement("circle", {
    cx: "100",
    cy: "90",
    r: "12",
    fill: "var(--bv-success)",
    stroke: "var(--background)",
    strokeWidth: "2.5"
  }), /*#__PURE__*/React.createElement("text", {
    x: "100",
    y: "113",
    textAnchor: "middle",
    className: "kg-label",
    style: {
      fontWeight: 600
    }
  }, "persist on Run"))))), /*#__PURE__*/React.createElement("p", {
    className: "mcc-caption"
  }, "No separate database. A markdown (or HTML) file's ", /*#__PURE__*/React.createElement("b", null, "frontmatter is the node"), ": ", /*#__PURE__*/React.createElement("code", null, "kind"), " sets its colour, ", /*#__PURE__*/React.createElement("code", null, "core_claim"), " its one line, the Nous block its score, and every ", /*#__PURE__*/React.createElement("code", null, "related:"), " entry draws an edge. Walk the filesystem and you've walked the graph \xB7 exactly bstack's ", /*#__PURE__*/React.createElement("b", null, "Bookkeeping (P6)"), " over ", /*#__PURE__*/React.createElement("code", null, "research/entities"), ". The agent files these as a reflex; you read them as a map."));
}

// ── K2 · The entity, opened · the inspector at full size ───────────────────
function MccKnowEntity() {
  const scope = KG_SCOPES["hawthorne-core"];
  const node = scope.nodes.find(n => n.id === "drun");
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-pad",
    style: {
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-detail-breadcrumb"
  }, "hawthorne / hawthorne-core / runs \xB7 7c2f1a"), /*#__PURE__*/React.createElement("div", {
    className: "kg-entity-card"
  }, /*#__PURE__*/React.createElement(KgInspector, {
    node: node,
    scope: scope,
    onSelect: () => {},
    big: true
  })), /*#__PURE__*/React.createElement("p", {
    className: "mcc-caption"
  }, "A node, opened: the entity page is the same frontmatter, rendered. The Nous score isn't decoration \xB7 it's the gate that kept this out of the noise (\u2265 7 fast-paths a promote; under 2 is discarded). ", /*#__PURE__*/React.createElement("code", null, "related:"), " is bidirectional, so backlinks come free \xB7 click one and the graph re-centres on it."));
}
Object.assign(window, {
  KG_SCOPES,
  kgPath,
  KgInspector,
  KnowTree,
  MccKnowNode,
  MccKnowEntity
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/ConceptKnowledge.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/ConceptMaestroLoop.jsx
try { (() => {
// Concepts canvas · the maestro loop: the synthesis (v2).
// This is the workspace-click view; clicking any folder underneath looks
// the same, except the FS pane shows THAT folder's location (and worktree).
// Tabs: sessions live on the LEFT of the strip; files open on the RIGHT,
// sliding in from the file pane and pushing the queue leftward. Drag a
// file tab toward the chat to keep a two-sided view. + spawns a new
// session on the current workspace layer; the toggle at the strip's right
// edge hides the FS pane.

const IcMlPanel = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("rect", {
  width: "18",
  height: "18",
  x: "3",
  y: "3",
  rx: "2"
}), /*#__PURE__*/React.createElement("path", {
  d: "M15 3v18"
}));
const IcMlPanelLeft = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("rect", {
  width: "18",
  height: "18",
  x: "3",
  y: "3",
  rx: "2"
}), /*#__PURE__*/React.createElement("path", {
  d: "M9 3v18"
}));

// ── The gate queue · stopgaps accumulated over ticks ─────────────────────
const MCC_ML_GATE_SEED = [
// superseded · the live seed is AiProtocol.jsx's MCC_ML_GATE (data-gate parts)
{
  id: "g1",
  kind: "gate",
  title: "Persist run transcripts on the Run record",
  meta: "ran 2h 14m unsupervised · judge passed · 14 tests",
  ask: "Approve the branch and tonight's phase 2 builds on it.",
  actions: [["Approve", "primary"], ["Send back", "secondary"]],
  t: "12m"
}, {
  id: "g2",
  kind: "warn",
  title: "Linear import needs an API scope",
  meta: "worker paused 41m · blocks 3 queued items downstream",
  ask: "Grant read access to Linear cycles, or park the import.",
  actions: [["Grant access", "primary"], ["Park it", "secondary"]],
  t: "41m"
}];
function MccGateQueue({
  items,
  mini
}) {
  const [open, setOpen] = React.useState(mini ? -1 : 0);
  // The grace window · a decision takes effect on the next tick, so the verb
  // stays reversible for a beat instead of being instantly irreversible.
  const [done, setDone] = React.useState({});
  const timers = React.useRef({});
  const GRACE = 10;
  React.useEffect(() => () => Object.values(timers.current).forEach(clearInterval), []);
  const act = (g, label) => {
    setDone(d => ({
      ...d,
      [g.id]: {
        label,
        left: GRACE
      }
    }));
    timers.current[g.id] = setInterval(() => {
      setDone(d => {
        const e = d[g.id];
        if (!e) return d;
        if (e.left <= 1) {
          clearInterval(timers.current[g.id]);
          return {
            ...d,
            [g.id]: {
              ...e,
              left: 0,
              final: true
            }
          };
        }
        return {
          ...d,
          [g.id]: {
            ...e,
            left: e.left - 1
          }
        };
      });
    }, 1000);
  };
  const undo = id => {
    clearInterval(timers.current[id]);
    setDone(d => {
      const n = {
        ...d
      };
      delete n[id];
      return n;
    });
  };
  const live = items.filter(g => !(done[g.id] && done[g.id].final));
  if (!live.length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "mcc-allclear",
      style: {
        padding: "2px 2px"
      }
    }, /*#__PURE__*/React.createElement(IcCheck, {
      size: 14
    }), "Nothing at your gate. The loop holds everything \xB7 next tick 13m");
  }
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-gateq",
    "data-screen-label": "Gate queue"
  }, live.map((g, i) => {
    const d = done[g.id];
    return /*#__PURE__*/React.createElement("div", {
      key: g.id,
      className: "mcc-gateq-card",
      onClick: () => setOpen(open === i ? -1 : i)
    }, /*#__PURE__*/React.createElement("div", {
      className: "mcc-gateq-row"
    }, /*#__PURE__*/React.createElement(MccLoopDot, {
      kind: g.kind
    }), /*#__PURE__*/React.createElement("span", {
      className: "mcc-gateq-title"
    }, g.title), /*#__PURE__*/React.createElement("span", {
      className: "mcc-loops-t",
      style: {
        marginTop: 0
      }
    }, g.t)), /*#__PURE__*/React.createElement("span", {
      className: "mcc-gateq-meta"
    }, g.meta), d ? /*#__PURE__*/React.createElement("div", {
      className: "mcc-gateq-done",
      onClick: e => e.stopPropagation()
    }, /*#__PURE__*/React.createElement(IcCheck, {
      size: 14
    }), d.label, /*#__PURE__*/React.createElement("span", {
      className: "mcc-gateq-done-note"
    }, "takes effect on the next tick"), /*#__PURE__*/React.createElement("button", {
      className: "bv-pill bv-pill--secondary bv-pill--sm mcc-gateq-undo",
      type: "button",
      onClick: () => undo(g.id)
    }, "Undo \xB7 ", d.left, "s")) : open === i && /*#__PURE__*/React.createElement(React.Fragment, null, g.look ? /*#__PURE__*/React.createElement("div", {
      className: "mcc-gateq-look"
    }, g.look.map(([k, v]) => /*#__PURE__*/React.createElement("div", {
      key: k,
      className: "mcc-gateq-look-row"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mcc-gateq-look-key"
    }, k), /*#__PURE__*/React.createElement("span", {
      className: "mcc-gateq-look-val"
    }, v)))) : /*#__PURE__*/React.createElement("span", {
      className: "mcc-gateq-ask"
    }, g.ask), /*#__PURE__*/React.createElement("div", {
      className: "mc-detail-actions",
      onClick: e => e.stopPropagation()
    }, g.actions.map(([label, tone]) => /*#__PURE__*/React.createElement("button", {
      key: label,
      className: "bv-pill bv-pill--" + tone + " bv-pill--sm",
      type: "button",
      onClick: () => act(g, tone === "primary" ? label === "Approve" ? "Approved" : label + " · done" : label === "Send back" ? "Sent back with notes" : label + " · done")
    }, tone === "primary" && /*#__PURE__*/React.createElement(IcCheck, {
      size: 13
    }), label)), /*#__PURE__*/React.createElement("span", {
      className: "mcc-look-timer"
    }, g.hint || (i === 0 ? "a 90-second look" : "unblocks 1 worker")))));
  }));
}

// ── The tick card · the loop narrating itself in the chat (gen-UI) ───────
function MccTickCard({
  rows
}) {
  rows = rows || [{
    g: "▷",
    cause: "interval 15m",
    causeColor: "var(--bv-gray-500)",
    label: "No-op · at capacity (2/2 worktrees)",
    t: "32m"
  }, {
    g: "▶",
    cause: "worker returned",
    causeColor: "var(--bv-blue)",
    label: "run/7c2f1a judged clean → queued to your gate",
    t: "12m"
  }, {
    g: "▷",
    cause: "interval 15m",
    causeColor: "var(--bv-gray-500)",
    label: "Holding · 2 decisions open at your gate",
    t: "2m"
  }];
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-tickcard",
    "data-screen-label": "Tick receipt (gen-UI)"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-tickcard-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 12,
      height: 12
    }
  }), "the loop \xB7 last 3 ticks"), /*#__PURE__*/React.createElement("div", {
    className: "mcc-wake-list"
  }, rows.map((r, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "mcc-wake"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-wake-glyph"
  }, r.g), /*#__PURE__*/React.createElement("span", {
    className: "mcc-wake-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-wake-top"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-wake-cause",
    style: {
      color: r.causeColor
    }
  }, r.cause), /*#__PURE__*/React.createElement("span", {
    className: "mcc-wake-label"
  }, r.label), /*#__PURE__*/React.createElement("span", {
    className: "mcc-loops-t",
    style: {
      marginTop: 0
    }
  }, r.t)))))));
}

// ── Maestro, docked left and collapsible ─────────────────────────
function MccMcDock({
  shut,
  onToggle,
  resize
}) {
  if (shut) {
    return /*#__PURE__*/React.createElement("div", {
      className: "mcc-mcol mcc-mcol--shut",
      "data-screen-label": "Maestro (collapsed)"
    }, /*#__PURE__*/React.createElement("button", {
      className: "mcc-panel-close",
      type: "button",
      onClick: onToggle,
      "aria-label": "Expand Maestro",
      title: "Maestro"
    }, /*#__PURE__*/React.createElement(IcBoard, {
      size: 15
    })), /*#__PURE__*/React.createElement("span", {
      className: "mcc-attn-chip",
      style: {
        padding: 0,
        width: 24,
        height: 24,
        justifyContent: "center"
      }
    }, "2"), MCC_AT_LOOPS.filter(l => l.kind === "live").map(l => /*#__PURE__*/React.createElement("span", {
      key: l.title,
      title: l.title
    }, /*#__PURE__*/React.createElement(MccLoopDot, {
      kind: "live"
    }))));
  }
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-mcol",
    "data-screen-label": "Maestro (docked)"
  }, resize && /*#__PURE__*/React.createElement("div", {
    className: "mcc-coldrag mcc-coldrag--right",
    onMouseDown: resize,
    title: "Drag to resize"
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-mcol-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-panel-label"
  }, "Maestro"), /*#__PURE__*/React.createElement("span", {
    className: "mcc-loops-count",
    style: {
      marginLeft: "auto"
    }
  }, "2 live"), /*#__PURE__*/React.createElement("button", {
    className: "mcc-panel-close",
    type: "button",
    onClick: onToggle,
    "aria-label": "Collapse Maestro",
    title: "Collapse"
  }, /*#__PURE__*/React.createElement(IcChevrons, {
    size: 13,
    style: {
      transform: "rotate(90deg)"
    }
  }))), /*#__PURE__*/React.createElement("div", {
    className: "mcc-mcol-body"
  }, /*#__PURE__*/React.createElement(MccDockFeedBody, {
    filter: null
  })));
}

// ── Per-scope FS pane data ────────────────────────────────────────────────
const MCC_FT_HAW = [{
  name: "hawthorne.md",
  path: "hawthorne.md",
  depth: 0,
  kind: "file"
}, {
  name: "hawthorne-core",
  depth: 0,
  kind: "folder"
}, {
  name: "spec.md",
  path: "spec.md",
  depth: 1,
  kind: "file"
}, {
  name: "prior-art.md",
  path: "prior-art.md",
  depth: 1,
  kind: "file"
}, {
  name: "api-decisions.md",
  path: "api-decisions.md",
  depth: 1,
  kind: "file"
}, {
  name: "run-7c2f1a.md",
  path: "run-7c2f1a.md",
  depth: 1,
  kind: "file"
}, {
  name: "hawthorne-db",
  depth: 0,
  kind: "folder"
}, {
  name: "hawthorne-engine",
  depth: 0,
  kind: "folder"
}];
const MCC_ML_FS = {
  root: {
    label: "Broomva/",
    location: "~/Broomva",
    entries: () => MCC_FT_ROOT,
    layer: "the workspace"
  },
  hawthorne: {
    label: "hawthorne/",
    location: "~/Broomva/hawthorne",
    entries: () => MCC_FT_HAW,
    layer: "hawthorne/"
  },
  core: {
    label: "hawthorne-core/",
    location: "~/Broomva/hawthorne/hawthorne-core",
    worktree: "worktree: run/7c2f1a",
    entries: () => MCC_FT_CORE,
    layer: "hawthorne-core/"
  }
};

// ── Chat panes · maestro + fresh sessions on the current layer ───────────
function MccChatPane({
  session,
  layer,
  chatLen,
  rail
}) {
  if (session.id !== "maestro") {
    return /*#__PURE__*/React.createElement("div", {
      className: "mcc-chatcol",
      "data-screen-label": "Session pane · " + session.label
    }, /*#__PURE__*/React.createElement("div", {
      className: "mcc-newchat"
    }, /*#__PURE__*/React.createElement("div", {
      className: "mcc-newchat-inner"
    }, /*#__PURE__*/React.createElement("span", {
      className: "bv-greeting-title"
    }, "A fresh session on ", layer), /*#__PURE__*/React.createElement("span", {
      className: "bv-greeting-sub"
    }, "It inherits this layer's contract \xB7 budget, gate, scope \xB7 and its receipts land here."), /*#__PURE__*/React.createElement(MccPromptPlate, {
      className: "mcc-prompt--glass",
      placeholder: "Tell " + layer + " what's next…"
    }))));
  }
  return /*#__PURE__*/React.createElement(MccMaestroChat, {
    key: chatLen || "short",
    layer: layer,
    chatLen: chatLen,
    rail: rail
  });
}

// The conversation minimap · a thin ruler pinned to the chat's right edge.
// The conversation minimap · a thin ruler of your inputs pinned to the chat's
// right edge. Three behaviours that adapt to volume:
//  · compact (a handful): a tight centered band; hovering a mark grows it with
//    a dock-style falloff onto its neighbours.
//  · dense (dozens–hundreds): a proportional overview. Adjacent inputs that
//    would collide are BUCKETED into a single mark whose thickness shows how
//    many it holds · so the rail stays legible at any density. On hover the
//    cursor opens a LENS: a fixed filmstrip of the ~11 turns around the focus
//    fans out at a readable pitch (dock magnification), and moving the cursor
//    scrubs that window through the whole history. Click jumps to the focus.
// Hover/scrub → the message + when you sent it; click → smooth-scroll there.
function MccChatMinimap({
  feedRef,
  messages
}) {
  const railRef = React.useRef(null);
  const ticksRef = React.useRef([]);
  const [ticks, setTicks] = React.useState([]);
  const [buckets, setBuckets] = React.useState([]);
  const [mode, setMode] = React.useState("compact");
  const [railH, setRailH] = React.useState(0);
  const [active, setActive] = React.useState(-1);
  const [hover, setHover] = React.useState(-1); // compact: hovered index
  const [pointerY, setPointerY] = React.useState(null); // dense: cursor Y in rail
  ticksRef.current = ticks;
  const DENSE_WIN = 5,
    DENSE_PITCH = 13; // lens: ±5 turns at 13px pitch

  const computeActive = React.useCallback(() => {
    const feed = feedRef.current;
    if (!feed) return;
    const probe = feed.scrollTop + 72;
    const arr = ticksRef.current;
    let idx = -1;
    for (let i = 0; i < arr.length; i++) {
      if (arr[i].top <= probe) idx = i;else break;
    }
    setActive(idx);
  }, [feedRef]);
  const measure = React.useCallback(() => {
    const feed = feedRef.current,
      rail = railRef.current;
    if (!feed || !rail) return;
    const rh = rail.clientHeight || 1;
    const total = feed.scrollHeight || 1;
    const rows = [];
    feed.querySelectorAll('[data-bv-user="1"]').forEach(el => {
      rows.push({
        top: el.offsetTop,
        text: (el.textContent || "").trim(),
        time: el.dataset.bvTime || ""
      });
    });
    const n = rows.length;
    const pad = 12;
    const usable = Math.max(1, rh - pad * 2);
    const compactGap = 14;
    const dense = n > 1 && (n - 1) * compactGap > usable;
    let bks = [];
    if (n === 1) {
      rows[0].y = rows[0].yBase = Math.round(rh / 2);
    } else if (dense) {
      rows.forEach(t => {
        t.yBase = pad + t.top / total * usable;
        t.y = t.yBase;
      });
      // Bin inputs into fixed ~5px slots so the at-rest overview never
      // collapses into one bar; each non-empty slot becomes one bucket.
      const bucketPitch = 5;
      let cur = null,
        curBin = -999;
      rows.forEach((t, i) => {
        const bin = Math.floor(t.yBase / bucketPitch);
        if (cur && bin === curBin) {
          cur.members.push(i);
          cur.y1 = t.yBase;
          cur.timeEnd = t.time;
        } else {
          cur = {
            y0: t.yBase,
            y1: t.yBase,
            members: [i],
            timeStart: t.time,
            timeEnd: t.time
          };
          curBin = bin;
          bks.push(cur);
        }
      });
      bks.forEach(b => {
        b.y = Math.round((b.y0 + b.y1) / 2);
        b.count = b.members.length;
      });
    } else if (n > 1) {
      const minT = rows[0].top,
        maxT = rows[n - 1].top;
      const range = Math.max(1, maxT - minT);
      const span = Math.min(usable, (n - 1) * compactGap);
      const startY = Math.round(rh / 2 - span / 2);
      rows.forEach(t => {
        t.y = Math.round(startY + (t.top - minT) / range * span);
        t.yBase = t.y;
      });
    }
    ticksRef.current = rows;
    setRailH(rh);
    setMode(dense ? "dense" : "compact");
    setTicks(rows);
    setBuckets(bks);
    computeActive();
  }, [feedRef, computeActive]);
  React.useLayoutEffect(() => {
    measure();
    const feed = feedRef.current;
    if (!feed) return;
    const onScroll = () => computeActive();
    feed.addEventListener("scroll", onScroll, {
      passive: true
    });
    const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => measure()) : null;
    if (ro) ro.observe(feed);
    window.addEventListener("resize", measure);
    return () => {
      feed.removeEventListener("scroll", onScroll);
      if (ro) ro.disconnect();
      window.removeEventListener("resize", measure);
    };
  }, [measure, computeActive, feedRef, messages]);
  const jump = t => {
    const feed = feedRef.current;
    if (!feed) return;
    const target = Math.max(0, Math.min(t.top - 20, feed.scrollHeight - feed.clientHeight));
    const start = feed.scrollTop;
    const dist = target - start;
    if (Math.abs(dist) < 2) {
      feed.scrollTop = target;
      return;
    }
    const reduce = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce) {
      feed.scrollTop = target;
      return;
    }
    const dur = Math.min(560, 200 + Math.abs(dist) * 0.45);
    const t0 = performance.now();
    const ease = p => 1 - Math.pow(1 - p, 3);
    const step = now => {
      const p = Math.min(1, (now - t0) / dur);
      feed.scrollTop = start + dist * ease(p);
      if (p < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
  };
  const onRailMove = e => {
    const r = railRef.current && railRef.current.getBoundingClientRect();
    if (r) setPointerY(e.clientY - r.top);
  };

  // Focus mark: nearest to cursor (dense) / hovered (compact).
  let focus = mode === "compact" ? hover : -1;
  if (mode === "dense" && pointerY != null && ticks.length) {
    let best = Infinity;
    ticks.forEach((t, i) => {
      const dd = Math.abs(t.yBase - pointerY);
      if (dd < best) {
        best = dd;
        focus = i;
      }
    });
  }
  const clampY = v => Math.max(12, Math.min(railH - 12, v));
  const tip = focus >= 0 && ticks[focus] ? ticks[focus] : null;
  const tipRenderY = tip ? mode === "dense" ? clampY(pointerY) : tip.y : 0;
  const popY = tip ? Math.min(Math.max(tipRenderY, 30), Math.max(30, railH - 30)) : 0;
  const renderDense = () => {
    const els = [];
    const winS = focus >= 0 ? Math.max(0, focus - DENSE_WIN) : -1;
    const winE = focus >= 0 ? Math.min(ticks.length - 1, focus + DENSE_WIN) : -1;
    const rTop = focus >= 0 ? clampY(pointerY + (winS - focus) * DENSE_PITCH) : 0;
    const rBot = focus >= 0 ? clampY(pointerY + (winE - focus) * DENSE_PITCH) : 0;
    buckets.forEach((b, bi) => {
      // Hide buckets behind the open lens; the filmstrip stands in for them.
      if (focus >= 0 && b.y >= rTop - 3 && b.y <= rBot + 3) return;
      const act = focus < 0 && active >= 0 && b.members.indexOf(active) >= 0;
      els.push(/*#__PURE__*/React.createElement("button", {
        key: "b" + bi,
        type: "button",
        tabIndex: -1,
        "aria-hidden": "true",
        className: "mcc-mmap-tick" + (b.count > 1 ? " is-bucket" : "") + (act ? " is-active" : ""),
        style: {
          top: b.y + "px",
          height: (b.count > 1 ? Math.min(7, 2 + b.count * 0.5) : 2) + "px"
        }
      }));
    });
    if (focus >= 0) {
      for (let i = winS; i <= winE; i++) {
        const o = i - focus,
          ao = Math.abs(o);
        const mag = ao === 0 ? " is-hover" : ao === 1 ? " is-near" : ao === 2 ? " is-near2" : "";
        els.push(/*#__PURE__*/React.createElement("button", {
          key: "r" + i,
          type: "button",
          tabIndex: -1,
          "aria-hidden": "true",
          className: "mcc-mmap-tick is-reveal" + mag,
          style: {
            top: clampY(pointerY + o * DENSE_PITCH) + "px"
          }
        }));
      }
    }
    return els;
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-mmap" + (mode === "dense" ? " is-dense" : ""),
    ref: railRef,
    "aria-hidden": ticks.length ? undefined : "true"
  }, mode === "dense" && /*#__PURE__*/React.createElement("div", {
    className: "mcc-mmap-hit",
    onMouseMove: onRailMove,
    onMouseLeave: () => setPointerY(null),
    onClick: () => {
      if (focus >= 0 && ticks[focus]) jump(ticks[focus]);
    }
  }), mode === "compact" && ticks.map((t, i) => {
    const dist = hover >= 0 ? Math.abs(i - hover) : 99;
    const mag = dist === 0 ? " is-hover" : dist === 1 ? " is-near" : dist === 2 ? " is-near2" : "";
    return /*#__PURE__*/React.createElement("button", {
      key: i,
      type: "button",
      className: "mcc-mmap-tick" + (i === active ? " is-active" : "") + mag,
      style: {
        top: t.y + "px"
      },
      onMouseEnter: () => setHover(i),
      onMouseLeave: () => setHover(h => h === i ? -1 : h),
      onFocus: () => setHover(i),
      onBlur: () => setHover(h => h === i ? -1 : h),
      onClick: () => jump(t),
      "aria-label": "Jump to your message · " + t.text
    });
  }), mode === "dense" && renderDense(), tip && /*#__PURE__*/React.createElement("div", {
    className: "mcc-mmap-pop",
    style: {
      top: popY + "px"
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-mmap-pop-text"
  }, tip.text), tip.time && /*#__PURE__*/React.createElement("span", {
    className: "mcc-mmap-pop-time"
  }, tip.time)));
}

// The maestro conversation · UIMessages over a switchable transport.
// Parts render via MccMessage (AiProtocol.jsx); the gate queue is derived
// from data-gate parts; the model chip cycles claude → gpt → harness.
function MccMaestroChat({
  layer,
  chatLen,
  rail
}) {
  const d = useMccDispatch();
  const {
    messages,
    status,
    sendMessage
  } = useBvChat({
    transport: bvGetTransport(d.harness, d.model),
    initialMessages: chatLen === "extreme" ? BV_SEED_EXTREME : chatLen === "stress" ? BV_SEED_STRESS : BV_SEED_MESSAGES
  });
  const gate = bvSelectGate(messages);
  const feedRef = React.useRef(null);
  React.useEffect(() => {
    const el = feedRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, status]);
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-chatcol",
    "data-screen-label": "Maestro \xB7 the conversation"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-chatcol-main"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-chat-feed mcc-chatcol-feed",
    ref: feedRef
  }, messages.map(m => /*#__PURE__*/React.createElement(MccMessage, {
    key: m.id,
    msg: m
  }))), /*#__PURE__*/React.createElement(MccChatMinimap, {
    feedRef: feedRef,
    messages: messages
  })), /*#__PURE__*/React.createElement("div", {
    className: "mcc-chatcol-foot"
  }, /*#__PURE__*/React.createElement(MccGateQueue, {
    items: gate
  }), /*#__PURE__*/React.createElement(MccPromptPlate, {
    className: "mcc-prompt--glass",
    placeholder: "Message maestro \xB7 anything beyond approve and send back\u2026",
    stop: status !== "ready",
    onSend: text => sendMessage({
      text
    }),
    railLeft: /*#__PURE__*/React.createElement(MccDispatchRail, {
      d: d,
      quiet: rail !== "full"
    })
  })));
}

// ── The frame ─────────────────────────────────────────────────────────────
// ── Maestro as the grown center · the full plane ──────────────
function MccMissionPlane() {
  const [view, setView] = React.useState(() => {
    try {
      return localStorage.getItem("mc4-view") || "feed";
    } catch {
      return "feed";
    }
  });
  const [filter, setFilter] = React.useState(null);
  const noop = () => {};
  React.useEffect(() => {
    try {
      localStorage.setItem("mc4-view", view);
    } catch {}
  }, [view]);
  const feedGroups = WK_GROUP_ORDER.map(state => ({
    state,
    items: WK_ITEMS.filter(i => i.state === state)
  })).filter(g => g.items.length > 0);
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-plane",
    "data-screen-label": "Maestro plane"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-plane-bar",
    style: {
      padding: "10px 22px 10px"
    }
  }, view === "feed" ? /*#__PURE__*/React.createElement("div", {
    className: "mc-chips",
    style: {
      flex: 1
    }
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mc-chip" + (filter === null ? " is-active" : ""),
    onClick: () => setFilter(null)
  }, "All"), feedGroups.map(g => {
    const meta = WK_STATES[g.state];
    return /*#__PURE__*/React.createElement("button", {
      key: g.state,
      type: "button",
      className: "mc-chip" + (filter === g.state ? " is-active" : ""),
      onClick: () => setFilter(filter === g.state ? null : g.state)
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: WK_TONE_COLOR[meta.tone]
      }
    }), meta.plain, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-count"
    }, g.items.length));
  })) : /*#__PURE__*/React.createElement("div", {
    style: {
      flex: 1
    }
  }), /*#__PURE__*/React.createElement(McvViewToggle, {
    view: view,
    onView: setView
  })), /*#__PURE__*/React.createElement("div", {
    className: "mcc-plane-body",
    "data-view": view
  }, view === "feed" && /*#__PURE__*/React.createElement(McvPlaneFeed, {
    items: WK_ITEMS,
    selectedId: null,
    onSelect: noop,
    vocab: "plain",
    receipts: true,
    signal: "undertow",
    filter: filter,
    onFilter: setFilter,
    hideFilters: true
  }), view === "board" && /*#__PURE__*/React.createElement(McvPlaneBoard, {
    items: WK_ITEMS,
    selectedId: null,
    onSelect: noop,
    vocab: "plain",
    receipts: true,
    signal: "undertow"
  }), view === "list" && /*#__PURE__*/React.createElement(McvPlaneList, {
    items: WK_ITEMS,
    selectedId: null,
    onSelect: noop,
    vocab: "plain",
    receipts: true
  })));
}
function MccMaestroLoopV2({
  initialScope = "root",
  initialMode = "workspace",
  app = false,
  theme = "light",
  onToggleTheme,
  onOpenView,
  chatLen,
  rail
}) {
  const noop = () => {};
  const [mode, setMode] = React.useState(initialMode);
  const [scope, setScope] = React.useState(initialScope);
  const [shut, setShut] = React.useState(() => app && typeof window !== "undefined" ? window.innerWidth < 1080 : false);
  const [fsOpen, setFsOpen] = React.useState(() => app && typeof window !== "undefined" ? window.innerWidth >= 1280 : true);
  const [navOpen, setNavOpen] = React.useState(() => {
    if (app && typeof window !== "undefined" && window.innerWidth < 1080) return false;
    try {
      return localStorage.getItem("bv-nav-open") !== "false";
    } catch {
      return true;
    }
  });
  const [cols, setCols] = React.useState(() => {
    const base = {
      dock: 320,
      chat: 430,
      fs: 380,
      split: 420,
      nav: 200
    };
    try {
      return {
        ...base,
        ...JSON.parse(localStorage.getItem("bv-ml-cols") || "{}")
      };
    } catch {
      return base;
    }
  });
  const [fileTabs, setFileTabs] = React.useState([]);
  const [chatTabs, setChatTabs] = React.useState([{
    id: "maestro",
    label: "maestro"
  }]);
  const [chatAct, setChatAct] = React.useState("maestro");
  const [view, setView] = React.useState({
    kind: "chat"
  });
  const [split, setSplit] = React.useState(null);
  const [dragging, setDragging] = React.useState(null);
  const [overDrop, setOverDrop] = React.useState(false);
  const fsScope = mode === "mission" ? "root" : scope;
  const fs = MCC_ML_FS[fsScope] || MCC_ML_FS.root;

  // Column resizing · every fixed column has a drag edge; widths persist.
  React.useEffect(() => {
    try {
      localStorage.setItem("bv-ml-cols", JSON.stringify(cols));
    } catch {}
  }, [cols]);
  React.useEffect(() => {
    try {
      localStorage.setItem("bv-nav-open", navOpen);
    } catch {}
  }, [navOpen]);
  const MCC_ML_CLAMP = {
    dock: [240, 440],
    chat: [360, 620],
    fs: [280, 480],
    split: [320, 640],
    nav: [160, 320]
  };
  const startDrag = (key, dir) => e => {
    e.preventDefault();
    const x0 = e.clientX,
      w0 = cols[key],
      [lo, hi] = MCC_ML_CLAMP[key];
    const move = ev => setCols(c => ({
      ...c,
      [key]: Math.max(lo, Math.min(hi, w0 + (ev.clientX - x0) * dir))
    }));
    const up = () => {
      window.removeEventListener("mousemove", move);
      window.removeEventListener("mouseup", up);
    };
    window.addEventListener("mousemove", move);
    window.addEventListener("mouseup", up);
  };

  // Responsive (app only): the FS pane yields first, then the dock.
  React.useEffect(() => {
    if (!app) return;
    let prev = window.innerWidth;
    const onR = () => {
      const w = window.innerWidth;
      if (w < 1280 && prev >= 1280) setFsOpen(false);
      if (w >= 1280 && prev < 1280) setFsOpen(true);
      if (w < 1080 && prev >= 1080) {
        setShut(true);
        setNavOpen(false);
      }
      if (w >= 1080 && prev < 1080) {
        setShut(false);
        try {
          setNavOpen(localStorage.getItem("bv-nav-open") !== "false");
        } catch {
          setNavOpen(true);
        }
      }
      prev = w;
    };
    window.addEventListener("resize", onR);
    return () => window.removeEventListener("resize", onR);
  }, [app]);
  const goMission = () => {
    setMode("mission");
    setSplit(null);
    setView({
      kind: "chat"
    });
  };
  const openMaestro = () => {
    setChatAct("maestro");
    if (!split) setView({
      kind: "chat"
    });
  };
  const goScope = s => {
    setScope(s);
    setMode("workspace");
  };
  const openFile = path => {
    setFileTabs(t => t.includes(path) ? t : [...t, path]);
    if (split) setSplit(path);else setView({
      kind: "file",
      path
    });
  };
  const clickFileTab = path => {
    if (split) setSplit(path);else setView({
      kind: "file",
      path
    });
  };
  const closeFile = path => {
    setFileTabs(t => t.filter(p => p !== path));
    if (split === path) {
      setSplit(null);
      setView({
        kind: "chat"
      });
    }
    if (view.kind === "file" && view.path === path) setView({
      kind: "chat"
    });
  };
  const clickChatTab = id => {
    setChatAct(id);
    if (!split) setView({
      kind: "chat"
    });
  };
  const newChat = () => {
    const n = chatTabs.length;
    const id = "sess-" + n;
    setChatTabs(c => [...c, {
      id,
      label: "session " + (n + 1)
    }]);
    setChatAct(id);
    if (!split) setView({
      kind: "chat"
    });
  };
  const closeChat = id => {
    setChatTabs(c => c.filter(x => x.id !== id));
    if (chatAct === id) setChatAct("maestro");
  };
  const session = chatTabs.find(c => c.id === chatAct) || chatTabs[0];
  const fileActive = p => split ? split === p : view.kind === "file" && view.path === p;
  const chatShowing = split !== null || view.kind === "chat";
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-fill"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-app",
    style: {
      gridTemplateColumns: (navOpen ? cols.nav : 56) + "px 1fr",
      transition: "grid-template-columns 0.15s ease"
    }
  }, /*#__PURE__*/React.createElement(MccTcSidebar, {
    scope: mode === "workspace" ? scope : "__none",
    setScope: goScope,
    onMission: goMission,
    missionActive: mode === "mission",
    resize: startDrag("nav", 1),
    collapsed: !navOpen,
    onOpenView: onOpenView
  }), /*#__PURE__*/React.createElement("div", {
    className: "bv-main"
  }, /*#__PURE__*/React.createElement(McvTopBar, {
    theme: theme,
    onToggleTheme: onToggleTheme || noop,
    onOpenMaestro: openMaestro,
    onWake: noop,
    waking: false,
    canWake: true,
    onShowIdea: noop,
    counts: {
      needYou: 1,
      stuck: 1
    },
    workers: ["claude", "bookkeeper"],
    wakes: MCC_TICK_WAKES,
    items: WK_ITEMS,
    onAttention: noop,
    onCommand: () => window.dispatchEvent(new CustomEvent("bv:command-open"))
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-ftabs",
    "data-screen-label": "Tab strip"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-prompt-iconbtn" + (navOpen ? " is-on" : ""),
    style: {
      width: 26,
      height: 26,
      flexShrink: 0,
      marginRight: 2
    },
    "aria-label": "Toggle sidebar",
    title: navOpen ? "Minimize sidebar" : "Expand sidebar",
    onClick: () => setNavOpen(v => !v)
  }, /*#__PURE__*/React.createElement(IcMlPanelLeft, {
    size: 14
  })), chatTabs.map(c => /*#__PURE__*/React.createElement("button", {
    key: c.id,
    type: "button",
    className: "mcc-ftab" + (chatShowing && chatAct === c.id ? " is-active" : ""),
    onClick: () => clickChatTab(c.id),
    title: c.id === "maestro" ? "The orchestrator's session · pinned" : "A session on " + fs.layer
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot bv-dot--pulse",
    style: {
      background: "var(--bv-info)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-ftab-name"
  }, c.label), c.id !== "maestro" && /*#__PURE__*/React.createElement("span", {
    className: "mcc-ftab-x",
    role: "button",
    "aria-label": "Close " + c.label,
    onClick: e => {
      e.stopPropagation();
      closeChat(c.id);
    }
  }, /*#__PURE__*/React.createElement(IcX, {
    size: 11
  })))), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-prompt-iconbtn",
    style: {
      width: 26,
      height: 26
    },
    "aria-label": "New session",
    title: "New session on " + fs.layer,
    onClick: newChat
  }, /*#__PURE__*/React.createElement(IcxPlus, {
    size: 14
  })), /*#__PURE__*/React.createElement("span", {
    className: "mcc-ftabs-spacer"
  }), fileTabs.map(p => /*#__PURE__*/React.createElement("button", {
    key: p,
    type: "button",
    draggable: mode === "workspace",
    className: "mcc-ftab mcc-ftab--in" + (fileActive(p) ? " is-active" : ""),
    onClick: () => clickFileTab(p),
    onDragStart: e => {
      e.dataTransfer.setData("text/plain", p);
      e.dataTransfer.effectAllowed = "move";
      setDragging(p);
    },
    onDragEnd: () => {
      setDragging(null);
      setOverDrop(false);
    },
    title: MCC_FS_DOCS[p] ? MCC_FS_DOCS[p].crumb + " · drag toward the chat to split" : p
  }, /*#__PURE__*/React.createElement(IcDoc, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-ftab-name"
  }, p.split("/").pop()), /*#__PURE__*/React.createElement("span", {
    className: "mcc-ftab-x",
    role: "button",
    "aria-label": "Close " + p,
    onClick: e => {
      e.stopPropagation();
      closeFile(p);
    }
  }, /*#__PURE__*/React.createElement(IcX, {
    size: 11
  })))), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-prompt-iconbtn" + (fsOpen ? " is-on" : ""),
    style: {
      width: 26,
      height: 26
    },
    "aria-label": "Toggle file pane",
    title: fsOpen ? "Hide files" : "Show files",
    onClick: () => setFsOpen(!fsOpen)
  }, /*#__PURE__*/React.createElement(IcMlPanel, {
    size: 14
  }))), /*#__PURE__*/React.createElement("div", {
    className: "mcc-mlrow",
    style: {
      gridTemplateColumns: (mode === "mission" ? "minmax(420px, 1fr) minmax(340px, " + cols.chat + "px)" : (shut ? "44px" : cols.dock + "px") + " minmax(0, 1fr)") + (fsOpen ? " " + cols.fs + "px" : "")
    }
  }, mode === "mission" ? /*#__PURE__*/React.createElement("div", {
    className: "mcc-mlcenter"
  }, view.kind === "file" ? /*#__PURE__*/React.createElement(MccFsDoc, {
    path: view.path
  }) : /*#__PURE__*/React.createElement(MccMissionPlane, null)) : /*#__PURE__*/React.createElement(MccMcDock, {
    shut: shut,
    onToggle: () => setShut(!shut),
    resize: startDrag("dock", 1)
  }), mode === "mission" ? /*#__PURE__*/React.createElement("div", {
    className: "mcc-chatside",
    "data-screen-label": "Chat docked right"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-coldrag mcc-coldrag--left",
    onMouseDown: startDrag("chat", -1),
    title: "Drag to resize"
  }), /*#__PURE__*/React.createElement(MccChatPane, {
    session: session,
    layer: fs.layer,
    chatLen: chatLen,
    rail: rail
  })) : /*#__PURE__*/React.createElement("div", {
    className: "mcc-mlcenter"
  }, split ? /*#__PURE__*/React.createElement("div", {
    className: "mcc-split",
    style: {
      gridTemplateColumns: "minmax(0, 1fr) " + cols.split + "px"
    }
  }, /*#__PURE__*/React.createElement(MccChatPane, {
    session: session,
    layer: fs.layer,
    chatLen: chatLen,
    rail: rail
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-splitpane",
    "data-screen-label": "Split file pane"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-coldrag mcc-coldrag--left",
    onMouseDown: startDrag("split", -1),
    title: "Drag to resize"
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-splitpane-head"
  }, /*#__PURE__*/React.createElement(IcDoc, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-ftab-name"
  }, split.split("/").pop()), /*#__PURE__*/React.createElement("button", {
    className: "mcc-panel-close",
    type: "button",
    "aria-label": "Close split",
    onClick: () => {
      setSplit(null);
      setView({
        kind: "chat"
      });
    }
  }, /*#__PURE__*/React.createElement(IcX, {
    size: 13
  }))), /*#__PURE__*/React.createElement(MccFsDoc, {
    path: split
  }))) : view.kind === "chat" ? /*#__PURE__*/React.createElement(MccChatPane, {
    session: session,
    layer: fs.layer,
    chatLen: chatLen,
    rail: rail
  }) : /*#__PURE__*/React.createElement(MccFsDoc, {
    path: view.path
  }), dragging && !split && mode === "workspace" && /*#__PURE__*/React.createElement("div", {
    className: "mcc-dropzone" + (overDrop ? " is-over" : ""),
    onDragOver: e => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      setOverDrop(true);
    },
    onDragLeave: () => setOverDrop(false),
    onDrop: e => {
      e.preventDefault();
      const p = e.dataTransfer.getData("text/plain") || dragging;
      setSplit(p);
      setView({
        kind: "chat"
      });
      setDragging(null);
      setOverDrop(false);
    }
  }, /*#__PURE__*/React.createElement("span", null, "Drop to view beside the chat"))), fsOpen && /*#__PURE__*/React.createElement("div", {
    className: "mcc-rpane"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-coldrag mcc-coldrag--left",
    onMouseDown: startDrag("fs", -1),
    title: "Drag to resize"
  }), /*#__PURE__*/React.createElement(MccFilePane, {
    entries: fs.entries(),
    label: fs.label,
    location: fs.location,
    worktree: fs.worktree,
    openPath: split || (view.kind === "file" ? view.path : null),
    onOpen: openFile
  }))))));
}
function MccMaestroLoop() {
  return /*#__PURE__*/React.createElement(MccMaestroLoopV2, {
    initialScope: "root"
  });
}
function MccMaestroLoopFolder() {
  return /*#__PURE__*/React.createElement(MccMaestroLoopV2, {
    initialScope: "core"
  });
}
function MccMaestroLoopMission() {
  return /*#__PURE__*/React.createElement(MccMaestroLoopV2, {
    initialMode: "mission"
  });
}

// ── The storyboard · ticks accumulate, the queue grows ───────────────────
function MccLoopStory() {
  const steps = [{
    label: "tick 09:15 · dispatched 2, nothing for you",
    cap: "The loop moves on its own. No decisions pending: the queue is an all-clear line, the prompt is just a prompt.",
    items: []
  }, {
    label: "tick 09:45 · a worker returned, judged clean",
    cap: "First stopgap: the run is at your gate. Maestro renders the decision above the prompt · chat stays the only surface.",
    items: [MCC_ML_GATE[0]]
  }, {
    label: "tick 10:15 · the import hit a missing scope",
    cap: "Second stopgap stacks beneath the first; the header now says what the pile is costing (3 queued items wait). Clear them in queue order or just talk.",
    items: MCC_ML_GATE
  }];
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-pad",
    style: {
      gap: 12
    }
  }, steps.map(s => /*#__PURE__*/React.createElement("div", {
    key: s.label,
    className: "mcc-cmp-study"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-cmp-study-label"
  }, s.label), /*#__PURE__*/React.createElement("div", {
    className: "mcc-ml-step"
  }, /*#__PURE__*/React.createElement(MccGateQueue, {
    items: s.items,
    mini: true
  }), /*#__PURE__*/React.createElement(MccPromptPlate, {
    mini: true,
    hint: null,
    placeholder: "Message maestro\u2026"
  })), /*#__PURE__*/React.createElement("p", {
    className: "mcc-caption"
  }, s.cap))));
}
Object.assign(window, {
  MccMaestroLoop,
  MccMaestroLoopFolder,
  MccMaestroLoopMission,
  MccMaestroLoopV2,
  MccLoopStory,
  MccGateQueue,
  MccTickCard,
  MccMcDock,
  MccMissionPlane,
  MccMaestroChat,
  MccChatPane,
  MCC_ML_FS
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/ConceptMaestroLoop.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/ConceptMcDock.jsx
try { (() => {
// Concepts canvas · the mission-control dock, restyled.
// The docked column in the maestro-loop frame was a flat list; these
// variations keep the FEED's vocabulary instead · group headers with tone
// dots, real work cards, the Undertow on running work. M1 is wired into
// the synthesis frames.

const MCC_MD_LIVELINE = {
  w3: "Edit reducer.ts · bun test 9 passed",
  w4: "Matching 41 of 63 · cloud sandbox"
};
const mccMdItems = ids => ids.map(id => WK_ITEMS.find(i => i.id === id));

// ── The feed body · group headers + cards, dock-compacted ────────────────
function MccDockFeedBody({
  filter
}) {
  const noop = () => {};
  const groups = [{
    state: "review",
    items: mccMdItems(["w1"]),
    kind: "attention"
  }, {
    state: "blocked",
    items: mccMdItems(["w2"]),
    kind: "attention"
  }, {
    state: "running",
    items: mccMdItems(["w3", "w4"]),
    kind: "running"
  }].filter(g => !filter || g.kind === filter);
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-dockfeed"
  }, groups.map(g => {
    const meta = WK_STATES[g.state];
    return /*#__PURE__*/React.createElement("section", {
      key: g.state,
      className: "mc-group"
    }, /*#__PURE__*/React.createElement("div", {
      className: "mc-group-header"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-group-label"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: WK_TONE_COLOR[meta.tone]
      }
    }), meta.plain), /*#__PURE__*/React.createElement("span", {
      className: "mc-group-count"
    }, g.items.length)), /*#__PURE__*/React.createElement("div", {
      className: "mc-group-cards"
    }, g.items.map(item => /*#__PURE__*/React.createElement(McvLiveCard, {
      key: item.id,
      item: item,
      selected: false,
      onSelect: noop
    }))));
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-dock-foot"
  }, "4 queued \xB7 1 standing \xB7 maestro holds them until a worktree frees"));
}

// ── Compact live row · the Undertow at one-line scale ────────────────────
function MccDockLiveRow({
  item
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-undertow-halo mcc-halo--tidalnebula mcc-dockrow-halo"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-halo-spin-layer"
  }), /*#__PURE__*/React.createElement("button", {
    className: "mcc-dockrow",
    type: "button"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 13,
      height: 13
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-dockrow-body"
  }, /*#__PURE__*/React.createElement("b", null, item.project), /*#__PURE__*/React.createElement("span", {
    className: "mcc-caret"
  }, MCC_MD_LIVELINE[item.id])), /*#__PURE__*/React.createElement("span", {
    className: "mcc-loops-t",
    style: {
      marginTop: 2
    }
  }, item.time)));
}

// ── Spec wrapper for the artboards ────────────────────────────────────────
function MccDockSpec({
  caption,
  children,
  body
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-side-pad"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-side",
    style: {
      width: 324,
      display: "flex",
      flexDirection: "column"
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-mcol-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-panel-label"
  }, "Maestro"), /*#__PURE__*/React.createElement("span", {
    className: "mcc-loops-count",
    style: {
      marginLeft: "auto"
    }
  }, "2 live"), /*#__PURE__*/React.createElement("button", {
    className: "mcc-panel-close",
    type: "button",
    "aria-label": "Collapse"
  }, /*#__PURE__*/React.createElement(IcChevrons, {
    size: 13,
    style: {
      transform: "rotate(90deg)"
    }
  }))), /*#__PURE__*/React.createElement("div", {
    className: "mcc-mcol-body"
  }, children)), /*#__PURE__*/React.createElement("p", {
    className: "mcc-caption"
  }, caption));
}

// M0 · Today · the flat list (reference).
function MccDockToday() {
  return /*#__PURE__*/React.createElement(MccDockSpec, {
    caption: "The reference: flat rows, no grouping, no cards. Quiet, but it speaks a different language than the plane \xB7 the feed's groups and the Undertow vanish at the dock."
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-sess-list"
  }, MCC_AT_LOOPS.map(l => /*#__PURE__*/React.createElement("button", {
    key: l.title,
    className: "mcc-sess",
    type: "button"
  }, /*#__PURE__*/React.createElement(MccLoopDot, {
    kind: l.kind
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-sess-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-sess-label"
  }, l.title), /*#__PURE__*/React.createElement("span", {
    className: "mcc-sess-meta" + (l.kind === "live" ? " mcc-caret" : "")
  }, l.line)), /*#__PURE__*/React.createElement("span", {
    className: "mcc-loops-t"
  }, l.t)))));
}

// M1 · The feed dock · the plane's own vocabulary, compacted.
function MccDockFeed() {
  return /*#__PURE__*/React.createElement(MccDockSpec, {
    caption: "The lead, wired into the synthesis frames: the same groups, cards, and Undertow as the plane \xB7 just narrower. Group hints drop, paddings tighten, queued work folds into one quiet footer line. The dock is the feed, not a summary of it."
  }, /*#__PURE__*/React.createElement(MccDockFeedBody, {
    filter: null
  }));
}

// M2 · Attention cards + live rows · full weight only where a human acts.
function MccDockAttention() {
  const noop = () => {};
  return /*#__PURE__*/React.createElement(MccDockSpec, {
    caption: "A hierarchy of weight: needs-you keeps full cards (they're the decisions), running compresses to one-line Undertow rows (it's ambient), everything else is the footer. Densest feed-true take."
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-dockfeed"
  }, /*#__PURE__*/React.createElement("section", {
    className: "mc-group"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-group-header"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-group-label"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      background: WK_TONE_COLOR.review
    }
  }), "Needs you"), /*#__PURE__*/React.createElement("span", {
    className: "mc-group-count"
  }, "2")), /*#__PURE__*/React.createElement("div", {
    className: "mc-group-cards"
  }, mccMdItems(["w1", "w2"]).map(item => /*#__PURE__*/React.createElement(McvLiveCard, {
    key: item.id,
    item: item,
    selected: false,
    onSelect: noop
  })))), /*#__PURE__*/React.createElement("section", {
    className: "mc-group"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-group-header"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-group-label"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      background: WK_TONE_COLOR.active
    }
  }), "Running"), /*#__PURE__*/React.createElement("span", {
    className: "mc-group-count"
  }, "2")), /*#__PURE__*/React.createElement("div", {
    className: "mc-group-cards"
  }, mccMdItems(["w3", "w4"]).map(item => /*#__PURE__*/React.createElement(MccDockLiveRow, {
    key: item.id,
    item: item
  })))), /*#__PURE__*/React.createElement("div", {
    className: "mcc-dock-foot"
  }, "4 queued \xB7 1 standing \xB7 maestro holds them until a worktree frees")));
}

// M3 · Chips + feed · the plane's filter carried to the edge.
function MccDockChips() {
  const [filter, setFilter] = React.useState(null);
  const chip = (id, label, dot, count) => /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mc-chip" + (filter === id ? " is-active" : ""),
    onClick: () => setFilter(filter === id ? null : id)
  }, dot && /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      background: dot
    }
  }), label, count != null && /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-count"
  }, count));
  return /*#__PURE__*/React.createElement(MccDockSpec, {
    caption: "M1 plus the feed's chips: filter the dock to attention or running without touching the plane. Earns its row once the workspace has a dozen live loops; below that it's chrome."
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-chips",
    style: {
      padding: "2px 10px 8px"
    }
  }, chip(null, "All", null, 4), chip("attention", "Needs you", "var(--bv-blue-accent)", 2), chip("running", "Running", "var(--bv-info)", 2)), /*#__PURE__*/React.createElement(MccDockFeedBody, {
    filter: filter
  }));
}
Object.assign(window, {
  MccDockFeedBody,
  MccDockLiveRow,
  MccDockToday,
  MccDockFeed,
  MccDockAttention,
  MccDockChips
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/ConceptMcDock.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/ConceptNavIA.jsx
try { (() => {
// Concept · sidebar architecture. The canvas already asked "what is the nav a
// list OF"; this answers "what are the top-level destinations, and where do
// History + Knowledge slot in". BvNav is the canonical sidebar, reused by the
// History and Knowledge full-page frames so the chrome is identical everywhere.

const IcSearch = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
  cx: "11",
  cy: "11",
  r: "8"
}), /*#__PURE__*/React.createElement("path", {
  d: "m21 21-4.3-4.3"
}));
const IcHistory = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M3 12a9 9 0 1 0 3-6.7L3 8"
}), /*#__PURE__*/React.createElement("path", {
  d: "M3 3v5h5"
}), /*#__PURE__*/React.createElement("path", {
  d: "M12 7v5l3 2"
}));
const IcGraph = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
  cx: "5",
  cy: "6",
  r: "2.5"
}), /*#__PURE__*/React.createElement("circle", {
  cx: "19",
  cy: "8",
  r: "2.5"
}), /*#__PURE__*/React.createElement("circle", {
  cx: "12",
  cy: "18",
  r: "2.5"
}), /*#__PURE__*/React.createElement("path", {
  d: "M7.2 7.1 16.8 9M6.4 8.2l4.6 7.6M17.7 10.2l-4.6 6"
}));
const IcInbox = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M22 12h-6l-2 3h-4l-2-3H2"
}), /*#__PURE__*/React.createElement("path", {
  d: "M5.5 5.1 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.5-6.9A2 2 0 0 0 16.8 4H7.2a2 2 0 0 0-1.7 1.1z"
}));
const IcUsers = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"
}), /*#__PURE__*/React.createElement("circle", {
  cx: "9",
  cy: "7",
  r: "4"
}), /*#__PURE__*/React.createElement("path", {
  d: "M22 21v-2a4 4 0 0 0-3-3.9"
}), /*#__PURE__*/React.createElement("path", {
  d: "M16 3.1a4 4 0 0 1 0 7.8"
}));
const IcMessage = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"
}));

// ── The workspace tree rows (places) · shared across the IA frames ─────────
function NavTreeRows() {
  const sbText = {
    flex: 1,
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    textAlign: "left"
  };
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button"
  }, /*#__PURE__*/React.createElement(IcFolderOpen, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "hawthorne"), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, "1/6")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 28
    }
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "hawthorne-core"), /*#__PURE__*/React.createElement("span", {
    className: "bv-sb-badge"
  }, "1")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 28
    }
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "hawthorne-db"), /*#__PURE__*/React.createElement("span", {
    className: "bv-sb-badge"
  }, "1")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button"
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "genesis"), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, "0/1")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 28
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 13,
      height: 13
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "@genesis/projection")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button"
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "ops"), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, "0/1")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 28
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 13,
      height: 13
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "bookkeeping")));
}
function NavBench() {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-sb-bench",
    title: "The bench \xB7 live workers, the orchestrator first among them"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-comet",
    style: {
      width: 15,
      height: 15
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-comet-core"
  })), /*#__PURE__*/React.createElement("span", {
    className: "mcc-bench-faces"
  }, /*#__PURE__*/React.createElement(McAvatar, {
    name: "claude",
    color: "var(--bv-blue)",
    size: 20
  }), /*#__PURE__*/React.createElement(McAvatar, {
    name: "bookkeeper",
    color: "var(--bv-purple, #7c6cf0)",
    size: 20
  })), /*#__PURE__*/React.createElement("span", {
    className: "mcc-sb-sub",
    style: {
      marginLeft: 2
    }
  }, "2 live \xB7 next 13m"));
}
const IcArrowR = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M5 12h14M13 6l6 6-6 6"
}));

// Today's runs, the looks as notches, the live one under the tidepool.
const AUTOP_RUNS = [{
  l: 6,
  w: 4
}, {
  l: 30,
  w: 1.6
}, {
  l: 36,
  w: 1.1
}, {
  l: 44,
  w: 21
}, {
  l: 67,
  w: 9
}, {
  l: 78,
  w: 8,
  live: true
}];
const AUTOP_LOOKS = [30, 65];
const AUTOP_WHERE = [{
  title: "Close the execution loop (M1b)",
  crumb: "hawthorne-engine",
  dur: "3h 50m",
  state: "done"
}, {
  title: "Reduce NDJSON to a phase machine",
  crumb: "genesis / projection",
  dur: "1h 18m",
  state: "live"
}, {
  title: "Nightly digest",
  crumb: "ops",
  dur: "31m",
  state: "routine"
}];
function NavAutonomy({
  onOpenView
}) {
  const [open, setOpen] = React.useState(false);
  const [pos, setPos] = React.useState(null);
  const cardRef = React.useRef(null);
  const timer = React.useRef(null);
  const place = () => {
    const el = cardRef.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const W = 332;
    let left = r.left;
    left = Math.max(8, Math.min(left, window.innerWidth - W - 8));
    setPos({
      left,
      bottom: window.innerHeight - r.top + 8
    });
  };
  const show = () => {
    clearTimeout(timer.current);
    place();
    setOpen(true);
  };
  const hide = () => {
    clearTimeout(timer.current);
    timer.current = setTimeout(() => setOpen(false), 140);
  };
  React.useEffect(() => () => clearTimeout(timer.current), []);
  const pop = open && pos && ReactDOM.createPortal(/*#__PURE__*/React.createElement("div", {
    className: "autop",
    style: {
      left: pos.left,
      bottom: pos.bottom
    },
    onMouseEnter: show,
    onMouseLeave: hide
  }, /*#__PURE__*/React.createElement("div", {
    className: "autop-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "autop-head-main"
  }, /*#__PURE__*/React.createElement("span", {
    className: "autop-label"
  }, "Unsupervised \xB7 today"), /*#__PURE__*/React.createElement("span", {
    className: "autop-big"
  }, "6h 24", /*#__PURE__*/React.createElement("small", null, "m"))), /*#__PURE__*/React.createElement("span", {
    className: "autop-delta"
  }, /*#__PURE__*/React.createElement(IcArrowR, {
    size: 12,
    style: {
      transform: "rotate(-45deg)"
    }
  }), "+18%")), /*#__PURE__*/React.createElement("div", {
    className: "autop-tl"
  }, /*#__PURE__*/React.createElement("div", {
    className: "autop-track",
    title: "Each block is a run; each notch is a moment you looked"
  }, AUTOP_RUNS.map((b, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    className: "autop-run" + (b.live ? " is-live" : ""),
    style: {
      left: b.l + "%",
      width: b.w + "%"
    }
  })), AUTOP_LOOKS.map((l, i) => /*#__PURE__*/React.createElement("span", {
    key: "k" + i,
    className: "autop-look",
    style: {
      left: l + "%"
    }
  }))), /*#__PURE__*/React.createElement("div", {
    className: "autop-ticks"
  }, /*#__PURE__*/React.createElement("span", null, "12a"), /*#__PURE__*/React.createElement("span", null, "9a"), /*#__PURE__*/React.createElement("span", null, "3p"), /*#__PURE__*/React.createElement("span", null, "now"))), /*#__PURE__*/React.createElement("div", {
    className: "autop-stats"
  }, /*#__PURE__*/React.createElement("div", {
    className: "autop-stat"
  }, /*#__PURE__*/React.createElement("span", {
    className: "autop-stat-val"
  }, "2"), /*#__PURE__*/React.createElement("span", {
    className: "autop-stat-lab"
  }, "looks today")), /*#__PURE__*/React.createElement("div", {
    className: "autop-stat"
  }, /*#__PURE__*/React.createElement("span", {
    className: "autop-stat-val"
  }, "3h 50m"), /*#__PURE__*/React.createElement("span", {
    className: "autop-stat-lab"
  }, "longest run")), /*#__PURE__*/React.createElement("div", {
    className: "autop-stat"
  }, /*#__PURE__*/React.createElement("span", {
    className: "autop-stat-val"
  }, "7"), /*#__PURE__*/React.createElement("span", {
    className: "autop-stat-lab"
  }, "sessions"))), /*#__PURE__*/React.createElement("div", {
    className: "autop-where"
  }, /*#__PURE__*/React.createElement("div", {
    className: "autop-where-label"
  }, "Where the hours went"), AUTOP_WHERE.map((s, i) => /*#__PURE__*/React.createElement("div", {
    className: "autop-row",
    key: i
  }, s.state === "live" ? /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 11,
      height: 11,
      flexShrink: 0
    }
  }) : /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      width: 8,
      height: 8,
      flexShrink: 0,
      background: s.state === "done" ? "var(--bv-success)" : "var(--bv-gray-400)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "autop-row-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "autop-row-title"
  }, s.title), /*#__PURE__*/React.createElement("span", {
    className: "autop-row-crumb"
  }, s.crumb, s.state === "routine" ? " · routine" : "")), /*#__PURE__*/React.createElement("span", {
    className: "autop-row-dur"
  }, s.dur)))), /*#__PURE__*/React.createElement("div", {
    className: "autop-foot"
  }, /*#__PURE__*/React.createElement("span", {
    className: "autop-foot-note"
  }, "A look is any time you stepped in."), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "autop-link",
    onClick: () => {
      setOpen(false);
      onOpenView && onOpenView("history");
    }
  }, "Open History", /*#__PURE__*/React.createElement(IcArrowR, null)))), document.body);
  return /*#__PURE__*/React.createElement("div", {
    ref: cardRef,
    style: {
      margin: "0 2px"
    },
    onMouseEnter: show,
    onMouseLeave: hide,
    tabIndex: 0,
    onFocus: show,
    onBlur: hide
  }, /*#__PURE__*/React.createElement(DsAutonomyScoreboard, {
    hours: "6h 24m",
    sub: "2 looks \xB7 longest run 3h 50m",
    segments: [{
      start: 0,
      width: 34
    }, {
      start: 36,
      width: 42
    }, {
      start: 80,
      width: 14,
      live: true
    }],
    notches: [34, 78],
    style: {
      margin: 0,
      cursor: "default",
      borderColor: open ? "var(--bv-border-15)" : undefined,
      background: open ? "var(--bv-frost-4)" : undefined,
      transition: "border-color var(--bv-dur-fast) var(--bv-ease-standard), background var(--bv-dur-fast)"
    }
  }, pop));
}

// ── The canonical sidebar · reused by History + Knowledge pages ────────────
function BvNav({
  active,
  inApp
}) {
  const item = (id, icon, label, badge) => /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item" + (active === id ? " is-active" : ""),
    type: "button"
  }, icon, /*#__PURE__*/React.createElement("span", {
    className: "mcc-sb-text"
  }, label), badge != null && /*#__PURE__*/React.createElement("span", {
    className: "bv-sb-badge"
  }, badge));
  return /*#__PURE__*/React.createElement("aside", {
    className: "bv-sidebar mcc-nav" + (inApp ? "" : " mcc-side"),
    "data-screen-label": "Canonical sidebar"
  }, /*#__PURE__*/React.createElement("button", {
    className: "bv-ws-switch",
    type: "button"
  }, /*#__PURE__*/React.createElement("img", {
    className: "bv-ws-logo",
    src: "../../assets/broomva-blackhole-logo.png",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", {
    className: "bv-ws-name"
  }, "Broomva"), /*#__PURE__*/React.createElement(IcChevrons, {
    size: 14
  })), /*#__PURE__*/React.createElement("button", {
    className: "mcc-sb-cmd",
    type: "button"
  }, /*#__PURE__*/React.createElement(IcSearch, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, "Search or run a command"), /*#__PURE__*/React.createElement("kbd", null, "\u2318K")), /*#__PURE__*/React.createElement("nav", {
    className: "mcc-sb-col",
    style: {
      marginTop: 4
    }
  }, item("needs", /*#__PURE__*/React.createElement(IcInbox, {
    size: 16
  }), "Needs you", 2), item("mc", /*#__PURE__*/React.createElement(IcBoard, null), "Maestro")), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-section-label"
  }, "Workspace"), /*#__PURE__*/React.createElement("div", {
    className: "mcc-sb-col"
  }, /*#__PURE__*/React.createElement(NavTreeRows, null)), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-section-label"
  }, "Library"), /*#__PURE__*/React.createElement("div", {
    className: "mcc-sb-col"
  }, item("history", /*#__PURE__*/React.createElement(IcHistory, {
    size: 16
  }), "History"), item("knowledge", /*#__PURE__*/React.createElement(IcGraph, {
    size: 16
  }), "Knowledge")), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-spacer"
  }), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-section-label",
    style: {
      paddingBottom: 6
    }
  }, "Bench"), /*#__PURE__*/React.createElement(NavBench, null), /*#__PURE__*/React.createElement(NavAutonomy, null), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      marginTop: 2
    }
  }, /*#__PURE__*/React.createElement(McAvatar, {
    name: "Ana Diaz",
    color: "var(--bv-gray-600)",
    size: 18
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      textAlign: "left"
    }
  }, "Ana Diaz"), /*#__PURE__*/React.createElement(IcSettings, {
    size: 15
  })));
}

// ── IA0 · The inventory · what earns a place in the sidebar ────────────────
const NAV_INVENTORY = [{
  name: "Needs you",
  role: "The gate · clean runs + blocks waiting on a human",
  verdict: "in",
  note: "first verb"
}, {
  name: "Maestro",
  role: "The plane · work sorted by what only you can decide",
  verdict: "in",
  note: "home"
}, {
  name: "Workspace",
  role: "Places · the FS tree, folders are work at any scale",
  verdict: "in",
  note: "the backbone"
}, {
  name: "History",
  role: "Sessions · every run, yours and the loop's",
  verdict: "lens",
  note: "a projection, not a place"
}, {
  name: "Knowledge",
  role: "The graph · frontmatter entities + related: edges",
  verdict: "lens",
  note: "a projection, not a place"
}, {
  name: "The bench",
  role: "Presence · live workers, maestro first",
  verdict: "dock",
  note: "footer, not nav"
}, {
  name: "Autonomy clock",
  role: "The score · unsupervised hours, next look",
  verdict: "dock",
  note: "footer"
}, {
  name: "Command / search",
  role: "Jump to any folder, session, or entity",
  verdict: "in",
  note: "top, ⌘K"
}, {
  name: "Sessions list",
  role: "Recent conversations, newest first",
  verdict: "out",
  note: "→ lives in History"
}, {
  name: "Settings",
  role: "Engine room · runners, credentials, scopes",
  verdict: "tuck",
  note: "by the account"
}];
const NAV_VERDICT = {
  in: {
    c: "var(--bv-success)",
    t: "nav"
  },
  lens: {
    c: "var(--bv-blue)",
    t: "library"
  },
  dock: {
    c: "var(--bv-blue-accent)",
    t: "docked"
  },
  tuck: {
    c: "var(--bv-gray-500)",
    t: "tucked"
  },
  out: {
    c: "var(--bv-warning)",
    t: "out"
  }
};
function MccNavInventory() {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-pad",
    style: {
      gap: 10
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-inv"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-inv-row mcc-inv-head"
  }, /*#__PURE__*/React.createElement("span", null, "Candidate"), /*#__PURE__*/React.createElement("span", null, "What it is"), /*#__PURE__*/React.createElement("span", null, "Where it lands")), NAV_INVENTORY.map(r => {
    const v = NAV_VERDICT[r.verdict];
    return /*#__PURE__*/React.createElement("div", {
      key: r.name,
      className: "mcc-inv-row"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mcc-inv-name"
    }, r.name), /*#__PURE__*/React.createElement("span", {
      className: "mcc-inv-role"
    }, r.role), /*#__PURE__*/React.createElement("span", {
      className: "mcc-inv-verdict"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mcc-inv-pill",
      style: {
        color: v.c,
        borderColor: "color-mix(in oklch, " + v.c + " 40%, transparent)"
      }
    }, v.t), /*#__PURE__*/React.createElement("span", {
      className: "mcc-inv-note"
    }, r.note)));
  })), /*#__PURE__*/React.createElement("p", {
    className: "mcc-caption"
  }, "The test isn't \"is it useful\" \xB7 everything's useful. It's ", /*#__PURE__*/React.createElement("b", null, "what kind of thing is it."), " Verbs and places are nav; presence and the score are docked furniture; sessions and the graph are ", /*#__PURE__*/React.createElement("i", null, "projections"), " of the work \xB7 powerful lenses, so they get a Library group, never the backbone. The old \"recent sessions\" list is the one thing that leaves: it graduates into History."));
}

// ── IA1 · Canonical (the lead) ─────────────────────────────────────────────
function MccNavCanonical() {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-side-pad"
  }, /*#__PURE__*/React.createElement(BvNav, {
    active: "mc"
  }), /*#__PURE__*/React.createElement("p", {
    className: "mcc-caption"
  }, "The lead: a command surface up top, two verbs (the gate, the plane), the ", /*#__PURE__*/React.createElement("b", null, "Workspace"), " tree as the backbone, then a ", /*#__PURE__*/React.createElement("b", null, "Library"), " of lenses \xB7 History and Knowledge \xB7 that read across the work without being places. The bench, the autonomy clock and the account settle into the footer. Six destinations, one score, never a flat dump."));
}

// ── IA2 · Flat destinations ───────────────────────────────────────────────
function MccNavFlat() {
  const sbText = {
    flex: 1,
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    textAlign: "left"
  };
  const row = (icon, label, badge, active) => /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item" + (active ? " is-active" : ""),
    type: "button"
  }, icon, /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, label), badge != null && /*#__PURE__*/React.createElement("span", {
    className: "bv-sb-badge"
  }, badge));
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-side-pad"
  }, /*#__PURE__*/React.createElement("aside", {
    className: "bv-sidebar mcc-side mcc-nav",
    "data-screen-label": "Flat destinations"
  }, /*#__PURE__*/React.createElement("button", {
    className: "bv-ws-switch",
    type: "button"
  }, /*#__PURE__*/React.createElement("img", {
    className: "bv-ws-logo",
    src: "../../assets/broomva-blackhole-logo.png",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", {
    className: "bv-ws-name"
  }, "Broomva"), /*#__PURE__*/React.createElement(IcChevrons, {
    size: 14
  })), /*#__PURE__*/React.createElement("button", {
    className: "mcc-sb-cmd",
    type: "button"
  }, /*#__PURE__*/React.createElement(IcSearch, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", null, "Search\u2026"), /*#__PURE__*/React.createElement("kbd", null, "\u2318K")), /*#__PURE__*/React.createElement("nav", {
    className: "mcc-sb-col",
    style: {
      marginTop: 4
    }
  }, row(/*#__PURE__*/React.createElement(IcInbox, {
    size: 16
  }), "Needs you", 2, true), row(/*#__PURE__*/React.createElement(IcBoard, null), "Maestro"), row(/*#__PURE__*/React.createElement(IcLayers, {
    size: 15
  }), "Workspace"), row(/*#__PURE__*/React.createElement(IcHistory, {
    size: 16
  }), "History"), row(/*#__PURE__*/React.createElement(IcGraph, {
    size: 16
  }), "Knowledge"), row(/*#__PURE__*/React.createElement(IcUsers, {
    size: 16
  }), "Bench", "2"), row(/*#__PURE__*/React.createElement(IcSettings, {
    size: 15
  }), "Settings")), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-spacer"
  }), /*#__PURE__*/React.createElement(NavAutonomy, null)), /*#__PURE__*/React.createElement("p", {
    className: "mcc-caption"
  }, "The literal seven, flat. Honest and dead simple \xB7 every destination is one click, no nesting to tend. The cost: ", /*#__PURE__*/React.createElement("b", null, "Workspace"), " hides the tree behind a click, so the folders that are the actual work go quiet, and the bench loses its faces. Best when the workspace is small or the operator lives in Maestro."));
}

// ── IA3 · Icon rail + reveal ──────────────────────────────────────────────
function MccNavRail() {
  const rail = [{
    ic: /*#__PURE__*/React.createElement(IcInbox, {
      size: 19
    }),
    on: false,
    badge: 2
  }, {
    ic: /*#__PURE__*/React.createElement(IcBoard, null),
    on: true
  }, {
    ic: /*#__PURE__*/React.createElement(IcLayers, {
      size: 18
    }),
    on: false
  }, {
    ic: /*#__PURE__*/React.createElement(IcHistory, {
      size: 19
    }),
    on: false
  }, {
    ic: /*#__PURE__*/React.createElement(IcGraph, {
      size: 19
    }),
    on: false
  }];
  const sbText = {
    flex: 1,
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    textAlign: "left"
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-side-pad"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-railwrap mcc-side",
    "data-screen-label": "Icon rail + reveal"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-rail"
  }, /*#__PURE__*/React.createElement("img", {
    className: "bv-ws-logo",
    src: "../../assets/broomva-blackhole-logo.png",
    alt: "",
    style: {
      width: 26,
      height: 26,
      marginBottom: 4
    }
  }), rail.map((r, i) => /*#__PURE__*/React.createElement("button", {
    key: i,
    className: "mcc-rail-btn" + (r.on ? " is-on" : ""),
    type: "button"
  }, r.ic, r.badge != null && /*#__PURE__*/React.createElement("span", {
    className: "mcc-rail-badge"
  }, r.badge))), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-spacer"
  }), /*#__PURE__*/React.createElement("button", {
    className: "mcc-rail-btn",
    type: "button"
  }, /*#__PURE__*/React.createElement(IcUsers, {
    size: 18
  })), /*#__PURE__*/React.createElement(McAvatar, {
    name: "Ana Diaz",
    color: "var(--bv-gray-600)",
    size: 26
  })), /*#__PURE__*/React.createElement("div", {
    className: "mcc-rail-reveal"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-reveal-head"
  }, "Maestro"), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-section-label",
    style: {
      paddingTop: 4
    }
  }, "Workspace"), /*#__PURE__*/React.createElement("div", {
    className: "mcc-sb-col"
  }, /*#__PURE__*/React.createElement(NavTreeRows, null)), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-spacer"
  }), /*#__PURE__*/React.createElement(NavBench, null))), /*#__PURE__*/React.createElement("p", {
    className: "mcc-caption"
  }, "The rail keeps all seven destinations one click away in 52px, and the second column reveals the ", /*#__PURE__*/React.createElement("i", null, "contents"), " of whichever you're in \xB7 here, Maestro's workspace tree. Space-efficient and calm; the tradeoff is a hover/click to read any label, so it rewards a power user who's learned the icons."));
}

// Sidebar width · the full-page frames read the same persisted column the app's
// drag-resize writes, so the sidebar never jumps when switching views.
function bvNavGrid() {
  let w = 200;
  try {
    w = JSON.parse(localStorage.getItem("bv-ml-cols") || "{}").nav || 200;
  } catch {}
  return Math.round(w) + "px 1fr";
}

// The app's actual workspace tree · mirrors MccTcSidebar so the sidebar reads
// identically on the full-page frames (History / Settings / Account). Rows
// jump back into the app.
function AppTreeRows({
  onOpen
}) {
  const sbText = {
    flex: 1,
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    textAlign: "left"
  };
  const open = onOpen || (() => {});
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    onClick: open,
    title: "The workspace root \xB7 ~/Broomva"
  }, /*#__PURE__*/React.createElement(IcFolderOpen, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "Broomva"), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, "3 places")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 24
    },
    onClick: open
  }, /*#__PURE__*/React.createElement(IcFolderOpen, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "hawthorne"), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, "1/6")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 42
    },
    onClick: open
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "hawthorne-core"), /*#__PURE__*/React.createElement("span", {
    className: "bv-sb-badge"
  }, "1")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 42
    },
    onClick: open
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "hawthorne-db"), /*#__PURE__*/React.createElement("span", {
    className: "bv-sb-badge"
  }, "1")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 24
    },
    onClick: open
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "genesis"), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, "0/1")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 42
    },
    onClick: open
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 13,
      height: 13
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "@genesis/projection")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 24
    },
    onClick: open
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "ops"), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, "0/1")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 42
    },
    onClick: open
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 13,
      height: 13
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "bookkeeping")));
}

// ── IA4 · Tree-led, lenses pinned (the chosen direction) ──────────────────
// The tree-led sidebar itself · reused by the IA4 frame AND the History /
// Knowledge pages (pass inApp). `active` is the lit lens; `attention` drives the
// adaptive primary (Needs you + count → Maestro when the gate is clear).
function BvNavTree({
  active,
  attention = 2,
  inApp,
  renderTree,
  onNav
}) {
  const go = id => onNav && onNav(id);
  const lens = (id, icon, label) => /*#__PURE__*/React.createElement("button", {
    className: "mcc-lens" + (active === id ? " is-active" : ""),
    type: "button",
    onClick: () => go(id)
  }, icon, label);
  return /*#__PURE__*/React.createElement("aside", {
    className: "bv-sidebar mcc-nav" + (inApp ? "" : " mcc-side"),
    "data-screen-label": "Tree-led nav"
  }, /*#__PURE__*/React.createElement("button", {
    className: "bv-ws-switch",
    type: "button"
  }, /*#__PURE__*/React.createElement("img", {
    className: "bv-ws-logo",
    src: "../../assets/broomva-blackhole-logo.png",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", {
    className: "bv-ws-name"
  }, "Broomva"), /*#__PURE__*/React.createElement(IcChevrons, {
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    className: "mcc-lensbar"
  }, attention > 0 ? /*#__PURE__*/React.createElement("button", {
    className: "mcc-lens" + (active === "needs" ? " is-active" : ""),
    type: "button",
    onClick: () => go("app")
  }, /*#__PURE__*/React.createElement(IcInbox, {
    size: 14
  }), "Needs you", /*#__PURE__*/React.createElement("span", {
    className: "mcc-lens-badge"
  }, attention)) : /*#__PURE__*/React.createElement("button", {
    className: "mcc-lens" + (active === "needs" ? " is-active" : ""),
    type: "button",
    onClick: () => go("app")
  }, /*#__PURE__*/React.createElement(IcBoard, null), "Maestro"), lens("history", /*#__PURE__*/React.createElement(IcHistory, {
    size: 14
  }), "History"), lens("knowledge", /*#__PURE__*/React.createElement(IcGraph, {
    size: 14
  }), "Knowledge")), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-section-label"
  }, "Workspace"), renderTree ? renderTree() : /*#__PURE__*/React.createElement("div", {
    className: "mcc-sb-col"
  }, /*#__PURE__*/React.createElement(AppTreeRows, {
    onOpen: () => go("app")
  })), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-spacer"
  }), /*#__PURE__*/React.createElement(NavAutonomy, null), /*#__PURE__*/React.createElement("div", {
    className: "mcc-nav-foot"
  }, /*#__PURE__*/React.createElement("button", {
    className: "mcc-foot-btn",
    type: "button",
    onClick: () => go("feedback")
  }, /*#__PURE__*/React.createElement(IcMessage, {
    size: 15
  }), "Feedback"), /*#__PURE__*/React.createElement("button", {
    className: "mcc-foot-btn" + (active === "settings" ? " is-active" : ""),
    type: "button",
    onClick: () => go("settings")
  }, /*#__PURE__*/React.createElement(IcSettings, {
    size: 15
  }), "Settings"), /*#__PURE__*/React.createElement("button", {
    className: "mcc-foot-btn mcc-foot-profile" + (active === "user" ? " is-active" : ""),
    type: "button",
    onClick: () => go("user")
  }, /*#__PURE__*/React.createElement(McAvatar, {
    name: "Ana Diaz",
    color: "var(--bv-gray-600)",
    size: 20
  }), /*#__PURE__*/React.createElement("span", null, "Ana Diaz"))));
}
function MccNavTreeLed() {
  const [attention, setAttention] = React.useState(2);
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-side-pad"
  }, /*#__PURE__*/React.createElement(BvNavTree, {
    active: "needs",
    attention: attention
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-demo-row"
  }, /*#__PURE__*/React.createElement("span", null, "demo \xB7 the gate:"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: attention > 0 ? "is-on" : "",
    onClick: () => setAttention(2)
  }, "2 pending"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: attention === 0 ? "is-on" : "",
    onClick: () => setAttention(0)
  }, "all clear")), /*#__PURE__*/React.createElement("p", {
    className: "mcc-caption"
  }, "Work-as-noun taken literally: the sidebar ", /*#__PURE__*/React.createElement("b", null, "is"), " the workspace tree, and the projections \xB7 History and Knowledge \xB7 pin above it as lenses, not siblings. The primary lens is ", /*#__PURE__*/React.createElement("b", null, "adaptive"), ": while work waits at your gate it reads ", /*#__PURE__*/React.createElement("b", null, "Needs you"), " with the count; the moment the queue clears it falls back to ", /*#__PURE__*/React.createElement("b", null, "Maestro"), " \xB7 one slot that always answers \u201Cwhere do I go first.\u201D Settings and Feedback settle into the footer. ", /*#__PURE__*/React.createElement("i", null, "Toggle the gate above to watch the primary morph.")));
}
Object.assign(window, {
  IcSearch,
  IcHistory,
  IcGraph,
  IcInbox,
  IcUsers,
  BvNav,
  NavTreeRows,
  AppTreeRows,
  NavBench,
  NavAutonomy,
  bvNavGrid,
  MccNavInventory,
  MccNavCanonical,
  MccNavFlat,
  MccNavRail,
  MccNavTreeLed
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/ConceptNavIA.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/ConceptSettings.jsx
try { (() => {
// The Settings page · "the engine room": runners, credentials, autonomy,
// routines, notifications, appearance, members. A full-page frame on the
// canonical BvNavTree (same chrome as History / Knowledge). Two layouts,
// toggled in the top bar: a two-pane section nav, and a single editorial
// scroll with a sticky table of contents.

// ── Local icons (built on the global McIcon) ──────────────────────────────
const IcCpu = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("rect", {
  x: "4",
  y: "4",
  width: "16",
  height: "16",
  rx: "2"
}), /*#__PURE__*/React.createElement("rect", {
  x: "9",
  y: "9",
  width: "6",
  height: "6"
}), /*#__PURE__*/React.createElement("path", {
  d: "M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2"
}));
const IcKey = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
  cx: "7.5",
  cy: "15.5",
  r: "4.5"
}), /*#__PURE__*/React.createElement("path", {
  d: "m10.7 12.3 8.3-8.3M16 6l3 3M14 8l2 2"
}));
const IcSliders = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"
}));
const IcClock = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
  cx: "12",
  cy: "12",
  r: "9"
}), /*#__PURE__*/React.createElement("path", {
  d: "M12 7v5l3 2"
}));
const IcBell = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9"
}), /*#__PURE__*/React.createElement("path", {
  d: "M10.3 21a1.94 1.94 0 0 0 3.4 0"
}));
const IcPalette = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
  cx: "13.5",
  cy: "6.5",
  r: "1.5"
}), /*#__PURE__*/React.createElement("circle", {
  cx: "17.5",
  cy: "10.5",
  r: "1.5"
}), /*#__PURE__*/React.createElement("circle", {
  cx: "8.5",
  cy: "7.5",
  r: "1.5"
}), /*#__PURE__*/React.createElement("circle", {
  cx: "6.5",
  cy: "12.5",
  r: "1.5"
}), /*#__PURE__*/React.createElement("path", {
  d: "M12 2a10 10 0 0 0 0 20 2.5 2.5 0 0 0 2-4 2.5 2.5 0 0 1 2-4h2a4 4 0 0 0 4-4 10 10 0 0 0-10-8Z"
}));
const IcShield = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"
}));
const IcLink = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M10 13a5 5 0 0 0 7 0l3-3a5 5 0 0 0-7-7l-1 1"
}), /*#__PURE__*/React.createElement("path", {
  d: "M14 11a5 5 0 0 0-7 0l-3 3a5 5 0 0 0 7 7l1-1"
}));
const IcPlus = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M12 5v14M5 12h14"
}));
function SetSwitch({
  on,
  onClick
}) {
  // Thin projection over the standard Switch.
  return /*#__PURE__*/React.createElement(DsSwitch, {
    checked: on,
    onChange: onClick
  });
}
function SetStepper({
  value,
  set,
  min = 0,
  max = 99,
  suffix
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "set-stepper"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    disabled: value <= min,
    onClick: () => set(Math.max(min, value - 1))
  }, "\u2212"), /*#__PURE__*/React.createElement("span", {
    className: "set-stepper-val"
  }, value, suffix ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 400,
      color: "var(--muted-foreground)"
    }
  }, " ", suffix) : null), /*#__PURE__*/React.createElement("button", {
    type: "button",
    disabled: value >= max,
    onClick: () => set(Math.min(max, value + 1))
  }, "+"));
}
function SetSeg({
  value,
  set,
  options
}) {
  // Thin projection over the standard Segmented (kit options are [value, label] pairs).
  return /*#__PURE__*/React.createElement(DsSegmented, {
    value: value,
    onChange: set,
    options: options.map(([v, label]) => ({
      value: v,
      label
    }))
  });
}
function SetSlider({
  value,
  set,
  min,
  max,
  step = 1,
  fmt
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "set-slider"
  }, /*#__PURE__*/React.createElement("input", {
    className: "set-range",
    type: "range",
    min: min,
    max: max,
    step: step,
    value: value,
    onChange: e => set(Number(e.target.value))
  }), /*#__PURE__*/React.createElement("span", {
    className: "set-slider-val"
  }, fmt(value)));
}
const SET_SECTIONS = [{
  id: "runners",
  label: "Runners & worktrees",
  short: "Runners",
  icon: /*#__PURE__*/React.createElement(IcCpu, null)
}, {
  id: "creds",
  label: "Credentials & scopes",
  short: "Credentials",
  icon: /*#__PURE__*/React.createElement(IcKey, null),
  badge: 1
}, {
  id: "autonomy",
  label: "Autonomy defaults",
  short: "Autonomy",
  icon: /*#__PURE__*/React.createElement(IcSliders, null)
}, {
  id: "routines",
  label: "Routines & wake",
  short: "Routines",
  icon: /*#__PURE__*/React.createElement(IcClock, null)
}, {
  id: "notify",
  label: "Notifications",
  short: "Notifications",
  icon: /*#__PURE__*/React.createElement(IcBell, null)
}, {
  id: "appearance",
  label: "Appearance",
  short: "Appearance",
  icon: /*#__PURE__*/React.createElement(IcPalette, null)
}, {
  id: "members",
  label: "Workspace & members",
  short: "Members",
  icon: /*#__PURE__*/React.createElement(IcUsers, null)
}];
const CREDS = [{
  name: "GitHub",
  glyph: "GH",
  desc: "hawthorne · 4 repos",
  scopes: ["repo", "workflow", "read:org"],
  status: "ok"
}, {
  name: "Linear",
  glyph: "LN",
  desc: "Import cycles · blocking 1 run",
  scopes: ["read", "write?"],
  miss: "write",
  status: "warn"
}, {
  name: "Anthropic API",
  glyph: "AI",
  desc: "runner claude · sonnet + opus",
  scopes: ["messages", "batches"],
  status: "ok"
}, {
  name: "Obsidian vault",
  glyph: "OB",
  desc: "the conversation bridge writes here",
  scopes: ["local fs"],
  status: "ok"
}, {
  name: "Slack",
  glyph: "SL",
  desc: "not connected",
  scopes: [],
  status: "off"
}];
const ROUTINES = [{
  name: "Nightly digest",
  when: "daily · 02:00",
  on: true
}, {
  name: "Morning briefing",
  when: "weekdays · 07:30",
  on: true
}, {
  name: "Linear import",
  when: "every 6h",
  on: false
}];
const WAKES = [{
  name: "On push to main",
  desc: "review + queue follow-up work",
  on: true
}, {
  name: "On new issue",
  desc: "triage into the right folder",
  on: true
}, {
  name: "On credential restored",
  desc: "retry the runs it blocked",
  on: true
}];
const MEMBERS = [{
  name: "Ana Diaz",
  role: "Owner",
  email: "ana@broomva.ai",
  color: "var(--bv-gray-600)"
}, {
  name: "Theo Park",
  role: "Operator",
  email: "theo@broomva.ai",
  color: "var(--bv-blue)"
}, {
  name: "Maya Lin",
  role: "Viewer",
  email: "maya@broomva.ai",
  color: "var(--bv-purple, #7c6cf0)"
}];
function MccSettings({
  onOpenView,
  theme,
  onSetTheme,
  density,
  onSetDensity,
  blue,
  onSetBlue
}) {
  const [layout, setLayout] = React.useState("twopane"); // twopane | scroll
  const [active, setActive] = React.useState("runners");

  // engine-room state
  const [runner, setRunner] = React.useState("claude");
  const [worktrees, setWorktrees] = React.useState(2);
  const [sandbox, setSandbox] = React.useState("both");
  const [concurrency, setConcurrency] = React.useState(3);
  const [autoClean, setAutoClean] = React.useState(true);
  const [budget, setBudget] = React.useState(20);
  const [gate, setGate] = React.useState("risk");
  const [cascade, setCascade] = React.useState(2);
  const [spend, setSpend] = React.useState(40);
  const [routines, setRoutines] = React.useState(ROUTINES.map(r => r.on));
  const [wakes, setWakes] = React.useState(WAKES.map(w => w.on));
  const [notif, setNotif] = React.useState({
    app: true,
    email: true,
    slack: false
  });
  const [pingWhen, setPingWhen] = React.useState("blocks");
  const Section = ({
    id
  }) => {
    switch (id) {
      case "runners":
        return /*#__PURE__*/React.createElement("div", {
          className: "set-section",
          id: "set-runners"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-head"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-title"
        }, /*#__PURE__*/React.createElement(IcCpu, {
          size: 17
        }), "Runners & worktrees"), /*#__PURE__*/React.createElement("div", {
          className: "set-section-sub"
        }, "The armed seam the scheduler dispatches through, and how many checkouts can run at once.")), /*#__PURE__*/React.createElement("div", {
          className: "set-panel"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Default runner"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "The model the loop arms by default. Per-folder overrides win.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSeg, {
          value: runner,
          set: setRunner,
          options: [["claude", "claude"], ["codex", "codex"], ["local", "local"]]
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Worktrees per runner"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "Parallel git checkouts a single runner can hold.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetStepper, {
          value: worktrees,
          set: setWorktrees,
          min: 1,
          max: 6
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Where work runs"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "Local machine, an ephemeral cloud sandbox, or whichever is free.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSeg, {
          value: sandbox,
          set: setSandbox,
          options: [["local", "Local"], ["cloud", "Cloud"], ["both", "Both"]]
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Concurrency cap"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "Most sessions live at once across the whole workspace.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetStepper, {
          value: concurrency,
          set: setConcurrency,
          min: 1,
          max: 12,
          suffix: "live"
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Auto-clean merged worktrees"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "Drop a checkout once its branch lands.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSwitch, {
          on: autoClean,
          onClick: () => setAutoClean(!autoClean)
        })))));
      case "creds":
        return /*#__PURE__*/React.createElement("div", {
          className: "set-section",
          id: "set-creds"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-head"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-title"
        }, /*#__PURE__*/React.createElement(IcKey, {
          size: 17
        }), "Credentials & scopes"), /*#__PURE__*/React.createElement("div", {
          className: "set-section-sub"
        }, "The thing that blocks runs. A missing scope halts the loop until a human grants it.")), /*#__PURE__*/React.createElement("div", {
          className: "set-panel"
        }, CREDS.map(c => /*#__PURE__*/React.createElement("div", {
          className: "set-field",
          key: c.name
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-rowglyph",
          style: {
            fontSize: 11,
            fontWeight: 600,
            fontFamily: "var(--bv-font-mono, monospace)"
          }
        }, c.glyph), /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, c.name), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, c.desc), c.scopes.length > 0 && /*#__PURE__*/React.createElement("div", {
          className: "set-scopes",
          style: {
            marginTop: 4
          }
        }, c.scopes.map(s => /*#__PURE__*/React.createElement("span", {
          key: s,
          className: "set-scope" + (s.endsWith("?") ? " set-scope--miss" : "")
        }, s.replace("?", ""), s.endsWith("?") ? " · missing" : "")))), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control",
          style: {
            flexDirection: "column",
            alignItems: "flex-end",
            gap: 8
          }
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-status set-status--" + c.status
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-status-dot"
        }), c.status === "ok" ? "connected" : c.status === "warn" ? "needs scope" : "off"), /*#__PURE__*/React.createElement(DsButton, {
          size: "sm",
          variant: "secondary"
        }, c.status === "off" ? "Connect" : c.status === "warn" ? "Grant write" : "Manage"))))), /*#__PURE__*/React.createElement(DsButton, {
          size: "sm",
          variant: "soft",
          style: {
            alignSelf: "flex-start"
          }
        }, /*#__PURE__*/React.createElement(IcPlus, {
          size: 16
        }), "Add credential"));
      case "autonomy":
        return /*#__PURE__*/React.createElement("div", {
          className: "set-section",
          id: "set-autonomy"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-head"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-title"
        }, /*#__PURE__*/React.createElement(IcSliders, {
          size: 17
        }), "Autonomy defaults"), /*#__PURE__*/React.createElement("div", {
          className: "set-section-sub"
        }, "How far the loop runs before it has to come back to your gate.")), /*#__PURE__*/React.createElement("div", {
          className: "set-panel"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Weekly budget"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "Unsupervised hours the loop may spend before pausing for review.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSlider, {
          value: budget,
          set: setBudget,
          min: 0,
          max: 60,
          fmt: v => v + " h / wk"
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Gate policy"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "When a session needs you. ", /*#__PURE__*/React.createElement("code", null, "Ask on risk"), " stops only at irreversible steps.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSeg, {
          value: gate,
          set: setGate,
          options: [["ask", "Ask first"], ["risk", "Ask on risk"], ["free", "Run free"]]
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Cascade depth"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "How many levels deep maestro may spawn sub-agents.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetStepper, {
          value: cascade,
          set: setCascade,
          min: 0,
          max: 5,
          suffix: "levels"
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Spend cap"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "Hard ceiling on model + sandbox cost per week.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSlider, {
          value: spend,
          set: setSpend,
          min: 0,
          max: 200,
          step: 5,
          fmt: v => "$" + v + " / wk"
        })))));
      case "routines":
        return /*#__PURE__*/React.createElement("div", {
          className: "set-section",
          id: "set-routines"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-head"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-title"
        }, /*#__PURE__*/React.createElement(IcClock, {
          size: 17
        }), "Routines & wake triggers"), /*#__PURE__*/React.createElement("div", {
          className: "set-section-sub"
        }, "Standing loops on a schedule, and the events that wake the orchestrator.")), /*#__PURE__*/React.createElement("div", {
          className: "set-panel"
        }, ROUTINES.map((r, i) => /*#__PURE__*/React.createElement("div", {
          className: "set-field",
          key: r.name
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-rowglyph"
        }, /*#__PURE__*/React.createElement(IcClock, {
          size: 16
        })), /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, r.name), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, r.when)), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement("span", {
          className: "mc-receipt"
        }, "routine"), /*#__PURE__*/React.createElement(SetSwitch, {
          on: routines[i],
          onClick: () => setRoutines(routines.map((v, j) => j === i ? !v : v))
        }))))), /*#__PURE__*/React.createElement("div", {
          className: "set-panel"
        }, WAKES.map((w, i) => /*#__PURE__*/React.createElement("div", {
          className: "set-field",
          key: w.name
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, w.name), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, w.desc)), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSwitch, {
          on: wakes[i],
          onClick: () => setWakes(wakes.map((v, j) => j === i ? !v : v))
        }))))));
      case "notify":
        return /*#__PURE__*/React.createElement("div", {
          className: "set-section",
          id: "set-notify"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-head"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-title"
        }, /*#__PURE__*/React.createElement(IcBell, {
          size: 17
        }), "Notifications"), /*#__PURE__*/React.createElement("div", {
          className: "set-section-sub"
        }, "When and where the loop pings you \xB7 kept quiet by default.")), /*#__PURE__*/React.createElement("div", {
          className: "set-panel"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "In-app"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "The ", /*#__PURE__*/React.createElement("b", null, "Needs you"), " lens badge.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSwitch, {
          on: notif.app,
          onClick: () => setNotif({
            ...notif,
            app: !notif.app
          })
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Email"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "ana@broomva.ai")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSwitch, {
          on: notif.email,
          onClick: () => setNotif({
            ...notif,
            email: !notif.email
          })
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Slack"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "Connect Slack in Credentials first.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSwitch, {
          on: notif.slack,
          onClick: () => setNotif({
            ...notif,
            slack: !notif.slack
          })
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Ping me when"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "Every halt is chatty; ", /*#__PURE__*/React.createElement("code", null, "Only blocks"), " waits for a real wall.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSeg, {
          value: pingWhen,
          set: setPingWhen,
          options: [["halt", "Every halt"], ["blocks", "Only blocks"], ["digest", "Daily digest"]]
        })))));
      case "appearance":
        return /*#__PURE__*/React.createElement("div", {
          className: "set-section",
          id: "set-appearance"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-head"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-title"
        }, /*#__PURE__*/React.createElement(IcPalette, {
          size: 17
        }), "Appearance"), /*#__PURE__*/React.createElement("div", {
          className: "set-section-sub"
        }, "These write through to the live app right now.")), /*#__PURE__*/React.createElement("div", {
          className: "set-panel"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Theme"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "Calm monochrome, light or dark.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSeg, {
          value: theme,
          set: onSetTheme,
          options: [["light", "Light"], ["dark", "Dark"]]
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Density"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "Calm gives cards room; dense packs the feed.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSeg, {
          value: density,
          set: onSetDensity,
          options: [["calm", "Calm"], ["dense", "Dense"]]
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-field"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Blue intensity"), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, "How much the ai-blue glow tints frost, shadow and the Undertow.")), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSlider, {
          value: blue,
          set: onSetBlue,
          min: 0,
          max: 2,
          step: 0.1,
          fmt: v => v.toFixed(1) + "×"
        })))));
      case "members":
        return /*#__PURE__*/React.createElement("div", {
          className: "set-section",
          id: "set-members"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-head"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-section-title"
        }, /*#__PURE__*/React.createElement(IcUsers, {
          size: 17
        }), "Workspace & members"), /*#__PURE__*/React.createElement("div", {
          className: "set-section-sub"
        }, "Who shares this orchestration plane, and what they can do.")), /*#__PURE__*/React.createElement("div", {
          className: "set-panel"
        }, /*#__PURE__*/React.createElement("div", {
          className: "set-field set-field--stacked"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, "Workspace name"), /*#__PURE__*/React.createElement("input", {
          className: "set-input set-input--full",
          defaultValue: "Broomva"
        }))), /*#__PURE__*/React.createElement("div", {
          className: "set-panel"
        }, MEMBERS.map(m => /*#__PURE__*/React.createElement("div", {
          className: "set-field",
          key: m.email
        }, /*#__PURE__*/React.createElement(McAvatar, {
          name: m.name,
          color: m.color,
          size: 32
        }), /*#__PURE__*/React.createElement("div", {
          className: "set-field-main"
        }, /*#__PURE__*/React.createElement("span", {
          className: "set-field-label"
        }, m.name), /*#__PURE__*/React.createElement("span", {
          className: "set-field-desc"
        }, m.email)), /*#__PURE__*/React.createElement("div", {
          className: "set-field-control"
        }, /*#__PURE__*/React.createElement(SetSeg, {
          value: m.role,
          set: () => {},
          options: [["Owner", "Owner"], ["Operator", "Operator"], ["Viewer", "Viewer"]]
        }))))), /*#__PURE__*/React.createElement(DsButton, {
          size: "sm",
          variant: "soft",
          style: {
            alignSelf: "flex-start"
          }
        }, /*#__PURE__*/React.createElement(IcPlus, {
          size: 16
        }), "Invite member"));
      default:
        return null;
    }
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-fill"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-app",
    style: {
      gridTemplateColumns: bvNavGrid()
    }
  }, /*#__PURE__*/React.createElement(BvNavTree, {
    active: "settings",
    inApp: true,
    onNav: onOpenView
  }), /*#__PURE__*/React.createElement("div", {
    className: "bv-main"
  }, /*#__PURE__*/React.createElement("header", {
    className: "bv-top-bar",
    "data-screen-label": "Settings \xB7 top bar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-topbar-left"
  }, /*#__PURE__*/React.createElement(IcSettings, {
    size: 17
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--foreground)",
      fontWeight: 600
    }
  }, "Settings"), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--muted-foreground)"
    }
  }, "\xB7 the engine room")), /*#__PURE__*/React.createElement("div", {
    className: "set-topright"
  }, /*#__PURE__*/React.createElement("span", {
    className: "set-saved"
  }, /*#__PURE__*/React.createElement(IcCheck, {
    size: 14
  }), "Saved"), /*#__PURE__*/React.createElement(DsSegmented, {
    value: layout,
    onChange: setLayout,
    options: [{
      value: "twopane",
      label: "Two-pane"
    }, {
      value: "scroll",
      label: "One scroll"
    }]
  }))), layout === "twopane" ? /*#__PURE__*/React.createElement("div", {
    className: "set-twopane",
    "data-screen-label": "Settings \xB7 two-pane"
  }, /*#__PURE__*/React.createElement("nav", {
    className: "set-secnav"
  }, /*#__PURE__*/React.createElement("div", {
    className: "set-secnav-label"
  }, "Engine room"), SET_SECTIONS.map(s => /*#__PURE__*/React.createElement("button", {
    key: s.id,
    type: "button",
    className: "set-secnav-btn" + (active === s.id ? " is-active" : ""),
    onClick: () => setActive(s.id)
  }, React.cloneElement(s.icon, {
    size: 16
  }), /*#__PURE__*/React.createElement("span", null, s.label), s.badge ? /*#__PURE__*/React.createElement("span", {
    className: "set-secnav-badge"
  }, s.badge) : null))), /*#__PURE__*/React.createElement("div", {
    className: "set-content"
  }, /*#__PURE__*/React.createElement("div", {
    className: "set-content-inner"
  }, /*#__PURE__*/React.createElement(Section, {
    id: active
  })))) : /*#__PURE__*/React.createElement("div", {
    className: "set-scrollwrap",
    "data-screen-label": "Settings \xB7 one scroll"
  }, /*#__PURE__*/React.createElement("div", {
    className: "set-scrollgrid"
  }, /*#__PURE__*/React.createElement("div", {
    className: "set-scrollmain"
  }, SET_SECTIONS.map((s, i) => /*#__PURE__*/React.createElement("div", {
    key: s.id,
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 12
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "set-bignum"
  }, String(i + 1).padStart(2, "0")), /*#__PURE__*/React.createElement(Section, {
    id: s.id
  })))), /*#__PURE__*/React.createElement("aside", {
    className: "set-toc"
  }, /*#__PURE__*/React.createElement("div", {
    className: "set-toc-label"
  }, "On this page"), SET_SECTIONS.map((s, i) => /*#__PURE__*/React.createElement("a", {
    key: s.id,
    href: "#set-" + s.id,
    className: "set-toc-btn" + (i === 0 ? " is-active" : "")
  }, /*#__PURE__*/React.createElement("span", {
    className: "set-toc-num"
  }, String(i + 1).padStart(2, "0")), /*#__PURE__*/React.createElement("span", null, s.short)))))))));
}
Object.assign(window, {
  MccSettings
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/ConceptSettings.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/ConceptTreeClick.jsx
try { (() => {
// Concepts canvas · clicking the workspace tree.
// The sidebar is the workspace; every rung is a folder with a contract.
// Selection scopes the plane AND retunes the panel's inspector:
//   root      → everything + the meta-contract (places, defaults, the score)
//   initiative→ the place's work + folder inspector (contract, subfolders)
//   project   → the contract's floor + spec & sessions (W2)
// Deeper rungs (work item → live panel, session → drill-in) already shipped.

const IcTcChev = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "m9 18 6-6-6-6"
}));
const mccTcById = id => WK_ITEMS.find(i => i.id === id);

// ── T0 · The ladder · schema ──────────────────────────────────────────────
function MccTreeSchema() {
  const rungs = [{
    depth: 0,
    glyph: /*#__PURE__*/React.createElement(IcFolderOpen, {
      size: 14
    }),
    name: "Broomva",
    kind: "the workspace root",
    plane: "everything · all places, grouped by attention",
    panel: "the meta-contract: cascade defaults, the places, the score"
  }, {
    depth: 1,
    glyph: /*#__PURE__*/React.createElement(IcFolderOpen, {
      size: 14
    }),
    name: "hawthorne/",
    kind: "initiative folder",
    plane: "the place · its work, grouped by state",
    panel: "folder inspector: contract chips, subfolders, sessions rollup"
  }, {
    depth: 2,
    glyph: /*#__PURE__*/React.createElement(IcFolder, {
      size: 13
    }),
    name: "hawthorne-core/",
    kind: "project folder",
    plane: "the contract's floor · only this folder's items",
    panel: "spec + sessions · the W2 inspector"
  }, {
    depth: 3,
    glyph: /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: "var(--bv-blue-accent)"
      }
    }),
    name: "work item",
    kind: "card in the plane",
    plane: "stays put · the card highlights",
    panel: "the live panel: chat / activity / the look (shipped)"
  }, {
    depth: 4,
    glyph: /*#__PURE__*/React.createElement("span", {
      className: "mcc-dot-tide",
      style: {
        width: 13,
        height: 13
      }
    }),
    name: "session",
    kind: "row in an inspector",
    plane: "stays put",
    panel: "drill-in: the chat projection, back-link to its folder (shipped)"
  }];
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-pad"
  }, /*#__PURE__*/React.createElement("div", null, rungs.map((r, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "mcc-rung"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-rung-name",
    style: {
      paddingLeft: r.depth * 16
    }
  }, r.glyph, /*#__PURE__*/React.createElement("span", {
    className: "mcc-rung-stack"
  }, /*#__PURE__*/React.createElement("span", null, r.name), /*#__PURE__*/React.createElement("span", {
    className: "mcc-rung-kind"
  }, r.kind))), /*#__PURE__*/React.createElement("span", {
    className: "mcc-prim-arrow"
  }, "\u2192"), /*#__PURE__*/React.createElement("div", {
    className: "mcc-rung-out"
  }, /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("b", null, "plane"), " ", r.plane), /*#__PURE__*/React.createElement("span", null, /*#__PURE__*/React.createElement("b", null, "panel"), " ", r.panel))))), /*#__PURE__*/React.createElement("p", {
    className: "mcc-caption"
  }, "One law for the whole ladder: a click never navigates away \xB7 it scopes the plane and retunes the panel. The deeper the rung, the more specific the contract; the receipts stay one click away at every depth."));
}

// ── Shared interactive frame ──────────────────────────────────────────────
// The maestro-loop sidebar · now in the IA4 tree-led structure (shared design
// with the Knowledge / History pages): adaptive lens primary + History/Knowledge
// lenses, the loop's Workspace tree (scope nav kept), bench, autonomy, footer.
function MccTcSidebar({
  scope,
  setScope,
  onMission,
  missionActive,
  resize,
  collapsed,
  onOpenView
}) {
  const sbText = {
    flex: 1,
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    textAlign: "left"
  };

  // Minimized · an icon rail (IA3): lenses + workspace folders + footer, icons only.
  if (collapsed) {
    const hawActive = scope === "hawthorne" || scope === "core";
    return /*#__PURE__*/React.createElement("aside", {
      className: "mcc-rail mcc-rail--side",
      "data-screen-label": "Sidebar (rail)"
    }, /*#__PURE__*/React.createElement("img", {
      className: "bv-ws-logo",
      src: "../../assets/broomva-blackhole-logo.png",
      alt: "",
      style: {
        width: 24,
        height: 24,
        marginBottom: 6
      }
    }), /*#__PURE__*/React.createElement("button", {
      className: "mcc-rail-btn" + (missionActive ? " is-on" : ""),
      type: "button",
      onClick: onMission,
      title: "Needs you"
    }, /*#__PURE__*/React.createElement(IcInbox, {
      size: 14
    }), /*#__PURE__*/React.createElement("span", {
      className: "mcc-rail-badge"
    }, "2")), /*#__PURE__*/React.createElement("button", {
      className: "mcc-rail-btn",
      type: "button",
      onClick: () => onOpenView && onOpenView("history"),
      title: "History"
    }, /*#__PURE__*/React.createElement(IcHistory, {
      size: 14
    })), /*#__PURE__*/React.createElement("button", {
      className: "mcc-rail-btn",
      type: "button",
      onClick: () => onOpenView && onOpenView("knowledge"),
      title: "Knowledge"
    }, /*#__PURE__*/React.createElement(IcGraph, {
      size: 14
    })), /*#__PURE__*/React.createElement("div", {
      className: "mcc-rail-div"
    }), /*#__PURE__*/React.createElement("button", {
      className: "mcc-rail-btn" + (scope === "root" ? " is-on" : ""),
      type: "button",
      onClick: () => setScope("root"),
      title: "Broomva \xB7 workspace root"
    }, /*#__PURE__*/React.createElement(IcFolderOpen, {
      size: 14
    })), /*#__PURE__*/React.createElement("button", {
      className: "mcc-rail-btn" + (hawActive ? " is-on" : ""),
      type: "button",
      onClick: () => setScope("hawthorne"),
      title: "hawthorne"
    }, /*#__PURE__*/React.createElement(IcFolder, {
      size: 14
    })), /*#__PURE__*/React.createElement("button", {
      className: "mcc-rail-btn",
      type: "button",
      onClick: () => setScope("root"),
      title: "genesis"
    }, /*#__PURE__*/React.createElement(IcFolder, {
      size: 14
    })), /*#__PURE__*/React.createElement("button", {
      className: "mcc-rail-btn",
      type: "button",
      onClick: () => setScope("root"),
      title: "ops"
    }, /*#__PURE__*/React.createElement(IcFolder, {
      size: 14
    })), /*#__PURE__*/React.createElement("div", {
      className: "bv-sb-spacer"
    }), /*#__PURE__*/React.createElement("button", {
      className: "mcc-rail-btn",
      type: "button",
      title: "Feedback",
      onClick: () => onOpenView && onOpenView("feedback")
    }, /*#__PURE__*/React.createElement(IcMessage, {
      size: 15
    })), /*#__PURE__*/React.createElement("button", {
      className: "mcc-rail-btn",
      type: "button",
      title: "Settings",
      onClick: () => onOpenView && onOpenView("settings")
    }, /*#__PURE__*/React.createElement(IcSettings, {
      size: 15
    })), /*#__PURE__*/React.createElement("button", {
      className: "mcc-rail-btn mcc-rail-avatar",
      type: "button",
      title: "Ana Diaz",
      onClick: () => onOpenView && onOpenView("user")
    }, /*#__PURE__*/React.createElement(McAvatar, {
      name: "Ana Diaz",
      color: "var(--bv-gray-600)",
      size: 20
    })));
  }
  return /*#__PURE__*/React.createElement("aside", {
    className: "bv-sidebar mcc-nav",
    "data-screen-label": "Sidebar",
    style: collapsed ? {
      padding: 0,
      borderRight: "none"
    } : undefined
  }, resize && !collapsed && /*#__PURE__*/React.createElement("div", {
    className: "mcc-coldrag mcc-coldrag--right",
    onMouseDown: resize,
    title: "Drag to resize"
  }), /*#__PURE__*/React.createElement("button", {
    className: "bv-ws-switch",
    type: "button"
  }, /*#__PURE__*/React.createElement("img", {
    className: "bv-ws-logo",
    src: "../../assets/broomva-blackhole-logo.png",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", {
    className: "bv-ws-name"
  }, "Broomva"), /*#__PURE__*/React.createElement(IcChevrons, {
    size: 14
  })), /*#__PURE__*/React.createElement("div", {
    className: "mcc-lensbar"
  }, /*#__PURE__*/React.createElement("button", {
    className: "mcc-lens" + (missionActive ? " is-active" : ""),
    type: "button",
    onClick: onMission
  }, /*#__PURE__*/React.createElement(IcInbox, {
    size: 14
  }), "Needs you", /*#__PURE__*/React.createElement("span", {
    className: "mcc-lens-badge"
  }, "2")), /*#__PURE__*/React.createElement("button", {
    className: "mcc-lens",
    type: "button",
    onClick: () => onOpenView && onOpenView("history")
  }, /*#__PURE__*/React.createElement(IcHistory, {
    size: 14
  }), "History"), /*#__PURE__*/React.createElement("button", {
    className: "mcc-lens",
    type: "button",
    onClick: () => onOpenView && onOpenView("knowledge")
  }, /*#__PURE__*/React.createElement(IcGraph, {
    size: 14
  }), "Knowledge")), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-section-label"
  }, "Workspace"), /*#__PURE__*/React.createElement("div", {
    className: "mcc-sb-col"
  }, /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item" + (scope === "root" ? " is-active" : ""),
    type: "button",
    onClick: () => setScope("root"),
    title: "The workspace root \xB7 ~/Broomva"
  }, /*#__PURE__*/React.createElement(IcFolderOpen, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "Broomva"), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, "3 places")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item" + (scope === "hawthorne" ? " is-active" : ""),
    type: "button",
    style: {
      paddingLeft: 24
    },
    onClick: () => setScope("hawthorne")
  }, /*#__PURE__*/React.createElement(IcFolderOpen, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "hawthorne"), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, "1/6")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item" + (scope === "core" ? " is-active" : ""),
    type: "button",
    style: {
      paddingLeft: 42
    },
    onClick: () => setScope("core")
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "hawthorne-core"), /*#__PURE__*/React.createElement("span", {
    className: "bv-sb-badge"
  }, "1")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 42
    }
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "hawthorne-db"), /*#__PURE__*/React.createElement("span", {
    className: "bv-sb-badge"
  }, "1")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 24
    }
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "genesis"), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, "0/1")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 42
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 13,
      height: 13
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "@genesis/projection")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 24
    }
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "ops"), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, "0/1")), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 42
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 13,
      height: 13
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, "bookkeeping"))), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-spacer"
  }), /*#__PURE__*/React.createElement(NavAutonomy, {
    onOpenView: onOpenView
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-nav-foot"
  }, /*#__PURE__*/React.createElement("button", {
    className: "mcc-foot-btn",
    type: "button",
    onClick: () => onOpenView && onOpenView("feedback")
  }, /*#__PURE__*/React.createElement(IcMessage, {
    size: 15
  }), "Feedback"), /*#__PURE__*/React.createElement("button", {
    className: "mcc-foot-btn",
    type: "button",
    onClick: () => onOpenView && onOpenView("settings")
  }, /*#__PURE__*/React.createElement(IcSettings, {
    size: 15
  }), "Settings"), /*#__PURE__*/React.createElement("button", {
    className: "mcc-foot-btn mcc-foot-profile",
    type: "button",
    onClick: () => onOpenView && onOpenView("user")
  }, /*#__PURE__*/React.createElement(McAvatar, {
    name: "Ana Diaz",
    color: "var(--bv-gray-600)",
    size: 20
  }), /*#__PURE__*/React.createElement("span", null, "Ana Diaz"))));
}
function MccTcGroup({
  state,
  items
}) {
  const meta = WK_STATES[state];
  return /*#__PURE__*/React.createElement("section", {
    className: "mc-group"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-group-header"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-group-label"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      background: WK_TONE_COLOR[meta.tone]
    }
  }), meta.plain), /*#__PURE__*/React.createElement("span", {
    className: "mc-group-count"
  }, items.length), /*#__PURE__*/React.createElement("span", {
    className: "mc-group-hint"
  }, WK_GROUP_HINTS[state])), /*#__PURE__*/React.createElement("div", {
    className: "mc-group-cards"
  }, items.map(item => /*#__PURE__*/React.createElement(MccLiveWorkCard, {
    key: item.id,
    item: item,
    selected: false,
    onSelect: () => {}
  }))));
}
const MCC_TC_PLANE = {
  root: {
    crumb: "~",
    title: "Broomva/",
    chips: ["kind: workspace", "3 places", "defaults cascade ↓"],
    groups: [["review", ["w1"]], ["blocked", ["w2"]], ["running", ["w3", "w4"]]]
  },
  hawthorne: {
    crumb: "~ / Broomva",
    title: "hawthorne/",
    chips: ["kind: initiative", "owner: you", "budget: 24h/wk unsupervised", "gate: human-approve"],
    groups: [["review", ["w1"]], ["blocked", ["w2"]], ["queued", ["w5", "w6"]]]
  },
  core: {
    crumb: "~ / Broomva / hawthorne",
    title: "hawthorne-core/",
    chips: ["kind: project", "inherits: budget 8h · gate human-approve", "worktree-per-run"],
    groups: [["review", ["w1"]], ["queued", ["w5"]], ["proposed", ["w7"]]]
  }
};
function MccTcPlane({
  scope
}) {
  const p = MCC_TC_PLANE[scope];
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-plane",
    "data-screen-label": "Plane scoped to " + scope
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-scope-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-detail-breadcrumb"
  }, p.crumb), /*#__PURE__*/React.createElement("div", {
    className: "mcc-folder-title-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-chat-pop-title"
  }, p.title), /*#__PURE__*/React.createElement("div", {
    className: "mcc-fm-chips"
  }, p.chips.map(c => /*#__PURE__*/React.createElement("span", {
    key: c,
    className: "mc-receipt"
  }, c))))), /*#__PURE__*/React.createElement("div", {
    className: "mcc-plane-body",
    "data-view": "feed"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-plane-feed"
  }, p.groups.map(([state, ids]) => /*#__PURE__*/React.createElement(MccTcGroup, {
    key: state,
    state: state,
    items: ids.map(mccTcById)
  })))));
}
function MccTcRow({
  glyph,
  label,
  meta,
  onClick
}) {
  return /*#__PURE__*/React.createElement("button", {
    className: "mcc-sess",
    type: "button",
    onClick: onClick,
    style: onClick ? undefined : {
      cursor: "default"
    }
  }, glyph, /*#__PURE__*/React.createElement("span", {
    className: "mcc-sess-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-sess-label"
  }, label), /*#__PURE__*/React.createElement("span", {
    className: "mcc-sess-meta"
  }, meta)), onClick && /*#__PURE__*/React.createElement(IcTcChev, {
    size: 13
  }));
}
function MccTcPanel({
  scope,
  setScope
}) {
  if (scope === "root") {
    return /*#__PURE__*/React.createElement("aside", {
      className: "mcc-live-panel",
      "data-screen-label": "Workspace inspector"
    }, /*#__PURE__*/React.createElement("div", {
      className: "mcc-panel-head"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-detail-breadcrumb"
    }, "~ / Broomva"), /*#__PURE__*/React.createElement("div", {
      className: "mcc-chat-pop-title-row"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mcc-chat-pop-title"
    }, "Broomva/"), /*#__PURE__*/React.createElement("span", {
      className: "mc-badge"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: "var(--bv-blue-accent)"
      }
    }), "2 need you")), /*#__PURE__*/React.createElement("div", {
      className: "mcc-fm-chips"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-receipt"
    }, "kind: workspace"), /*#__PURE__*/React.createElement("span", {
      className: "mc-receipt"
    }, "runner: claude \xB7 worktrees 2/2"), /*#__PURE__*/React.createElement("span", {
      className: "mc-receipt"
    }, "defaults: gate human-approve"))), /*#__PURE__*/React.createElement("div", {
      className: "mcc-panel-activity"
    }, /*#__PURE__*/React.createElement("div", {
      className: "mcc-panel-label",
      style: {
        paddingBottom: 0
      }
    }, "Places \xB7 contracts cascade down"), /*#__PURE__*/React.createElement("div", {
      className: "mcc-sess-list"
    }, /*#__PURE__*/React.createElement(MccTcRow, {
      glyph: /*#__PURE__*/React.createElement(IcFolderOpen, {
        size: 14
      }),
      label: "hawthorne",
      meta: "1/6 done \xB7 2 need you \xB7 budget 24h/wk",
      onClick: () => setScope("hawthorne")
    }), /*#__PURE__*/React.createElement(MccTcRow, {
      glyph: /*#__PURE__*/React.createElement("span", {
        className: "mcc-dot-tide",
        style: {
          width: 13,
          height: 13
        }
      }),
      label: "genesis",
      meta: "1 live \xB7 reduce the NDJSON stream"
    }), /*#__PURE__*/React.createElement(MccTcRow, {
      glyph: /*#__PURE__*/React.createElement("span", {
        className: "mcc-dot-tide",
        style: {
          width: 13,
          height: 13
        }
      }),
      label: "ops",
      meta: "1 live \xB7 1 standing \xB7 nightly digest 02:00"
    })), /*#__PURE__*/React.createElement("div", {
      className: "mcc-panel-label",
      style: {
        paddingBottom: 0
      }
    }, "The score"), /*#__PURE__*/React.createElement(MccTcRow, {
      glyph: /*#__PURE__*/React.createElement("span", {
        className: "mc-chip-dot",
        style: {
          background: "var(--bv-success)"
        }
      }),
      label: "6h 24m unsupervised today",
      meta: "2 looks \xB7 longest run 3h 50m"
    })));
  }
  if (scope === "hawthorne") {
    return /*#__PURE__*/React.createElement("aside", {
      className: "mcc-live-panel",
      "data-screen-label": "Folder inspector (initiative)"
    }, /*#__PURE__*/React.createElement("div", {
      className: "mcc-panel-head"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-detail-breadcrumb"
    }, "Broomva / hawthorne"), /*#__PURE__*/React.createElement("div", {
      className: "mcc-chat-pop-title-row"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mcc-chat-pop-title"
    }, "hawthorne/"), /*#__PURE__*/React.createElement("span", {
      className: "mc-badge"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: "var(--bv-blue-accent)"
      }
    }), "2 need you")), /*#__PURE__*/React.createElement("div", {
      className: "mcc-fm-chips"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-receipt"
    }, "kind: initiative"), /*#__PURE__*/React.createElement("span", {
      className: "mc-receipt"
    }, "owner: you"), /*#__PURE__*/React.createElement("span", {
      className: "mc-receipt"
    }, "spec: hawthorne.md"), /*#__PURE__*/React.createElement("span", {
      className: "mc-receipt"
    }, "budget: 24h/wk"))), /*#__PURE__*/React.createElement("div", {
      className: "mcc-panel-activity"
    }, /*#__PURE__*/React.createElement("div", {
      className: "mcc-panel-label",
      style: {
        paddingBottom: 0
      }
    }, "Folders"), /*#__PURE__*/React.createElement("div", {
      className: "mcc-sess-list"
    }, /*#__PURE__*/React.createElement(MccTcRow, {
      glyph: /*#__PURE__*/React.createElement(IcFolder, {
        size: 14
      }),
      label: "hawthorne-core",
      meta: "3 open \xB7 1 at your gate",
      onClick: () => setScope("core")
    }), /*#__PURE__*/React.createElement(MccTcRow, {
      glyph: /*#__PURE__*/React.createElement("span", {
        className: "mc-chip-dot",
        style: {
          background: "var(--bv-warning)",
          marginTop: 5
        }
      }),
      label: "hawthorne-db",
      meta: "1 stuck \xB7 needs a Linear API scope"
    }), /*#__PURE__*/React.createElement(MccTcRow, {
      glyph: /*#__PURE__*/React.createElement(IcFolder, {
        size: 14
      }),
      label: "hawthorne-engine",
      meta: "1 queued \xB7 1 done"
    })), /*#__PURE__*/React.createElement("div", {
      className: "mcc-panel-label",
      style: {
        paddingBottom: 0
      }
    }, "Sessions today"), /*#__PURE__*/React.createElement(MccTcRow, {
      glyph: /*#__PURE__*/React.createElement("span", {
        className: "mc-chip-dot",
        style: {
          background: "var(--bv-success)"
        }
      }),
      label: "3 sessions \xB7 2h 40m unsupervised",
      meta: "1 look \xB7 the API design review"
    })));
  }
  return /*#__PURE__*/React.createElement("aside", {
    className: "mcc-live-panel",
    "data-screen-label": "Folder inspector (project, W2)"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-detail-breadcrumb"
  }, "hawthorne / hawthorne-core"), /*#__PURE__*/React.createElement("div", {
    className: "mcc-chat-pop-title-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-chat-pop-title"
  }, "hawthorne-core/"), /*#__PURE__*/React.createElement("span", {
    className: "mc-badge"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      background: "var(--bv-blue-accent)"
    }
  }), "At your gate")), /*#__PURE__*/React.createElement("div", {
    className: "mcc-fm-chips"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-receipt"
  }, "kind: project"), /*#__PURE__*/React.createElement("span", {
    className: "mc-receipt"
  }, "owner: maestro"), /*#__PURE__*/React.createElement("span", {
    className: "mc-receipt"
  }, "budget: 8h unsupervised"), /*#__PURE__*/React.createElement("span", {
    className: "mc-receipt"
  }, "gate: human-approve"))), /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-activity"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label",
    style: {
      paddingBottom: 0
    }
  }, "Contract"), /*#__PURE__*/React.createElement("div", {
    className: "mcc-sess-list"
  }, /*#__PURE__*/React.createElement(MccTcRow, {
    glyph: /*#__PURE__*/React.createElement(IcDoc, {
      size: 14
    }),
    label: "spec.md",
    meta: "persist transcripts on the Run record \xB7 updated 2d"
  }), /*#__PURE__*/React.createElement(MccTcRow, {
    glyph: /*#__PURE__*/React.createElement(IcFolder, {
      size: 14
    }),
    label: "notes/",
    meta: "2 files \xB7 prior-art survey, API decisions"
  })), /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label",
    style: {
      paddingBottom: 0
    }
  }, "Sessions"), /*#__PURE__*/React.createElement("div", {
    className: "mcc-sess-list"
  }, /*#__PURE__*/React.createElement(MccTcRow, {
    glyph: /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: "var(--bv-blue-accent)",
        marginTop: 5
      }
    }),
    label: "persist run transcripts",
    meta: "maestro \u2192 claude \xB7 2h 14m \xB7 ran to the gate"
  }), /*#__PURE__*/React.createElement(MccTcRow, {
    glyph: /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: "var(--bv-success)",
        marginTop: 5
      }
    }),
    label: "API design review",
    meta: "you \u2192 claude \xB7 38 events \xB7 done (2 looks)"
  }))));
}
function MccTreeFrame({
  initial
}) {
  const noop = () => {};
  const [scope, setScope] = React.useState(initial);
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-fill"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-app"
  }, /*#__PURE__*/React.createElement(MccTcSidebar, {
    scope: scope,
    setScope: setScope
  }), /*#__PURE__*/React.createElement("div", {
    className: "bv-main"
  }, /*#__PURE__*/React.createElement(McvTopBar, {
    theme: "light",
    onToggleTheme: noop,
    onOpenMaestro: noop,
    onWake: noop,
    waking: false,
    canWake: true,
    onShowIdea: noop,
    counts: {
      needYou: 1,
      stuck: 1
    },
    workers: ["claude", "bookkeeper"],
    wakes: MCC_TICK_WAKES,
    items: WK_ITEMS,
    onAttention: noop,
    onCommand: noop
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-merged-row",
    style: {
      gridTemplateColumns: "minmax(0, 1fr) 440px"
    }
  }, /*#__PURE__*/React.createElement(MccTcPlane, {
    scope: scope
  }), /*#__PURE__*/React.createElement(MccTcPanel, {
    scope: scope,
    setScope: setScope
  })))));
}
function MccTreeRoot() {
  return /*#__PURE__*/React.createElement(MccTreeFrame, {
    initial: "root"
  });
}
function MccTreeInitiative() {
  return /*#__PURE__*/React.createElement(MccTreeFrame, {
    initial: "hawthorne"
  });
}
function MccTreeProject() {
  return /*#__PURE__*/React.createElement(MccTreeFrame, {
    initial: "core"
  });
}
Object.assign(window, {
  MccTreeSchema,
  MccTreeRoot,
  MccTreeInitiative,
  MccTreeProject,
  MccTcSidebar,
  MccTcPlane,
  MccTcPanel
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/ConceptTreeClick.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/ConceptUser.jsx
try { (() => {
// The account / user page · clicking the "Ana Diaz" row in the sidebar footer.
// Center of gravity: who you are and, in this product, your autonomy score —
// how much work ran without you. Full-page frame on the canonical BvNavTree.
// Two views, toggled in the top bar: an Overview dashboard, and an editable
// Account page (identity · preferences · security). Reuses globals defined by
// ConceptSettings (IcKey, IcShield, IcLink, SetSwitch, SetSeg) · loaded first.

const IcPencil = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M12 20h9"
}), /*#__PURE__*/React.createElement("path", {
  d: "M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4Z"
}));
const IcLogOut = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"
}), /*#__PURE__*/React.createElement("path", {
  d: "M16 17l5-5-5-5"
}), /*#__PURE__*/React.createElement("path", {
  d: "M21 12H9"
}));
const IcLaptop = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("rect", {
  x: "3",
  y: "4",
  width: "18",
  height: "12",
  rx: "2"
}), /*#__PURE__*/React.createElement("path", {
  d: "M2 20h20"
}));
const IcPhone = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("rect", {
  x: "7",
  y: "2",
  width: "10",
  height: "20",
  rx: "2"
}), /*#__PURE__*/React.createElement("path", {
  d: "M11 18h2"
}));
const USR_WEEK = [{
  d: "Mon",
  h: 4.1
}, {
  d: "Tue",
  h: 6.4
}, {
  d: "Wed",
  h: 2.0
}, {
  d: "Thu",
  h: 7.6,
  peak: true
}, {
  d: "Fri",
  h: 5.2
}, {
  d: "Sat",
  h: 1.1
}, {
  d: "Sun",
  h: 4.8
}];
function MccUser({
  onOpenView
}) {
  const [view, setView] = React.useState("overview"); // overview | account
  const maxH = Math.max(...USR_WEEK.map(d => d.h));

  // Your sessions vs the loop's · drawn from the shared History dataset.
  const mine = (typeof HIST_SESSIONS !== "undefined" ? HIST_SESSIONS : []).slice(0, 6);
  const IdentityHeader = ({
    big
  }) => /*#__PURE__*/React.createElement("div", {
    className: "usr-id"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-id-avatar"
  }, /*#__PURE__*/React.createElement(McAvatar, {
    name: "Ana Diaz",
    color: "var(--bv-gray-600)",
    size: big ? 76 : 64
  })), /*#__PURE__*/React.createElement("div", {
    className: "usr-id-meta"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-id-name"
  }, "Ana Diaz"), /*#__PURE__*/React.createElement("div", {
    className: "usr-id-line"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-role"
  }, "Operator \xB7 Owner"), /*#__PURE__*/React.createElement("span", {
    className: "usr-id-sep"
  }), /*#__PURE__*/React.createElement("span", null, "ana@broomva.ai"), /*#__PURE__*/React.createElement("span", {
    className: "usr-id-sep"
  }), /*#__PURE__*/React.createElement("span", null, "joined Mar 2025"))), /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    variant: "secondary",
    onClick: () => setView("account")
  }, /*#__PURE__*/React.createElement(IcPencil, {
    size: 16
  }), "Edit profile"));
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-fill"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-app",
    style: {
      gridTemplateColumns: bvNavGrid()
    }
  }, /*#__PURE__*/React.createElement(BvNavTree, {
    active: "user",
    inApp: true,
    onNav: onOpenView
  }), /*#__PURE__*/React.createElement("div", {
    className: "bv-main"
  }, /*#__PURE__*/React.createElement("header", {
    className: "bv-top-bar",
    "data-screen-label": "Account \xB7 top bar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-topbar-left"
  }, /*#__PURE__*/React.createElement(McAvatar, {
    name: "Ana Diaz",
    color: "var(--bv-gray-600)",
    size: 20
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      color: "var(--foreground)",
      fontWeight: 600
    }
  }, "Ana Diaz")), /*#__PURE__*/React.createElement("div", {
    className: "set-topright"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-runner-pill"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-runner-dot"
  }), "31h 12m unsupervised this week"), /*#__PURE__*/React.createElement(DsSegmented, {
    value: view,
    onChange: setView,
    options: [{
      value: "overview",
      label: "Overview"
    }, {
      value: "account",
      label: "Account"
    }]
  }))), view === "overview" ? /*#__PURE__*/React.createElement("div", {
    className: "usr-wrap",
    "data-screen-label": "Account \xB7 overview"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-inner"
  }, /*#__PURE__*/React.createElement(IdentityHeader, {
    big: true
  }), /*#__PURE__*/React.createElement("div", {
    className: "usr-score"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-score-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-score-title"
  }, "Your autonomy score"), /*#__PURE__*/React.createElement("span", {
    className: "usr-score-sub"
  }, "the number this product is really about \xB7 how long work ran without you")), /*#__PURE__*/React.createElement("div", {
    className: "usr-score-stats"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-stat"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-stat-val"
  }, "31", /*#__PURE__*/React.createElement("small", null, "h"), " 12", /*#__PURE__*/React.createElement("small", null, "m")), /*#__PURE__*/React.createElement("div", {
    className: "usr-stat-label"
  }, "Unsupervised this week"), /*#__PURE__*/React.createElement("div", {
    className: "usr-stat-foot"
  }, "+18% vs last week")), /*#__PURE__*/React.createElement("div", {
    className: "usr-stat"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-stat-val"
  }, "9"), /*#__PURE__*/React.createElement("div", {
    className: "usr-stat-label"
  }, "Times you had to look"), /*#__PURE__*/React.createElement("div", {
    className: "usr-stat-foot"
  }, "2 today \xB7 mostly scope grants")), /*#__PURE__*/React.createElement("div", {
    className: "usr-stat"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-stat-val"
  }, "3", /*#__PURE__*/React.createElement("small", null, "h"), " 50", /*#__PURE__*/React.createElement("small", null, "m")), /*#__PURE__*/React.createElement("div", {
    className: "usr-stat-label"
  }, "Longest single run"), /*#__PURE__*/React.createElement("div", {
    className: "usr-stat-foot"
  }, "M1b execution loop \xB7 Tue"))), /*#__PURE__*/React.createElement("div", {
    className: "usr-week"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-week-bars"
  }, USR_WEEK.map(d => /*#__PURE__*/React.createElement("div", {
    className: "usr-week-day",
    key: d.d
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-week-bar" + (d.peak ? " is-peak" : ""),
    style: {
      height: Math.round(d.h / maxH * 56) + "px"
    },
    title: d.h + "h"
  }), /*#__PURE__*/React.createElement("span", {
    className: "usr-week-lab"
  }, d.d)))))), /*#__PURE__*/React.createElement("div", {
    className: "usr-cols"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-card-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-card-head-title"
  }, "Your sessions"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "usr-card-link",
    onClick: () => onOpenView && onOpenView("history")
  }, "Open History \u2192")), mine.map(s => /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "usr-sess",
    key: s.id,
    onClick: () => onOpenView && onOpenView("history")
  }, s.state === "live" ? /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 12,
      height: 12
    }
  }) : /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      width: 8,
      height: 8,
      background: s.state === "halt" ? "var(--bv-blue-accent)" : s.state === "blocked" ? "var(--bv-warning)" : "var(--bv-success)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "usr-sess-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-sess-title"
  }, s.title), /*#__PURE__*/React.createElement("span", {
    className: "usr-sess-meta"
  }, s.folder.split(" / ").slice(-1)[0], " \xB7 ", s.dur)), /*#__PURE__*/React.createElement("span", {
    className: "usr-sess-kind usr-sess-kind--" + (s.kind === "you" ? "you" : "loop")
  }, s.kind === "you" ? "you" : "loop")))), /*#__PURE__*/React.createElement("div", {
    className: "usr-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-card-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-card-head-title"
  }, "Preferences")), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-main"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-label"
  }, "Start view"), /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-desc"
  }, "Where the app opens")), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-control"
  }, /*#__PURE__*/React.createElement(SetSeg, {
    value: "needs",
    set: () => {},
    options: [["needs", "Needs you"], ["mc", "Mission"]]
  }))), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-main"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-label"
  }, "Default runner"), /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-desc"
  }, "For sessions you start")), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-control"
  }, /*#__PURE__*/React.createElement(SetSeg, {
    value: "claude",
    set: () => {},
    options: [["claude", "claude"], ["codex", "codex"]]
  }))), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-main"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-label"
  }, "Digest email"), /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-desc"
  }, "A morning summary of overnight work")), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-control"
  }, /*#__PURE__*/React.createElement(SetSwitch, {
    on: true,
    onClick: () => {}
  }))), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-main"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-label"
  }, "Show autonomy clock"), /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-desc"
  }, "In the sidebar footer")), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-control"
  }, /*#__PURE__*/React.createElement(SetSwitch, {
    on: true,
    onClick: () => {}
  }))))))) : /*#__PURE__*/React.createElement("div", {
    className: "usr-wrap",
    "data-screen-label": "Account \xB7 account"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-inner"
  }, /*#__PURE__*/React.createElement(IdentityHeader, null), /*#__PURE__*/React.createElement("div", {
    className: "usr-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-card-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-card-head-title"
  }, "Identity"), /*#__PURE__*/React.createElement("span", {
    className: "mc-receipt"
  }, "syncs to your profile")), /*#__PURE__*/React.createElement("div", {
    className: "usr-form"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-form-field"
  }, /*#__PURE__*/React.createElement("label", {
    className: "usr-form-label"
  }, "Full name"), /*#__PURE__*/React.createElement("input", {
    className: "set-input",
    defaultValue: "Ana Diaz"
  })), /*#__PURE__*/React.createElement("div", {
    className: "usr-form-field"
  }, /*#__PURE__*/React.createElement("label", {
    className: "usr-form-label"
  }, "Display name"), /*#__PURE__*/React.createElement("input", {
    className: "set-input",
    defaultValue: "Ana"
  })), /*#__PURE__*/React.createElement("div", {
    className: "usr-form-field"
  }, /*#__PURE__*/React.createElement("label", {
    className: "usr-form-label"
  }, "Email"), /*#__PURE__*/React.createElement("input", {
    className: "set-input",
    defaultValue: "ana@broomva.ai"
  })), /*#__PURE__*/React.createElement("div", {
    className: "usr-form-field"
  }, /*#__PURE__*/React.createElement("label", {
    className: "usr-form-label"
  }, "Role"), /*#__PURE__*/React.createElement("input", {
    className: "set-input",
    defaultValue: "Operator",
    disabled: true,
    style: {
      opacity: 0.6
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "usr-form-field usr-form-field--full"
  }, /*#__PURE__*/React.createElement("label", {
    className: "usr-form-label"
  }, "Timezone"), /*#__PURE__*/React.createElement("input", {
    className: "set-input set-input--full",
    defaultValue: "America/Mexico_City (GMT\u22126)"
  })))), /*#__PURE__*/React.createElement("div", {
    className: "usr-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-card-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-card-head-title"
  }, "Personal preferences")), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-main"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-label"
  }, "Theme"), /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-desc"
  }, "Overrides the workspace default for you")), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-control"
  }, /*#__PURE__*/React.createElement(SetSeg, {
    value: "system",
    set: () => {},
    options: [["light", "Light"], ["dark", "Dark"], ["system", "System"]]
  }))), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-main"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-label"
  }, "Keyboard shortcuts"), /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-desc"
  }, /*#__PURE__*/React.createElement("code", null, "\u2318K"), " command \xB7 ", /*#__PURE__*/React.createElement("code", null, "g h"), " History \xB7 ", /*#__PURE__*/React.createElement("code", null, "g k"), " Knowledge")), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-control"
  }, /*#__PURE__*/React.createElement(SetSwitch, {
    on: true,
    onClick: () => {}
  }))), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-main"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-label"
  }, "Reduced motion"), /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-desc"
  }, "Calm the Undertow and tidepool animations")), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-control"
  }, /*#__PURE__*/React.createElement(SetSwitch, {
    on: false,
    onClick: () => {}
  })))), /*#__PURE__*/React.createElement("div", {
    className: "usr-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-card-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-card-head-title"
  }, "Security")), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-main"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-label"
  }, "Sign-in method"), /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-desc"
  }, "Google \xB7 ana@broomva.ai \xB7 passkey enabled")), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-control"
  }, /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    variant: "secondary"
  }, "Manage"))), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-main"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-label"
  }, "API keys"), /*#__PURE__*/React.createElement("span", {
    className: "usr-prow-desc"
  }, /*#__PURE__*/React.createElement("code", null, "brm_live_\u2022\u2022\u2022\u20224f2a"), " \xB7 2 active")), /*#__PURE__*/React.createElement("div", {
    className: "usr-prow-control"
  }, /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    variant: "secondary"
  }, /*#__PURE__*/React.createElement(IcKey, {
    size: 16
  }), "Keys")))), /*#__PURE__*/React.createElement("div", {
    className: "usr-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "usr-card-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-card-head-title"
  }, "Where you're signed in")), /*#__PURE__*/React.createElement("div", {
    className: "usr-dev"
  }, /*#__PURE__*/React.createElement("span", {
    className: "set-rowglyph"
  }, /*#__PURE__*/React.createElement(IcLaptop, {
    size: 16
  })), /*#__PURE__*/React.createElement("div", {
    className: "usr-dev-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-dev-name"
  }, "MacBook Pro \xB7 Chrome ", /*#__PURE__*/React.createElement("span", {
    className: "usr-here"
  }, "this device")), /*#__PURE__*/React.createElement("span", {
    className: "usr-dev-meta"
  }, "Mexico City \xB7 active now"))), /*#__PURE__*/React.createElement("div", {
    className: "usr-dev"
  }, /*#__PURE__*/React.createElement("span", {
    className: "set-rowglyph"
  }, /*#__PURE__*/React.createElement(IcPhone, {
    size: 16
  })), /*#__PURE__*/React.createElement("div", {
    className: "usr-dev-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-dev-name"
  }, "iPhone 15 \xB7 Broomva PWA"), /*#__PURE__*/React.createElement("span", {
    className: "usr-dev-meta"
  }, "Mexico City \xB7 2h ago")), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "usr-danger"
  }, "Revoke")), /*#__PURE__*/React.createElement("div", {
    className: "usr-dev"
  }, /*#__PURE__*/React.createElement("span", {
    className: "set-rowglyph"
  }, /*#__PURE__*/React.createElement(IcLaptop, {
    size: 16
  })), /*#__PURE__*/React.createElement("div", {
    className: "usr-dev-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "usr-dev-name"
  }, "Linux \xB7 cloud sandbox runner"), /*#__PURE__*/React.createElement("span", {
    className: "usr-dev-meta"
  }, "us-east \xB7 6h ago")), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "usr-danger"
  }, "Revoke"))), /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    variant: "secondary",
    style: {
      alignSelf: "flex-start",
      color: "var(--bv-danger)"
    }
  }, /*#__PURE__*/React.createElement(IcLogOut, {
    size: 16
  }), "Sign out"))))));
}
Object.assign(window, {
  MccUser
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/ConceptUser.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/KgGraph.jsx
try { (() => {
// KgGraph.jsx · the hierarchical, force-directed knowledge graph for the
// Knowledge page. Nodes are files; edges are `related:` links; gold nodes are
// folders you can enter (zoom-morph between scopes). Plus the surfaces the page
// flows need: type-filter dimming, auto-frame-to-matches on search, a hover
// preview card, a minimap, and KgMiniGraph for the detail drawer.

// Scope (folder) nodes · blue-black ink, in the system's one hue family.
const KG_GOLD = "oklch(0.38 0.045 265)";
const KG_TYPE = {
  concept: {
    color: "var(--bv-blue)",
    label: "concept"
  },
  pattern: {
    color: "var(--bv-glow-indigo)",
    label: "pattern"
  },
  primitive: {
    color: "var(--bv-blue-accent)",
    label: "primitive"
  },
  tool: {
    color: "oklch(0.60 0.09 245)",
    label: "tool"
  },
  person: {
    color: "var(--bv-gray-600)",
    label: "person"
  },
  paper: {
    color: "oklch(0.70 0.06 260)",
    label: "paper"
  },
  decision: {
    color: "oklch(0.50 0.14 260)",
    label: "decision"
  },
  doc: {
    color: "var(--bv-gray-500)",
    label: "doc"
  },
  session: {
    color: "var(--bv-info)",
    label: "session"
  },
  vault: {
    color: KG_GOLD,
    label: "meta-vault"
  },
  workspace: {
    color: KG_GOLD,
    label: "workspace"
  },
  initiative: {
    color: KG_GOLD,
    label: "initiative"
  },
  project: {
    color: KG_GOLD,
    label: "project"
  },
  task: {
    color: KG_GOLD,
    label: "task"
  },
  routine: {
    color: KG_GOLD,
    label: "routine"
  }
};
const kgIsScope = n => !!n.scopeRef;
const kgCategory = n => kgIsScope(n) ? "folder" : n.type;
const kgTypeColor = n => kgIsScope(n) ? KG_GOLD : (KG_TYPE[n.type] || KG_TYPE.concept).color;
function kgHash(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return (h >>> 0) / 4294967295;
}
function kgEdges(nodes) {
  const ids = new Set(nodes.map(n => n.id));
  const seen = new Set(),
    out = [];
  nodes.forEach(n => (n.related || []).forEach(r => {
    if (!ids.has(r)) return;
    const key = [n.id, r].sort().join("|");
    if (seen.has(key) || n.id === r) return;
    seen.add(key);
    out.push({
      s: n.id,
      t: r
    });
  }));
  return out;
}
function kgLayout(nodes, edges, W, H) {
  const pos = {};
  nodes.forEach(n => {
    const a = kgHash(n.id) * Math.PI * 2;
    const r = (kgIsScope(n) ? 20 : 55) + kgHash(n.id + "r") * Math.min(W, H) * 0.28;
    pos[n.id] = {
      x: W / 2 + Math.cos(a) * r,
      y: H / 2 + Math.sin(a) * r,
      vx: 0,
      vy: 0
    };
  });
  const cx = W / 2,
    cy = H / 2,
    ideal = 116;
  for (let it = 0; it < 340; it++) {
    const alpha = 1 - it / 340;
    for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
      const a = pos[nodes[i].id],
        b = pos[nodes[j].id];
      let dx = a.x - b.x,
        dy = a.y - b.y,
        d2 = dx * dx + dy * dy || 0.01,
        d = Math.sqrt(d2);
      const f = 4600 / d2,
        ux = dx / d,
        uy = dy / d;
      a.vx += ux * f;
      a.vy += uy * f;
      b.vx -= ux * f;
      b.vy -= uy * f;
    }
    edges.forEach(e => {
      const a = pos[e.s],
        b = pos[e.t];
      if (!a || !b) return;
      let dx = b.x - a.x,
        dy = b.y - a.y,
        d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = (d - ideal) * 0.022,
        ux = dx / d,
        uy = dy / d;
      a.vx += ux * f;
      a.vy += uy * f;
      b.vx -= ux * f;
      b.vy -= uy * f;
    });
    nodes.forEach(n => {
      const p = pos[n.id],
        pull = kgIsScope(n) ? 0.03 : 0.009;
      p.vx += (cx - p.x) * pull;
      p.vy += (cy - p.y) * pull;
      p.x += p.vx * alpha * 0.85;
      p.y += p.vy * alpha * 0.85;
      p.vx *= 0.82;
      p.vy *= 0.82;
      p.x = Math.max(46, Math.min(W - 46, p.x));
      p.y = Math.max(40, Math.min(H - 36, p.y));
    });
  }
  return pos;
}
const kgLerp = (a, b, t) => a + (b - a) * t;
const kgClamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const kgScaleAround = (px, py, s) => `translate(${(px * (1 - s)).toFixed(2)} ${(py * (1 - s)).toFixed(2)}) scale(${s.toFixed(4)})`;
const kgNodeR = (n, deg) => kgIsScope(n) ? 13 + Math.min(deg || 0, 5) : 7 + Math.min(deg || 0, 6) * 1.4;

// Tiny radial neighborhood graph for the detail drawer (center + neighbours).
function KgMiniGraph({
  scope,
  centerId,
  onPick,
  w = 300,
  h = 190
}) {
  const center = scope.nodes.find(n => n.id === centerId);
  if (!center) return null;
  const nb = scope.nodes.filter(n => n.id !== centerId && ((center.related || []).includes(n.id) || (n.related || []).includes(centerId)));
  const cx = w / 2,
    cy = h / 2,
    R = Math.min(w, h) / 2 - 30;
  const pts = nb.map((n, i) => {
    const a = -Math.PI / 2 + i / Math.max(nb.length, 1) * Math.PI * 2;
    return {
      n,
      x: cx + Math.cos(a) * R,
      y: cy + Math.sin(a) * R
    };
  });
  return /*#__PURE__*/React.createElement("svg", {
    viewBox: `0 0 ${w} ${h}`,
    className: "kg-mini",
    preserveAspectRatio: "xMidYMid meet"
  }, pts.map((p, i) => /*#__PURE__*/React.createElement("line", {
    key: i,
    x1: cx,
    y1: cy,
    x2: p.x,
    y2: p.y,
    className: "kg-edge",
    style: {
      opacity: 0.35
    }
  })), pts.map(p => /*#__PURE__*/React.createElement("g", {
    key: p.n.id,
    transform: `translate(${p.x} ${p.y})`,
    style: {
      cursor: "pointer"
    },
    onClick: () => onPick && onPick(p.n.id)
  }, /*#__PURE__*/React.createElement("circle", {
    r: kgIsScope(p.n) ? 8 : 6,
    fill: kgTypeColor(p.n),
    stroke: "var(--card)",
    strokeWidth: "2"
  }), /*#__PURE__*/React.createElement("text", {
    className: "kg-mini-label",
    x: 0,
    y: kgIsScope(p.n) ? 19 : 17,
    textAnchor: "middle"
  }, p.n.label))), /*#__PURE__*/React.createElement("g", {
    transform: `translate(${cx} ${cy})`
  }, /*#__PURE__*/React.createElement("circle", {
    r: 11,
    fill: kgTypeColor(center),
    stroke: "var(--card)",
    strokeWidth: "2.5"
  })));
}
function KgGraph({
  scope,
  scopes,
  selectedId,
  onSelectNode,
  onNavigate,
  query,
  typeFilter,
  width = 840,
  height = 560
}) {
  const cache = React.useRef({});
  const getLayout = React.useCallback(sc => {
    if (!cache.current[sc.id]) {
      const edges = kgEdges(sc.nodes),
        pos = kgLayout(sc.nodes, edges, width, height),
        deg = {};
      sc.nodes.forEach(n => deg[n.id] = 0);
      edges.forEach(e => {
        deg[e.s]++;
        deg[e.t]++;
      });
      cache.current[sc.id] = {
        pos,
        edges,
        deg
      };
    }
    return cache.current[sc.id];
  }, [width, height]);
  const [view, setView] = React.useState({
    tx: 0,
    ty: 0,
    k: 1
  });
  const [panning, setPanning] = React.useState(false);
  const [hover, setHover] = React.useState(null);
  const [override, setOverride] = React.useState({});
  const [trans, setTrans] = React.useState(null);
  const prevScope = React.useRef(scope);
  const raf = React.useRef(0);
  const svgRef = React.useRef(null);
  const stageRef = React.useRef(null);
  const drag = React.useRef(null);
  const childOnPath = React.useCallback((ancId, desc) => {
    let p = desc;
    while (p && p.parent && p.parent !== ancId) p = scopes[p.parent];
    return p && p.parent === ancId ? p : null;
  }, [scopes]);
  const layout = getLayout(scope);
  const pos = {
    ...layout.pos,
    ...override
  };
  const edges = layout.edges,
    deg = layout.deg;
  const q = (query || "").trim().toLowerCase();
  const nodeById = React.useMemo(() => Object.fromEntries(scope.nodes.map(n => [n.id, n])), [scope]);
  const isHit = id => {
    if (!q) return true;
    const n = nodeById[id];
    return (n.label + " " + (n.claim || "") + " " + n.type).toLowerCase().includes(q);
  };
  const offType = n => typeFilter && typeFilter.size && !typeFilter.has(kgCategory(n));
  const neighbors = id => {
    const s = new Set([id]);
    edges.forEach(e => {
      if (e.s === id) s.add(e.t);
      if (e.t === id) s.add(e.s);
    });
    return s;
  };
  const focusId = hover || selectedId;
  const focusSet = focusId ? neighbors(focusId) : null;

  // morph on scope change
  React.useEffect(() => {
    const from = prevScope.current,
      to = scope;
    if (from.id === to.id) return;
    setView({
      tx: 0,
      ty: 0,
      k: 1
    });
    setOverride({});
    let dir = "jump",
      anchor = {
        x: width / 2,
        y: height / 2
      };
    const down = childOnPath(from.id, to),
      up = childOnPath(to.id, from);
    if (down) {
      dir = "descend";
      const a = getLayout(from).pos[down.id];
      if (a) anchor = {
        x: a.x,
        y: a.y
      };
    } else if (up) {
      dir = "ascend";
      const a = getLayout(to).pos[up.id];
      if (a) anchor = {
        x: a.x,
        y: a.y
      };
    }
    cancelAnimationFrame(raf.current);
    const start = performance.now(),
      dur = 660;
    const tick = now => {
      const raw = Math.min(1, (now - start) / dur);
      const e = raw < 0.5 ? 2 * raw * raw : 1 - Math.pow(-2 * raw + 2, 2) / 2;
      setTrans({
        from,
        to,
        dir,
        anchor,
        t: e
      });
      if (raw < 1) raf.current = requestAnimationFrame(tick);else setTrans(null);
    };
    raf.current = requestAnimationFrame(tick);
    prevScope.current = scope;
    return () => cancelAnimationFrame(raf.current);
  }, [scope, childOnPath, getLayout, width, height]);

  // auto-frame to search matches (and reset when cleared)
  React.useEffect(() => {
    if (trans) return;
    if (!q) {
      setView({
        tx: 0,
        ty: 0,
        k: 1
      });
      return;
    }
    const hits = scope.nodes.filter(n => isHit(n.id)).map(n => pos[n.id]).filter(Boolean);
    if (!hits.length) return;
    let x0 = 1e9,
      y0 = 1e9,
      x1 = -1e9,
      y1 = -1e9;
    hits.forEach(p => {
      x0 = Math.min(x0, p.x);
      y0 = Math.min(y0, p.y);
      x1 = Math.max(x1, p.x);
      y1 = Math.max(y1, p.y);
    });
    const pad = 110,
      bw = x1 - x0 + pad,
      bh = y1 - y0 + pad,
      cx = (x0 + x1) / 2,
      cy = (y0 + y1) / 2;
    const k = kgClamp(Math.min(width / bw, height / bh), 0.6, 2.0);
    setView({
      k,
      tx: width / 2 - cx * k,
      ty: height / 2 - cy * k
    });
  }, [query, scope]); // eslint-disable-line

  const toWorld = (cx, cy) => {
    const r = svgRef.current.getBoundingClientRect(),
      sx = r.width / width,
      sy = r.height / height;
    return {
      x: ((cx - r.left) / sx - view.tx) / view.k,
      y: ((cy - r.top) / sy - view.ty) / view.k
    };
  };
  const onDown = (e, id) => {
    e.preventDefault();
    svgRef.current.setPointerCapture(e.pointerId);
    if (id) drag.current = {
      type: "node",
      id,
      moved: false
    };else {
      drag.current = {
        type: "pan",
        x0: e.clientX,
        y0: e.clientY,
        tx: view.tx,
        ty: view.ty
      };
      setPanning(true);
    }
  };
  const onMove = e => {
    const d = drag.current;
    if (!d) return;
    if (d.type === "node") {
      d.moved = true;
      const w = toWorld(e.clientX, e.clientY);
      setOverride(o => ({
        ...o,
        [d.id]: {
          x: w.x,
          y: w.y
        }
      }));
    } else {
      const r = svgRef.current.getBoundingClientRect(),
        sx = r.width / width,
        sy = r.height / height;
      setView(v => ({
        ...v,
        tx: d.tx + (e.clientX - d.x0) / sx,
        ty: d.ty + (e.clientY - d.y0) / sy
      }));
    }
  };
  const onUp = e => {
    if (svgRef.current.hasPointerCapture(e.pointerId)) svgRef.current.releasePointerCapture(e.pointerId);
    drag.current = null;
    setPanning(false);
  };
  const zoom = f => setView(v => {
    const k = kgClamp(v.k * f, 0.45, 2.6),
      cx = width / 2,
      cy = height / 2;
    return {
      k,
      tx: cx - (cx - v.tx) * (k / v.k),
      ty: cy - (cy - v.ty) * (k / v.k)
    };
  });

  // hover preview position (px within the stage)
  const hoverNode = hover && !panning && !trans && !drag.current ? nodeById[hover] : null;
  const hoverPos = (() => {
    if (!hoverNode || !svgRef.current || !stageRef.current) return null;
    const p = pos[hover];
    if (!p) return null;
    const r = svgRef.current.getBoundingClientRect(),
      st = stageRef.current.getBoundingClientRect();
    const sx = r.width / width,
      sy = r.height / height;
    return {
      x: r.left - st.left + (view.tx + p.x * view.k) * sx,
      y: r.top - st.top + (view.ty + p.y * view.k) * sy,
      r: kgNodeR(hoverNode, deg[hover]) * sx
    };
  })();
  const drawNet = (sc, P, EG, DG, live) => /*#__PURE__*/React.createElement(React.Fragment, null, EG.map((e, i) => {
    const a = P[e.s],
      b = P[e.t];
    if (!a || !b) return null;
    const on = live && focusId && (e.s === focusId || e.t === focusId);
    const faded = live && (q && (!isHit(e.s) || !isHit(e.t)) || focusSet && !on || offType(nodeById[e.s]) || offType(nodeById[e.t]));
    return /*#__PURE__*/React.createElement("line", {
      key: i,
      x1: a.x,
      y1: a.y,
      x2: b.x,
      y2: b.y,
      className: "kg-edge" + (on ? " is-on" : ""),
      style: {
        opacity: faded ? 0.06 : on ? 0.9 : 0.3
      }
    });
  }), sc.nodes.map(n => {
    const p = P[n.id];
    if (!p) return null;
    const t = KG_TYPE[n.type] || KG_TYPE.concept,
      r = kgNodeR(n, DG[n.id]),
      folder = kgIsScope(n);
    const sel = live && n.id === selectedId;
    const faded = live && (!isHit(n.id) || offType(n) || focusSet && !focusSet.has(n.id));
    return /*#__PURE__*/React.createElement("g", {
      key: n.id,
      transform: `translate(${p.x.toFixed(2)} ${p.y.toFixed(2)})`,
      className: "kg-node",
      style: {
        opacity: faded ? 0.18 : 1,
        cursor: live ? "pointer" : "default"
      },
      onPointerDown: live ? e => {
        e.stopPropagation();
        onDown(e, n.id);
      } : undefined,
      onClick: live ? e => {
        e.stopPropagation();
        if (drag.current && drag.current.moved) return;
        if (folder) onNavigate && onNavigate(n.scopeRef);else onSelectNode && onSelectNode(n.id);
      } : undefined,
      onPointerEnter: live ? () => setHover(n.id) : undefined,
      onPointerLeave: live ? () => setHover(h => h === n.id ? null : h) : undefined
    }, sel && /*#__PURE__*/React.createElement("circle", {
      r: r + 6,
      className: "kg-ring"
    }), folder && /*#__PURE__*/React.createElement("circle", {
      r: r + 5,
      className: "kg-scope-ring"
    }), /*#__PURE__*/React.createElement("circle", {
      r: r,
      fill: t.color,
      className: "kg-dot" + (n.live ? " kg-live" : ""),
      stroke: "var(--background)",
      strokeWidth: folder ? 2.5 : 2
    }), folder && /*#__PURE__*/React.createElement("path", {
      d: "M-4.5 -2.2 h2.4 l1 1.3 h4.6 a0.7 0.7 0 0 1 0.7 0.7 v3.4 a0.7 0.7 0 0 1 -0.7 0.7 h-8 a0.7 0.7 0 0 1 -0.7 -0.7 v-4.7 a0.7 0.7 0 0 1 0.7 -0.7 z",
      fill: "var(--card)",
      opacity: "0.92"
    }), n.live && /*#__PURE__*/React.createElement("circle", {
      r: r,
      fill: "none",
      stroke: t.color,
      className: "kg-pulse"
    }), /*#__PURE__*/React.createElement("text", {
      className: "kg-label",
      x: 0,
      y: r + 13,
      textAnchor: "middle",
      style: {
        fontWeight: folder || sel || n.id === focusId ? 600 : 400
      }
    }, n.label));
  }));
  let content;
  if (trans) {
    const {
        from,
        to,
        dir,
        anchor,
        t
      } = trans,
      lf = getLayout(from),
      lt = getLayout(to);
    let fromTf, fromOp, toTf, toOp, order;
    if (dir === "descend") {
      fromTf = kgScaleAround(anchor.x, anchor.y, kgLerp(1, 2.9, t));
      fromOp = kgClamp(1 - t * 1.7, 0, 1);
      toTf = kgScaleAround(width / 2, height / 2, kgLerp(0.38, 1, t));
      toOp = kgClamp((t - 0.32) / 0.68, 0, 1);
      order = "ft";
    } else if (dir === "ascend") {
      fromTf = kgScaleAround(width / 2, height / 2, kgLerp(1, 0.4, t));
      fromOp = kgClamp(1 - t * 1.7, 0, 1);
      toTf = kgScaleAround(anchor.x, anchor.y, kgLerp(2.9, 1, t));
      toOp = kgClamp((t - 0.28) / 0.72, 0, 1);
      order = "tf";
    } else {
      fromTf = kgScaleAround(width / 2, height / 2, kgLerp(1, 1.25, t));
      fromOp = kgClamp(1 - t * 1.6, 0, 1);
      toTf = kgScaleAround(width / 2, height / 2, kgLerp(0.85, 1, t));
      toOp = kgClamp((t - 0.4) / 0.6, 0, 1);
      order = "ft";
    }
    const fromG = /*#__PURE__*/React.createElement("g", {
      key: "from",
      transform: fromTf,
      style: {
        opacity: fromOp,
        pointerEvents: "none"
      }
    }, drawNet(from, lf.pos, lf.edges, lf.deg, false));
    const toG = /*#__PURE__*/React.createElement("g", {
      key: "to",
      transform: toTf,
      style: {
        opacity: toOp,
        pointerEvents: "none"
      }
    }, drawNet(to, lt.pos, lt.edges, lt.deg, false));
    content = order === "ft" ? [fromG, toG] : [toG, fromG];
  } else {
    content = /*#__PURE__*/React.createElement("g", {
      transform: `translate(${view.tx} ${view.ty}) scale(${view.k})`,
      style: {
        transition: panning ? "none" : "transform 0.45s var(--bv-ease-standard)"
      }
    }, drawNet(scope, pos, edges, deg, true));
  }

  // minimap geometry
  const mmW = 150,
    mmH = 108,
    mmK = Math.min(mmW / width, mmH / height) * 0.9,
    mmOx = (mmW - width * mmK) / 2,
    mmOy = (mmH - height * mmK) / 2;
  const vx = -view.tx / view.k,
    vy = -view.ty / view.k,
    vw = width / view.k,
    vh = height / view.k;
  const onMinimap = e => {
    const r = e.currentTarget.getBoundingClientRect();
    const mx = (e.clientX - r.left) / r.width * mmW,
      my = (e.clientY - r.top) / r.height * mmH;
    const lx = (mx - mmOx) / mmK,
      ly = (my - mmOy) / mmK;
    setView(v => ({
      ...v,
      tx: width / 2 - lx * v.k,
      ty: height / 2 - ly * v.k
    }));
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "kg-stage",
    ref: stageRef
  }, /*#__PURE__*/React.createElement("svg", {
    ref: svgRef,
    className: "kg-svg",
    viewBox: `0 0 ${width} ${height}`,
    preserveAspectRatio: "xMidYMid meet",
    onPointerDown: trans ? undefined : e => onDown(e, null),
    onPointerMove: onMove,
    onPointerUp: onUp,
    onPointerCancel: onUp
  }, content), hoverNode && hoverPos && /*#__PURE__*/React.createElement("div", {
    className: "kg-hovercard",
    style: {
      left: hoverPos.x,
      top: hoverPos.y - (hoverPos.r + 10)
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "kg-hover-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "kg-legend-dot",
    style: {
      background: kgTypeColor(hoverNode)
    }
  }), /*#__PURE__*/React.createElement("b", null, hoverNode.label), /*#__PURE__*/React.createElement("span", {
    className: "kg-hover-kind"
  }, (KG_TYPE[hoverNode.type] || {}).label || hoverNode.type)), /*#__PURE__*/React.createElement("p", {
    className: "kg-hover-claim"
  }, hoverNode.claim), hoverNode.score && /*#__PURE__*/React.createElement("div", {
    className: "kg-hover-score"
  }, "Nous ", hoverNode.score[0] + hoverNode.score[1] + hoverNode.score[2], "/9"), kgIsScope(hoverNode) && /*#__PURE__*/React.createElement("div", {
    className: "kg-hover-enter"
  }, "click to enter \u2192")), /*#__PURE__*/React.createElement("div", {
    className: "kg-minimap",
    onPointerDown: onMinimap
  }, /*#__PURE__*/React.createElement("svg", {
    viewBox: `0 0 ${mmW} ${mmH}`,
    width: mmW,
    height: mmH
  }, /*#__PURE__*/React.createElement("rect", {
    x: "0",
    y: "0",
    width: mmW,
    height: mmH,
    className: "kg-mm-bg"
  }), scope.nodes.map(n => {
    const p = pos[n.id];
    if (!p) return null;
    return /*#__PURE__*/React.createElement("circle", {
      key: n.id,
      cx: mmOx + p.x * mmK,
      cy: mmOy + p.y * mmK,
      r: kgIsScope(n) ? 2.6 : 1.8,
      fill: kgTypeColor(n)
    });
  }), /*#__PURE__*/React.createElement("rect", {
    className: "kg-mm-view",
    x: mmOx + vx * mmK,
    y: mmOy + vy * mmK,
    width: vw * mmK,
    height: vh * mmK
  }))), /*#__PURE__*/React.createElement("div", {
    className: "kg-zoom"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: () => zoom(1.25),
    title: "Zoom in",
    "aria-label": "Zoom in"
  }, "+"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: () => zoom(0.8),
    title: "Zoom out",
    "aria-label": "Zoom out"
  }, "\u2212"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: () => setView({
      tx: 0,
      ty: 0,
      k: 1
    }),
    title: "Reset view",
    "aria-label": "Reset view"
  }, "\u2299")), /*#__PURE__*/React.createElement("div", {
    className: "kg-legend"
  }, [["folder", "folder"], ["concept", "concept"], ["decision", "decision"], ["primitive", "primitive"], ["session", "session"]].map(([k, lab]) => /*#__PURE__*/React.createElement("span", {
    key: k,
    className: "kg-legend-item"
  }, /*#__PURE__*/React.createElement("span", {
    className: "kg-legend-dot",
    style: {
      background: k === "folder" ? KG_GOLD : KG_TYPE[k].color
    }
  }), lab))));
}
Object.assign(window, {
  KgGraph,
  KgMiniGraph,
  KG_TYPE,
  KG_GOLD,
  kgIsScope,
  kgCategory,
  kgTypeColor
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/KgGraph.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/KnowledgeApp.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
// KnowledgeApp.jsx · the full Knowledge page + its flows, built on the scope
// graph (KG_SCOPES) and KgGraph. The search field here IS the app-wide layout
// search: it opens a command palette (entities · folders · sessions · pages,
// all KG-enriched) AND, because the Knowledge view is under the same layout, it
// live-drives the graph (dim + auto-frame) and can "ask the graph". Other
// surfaces: type-filter chips, graph⇄list toggle, a slide-over detail drawer
// with a neighbourhood mini-graph, hover previews, a minimap, and a right rail
// of recently-viewed · pinned · what's-new.

const IcPin = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M12 17v5"
}), /*#__PURE__*/React.createElement("path", {
  d: "M9 10.76a2 2 0 0 1-1.11 1.79l-1.78.9A2 2 0 0 0 5 15.24V16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1v-.76a2 2 0 0 0-1.11-1.79l-1.78-.9A2 2 0 0 1 15 10.76V7a1 1 0 0 1 1-1 2 2 0 0 0 0-4H8a2 2 0 0 0 0 4 1 1 0 0 1 1 1z"
}));

// freshly-bookkept entities (the "what's new" feed) · {scopeId, nodeId, when}
const KG_FRESH = [{
  scopeId: "hawthorne-core",
  nodeId: "drun",
  when: "12m"
}, {
  scopeId: "broomva",
  nodeId: "nous",
  when: "1h"
}, {
  scopeId: "genesis",
  nodeId: "uimsg",
  when: "3h"
}, {
  scopeId: "bookkeeping",
  nodeId: "reconciled",
  when: "5h"
}, {
  scopeId: "broomva",
  nodeId: "rcs",
  when: "1d"
}];
const KG_NAV_PAGES = [{
  id: "needs",
  label: "Needs you",
  hint: "2 at your gate",
  icon: "needs"
}, {
  id: "mc",
  label: "Maestro",
  hint: "the plane",
  icon: "board"
}, {
  id: "history",
  label: "History",
  hint: "every session",
  icon: "history"
}];
function kgFlatIndex() {
  const out = [];
  Object.values(KG_SCOPES).forEach(sc => sc.nodes.forEach(n => out.push({
    scopeId: sc.id,
    scope: sc,
    node: n
  })));
  return out;
}

// ── The global search + command palette ────────────────────────────────────
function BvKgSearch({
  query,
  setQuery,
  scope,
  onPickEntity,
  onNavigate,
  onAsk
}) {
  const [open, setOpen] = React.useState(false);
  const [hi, setHi] = React.useState(0);
  const inputRef = React.useRef(null);
  const wrapRef = React.useRef(null);
  const all = React.useMemo(() => kgFlatIndex(), []);
  const q = query.trim().toLowerCase();
  React.useEffect(() => {
    const onKey = e => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        inputRef.current && inputRef.current.focus();
        setOpen(true);
      }
      if (e.key === "Escape") {
        setOpen(false);
        inputRef.current && inputRef.current.blur();
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, []);
  React.useEffect(() => {
    const off = e => {
      if (wrapRef.current && !wrapRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener("pointerdown", off, true);
    return () => document.removeEventListener("pointerdown", off, true);
  }, []);
  const match = n => (n.label + " " + (n.claim || "") + " " + n.type).toLowerCase().includes(q);
  const here = q ? scope.nodes.filter(n => !n.scopeRef && match(n)).slice(0, 5) : [];
  const folders = q ? all.filter(x => x.node.scopeRef && match(x.node)).slice(0, 4) : [];
  const elsewhere = q ? all.filter(x => x.scopeId !== scope.id && !x.node.scopeRef && match(x.node)).slice(0, 5) : [];
  const sessions = q ? all.filter(x => x.node.type === "session" && match(x.node)).slice(0, 3) : [];
  const pages = q ? KG_NAV_PAGES.filter(p => (p.label + " " + p.hint).toLowerCase().includes(q)) : [];

  // flatten into a keyboard-navigable command list
  const cmds = [];
  if (q) cmds.push({
    kind: "ask",
    label: 'Ask the graph: "' + query.trim() + '"'
  });
  here.forEach(n => cmds.push({
    kind: "entity",
    node: n,
    scopeId: scope.id,
    group: "In this scope"
  }));
  folders.forEach(x => cmds.push({
    kind: "folder",
    node: x.node,
    scopeId: x.scopeId,
    group: "Folders"
  }));
  elsewhere.forEach(x => cmds.push({
    kind: "entity",
    node: x.node,
    scopeId: x.scopeId,
    scope: x.scope,
    group: "Across the workspace"
  }));
  sessions.forEach(x => cmds.push({
    kind: "entity",
    node: x.node,
    scopeId: x.scopeId,
    scope: x.scope,
    group: "Sessions"
  }));
  pages.forEach(p => cmds.push({
    kind: "page",
    page: p,
    group: "Go to"
  }));
  const run = c => {
    if (!c) return;
    if (c.kind === "ask") {
      onAsk(query.trim());
      setOpen(false);
      return;
    }
    if (c.kind === "folder") {
      onNavigate(c.node.scopeRef);
      setOpen(false);
      return;
    }
    if (c.kind === "page") {
      onNavigate("__page:" + c.page.id);
      setOpen(false);
      return;
    }
    if (c.kind === "entity") {
      onPickEntity(c.scopeId, c.node.id);
      setOpen(false);
    }
  };
  const onKeyDown = e => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHi(h => Math.min(h + 1, cmds.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHi(h => Math.max(h - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      run(cmds[hi]);
    }
  };
  React.useEffect(() => {
    setHi(0);
  }, [query]);
  let lastGroup = null;
  return /*#__PURE__*/React.createElement("div", {
    className: "kg-search",
    ref: wrapRef
  }, /*#__PURE__*/React.createElement("div", {
    className: "kg-search-field" + (open ? " is-open" : "")
  }, /*#__PURE__*/React.createElement(IcSearch, {
    size: 15
  }), /*#__PURE__*/React.createElement("input", {
    ref: inputRef,
    value: query,
    placeholder: "Search Broomva \xB7 entities, folders, sessions\u2026",
    onChange: e => {
      setQuery(e.target.value);
      setOpen(true);
    },
    onFocus: () => setOpen(true),
    onKeyDown: onKeyDown
  }), query ? /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "kg-search-clear",
    onClick: () => {
      setQuery("");
      inputRef.current.focus();
    },
    "aria-label": "Clear"
  }, /*#__PURE__*/React.createElement(IcX, {
    size: 13
  })) : /*#__PURE__*/React.createElement("kbd", {
    className: "kg-search-kbd"
  }, "\u2318K")), open && q && /*#__PURE__*/React.createElement("div", {
    className: "kg-palette"
  }, cmds.length === 0 && /*#__PURE__*/React.createElement("div", {
    className: "kg-pal-empty"
  }, "No matches for \u201C", query.trim(), "\u201D."), cmds.map((c, i) => {
    const showGroup = c.group && c.group !== lastGroup;
    lastGroup = c.group || lastGroup;
    return /*#__PURE__*/React.createElement(React.Fragment, {
      key: i
    }, showGroup && /*#__PURE__*/React.createElement("div", {
      className: "kg-pal-group"
    }, c.group), /*#__PURE__*/React.createElement("button", {
      type: "button",
      className: "kg-pal-row" + (i === hi ? " is-hi" : ""),
      onPointerEnter: () => setHi(i),
      onClick: () => run(c)
    }, c.kind === "ask" ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
      className: "kg-pal-ask-ic"
    }, /*#__PURE__*/React.createElement(IcGraph, {
      size: 14
    })), /*#__PURE__*/React.createElement("span", {
      className: "kg-pal-label"
    }, c.label), /*#__PURE__*/React.createElement("span", {
      className: "kg-pal-meta"
    }, "enrich \u21B5")) : c.kind === "page" ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
      className: "kg-legend-dot",
      style: {
        background: "var(--bv-blue)"
      }
    }), /*#__PURE__*/React.createElement("span", {
      className: "kg-pal-label"
    }, c.page.label), /*#__PURE__*/React.createElement("span", {
      className: "kg-pal-meta"
    }, c.page.hint)) : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("span", {
      className: "kg-legend-dot",
      style: {
        background: kgTypeColor(c.node)
      }
    }), /*#__PURE__*/React.createElement("span", {
      className: "kg-pal-label"
    }, c.node.label), /*#__PURE__*/React.createElement("span", {
      className: "kg-pal-meta"
    }, c.scopeId !== scope.id ? KG_SCOPES[c.scopeId].crumb : (KG_TYPE[c.node.type] || {}).label || c.node.type))));
  }), /*#__PURE__*/React.createElement("div", {
    className: "kg-pal-foot"
  }, /*#__PURE__*/React.createElement("span", null, "\u2191\u2193 to move \xB7 \u21B5 to open \xB7 esc to close"), /*#__PURE__*/React.createElement("span", null, "searches everything \xB7 enriched by the graph"))));
}

// ── The slide-over detail drawer ────────────────────────────────────────────
function KgDetailDrawer({
  scope,
  nodeId,
  pinned,
  onPin,
  onSelect,
  onNavigate,
  onClose
}) {
  const node = scope.nodes.find(n => n.id === nodeId);
  if (!node) return null;
  const isPinned = pinned.some(p => p.scopeId === scope.id && p.nodeId === nodeId);
  return /*#__PURE__*/React.createElement("div", {
    className: "kg-drawer",
    "data-screen-label": "Node detail"
  }, /*#__PURE__*/React.createElement("div", {
    className: "kg-drawer-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-detail-breadcrumb"
  }, kgPath(scope.id).map(s => s.crumb).join(" / ")), /*#__PURE__*/React.createElement("div", {
    className: "kg-drawer-actions"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "kg-iconbtn" + (isPinned ? " is-on" : ""),
    title: isPinned ? "Unpin" : "Pin",
    onClick: () => onPin(scope.id, nodeId)
  }, /*#__PURE__*/React.createElement(IcPin, {
    size: 15
  })), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "kg-iconbtn",
    title: "Close",
    onClick: onClose
  }, /*#__PURE__*/React.createElement(IcX, {
    size: 15
  })))), /*#__PURE__*/React.createElement("div", {
    className: "kg-drawer-body"
  }, /*#__PURE__*/React.createElement(KgInspector, {
    node: node,
    scope: scope,
    onSelect: onSelect,
    big: true
  }), /*#__PURE__*/React.createElement("div", {
    className: "kg-ent-sec"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label"
  }, "neighbourhood"), /*#__PURE__*/React.createElement("div", {
    className: "kg-mini-wrap"
  }, /*#__PURE__*/React.createElement(KgMiniGraph, {
    scope: scope,
    centerId: nodeId,
    onPick: onSelect,
    w: 300,
    h: 190
  })))));
}

// ── List / table view ───────────────────────────────────────────────────────
function KgListView({
  scope,
  selectedId,
  onSelect,
  onNavigate,
  query,
  typeFilter
}) {
  const q = (query || "").trim().toLowerCase();
  const rows = scope.nodes.filter(n => {
    const cat = kgCategory(n);
    if (typeFilter && typeFilter.size && !typeFilter.has(cat)) return false;
    if (q && !(n.label + " " + (n.claim || "") + " " + n.type).toLowerCase().includes(q)) return false;
    return true;
  });
  const rel = n => scope.nodes.filter(m => (m.related || []).includes(n.id) || (n.related || []).includes(m.id)).length;
  return /*#__PURE__*/React.createElement("div", {
    className: "kg-list"
  }, /*#__PURE__*/React.createElement("div", {
    className: "kg-list-head"
  }, /*#__PURE__*/React.createElement("span", null, "Entity"), /*#__PURE__*/React.createElement("span", null, "Kind"), /*#__PURE__*/React.createElement("span", null, "Nous"), /*#__PURE__*/React.createElement("span", null, "Links")), /*#__PURE__*/React.createElement("div", {
    className: "kg-list-rows"
  }, rows.map(n => {
    const total = n.score ? n.score[0] + n.score[1] + n.score[2] : null;
    return /*#__PURE__*/React.createElement("button", {
      type: "button",
      key: n.id,
      className: "kg-list-row" + (n.id === selectedId ? " is-sel" : ""),
      onClick: () => n.scopeRef ? onNavigate(n.scopeRef) : onSelect(n.id)
    }, /*#__PURE__*/React.createElement("span", {
      className: "kg-list-name"
    }, /*#__PURE__*/React.createElement("span", {
      className: "kg-legend-dot",
      style: {
        background: kgTypeColor(n)
      }
    }), n.label, n.live && /*#__PURE__*/React.createElement("span", {
      className: "mcc-dot-tide",
      style: {
        width: 10,
        height: 10,
        marginLeft: 2
      }
    })), /*#__PURE__*/React.createElement("span", {
      className: "kg-list-kind"
    }, n.scopeRef ? "folder ›" : (KG_TYPE[n.type] || {}).label || n.type), /*#__PURE__*/React.createElement("span", {
      className: "kg-list-score"
    }, total != null ? /*#__PURE__*/React.createElement("span", {
      className: "kg-list-pip",
      "data-v": total >= 7 ? "hi" : total >= 3 ? "mid" : "lo"
    }, total) : "—"), /*#__PURE__*/React.createElement("span", {
      className: "kg-list-links"
    }, rel(n)));
  })));
}

// ── Right rail · recently viewed · pinned · what's new ──────────────────────
function KgRailItem({
  scopeId,
  nodeId,
  meta,
  onPick,
  onUnpin
}) {
  const sc = KG_SCOPES[scopeId];
  const n = sc && sc.nodes.find(x => x.id === nodeId);
  if (!n) return null;
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "kg-rail-item",
    onClick: () => onPick(scopeId, nodeId)
  }, /*#__PURE__*/React.createElement("span", {
    className: "kg-legend-dot",
    style: {
      background: kgTypeColor(n)
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "kg-rail-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "kg-rail-label"
  }, n.label), /*#__PURE__*/React.createElement("span", {
    className: "kg-rail-sub"
  }, sc.crumb, " \xB7 ", meta || (KG_TYPE[n.type] || {}).label || n.type)), onUnpin && /*#__PURE__*/React.createElement("span", {
    className: "kg-iconbtn kg-rail-pin",
    onClick: e => {
      e.stopPropagation();
      onUnpin(scopeId, nodeId);
    },
    title: "Unpin"
  }, /*#__PURE__*/React.createElement(IcPin, {
    size: 13
  })));
}
function KgRail({
  recent,
  pinned,
  onPick,
  onUnpin
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "kg-rail"
  }, pinned.length > 0 && /*#__PURE__*/React.createElement("div", {
    className: "kg-rail-sec"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label"
  }, /*#__PURE__*/React.createElement(IcPin, {
    size: 12
  }), " Pinned"), pinned.map(p => /*#__PURE__*/React.createElement(KgRailItem, _extends({
    key: p.scopeId + p.nodeId
  }, p, {
    onPick: onPick,
    onUnpin: onUnpin
  })))), /*#__PURE__*/React.createElement("div", {
    className: "kg-rail-sec"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label"
  }, "Recently viewed"), recent.length === 0 ? /*#__PURE__*/React.createElement("p", {
    className: "kg-rail-empty"
  }, "Open an entity and it lands here.") : recent.map(p => /*#__PURE__*/React.createElement(KgRailItem, _extends({
    key: p.scopeId + p.nodeId
  }, p, {
    onPick: onPick
  })))), /*#__PURE__*/React.createElement("div", {
    className: "kg-rail-sec"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label"
  }, "What's new ", /*#__PURE__*/React.createElement("span", {
    className: "kg-rail-count"
  }, "freshly bookkept")), KG_FRESH.map(f => /*#__PURE__*/React.createElement(KgRailItem, {
    key: f.scopeId + f.nodeId,
    scopeId: f.scopeId,
    nodeId: f.nodeId,
    meta: f.when + " ago",
    onPick: onPick
  }))));
}

// ── The page ────────────────────────────────────────────────────────────────
function MccKnowledge({
  onOpenView,
  theme,
  onToggleTheme
}) {
  const noop = () => {};
  const [scopeId, setScopeId] = React.useState("broomva");
  const [sel, setSel] = React.useState(null);
  const [drawer, setDrawer] = React.useState(false);
  const [q, setQ] = React.useState("");
  const [view, setView] = React.useState("graph");
  const [filter, setFilter] = React.useState(new Set());
  const [recent, setRecent] = React.useState([]);
  const [pinned, setPinned] = React.useState([{
    scopeId: "broomva",
    nodeId: "p6"
  }]);
  const [ask, setAsk] = React.useState(null);
  const scope = KG_SCOPES[scopeId];
  const path = kgPath(scopeId);
  const cats = React.useMemo(() => {
    const s = new Set(scope.nodes.map(kgCategory));
    return ["folder", "concept", "decision", "primitive", "tool", "person", "paper", "doc", "session", "pattern"].filter(c => s.has(c));
  }, [scope]);
  const navigate = id => {
    if (typeof id === "string" && id.indexOf("__page:") === 0) {
      onOpenView && onOpenView(id.slice(7));
      return;
    }
    if (!KG_SCOPES[id]) return;
    setScopeId(id);
    setSel(null);
    setDrawer(false);
    setAsk(null);
  };
  const pushRecent = (sid, nid) => setRecent(r => [{
    scopeId: sid,
    nodeId: nid
  }, ...r.filter(x => !(x.scopeId === sid && x.nodeId === nid))].slice(0, 6));
  const selectNode = nid => {
    setSel(nid);
    setDrawer(true);
    setAsk(null);
    pushRecent(scopeId, nid);
  };
  const pickEntity = (sid, nid) => {
    if (sid !== scopeId) {
      setScopeId(sid);
    }
    setSel(nid);
    setDrawer(true);
    setAsk(null);
    pushRecent(sid, nid);
  };
  const togglePin = (sid, nid) => setPinned(p => p.some(x => x.scopeId === sid && x.nodeId === nid) ? p.filter(x => !(x.scopeId === sid && x.nodeId === nid)) : [...p, {
    scopeId: sid,
    nodeId: nid
  }]);
  const toggleCat = c => setFilter(f => {
    const n = new Set(f);
    n.has(c) ? n.delete(c) : n.add(c);
    return n;
  });
  const doAsk = text => {
    setQ(text);
    const hits = scope.nodes.filter(n => !n.scopeRef && (n.label + " " + n.claim).toLowerCase().includes(text.toLowerCase())).slice(0, 4);
    setAsk({
      text,
      hits: hits.map(h => h.id)
    });
    setSel(null);
    setDrawer(false);
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-fill"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-app",
    style: {
      gridTemplateColumns: bvNavGrid()
    }
  }, /*#__PURE__*/React.createElement(BvNavTree, {
    active: "knowledge",
    inApp: true,
    onNav: onOpenView,
    renderTree: () => /*#__PURE__*/React.createElement(KnowTree, {
      activeId: scopeId,
      onNav: navigate
    })
  }), /*#__PURE__*/React.createElement("div", {
    className: "bv-main"
  }, /*#__PURE__*/React.createElement(McvTopBar, {
    theme: theme,
    onToggleTheme: onToggleTheme || noop,
    onOpenMaestro: () => onOpenView && onOpenView("app"),
    onWake: noop,
    waking: false,
    canWake: true,
    onShowIdea: noop,
    counts: {
      needYou: 1,
      stuck: 1
    },
    workers: ["claude", "bookkeeper"],
    wakes: MCC_TICK_WAKES,
    items: WK_ITEMS,
    onAttention: () => onOpenView && onOpenView("app"),
    onCommand: () => window.dispatchEvent(new CustomEvent("bv:command-open"))
  }), /*#__PURE__*/React.createElement("div", {
    className: "kg-page",
    "data-screen-label": "Knowledge graph"
  }, /*#__PURE__*/React.createElement("div", {
    className: "kg-bar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "kg-path"
  }, path.map((s, i) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: s.id
  }, i > 0 && /*#__PURE__*/React.createElement("span", {
    className: "kg-crumb-sep"
  }, "\u203A"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "kg-crumb-btn" + (s.id === scopeId ? " is-active" : ""),
    onClick: () => navigate(s.id)
  }, s.crumb))), /*#__PURE__*/React.createElement("span", {
    className: "kg-scopekind"
  }, scope.kind, " \xB7 ", scope.nodes.length)), /*#__PURE__*/React.createElement("div", {
    className: "kg-bar-right"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-seg kg-viewtoggle"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-seg-btn" + (view === "graph" ? " is-active" : ""),
    onClick: () => setView("graph")
  }, /*#__PURE__*/React.createElement(IcGraph, {
    size: 13
  }), "Graph"), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-seg-btn" + (view === "list" ? " is-active" : ""),
    onClick: () => setView("list")
  }, /*#__PURE__*/React.createElement(IcList, {
    size: 13
  }), "List")))), /*#__PURE__*/React.createElement("div", {
    className: "kg-body"
  }, /*#__PURE__*/React.createElement("div", {
    className: "kg-main"
  }, /*#__PURE__*/React.createElement("div", {
    className: "kg-chips"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "kg-chip" + (filter.size === 0 ? " is-active" : ""),
    onClick: () => setFilter(new Set())
  }, "All"), cats.map(c => /*#__PURE__*/React.createElement("button", {
    type: "button",
    key: c,
    className: "kg-chip" + (filter.has(c) ? " is-active" : ""),
    onClick: () => toggleCat(c)
  }, /*#__PURE__*/React.createElement("span", {
    className: "kg-legend-dot",
    style: {
      background: c === "folder" ? KG_GOLD : (KG_TYPE[c] || {}).color
    }
  }), c === "folder" ? "folders" : (KG_TYPE[c] || {}).label || c))), /*#__PURE__*/React.createElement("div", {
    className: "kg-graphwrap"
  }, view === "graph" ? /*#__PURE__*/React.createElement(KgGraph, {
    scope: scope,
    scopes: KG_SCOPES,
    selectedId: sel,
    onSelectNode: selectNode,
    onNavigate: navigate,
    query: ask ? ask.text : q,
    typeFilter: filter,
    width: 820,
    height: 660
  }) : /*#__PURE__*/React.createElement(KgListView, {
    scope: scope,
    selectedId: sel,
    onSelect: selectNode,
    onNavigate: navigate,
    query: q,
    typeFilter: filter
  }), drawer && /*#__PURE__*/React.createElement(KgDetailDrawer, {
    scope: scope,
    nodeId: sel,
    pinned: pinned,
    onPin: togglePin,
    onSelect: selectNode,
    onNavigate: navigate,
    onClose: () => {
      setDrawer(false);
      setSel(null);
    }
  }))), /*#__PURE__*/React.createElement("div", {
    className: "kg-panel"
  }, ask ? /*#__PURE__*/React.createElement(KgAskPanel, {
    ask: ask,
    scope: scope,
    onPick: selectNode,
    onClose: () => {
      setAsk(null);
      setQ("");
    }
  }) : /*#__PURE__*/React.createElement(KgRail, {
    recent: recent,
    pinned: pinned,
    onPick: pickEntity,
    onUnpin: togglePin
  })))))));
}

// answer card for "ask the graph"
function KgAskPanel({
  ask,
  scope,
  onPick,
  onClose
}) {
  const hits = ask.hits.map(id => scope.nodes.find(n => n.id === id)).filter(Boolean);
  return /*#__PURE__*/React.createElement("div", {
    className: "kg-ask"
  }, /*#__PURE__*/React.createElement("div", {
    className: "kg-ask-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "kg-ask-q"
  }, /*#__PURE__*/React.createElement(IcGraph, {
    size: 14
  }), " ", ask.text), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "kg-iconbtn",
    onClick: onClose
  }, /*#__PURE__*/React.createElement(IcX, {
    size: 14
  }))), /*#__PURE__*/React.createElement("p", {
    className: "kg-ask-answer"
  }, hits.length ? /*#__PURE__*/React.createElement(React.Fragment, null, "The graph surfaces ", /*#__PURE__*/React.createElement("b", null, hits.length), " ", hits.length === 1 ? "entity" : "entities", " in ", /*#__PURE__*/React.createElement("b", null, scope.crumb), " that bear on this \xB7 highlighted on the canvas, cited below.") : /*#__PURE__*/React.createElement(React.Fragment, null, "Nothing in ", /*#__PURE__*/React.createElement("b", null, scope.crumb), " matches yet. Try a parent scope, or rephrase.")), /*#__PURE__*/React.createElement("div", {
    className: "kg-ask-cites"
  }, hits.map(n => /*#__PURE__*/React.createElement("button", {
    type: "button",
    key: n.id,
    className: "kg-back",
    onClick: () => onPick(n.id)
  }, /*#__PURE__*/React.createElement("span", {
    className: "kg-legend-dot",
    style: {
      background: kgTypeColor(n)
    }
  }), n.label))), /*#__PURE__*/React.createElement("p", {
    className: "kg-ask-foot"
  }, "An answer is a retrieval, not a guess \xB7 every claim cites the entity it came from (P6)."));
}
Object.assign(window, {
  MccKnowledge,
  BvKgSearch,
  KgDetailDrawer,
  KgListView,
  KgRail,
  KgAskPanel,
  KG_FRESH,
  KG_NAV_PAGES
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/KnowledgeApp.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/LiveCommand.jsx
try { (() => {
// Live ⌘K command palette (V3). Opens over the real app, anchored under the
// top-bar command field, type-to-filter, full keyboard nav, and the jump-to
// rows actually navigate (History / Knowledge / Settings / Account / Feedback).
// On-standard glass via command.css. Uses the global McIcon (from WorkData).

const Ck = {
  search: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
    cx: "11",
    cy: "11",
    r: "7"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m21 21-4.3-4.3"
  })),
  clock: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "9"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 7v5l3 2"
  })),
  doc: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
    d: "M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M14 3v5h5M9 13h6M9 17h4"
  })),
  code: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
    d: "m9 9-3 3 3 3M15 9l3 3-3 3M13 7l-2 10"
  })),
  run: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "9"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m10 9 5 3-5 3Z"
  })),
  folder: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
    d: "M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"
  })),
  spark: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
    d: "M12 3v4M12 17v4M3 12h4M17 12h4M6 6l2.5 2.5M15.5 15.5 18 18M18 6l-2.5 2.5M8.5 15.5 6 18"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "2.4"
  })),
  wake: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
    d: "M13 2 4.5 13H11l-1 9 8.5-11H12Z"
  })),
  gate: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
    d: "M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m9 12 2 2 4-4"
  })),
  person: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "8",
    r: "4"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M5 21a7 7 0 0 1 14 0"
  })),
  history: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
    d: "M3 12a9 9 0 1 0 3-6.7L3 8"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M3 3v5h5M12 7v5l4 2"
  })),
  book: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
    d: "M4 19V5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2Z"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M19 17H6a2 2 0 0 0-2 2"
  })),
  settings: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
    cx: "12",
    cy: "12",
    r: "3"
  }), /*#__PURE__*/React.createElement("path", {
    d: "M12 2v3M12 19v3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M2 12h3M19 12h3M4.9 19.1l2.1-2.1M17 7l2.1-2.1"
  })),
  msg: p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
    d: "M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2Z"
  }))
};

// ── Data (illustrative, on-product) ───────────────────────────────────────
const CMDK_RECENT_SEARCHES = ["relay protocol handoff", "NDJSON phase machine", "linear missing scope"];
const CMDK_ARTIFACTS = [{
  id: "a1",
  title: "relay-protocol.md",
  meta: "hawthorne-core · spec · 12m ago",
  icon: "doc"
}, {
  id: "a2",
  title: "run/7c2f1a",
  meta: "judged clean · 14 tests · at your gate",
  icon: "run",
  state: "done"
}, {
  id: "a3",
  title: "projection.ts",
  meta: "genesis / projection · live session",
  icon: "code",
  state: "live"
}, {
  id: "a4",
  title: "api-decisions.md",
  meta: "hawthorne-core · doc",
  icon: "doc"
}];
const CMDK_COMMANDS = [{
  id: "c1",
  title: "Start a session…",
  meta: "dispatch work on the current folder",
  icon: "spark",
  kbd: "S",
  accent: true
}, {
  id: "c2",
  title: "Wake maestro now",
  meta: "run the next tick early",
  icon: "wake",
  kbd: "W"
}, {
  id: "c3",
  title: "Approve at the gate",
  meta: "1 run waiting on you",
  icon: "gate"
}, {
  id: "c4",
  title: "New spec / brief",
  meta: "write work for the loop to pick up",
  icon: "doc",
  kbd: "N"
}];
const CMDK_JUMP = [{
  id: "j1",
  title: "History",
  meta: "312 sessions",
  icon: "history",
  nav: "history"
}, {
  id: "j2",
  title: "Knowledge",
  meta: "the loop's memory",
  icon: "book",
  nav: "knowledge"
}, {
  id: "j3",
  title: "Settings",
  meta: "the engine room",
  icon: "settings",
  nav: "settings"
}, {
  id: "j4",
  title: "Account · Ana Diaz",
  meta: "your autonomy score",
  icon: "person",
  nav: "user"
}, {
  id: "j5",
  title: "Feedback",
  meta: "hand it to the loop",
  icon: "msg",
  nav: "feedback"
}];

// Contextual primaries · what ⌘K searches FIRST depends on where you are.
const CMDK_HISTORY = [{
  id: "h1",
  title: "Persist run transcripts on the Run record",
  meta: "hawthorne-core · 12m ago · judged clean",
  icon: "run",
  state: "done"
}, {
  id: "h2",
  title: "Reduce the NDJSON stream to a phase machine",
  meta: "genesis / projection · running now",
  icon: "run",
  state: "live"
}, {
  id: "h3",
  title: "Import Linear cycles into the object model",
  meta: "hawthorne-db · stuck · missing scope",
  icon: "run"
}, {
  id: "h4",
  title: "Reconcile May invoices",
  meta: "bookkeeping · 2h ago",
  icon: "run",
  state: "done"
}, {
  id: "h5",
  title: "Draft the relay protocol handoff",
  meta: "you · yesterday",
  icon: "run",
  state: "done"
}];
const CMDK_GRAPH = [{
  id: "g1",
  title: "relay protocol",
  meta: "concept · 6 links · genesis",
  icon: "spark"
}, {
  id: "g2",
  title: "NDJSON phase machine",
  meta: "pattern · 4 links",
  icon: "code"
}, {
  id: "g3",
  title: "Run record",
  meta: "primitive · 9 links",
  icon: "doc"
}, {
  id: "g4",
  title: "the conversation bridge",
  meta: "tool · writes to Obsidian",
  icon: "folder"
}, {
  id: "g5",
  title: "hawthorne-core",
  meta: "folder node · 12 inside",
  icon: "folder"
}];

// context id → primary dataset + the language it searches in.
const CMDK_PRIMARY = {
  history: {
    noun: "history",
    recentLabel: "Recent in history",
    hitLabel: "Sessions",
    scopeMeta: "all 312 sessions",
    data: CMDK_HISTORY
  },
  knowledge: {
    noun: "the graph",
    recentLabel: "In the knowledge graph",
    hitLabel: "Nodes",
    scopeMeta: "every node",
    data: CMDK_GRAPH
  }
};
const CMDK_PLACEHOLDER = {
  history: "Search history…",
  knowledge: "Search the knowledge graph…",
  app: "Ask, find, or start work…"
};

// Highlight the matched substring
function ckMark(text, q) {
  if (!q) return text;
  const i = text.toLowerCase().indexOf(q.toLowerCase());
  if (i < 0) return text;
  return /*#__PURE__*/React.createElement(React.Fragment, null, text.slice(0, i), /*#__PURE__*/React.createElement("em", null, text.slice(i, i + q.length)), text.slice(i + q.length));
}
function ckHit(item, q) {
  return (item.title + " " + (item.meta || "")).toLowerCase().includes(q.toLowerCase());
}
function CkDot({
  state
}) {
  if (state === "live") return /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 11,
      height: 11
    }
  });
  if (state === "done") return /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      width: 8,
      height: 8,
      background: "var(--bv-success)"
    }
  });
  return null;
}
function MccCommandPalette({
  open,
  onClose,
  onNav,
  context = "app"
}) {
  const [q, setQ] = React.useState("");
  const [active, setActive] = React.useState(0);
  const [rect, setRect] = React.useState(null);
  const inputRef = React.useRef(null);

  // Position under the real command field; fall back to top-center if the
  // current page has no command field mounted (e.g. config pages).
  const place = React.useCallback(() => {
    const anchor = document.querySelector("[data-cmdk-anchor]");
    if (anchor) {
      const r = anchor.getBoundingClientRect();
      const width = Math.max(r.width, 440);
      let left = r.left + (r.width - width) / 2;
      left = Math.max(10, Math.min(left, window.innerWidth - width - 10));
      setRect({
        left,
        top: r.bottom + 6,
        width
      });
    } else {
      const width = 480;
      setRect({
        left: (window.innerWidth - width) / 2,
        top: 66,
        width
      });
    }
  }, []);
  React.useEffect(() => {
    if (!open) return;
    setQ("");
    setActive(0);
    place();
    const t = setTimeout(() => inputRef.current && inputRef.current.focus(), 50);
    const onResize = () => place();
    window.addEventListener("resize", onResize, true);
    window.addEventListener("scroll", onResize, true);
    return () => {
      clearTimeout(t);
      window.removeEventListener("resize", onResize, true);
      window.removeEventListener("scroll", onResize, true);
    };
  }, [open, place]);

  // Build the grouped, filtered model · contextual: the page you're on
  // decides what ⌘K searches first.
  const groups = React.useMemo(() => {
    const query = q.trim();
    const prim = CMDK_PRIMARY[context];
    const g = [];
    if (query) {
      const leadTitle = prim ? /*#__PURE__*/React.createElement("span", null, "Search \u201C", /*#__PURE__*/React.createElement("em", null, query), "\u201D in ", prim.noun) : /*#__PURE__*/React.createElement("span", null, "Search \u201C", /*#__PURE__*/React.createElement("em", null, query), "\u201D across all folders");
      g.push({
        label: prim ? "Find in " + prim.noun : "Find in workspace",
        items: [{
          id: "find",
          title: leadTitle,
          meta: prim ? prim.scopeMeta : "everywhere",
          icon: "search",
          accent: true,
          kind: "find"
        }]
      });
      if (prim) {
        const hits = prim.data.filter(it => ckHit(it, query));
        if (hits.length) g.push({
          label: prim.hitLabel,
          items: hits.map(it => ({
            ...it,
            kind: "ctx",
            titleNode: ckMark(it.title, query)
          }))
        });
      }
      const arts = CMDK_ARTIFACTS.filter(it => ckHit(it, query));
      if (arts.length) g.push({
        label: "Artifacts",
        items: arts.map(it => ({
          ...it,
          kind: "artifact",
          titleNode: ckMark(it.title, query)
        }))
      });
      if (context === "app") {
        const cmds = CMDK_COMMANDS.filter(it => ckHit(it, query));
        if (cmds.length) g.push({
          label: "Commands",
          items: cmds.map(it => ({
            ...it,
            kind: "command",
            titleNode: ckMark(it.title, query)
          }))
        });
      }
      const jumps = CMDK_JUMP.filter(it => ckHit(it, query));
      if (jumps.length) g.push({
        label: "Jump to",
        items: jumps.map(it => ({
          ...it,
          kind: "nav",
          titleNode: ckMark(it.title, query)
        }))
      });
    } else if (prim) {
      g.push({
        label: prim.recentLabel,
        items: prim.data.map(it => ({
          ...it,
          kind: "ctx"
        }))
      });
      g.push({
        label: "Recent searches",
        items: CMDK_RECENT_SEARCHES.map((s, i) => ({
          id: "rs" + i,
          title: s,
          icon: "clock",
          kind: "search"
        }))
      });
      g.push({
        label: "Jump to",
        items: CMDK_JUMP.map(it => ({
          ...it,
          kind: "nav"
        }))
      });
    } else {
      g.push({
        label: "Recent searches",
        items: CMDK_RECENT_SEARCHES.map((s, i) => ({
          id: "rs" + i,
          title: s,
          icon: "clock",
          kind: "search"
        }))
      });
      g.push({
        label: "Recent artifacts",
        items: CMDK_ARTIFACTS.map(it => ({
          ...it,
          kind: "artifact"
        }))
      });
      g.push({
        label: "Commands",
        items: CMDK_COMMANDS.map(it => ({
          ...it,
          kind: "command"
        }))
      });
      g.push({
        label: "Jump to",
        items: CMDK_JUMP.map(it => ({
          ...it,
          kind: "nav"
        }))
      });
    }
    return g;
  }, [q, context]);
  const flat = React.useMemo(() => groups.flatMap(g => g.items), [groups]);
  React.useEffect(() => {
    setActive(a => Math.min(a, Math.max(0, flat.length - 1)));
  }, [flat.length]);
  if (!open) return null;
  const choose = it => {
    if (!it) return;
    if (it.kind === "search") {
      setQ(it.title);
      setActive(0);
      inputRef.current && inputRef.current.focus();
      return;
    }
    if (it.kind === "nav") {
      onClose && onClose();
      onNav && onNav(it.nav);
      return;
    }
    // find / artifact / command · illustrative: just close.
    onClose && onClose();
  };
  const onKey = e => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setActive(a => Math.min(a + 1, flat.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setActive(a => Math.max(a - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      choose(flat[active]);
    } else if (e.key === "Escape") {
      e.preventDefault();
      onClose && onClose();
    }
  };
  let idx = -1;
  const combo = /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "cmdk-scrim",
    onMouseDown: onClose
  }), /*#__PURE__*/React.createElement("div", {
    className: "cmdk-combo",
    style: rect ? {
      left: rect.left,
      top: rect.top,
      width: rect.width
    } : {
      left: -9999,
      top: 0
    },
    role: "dialog",
    "aria-modal": "true",
    "aria-label": "Command palette"
  }, /*#__PURE__*/React.createElement("div", {
    className: "cmdk-input-row"
  }, /*#__PURE__*/React.createElement(Ck.search, {
    size: 17
  }), /*#__PURE__*/React.createElement("input", {
    ref: inputRef,
    className: "cmdk-input",
    placeholder: CMDK_PLACEHOLDER[context] || CMDK_PLACEHOLDER.app,
    value: q,
    onChange: e => {
      setQ(e.target.value);
      setActive(0);
    },
    onKeyDown: onKey
  }), /*#__PURE__*/React.createElement("span", {
    className: "cmdk-esc"
  }, "esc")), /*#__PURE__*/React.createElement("div", {
    className: "cmdk-results"
  }, flat.length === 0 && /*#__PURE__*/React.createElement("div", {
    className: "cmdk-empty"
  }, "No matches. Press \u21B5 to search everywhere."), groups.map(grp => /*#__PURE__*/React.createElement(React.Fragment, {
    key: grp.label
  }, /*#__PURE__*/React.createElement("div", {
    className: "cmdk-group-label"
  }, grp.label), grp.items.map(it => {
    idx += 1;
    const me = idx;
    const Icon = Ck[it.icon] || Ck.search;
    return /*#__PURE__*/React.createElement("button", {
      key: it.id,
      type: "button",
      className: "cmdk-item" + (active === me ? " is-active" : ""),
      onMouseEnter: () => setActive(me),
      onClick: () => choose(it)
    }, /*#__PURE__*/React.createElement("span", {
      className: "cmdk-ic" + (it.accent ? " cmdk-ic--accent" : "")
    }, it.state ? /*#__PURE__*/React.createElement(CkDot, {
      state: it.state
    }) : /*#__PURE__*/React.createElement(Icon, null)), /*#__PURE__*/React.createElement("span", {
      className: "cmdk-item-body"
    }, /*#__PURE__*/React.createElement("span", {
      className: "cmdk-item-title"
    }, it.titleNode || it.title), it.meta && /*#__PURE__*/React.createElement("span", {
      className: "cmdk-item-meta"
    }, it.meta)), /*#__PURE__*/React.createElement("span", {
      className: "cmdk-item-right"
    }, it.kbd && /*#__PURE__*/React.createElement("span", {
      className: "cmdk-kbd"
    }, it.kbd), /*#__PURE__*/React.createElement("span", {
      className: "cmdk-enter"
    }, "\u21B5")));
  })))), /*#__PURE__*/React.createElement("div", {
    className: "cmdk-foot"
  }, /*#__PURE__*/React.createElement("span", {
    className: "cmdk-foot-hint"
  }, /*#__PURE__*/React.createElement("span", {
    className: "cmdk-foot-kbd"
  }, "\u2191\u2193"), " navigate"), /*#__PURE__*/React.createElement("span", {
    className: "cmdk-foot-hint"
  }, /*#__PURE__*/React.createElement("span", {
    className: "cmdk-foot-kbd"
  }, "\u21B5"), " open"), /*#__PURE__*/React.createElement("span", {
    className: "cmdk-foot-hint"
  }, /*#__PURE__*/React.createElement("span", {
    className: "cmdk-foot-kbd"
  }, "esc"), " close"), /*#__PURE__*/React.createElement("span", {
    className: "cmdk-foot-spacer"
  }), /*#__PURE__*/React.createElement("span", {
    className: "cmdk-foot-brand"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 9,
      height: 9
    }
  }), " maestro"))));
  return ReactDOM.createPortal(combo, document.body);
}
Object.assign(window, {
  MccCommandPalette
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/LiveCommand.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/MaestroApp.jsx
try { (() => {
// Maestro v4 · the maestro loop, promoted from the concepts canvas.
// One layout, two states: Maestro grows the plane (feed/board/list,
// chat docked right); clicking a workspace/folder collapses it to the dock
// and the conversation takes center. Tabs and the FS pane never move.
// All fixed columns drag to resize; the FS pane and dock yield responsively.

const MC4_TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "density": "calm",
  "blue": 1,
  "chatLen": "short",
  "rail": "quiet",
  "mobileNav": "sheet"
} /*EDITMODE-END*/;
function Mc4App() {
  const [t, setTweak] = useTweaks(MC4_TWEAK_DEFAULTS);
  const [theme, setTheme] = React.useState("light");
  const [view, setView] = React.useState("app"); // app | knowledge | history | settings | user
  const [feedbackOpen, setFeedbackOpen] = React.useState(false);
  const [cmdOpen, setCmdOpen] = React.useState(false);
  const vp = useBvViewport();
  const toggleTheme = () => setTheme(theme === "dark" ? "light" : "dark");
  const openView = id => {
    if (id === "feedback") {
      setFeedbackOpen(true);
      return;
    }
    setView(id === "knowledge" ? "knowledge" : id === "history" ? "history" : id === "settings" ? "settings" : id === "user" ? "user" : "app");
  };
  const FB_CONTEXT = {
    app: "Maestro",
    knowledge: "Knowledge",
    history: "History",
    settings: "Settings",
    user: "Ana Diaz"
  };

  // ⌘K is global; the shared command field (on every page) dispatches an event.
  React.useEffect(() => {
    const onKey = e => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) {
        e.preventDefault();
        setCmdOpen(v => !v);
      }
    };
    const onOpen = () => setCmdOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("bv:command-open", onOpen);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("bv:command-open", onOpen);
    };
  }, []);
  React.useEffect(() => {
    const el = document.documentElement;
    el.setAttribute("data-theme", theme);
    el.setAttribute("data-density", t.density);
    el.style.setProperty("--bv-blue-mult", String(t.blue));
    // Keep the PWA status-bar colour in step with the theme.
    const meta = document.querySelector('meta[name="theme-color"]:not([media])');
    if (meta) meta.setAttribute("content", theme === "dark" ? "#16151f" : "#ffffff");
  }, [theme, t.density, t.blue]);
  return /*#__PURE__*/React.createElement(React.Fragment, null, vp === "desktop" ? view === "knowledge" ? /*#__PURE__*/React.createElement(MccKnowledge, {
    onOpenView: openView,
    theme: theme,
    onToggleTheme: toggleTheme
  }) : view === "history" ? /*#__PURE__*/React.createElement(MccHistory, {
    onOpenView: openView,
    theme: theme,
    onToggleTheme: toggleTheme
  }) : view === "settings" ? /*#__PURE__*/React.createElement(MccSettings, {
    onOpenView: openView,
    theme: theme,
    onSetTheme: setTheme,
    density: t.density,
    onSetDensity: v => setTweak("density", v),
    blue: t.blue,
    onSetBlue: v => setTweak("blue", v)
  }) : view === "user" ? /*#__PURE__*/React.createElement(MccUser, {
    onOpenView: openView
  }) : /*#__PURE__*/React.createElement(MccMaestroLoopV2, {
    app: true,
    initialMode: "mission",
    theme: theme,
    onToggleTheme: toggleTheme,
    onOpenView: openView,
    chatLen: t.chatLen,
    rail: t.rail
  }) : /*#__PURE__*/React.createElement(MccMobileShell, {
    mode: vp,
    theme: theme,
    onToggleTheme: toggleTheme,
    nav: t.mobileNav,
    sheetTrigger: "icons"
  }), /*#__PURE__*/React.createElement(MccCommandPalette, {
    open: cmdOpen,
    onClose: () => setCmdOpen(false),
    onNav: openView,
    context: view
  }), /*#__PURE__*/React.createElement(MccFeedback, {
    open: feedbackOpen,
    onClose: () => setFeedbackOpen(false),
    context: FB_CONTEXT[view] || "Maestro"
  }), /*#__PURE__*/React.createElement(TweaksPanel, null, /*#__PURE__*/React.createElement(TweakSection, {
    label: "Layout"
  }), /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Density",
    value: t.density,
    options: ["calm", "dense"],
    onChange: v => setTweak("density", v)
  }), /*#__PURE__*/React.createElement(TweakSection, {
    label: "Conversation"
  }), /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Length",
    value: t.chatLen,
    options: ["short", "stress", "extreme"],
    onChange: v => setTweak("chatLen", v)
  }), /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Dispatch rail",
    value: t.rail,
    options: [{
      value: "quiet",
      label: "Quiet"
    }, {
      value: "full",
      label: "Full"
    }],
    onChange: v => setTweak("rail", v)
  }), /*#__PURE__*/React.createElement(TweakSection, {
    label: "Mobile nav"
  }), /*#__PURE__*/React.createElement(TweakRadio, {
    label: "Model",
    value: t.mobileNav,
    options: [{
      value: "sheet",
      label: "Sheets"
    }, {
      value: "page",
      label: "Pager"
    }, {
      value: "menu",
      label: "Menu"
    }, {
      value: "edge",
      label: "Edge"
    }],
    onChange: v => setTweak("mobileNav", v)
  }), /*#__PURE__*/React.createElement(TweakSection, {
    label: "Color"
  }), /*#__PURE__*/React.createElement(TweakSlider, {
    label: "Blue intensity",
    value: t.blue,
    min: 0,
    max: 2,
    step: 0.1,
    onChange: v => setTweak("blue", v)
  })));
}
ReactDOM.createRoot(document.getElementById("root")).render(/*#__PURE__*/React.createElement(Mc4App, null));
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/MaestroApp.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/MobileShell.jsx
try { (() => {
// Broomva Maestro · the mobile + tablet shell.
// Chat-first: the maestro conversation is the home surface, the gate queue
// rides above the prompt. Three primary surfaces · Chat · Mission · Files.
// The phone navigation *model* is selectable (`nav` prop / Tweaks panel). All
// keep the frosted-glass language; they differ in the underlying interaction:
//   · "page"  · surfaces are swipeable pages; a carousel indicator up top
//   · "sheet" · chat is the canvas; Mission & Files rise as pull-up sheets
//   · "menu"  · the header title is a "Chat ▾" popover switcher
//   · "edge"  · a slim vertical glass rail pinned to the right edge
// (legacy: "tray" / "top" / "orbit" kept for reference.)
// Tablets always use the right-edge side rail. The workspace tree is an
// off-canvas drawer. Reuses the desktop chat / plane / file components verbatim
// · only the chrome is phone-shaped.

const IcMlMenu = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M4 6h16"
}), /*#__PURE__*/React.createElement("path", {
  d: "M4 12h16"
}), /*#__PURE__*/React.createElement("path", {
  d: "M4 18h16"
}));
const IcMlBack = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "m12 19-7-7 7-7"
}), /*#__PURE__*/React.createElement("path", {
  d: "M19 12H5"
}));
const IcMlFiles = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"
}));
const IcMlChev = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "m6 9 6 6 6-6"
}));

// mobile (<768) · tablet (768–1023) · desktop (≥1024)
function useBvViewport() {
  const get = () => {
    if (typeof window === "undefined") return "desktop";
    // ?vp=mobile|tablet|desktop forces a layout (for previewing on a wide canvas).
    try {
      const f = new URLSearchParams(location.search).get("vp");
      if (f === "mobile" || f === "tablet" || f === "desktop") return f;
    } catch (e) {}
    const w = window.innerWidth;
    return w < 768 ? "mobile" : w < 1024 ? "tablet" : "desktop";
  };
  const [vp, setVp] = React.useState(get);
  React.useEffect(() => {
    let raf = 0;
    const onR = () => {
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => setVp(get()));
    };
    window.addEventListener("resize", onR);
    window.addEventListener("orientationchange", onR);
    return () => {
      window.removeEventListener("resize", onR);
      window.removeEventListener("orientationchange", onR);
      cancelAnimationFrame(raf);
    };
  }, []);
  return vp;
}

// The Files surface · the pane (browse) or a single doc (read).
function MccMobileFiles({
  fs,
  openFile,
  setOpenFile
}) {
  if (openFile) return /*#__PURE__*/React.createElement(MccFsDoc, {
    path: openFile
  });
  return /*#__PURE__*/React.createElement(MccFilePane, {
    entries: fs.entries(),
    label: fs.label,
    location: fs.location,
    worktree: fs.worktree,
    openPath: null,
    onOpen: setOpenFile
  });
}

// Files as a full pane · browse, or read one doc with a back affordance.
function MccFilesPane({
  fs,
  openFile,
  setOpenFile
}) {
  return /*#__PURE__*/React.createElement("section", {
    className: "bvm-pane bvm-pane--files",
    "data-screen-label": "Files (mobile)"
  }, openFile ? /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "bvm-panehead"
  }, /*#__PURE__*/React.createElement("button", {
    className: "bvm-iconbtn",
    type: "button",
    "aria-label": "Back to files",
    onClick: () => setOpenFile(null),
    style: {
      marginLeft: 0
    }
  }, /*#__PURE__*/React.createElement(IcMlBack, {
    size: 20
  })), /*#__PURE__*/React.createElement("span", {
    className: "bvm-panehead-title"
  }, openFile.split("/").pop())), /*#__PURE__*/React.createElement("div", {
    className: "bvm-pane-scroll"
  }, /*#__PURE__*/React.createElement(MccFsDoc, {
    path: openFile
  }))) : /*#__PURE__*/React.createElement(MccMobileFiles, {
    fs: fs,
    openFile: null,
    setOpenFile: setOpenFile
  }));
}
function MccMobileShell({
  mode = "mobile",
  theme = "light",
  onToggleTheme,
  nav = "page",
  sheetTrigger = "peek"
}) {
  const [tab, setTab] = React.useState("chat"); // chat | mission | files
  const [drawer, setDrawer] = React.useState(false);
  const [scope, setScope] = React.useState("root");
  const [openFile, setOpenFile] = React.useState(null);
  const [orbit, setOrbit] = React.useState(false); // legacy orbit switcher
  const [sheetSurf, setSheetSurf] = React.useState(null); // sheet model: null|mission|files
  const [menuOpen, setMenuOpen] = React.useState(false); // menu model popover
  const bodyRef = React.useRef(null);
  const pagerLock = React.useRef(false);
  const noop = () => {};
  const fs = MCC_ML_FS[scope] || MCC_ML_FS.root;
  const isTablet = mode === "tablet";
  // ?nav=… forces a model (preview without the panel), mirroring ?vp. Tablets
  // always use the right-edge side rail; the phone `nav` tweak governs phones.
  let navPref = nav;
  try {
    const f = new URLSearchParams(location.search).get("nav");
    if (["page", "sheet", "menu", "edge", "tray", "top", "orbit"].includes(f)) navPref = f;
  } catch (e) {}
  const navMode = isTablet ? "rail" : navPref;

  // Sheet-model trigger treatment (how Mission/Files are surfaced). Only used
  // when navMode === "sheet". ?strig= overrides for preview.
  let strig = sheetTrigger;
  try {
    const f = new URLSearchParams(location.search).get("strig");
    if (["peek", "dock", "edge", "icons"].includes(f)) strig = f;
  } catch (e) {}

  // The three primary surfaces · shared by every nav model.
  const surfaces = [{
    id: "chat",
    icon: /*#__PURE__*/React.createElement(IcChat, {
      size: 21
    }),
    label: "Chat",
    badge: "2"
  }, {
    id: "mission",
    icon: /*#__PURE__*/React.createElement(IcBoard, {
      size: 21
    }),
    label: "Mission"
  }, {
    id: "files",
    icon: /*#__PURE__*/React.createElement(IcMlFiles, {
      size: 21
    }),
    label: "Files"
  }];
  const dockIdx = Math.max(0, surfaces.findIndex(s => s.id === tab));
  const active = surfaces.find(s => s.id === tab) || surfaces[0];

  // The two surfaces that rise as sheets over the chat canvas.
  const sheetSurfaces = [{
    id: "mission",
    label: "Mission",
    icon: /*#__PURE__*/React.createElement(IcBoard, {
      size: 20
    }),
    count: "2",
    hint: "2 awaiting"
  }, {
    id: "files",
    label: "Files",
    icon: /*#__PURE__*/React.createElement(IcMlFiles, {
      size: 20
    }),
    count: null,
    hint: "~/Broomva"
  }];

  // Lock body scroll while a full overlay is open.
  React.useEffect(() => {
    const open = drawer || orbit || sheetSurf || menuOpen;
    document.body.style.overflow = open ? "hidden" : "";
    return () => {
      document.body.style.overflow = "";
    };
  }, [drawer, orbit, sheetSurf, menuOpen]);
  React.useEffect(() => {
    setOrbit(false);
    setMenuOpen(false);
  }, [tab]);

  // ── Pager model: keep horizontal scroll position synced with `tab` ──
  React.useEffect(() => {
    if (navMode !== "page") return;
    const el = bodyRef.current;
    if (!el) return;
    const i = surfaces.findIndex(s => s.id === tab);
    el.scrollLeft = i * el.clientWidth; // jump on mount / model switch
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [navMode]);
  React.useEffect(() => {
    if (navMode !== "page") return;
    if (pagerLock.current) {
      pagerLock.current = false;
      return;
    }
    const el = bodyRef.current;
    if (!el) return;
    const i = surfaces.findIndex(s => s.id === tab);
    el.scrollTo({
      left: i * el.clientWidth,
      behavior: "smooth"
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, navMode]);
  const onPagerScroll = () => {
    if (navMode !== "page") return;
    const el = bodyRef.current;
    if (!el) return;
    const i = Math.round(el.scrollLeft / el.clientWidth);
    const id = surfaces[i] && surfaces[i].id;
    if (id && id !== tab) {
      pagerLock.current = true;
      setTab(id);
    }
  };
  const goScope = s => {
    setScope(s);
    setOpenFile(null);
    setDrawer(false);
  };
  const goMission = () => {
    pick("mission");
    setDrawer(false);
  };

  // The one surface-selection entry point · behaves per model.
  function pick(id) {
    if (navMode === "sheet") {
      setSheetSurf(id === "chat" ? null : id);
      return;
    }
    setTab(id);
    setOrbit(false);
    setMenuOpen(false);
  }
  const sub = scope === "root" ? "~/Broomva · 2 live" : fs.location;
  const title = tab === "mission" ? "The plane" : tab === "files" ? "Files" : "Maestro";

  // Header center varies by model.
  let headerCenter;
  if (navMode === "top") {
    headerCenter = /*#__PURE__*/React.createElement("nav", {
      className: "bvm-topseg",
      role: "tablist",
      "aria-label": "Surface",
      style: {
        "--seg-idx": dockIdx,
        "--seg-n": surfaces.length
      }
    }, /*#__PURE__*/React.createElement("span", {
      className: "bvm-topseg-pill",
      "aria-hidden": "true"
    }), surfaces.map(s => /*#__PURE__*/React.createElement("button", {
      key: s.id,
      role: "tab",
      "aria-selected": tab === s.id,
      className: "bvm-topseg-btn" + (tab === s.id ? " is-active" : ""),
      type: "button",
      onClick: () => pick(s.id)
    }, /*#__PURE__*/React.createElement("span", {
      className: "bvm-topseg-ico"
    }, s.icon), /*#__PURE__*/React.createElement("span", {
      className: "bvm-topseg-lbl"
    }, s.label), s.badge && tab !== s.id ? /*#__PURE__*/React.createElement("span", {
      className: "bvm-topseg-badge"
    }, s.badge) : null)));
  } else if (navMode === "menu") {
    // Title becomes a dropdown switcher.
    headerCenter = /*#__PURE__*/React.createElement("button", {
      className: "bvm-titlebtn" + (menuOpen ? " is-open" : ""),
      type: "button",
      "aria-haspopup": "true",
      "aria-expanded": menuOpen,
      onClick: () => setMenuOpen(v => !v)
    }, /*#__PURE__*/React.createElement("span", {
      className: "bvm-titlebtn-ico"
    }, active.icon), /*#__PURE__*/React.createElement("span", {
      className: "bvm-titlebtn-txt"
    }, title), /*#__PURE__*/React.createElement("span", {
      className: "bvm-titlebtn-chev"
    }, /*#__PURE__*/React.createElement(IcMlChev, {
      size: 16
    })), tab !== "chat" ? /*#__PURE__*/React.createElement("span", {
      className: "bvm-titlebtn-badge"
    }, "2") : null);
  } else if (navMode === "sheet" && strig === "icons") {
    // Minimal: clean icon buttons live in the top-actions row (below); the
    // header center stays as the plain identity block.
    headerCenter = /*#__PURE__*/React.createElement("div", {
      className: "bvm-top-id"
    }, /*#__PURE__*/React.createElement("img", {
      className: "bvm-top-logo",
      src: "../../assets/broomva-blackhole-logo.png",
      alt: ""
    }), /*#__PURE__*/React.createElement("div", {
      className: "bvm-top-titles"
    }, /*#__PURE__*/React.createElement("span", {
      className: "bvm-top-title"
    }, title), /*#__PURE__*/React.createElement("span", {
      className: "bvm-top-sub"
    }, sub)));
  } else {
    headerCenter = /*#__PURE__*/React.createElement("div", {
      className: "bvm-top-id"
    }, /*#__PURE__*/React.createElement("img", {
      className: "bvm-top-logo",
      src: "../../assets/broomva-blackhole-logo.png",
      alt: ""
    }), /*#__PURE__*/React.createElement("div", {
      className: "bvm-top-titles"
    }, /*#__PURE__*/React.createElement("span", {
      className: "bvm-top-title"
    }, title), /*#__PURE__*/React.createElement("span", {
      className: "bvm-top-sub"
    }, sub)));
  }
  return /*#__PURE__*/React.createElement("div", {
    className: "bvm",
    "data-mode": mode,
    "data-tab": tab,
    "data-nav": navMode,
    "data-strig": strig,
    "data-drawer": drawer ? "open" : "shut",
    "data-orbit": orbit ? "open" : "shut",
    "data-sheet": sheetSurf ? "open" : "shut",
    "data-menu": menuOpen ? "open" : "shut"
  }, /*#__PURE__*/React.createElement("header", {
    className: "bvm-top",
    "data-screen-label": "Mobile top bar"
  }, /*#__PURE__*/React.createElement("button", {
    className: "bvm-iconbtn",
    type: "button",
    "aria-label": "Open workspace",
    onClick: () => setDrawer(true)
  }, /*#__PURE__*/React.createElement(IcMlMenu, {
    size: 21
  })), headerCenter, /*#__PURE__*/React.createElement("div", {
    className: "bvm-top-actions"
  }, navMode === "sheet" && strig === "icons" && /*#__PURE__*/React.createElement("div", {
    className: "bvm-sicons",
    role: "group",
    "aria-label": "Surfaces"
  }, sheetSurfaces.map(s => /*#__PURE__*/React.createElement("button", {
    key: s.id,
    type: "button",
    className: "bvm-iconbtn bvm-sicon" + (sheetSurf === s.id ? " is-active" : ""),
    "aria-label": "Open " + s.label,
    onClick: () => setSheetSurf(s.id)
  }, s.icon, s.count ? /*#__PURE__*/React.createElement("span", {
    className: "bvm-sicon-badge"
  }, s.count) : null)), /*#__PURE__*/React.createElement("span", {
    className: "bvm-sicons-div",
    "aria-hidden": "true"
  })), /*#__PURE__*/React.createElement("button", {
    className: "bvm-iconbtn",
    type: "button",
    "aria-label": "Toggle theme",
    onClick: onToggleTheme || noop
  }, theme === "dark" ? /*#__PURE__*/React.createElement(IcSun, {
    size: 19
  }) : /*#__PURE__*/React.createElement(IcMoon, {
    size: 19
  }))), navMode === "menu" && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "bvm-menu-scrim",
    onClick: () => setMenuOpen(false)
  }), /*#__PURE__*/React.createElement("div", {
    className: "bvm-navmenu",
    role: "menu"
  }, surfaces.map(s => /*#__PURE__*/React.createElement("button", {
    key: s.id,
    role: "menuitemradio",
    "aria-checked": tab === s.id,
    className: "bvm-navmenu-item" + (tab === s.id ? " is-active" : ""),
    type: "button",
    onClick: () => pick(s.id)
  }, /*#__PURE__*/React.createElement("span", {
    className: "bvm-navmenu-ico"
  }, s.icon), /*#__PURE__*/React.createElement("span", {
    className: "bvm-navmenu-lbl"
  }, s.label), s.badge && tab !== s.id ? /*#__PURE__*/React.createElement("span", {
    className: "bvm-navmenu-badge"
  }, s.badge) : null, tab === s.id ? /*#__PURE__*/React.createElement("span", {
    className: "bvm-navmenu-dot",
    "aria-hidden": "true"
  }) : null))))), navMode === "page" && /*#__PURE__*/React.createElement("div", {
    className: "bvm-pager",
    role: "tablist",
    "aria-label": "Surface"
  }, surfaces.map(s => /*#__PURE__*/React.createElement("button", {
    key: s.id,
    role: "tab",
    "aria-selected": tab === s.id,
    className: "bvm-pager-seg" + (tab === s.id ? " is-active" : ""),
    type: "button",
    onClick: () => pick(s.id)
  }, /*#__PURE__*/React.createElement("span", {
    className: "bvm-pager-ico"
  }, s.icon), /*#__PURE__*/React.createElement("span", {
    className: "bvm-pager-lbl"
  }, s.label), s.badge && tab !== s.id ? /*#__PURE__*/React.createElement("span", {
    className: "bvm-pager-badge"
  }, s.badge) : null))), /*#__PURE__*/React.createElement("div", {
    className: "bvm-body",
    ref: bodyRef,
    onScroll: onPagerScroll
  }, /*#__PURE__*/React.createElement("section", {
    className: "bvm-pane bvm-pane--chat",
    "data-screen-label": "Maestro (mobile)"
  }, /*#__PURE__*/React.createElement(MccMaestroChat, {
    layer: fs.layer
  })), /*#__PURE__*/React.createElement("section", {
    className: "bvm-pane bvm-pane--mission",
    "data-screen-label": "Mission plane (mobile)"
  }, /*#__PURE__*/React.createElement(MccMissionPlane, null)), /*#__PURE__*/React.createElement(MccFilesPane, {
    fs: fs,
    openFile: openFile,
    setOpenFile: setOpenFile
  })), navMode === "edge" && /*#__PURE__*/React.createElement("nav", {
    className: "bvm-edge",
    "data-screen-label": "Edge rail",
    style: {
      "--eidx": dockIdx,
      "--en": surfaces.length
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "bvm-edge-pill",
    "aria-hidden": "true"
  }), surfaces.map(s => /*#__PURE__*/React.createElement("button", {
    key: s.id,
    className: "bvm-edge-btn" + (tab === s.id ? " is-active" : ""),
    type: "button",
    "aria-label": s.label,
    onClick: () => pick(s.id)
  }, /*#__PURE__*/React.createElement("span", {
    className: "bvm-edge-ico"
  }, s.icon), s.badge && tab !== s.id ? /*#__PURE__*/React.createElement("span", {
    className: "bvm-edge-badge"
  }, s.badge) : null))), navMode === "sheet" && /*#__PURE__*/React.createElement(React.Fragment, null, strig === "peek" && /*#__PURE__*/React.createElement("div", {
    className: "bvm-peek",
    "data-screen-label": "Peek triggers"
  }, sheetSurfaces.map(s => /*#__PURE__*/React.createElement("button", {
    key: s.id,
    type: "button",
    className: "bvm-peek-card",
    onClick: () => setSheetSurf(s.id)
  }, /*#__PURE__*/React.createElement("span", {
    className: "bvm-peek-grab",
    "aria-hidden": "true"
  }), /*#__PURE__*/React.createElement("span", {
    className: "bvm-peek-ico"
  }, s.icon), /*#__PURE__*/React.createElement("span", {
    className: "bvm-peek-lbl"
  }, s.label), /*#__PURE__*/React.createElement("span", {
    className: "bvm-peek-hint"
  }, s.hint), s.count ? /*#__PURE__*/React.createElement("span", {
    className: "bvm-peek-badge"
  }, s.count) : null, /*#__PURE__*/React.createElement("span", {
    className: "bvm-peek-up"
  }, /*#__PURE__*/React.createElement(IcMlChev, {
    size: 15
  }))))), strig === "dock" && /*#__PURE__*/React.createElement("div", {
    className: "bvm-sdock",
    "data-screen-label": "Dock triggers"
  }, sheetSurfaces.map(s => /*#__PURE__*/React.createElement("button", {
    key: s.id,
    type: "button",
    className: "bvm-sdock-chip",
    onClick: () => setSheetSurf(s.id)
  }, /*#__PURE__*/React.createElement("span", {
    className: "bvm-sdock-ico"
  }, s.icon), /*#__PURE__*/React.createElement("span", {
    className: "bvm-sdock-lbl"
  }, s.label), s.count ? /*#__PURE__*/React.createElement("span", {
    className: "bvm-sdock-badge"
  }, s.count) : null))), strig === "edge" && /*#__PURE__*/React.createElement("div", {
    className: "bvm-stabs",
    "data-screen-label": "Edge pull-tabs"
  }, sheetSurfaces.map(s => /*#__PURE__*/React.createElement("button", {
    key: s.id,
    type: "button",
    className: "bvm-stab",
    onClick: () => setSheetSurf(s.id)
  }, /*#__PURE__*/React.createElement("span", {
    className: "bvm-stab-ico"
  }, s.icon), /*#__PURE__*/React.createElement("span", {
    className: "bvm-stab-lbl"
  }, s.label), s.count ? /*#__PURE__*/React.createElement("span", {
    className: "bvm-stab-badge"
  }, s.count) : null))), /*#__PURE__*/React.createElement("div", {
    className: "bvm-sheet-scrim",
    onClick: () => setSheetSurf(null)
  }), /*#__PURE__*/React.createElement("div", {
    className: "bvm-sheet",
    "data-screen-label": "Pull-up sheet"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bvm-sheet-grab",
    onClick: () => setSheetSurf(null)
  }, /*#__PURE__*/React.createElement("span", {
    className: "bvm-sheet-bar",
    "aria-hidden": "true"
  })), /*#__PURE__*/React.createElement("div", {
    className: "bvm-sheet-body"
  }, sheetSurf === "mission" && /*#__PURE__*/React.createElement(MccMissionPlane, null), sheetSurf === "files" && /*#__PURE__*/React.createElement(MccFilesPane, {
    fs: fs,
    openFile: openFile,
    setOpenFile: setOpenFile
  })))), (navMode === "tray" || navMode === "rail") && /*#__PURE__*/React.createElement("nav", {
    className: "bvm-dock",
    "data-screen-label": navMode === "rail" ? "Side rail" : "Bottom tray",
    style: {
      "--bvm-idx": dockIdx,
      "--bvm-n": surfaces.length
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "bvm-dock-glow",
    "aria-hidden": "true"
  }), /*#__PURE__*/React.createElement("span", {
    className: "bvm-dock-pill",
    "aria-hidden": "true"
  }), surfaces.map(s => /*#__PURE__*/React.createElement("button", {
    key: s.id,
    className: "bvm-tab" + (tab === s.id ? " is-active" : ""),
    type: "button",
    onClick: () => pick(s.id)
  }, /*#__PURE__*/React.createElement("span", {
    className: "bvm-tab-ico"
  }, s.icon), /*#__PURE__*/React.createElement("span", {
    className: "bvm-tab-lbl"
  }, s.label), s.badge ? /*#__PURE__*/React.createElement("span", {
    className: "bvm-tab-badge"
  }, s.badge) : null))), navMode === "orbit" && /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "bvm-orbit-scrim",
    onClick: () => setOrbit(false)
  }), /*#__PURE__*/React.createElement("div", {
    className: "bvm-orbit",
    "data-screen-label": "Orbit switcher"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bvm-orbit-stack"
  }, surfaces.map((s, i) => /*#__PURE__*/React.createElement("button", {
    key: s.id,
    className: "bvm-orbit-item" + (tab === s.id ? " is-active" : ""),
    type: "button",
    style: {
      "--oi": surfaces.length - 1 - i
    },
    onClick: () => pick(s.id)
  }, /*#__PURE__*/React.createElement("span", {
    className: "bvm-orbit-lbl"
  }, s.label), /*#__PURE__*/React.createElement("span", {
    className: "bvm-orbit-ico"
  }, s.icon), s.badge && tab !== s.id ? /*#__PURE__*/React.createElement("span", {
    className: "bvm-orbit-badge"
  }, s.badge) : null))), /*#__PURE__*/React.createElement("button", {
    className: "bvm-orbit-fab",
    type: "button",
    "aria-label": orbit ? "Close switcher" : "Switch surface",
    "aria-expanded": orbit,
    onClick: () => setOrbit(v => !v)
  }, /*#__PURE__*/React.createElement("span", {
    className: "bvm-orbit-fab-ico"
  }, orbit ? /*#__PURE__*/React.createElement(IcX, {
    size: 22
  }) : active.icon), !orbit && tab !== "chat" ? /*#__PURE__*/React.createElement("span", {
    className: "bvm-tab-badge"
  }, "2") : null))), /*#__PURE__*/React.createElement("div", {
    className: "bvm-scrim",
    onClick: () => setDrawer(false)
  }), /*#__PURE__*/React.createElement("aside", {
    className: "bvm-drawer",
    "data-screen-label": "Workspace drawer"
  }, /*#__PURE__*/React.createElement(MccTcSidebar, {
    scope: tab === "mission" ? "__none" : scope,
    setScope: goScope,
    onMission: goMission,
    missionActive: tab === "mission"
  })));
}
Object.assign(window, {
  useBvViewport,
  MccMobileShell
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/MobileShell.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/PromptPlate.jsx
try { (() => {
// The prompt plate · Broomva's composer, promoted from the concepts canvas (P2).
// Two storeys: text on top with the ⌘L hint, a rail of dispatch context
// beneath. Glass is earned by the composer, so the plate keeps the
// frosted-blue halo. Shared by the v3 app and the concepts canvas.

const IcxPlus = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M5 12h14"
}), /*#__PURE__*/React.createElement("path", {
  d: "M12 5v14"
}));
const IcxMic = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z"
}), /*#__PURE__*/React.createElement("path", {
  d: "M19 10v2a7 7 0 0 1-14 0v-2"
}), /*#__PURE__*/React.createElement("path", {
  d: "M12 19v3"
}));
const IcxSpark = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M12 6v12"
}), /*#__PURE__*/React.createElement("path", {
  d: "M17.196 9 6.804 15"
}), /*#__PURE__*/React.createElement("path", {
  d: "m6.804 9 10.392 6"
}));
const IcxChevDown = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "m6 9 6 6 6-6"
}));
const IcxStop = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("rect", {
  x: "7",
  y: "7",
  width: "10",
  height: "10",
  rx: "2",
  fill: "currentColor",
  stroke: "none"
}));
const IcxClock = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
  cx: "12",
  cy: "12",
  r: "10"
}), /*#__PURE__*/React.createElement("path", {
  d: "M12 6v6l4 2"
}));
function MccEffortBars({
  level = 4,
  bars = 6
}) {
  return /*#__PURE__*/React.createElement("span", {
    className: "mcc-effort",
    "aria-hidden": "true"
  }, Array.from({
    length: bars
  }).map((_, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    className: i < level ? "" : "is-off",
    style: {
      height: 3 + i * 2
    }
  })));
}
function MccRailModel() {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-prompt-chip mcc-prompt-chip--model"
  }, /*#__PURE__*/React.createElement(IcxSpark, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-prompt-chip-label"
  }, "claude 4.6"), /*#__PURE__*/React.createElement(IcxChevDown, {
    size: 11,
    className: "mcc-prompt-chev"
  }));
}
function MccRailEffort() {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-prompt-chip mcc-prompt-chip--effort"
  }, /*#__PURE__*/React.createElement(MccEffortBars, {
    level: 4
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-prompt-chip-label"
  }, "High"));
}
function MccRailScope({
  label = "hawthorne-core"
}) {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-prompt-chip mcc-prompt-chip--scope"
  }, /*#__PURE__*/React.createElement(IcFolder, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-prompt-code mcc-prompt-chip-label"
  }, label));
}
function MccRailAutonomy() {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-prompt-chip"
  }, /*#__PURE__*/React.createElement(IcxClock, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", null, "4h"), /*#__PURE__*/React.createElement("span", {
    className: "mcc-chip-sub"
  }, "unsupervised"));
}
function MccPromptSend({
  ready,
  stop,
  onClick
}) {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    "aria-label": stop ? "Stop" : "Send",
    className: "mcc-prompt-send" + (ready || stop ? " is-ready" : ""),
    onClick: onClick
  }, stop ? /*#__PURE__*/React.createElement(IcxStop, {
    size: 15
  }) : /*#__PURE__*/React.createElement(IcArrowUp, {
    size: 16
  }));
}
function MccPromptRight({
  ready,
  stop,
  onSend
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-prompt-rail-right"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-prompt-iconbtn",
    "aria-label": "Attach"
  }, /*#__PURE__*/React.createElement(IcxPlus, {
    size: 16
  })), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mcc-prompt-iconbtn",
    "aria-label": "Dictate"
  }, /*#__PURE__*/React.createElement(IcxMic, {
    size: 15
  })), /*#__PURE__*/React.createElement(MccPromptSend, {
    ready: ready,
    stop: stop,
    onClick: onSend
  }));
}
function MccPromptPlate({
  placeholder = "Tell this work what's next…",
  hint = "⌘L to focus",
  className = "",
  mini = false,
  railLeft,
  stop = false,
  value,
  onChange,
  onSend
}) {
  const [inner, setInner] = React.useState("");
  const text = value !== undefined ? value : inner;
  const set = onChange || setInner;
  const ready = text.trim().length > 0;
  const taRef = React.useRef(null);
  // Auto-grow · the field tracks its content up to ~5 lines, then scrolls.
  React.useLayoutEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    const max = mini ? 120 : 184;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, max) + "px";
    ta.style.overflowY = ta.scrollHeight > max ? "auto" : "hidden";
  }, [text, mini]);
  // ⌘L focuses the plate, as the hint promises.
  React.useEffect(() => {
    if (!hint || hint.indexOf("⌘L") === -1) return;
    const onKey = e => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "l" || e.key === "L")) {
        const ta = taRef.current;
        if (ta && ta.offsetParent !== null) {
          e.preventDefault();
          ta.focus();
        }
      }
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [hint]);
  const send = () => {
    if (!ready || !onSend) return;
    onSend(text.trim());
    if (value === undefined) setInner("");
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-prompt " + className + (mini ? " mcc-prompt--mini" : "")
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-prompt-top"
  }, /*#__PURE__*/React.createElement("textarea", {
    ref: taRef,
    className: "mcc-prompt-input",
    rows: 1,
    placeholder: placeholder,
    value: text,
    onChange: e => set(e.target.value),
    onKeyDown: e => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        send();
      }
    }
  }), hint && /*#__PURE__*/React.createElement("span", {
    className: "mcc-prompt-hint"
  }, hint)), /*#__PURE__*/React.createElement("div", {
    className: "mcc-prompt-rail"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-prompt-rail-left"
  }, railLeft !== undefined ? railLeft : window.MccDefaultRail ? /*#__PURE__*/React.createElement(MccDefaultRail, null) : /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(MccRailModel, null), /*#__PURE__*/React.createElement(MccRailEffort, null))), /*#__PURE__*/React.createElement(MccPromptRight, {
    ready: ready,
    stop: stop,
    onSend: send
  })));
}
Object.assign(window, {
  IcxPlus,
  IcxMic,
  IcxSpark,
  IcxChevDown,
  IcxStop,
  IcxClock,
  MccEffortBars,
  MccRailModel,
  MccRailEffort,
  MccRailScope,
  MccRailAutonomy,
  MccPromptSend,
  MccPromptRight,
  MccPromptPlate
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/PromptPlate.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/WorkData.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
// Maestro v2 · icons (Lucide paths, stroke 2, currentColor) + demo data.
// The data model is the work-as-noun reframe: a work item is an object with a
// lifecycle (proposed → queued → running → review → done), agents are workers
// dispatched against it, and chat is one projection of its run stream.

const McIcon = ({
  children,
  size = 16,
  style,
  ...rest
}) => /*#__PURE__*/React.createElement("svg", _extends({
  viewBox: "0 0 24 24",
  fill: "none",
  stroke: "currentColor",
  strokeWidth: "2",
  strokeLinecap: "round",
  strokeLinejoin: "round"
}, rest, {
  style: {
    width: size,
    height: size,
    ...style
  }
}), children);
const IcBoard = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("rect", {
  width: "7",
  height: "9",
  x: "3",
  y: "3",
  rx: "1"
}), /*#__PURE__*/React.createElement("rect", {
  width: "7",
  height: "5",
  x: "14",
  y: "3",
  rx: "1"
}), /*#__PURE__*/React.createElement("rect", {
  width: "7",
  height: "9",
  x: "14",
  y: "12",
  rx: "1"
}), /*#__PURE__*/React.createElement("rect", {
  width: "7",
  height: "5",
  x: "3",
  y: "16",
  rx: "1"
}));
const IcList = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("line", {
  x1: "8",
  x2: "21",
  y1: "6",
  y2: "6"
}), /*#__PURE__*/React.createElement("line", {
  x1: "8",
  x2: "21",
  y1: "12",
  y2: "12"
}), /*#__PURE__*/React.createElement("line", {
  x1: "8",
  x2: "21",
  y1: "18",
  y2: "18"
}), /*#__PURE__*/React.createElement("line", {
  x1: "3",
  x2: "3.01",
  y1: "6",
  y2: "6"
}), /*#__PURE__*/React.createElement("line", {
  x1: "3",
  x2: "3.01",
  y1: "12",
  y2: "12"
}), /*#__PURE__*/React.createElement("line", {
  x1: "3",
  x2: "3.01",
  y1: "18",
  y2: "18"
}));
const IcDoc = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"
}), /*#__PURE__*/React.createElement("path", {
  d: "M14 2v4a2 2 0 0 0 2 2h4"
}), /*#__PURE__*/React.createElement("path", {
  d: "M10 9H8"
}), /*#__PURE__*/React.createElement("path", {
  d: "M16 13H8"
}), /*#__PURE__*/React.createElement("path", {
  d: "M16 17H8"
}));
const IcSettings = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"
}), /*#__PURE__*/React.createElement("circle", {
  cx: "12",
  cy: "12",
  r: "3"
}));
const IcLayers = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.84Z"
}), /*#__PURE__*/React.createElement("path", {
  d: "m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"
}), /*#__PURE__*/React.createElement("path", {
  d: "m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"
}));
const IcBranch = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("line", {
  x1: "6",
  x2: "6",
  y1: "3",
  y2: "15"
}), /*#__PURE__*/React.createElement("circle", {
  cx: "18",
  cy: "6",
  r: "3"
}), /*#__PURE__*/React.createElement("circle", {
  cx: "6",
  cy: "18",
  r: "3"
}), /*#__PURE__*/React.createElement("path", {
  d: "M18 9a9 9 0 0 1-9 9"
}));
const IcPlay = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("polygon", {
  points: "6 3 20 12 6 21 6 3"
}));
const IcCheck = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M20 6 9 17l-5-5"
}));
const IcArrowUp = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M12 19V5"
}), /*#__PURE__*/React.createElement("path", {
  d: "m5 12 7-7 7 7"
}));
const IcSun = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
  cx: "12",
  cy: "12",
  r: "4"
}), /*#__PURE__*/React.createElement("path", {
  d: "M12 2v2"
}), /*#__PURE__*/React.createElement("path", {
  d: "M12 20v2"
}), /*#__PURE__*/React.createElement("path", {
  d: "m4.93 4.93 1.41 1.41"
}), /*#__PURE__*/React.createElement("path", {
  d: "m17.66 17.66 1.41 1.41"
}), /*#__PURE__*/React.createElement("path", {
  d: "M2 12h2"
}), /*#__PURE__*/React.createElement("path", {
  d: "M20 12h2"
}), /*#__PURE__*/React.createElement("path", {
  d: "m6.34 17.66-1.41 1.41"
}), /*#__PURE__*/React.createElement("path", {
  d: "m19.07 4.93-1.41 1.41"
}));
const IcMoon = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"
}));
const IcX = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M18 6 6 18"
}), /*#__PURE__*/React.createElement("path", {
  d: "m6 6 12 12"
}));
const IcChevrons = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "m7 15 5 5 5-5"
}), /*#__PURE__*/React.createElement("path", {
  d: "m7 9 5-5 5 5"
}));
const IcAlert = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("circle", {
  cx: "12",
  cy: "12",
  r: "10"
}), /*#__PURE__*/React.createElement("line", {
  x1: "12",
  x2: "12",
  y1: "8",
  y2: "12"
}), /*#__PURE__*/React.createElement("line", {
  x1: "12",
  x2: "12.01",
  y1: "16",
  y2: "16"
}));
const IcEye = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"
}), /*#__PURE__*/React.createElement("circle", {
  cx: "12",
  cy: "12",
  r: "3"
}));
const IcSeam = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("rect", {
  width: "20",
  height: "8",
  x: "2",
  y: "2",
  rx: "2"
}), /*#__PURE__*/React.createElement("rect", {
  width: "20",
  height: "8",
  x: "2",
  y: "14",
  rx: "2"
}), /*#__PURE__*/React.createElement("line", {
  x1: "6",
  x2: "6.01",
  y1: "6",
  y2: "6"
}), /*#__PURE__*/React.createElement("line", {
  x1: "6",
  x2: "6.01",
  y1: "18",
  y2: "18"
}));
const IcChat = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M7.9 20A9 9 0 1 0 4 16.1L2 22Z"
}));
const IcGavel = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "m14 13-7.5 7.5a2.12 2.12 0 0 1-3-3L11 10"
}), /*#__PURE__*/React.createElement("path", {
  d: "m16 16 6 6"
}), /*#__PURE__*/React.createElement("path", {
  d: "m8 8 6-6"
}), /*#__PURE__*/React.createElement("path", {
  d: "m9 7 8 8"
}), /*#__PURE__*/React.createElement("path", {
  d: "m21 11-8-8"
}));

// ── States · one vocabulary, two registers ───────────────────────────────
// plain = Broomva voice ("Needs you", not "InReview"); system = Hawthorne enums.
const WK_STATES = {
  proposed: {
    plain: "Proposed",
    system: "Proposed",
    tone: "muted"
  },
  queued: {
    plain: "Queued",
    system: "Todo",
    tone: "muted"
  },
  running: {
    plain: "Running",
    system: "InProgress",
    tone: "active"
  },
  blocked: {
    plain: "Stuck",
    system: "Blocked",
    tone: "warn"
  },
  review: {
    plain: "Needs you",
    system: "InReview",
    tone: "review"
  },
  done: {
    plain: "Done",
    system: "Done",
    tone: "done"
  }
};
const WK_TONE_COLOR = {
  muted: "var(--bv-gray-400)",
  active: "var(--bv-info)",
  warn: "var(--bv-warning)",
  review: "var(--bv-blue-accent)",
  done: "var(--bv-success)"
};
// Attention-first: what needs you, then what's moving, then backlog, then receipts.
const WK_GROUP_ORDER = ["review", "blocked", "running", "queued", "proposed", "done"];
const WK_GROUP_HINTS = {
  review: "Clean runs waiting at your gate",
  blocked: "A worker is stuck · unblock it",
  running: "Dispatched, live in a worktree",
  queued: "Actionable on the next tick",
  proposed: "Specs not yet dispatched",
  done: "The branch is the receipt"
};
const WK_ATTENTION = ["review", "blocked"];

// Genesis phase machine, per state · how a run renders inside chat.
const WK_PHASE = {
  running: "running",
  blocked: "blocked",
  review: "awaiting you",
  done: "done",
  queued: "queued",
  proposed: "—"
};

// ── Initiatives (light grouping; tasks are the cards) ────────────────────
const WK_INITIATIVES = [{
  id: "hawthorne",
  name: "Hawthorne M2",
  hint: "multi-turn"
}, {
  id: "genesis",
  name: "Genesis P1",
  hint: "walking skeleton"
}, {
  id: "ops",
  name: "Studio ops",
  hint: ""
}];

// ── Work items ───────────────────────────────────────────────────────────
const WK_ITEMS = [{
  id: "w1",
  state: "review",
  time: "12m",
  title: "Persist run transcripts on the Run record",
  initiative: "hawthorne",
  project: "hawthorne-core",
  worker: {
    name: "claude",
    where: "local worktree"
  },
  run: "run/7c2f1a",
  verdict: "Checks passed · 14 tests added",
  look: {
    ran: "2h 14m unsupervised · 41 events · ran to the gate",
    decided: ["Persist the transcript on the Run record, not the session · survives worker restarts", "Replay covered by 14 tests instead of snapshotting live state", "Deferred compression · transcripts are small until multi-day runs land"],
    ask: "Approve the branch so reviews stop needing the live session · and allow reading ops so the import can run unsupervised next loop."
  },
  events: [{
    g: "↑",
    verb: "Queued",
    detail: "Pushed from the spec board",
    t: "3h"
  }, {
    g: "▶",
    verb: "Picked up",
    detail: /*#__PURE__*/React.createElement("span", null, "Worktree created on ", /*#__PURE__*/React.createElement("code", null, "run/7c2f1a"), " \xB7 runner ", /*#__PURE__*/React.createElement("code", null, "claude")),
    t: "2h"
  }, {
    g: "✦",
    verb: "Run finished clean",
    detail: "41 file events · exit 0",
    t: "26m"
  }, {
    g: "⚖",
    verb: "Judge: checks passed",
    detail: "No auto-Done · a clean run still lands at your gate",
    t: "12m",
    tone: "review"
  }],
  chat: [{
    from: "user",
    text: "Persist the full transcript on each Run so reviews don't need the live session"
  }, {
    from: "run",
    phase: "awaiting you",
    run: "run/7c2f1a",
    lines: [["Edit", "crates/hawthorne-core/src/store/run.rs"], ["Test", "cargo test -p hawthorne-core · 14 passed"], ["Commit", "run/7c2f1a · transcript persisted on Run"]]
  }, {
    from: "assistant",
    html: "The run is clean: transcripts now persist on the <b>Run</b> record and 14 tests cover replay. The judge passed its checks, so this is waiting on you · approve and the branch lands as the receipt."
  }]
}, {
  id: "w2",
  state: "blocked",
  time: "41m",
  title: "Import Linear cycles into the object model",
  initiative: "hawthorne",
  project: "hawthorne-db",
  worker: {
    name: "claude",
    where: "local worktree"
  },
  run: "run/b91e44",
  reason: "Needs a Linear API scope before the import can run",
  events: [{
    g: "↑",
    verb: "Queued",
    detail: "Pushed from the spec board",
    t: "5h"
  }, {
    g: "▶",
    verb: "Picked up",
    detail: /*#__PURE__*/React.createElement("span", null, "Worktree created on ", /*#__PURE__*/React.createElement("code", null, "run/b91e44")),
    t: "2h"
  }, {
    g: "✕",
    verb: "Blocked",
    detail: "Worker paused: missing LINEAR_API_KEY scope",
    t: "41m",
    tone: "warn"
  }],
  chat: [{
    from: "user",
    text: "Sync our Linear cycles into the store"
  }, {
    from: "run",
    phase: "blocked",
    run: "run/b91e44",
    lines: [["Read", "crates/hawthorne-db/src/index.rs"], ["Pause", "missing credential: LINEAR_API_KEY (read scope)"]]
  }, {
    from: "assistant",
    html: "I mapped the cycle schema, but I can't reach Linear without a read scope. <button class=\"bv-link-pill\">Grant Linear access</button> and I'll resume the run where it paused."
  }]
}, {
  id: "w3",
  state: "running",
  time: "now",
  title: "Reduce the NDJSON stream to the phase machine",
  initiative: "genesis",
  project: "@genesis/projection",
  worker: {
    name: "claude",
    where: "local worktree"
  },
  run: "run/4fd028",
  events: [{
    g: "↑",
    verb: "Queued",
    detail: "Pushed from chat · text in, work out",
    t: "1h"
  }, {
    g: "▶",
    verb: "Picked up",
    detail: /*#__PURE__*/React.createElement("span", null, "Worktree created on ", /*#__PURE__*/React.createElement("code", null, "run/4fd028")),
    t: "32m"
  }, {
    g: "●",
    verb: "Running",
    detail: "Reducer folding events: running · awaiting · blocked · done",
    t: "now",
    tone: "active"
  }],
  chat: [{
    from: "user",
    text: "Fold the agent's NDJSON stream into a live phase machine the chat can render"
  }, {
    from: "run",
    phase: "running",
    run: "run/4fd028",
    live: true,
    lines: [["Edit", "packages/projection/src/reducer.ts"], ["Test", "bun test packages/projection · 9 passed, 2 todo"], ["Write", "reducer: tool_use → phase 'running'"]]
  }]
}, {
  id: "w4",
  state: "running",
  time: "6m",
  title: "Reconcile May invoices",
  initiative: "ops",
  project: "bookkeeping",
  worker: {
    name: "Bookkeeper",
    where: "cloud sandbox"
  },
  run: "run/c30a9d",
  events: [{
    g: "↑",
    verb: "Queued",
    detail: "Recurring work · first Monday of the month",
    t: "2d"
  }, {
    g: "▶",
    verb: "Picked up",
    detail: /*#__PURE__*/React.createElement("span", null, "Dispatched to a cloud sandbox on ", /*#__PURE__*/React.createElement("code", null, "run/c30a9d")),
    t: "6m"
  }, {
    g: "●",
    verb: "Running",
    detail: "Same plane, different worker · the core never knows where work runs",
    t: "now",
    tone: "active"
  }],
  chat: [{
    from: "user",
    text: "Reconcile May invoices"
  }, {
    from: "run",
    phase: "running",
    run: "run/c30a9d",
    live: true,
    lines: [["Read", "drive: /receipts/2026-05 · 38 documents"], ["Match", "31 of 36 invoices reconciled"]]
  }]
}, {
  id: "w5",
  state: "queued",
  time: "2h",
  title: "Resume sessions across turns (Phase 2)",
  initiative: "hawthorne",
  project: "hawthorne-core",
  worker: null,
  events: [{
    g: "↑",
    verb: "Queued",
    detail: "Holding at the concurrency cap · 2 of 2 worktrees in use",
    t: "2h"
  }],
  chat: [{
    from: "user",
    text: "Make sessions resumable so a task can span turns"
  }, {
    from: "assistant",
    html: "Queued. The scheduler is at its cap (2 of 2 worktrees), so I'll dispatch this on the next free tick."
  }]
}, {
  id: "w6",
  state: "queued",
  time: "1d",
  kind: "handoff",
  title: "Handoff: Maestro relay, phase 1b",
  initiative: "hawthorne",
  project: "hawthorne-engine",
  worker: null,
  firstAction: "Wire POST /trigger to the N=1 budget and surface orch-state transitions over /ws.",
  events: [{
    g: "↑",
    verb: "Pushed",
    detail: "Handoff queued from your phone · first action travels with it",
    t: "1d"
  }],
  chat: [{
    from: "user",
    text: "Picking this up later · queue the relay handoff with the first action attached"
  }, {
    from: "assistant",
    html: "Queued with its first action: <b>wire /trigger to the N=1 budget</b>. Any session · yours or a worker's · can pick it up from here."
  }]
}, {
  id: "w7",
  state: "proposed",
  time: "3d",
  kind: "spec",
  title: "Spec: TunnelRunner relay protocol (V2)",
  initiative: "hawthorne",
  project: "hawthorne-core",
  worker: null,
  events: [{
    g: "✎",
    verb: "Proposed",
    detail: "Draft spec · adding a runner never touches the core",
    t: "3d"
  }],
  chat: [{
    from: "user",
    text: "Draft the relay protocol for running work on my own machine"
  }, {
    from: "assistant",
    html: "Drafted. It stays a proposal until you dispatch it · work exists before, and outlives, any agent session."
  }]
}, {
  id: "w8",
  state: "done",
  time: "2d",
  title: "Close the single-stage execution loop (M1b)",
  initiative: "hawthorne",
  project: "hawthorne-engine",
  worker: {
    name: "claude",
    where: "local worktree"
  },
  run: "run/19adf2",
  verdict: "Judge passed · you approved",
  events: [{
    g: "▶",
    verb: "Picked up",
    detail: /*#__PURE__*/React.createElement("span", null, "Worktree created on ", /*#__PURE__*/React.createElement("code", null, "run/19adf2")),
    t: "3d"
  }, {
    g: "⚖",
    verb: "Judge: checks passed",
    detail: "Agent created the file, committed it, exit 0",
    t: "2d",
    tone: "review"
  }, {
    g: "✓",
    verb: "You approved",
    detail: /*#__PURE__*/React.createElement("span", null, "Committed on ", /*#__PURE__*/React.createElement("code", null, "run/19adf2"), " \xB7 worktree reclaimed \xB7 the branch is the receipt"),
    t: "2d",
    tone: "done"
  }],
  chat: [{
    from: "user",
    text: "Close the loop: observe, decide, act, judge, commit"
  }, {
    from: "run",
    phase: "done",
    run: "run/19adf2",
    lines: [["Commit", "run/19adf2 · loop closed end-to-end"]]
  }, {
    from: "assistant",
    html: "Done · and <b>Done was earned</b>: the judge passed its checks and you approved at the gate. The worktree is reclaimed; the branch remains as the receipt."
  }]
}];
const WK_REPLY = "Noted on the work item · I'll fold that into the next run. The thread stays with the work, not with me.";
Object.assign(window, {
  McIcon,
  IcBoard,
  IcList,
  IcDoc,
  IcSettings,
  IcLayers,
  IcBranch,
  IcPlay,
  IcCheck,
  IcArrowUp,
  IcSun,
  IcMoon,
  IcX,
  IcChevrons,
  IcAlert,
  IcEye,
  IcSeam,
  IcChat,
  IcGavel,
  WK_STATES,
  WK_TONE_COLOR,
  WK_GROUP_ORDER,
  WK_GROUP_HINTS,
  WK_ATTENTION,
  WK_PHASE,
  WK_INITIATIVES,
  WK_ITEMS,
  WK_REPLY
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/WorkData.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/WorkDetail.jsx
try { (() => {
// Maestro · the work item detail pane.
// One object, three projections: a lifecycle rail, an activity timeline
// (the run stream as receipts), and chat (the same stream as conversation).
// The rail, receipts and gate buttons compose the standard components.

const MC_RAIL_STAGES = [{
  id: "proposed",
  plain: "Proposed",
  system: "Proposed"
}, {
  id: "queued",
  plain: "Queued",
  system: "Todo"
}, {
  id: "running",
  plain: "Running",
  system: "InProgress"
}, {
  id: "review",
  plain: "Your gate",
  system: "InReview"
}, {
  id: "done",
  plain: "Done",
  system: "Done"
}];
const MC_RAIL_INDEX = {
  proposed: 0,
  queued: 1,
  running: 2,
  blocked: 2,
  review: 3,
  done: 4
};
function McRail({
  state,
  vocab
}) {
  const cur = MC_RAIL_INDEX[state];
  const stages = MC_RAIL_STAGES.map((s, i) => ({
    name: (vocab === "system" ? s.system : s.plain) + (i === cur && state === "blocked" ? " · blocked" : ""),
    state: i < cur ? "passed" : i === cur ? state === "blocked" ? "warn" : "current" : "upcoming"
  }));
  return /*#__PURE__*/React.createElement("div", null, /*#__PURE__*/React.createElement(DsLifecycleRail, {
    stages: stages
  }), /*#__PURE__*/React.createElement("div", {
    className: "mc-rail-note"
  }, "Done is earned \xB7 the judge is its only source, and clean runs still pass your gate."));
}
function McTimeline({
  events
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mc-tl"
  }, events.map((e, i) => /*#__PURE__*/React.createElement("div", {
    key: i,
    className: "mc-tl-item"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-tl-glyph",
    style: e.tone ? {
      color: WK_TONE_COLOR[e.tone]
    } : undefined
  }, e.g), /*#__PURE__*/React.createElement("div", {
    className: "mc-tl-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-tl-verb"
  }, e.verb, /*#__PURE__*/React.createElement("span", {
    className: "mc-tl-time"
  }, e.t)), e.detail && /*#__PURE__*/React.createElement("span", {
    className: "mc-tl-detail"
  }, e.detail)))));
}
function McRunCard({
  msg
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mc-run-card"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-run-card-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-phase"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot bv-dot--pulse",
    style: {
      background: msg.phase === "running" ? "var(--bv-info)" : msg.phase === "blocked" ? "var(--bv-warning)" : msg.phase === "done" ? "var(--bv-success)" : "var(--bv-blue-accent)",
      animation: msg.live ? undefined : "none"
    }
  }), msg.phase), /*#__PURE__*/React.createElement("span", {
    className: "mc-receipt"
  }, msg.run)), /*#__PURE__*/React.createElement("div", {
    className: "mc-run-lines"
  }, msg.lines.map((l, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    className: "mc-run-line"
  }, /*#__PURE__*/React.createElement("b", null, l[0]), " ", l[1], msg.live && i === msg.lines.length - 1 ? /*#__PURE__*/React.createElement("span", {
    className: "mcc-caret"
  }) : null))));
}
function McChat({
  item,
  extra,
  typing,
  onSend
}) {
  const [draft, setDraft] = React.useState("");
  const feedRef = React.useRef(null);
  const msgs = [...item.chat, ...(extra[item.id] || [])];
  React.useEffect(() => {
    const el = feedRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [msgs.length, typing]);
  function send() {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    onSend(item.id, text);
  }
  return /*#__PURE__*/React.createElement("div", {
    className: "mc-chat"
  }, /*#__PURE__*/React.createElement("div", {
    className: "bv-chat-feed",
    ref: feedRef
  }, msgs.map((m, i) => {
    if (m.from === "run") return /*#__PURE__*/React.createElement(McRunCard, {
      key: i,
      msg: m
    });
    if (m.from === "user") return /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "bv-msg bv-msg--user"
    }, m.text);
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      className: "bv-msg bv-msg--assistant",
      dangerouslySetInnerHTML: {
        __html: m.html
      }
    });
  }), typing && /*#__PURE__*/React.createElement("div", {
    className: "bv-typing"
  }, /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("span", null))), /*#__PURE__*/React.createElement("div", {
    className: "bv-chat-composer-wrap"
  }, /*#__PURE__*/React.createElement(MccPromptPlate, {
    className: "mcc-prompt--glass",
    placeholder: "Tell this work what's next\u2026",
    value: draft,
    onChange: setDraft,
    onSend: () => send()
  })));
}
function McDetail({
  item,
  vocab,
  receipts,
  tab,
  onTab,
  onApprove,
  onSendBack,
  chatExtra,
  typing,
  onSend
}) {
  if (!item) {
    return /*#__PURE__*/React.createElement("aside", {
      className: "mc-detail",
      "data-screen-label": "Detail pane"
    }, /*#__PURE__*/React.createElement("div", {
      className: "mc-detail-empty"
    }, /*#__PURE__*/React.createElement("span", {
      className: "bv-greeting-title"
    }, "No work selected"), /*#__PURE__*/React.createElement("span", {
      className: "bv-greeting-sub"
    }, "Pick a work item from the feed \xB7 it carries its own history, runs, and conversation.")));
  }
  const meta = WK_STATES[item.state];
  const init = WK_INITIATIVES.find(i => i.id === item.initiative);
  return /*#__PURE__*/React.createElement("aside", {
    className: "mc-detail",
    "data-screen-label": "Detail pane"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-detail-header"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-detail-breadcrumb"
  }, init ? init.name : "", " \u203A ", item.project), /*#__PURE__*/React.createElement("div", {
    className: "mc-detail-title-row"
  }, /*#__PURE__*/React.createElement("h2", {
    className: "mc-detail-title"
  }, item.title), /*#__PURE__*/React.createElement("span", {
    className: "mc-badge",
    style: {
      color: WK_TONE_COLOR[meta.tone] === "var(--bv-gray-400)" ? "var(--muted-foreground)" : undefined
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      background: WK_TONE_COLOR[meta.tone]
    }
  }), vocab === "system" ? meta.system : meta.plain)), item.state === "review" && /*#__PURE__*/React.createElement("div", {
    className: "mc-detail-actions"
  }, /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    onClick: () => onApprove(item.id)
  }, /*#__PURE__*/React.createElement(IcCheck, {
    size: 16
  }), "Approve"), /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    variant: "secondary",
    onClick: () => onSendBack(item.id)
  }, "Send back"), item.verdict && /*#__PURE__*/React.createElement("span", {
    className: "mc-triage-sub"
  }, item.verdict)), item.state === "blocked" && /*#__PURE__*/React.createElement("div", {
    className: "mc-detail-actions"
  }, /*#__PURE__*/React.createElement(DsButton, {
    size: "sm"
  }, "Grant access"), /*#__PURE__*/React.createElement("span", {
    className: "mc-triage-sub"
  }, item.reason)), /*#__PURE__*/React.createElement("div", {
    className: "bv-tabs",
    style: {
      marginTop: 2
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "bv-tab" + (tab === "activity" ? " is-active" : ""),
    type: "button",
    onClick: () => onTab("activity")
  }, "Activity"), /*#__PURE__*/React.createElement("button", {
    className: "bv-tab" + (tab === "chat" ? " is-active" : ""),
    type: "button",
    onClick: () => onTab("chat")
  }, "Chat"))), tab === "activity" ? /*#__PURE__*/React.createElement("div", {
    className: "mc-detail-body"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-detail-section"
  }, /*#__PURE__*/React.createElement(McRail, {
    state: item.state,
    vocab: vocab
  })), /*#__PURE__*/React.createElement("div", {
    className: "mc-detail-section",
    style: {
      paddingTop: 4
    }
  }, /*#__PURE__*/React.createElement(McTimeline, {
    events: item.events
  }), receipts && item.run && /*#__PURE__*/React.createElement(DsReceipt, {
    style: {
      padding: "10px 13px",
      gap: 5,
      fontSize: 12.5
    },
    rows: [{
      icon: /*#__PURE__*/React.createElement(IcBranch, {
        size: 13
      }),
      label: /*#__PURE__*/React.createElement("span", null, "branch ", /*#__PURE__*/React.createElement(McMono, null, item.run), " \xB7 worktree-per-run")
    }, ...(item.verdict ? [{
      icon: /*#__PURE__*/React.createElement(IcGavel, {
        size: 13
      }),
      label: /*#__PURE__*/React.createElement("span", null, "judge \xB7 ", item.verdict.toLowerCase())
    }] : []), {
      icon: /*#__PURE__*/React.createElement(IcCheck, {
        size: 13
      }),
      label: "the branch is the receipt · the worktree is reclaimed after the run"
    }]
  }))) : /*#__PURE__*/React.createElement(McChat, {
    item: item,
    extra: chatExtra,
    typing: typing,
    onSend: onSend
  }));
}

// Mono machine fact inside receipt copy · matches .mc-receipt-row code.
function McMono({
  children
}) {
  return /*#__PURE__*/React.createElement("code", {
    style: {
      fontFamily: "var(--bv-font-mono, ui-monospace, monospace)",
      fontSize: 11.5,
      color: "var(--foreground)"
    }
  }, children);
}
Object.assign(window, {
  McDetail,
  McRail,
  McTimeline,
  McRunCard,
  McChat,
  McMono
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/WorkDetail.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/WorkFeed.jsx
try { (() => {
// Maestro v2 · the work feed: triage headline, filter chips,
// attention-first groups (Maestro's ordering on the Hawthorne object model).

function McStateLabel({
  state,
  vocab,
  dot
}) {
  const meta = WK_STATES[state];
  return /*#__PURE__*/React.createElement("span", {
    className: "mc-state",
    style: {
      color: "var(--foreground)"
    }
  }, dot || /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      background: WK_TONE_COLOR[meta.tone]
    }
  }), vocab === "system" ? meta.system : meta.plain);
}
function McWorkCard({
  item,
  selected,
  onSelect,
  vocab,
  receipts,
  glow = true,
  dot,
  extra
}) {
  const init = WK_INITIATIVES.find(i => i.id === item.initiative);
  const running = item.state === "running";
  const effDot = dot || (running ? /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide"
  }) : undefined);
  const card = /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "bv-card mc-card" + (selected ? " is-selected" : ""),
    onClick: () => onSelect(item.id)
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-card-top"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-breadcrumb"
  }, /*#__PURE__*/React.createElement("b", null, init ? init.name : ""), " \u203A ", item.project), /*#__PURE__*/React.createElement("span", {
    className: "mc-card-time"
  }, item.time)), /*#__PURE__*/React.createElement("div", {
    className: "mc-card-title"
  }, item.title), item.reason && /*#__PURE__*/React.createElement("div", {
    className: "mc-reason"
  }, /*#__PURE__*/React.createElement(IcAlert, null), item.reason), item.firstAction && /*#__PURE__*/React.createElement("div", {
    className: "mc-reason mc-reason--top"
  }, /*#__PURE__*/React.createElement(IcArrowUp, null), /*#__PURE__*/React.createElement("span", {
    className: "mc-clamp2"
  }, "First action: ", item.firstAction)), /*#__PURE__*/React.createElement("div", {
    className: "mc-card-meta"
  }, /*#__PURE__*/React.createElement(McStateLabel, {
    state: item.state,
    vocab: vocab,
    dot: effDot
  }), item.worker && /*#__PURE__*/React.createElement("span", {
    className: "mc-worker"
  }, /*#__PURE__*/React.createElement(McAvatar, {
    name: item.worker.name,
    color: item.worker.where === "cloud sandbox" ? "var(--bv-blue-accent)" : "var(--bv-blue)",
    size: 15
  }), item.worker.name, " \xB7 ", item.worker.where), receipts && item.run && /*#__PURE__*/React.createElement("span", {
    className: "mc-receipt"
  }, item.run)), extra);
  if (running && glow) {
    return /*#__PURE__*/React.createElement("div", {
      className: "mcc-undertow-halo mcc-halo--tidalnebula"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mcc-halo-spin-layer"
    }), card);
  }
  return card;
}
function McFeed({
  items,
  selectedId,
  onSelect,
  vocab,
  receipts,
  filter,
  onFilter
}) {
  const attention = items.filter(i => WK_ATTENTION.includes(i.state)).length;
  const active = items.filter(i => i.state !== "done").length;
  const groups = WK_GROUP_ORDER.map(state => ({
    state,
    items: items.filter(i => i.state === state)
  })).filter(g => g.items.length > 0);
  const visible = filter ? groups.filter(g => g.state === filter) : groups;
  return /*#__PURE__*/React.createElement("div", {
    className: "mc-feed",
    "data-screen-label": "Work feed"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-feed-inner"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-triage"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-triage-headline"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-triage-title"
  }, attention > 0 ? `${attention} ${attention === 1 ? "piece" : "pieces"} of work ${attention === 1 ? "needs" : "need"} you` : "All clear"), /*#__PURE__*/React.createElement("span", {
    className: "mc-triage-sub"
  }, active, " active \xB7 workers handle the rest")), /*#__PURE__*/React.createElement("div", {
    className: "mc-chips"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mc-chip" + (filter === null ? " is-active" : ""),
    onClick: () => onFilter(null)
  }, "All"), groups.map(g => {
    const meta = WK_STATES[g.state];
    return /*#__PURE__*/React.createElement("button", {
      key: g.state,
      type: "button",
      className: "mc-chip" + (filter === g.state ? " is-active" : ""),
      onClick: () => onFilter(filter === g.state ? null : g.state)
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: WK_TONE_COLOR[meta.tone]
      }
    }), vocab === "system" ? meta.system : meta.plain, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-count"
    }, g.items.length));
  }))), visible.map(g => {
    const meta = WK_STATES[g.state];
    return /*#__PURE__*/React.createElement("section", {
      key: g.state,
      className: "mc-group",
      "data-screen-label": "Group: " + meta.plain
    }, /*#__PURE__*/React.createElement("div", {
      className: "mc-group-header"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-group-label"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: WK_TONE_COLOR[meta.tone]
      }
    }), vocab === "system" ? meta.system : meta.plain), /*#__PURE__*/React.createElement("span", {
      className: "mc-group-count"
    }, g.items.length), /*#__PURE__*/React.createElement("span", {
      className: "mc-group-hint"
    }, WK_GROUP_HINTS[g.state])), /*#__PURE__*/React.createElement("div", {
      className: "mc-group-cards"
    }, g.items.map(item => /*#__PURE__*/React.createElement(McWorkCard, {
      key: item.id,
      item: item,
      selected: item.id === selectedId,
      onSelect: onSelect,
      vocab: vocab,
      receipts: receipts
    }))));
  })));
}
Object.assign(window, {
  McFeed,
  McWorkCard,
  McStateLabel
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/WorkFeed.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/WorkPanel.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
// Maestro v3 · top bar (the bench + tick timer) + the live panel
// (closeable, resizable; Chat / Activity tabs; maestro-aware).

// The settled right zone, shared with the concepts canvas via window.
const MCC_TICK_WAKES = [{
  g: "↻",
  verb: "Routine · nightly digest",
  tone: "done",
  detail: "Self-scheduled at 02:00 → composed the handoff digest",
  t: "8h"
}, {
  g: "✎",
  verb: "You",
  detail: "\"prioritize the API work\" → reordered queue",
  t: "1h"
}, {
  g: "▷",
  verb: "Interval · 15m",
  detail: "No-op · holding at capacity (2/2 worktrees)",
  t: "17m"
}, {
  g: "▶",
  verb: "Worker returned",
  tone: "active",
  detail: "run/4fd028 → judged clean, moved to your gate",
  t: "2m"
}];
function MccLineageRow({
  depth = 0,
  live,
  done,
  halt,
  who,
  label,
  dur,
  durPct
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-lin-row",
    style: {
      paddingLeft: depth * 22
    }
  }, depth > 0 && /*#__PURE__*/React.createElement("span", {
    className: "mcc-lin-elbow"
  }), live ? /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 13,
      height: 13
    }
  }) : /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      background: done ? "var(--bv-success)" : halt ? "var(--bv-blue-accent)" : "var(--bv-gray-400)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-lin-body"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-lin-label"
  }, label), /*#__PURE__*/React.createElement("span", {
    className: "mcc-lin-who"
  }, who)), /*#__PURE__*/React.createElement("span", {
    className: "mcc-lin-track"
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: durPct
    }
  })), /*#__PURE__*/React.createElement("span", {
    className: "mcc-lin-dur"
  }, dur));
}

// Lineage derived from live items: sessions spawn sessions, hours roll up.
function MccLineage({
  items
}) {
  const rows = [{
    live: true,
    label: "maestro",
    who: "the loop · routine",
    dur: "all day",
    durPct: "100%"
  }];
  for (const i of items.filter(x => x.state === "running")) rows.push({
    depth: 1,
    live: true,
    label: i.project,
    who: "maestro → " + (i.worker ? i.worker.name : "worker"),
    dur: i.time,
    durPct: "56%"
  });
  for (const i of items.filter(x => x.state === "review")) rows.push({
    depth: 1,
    halt: true,
    label: i.project,
    who: "waiting at your gate",
    dur: i.time,
    durPct: "96%"
  });
  for (const i of items.filter(x => x.state === "queued").slice(0, 2)) rows.push({
    depth: 1,
    label: i.project,
    who: "queued · next loop",
    dur: "—",
    durPct: "0%"
  });
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column"
    }
  }, rows.slice(0, 6).map((r, i) => /*#__PURE__*/React.createElement(MccLineageRow, _extends({
    key: i
  }, r))));
}
function MccBench({
  workers,
  onClick,
  items
}) {
  const colors = {
    claude: "var(--bv-blue)",
    bookkeeper: "var(--bv-purple, #7c6cf0)"
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-timer"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-undertow-halo mcc-halo--tidalnebula mcc-halo--pill"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-halo-spin-layer"
  }), /*#__PURE__*/React.createElement("button", {
    className: "mcc-bench",
    type: "button",
    onClick: onClick,
    title: workers.join(" · ") + " · open the orchestrator"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-bench-faces"
  }, workers.map(w => /*#__PURE__*/React.createElement(McAvatar, {
    key: w,
    name: w,
    color: colors[w.toLowerCase()] || "var(--bv-blue)",
    size: 20
  }))), /*#__PURE__*/React.createElement("span", {
    className: "mcc-bench-label"
  }, workers.length, " live"))), /*#__PURE__*/React.createElement("div", {
    className: "mcc-timer-pop bv-glass-heavy",
    style: {
      width: 380
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label",
    style: {
      paddingBottom: 6
    }
  }, "Live sessions \xB7 where the hours go"), /*#__PURE__*/React.createElement(MccLineage, {
    items: items || WK_ITEMS
  })));
}
function MccTickTimer({
  wakes = MCC_TICK_WAKES,
  label = "next 13m",
  onClick,
  disabled
}) {
  const r = 8,
    c = 2 * Math.PI * r;
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-timer"
  }, /*#__PURE__*/React.createElement("button", {
    className: "mcc-orch-chip",
    type: "button",
    onClick: onClick,
    disabled: disabled,
    title: "Next tick \xB7 click to wake now"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-ring"
  }, /*#__PURE__*/React.createElement("svg", {
    viewBox: "0 0 20 20",
    width: "20",
    height: "20"
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "10",
    cy: "10",
    r: r,
    fill: "none",
    stroke: "var(--bv-border-15)",
    strokeWidth: "2"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "10",
    cy: "10",
    r: r,
    fill: "none",
    stroke: "var(--bv-blue)",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeDasharray: c,
    strokeDashoffset: c * (13 / 15),
    transform: "rotate(-90 10 10)",
    className: "mcc-ring-arc"
  }), /*#__PURE__*/React.createElement("circle", {
    cx: "10",
    cy: "10",
    r: "3",
    fill: "var(--bv-info)"
  }))), /*#__PURE__*/React.createElement("span", {
    className: "mcc-orch-meta"
  }, label)), /*#__PURE__*/React.createElement("div", {
    className: "mcc-timer-pop bv-glass-heavy"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label",
    style: {
      paddingBottom: 6
    }
  }, "The loop"), /*#__PURE__*/React.createElement(McTimeline, {
    events: wakes
  })));
}
Object.assign(window, {
  MccBench,
  MccTickTimer,
  MccLineage,
  MCC_TICK_WAKES
});
function McvTopBar({
  theme,
  onToggleTheme,
  onOpenMaestro,
  onWake,
  waking,
  canWake,
  onShowIdea,
  counts,
  workers,
  wakes,
  items,
  onAttention,
  onCommand,
  cmdOpen
}) {
  const attn = counts.needYou + counts.stuck;
  return /*#__PURE__*/React.createElement("header", {
    className: "bv-top-bar mcv-top",
    "data-screen-label": "Top bar"
  }, /*#__PURE__*/React.createElement("button", {
    className: "mcc-quiet mcc-narr mcv-narr",
    type: "button",
    onClick: onOpenMaestro,
    title: "Open the wake log"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide"
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcv-narr-text"
  }, waking ? "maestro is waking…" : /*#__PURE__*/React.createElement(React.Fragment, null, "maestro woke 2m ago \xB7 ", /*#__PURE__*/React.createElement("b", null, "run/4fd028"), " judged clean, at your gate"))), /*#__PURE__*/React.createElement("span", {
    className: "cmdk-lift" + (cmdOpen ? " is-open" : "")
  }, /*#__PURE__*/React.createElement("button", {
    className: "mcc-cmd",
    type: "button",
    "data-cmdk-anchor": true,
    onClick: onCommand,
    title: "Ask, find, or start work (\u2318K)"
  }, /*#__PURE__*/React.createElement(IcChat, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-cmd-ph"
  }, "Ask, find, or start work\u2026"), /*#__PURE__*/React.createElement("span", {
    className: "mcc-cmd-kbd"
  }, "\u2318K"))), /*#__PURE__*/React.createElement("div", {
    className: "mc-topbar-right"
  }, attn > 0 && /*#__PURE__*/React.createElement("button", {
    className: "mcc-attn-chip mcc-attn-btn",
    type: "button",
    onClick: onAttention,
    title: "Blocked or waiting on you"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      background: "var(--bv-blue-accent)"
    }
  }), attn, " need", attn === 1 ? "s" : "", " you"), /*#__PURE__*/React.createElement(MccTickTimer, {
    wakes: wakes,
    label: waking ? "waking…" : "next 13m",
    onClick: onWake,
    disabled: waking || !canWake
  }), /*#__PURE__*/React.createElement("button", {
    className: "bv-icon-btn",
    type: "button",
    "aria-label": "Toggle theme",
    onClick: onToggleTheme
  }, theme === "dark" ? /*#__PURE__*/React.createElement(IcSun, {
    size: 18
  }) : /*#__PURE__*/React.createElement(IcMoon, {
    size: 18
  }))));
}

// ── The live panel ────────────────────────────────────────────────────────
function McvLivePanel({
  item,
  isMaestro,
  routines,
  tab,
  onTab,
  onClose,
  onDragStart,
  vocab,
  receipts,
  onApprove,
  onSendBack,
  chatExtra,
  typing,
  onSend
}) {
  const meta = WK_STATES[item.state];
  const init = item.initiative ? WK_INITIATIVES.find(i => i.id === item.initiative) : null;
  const isReview = !isMaestro && item.state === "review";
  // The look is only available at the gate; fall back to chat elsewhere.
  const effTab = tab === "look" && !isReview ? "chat" : tab;
  return /*#__PURE__*/React.createElement("aside", {
    className: "mcc-live-panel",
    "data-screen-label": "Live panel"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-drag",
    onMouseDown: onDragStart,
    title: "Drag to resize"
  }), /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-top"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-detail-breadcrumb"
  }, isMaestro ? "Agents › orchestrator" : (init ? init.name : "") + " › " + item.project), /*#__PURE__*/React.createElement("button", {
    className: "mcc-panel-close",
    type: "button",
    "aria-label": "Close panel",
    onClick: onClose
  }, /*#__PURE__*/React.createElement(IcX, {
    size: 14
  }))), /*#__PURE__*/React.createElement("div", {
    className: "mcc-chat-pop-title-row"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-chat-pop-title"
  }, item.title), isMaestro ? /*#__PURE__*/React.createElement("span", {
    className: "mc-badge"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot bv-dot--pulse",
    style: {
      background: "var(--bv-info)"
    }
  }), "Listening") : /*#__PURE__*/React.createElement("span", {
    className: "mc-badge"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-chip-dot",
    style: {
      background: WK_TONE_COLOR[meta.tone]
    }
  }), vocab === "system" ? meta.system : meta.plain)), isMaestro && /*#__PURE__*/React.createElement("span", {
    className: "mcc-orch-routines"
  }, routines.map(r => /*#__PURE__*/React.createElement("span", {
    key: r,
    className: "mc-receipt"
  }, r))), !isMaestro && item.state === "review" && effTab !== "look" && /*#__PURE__*/React.createElement("div", {
    className: "mc-detail-actions"
  }, /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    onClick: () => onApprove(item.id)
  }, /*#__PURE__*/React.createElement(IcCheck, {
    size: 16
  }), "Approve"), /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    variant: "secondary",
    onClick: () => onSendBack(item.id)
  }, "Send back")), /*#__PURE__*/React.createElement("div", {
    className: "bv-tabs",
    style: {
      marginTop: 2
    }
  }, isReview && /*#__PURE__*/React.createElement("button", {
    className: "bv-tab" + (effTab === "look" ? " is-active" : ""),
    type: "button",
    onClick: () => onTab("look")
  }, "Review"), /*#__PURE__*/React.createElement("button", {
    className: "bv-tab" + (effTab === "chat" ? " is-active" : ""),
    type: "button",
    onClick: () => onTab("chat")
  }, "Chat"), /*#__PURE__*/React.createElement("button", {
    className: "bv-tab" + (effTab === "activity" ? " is-active" : ""),
    type: "button",
    onClick: () => onTab("activity")
  }, isMaestro ? "Wake log" : "Activity"))), effTab === "look" ? /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-activity",
    style: {
      gap: 14
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-look-ran"
  }, /*#__PURE__*/React.createElement("b", null, item.look ? item.look.ran : "Ran to the gate"), item.worker ? /*#__PURE__*/React.createElement("span", null, " \xB7 ", item.worker.name, " \xB7 ", item.worker.where) : null), /*#__PURE__*/React.createElement("div", {
    className: "mcc-look-sec"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label",
    style: {
      paddingBottom: 4
    }
  }, "What changed"), /*#__PURE__*/React.createElement(DsReceipt, {
    style: {
      padding: "10px 13px",
      gap: 5,
      fontSize: 12.5
    },
    rows: [...(item.run ? [{
      icon: /*#__PURE__*/React.createElement(IcBranch, {
        size: 13
      }),
      label: /*#__PURE__*/React.createElement("span", null, "branch ", /*#__PURE__*/React.createElement(McMono, null, item.run), " \xB7 worktree-per-run")
    }] : []), ...(item.verdict ? [{
      icon: /*#__PURE__*/React.createElement(IcGavel, {
        size: 13
      }),
      label: /*#__PURE__*/React.createElement("span", null, "judge \xB7 ", item.verdict.toLowerCase())
    }] : []), ...(item.run ? [{
      icon: /*#__PURE__*/React.createElement(IcEye, {
        size: 13
      }),
      label: /*#__PURE__*/React.createElement("span", null, "scope: worktree \xB7 reads ../spec.md \xB7 writes runs/", item.run.replace("run/", ""), ".md")
    }] : [])]
  })), item.look && item.look.decided && /*#__PURE__*/React.createElement("div", {
    className: "mcc-look-sec"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label",
    style: {
      paddingBottom: 4
    }
  }, "What it decided"), /*#__PURE__*/React.createElement("ul", {
    className: "mcc-look-list"
  }, item.look.decided.map((d, i) => /*#__PURE__*/React.createElement("li", {
    key: i
  }, d)))), /*#__PURE__*/React.createElement("div", {
    className: "mcc-look-sec"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-label",
    style: {
      paddingBottom: 4
    }
  }, "The ask"), /*#__PURE__*/React.createElement("p", {
    className: "mcc-look-ask"
  }, item.look ? item.look.ask : "Approve the branch · it lands as the receipt.")), /*#__PURE__*/React.createElement("div", {
    className: "mc-detail-actions"
  }, /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    onClick: () => onApprove(item.id)
  }, /*#__PURE__*/React.createElement(IcCheck, {
    size: 16
  }), "Approve"), /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    variant: "secondary",
    onClick: () => onSendBack(item.id)
  }, "Send back"), /*#__PURE__*/React.createElement("span", {
    className: "mcc-look-timer"
  }, "a 90-second look"))) : effTab === "chat" ? /*#__PURE__*/React.createElement(McChat, {
    item: item,
    extra: chatExtra,
    typing: typing,
    onSend: onSend
  }) : /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-activity"
  }, !isMaestro && item.run && /*#__PURE__*/React.createElement("div", {
    className: "mcc-panel-receipt-label"
  }, "Live feed", /*#__PURE__*/React.createElement("span", {
    className: "mc-receipt"
  }, item.run)), /*#__PURE__*/React.createElement(McTimeline, {
    events: item.events
  }), !isMaestro && item.run && /*#__PURE__*/React.createElement(DsReceipt, {
    style: {
      padding: "10px 13px",
      gap: 5,
      fontSize: 12.5
    },
    rows: [{
      icon: /*#__PURE__*/React.createElement(IcBranch, {
        size: 13
      }),
      label: /*#__PURE__*/React.createElement("span", null, "branch ", /*#__PURE__*/React.createElement(McMono, null, item.run), " \xB7 worktree-per-run")
    }, ...(item.verdict ? [{
      icon: /*#__PURE__*/React.createElement(IcGavel, {
        size: 13
      }),
      label: /*#__PURE__*/React.createElement("span", null, "judge \xB7 ", item.verdict.toLowerCase())
    }] : []), {
      icon: /*#__PURE__*/React.createElement(IcEye, {
        size: 13
      }),
      label: /*#__PURE__*/React.createElement("span", null, "scope: worktree \xB7 reads ../spec.md \xB7 writes runs/", item.run.replace("run/", ""), ".md")
    }]
  })));
}
Object.assign(window, {
  McvTopBar,
  McvLivePanel
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/WorkPanel.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/WorkPlanes.jsx
try { (() => {
// Maestro v3 · the work planes: feed / board / list, switchable.
// Running work wears the Undertow (contained halo + tidepool dot) · the one
// running treatment. The border comet is retired.

const MCV_UNDERTOW_DOT = /*#__PURE__*/React.createElement("span", {
  className: "mcc-dot-tide"
});

// A work card that wears the running signal.
function McvLiveCard({
  item,
  selected,
  onSelect,
  vocab,
  receipts
}) {
  if (item.state !== "running") {
    return /*#__PURE__*/React.createElement(McWorkCard, {
      item: item,
      selected: selected,
      onSelect: onSelect,
      vocab: vocab,
      receipts: receipts
    });
  }
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-undertow-halo mcc-halo--tidalnebula"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mcc-halo-spin-layer"
  }), /*#__PURE__*/React.createElement(McWorkCard, {
    item: item,
    selected: selected,
    onSelect: onSelect,
    vocab: vocab,
    receipts: receipts,
    glow: false,
    dot: MCV_UNDERTOW_DOT
  }));
}
function McvGroups({
  items,
  filter
}) {
  const groups = WK_GROUP_ORDER.map(state => ({
    state,
    items: items.filter(i => i.state === state)
  })).filter(g => g.items.length > 0);
  return filter ? groups.filter(g => g.state === filter) : groups;
}

// ── Feed ──────────────────────────────────────────────────────────────────
function McvPlaneFeed({
  items,
  selectedId,
  onSelect,
  vocab,
  receipts,
  signal,
  filter,
  onFilter,
  hideFilters
}) {
  const groups = WK_GROUP_ORDER.map(state => ({
    state,
    items: items.filter(i => i.state === state)
  })).filter(g => g.items.length > 0);
  const visible = filter ? groups.filter(g => g.state === filter) : groups;
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-plane-feed"
  }, !hideFilters && /*#__PURE__*/React.createElement("div", {
    className: "mc-chips"
  }, /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "mc-chip" + (filter === null ? " is-active" : ""),
    onClick: () => onFilter(null)
  }, "All"), groups.map(g => {
    const meta = WK_STATES[g.state];
    return /*#__PURE__*/React.createElement("button", {
      key: g.state,
      type: "button",
      className: "mc-chip" + (filter === g.state ? " is-active" : ""),
      onClick: () => onFilter(filter === g.state ? null : g.state)
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: WK_TONE_COLOR[meta.tone]
      }
    }), vocab === "system" ? meta.system : meta.plain, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-count"
    }, g.items.length));
  })), visible.map(g => {
    const meta = WK_STATES[g.state];
    return /*#__PURE__*/React.createElement("section", {
      key: g.state,
      className: "mc-group",
      "data-screen-label": "Group: " + meta.plain
    }, /*#__PURE__*/React.createElement("div", {
      className: "mc-group-header"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-group-label"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: WK_TONE_COLOR[meta.tone]
      }
    }), vocab === "system" ? meta.system : meta.plain), /*#__PURE__*/React.createElement("span", {
      className: "mc-group-count"
    }, g.items.length), /*#__PURE__*/React.createElement("span", {
      className: "mc-group-hint"
    }, WK_GROUP_HINTS[g.state])), /*#__PURE__*/React.createElement("div", {
      className: "mc-group-cards"
    }, g.items.map(item => /*#__PURE__*/React.createElement(McvLiveCard, {
      key: item.id,
      item: item,
      selected: item.id === selectedId,
      onSelect: onSelect,
      vocab: vocab,
      receipts: receipts,
      signal: signal
    }))));
  }));
}

// ── Board ─────────────────────────────────────────────────────────────────
const MCV_COLS = [{
  label: "Queued",
  states: ["proposed", "queued"],
  tone: "muted",
  hint: "Specs and next ticks"
}, {
  label: "Running",
  states: ["running"],
  tone: "active",
  hint: "Live in worktrees"
}, {
  label: "Needs you",
  states: ["review", "blocked"],
  tone: "review",
  hint: "At your gate or stuck"
}, {
  label: "Done",
  states: ["done"],
  tone: "done",
  hint: "The branch is the receipt"
}];
function McvPlaneBoard({
  items,
  selectedId,
  onSelect,
  vocab,
  receipts,
  signal
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-plane-board"
  }, MCV_COLS.map(col => {
    const colItems = items.filter(i => col.states.includes(i.state));
    return /*#__PURE__*/React.createElement("div", {
      key: col.label,
      className: "mcc-col",
      "data-screen-label": "Column: " + col.label
    }, /*#__PURE__*/React.createElement("div", {
      className: "mcc-col-header"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: WK_TONE_COLOR[col.tone]
      }
    }), col.label, /*#__PURE__*/React.createElement("span", {
      className: "mcc-col-count"
    }, colItems.length)), /*#__PURE__*/React.createElement("div", {
      className: "mcc-col-hint"
    }, col.hint), /*#__PURE__*/React.createElement("div", {
      className: "mcc-col-body"
    }, colItems.map(item => /*#__PURE__*/React.createElement(McvLiveCard, {
      key: item.id,
      item: item,
      selected: item.id === selectedId,
      onSelect: onSelect,
      vocab: vocab,
      receipts: receipts,
      signal: signal
    }))));
  }));
}

// ── List ──────────────────────────────────────────────────────────────────
function McvPlaneList({
  items,
  selectedId,
  onSelect,
  vocab,
  receipts
}) {
  const groups = WK_GROUP_ORDER.map(state => ({
    state,
    items: items.filter(i => i.state === state)
  })).filter(g => g.items.length > 0);
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-plane-list"
  }, groups.map(g => {
    const meta = WK_STATES[g.state];
    return /*#__PURE__*/React.createElement(React.Fragment, {
      key: g.state
    }, /*#__PURE__*/React.createElement("div", {
      className: "mcc-list-group"
    }, /*#__PURE__*/React.createElement("span", {
      className: "mc-chip-dot",
      style: {
        background: WK_TONE_COLOR[meta.tone]
      }
    }), vocab === "system" ? meta.system : meta.plain, /*#__PURE__*/React.createElement("span", {
      className: "mc-group-count"
    }, g.items.length), /*#__PURE__*/React.createElement("span", {
      className: "mc-group-hint"
    }, WK_GROUP_HINTS[g.state])), g.items.map(item => {
      const init = WK_INITIATIVES.find(i => i.id === item.initiative);
      return /*#__PURE__*/React.createElement("button", {
        key: item.id,
        type: "button",
        className: "mcc-rowitem" + (item.id === selectedId ? " is-selected" : ""),
        onClick: () => onSelect(item.id)
      }, item.state === "running" ? MCV_UNDERTOW_DOT : /*#__PURE__*/React.createElement("span", {
        className: "mc-chip-dot",
        style: {
          background: WK_TONE_COLOR[meta.tone]
        }
      }), /*#__PURE__*/React.createElement("span", {
        className: "mcc-row-title"
      }, item.title), /*#__PURE__*/React.createElement("span", {
        className: "mcc-row-crumb"
      }, init ? init.name : "", " \u203A ", item.project), receipts && item.run ? /*#__PURE__*/React.createElement("span", {
        className: "mc-receipt"
      }, item.run) : /*#__PURE__*/React.createElement("span", null), /*#__PURE__*/React.createElement("span", {
        className: "mcc-row-time"
      }, item.time));
    }));
  }));
}

// ── View toggle ───────────────────────────────────────────────────────────
const MCV_VIEWS = [{
  id: "feed",
  label: "Feed",
  icon: IcList
}, {
  id: "board",
  label: "Board",
  icon: IcBoard
}, {
  id: "list",
  label: "List",
  icon: IcSeam
}];
function McvViewToggle({
  view,
  onView
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "mcc-seg",
    role: "tablist"
  }, MCV_VIEWS.map(v => /*#__PURE__*/React.createElement("button", {
    key: v.id,
    type: "button",
    role: "tab",
    "aria-selected": view === v.id,
    className: "mcc-seg-btn" + (view === v.id ? " is-active" : ""),
    onClick: () => onView(v.id)
  }, /*#__PURE__*/React.createElement(v.icon, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    className: "mcc-seg-label"
  }, v.label))));
}
Object.assign(window, {
  McvLiveCard,
  McvPlaneFeed,
  McvPlaneBoard,
  McvPlaneList,
  McvViewToggle,
  MCV_UNDERTOW_DOT
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/WorkPlanes.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/WorkShell.jsx
try { (() => {
// Maestro · sidebar (the workspace tree + autonomy footer) + legacy top bar.
// Composes the standard components (DsAvatar, DsButton, DsAutonomyScoreboard)
// via ds-adapter.jsx instead of re-implementing them.

const IcFolder = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "M20 20a2 2 0 0 0 2-2V8a2 2 0 0 0-2-2h-7.9a2 2 0 0 1-1.69-.9L9.6 3.9A2 2 0 0 0 7.93 3H4a2 2 0 0 0-2 2v13a2 2 0 0 0 2 2Z"
}));
const IcFolderOpen = p => /*#__PURE__*/React.createElement(McIcon, p, /*#__PURE__*/React.createElement("path", {
  d: "m6 14 1.45-2.9A2 2 0 0 1 9.24 10H20a2 2 0 0 1 1.94 2.5l-1.55 6a2 2 0 0 1-1.94 1.5H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3.93a2 2 0 0 1 1.66.9l.82 1.2a2 2 0 0 0 1.66.9H18a2 2 0 0 1 2 2v2"
}));
function McAvatar({
  name,
  color,
  size = 22
}) {
  // Thin projection over the standard Avatar · keeps the app-local name.
  return /*#__PURE__*/React.createElement(DsAvatar, {
    name: name,
    color: color,
    size: size
  });
}
function McSidebar({
  attention,
  initiativeCounts,
  items = WK_ITEMS
}) {
  // The nav is the workspace itself: folders at any depth, live sessions as
  // dot comets, autonomy halts as badges. Initiative → folder, project →
  // subfolder (shown only while it has live or halted work).
  const sbText = {
    flex: 1,
    minWidth: 0,
    overflow: "hidden",
    textOverflow: "ellipsis",
    whiteSpace: "nowrap",
    textAlign: "left"
  };
  const folders = WK_INITIATIVES.map(init => {
    const list = items.filter(i => i.initiative === init.id);
    const projects = [...new Set(list.map(i => i.project))].map(p => {
      const pl = list.filter(i => i.project === p);
      return {
        name: p,
        live: pl.some(i => i.state === "running"),
        attn: pl.filter(i => WK_ATTENTION.includes(i.state)).length
      };
    }).filter(p => p.live || p.attn > 0);
    return {
      id: init.id,
      done: list.filter(i => i.state === "done").length,
      total: list.length,
      projects
    };
  });
  return /*#__PURE__*/React.createElement("aside", {
    className: "bv-sidebar",
    "data-screen-label": "Sidebar"
  }, /*#__PURE__*/React.createElement("button", {
    className: "bv-ws-switch",
    type: "button"
  }, /*#__PURE__*/React.createElement("img", {
    className: "bv-ws-logo",
    src: "../../assets/broomva-blackhole-logo.png",
    alt: ""
  }), /*#__PURE__*/React.createElement("span", {
    className: "bv-ws-name"
  }, "Broomva"), /*#__PURE__*/React.createElement(IcChevrons, {
    size: 14
  })), /*#__PURE__*/React.createElement("nav", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 2
    }
  }, /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item is-active",
    type: "button"
  }, /*#__PURE__*/React.createElement(IcBoard, null), "Maestro", attention > 0 && /*#__PURE__*/React.createElement("span", {
    className: "bv-sb-badge"
  }, attention)), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button"
  }, /*#__PURE__*/React.createElement(IcDoc, null), "Docs")), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-section-label"
  }, "Workspace"), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 2
    }
  }, folders.map(f => /*#__PURE__*/React.createElement(React.Fragment, {
    key: f.id
  }, /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button"
  }, f.projects.length > 0 ? /*#__PURE__*/React.createElement(IcFolderOpen, {
    size: 14
  }) : /*#__PURE__*/React.createElement(IcFolder, {
    size: 14
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, f.id), /*#__PURE__*/React.createElement("span", {
    className: "mc-init-progress"
  }, f.done, "/", f.total)), f.projects.map(p => /*#__PURE__*/React.createElement("button", {
    key: p.name,
    className: "bv-sb-item",
    type: "button",
    style: {
      paddingLeft: 28
    }
  }, p.live ? /*#__PURE__*/React.createElement("span", {
    className: "mcc-dot-tide",
    style: {
      width: 13,
      height: 13
    }
  }) : /*#__PURE__*/React.createElement(IcFolder, {
    size: 13
  }), /*#__PURE__*/React.createElement("span", {
    style: sbText
  }, p.name), p.attn > 0 && /*#__PURE__*/React.createElement("span", {
    className: "bv-sb-badge"
  }, p.attn)))))), /*#__PURE__*/React.createElement("div", {
    className: "bv-sb-spacer"
  }), /*#__PURE__*/React.createElement(DsAutonomyScoreboard, {
    title: "Unsupervised hours today \xB7 each notch is a human look",
    hours: "6h 24m",
    sub: "2 looks \xB7 longest run 3h 50m",
    segments: [{
      start: 0,
      width: 34
    }, {
      start: 36,
      width: 42
    }, {
      start: 80,
      width: 14,
      live: true
    }],
    notches: [34, 78]
  }), /*#__PURE__*/React.createElement("button", {
    className: "bv-sb-item",
    type: "button"
  }, /*#__PURE__*/React.createElement(McAvatar, {
    name: "Ana Diaz",
    color: "var(--bv-gray-600)",
    size: 18
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      textAlign: "left"
    }
  }, "Ana Diaz")));
}
function McTopBar({
  theme,
  onToggleTheme,
  onTick,
  ticking,
  canTick,
  onShowIdea
}) {
  return /*#__PURE__*/React.createElement("header", {
    className: "bv-top-bar",
    "data-screen-label": "Top bar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "mc-topbar-left"
  }, /*#__PURE__*/React.createElement("span", null, "Maestro")), /*#__PURE__*/React.createElement("div", {
    className: "mc-topbar-right"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-runner-pill",
    title: "The armed runner \xB7 the seam the scheduler dispatches through"
  }, /*#__PURE__*/React.createElement("span", {
    className: "mc-runner-dot"
  }), "runner ", /*#__PURE__*/React.createElement("code", null, "claude"), " \xB7 worktrees 2/2"), /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    variant: "secondary",
    onClick: onTick,
    disabled: ticking || !canTick,
    title: "One scheduler tick: observe, decide, act, judge, commit"
  }, /*#__PURE__*/React.createElement(IcPlay, {
    size: 16
  }), ticking ? "Ticking" : "Tick"), /*#__PURE__*/React.createElement(DsButton, {
    size: "sm",
    variant: "soft",
    onClick: onShowIdea
  }, "The idea"), /*#__PURE__*/React.createElement("button", {
    className: "bv-icon-btn",
    type: "button",
    onClick: onToggleTheme,
    "aria-label": theme === "dark" ? "Switch to light" : "Switch to dark",
    title: theme === "dark" ? "Switch to light" : "Switch to dark"
  }, theme === "dark" ? /*#__PURE__*/React.createElement(IcSun, {
    size: 18
  }) : /*#__PURE__*/React.createElement(IcMoon, {
    size: 18
  }))));
}
Object.assign(window, {
  McAvatar,
  McSidebar,
  McTopBar,
  IcFolder,
  IcFolderOpen
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/WorkShell.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/ds-adapter.jsx
try { (() => {
// Maestro · design-system bridge.
// The compiled bundle (../../_ds_bundle.js) carries the standard components;
// this adapter exposes them as Ds* globals so app files compose them instead
// of re-implementing. Add new standard components here, never ad-hoc copies.
(() => {
  const DS = window.BroomvaDesignSystem_5727d9;
  if (!DS) {
    console.error("ds-adapter: design-system bundle not loaded · check the _ds_bundle.js path in index.html");
    return;
  }
  window.DS = DS;
  Object.assign(window, {
    DsButton: DS.Button,
    DsIconButton: DS.IconButton,
    DsInput: DS.Input,
    DsCard: DS.Card,
    DsAvatar: DS.Avatar,
    DsStatusBadge: DS.StatusBadge,
    DsComposer: DS.Composer,
    // forms
    DsSelect: DS.Select,
    DsCheckbox: DS.Checkbox,
    DsRadio: DS.Radio,
    DsSwitch: DS.Switch,
    DsTextarea: DS.Textarea,
    DsField: DS.Field,
    // navigation
    DsTabs: DS.Tabs,
    DsSegmented: DS.Segmented,
    DsCommandPalette: DS.CommandPalette,
    // overlays
    DsDialog: DS.Dialog,
    DsConfirmDialog: DS.ConfirmDialog,
    DsMenu: DS.Menu,
    DsMenuItem: DS.MenuItem,
    DsMenuDivider: DS.MenuDivider,
    DsTooltip: DS.Tooltip,
    DsToast: DS.Toast,
    // work primitives
    DsWorkState: DS.WorkState,
    DsLifecycleRail: DS.LifecycleRail,
    DsReceipt: DS.Receipt,
    DsReceiptRow: DS.ReceiptRow,
    DsUndertow: DS.Undertow,
    DsRunCard: DS.RunCard,
    DsAutonomyScoreboard: DS.AutonomyScoreboard
  });
})();
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/ds-adapter.jsx", error: String((e && e.message) || e) }); }

// apps/maestro/tweaks-panel.jsx
try { (() => {
// @ds-adherence-ignore -- omelette starter scaffold (raw elements/hex/px by design)

/* BEGIN USAGE */
// tweaks-panel.jsx
// Reusable Tweaks shell + form-control helpers.
// Exports (to window): useTweaks, TweaksPanel, TweakSection, TweakRow, TweakSlider,
//   TweakToggle, TweakRadio, TweakSelect, TweakText, TweakNumber, TweakColor, TweakButton.
//
// Owns the host protocol (listens for __activate_edit_mode / __deactivate_edit_mode,
// posts __edit_mode_available / __edit_mode_set_keys / __edit_mode_dismissed) so
// individual prototypes don't re-roll it. Ships a consistent set of controls so you
// don't hand-draw <input type="range">, segmented radios, steppers, etc.
//
// Usage (in an HTML file that loads React + Babel):
//
//   const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
//     "primaryColor": "#D97757",
//     "palette": ["#D97757", "#29261b", "#f6f4ef"],
//     "fontSize": 16,
//     "density": "regular",
//     "dark": false
//   }/*EDITMODE-END*/;
//
//   function App() {
//     const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
//     return (
//       <div style={{ fontSize: t.fontSize, color: t.primaryColor }}>
//         Hello
//         <TweaksPanel>
//           <TweakSection label="Typography" />
//           <TweakSlider label="Font size" value={t.fontSize} min={10} max={32} unit="px"
//                        onChange={(v) => setTweak('fontSize', v)} />
//           <TweakRadio  label="Density" value={t.density}
//                        options={['compact', 'regular', 'comfy']}
//                        onChange={(v) => setTweak('density', v)} />
//           <TweakSection label="Theme" />
//           <TweakColor  label="Primary" value={t.primaryColor}
//                        options={['#D97757', '#2A6FDB', '#1F8A5B', '#7A5AE0']}
//                        onChange={(v) => setTweak('primaryColor', v)} />
//           <TweakColor  label="Palette" value={t.palette}
//                        options={[['#D97757', '#29261b', '#f6f4ef'],
//                                  ['#475569', '#0f172a', '#f1f5f9']]}
//                        onChange={(v) => setTweak('palette', v)} />
//           <TweakToggle label="Dark mode" value={t.dark}
//                        onChange={(v) => setTweak('dark', v)} />
//         </TweaksPanel>
//       </div>
//     );
//   }
//
// TweakRadio is the segmented control for 2–3 short options (auto-falls-back to
// TweakSelect past ~16/~10 chars per label); reach for TweakSelect directly when
// options are many or long. For color tweaks always curate 3-4 options rather than
// a free picker; an option can also be a whole 2–5 color palette (the stored value
// is the array). The Tweak* controls are a floor, not a ceiling — build custom
// controls inside the panel if a tweak calls for UI they don't cover.
/* END USAGE */
// ─────────────────────────────────────────────────────────────────────────────

const __TWEAKS_STYLE = `
  .twk-panel{position:fixed;right:16px;bottom:16px;z-index:2147483646;width:280px;
    max-height:calc(100vh - 32px);display:flex;flex-direction:column;
    transform:scale(var(--dc-inv-zoom,1));transform-origin:bottom right;
    background:rgba(250,249,247,.78);color:#29261b;
    -webkit-backdrop-filter:blur(24px) saturate(160%);backdrop-filter:blur(24px) saturate(160%);
    border:.5px solid rgba(255,255,255,.6);border-radius:14px;
    box-shadow:0 1px 0 rgba(255,255,255,.5) inset,0 12px 40px rgba(0,0,0,.18);
    font:11.5px/1.4 ui-sans-serif,system-ui,-apple-system,sans-serif;overflow:hidden}
  .twk-hd{display:flex;align-items:center;justify-content:space-between;
    padding:10px 8px 10px 14px;cursor:move;user-select:none}
  .twk-hd b{font-size:12px;font-weight:600;letter-spacing:.01em}
  .twk-x{appearance:none;border:0;background:transparent;color:rgba(41,38,27,.55);
    width:22px;height:22px;border-radius:6px;cursor:default;font-size:13px;line-height:1}
  .twk-x:hover{background:rgba(0,0,0,.06);color:#29261b}
  .twk-body{padding:2px 14px 14px;display:flex;flex-direction:column;gap:10px;
    overflow-y:auto;overflow-x:hidden;min-height:0;
    scrollbar-width:thin;scrollbar-color:rgba(0,0,0,.15) transparent}
  .twk-body::-webkit-scrollbar{width:8px}
  .twk-body::-webkit-scrollbar-track{background:transparent;margin:2px}
  .twk-body::-webkit-scrollbar-thumb{background:rgba(0,0,0,.15);border-radius:4px;
    border:2px solid transparent;background-clip:content-box}
  .twk-body::-webkit-scrollbar-thumb:hover{background:rgba(0,0,0,.25);
    border:2px solid transparent;background-clip:content-box}
  .twk-row{display:flex;flex-direction:column;gap:5px}
  .twk-row-h{flex-direction:row;align-items:center;justify-content:space-between;gap:10px}
  .twk-lbl{display:flex;justify-content:space-between;align-items:baseline;
    color:rgba(41,38,27,.72)}
  .twk-lbl>span:first-child{font-weight:500}
  .twk-val{color:rgba(41,38,27,.5);font-variant-numeric:tabular-nums}

  .twk-sect{font-size:10px;font-weight:600;letter-spacing:.06em;text-transform:uppercase;
    color:rgba(41,38,27,.45);padding:10px 0 0}
  .twk-sect:first-child{padding-top:0}

  .twk-field{appearance:none;box-sizing:border-box;width:100%;min-width:0;height:26px;padding:0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;
    background:rgba(255,255,255,.6);color:inherit;font:inherit;outline:none}
  .twk-field:focus{border-color:rgba(0,0,0,.25);background:rgba(255,255,255,.85)}
  select.twk-field{padding-right:22px;
    background-image:url("data:image/svg+xml;utf8,<svg xmlns='http://www.w3.org/2000/svg' width='10' height='6' viewBox='0 0 10 6'><path fill='rgba(0,0,0,.5)' d='M0 0h10L5 6z'/></svg>");
    background-repeat:no-repeat;background-position:right 8px center}

  .twk-slider{appearance:none;-webkit-appearance:none;width:100%;height:4px;margin:6px 0;
    border-radius:999px;background:rgba(0,0,0,.12);outline:none}
  .twk-slider::-webkit-slider-thumb{-webkit-appearance:none;appearance:none;
    width:14px;height:14px;border-radius:50%;background:#fff;
    border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}
  .twk-slider::-moz-range-thumb{width:14px;height:14px;border-radius:50%;
    background:#fff;border:.5px solid rgba(0,0,0,.12);box-shadow:0 1px 3px rgba(0,0,0,.2);cursor:default}

  .twk-seg{position:relative;display:flex;padding:2px;border-radius:8px;
    background:rgba(0,0,0,.06);user-select:none}
  .twk-seg-thumb{position:absolute;top:2px;bottom:2px;border-radius:6px;
    background:rgba(255,255,255,.9);box-shadow:0 1px 2px rgba(0,0,0,.12);
    transition:left .15s cubic-bezier(.3,.7,.4,1),width .15s}
  .twk-seg.dragging .twk-seg-thumb{transition:none}
  .twk-seg button{appearance:none;position:relative;z-index:1;flex:1;border:0;
    background:transparent;color:inherit;font:inherit;font-weight:500;min-height:22px;
    border-radius:6px;cursor:default;padding:4px 6px;line-height:1.2;
    overflow-wrap:anywhere}

  .twk-toggle{position:relative;width:32px;height:18px;border:0;border-radius:999px;
    background:rgba(0,0,0,.15);transition:background .15s;cursor:default;padding:0}
  .twk-toggle[data-on="1"]{background:#34c759}
  .twk-toggle i{position:absolute;top:2px;left:2px;width:14px;height:14px;border-radius:50%;
    background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.25);transition:transform .15s}
  .twk-toggle[data-on="1"] i{transform:translateX(14px)}

  .twk-num{display:flex;align-items:center;box-sizing:border-box;min-width:0;height:26px;padding:0 0 0 8px;
    border:.5px solid rgba(0,0,0,.1);border-radius:7px;background:rgba(255,255,255,.6)}
  .twk-num-lbl{font-weight:500;color:rgba(41,38,27,.6);cursor:ew-resize;
    user-select:none;padding-right:8px}
  .twk-num input{flex:1;min-width:0;height:100%;border:0;background:transparent;
    font:inherit;font-variant-numeric:tabular-nums;text-align:right;padding:0 8px 0 0;
    outline:none;color:inherit;-moz-appearance:textfield}
  .twk-num input::-webkit-inner-spin-button,.twk-num input::-webkit-outer-spin-button{
    -webkit-appearance:none;margin:0}
  .twk-num-unit{padding-right:8px;color:rgba(41,38,27,.45)}

  .twk-btn{appearance:none;height:26px;padding:0 12px;border:0;border-radius:7px;
    background:rgba(0,0,0,.78);color:#fff;font:inherit;font-weight:500;cursor:default}
  .twk-btn:hover{background:rgba(0,0,0,.88)}
  .twk-btn.secondary{background:rgba(0,0,0,.06);color:inherit}
  .twk-btn.secondary:hover{background:rgba(0,0,0,.1)}

  .twk-swatch{appearance:none;-webkit-appearance:none;width:56px;height:22px;
    border:.5px solid rgba(0,0,0,.1);border-radius:6px;padding:0;cursor:default;
    background:transparent;flex-shrink:0}
  .twk-swatch::-webkit-color-swatch-wrapper{padding:0}
  .twk-swatch::-webkit-color-swatch{border:0;border-radius:5.5px}
  .twk-swatch::-moz-color-swatch{border:0;border-radius:5.5px}

  .twk-chips{display:flex;gap:6px}
  .twk-chip{position:relative;appearance:none;flex:1;min-width:0;height:46px;
    padding:0;border:0;border-radius:6px;overflow:hidden;cursor:default;
    box-shadow:0 0 0 .5px rgba(0,0,0,.12),0 1px 2px rgba(0,0,0,.06);
    transition:transform .12s cubic-bezier(.3,.7,.4,1),box-shadow .12s}
  .twk-chip:hover{transform:translateY(-1px);
    box-shadow:0 0 0 .5px rgba(0,0,0,.18),0 4px 10px rgba(0,0,0,.12)}
  .twk-chip[data-on="1"]{box-shadow:0 0 0 1.5px rgba(0,0,0,.85),
    0 2px 6px rgba(0,0,0,.15)}
  .twk-chip>span{position:absolute;top:0;bottom:0;right:0;width:34%;
    display:flex;flex-direction:column;box-shadow:-1px 0 0 rgba(0,0,0,.1)}
  .twk-chip>span>i{flex:1;box-shadow:0 -1px 0 rgba(0,0,0,.1)}
  .twk-chip>span>i:first-child{box-shadow:none}
  .twk-chip svg{position:absolute;top:6px;left:6px;width:13px;height:13px;
    filter:drop-shadow(0 1px 1px rgba(0,0,0,.3))}
`;

// ── useTweaks ───────────────────────────────────────────────────────────────
// Single source of truth for tweak values. setTweak persists via the host
// (__edit_mode_set_keys → host rewrites the EDITMODE block on disk).
function useTweaks(defaults) {
  const [values, setValues] = React.useState(defaults);
  // Accepts either setTweak('key', value) or setTweak({ key: value, ... }) so a
  // useState-style call doesn't write a "[object Object]" key into the persisted
  // JSON block.
  const setTweak = React.useCallback((keyOrEdits, val) => {
    const edits = typeof keyOrEdits === 'object' && keyOrEdits !== null ? keyOrEdits : {
      [keyOrEdits]: val
    };
    setValues(prev => ({
      ...prev,
      ...edits
    }));
    window.parent.postMessage({
      type: '__edit_mode_set_keys',
      edits
    }, '*');
    // Same-window signal so in-page listeners (deck-stage rail thumbnails)
    // can react — the parent message only reaches the host, not peers.
    window.dispatchEvent(new CustomEvent('tweakchange', {
      detail: edits
    }));
  }, []);
  return [values, setTweak];
}

// ── TweaksPanel ─────────────────────────────────────────────────────────────
// Floating shell. Registers the protocol listener BEFORE announcing
// availability — if the announce ran first, the host's activate could land
// before our handler exists and the toolbar toggle would silently no-op.
// The close button posts __edit_mode_dismissed so the host's toolbar toggle
// flips off in lockstep; the host echoes __deactivate_edit_mode back which
// is what actually hides the panel.
function TweaksPanel({
  title = 'Tweaks',
  children
}) {
  const [open, setOpen] = React.useState(false);
  const dragRef = React.useRef(null);
  const offsetRef = React.useRef({
    x: 16,
    y: 16
  });
  const PAD = 16;
  const clampToViewport = React.useCallback(() => {
    const panel = dragRef.current;
    if (!panel) return;
    const w = panel.offsetWidth,
      h = panel.offsetHeight;
    const maxRight = Math.max(PAD, window.innerWidth - w - PAD);
    const maxBottom = Math.max(PAD, window.innerHeight - h - PAD);
    offsetRef.current = {
      x: Math.min(maxRight, Math.max(PAD, offsetRef.current.x)),
      y: Math.min(maxBottom, Math.max(PAD, offsetRef.current.y))
    };
    panel.style.right = offsetRef.current.x + 'px';
    panel.style.bottom = offsetRef.current.y + 'px';
  }, []);
  React.useEffect(() => {
    if (!open) return;
    clampToViewport();
    if (typeof ResizeObserver === 'undefined') {
      window.addEventListener('resize', clampToViewport);
      return () => window.removeEventListener('resize', clampToViewport);
    }
    const ro = new ResizeObserver(clampToViewport);
    ro.observe(document.documentElement);
    return () => ro.disconnect();
  }, [open, clampToViewport]);
  React.useEffect(() => {
    const onMsg = e => {
      const t = e?.data?.type;
      if (t === '__activate_edit_mode') setOpen(true);else if (t === '__deactivate_edit_mode') setOpen(false);
    };
    window.addEventListener('message', onMsg);
    window.parent.postMessage({
      type: '__edit_mode_available'
    }, '*');
    return () => window.removeEventListener('message', onMsg);
  }, []);
  const dismiss = () => {
    setOpen(false);
    window.parent.postMessage({
      type: '__edit_mode_dismissed'
    }, '*');
  };
  const onDragStart = e => {
    const panel = dragRef.current;
    if (!panel) return;
    const r = panel.getBoundingClientRect();
    const sx = e.clientX,
      sy = e.clientY;
    const startRight = window.innerWidth - r.right;
    const startBottom = window.innerHeight - r.bottom;
    const move = ev => {
      offsetRef.current = {
        x: startRight - (ev.clientX - sx),
        y: startBottom - (ev.clientY - sy)
      };
      clampToViewport();
    };
    const up = () => {
      window.removeEventListener('mousemove', move);
      window.removeEventListener('mouseup', up);
    };
    window.addEventListener('mousemove', move);
    window.addEventListener('mouseup', up);
  };
  if (!open) return null;
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("style", null, __TWEAKS_STYLE), /*#__PURE__*/React.createElement("div", {
    ref: dragRef,
    className: "twk-panel",
    "data-omelette-chrome": "",
    style: {
      right: offsetRef.current.x,
      bottom: offsetRef.current.y
    }
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-hd",
    onMouseDown: onDragStart
  }, /*#__PURE__*/React.createElement("b", null, title), /*#__PURE__*/React.createElement("button", {
    className: "twk-x",
    "aria-label": "Close tweaks",
    onMouseDown: e => e.stopPropagation(),
    onClick: dismiss
  }, "\u2715")), /*#__PURE__*/React.createElement("div", {
    className: "twk-body"
  }, children)));
}

// ── Layout helpers ──────────────────────────────────────────────────────────

function TweakSection({
  label,
  children
}) {
  return /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement("div", {
    className: "twk-sect"
  }, label), children);
}
function TweakRow({
  label,
  value,
  children,
  inline = false
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: inline ? 'twk-row twk-row-h' : 'twk-row'
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-lbl"
  }, /*#__PURE__*/React.createElement("span", null, label), value != null && /*#__PURE__*/React.createElement("span", {
    className: "twk-val"
  }, value)), children);
}

// ── Controls ────────────────────────────────────────────────────────────────

function TweakSlider({
  label,
  value,
  min = 0,
  max = 100,
  step = 1,
  unit = '',
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label,
    value: `${value}${unit}`
  }, /*#__PURE__*/React.createElement("input", {
    type: "range",
    className: "twk-slider",
    min: min,
    max: max,
    step: step,
    value: value,
    onChange: e => onChange(Number(e.target.value))
  }));
}
function TweakToggle({
  label,
  value,
  onChange
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "twk-row twk-row-h"
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-lbl"
  }, /*#__PURE__*/React.createElement("span", null, label)), /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: "twk-toggle",
    "data-on": value ? '1' : '0',
    role: "switch",
    "aria-checked": !!value,
    onClick: () => onChange(!value)
  }, /*#__PURE__*/React.createElement("i", null)));
}
function TweakRadio({
  label,
  value,
  options,
  onChange
}) {
  const trackRef = React.useRef(null);
  const [dragging, setDragging] = React.useState(false);
  // The active value is read by pointer-move handlers attached for the lifetime
  // of a drag — ref it so a stale closure doesn't fire onChange for every move.
  const valueRef = React.useRef(value);
  valueRef.current = value;

  // Segments wrap mid-word once per-segment width runs out. The track is
  // ~248px (280 panel − 28 body pad − 4 seg pad), each button loses 12px
  // to its own padding, and 11.5px system-ui averages ~6.3px/char — so 2
  // options fit ~16 chars each, 3 fit ~10. Past that (or >3 options), fall
  // back to a dropdown rather than wrap.
  const labelLen = o => String(typeof o === 'object' ? o.label : o).length;
  const maxLen = options.reduce((m, o) => Math.max(m, labelLen(o)), 0);
  const fitsAsSegments = maxLen <= ({
    2: 16,
    3: 10
  }[options.length] ?? 0);
  if (!fitsAsSegments) {
    // <select> emits strings — map back to the original option value so the
    // fallback stays type-preserving (numbers, booleans) like the segment path.
    const resolve = s => {
      const m = options.find(o => String(typeof o === 'object' ? o.value : o) === s);
      return m === undefined ? s : typeof m === 'object' ? m.value : m;
    };
    return /*#__PURE__*/React.createElement(TweakSelect, {
      label: label,
      value: value,
      options: options,
      onChange: s => onChange(resolve(s))
    });
  }
  const opts = options.map(o => typeof o === 'object' ? o : {
    value: o,
    label: o
  });
  const idx = Math.max(0, opts.findIndex(o => o.value === value));
  const n = opts.length;
  const segAt = clientX => {
    const r = trackRef.current.getBoundingClientRect();
    const inner = r.width - 4;
    const i = Math.floor((clientX - r.left - 2) / inner * n);
    return opts[Math.max(0, Math.min(n - 1, i))].value;
  };
  const onPointerDown = e => {
    setDragging(true);
    const v0 = segAt(e.clientX);
    if (v0 !== valueRef.current) onChange(v0);
    const move = ev => {
      if (!trackRef.current) return;
      const v = segAt(ev.clientX);
      if (v !== valueRef.current) onChange(v);
    };
    const up = () => {
      setDragging(false);
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("div", {
    ref: trackRef,
    role: "radiogroup",
    onPointerDown: onPointerDown,
    className: dragging ? 'twk-seg dragging' : 'twk-seg'
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-seg-thumb",
    style: {
      left: `calc(2px + ${idx} * (100% - 4px) / ${n})`,
      width: `calc((100% - 4px) / ${n})`
    }
  }), opts.map(o => /*#__PURE__*/React.createElement("button", {
    key: o.value,
    type: "button",
    role: "radio",
    "aria-checked": o.value === value
  }, o.label))));
}
function TweakSelect({
  label,
  value,
  options,
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("select", {
    className: "twk-field",
    value: value,
    onChange: e => onChange(e.target.value)
  }, options.map(o => {
    const v = typeof o === 'object' ? o.value : o;
    const l = typeof o === 'object' ? o.label : o;
    return /*#__PURE__*/React.createElement("option", {
      key: v,
      value: v
    }, l);
  })));
}
function TweakText({
  label,
  value,
  placeholder,
  onChange
}) {
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("input", {
    className: "twk-field",
    type: "text",
    value: value,
    placeholder: placeholder,
    onChange: e => onChange(e.target.value)
  }));
}
function TweakNumber({
  label,
  value,
  min,
  max,
  step = 1,
  unit = '',
  onChange
}) {
  const clamp = n => {
    if (min != null && n < min) return min;
    if (max != null && n > max) return max;
    return n;
  };
  const startRef = React.useRef({
    x: 0,
    val: 0
  });
  const onScrubStart = e => {
    e.preventDefault();
    startRef.current = {
      x: e.clientX,
      val: value
    };
    const decimals = (String(step).split('.')[1] || '').length;
    const move = ev => {
      const dx = ev.clientX - startRef.current.x;
      const raw = startRef.current.val + dx * step;
      const snapped = Math.round(raw / step) * step;
      onChange(clamp(Number(snapped.toFixed(decimals))));
    };
    const up = () => {
      window.removeEventListener('pointermove', move);
      window.removeEventListener('pointerup', up);
    };
    window.addEventListener('pointermove', move);
    window.addEventListener('pointerup', up);
  };
  return /*#__PURE__*/React.createElement("div", {
    className: "twk-num"
  }, /*#__PURE__*/React.createElement("span", {
    className: "twk-num-lbl",
    onPointerDown: onScrubStart
  }, label), /*#__PURE__*/React.createElement("input", {
    type: "number",
    value: value,
    min: min,
    max: max,
    step: step,
    onChange: e => onChange(clamp(Number(e.target.value)))
  }), unit && /*#__PURE__*/React.createElement("span", {
    className: "twk-num-unit"
  }, unit));
}

// Relative-luminance contrast pick — checkmarks drawn over a swatch need to
// read on both #111 and #fafafa without per-option configuration. Hex input
// only (#rgb / #rrggbb); named or rgb()/hsl() colors fall through to "light".
function __twkIsLight(hex) {
  const h = String(hex).replace('#', '');
  const x = h.length === 3 ? h.replace(/./g, c => c + c) : h.padEnd(6, '0');
  const n = parseInt(x.slice(0, 6), 16);
  if (Number.isNaN(n)) return true;
  const r = n >> 16 & 255,
    g = n >> 8 & 255,
    b = n & 255;
  return r * 299 + g * 587 + b * 114 > 148000;
}
const __TwkCheck = ({
  light
}) => /*#__PURE__*/React.createElement("svg", {
  viewBox: "0 0 14 14",
  "aria-hidden": "true"
}, /*#__PURE__*/React.createElement("path", {
  d: "M3 7.2 5.8 10 11 4.2",
  fill: "none",
  strokeWidth: "2.2",
  strokeLinecap: "round",
  strokeLinejoin: "round",
  stroke: light ? 'rgba(0,0,0,.78)' : '#fff'
}));

// TweakColor — curated color/palette picker. Each option is either a single
// hex string or an array of 1-5 hex strings; the card adapts — a lone color
// renders solid, a palette renders colors[0] as the hero (left ~2/3) with the
// rest stacked in a sharp column on the right. onChange emits the
// option in the shape it was passed (string stays string, array stays array).
// Without options it falls back to the native color input for back-compat.
function TweakColor({
  label,
  value,
  options,
  onChange
}) {
  if (!options || !options.length) {
    return /*#__PURE__*/React.createElement("div", {
      className: "twk-row twk-row-h"
    }, /*#__PURE__*/React.createElement("div", {
      className: "twk-lbl"
    }, /*#__PURE__*/React.createElement("span", null, label)), /*#__PURE__*/React.createElement("input", {
      type: "color",
      className: "twk-swatch",
      value: value,
      onChange: e => onChange(e.target.value)
    }));
  }
  // Native <input type=color> emits lowercase hex per the HTML spec, so
  // compare case-insensitively. String() guards JSON.stringify(undefined),
  // which returns the primitive undefined (no .toLowerCase).
  const key = o => String(JSON.stringify(o)).toLowerCase();
  const cur = key(value);
  return /*#__PURE__*/React.createElement(TweakRow, {
    label: label
  }, /*#__PURE__*/React.createElement("div", {
    className: "twk-chips",
    role: "radiogroup"
  }, options.map((o, i) => {
    const colors = Array.isArray(o) ? o : [o];
    const [hero, ...rest] = colors;
    const sup = rest.slice(0, 4);
    const on = key(o) === cur;
    return /*#__PURE__*/React.createElement("button", {
      key: i,
      type: "button",
      className: "twk-chip",
      role: "radio",
      "aria-checked": on,
      "data-on": on ? '1' : '0',
      "aria-label": colors.join(', '),
      title: colors.join(' · '),
      style: {
        background: hero
      },
      onClick: () => onChange(o)
    }, sup.length > 0 && /*#__PURE__*/React.createElement("span", null, sup.map((c, j) => /*#__PURE__*/React.createElement("i", {
      key: j,
      style: {
        background: c
      }
    }))), on && /*#__PURE__*/React.createElement(__TwkCheck, {
      light: __twkIsLight(hero)
    }));
  })));
}
function TweakButton({
  label,
  onClick,
  secondary = false
}) {
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    className: secondary ? 'twk-btn secondary' : 'twk-btn',
    onClick: onClick
  }, label);
}
Object.assign(window, {
  useTweaks,
  TweaksPanel,
  TweakSection,
  TweakRow,
  TweakSlider,
  TweakToggle,
  TweakRadio,
  TweakSelect,
  TweakText,
  TweakNumber,
  TweakColor,
  TweakButton
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "apps/maestro/tweaks-panel.jsx", error: String((e && e.message) || e) }); }

// components/core/Avatar.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Circular avatar: initials or glyph over a tinted accent. */
function Avatar({
  name = "",
  color = "var(--bv-blue)",
  size = 22,
  src,
  style,
  ...rest
}) {
  const initials = name.trim().split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
  return /*#__PURE__*/React.createElement("span", _extends({
    title: name,
    style: {
      width: size,
      height: size,
      borderRadius: size / 2,
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      background: src ? "transparent" : color,
      color: "var(--bv-white)",
      fontSize: Math.max(9, size * 0.42),
      fontWeight: 600,
      flexShrink: 0,
      overflow: "hidden",
      userSelect: "none",
      ...style
    }
  }, rest), src ? /*#__PURE__*/React.createElement("img", {
    src: src,
    alt: name,
    style: {
      width: "100%",
      height: "100%",
      objectFit: "cover"
    }
  }) : initials);
}
Object.assign(__ds_scope, { Avatar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Avatar.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Pill-shaped action button. Primary is ink fill (dark blue, never black);
   hover lightens one step or frosts blue. No scale, no transform. */
function Button({
  variant = "primary",
  size = "md",
  disabled = false,
  children,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const sizes = {
    sm: {
      height: 28,
      padding: "0 10px",
      fontSize: 12
    },
    md: {
      height: "var(--bv-h-btn)",
      padding: "0 14px",
      fontSize: 14
    },
    lg: {
      height: "var(--bv-h-btn-lg)",
      padding: "0 18px",
      fontSize: 14
    }
  };
  const variants = {
    primary: {
      background: disabled ? "var(--bv-gray-300)" : hover ? "var(--bv-ink-hover)" : "var(--primary)",
      color: "var(--primary-foreground)",
      border: "1px solid transparent"
    },
    secondary: {
      background: hover ? "var(--bv-frost-4)" : "var(--card)",
      color: "var(--foreground)",
      border: "1px solid var(--bv-border-15)"
    },
    soft: {
      background: hover ? "var(--bv-frost-8)" : "var(--bv-canvas-soft)",
      color: "var(--foreground)",
      border: "1px solid transparent"
    },
    ghost: {
      background: hover ? "var(--bv-frost-8)" : "transparent",
      color: "var(--foreground)",
      border: "1px solid transparent"
    }
  };
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    disabled: disabled,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      borderRadius: "var(--bv-radius-full)",
      fontFamily: "inherit",
      fontWeight: 500,
      whiteSpace: "nowrap",
      cursor: disabled ? "not-allowed" : "pointer",
      transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
      ...sizes[size],
      ...variants[variant],
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Matte card. rounded-12, whisper border, edge shadow at rest, blue-tinted
   lift on hover (when interactive). When running, the card stays matte and
   wears the Undertow: a contained 4px halo frame (breathing pools, counter-
   phase tide, faint 9s orbit). Requires styles.css (tokens/motion.css). */
function Card({
  interactive = false,
  running = false,
  children,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  const inner = /*#__PURE__*/React.createElement("div", _extends({
    onMouseEnter: interactive ? () => setHover(true) : undefined,
    onMouseLeave: interactive ? () => setHover(false) : undefined,
    style: {
      background: "var(--card)",
      border: "1px solid var(--bv-border-5)",
      borderRadius: "var(--bv-radius-xl)",
      boxShadow: hover ? "var(--bv-shadow-card-hover)" : "var(--bv-shadow-edge)",
      padding: "12px 14px",
      display: "flex",
      flexDirection: "column",
      gap: 8,
      cursor: interactive ? "pointer" : "default",
      transition: "box-shadow var(--bv-dur-fast) var(--bv-ease-standard)",
      ...style
    }
  }, rest), children);
  if (!running) return inner;
  return /*#__PURE__*/React.createElement("div", {
    className: "bv-undertow"
  }, /*#__PURE__*/React.createElement("span", {
    className: "bv-undertow-orbit"
  }), inner);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/Composer.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* The composer: rounded-28 glass capsule with the frosted-blue halo.
   The single dramatic depth cue in the product. */
function Composer({
  placeholder = "Message Broomva",
  value,
  onChange,
  onSend,
  leading,
  style,
  ...rest
}) {
  const [inner, setInner] = React.useState("");
  const text = value !== undefined ? value : inner;
  const set = onChange || setInner;
  const send = () => {
    if (text.trim() && onSend) onSend(text.trim());
    if (value === undefined) setInner("");
  };
  return /*#__PURE__*/React.createElement("div", _extends({
    className: "bv-glass-composer",
    style: {
      borderRadius: "var(--bv-radius-composer)",
      padding: 10,
      display: "grid",
      gridTemplateColumns: leading ? "auto 1fr auto" : "1fr auto",
      alignItems: "center",
      gap: 4,
      ...style
    }
  }, rest), leading, /*#__PURE__*/React.createElement("input", {
    value: text,
    onChange: e => set(e.target.value),
    onKeyDown: e => {
      if (e.key === "Enter") send();
    },
    placeholder: placeholder,
    style: {
      border: "none",
      background: "transparent",
      outline: "none",
      font: "inherit",
      fontSize: 16,
      padding: "8px 10px",
      color: "var(--foreground)",
      minWidth: 0
    }
  }), /*#__PURE__*/React.createElement("button", {
    type: "button",
    "aria-label": "Send",
    onClick: send,
    style: {
      width: 36,
      height: 36,
      borderRadius: 18,
      background: "var(--primary)",
      color: "var(--primary-foreground)",
      border: "none",
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("svg", {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: {
      width: 18,
      height: 18
    }
  }, /*#__PURE__*/React.createElement("path", {
    d: "M12 19V5"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m5 12 7-7 7 7"
  }))));
}
Object.assign(__ds_scope, { Composer });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Composer.jsx", error: String((e && e.message) || e) }); }

// components/core/DotComet.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* The tidepool dot — the running signal at dot scale. The Undertow's
   blue → ice weather drifts inside the circle: one motion language at every
   scale. For list rows, status lines, chips, and the bench in the chrome.
   Requires styles.css (tokens/motion.css). */
function DotComet({
  size = 15,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("span", _extends({
    className: "bv-dot-live",
    style: {
      width: size,
      height: size,
      ...style
    },
    "aria-hidden": "true"
  }, rest));
}
Object.assign(__ds_scope, { DotComet });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/DotComet.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* 36px square ghost button for a single icon. Hover = frosted blue fill. */
function IconButton({
  label,
  children,
  style,
  ...rest
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    "aria-label": label,
    title: label,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      width: "var(--bv-h-icon)",
      height: "var(--bv-h-icon)",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      borderRadius: "var(--bv-radius-lg)",
      border: "none",
      background: hover ? "var(--bv-frost-8)" : "transparent",
      color: "var(--bv-gray-700)",
      cursor: "pointer",
      flexShrink: 0,
      transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
      ...style
    }
  }, rest), children);
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/core/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Text input: rounded-md, gray edge, ai-blue focus ring (via :focus-visible). */
function Input({
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("input", _extends({
    style: {
      height: "var(--bv-h-btn)",
      padding: "0 12px",
      borderRadius: "var(--bv-radius-md)",
      border: "1px solid var(--input)",
      background: "var(--card)",
      color: "var(--foreground)",
      font: "inherit",
      fontSize: 14,
      outline: "none",
      ...style
    }
  }, rest));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Input.jsx", error: String((e && e.message) || e) }); }

// components/core/StatusBadge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Status pill: soft gray capsule + colored dot + sentence-case label. */
function StatusBadge({
  status = "info",
  pulse = false,
  children,
  style,
  ...rest
}) {
  const colors = {
    success: "var(--bv-success)",
    info: "var(--bv-info)",
    warning: "var(--bv-warning)",
    danger: "var(--bv-danger)",
    neutral: "var(--bv-gray-400)"
  };
  return /*#__PURE__*/React.createElement("span", _extends({
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 7,
      height: 26,
      padding: "0 12px",
      borderRadius: "var(--bv-radius-full)",
      background: "var(--bv-canvas-soft)",
      fontSize: 12,
      fontWeight: 500,
      color: "var(--foreground)",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("style", null, `@keyframes bv-pulse { 0%,100% { opacity: 0.45; transform: scale(1); } 50% { opacity: 1; transform: scale(1.08); } }`), /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: 99,
      flexShrink: 0,
      background: colors[status] || colors.info,
      animation: pulse ? "bv-pulse 1s ease-in-out infinite" : "none"
    }
  }), children);
}
Object.assign(__ds_scope, { StatusBadge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/StatusBadge.jsx", error: String((e && e.message) || e) }); }

// components/forms/Checkbox.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* 18px square, chip radius. Checked = ink fill with a white check.
   Hover frosts blue. Label is sentence case, 14px. */
function Checkbox({
  checked,
  defaultChecked = false,
  onChange,
  disabled = false,
  children,
  style,
  ...rest
}) {
  const [inner, setInner] = React.useState(defaultChecked);
  const [hover, setHover] = React.useState(false);
  const isOn = checked !== undefined ? checked : inner;
  const toggle = () => {
    if (disabled) return;
    if (checked === undefined) setInner(!isOn);
    onChange && onChange(!isOn);
  };
  return /*#__PURE__*/React.createElement("label", {
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 8,
      fontSize: 14,
      color: disabled ? "var(--bv-gray-400)" : "var(--foreground)",
      cursor: disabled ? "not-allowed" : "pointer",
      userSelect: "none",
      ...style
    }
  }, /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    role: "checkbox",
    "aria-checked": isOn,
    disabled: disabled,
    onClick: toggle,
    style: {
      width: 18,
      height: 18,
      flexShrink: 0,
      padding: 0,
      borderRadius: "var(--bv-radius-chip)",
      border: isOn ? "1px solid transparent" : "1px solid var(--bv-border-25)",
      background: isOn ? disabled ? "var(--bv-gray-300)" : "var(--primary)" : hover && !disabled ? "var(--bv-frost-8)" : "var(--card)",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      cursor: "inherit",
      transition: "background var(--bv-dur-fast) var(--bv-ease-standard)"
    }
  }, rest), isOn && /*#__PURE__*/React.createElement("svg", {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "var(--primary-foreground)",
    strokeWidth: "3",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: {
      width: 12,
      height: 12
    }
  }, /*#__PURE__*/React.createElement("path", {
    d: "M20 6 9 17l-5-5"
  }))), children);
}
Object.assign(__ds_scope, { Checkbox });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Checkbox.jsx", error: String((e && e.message) || e) }); }

// components/forms/Field.jsx
try { (() => {
/* Label + control + hint/error. Labels are sentence case, 13px medium.
   Errors use --bv-danger text only; the control never turns red. */
function Field({
  label,
  hint,
  error,
  children,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      flexDirection: "column",
      gap: 6,
      ...style
    }
  }, label && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13,
      fontWeight: 500,
      color: "var(--foreground)"
    }
  }, label), children, error ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      color: "var(--bv-danger)"
    }
  }, error) : hint ? /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      color: "var(--muted-foreground)"
    }
  }, hint) : null);
}
Object.assign(__ds_scope, { Field });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Field.jsx", error: String((e && e.message) || e) }); }

// components/forms/Radio.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* 18px circle. Checked = ink ring with an ink core. Hover frosts blue. */
function Radio({
  checked,
  defaultChecked = false,
  onChange,
  disabled = false,
  children,
  style,
  ...rest
}) {
  const [inner, setInner] = React.useState(defaultChecked);
  const [hover, setHover] = React.useState(false);
  const isOn = checked !== undefined ? checked : inner;
  const pick = () => {
    if (disabled || isOn) return;
    if (checked === undefined) setInner(true);
    onChange && onChange(true);
  };
  return /*#__PURE__*/React.createElement("label", {
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 8,
      fontSize: 14,
      color: disabled ? "var(--bv-gray-400)" : "var(--foreground)",
      cursor: disabled ? "not-allowed" : "pointer",
      userSelect: "none",
      ...style
    }
  }, /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    role: "radio",
    "aria-checked": isOn,
    disabled: disabled,
    onClick: pick,
    style: {
      width: 18,
      height: 18,
      flexShrink: 0,
      padding: 0,
      borderRadius: "var(--bv-radius-full)",
      border: isOn ? "5.5px solid " + (disabled ? "var(--bv-gray-300)" : "var(--primary)") : "1px solid var(--bv-border-25)",
      background: isOn ? "var(--primary-foreground)" : hover && !disabled ? "var(--bv-frost-8)" : "var(--card)",
      cursor: "inherit",
      transition: "background var(--bv-dur-fast) var(--bv-ease-standard)"
    }
  }, rest)), children);
}
Object.assign(__ds_scope, { Radio });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Radio.jsx", error: String((e && e.message) || e) }); }

// components/forms/Select.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Native select styled like Input: rounded-md, gray edge, ai-blue focus
   ring via :focus-visible, lucide chevron in currentColor. */
function Select({
  options = [],
  placeholder,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      position: "relative",
      display: "inline-flex",
      ...style
    }
  }, /*#__PURE__*/React.createElement("select", _extends({
    defaultValue: rest.value === undefined && placeholder ? "" : undefined,
    style: {
      height: "var(--bv-h-btn)",
      padding: "0 32px 0 12px",
      borderRadius: "var(--bv-radius-md)",
      border: "1px solid var(--input)",
      background: "var(--card)",
      color: "var(--foreground)",
      font: "inherit",
      fontSize: 14,
      outline: "none",
      appearance: "none",
      WebkitAppearance: "none",
      cursor: "pointer",
      width: "100%"
    }
  }, rest), placeholder && /*#__PURE__*/React.createElement("option", {
    value: "",
    disabled: true
  }, placeholder), options.map(o => {
    const opt = typeof o === "string" ? {
      value: o,
      label: o
    } : o;
    return /*#__PURE__*/React.createElement("option", {
      key: opt.value,
      value: opt.value
    }, opt.label);
  })), /*#__PURE__*/React.createElement("svg", {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: {
      width: 16,
      height: 16,
      position: "absolute",
      right: 10,
      top: "50%",
      transform: "translateY(-50%)",
      pointerEvents: "none",
      color: "var(--bv-gray-500)"
    }
  }, /*#__PURE__*/React.createElement("path", {
    d: "m6 9 6 6 6-6"
  })));
}
Object.assign(__ds_scope, { Select });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Select.jsx", error: String((e && e.message) || e) }); }

// components/forms/Switch.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* 38×22 track, full radius — the Maestro settings switch. On = ai-blue
   (the one control where the accent means "armed"); off = gray track
   (--bv-switch-off handles dark). White thumb slides 150ms; no bounce. */
function Switch({
  checked,
  defaultChecked = false,
  onChange,
  disabled = false,
  style,
  ...rest
}) {
  const [inner, setInner] = React.useState(defaultChecked);
  const isOn = checked !== undefined ? checked : inner;
  const toggle = () => {
    if (disabled) return;
    if (checked === undefined) setInner(!isOn);
    onChange && onChange(!isOn);
  };
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    role: "switch",
    "aria-checked": isOn,
    disabled: disabled,
    onClick: toggle,
    style: {
      position: "relative",
      width: 38,
      height: 22,
      flexShrink: 0,
      borderRadius: 99,
      border: "none",
      padding: 0,
      background: isOn ? "var(--bv-blue)" : "var(--bv-switch-off, var(--bv-gray-300))",
      opacity: disabled ? 0.55 : 1,
      cursor: disabled ? "not-allowed" : "pointer",
      transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      top: 2,
      left: 2,
      width: 18,
      height: 18,
      borderRadius: 99,
      background: "var(--bv-white)",
      boxShadow: "0 1px 2px oklch(0.2 0.04 265 / 0.25)",
      transform: isOn ? "translateX(16px)" : "translateX(0)",
      transition: "transform var(--bv-dur-fast) var(--bv-ease-standard)"
    }
  }));
}
Object.assign(__ds_scope, { Switch });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Switch.jsx", error: String((e && e.message) || e) }); }

// components/forms/Textarea.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Multiline input: same recipe as Input, vertical resize only. */
function Textarea({
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("textarea", _extends({
    rows: 3,
    style: {
      padding: "8px 12px",
      minHeight: 72,
      borderRadius: "var(--bv-radius-md)",
      border: "1px solid var(--input)",
      background: "var(--card)",
      color: "var(--foreground)",
      font: "inherit",
      fontSize: 14,
      lineHeight: 1.5,
      outline: "none",
      resize: "vertical",
      width: "100%",
      boxSizing: "border-box",
      ...style
    }
  }, rest));
}
Object.assign(__ds_scope, { Textarea });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Textarea.jsx", error: String((e && e.message) || e) }); }

// components/navigation/CommandPalette.jsx
try { (() => {
/* The command palette combobox — earned glass (.bv-glass-heavy from
   tokens/glass.css). Input row + grouped results + kbd hints + footer.
   Render it inside a fixed scrim (blue-black, never gray) or standalone
   in a card for specimens. Static: filtering is the caller's job. */
function CommandPalette({
  query = "",
  placeholder = "Type a command or search…",
  groups = [],
  activeId,
  onQuery,
  onPick,
  footer = true,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "bv-glass-heavy",
    style: {
      width: "min(560px, 100%)",
      display: "flex",
      flexDirection: "column",
      overflow: "hidden",
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      flexShrink: 0,
      display: "flex",
      alignItems: "center",
      gap: 10,
      height: 40,
      padding: "0 13px",
      borderBottom: "1px solid var(--bv-border-5)"
    }
  }, /*#__PURE__*/React.createElement("svg", {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "var(--bv-blue)",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: {
      width: 15,
      height: 15,
      flexShrink: 0
    }
  }, /*#__PURE__*/React.createElement("circle", {
    cx: "11",
    cy: "11",
    r: "8"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m21 21-4.3-4.3"
  })), /*#__PURE__*/React.createElement("input", {
    value: query,
    placeholder: placeholder,
    onChange: e => onQuery && onQuery(e.target.value),
    style: {
      flex: 1,
      minWidth: 0,
      border: "none",
      background: "transparent",
      outline: "none",
      font: "inherit",
      fontSize: 14,
      color: "var(--foreground)"
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      flexShrink: 0,
      fontSize: 10.5,
      fontWeight: 500,
      color: "var(--muted-foreground)",
      padding: "2px 7px",
      border: "1px solid var(--bv-border-15)",
      borderRadius: 5
    }
  }, "esc")), /*#__PURE__*/React.createElement("div", {
    style: {
      overflowY: "auto",
      padding: 6,
      display: "flex",
      flexDirection: "column",
      maxHeight: "52vh"
    }
  }, groups.length === 0 && /*#__PURE__*/React.createElement("div", {
    style: {
      padding: "26px 12px",
      textAlign: "center",
      fontSize: 13,
      color: "var(--muted-foreground)"
    }
  }, "Nothing matches"), groups.map((g, gi) => /*#__PURE__*/React.createElement(React.Fragment, {
    key: gi
  }, g.label && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 11,
      fontWeight: 500,
      color: "var(--muted-foreground)",
      padding: "9px 10px 5px"
    }
  }, g.label), g.items.map(it => /*#__PURE__*/React.createElement(PaletteItem, {
    key: it.id,
    item: it,
    active: it.id === activeId,
    onPick: onPick
  }))))), footer && /*#__PURE__*/React.createElement("div", {
    style: {
      flexShrink: 0,
      display: "flex",
      alignItems: "center",
      gap: 14,
      padding: "9px 14px",
      borderTop: "1px solid var(--bv-border-5)",
      fontSize: 11,
      color: "var(--muted-foreground)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 5
    }
  }, /*#__PURE__*/React.createElement(Kbd, null, "\u2191\u2193"), " navigate"), /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 5
    }
  }, /*#__PURE__*/React.createElement(Kbd, null, "\u21B5"), " open")));
}
function Kbd({
  children
}) {
  return /*#__PURE__*/React.createElement("span", {
    style: {
      fontFamily: "var(--bv-font-mono, monospace)",
      fontSize: 10,
      padding: "1px 5px",
      border: "1px solid var(--bv-border-15)",
      borderRadius: 4
    }
  }, children);
}
function PaletteItem({
  item,
  active,
  onPick
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: () => onPick && onPick(item),
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "flex",
      alignItems: "center",
      gap: 11,
      width: "100%",
      textAlign: "left",
      padding: "8px 10px",
      borderRadius: 10,
      border: "none",
      background: active ? "var(--bv-frost-8)" : hover ? "var(--bv-frost-4)" : "transparent",
      font: "inherit",
      cursor: "pointer",
      position: "relative",
      transition: "background var(--bv-dur-fast) var(--bv-ease-standard)"
    }
  }, active && /*#__PURE__*/React.createElement("span", {
    style: {
      position: "absolute",
      left: 0,
      top: 9,
      bottom: 9,
      width: 2.5,
      borderRadius: 2,
      background: "var(--bv-blue)"
    }
  }), item.icon && /*#__PURE__*/React.createElement("span", {
    style: {
      width: 28,
      height: 28,
      flexShrink: 0,
      borderRadius: 8,
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center",
      background: active ? "var(--bv-frost-12)" : "var(--bv-canvas-soft)",
      color: active ? "var(--bv-blue)" : "var(--bv-gray-600)"
    }
  }, item.icon), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      minWidth: 0,
      display: "flex",
      flexDirection: "column",
      gap: 1
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13.5,
      fontWeight: 500,
      color: "var(--foreground)",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, item.title), item.meta && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 11.5,
      color: "var(--muted-foreground)",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap"
    }
  }, item.meta)), item.kbd && /*#__PURE__*/React.createElement("span", {
    style: {
      flexShrink: 0,
      fontSize: 10.5,
      fontWeight: 500,
      color: "var(--muted-foreground)",
      padding: "2px 6px",
      border: "1px solid var(--bv-border-15)",
      borderRadius: 5,
      background: "var(--card)",
      fontFamily: "var(--bv-font-mono, monospace)"
    }
  }, item.kbd));
}
Object.assign(__ds_scope, { CommandPalette });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/CommandPalette.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Segmented.jsx
try { (() => {
/* Segmented control — the Maestro settings pattern (.mcc-seg): a bordered
   pill holding frost-pill options. Active wears frost-12. For 2–4 short,
   mutually exclusive choices; use Tabs for view switching, Select for long lists. */
function Segmented({
  options = [],
  value,
  onChange,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "inline-flex",
      gap: 2,
      padding: 3,
      flexShrink: 0,
      border: "1px solid var(--bv-border-15)",
      borderRadius: "var(--bv-radius-full)",
      ...style
    }
  }, options.map(o => {
    const opt = typeof o === "string" ? {
      value: o,
      label: o
    } : o;
    return /*#__PURE__*/React.createElement(SegBtn, {
      key: opt.value,
      active: opt.value === value,
      onClick: () => onChange && onChange(opt.value)
    }, opt.icon, opt.label);
  }));
}
function SegBtn({
  active,
  onClick,
  children
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    "aria-pressed": active,
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      height: 26,
      padding: "0 12px",
      border: "none",
      borderRadius: 99,
      background: active ? "var(--bv-frost-12)" : hover ? "var(--bv-frost-8)" : "transparent",
      font: "inherit",
      fontSize: 12.5,
      color: active ? "var(--foreground)" : "var(--muted-foreground)",
      cursor: "pointer",
      transition: "background var(--bv-dur-fast) var(--bv-ease-standard)"
    }
  }, children);
}
Object.assign(__ds_scope, { Segmented });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Segmented.jsx", error: String((e && e.message) || e) }); }

// components/navigation/Tabs.jsx
try { (() => {
/* Frost-pill tab strip — the mission-control tab pattern. Active tab wears
   frost-12; hover frost-8. No underlines, no borders. */
function Tabs({
  tabs = [],
  active,
  defaultActive = 0,
  onChange,
  style
}) {
  const [inner, setInner] = React.useState(defaultActive);
  const current = active !== undefined ? active : inner;
  const pick = i => {
    if (active === undefined) setInner(i);
    onChange && onChange(i);
  };
  return /*#__PURE__*/React.createElement("div", {
    role: "tablist",
    style: {
      display: "flex",
      alignItems: "center",
      gap: 3,
      ...style
    }
  }, tabs.map((t, i) => {
    const tab = typeof t === "string" ? {
      label: t
    } : t;
    return /*#__PURE__*/React.createElement(TabPill, {
      key: i,
      active: i === current,
      onClick: () => pick(i)
    }, tab.icon, tab.label, tab.count !== undefined && /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        color: "var(--muted-foreground)"
      }
    }, tab.count));
  }));
}
function TabPill({
  active,
  onClick,
  children
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "tab",
    "aria-selected": active,
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 7,
      height: 28,
      padding: "0 10px",
      border: "none",
      borderRadius: "var(--bv-radius-lg)",
      background: active ? "var(--bv-frost-12)" : hover ? "var(--bv-frost-8)" : "transparent",
      font: "inherit",
      fontSize: 12.5,
      fontWeight: active ? 500 : 400,
      color: active ? "var(--foreground)" : "var(--muted-foreground)",
      cursor: "pointer",
      whiteSpace: "nowrap",
      flexShrink: 0,
      transition: "background var(--bv-dur-fast) var(--bv-ease-standard)"
    }
  }, children);
}
Object.assign(__ds_scope, { Tabs });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/Tabs.jsx", error: String((e && e.message) || e) }); }

// components/overlays/Dialog.jsx
try { (() => {
/* Modal dialog — earned glass (.bv-glass-heavy) over the blue-black scrim.
   Title 18/600, body 14 muted, actions right-aligned. Esc/scrim close. */
function Dialog({
  open = true,
  title,
  children,
  actions,
  onClose,
  width = 440,
  style
}) {
  React.useEffect(() => {
    if (!open || !onClose) return;
    const onKey = e => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return /*#__PURE__*/React.createElement("div", {
    onClick: e => {
      if (e.target === e.currentTarget && onClose) onClose();
    },
    style: {
      position: "fixed",
      inset: 0,
      zIndex: 60,
      background: "oklch(0.135 0.02 272 / 0.42)",
      backdropFilter: "blur(2px)",
      WebkitBackdropFilter: "blur(2px)",
      display: "flex",
      alignItems: "center",
      justifyContent: "center",
      padding: 32
    }
  }, /*#__PURE__*/React.createElement("div", {
    role: "dialog",
    "aria-modal": "true",
    className: "bv-glass-heavy",
    style: {
      width: "min(" + width + "px, 100%)",
      maxHeight: "calc(100vh - 64px)",
      overflowY: "auto",
      padding: "22px 24px",
      display: "flex",
      flexDirection: "column",
      gap: 14,
      ...style
    }
  }, title && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 18,
      fontWeight: 600,
      letterSpacing: "-0.01em",
      color: "var(--foreground)"
    }
  }, title), /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 14,
      lineHeight: 1.55,
      color: "var(--muted-foreground)"
    }
  }, children), actions && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      justifyContent: "flex-end",
      gap: 8,
      paddingTop: 4
    }
  }, actions)));
}

/* Convenience: a confirm-shaped dialog. */
function ConfirmDialog({
  open,
  title,
  body,
  confirmLabel = "Approve",
  cancelLabel = "Cancel",
  onConfirm,
  onClose
}) {
  return /*#__PURE__*/React.createElement(Dialog, {
    open: open,
    title: title,
    onClose: onClose,
    actions: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(__ds_scope.Button, {
      variant: "ghost",
      onClick: onClose
    }, cancelLabel), /*#__PURE__*/React.createElement(__ds_scope.Button, {
      variant: "primary",
      onClick: onConfirm
    }, confirmLabel))
  }, body);
}
Object.assign(__ds_scope, { Dialog, ConfirmDialog });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/overlays/Dialog.jsx", error: String((e && e.message) || e) }); }

// components/overlays/Menu.jsx
try { (() => {
/* Popover menu — glass (popovers earn glass). Items 13px, hover frost-8,
   danger items in --bv-danger. Static positioning is the caller's job. */
function Menu({
  children,
  minWidth = 180,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "bv-glass",
    role: "menu",
    style: {
      display: "inline-flex",
      flexDirection: "column",
      padding: 5,
      minWidth,
      ...style
    }
  }, children);
}
function MenuItem({
  icon,
  kbd,
  danger = false,
  disabled = false,
  onClick,
  children,
  style
}) {
  const [hover, setHover] = React.useState(false);
  return /*#__PURE__*/React.createElement("button", {
    type: "button",
    role: "menuitem",
    disabled: disabled,
    onClick: onClick,
    onMouseEnter: () => setHover(true),
    onMouseLeave: () => setHover(false),
    style: {
      display: "flex",
      alignItems: "center",
      gap: 9,
      width: "100%",
      textAlign: "left",
      padding: "7px 9px",
      borderRadius: "var(--bv-radius-lg)",
      border: "none",
      background: hover && !disabled ? "var(--bv-frost-8)" : "transparent",
      font: "inherit",
      fontSize: 13,
      color: disabled ? "var(--bv-gray-400)" : danger ? "var(--bv-danger)" : "var(--foreground)",
      cursor: disabled ? "not-allowed" : "pointer",
      transition: "background var(--bv-dur-fast) var(--bv-ease-standard)",
      ...style
    }
  }, icon && /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      flexShrink: 0,
      color: danger ? "var(--bv-danger)" : "var(--bv-gray-600)"
    }
  }, icon), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      minWidth: 0
    }
  }, children), kbd && /*#__PURE__*/React.createElement("span", {
    style: {
      flexShrink: 0,
      fontSize: 10.5,
      color: "var(--muted-foreground)",
      fontFamily: "var(--bv-font-mono, monospace)"
    }
  }, kbd));
}
function MenuDivider() {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      height: 1,
      margin: "4px 6px",
      background: "var(--bv-border-5)"
    }
  });
}
Object.assign(__ds_scope, { Menu, MenuItem, MenuDivider });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/overlays/Menu.jsx", error: String((e && e.message) || e) }); }

// components/overlays/Toast.jsx
try { (() => {
/* Toast — a floating glass notice (floating surfaces earn glass).
   Status dot instead of big icons; one optional action; no celebration. */
function Toast({
  status = "info",
  title,
  meta,
  action,
  onAction,
  onDismiss,
  style
}) {
  const colors = {
    success: "var(--bv-success)",
    info: "var(--bv-info)",
    warning: "var(--bv-warning)",
    danger: "var(--bv-danger)",
    neutral: "var(--bv-gray-400)"
  };
  return /*#__PURE__*/React.createElement("div", {
    role: "status",
    className: "bv-glass",
    style: {
      display: "flex",
      alignItems: "center",
      gap: 10,
      padding: "10px 12px",
      width: "min(360px, 100%)",
      boxShadow: "var(--bv-shadow-card-hover)",
      ...style
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      width: 8,
      height: 8,
      borderRadius: 99,
      flexShrink: 0,
      background: colors[status] || colors.info
    }
  }), /*#__PURE__*/React.createElement("span", {
    style: {
      flex: 1,
      minWidth: 0,
      display: "flex",
      flexDirection: "column",
      gap: 1
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 13.5,
      fontWeight: 500,
      color: "var(--foreground)"
    }
  }, title), meta && /*#__PURE__*/React.createElement("span", {
    style: {
      fontSize: 12,
      color: "var(--muted-foreground)"
    }
  }, meta)), action && /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: onAction,
    style: {
      flexShrink: 0,
      border: "none",
      background: "transparent",
      font: "inherit",
      fontSize: 12.5,
      fontWeight: 500,
      color: "var(--bv-blue)",
      cursor: "pointer",
      padding: "4px 6px",
      borderRadius: "var(--bv-radius-lg)"
    }
  }, action), onDismiss && /*#__PURE__*/React.createElement("button", {
    type: "button",
    onClick: onDismiss,
    "aria-label": "Dismiss",
    style: {
      flexShrink: 0,
      width: 22,
      height: 22,
      border: "none",
      background: "transparent",
      color: "var(--muted-foreground)",
      cursor: "pointer",
      borderRadius: "var(--bv-radius-lg)",
      display: "inline-flex",
      alignItems: "center",
      justifyContent: "center"
    }
  }, /*#__PURE__*/React.createElement("svg", {
    viewBox: "0 0 24 24",
    fill: "none",
    stroke: "currentColor",
    strokeWidth: "2",
    strokeLinecap: "round",
    strokeLinejoin: "round",
    style: {
      width: 13,
      height: 13
    }
  }, /*#__PURE__*/React.createElement("path", {
    d: "M18 6 6 18"
  }), /*#__PURE__*/React.createElement("path", {
    d: "m6 6 12 12"
  }))));
}
Object.assign(__ds_scope, { Toast });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/overlays/Toast.jsx", error: String((e && e.message) || e) }); }

// components/overlays/Tooltip.jsx
try { (() => {
/* Hover tooltip — a small glass chip (popovers earn glass). 12px, no arrow,
   no delay theatrics; fades in 150ms. */
function Tooltip({
  label,
  side = "top",
  children,
  style
}) {
  const [show, setShow] = React.useState(false);
  const pos = {
    top: {
      bottom: "calc(100% + 6px)",
      left: "50%",
      transform: "translateX(-50%)"
    },
    bottom: {
      top: "calc(100% + 6px)",
      left: "50%",
      transform: "translateX(-50%)"
    },
    left: {
      right: "calc(100% + 6px)",
      top: "50%",
      transform: "translateY(-50%)"
    },
    right: {
      left: "calc(100% + 6px)",
      top: "50%",
      transform: "translateY(-50%)"
    }
  };
  return /*#__PURE__*/React.createElement("span", {
    onMouseEnter: () => setShow(true),
    onMouseLeave: () => setShow(false),
    onFocus: () => setShow(true),
    onBlur: () => setShow(false),
    style: {
      position: "relative",
      display: "inline-flex",
      ...style
    }
  }, children, /*#__PURE__*/React.createElement("span", {
    role: "tooltip",
    className: "bv-glass",
    style: {
      position: "absolute",
      zIndex: 70,
      ...pos[side],
      padding: "4px 9px",
      borderRadius: "var(--bv-radius-lg)",
      fontSize: 12,
      fontWeight: 500,
      color: "var(--foreground)",
      whiteSpace: "nowrap",
      pointerEvents: "none",
      opacity: show ? 1 : 0,
      transition: "opacity var(--bv-dur-fast) var(--bv-ease-standard)"
    }
  }, label));
}
Object.assign(__ds_scope, { Tooltip });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/overlays/Tooltip.jsx", error: String((e && e.message) || e) }); }

// components/work/AutonomyScoreboard.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* The autonomy scoreboard — keep score in unsupervised hours, never
   percentages of "done". Blue segments are unsupervised stretches, accent
   notches are human looks, the live segment is the run happening now. */
function AutonomyScoreboard({
  label = "unsupervised today",
  hours,
  sub,
  segments = [],
  notches = [],
  children,
  style,
  ...rest
}) {
  return /*#__PURE__*/React.createElement("div", _extends({
    style: {
      margin: "0 2px",
      padding: "9px 10px",
      border: "1px solid var(--bv-border-5)",
      borderRadius: "var(--bv-radius-lg)",
      background: "var(--card)",
      display: "flex",
      flexDirection: "column",
      gap: 6,
      ...style
    }
  }, rest), /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "baseline",
      justifyContent: "space-between",
      fontSize: 11,
      color: "var(--muted-foreground)"
    }
  }, /*#__PURE__*/React.createElement("span", null, label), /*#__PURE__*/React.createElement("b", {
    style: {
      fontSize: 12.5,
      fontWeight: 500,
      color: "var(--foreground)",
      fontVariantNumeric: "tabular-nums"
    }
  }, hours)), /*#__PURE__*/React.createElement("div", {
    style: {
      position: "relative",
      height: 4,
      borderRadius: 99,
      background: "var(--bv-border-5)",
      overflow: "visible"
    }
  }, segments.map((s, i) => /*#__PURE__*/React.createElement("span", {
    key: "s" + i,
    style: {
      position: "absolute",
      top: 0,
      bottom: 0,
      borderRadius: 99,
      left: s.start + "%",
      width: s.width + "%",
      background: s.live ? "linear-gradient(90deg, var(--bv-blue), oklch(0.82 0.09 230))" : "var(--bv-blue)",
      opacity: s.live ? 1 : 0.55
    }
  })), notches.map((n, i) => /*#__PURE__*/React.createElement("i", {
    key: "n" + i,
    style: {
      position: "absolute",
      top: -2.5,
      width: 1.5,
      height: 9,
      borderRadius: 1,
      left: n + "%",
      background: "var(--bv-blue-accent)"
    }
  }))), sub && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 10.5,
      color: "var(--muted-foreground)"
    }
  }, sub), children);
}
Object.assign(__ds_scope, { AutonomyScoreboard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/work/AutonomyScoreboard.jsx", error: String((e && e.message) || e) }); }

// components/work/LifecycleRail.jsx
try { (() => {
/* The lifecycle rail — the inspector's horizontal stage tracker
   (proposed → queued → running → review → done). Passed and current
   stages carry ai-blue; a warn stage carries warning. Never a progress bar. */
function LifecycleRail({
  stages = [],
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "flex-start",
      padding: "4px 0 0",
      ...style
    }
  }, stages.map((st, i) => {
    const state = st.state || "upcoming";
    const passed = state === "passed";
    const current = state === "current";
    const warn = state === "warn";
    const lit = passed || current || warn;
    return /*#__PURE__*/React.createElement("div", {
      key: i,
      style: {
        flex: 1,
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        gap: 6,
        position: "relative",
        minWidth: 0
      }
    }, i > 0 && /*#__PURE__*/React.createElement("span", {
      style: {
        position: "absolute",
        top: 4.5,
        left: "-50%",
        right: "50%",
        height: 1.5,
        background: passed || current ? "oklch(0.60 0.12 260 / 0.45)" : "var(--bv-border-15)"
      }
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        width: 10,
        height: 10,
        borderRadius: 99,
        position: "relative",
        zIndex: 1,
        background: warn ? "var(--bv-warning)" : lit ? "var(--bv-blue)" : "var(--background)",
        border: "1.5px solid " + (warn ? "var(--bv-warning)" : lit ? "var(--bv-blue)" : "var(--bv-border-25)"),
        boxShadow: current ? "0 0 0 4px var(--bv-frost-12)" : warn ? "0 0 0 4px oklch(0.76 0.15 85 / 0.18)" : "none"
      }
    }), /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11,
        textAlign: "center",
        color: current ? "var(--foreground)" : "var(--muted-foreground)",
        fontWeight: current ? 500 : 400
      }
    }, st.name), st.note && /*#__PURE__*/React.createElement("span", {
      style: {
        fontSize: 11.5,
        color: "var(--muted-foreground)",
        textAlign: "center",
        paddingTop: 2
      }
    }, st.note));
  }));
}
Object.assign(__ds_scope, { LifecycleRail });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/work/LifecycleRail.jsx", error: String((e && e.message) || e) }); }

// components/work/Receipt.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Receipts — evidence blocks that stand in for progress bars.
   Branch, diffstat, judge verdict; mono for machine facts.
   The branch is the receipt: never fake percentages. */
function Receipt({
  rows = [],
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      border: "1px solid var(--bv-border-5)",
      borderRadius: "var(--bv-radius-lg)",
      background: "var(--bv-canvas-soft)",
      padding: "10px 12px",
      display: "flex",
      flexDirection: "column",
      gap: 7,
      fontSize: 12.5,
      ...style
    }
  }, rows.map((r, i) => /*#__PURE__*/React.createElement(ReceiptRow, _extends({
    key: i
  }, r))));
}
function ReceiptRow({
  icon,
  label,
  code,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      color: "var(--muted-foreground)",
      ...style
    }
  }, icon && /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      flexShrink: 0,
      width: 13,
      height: 13
    }
  }, icon), label && /*#__PURE__*/React.createElement("span", null, label), code && /*#__PURE__*/React.createElement("code", {
    style: {
      fontFamily: "var(--bv-font-mono, ui-monospace, monospace)",
      fontSize: 11.5,
      color: "var(--foreground)"
    }
  }, code));
}
Object.assign(__ds_scope, { Receipt, ReceiptRow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/work/Receipt.jsx", error: String((e && e.message) || e) }); }

// components/work/Undertow.jsx
try { (() => {
/* The Undertow — THE running signal. Wraps a matte card in the contained
   4px halo (breathing pools + counter-phase tide + faint 9s orbit) defined
   in tokens/motion.css. Presence, not progress. `active={false}` renders
   children bare, so running state can toggle without remounting. */
function Undertow({
  active = true,
  children,
  style
}) {
  if (!active) return /*#__PURE__*/React.createElement(React.Fragment, null, children);
  return /*#__PURE__*/React.createElement("div", {
    className: "bv-undertow",
    style: style
  }, /*#__PURE__*/React.createElement("span", {
    className: "bv-undertow-orbit"
  }), children);
}
Object.assign(__ds_scope, { Undertow });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/work/Undertow.jsx", error: String((e && e.message) || e) }); }

// components/work/WorkState.jsx
try { (() => {
/* The plain-voice work states — Broomva's canon vocabulary. The dot
   carries the color; running wears the tidepool, standing pulses.
   System enums (Todo/InProgress/Blocked/InReview) are a developer
   surface only — never render them here. */
const STATES = {
  queued: {
    label: "Queued",
    color: "var(--bv-gray-400)"
  },
  running: {
    label: "Running",
    color: "var(--bv-blue)",
    live: true
  },
  stuck: {
    label: "Stuck",
    color: "var(--bv-warning)"
  },
  "needs-you": {
    label: "Needs you",
    color: "var(--bv-blue-accent)"
  },
  done: {
    label: "Done",
    color: "var(--bv-success)"
  },
  standing: {
    label: "Standing",
    color: "var(--bv-blue)",
    pulse: true
  }
};
function WorkState({
  state = "queued",
  variant = "inline",
  children,
  style
}) {
  const s = STATES[state] || STATES.queued;
  const dot = s.live ? /*#__PURE__*/React.createElement("span", {
    className: "bv-dot-live",
    style: {
      width: 10,
      height: 10
    }
  }) : /*#__PURE__*/React.createElement("span", {
    className: s.pulse ? "bv-dot--pulse" : undefined,
    style: {
      width: 8,
      height: 8,
      borderRadius: 99,
      flexShrink: 0,
      background: s.color
    }
  });
  if (variant === "chip") {
    return /*#__PURE__*/React.createElement("span", {
      style: {
        display: "inline-flex",
        alignItems: "center",
        gap: 7,
        height: 26,
        padding: "0 12px",
        borderRadius: "var(--bv-radius-full)",
        background: "var(--bv-canvas-soft)",
        fontSize: 12,
        fontWeight: 500,
        color: "var(--foreground)",
        ...style
      }
    }, dot, children || s.label);
  }
  return /*#__PURE__*/React.createElement("span", {
    style: {
      display: "inline-flex",
      alignItems: "center",
      gap: 6,
      fontSize: 13,
      fontWeight: 500,
      color: "var(--foreground)",
      ...style
    }
  }, dot, children || s.label);
}
Object.assign(__ds_scope, { WorkState });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/work/WorkState.jsx", error: String((e && e.message) || e) }); }

// components/work/RunCard.jsx
try { (() => {
/* The look — the gate's run card. Compresses a session to:
   what changed · what it decided · what it asks. Approve / Send back
   are the only controls. A fast, confident look earns the next longer
   unsupervised run. */
function RunCard({
  state = "needs-you",
  agent,
  duration,
  title,
  decided,
  asks,
  receipts = [],
  onApprove,
  onSendBack,
  style
}) {
  return /*#__PURE__*/React.createElement("div", {
    style: {
      border: "1px solid var(--bv-border-5)",
      borderRadius: "var(--bv-radius-xl)",
      background: "var(--card)",
      boxShadow: "var(--bv-shadow-edge)",
      padding: "14px 16px",
      display: "flex",
      flexDirection: "column",
      gap: 12,
      maxWidth: "100%",
      ...style
    }
  }, /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8,
      fontSize: 12.5,
      color: "var(--muted-foreground)"
    }
  }, /*#__PURE__*/React.createElement(__ds_scope.WorkState, {
    state: state
  }), agent && /*#__PURE__*/React.createElement("span", null, "\xB7 ", agent), duration && /*#__PURE__*/React.createElement("span", {
    style: {
      marginLeft: "auto"
    }
  }, duration, " unsupervised")), title && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 15,
      fontWeight: 500,
      lineHeight: 1.4,
      color: "var(--foreground)"
    }
  }, title), decided && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      lineHeight: 1.55,
      color: "var(--muted-foreground)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 500,
      color: "var(--foreground)"
    }
  }, "Decided"), " \u2014 ", decided), asks && /*#__PURE__*/React.createElement("div", {
    style: {
      fontSize: 13,
      lineHeight: 1.55,
      color: "var(--muted-foreground)"
    }
  }, /*#__PURE__*/React.createElement("span", {
    style: {
      fontWeight: 500,
      color: "var(--foreground)"
    }
  }, "Asks"), " \u2014 ", asks), receipts.length > 0 && /*#__PURE__*/React.createElement(__ds_scope.Receipt, {
    rows: receipts
  }), (onApprove || onSendBack) && /*#__PURE__*/React.createElement("div", {
    style: {
      display: "flex",
      alignItems: "center",
      gap: 8
    }
  }, onApprove && /*#__PURE__*/React.createElement(__ds_scope.Button, {
    variant: "primary",
    size: "sm",
    onClick: onApprove
  }, "Approve"), onSendBack && /*#__PURE__*/React.createElement(__ds_scope.Button, {
    variant: "ghost",
    size: "sm",
    onClick: onSendBack
  }, "Send back")));
}
Object.assign(__ds_scope, { RunCard });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/work/RunCard.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Avatar = __ds_scope.Avatar;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.Composer = __ds_scope.Composer;

__ds_ns.DotComet = __ds_scope.DotComet;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.StatusBadge = __ds_scope.StatusBadge;

__ds_ns.Checkbox = __ds_scope.Checkbox;

__ds_ns.Field = __ds_scope.Field;

__ds_ns.Radio = __ds_scope.Radio;

__ds_ns.Select = __ds_scope.Select;

__ds_ns.Switch = __ds_scope.Switch;

__ds_ns.Textarea = __ds_scope.Textarea;

__ds_ns.CommandPalette = __ds_scope.CommandPalette;

__ds_ns.Segmented = __ds_scope.Segmented;

__ds_ns.Tabs = __ds_scope.Tabs;

__ds_ns.Dialog = __ds_scope.Dialog;

__ds_ns.ConfirmDialog = __ds_scope.ConfirmDialog;

__ds_ns.Menu = __ds_scope.Menu;

__ds_ns.MenuItem = __ds_scope.MenuItem;

__ds_ns.MenuDivider = __ds_scope.MenuDivider;

__ds_ns.Toast = __ds_scope.Toast;

__ds_ns.Tooltip = __ds_scope.Tooltip;

__ds_ns.AutonomyScoreboard = __ds_scope.AutonomyScoreboard;

__ds_ns.LifecycleRail = __ds_scope.LifecycleRail;

__ds_ns.Receipt = __ds_scope.Receipt;

__ds_ns.ReceiptRow = __ds_scope.ReceiptRow;

__ds_ns.RunCard = __ds_scope.RunCard;

__ds_ns.Undertow = __ds_scope.Undertow;

__ds_ns.WorkState = __ds_scope.WorkState;

})();
