"""Nothing secret-shaped reaches the store.

Every string in an event passes the redaction pass before it is written:
tokens, Bearer headers and key=value secrets are replaced, and paths under
crm/ or with a secret-shaped segment are dropped. Checked on the function and
end to end through the Stop hook, against the bytes on disk.
"""
from __future__ import annotations

import pytest

import ctx
from conftest import World

#: Synthetic, never-issued values. Each is assembled from pieces so no
#: secret-shaped literal sits in the source: push protection (rightly) refuses
#: one, and a fixture that trips a scanner trains people to click "allow".
_J = "".join
SECRETS = {
    "github classic": _J(["gh", "p_", "A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8"]),
    "github fine-grained": _J(["github", "_pat_", "11ABCDEFG0123456789_", "abcdefghijklmnopqrstuvwxyz0123456789ABCDEFGHIJ"]),
    "anthropic": _J(["sk-", "ant-api03-", "x" * 40]),
    "openai": _J(["sk-", "proj-", "Ab1" * 12]),
    "stripe": _J(["sk_", "live_", "51HxYzAbCdEfGhIjKl"]),
    "slack": _J(["xo", "xb-", "1234567890-0987654321-", "AbCdEfGhIjKlMnOp"]),
    "aws": _J(["AK", "IA", "Z" * 16]),
    "google": _J(["AI", "za", "SyA-1234567890", "abcdefghijklmnopqrstu"]),
    "jwt": _J(["ey", "JhbGciOiJIUzI1NiJ9", ".", "ey", "JzdWIiOiIxMjM0NTY3ODkwIn0", ".", "dozjgNryP4J3jVmNHl0w5N_XgL0n3I9PlFUP0THsR8U"]),
    "npm": _J(["np", "m_", "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8"]),
    "gitlab": _J(["gl", "pat-", "Ab12Cd34Ef56Gh78Ij90"]),
    "linear": _J(["lin", "_api_", "Q" * 40]),
    "linear oauth": _J(["lin", "_oauth_", "a1B2" * 8]),
    "google oauth": _J(["ya", "29.", "a0AfH6SMBx", "Q" * 30]),
    "slack app": _J(["xa", "pp-", "1-A0123456789-", "1234567890123-", "abcdef0123456789"]),
    "sendgrid": _J(["S", "G.", "abcdefghijklmnopqrstuv", ".", "ABCDEFGHIJKLMNOPQRSTUVWXYZ012345678"]),
    "telegram": _J(["123456789", ":AA", "Hdqwertyuiopasdfghjklzxcvbnm12345"]),
    "supabase": _J(["sb", "p_", "0123456789abcdef0123456789abcdef01234567"]),
    "groq": _J(["gs", "k_", "Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv"]),
    "unknown vendor": _J(["Zq9Xw8", "Ve7Ru6", "Tp5So4", "Rn3Qm2", "Pl1Ok0", "Nj9Mi8"]),
}
#: (text as written, the secret value that must not survive)
SHAPED = [
    (_J(["Author", "ization: Bea", "rer ee18c0ffee0000000000000000000000"]), "ee18c0ffee0000000000000000000000"),
    (_J(["curl -H 'Author", "ization: token s3cr3tv4lue'"]), "s3cr3tv4lue"),
    ("using bearer abc.def-ghi_jkl.0123", "abc.def-ghi_jkl.0123"),
    ("PASEO_PASSWORD=hunter2 paseo ls", "hunter2"),
    ("export OPENAI_API_KEY=abc123xyz", "abc123xyz"),
    ("client_secret: 'q9w8e7r6'", "q9w8e7r6"),
    ('{"token": "tok-live-778899"}', "tok-live-778899"),
    ("STRIPE_KEY=rk_other_value_1", "rk_other_value_1"),
    ("mcp url http://127.0.0.1:6767/mcp?access_token=deadbeefcafe&x=1", "deadbeefcafe"),
    (_J(["clone https://", "carlos:", "ghs-pass-123", "@github.com/o/r"]), "ghs-pass-123"),
    (_J(["-----BEGIN OPENSSH ", "PRIVATE KEY-----\n", "b3BlbnNzaC1rZXktdjE=", "\n-----END OPENSSH ", "PRIVATE KEY-----"]),
     "b3BlbnNzaC1rZXktdjE="),
    ("Cookie: session=abcdef0123456789", "abcdef0123456789"),
    ('{"accessToken": "abcDEF123456"}', "abcDEF123456"),
    ("authToken=zzzz9999yyyy", "zzzz9999yyyy"),
    ("refreshToken: 'r3fr3sh-t0k3n'", "r3fr3sh-t0k3n"),
    ("gh auth login --token=s3cretvalue42", "s3cretvalue42"),
    ("psql --password s3cretpass", "s3cretpass"),
    ("curl -u admin:pa55word https://x.example", "pa55word"),
    ("the paseo token ee18c0ffee00000000000000000000aa in argv", "ee18c0ffee00000000000000000000aa"),
    ("the password is hunter22", "hunter22"),
    (_J(["posted to https://hooks.slack.com/services/", "T0000/B0000/", "XXXXXXXXXXXXXXXXXXXXXXXX"]),
     "XXXXXXXXXXXXXXXXXXXXXXXX"),
]
PATHS = ["crm/leads.csv", "/Users/x/broomva/crm/deals/acme.md", ".env", "apps/web/.env.local",
         "~/.ssh/id_ed25519", "deploy/keys/server.pem", "~/.aws/credentials", "config/secrets/prod.yaml"]
