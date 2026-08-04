/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          argv-array-test-runner-target (v1)
 * minted from: pyproject.toml#tool-tox-env-run-base
 * minted at:   2026-07-25T03:33:01.420Z
 * shape:
 * A build-tool environment or target that declares a `commands` list in ARGV-ARRAY form whose elements invoke a language test runner -- tox 4's TOML `commands = [["pytest", "-v", ...]]`, and any other config that spells the command as a quoted argument vector rather than a shell string. It complements the existing shell-string test-invocation shapes, which key on tokens like `pytest tests` or `pytest {posargs` and therefore never fire on a quoted argv element. Keyed on the invocation form (a `commands` declaration containing a quoted runner argv), never on the file it lives in, and it deliberately requires the `commands` declaration so that a dependency group merely LISTING "pytest" as a package does not match. Abstains -- hands the node back to the agent -- when the body suppresses its own exit status (`|| true`, `continue-on-error`, `exit 0`), regenerates its own expected output (`--update-snapshot`), or only collects without running (`--collect-only`).
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      the test runner process's exit code, produced by the language runtime executing the committed suite from a build-tool environment's argv command list
 *   actorCanWrite: false
 *   The target declares a `commands` list whose argv invokes a test runner directly (tox 4's TOML form `commands = [["pytest", "-v", ...]]`, and any config using the same argv-array shape). The build tool execs that argv and fails the environment on a non-zero status, so the signal is the interpreter's verdict on importing and running the committed test modules: a failing assertion, an import error or a crash cannot be argued into exiting zero. Documented limit, and it travels with this verdict: the EXECUTION is anchored, the ORACLE is not — implementation and assertions are typically authored by the same people in the same tree, so a green run proves the code does what these tests say, not that the tests say the right thing. This shape reads a target definition, not a pipeline: whether the environment is selected by a CI job is the agent's to establish separately.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["script","test_target","ci_step"];
const ALL_OF = ["commands"];
const ANY_OF = ["\"pytest\"","'pytest'","\"cargo\", \"test\"","\"go\", \"test\"","\"npm\", \"test\"","\"vitest\", \"run\""];
const NONE_OF = ["uses:","dependency-groups","optional-dependencies"];

/**
 * The shape, keyed on structure. Not on a repo, not on a path.
 *
 * `node.source` is deliberately NOT in the haystack. A file path says where a
 * check lives, never what produces its signal, and a path is attacker-adjacent
 * input: a repo that names a workflow `claude-review.yml` would otherwise have
 * every step in it — `pytest`, `cargo build` — match a probe about LLM review
 * gates. `mint-probe`'s `rejectRepoLiterals()` refuses path literals as tokens;
 * excluding `source` from the text being searched is the other half of that.
 */
function signature(node) {
  if (KINDS.length && !KINDS.includes(node.kind)) return false;
  const hay = [node.name, node.raw].join('\n').toLowerCase();
  if (!ALL_OF.every((t) => hay.includes(t))) return false;
  if (ANY_OF.length && !ANY_OF.some((t) => hay.includes(t))) return false;
  if (NONE_OF.some((t) => hay.includes(t))) return false;
  return true;
}

const ASSERT_ALL = [];
const ASSERT_ANY = ["\"pytest\"","'pytest'","\"cargo\", \"test\"","\"go\", \"test\"","\"npm\", \"test\"","\"vitest\", \"run\""];
const ASSERT_NONE = ["|| true","continue-on-error","exit 0","--update-snapshot","--snapshot-update","--collect-only"];

/**
 * The CONFIRMING stage — strictly narrower than `signature`, and reading
 * `node.raw` alone. `match` is a cheap structural filter; this is the check
 * that can fail, which is what makes the abstention below reachable. A node that
 * matches but does not confirm goes back to the agent.
 */
function confirms(node) {
  const raw = String(node.raw == null ? '' : node.raw).toLowerCase();
  if (!ASSERT_ALL.every((t) => raw.includes(t))) return false;
  if (ASSERT_ANY.length && !ASSERT_ANY.some((t) => raw.includes(t))) return false;
  if (ASSERT_NONE.some((t) => raw.includes(t))) return false;
  return true;
}

const probe = {
  id: "argv-array-test-runner-target",
  version: 1,
  mintedAt: "2026-07-25T03:33:01.420Z",
  mintedFrom: "pyproject.toml#tool-tox-env-run-base",
  description: "A build-tool environment or target that declares a `commands` list in ARGV-ARRAY form whose elements invoke a language test runner -- tox 4's TOML `commands = [[\"pytest\", \"-v\", ...]]`, and any other config that spells the command as a quoted argument vector rather than a shell string. It complements the existing shell-string test-invocation shapes, which key on tokens like `pytest tests` or `pytest {posargs` and therefore never fire on a quoted argv element. Keyed on the invocation form (a `commands` declaration containing a quoted runner argv), never on the file it lives in, and it deliberately requires the `commands` declaration so that a dependency group merely LISTING \"pytest\" as a package does not match. Abstains -- hands the node back to the agent -- when the body suppresses its own exit status (`|| true`, `continue-on-error`, `exit 0`), regenerates its own expected output (`--update-snapshot`), or only collects without running (`--collect-only`).",
  match(node) {
    return signature(node);
  },
  assess(node) {
    // Two-stage: `match` filtered on structure, this confirms on the literal
    // text. Abstention (`null`) is REACHABLE here — a node this probe matched
    // can still fail `confirms` and fall through to the agent. Abstention is
    // the ONLY way a probe says "I cannot tell"; it may never say 'unknown'.
    if (!signature(node)) return null;
    if (!confirms(node)) return null;
    return {
      class: "anchored",
      writeBoundary: {"producer":"the test runner process's exit code, produced by the language runtime executing the committed suite from a build-tool environment's argv command list","actorCanWrite":false,"argument":"The target declares a `commands` list whose argv invokes a test runner directly (tox 4's TOML form `commands = [[\"pytest\", \"-v\", ...]]`, and any config using the same argv-array shape). The build tool execs that argv and fails the environment on a non-zero status, so the signal is the interpreter's verdict on importing and running the committed test modules: a failing assertion, an import error or a crash cannot be argued into exiting zero. Documented limit, and it travels with this verdict: the EXECUTION is anchored, the ORACLE is not — implementation and assertions are typically authored by the same people in the same tree, so a green run proves the code does what these tests say, not that the tests say the right thing. This shape reads a target definition, not a pipeline: whether the environment is selected by a CI job is the agent's to establish separately."},
      evidence: ["a build-tool environment table whose `commands` argv list begins with a test runner"],
      confidence: 0.85,
    };
  },
};

export default probe;
export { probe };
