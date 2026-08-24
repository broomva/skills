import type { ActiveOntology } from "../core/ontology";
import type { Certificate, Score, Trajectory } from "../core/ops";
import { splitOrigins } from "../core/provenance";

/**
 * The receipt: a self-contained page describing one run.
 *
 * This is the artifact the agent hands back into the thread. It exists because
 * a number delivered over WhatsApp has no room to carry its own provenance, and
 * a number without provenance is the thing this system refuses to produce. So
 * the message carries the answer and a link, and the link carries the proof.
 *
 * Self-contained by construction -- no external CSS, fonts, scripts or images.
 * It is served read-only from a static directory, and anything it fetched at
 * view time would be a claim the reader cannot check.
 */

export interface RunReceipt {
  readonly runId: string;
  readonly ontology: ActiveOntology;
  readonly certificate: Certificate;
  readonly trajectory: Trajectory;
  readonly scores: Score[];
  readonly traceHash: string;
  readonly branchClass: string;
  readonly baseline?: { readonly traceHash: string; readonly violations: number };
}

const esc = (s: unknown): string =>
  String(s).replace(
    /[&<>"']/g,
    (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c] ?? c,
  );

export function renderReceipt(r: RunReceipt): string {
  const origins = splitOrigins(r.trajectory.map((s) => s.origin));
  const violations = r.trajectory.flatMap((s) => s.violations);
  const total = origins.observed + origins.simulated;
  const observedPct = total === 0 ? 0 : Math.round((origins.observed / total) * 100);

  const steps = r.trajectory
    .map((s, i) => {
      const bad = s.violations.length > 0;
      return `<tr class="${bad ? "bad" : ""}">
      <td class="m dim">${String(i).padStart(3, "0")}</td>
      <td class="m">${esc(s.event.actor)}</td>
      <td class="m">${esc(s.event.action)}</td>
      <td class="m dim">${esc(JSON.stringify(s.event.params))}</td>
      <td class="m"><span class="tag ${s.origin}">${s.origin}</span></td>
      <td class="m">${bad ? `<span class="viol">${esc(s.violations.map((v) => v.invariant).join(", "))}</span>` : "<span class='dim'>-</span>"}</td>
    </tr>`;
    })
    .join("\n");

  const scoreRows = r.scores
    .map(
      (s) => `<tr>
      <td class="m">${esc(s.objective)}</td>
      <td class="m num">${esc(s.value)}</td>
      <td class="m"><span class="tag ${s.admissible ? "ok" : "no"}">${s.admissible ? "admissible" : "inadmissible"}</span></td>
      <td class="m"><span class="tag ${s.origin}">${s.origin}</span></td>
    </tr>`,
    )
    .join("\n");

  const verdict = buildVerdict(r, violations.length, observedPct);

  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Parallax run ${esc(r.runId.slice(0, 8))}</title>
<style>
:root{
  --bg:#0F1216; --panel:#151A20; --line:rgba(226,232,240,.14); --line-2:rgba(226,232,240,.22);
  --fg:rgba(226,232,240,.92); --fg-2:rgba(226,232,240,.66); --fg-3:rgba(226,232,240,.42);
  --accent:#5B8DEF; --warn:#D8A657; --bad:#E0796B; --ok:#7FB283;
  --mono:ui-monospace,SFMono-Regular,"SF Mono",Menlo,monospace;
  --sans:ui-sans-serif,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
}
@media(prefers-color-scheme:light){:root{
  --bg:#FBFCFD; --panel:#FFF; --line:rgba(15,18,22,.12); --line-2:rgba(15,18,22,.2);
  --fg:rgba(15,18,22,.92); --fg-2:rgba(15,18,22,.62); --fg-3:rgba(15,18,22,.42);
}}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--fg);font-family:var(--sans);font-size:15px;line-height:1.6;
  background-image:linear-gradient(var(--line) 1px,transparent 1px),linear-gradient(90deg,var(--line) 1px,transparent 1px);
  background-size:56px 56px;background-position:-1px -1px}
.wrap{max-width:62rem;margin:0 auto;padding:3rem max(4vw,1.25rem) 6rem}
.m{font-family:var(--mono);font-size:.8125rem}
.dim{color:var(--fg-3)}
.eyebrow{font-family:var(--mono);font-size:.6875rem;letter-spacing:.16em;text-transform:uppercase;color:var(--accent);margin:0 0 .75rem}
h1{font-size:clamp(1.6rem,3.6vw,2.3rem);line-height:1.12;letter-spacing:-.02em;margin:0 0 .5rem;font-weight:600}
h2{font-size:1.0625rem;font-weight:600;margin:2.75rem 0 .75rem;letter-spacing:-.01em}
.sub{color:var(--fg-2);margin:0 0 2rem}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:.75rem;padding:1.25rem 1.4rem;margin:1rem 0}
.verdict{border-left:2px solid var(--accent)}
.verdict p{margin:0;color:var(--fg)}
.kv{display:grid;grid-template-columns:repeat(auto-fit,minmax(11rem,1fr));gap:1px;background:var(--line);
  border:1px solid var(--line);border-radius:.75rem;overflow:hidden;margin:1rem 0}
