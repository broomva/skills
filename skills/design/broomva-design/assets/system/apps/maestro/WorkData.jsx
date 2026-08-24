// Maestro v2 · icons (Lucide paths, stroke 2, currentColor) + demo data.
// The data model is the work-as-noun reframe: a work item is an object with a
// lifecycle (proposed → queued → running → review → done), agents are workers
// dispatched against it, and chat is one projection of its run stream.

const McIcon = ({ children, size = 16, style, ...rest }) => (
  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"
       strokeLinecap="round" strokeLinejoin="round"
       {...rest} style={{ width: size, height: size, ...style }}>{children}</svg>
);

const IcBoard = (p) => <McIcon {...p}><rect width="7" height="9" x="3" y="3" rx="1"></rect><rect width="7" height="5" x="14" y="3" rx="1"></rect><rect width="7" height="9" x="14" y="12" rx="1"></rect><rect width="7" height="5" x="3" y="16" rx="1"></rect></McIcon>;
const IcList = (p) => <McIcon {...p}><line x1="8" x2="21" y1="6" y2="6"></line><line x1="8" x2="21" y1="12" y2="12"></line><line x1="8" x2="21" y1="18" y2="18"></line><line x1="3" x2="3.01" y1="6" y2="6"></line><line x1="3" x2="3.01" y1="12" y2="12"></line><line x1="3" x2="3.01" y1="18" y2="18"></line></McIcon>;
const IcDoc = (p) => <McIcon {...p}><path d="M15 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7Z"></path><path d="M14 2v4a2 2 0 0 0 2 2h4"></path><path d="M10 9H8"></path><path d="M16 13H8"></path><path d="M16 17H8"></path></McIcon>;
const IcSettings = (p) => <McIcon {...p}><path d="M12.22 2h-.44a2 2 0 0 0-2 2v.18a2 2 0 0 1-1 1.73l-.43.25a2 2 0 0 1-2 0l-.15-.08a2 2 0 0 0-2.73.73l-.22.38a2 2 0 0 0 .73 2.73l.15.1a2 2 0 0 1 1 1.72v.51a2 2 0 0 1-1 1.74l-.15.09a2 2 0 0 0-.73 2.73l.22.38a2 2 0 0 0 2.73.73l.15-.08a2 2 0 0 1 2 0l.43.25a2 2 0 0 1 1 1.73V20a2 2 0 0 0 2 2h.44a2 2 0 0 0 2-2v-.18a2 2 0 0 1 1-1.73l.43-.25a2 2 0 0 1 2 0l.15.08a2 2 0 0 0 2.73-.73l.22-.39a2 2 0 0 0-.73-2.73l-.15-.08a2 2 0 0 1-1-1.74v-.5a2 2 0 0 1 1-1.74l.15-.09a2 2 0 0 0 .73-2.73l-.22-.38a2 2 0 0 0-2.73-.73l-.15.08a2 2 0 0 1-2 0l-.43-.25a2 2 0 0 1-1-1.73V4a2 2 0 0 0-2-2z"></path><circle cx="12" cy="12" r="3"></circle></McIcon>;
const IcLayers = (p) => <McIcon {...p}><path d="m12.83 2.18a2 2 0 0 0-1.66 0L2.6 6.08a1 1 0 0 0 0 1.83l8.58 3.91a2 2 0 0 0 1.66 0l8.58-3.9a1 1 0 0 0 0-1.84Z"></path><path d="m22 17.65-9.17 4.16a2 2 0 0 1-1.66 0L2 17.65"></path><path d="m22 12.65-9.17 4.16a2 2 0 0 1-1.66 0L2 12.65"></path></McIcon>;
const IcBranch = (p) => <McIcon {...p}><line x1="6" x2="6" y1="3" y2="15"></line><circle cx="18" cy="6" r="3"></circle><circle cx="6" cy="18" r="3"></circle><path d="M18 9a9 9 0 0 1-9 9"></path></McIcon>;
const IcPlay = (p) => <McIcon {...p}><polygon points="6 3 20 12 6 21 6 3"></polygon></McIcon>;
const IcCheck = (p) => <McIcon {...p}><path d="M20 6 9 17l-5-5"></path></McIcon>;
const IcArrowUp = (p) => <McIcon {...p}><path d="M12 19V5"></path><path d="m5 12 7-7 7 7"></path></McIcon>;
const IcSun = (p) => <McIcon {...p}><circle cx="12" cy="12" r="4"></circle><path d="M12 2v2"></path><path d="M12 20v2"></path><path d="m4.93 4.93 1.41 1.41"></path><path d="m17.66 17.66 1.41 1.41"></path><path d="M2 12h2"></path><path d="M20 12h2"></path><path d="m6.34 17.66-1.41 1.41"></path><path d="m19.07 4.93-1.41 1.41"></path></McIcon>;
const IcMoon = (p) => <McIcon {...p}><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"></path></McIcon>;
const IcX = (p) => <McIcon {...p}><path d="M18 6 6 18"></path><path d="m6 6 12 12"></path></McIcon>;
const IcChevrons = (p) => <McIcon {...p}><path d="m7 15 5 5 5-5"></path><path d="m7 9 5-5 5 5"></path></McIcon>;
const IcAlert = (p) => <McIcon {...p}><circle cx="12" cy="12" r="10"></circle><line x1="12" x2="12" y1="8" y2="12"></line><line x1="12" x2="12.01" y1="16" y2="16"></line></McIcon>;
const IcEye = (p) => <McIcon {...p}><path d="M2 12s3-7 10-7 10 7 10 7-3 7-10 7-10-7-10-7Z"></path><circle cx="12" cy="12" r="3"></circle></McIcon>;
const IcSeam = (p) => <McIcon {...p}><rect width="20" height="8" x="2" y="2" rx="2"></rect><rect width="20" height="8" x="2" y="14" rx="2"></rect><line x1="6" x2="6.01" y1="6" y2="6"></line><line x1="6" x2="6.01" y1="18" y2="18"></line></McIcon>;
const IcChat = (p) => <McIcon {...p}><path d="M7.9 20A9 9 0 1 0 4 16.1L2 22Z"></path></McIcon>;
const IcGavel = (p) => <McIcon {...p}><path d="m14 13-7.5 7.5a2.12 2.12 0 0 1-3-3L11 10"></path><path d="m16 16 6 6"></path><path d="m8 8 6-6"></path><path d="m9 7 8 8"></path><path d="m21 11-8-8"></path></McIcon>;

