"""Integration tests for the M7 extraction pipeline.

Drives `extract_and_queue()` against each fixture and verifies:
  - the review queue + entity-graph directories are populated correctly,
  - the score-≥5 cut promotes candidates, score-<5 routes to low-score,
  - no anonymization leaks land in either queued or promoted records,
  - the ENGAGEMENT_CONCLUDED reflexive hook fires automatically,
  - the CLI `phronesis bookkeep <slug>` smoke test passes.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from click.testing import CliRunner

from core.extraction.pipeline import extract_and_queue, on_engagement_concluded
from runners.cli.__main__ import cli
from tests.fixtures.acme_bank import build_acme_bank_engagement
from tests.fixtures.nova_construction import build_nova_construction_engagement
from tests.fixtures.tropico_renovables import build_tropico_engagement

pytestmark = [pytest.mark.integration]


def _entity_snapshot(root: Path) -> set[str]:
    """Every entity page under `root`, as repo-relative strings."""
    return {str(p.relative_to(root)) for p in root.rglob("*.md")}


# Pre-emptively force the deterministic stub scorer for these tests.
# Real bookkeeping scoring depends on the optional `mistune` import +
# network LLM calls — both unsuitable for CI. The bookkeeping-integration
# path is exercised separately under a tagged smoke test.
@pytest.fixture(autouse=True)
def force_stub_scorer(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PHRONESIS_EXTRACTION_STUB_SCORER", "1")


@pytest.fixture
def queue_root(tmp_path: Path) -> Path:
    return tmp_path / "queue"


@pytest.fixture
def entity_root(tmp_path: Path) -> Path:
    return tmp_path / "entities"


class TestExtractAndQueue:
    @pytest.mark.parametrize(
        "fixture_builder, expected_slug",
        [
            (build_tropico_engagement, "tropico-renovables"),
            (build_acme_bank_engagement, "acme-bank"),
            (build_nova_construction_engagement, "nova-construction"),
        ],
    )
    def test_runs_for_each_fixture_and_persists_records(
        self,
        fixture_builder,
        expected_slug,
        queue_root: Path,
        entity_root: Path,
    ):
        eng = fixture_builder()
        result = extract_and_queue(eng, queue_root=queue_root, entity_graph_root=entity_root)

        assert result.engagement_slug == expected_slug
        assert result.total_candidates >= 1
        assert not result.leaks, f"Pipeline reported leaks for {expected_slug}: {result.leaks}"

        # Queue dir must exist and contain at least one record.
        engagement_queue = queue_root / expected_slug
        assert engagement_queue.exists(), (
            f"Queue dir missing for {expected_slug}: {engagement_queue}"
        )

        all_records = list(engagement_queue.rglob("*.json"))
        assert len(all_records) == result.total_candidates, (
            f"Persisted {len(all_records)} JSON records vs "
            f"{result.total_candidates} candidates produced."
        )

        # Either promoted/ or low-score/ must hold them.
        if result.promoted_count:
            promoted_dir = engagement_queue / "promoted"
            assert promoted_dir.exists()
            promoted_files = list(promoted_dir.glob("*.json"))
            assert len(promoted_files) == result.promoted_count

            # Entity stubs persisted in entity_root/{type}/.
            assert len(result.promotion_paths) == result.promoted_count
            for path in result.promotion_paths:
                assert path.exists()
                assert path.suffix == ".md"
                body = path.read_text()
                assert "status: candidate" in body
                assert "engagement_slug:" in body

        if result.queued_count:
            low_score_dir = engagement_queue / "low-score"
            assert low_score_dir.exists()


class TestReflexiveHook:
    def test_on_engagement_concluded_fires_for_concluded_engagement(
        self, queue_root: Path, entity_root: Path
    ):
        eng = build_tropico_engagement()
        result = on_engagement_concluded(eng, queue_root=queue_root, entity_graph_root=entity_root)
        assert result is not None
        assert result.engagement_slug == "tropico-renovables"

    def test_on_engagement_concluded_skips_when_not_concluded(
        self,
        queue_root: Path,
        entity_root: Path,
    ):
        # Build but truncate journal at intake — never reaches conclusion.
        from core.engagement import Engagement, EngagementJournal
        from core.types import TenantContext

        tenant = TenantContext(
            tenant_slug="midway-coop",
            name="Midway Co-op Ltd",
            industry="energy-utilities",
            region="CO",
            revenue_band="<10M",
            headcount_band="50-500",
            sponsor="Jane Doe",
            sponsor_role="COO",
            engagement_scope="scope",
            starts_at=__import__("datetime").datetime(
                2026, 5, 6, tzinfo=__import__("datetime").timezone.utc
            ),
            target_duration_weeks=10,
        )
        eng = Engagement(tenant=tenant, journal=EngagementJournal(tenant=tenant))
        result = on_engagement_concluded(eng, queue_root=queue_root, entity_graph_root=entity_root)
        assert result is None
        # Queue dir must not be created.
        assert not (queue_root / "midway-coop").exists()

    def test_engagement_emit_concluded_fires_extraction_pipeline(
        self,
        monkeypatch: pytest.MonkeyPatch,
        queue_root: Path,
        entity_root: Path,
    ):
        """ENGAGEMENT_CONCLUDED emission triggers the M7 pipeline via the
        hook in `Engagement.emit()`."""
        monkeypatch.setenv("PHRONESIS_EXTRACTION_QUEUE_ROOT", str(queue_root))
        monkeypatch.setenv("PHRONESIS_ENTITY_GRAPH_ROOT", str(entity_root))

        # The fixture's build function emits ENGAGEMENT_CONCLUDED itself.
        # When env vars route to tmp dirs, the hook should populate them.
        build_tropico_engagement()
        assert (queue_root / "tropico-renovables").exists(), (
            "Reflexive hook did not fire on ENGAGEMENT_CONCLUDED emission; "
            "queue_root has no tropico-renovables subdir."
        )


class TestBookkeepCli:
    def test_bookkeep_help(self):
        runner = CliRunner()
        result = runner.invoke(cli, ["bookkeep", "--help"])
        assert result.exit_code == 0
        assert "bookkeep" in result.output.lower()
        assert "--dry-run" in result.output

    def test_bookkeep_runs_against_tropico_fixture(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        """End-to-end CLI: init engagement, drive through stages
        (via fixture), then `phronesis bookkeep <slug>` against the
        on-disk journal."""
        # Operate in tmp workspace + isolated queue/entity dirs.
        monkeypatch.chdir(tmp_path)
        queue_dir = tmp_path / "queue"
        entity_dir = tmp_path / "entities"

        # Persist the Tropico engagement to engagements/<slug>/ on disk.
        eng = build_tropico_engagement()
        from runners.cli.io import journal_path, save_tenant

        save_tenant(eng.tenant.tenant_slug, eng.tenant)
        eng.journal.save_jsonl(journal_path(eng.tenant.tenant_slug))

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "bookkeep",
                "tropico-renovables",
                "--queue-root",
                str(queue_dir),
                "--entity-graph-root",
                str(entity_dir),
            ],
        )
        assert result.exit_code == 0, (
            f"bookkeep CLI exited non-zero. Stdout: {result.output}\nException: {result.exception}"
        )
        assert "Engagement: tropico-renovables" in result.output
        assert "Industry-pattern candidates:" in result.output
        assert (queue_dir / "tropico-renovables").exists()

    def test_bookkeep_dry_run_persists_nothing(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ):
        monkeypatch.chdir(tmp_path)
        queue_dir = tmp_path / "queue"
        entity_dir = tmp_path / "entities"
        (entity_dir / "industry-pattern").mkdir(parents=True)
        (entity_dir / "framework-refinement").mkdir(parents=True)

        eng = build_tropico_engagement()
        from runners.cli.io import journal_path, save_tenant

        save_tenant(eng.tenant.tenant_slug, eng.tenant)
        eng.journal.save_jsonl(journal_path(eng.tenant.tenant_slug))

        entity_before = _entity_snapshot(entity_dir)

        runner = CliRunner()
        result = runner.invoke(
            cli,
            [
                "bookkeep",
                "tropico-renovables",
                "--dry-run",
                "--queue-root",
                str(queue_dir),
                "--entity-graph-root",
                str(entity_dir),
            ],
        )
        assert result.exit_code == 0
        assert "[dry-run]" in result.output
        # dry-run uses an in-process tempdir; queue_dir is never written.
        assert not queue_dir.exists()
        # ...and NEITHER is the entity graph. This half was missing, which is
        # how a --dry-run that wrote 6 pages into the operator's live knowledge
        # graph passed CI: the test asserted only about the queue.
        assert entity_before == _entity_snapshot(entity_dir), (
            "--dry-run PERSISTED entity page(s): "
            f"{sorted(_entity_snapshot(entity_dir) - entity_before)}"
        )


class TestEntityStub:
    """Smoke: promoted entity stubs are markdown with the right frontmatter."""

    def test_promoted_entity_has_yaml_frontmatter_and_body(
        self, queue_root: Path, entity_root: Path
    ):
        eng = build_acme_bank_engagement()
        result = extract_and_queue(eng, queue_root=queue_root, entity_graph_root=entity_root)
        if not result.promotion_paths:
            pytest.skip("No promotions for this fixture under stub scorer")

        path = result.promotion_paths[0]
        body = path.read_text()
        assert body.startswith("---\n")
        # Frontmatter closes
        assert "\n---\n" in body
        # Required fields
        for key in ("type:", "title:", "status: candidate", "score:"):
            assert key in body
        # The original read `"slug:" in body`, which ALSO matches
        # `engagement_slug:` — so it passed with no top-level slug key present,
        # and asserted the opposite of the unit test
        # (`"slug" not in _frontmatter(...)`, since workspace#530 dropped the
        # redundant field). Line-anchored, and asserting ABSENCE, so the two
        # tests now agree and this one can actually fail.
        assert not any(ln.startswith("slug:") for ln in body.splitlines()), \
            "top-level slug: is redundant with the filename (workspace#530)"


class TestPromotionRefusals:
    """The two refusals the writer used to ignore (BRO-2404).

    A P20 mutation sweep found both of these behaviours SURVIVING every
    mutation — the guards shipped with no test at all, which is the same
    shape as the defect they were added to fix.
    """

    def test_existing_entity_page_is_never_overwritten(
        self, queue_root: Path, entity_root: Path
    ) -> None:
        """This module's docstring says candidates "do NOT go directly to
        research/entities/ — every candidate must clear a human review pass
        first". `write_text` was unconditional and clobbered operator-polished
        pages; observed overwriting a claim authored by repair commit
        a1242b227.
        """
        eng = build_nova_construction_engagement()
        first = extract_and_queue(
            eng, queue_root=queue_root, entity_graph_root=entity_root
        )
        assert first.promotion_paths, "fixture unreachable — nothing was promoted"

        polished = first.promotion_paths[0]
        sentinel = "OPERATOR-POLISHED BODY — MUST SURVIVE RE-EXTRACTION"
        polished.write_text(sentinel, encoding="utf-8")

        second = extract_and_queue(
            eng, queue_root=queue_root, entity_graph_root=entity_root
        )

        assert polished.read_text(encoding="utf-8") == sentinel
        assert polished in second.skipped_existing
        assert polished not in second.promotion_paths

    def test_queue_record_is_still_written_when_promotion_is_skipped(
        self, queue_root: Path, entity_root: Path
    ) -> None:
        """Refusing to clobber must not lose the candidate."""
        eng = build_nova_construction_engagement()
        extract_and_queue(eng, queue_root=queue_root, entity_graph_root=entity_root)
        second = extract_and_queue(
            eng, queue_root=queue_root, entity_graph_root=entity_root
        )
        assert second.skipped_existing
        assert second.queue_paths, "the queue record is the operator's recovery path"

    def test_underivable_claim_blocks_promotion_instead_of_truncating(
        self, monkeypatch: pytest.MonkeyPatch, queue_root: Path, entity_root: Path
    ) -> None:
        """`derive_core_claim` returning None is promotion-blocking (BRO-1983).

        The previous code truncated to `sentence[:139] + "…"`, which the
        linter rejects as a hard ERROR.
        """
        import core.extraction.pipeline as pipeline

        monkeypatch.setattr(pipeline, "_derive_core_claim", lambda c: None)
        eng = build_nova_construction_engagement()
        result = extract_and_queue(
            eng, queue_root=queue_root, entity_graph_root=entity_root
        )

        assert result.unpromotable, "nothing was blocked — the guard is inert"
        assert result.promotion_paths == []
        assert not list(entity_root.rglob("*.md"))
        assert result.queue_paths, "blocked candidates must still be queued"

    def test_promoted_pages_are_status_candidate_not_active(
        self, queue_root: Path, entity_root: Path
    ) -> None:
        """A stub entering the graph as `active` would bypass operator review."""
        import yaml

        eng = build_nova_construction_engagement()
        result = extract_and_queue(
            eng, queue_root=queue_root, entity_graph_root=entity_root
        )
        assert result.promotion_paths
        for page in result.promotion_paths:
            fm = yaml.safe_load(page.read_text(encoding="utf-8").split("---", 2)[1])
            assert fm["status"] == "candidate"


class TestPromotedPageContent:
    """The edge no unit test in this repo can close: what lands on disk.

    A P20 mutation proved this edge was open — making `extract_and_queue`
    render a hardcoded `"Placeholder claim."` instead of the derived claim
    left all 500 tests green. The unit test that claimed to cover it computed
    the claim, passed it into the renderer, and asserted the output equalled
    it: a tautology. This reads the promoted file back off disk.
    """

    def test_promoted_page_carries_the_derived_claim(
        self, queue_root: Path, entity_root: Path
    ) -> None:
        import yaml

        from core.extraction.pipeline import _derive_core_claim, extract_and_queue

        eng = build_nova_construction_engagement()
        result = extract_and_queue(
            eng, queue_root=queue_root, entity_graph_root=entity_root
        )
        assert result.promotion_paths, "fixture unreachable — nothing was promoted"

        checked = 0
        for page in result.promotion_paths:
            fm = yaml.safe_load(page.read_text(encoding="utf-8").split("---", 2)[1])
            claim = fm["core_claim"]
            # The page's own body is what the claim was derived from.
            body = page.read_text(encoding="utf-8").split("## Pattern (anonymized)")[1]
            body = body.split("##")[0].strip()

            class _C:
                content = body
                title = fm["title"]
                slug = page.stem

            expected = _derive_core_claim(_C())
            if expected is None:
                continue
            assert claim == expected, f"{page.name}: page claim is not the derived one"
            checked += 1

        assert checked > 0, "no promoted page exercised the derivation"


class TestOperatorSummary:
    """The refusals must be legible to the operator, not just to the model.

    Before this, a re-run over a populated graph printed
        Total candidates: 6 / Promoted: 0 / Queued for review (score <5/9): 0
    -- six candidates and six queue writes, reported as nothing.
    """

    def test_skipped_pages_are_reported_not_swallowed(
        self, queue_root: Path, entity_root: Path
    ) -> None:
        eng = build_nova_construction_engagement()
        extract_and_queue(eng, queue_root=queue_root, entity_graph_root=entity_root)
        result = extract_and_queue(
            eng, queue_root=queue_root, entity_graph_root=entity_root
        )
        assert result.skipped_existing, "fixture unreachable — nothing was skipped"

        import click.testing

        from runners.cli.commands.bookkeep import _print_summary

        runner = click.testing.CliRunner()
        with runner.isolation() as (out, _err, _):
            _print_summary(result, dry_run=False)
        text = out.getvalue().decode()
        assert "Already on disk" in text, text
        assert str(len(result.skipped_existing)) in text

    def test_unpromotable_is_not_labelled_as_a_low_score(
        self, monkeypatch: pytest.MonkeyPatch, queue_root: Path, entity_root: Path
    ) -> None:
        """They scored >=5; printing them under "score <5/9" states a falsehood."""
        import core.extraction.pipeline as pipeline

        monkeypatch.setattr(pipeline, "_derive_core_claim", lambda c: None)
        result = extract_and_queue(
            build_nova_construction_engagement(),
            queue_root=queue_root,
            entity_graph_root=entity_root,
        )
        assert result.unpromotable, "fixture unreachable — nothing was blocked"

        import click.testing

        from runners.cli.commands.bookkeep import _print_summary

        runner = click.testing.CliRunner()
        with runner.isolation() as (out, _err, _):
            _print_summary(result, dry_run=False)
        text = out.getvalue().decode()
        low = [ln for ln in text.splitlines() if "score <5/9" in ln][0]
        assert low.strip().endswith("0"), f"unpromotable leaked into the low-score line: {low}"
        assert "No self-contained claim" in text, text

    # DELETED: test_dry_run_predicts_the_real_run_over_a_populated_graph.
    #
    # It built its own symlink mirror inline and called extract_and_queue
    # directly, never invoking `bookkeep` -- so it tested a re-implementation
    # of the dry-run block rather than the block itself, and passed while the
    # real command wrote 6 pages into the live knowledge graph. A gate that
    # re-implements the code under test is why that shipped.
    #
    # The prediction gap it described is real and now documented as a known
    # limitation in bookkeep.py; the safe fix (a read-only existence oracle)
    # is an API change and belongs in its own PR.
