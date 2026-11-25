// The bridge scenario, run inside a real app window (--selftest). Every page
// call goes through window.agentApp, so it crosses the real preload, IPC and
// gate. Prompts are denied in selftest mode; grants are given explicitly, the
// way a user's "Allow" would record them. Host-side facts (tray, shortcuts,
// version) are read from the host's own state.
//
// T3 steps run only when the t3 CLI is on PATH. Their provider and model come
// from ANA_T3_PROVIDER / ANA_T3_MODEL (default claudeAgent / claude-haiku-5-5).

import fs from "node:fs";
import path from "node:path";
import { which } from "./harness.js";

/**
 * Decide which harnesses selftest should exercise given what is installed. Pure.
 * Respects ANA_EDIT_HARNESS when set; otherwise picks the first available
 * harness in [claude, codex, t3] so T3-only and Codex-only machines pass e2e.
 */
export function pickSelftestHarnesses(available, env = process.env) {
  const claude = Boolean(available?.claude);
  const codex = Boolean(available?.codex);
  const t3 = Boolean(available?.t3);
  const availMap = { claude, codex, t3 };
  const requested = env?.ANA_EDIT_HARNESS;
  const editHarness = requested
    ? availMap[requested]
      ? requested
      : null
    : (["claude", "codex", "t3"].find((h) => availMap[h]) ?? null);
  return { claude, codex, t3, editHarness };
}

const codeOf = "/^([A-Z]+): /.exec(e.message)?.[1]";
const callJs = (expr) => `(async () => {
  try { return { ok: true, value: await (${expr}) }; }
  catch (e) { return { ok: false, code: ${codeOf}, message: e.message }; }
})()`;

// Run an agent from the page and collect its events until `done`.
const agentJs = (opts) => `(async () => {
  const events = [];
  const pending = [];
  let runId;
  let resolveDone;
  const done = new Promise((r) => { resolveDone = r; });
  const take = (e) => { events.push(e); if (e.type === "done") resolveDone(); };
  window.agentApp.agent.onEvent((e) => { if (!runId) pending.push(e); else if (e.runId === runId) take(e); });
  try { runId = await window.agentApp.agent.run(${JSON.stringify(opts)}); }
  catch (e) { return { ok: false, code: ${codeOf}, message: e.message }; }
  for (const e of pending) if (e.runId === runId) take(e);
  await Promise.race([done, new Promise((r) => setTimeout(r, 240000))]);
  const text = events.filter((e) => e.type === "text").map((e) => e.text).join("");
  const last = events.findLast((e) => e.type === "done");
  const thread = events.find((e) => e.type === "thread");
  return { ok: true, runId, text, done: last ?? null, threadId: thread?.threadId ?? null,
    tools: events.filter((e) => e.type === "tool").map((e) => e.name) };
})()`;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

