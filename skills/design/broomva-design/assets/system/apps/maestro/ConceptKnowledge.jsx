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
    id: "broomva", crumb: "Broomva", kind: "vault", desc: "governance · the bstack contract", parent: null,
    nodes: [
      { id: "hawthorne", label: "hawthorne", type: "initiative", scopeRef: "hawthorne", claim: "The agent platform · multi-turn work with a lifecycle.", related: ["p6", "genesis"] },
      { id: "genesis", label: "genesis", type: "project", scopeRef: "genesis", claim: "The walking-skeleton repo: observe, decide, act, judge, commit.", related: ["hawthorne", "p1"] },
      { id: "ops", label: "ops", type: "initiative", scopeRef: "ops", claim: "Recurring ops · bookkeeping, nightly digests.", related: ["p2"] },
      { id: "agents", label: "AGENTS.md", type: "doc", claim: "Reflexive trigger rules every agent loads at session start.", related: ["p6", "p2", "policy", "p1"] },
      { id: "policy", label: ".control/policy.yaml", type: "doc", claim: "L3 governance · gates, budgets, scopes. The controller of last resort.", related: ["p2", "rcs", "agents"] },
      { id: "p6", label: "Bookkeeping (P6)", type: "primitive", claim: "Knowledge graphs without quality control degrade into noise.", score: [3, 3, 3], sources: ["primitives.md#p6", "bookkeeping.py"], related: ["agents", "nous", "engine"] },
      { id: "p2", label: "Control Gate (P2)", type: "primitive", claim: "Blocks destructive ops the model didn't authorize · gates G1–G11.", score: [3, 2, 3], sources: ["primitives.md#p2"], related: ["policy", "agents"] },
      { id: "p1", label: "Conversation Bridge (P1)", type: "primitive", claim: "Closes session amnesia · each session writes back an Obsidian doc.", score: [3, 3, 2], sources: ["primitives.md#p1"], related: ["agents"] },
      { id: "nous", label: "Nous gate", type: "concept", claim: "Novelty + specificity + relevance, each 0–3. Items < 2/9 are discarded.", score: [2, 3, 3], sources: ["bookkeeping.py"], related: ["p6"] },
      { id: "rcs", label: "RCS L3 stability", type: "concept", claim: "Governance margin λ = 0.006 · the contract evolves slowly on purpose.", sources: ["recursive-controlled-systems"], related: ["policy"] },
      { id: "engine", label: "bstack-engine", type: "pattern", claim: "The candidate ledger · where primitives are born and gated.", sources: ["bstack-engine.md"], related: ["p6"] },
    ],
  },
  hawthorne: {
    id: "hawthorne", crumb: "hawthorne", kind: "initiative", desc: "the agent platform · multi-turn object model", parent: "broomva",
    nodes: [
      { id: "hawthorne-core", label: "hawthorne-core", type: "project", scopeRef: "hawthorne-core", claim: "The object model · persist run transcripts, at your gate.", related: ["worknoun", "hawthorne-db"] },
      { id: "hawthorne-db", label: "hawthorne-db", type: "project", scopeRef: "hawthorne-db", claim: "Imports + the store · Linear cycles land as work items.", related: ["hawthorne-core"] },
      { id: "worknoun", label: "work-as-noun", type: "concept", claim: "Folders are work at any scale; sessions are the verb acting on them.", score: [3, 3, 3], sources: ["work-model.md"], related: ["mc", "autonomy"] },
      { id: "mc", label: "Maestro", type: "concept", claim: "The plane that sorts your screen by the decisions only a human can make.", related: ["worknoun", "gate"] },
      { id: "autonomy", label: "unsupervised hours", type: "concept", claim: "The scarce resource: how long an agent runs before a human must look.", score: [3, 3, 3], sources: ["decision-log"], related: ["look", "worknoun"] },
      { id: "look", label: "the look", type: "concept", claim: "Hours compressed to what changed · decided · asks · a 90-second look.", related: ["autonomy", "gate"] },
      { id: "gate", label: "the gate", type: "concept", claim: "A clean run still lands at your gate · needing you is a gate, not a failure.", related: ["mc", "look"] },
      { id: "maestro", label: "maestro", type: "person", claim: "The orchestrator is just a session that schedules sessions.", sources: ["symphony skill"], related: ["hawthorne-core", "gate"] },
    ],
  },
  genesis: {
    id: "genesis", crumb: "genesis", kind: "project", desc: "one repo · its own .git + contract", parent: "broomva",
    nodes: [
      { id: "projection", label: "@genesis/projection", type: "session", live: true, claim: "Reduce the NDJSON stream to a phase machine · 1h 18m.", related: ["phase", "reducer"] },
      { id: "phase", label: "phase machine", type: "concept", claim: "Reduce the NDJSON stream to running · awaiting · blocked · done.", related: ["ndjson", "reducer", "uimsg"] },
      { id: "ndjson", label: "NDJSON stream", type: "concept", claim: "Append-only event timeline · the session's source of truth.", related: ["phase"] },
      { id: "reducer", label: "projection/reducer.ts", type: "tool", claim: "Folds tool_use events into the live phase the chat renders.", related: ["phase", "uimsg"] },
      { id: "uimsg", label: "UIMessage parts", type: "concept", claim: "text · reasoning · tool-NAME · data-NAME · the AI SDK contract.", score: [3, 2, 3], sources: ["ai-sdk docs"], related: ["aisdk", "reducer"] },
      { id: "aisdk", label: "UI Message Stream", type: "paper", claim: "Gen-UI stops being bespoke when every part speaks the same chunks.", sources: ["sdk.vercel.ai"], related: ["uimsg"] },
      { id: "metr", label: "METR Time Horizon 1.1", type: "paper", claim: "80%-reliability deployable horizon ~1h on Opus 4.6 · above it, persist.", sources: ["metr.org · Jan 2026"], related: ["phase"] },
    ],
  },
  "hawthorne-core": {
    id: "hawthorne-core", crumb: "hawthorne-core", kind: "project", desc: "persist run transcripts · worktree-per-run", parent: "hawthorne",
    nodes: [
      { id: "objmodel", label: "object model", type: "concept", claim: "Work item → lifecycle: proposed → running → review → done.", score: [3, 2, 3], sources: ["hawthorne-core"], related: ["multiturn", "relay"] },
      { id: "multiturn", label: "multi-turn", type: "concept", claim: "A work item outlives any single session that touches it.", related: ["objmodel"] },
      { id: "relay", label: "Maestro relay", type: "concept", claim: "Handoff protocol · any session can pick up the work from here.", related: ["objmodel"] },
      { id: "spec3", label: "spec.md", type: "doc", claim: "kind: project · owner: maestro · budget: 8h · gate: human-approve.", related: ["drun", "notes", "run7c"] },
      { id: "drun", label: "persist transcript on Run", type: "decision", claim: "Not the session · survives restarts; 14 tests cover replay.", score: [3, 3, 3], sources: ["run/7c2f1a", "PR #214"], related: ["spec3", "run7c", "notes"] },
      { id: "ddefer", label: "defer compression", type: "decision", claim: "Transcripts stay small until multi-day runs land · revisit then.", score: [2, 3, 2], sources: ["decision-log 2026-06-06"], related: ["spec3"] },
      { id: "notes", label: "notes/prior-art.md", type: "doc", claim: "Survey of resumability approaches, written from scout's 47m run.", related: ["scout", "drun"] },
      { id: "run7c", label: "run/7c2f1a", type: "session", claim: "claude · 2h 14m unsupervised · 41 events · ran to the gate.", live: true, related: ["drun", "spec3", "judge"] },
      { id: "scout", label: "scout · survey", type: "session", claim: "claude → scout · 47m unsupervised · done.", related: ["notes"] },
      { id: "judge", label: "judge verdict", type: "concept", claim: "Checks passed · 14 tests added · a clean run, still your gate.", related: ["run7c", "drun"] },
      { id: "review", label: "you → review API", type: "session", claim: "Halted · needed you (2 looks).", related: ["spec3"] },
    ],
  },
  "hawthorne-db": {
    id: "hawthorne-db", crumb: "hawthorne-db", kind: "project", desc: "imports + the store", parent: "hawthorne",
    nodes: [
      { id: "linear", label: "Linear import", type: "decision", claim: "Blocked · needs a LINEAR_API_KEY read scope before it can run.", sources: ["run/b91e44"], related: ["runb91", "cycles"] },
      { id: "runb91", label: "run/b91e44", type: "session", claim: "claude · 41m · paused · waiting on the credential grant.", related: ["linear"] },
      { id: "cycles", label: "linear-cycles.md", type: "doc", claim: "Map Linear cycles → work items · the import contract.", related: ["linear"] },
    ],
  },
  ops: {
    id: "ops", crumb: "ops", kind: "initiative", desc: "recurring ops", parent: "broomva",
    nodes: [
      { id: "nightly", label: "nightly-digest", type: "routine", scopeRef: "nightly", claim: "A standing loop: the routine is the deliverable, gate: none.", related: ["finance"] },
      { id: "bookkeeping", label: "bookkeeping", type: "task", scopeRef: "bookkeeping", claim: "Reconcile May invoices in a cloud sandbox.", related: ["finance", "reconcile"] },
      { id: "finance", label: "finance-substrate", type: "tool", claim: "Bookkeeper reconciles invoices and pushes digests each month.", sources: ["finance-substrate skill"], related: ["nightly", "bookkeeping"] },
      { id: "reconcile", label: "reconciliation", type: "concept", claim: "Match receipts to invoices; flag the gaps for a look.", related: ["bookkeeping"] },
    ],
  },
  nightly: {
    id: "nightly", crumb: "nightly-digest", kind: "routine", desc: "a loop that never closes", parent: "ops",
    nodes: [
      { id: "cadence", label: "cadence: 02:00", type: "doc", claim: "kind: routine · cadence: nightly 02:00 · gate: none.", related: ["digest", "run0610"] },
      { id: "digest", label: "digest template", type: "doc", claim: "What landed, what's stuck, what needs a look by morning.", related: ["cadence"] },
      { id: "run0610", label: "Thu 02:00 run", type: "session", claim: "31m · digest pushed + flagged a stuck import.", related: ["cadence", "digest"] },
      { id: "run0609", label: "Wed 02:00 run", type: "session", claim: "19m · digest pushed · /h/digest-0610.", related: ["cadence"] },
    ],
  },
  bookkeeping: {
    id: "bookkeeping", crumb: "bookkeeping", kind: "task", desc: "May reconciliation · cloud sandbox", parent: "ops",
    nodes: [
      { id: "may", label: "may-invoices.md", type: "doc", claim: "36 invoices, 38 receipts · the month's ledger.", related: ["bk", "reconciled"] },
      { id: "bk", label: "bookkeeper run", type: "session", claim: "Bookkeeper · cloud sandbox · 31 of 36 reconciled.", live: true, related: ["may", "reconciled"] },
      { id: "receipts", label: "drive: /receipts/2026-05", type: "doc", claim: "38 source documents pulled from the drive.", related: ["bk"] },
      { id: "reconciled", label: "5 unmatched", type: "decision", claim: "Five invoices have no receipt · flagged for your look.", score: [2, 3, 3], sources: ["run/c30a9d"], related: ["may", "bk"] },
    ],
  },
};

