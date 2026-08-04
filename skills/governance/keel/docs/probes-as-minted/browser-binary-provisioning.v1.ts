/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          browser-binary-provisioning (v1)
 * minted from: .github/workflows/publish.yml#130-uvx-playwright-install-chrome
 * minted at:   2026-07-25T02:45:47.887Z
 * shape:
 * A pipeline step or script command that downloads a browser engine for automation — `playwright install <browser>`, `puppeteer browsers install`, or an equivalent `install chromium/chrome/firefox/webkit` fetch. Keyed on the command, never on the workflow file it lives in. Does not match bare `uses:` action steps. Abstains — hands the node back to the agent — when the same body also runs something that can assert on the repository (a test runner, a linter, an explicit `exit 1` branch, a diff), because a compound step can genuinely fail on a property of the code.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      a browser-automation CLI downloading a browser build into the runner's cache
 *   actorCanWrite: false
 *   The command fetches a browser binary so that later steps have one to drive. It evaluates nothing about the repository: its only failure modes are network reachability and CDN availability, which are properties of the runner's environment rather than of the code under test. Nothing downstream reads a pass/fail from it, so it is machine preparation and is excluded from the ratio rather than counted as a weak check.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = [];
const ANY_OF = ["playwright install","browsers install","install chromium","install chrome","install firefox","install webkit"];
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
const ASSERT_ANY = ["playwright install","browsers install","install chromium","install chrome","install firefox","install webkit"];
const ASSERT_NONE = ["pytest","npm test","go test","cargo test","vitest","jest","exit 1","|| true","lint","assert","diff"];

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
  id: "browser-binary-provisioning",
  version: 1,
  mintedAt: "2026-07-25T02:45:47.887Z",
  mintedFrom: ".github/workflows/publish.yml#130-uvx-playwright-install-chrome",
  description: "A pipeline step or script command that downloads a browser engine for automation — `playwright install <browser>`, `puppeteer browsers install`, or an equivalent `install chromium/chrome/firefox/webkit` fetch. Keyed on the command, never on the workflow file it lives in. Does not match bare `uses:` action steps. Abstains — hands the node back to the agent — when the same body also runs something that can assert on the repository (a test runner, a linter, an explicit `exit 1` branch, a diff), because a compound step can genuinely fail on a property of the code.",
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
      writeBoundary: {"producer":"a browser-automation CLI downloading a browser build into the runner's cache","actorCanWrite":false,"argument":"The command fetches a browser binary so that later steps have one to drive. It evaluates nothing about the repository: its only failure modes are network reachability and CDN availability, which are properties of the runner's environment rather than of the code under test. Nothing downstream reads a pass/fail from it, so it is machine preparation and is excluded from the ratio rather than counted as a weak check."},
      evidence: [".github/workflows/publish.yml:130"],
      confidence: 0.85,
    };
  },
};

export default probe;
export { probe };
