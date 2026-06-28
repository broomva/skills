"""Tests for FilesystemTokenStore."""

from __future__ import annotations

import json
import stat
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from broomva_health.adapters.token_stores.filesystem import FilesystemTokenStore
from broomva_health.domain.results import TokenBundle
from broomva_health.domain.source import Source

T0 = datetime(2026, 5, 22, 12, 0, tzinfo=UTC)


def _bundle(
    *,
    source: Source,
    profile: str = "default",
    raw_bytes: bytes = b"x",
    stored_at: datetime = T0,
    expires_at: datetime | None = None,
) -> TokenBundle:
    """Build a TokenBundle bypassing pydantic validation.

    The domain's `field_validator(mode="after")` decorators in `results.py`
    use a (cls, v) lambda shape that is incompatible with pydantic v2 (which
    passes (value, ValidationInfo)). Until Stream A repairs the validators,
    these adapter tests use `model_construct` — the FilesystemTokenStore
    only reads the attributes, so skipping validation is sound here.
    """
    return TokenBundle.model_construct(
        source=source,
        profile=profile,
        raw_bytes=raw_bytes,
        stored_at=stored_at,
        expires_at=expires_at,
    )


@pytest.fixture
def store(tmp_path: Path) -> FilesystemTokenStore:
    return FilesystemTokenStore(tmp_path / "tokens")


def test_tokens_dir_created_with_mode_0700(tmp_path: Path) -> None:
    tokens_dir = tmp_path / "tokens"
    FilesystemTokenStore(tokens_dir)
    assert tokens_dir.exists()
    mode = stat.S_IMODE(tokens_dir.stat().st_mode)
    # On macOS/Linux this should be 0o700; on a system that can't chmod we
    # tolerate any value (best-effort behavior).
    assert mode in {0o700, 0o755, 0o775, 0o777}  # accept platform defaults
    # but we *did* attempt 0o700 on POSIX
    import os as _os
    if hasattr(_os, "chmod"):
        assert mode == 0o700


def test_get_missing_returns_none(store: FilesystemTokenStore) -> None:
    assert store.get(Source.GARMIN) is None
    assert store.get(Source.WHOOP, "alt") is None


def test_round_trip_put_get(store: FilesystemTokenStore) -> None:
    bundle = _bundle(
        source=Source.WHOOP,
        raw_bytes=b"opaque-bytes-here",
        expires_at=T0 + timedelta(hours=1),
    )
    store.put(bundle)
    loaded = store.get(Source.WHOOP)
    assert loaded is not None
    assert loaded.source is Source.WHOOP
    assert loaded.profile == "default"
    assert loaded.raw_bytes == b"opaque-bytes-here"
    assert loaded.stored_at == T0
    assert loaded.expires_at == T0 + timedelta(hours=1)


def test_round_trip_without_expiry(store: FilesystemTokenStore) -> None:
    bundle = _bundle(source=Source.OURA, profile="me")
    store.put(bundle)
    loaded = store.get(Source.OURA, profile="me")
    assert loaded is not None
    assert loaded.expires_at is None


def test_bundle_file_mode_0600(store: FilesystemTokenStore, tmp_path: Path) -> None:
    bundle = _bundle(source=Source.WHOOP)
    store.put(bundle)
    bundle_path = tmp_path / "tokens" / "whoop" / "default" / "bundle.bin"
    mode = stat.S_IMODE(bundle_path.stat().st_mode)
    assert mode == 0o600


def test_put_overwrites_existing(store: FilesystemTokenStore) -> None:
    first = _bundle(source=Source.WHOOP, raw_bytes=b"v1")
    second = _bundle(
        source=Source.WHOOP, raw_bytes=b"v2", stored_at=T0 + timedelta(seconds=10)
    )
    store.put(first)
    store.put(second)
    loaded = store.get(Source.WHOOP)
    assert loaded is not None
    assert loaded.raw_bytes == b"v2"


def test_delete_removes_profile(store: FilesystemTokenStore, tmp_path: Path) -> None:
    store.put(_bundle(source=Source.OURA))
    assert store.get(Source.OURA) is not None
    store.delete(Source.OURA)
    assert store.get(Source.OURA) is None
    profile_dir = tmp_path / "tokens" / "oura" / "default"
    assert not profile_dir.exists()


def test_delete_missing_is_noop(store: FilesystemTokenStore) -> None:
    # should not raise
    store.delete(Source.WHOOP, profile="never-existed")


def test_list_profiles_empty(store: FilesystemTokenStore) -> None:
    assert store.list_profiles(Source.GARMIN) == []


def test_list_profiles_sorted(store: FilesystemTokenStore) -> None:
    for profile in ("charlie", "alpha", "bravo"):
        store.put(_bundle(source=Source.GARMIN, profile=profile))
    assert store.list_profiles(Source.GARMIN) == ["alpha", "bravo", "charlie"]


def test_garmin_special_writes_compat_file(
    store: FilesystemTokenStore, tmp_path: Path
) -> None:
    raw = b'{"access_token": "abc", "refresh_token": "xyz"}'
    bundle = _bundle(source=Source.GARMIN, raw_bytes=raw)
    store.put(bundle)
    compat = tmp_path / "tokens" / "garmin" / "default" / "garmin_tokens.json"
    assert compat.exists()
    assert compat.read_bytes() == raw


def test_non_garmin_does_not_write_compat_file(
    store: FilesystemTokenStore, tmp_path: Path
) -> None:
    store.put(_bundle(source=Source.WHOOP))
    compat = tmp_path / "tokens" / "whoop" / "default" / "garmin_tokens.json"
    assert not compat.exists()


def test_meta_file_contains_expected_keys(
    store: FilesystemTokenStore, tmp_path: Path
) -> None:
    store.put(_bundle(source=Source.OURA, profile="me"))
    meta_path = tmp_path / "tokens" / "oura" / "me" / "bundle.meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    assert meta["source"] == "oura"
    assert meta["profile"] == "me"
    assert meta["expires_at"] is None
    assert "stored_at" in meta


def test_profile_dir_helper(store: FilesystemTokenStore, tmp_path: Path) -> None:
    expected = tmp_path / "tokens" / "garmin" / "broomva"
    assert store.profile_dir(Source.GARMIN, "broomva") == expected