function kgScore(arr) { return arr ? arr[0] + arr[1] + arr[2] : null; }
function kgPath(id) { const out = []; let s = KG_SCOPES[id]; while (s) { out.unshift(s); s = s.parent ? KG_SCOPES[s.parent] : null; } return out; }

// ── The inspector · an entity page rendered from a node ────────────────────
function KgInspector({ node, scope, onSelect, big }) {
  if (!node) {
    const folders = scope.nodes.filter((n) => n.scopeRef).length;
    return (
      <div className="kg-inspect kg-inspect--empty">
        <div className="mcc-panel-label">{scope.crumb}/ · {scope.kind}</div>
        <p className="mcc-doc-p" style={{ color: "var(--muted-foreground)" }}>{scope.nodes.length} entities{folders > 0 ? " · " + folders + " sub-folder" + (folders > 1 ? "s" : "") : ""} · {scope.desc}.</p>
        <p className="mcc-doc-p" style={{ color: "var(--muted-foreground)" }}>Click an entity to open its page. The <b style={{ color: "var(--foreground)" }}>gold folder nodes</b> are sub-scopes · click one to dive into its graph.</p>
        <div className="kg-empty-hint"><IcGraph size={15} />Drag to pan · drag a node to pull it · /kg to filter</div>
      </div>
    );
  }
  const t = KG_TYPE[node.type] || KG_TYPE.concept;
  const total = kgScore(node.score);
  const backlinks = scope.nodes.filter((n) => (n.related || []).includes(node.id) || (node.related || []).includes(n.id));
  const subs = [["novelty", node.score && node.score[0]], ["specificity", node.score && node.score[1]], ["relevance", node.score && node.score[2]]];
  return (
    <div className={"kg-inspect" + (big ? " kg-inspect--big" : "")}>
      <div className="kg-ent-head">
        <span className="kg-ent-kind" style={{ color: t.color, borderColor: "color-mix(in oklch, " + t.color + " 42%, transparent)" }}>
          <span className="kg-legend-dot" style={{ background: t.color }}></span>{t.label}
        </span>
        {node.live && <span className="mc-badge"><span className="mcc-dot-comet" style={{ width: 12, height: 12 }}><span className="mcc-dot-comet-core"></span></span>live</span>}
      </div>
      <div className="kg-ent-title">{node.label}{node.type !== "session" && !node.scopeRef ? <span className="kg-ent-ext">.md</span> : null}</div>
      <p className="kg-ent-claim">“{node.claim}”</p>

      {total != null && (
        <div className="kg-score">
          <div className="kg-score-top"><span>Nous score</span><b>{total}<i>/9</i></b><span className="kg-score-verdict">{total >= 7 ? "fast-path promote" : total >= 3 ? "second opinion" : "discard"}</span></div>
          {subs.map(([k, v]) => (
            <div key={k} className="kg-score-row">
              <span className="kg-score-k">{k}</span>
              <span className="kg-score-bar"><i style={{ width: (v / 3 * 100) + "%" }}></i></span>
              <span className="kg-score-v">{v}</span>
            </div>
          ))}
        </div>
      )}

      {node.sources && (
        <div className="kg-ent-sec">
          <div className="mcc-panel-label">sources</div>
          <div className="kg-src-list">{node.sources.map((s, i) => <span key={i} className="mc-receipt">{s}</span>)}</div>
        </div>
      )}

      <div className="kg-ent-sec">
        <div className="mcc-panel-label">related · {backlinks.length}</div>
        <div className="kg-back-list">
          {backlinks.map((n) => {
            const bt = KG_TYPE[n.type] || KG_TYPE.concept;
            return (
              <button key={n.id} type="button" className="kg-back" onClick={() => onSelect && onSelect(n.id)}>
                <span className="kg-legend-dot" style={{ background: bt.color }}></span>{n.label}
              </button>
            );
          })}
        </div>
      </div>
    </div>
  );
}

