// KgGraph.jsx · the hierarchical, force-directed knowledge graph for the
// Knowledge page. Nodes are files; edges are `related:` links; gold nodes are
// folders you can enter (zoom-morph between scopes). Plus the surfaces the page
// flows need: type-filter dimming, auto-frame-to-matches on search, a hover
// preview card, a minimap, and KgMiniGraph for the detail drawer.

// Scope (folder) nodes · blue-black ink, in the system's one hue family.
const KG_GOLD = "oklch(0.38 0.045 265)";
const KG_TYPE = {
  concept:   { color: "var(--bv-blue)",            label: "concept"   },
  pattern:   { color: "var(--bv-glow-indigo)",     label: "pattern"   },
  primitive: { color: "var(--bv-blue-accent)",     label: "primitive" },
  tool:      { color: "oklch(0.60 0.09 245)",      label: "tool"      },
  person:    { color: "var(--bv-gray-600)",        label: "person"    },
  paper:     { color: "oklch(0.70 0.06 260)",      label: "paper"     },
  decision:  { color: "oklch(0.50 0.14 260)",      label: "decision"  },
  doc:       { color: "var(--bv-gray-500)",        label: "doc"       },
  session:   { color: "var(--bv-info)",            label: "session"   },
  vault:      { color: KG_GOLD, label: "meta-vault" },
  workspace:  { color: KG_GOLD, label: "workspace"  },
  initiative: { color: KG_GOLD, label: "initiative" },
  project:    { color: KG_GOLD, label: "project"    },
  task:       { color: KG_GOLD, label: "task"       },
  routine:    { color: KG_GOLD, label: "routine"    },
};
const kgIsScope = (n) => !!n.scopeRef;
const kgCategory = (n) => kgIsScope(n) ? "folder" : n.type;
const kgTypeColor = (n) => kgIsScope(n) ? KG_GOLD : (KG_TYPE[n.type] || KG_TYPE.concept).color;

function kgHash(s) { let h = 2166136261; for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0) / 4294967295; }

function kgEdges(nodes) {
  const ids = new Set(nodes.map((n) => n.id));
  const seen = new Set(), out = [];
  nodes.forEach((n) => (n.related || []).forEach((r) => {
    if (!ids.has(r)) return;
    const key = [n.id, r].sort().join("|");
    if (seen.has(key) || n.id === r) return;
    seen.add(key); out.push({ s: n.id, t: r });
  }));
  return out;
}

function kgLayout(nodes, edges, W, H) {
  const pos = {};
  nodes.forEach((n) => {
    const a = kgHash(n.id) * Math.PI * 2;
    const r = (kgIsScope(n) ? 20 : 55) + kgHash(n.id + "r") * Math.min(W, H) * 0.28;
    pos[n.id] = { x: W / 2 + Math.cos(a) * r, y: H / 2 + Math.sin(a) * r, vx: 0, vy: 0 };
  });
  const cx = W / 2, cy = H / 2, ideal = 116;
  for (let it = 0; it < 340; it++) {
    const alpha = 1 - it / 340;
    for (let i = 0; i < nodes.length; i++) for (let j = i + 1; j < nodes.length; j++) {
      const a = pos[nodes[i].id], b = pos[nodes[j].id];
      let dx = a.x - b.x, dy = a.y - b.y, d2 = dx * dx + dy * dy || 0.01, d = Math.sqrt(d2);
      const f = 4600 / d2, ux = dx / d, uy = dy / d;
      a.vx += ux * f; a.vy += uy * f; b.vx -= ux * f; b.vy -= uy * f;
    }
    edges.forEach((e) => {
      const a = pos[e.s], b = pos[e.t]; if (!a || !b) return;
      let dx = b.x - a.x, dy = b.y - a.y, d = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const f = (d - ideal) * 0.022, ux = dx / d, uy = dy / d;
      a.vx += ux * f; a.vy += uy * f; b.vx -= ux * f; b.vy -= uy * f;
    });
    nodes.forEach((n) => {
      const p = pos[n.id], pull = kgIsScope(n) ? 0.03 : 0.009;
      p.vx += (cx - p.x) * pull; p.vy += (cy - p.y) * pull;
      p.x += p.vx * alpha * 0.85; p.y += p.vy * alpha * 0.85; p.vx *= 0.82; p.vy *= 0.82;
      p.x = Math.max(46, Math.min(W - 46, p.x)); p.y = Math.max(40, Math.min(H - 36, p.y));
    });
  }
  return pos;
}

