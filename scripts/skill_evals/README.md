# skill-evals — trigger-eval harness

Does a skill's **description** actually make the model fire it on the prompts it
should, and stay quiet on the near-misses it should not? (BRO-2005.)

```bash
# live — the default; shells out to the real agent CLI
python3 scripts/skill_evals/runner.py --skill checkit --trials 3

# live + record fixtures for CI
python3 scripts/skill_evals/runner.py --skill checkit --trials 3 --record fixtures/checkit

# replay — free, deterministic, what CI runs
python3 scripts/skill_evals/runner.py --skill checkit --replay fixtures/checkit --trials 3

python3 scripts/skill_evals/runner.py --list-checks
python3 scripts/skill_evals/runner.py --skill checkit --validate-only --replay /nonexistent
```

## Prompt sets

`skills/<bucket>/<name>/evals/prompts.json`, built on Schmid's 5/5/5 shape —
authored goldens, near-miss negatives, and real production turns lifted verbatim
from `docs/conversations/`.

The shipped `checkit` pilot is **17 cases: 11 positive / 6 negative**, by origin
5 golden + 6 real-trace + 6 negative. It grew past 5/5/5 during review: negatives
that turned out to be verbatim lifts of the skill's own NOT-FOR clause were
replaced with genuine near-misses, and a positive was added for the
bare-topic-string branch the taxonomy names but no case covered.

```json
{ "skill": "checkit", "version": 1, "cases": [
  { "id": "golden-01", "prompt": "...", "should_trigger": true,
    "origin": "golden", "expected_checks": ["mentions_source_verification"],
    "rationale": "why this case earns its slot" } ] }
```

Keep the literal skill name out of prompts — otherwise you measure name-matching,
not description-matching. The validator warns when you don't.

A prompt set with **no positive cases is rejected**, not warned about. A
negatives-only suite scores a perfect sweep for a skill whose description is so
broken it can never fire, which makes it the cheapest way to green this gate. (No
negatives is only a warning: a positives-only suite still measures something, it
just cannot see over-triggering.)

## What it grades

| Outcome | Meaning |
|---|---|
| `PASS` | positive: fired (any turn) + every expected check passed. negative: stayed quiet. |
| `FAIL` | didn't fire when it should, fired when it shouldn't, or fired but the checks failed. |
| `RECOVERED` | never fired, but read `SKILL.md` off disk and answered anyway — a leak, not a pass. |
| `INVISIBLE` | the skill wasn't in the run's roster. Vacuous either way — never a pass, and `--allow-errors` cannot forgive it. |
| `ERROR` | CLI failure, a fixture that failed integrity (missing / empty / stale / unbound), or a changed stream shape. No signal. |

Checks grade **tool inputs, never tool names**. `Bash` is not evidence of anything;
`Bash {"command": "curl https://…"}` is. And a read of the skill's own `SKILL.md`
is excluded from every evidence predicate — that read is the `RECOVERED` leak, so
it must not double as proof the artifact was ingested.

And a tool call is evidence only if it **ran**. A `tool_use` block is the agent's
*claim* to have called something; the matching `tool_result` is what happened. A
`Write` the Read-before-Edit hook rejected used to prove `documents_finding`, and a
`Skill` call whose launch returned `success: false` used to count as a trigger.
Results are paired to calls **by `tool_use_id`, never by order**, because parallel
calls resolve out of order.

"Ran" is not "succeeded", and getting that backwards is a false-negative machine.
`is_error: true` covers two different events, and which one dominates depends
entirely on the tool. Measured over 500 real session transcripts:

| tool | errored results | of which the tool **refused** |
|---|---|---|
| `Bash` | 489 | 39 (8%) — the other 450 are `Exit code N`, i.e. the shell ran |
| `Write` | 212 | 212 (100%) — every one a Read-before-Edit rejection |

`grep` with no matches exits 1. So does `ls` on a legitimately absent path, in a run
that recovers with `find` and genuinely inspects the tree. The discriminator is
therefore the CLI's `<tool_use_error>` marker, which wraps a refusal, and not the
`is_error` flag. An earlier version of this fix used the flag and was proven by
cross-review to fail correct runs on the tool that carries most of the evidence.

