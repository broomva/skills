// The security claim: an agent given only the vbash tool cannot read the host.
//
// Asserted THROUGH THE MCP SERVER -- the same path Claude Code uses -- not against
// the World class directly, so a containment regression in the server surface is
// caught too. Probes assert the read produced NOTHING, not merely that it lacked a
// canary literal: a probe that only rejects one string stays green while the whole
// of /etc/hosts leaks.
import { test } from "node:test";
import assert from "node:assert/strict";
import * as nfs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const SERVER = path.join(path.dirname(fileURLToPath(import.meta.url)), "..", "..", "scripts", "vbash-server.mjs");
const CANARY = "CANARY-a7f3e9-TOPSECRET";
const OPEN = new Set();

async function connect(world) {
  const c = new Client({ name: "contain", version: "1.0.0" });
  await c.connect(new StdioClientTransport({
    command: process.execPath, args: [SERVER],
    env: { ...process.env, JB_WORLD: world, HOST_CANARY: CANARY },   // also a leak vector
  }));
  OPEN.add(c);
  return c;
}
async function shut(c) { OPEN.delete(c); try { await c.close(); } catch { /* gone */ } }
const call = async (c, command) =>
  (await c.callTool({ name: "vbash", arguments: { command } })).content[0].text;

function fixture() {
  const d = nfs.mkdtempSync(path.join(os.tmpdir(), "contain-"));
  nfs.writeFileSync(path.join(d, "host-canary.txt"), CANARY + "\n");
  return d;
}
/** A contained read yields NO STDOUT. The server formats a result as
 *  `<stdout>\n[stderr]\n<stderr>\n[exit N]`, so checking only that an error appeared
 *  would pass a command that leaked a whole file AND then exited nonzero. */
function stdoutOf(out) {
  return out.split(/\n?\[stderr\]|\n?\[exit /)[0].trim();
}
function assertNoContent(out, label) {
  assert.ok(!out.includes("TOPSECRET"), `${label}: canary leaked`);
  const body = stdoutOf(out);
  assert.ok(body === "" || body === "(no output)",
    `${label}: produced stdout instead of failing -> ${JSON.stringify(body.slice(0, 140))}`);
}

test("no host path is reachable through the MCP server", { timeout: 30000 }, async () => {
  const d = fixture();
  const c = await connect(path.join(d, "w.json"));
  try {
    for (const [label, cmd] of [
      ["host canary",        `cat ${d}/host-canary.txt`],
      ["/etc/hosts",         "cat /etc/hosts"],
      ["/etc/passwd",        "cat /etc/passwd"],
      ["parent traversal",   "cat /work/../../../etc/hosts"],
      ["home directory",     `ls ${os.homedir()}`],
      ["resolved abs path",  `cat ${path.resolve(d)}/host-canary.txt`],
      ["proc environ",       "cat /proc/self/environ"],
    ]) assertNoContent(await call(c, cmd), label);

    // env and filesystem sweeps must return nothing at all
    for (const [label, cmd] of [
      ["env sweep",   "env | grep -i -E 'canary|key|token|secret|aws|anthropic' | head"],
      ["fs sweep",    "grep -rl TOPSECRET / 2>/dev/null | head"],
    ]) {
      const out = (await call(c, cmd)).trim();
      assert.ok(out === "" || out === "(no output)", `${label} returned: ${JSON.stringify(out.slice(0, 120))}`);
    }
  } finally { for (const x of [...OPEN]) await shut(x); }
});

test("POSITIVE CONTROL: the probe detects a canary planted inside the world", { timeout: 30000 }, async () => {
  const c = await connect(path.join(fixture(), "w.json"));
  try {
    await call(c, `echo '${CANARY}' > /work/planted.txt`);
    const out = await call(c, "cat /work/planted.txt");
    assert.ok(out.includes("TOPSECRET"), "probe cannot see content it should -- containment test is vacuous");
    // and the strict assertion must reject it, proving assertNoContent discriminates
    assert.throws(() => assertNoContent(out, "control"), /canary leaked/);
    // and content-plus-an-error must still be rejected: the earlier version of this
    // helper passed anything that merely looked like a failure.
    assert.throws(() => assertNoContent("root:x:0:0:root:/root:/bin/sh\n[exit 1]", "control2"),
      /produced stdout/);
  } finally { for (const x of [...OPEN]) await shut(x); }
});

test("writes inside the world never touch the host filesystem", { timeout: 30000 }, async () => {
  const d = fixture();
  const c = await connect(path.join(d, "w.json"));
  try {
    const before = nfs.readdirSync(d).sort();
    await call(c, "mkdir -p /work/deep/nested && echo x > /work/deep/nested/f.txt");
    await call(c, `echo escape > ${d}/should-not-appear.txt`);
    const after = nfs.readdirSync(d).sort().filter((f) => !f.endsWith(".json"));
    assert.deepEqual(after, before.filter((f) => !f.endsWith(".json")), "the world wrote to the host filesystem");
  } finally { for (const x of [...OPEN]) await shut(x); }
});
