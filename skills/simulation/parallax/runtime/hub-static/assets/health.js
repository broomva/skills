// Fill the panel from the running instance rather than from a build constant.
// A page that states its own commit from a literal is a page that lies after
// the next deploy.
const el = document.getElementById("live");
try {
  const r = await fetch("health", { headers: { accept: "application/json" } });
  const h = await r.json();
  el.innerHTML =
    `commit <b>${String(h.commit ?? "unknown").slice(0, 12)}</b> · ` +
    `version <b>${h.version ?? "?"}</b> · up <b>${h.uptimeSeconds ?? "?"}s</b>`;
} catch {
  el.textContent = "/health did not answer — this instance may still be waking up.";
}