// ── States · one vocabulary, two registers ───────────────────────────────
// plain = Broomva voice ("Needs you", not "InReview"); system = Hawthorne enums.
const WK_STATES = {
  proposed: { plain: "Proposed",  system: "Proposed",   tone: "muted"  },
  queued:   { plain: "Queued",    system: "Todo",       tone: "muted"  },
  running:  { plain: "Running",   system: "InProgress", tone: "active" },
  blocked:  { plain: "Stuck",     system: "Blocked",    tone: "warn"   },
  review:   { plain: "Needs you", system: "InReview",   tone: "review" },
  done:     { plain: "Done",      system: "Done",       tone: "done"   },
};
const WK_TONE_COLOR = {
  muted:  "var(--bv-gray-400)",
  active: "var(--bv-info)",
  warn:   "var(--bv-warning)",
  review: "var(--bv-blue-accent)",
  done:   "var(--bv-success)",
};
// Attention-first: what needs you, then what's moving, then backlog, then receipts.
const WK_GROUP_ORDER = ["review", "blocked", "running", "queued", "proposed", "done"];
const WK_GROUP_HINTS = {
  review:   "Clean runs waiting at your gate",
  blocked:  "A worker is stuck · unblock it",
  running:  "Dispatched, live in a worktree",
  queued:   "Actionable on the next tick",
  proposed: "Specs not yet dispatched",
  done:     "The branch is the receipt",
};
const WK_ATTENTION = ["review", "blocked"];

// Genesis phase machine, per state · how a run renders inside chat.
const WK_PHASE = { running: "running", blocked: "blocked", review: "awaiting you", done: "done", queued: "queued", proposed: "—" };

// ── Initiatives (light grouping; tasks are the cards) ────────────────────
const WK_INITIATIVES = [
  { id: "hawthorne", name: "Hawthorne M2",  hint: "multi-turn" },
  { id: "genesis",   name: "Genesis P1",    hint: "walking skeleton" },
  { id: "ops",       name: "Studio ops",    hint: "" },
];

