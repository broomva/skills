"""Filesystem TokenStore — default adapter for token persistence.

Layout::

    <tokens_dir>/                       (0o700)
        garmin/
            default/
                bundle.bin              (0o600) — opaque raw_bytes
                bundle.meta.json        — provenance: stored_at, expires_at, source, profile
                garmin_tokens.json      — Garmin library-compatible token file
                                          (only for Source.GARMIN; raw_bytes IS this file)
            broomva/
                ...
        whoop/
            default/
                ...

For Source.GARMIN, the raw_bytes IS the content of the Garmin library's
`garmin_tokens.json` file — we duplicate it on disk under the standard name
so the library's `Garmin.login(tokenstore=<dir>)` path picks it up.
"""

from __future__ import annotations

import json
import logging
import os
import shutil
from datetime import datetime
from pathlib import Path

from broomva_health.domain.results import TokenBundle
from broomva_health.domain.source import Source
from broomva_health.domain.time import ensure_utc

__all__ = ["FilesystemTokenStore"]

logger = logging.getLogger(__name__)

_BUNDLE_FILE = "bundle.bin"
_META_FILE = "bundle.meta.json"
_GARMIN_LIB_FILE = "garmin_tokens.json"


class FilesystemTokenStore:
    """Persist + retrieve TokenBundles under a directory tree on disk.

    The tokens_dir is created at mode 0o700 on first construction; bundle.bin
    files are written at 0o600. Atomic writes (tmp + rename) so a crashed
    process never leaves a half-written token on disk.
    """

    def __init__(self, tokens_dir: Path) -> None:
        self._root = Path(tokens_dir).expanduser()
        self._root.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self._root, 0o700)
        except OSError as exc:  # pragma: no cover — Windows etc.
            logger.debug("Could not chmod tokens_dir to 0700: %s", exc)

    # --- public API ---

    def get(self, source: Source, profile: str = "default") -> TokenBundle | None:
        bundle_path, meta_path = self._paths(source, profile)
        if not bundle_path.exists() or not meta_path.exists():
            return None
        raw_bytes = bundle_path.read_bytes()
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        stored_at = _parse_iso(meta["stored_at"])
        expires_raw = meta.get("expires_at")
        expires_at = _parse_iso(expires_raw) if expires_raw else None
        # Plain constructor — validators run. The ISO parser returns
        # UTC-aware datetimes; the Source enum normalizes the string;
        # `raw_bytes` is opaque so no validation needed there.
        return TokenBundle(
            source=Source(meta["source"]),
            profile=meta["profile"],
            raw_bytes=raw_bytes,
            stored_at=stored_at,
            expires_at=expires_at,
        )

    def put(self, bundle: TokenBundle) -> None:
        bundle_path, meta_path = self._paths(bundle.source, bundle.profile)
        bundle_path.parent.mkdir(parents=True, exist_ok=True)

        _atomic_write_bytes(bundle_path, bundle.raw_bytes, mode=0o600)
        meta = {
            "source": str(bundle.source),
            "profile": bundle.profile,
            "stored_at": ensure_utc(bundle.stored_at).isoformat(),
            "expires_at": (
                ensure_utc(bundle.expires_at).isoformat() if bundle.expires_at else None
            ),
        }
        _atomic_write_text(
            meta_path, json.dumps(meta, indent=2, sort_keys=True) + "\n", mode=0o600
        )

        # Garmin library compatibility — the raw_bytes IS the token JSON,
        # mirror it to garmin_tokens.json so Garmin().login(tokenstore=<dir>) works.
        if bundle.source is Source.GARMIN:
            lib_path = bundle_path.parent / _GARMIN_LIB_FILE
            _atomic_write_bytes(lib_path, bundle.raw_bytes, mode=0o600)

    def delete(self, source: Source, profile: str = "default") -> None:
        profile_dir = self._root / str(source) / profile
        if profile_dir.exists():
            shutil.rmtree(profile_dir)

    def list_profiles(self, source: Source) -> list[str]:
        source_dir = self._root / str(source)
        if not source_dir.exists():
            return []
        return sorted(p.name for p in source_dir.iterdir() if p.is_dir())

    # --- helpers ---

    def _paths(self, source: Source, profile: str) -> tuple[Path, Path]:
        profile_dir = self._root / str(source) / profile
        return profile_dir / _BUNDLE_FILE, profile_dir / _META_FILE

    def profile_dir(self, source: Source, profile: str = "default") -> Path:
        """Public — the on-disk directory holding `garmin_tokens.json` for a profile.

        Useful for adapters that want to pass a directory to a third-party
        library (e.g. Garmin().login(tokenstore=<dir>)).
        """
        return self._root / str(source) / profile


def _parse_iso(value: str) -> datetime:
    """Parse ISO-8601 and normalize to UTC."""
    return ensure_utc(datetime.fromisoformat(value))


def _atomic_write_bytes(path: Path, data: bytes, *, mode: int) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_bytes(data)
    try:
        os.chmod(tmp, mode)
    except OSError as exc:  # pragma: no cover
        logger.debug("Could not chmod %s to %o: %s", tmp, mode, exc)
    os.replace(tmp, path)


def _atomic_write_text(path: Path, data: str, *, mode: int) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(data, encoding="utf-8")
    try:
        os.chmod(tmp, mode)
    except OSError as exc:  # pragma: no cover
        logger.debug("Could not chmod %s to %o: %s", tmp, mode, exc)
    os.replace(tmp, path)
