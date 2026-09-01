import { test } from "node:test";
import assert from "node:assert/strict";
import { Bash, InMemoryFs } from "just-bash";
import { PersistentShell } from "../../scripts/persistent-shell.mjs";

test("BASELINE: plain Bash loses env and cwd between exec() calls", async () => {
  const b = new Bash();
  await b.exec("export TOKEN=abc123");
  assert.equal((await b.exec('echo "[$TOKEN]"')).stdout.trim(), "[]",
    "if this ever passes, just-bash changed and PersistentShell may be unnecessary");
  await b.exec("cd /tmp");
  assert.equal((await b.exec("pwd")).stdout.trim(), "/home/user");
});

test("env survives across exec calls", async () => {
  const sh = new PersistentShell({ fs: new InMemoryFs() });
  await sh.exec("export TOKEN=abc123");
  assert.equal((await sh.exec('echo "[$TOKEN]"')).stdout.trim(), "[abc123]");
});

test("cwd survives and compounds", async () => {
  const sh = new PersistentShell({ fs: new InMemoryFs() });
  await sh.exec("mkdir -p /work/deep && cd /work/deep");
  assert.equal((await sh.exec("pwd")).stdout.trim(), "/work/deep");
  assert.equal((await sh.exec("cd .. && pwd")).stdout.trim(), "/work");
});

test("exit code is preserved and stdout is not polluted by state capture", async () => {
  const sh = new PersistentShell({ fs: new InMemoryFs() });
  const r = await sh.exec("echo out; exit 42");
  assert.equal(r.exitCode, 42);
  assert.equal(r.stdout, "out\n");
});

test("values containing spaces and quotes round-trip", async () => {
  const sh = new PersistentShell({ fs: new InMemoryFs() });
  await sh.exec(`export A=1; export B='two words'`);
  assert.equal((await sh.exec('echo "$A|$B"')).stdout.trim(), "1|two words");
});

test("rc-registered functions replay (declare -f cannot recover them)", async () => {
  const sh = new PersistentShell({ fs: new InMemoryFs() });
  sh.addRc('greet() { echo "hi $1"; }');
  assert.equal((await sh.exec("greet world")).stdout.trim(), "hi world");
});

test("declare -f returns a STUB, which is why addRc exists", async () => {
  const b = new Bash();
  const out = (await b.exec('f(){ echo secret_body; }\ndeclare -f')).stdout;
  assert.ok(!out.includes("secret_body"),
    "if the body is emitted, functions could be captured from the guest and addRc could be dropped");
});

test("state must be restored PAIRED with its filesystem", async () => {
  const fs = new InMemoryFs();
  const sh = new PersistentShell({ fs });
  await sh.exec("mkdir -p /work/proj && cd /work/proj && export T=tok");
  const saved = JSON.parse(JSON.stringify(sh.getState()));
  // unpaired: same shell state, a filesystem that never had /work/proj
  const orphan = new PersistentShell({ fs: new InMemoryFs() }).loadState(saved);
  assert.notEqual((await orphan.exec("pwd")).stdout.trim(), "/work/proj");
  // paired: same filesystem
  const paired = new PersistentShell({ fs }).loadState(saved);
  assert.equal((await paired.exec('echo "$T@$(pwd)"')).stdout.trim(), "tok@/work/proj");
});

test("state file lives outside the snapshot prefix", async () => {
  const { snapshot } = await import("../../scripts/fs-snapshot.mjs");
  const fs = new InMemoryFs();
  const sh = new PersistentShell({ fs });
  await sh.exec("mkdir -p /work && echo x > /work/a.txt && cd /work");
  const snap = await snapshot(fs, "/work");
  assert.ok(!JSON.stringify(snap).includes("forkable-shell-state"),
    "shell bookkeeping must not leak into the captured world");
});

// --- regressions from the P20 cross-model review -----------------------------

test("REGRESSION: env values containing newlines and tabs survive replay", async () => {
  // bash emits these as ANSI-C quoted $'...'; a double-quote-only parser drops them.
  const sh = new PersistentShell({ fs: new InMemoryFs() });
  await sh.exec(`export NL=$'a\\nb'; export TAB=$'x\\ty'; export PLAIN=ok`);
  const r = await sh.exec('printf "[%s][%s][%s]" "$NL" "$TAB" "$PLAIN"');
  assert.equal(r.stdout, "[a\nb][x\ty][ok]");
});

test("REGRESSION: a malformed env NAME cannot smuggle commands into the preamble", async () => {
  const sh = new PersistentShell({ fs: new InMemoryFs() });
  sh.env = { "SAFE=x; mkdir -p /work; echo INJECTED > /work/pwned; export T": "1", GOOD: "kept" };
  await sh.exec("true");
  assert.match((await sh.exec("cat /work/pwned 2>/dev/null || echo none")).stdout, /none/,
    "a crafted env name executed during replay");
  assert.equal((await sh.exec("echo $GOOD")).stdout.trim(), "kept", "valid names must still replay");
});

test("REGRESSION: a command that exits early reports stateCaptured=false", async () => {
  // just-bash implements no `trap`, so `exit N` and `set -e` failures abandon the
  // script before the state epilogue. That cannot be prevented -- but it MUST be
  // reported, or the caller cannot tell "nothing changed" from "we never looked".
  const sh = new PersistentShell({ fs: new InMemoryFs() });
  await sh.exec("mkdir -p /work/sub");
  const ok = await sh.exec("export K=good; cd /work");
  assert.equal(ok.stateCaptured, true);

  const bailed = await sh.exec("export K=lost; cd /work/sub; exit 7");
  assert.equal(bailed.exitCode, 7);
  assert.equal(bailed.stateCaptured, false, "early exit must be reported, not silently ignored");

  const errexit = await sh.exec("export K=lost2; cd /work/sub; set -e; false; echo unreached");
  assert.equal(errexit.stateCaptured, false, "set -e failure must be reported");

  // prior good state is retained rather than corrupted
  assert.equal((await sh.exec('echo "$K@$(pwd)"')).stdout.trim(), "good@/work");
});

test("REGRESSION: ANSI-C octal escapes decode to the right byte", async () => {
  const sh = new PersistentShell({ fs: new InMemoryFs() });
  await sh.exec(`export OCT=$'a\\001b'`);
  const out = (await sh.exec('printf "%s" "$OCT" | od -An -c | head -1')).stdout.trim();
  assert.match(out, /a\s+001\s+b/, `octal escape mis-decoded: ${JSON.stringify(out)}`);
});