// ── Work items ───────────────────────────────────────────────────────────
const WK_ITEMS = [
  {
    id: "w1", state: "review", time: "12m",
    title: "Persist run transcripts on the Run record",
    initiative: "hawthorne", project: "hawthorne-core",
    worker: { name: "claude", where: "local worktree" },
    run: "run/7c2f1a", verdict: "Checks passed · 14 tests added",
    look: {
      ran: "2h 14m unsupervised · 41 events · ran to the gate",
      decided: [
        "Persist the transcript on the Run record, not the session · survives worker restarts",
        "Replay covered by 14 tests instead of snapshotting live state",
        "Deferred compression · transcripts are small until multi-day runs land",
      ],
      ask: "Approve the branch so reviews stop needing the live session · and allow reading ops so the import can run unsupervised next loop.",
    },
    events: [
      { g: "↑", verb: "Queued", detail: "Pushed from the spec board", t: "3h" },
      { g: "▶", verb: "Picked up", detail: <span>Worktree created on <code>run/7c2f1a</code> · runner <code>claude</code></span>, t: "2h" },
      { g: "✦", verb: "Run finished clean", detail: "41 file events · exit 0", t: "26m" },
      { g: "⚖", verb: "Judge: checks passed", detail: "No auto-Done · a clean run still lands at your gate", t: "12m", tone: "review" },
    ],
    chat: [
      { from: "user", text: "Persist the full transcript on each Run so reviews don't need the live session" },
      { from: "run", phase: "awaiting you", run: "run/7c2f1a", lines: [
        ["Edit", "crates/hawthorne-core/src/store/run.rs"],
        ["Test", "cargo test -p hawthorne-core · 14 passed"],
        ["Commit", "run/7c2f1a · transcript persisted on Run"],
      ]},
      { from: "assistant", html: "The run is clean: transcripts now persist on the <b>Run</b> record and 14 tests cover replay. The judge passed its checks, so this is waiting on you · approve and the branch lands as the receipt." },
    ],
  },
  {
    id: "w2", state: "blocked", time: "41m",
    title: "Import Linear cycles into the object model",
    initiative: "hawthorne", project: "hawthorne-db",
    worker: { name: "claude", where: "local worktree" },
    run: "run/b91e44",
    reason: "Needs a Linear API scope before the import can run",
    events: [
      { g: "↑", verb: "Queued", detail: "Pushed from the spec board", t: "5h" },
      { g: "▶", verb: "Picked up", detail: <span>Worktree created on <code>run/b91e44</code></span>, t: "2h" },
      { g: "✕", verb: "Blocked", detail: "Worker paused: missing LINEAR_API_KEY scope", t: "41m", tone: "warn" },
    ],
    chat: [
      { from: "user", text: "Sync our Linear cycles into the store" },
      { from: "run", phase: "blocked", run: "run/b91e44", lines: [
        ["Read", "crates/hawthorne-db/src/index.rs"],
        ["Pause", "missing credential: LINEAR_API_KEY (read scope)"],
      ]},
      { from: "assistant", html: "I mapped the cycle schema, but I can't reach Linear without a read scope. <button class=\"bv-link-pill\">Grant Linear access</button> and I'll resume the run where it paused." },
    ],
  },
  {
    id: "w3", state: "running", time: "now",
    title: "Reduce the NDJSON stream to the phase machine",
    initiative: "genesis", project: "@genesis/projection",
    worker: { name: "claude", where: "local worktree" },
    run: "run/4fd028",
    events: [
      { g: "↑", verb: "Queued", detail: "Pushed from chat · text in, work out", t: "1h" },
      { g: "▶", verb: "Picked up", detail: <span>Worktree created on <code>run/4fd028</code></span>, t: "32m" },
      { g: "●", verb: "Running", detail: "Reducer folding events: running · awaiting · blocked · done", t: "now", tone: "active" },
    ],
    chat: [
      { from: "user", text: "Fold the agent's NDJSON stream into a live phase machine the chat can render" },
      { from: "run", phase: "running", run: "run/4fd028", live: true, lines: [
        ["Edit", "packages/projection/src/reducer.ts"],
        ["Test", "bun test packages/projection · 9 passed, 2 todo"],
        ["Write", "reducer: tool_use → phase 'running'"],
      ]},
    ],
  },
  {
    id: "w4", state: "running", time: "6m",
    title: "Reconcile May invoices",
    initiative: "ops", project: "bookkeeping",
    worker: { name: "Bookkeeper", where: "cloud sandbox" },
    run: "run/c30a9d",
    events: [
      { g: "↑", verb: "Queued", detail: "Recurring work · first Monday of the month", t: "2d" },
      { g: "▶", verb: "Picked up", detail: <span>Dispatched to a cloud sandbox on <code>run/c30a9d</code></span>, t: "6m" },
      { g: "●", verb: "Running", detail: "Same plane, different worker · the core never knows where work runs", t: "now", tone: "active" },
    ],
    chat: [
      { from: "user", text: "Reconcile May invoices" },
      { from: "run", phase: "running", run: "run/c30a9d", live: true, lines: [
        ["Read", "drive: /receipts/2026-05 · 38 documents"],
        ["Match", "31 of 36 invoices reconciled"],
      ]},
    ],
  },
  {
    id: "w5", state: "queued", time: "2h",
    title: "Resume sessions across turns (Phase 2)",
    initiative: "hawthorne", project: "hawthorne-core",
    worker: null,
    events: [
      { g: "↑", verb: "Queued", detail: "Holding at the concurrency cap · 2 of 2 worktrees in use", t: "2h" },
    ],
    chat: [
      { from: "user", text: "Make sessions resumable so a task can span turns" },
      { from: "assistant", html: "Queued. The scheduler is at its cap (2 of 2 worktrees), so I'll dispatch this on the next free tick." },
    ],
  },
  {
    id: "w6", state: "queued", time: "1d", kind: "handoff",
    title: "Handoff: Maestro relay, phase 1b",
    initiative: "hawthorne", project: "hawthorne-engine",
    worker: null,
    firstAction: "Wire POST /trigger to the N=1 budget and surface orch-state transitions over /ws.",
    events: [
      { g: "↑", verb: "Pushed", detail: "Handoff queued from your phone · first action travels with it", t: "1d" },
    ],
    chat: [
      { from: "user", text: "Picking this up later · queue the relay handoff with the first action attached" },
      { from: "assistant", html: "Queued with its first action: <b>wire /trigger to the N=1 budget</b>. Any session · yours or a worker's · can pick it up from here." },
    ],
  },
  {
    id: "w7", state: "proposed", time: "3d", kind: "spec",
    title: "Spec: TunnelRunner relay protocol (V2)",
    initiative: "hawthorne", project: "hawthorne-core",
    worker: null,
    events: [
      { g: "✎", verb: "Proposed", detail: "Draft spec · adding a runner never touches the core", t: "3d" },
    ],
    chat: [
      { from: "user", text: "Draft the relay protocol for running work on my own machine" },
      { from: "assistant", html: "Drafted. It stays a proposal until you dispatch it · work exists before, and outlives, any agent session." },
    ],
  },
  {
    id: "w8", state: "done", time: "2d",
    title: "Close the single-stage execution loop (M1b)",
    initiative: "hawthorne", project: "hawthorne-engine",
    worker: { name: "claude", where: "local worktree" },
    run: "run/19adf2", verdict: "Judge passed · you approved",
    events: [
      { g: "▶", verb: "Picked up", detail: <span>Worktree created on <code>run/19adf2</code></span>, t: "3d" },
      { g: "⚖", verb: "Judge: checks passed", detail: "Agent created the file, committed it, exit 0", t: "2d", tone: "review" },
      { g: "✓", verb: "You approved", detail: <span>Committed on <code>run/19adf2</code> · worktree reclaimed · the branch is the receipt</span>, t: "2d", tone: "done" },
    ],
    chat: [
      { from: "user", text: "Close the loop: observe, decide, act, judge, commit" },
      { from: "run", phase: "done", run: "run/19adf2", lines: [
        ["Commit", "run/19adf2 · loop closed end-to-end"],
      ]},
      { from: "assistant", html: "Done · and <b>Done was earned</b>: the judge passed its checks and you approved at the gate. The worktree is reclaimed; the branch remains as the receipt." },
    ],
  },
];

const WK_REPLY = "Noted on the work item · I'll fold that into the next run. The thread stays with the work, not with me.";

Object.assign(window, {
  McIcon, IcBoard, IcList, IcDoc, IcSettings, IcLayers, IcBranch, IcPlay, IcCheck,
  IcArrowUp, IcSun, IcMoon, IcX, IcChevrons, IcAlert, IcEye, IcSeam, IcChat, IcGavel,
  WK_STATES, WK_TONE_COLOR, WK_GROUP_ORDER, WK_GROUP_HINTS, WK_ATTENTION, WK_PHASE,
  WK_INITIATIVES, WK_ITEMS, WK_REPLY,
});
