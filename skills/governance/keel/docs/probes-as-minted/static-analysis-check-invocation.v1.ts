/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          static-analysis-check-invocation (v1)
 * minted from: .github/workflows/lint.yml#31-uv-run-ruff-check-no-fix-select-ple
 * minted at:   2026-07-25T02:45:27.908Z
 * shape:
 * A pipeline step or script command that invokes a static analyser as a check — ruff check, eslint, mypy, pyright, flake8, pylint, golangci-lint, cargo clippy, biome check, staticcheck, tsc --noEmit. Keyed on the command being executed, never on the file it lives in. Does not match bare `uses:` action steps and does not match tool CONFIG tables (`[tool.…]`), which declare rules rather than produce an exit code. Abstains — hands the node back to the agent — when the command suppresses its own failure (`|| true`, `continue-on-error`, `exit 0`), when it rewrites instead of reporting (`--fix`, `--write`), or when the analyser name appears only because the step is installing it.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      the static-analysis tool's process exit code — a linter or type checker parsing the checked-out source and returning non-zero on a violation
 *   actorCanWrite: false
 *   The step shells out to a static analyser (ruff check, eslint, mypy, pyright, flake8, pylint, golangci-lint, cargo clippy, biome check, staticcheck, tsc --noEmit) over the committed tree. The verdict is computed by that program from the source text, so an author cannot make a violating file report clean without changing the file or changing the pinned analyser configuration — the signal's producer is the interpreter/binary, not any claim the repository makes about itself. Documented limit: the RULE SET is author-controlled (select/ignore/exclude lists live in the repo), so this is anchored on the execution axis while the scope of what gets enforced sits inside the write boundary.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = [];
const ANY_OF = ["ruff check","eslint","mypy","pyright","flake8","pylint","golangci-lint","cargo clippy","biome check","staticcheck","tsc --noemit"];
const NONE_OF = ["uses:","[tool."];

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
const ASSERT_ANY = ["ruff check","eslint","mypy","pyright","flake8","pylint","golangci-lint","cargo clippy","biome check","staticcheck","tsc --noemit"];
const ASSERT_NONE = ["|| true","continue-on-error","exit 0","--fix","--write","pip install","npm install","uv add","apt-get install"];

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
  id: "static-analysis-check-invocation",
  version: 1,
  mintedAt: "2026-07-25T02:45:27.908Z",
  mintedFrom: ".github/workflows/lint.yml#31-uv-run-ruff-check-no-fix-select-ple",
  description: "A pipeline step or script command that invokes a static analyser as a check — ruff check, eslint, mypy, pyright, flake8, pylint, golangci-lint, cargo clippy, biome check, staticcheck, tsc --noEmit. Keyed on the command being executed, never on the file it lives in. Does not match bare `uses:` action steps and does not match tool CONFIG tables (`[tool.…]`), which declare rules rather than produce an exit code. Abstains — hands the node back to the agent — when the command suppresses its own failure (`|| true`, `continue-on-error`, `exit 0`), when it rewrites instead of reporting (`--fix`, `--write`), or when the analyser name appears only because the step is installing it.",
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
      writeBoundary: {"producer":"the static-analysis tool's process exit code — a linter or type checker parsing the checked-out source and returning non-zero on a violation","actorCanWrite":false,"argument":"The step shells out to a static analyser (ruff check, eslint, mypy, pyright, flake8, pylint, golangci-lint, cargo clippy, biome check, staticcheck, tsc --noEmit) over the committed tree. The verdict is computed by that program from the source text, so an author cannot make a violating file report clean without changing the file or changing the pinned analyser configuration — the signal's producer is the interpreter/binary, not any claim the repository makes about itself. Documented limit: the RULE SET is author-controlled (select/ignore/exclude lists live in the repo), so this is anchored on the execution axis while the scope of what gets enforced sits inside the write boundary."},
      evidence: [".github/workflows/lint.yml:31"],
      confidence: 0.85,
    };
  },
};

export default probe;
export { probe };
