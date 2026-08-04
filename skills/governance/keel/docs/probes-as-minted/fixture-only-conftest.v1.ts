/**
 * MINTED PROBE — crystallized agent judgment. REVIEW ME, and reject me if the
 * generalization is wrong. That is why probes are code.
 *
 * id:          fixture-only-conftest (v1)
 * minted from: computer-use-demo/tests/conftest.py#conftest-py
 * minted at:   2026-07-25T03:57:47.038Z
 * shape:
 * A declared test-suite surface whose entire body is pytest fixture plumbing - it defines `@pytest.fixture` helpers (env patches, mocks, temp dirs) and contains no assertion and no test function. Fixtures set up the environment the real assertions run in; they cannot turn a run red on their own, so the file asserts nothing about correctness and the suite's actual verdict lives in the test modules. Abstains the moment the body contains an `assert`, a `def test_`, a raise, or a hard `exit 1`, because such a conftest can itself fail a run and must be judged by the agent.
 *
 * Write-boundary argument, carried verbatim from the judgment that produced it:
 *   producer:      an autouse pytest fixture that patches os.environ with HEIGHT/WIDTH/DISPLAY_NUM for the duration of every test
 *   actorCanWrite: null
 *   The whole file is one `mock.patch.dict` fixture and its yield — it contains no assert, no `def test_`, and no collection hook that can fail. It cannot turn the suite red; every assertion in this job lives in the test modules the fixture merely sets up. Worth naming rather than crediting: what it does do is substitute fabricated screen dimensions for the real environment, so it narrows what the tests it supports can observe.
 *
 * Contract: skills/keel/schemas/keel.ts (`Probe`). Deliberately untyped here:
 * minted probes live outside the repo, where a relative type import would not
 * resolve. Contributing it back to skills/keel/probes/? Add
 *   import type { Node, Probe } from '../schemas/keel.ts';
 * and annotate `probe` with `: Probe` so the compiler holds the contract.
 */

const KINDS = ["test_target"];
const ALL_OF = ["pytest.fixture"];
const ANY_OF = [];
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

const ASSERT_ALL = ["pytest.fixture"];
const ASSERT_ANY = [];
const ASSERT_NONE = ["assert","def test_","exit 1","raise"];

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
  id: "fixture-only-conftest",
  version: 1,
  mintedAt: "2026-07-25T03:57:47.038Z",
  mintedFrom: "computer-use-demo/tests/conftest.py#conftest-py",
  description: "A declared test-suite surface whose entire body is pytest fixture plumbing - it defines `@pytest.fixture` helpers (env patches, mocks, temp dirs) and contains no assertion and no test function. Fixtures set up the environment the real assertions run in; they cannot turn a run red on their own, so the file asserts nothing about correctness and the suite's actual verdict lives in the test modules. Abstains the moment the body contains an `assert`, a `def test_`, a raise, or a hard `exit 1`, because such a conftest can itself fail a run and must be judged by the agent.",
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
      writeBoundary: {"producer":"an autouse pytest fixture that patches os.environ with HEIGHT/WIDTH/DISPLAY_NUM for the duration of every test","actorCanWrite":null,"argument":"The whole file is one `mock.patch.dict` fixture and its yield — it contains no assert, no `def test_`, and no collection hook that can fail. It cannot turn the suite red; every assertion in this job lives in the test modules the fixture merely sets up. Worth naming rather than crediting: what it does do is substitute fabricated screen dimensions for the real environment, so it narrows what the tests it supports can observe."},
      evidence: ["computer-use-demo/tests/conftest.py:1-15","computer-use-demo/tests/conftest.py:8-12 (mock.patch.dict of HEIGHT/WIDTH/DISPLAY_NUM)"],
      confidence: 0.75,
    };
  },
};

export default probe;
export { probe };
