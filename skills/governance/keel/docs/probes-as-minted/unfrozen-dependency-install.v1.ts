/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          unfrozen-dependency-install (v1)
 * minted from: .github/workflows/ci.yml#31-install-dependencies
 * minted at:   2026-07-25T01:34:55.544Z
 * shape:
 * A pipeline step or script whose command is a plain dependency install (uv sync, npm/pnpm/yarn install, pip install, poetry install, bundle install, go mod download). Keyed on the command. Abstains — hands the node back to the agent — whenever a lockfile-freezing flag is present (--locked, --frozen, --frozen-lockfile, --deployment, npm ci), because those DO assert manifest/lock consistency and are a real check.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      a package manager's dependency resolver populating an environment
 *   actorCanWrite: null
 *   The command installs declared dependencies so that later steps can run. Without a lockfile-freezing flag the resolver will refresh a stale lock rather than error, so the step cannot report a discrepancy between the manifest and the lock; its non-zero exits mean the network or the index failed, not that the repository is wrong. The assertion in such a job lives in whatever executes against the installed environment afterwards.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = [];
const ANY_OF = ["uv sync","npm install","pnpm install","yarn install","pip install","poetry install","bundle install","go mod download"];
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

const ASSERT_ALL = [];
const ASSERT_ANY = ["uv sync","npm install","pnpm install","yarn install","pip install","poetry install","bundle install","go mod download"];
const ASSERT_NONE = ["--locked","--frozen","npm ci","--deployment","--require-hashes"];

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
  // RETIRED GENERALIZATION (epsilon-audit, 2026-07-24). This probe used to file a
  // whole step `not_a_check` because its `run:` block contained an install. On
  // tiktoken that swallowed two real checks:
  //     run: |
  //       pip install check-manifest
  //       check-manifest -v          <- exits non-zero if MANIFEST.in is wrong
  //     run: |
  //       pip install --upgrade build
  //       python -m build --sdist    <- exits non-zero if the build breaks
  // Both were agent-judged `anchored` and the probe called them `not_a_check` —
  // drift INTO the shoppable class, which inflates the ratio. A step is only an
  // install if installing is ALL it does; anything else in the block is work the
  // probe cannot see, so it abstains and the agent decides.
  const body = raw
    .split('\n')
    .map((l) => l.trim())
    .filter((l) => l && !/^-?\s*(name|run|uses|with|if|env|id)\s*:/.test(l) && !/^[|>&-]/.test(l));
  const installer = /^(pip|python\s+-m\s+pip|uv|npm|pnpm|yarn|poetry|bundle|go\s+mod)\b/;
  if (body.some((l) => !installer.test(l))) return false;
  return true;
}

const probe = {
  id: "unfrozen-dependency-install",
  version: 1,
  mintedAt: "2026-07-25T01:34:55.544Z",
  mintedFrom: ".github/workflows/ci.yml#31-install-dependencies",
  description: "A pipeline step or script whose command is a plain dependency install (uv sync, npm/pnpm/yarn install, pip install, poetry install, bundle install, go mod download). Keyed on the command. Abstains — hands the node back to the agent — whenever a lockfile-freezing flag is present (--locked, --frozen, --frozen-lockfile, --deployment, npm ci), because those DO assert manifest/lock consistency and are a real check.",
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
      writeBoundary: {"producer":"a package manager's dependency resolver populating an environment","actorCanWrite":null,"argument":"The command installs declared dependencies so that later steps can run. Without a lockfile-freezing flag the resolver will refresh a stale lock rather than error, so the step cannot report a discrepancy between the manifest and the lock; its non-zero exits mean the network or the index failed, not that the repository is wrong. The assertion in such a job lives in whatever executes against the installed environment afterwards."},
      evidence: ["the run command is a bare dependency install with no --locked/--frozen equivalent"],
      confidence: 0.8,
    };
  },
};

export default probe;
export { probe };
