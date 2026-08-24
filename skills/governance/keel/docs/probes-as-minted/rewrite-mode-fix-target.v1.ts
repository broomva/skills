/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          rewrite-mode-fix-target (v1)
 * minted from: package.json#fix-format
 * minted at:   2026-07-25T03:48:25.989Z
 * shape:
 * A script or pipeline command that runs a formatter/linter in REWRITE mode — prettier --write, eslint --fix, ruff format, cargo fmt, gofmt -w, black . — rather than in verify mode. The command's effect is to edit the working tree until the tool is satisfied; it produces no surviving verdict about the artefact, so it belongs outside the ratio. Keyed on the write-mode flag/command, never on the target's name or the file it lives in, and it refuses to fire when a verify flag (--check, --diff, --dry-run, --list-different, --verify) is present. Abstains whenever the command is chained (&&, ||, ;) or mentions a test runner, because then a real assertion may be riding along behind the rewrite and only the agent should say whether the edge asserts anything.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      no verdict producer — prettier in --write mode edits the files and exits 0
 *   actorCanWrite: null
 *   `prettier --write .` rewrites every file it can parse and reports success; it is the remediation counterpart of check:format, not an assertion. There is no state in which it says 'this tree is wrong' — it makes the tree conform instead — so it is structurally incapable of being a check, and no workflow calls it. The assertion about formatting is made by `prettier --check .` in the CI-invoked `npm run check`.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["ci_step","script"];
const ALL_OF = [];
const ANY_OF = ["--write","--fix","gofmt -w","ruff format","cargo fmt","black ."];
const NONE_OF = ["--check","--diff","--dry-run","--list-different","--verify"];

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
const ASSERT_ANY = ["--write","--fix","gofmt -w","ruff format","cargo fmt","black ."];
const ASSERT_NONE = ["&&","||",";","--check","test"];

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
  id: "rewrite-mode-fix-target",
  version: 1,
  mintedAt: "2026-07-25T03:48:25.989Z",
  mintedFrom: "package.json#fix-format",
  description: "A script or pipeline command that runs a formatter/linter in REWRITE mode — prettier --write, eslint --fix, ruff format, cargo fmt, gofmt -w, black . — rather than in verify mode. The command's effect is to edit the working tree until the tool is satisfied; it produces no surviving verdict about the artefact, so it belongs outside the ratio. Keyed on the write-mode flag/command, never on the target's name or the file it lives in, and it refuses to fire when a verify flag (--check, --diff, --dry-run, --list-different, --verify) is present. Abstains whenever the command is chained (&&, ||, ;) or mentions a test runner, because then a real assertion may be riding along behind the rewrite and only the agent should say whether the edge asserts anything.",
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
      writeBoundary: {"producer":"no verdict producer — prettier in --write mode edits the files and exits 0","actorCanWrite":null,"argument":"`prettier --write .` rewrites every file it can parse and reports success; it is the remediation counterpart of check:format, not an assertion. There is no state in which it says 'this tree is wrong' — it makes the tree conform instead — so it is structurally incapable of being a check, and no workflow calls it. The assertion about formatting is made by `prettier --check .` in the CI-invoked `npm run check`."},
      evidence: ["package.json:19 (\"fix:format\": \"prettier --write .\")","package.json:13 (the --check counterpart)"],
      confidence: 0.85,
    };
  },
};

export default probe;
export { probe };
