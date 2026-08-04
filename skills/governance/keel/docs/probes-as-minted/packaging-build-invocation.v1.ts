/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          packaging-build-invocation (v1)
 * minted from: .github/workflows/publish.yml#47-build
 * minted at:   2026-07-25T03:00:27.037Z
 * shape:
 * A pipeline step or script command that invokes a build/packaging toolchain as a gate — `python -m build`, `pyproject-build`, `poetry build`, `hatch build`, `flit build`, `cargo build`, `go build`, `dotnet build`, `mvn package`. Keyed on the command executed, never on the file it lives in. Does not match bare `uses:` action steps. Abstains — hands the node back to the agent — when the command's failure is suppressed (`|| true`, `continue-on-error`, `exit 0`), when it is a dry run, or when the word appears only because a package manager is installing something.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      the language's build/packaging backend executing over the checked-out tree, and its process exit code
 *   actorCanWrite: false
 *   The step shells out to a build or packaging command (python -m build, poetry/hatch/flit build, cargo build, go build, dotnet build, mvn package) which compiles or assembles the committed source. The verdict is computed by that toolchain from the tree: malformed metadata, an unresolvable dependency specifier, a type/compile error, or a layout that does not resolve all produce a non-zero exit, and an author cannot make an unbuildable tree report success without changing the tree. Documented limit: a green build proves the artefact compiles and packages, not that it behaves correctly — it says nothing about runtime semantics.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = [];
const ANY_OF = ["python -m build","pyproject-build","poetry build","hatch build","flit build","cargo build","go build","dotnet build","mvn package"];
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
const ASSERT_ANY = ["python -m build","pyproject-build","poetry build","hatch build","flit build","cargo build","go build","dotnet build","mvn package"];
const ASSERT_NONE = ["|| true","continue-on-error","exit 0","--dry-run","pip install","npm install","apt-get install"];

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
  id: "packaging-build-invocation",
  version: 1,
  mintedAt: "2026-07-25T03:00:27.037Z",
  mintedFrom: ".github/workflows/publish.yml#47-build",
  description: "A pipeline step or script command that invokes a build/packaging toolchain as a gate — `python -m build`, `pyproject-build`, `poetry build`, `hatch build`, `flit build`, `cargo build`, `go build`, `dotnet build`, `mvn package`. Keyed on the command executed, never on the file it lives in. Does not match bare `uses:` action steps. Abstains — hands the node back to the agent — when the command's failure is suppressed (`|| true`, `continue-on-error`, `exit 0`), when it is a dry run, or when the word appears only because a package manager is installing something.",
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
      writeBoundary: {"producer":"the language's build/packaging backend executing over the checked-out tree, and its process exit code","actorCanWrite":false,"argument":"The step shells out to a build or packaging command (python -m build, poetry/hatch/flit build, cargo build, go build, dotnet build, mvn package) which compiles or assembles the committed source. The verdict is computed by that toolchain from the tree: malformed metadata, an unresolvable dependency specifier, a type/compile error, or a layout that does not resolve all produce a non-zero exit, and an author cannot make an unbuildable tree report success without changing the tree. Documented limit: a green build proves the artefact compiles and packages, not that it behaves correctly — it says nothing about runtime semantics."},
      evidence: [".github/workflows/publish.yml:47-49"],
      confidence: 0.82,
    };
  },
};

export default probe;
export { probe };
