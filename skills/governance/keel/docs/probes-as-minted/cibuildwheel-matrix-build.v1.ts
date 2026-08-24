/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          cibuildwheel-matrix-build (v1)
 * minted from: .github/workflows/build_wheels.yml#25-pypa-cibuildwheel-65b8265957fd86372d9689a0acdfd55813970d5d-v3-1-4
 * minted at:   2026-07-25T03:05:56.296Z
 * shape:
 * A CI step whose body is a `uses:` of the pypa/cibuildwheel action. Keyed on the action reference — what the step DOES — never on the workflow file it sits in. cibuildwheel compiles/packages the project once per target interpreter and architecture and optionally runs the project's configured test-command against each built wheel, so its exit code is produced by a toolchain executing the committed source. Abstains — hands the node back to the agent — when the step suppresses its own failure (`continue-on-error`, `|| true`, `exit 0`) or is run in a listing/dry-run mode (`--print-build-identifiers`), because then the signal either cannot vary or nothing is built.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      the cibuildwheel run: the project's build backend and compiler toolchain executing over the checked-out source once per matrix cell, plus the test-command process cibuildwheel runs against each wheel it produced
 *   actorCanWrite: false
 *   cibuildwheel's entire function is to execute the project's build backend against the committed source in a clean container/venv per target interpreter and architecture, and then, where the project's cibuildwheel table defines a test-command, to install the resulting wheel into a fresh environment and run that command. Every pass/fail it emits is an exit code from a compiler, a build backend, or a test runner executing the artifact under test; an author cannot make a compile error or a failing suite report clean without changing the source or the pinned action/config. DOCUMENTED LIMITS: (1) if the project defines no test-command the step asserts only that the package builds, not that it works; (2) where a test-command exists, its assertions are authored in-repo alongside the implementation, so the execution axis is anchored while the oracle sits inside the write boundary; (3) test-skip patterns can leave some matrix cells built but never exercised.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step"];
const ALL_OF = ["uses:"];
const ANY_OF = ["cibuildwheel@"];
const NONE_OF = [];

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

const ASSERT_ALL = ["cibuildwheel@"];
const ASSERT_ANY = [];
const ASSERT_NONE = ["continue-on-error","|| true","exit 0","--print-build-identifiers","--dry-run"];

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
  id: "cibuildwheel-matrix-build",
  version: 1,
  mintedAt: "2026-07-25T03:05:56.296Z",
  mintedFrom: ".github/workflows/build_wheels.yml#25-pypa-cibuildwheel-65b8265957fd86372d9689a0acdfd55813970d5d-v3-1-4",
  description: "A CI step whose body is a `uses:` of the pypa/cibuildwheel action. Keyed on the action reference — what the step DOES — never on the workflow file it sits in. cibuildwheel compiles/packages the project once per target interpreter and architecture and optionally runs the project's configured test-command against each built wheel, so its exit code is produced by a toolchain executing the committed source. Abstains — hands the node back to the agent — when the step suppresses its own failure (`continue-on-error`, `|| true`, `exit 0`) or is run in a listing/dry-run mode (`--print-build-identifiers`), because then the signal either cannot vary or nothing is built.",
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
      writeBoundary: {"producer":"the cibuildwheel run: the project's build backend and compiler toolchain executing over the checked-out source once per matrix cell, plus the test-command process cibuildwheel runs against each wheel it produced","actorCanWrite":false,"argument":"cibuildwheel's entire function is to execute the project's build backend against the committed source in a clean container/venv per target interpreter and architecture, and then, where the project's cibuildwheel table defines a test-command, to install the resulting wheel into a fresh environment and run that command. Every pass/fail it emits is an exit code from a compiler, a build backend, or a test runner executing the artifact under test; an author cannot make a compile error or a failing suite report clean without changing the source or the pinned action/config. DOCUMENTED LIMITS: (1) if the project defines no test-command the step asserts only that the package builds, not that it works; (2) where a test-command exists, its assertions are authored in-repo alongside the implementation, so the execution axis is anchored while the oracle sits inside the write boundary; (3) test-skip patterns can leave some matrix cells built but never exercised."},
      evidence: ["the step body is a `uses:` of the pypa/cibuildwheel action, whose failure signal is a build/test toolchain exit code"],
      confidence: 0.75,
    };
  },
};

export default probe;
export { probe };