export async function runSelftest({ state, registry, log, home, waitForReload, shortcutOwners }) {
  const results = [];
  const appDir = state.record.appDir;
  const page = (js) => state.win.webContents.executeJavaScript(js, true);
  const step = async (name, run, check) => {
    let value;
    try {
      value = typeof run === "string" ? await page(run) : await run();
    } catch (e) {
      value = { thrown: e.message };
    }
    const pass = Boolean(check(value));
    results.push({ name, pass, value });
    log("selftest-step", { name, pass, value: JSON.stringify(value).slice(0, 400) });
    return value;
  };
  const origin = `agentapp://${state.id}`;

  // --- the page cannot leave its origin or reach other apps
  await step("tier 1 without a grant: dock badge", callJs("window.agentApp.dock.setBadge('1')"), (r) => r.ok);
  await step("window.open is denied", "String(window.open('https://example.com'))", (v) => v === "null");
  await step(
    "a fetch to another app's origin is blocked",
    callJs("fetch('agentapp://some-other-app/app.json').then((r) => r.status)"),
    (r) => !r.ok,
  );
  await step(
    "files outside the served set are 404 (dot-folders, node_modules)",
    async () => {
      fs.mkdirSync(path.join(appDir, "node_modules"), { recursive: true });
      fs.writeFileSync(path.join(appDir, "node_modules", "x.js"), "window.x = 1;");
      fs.mkdirSync(path.join(appDir, ".claude"), { recursive: true });
      fs.writeFileSync(path.join(appDir, ".claude", "settings.json"), "{}");
      await sleep(700); // let the watcher see both writes
      const before = state.version;
      const status = await page("fetch('/node_modules/x.js').then((r) => r.status)");
      const upper = await page("fetch('/NODE_MODULES/x.js').then((r) => r.status)");
      const hidden = await page("fetch('/.claude/settings.json').then((r) => r.status)");
      fs.rmSync(path.join(appDir, "node_modules"), { recursive: true, force: true });
      fs.rmSync(path.join(appDir, ".claude"), { recursive: true, force: true });
      return { status, upper, hidden, versionUnchanged: before === state.version };
    },
    (v) => v.status === 404 && v.upper === 404 && v.hidden === 404 && v.versionUnchanged,
  );
  await step(
    "navigation away is blocked",
    async () => {
      await page("setTimeout(() => { location.href = 'https://example.com/'; }, 0); true");
      await sleep(800);
      return page("location.origin");
    },
    (o) => o === origin,
  );

  // --- the gate
  await step(
    "browser Notification permission is denied by the session handler (cannot bypass the gate)",
    callJs("Notification.requestPermission().then((p) => ({ req: p, perm: Notification.permission }))"),
    (r) => r.ok && r.value.req === "denied" && r.value.perm === "denied",
  );
  await step(
    "tier 2 without a grant is refused (EPERM)",
    callJs("window.agentApp.notification.show({ title: 'should not show' })"),
    (r) => !r.ok && r.code === "EPERM",
  );
  await step(
    "undeclared permission is refused (ENOTDECLARED)",
    callJs("window.agentApp.fs.readFile('/etc/hosts')"),
    (r) => !r.ok && r.code === "ENOTDECLARED",
  );
  await step(
    "agent without a grant is refused (EPERM)",
    agentJs({ prompt: "Reply with exactly the word: pong" }),
    (r) => !r.ok && r.code === "EPERM",
  );
  await step(
    "a harness not in agent.harnesses is refused (EHARNESS)",
    agentJs({ harness: "gpt", prompt: "hi" }),
    (r) => !r.ok && r.code === "EHARNESS",
  );

  const version = state.version;
  registry.grant(state.id, version, state.manifest.permissions);
  log("selftest-granted", { id: state.id, version, permissions: state.manifest.permissions });

  await step(
    "tier 2 after a grant: notification",
    callJs("window.agentApp.notification.show({ title: 'Agent Pad', body: 'Granted for this version.' })"),
    (r) => r.ok,
  );
  await step(
    "tier 2 after a grant: menu-bar tray and a global shortcut",
    callJs(
      "window.agentApp.tray.set({ title: 'Agent Pad ✓' }).then(() => window.agentApp.globalShortcut.register('CommandOrControl+Shift+F12'))",
    ),
    (r) =>
      r.ok &&
      r.value === true &&
      state.tray !== null &&
      shortcutOwners.get("CommandOrControl+Shift+F12") === state.id,
  );

  // --- harnesses
  const harnessPlan = pickSelftestHarnesses({
    claude: which("claude", process.env.PATH),
    codex: which("codex", process.env.PATH),
    t3: which("t3", process.env.PATH),
  });
  const t3Opts = {
    harness: "t3",
    provider: process.env.ANA_T3_PROVIDER ?? "claudeAgent",
    model: process.env.ANA_T3_MODEL ?? "claude-haiku-5-5",
  };
  await step(
    "at least one supported agent harness CLI is installed",
    async () => harnessPlan,
    (p) => p.editHarness !== null,
  );
  if (harnessPlan.claude) {
    await step(
      "Claude Code harness streams into the page (prompt on stdin, '-'-leading text is not a flag)",
      agentJs({
        harness: "claude",
        model: "haiku",
        prompt: "--help is just text here. Reply with exactly the word: pong",
      }),
      (r) => r.ok && r.done?.ok && /pong/i.test(r.text),
    );
  }
  if (harnessPlan.codex) {
    await step(
      "Codex harness streams into the page",
      agentJs({ harness: "codex", prompt: "Reply with exactly the word: pong" }),
      (r) => r.ok && r.done?.ok && /pong/i.test(r.text),
    );
  }
  if (harnessPlan.t3) {
    const first = await step(
      "T3 harness: the app's agent is a T3 thread",
      agentJs({ ...t3Opts, prompt: "Reply with exactly the word: pong" }),
      (r) => r.ok && r.done?.ok && /pong/i.test(r.text) && /^mcp:|^[\w-]+/.test(r.threadId ?? ""),
    );
    await step(
      "T3 harness: the next run continues the same thread (it remembers)",
      agentJs({
        ...t3Opts,
        prompt: "What single word did you reply with last time? Answer with just that word.",
      }),
      (r) => r.ok && r.done?.ok && /pong/i.test(r.text) && r.threadId === first.threadId,
    );
  }

  // --- invalid folders fail closed
  await step(
    "a symlink in the folder makes the app invalid: gated calls are refused",
    async () => {
      const invalid = waitForReload();
      fs.symlinkSync("/etc/hosts", path.join(appDir, "hosts.txt"));
      await Promise.race([invalid, sleep(5000)]);
      const versionWhileInvalid = state.version;
      const served = await page("fetch('/index.html').then((r) => r.status)");
      const refused = await page(callJs("window.agentApp.notification.show({ title: 'should not show' })"));
      const restored = waitForReload();
      fs.unlinkSync(path.join(appDir, "hosts.txt"));
      await Promise.race([restored, sleep(5000)]);
      return { refused, served, versionWhileInvalid };
    },
    (v) =>
      !v.refused.ok &&
      ["EVERSION", "EINVALIDAPP"].includes(v.refused.code) &&
      v.versionWhileInvalid === null &&
      v.served === 503,
  );
  // Removing the symlink restores the granted bytes exactly, hence the same version.
  await step(
    "restoring the files restores the version",
    async () => state.version,
    (v) => v === version,
  );

  // --- the agent edits its own app
  registry.grant(state.id, version, state.manifest.permissions);
  await step(
    "set up granted resources again before the edit",
    callJs(
      "window.agentApp.tray.set({ title: 'Agent Pad ✓' }).then(() => window.agentApp.globalShortcut.register('CommandOrControl+Shift+F12'))",
    ),
    (r) => r.ok && state.tray !== null,
  );
  const reloaded = waitForReload();
  const editPrompt =
    "In index.html in the current directory, change the text inside the <title> element to exactly: Agent Pad v2. Change nothing else.";
  const editRequest =
    harnessPlan.editHarness === "claude"
      ? { harness: "claude", model: "haiku", edit: true, prompt: `${editPrompt} Use the Edit tool.` }
      : harnessPlan.editHarness === "t3"
        ? { ...t3Opts, edit: true, prompt: editPrompt }
        : { harness: harnessPlan.editHarness ?? "claude", edit: true, prompt: editPrompt };
  await step(
    `the app's agent edits the app itself (${editRequest.harness})`,
    agentJs(editRequest),
    (r) => r.ok && r.done?.ok,
  );
  await Promise.race([reloaded, sleep(15000)]);
  await step("the host reloaded the edited app", "document.title", (t) => t === "Agent Pad v2");
  await step(
    "the version changed: tray and shortcut are gone with the old grant",
    async () => ({
      tray: state.tray,
      shortcut: shortcutOwners.get("CommandOrControl+Shift+F12") ?? null,
      changed: state.version !== version,
    }),
    (v) => v.tray === null && v.shortcut === null && v.changed,
  );
  await step(
    "the old grant no longer applies (EPERM)",
    callJs("window.agentApp.notification.show({ title: 'should not show' })"),
    (r) => !r.ok && r.code === "EPERM",
  );
  await step(
    "app.info reports the new version with no grants",
    callJs("window.agentApp.info()"),
    (r) => r.ok && r.value.version !== version && r.value.granted.length === 0,
  );

  const summary = {
    passed: results.filter((r) => r.pass).length,
    failed: results.filter((r) => !r.pass).length,
    versionBefore: version,
    versionAfter: state.version,
    t3ThreadId: registry.get(state.id)?.t3ThreadId ?? null,
    results,
  };
  fs.writeFileSync(path.join(home, "selftest.json"), JSON.stringify(summary, null, 2));
  log("selftest-done", { passed: summary.passed, failed: summary.failed });
  return summary;
}