KEPT = [
    "missing token: see PR 12",
    "the bearer token flow",
    "rotating the secret: step 2",
    "sort key: ts, sort_key=ts, primary_key: id, monkey=3",
    "token count 12 of 40",
    "https://github.com/broomva/workspace/blob/main/docs/credentials.md",
    "on feat/BRO-2591-role-x-intake-hook-isolation-python-I",
    "session_id: e854782f-869e-44ef-89da-f0b99d8cce10",
    "ARC-STATUS: MERGED https://github.com/broomva/skills/pull/245",
    "head 427341c0b1e5f3a9d2c4b6a8e0f1d3c5b7a9e1f3 on feat/ctx-core-phase1",
    "author=Carlos reviewer=codex monkey=3",
    "npm-registry-authentication-failure in apps/web/package.json",
    "see skills/orchestration/ctx-core/scripts/ctx.py and docs/specs/x.html",
]


@pytest.mark.parametrize("name", sorted(SECRETS))
def test_tokens_are_redacted(name: str) -> None:
    out = ctx.redact_text("ARC-STATUS: BLOCKED leaked %s here" % SECRETS[name])
    assert SECRETS[name] not in out and "[REDACTED]" in out


@pytest.mark.parametrize("text,value", SHAPED)
def test_headers_and_key_values_are_redacted(text: str, value: str) -> None:
    out = ctx.redact_text(text)
    assert value not in out, out
    assert "[REDACTED]" in out


@pytest.mark.parametrize("path", PATHS)
def test_crm_and_secret_shaped_paths_are_dropped(path: str) -> None:
    out = ctx.redact_text("edited %s, then pushed" % path)
    assert path not in out and "[excluded-path]" in out
    assert ctx.excluded_path(path)


@pytest.mark.parametrize("text", KEPT)
def test_ordinary_text_is_left_alone(text: str) -> None:
    assert ctx.redact_text(text) == text


@pytest.mark.parametrize("text", [*SECRETS.values(), *(t for t, _ in SHAPED), *PATHS, *KEPT])
def test_redaction_is_idempotent(text: str) -> None:
    once = ctx.redact_text(text)
    assert ctx.redact_text(once) == once


def test_redact_walks_nested_values_and_leaves_keys_and_numbers() -> None:
    ev = {"payload": {"a": ["x", {"token": "token=zzz111"}], "n": 3, "ok": True, "none": None}}
    out = ctx.redact(ev)
    assert out == {"payload": {"a": ["x", {"token": "token=[REDACTED]"}], "n": 3, "ok": True, "none": None}}


def test_nothing_secret_reaches_the_log_through_the_stop_hook(world: World) -> None:
    lines = ["ARC-STATUS: BLOCKED " + " ".join(SECRETS.values()) + " " + " ".join(t for t, _ in SHAPED[:9])]
    lines += ["worked on %s" % p for p in PATHS]
    message = "\n".join(reversed(lines))  # the ARC-STATUS line last, so it is the one captured
    world.stop("s-1", world.broomva, message)
    world.died("s-1", world.broomva)
    world.hook("stop-failure", {"session_id": "s-2", "cwd": str(world.broomva), "error_type": "api_error",
                                "error": "401 from https://api.example.com?api_key=kkkk9999 Bearer " + SECRETS["jwt"],
                                "last_assistant_message": "ARC-STATUS: DIED " + SECRETS["anthropic"]})
    raw = (world.store("broomva") / "events.jsonl").read_text()
    assert raw.count("\n") == 3 and "[REDACTED]" in raw
    for value in [*SECRETS.values(), *(v for _, v in SHAPED[:9]), "kkkk9999"]:
        assert value not in raw, value
    board = (world.store("broomva") / "board.json").read_text()
    assert all(v not in board for v in SECRETS.values())


def test_a_crm_path_in_a_payload_never_reaches_the_log(world: World) -> None:
    world.stop("s-1", world.broomva, "ARC-STATUS: DONE updated crm/pipeline/acme.md and ~/.ssh/config")
    raw = (world.store("broomva") / "events.jsonl").read_text()
    assert "crm/" not in raw and ".ssh" not in raw
    assert "ARC-STATUS: DONE updated [excluded-path] and [excluded-path]" in raw


def test_a_token_straddling_the_clip_is_redacted_before_the_cut(world: World) -> None:
    """Clipping first would cut the token and leave a prefix too short for any
    pattern, so that prefix would be written."""
    for pad in range(ctx.MAX_STR - 30, ctx.MAX_STR + 5):
        line = "ARC-STATUS: BLOCKED " + "x" * (pad - 20) + " " + SECRETS["github classic"]
        world.stop("s-%d" % pad, world.broomva, line)
    raw = (world.store("broomva") / "events.jsonl").read_text()
    assert "ghp_" not in raw


@pytest.mark.parametrize("text", ["a-" * 1600, "a1-" * 1066, "api-" * 800, "A_" * 1600, "token" * 640,
                                  "x." * 1600, "Aa1" * 1066, "bearer " * 457])
def test_no_pattern_is_quadratic(text: str) -> None:
    """Round-2 finding: an unbounded lazy key prefix took 415 ms on `a-a-a…`."""
    import time as _time
    t0 = _time.perf_counter()
    ctx.redact(text)
    assert _time.perf_counter() - t0 < 0.05, "%.0f ms" % ((_time.perf_counter() - t0) * 1000)


def test_the_pre_cap_leaves_no_partial_token() -> None:
    """Round-2 finding: a cut at the pre-cap could leave a token prefix too short
    to recognise, and redaction shrinking the text could bring it inside the clip."""
    for pad in range(ctx.PRECAP - 45, ctx.PRECAP + 2):
        text = "ARC-STATUS: BLOCKED token=" + "A" * (pad - 27) + " " + SECRETS["github classic"]
        out = ctx.redact(text)
        assert "ghp_" not in out and "gh" + "p" not in out.split()[-1], (pad, out[-40:])
