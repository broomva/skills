"""Import-only sources (several producers, no reconciliation) stay out of one-stream surfaces."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from typer.testing import CliRunner

from broomva_health.cli import auth, sync
from broomva_health.cli.synthesis import synthesis_by_source
from broomva_health.domain.source import IMPORT_ONLY_SOURCES, Source, single_stream


class _Boom:
    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"import-only source touched: {name}")


def _container(tmp_path: Path) -> SimpleNamespace:
    def repository_for(src: Source) -> object:
        if src in IMPORT_ONLY_SOURCES:
            raise AssertionError("an import-only trace DB was opened")
        raise RuntimeError("no garmin db in this test")

    return SimpleNamespace(
        sources={Source.APPLE_HEALTH: _Boom()},
        repository_for=repository_for,
        token_store=None,
        rate_limiter=None,
        mfa=None,
        paths=SimpleNamespace(data_dir=tmp_path, vault_dir=tmp_path, ensure=lambda: None),
    )


def test_single_stream_drops_import_only_sources() -> None:
    assert single_stream([Source.GARMIN, Source.APPLE_HEALTH]) == [Source.GARMIN]


def test_sync_of_an_import_only_source_opens_nothing(tmp_path: Path) -> None:
    obj = {"container": _container(tmp_path), "format": "json", "fields": None}
    explicit = CliRunner().invoke(sync.app, ["--source", "apple_health"], obj=obj)
    assert explicit.exit_code == 0, explicit.output
    assert "import-only" in explicit.output
    everything = CliRunner().invoke(sync.app, [], obj=obj)
    assert everything.exit_code == 0, everything.output


def test_login_for_an_import_only_source_asks_for_nothing(tmp_path: Path) -> None:
    obj = {"container": _container(tmp_path), "format": "json", "fields": None}
    result = CliRunner().invoke(auth.app, ["login", "--source", "apple_health"], obj=obj, input="")
    assert result.exit_code == 0, result.output
    assert "needs no login" in result.output


def test_synthesis_skips_import_only_sources(tmp_path: Path) -> None:
    assert synthesis_by_source(_container(tmp_path), on_date=None) == {}  # type: ignore[arg-type]


def test_daily_note_refuses_an_import_only_source(tmp_path: Path) -> None:
    from datetime import UTC, datetime

    from broomva_health.cli import daily_note

    container = _container(tmp_path)
    container.clock = SimpleNamespace(now=lambda: datetime(2024, 3, 3, tzinfo=UTC))
    container.projection = object()
    obj = {"container": container, "format": "json", "fields": None}
    explicit = CliRunner().invoke(daily_note.app, ["--source", "apple_health"], obj=obj)
    assert explicit.exit_code == 1
    assert "series" in explicit.output
    default = CliRunner().invoke(
        daily_note.app, [], obj=obj
    )  # only an import-only source registered
    assert default.exit_code == 1


def test_context_lists_but_never_reads_an_import_only_source(tmp_path: Path) -> None:
    import json
    from datetime import UTC, datetime

    from broomva_health.cli import context

    opened: list[Source] = []
    container = _container(tmp_path)

    def repository_for(src: Source) -> object:
        opened.append(src)
        raise RuntimeError("no db")

    container.repository_for = repository_for
    container.clock = SimpleNamespace(now=lambda: datetime(2024, 3, 3, tzinfo=UTC))
    result = CliRunner().invoke(
        context.app, [], obj={"container": container, "format": "json", "fields": None}
    )
    assert result.exit_code == 0, result.output
    assert opened == []
    assert json.loads(result.output)["profile_info"]["registered_sources"] == ["apple_health"]