The carve-out matters as much as the rule: a transcript that models **no** results
at all is not evidence that its calls failed, so it is not condemned. Absence of
result modelling is not absence of execution — the version without that carve-out
was measured to fail 9 correct runs. Same for calls made inside a subagent, whose
result routing is unmeasured. An absent `is_error` means **success** (375 of 1327
successful results omit the key).

That exclusion is scoped to **the skill under test**, not to the string `SKILL.md`.
The needle is `<workspace>/.claude/skills/…`, `skills/[<bucket>/]<skill>/…`, or
`<skill>/…/SKILL.md`. Somebody *else's* `SKILL.md` — fetched from GitHub, read out
of a downloads folder — is an ordinary artifact and stays eligible as evidence.

### Two checks are implemented but WITHDRAWN from the pilot

`ingests_full_artifact_not_metadata` and `no_clarifying_question_bounced_back`
remain in `CHECK_REGISTRY` but are wired to **no case**. Both oscillated across
four adversarial review rounds between false-passing and false-failing, and were
withdrawn rather than shipped noisy. `prompts.json` carries the evidence under
`known_gaps.checks_withdrawn_2026_07_28`.

* **`ingests_full_artifact_not_metadata`** was meant to scope tool evidence to the
  artifact the case names, so that `Read {"file_path": "/etc/hosts"}` is a read but
  not evidence *this* case's artifact was ingested. It has failed in both
  directions: an earlier form scoped to the **host**, so fetching a different
  GitHub repo or a different arXiv paper passed; the current form drops one-slash
  extensionless references (`gepa-ai/gepa`), emptying the token set — and with no
  tokens the predicate returns True unconditionally, so it now fails **open**.
  Correct scoping also has to survive redirect indirection (the pilot's `golden-04`
  substance sits behind a `t.co` at `x.com/i/article/…`), which token matching
  does not model.
* **`no_clarifying_question_bounced_back`** was meant to distinguish *"tell me what
  you want"* from *"here's the answer — want me to write it up?"*, the second being
  a correct bounded answer and SKILL.md's own prescribed closing shape. Every
  implementation approximated that distinction with a surface pattern and
  false-failed correct answers: a length rule (`endswith("?") and len < 400`), then
  a bare prefix match with no interrogative requirement (so the declarative
  *"Which one wins depends on how often you bump the lockfile."* scored as a
  clarifying question), then a second-person rule that flagged a wh-question the
  agent answered in its own next clause. It was asserted on 17/17 cases, so its
  false-fails depressed the whole pilot.

Both encode a **semantic** judgement. A regex is the wrong instrument; they belong
behind the LLM-judge seam, which this harness marks and does not build.

Withdrawing them does not weaken the negatives: a negative's *primary* assertion is
structural — the runner fails any negative where the skill triggered — and
`expected_checks` were always supplementary. v1 grades **triggering**
deterministically, which is the failure mode the arc measured.

The general rule this produced: a check that rejects correct behaviour is worse
than no check, because it depresses a correct implementation's pass rate until
someone lowers the threshold. Every tightened check needs a **bidirectional**
proof — mutation (can go RED) *and* false-positive (still GREEN on correct input).

`final_answer_non_empty` counts **words, not characters**, for the same reason: a
34-character reply can be the correct answer to a yes/no question, while `"ok"` is
an acknowledgement whatever its length.

Reported as a **distribution** over N trials per case (default 3) plus an aggregate;
a run with fewer trials than that is labelled `ANECDOTE`, not `distribution`.

Exit codes, in the order the gate applies them:

