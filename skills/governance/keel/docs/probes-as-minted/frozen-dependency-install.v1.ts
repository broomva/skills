/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          frozen-dependency-install (v1)
 * minted from: .github/workflows/update-model-settings.yml#64-install-dependencies
 * minted at:   2026-07-25T02:24:47.041Z
 * shape:
 * A dependency install command that is pinned to the committed lockfile (--frozen-lockfile, --locked, --immutable, npm ci, --deployment, --require-hashes). Unlike a bare install, the resolver refuses to refresh a stale lock and exits non-zero, so the step is a falsifiable assertion that the manifest and the lockfile in the tree agree. It says nothing about whether the code works.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      pnpm's resolver comparing the committed pnpm-lock.yaml against the committed package.json manifests, and refusing to proceed on a mismatch
 *   actorCanWrite: false
 *   `--frozen-lockfile` is what makes this different from a plain install: pnpm will not refresh a stale lock, it exits non-zero, so the step is a genuine falsifiable assertion about two committed files agreeing — an author who edits a dependency and forgets to regenerate the lock cannot make this pass without changing the tree. The producer is the resolver executing, not anyone's claim. The exit code gates the rest of the job: the 'Generate model settings' and PR-creation steps below only run if this succeeds. DOCUMENTED LIMIT: what is anchored is manifest/lock agreement and registry reachability, nothing about whether the code works; and this instance sits in a scheduled bot workflow, so it gates that workflow's PR creation rather than a merge (the same command in ci.yml is the merge-gating instance).
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = [];
const ANY_OF = ["npm ci","npm install","pnpm install","yarn install","uv sync","pip install","poetry install","bundle install","pdm install","composer install"];
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
const ASSERT_ANY = ["--frozen","--locked","--immutable","npm ci","--deployment","--require-hashes"];
const ASSERT_NONE = ["|| true","continue-on-error: true"];

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
  id: "frozen-dependency-install",
  version: 1,
  mintedAt: "2026-07-25T02:24:47.041Z",
  mintedFrom: ".github/workflows/update-model-settings.yml#64-install-dependencies",
  description: "A dependency install command that is pinned to the committed lockfile (--frozen-lockfile, --locked, --immutable, npm ci, --deployment, --require-hashes). Unlike a bare install, the resolver refuses to refresh a stale lock and exits non-zero, so the step is a falsifiable assertion that the manifest and the lockfile in the tree agree. It says nothing about whether the code works.",
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
      writeBoundary: {"producer":"pnpm's resolver comparing the committed pnpm-lock.yaml against the committed package.json manifests, and refusing to proceed on a mismatch","actorCanWrite":false,"argument":"`--frozen-lockfile` is what makes this different from a plain install: pnpm will not refresh a stale lock, it exits non-zero, so the step is a genuine falsifiable assertion about two committed files agreeing — an author who edits a dependency and forgets to regenerate the lock cannot make this pass without changing the tree. The producer is the resolver executing, not anyone's claim. The exit code gates the rest of the job: the 'Generate model settings' and PR-creation steps below only run if this succeeds. DOCUMENTED LIMIT: what is anchored is manifest/lock agreement and registry reachability, nothing about whether the code works; and this instance sits in a scheduled bot workflow, so it gates that workflow's PR creation rather than a merge (the same command in ci.yml is the merge-gating instance)."},
      evidence: [".github/workflows/update-model-settings.yml:64-65 (run: pnpm install --frozen-lockfile)",".github/workflows/update-model-settings.yml:67-71 ('Generate model settings' runs after it)",".github/workflows/ci.yml:31, :57, :100, :126 (same frozen install on the merge-gating path)"],
      confidence: 0.72,
    };
  },
};

export default probe;
export { probe };
