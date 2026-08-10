"""Tests for the opt-in, warning-only temporal-drift audit."""

import json
from datetime import date
from pathlib import Path

import bookkeeping
from bookkeeping import _lint_temporal_drift


AUDIT_DATE = date(2026, 8, 9)


def _fields(errors):
    return [error.field for error in errors]


def _lint(frontmatter, body=""):
    return _lint_temporal_drift(
        "entity.md",
        frontmatter,
        body,
        audit_date=AUDIT_DATE,
    )


def test_updated_before_newest_source_or_body_date_warns():
    errors = _lint(
        {
            "updated": "2026-06-01",
            "sources": ["Decision report recorded 2026-06-26"],
        },
        "The implementation was independently checked on 2026-07-07.",
    )

    temporal = [error for error in errors if error.field == "temporal_updated"]
    assert len(temporal) == 1
    assert "2026-06-01" in temporal[0].message
    assert "2026-07-07" in temporal[0].message


def test_updated_equal_to_or_newer_than_evidence_is_clean():
    assert _lint(
        {"updated": "2026-07-07", "sources": ["Report dated 2026-06-26"]},
        "Validated 2026-07-07.",
    ) == []


def test_missing_updated_is_not_promoted_into_a_new_schema_requirement():
    assert _lint(
        {"sources": ["Report dated 2026-07-07"]},
        "Historical observation recorded 2026-07-07.",
    ) == []


def test_invalid_and_future_content_dates_do_not_make_updated_stale():
    assert _lint(
        {
            "updated": "2026-08-09",
            "sources": ["Invalid 2026-99-99; planned 2027-01-01"],
        },
        "No eligible later date.",
    ) == []


def test_catalog_visible_current_state_claim_needs_inline_as_of_date():
    errors = _lint({
        "updated": "2026-08-09",
        "core_claim": "Base MCP is now a hosted remote service.",
    })

    assert "temporal_as_of" in _fields(errors)


def test_dated_current_state_claim_is_clean():
    assert _lint({
        "updated": "2026-08-09",
        "core_claim": "As of 2026-08-09, Base MCP is now a hosted remote service.",
    }) == []


def test_mutable_heading_accepts_date_in_heading_or_first_content_line():
    undated = _lint(
        {"updated": "2026-08-09"},
        "## Open follow-ups\n\nM3 still needs a storage decision.\n",
    )
    assert "temporal_as_of" in _fields(undated)

    assert _lint(
        {"updated": "2026-08-09"},
        "## Open follow-ups\n\nAs of 2026-08-09, only M3 remains.\n",
    ) == []
    assert _lint(
        {"updated": "2026-08-09"},
        "## Status — 2026-08-09\n\nM3 remains planned.\n",
    ) == []


def test_explicit_mutable_label_needs_same_line_date():
    errors = _lint(
        {"updated": "2026-08-09"},
        "**Current state**: embedded mode is the default.\n",
    )
    assert "temporal_as_of" in _fields(errors)

    assert _lint(
        {"updated": "2026-08-09"},
        "**Current state (2026-08-09)**: embedded mode is the default.\n",
    ) == []


def test_false_positive_prone_language_stays_out_of_scope():
    errors = _lint(
        {
            "updated": "2026-08-09",
            "core_claim": (
                "A gitignored fixture can make CI green while the shipped "
                "artifact is broken."
            ),
        },
        "## Open Questions\n\nWhat is the stable abstraction?\n\n"
        "## Status quo bias\n\nThis is a conceptual heading.\n\n"
        "## Current research literature\n\nThis is not a live-state label.\n\n"
        "A superseded record can still matter to a counterfactual.\n",
    )
    assert errors == []


def test_temporal_findings_are_warning_only():
    errors = _lint(
        {
            "updated": "2026-06-01",
            "sources": ["New evidence 2026-07-01"],
            "core_claim": "The service is now remote.",
        },
        "## Open decision\n\nChoose the authority.\n",
    )

    assert errors
    assert all(error.severity == "warning" for error in errors)


def test_cli_temporal_flag_is_explicit_opt_in():
    parser = bookkeeping.build_parser()

    assert parser.parse_args(["lint", "--all"]).temporal is False
    assert parser.parse_args(["lint", "--all", "--temporal"]).temporal is True


def test_calibration_receipt_is_machine_readable_and_internally_consistent():
    receipt_path = (
        Path(__file__).parents[1]
        / "references"
        / "temporal-drift-calibration-2026-08-09.json"
    )
    receipt = json.loads(receipt_path.read_text())
    result = receipt["result"]

    assert receipt["source_commit"] == (
        "f4e04b4519f43bf39f18684bf86f079538a84be9"
    )
    assert result["temporal_findings"] == sum(result["by_field"].values())
    assert result["affected_entities"] <= result["entity_pages"]
    assert result["all_findings_warning"] is True
    assert receipt["command_contract"]["exit_status"] == 0
