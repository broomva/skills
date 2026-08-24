/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          npm-ci-frozen-install (v1)
 * minted from: .github/workflows/tests.yml#26-npm-install
 * minted at:   2026-07-25T03:48:26.107Z
 * shape:
 * A pipeline step whose run command is `npm ci` — npm's lockfile-frozen install. It refuses to refresh a stale lock, errors when package.json and package-lock.json disagree, and verifies each downloaded tarball against the integrity hash in the lock, so it is a falsifiable assertion that two committed files agree and that the registry still serves what they name; it says nothing about whether the code works. This is the npm sibling of frozen-dependency-install, which covers --frozen-lockfile / --locked / --immutable / --deployment. The token is deliberately `run: npm ci` and not the bare `npm ci`: the bare form is a substring of `pnpm ci:<task>`, and that exact over-match was the defect withdrawn from frozen-dependency-install v1. Multi-line run blocks therefore fall through to the agent, which is the safe direction. Abstains when the step suppresses its own failure.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      npm's installer refusing to proceed when the committed package-lock.json and package.json disagree, plus registry tarball integrity hashes verified against the lockfile
 *   actorCanWrite: false
 *   `npm ci` is the frozen form of install, not the ordinary one: it will not refresh a stale lock, it errors out when package.json and package-lock.json are out of sync, and it verifies each downloaded tarball against the integrity hash recorded in the lock. So the step is a falsifiable assertion that two committed files agree and that the registry still serves the exact artefacts they name — an author who bumps a dependency and forgets to regenerate the lock cannot make it pass without changing the tree. Its exit code gates the rest of the job: `npm test` and `npm run check` (lines 28-31) only run if it succeeds. DOCUMENTED LIMIT: what is anchored is manifest/lock agreement and registry reachability, nothing about whether the code works.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = [];
const ANY_OF = ["run: npm ci"];
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

const ASSERT_ALL = ["npm ci"];
const ASSERT_ANY = [];
const ASSERT_NONE = ["|| true","continue-on-error","exit 0"];

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
  id: "npm-ci-frozen-install",
  version: 1,
  mintedAt: "2026-07-25T03:48:26.107Z",
  mintedFrom: ".github/workflows/tests.yml#26-npm-install",
  description: "A pipeline step whose run command is `npm ci` — npm's lockfile-frozen install. It refuses to refresh a stale lock, errors when package.json and package-lock.json disagree, and verifies each downloaded tarball against the integrity hash in the lock, so it is a falsifiable assertion that two committed files agree and that the registry still serves what they name; it says nothing about whether the code works. This is the npm sibling of frozen-dependency-install, which covers --frozen-lockfile / --locked / --immutable / --deployment. The token is deliberately `run: npm ci` and not the bare `npm ci`: the bare form is a substring of `pnpm ci:<task>`, and that exact over-match was the defect withdrawn from frozen-dependency-install v1. Multi-line run blocks therefore fall through to the agent, which is the safe direction. Abstains when the step suppresses its own failure.",
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
      writeBoundary: {"producer":"npm's installer refusing to proceed when the committed package-lock.json and package.json disagree, plus registry tarball integrity hashes verified against the lockfile","actorCanWrite":false,"argument":"`npm ci` is the frozen form of install, not the ordinary one: it will not refresh a stale lock, it errors out when package.json and package-lock.json are out of sync, and it verifies each downloaded tarball against the integrity hash recorded in the lock. So the step is a falsifiable assertion that two committed files agree and that the registry still serves the exact artefacts they name — an author who bumps a dependency and forgets to regenerate the lock cannot make it pass without changing the tree. Its exit code gates the rest of the job: `npm test` and `npm run check` (lines 28-31) only run if it succeeds. DOCUMENTED LIMIT: what is anchored is manifest/lock agreement and registry reachability, nothing about whether the code works."},
      evidence: [".github/workflows/tests.yml:26-27 (run: npm ci)","package-lock.json (the committed lockfile npm ci is pinned to)",".github/workflows/tests.yml:28-31 (subsequent steps depend on this exit code)"],
      confidence: 0.7,
    };
  },
};

export default probe;
export { probe };