.kv>div{background:var(--panel);padding:1rem 1.1rem}
.kv .k{font-family:var(--mono);font-size:.625rem;letter-spacing:.14em;text-transform:uppercase;color:var(--fg-3);margin:0 0 .4rem}
.kv .v{font-family:var(--mono);font-size:1.05rem;margin:0;word-break:break-all;color:var(--fg)}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:.75rem;background:var(--panel)}
table{border-collapse:collapse;width:100%;min-width:44rem}
th{text-align:left;font-family:var(--mono);font-size:.625rem;letter-spacing:.14em;text-transform:uppercase;
  color:var(--fg-3);font-weight:500;padding:.7rem .9rem;border-bottom:1px solid var(--line)}
td{padding:.55rem .9rem;border-bottom:1px solid var(--line)}
tr:last-child td{border-bottom:0}
tr.bad td{background:color-mix(in srgb,var(--bad) 9%,transparent)}
.num{text-align:right}
.tag{font-family:var(--mono);font-size:.6875rem;padding:.15rem .5rem;border-radius:999px;border:1px solid var(--line-2);white-space:nowrap}
.tag.observed{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 40%,transparent)}
.tag.simulated{color:var(--accent);border-color:color-mix(in srgb,var(--accent) 40%,transparent)}
.tag.ok{color:var(--ok);border-color:color-mix(in srgb,var(--ok) 40%,transparent)}
.tag.no{color:var(--bad);border-color:color-mix(in srgb,var(--bad) 40%,transparent)}
.viol{color:var(--bad)}
.bar{display:flex;height:8px;border-radius:999px;overflow:hidden;border:1px solid var(--line);margin:.65rem 0 .35rem}
.bar i{display:block;height:100%}
.bar .o{background:var(--ok)}
.bar .s{background:var(--accent)}
footer{margin-top:3.5rem;padding-top:1.25rem;border-top:1px solid var(--line);color:var(--fg-3);font-family:var(--mono);font-size:.75rem}
@media(max-width:30rem){.wrap{padding-top:2rem}}
</style></head>
<body><div class="wrap">
<p class="eyebrow">Parallax run receipt</p>
<h1>${esc(r.ontology.world.title)}</h1>
<p class="sub">Accepted by ${esc(r.ontology.acceptedBy)} · ${r.trajectory.length} steps · trace <span class="m">${esc(r.traceHash.slice(0, 16))}</span></p>

<div class="panel verdict"><p>${verdict}</p></div>

<div class="kv">
  <div><p class="k">Branch class</p><p class="v">${esc(r.branchClass)}</p></div>
  <div><p class="k">Policy declared</p><p class="v">${esc(r.certificate.declared)}</p></div>
  <div><p class="k">Policy demonstrated</p><p class="v">${esc(r.certificate.effective)}${r.certificate.demoted ? ' <span class="tag no">demoted</span>' : ""}</p></div>
  <div><p class="k">Violations</p><p class="v">${violations.length}</p></div>
</div>

<h2>How much of this was real</h2>
<div class="panel">
  <div class="bar"><i class="o" style="width:${observedPct}%"></i><i class="s" style="width:${100 - observedPct}%"></i></div>
  <p class="m dim">${origins.observed} observed · ${origins.simulated} simulated — a value derived from anything simulated is simulated, however much observed data went in beside it.</p>
</div>

<h2>Certification</h2>
<div class="panel"><p class="m">${esc(r.certificate.policy)} — ${esc(r.certificate.reason)}</p>
<p class="m dim" style="margin:.5rem 0 0">A class a policy declares about itself is not evidence. This one was measured.</p></div>

${r.scores.length ? `<h2>Objectives</h2><div class="scroll"><table><thead><tr><th>Objective</th><th class="num">Value</th><th>Constraint</th><th>Origin</th></tr></thead><tbody>${scoreRows}</tbody></table></div>` : ""}

<h2>Trajectory</h2>
<div class="scroll"><table><thead><tr><th>#</th><th>Actor</th><th>Action</th><th>Params</th><th>Origin</th><th>Violated</th></tr></thead><tbody>
${steps}
</tbody></table></div>

<footer>run ${esc(r.runId)} · ontology ${esc(r.ontology.proposalId.slice(0, 16))} · accepted ${esc(new Date(r.ontology.acceptedAt).toISOString())}<br>
Replay is a hash comparison, not a claim. Same inputs reproduce ${esc(r.traceHash.slice(0, 16))}.</footer>
</div></body></html>`;
}

function buildVerdict(r: RunReceipt, violations: number, observedPct: number): string {
  const parts: string[] = [];
  if (violations > 0) {
    const names = [...new Set(r.trajectory.flatMap((s) => s.violations.map((v) => v.invariant)))];
    parts.push(
      `This run broke ${violations === 1 ? "an invariant" : `${violations} invariants`} (${esc(names.join(", "))}). It is not a plan you can act on.`,
    );
  } else {
    parts.push("Every invariant held for the whole run.");
  }
  if (r.certificate.demoted) {
    parts.push(
      `The policy claimed ${esc(r.certificate.declared)} and demonstrated ${esc(r.certificate.effective)}, so the byte-identical replay claim has been withdrawn automatically.`,
    );
  }
  if (observedPct === 0) {
    parts.push("Nothing here was observed; the entire trajectory is simulated.");
  }
  if (r.baseline) {
    const d = violations - r.baseline.violations;
    parts.push(
      d === 0
        ? "It matches the recorded baseline on violations."
        : `Against what actually happened: ${d < 0 ? `${-d} fewer` : `${d} more`} violations.`,
    );
  }
  return parts.join(" ");
}
