#!/usr/bin/env python3
"""
Tekton — shared architecture-intent model engine (v0.2).

One typed graph across tiers (system / journey / data / infra / decisions /
qualities). Views are queries over that single graph, not separate diagrams.
The canonical artifact is a YAML model (diff-friendly, git-versioned, agent-
and human-writable).

v0.2 adds the four upgrades from the architecture review (BRO-1717):
  1. Containment/hierarchy — `parent:` on any node (+ `boundary` type); the
     viewer renders nested groups (elkjs INCLUDE_CHILDREN) with collapse/expand
     drill-down.
  2. Lifecycle — `status:` on nodes (current|target|deprecated; target renders
     dashed) and full Nygard fields on decisions (context, consequences,
     status, supersedes).
  3. Qualities — top-level `qualities:` block; quality nodes `constrains` any
     element; surfaced in the detail panel and a dedicated view.
  4. Fitness functions — `tekton lint` with a `rules:` block (forbid-dep,
     no-cycle, layer-order). Machine-checked design rules; exit 1 on violation.

Primary render: custom on-brand viewer (elkjs layout + Broomva Design System
matte cards; glass only on the floating detail panel). Mermaid remains a
throwaway embed target.

Usage:
  tekton.py validate <model.arch.yaml>
  tekton.py lint     <model.arch.yaml>
  tekton.py views
  tekton.py mermaid  <model.arch.yaml> <view>
  tekton.py render   <model.arch.yaml> [-o out.html]
  tekton.py query    <model.arch.yaml> <from> <to>
  tekton.py stats    <model.arch.yaml>
"""
import sys, os, argparse, re, json, html as _html
from collections import deque, defaultdict

try:
    import yaml
