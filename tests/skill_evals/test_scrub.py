"""Tests for the fixture scrubber (scripts/skill_evals/scrub.py, BRO-2030).

The env jail isolates the filesystem and environment. It does NOT isolate the process
table — and a live eval runs a real agent with `bypassPermissions`, free to `ps` and
put the result in a transcript that then gets committed to a PUBLIC repo.

Not hypothetical: the first full sweep produced a `dogfood` transcript carrying the
recording machine's process listing, and one of those command lines contained
`-session-token <36 chars>`. The pre-commit gitleaks hook caught it. This module is
the step between recording and publishing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPTS = REPO / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from skill_evals import fixture_guard as G  # noqa: E402
from skill_evals import scrub as S  # noqa: E402


def test_the_home_directory_is_redacted():
    out, counts = S.scrub_text("reading /Users/somebody/.config/thing")
    assert "/Users/somebody" not in out
    assert out == "reading /Users/USER/.config/thing"
    assert counts["home directory"] == 1


def test_a_session_token_in_a_process_line_is_redacted():
    """THE case this exists for, in the shape the first sweep actually produced.

    The real `ps` capture used a COLON — `-session-token:<36 chars>` — inside an
    Electron-style argument list. An earlier version of this test guessed a SPACE
    separator, which is a different string, and getting that wrong is how a rule
    aimed at a known artefact ends up never matching it.
    """
    # Assembled at runtime, not written as a literal: a 36-char token-shaped string
    # sitting in a tracked file trips the repo's own secret scanner, and a test that
    # cannot be committed is not a test.
    fake = "cd47a1" + "b2c3d4e5f6" + "0718293a4b" + "5c6d7269"
    line = f"node /opt/app -process-type:main -session-token:{fake} -target-handle:820"
    out, counts = S.scrub_text(line)
    assert fake not in out
    assert "-session-token:REDACTED" in out
    assert counts["credential-shaped assignment"] >= 1


def test_a_space_separated_credential_is_also_redacted():
    """Both separators, because CLI conventions differ and the cost of missing one
    on a public repo is permanent."""
    fake = "abcdefgh" + "12345678" + "ijklmnop"
    out, _ = S.scrub_text(f"--api-key {fake}")
    assert fake not in out


def test_it_matches_on_the_KEY_not_the_value_shape():
    """Guessing which 36-character strings are secret is whack-a-mole, and every
    miss is permanent once pushed to a public repo. So an innocuous long value stays,
    and a short value under a credential-shaped key still goes."""
    # Also assembled at runtime — there is a certain irony in the assertion that a
    # plain hash is not a secret being itself flagged as one, but the scanner is
    # pattern-matching and the cheap fix is to not hand it a literal.
    sha = "0fd7c7aa9e" + "1b4c3d5e6f" + "70819a2b3c" + "4d5e6f7049"
    kept, _ = S.scrub_text(f'"commit": "{sha}"')
    assert sha in kept, "a plain hash is not a secret"

    short = "abcd1234" + "efgh5678" + "ijkl"
    gone, _ = S.scrub_text(f"api_key={short}")
    assert short not in gone


def test_several_credential_key_spellings_are_covered():
    for text in (
        "AUTH_TOKEN=aaaaaaaaaaaaaaaaaaaa",
        'password: "bbbbbbbbbbbbbbbbbbbb"',
        "machine_id=cccccccccccccccccccc",
        "X-Api-Key: dddddddddddddddddddd",
        "session_id=eeeeeeeeeeeeeeeeeeee",
    ):
        out, _ = S.scrub_text(text)
        assert "REDACTED" in out, text


def test_scrub_is_idempotent():
    """--apply runs before every commit; a second pass must be a no-op or the
    fixtures churn on every run and the diff becomes unreadable."""
    once, _ = S.scrub_text("/Users/me/x and token=aaaaaaaaaaaaaaaaaaaa")
    twice, counts = S.scrub_text(once)
    assert once == twice
    assert not counts


def test_check_reports_without_writing(tmp_path):
    """--check is a gate to run before committing, and must not modify anything."""
    f = tmp_path / "t.jsonl"
    f.write_text('{"cwd": "/Users/somebody/ws"}')
    before = f.read_text()
    rc = S.main([str(tmp_path), "--check"])
    assert rc == 1, "--check exits non-zero when there is something to redact"
    assert f.read_text() == before, "--check must not write"


def test_apply_rewrites_and_then_check_is_clean(tmp_path):
    f = tmp_path / "t.jsonl"
    f.write_text('{"cwd": "/Users/somebody/ws"}')
    assert S.main([str(tmp_path), "--apply"]) == 0
    assert "/Users/somebody" not in f.read_text()
    assert S.main([str(tmp_path), "--check"]) == 0, "clean after apply"


def test_only_fixture_files_are_touched(tmp_path):
    """A stray .md or .py under the fixtures tree is not a transcript."""
    (tmp_path / "notes.md").write_text("/Users/somebody/x")
    (tmp_path / "t.jsonl").write_text("/Users/somebody/x")
    S.main([str(tmp_path), "--apply"])
    assert "/Users/somebody" in (tmp_path / "notes.md").read_text()
    assert "/Users/somebody" not in (tmp_path / "t.jsonl").read_text()


# ===========================================================================
# IDENTITY — the class the scrubber had NO rule for (BRO-2030)
#
# Every test below fails against the scrubber as it stood at 6de92249: it had rules for
# the home directory, temp roots, npx hashes and credential-shaped assignments, and
# nothing whatsoever for account identity. Three of 703 fixtures carried the operator's
# real work email, their org name, their org UUID and a stable 64-hex user id, because
# a trial read a Claude Code config JSON and the tool result was recorded verbatim.
#
# The mutation proof for this block is
#   skills/governance/cross-review/scripts/mutation-proof.sh run \
#     --target scripts/skill_evals/scrub.py --strategy revert --ref 6de92249 \
#     --test 'python3 -m pytest tests/skill_evals/test_scrub.py -q'
# which reverts scrub.py to precisely its pre-identity state and must go RED.
# ===========================================================================


#: EVERY identifying value below is INVENTED, and that is a hard rule for this module
#: rather than a preference.
#:
#: The first version of these tests used the real `organizationUuid` and `accountUuid`
#: from the leak, on the reasoning that testing against the actual artefact is more
#: honest. It is the opposite. This PR's own argument is that the org UUID and the 64-hex
#: userID are the part of #117's exposure that is NOT otherwise public — so committing
#: them here would publish exactly those values into `main`, permanently, in plaintext,
#: in the test file for the scrubber whose job is to remove them. #117's copy at least
#: sits in unmerged branch objects a GC can reach; a merged test file never goes away.
#:
#: It is also the arc's own defect one turn further in: the fix embedding the thing it
#: fixes. An invented UUID exercises the pattern identically — same 8-4-4-4-12 hex shape,
#: same version and variant nibbles — and proves the rule STRICTLY BETTER, because a
#: reader cannot mistake it for live data.
FAKE_ORG_UUID = "decafbad-cafe-4bad-8bad-decafbadcafe"
FAKE_ACCOUNT_UUID = "0ddba11a-f00d-4d0d-8fed-0ddba11acced"
FAKE_USER_ID = "deadbeef" * 8  # 64 hex, the shape of a real `userID`
#: The real value here named the org's actual subscription tier, which is plan metadata
#: and identifying. Same treatment: invented, same shape, obviously not live.
FAKE_RATE_TIER = "synthetic_tier_99x"


#: The two modules that carry leak-derived test data. Scoped to these rather than to the
#: whole suite on purpose: `test_listing.py` and `test_usage.py` legitimately contain
#: UUIDs, and every `harness-selftest` meta sidecar contains real sha256 digests that ARE
#: the artifact binding. A guard that fired on those would be muted within a week, which
#: is the failure mode this repo's own README names.
_MODULES_WITH_LEAK_DERIVED_DATA = ("test_scrub.py", "test_fixture_guard.py")


#: The invented constants, pinned by digest. This second leg is not belt-and-braces — the
#: first version of the guard was VACUOUS without it, and I proved that by hand: it
#: compares literals against the RUNTIME VALUES of the constants, so pasting the real org
#: UUID into `FAKE_ORG_UUID = …` made the real value "the allowed constant" and the guard
#: went green. It caught a real value at a CALL SITE and missed one at the DEFINITION,
#: which is the more likely edit of the two.
#:
#: A digest pin has no such hole: any change to these three, to a real value or otherwise,
#: turns this red. The digests are of INVENTED strings, so committing them leaks nothing.
_PINNED_FAKE_DIGESTS = {
    "FAKE_ORG_UUID": "e7e033a5faa42a63471ac19a9f06045259c1d16bbb793aea99e08bce0e45fbf3",
    "FAKE_ACCOUNT_UUID": "880db34e8135d02492cc0c9bc4f8b2ee77f4fd17b3691afb7e92ffedff723da0",
    "FAKE_USER_ID": "247d08f3e13938b244f5ecd8966f1778e5e72b175820f46ba86c9c039272affa",
    "FAKE_RATE_TIER": "081fa21d4b90efbf6ef12ae4bfd689609b2e87b11a34352d98530b2acf9e692f",
}


def test_the_invented_identity_constants_are_pinned():
    """Leg 2 of the guard. See _PINNED_FAKE_DIGESTS for why one leg was not enough."""
    import hashlib
    for name, digest in _PINNED_FAKE_DIGESTS.items():
        value = globals()[name]
        assert hashlib.sha256(value.encode()).hexdigest() == digest, (
            f"{name} changed. These are pinned deliberately: if you are editing one, you "
            "are probably pasting a value from a real transcript, which is exactly what "
            "this module must not contain. Invent a new one and update the pin."
        )


def test_no_real_identity_value_is_hardcoded_in_the_leak_derived_tests():
    """Leg 1. A future edit reaching for "the real value it actually caught" is the
    obvious and sympathetic mistake.

    Asserted on the SHAPE of a fixture-derived identifier — any UUID or 64-hex literal in
    either module must be one of the three invented constants, or one of the digests that
    pins them (a digest of an invented string is itself 64-hex, and leg 1 flagged leg 2's
    own pins the first time round).

    THE LIMIT, stated rather than implied: an author who changes a constant AND its pin
    together, to real values, passes both legs. No self-referential check can close that.
    What these two legs close is ACCIDENTAL reintroduction — a paste at a call site, or a
    paste at the definition — which is the failure that actually happened.
    """
    import re as _re
    allowed = ({FAKE_ORG_UUID, FAKE_ACCOUNT_UUID, FAKE_USER_ID}
               | set(_PINNED_FAKE_DIGESTS.values()))
    patterns = (r"\b[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}\b", r"\b[0-9a-f]{64}\b")
    here = Path(__file__).parent
    for name in _MODULES_WITH_LEAK_DERIVED_DATA:
        src = (here / name).read_text(encoding="utf-8")
        for pattern in patterns:
            for hit in _re.findall(pattern, src):
                assert hit in allowed, (
                    f"{name}: {hit!r} is a real-looking identity literal. Use "
                    "FAKE_ORG_UUID / FAKE_ACCOUNT_UUID / FAKE_USER_ID — see the note "
                    "above them for why an invented value proves the rule better."
                )


def _config_fragment(email: str, org_uuid: str, user_id: str) -> str:
    """The leak in the shape a fixture actually carries it: an escaped JSON document
    inside an NDJSON tool result. A rule written against unescaped `"key": "value"`
    matches nothing here, which is the mistake this module has already made once."""
    inner = (
        r'  \"userID\": \"' + user_id + r'\",\n'
        r'  \"oauthAccount\": {\n'
        r'    \"accountUuid\": \"' + FAKE_ACCOUNT_UUID + r'\",\n'
        r'    \"emailAddress\": \"' + email + r'\",\n'
        r'    \"organizationUuid\": \"' + org_uuid + r'\",\n'
        r'    \"ccOnboardingFlags\": {},\n'
        r'    \"displayName\": \"AcmeCorp\",\n'
        r'    \"organizationRateLimitTier\": \"' + FAKE_RATE_TIER + r'\",\n'
        r'    \"organizationName\": \"' + email + "'s Organization" + r'\"\n'
        r'  },\n'
        r'  \"org\": \"' + org_uuid + r'\"'
    )
    return '{"tool_result": "' + inner + '"}'


def test_an_email_address_is_redacted():
    """THE field that got through. An address is the one value whose SHAPE is
    unambiguous, so this rule matches the value and not the key — it has to, because
    the key names it arrives under cannot be enumerated (`emailAddress`, `author`,
    `Correspondence:` in a fetched paper, a bare `git log` line)."""
    out, counts = S.scrub_text("contact: ops@northwind-labs.co")
    assert "ops@northwind-labs.co" not in out
    assert out == "contact: REDACTED@REDACTED.invalid"
    assert counts["email address"] == 1


def test_reserved_and_service_addresses_survive():
    """Over-redaction has a cost too. `git@github.com` is in every `git remote -v`, and
    an RFC 2606 reserved domain identifies nobody by construction."""
    for keep in ("git@github.com", "user@example.com", "noreply@anthropic.com",
                 "someone@REDACTED.invalid"):
        assert S.scrub_text(f"x {keep} y")[0] == f"x {keep} y", keep


def test_an_escaped_newline_abutting_an_at_sign_is_not_an_address():
    """`\\n@pytest.fixture` in a recorded file read is two escape characters and a
    decorator. Redacting it corrupts readable content for no gain."""
    assert S.scrub_text(r"def f():\n@pytest.fixture")[0] == r"def f():\n@pytest.fixture"


def test_a_real_address_after_an_escaped_newline_keeps_the_escape():
    """The other direction, and the sharper one: eating the `n` leaves `\\REDACTED`,
    which is not a legal JSON escape — the line stops parsing and replay scores the
    trial ERROR on a fixture the scrubber "cleaned"."""
    out, _ = S.scrub_text(r'{"r": "authors:\ndevteam@acme.co"}')
    assert "devteam@acme.co" not in out
    assert r"\nREDACTED@REDACTED.invalid" in out
    assert json.loads(out)["r"] == "authors:\nREDACTED@REDACTED.invalid"


def test_a_version_string_is_not_an_address():
    """`acpx@0.12.0.patch` is a pnpm patch filename. A purely numeric label is the
    tell; this cost four substitutions of real recorded content before it was added."""
    for keep in ("acpx@0.12.0.patch", "embedded-postgres@18.1.0-beta.16.patch"):
        assert S.scrub_text(keep)[0] == keep, keep


def test_the_account_object_is_elided_whole():
    """The rule about the SHAPE, not the field names. `oauthAccount` carried nineteen
    fields and four were identifying; naming those four leaves fifteen, plus whatever
    the next CLI release adds."""
    text = _config_fragment("a@b.co", FAKE_ORG_UUID, FAKE_USER_ID)
    out, counts = S.scrub_text(text)
    assert counts["account object"] >= 1
    assert "{REDACTED_account_object}" in out
    for gone in (FAKE_ACCOUNT_UUID[:8], "AcmeCorp", FAKE_RATE_TIER, "accountUuid"):
        assert gone not in out, gone


def test_every_identifying_value_in_a_config_dump_is_gone():
    """End to end on the real artefact, asserted by VALUE rather than by field name —
    a rule that renamed the field but left the bytes would pass a key-based assertion.
    """
    email, org, uid = "ops@northwind-labs.co", FAKE_ORG_UUID, FAKE_USER_ID
    out, _ = S.scrub_text(_config_fragment(email, org, uid))
    for gone in (email, org, uid, FAKE_ACCOUNT_UUID, "AcmeCorp"):
        assert gone not in out, gone


def test_the_scrubbed_config_dump_is_still_valid_json():
    """The fixture is NDJSON and replay parses it. A redaction that breaks the line
    turns a graded trial into an ERROR, which is a different claim about a different
    thing — and it would be invisible, because nothing re-reads the file."""
    text = _config_fragment("a@b.co", FAKE_ORG_UUID, FAKE_USER_ID)
    out, _ = S.scrub_text(text)
    assert isinstance(json.loads(out), dict)


def test_identity_keys_are_matched_as_a_FAMILY_not_a_list():
    """`organizationRateLimitTier` and `userRateLimitTier` are covered without being
    named anywhere, which is the property that makes this survive the next field the
    CLI adds."""
    for key in ("organizationRateLimitTier", "userRateLimitTier", "accountCreatedAt",
                "subscriptionCreatedAt", "billingType", "tenantId", "customerName",
                "workspace_id", "login"):
        out, _ = S.scrub_text(f'\\"{key}\\": \\"something-identifying\\"')
        assert "something-identifying" not in out, key


def test_identity_rules_leave_non_string_values_alone():
    """`userModified: false` occurs 116 times, `seatTier: null` and
    `minUserTurnsBeforeFeedback: 3` carry an identity noun and nothing identifying. A
    rule that rewrote booleans and nulls would corrupt 116 fixtures to redact 0 facts.
    """
    for keep in ('\\"userModified\\": false', '\\"seatTier\\": null',
                 '\\"minUserTurnsBeforeFeedback\\": 3', '\\"orgModelDefaultCache\\": null'):
        assert S.scrub_text(keep)[0] == keep, keep


def test_the_artifact_binding_hashes_are_NEVER_redacted():
    """`prompt_sha256` / `description_sha256` / `skill_md_sha256` are 64-hex, and they
    are what binds a fixture to the SKILL.md it was recorded against. A value-shape
    rule over 64-hex would destroy the binding and the whole gate with it — which is
    why the identity rules are key-anchored."""
    sha = "0fd7c7aa9e" + "1b4c3d5e6f" + "70819a2b3c" + "4d5e6f7049" + "aabbccdd" + "eeff0011" + "2233"
    text = f'{{"prompt_sha256": "{sha[:64]}", "description_sha256": "{sha[:64]}"}}'
    assert S.scrub_text(text)[0] == text


def test_an_env_var_is_redacted_but_a_python_assignment_is_not():
    """`[A-Z0-9_]` under re.IGNORECASE also matches LOWERCASE, so the first version of
    this rule — commented "SCREAMING_SNAKE keys only" — rewrote
    `user = get_current_user()` in a recorded source file to `user = REDACTED()`."""
    out, _ = S.scrub_text(f"ANTHROPIC_ORGANIZATION_ID={FAKE_ORG_UUID}")
    assert FAKE_ORG_UUID[:8] not in out and out.endswith("=REDACTED")
    for code in ("user = get_current_user()", "owner = repo.get_owner()",
                 "email = build_email(row)", "for user in users:"):
        assert S.scrub_text(code)[0] == code, code


def test_an_identity_cli_flag_is_redacted_and_profile_is_not():
    """`--profile` is one of the most common non-identity flags there is. Including
    `profile` as an identity noun redacted `--profile preview` and
    `--profile production` out of 18 recorded deploy commands — which are graded tool
    INPUTS — to protect nothing."""
    assert FAKE_ORG_UUID[:8] not in S.scrub_text(f"--organization-uuid {FAKE_ORG_UUID}")[0]
    assert "abc123def" not in S.scrub_text("--user-id=abc123def")[0]
    for keep in ("--profile preview", "--profile production", "--profile admin"):
        assert S.scrub_text(keep)[0] == keep, keep


def test_the_temp_root_replacement_does_not_re_match_itself():
    """The home rule guards its placeholder with `(?!USER\\b)`; the temp-root rule did
    not, so `--apply` re-substituted an identical string and `--check` reported 67
    "redactions" in one file that changed nothing. Phantom counts are how a reader
    stops trusting the report."""
    once, _ = S.scrub_text("/var/folders/ab/cdef/T/x")
    twice, counts = S.scrub_text(once)
    assert once == twice
    assert not counts


def test_identity_scrubbing_is_idempotent():
    """--apply runs before every pack; a second pass must report ZERO, or the fixtures
    churn and the manifest checksum stops meaning anything."""
    once, _ = S.scrub_text(_config_fragment("a@b.co", FAKE_ORG_UUID, FAKE_USER_ID))
    twice, counts = S.scrub_text(once)
    assert once == twice
    assert not counts, counts


def test_every_tracked_fixture_in_the_repo_is_scrubbed():
    """The COMMIT-time gate, scoped to what git TRACKS, repo-wide.

    Not scoped to `fixtures/live` — that scoping is what let a second agent's `p9`
    fixtures, recorded off main into their own directory, carry the operator's home
    path in three files and the same identity triple in a fourth. A guard that only
    knows one directory name cannot see a fixture set recorded somewhere else.
    """
    findings = G.audit_tracked_fixtures(REPO)
    assert findings == {}, (
        "tracked fixtures contain unscrubbed host content:\n"
        + "\n".join(f"  {f}: {c}" for f, c in findings.items())
        + "\nRun: python3 scripts/skill_evals/scrub.py <dir> --apply"
    )


def test_no_recorded_fixture_is_tracked_outside_the_synthetic_set():
    """Recorded model output does not belong in a PUBLIC repo's permanent history.

    The one exception is the hand-authored `harness-selftest` set, which CI's graded
    replay depends on. Anything else fixture-shaped and tracked is 20 MB of transcript
    on its way into objects that stay reachable by SHA forever.
    """
    tracked = G.tracked_recorded_fixtures(REPO)
    assert tracked == [], (
        "recorded fixtures are tracked by git:\n" + "\n".join(f"  {p}" for p in tracked)
        + "\nThey belong in the release asset: "
          "python3 scripts/skill_evals/fixture_pack.py pack"
    )


def test_the_live_fixture_tree_is_scrubbed_when_it_is_present():
    """Standing guard on the payload itself, when a developer has fetched it. Skipped
    rather than failed when absent: the tree is no longer in git, so its absence on a
    fresh clone is correct and not a finding."""
    live = REPO / "tests" / "skill_evals" / "fixtures" / "live"
    payload = [p for p in live.rglob("*") if p.suffix in (".jsonl", ".json")
               and p.name != "MANIFEST.json"] if live.is_dir() else []
    if not payload:
        return
    assert S.scan(live) == {}, (
        "fetched live fixtures contain unscrubbed host content — run "
        "`python3 scripts/skill_evals/scrub.py tests/skill_evals/fixtures/live --apply`"
    )