// ── The workspace tree in the sidebar · the graph's navigator ──────────────
function KnowScopeRows({ parentId, depth, activeId, pathSet, onNav }) {
  const kids = Object.values(KG_SCOPES).filter((s) => s.parent === parentId);
  return kids.map((sc) => {
    const has = Object.values(KG_SCOPES).some((s) => s.parent === sc.id);
    const live = sc.nodes.some((n) => n.live);
    const open = has && pathSet.has(sc.id);
    return (
      <React.Fragment key={sc.id}>
        <button className={"bv-sb-item" + (sc.id === activeId ? " is-active" : "")} type="button"
          style={{ paddingLeft: 10 + depth * 15 }} onClick={() => onNav(sc.id)}>
          {live ? <span className="mcc-dot-tide" style={{ width: 13, height: 13 }}></span> : (open ? <IcFolderOpen size={14} /> : <IcFolder size={14} />)}
          <span className="mcc-sb-text">{sc.crumb}</span>
          <span className="mc-init-progress">{sc.nodes.length}</span>
        </button>
        {has && <KnowScopeRows parentId={sc.id} depth={depth + 1} activeId={activeId} pathSet={pathSet} onNav={onNav} />}
      </React.Fragment>
    );
  });
}

function KnowTree({ activeId, onNav }) {
  const pathSet = new Set(kgPath(activeId).map((s) => s.id));
  return (
    <div className="mcc-sb-col">
      <button className={"bv-sb-item" + (activeId === "broomva" ? " is-active" : "")} type="button" onClick={() => onNav("broomva")}>
        <IcLayers size={15} /><span className="mcc-sb-text">Broomva</span><span className="mc-init-progress">vault</span>
      </button>
      <KnowScopeRows parentId="broomva" depth={1} activeId={activeId} pathSet={pathSet} onNav={onNav} />
    </div>
  );
}