const kgLerp = (a, b, t) => a + (b - a) * t;
const kgClamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const kgScaleAround = (px, py, s) => `translate(${(px * (1 - s)).toFixed(2)} ${(py * (1 - s)).toFixed(2)}) scale(${s.toFixed(4)})`;
const kgNodeR = (n, deg) => kgIsScope(n) ? 13 + Math.min(deg || 0, 5) : 7 + Math.min(deg || 0, 6) * 1.4;

// Tiny radial neighborhood graph for the detail drawer (center + neighbours).
function KgMiniGraph({ scope, centerId, onPick, w = 300, h = 190 }) {
  const center = scope.nodes.find((n) => n.id === centerId);
  if (!center) return null;
  const nb = scope.nodes.filter((n) => n.id !== centerId && ((center.related || []).includes(n.id) || (n.related || []).includes(centerId)));
  const cx = w / 2, cy = h / 2, R = Math.min(w, h) / 2 - 30;
  const pts = nb.map((n, i) => { const a = -Math.PI / 2 + (i / Math.max(nb.length, 1)) * Math.PI * 2; return { n, x: cx + Math.cos(a) * R, y: cy + Math.sin(a) * R }; });
  return (
    <svg viewBox={`0 0 ${w} ${h}`} className="kg-mini" preserveAspectRatio="xMidYMid meet">
      {pts.map((p, i) => <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} className="kg-edge" style={{ opacity: 0.35 }} />)}
      {pts.map((p) => (
        <g key={p.n.id} transform={`translate(${p.x} ${p.y})`} style={{ cursor: "pointer" }} onClick={() => onPick && onPick(p.n.id)}>
          <circle r={kgIsScope(p.n) ? 8 : 6} fill={kgTypeColor(p.n)} stroke="var(--card)" strokeWidth="2" />
          <text className="kg-mini-label" x={0} y={kgIsScope(p.n) ? 19 : 17} textAnchor="middle">{p.n.label}</text>
        </g>
      ))}
      <g transform={`translate(${cx} ${cy})`}>
        <circle r={11} fill={kgTypeColor(center)} stroke="var(--card)" strokeWidth="2.5" />
      </g>
    </svg>
  );
}

