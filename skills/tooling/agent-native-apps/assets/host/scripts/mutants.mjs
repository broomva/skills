// Mutation check: each guard below is removed in a throwaway copy of src/ and
// test/, and the unit tests must then FAIL. A mutant that survives means a
// guard no test enforces. Exit 0 only if every mutant is killed.
//
// Usage: node scripts/mutants.mjs

import { spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const MUTANTS = [
  [
    "served set: node_modules is served and hashed",
    "src/manifest.js",
    'name.toLowerCase() !== "node_modules"',
    "true",
  ],
  [
    "served set: uppercase NODE_MODULES bypasses exclusion on case-insensitive FS",
    "src/manifest.js",
    'name.toLowerCase() !== "node_modules"',
    'name !== "node_modules"',
  ],
  ["served set: dot-folders are served and hashed", "src/manifest.js", '!name.startsWith(".") && ', ""],
  ["symlinks are accepted in an app folder", "src/manifest.js", "if (entry.isSymbolicLink())", "if (false)"],
  [
    "async agent launch ignores version change during setup",
    "src/capabilities.js",
    "if (checkVersion() || !getVersion())",
    "if (false)",
  ],
  [
    "served files allow in-folder symlinks",
    "src/manifest.js",
    "if (fs.lstatSync(walk).isSymbolicLink()) return null;",
    "if (false) return null;",
  ],
  [
    "file bytes go into the version hash unframed",
    "src/manifest.js",
    'frame(tree, createHash("sha256").update(fs.readFileSync(file)).digest());',
    "tree.update(fs.readFileSync(file));",
  ],
  [
    "a t3 provider may come without a model",
    "src/manifest.js",
    'harness === "t3" && agent.provider !== undefined && agent.model === undefined',
    "false",
  ],
  [
    "a model id may start with a dash",
    "src/manifest.js",
    "/^[A-Za-z0-9][\\w.:/-]{0,80}$/",
    "/^[\\w.:/-]{1,80}$/",
  ],
  ["the ceiling fails open on NaN", "src/capabilities.js", "!(tier <= ctx.maxTier)", "tier > ctx.maxTier"],
  [
    "any --max-tier value is accepted",
    "src/capabilities.js",
    "!Number.isInteger(n) || n < 1 || n > 3",
    "false",
  ],
  ["a t3 run needs only `agent`", "src/capabilities.js", ' || args[0]?.harness === "t3"', ""],
  ["an agent run is tier 2", "src/capabilities.js", "agent: TIERS.FULL,", "agent: TIERS.PERMISSION,"],
  [
    "a grant counts without a declaration",
    "src/capabilities.js",
    "if (!ctx.declared.has(permission))",
    "if (false)",
  ],
  ["a call passes without a grant", "src/capabilities.js", "if (!ctx.granted.has(permission))", "if (false)"],
  [
    "prompt grant skips post-consent disk re-hash",
    "src/capabilities.js",
    "const changed = checkVersion();",
    "const changed = false;",
  ],
  [
    "async agent launch ignores app close during setup",
    "src/capabilities.js",
    'if (isClosed()) throw new CapabilityError("ECLOSED", "The app closed.");',
    "if (false) throw new CapabilityError('ECLOSED', 'The app closed.');",
  ],
  [
    "claude loads project settings",
    "src/harness.js",
    '"--setting-sources",\n        "",',
    '"--setting-sources",\n        "project",',
  ],
  ["claude keeps the user's MCP servers", "src/harness.js", "'{\"mcpServers\":{}}',", '"{}",'],
  [
    "the child gets the host's whole environment",
    "src/harness.js",
    'for (const key of ENV_ALLOW) if (typeof env[key] === "string") out[key] = env[key];',
    "Object.assign(out, env);",
  ],
  [
    "harness names resolve through the prototype",
    "src/harness.js",
    "if (!Object.hasOwn(HARNESSES, harness))",
    "if (!HARNESSES[harness])",
  ],
  [
    "the prompt is not written to stdin",
    "src/harness.js",
    "child.stdin?.end?.(prompt);",
    "child.stdin?.end?.();",
  ],
  [
    "done is emitted while the process still runs",
    "src/harness.js",
    "reported ??= event;\n      return;",
    "reported ??= event;\n      onEvent(event);\n      return;",
  ],
  ["the run is not in its own process group", "src/harness.js", "env, detached: true }", "env }"],
  [
    "cancel kills only the direct child, not its process group",
    "src/harness.js",
    "process.kill(-child.pid, sig);",
    "child.kill(sig);",
  ],
  [
    "direct-child close disarms SIGKILL escalation for surviving descendants",
    "src/harness.js",
    "if (!cancelled) stopEscalation();\n      else await cleanupDone;",
    "stopEscalation();",
  ],
  [
    "before-quit exits without preventing shutdown during active run cleanup",
    "src/harness.js",
    "event.preventDefault();",
    "",
  ],
  [
    "writeShimBundle deletes unowned existing bundle",
    "src/bundle.js",
    "if (!allowReplace && fs.existsSync(bundlePath))",
    "if (false)",
  ],
  [
    "forwarded command silently loosens requested --max-tier",
    "src/args.js",
    "if (requested?.maxTier !== undefined && requested.maxTier < running.maxTier)",
    "if (false)",
  ],
  [
    "selftest hardcodes claude instead of selecting an installed harness",
    "src/selftest.js",
    '(["claude", "codex", "t3"].find((h) => availMap[h]) ?? null)',
    '"claude"',
  ],
  [
    "lastJsonObject infinite-loops at index 0 on malformed leading brace",
    "src/harness.js",
    "if (start === 0) break;",
    "if (false) break;",
  ],
  [
    "a top-level codex error ends the run",
    "src/harness.js",
    'return [{ type: "error", message: String(obj.message ?? "codex error") }];',
    'return [{ type: "done", ok: false, summary: "error" }];',
  ],
  [
    "t3 continues no thread",
    "src/harness.js",
    'if (threadId) return ["thread", "send", threadId, "-", "--wait", "--json"];',
    "",
  ],
  [
    "a corrupt registry starts empty",
    "src/registry.js",
    "throw new RegistryError(`${this.file} is not valid JSON",
    "console.error(`${this.file} is not valid JSON",
  ],
  [
    "a null version can hold grants",
    "src/registry.js",
    "version && grant && grant.version === version",
    "grant && grant.version === version",
  ],
  ["the registry file is world-readable", "src/registry.js", "{ mode: 0o600 }", "{ mode: 0o644 }"],
  [
    "install paths are not resolved against the caller's cwd",
    "src/args.js",
    'path.resolve(cwd, rest[0] ?? ".")',
    'rest[0] ?? "."',
  ],
  ["unknown flags are ignored", "src/args.js", "throw new ArgsError(`Unknown flag --${name}.`);", ""],
];

function copyTree(to) {
  for (const dir of ["src", "test"]) fs.cpSync(path.join(ROOT, dir), path.join(to, dir), { recursive: true });
}

function runTests(cwd) {
  const files = fs
    .readdirSync(path.join(cwd, "test"))
    .filter((f) => f.endsWith(".test.js"))
    .map((f) => path.join("test", f));
  const res = spawnSync(process.execPath, ["--test", ...files], { cwd, encoding: "utf8", timeout: 15000 });
  return res.status ?? 1;
}

const base = fs.mkdtempSync(path.join(os.tmpdir(), "ana-mutants-"));
let survived = 0;
let broken = 0;
try {
  const clean = path.join(base, "clean");
  copyTree(clean);
  if (runTests(clean) !== 0) {
    console.error("The unmutated tests fail; fix them first.");
    process.exit(2);
  }
  for (const [name, file, find, replace] of MUTANTS) {
    const dir = path.join(base, "m");
    fs.rmSync(dir, { recursive: true, force: true });
    copyTree(dir);
    const target = path.join(dir, file);
    const source = fs.readFileSync(target, "utf8");
    if (source.split(find).length !== 2) {
      console.log(
        `BROKEN   ${name}: the text to mutate appears ${source.split(find).length - 1} times in ${file}`,
      );
      broken++;
      continue;
    }
    fs.writeFileSync(target, source.replace(find, replace));
    const killed = runTests(dir) !== 0;
    console.log(`${killed ? "killed  " : "SURVIVED"} ${name}`);
    if (!killed) survived++;
  }
} finally {
  fs.rmSync(base, { recursive: true, force: true });
}
console.log(`\n${MUTANTS.length - survived - broken} killed, ${survived} survived, ${broken} broken`);
process.exit(survived === 0 && broken === 0 ? 0 : 1);