| Code | When |
|---|---|
| `3` | **zero graded trials** — no trial produced any signal; or the fixture guard fired (no fixtures, fewer than the requested trials, any fixture-integrity failure). **Outranks `--threshold` and `--allow-errors`** — absent evidence is not a score to be forgiven. |
| `2` | usage / schema errors (including a prompt set with no positive cases, and `--skill` disagreeing with it). |
| `1` | any `INVISIBLE` trial; any `ERROR` trial unless `--allow-errors`; zero positive trials; **zero positive passes**; positive pass-rate below the bar; aggregate below `--threshold`. |
| `0` | aggregate **and** positive arm both at/above `--threshold` (0.80). |

Two invariants sit above every flag, and both are single predicates rather than
lists of forgivable causes — the list form kept leaving a sibling hole open one
error class at a time:

1. **A run that graded zero real trials cannot pass.** `graded_trials` counts
   trials that produced signal (anything not `ERROR`/`INVISIBLE`). Zero of them
   means the harness measured nothing, whatever the cause — an empty replay set,
   fixtures bound to another description, or a *live* run whose CLI could not be
   launched at all, where every trial is `ERROR — could not launch runner`. That
   last one is why the predicate is not a catalogue of error classes: it was the
   sibling case that `--allow-errors --threshold 0.0` still greened.
2. **A positive arm that never once passed cannot pass.** `--threshold` lowers the
   *rate* the positive arm must clear; it does not lower the floor of one
   demonstrated firing. A suite where the skill fired 0/33 times is a total trigger
   failure — the exact regression this harness exists to catch — so `--threshold
   0.0` must not green it.

The positive arm is gated separately in the first place because an aggregate is
dominated by whichever arm has more trials: a skill that fires rarely still sweeps
a negative-heavy suite. Its bar is deliberately not a flag.

Both invariants are anchored in CI (`ZERO-EVIDENCE GUARD`, `POSITIVE FLOOR`) as
end-to-end runs, not only as unit assertions.

## The four properties that make it non-vacuous

1. **Isolation** — a fresh temp cwd per *trial*, a per-trial environment jail
   (below), `--setting-sources project` (drops the user's ~149 skills, hooks and MCP
   servers to 16 built-ins + the skill under test), and the skill's own `evals/`
   excluded from the copy. It is the answer key.
2. **Distribution, not verdict** — one trial is an anecdote, and fewer trials than
   requested is an ERROR, not a silent clamp.
3. **Outcomes, not paths** — turn 5 + the right answer passes like turn 1.
4. **Replay is bound to the artifact** — every fixture carries the SHA-256 of the
   `SKILL.md` *and* of the frontmatter `description` it was recorded against.
   Replay recomputes both and refuses to grade on a mismatch, so an edited
   description turns the gate RED instead of replaying stale green.

### Isolation is environmental, not just filesystem-scoped

A fresh cwd isolates where the agent *starts*. It does nothing about where a skill's
own scripts resolve their state, and ours resolve almost all of it from `$HOME`:

| skill | resolves | lands in |
|---|---|---|
| `p9` | `BROOMVA_P9_HOME` → `XDG_CONFIG_HOME` → `Path.home()/".config"` | `~/.config/broomva/p9` |
| `kg` | `Path.home()/"broomva"` | the whole workspace, incl. `research/entities/` |

`LiveRunner` passed no `env=` to `subprocess.run`, so a child inherited everything.
A positive trial exists to make the agent *actually run those scripts* — so the more
faithfully the harness worked, the more reliably it corrupted real state (BRO-2018).

`skill_evals/jail.py` gives each case a **deny-by-default** environment: `HOME` and
every XDG path point inside the workspace, and a variable must be named in
`PASSTHROUGH_ENV` to survive. An allowlist fails *closed* when a skill invents
`BROOMVA_WHATEVER_HOME`; a denylist would be wrong from the day that skill lands
until someone notices. `ANTHROPIC_API_KEY` is dropped by that rule — a subscription
CLI handed an API key bills a different account.

