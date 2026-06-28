"""Real-boundary contract test for the `library` backend's token format.

BRO-1552/1553: `garminconnect` ≥ 0.3 wraps garth, whose `dump(dir)` writes the
**two-file** format `oauth1_token.json` + `oauth2_token.json` — NOT a single
`garmin_tokens.json`. The original `_read_persisted_tokens` only checked the
single legacy file, so a real login always false-failed. These tests pin the
actual on-disk contract so a mock can't hide the mismatch again.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from broomva_health.adapters.sources.garmin import GarminTraceSource
from broomva_health.config.paths import HealthPaths
from broomva_health.domain.errors import AuthRequired


def _paths(tmp_path: Path) -> HealthPaths:
    p = HealthPaths(
        config_dir=tmp_path / "config",
        data_dir=tmp_path / "data",
        vault_dir=tmp_path / "vault",
    )
    p.ensure()
    return p


def _substantial_oauth2() -> str:
    return json.dumps(
        {"access_token": "a" * 120, "token_type": "Bearer", "expires_at": 1781499487}
    )


def test_read_persisted_tokens_accepts_garth_two_file(tmp_path: Path) -> None:
    """garth's real dump format (oauth2_token.json present, no garmin_tokens.json)
    must validate — not raise AuthRequired."""
    src = GarminTraceSource(paths=_paths(tmp_path))
    token_dir = tmp_path / "tok"
    token_dir.mkdir()
    (token_dir / "oauth2_token.json").write_text(_substantial_oauth2())
    (token_dir / "oauth1_token.json").write_text(json.dumps({"oauth_token": "x" * 60}))

    raw = src._read_persisted_tokens(token_dir)
    assert raw  # non-empty → did NOT false-fail despite no garmin_tokens.json


def test_read_persisted_tokens_falls_back_to_legacy_single_file(tmp_path: Path) -> None:
    """Older library builds that still emit a single garmin_tokens.json keep working."""
    src = GarminTraceSource(paths=_paths(tmp_path))
    token_dir = tmp_path / "tok"
    token_dir.mkdir()
    (token_dir / "garmin_tokens.json").write_text(
        json.dumps({"oauth2_token": {"access_token": "b" * 120}})
    )

    raw = src._read_persisted_tokens(token_dir)
    assert raw


def test_read_persisted_tokens_raises_when_no_tokens(tmp_path: Path) -> None:
    """Empty dir → AuthRequired (the genuine 'login returned but wrote nothing' guard)."""
    src = GarminTraceSource(paths=_paths(tmp_path))
    token_dir = tmp_path / "empty"
    token_dir.mkdir()

    with pytest.raises(AuthRequired):
        src._read_persisted_tokens(token_dir)
