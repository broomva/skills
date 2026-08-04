/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          format-check-invocation (v1)
 * minted from: package.json#check-format
 * minted at:   2026-07-25T03:48:21.359Z
 * shape:
 * A script or pipeline command that runs a code FORMATTER IN VERIFY MODE — prettier --check, black --check, cargo fmt --check, gofmt -l, ruff format --check, dotnet format --verify-no-changes, clang-format --dry-run. Keyed on the command being executed, never on the file it lives in. In verify mode the formatter re-formats in memory and compares against the committed bytes, exiting non-zero on a difference, so it is a falsifiable assertion computed by the binary rather than a claim the repo makes about itself. Deliberately does NOT match the rewriting forms (--write / --fix), which assert nothing, and does not match bare `uses:` action steps. Abstains — hands the node back to the agent — when the command suppresses its own failure (|| true, continue-on-error, exit 0) or also rewrites, because then the signal either cannot vary or the tree is being edited rather than judged.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      the prettier process's exit code, computed by re-formatting each committed file in memory and comparing the result to the bytes on disk
 *   actorCanWrite: false
 *   `--check` is the verify mode, not the rewrite mode: prettier prints the offending paths and exits 1 without touching the tree, so the signal is a genuine falsifiable comparison performed by the formatter binary against the committed bytes. An author cannot make an unformatted file pass without reformatting it or editing .prettierrc.js / .prettierignore. It reaches the merge path through `npm run check` at .github/workflows/tests.yml:30. DOCUMENTED LIMIT: what this asserts is formatting agreement only — it says nothing about whether the code is correct, and the style rules themselves are in-repo.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = [];
const ANY_OF = ["prettier --check","black --check","cargo fmt --check","gofmt -l","ruff format --check","--verify-no-changes","clang-format --dry-run"];
const NONE_OF = ["uses:"];

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
const ASSERT_ANY = ["prettier --check","black --check","cargo fmt --check","gofmt -l","ruff format --check","--verify-no-changes","clang-format --dry-run"];
const ASSERT_NONE = ["|| true","continue-on-error","exit 0","--write","--fix"];

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
  id: "format-check-invocation",
  version: 1,
  mintedAt: "2026-07-25T03:48:21.359Z",
  mintedFrom: "package.json#check-format",
  description: "A script or pipeline command that runs a code FORMATTER IN VERIFY MODE — prettier --check, black --check, cargo fmt --check, gofmt -l, ruff format --check, dotnet format --verify-no-changes, clang-format --dry-run. Keyed on the command being executed, never on the file it lives in. In verify mode the formatter re-formats in memory and compares against the committed bytes, exiting non-zero on a difference, so it is a falsifiable assertion computed by the binary rather than a claim the repo makes about itself. Deliberately does NOT match the rewriting forms (--write / --fix), which assert nothing, and does not match bare `uses:` action steps. Abstains — hands the node back to the agent — when the command suppresses its own failure (|| true, continue-on-error, exit 0) or also rewrites, because then the signal either cannot vary or the tree is being edited rather than judged.",
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
      writeBoundary: {"producer":"the prettier process's exit code, computed by re-formatting each committed file in memory and comparing the result to the bytes on disk","actorCanWrite":false,"argument":"`--check` is the verify mode, not the rewrite mode: prettier prints the offending paths and exits 1 without touching the tree, so the signal is a genuine falsifiable comparison performed by the formatter binary against the committed bytes. An author cannot make an unformatted file pass without reformatting it or editing .prettierrc.js / .prettierignore. It reaches the merge path through `npm run check` at .github/workflows/tests.yml:30. DOCUMENTED LIMIT: what this asserts is formatting agreement only — it says nothing about whether the code is correct, and the style rules themselves are in-repo."},
      evidence: ["package.json:13 (\"check:format\": \"prettier --check .\")",".prettierrc.js",".github/workflows/tests.yml:30-31"],
      confidence: 0.85,
    };
  },
};

export default probe;
export { probe };