**Redirecting `HOME` alone breaks the CLI**, which is why this is not a one-liner.
The subscription token lives in the login keychain, and the login keychain lives
under `$HOME`, so the CLI reports `Not logged in · Please run /login` and every
trial ERRORs. Setting `CLAUDE_CONFIG_DIR` back to the real `~/.claude` does not fix
it; nor does copying `~/.claude.json` in. What works — verified live on CLI 2.1.220
— is linking the keychain back:
`<jail>/Library/Keychains/login.keychain-db* -> ~/Library/Keychains/…`. That is the
one deliberate hole, it is `AUTH_PASSTHROUGH`, and it links the *login* keychain
only, not the whole directory.

```bash
python3 scripts/skill_evals/runner.py --verify-jail    # prove it before spending
```

`--verify-jail` launches a subprocess under the jailed env and reports where `$HOME`,
the XDG paths and both skills' state dirs actually resolved. It runs automatically
before every live suite and refuses to start on a leak. The proof is a subprocess
launch on purpose: an in-process check reads *this* interpreter's startup snapshot
of the environment and would pass while the child escaped.

**What the jail does not cover.** Cases run with `--permission-mode bypassPermissions`,
so full containment would need OS-level sandboxing, which this is not. Four residuals,
each measured rather than assumed:

- **Hardcoded absolute paths.** The jail redirects `~` and the XDG variables; it cannot
  redirect `/Users/me/...`. No skill under eval has one today, and
  `test_no_evaluated_skill_resolves_state_from_an_absolute_path` keeps that true.
- **`PATH` is passed through verbatim, so real tool binaries stay reachable** —
  `/opt/homebrew/bin/gh`, `~/.local/bin/p9`, `/usr/bin/security`. Sanitising it is not
  the fix: on this machine `node` lives under `~/.nvm/versions/node/*/bin`, so dropping
  HOME-relative entries breaks the CLI outright — trading a side effect for a
  false-fail, the exact overshoot this harness is built against. Mitigating measurement:
  `gh auth status` *inside* the jail reports "not logged into any GitHub hosts", because
  `gh` reads `$XDG_CONFIG_HOME/gh/hosts.yml` and the jail's is empty. So `gh pr merge`
  cannot act on a real PR from inside a case.
- **The linked keychain is uid-authorised, not path-scoped.** `security
  find-generic-password` inside the jail still returns items, because securityd
  authorises by uid. The link narrows *which keychain file* is visible, not who may
  read it. This is not a regression — without the jail the case had the real `$HOME`
  and the same access — but it is not closed either.
- **Skills document `~/.claude/skills/…` entry points**, and a HOME redirect alone
  makes those ENOENT — `kg/SKILL.md` says
  `python3 ~/.claude/skills/kg/scripts/kg.py load …`, and the `p9` wrapper on PATH
  is `exec python3 "$HOME/.claude/skills/p9/scripts/p9.py"`. That would prevent the
  state write by *breaking the skill*, and score as a trigger failure. So the jail
  links `~/.claude/skills` to the copy materialised in the case workspace. Note
  what that also fixes: **without** the jail those commands resolved to the
  operator's real installed skill — a different artifact from the one under test —
  so the pre-jail behaviour did not merely leak, it graded the wrong copy.
- **Wrapper CLIs.** `shutil.which("claude")` can resolve to a wrapper that appends
  `--settings`, which `--setting-sources project` does *not* gate. The one on this
  machine gates its injection on `SUPERCONDUCTOR_*`, which deny-by-default drops, so
  the jail closes it — as a consequence of the allowlist rather than by intent, which
  is why `test_wrapper_activation_vars_are_dropped` pins it.

`--fail-on-real-state-change` promotes the post-run watch over `~/.config/broomva`
from a warning to a failure. It is *off* by default, and that is a calibration, not
timidity: those stores are shared, so a p9 watcher in another terminal is
indistinguishable from a leak by mtime alone, and a check that fails for unrelated
reasons gets muted. `--verify-jail` is the deterministic guarantee; the watch is
there because the ticket's other complaint was that a leak was *invisible*.

### The description hash must be the loader's description

That binding is only as good as the parser behind it. **PyYAML is the reference
implementation** and is used whenever it imports; a hand parser is the fallback for
environments without it, and a differential test holds the two byte-identical
across every `SKILL.md` in the repo. PyYAML is in `requirements-dev.txt` so CI runs
that test rather than skipping it.

