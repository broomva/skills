/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          direct-test-runner-invocation (v1)
 * minted from: .github/workflows/ubuntu-tests.yml#52-run-tests
 * minted at:   2026-07-25T02:35:41.017Z
 * shape:
 * A pipeline step whose run command directly invokes a language test runner (pytest, go test, cargo test, dotnet test, mvn/gradle test, rspec, phpunit, vitest run, jest). Keyed on the command the step executes, never on the workflow file it lives in. Excludes steps that are installing the runner rather than running it (`pip install pytest`) and bare `uses:` action steps. Abstains — hands the node back to the agent — whenever the step suppresses its own failure (`|| true`, `continue-on-error`) or regenerates its own expected output (`--update-snapshot`), because in those cases the exit code either cannot vary or the oracle was authored by the thing under test.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      the test runner process's exit code, produced by the language runtime executing the suite in the pipeline
 *   actorCanWrite: false
 *   The step invokes a language test runner directly, so the step's exit status IS the runtime's verdict on executing the committed test modules against the built artefact. A failing assertion, an uncaught exception, an import error or a crash cannot be persuaded to report green without changing the code or the tests. Documented limit, and it matters: the EXECUTION is anchored, the ORACLE is not — implementation and assertions are typically authored by the same people in the same repo, so a green run proves the code does what these tests say, not that the tests say the right thing. Whether the step blocks a merge additionally depends on the workflow's triggers, which this shape does not read.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = ["run"];
const ANY_OF = ["pytest","go test","cargo test","dotnet test","mvn test","gradle test","rspec","phpunit","vitest run","jest"];
const NONE_OF = ["install","uses:"];

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
const ASSERT_ANY = ["pytest","go test","cargo test","dotnet test","mvn test","gradle test","rspec","phpunit","vitest run","jest"];
const ASSERT_NONE = ["|| true","continue-on-error","--update-snapshot","--snapshot-update","-u --","exit 0"];

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
  id: "direct-test-runner-invocation",
  version: 1,
  mintedAt: "2026-07-25T02:35:41.017Z",
  mintedFrom: ".github/workflows/ubuntu-tests.yml#52-run-tests",
  description: "A pipeline step whose run command directly invokes a language test runner (pytest, go test, cargo test, dotnet test, mvn/gradle test, rspec, phpunit, vitest run, jest). Keyed on the command the step executes, never on the workflow file it lives in. Excludes steps that are installing the runner rather than running it (`pip install pytest`) and bare `uses:` action steps. Abstains — hands the node back to the agent — whenever the step suppresses its own failure (`|| true`, `continue-on-error`) or regenerates its own expected output (`--update-snapshot`), because in those cases the exit code either cannot vary or the oracle was authored by the thing under test.",
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
      writeBoundary: {"producer":"the test runner process's exit code, produced by the language runtime executing the suite in the pipeline","actorCanWrite":false,"argument":"The step invokes a language test runner directly, so the step's exit status IS the runtime's verdict on executing the committed test modules against the built artefact. A failing assertion, an uncaught exception, an import error or a crash cannot be persuaded to report green without changing the code or the tests. Documented limit, and it matters: the EXECUTION is anchored, the ORACLE is not — implementation and assertions are typically authored by the same people in the same repo, so a green run proves the code does what these tests say, not that the tests say the right thing. Whether the step blocks a merge additionally depends on the workflow's triggers, which this shape does not read."},
      evidence: ["the step's run command is a direct invocation of a language test runner, with no install/provisioning command and no failure-suppressing flag"],
      confidence: 0.85,
    };
  },
};

export default probe;
export { probe };