except ImportError:
    print("error: pyyaml required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)

# ---------------------------------------------------------------- ontology ---
NODE_TYPES = {
    "actor":     ("{i}([\"{l}\"])",     "actor"),
    "journey":   ("{i}[\"{l}\"]",       "journey"),
    "step":      ("{i}(\"{l}\")",       "step"),
    "component": ("{i}[\"{l}\"]",       "component"),
    "service":   ("{i}[\"{l}\"]",       "component"),
    "datastore": ("{i}[(\"{l}\")]",     "datastore"),
    "entity":    ("{i}{{{{\"{l}\"}}}}", "entity"),
    "infra":     ("{i}[/\"{l}\"/]",     "infra"),
    "external":  ("{i}[[\"{l}\"]]",     "external"),
    "decision":  ("{i}{{\"{l}\"}}",     "decision"),
    "boundary":  ("{i}[\"{l}\"]",       "boundary"),   # v0.2 — context/team/trust boundary
    "quality":   ("{i}([\"{l}\"])",     "quality"),    # v0.2 — quality attribute / NFR
}
EDGE_TYPES = {
    "uses", "calls", "emits", "consumes", "reads", "writes", "stores",
    "owns", "deploys-to", "runs-on", "step-of", "next", "touches",
    "governs", "decides", "depends-on", "realizes",
    "constrains", "supersedes",                          # v0.2
}
NODE_STATUS = {"current", "target", "deprecated"}
DECISION_STATUS = {"proposed", "accepted", "superseded", "deprecated"}
RULE_KINDS = {"forbid-dep", "no-cycle", "layer-order"}
RULE_ALLOWED = {
    "forbid-dep":  {"id", "rule", "from", "to", "via", "why"},
    "no-cycle":    {"id", "rule", "via", "why"},
    "layer-order": {"id", "rule", "layers", "via", "why"},
}
SELECTOR_KEYS = {"id", "type", "layer"}


# Sentinel for "present but wrongly typed". A unique list instance so the
# return unions stay list-typed; always compared with `is`, never contents.
_INVALID: list = ["<invalid>"]


def _coerce_via(rule):
    """Accept `via: writes` (string) as well as `via: [writes]` (list).
    Any other type returns _INVALID so validate() can report it cleanly."""
    v = rule.get("via")
    if v is None:
        return None
    if isinstance(v, str):
        return [v]
    if isinstance(v, list):
        return v
    return _INVALID


def _str_list(v):
    """Coerce str|list-of-str → list[str]; anything else → _INVALID."""
    if v is None:
        return []
    if isinstance(v, str):
        return [v]
    if isinstance(v, list) and all(isinstance(x, str) for x in v):
        return v
    return _INVALID

# view: (node types included, edge types included, ANCHOR types).
# Anchors always render; non-anchor ("context") node types render only when
# connected by a view-edge (or containing something that is) — keeps e.g. the
# journey view from dragging in every unconnected component and empty boundary.
VIEWS = {
    "system":    ({"component", "service", "datastore", "external", "boundary"},
                  {"uses", "calls", "reads", "writes", "emits", "consumes", "depends-on"},
                  {"component", "service", "datastore", "external", "boundary"}),
    "journey":   ({"actor", "journey", "step", "component", "boundary"},
                  {"step-of", "next", "touches", "uses"},
                  {"actor", "journey", "step"}),
    "data":      ({"entity", "datastore", "component", "boundary"},
                  {"stores", "reads", "writes", "owns"},
                  {"entity", "datastore"}),
    "infra":     ({"component", "service", "infra", "datastore", "external", "boundary"},
                  {"deploys-to", "runs-on", "uses"},
                  {"infra"}),
    "decisions": ({"decision", "component", "service", "datastore", "entity",
                   "infra", "journey", "boundary", "quality"},
                  {"governs", "decides", "realizes", "supersedes"},
                  {"decision"}),
    "qualities": ({"quality", "component", "service", "datastore", "entity",
                   "infra", "journey", "step", "boundary"},
                  {"constrains"},
                  {"quality"}),
}
VIEW_TITLES = {
    "system":    "System — components, stores & their calls",
    "journey":   "Journey — actors, flows & the components they touch",
    "data":      "Data — entities, stores & read/write access",
    "infra":     "Infra — deployment topology",
    "decisions": "Decisions — ADRs pinned to what they govern",
    "qualities": "Qualities — NFRs & the elements they constrain",
}

NODE_FIELDS = ("id", "type", "label", "parent", "status", "layer", "note")

# ---------------------------------------------------------------- model io ---
class Model:
    def __init__(self, data, path):
        self.path = path
        if not isinstance(data, dict):
            raise SystemExit(f"error: {path}: model must be a YAML mapping "
                             f"(got {type(data).__name__})")
        self.name = str(data.get("name", os.path.basename(path)))
        self.description = str(data.get("description", ""))
        self.rules = data.get("rules", []) or []
        self.load_errors = []
        self.nodes = {}

        def _insert(nid, node, src):
            if not nid or not isinstance(nid, str):
                self.load_errors.append(f"{src} entry missing 'id': {node!r}")
                return False
            if nid in self.nodes:
                self.load_errors.append(
                    f"duplicate id '{nid}' in {src} — earlier definition kept, "
                    f"this one IGNORED (rename one of them)")
                return False
            self.nodes[nid] = node
            return True

        for n in data.get("nodes", []) or []:
            if not isinstance(n, dict):
                self.load_errors.append(f"nodes entry is not a mapping: {n!r}"); continue
            _insert(n.get("id"), dict(n), "nodes")
        # decisions block (Nygard ADR fields)
        for d in data.get("decisions", []) or []:
            if not isinstance(d, dict):
                self.load_errors.append(f"decisions entry is not a mapping: {d!r}"); continue
            nd = {"id": d.get("id"), "type": "decision",
                  "label": d.get("label", d.get("id")),
                  "status": d.get("status"),
                  "context": d.get("context"),
                  "consequences": d.get("consequences"),
                  "note": d.get("note")}
            _insert(d.get("id"), nd, "decisions")
        # qualities block
        for q in data.get("qualities", []) or []:
            if not isinstance(q, dict):
                self.load_errors.append(f"qualities entry is not a mapping: {q!r}"); continue
            nq = {"id": q.get("id"), "type": "quality",
                  "label": q.get("label", q.get("id")),
                  "kind": q.get("kind"), "target": q.get("target"),
                  "note": q.get("note")}
            _insert(q.get("id"), nq, "qualities")

        self.edges = []
        for e in data.get("edges", []) or []:
            if not isinstance(e, dict) or "from" not in e or "to" not in e:
                self.load_errors.append(f"edge missing 'from'/'to': {e!r}"); continue
            self.edges.append({"from": e["from"], "to": e["to"],
                               "type": e.get("type", "uses"), "label": e.get("label")})
        def _ref_list(owner, field, v):
            lst = _str_list(v)
            if lst is _INVALID:
                self.load_errors.append(
                    f"'{owner}': '{field}' must be a node id or list of node ids "
                    f"(got {type(v).__name__})")
                return []
            return lst

        for d in data.get("decisions", []) or []:
            if not isinstance(d, dict) or not d.get("id"):
                continue
            for tgt in _ref_list(d["id"], "governs", d.get("governs")):
                self.edges.append({"from": d["id"], "to": tgt, "type": "governs", "label": None})
            for tgt in _ref_list(d["id"], "supersedes", d.get("supersedes")):
                self.edges.append({"from": d["id"], "to": tgt,
                                   "type": "supersedes", "label": None})
        for q in data.get("qualities", []) or []:
            if not isinstance(q, dict) or not q.get("id"):
                continue
            for tgt in _ref_list(q["id"], "applies_to", q.get("applies_to")):
                self.edges.append({"from": q["id"], "to": tgt, "type": "constrains", "label": None})

    @classmethod
    def load(cls, path):
        try:
            with open(path) as f:
                data = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            raise SystemExit(f"error: {path}: not valid YAML — {e}")
        except OSError as e:
            raise SystemExit(f"error: {e}")
        return cls(data, path)

    # ---- integrity (referential + enum + hierarchy + rule schema) ----
    def validate(self):
        errs, warns = list(self.load_errors), []
        for nid, n in self.nodes.items():
            if n.get("type") not in NODE_TYPES:
                errs.append(f"node '{nid}': unknown type '{n.get('type')}'")
            if not n.get("label"):
                warns.append(f"node '{nid}': no label (will show id)")
            st = n.get("status")
            if n.get("type") == "decision":
                if st and st not in DECISION_STATUS:
                    errs.append(f"decision '{nid}': status '{st}' not in {sorted(DECISION_STATUS)}")
            elif st and st not in NODE_STATUS:
                errs.append(f"node '{nid}': status '{st}' not in {sorted(NODE_STATUS)}")
            p = n.get("parent")
            if p and p not in self.nodes:
                errs.append(f"node '{nid}': parent '{p}' does not exist")
        # parent cycles
        for nid in self.nodes:
            seen, cur = set(), nid
            while cur:
                if cur in seen:
                    errs.append(f"parent cycle involving '{nid}'"); break
                seen.add(cur)
                cur = self.nodes.get(cur, {}).get("parent")
        for e in self.edges:
            if e["type"] not in EDGE_TYPES:
                errs.append(f"edge {e['from']}->{e['to']}: unknown type '{e['type']}'")
            if e["from"] not in self.nodes:
                errs.append(f"edge references missing node '{e['from']}'")
            if e["to"] not in self.nodes:
                errs.append(f"edge references missing node '{e['to']}'")
        for i, r in enumerate(self.rules):
            rid = r.get("id", f"rule#{i}") if isinstance(r, dict) else f"rule#{i}"
            if not isinstance(r, dict):
                errs.append(f"rule '{rid}': not a mapping"); continue
            kind = r.get("rule")
            if kind not in RULE_KINDS:
                errs.append(f"rule '{rid}': unknown kind '{kind}' (known: {sorted(RULE_KINDS)})")
                continue
            unknown = set(r) - RULE_ALLOWED[kind]
            if unknown:
                errs.append(f"rule '{rid}': unknown key(s) {sorted(unknown)} — "
                            f"allowed for {kind}: {sorted(RULE_ALLOWED[kind])} "
                            f"(a typo here silently changes what the rule matches)")
            via = _coerce_via(r)
            if via is _INVALID:
                errs.append(f"rule '{rid}': 'via' must be a string or list of edge types "
                            f"(got {type(r.get('via')).__name__})")
            elif via is not None:
                bad = [x for x in via if not isinstance(x, str) or x not in EDGE_TYPES]
                if bad:
                    errs.append(f"rule '{rid}': unknown edge type(s) in via: {bad}")
            if kind == "forbid-dep":
                for side in ("from", "to"):
                    sel = r.get(side)
                    if sel is None:
                        continue
                    if not isinstance(sel, dict):
                        errs.append(f"rule '{rid}': '{side}' must be a mapping"); continue
                    badk = set(sel) - SELECTOR_KEYS
                    if badk:
                        errs.append(f"rule '{rid}': unknown selector key(s) {sorted(badk)} "
                                    f"in '{side}' — allowed: {sorted(SELECTOR_KEYS)}")
                    if "id" in sel and sel["id"] not in self.nodes:
                        warns.append(f"rule '{rid}': {side}.id '{sel['id']}' matches no node "
                                     f"— rule can never fire")
                    if "type" in sel and sel["type"] not in NODE_TYPES:
                        errs.append(f"rule '{rid}': {side}.type '{sel['type']}' is not a "
                                    f"known node type")
            if kind == "layer-order":
                layers = r.get("layers")
                if not isinstance(layers, list) or not layers:
                    errs.append(f"rule '{rid}': layer-order requires a non-empty 'layers' list")
        return errs, warns

    # ---- fitness functions (v0.2) ----
    def lint(self):
        errs, warns = self.validate()
        viols = list(errs)

        def match(sel, nid):
            if not sel:
                return True
            n = self.nodes.get(nid, {})
            if "id" in sel and nid != sel["id"]:
                return False
            if "type" in sel and n.get("type") != sel["type"]:
                return False
            if "layer" in sel and n.get("layer") != sel["layer"]:
                return False
            return True

        for i, r in enumerate(self.rules):
            if not isinstance(r, dict) or r.get("rule") not in RULE_KINDS:
                continue  # already reported by validate()
            rid = r.get("id", f"rule#{i}")
            kind = r.get("rule")
            raw_via = _coerce_via(r)
            if raw_via is _INVALID:
                continue  # already reported as a validate error above
            via = set(raw_via) if raw_via else None
            if kind == "forbid-dep":
                for e in self.edges:
                    if via and e["type"] not in via:
                        continue
                    if match(r.get("from"), e["from"]) and match(r.get("to"), e["to"]):
                        viols.append(f"[{rid}] forbidden dependency: "
                                     f"{e['from']} --{e['type']}--> {e['to']}"
                                     + (f"  ({r['why']})" if r.get("why") else ""))
            elif kind == "no-cycle":
                adj = defaultdict(list)
                for e in self.edges:
                    if via and e["type"] not in via:
                        continue
                    adj[e["from"]].append(e["to"])
                # iterative white/gray/black DFS — no recursion limit
                color, path = {}, []
                for start in list(adj):
                    if color.get(start):
                        continue
                    color[start] = 1; path.append(start)
                    stack = [(start, iter(adj[start]))]
                    while stack:
                        node, it = stack[-1]
                        v = next(it, None)
                        if v is None:
                            color[node] = 2; stack.pop(); path.pop(); continue
                        if color.get(v) == 1:
                            cyc = path[path.index(v):] + [v]
                            viols.append(f"[{rid}] cycle: {' -> '.join(cyc)}")
                        elif color.get(v) is None:
                            color[v] = 1; path.append(v)
                            stack.append((v, iter(adj.get(v, []))))
            elif kind == "layer-order":
                layers = r.get("layers", []) if isinstance(r.get("layers"), list) else []
                idx = {l: i for i, l in enumerate(layers)}
                unlayered = set()
                for e in self.edges:
                    if via and e["type"] not in via:
                        continue
                    lf = self.nodes.get(e["from"], {}).get("layer")
                    lt = self.nodes.get(e["to"], {}).get("layer")
                    for nid, l in ((e["from"], lf), (e["to"], lt)):
                        if l is None and nid in self.nodes:
                            unlayered.add(nid)
                    if lf in idx and lt in idx and idx[lf] > idx[lt]:
                        viols.append(f"[{rid}] layer violation: {e['from']} ({lf}) "
                                     f"--{e['type']}--> {e['to']} ({lt}); "
                                     f"dependencies must flow {' -> '.join(layers)}")
                if unlayered:
                    ex = ", ".join(sorted(unlayered)[:6])
                    more = "" if len(unlayered) <= 6 else f" (+{len(unlayered) - 6} more)"
                    warns.append(f"[{rid}] {len(unlayered)} node(s) on via-edges lack "
                                 f"'layer' and are EXEMPT from layering: {ex}{more}")
        # hygiene warnings
        deg = defaultdict(int)
        kids = defaultdict(int)
        for e in self.edges:
            deg[e["from"]] += 1; deg[e["to"]] += 1
        for n in self.nodes.values():
            if n.get("parent"):
                kids[n["parent"]] += 1
        for nid, n in self.nodes.items():
            if deg[nid] == 0 and kids[nid] == 0 and not n.get("parent"):
                warns.append(f"orphan node '{nid}' (no edges, no children, no parent)")
            if n.get("type") == "decision" and not n.get("status"):
                warns.append(f"decision '{nid}' has no status (proposed|accepted|superseded|deprecated)")
        return viols, warns


def view_graph(model, view):
    ntypes, etypes, anchors = VIEWS[view]
    incl = {nid for nid, n in model.nodes.items() if n.get("type") in ntypes}
    edges = [{"from": e["from"], "to": e["to"], "type": e["type"]}
             for e in model.edges
             if e["type"] in etypes and e["from"] in incl and e["to"] in incl]
    deg = defaultdict(int)
    for e in edges:
        deg[e["from"]] += 1; deg[e["to"]] += 1
    # prune unconnected context-type nodes (fixpoint: an empty boundary whose
    # only children were pruned goes too)
    while True:
        kids = defaultdict(int)
        for nid in incl:
            p = model.nodes[nid].get("parent")
            if p in incl:
                kids[p] += 1
        drop = {nid for nid in incl
                if model.nodes[nid].get("type") not in anchors
                and deg.get(nid, 0) == 0 and kids.get(nid, 0) == 0}
        if not drop:
            break
        incl -= drop
    nodes = []
    for nid in incl:
        n = model.nodes[nid]
        p = n.get("parent")
        nodes.append({"id": nid, "label": n.get("label", nid), "type": n["type"],
                      "status": n.get("status"),
                      "parent": p if p in incl else None})
    return {"nodes": nodes, "edges": edges}


def _view_nonempty(model, view):
    ntypes = VIEWS[view][0]
    return any(n.get("type") in ntypes for n in model.nodes.values())


# --------------------------------------------------------- mermaid fallback ---
def _sid(nid):
    s = re.sub(r"[^0-9a-zA-Z_]", "_", nid)
    return s if s and not s[0].isdigit() else "n_" + s


def _esc(s):
    return str(s).replace('"', "&quot;").replace("|", "/")


def mermaid_for_view(model, view):
    if view not in VIEWS:
        raise SystemExit(f"unknown view '{view}' (known: {', '.join(VIEWS)})")
    g = view_graph(model, view)   # flat — hierarchy is a viewer feature
    lines = ["graph LR"]
    for n in g["nodes"]:
        tmpl = NODE_TYPES[n["type"]][0]
        lines.append("  " + tmpl.format(i=_sid(n["id"]), l=_esc(n["label"])))
    for e in g["edges"]:
        lines.append(f'  {_sid(e["from"])} -->|{_esc(e["type"])}| {_sid(e["to"])}')
    return "\n".join(lines)


# ------------------------------------------------------------- traceability ---
def paths(model, src, dst, max_depth=8, limit=500):
    if src not in model.nodes:
        raise SystemExit(f"no such node '{src}'")
    if dst not in model.nodes:
        raise SystemExit(f"no such node '{dst}'")
    adj = defaultdict(list)
    for e in model.edges:
        adj[e["from"]].append((e["to"], e["type"]))
    out, q, truncated = [], deque([(src, [(src, None)])]), False
    while q:
        if limit and len(out) >= limit:   # limit 0/None = unbounded
            truncated = True; break
        cur, path = q.popleft()
        if len(path) > max_depth:
            continue
        if cur == dst and len(path) > 1:
            out.append(path); continue
        for nxt, et in adj[cur]:
            if nxt in [p[0] for p in path]:
                continue
            q.append((nxt, path + [(nxt, et)]))
    return out, truncated


# ----------------------------------------------------------------- viewer ---
VIEWER = r"""<!DOCTYPE html>
<html lang="en" data-theme="dark"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>__TITLE__ — Tekton</title>
<style>
:root{
  --bg:oklch(0.135 0.020 272); --card:oklch(0.175 0.025 272); --fg:oklch(0.965 0.004 265);
  --muted:oklch(0.62 0.020 270); --border:oklch(0.62 0.05 268 / 0.16);
  --border-strong:oklch(0.62 0.05 268 / 0.30); --blue:oklch(0.60 0.12 260);
  --frost:oklch(0.60 0.12 260 / 0.14);
  --glass:oklch(0.195 0.026 272 / 0.78); --glass-border:oklch(0.62 0.06 265 / 0.22);
  --glass-light:oklch(1 0 0 / 0.10);
  --shadow-card:0 6px 16px oklch(0 0 0 / 0.35), 0 1px 0 oklch(0.25 0.05 265 / 0.06);
  --shadow-glow:0 0 0 1px var(--blue), 0 0 26px oklch(0.60 0.12 260 / 0.34);
  --glass-elev:inset 0 1px 0 var(--glass-light), inset 0 0 0 1px oklch(1 0 0 / 0.05),
    0 2px 4px oklch(0.30 0.06 262 / 0.10), 0 24px 56px oklch(0.30 0.06 262 / 0.34);
  --t-actor:oklch(0.60 0.12 260); --t-journey:oklch(0.66 0.15 280);
  --t-step:oklch(0.62 0.02 270); --t-component:oklch(0.72 0.13 220);
  --t-service:oklch(0.72 0.13 220); --t-datastore:oklch(0.72 0.17 155);
  --t-entity:oklch(0.80 0.15 88); --t-infra:oklch(0.65 0.14 235);
  --t-external:oklch(0.84 0.07 240); --t-decision:oklch(0.64 0.20 25);
  --t-boundary:oklch(0.66 0.15 280); --t-quality:oklch(0.85 0.16 88);
  --radius:12px;
  --font:ui-sans-serif,-apple-system,system-ui,"Segoe UI",Helvetica,Arial,sans-serif;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,Monaco,monospace;
}
*{box-sizing:border-box}
html,body{height:100%;margin:0}
body{background:var(--bg);color:var(--fg);font-family:var(--font);display:flex;flex-direction:column;overflow:hidden}
header{padding:16px 22px 12px;border-bottom:1px solid var(--border);
  background:linear-gradient(160deg,oklch(0.60 0.12 260 / 0.06),transparent)}
h1{margin:0;font-size:18px;font-weight:600;letter-spacing:-.01em}
h1 .k{font-family:var(--mono);font-size:11px;letter-spacing:.16em;color:var(--blue);font-weight:500}
.desc{margin:4px 0 0;color:var(--muted);font-size:13px}
.bar{display:flex;align-items:center;gap:14px;justify-content:space-between;padding:12px 22px 0;flex-wrap:wrap}
.tabs{display:inline-flex;gap:4px;background:oklch(0.165 0.022 272);border:1px solid var(--border);
  border-radius:10px;padding:4px}
.tab{font:inherit;font-size:13px;color:var(--muted);background:transparent;border:0;
  padding:7px 14px;border-radius:7px;cursor:pointer;transition:.15s}
.tab:hover{color:var(--fg)}
.tab.on{color:var(--fg);background:var(--frost);box-shadow:inset 0 0 0 1px oklch(0.60 0.12 260 / 0.25)}
.hint{font-size:12px;color:var(--muted)}
.hint b{color:var(--fg);font-weight:500}
.vtitle{padding:10px 22px 0;color:var(--muted);font-size:12.5px}
#stage{position:relative;flex:1;overflow:hidden;margin:10px 16px 16px;border:1px solid var(--border);
  border-radius:16px;background:
    radial-gradient(oklch(0.62 0.05 268 / 0.10) 1px, transparent 1px) 0 0/22px 22px,
    oklch(0.15 0.021 272);cursor:grab;touch-action:none}
#stage:active{cursor:grabbing}
#world{position:absolute;left:0;top:0;transform-origin:0 0}
#edges{position:absolute;left:0;top:0;overflow:visible}
.edge{fill:none;stroke:var(--border-strong);stroke-width:1.5;transition:stroke .15s,opacity .15s}
.edge.hot{stroke:var(--blue);stroke-width:2.25}
.edge.dim{opacity:.14}
.elabel{position:absolute;transform:translate(-50%,-50%);font-family:var(--mono);font-size:10px;
  color:var(--muted);background:oklch(0.15 0.021 272);padding:1px 5px;border-radius:5px;
  border:1px solid var(--border);pointer-events:none;white-space:nowrap}
.elabel.dim{opacity:.12}
.group{position:absolute;border:1.5px solid color-mix(in oklch, var(--accent,var(--blue)) 55%, transparent);
  border-radius:16px;background:color-mix(in oklch, var(--accent,var(--blue)) 6%, transparent)}
.group.st-target{border-style:dashed}
.ghead{position:absolute;left:0;top:0;right:0;height:36px;display:flex;align-items:center;gap:8px;
  padding:0 14px;cursor:pointer;font-size:12.5px;font-weight:600;color:var(--fg)}
.ghead .gtype{font-family:var(--mono);font-size:10px;color:var(--muted);font-weight:400}
.ghead .chev{margin-left:auto;color:var(--muted);font-size:11px}
.node{position:absolute;display:flex;align-items:center;gap:10px;height:54px;padding:0 15px 0 13px;
  background:var(--card);color:var(--fg);border:1px solid var(--border);
  border-left:3px solid var(--accent,var(--blue));border-radius:var(--radius);
  box-shadow:var(--shadow-card);cursor:pointer;transition:box-shadow .15s,border-color .15s,transform .12s,opacity .15s}
.node:hover{border-color:var(--border-strong);transform:translateY(-1px)}
.node.sel{box-shadow:var(--shadow-glow);border-color:var(--accent)}
.node.dim{opacity:.28}
.node.st-target{border-style:dashed;border-left-style:solid;opacity:.9}
.node.st-deprecated{opacity:.45}
.node.st-deprecated .nlabel{text-decoration:line-through}
.ndot{width:9px;height:9px;border-radius:99px;background:var(--accent);flex:none;box-shadow:0 0 8px var(--accent)}
.nbody{min-width:0}
.nlabel{font-size:14px;font-weight:500;line-height:1.15;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.ntype{font-size:11px;color:var(--muted);font-family:var(--mono);letter-spacing:.02em}
.ntype .st{color:var(--t-quality)}
.ntype .st.dep{color:var(--t-decision)}
.node[data-type=actor],.group[data-type=actor]{--accent:var(--t-actor)}
.node[data-type=journey],.group[data-type=journey]{--accent:var(--t-journey)}
.node[data-type=step],.group[data-type=step]{--accent:var(--t-step)}
.node[data-type=component],.group[data-type=component]{--accent:var(--t-component)}
.node[data-type=service],.group[data-type=service]{--accent:var(--t-service)}
.node[data-type=datastore],.group[data-type=datastore]{--accent:var(--t-datastore)}
.node[data-type=entity],.group[data-type=entity]{--accent:var(--t-entity)}
.node[data-type=infra],.group[data-type=infra]{--accent:var(--t-infra)}
.node[data-type=external],.group[data-type=external]{--accent:var(--t-external)}
.node[data-type=decision],.group[data-type=decision]{--accent:var(--t-decision)}
.node[data-type=boundary],.group[data-type=boundary]{--accent:var(--t-boundary)}
.node[data-type=quality],.group[data-type=quality]{--accent:var(--t-quality)}
#detail{position:absolute;top:14px;right:14px;width:296px;max-height:calc(100% - 28px);overflow:auto;
  background:var(--glass);backdrop-filter:blur(22px) saturate(1.8);-webkit-backdrop-filter:blur(22px) saturate(1.8);
  border:1px solid var(--glass-border);border-radius:16px;box-shadow:var(--glass-elev);padding:15px 16px;display:none;z-index:6}
#detail.on{display:block}
#detail .dt{font-family:var(--mono);font-size:10px;letter-spacing:.08em;text-transform:uppercase;color:var(--blue)}
#detail .dt .st{color:var(--t-quality)}
#detail .dl{font-size:15px;font-weight:600;margin:3px 0 10px}
#detail .dnote{font-size:12.5px;color:var(--muted);margin:0 0 6px;line-height:1.5}
#detail h4{margin:12px 0 6px;font-size:11px;text-transform:uppercase;letter-spacing:.06em;color:var(--muted);font-weight:600}
#detail .adr{font-size:12.5px;line-height:1.5;color:var(--fg);margin:2px 0 8px}
#detail .adr b{color:var(--muted);font-weight:600;font-size:11px;text-transform:uppercase;letter-spacing:.04em;display:block}
#detail .q{font-size:12.5px;margin:4px 0;padding:7px 9px;border-radius:8px;
  background:color-mix(in oklch, var(--t-quality) 10%, transparent);
  border:1px solid color-mix(in oklch, var(--t-quality) 30%, transparent)}
#detail .q .qt{font-family:var(--mono);font-size:10.5px;color:var(--t-quality)}
#detail a{display:flex;gap:7px;align-items:baseline;padding:5px 7px;border-radius:8px;cursor:pointer;
  color:var(--fg);text-decoration:none;font-size:13px}
#detail a:hover{background:var(--frost)}
#detail a .et{font-family:var(--mono);font-size:10px;color:var(--muted);flex:none}
#detail a .tier{font-family:var(--mono);font-size:9.5px;color:var(--blue);margin-left:auto;flex:none}
#detail .close{position:absolute;top:12px;right:12px;color:var(--muted);cursor:pointer;font-size:16px;line-height:1}
#legend{position:absolute;left:14px;bottom:14px;display:flex;flex-wrap:wrap;gap:5px 12px;max-width:62%;
  background:oklch(0.165 0.022 272 / 0.85);border:1px solid var(--border);border-radius:10px;padding:9px 12px;z-index:5}
#legend span{display:inline-flex;align-items:center;gap:6px;font-size:11px;color:var(--muted)}
#legend i{width:8px;height:8px;border-radius:2px;display:inline-block}
#legend .dash{width:14px;height:0;border-top:2px dashed var(--muted);border-radius:0}
.tools{position:absolute;right:14px;bottom:14px;display:flex;gap:6px;z-index:5}
.tools button{font:inherit;font-size:12px;color:var(--muted);background:oklch(0.165 0.022 272 / 0.9);
  border:1px solid var(--border);border-radius:8px;padding:6px 10px;cursor:pointer}
.tools button:hover{color:var(--fg);border-color:var(--border-strong)}
</style></head><body>
<header>
  <h1>__TITLE__ &nbsp;<span class="k">TEKTON</span></h1>
  <p class="desc">__DESC__</p>
</header>
<div class="bar">
  <div class="tabs" id="tabs"></div>
  <div class="hint">click = <b>trace</b> · double-click a group/card = <b>collapse/expand</b> · scroll = zoom · drag = pan</div>
</div>
<p class="vtitle" id="vtitle"></p>
<div id="stage">
  <div id="world"></div>
  <div id="detail"></div>
  <div id="legend"></div>
  <div class="tools"><button id="fitb">Fit</button></div>
</div>
<script src="https://cdn.jsdelivr.net/npm/elkjs@0.9.3/lib/elk.bundled.js"></script>
<script>
const DATA = __DATA__;
const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const NS="http://www.w3.org/2000/svg";
const elk = new ELK();
const stage=document.getElementById('stage'), world=document.getElementById('world'),
      detail=document.getElementById('detail'), tabsEl=document.getElementById('tabs');
let view=DATA.order[0], tf={x:0,y:0,k:1}, worldW=1000, worldH=600, selId=null;
const collapsed=new Set(), cache={};

DATA.order.forEach((v,i)=>{const b=document.createElement('button');b.className='tab'+(i?'':' on');
  b.textContent=v;b.dataset.v=v;b.onclick=()=>switchView(v);tabsEl.appendChild(b);});
function switchView(v,thenSel){[...tabsEl.children].forEach(c=>c.classList.toggle('on',c.dataset.v===v));
  view=v;try{history.replaceState(null,'','#'+v);}catch(e){}
  if(!thenSel){selId=null;detail.classList.remove('on');}go(thenSel);}
const TYPES=['actor','journey','step','component','datastore','entity','infra','external','decision','boundary','quality'];
function drawLegend(vi){const present=TYPES.filter(t=>vi.g.nodes.some(n=>n.type===t||(t==='component'&&n.type==='service')));
  const hasTarget=vi.g.nodes.some(n=>n.status==='target');
  document.getElementById('legend').innerHTML=present.map(t=>
    `<span><i style="background:var(--t-${t})"></i>${t}</span>`).join('')+
    (hasTarget?`<span><i class="dash"></i>target (to-be)</span>`:'');}

// ---- per-view hierarchy helpers ----
function vinfo(v){const g=DATA.views[v];const byId={},kids={};
  g.nodes.forEach(n=>byId[n.id]=n);
  g.nodes.forEach(n=>{if(n.parent){(kids[n.parent]=kids[n.parent]||[]).push(n.id);}});
  const roots=g.nodes.filter(n=>!n.parent).map(n=>n.id);
  return {g,byId,kids,roots};}
function chain(byId,id){const c=[];let cur=id;while(cur){c.unshift(cur);cur=byId[cur]&&byId[cur].parent;}return c;}
function repr(vi,id){if(!vi.byId[id])return null;const c=chain(vi.byId,id);
  for(let i=0;i<c.length-1;i++){if(collapsed.has(c[i]))return c[i];}return id;}
function nodeW(l){return Math.min(276,Math.max(128,l.length*8+64));}
function isContainer(vi,id){return (vi.kids[id]||[]).length>0 && !collapsed.has(id);}

function buildElk(vi,id){
  const n=vi.byId[id],kids=vi.kids[id]||[];
  if(kids.length && !collapsed.has(id))
    return {id,layoutOptions:{'elk.padding':'[top=50,left=18,bottom=18,right=18]'},
            children:kids.map(k=>buildElk(vi,k))};
  const lbl=n.label+(kids.length?` (+${kids.length})`:'');
  return {id,width:nodeW(lbl),height:54};}

async function layout(v){
  const key=v+'|'+[...collapsed].sort().join(',');
  if(cache[key])return cache[key];
  const vi=vinfo(v);
  const seen=new Set(),edges=[];
  vi.g.edges.forEach((e,i)=>{const a=repr(vi,e.from),b=repr(vi,e.to);
    if(!a||!b||a===b)return;const k=a+'|'+b+'|'+e.type;if(seen.has(k))return;seen.add(k);
    edges.push({id:'e'+edges.length,sources:[a],targets:[b],_type:e.type,_from:a,_to:b});});
  const graph={id:'root',
    layoutOptions:{'elk.algorithm':'layered','elk.direction':'RIGHT',
      'elk.hierarchyHandling':'INCLUDE_CHILDREN',
      'elk.layered.spacing.nodeNodeBetweenLayers':'86','elk.spacing.nodeNode':'34',
      'elk.layered.nodePlacement.strategy':'NETWORK_SIMPLEX','elk.edgeRouting':'ORTHOGONAL'},
    children:vi.roots.map(r=>buildElk(vi,r)),edges};
  const res=await elk.layout(graph);res._edges=edges;cache[key]=res;return res;}

function svgel(t,a){const e=document.createElementNS(NS,t);for(const k in a)e.setAttribute(k,a[k]);return e;}
function pathFor(s){let p=`M${s.startPoint.x},${s.startPoint.y}`;
  (s.bendPoints||[]).forEach(b=>p+=` L${b.x},${b.y}`);p+=` L${s.endPoint.x},${s.endPoint.y}`;return p;}

let _gen=0;
async function go(thenSel){
  const g=++_gen;                       // re-entrancy guard: latest call wins
  document.getElementById('vtitle').textContent=DATA.views[view].title;
  const vi=vinfo(view),res=await layout(view);
  if(g!==_gen)return;                   // a newer render superseded this one
  world.innerHTML='';
  drawLegend(vi);
  worldW=Math.max(res.width||900,300);worldH=Math.max(res.height||500,300);
  const svg=svgel('svg',{id:'edges',width:worldW,height:worldH});
  const defs=svgel('defs',{});
  const mk=svgel('marker',{id:'ah',markerWidth:9,markerHeight:9,refX:8,refY:4.5,orient:'auto',markerUnits:'userSpaceOnUse'});
  mk.appendChild(svgel('path',{d:'M0,0 L9,4.5 L0,9 z',fill:'oklch(0.62 0.05 268 / 0.55)'}));
  defs.appendChild(mk);svg.appendChild(defs);
  world.appendChild(svg);
  // absolute position of every laid-out node (containers included) — needed to
  // resolve edge coordinate frames under INCLUDE_CHILDREN.
  const absPos={};
  (function ap(c,ox,oy){(c.children||[]).forEach(ch=>{const ax=ox+ch.x,ay=oy+ch.y;
    absPos[ch.id]={x:ax,y:ay};ap(ch,ax,ay);});})(res,0,0);
  // edges: ELK places a section's coords relative to the edge's CONTAINER
  // (the least common ancestor), not the root — offset accordingly.
  (res.edges||[]).forEach(re=>{if(!re.sections)return;const s=re.sections[0];
    const off=(re.container&&re.container!=='root'&&absPos[re.container])?absPos[re.container]:{x:0,y:0};
    const shift=pt=>({x:pt.x+off.x,y:pt.y+off.y});
    const sec={startPoint:shift(s.startPoint),endPoint:shift(s.endPoint),
               bendPoints:(s.bendPoints||[]).map(shift)};
    const p=svgel('path',{class:'edge',d:pathFor(sec),'marker-end':'url(#ah)'});
    p.dataset.from=re._from;p.dataset.to=re._to;svg.appendChild(p);
    const mid=sec.bendPoints.length?sec.bendPoints[Math.floor(sec.bendPoints.length/2)]
      :{x:(sec.startPoint.x+sec.endPoint.x)/2,y:(sec.startPoint.y+sec.endPoint.y)/2};
    const lab=document.createElement('div');lab.className='elabel';lab.textContent=re._type;
    lab.style.left=mid.x+'px';lab.style.top=mid.y+'px';lab.dataset.from=re._from;lab.dataset.to=re._to;
    world.appendChild(lab);});
  // nodes + groups, walking the hierarchy for absolute coords
  function walk(c,ox,oy){
    (c.children||[]).forEach(ch=>{
      const n=vi.byId[ch.id];if(!n)return;
      const ax=ox+ch.x,ay=oy+ch.y;
      if(ch.children&&ch.children.length){
        const g=document.createElement('div');g.className='group';g.dataset.id=ch.id;g.dataset.type=n.type;
        if(n.status)g.classList.add('st-'+n.status);
        g.style.left=ax+'px';g.style.top=ay+'px';g.style.width=ch.width+'px';g.style.height=ch.height+'px';
        const h=document.createElement('div');h.className='ghead';
        h.innerHTML=`<span>${esc(n.label)}</span><span class="gtype">${esc(n.type)}${n.status?' · '+esc(n.status):''}</span><span class="chev">▾ collapse</span>`;
        h.onclick=ev=>{ev.stopPropagation();select(ch.id);};
        h.ondblclick=ev=>{ev.stopPropagation();collapsed.add(ch.id);go(selId);};
        g.appendChild(h);world.appendChild(g);
        walk(ch,ax,ay);
      }else{
        const kids=(vi.kids[ch.id]||[]).length;
        const d=document.createElement('div');d.className='node';d.dataset.id=ch.id;d.dataset.type=n.type;
        if(n.status)d.classList.add('st-'+n.status);
        d.style.left=ax+'px';d.style.top=ay+'px';d.style.width=ch.width+'px';
        const stTxt=n.status?` · <span class="st${n.status==='deprecated'?' dep':''}">${esc(n.status)}</span>`:'';
        d.innerHTML=`<span class="ndot"></span><div class="nbody">
          <div class="nlabel">${esc(n.label)}${kids?` <span style="color:var(--muted)">(+${kids})</span>`:''}</div>
          <div class="ntype">${esc(n.type)}${stTxt}${kids?' · ▸ dbl-click to expand':''}</div></div>`;
        d.onclick=ev=>{ev.stopPropagation();select(ch.id);};
        if(kids)d.ondblclick=ev=>{ev.stopPropagation();collapsed.delete(ch.id);go(selId);};
        world.appendChild(d);
      }});}
  walk(res,0,0);
  world.style.width=worldW+'px';world.style.height=worldH+'px';
  fit();
  if(thenSel){const r=repr(vi,thenSel);if(r)select(r);}
  else if(selId){const r=repr(vi,selId);if(r)select(r);}
}

function fit(){const r=stage.getBoundingClientRect();
  const k=Math.min(r.width/worldW,r.height/worldH,1.15)*0.9;
  tf.k=k;tf.x=(r.width-worldW*k)/2;tf.y=(r.height-worldH*k)/2;apply();}
function apply(){world.style.transform=`translate(${tf.x}px,${tf.y}px) scale(${tf.k})`;}

function select(id){selId=id;const vi=vinfo(view);
  const nb=new Set([id]);
  world.querySelectorAll('.edge').forEach(p=>{const h=p.dataset.from===id||p.dataset.to===id;
    if(h){nb.add(p.dataset.from);nb.add(p.dataset.to);}
    p.classList.toggle('hot',h);p.classList.toggle('dim',!h);});
  world.querySelectorAll('.elabel').forEach(l=>{const h=l.dataset.from===id||l.dataset.to===id;
    l.classList.toggle('dim',!h);});
  world.querySelectorAll('.node,.group').forEach(n=>{const x=n.dataset.id;
    n.classList.toggle('sel',x===id);
    if(n.classList.contains('node'))n.classList.toggle('dim',!nb.has(x));});
  showDetail(id);}
function deselect(){selId=null;
  world.querySelectorAll('.node,.edge,.elabel,.group').forEach(e=>e.classList.remove('sel','dim','hot'));
  detail.classList.remove('on');}

function tierOf(id){const t=DATA.graph.nodes[id]&&DATA.graph.nodes[id].type;
  for(const v of DATA.order){if(v!==view&&DATA.views[v].nodes.some(n=>n.id===id))return v;}
  return t;}
function showDetail(id){const n=DATA.graph.nodes[id];if(!n)return;
  const vi=vinfo(view);
  const stTxt=n.status?` · <span class="st">${esc(n.status)}</span>`:'';
  let h=`<span class="close" id="dcl">✕</span><div class="dt">${esc(n.type)}${stTxt}</div><div class="dl">${esc(n.label)}</div>`;
  if(n.note)h+=`<p class="dnote">${esc(n.note)}</p>`;
  if(n.type==='decision'){
    if(n.context)h+=`<div class="adr"><b>Context</b>${esc(n.context)}</div>`;
    if(n.consequences)h+=`<div class="adr"><b>Consequences</b>${esc(n.consequences)}</div>`;}
  if(n.type==='quality'&&(n.kind||n.target))
    h+=`<div class="q"><span class="qt">${esc(n.kind||'quality')}</span><br>${esc(n.target||'')}</div>`;
  const qs=DATA.graph.edges.filter(e=>e.type==='constrains'&&e.to===id);
  if(qs.length){h+='<h4>quality constraints</h4>';
    qs.forEach(e=>{const q=DATA.graph.nodes[e.from];
      h+=`<div class="q"><span class="qt">${esc((q&&q.kind)||'quality')}</span> ${esc(q?q.label:e.from)}${q&&q.target?`<br><span style="color:var(--muted)">${esc(q.target)}</span>`:''}</div>`;});}
  const row=(e,other,dir)=>{const o=DATA.graph.nodes[other];const inView=!!vi.byId[other];
    const tier=inView?'':`<span class="tier">${esc(tierOf(other))} ↗</span>`;
    return `<a data-go="${esc(other)}" data-inview="${inView?1:0}"><span class="et">${esc(e.type)}</span><span>${esc(o?o.label:other)}</span>${tier}</a>`;};
  const out=DATA.graph.edges.filter(e=>e.from===id),inc=DATA.graph.edges.filter(e=>e.to===id&&e.type!=='constrains');
  if(out.length)h+='<h4>outgoing →</h4>'+out.map(e=>row(e,e.to)).join('');
  if(inc.length)h+='<h4>← incoming</h4>'+inc.map(e=>row(e,e.from)).join('');
  detail.innerHTML=h;detail.classList.add('on');
  detail.querySelector('#dcl').onclick=deselect;
  detail.querySelectorAll('[data-go]').forEach(a=>a.onclick=()=>{
    const t=a.dataset.go;
    if(a.dataset.inview==='1'){const r=repr(vinfo(view),t);if(r)select(r);}
    else{const v=DATA.order.find(v=>DATA.views[v].nodes.some(n=>n.id===t));
      if(v)switchView(v,t);}});}

stage.addEventListener('wheel',e=>{e.preventDefault();const r=stage.getBoundingClientRect();
  const mx=e.clientX-r.left,my=e.clientY-r.top,dk=Math.exp(-e.deltaY*0.0015);
  const nk=Math.min(2.6,Math.max(0.18,tf.k*dk));
  tf.x=mx-(mx-tf.x)*(nk/tf.k);tf.y=my-(my-tf.y)*(nk/tf.k);tf.k=nk;apply();},{passive:false});
let pan=null;
stage.addEventListener('pointerdown',e=>{if(e.target.closest('.node')||e.target.closest('#detail')||e.target.closest('.ghead'))return;
  pan={x:e.clientX,y:e.clientY,tx:tf.x,ty:tf.y};stage.setPointerCapture(e.pointerId);});
stage.addEventListener('pointermove',e=>{if(!pan)return;tf.x=pan.tx+(e.clientX-pan.x);tf.y=pan.ty+(e.clientY-pan.y);apply();});
stage.addEventListener('pointerup',()=>pan=null);
stage.addEventListener('click',e=>{if(!e.target.closest('.node')&&!e.target.closest('#detail')&&!e.target.closest('.ghead'))deselect();});
document.addEventListener('keydown',e=>{if(e.key==='Escape')deselect();});
document.getElementById('fitb').onclick=fit;
window.addEventListener('resize',fit);
// deep-link: open directly on #<view>; single entry point (no double-render race)
{const h=location.hash.replace('#','');
 if(DATA.order.includes(h))switchView(h); else go();}
</script></body></html>"""


def render_html(model):
    order = [v for v in VIEWS if _view_nonempty(model, v)] or list(VIEWS)
    gnodes = {}
    for nid, n in model.nodes.items():
        gnodes[nid] = {k: n.get(k) for k in
                       ("label", "type", "status", "parent", "note", "context",
                        "consequences", "kind", "target") if n.get(k) is not None}
        gnodes[nid].setdefault("label", nid)
    data = {
        "meta": {"name": model.name, "desc": model.description,
                 "nodes": len(model.nodes), "edges": len(model.edges)},
        "views": {v: {"title": VIEW_TITLES[v], **view_graph(model, v)} for v in order},
        "graph": {"nodes": gnodes,
                  "edges": [{"from": e["from"], "to": e["to"], "type": e["type"]}
                            for e in model.edges]},
        "order": order,
    }
    # Split on __DATA__ FIRST, then substitute TITLE/DESC only in the template
    # halves — model text containing any sentinel can neither be clobbered nor
    # leak the JSON blob. Escape "</" so a label containing "</script>" cannot
    # terminate the script block (valid JSON: \/).
    safe_json = json.dumps(data).replace("</", "<\\/")
    head, tail = VIEWER.split("__DATA__", 1)
    title, desc = _html.escape(model.name), _html.escape(model.description)
    head = head.replace("__TITLE__", title).replace("__DESC__", desc)
    tail = tail.replace("__TITLE__", title).replace("__DESC__", desc)
    return head + safe_json + tail


# ---------------------------------------------------------------- cli ---
def main():
    ap = argparse.ArgumentParser(prog="tekton", description="shared architecture-intent model engine")
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("views")
    for c in ("validate", "lint", "stats"):
        sp = sub.add_parser(c); sp.add_argument("model")
    sp = sub.add_parser("mermaid"); sp.add_argument("model"); sp.add_argument("view")
    sp = sub.add_parser("render"); sp.add_argument("model"); sp.add_argument("-o", "--out")
    sp = sub.add_parser("query"); sp.add_argument("model"); sp.add_argument("src"); sp.add_argument("dst")
    sp.add_argument("--max-depth", type=int, default=8); sp.add_argument("--limit", type=int, default=500)
    args = ap.parse_args()

    if args.cmd == "views":
        for v in VIEWS:
            print(f"{v:11} {VIEW_TITLES[v]}")
        return
    if not args.cmd:
        ap.print_help(); return

    m = Model.load(args.model)

    if args.cmd == "validate":
        errs, warns = m.validate()
        for w in warns: print(f"warn: {w}")
        for e in errs: print(f"ERROR: {e}")
        print(f"\n{'INVALID' if errs else 'valid'}: {len(m.nodes)} nodes, {len(m.edges)} edges, "
              f"{len(errs)} errors, {len(warns)} warnings")
        sys.exit(1 if errs else 0)

    if args.cmd == "lint":
        viols, warns = m.lint()
        for w in warns: print(f"warn: {w}")
        for v in viols: print(f"VIOLATION: {v}")
        print(f"\n{'FAIL' if viols else 'PASS'}: {len(m.rules)} rules, "
              f"{len(viols)} violations, {len(warns)} warnings")
        sys.exit(1 if viols else 0)

    if args.cmd == "stats":
        by = defaultdict(int)
        st = defaultdict(int)
        for n in m.nodes.values():
            by[n.get("type")] += 1
            st[n.get("status") or "current"] += 1
        et = defaultdict(int)
        for e in m.edges: et[e["type"]] += 1
        print(f"{m.name}: {len(m.nodes)} nodes, {len(m.edges)} edges, {len(m.rules)} rules")
        print("nodes:", ", ".join(f"{k}={v}" for k, v in sorted(by.items())))
        print("status:", ", ".join(f"{k}={v}" for k, v in sorted(st.items())))
        print("edges:", ", ".join(f"{k}={v}" for k, v in sorted(et.items())))
        print("views:", ", ".join(v for v in VIEWS if _view_nonempty(m, v)))
        return

    if args.cmd == "mermaid":
        print(mermaid_for_view(m, args.view)); return

    if args.cmd == "render":
        errs, _ = m.validate()
        if errs:
            for e in errs: print(f"ERROR: {e}")
            print(f"refusing to render: {len(errs)} validate error(s) — "
                  f"a structurally invalid model (e.g. parent cycle) can hang the viewer")
            sys.exit(1)
        out = args.out or os.path.splitext(args.model)[0] + ".view.html"
        with open(out, "w") as f:
            f.write(render_html(m))
        print(f"rendered {len([v for v in VIEWS if _view_nonempty(m, v)])} views → {out}")
        return

    if args.cmd == "query":
        ps, truncated = paths(m, args.src, args.dst,
                              max_depth=args.max_depth, limit=args.limit)
        if not ps:
            print(f"no directed path {args.src} → {args.dst}"); return
        print(f"{len(ps)} path(s) {args.src} → {args.dst}"
              + (f" (TRUNCATED at --limit {args.limit})" if truncated else "") + ":")
        for p in ps:
            seg = []
            for i, (nid, et) in enumerate(p):
                lbl = m.nodes[nid].get("label", nid)
                seg.append(lbl if i == 0 else f"--[{et}]--> {lbl}")
            print("  " + " ".join(seg))
        return


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:      # `tekton query … | head` is a legitimate use
        os._exit(0)
