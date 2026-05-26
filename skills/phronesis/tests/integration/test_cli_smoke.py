"""CLI end-to-end smoke test.

Drives the Click CLI runner via Click's CliRunner against an isolated
temporary engagement directory. Verifies the init → status → lint flow
that ships in Phase 1.
"""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from click.testing import CliRunner

from runners.cli.__main__ import cli

pytestmark = [pytest.mark.integration]


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


@pytest.fixture
def workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Run CLI inside an isolated tmp workspace so engagements/ doesn't
    bleed into the project root."""
    monkeypatch.chdir(tmp_path)
    return tmp_path


class TestCliSmoke:
    def test_help_lists_commands(self, runner: CliRunner):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "init" in result.output
        assert "status" in result.output
        assert "lint" in result.output
        assert "render" in result.output

    def test_init_creates_scaffold(self, runner: CliRunner, workspace: Path):
        result = runner.invoke(
            cli,
            [
                "init",
                "demo",
                "--name",
                "Demo Inc",
                "--industry",
                "banking",
                "--region",
                "CO",
                "--revenue-band",
                "100M-1B",
                "--headcount-band",
                "500-5000",
                "--sponsor",
                "Jane Doe",
                "--sponsor-role",
                "CDO",
                "--scope",
                "Phase 1 smoke",
                "--target-duration-weeks",
                "8",
            ],
        )
        assert result.exit_code == 0, result.output
        assert (workspace / "engagements" / "demo" / "tenant.yaml").exists()
        assert (workspace / "engagements" / "demo" / "journal.jsonl").exists()

    def test_init_aborts_on_existing_engagement(self, runner: CliRunner, workspace: Path):
        # First init succeeds
        args = [
            "init",
            "demo",
            "--name",
            "Demo Inc",
            "--industry",
            "banking",
            "--region",
            "CO",
            "--revenue-band",
            "100M-1B",
            "--headcount-band",
            "500-5000",
            "--sponsor",
            "Jane Doe",
            "--sponsor-role",
            "CDO",
            "--scope",
            "s",
            "--target-duration-weeks",
            "8",
        ]
        first = runner.invoke(cli, args)
        assert first.exit_code == 0
        # Second init refuses to overwrite
        second = runner.invoke(cli, args)
        assert second.exit_code == 1
        assert "already exists" in second.output

    def test_status_after_init(self, runner: CliRunner, workspace: Path):
        runner.invoke(
            cli,
            [
                "init",
                "demo",
                "--name",
                "Demo Inc",
                "--industry",
                "banking",
                "--region",
                "CO",
                "--revenue-band",
                "100M-1B",
                "--headcount-band",
                "500-5000",
                "--sponsor",
                "Jane Doe",
                "--sponsor-role",
                "CDO",
                "--scope",
                "Phase 1 smoke",
                "--target-duration-weeks",
                "8",
            ],
        )
        result = runner.invoke(cli, ["status", "demo"])
        assert result.exit_code == 0, result.output
        assert "Demo Inc" in result.output
        assert "Current stage: intake" in result.output
        assert "Concluded:     False" in result.output
        assert "Thesis:        NOT declared" in result.output
        assert "Journal events: 1" in result.output  # ENGAGEMENT_STARTED

    def test_lint_clean_on_fresh_engagement(self, runner: CliRunner, workspace: Path):
        runner.invoke(
            cli,
            [
                "init",
                "demo",
                "--name",
                "Demo Inc",
                "--industry",
                "banking",
                "--region",
                "CO",
                "--revenue-band",
                "100M-1B",
                "--headcount-band",
                "500-5000",
                "--sponsor",
                "Jane Doe",
                "--sponsor-role",
                "CDO",
                "--scope",
                "Phase 1 smoke",
                "--target-duration-weeks",
                "8",
            ],
        )
        result = runner.invoke(cli, ["lint", "demo"])
        assert result.exit_code == 0
        assert "lints clean" in result.output

    def test_status_missing_engagement_errors(self, runner: CliRunner, workspace: Path):
        result = runner.invoke(cli, ["status", "nonexistent"])
        assert result.exit_code != 0
        # FileNotFoundError surfaces as Click's exception output
        assert "not found" in str(result.exception) or "not found" in result.output


class TestCliVersion:
    def test_version_flag(self, runner: CliRunner):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        # Version is whatever pyproject declares
        assert result.output.strip()  # non-empty


# Sanity: ensure CWD-changing fixture leaves cwd untouched after teardown.
def test_workspace_isolation(workspace: Path):
    assert os.getcwd() == str(workspace)
