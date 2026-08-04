/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          build-tool-target-test-invocation (v1)
 * minted from: Makefile#ci
 * minted at:   2026-07-25T03:13:00.671Z
 * shape:
 * A build-tool target (Makefile recipe, tox envlist commands, task/package script — node kind `script` or `test_target`) whose body directly invokes a language test runner: `python -m pytest`, `pytest <path>`, tox's `commands = pytest {posargs...}`, `cargo test`, `go test ./...`, `dotnet test`, `mvn/gradle test`, `npm test`, `vitest run`. It complements the existing pipeline-step shape, which requires a workflow `run:` key and therefore never fires on a Makefile recipe or a tox.ini envlist. Keyed on the INVOCATION form, never on the file it lives in, so a fixture module that merely imports pytest (`import pytest`, `@pytest.fixture`) does not match. Abstains — hands the node back to the agent — when the recipe suppresses its own exit status (`|| true`, `continue-on-error`), regenerates its own expected output (`--update-snapshot`), or is installing the runner rather than running it.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      the test runner process's exit code — the language runtime executing the committed suite when the build-tool target is invoked
 *   actorCanWrite: false
 *   The target's recipe body is a direct test-runner invocation (python -m pytest, pytest <path>, a tox `commands = pytest {posargs}` line, cargo/go/dotnet/mvn/gradle test, npm test, vitest run), so the target's exit status IS the runtime's verdict on running the committed test modules against the built artefact: a failed assertion, an uncaught exception, an import error or a crash cannot be persuaded to report green without changing the code or the tests. Two limits travel with this verdict and must not be dropped. (1) The EXECUTION is anchored, the ORACLE is not — implementation and assertions are typically authored by the same people in the same repo, so a green run proves the code does what these tests say, not that the tests say the right thing. (2) This shape reads a build-tool target, not a pipeline: whether this particular target blocks a merge depends on some workflow actually invoking it, which the agent must establish separately — a repo commonly has several test targets of which CI calls only one.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["script","test_target"];
const ALL_OF = [];
const ANY_OF = ["python -m pytest","pytest tests","pytest {posargs","-m pytest","cargo test","go test ./","dotnet test","mvn test","gradle test","npm test","vitest run"];
const NONE_OF = ["import pytest","uses:","pip install"];

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
const ASSERT_ANY = ["python -m pytest","pytest tests","pytest {posargs","-m pytest","cargo test","go test ./","dotnet test","mvn test","gradle test","npm test","vitest run"];
const ASSERT_NONE = ["|| true","continue-on-error","--update-snapshot","--snapshot-update","exit 0","|| echo"];

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
  id: "build-tool-target-test-invocation",
  version: 1,
  mintedAt: "2026-07-25T03:13:00.671Z",
  mintedFrom: "Makefile#ci",
  description: "A build-tool target (Makefile recipe, tox envlist commands, task/package script — node kind `script` or `test_target`) whose body directly invokes a language test runner: `python -m pytest`, `pytest <path>`, tox's `commands = pytest {posargs...}`, `cargo test`, `go test ./...`, `dotnet test`, `mvn/gradle test`, `npm test`, `vitest run`. It complements the existing pipeline-step shape, which requires a workflow `run:` key and therefore never fires on a Makefile recipe or a tox.ini envlist. Keyed on the INVOCATION form, never on the file it lives in, so a fixture module that merely imports pytest (`import pytest`, `@pytest.fixture`) does not match. Abstains — hands the node back to the agent — when the recipe suppresses its own exit status (`|| true`, `continue-on-error`), regenerates its own expected output (`--update-snapshot`), or is installing the runner rather than running it.",
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
      writeBoundary: {"producer":"the test runner process's exit code — the language runtime executing the committed suite when the build-tool target is invoked","actorCanWrite":false,"argument":"The target's recipe body is a direct test-runner invocation (python -m pytest, pytest <path>, a tox `commands = pytest {posargs}` line, cargo/go/dotnet/mvn/gradle test, npm test, vitest run), so the target's exit status IS the runtime's verdict on running the committed test modules against the built artefact: a failed assertion, an uncaught exception, an import error or a crash cannot be persuaded to report green without changing the code or the tests. Two limits travel with this verdict and must not be dropped. (1) The EXECUTION is anchored, the ORACLE is not — implementation and assertions are typically authored by the same people in the same repo, so a green run proves the code does what these tests say, not that the tests say the right thing. (2) This shape reads a build-tool target, not a pipeline: whether this particular target blocks a merge depends on some workflow actually invoking it, which the agent must establish separately — a repo commonly has several test targets of which CI calls only one."},
      evidence: ["the target's recipe body is a direct language test-runner invocation, with no install/provisioning command and no failure-suppressing construct"],
      confidence: 0.8,
    };
  },
};

export default probe;
export { probe };