function KgGraph({ scope, scopes, selectedId, onSelectNode, onNavigate, query, typeFilter, width = 840, height = 560 }) {
  const cache = React.useRef({});
  const getLayout = React.useCallback((sc) => {
    if (!cache.current[sc.id]) {
      const edges = kgEdges(sc.nodes), pos = kgLayout(sc.nodes, edges, width, height), deg = {};
      sc.nodes.forEach((n) => (deg[n.id] = 0)); edges.forEach((e) => { deg[e.s]++; deg[e.t]++; });
      cache.current[sc.id] = { pos, edges, deg };
    }
    return cache.current[sc.id];
  }, [width, height]);

  const [view, setView] = React.useState({ tx: 0, ty: 0, k: 1 });
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
    let p = desc; while (p && p.parent && p.parent !== ancId) p = scopes[p.parent];
    return (p && p.parent === ancId) ? p : null;
  }, [scopes]);

  const layout = getLayout(scope);
  const pos = { ...layout.pos, ...override };
  const edges = layout.edges, deg = layout.deg;
  const q = (query || "").trim().toLowerCase();
  const nodeById = React.useMemo(() => Object.fromEntries(scope.nodes.map((n) => [n.id, n])), [scope]);
  const isHit = (id) => { if (!q) return true; const n = nodeById[id]; return (n.label + " " + (n.claim || "") + " " + n.type).toLowerCase().includes(q); };
  const offType = (n) => typeFilter && typeFilter.size && !typeFilter.has(kgCategory(n));
  const neighbors = (id) => { const s = new Set([id]); edges.forEach((e) => { if (e.s === id) s.add(e.t); if (e.t === id) s.add(e.s); }); return s; };
  const focusId = hover || selectedId;
  const focusSet = focusId ? neighbors(focusId) : null;

  // morph on scope change
  React.useEffect(() => {
    const from = prevScope.current, to = scope;
    if (from.id === to.id) return;
    setView({ tx: 0, ty: 0, k: 1 }); setOverride({});
    let dir = "jump", anchor = { x: width / 2, y: height / 2 };
    const down = childOnPath(from.id, to), up = childOnPath(to.id, from);
    if (down) { dir = "descend"; const a = getLayout(from).pos[down.id]; if (a) anchor = { x: a.x, y: a.y }; }
    else if (up) { dir = "ascend"; const a = getLayout(to).pos[up.id]; if (a) anchor = { x: a.x, y: a.y }; }
    cancelAnimationFrame(raf.current);
    const start = performance.now(), dur = 660;
    const tick = (now) => {
      const raw = Math.min(1, (now - start) / dur);
      const e = raw < 0.5 ? 2 * raw * raw : 1 - Math.pow(-2 * raw + 2, 2) / 2;
      setTrans({ from, to, dir, anchor, t: e });
      if (raw < 1) raf.current = requestAnimationFrame(tick); else setTrans(null);
    };
    raf.current = requestAnimationFrame(tick);
    prevScope.current = scope;
    return () => cancelAnimationFrame(raf.current);
  }, [scope, childOnPath, getLayout, width, height]);

  // auto-frame to search matches (and reset when cleared)
  React.useEffect(() => {
    if (trans) return;
    if (!q) { setView({ tx: 0, ty: 0, k: 1 }); return; }
    const hits = scope.nodes.filter((n) => isHit(n.id)).map((n) => pos[n.id]).filter(Boolean);
    if (!hits.length) return;
    let x0 = 1e9, y0 = 1e9, x1 = -1e9, y1 = -1e9;
    hits.forEach((p) => { x0 = Math.min(x0, p.x); y0 = Math.min(y0, p.y); x1 = Math.max(x1, p.x); y1 = Math.max(y1, p.y); });
    const pad = 110, bw = (x1 - x0) + pad, bh = (y1 - y0) + pad, cx = (x0 + x1) / 2, cy = (y0 + y1) / 2;
    const k = kgClamp(Math.min(width / bw, height / bh), 0.6, 2.0);
    setView({ k, tx: width / 2 - cx * k, ty: height / 2 - cy * k });
  }, [query, scope]); // eslint-disable-line

  const toWorld = (cx, cy) => {
    const r = svgRef.current.getBoundingClientRect(), sx = r.width / width, sy = r.height / height;
    return { x: ((cx - r.left) / sx - view.tx) / view.k, y: ((cy - r.top) / sy - view.ty) / view.k };
  };
  const onDown = (e, id) => {
    e.preventDefault(); svgRef.current.setPointerCapture(e.pointerId);
    if (id) drag.current = { type: "node", id, moved: false };
    else { drag.current = { type: "pan", x0: e.clientX, y0: e.clientY, tx: view.tx, ty: view.ty }; setPanning(true); }
  };
  const onMove = (e) => {
    const d = drag.current; if (!d) return;
    if (d.type === "node") { d.moved = true; const w = toWorld(e.clientX, e.clientY); setOverride((o) => ({ ...o, [d.id]: { x: w.x, y: w.y } })); }
    else { const r = svgRef.current.getBoundingClientRect(), sx = r.width / width, sy = r.height / height; setView((v) => ({ ...v, tx: d.tx + (e.clientX - d.x0) / sx, ty: d.ty + (e.clientY - d.y0) / sy })); }
  };
  const onUp = (e) => { if (svgRef.current.hasPointerCapture(e.pointerId)) svgRef.current.releasePointerCapture(e.pointerId); drag.current = null; setPanning(false); };
  const zoom = (f) => setView((v) => { const k = kgClamp(v.k * f, 0.45, 2.6), cx = width / 2, cy = height / 2; return { k, tx: cx - (cx - v.tx) * (k / v.k), ty: cy - (cy - v.ty) * (k / v.k) }; });

  // hover preview position (px within the stage)
  const hoverNode = hover && !panning && !trans && !drag.current ? nodeById[hover] : null;
  const hoverPos = (() => {
    if (!hoverNode || !svgRef.current || !stageRef.current) return null;
    const p = pos[hover]; if (!p) return null;
    const r = svgRef.current.getBoundingClientRect(), st = stageRef.current.getBoundingClientRect();
    const sx = r.width / width, sy = r.height / height;
    return { x: r.left - st.left + (view.tx + p.x * view.k) * sx, y: r.top - st.top + (view.ty + p.y * view.k) * sy, r: kgNodeR(hoverNode, deg[hover]) * sx };
  })();

  const drawNet = (sc, P, EG, DG, live) => (
    <>
      {EG.map((e, i) => {
        const a = P[e.s], b = P[e.t]; if (!a || !b) return null;
        const on = live && focusId && (e.s === focusId || e.t === focusId);
        const faded = live && ((q && (!isHit(e.s) || !isHit(e.t))) || (focusSet && !on) || offType(nodeById[e.s]) || offType(nodeById[e.t]));
        return <line key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y} className={"kg-edge" + (on ? " is-on" : "")} style={{ opacity: faded ? 0.06 : on ? 0.9 : 0.3 }} />;
      })}
      {sc.nodes.map((n) => {
        const p = P[n.id]; if (!p) return null;
        const t = KG_TYPE[n.type] || KG_TYPE.concept, r = kgNodeR(n, DG[n.id]), folder = kgIsScope(n);
        const sel = live && n.id === selectedId;
        const faded = live && ((!isHit(n.id)) || offType(n) || (focusSet && !focusSet.has(n.id)));
        return (
          <g key={n.id} transform={`translate(${p.x.toFixed(2)} ${p.y.toFixed(2)})`} className="kg-node"
            style={{ opacity: faded ? 0.18 : 1, cursor: live ? "pointer" : "default" }}
            onPointerDown={live ? (e) => { e.stopPropagation(); onDown(e, n.id); } : undefined}
            onClick={live ? (e) => { e.stopPropagation(); if (drag.current && drag.current.moved) return; if (folder) onNavigate && onNavigate(n.scopeRef); else onSelectNode && onSelectNode(n.id); } : undefined}
            onPointerEnter={live ? () => setHover(n.id) : undefined}
            onPointerLeave={live ? () => setHover((h) => (h === n.id ? null : h)) : undefined}>
            {sel && <circle r={r + 6} className="kg-ring" />}
            {folder && <circle r={r + 5} className="kg-scope-ring" />}
            <circle r={r} fill={t.color} className={"kg-dot" + (n.live ? " kg-live" : "")} stroke="var(--background)" strokeWidth={folder ? 2.5 : 2} />
            {folder && <path d="M-4.5 -2.2 h2.4 l1 1.3 h4.6 a0.7 0.7 0 0 1 0.7 0.7 v3.4 a0.7 0.7 0 0 1 -0.7 0.7 h-8 a0.7 0.7 0 0 1 -0.7 -0.7 v-4.7 a0.7 0.7 0 0 1 0.7 -0.7 z" fill="var(--card)" opacity="0.92" />}
            {n.live && <circle r={r} fill="none" stroke={t.color} className="kg-pulse" />}
            <text className="kg-label" x={0} y={r + 13} textAnchor="middle" style={{ fontWeight: folder || sel || n.id === focusId ? 600 : 400 }}>{n.label}</text>
          </g>
        );
      })}
    </>
  );

  let content;
  if (trans) {
    const { from, to, dir, anchor, t } = trans, lf = getLayout(from), lt = getLayout(to);
    let fromTf, fromOp, toTf, toOp, order;
    if (dir === "descend") { fromTf = kgScaleAround(anchor.x, anchor.y, kgLerp(1, 2.9, t)); fromOp = kgClamp(1 - t * 1.7, 0, 1); toTf = kgScaleAround(width / 2, height / 2, kgLerp(0.38, 1, t)); toOp = kgClamp((t - 0.32) / 0.68, 0, 1); order = "ft"; }
    else if (dir === "ascend") { fromTf = kgScaleAround(width / 2, height / 2, kgLerp(1, 0.4, t)); fromOp = kgClamp(1 - t * 1.7, 0, 1); toTf = kgScaleAround(anchor.x, anchor.y, kgLerp(2.9, 1, t)); toOp = kgClamp((t - 0.28) / 0.72, 0, 1); order = "tf"; }
    else { fromTf = kgScaleAround(width / 2, height / 2, kgLerp(1, 1.25, t)); fromOp = kgClamp(1 - t * 1.6, 0, 1); toTf = kgScaleAround(width / 2, height / 2, kgLerp(0.85, 1, t)); toOp = kgClamp((t - 0.4) / 0.6, 0, 1); order = "ft"; }
    const fromG = <g key="from" transform={fromTf} style={{ opacity: fromOp, pointerEvents: "none" }}>{drawNet(from, lf.pos, lf.edges, lf.deg, false)}</g>;
    const toG = <g key="to" transform={toTf} style={{ opacity: toOp, pointerEvents: "none" }}>{drawNet(to, lt.pos, lt.edges, lt.deg, false)}</g>;
    content = order === "ft" ? [fromG, toG] : [toG, fromG];
  } else {
    content = <g transform={`translate(${view.tx} ${view.ty}) scale(${view.k})`} style={{ transition: panning ? "none" : "transform 0.45s var(--bv-ease-standard)" }}>{drawNet(scope, pos, edges, deg, true)}</g>;
  }

  // minimap geometry
  const mmW = 150, mmH = 108, mmK = Math.min(mmW / width, mmH / height) * 0.9, mmOx = (mmW - width * mmK) / 2, mmOy = (mmH - height * mmK) / 2;
  const vx = (-view.tx / view.k), vy = (-view.ty / view.k), vw = width / view.k, vh = height / view.k;
  const onMinimap = (e) => {
    const r = e.currentTarget.getBoundingClientRect();
    const mx = (e.clientX - r.left) / r.width * mmW, my = (e.clientY - r.top) / r.height * mmH;
    const lx = (mx - mmOx) / mmK, ly = (my - mmOy) / mmK;
    setView((v) => ({ ...v, tx: width / 2 - lx * v.k, ty: height / 2 - ly * v.k }));
  };

  return (
    <div className="kg-stage" ref={stageRef}>
      <svg ref={svgRef} className="kg-svg" viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="xMidYMid meet"
        onPointerDown={trans ? undefined : (e) => onDown(e, null)} onPointerMove={onMove} onPointerUp={onUp} onPointerCancel={onUp}>
        {content}
      </svg>

      {hoverNode && hoverPos && (
        <div className="kg-hovercard" style={{ left: hoverPos.x, top: hoverPos.y - (hoverPos.r + 10) }}>
          <div className="kg-hover-row">
            <span className="kg-legend-dot" style={{ background: kgTypeColor(hoverNode) }}></span>
            <b>{hoverNode.label}</b>
            <span className="kg-hover-kind">{(KG_TYPE[hoverNode.type] || {}).label || hoverNode.type}</span>
          </div>
          <p className="kg-hover-claim">{hoverNode.claim}</p>
          {hoverNode.score && <div className="kg-hover-score">Nous {hoverNode.score[0] + hoverNode.score[1] + hoverNode.score[2]}/9</div>}
          {kgIsScope(hoverNode) && <div className="kg-hover-enter">click to enter →</div>}
        </div>
      )}

      <div className="kg-minimap" onPointerDown={onMinimap}>
        <svg viewBox={`0 0 ${mmW} ${mmH}`} width={mmW} height={mmH}>
          <rect x="0" y="0" width={mmW} height={mmH} className="kg-mm-bg" />
          {scope.nodes.map((n) => { const p = pos[n.id]; if (!p) return null; return <circle key={n.id} cx={mmOx + p.x * mmK} cy={mmOy + p.y * mmK} r={kgIsScope(n) ? 2.6 : 1.8} fill={kgTypeColor(n)} />; })}
          <rect className="kg-mm-view" x={mmOx + vx * mmK} y={mmOy + vy * mmK} width={vw * mmK} height={vh * mmK} />
        </svg>
      </div>

      <div className="kg-zoom">
        <button type="button" onClick={() => zoom(1.25)} title="Zoom in" aria-label="Zoom in">+</button>
        <button type="button" onClick={() => zoom(0.8)} title="Zoom out" aria-label="Zoom out">−</button>
        <button type="button" onClick={() => setView({ tx: 0, ty: 0, k: 1 })} title="Reset view" aria-label="Reset view">⊙</button>
      </div>

      <div className="kg-legend">
        {[["folder", "folder"], ["concept", "concept"], ["decision", "decision"], ["primitive", "primitive"], ["session", "session"]].map(([k, lab]) => (
          <span key={k} className="kg-legend-item"><span className="kg-legend-dot" style={{ background: k === "folder" ? KG_GOLD : KG_TYPE[k].color }}></span>{lab}</span>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { KgGraph, KgMiniGraph, KG_TYPE, KG_GOLD, kgIsScope, kgCategory, kgTypeColor });
