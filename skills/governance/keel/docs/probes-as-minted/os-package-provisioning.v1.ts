/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          os-package-provisioning (v1)
 * minted from: .github/workflows/ubuntu-tests.yml#41-install-system-dependencies
 * minted at:   2026-07-25T02:36:04.338Z
 * shape:
 * A pipeline step or script whose command is an operating-system package-manager install (apt-get install/update, apt install, apk add, yum/dnf install, brew install, choco install, pacman -S). Keyed on the command, never on the file it lives in. Abstains — hands the node back to the agent — when the same step also runs something that could assert on the repository (a test runner, a build tool, a make target), because a compound step can genuinely fail on a property of the code.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      an operating-system package manager fetching packages from a distribution mirror onto the runner
 *   actorCanWrite: null
 *   The command installs OS-level packages or headers so that later steps have a toolchain or shared library to build and link against. Nothing in the repository is read or evaluated: a non-zero exit means the distribution mirror was unreachable or a package name changed upstream, never that the code under review is wrong, and the mirror's contents are not part of the artefact being verified. Whatever assertion exists in such a job is made by the step that executes against the provisioned environment afterwards, so this edge must not enter the ratio in either direction.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = [];
const ANY_OF = ["apt-get install","apt-get update","apt install","apk add","yum install","dnf install","brew install","choco install","pacman -s"];
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
const ASSERT_ANY = ["apt-get install","apt-get update","apt install","apk add","yum install","dnf install","brew install","choco install","pacman -s"];
const ASSERT_NONE = ["pytest","npm run","go test","cargo","make","./gradlew","tox","lint"];

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
  id: "os-package-provisioning",
  version: 1,
  mintedAt: "2026-07-25T02:36:04.338Z",
  mintedFrom: ".github/workflows/ubuntu-tests.yml#41-install-system-dependencies",
  description: "A pipeline step or script whose command is an operating-system package-manager install (apt-get install/update, apt install, apk add, yum/dnf install, brew install, choco install, pacman -S). Keyed on the command, never on the file it lives in. Abstains — hands the node back to the agent — when the same step also runs something that could assert on the repository (a test runner, a build tool, a make target), because a compound step can genuinely fail on a property of the code.",
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
      class: "not_a_check",
      writeBoundary: {"producer":"an operating-system package manager fetching packages from a distribution mirror onto the runner","actorCanWrite":null,"argument":"The command installs OS-level packages or headers so that later steps have a toolchain or shared library to build and link against. Nothing in the repository is read or evaluated: a non-zero exit means the distribution mirror was unreachable or a package name changed upstream, never that the code under review is wrong, and the mirror's contents are not part of the artefact being verified. Whatever assertion exists in such a job is made by the step that executes against the provisioned environment afterwards, so this edge must not enter the ratio in either direction."},
      evidence: ["the run command is an OS package-manager install with no command of its own that touches the repository"],
      confidence: 0.9,
    };
  },
};

export default probe;
export { probe };