// ── K0 · A node is a file · frontmatter builds the graph ───────────────────
function MccKnowNode() {
  return (
    <div className="mcc-pad" style={{ gap: 14 }}>
      <div className="kg-node-spec">
        <pre className="mcc-fm" style={{ flex: 1 }}><code>{`---
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
snapshotting live session state…`}</code></pre>
        <span className="mcc-prim-arrow" style={{ alignSelf: "center" }}>becomes</span>
        <div className="kg-node-demo">
          <svg viewBox="0 0 200 180" className="kg-node-demo-svg">
            <line x1="100" y1="90" x2="40" y2="40" className="kg-edge" style={{ opacity: 0.5 }} />
            <line x1="100" y1="90" x2="165" y2="55" className="kg-edge" style={{ opacity: 0.5 }} />
            <line x1="100" y1="90" x2="150" y2="150" className="kg-edge" style={{ opacity: 0.5 }} />
            <g><circle cx="40" cy="40" r="8" fill="var(--bv-blue)" stroke="var(--background)" strokeWidth="2" /><text x="40" y="26" textAnchor="middle" className="kg-label">resumable</text></g>
            <g><circle cx="165" cy="55" r="8" fill="var(--bv-blue)" stroke="var(--background)" strokeWidth="2" /><text x="165" y="41" textAnchor="middle" className="kg-label">ndjson</text></g>
            <g><circle cx="150" cy="150" r="8" fill="var(--bv-info)" stroke="var(--background)" strokeWidth="2" /><text x="150" y="170" textAnchor="middle" className="kg-label">judge</text></g>
            <g><circle cx="100" cy="90" r="12" fill="var(--bv-success)" stroke="var(--background)" strokeWidth="2.5" /><text x="100" y="113" textAnchor="middle" className="kg-label" style={{ fontWeight: 600 }}>persist on Run</text></g>
          </svg>
        </div>
      </div>
      <p className="mcc-caption">No separate database. A markdown (or HTML) file's <b>frontmatter is the node</b>: <code>kind</code> sets its colour, <code>core_claim</code> its one line, the Nous block its score, and every <code>related:</code> entry draws an edge. Walk the filesystem and you've walked the graph · exactly bstack's <b>Bookkeeping (P6)</b> over <code>research/entities</code>. The agent files these as a reflex; you read them as a map.</p>
    </div>
  );
}

// ── K2 · The entity, opened · the inspector at full size ───────────────────
function MccKnowEntity() {
  const scope = KG_SCOPES["hawthorne-core"];
  const node = scope.nodes.find((n) => n.id === "drun");
  return (
    <div className="mcc-pad" style={{ gap: 12 }}>
      <span className="mc-detail-breadcrumb">hawthorne / hawthorne-core / runs · 7c2f1a</span>
      <div className="kg-entity-card">
        <KgInspector node={node} scope={scope} onSelect={() => {}} big />
      </div>
      <p className="mcc-caption">A node, opened: the entity page is the same frontmatter, rendered. The Nous score isn't decoration · it's the gate that kept this out of the noise (≥ 7 fast-paths a promote; under 2 is discarded). <code>related:</code> is bidirectional, so backlinks come free · click one and the graph re-centres on it.</p>
    </div>
  );
}

Object.assign(window, { KG_SCOPES, kgPath, KgInspector, KnowTree, MccKnowNode, MccKnowEntity });
