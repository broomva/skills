"""``health doctor`` subcommand — self-diagnostic checklist."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import typer

from broomva_health.cli.formatters import format_value
from broomva_health.domain.source import Source

# Temp-dir prefixes that make an editable install fragile (vanish on reboot).
# These are match prefixes for path *detection*, not temp-file creation — the
# S108 (bandit insecure-temp) lint does not apply.
_EPHEMERAL_PREFIXES = (
    "/tmp/",  # noqa: S108
    "/private/tmp/",
    "/var/tmp/",  # noqa: S108
    "/var/folders/",
    "/private/var/folders/",
)

if TYPE_CHECKING:
    from broomva_health.cli.container import Container

__all__ = ["app"]


app = typer.Typer(
    invoke_without_command=True,
    no_args_is_help=False,
    help="Self-diagnostic — paths, config, token presence, DB migration, vault.",
)


@dataclass(frozen=True)
class Check:
    name: str
    status: str  # "OK" | "WARN" | "FAIL"
    detail: str


def _container_from_ctx(ctx: typer.Context) -> Container:
    container = ctx.obj["container"] if ctx.obj else None
    if container is None:
        raise typer.BadParameter("CLI was not initialized — container missing")
    return container  # type: ignore[no-any-return]


def _check_paths(container: Container) -> list[Check]:
    checks: list[Check] = []
    paths = container.paths
    for label, path, required in (
        ("config_dir", paths.config_dir, True),
        ("data_dir", paths.data_dir, True),
        ("traces_dir", paths.traces_dir, True),
        ("tokens_dir", paths.tokens_dir, True),
        ("vault_dir", paths.vault_dir, False),
    ):
        if path.exists():
            checks.append(Check(f"path.{label}", "OK", str(path)))
        elif required:
            checks.append(Check(f"path.{label}", "FAIL", f"missing: {path}"))
        else:
            checks.append(Check(f"path.{label}", "WARN", f"missing: {path}"))
    return checks


def _check_config(container: Container) -> list[Check]:
    cfg = container.paths.config_file
    if cfg.exists():
        try:
            data = cfg.read_text()
            return [Check("config.toml", "OK", f"{len(data)} bytes at {cfg}")]
        except OSError as exc:
            return [Check("config.toml", "FAIL", f"unreadable: {exc}")]
    return [
        Check(
            "config.toml",
            "WARN",
            f"absent at {cfg} — using defaults + env",
        )
    ]


def _check_tokens(container: Container) -> list[Check]:
    """Token validity via each source's own ``status()`` — the same contract
    ``auth status`` uses.

    A generic ``token_store`` lookup false-FAILs for the default native backend,
    which keeps its garth token outside the ``token_store`` (in
    ``tokens_dir/garmin-garth/<profile>``). ``status()`` resolves the token
    wherever the backend actually stores it, so doctor agrees with ``auth status``.
    """
    checks: list[Check] = []
    profile = container.settings.default_profile
    for src, source in container.sources.items():
        try:
            st = source.status(token_store=container.token_store, profile=profile)
        except Exception as exc:  # status() is reflexive and shouldn't raise; be safe
            checks.append(Check(f"token.{src.value}", "WARN", f"status check failed: {exc}"))
            continue
        if st.token_valid:
            detail = "token valid"
            if st.token_expires_at is not None:
                detail += f"; expires {st.token_expires_at.isoformat()}"
            checks.append(Check(f"token.{src.value}", "OK", detail))
        else:
            severity = "FAIL" if src is Source.GARMIN else "WARN"
            detail = st.last_error or (
                f"no valid token for profile={profile} — run `health auth import` "
                "(native backend) or `health auth login`"
            )
            checks.append(Check(f"token.{src.value}", severity, detail))
    return checks


def _check_repository(container: Container) -> list[Check]:
    checks: list[Check] = []
    for src in container.sources:
        try:
            repo = container.repository_for(src)
            applied = repo.migrate()
            checks.append(
                Check(
                    f"repo.{src.value}",
                    "OK",
                    f"migrated ({applied} steps); {container.paths.trace_db_for(src.value)}",
                )
            )
        except Exception as exc:
            checks.append(Check(f"repo.{src.value}", "FAIL", f"{type(exc).__name__}: {exc}"))
    return checks


def _check_vault(container: Container) -> list[Check]:
    vault = container.paths.vault_health_dir
    if vault.exists():
        return [Check("vault.health", "OK", str(vault))]
    return [Check("vault.health", "WARN", f"missing: {vault} — daily-note will be skipped")]


def _check_legacy_data(container: Container) -> list[Check]:
    """Warn if biometric data is sitting in the pre-v0.5 in-repo location."""
    from broomva_health.config.paths import HealthPaths

    legacy = HealthPaths.legacy_data_dir()
    legacy_traces = legacy / "traces"
    current = container.paths.data_dir
    if legacy != current and legacy_traces.exists() and any(legacy_traces.glob("*.db")):
        return [
            Check(
                "legacy_data",
                "WARN",
                f"biometric DB found in the old in-repo location {legacy_traces} — "
                f"move it to {current / 'traces'} (it may be inside a git repo). "
                f"`mv {legacy}/* {current}/` then `rmdir {legacy}`.",
            )
        ]
    return [Check("legacy_data", "OK", "no biometric data in the legacy in-repo location")]


def _check_install(container: Container | None = None) -> list[Check]:  # noqa: ARG001
    """Flag an editable install pinned to an ephemeral temp dir.

    RC1 (BRO-1552): the CLI was once editable-installed (`pip install -e`) from a
    `mktemp` clone under `/tmp`; when the OS cleared `/tmp` the import broke on
    EVERY call (`ModuleNotFoundError`), which masked an otherwise-working skill.
    `install.sh`'s durability guard prevents *new* installs from landing here,
    but a pre-existing fragile install only surfaces on the next reboot — this
    check warns *before* that, while the temp dir still happens to exist.
    """
    import broomva_health

    src = Path(broomva_health.__file__).resolve()
    s = str(src)
    prefixes: list[str] = list(_EPHEMERAL_PREFIXES)
    tmpdir = os.environ.get("TMPDIR", "").rstrip("/")
    if tmpdir:
        prefixes.append(tmpdir + "/")
    root = src.parent.parent  # .../src (editable) or .../site-packages (regular)
    if any(s.startswith(p) for p in prefixes):
        return [
            Check(
                "install.source",
                "FAIL",
                f"package is installed from an ephemeral temp path ({root}); it will "
                "vanish on reboot and break every `health` call. Reinstall from a stable "
                "location — e.g. `bash ~/.claude/skills/health/install.sh` (the durability "
                "guard copies temp sources to a stable home).",
            )
        ]
    return [Check("install.source", "OK", str(root))]


def _render_checks_human(checks: list[Check]) -> str:
    lines: list[str] = []
    for chk in checks:
        marker = {"OK": "[ OK ]", "WARN": "[WARN]", "FAIL": "[FAIL]"}.get(chk.status, "[ ?? ]")
        lines.append(f"{marker} {chk.name}  —  {chk.detail}")
    return "\n".join(lines) + "\n"


@app.callback()
def doctor_root(ctx: typer.Context) -> None:
    """Run a self-diagnostic checklist; exit non-zero on any FAIL.

    WARN-level results (e.g. missing vault dir, missing token bundle for a
    non-required source) do not cause a non-zero exit.
    """

    if ctx.invoked_subcommand is not None:
        return

    container = _container_from_ctx(ctx)
    checks: list[Check] = []
    checks.extend(_check_paths(container))
    checks.extend(_check_config(container))
    checks.extend(_check_tokens(container))
    checks.extend(_check_repository(container))
    checks.extend(_check_vault(container))
    checks.extend(_check_legacy_data(container))
    checks.extend(_check_install(container))

    fmt = ctx.obj["format"]
    fields = ctx.obj["fields"]
    if fmt == "human":
        typer.echo(_render_checks_human(checks), nl=False)
    else:
        payload = [{"name": c.name, "status": c.status, "detail": c.detail} for c in checks]
        typer.echo(format_value(payload, fmt, fields=fields))
    if any(chk.status == "FAIL" for chk in checks):
        raise typer.Exit(code=1)