Why both, rather than only the hand parser: the earlier one disagreed with YAML on
27 of 89 real files. 26 were quote retention; `skills/design/arcan-glass/SKILL.md`
diverged by 159 characters because its description contains `(AI Blue #0066FF)` and
YAML treats ` #` in a plain scalar as a comment. A parser that disagrees with the
real loader is not a cosmetic problem here — it both *misses* a real description
change and *manufactures* a phantom one (edit the comment, every fixture goes
stale). Why not PyYAML alone: the hash would then depend on whether an optional
dependency happened to be installed, so a fixture recorded on one machine would
read as stale on another. Agreement between the two paths is what makes the hash
environment-independent, and it is asserted, not assumed.

## Is the skill still earning its rent? (`--ablate`)

Capability skills are temporary — every model release absorbs a little more of what
they encode, and an absorbed skill is pure cost. `--ablate` runs the same prompt set
twice, with the skill installed and without, and reports the difference.

```bash
python3 scripts/skill_evals/runner.py --skill checkit --trials 10 --ablate --dry-run
python3 scripts/skill_evals/runner.py --skill checkit --trials 10 --ablate
```

`--ablate` is **live-only**. It refuses `--replay` (both arms would replay the same
fixtures, so the baseline is 100% `LEAKED` by construction) and `--record` (fixtures
are stored per *case*, not per *arm*, so the absent arm would overwrite the present
arm's transcripts and destroy the evidence just paid for). Both are refusals rather
than caveats because each mode silently produced a wrong artifact.

Negatives are not re-run in the baseline: an uninstalled skill cannot over-trigger,
so the case asserts nothing and spending on it is just spending. They score
`NOT_COMPARABLE`.

**The grading has to change, not just the workspace.** In the absent arm
`should_trigger` is meaningless. Scoring it with the present arm's rules gives the
baseline a guaranteed zero — every skill looks maximally load-bearing and the sweep
recommends nothing. So the baseline is graded on **outcome checks only**, and
trigger-dependent checks are recorded with `passed: null`. Counting them *passed*
inflates the baseline (lift too low → retire something load-bearing); counting them
*failed* zeroes it (lift too high → the original vacuity).

The exclusion applies to **both arms**, which is what makes the numerator
arm-*symmetric* and is not a detail. Excluding it only where the absent arm flagged it
grades the present arm on a strict superset — fire *and* satisfy the outcome checks,
versus satisfy the outcome checks — so every trial where the skill did not fire
becomes a lift penalty. On `kg`'s committed prompt set at default flags, a skill
firing on 81% of trials (clearing the harness's own 0.80 threshold) scored lift
**−0.19** and verdict **`retire-candidate`**. Trigger behaviour is not lost; it is
reported on its own axis as `trigger_rate` and `end_to_end_lift`.

**`expect_visible` is now a bidirectional contract.** It used to be a skip switch, so
a skill that leaked into the baseline scored as an ordinary result and the lift came
out at zero — indistinguishable from absorption. A leaked baseline trial is `LEAKED`,
which is in `NON_PASS_ERRORS` and so drops out of `graded_trials` for free.

| verdict | meaning |
|---|---|
| `load-bearing` | the 95% interval for the lift is entirely above zero |
| `retire-candidate` | the whole interval sits below the margin (default 0.10) |
| `indeterminate` | the interval straddles the margin — more trials needed |
| `inconclusive-underpowered` | fewer than 10 graded positive trials in an arm |
| `inconclusive-no-trigger` | present-arm trigger rate < 0.5 — cannot separate absorption from a trigger failure |
| `inconclusive-weak-checks` | the graded checks are CONSTANT — none failed in either arm, or none passed. Lift is 0.0 by construction either way, so the checks cannot tell the arms apart. (A check that *raises* is recorded as failed, so one buggy predicate would otherwise read as 'retire everything'.) |
| `inconclusive-name-collision` | the name is a CLI built-in, so there is no absent arm |

Every inconclusive verdict serialises `"skill_lift": null` — **never `0.0`**, because a
defaulted zero reads as perfect absorption, the most dangerous vacuity available here.

Three limits the harness cannot remove, each of which changes what a verdict is worth:

- **The baseline is not a bare model.** The absent arm still has the CLI's built-in
  skills, so lift is marginal value over *those*.
- **Tool-bearing skills are not comparable**, and the mechanic pushes the *opposite*
  way from what you would guess. For `p9`, `kg`, `dogfood` the absent arm removes
  executable scripts, so you might expect lift near 1.0 — but only if the prompt set's
  `expected_checks` can actually detect the difference. `kg`'s committed set asserts a
  non-empty answer and no permission denials, both of which an uninstalled baseline
  satisfies, so its measured lift is exactly 0.0 and the verdict is
  `inconclusive-weak-checks`. The check suite, not the skill, is the binding
  constraint there.
- **Absorption is a non-inferiority claim** and cannot be proven by a point estimate
  of zero. At the default 3 trials the interval is roughly ±0.28 wide, so most honest
  verdicts are `indeterminate`; a real retirement decision needs ~30 positive trials
  per arm (≈60 live CLI runs per skill).

`--ablate` is **report-only** and can never soften the existing gate. An unusable
baseline gets its own exit code (`4`), because nothing is wrong with the skill — the
*measurement* is void, and reporting that as a threshold failure would send a reader
to fix the wrong thing. `--fail-on-retire-candidate` is opt-in.
## Does the description even reach the model? (`listing.py`)

The arc's premise was that the description we author is the description the model
sees. **It usually is not.** Claude Code injects the roster as a `skill_listing`
attachment whose rendered `content` is capped; when the roster overflows, skills
render as a bare `- name` line with no trigger text at all.

```bash
python3 scripts/skill_evals/listing.py            # classify the latest real listing
python3 scripts/skill_evals/listing.py --budget   # mass vs cap, heaviest skills
python3 scripts/skill_evals/listing.py --calibrate # re-derive the caps from disk
```

Measured here (1,199 listings across 1,039 session transcripts): largest listing
ever delivered **39,013 chars**; the trigger surface of the 124 roster skills found
on disk is **94,800 chars**, a 2.4× overshoot. In the session that produced the
module: 146 skills → **34 full, 2 truncated, 110 BARE (75.3%)**.

The budget is scoped to the **roster** — the names the harness actually lists. An
earlier version counted every `SKILL.md` it could reach and reported 369 skills
against a 146-name roster, 60% of that mass from skills that have never been listed,
while *missing* 84 that had: `Path.rglob` does not follow symlinks, and a skill
install root is almost entirely symlinks (125 of 129 entries here — rglob found 3
`SKILL.md` files, `iterdir` finds 128). The tell was a single run reporting `kg` and
`dogfood` TRUNCATED from the transcript while `over_per_skill_cap` came back empty.

The bstack primitives are among the worst hit — `role-x` (P17), `persist` (P12),
`cross-review` (P20), `orchestration` (P19) and `bookkeeping` (P6) all arrived
**BARE**; `kg` and `dogfood` arrived truncated mid-sentence. Which skills win is not
stable between sessions, so this is not a fixed set to design around.

Two consequences worth stating plainly:

- **A trigger eval on a bare skill measures nothing about its description**, because
  the model never received one. Coverage numbers should be read against delivery.
- **Trimming descriptions cannot fix it.** The affordable mean at this skill count is
  ~315 chars, and the fifteen heaviest are a small fraction of the mass. The lever is
  the model-invocable skill **count** (`disable-model-invocation` on the long tail),
  which is a governance decision, not this module's job.

`BUDGET_CHARS` and `PER_SKILL_CHARS` are **observations, not assertions**, and
`--calibrate` re-derives them and exits non-zero when one is stale. That is not
decoration: its first real run rejected this module's own initial `BUDGET_CHARS`
(30,000, from a smaller sample) against an observed 39,013.

Deliberately **not** a CI gate. Its input is one machine's `~/.claude/projects`,
which does not exist on a runner — a CI check over it would be green by
construction, the exact vacuity this harness exists to hunt. It belongs in
`bstack doctor` as an advisory section, next to P7 freshness.

## What replay does and does not guarantee

Being precise about this is load-bearing: an earlier version of this file claimed
"replay cannot fake green", and an adversarial review disproved it by hand-writing
45 transcripts and stubbing the description to `xxxx` — 45/45, exit 0.

**Guaranteed.** Replay exits non-zero when fixtures are missing, empty,
unparseable, fewer than the requested trial count, recorded against a different
prompt, or recorded against a different `SKILL.md` / description than the one on
disk. A fixture with no meta sidecar is refused outright, and one written by a
non-`live-record` path is refused unless `--allow-synthetic-fixtures` is passed.
The mode, the artifact path and both hashes print on every invocation.

**Not guaranteed — do not read the numbers as if it were.** Replay does *not*
authenticate a transcript. Anyone with write access to the repo can hand-write a
`.jsonl` and a matching meta sidecar, including a correct skill hash and
`"provenance": "live-record"`. The hashes prove a fixture is **current**, not that
a model produced it. There is no cryptographic answer to this available to a
harness whose fixtures live in the same repo as the harness; what there is instead
is (a) staleness detection, (b) a declared provenance field, and (c) the fact that
the live path is the default and replay must be asked for by name.

Two reported numbers are read straight out of the fixture and are therefore only
as trustworthy as it is: `cost` and `duration`. In replay they print with an
explicit "as recorded in fixtures — not re-incurred" tag. They are context, never
evidence.

## Committed fixtures

`tests/skill_evals/fixtures/harness-selftest/` — 4 cases x 3 trials, replayed and
graded by CI on every PR, plus a mutation-proof step that rewrites the fixture
skill's description and asserts the run goes RED.

These transcripts are **synthetic** (hand-authored by `generate.py`, no model
involved) and every sidecar says so. They are evidence about the *harness*. They
are not evidence about any skill's real trigger behaviour — only `--record`
against the live CLI produces that, and **checkit has no committed fixtures yet**.
Regenerate after editing the fixture skill or its prompt set:

```bash
python3 tests/skill_evals/fixtures/harness-selftest/generate.py
```

## Seams left open

* **LLM judge** — `make_judge_check` / `JUDGE_SCHEMA` in `checks.py`. Deliberately
  raises rather than stubbing a pass. Keep it a minority of any prompt set: if a
  skill's verdict hinges on judge calls, the outcome wasn't specified sharply enough.

## Pinning

Stream parsing is verified against agent CLI **2.1.220**. `--output-format json`
carries no tool data at all, so `stream-json --verbose` is mandatory; a run whose
`init` event lacks a `skills` array is scored `ERROR`, never a silent non-trigger.

Fixtures record the `model` and `cli_version` they were produced on. Drift from the
current expectation prints a `fixture drift` warning, and `--strict-fixtures` makes
it fatal. (Prompt-hash and skill-hash mismatches are *always* fatal — no flag.)

`--allow-errors` forgives `ERROR` trials for diagnostics. It does **not** forgive
`INVISIBLE`: a run where the skill was never loaded is vacuous by construction, and
no flag may turn it green. It also cannot forgive *all* the trials — see the
zero-graded-trials invariant above.

Fixtures recorded against a **different prompt** than the set now carries get their
own guard line and a `meta.stale_prompt_fixtures` entry in the JSON report; their
remedy is its own ("the prompt set moved, re-record those cases"), which is why
they are reported separately from generic integrity failures rather than only
counted among them.

## Prompt-set data is pinned too

Every case in a shipped prompt set must carry at least one `expected_check`, and
every negative must assert `final_answer_non_empty`. Without that, a negative
asserts only "the skill stayed quiet" — which a run that says nothing at all also
satisfies — and reverting the assertions to `expected_checks: []` would leave CI
green. `tests/skill_evals/test_runner.py` asserts both.
