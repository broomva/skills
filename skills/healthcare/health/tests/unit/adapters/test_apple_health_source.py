"""Tests for AppleHealthTraceSource — the iPhone "Export All Health Data" importer.

Every export here is synthetic, built in the shape Apple writes (an internal
DTD, attribute-only <Record> elements, nested Correlation records, a localised
XML name inside the zip).
"""

from __future__ import annotations

import zipfile
from datetime import UTC, date, datetime
from pathlib import Path

import pytest

from broomva_health.adapters.repositories.sqlite import SQLiteTraceRepository
from broomva_health.adapters.sources._registry import build_sources
from broomva_health.adapters.sources.apple_health import (
    AppleHealthTraceSource,
    find_export,
    iter_samples,
    open_export,
    parse_device,
)
from broomva_health.config.paths import HealthPaths
from broomva_health.config.settings import HealthSettings
from broomva_health.domain.errors import SourceUnavailable
from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.samples import CategorySample, QuantitySample
from broomva_health.domain.source import Source

WATCH = (
    "&lt;&lt;HKDevice: 0x1&gt;, name:Apple Watch, manufacturer:Apple Inc., model:Watch, "
    "hardware:Watch6,1, software:10.0&gt;"
)
RING = "&lt;&lt;HKDevice: 0x2&gt;, name:Oura, manufacturer:Oura Health, model:Gen3&gt;"


def _record(
    kind: str,
    start: str,
    end: str,
    value: str,
    unit: str = "",
    device: str = WATCH,
    source: str = "Test Watch",
) -> str:
    unit_attr = f' unit="{unit}"' if unit else ""
    return (
        f'<Record type="{kind}" sourceName="{source}" sourceVersion="10.0"{unit_attr} '
        f'device="{device}" creationDate="{end}" startDate="{start}" endDate="{end}" value="{value}">'
        '<MetadataEntry key="HKMetadataKeyHeartRateMotionContext" value="0"/></Record>'
    )


HK = "HKQuantityTypeIdentifier"
RECORDS = [
    _record(
        f"{HK}HeartRate",
        "2024-03-01 23:10:00 -0500",
        "2024-03-01 23:10:00 -0500",
        "58",
        "count/min",
    ),
    _record(
        f"{HK}RestingHeartRate",
        "2024-03-02 00:00:00 -0500",
        "2024-03-02 23:59:00 -0500",
        "55",
        "count/min",
    ),
    _record(
        f"{HK}HeartRateVariabilitySDNN",
        "2024-03-02 03:00:00 -0500",
        "2024-03-02 03:01:00 -0500",
        "42.5",
        "ms",
    ),
    _record(
        f"{HK}RespiratoryRate",
        "2024-03-02 03:05:00 -0500",
        "2024-03-02 03:05:00 -0500",
        "13.5",
        "count/min",
        device=RING,
        source="Oura",
    ),
    _record(
        f"{HK}OxygenSaturation",
        "2024-03-02 03:06:00 -0500",
        "2024-03-02 03:06:00 -0500",
        "0.96",
        "%",
    ),
    _record(
        f"{HK}ActiveEnergyBurned",
        "2024-03-02 10:00:00 -0500",
        "2024-03-02 10:05:00 -0500",
        "418.4",
        "kJ",
    ),
    _record(
        f"{HK}BodyMass", "2024-03-02 07:00:00 -0500", "2024-03-02 07:00:00 -0500", "176.37", "lb"
    ),
    _record(
        f"{HK}StepCount", "2024-03-02 09:00:00 -0500", "2024-03-02 09:10:00 -0500", "800", "count"
    ),
    _record(
        f"{HK}StepCount", "2024-03-02 09:20:00 -0500", "2024-03-02 09:30:00 -0500", "5", "furlong"
    ),
    _record(
        "HKCategoryTypeIdentifierSleepAnalysis",
        "2024-03-02 01:00:00 -0500",
        "2024-03-02 02:30:00 -0500",
        "HKCategoryValueSleepAnalysisAsleepDeep",
        device=RING,
        source="Oura",
    ),
    _record(
        "HKCategoryTypeIdentifierSleepAnalysis",
        "2024-03-02 02:30:00 -0500",
        "2024-03-02 03:00:00 -0500",
        "HKCategoryValueSleepAnalysisAsleepREM",
        device=RING,
        source="Oura",
    ),
    _record(
        "HKCategoryTypeIdentifierMindfulSession",
        "2024-03-02 08:00:00 -0500",
        "2024-03-02 08:10:00 -0500",
        "HKCategoryValueNotApplicable",
    ),
    _record(
        f"{HK}HeartRate",
        "2024-03-05 12:00:00 -0500",
        "2024-03-05 12:00:00 -0500",
        "90",
        "count/min",
    ),
]

EXPORT_XML = (
    '<?xml version="1.0" encoding="UTF-8"?>\n'
    "<!DOCTYPE HealthData [\n<!ELEMENT HealthData (ExportDate,Me,(Record|Correlation|Workout)*)>\n"
    "<!ATTLIST Record type CDATA #REQUIRED>\n]>\n"
    '<HealthData locale="en_US"><ExportDate value="2024-03-06 10:00:00 -0500"/>'
    '<Me HKCharacteristicTypeIdentifierDateOfBirth=""/>'
    + "".join(RECORDS)
    + '<Correlation type="HKCorrelationTypeIdentifierBloodPressure" startDate="2024-03-02 08:00:00 -0500" '
    'endDate="2024-03-02 08:00:00 -0500">'
    + _record(
        f"{HK}BloodPressureSystolic",
        "2024-03-02 08:00:00 -0500",
        "2024-03-02 08:00:00 -0500",
        "121",
        "mmHg",
    )
    + _record(
        f"{HK}BloodPressureDiastolic",
        "2024-03-02 08:00:00 -0500",
        "2024-03-02 08:00:00 -0500",
        "78",
        "mmHg",
    )
    + "</Correlation>"
    # Apple's DTD: records inside a Correlation also appear at top level.
    + _record(
        f"{HK}BloodPressureSystolic",
        "2024-03-02 08:00:00 -0500",
        "2024-03-02 08:00:00 -0500",
        "121",
        "mmHg",
    )
    + _record(
        f"{HK}BloodPressureDiastolic",
        "2024-03-02 08:00:00 -0500",
        "2024-03-02 08:00:00 -0500",
        "78",
        "mmHg",
    )
    + '<Workout workoutActivityType="HKWorkoutActivityTypeRunning" duration="30"/>'
    "</HealthData>\n"
)


def _write_zip(path: Path, xml_name: str = "apple_health_export/exportar.xml") -> Path:
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("apple_health_export/export_cda.xml", "<ClinicalDocument/>")
        zf.writestr(xml_name, EXPORT_XML)
    return path


def _samples(path: Path, start: date, end: date) -> list[QuantitySample | CategorySample]:
    with open_export(path) as stream:
        return list(iter_samples(stream, start=start, end=end))


def _by_metric(samples: list[QuantitySample | CategorySample]) -> dict[MetricCode, list]:
    out: dict[MetricCode, list] = {}
    for s in samples:
        out.setdefault(s.metric, []).append(s)
    return out


@pytest.fixture
def export_zip(tmp_path: Path) -> Path:
    return _write_zip(tmp_path / "export.zip")


def test_maps_records_to_canonical_units(export_zip: Path) -> None:
    got = _by_metric(_samples(export_zip, date(2024, 3, 1), date(2024, 3, 2)))
    assert got[MetricCode.HEART_RATE][0].value == 58.0
    assert got[MetricCode.RESTING_HEART_RATE][0].value == 55.0
    assert got[MetricCode.HR_VARIABILITY_SDNN][0].value == 42.5
    assert got[MetricCode.RESPIRATION_RPM][0].value == 13.5
    assert got[MetricCode.SPO2_PCT][0].value == pytest.approx(96.0)
    assert got[MetricCode.ACTIVE_KCAL][0].value == pytest.approx(100.0)
    assert got[MetricCode.WEIGHT_KG][0].value == pytest.approx(80.0, abs=0.01)
    assert got[MetricCode.BLOOD_PRESSURE_SYSTOLIC][0].value == 121.0
    assert got[MetricCode.BLOOD_PRESSURE_DIASTOLIC][0].value == 78.0
    for samples in got.values():
        for s in samples:
            assert s.source is Source.APPLE_HEALTH


def test_unknown_unit_and_unmapped_types_are_skipped(export_zip: Path) -> None:
    got = _by_metric(_samples(export_zip, date(2024, 3, 1), date(2024, 3, 2)))
    assert [s.value for s in got[MetricCode.STEPS]] == [800.0]  # the "furlong" row is dropped
    assert all(
        s.metadata.get("hk_type") != "HKCategoryTypeIdentifierMindfulSession"
        for v in got.values()
        for s in v
    )


def test_sleep_stages_map_and_keep_their_producer(export_zip: Path) -> None:
    stages = _by_metric(_samples(export_zip, date(2024, 3, 2), date(2024, 3, 2)))[
        MetricCode.SLEEP_STAGE
    ]
    assert [s.category for s in stages] == ["deep", "rem"]
    assert stages[0].device is not None
    assert stages[0].device.manufacturer == "Oura Health"
    assert stages[0].metadata["source_name"] == "Oura"
    assert stages[0].end_ts - stages[0].start_ts == datetime(2024, 1, 1, 2, 30) - datetime(
        2024, 1, 1, 1
    )


def test_window_uses_the_local_day_of_the_start(export_zip: Path) -> None:
    only_first = _samples(export_zip, date(2024, 3, 1), date(2024, 3, 1))
    assert [s.metric for s in only_first] == [MetricCode.HEART_RATE]
    assert only_first[0].start_ts == datetime(
        2024, 3, 2, 4, 10, tzinfo=UTC
    )  # 23:10 -0500, stored UTC
    later = _samples(export_zip, date(2024, 3, 5), date(2024, 3, 31))
    assert [s.value for s in later] == [90.0]


def test_plain_xml_export_reads_the_same(tmp_path: Path, export_zip: Path) -> None:
    xml = tmp_path / "export.xml"
    xml.write_text(EXPORT_XML, encoding="utf-8")
    assert len(_samples(xml, date(2024, 1, 1), date(2024, 12, 31))) == len(
        _samples(export_zip, date(2024, 1, 1), date(2024, 12, 31))
    )


def test_zip_without_health_data_is_refused(tmp_path: Path) -> None:
    bad = tmp_path / "export.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.writestr("apple_health_export/export_cda.xml", "<HealthData/>")
        zf.writestr("notes.xml", "<Other/>")
    with pytest.raises(SourceUnavailable), open_export(bad):
        pass


def test_parse_device_handles_partial_fields() -> None:
    d = parse_device(
        "<<HKDevice: 0x1>, name:Apple Watch, manufacturer:Apple Inc., hardware:Watch6,1, software:10.0>"
    )
    assert d is not None
    assert d.manufacturer == "Apple Inc."
    assert d.product == "Watch6,1"
    assert d.software_version == "10.0"
    assert parse_device(None) is None
    assert parse_device("garbage") is None


def test_backfill_writes_through_the_repository_idempotently(tmp_paths: HealthPaths) -> None:
    folder = tmp_paths.exports_dir / "apple_health"
    folder.mkdir(parents=True)
    _write_zip(folder / "export.zip")
    source = AppleHealthTraceSource(paths=tmp_paths)
    repo = SQLiteTraceRepository(tmp_paths.trace_db_for("apple_health"))
    repo.migrate()
    kwargs = {
        "repo": repo,
        "token_store": None,
        "rate_limiter": None,
        "start": date(2024, 3, 1),
        "end": date(2024, 3, 2),
    }
    first = source.backfill(**kwargs)  # type: ignore[arg-type]
    second = source.backfill(**kwargs)  # type: ignore[arg-type]
    assert first.samples_ingested == second.samples_ingested == 12
    hr = repo.query_quantity(
        Source.APPLE_HEALTH,
        MetricCode.HEART_RATE,
        datetime(2024, 3, 1, tzinfo=UTC),
        datetime(2024, 3, 3, tzinfo=UTC),
    )
    assert [s.value for s in hr] == [58.0]
    repo.close()


def test_missing_export_is_a_clear_error(tmp_paths: HealthPaths) -> None:
    source = AppleHealthTraceSource(paths=tmp_paths)
    with pytest.raises(SourceUnavailable, match="Export All Health Data"):
        source.backfill(
            repo=None,
            token_store=None,
            rate_limiter=None,  # type: ignore[arg-type]
            start=date(2024, 1, 1),
            end=date(2024, 1, 2),
        )
    assert source.status(token_store=None).token_valid is False  # type: ignore[arg-type]


def test_find_export_prefers_config_then_newest_valid_file(
    tmp_paths: HealthPaths, tmp_path: Path
) -> None:
    import os

    folder = tmp_paths.exports_dir / "apple_health"
    folder.mkdir(parents=True)
    old, new = _write_zip(folder / "old.zip"), folder / "new.xml"
    new.write_text(EXPORT_XML, encoding="utf-8")
    os.utime(old, (1, 1))
    assert find_export(tmp_paths) == new
    # A newer stray XML that is not a HealthData document is never chosen.
    stray = folder / "notes.xml"
    stray.write_text("<Notes><Record type='x'/></Notes>", encoding="utf-8")
    assert find_export(tmp_paths) == new
    custom = _write_zip(tmp_path / "elsewhere.zip")
    assert find_export(tmp_paths, str(custom)) == custom
    assert find_export(tmp_paths, str(stray)) is None
    assert find_export(tmp_paths, str(tmp_path / "missing.zip")) is None


def test_registry_adds_apple_health_only_when_an_export_exists(
    tmp_paths: HealthPaths, tmp_settings: HealthSettings
) -> None:
    assert Source.APPLE_HEALTH not in build_sources(tmp_settings, tmp_paths)
    folder = tmp_paths.exports_dir / "apple_health"
    folder.mkdir(parents=True)
    _write_zip(folder / "export.zip")
    assert isinstance(
        build_sources(tmp_settings, tmp_paths)[Source.APPLE_HEALTH], AppleHealthTraceSource
    )


def test_documented_type_count_matches_the_map() -> None:
    from broomva_health.adapters.sources.apple_health import QUANTITY_MAP

    assert len(QUANTITY_MAP) == 19  # CHANGELOG and SKILL.md name 19 quantity types


def _mini_export(path: Path, records: list[str]) -> Path:
    xml = '<?xml version="1.0"?><HealthData locale="en_US">' + "".join(records) + "</HealthData>"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("apple_health_export/export.xml", xml)
    return path


def test_registry_skips_a_configured_export_that_no_longer_exists(
    tmp_paths: HealthPaths, tmp_settings: HealthSettings, tmp_path: Path
) -> None:
    settings = tmp_settings.model_copy(
        update={"apple_health": {"export_path": str(tmp_path / "gone.zip")}}
    )
    assert Source.APPLE_HEALTH not in build_sources(settings, tmp_paths)
    _write_zip(tmp_path / "gone.zip")
    assert Source.APPLE_HEALTH in build_sources(settings, tmp_paths)


@pytest.mark.parametrize("content", [b"not a zip at all", None])
def test_corrupt_or_truncated_export_is_a_source_error(
    tmp_paths: HealthPaths, tmp_path: Path, content: bytes | None
) -> None:
    path = tmp_path / "export.zip"
    if content is None:  # a valid zip whose XML is cut off mid-record
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("apple_health_export/export.xml", EXPORT_XML[: len(EXPORT_XML) // 2])
    else:
        path.write_bytes(content)
    repo = SQLiteTraceRepository(tmp_paths.trace_db_for("apple_health"))
    repo.migrate()
    with pytest.raises(SourceUnavailable, match="unreadable"):
        AppleHealthTraceSource(paths=tmp_paths, export_path=str(path)).backfill(
            repo=repo,
            token_store=None,
            rate_limiter=None,  # type: ignore[arg-type]
            start=date(2024, 1, 1),
            end=date(2024, 12, 31),
        )
    repo.close()


def test_two_producers_at_the_same_instant_both_survive(
    tmp_paths: HealthPaths, tmp_path: Path
) -> None:
    hr = f"{HK}HeartRate"
    ts = "2024-05-01 09:00:00 +0000"
    path = _mini_export(
        tmp_path / "x.zip",
        [
            _record(hr, ts, ts, "60", "count/min", source="Watch"),
            _record(hr, ts, ts, "72", "count/min", device=RING, source="Chest strap"),
        ],
    )
    repo = SQLiteTraceRepository(tmp_paths.trace_db_for("apple_health"))
    repo.migrate()
    AppleHealthTraceSource(paths=tmp_paths, export_path=str(path)).backfill(
        repo=repo,
        token_store=None,
        rate_limiter=None,  # type: ignore[arg-type]
        start=date(2024, 5, 1),
        end=date(2024, 5, 1),
    )
    got = repo.query_quantity(
        Source.APPLE_HEALTH,
        MetricCode.HEART_RATE,
        datetime(2024, 5, 1, tzinfo=UTC),
        datetime(2024, 5, 2, tzinfo=UTC),
    )
    assert sorted((s.producer, s.value) for s in got) == [("Chest strap", 72.0), ("Watch", 60.0)]
    repo.close()


def test_records_nested_in_a_correlation_are_not_read_twice(tmp_path: Path) -> None:
    sys_type = f"{HK}BloodPressureSystolic"
    ts = "2024-03-02 08:00:00 -0500"
    nested_only = _mini_export(
        tmp_path / "n.zip",
        [
            f'<Correlation type="HKCorrelationTypeIdentifierBloodPressure" startDate="{ts}" endDate="{ts}">'
            + _record(sys_type, ts, ts, "121", "mmHg")
            + "</Correlation>",
        ],
    )
    assert _samples(nested_only, date(2024, 1, 1), date(2024, 12, 31)) == []


def test_zip_member_is_chosen_by_parsed_root_not_substring(tmp_path: Path) -> None:
    path = tmp_path / "export.zip"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("notes.xml", "<!-- <HealthData --><Notes>" + "x" * 200_000 + "</Notes>")
        zf.writestr("apple_health_export/export.xml", EXPORT_XML)
    assert len(_samples(path, date(2024, 1, 1), date(2024, 12, 31))) > 0


def test_legacy_get_source_knows_apple_health(tmp_paths: HealthPaths) -> None:
    from broomva_health.adapters.sources._registry import get_source

    assert isinstance(get_source(Source.APPLE_HEALTH, paths=tmp_paths), AppleHealthTraceSource)


_BAD_DTD = (
    '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE HealthData [\n'
    "<!ATTLIST RightEye value CDATA>\n"  # invalid: no default declaration (seen in real exports)
    "{pad}]>\n"
)


@pytest.mark.parametrize("pad", ["", "<!-- " + "x" * 200_000 + " -->\n"])
@pytest.mark.parametrize("as_zip", [True, False])
def test_a_malformed_internal_dtd_does_not_block_the_records(
    tmp_path: Path, pad: str, as_zip: bool
) -> None:
    body = '<HealthData locale="en_US">' + RECORDS[0] + "</HealthData>"
    xml = _BAD_DTD.format(pad=pad) + body
    if as_zip:
        path = tmp_path / "export.zip"
        with zipfile.ZipFile(path, "w") as zf:
            zf.writestr("apple_health_export/export.xml", xml)
    else:
        path = tmp_path / "export.xml"
        path.write_text(xml, encoding="utf-8")
    got = _samples(path, date(2024, 1, 1), date(2024, 12, 31))
    assert [s.value for s in got] == [58.0]


def test_an_external_doctype_without_a_subset_is_removed_too(tmp_path: Path) -> None:
    path = tmp_path / "export.xml"
    path.write_text(
        '<?xml version="1.0"?><!DOCTYPE HealthData SYSTEM "x.dtd"><HealthData>'
        + RECORDS[0]
        + "</HealthData>",
        encoding="utf-8",
    )
    assert len(_samples(path, date(2024, 1, 1), date(2024, 12, 31))) == 1


def test_sync_is_a_no_op_and_backfill_is_the_import(tmp_paths: HealthPaths) -> None:
    folder = tmp_paths.exports_dir / "apple_health"
    folder.mkdir(parents=True)
    _write_zip(folder / "export.zip")
    repo = SQLiteTraceRepository(tmp_paths.trace_db_for("apple_health"))
    repo.migrate()
    result = AppleHealthTraceSource(paths=tmp_paths).sync(
        repo=repo,
        token_store=None,  # type: ignore[arg-type]
        rate_limiter=None,  # type: ignore[arg-type]
    )
    assert result.samples_ingested == 0
    assert result.succeeded
    assert not (tmp_paths.traces_dir / "apple_health.import.json").exists()
    repo.close()


def test_same_producer_records_sharing_a_start_all_survive(
    tmp_paths: HealthPaths, tmp_path: Path
) -> None:
    sleep = "HKCategoryTypeIdentifierSleepAnalysis"
    start = "2024-03-01 22:00:00 -0500"
    path = _mini_export(
        tmp_path / "s.zip",
        [
            _record(sleep, start, "2024-03-02 07:00:00 -0500", "HKCategoryValueSleepAnalysisInBed"),
            _record(sleep, start, "2024-03-01 22:20:00 -0500", "HKCategoryValueSleepAnalysisAwake"),
        ],
    )
    repo = SQLiteTraceRepository(tmp_paths.trace_db_for("apple_health"))
    repo.migrate()
    source = AppleHealthTraceSource(paths=tmp_paths, export_path=str(path))
    for _ in range(2):  # a repeat import rewrites the same rows
        source.backfill(
            repo=repo,
            token_store=None,  # type: ignore[arg-type]
            rate_limiter=None,  # type: ignore[arg-type]
            start=date(2024, 3, 1),
            end=date(2024, 3, 2),
        )
    import sqlite3

    rows = (
        sqlite3.connect(tmp_paths.trace_db_for("apple_health"))
        .execute("SELECT category FROM category_sample ORDER BY category")
        .fetchall()
    )
    assert rows == [("awake",), ("in_bed",)]
    repo.close()


def test_a_non_health_root_is_refused_not_imported(tmp_path: Path) -> None:
    path = tmp_path / "export.xml"
    path.write_text(
        "<Notes>"
        + _record(
            f"{HK}HeartRate",
            "2024-03-01 10:00:00 +0000",
            "2024-03-01 10:00:00 +0000",
            "60",
            "count/min",
        )
        + "</Notes>",
        encoding="utf-8",
    )
    with pytest.raises(SourceUnavailable, match="not an Apple Health export"):
        _samples(path, date(2024, 1, 1), date(2024, 12, 31))


def test_a_utf16_export_gets_a_clear_refusal(tmp_path: Path) -> None:
    path = tmp_path / "export.xml"
    path.write_bytes(
        ('<?xml version="1.0" encoding="UTF-16"?>' + EXPORT_XML.split("?>", 1)[1]).encode("utf-16")
    )
    with pytest.raises(SourceUnavailable, match="UTF-16"):
        _samples(path, date(2024, 1, 1), date(2024, 12, 31))


def test_the_same_record_under_another_offset_updates_not_duplicates(
    tmp_paths: HealthPaths, tmp_path: Path
) -> None:
    hr = f"{HK}HeartRate"
    repo = SQLiteTraceRepository(tmp_paths.trace_db_for("apple_health"))
    repo.migrate()
    for i, stamp in enumerate(("2024-04-01 09:00:00 +0000", "2024-04-01 04:00:00 -0500")):
        path = _mini_export(tmp_path / f"{i}.zip", [_record(hr, stamp, stamp, "60", "count/min")])
        AppleHealthTraceSource(paths=tmp_paths, export_path=str(path)).backfill(
            repo=repo,
            token_store=None,  # type: ignore[arg-type]
            rate_limiter=None,  # type: ignore[arg-type]
            start=date(2024, 3, 31),
            end=date(2024, 4, 2),
        )
    got = repo.query_quantity(
        Source.APPLE_HEALTH,
        MetricCode.HEART_RATE,
        datetime(2024, 4, 1, tzinfo=UTC),
        datetime(2024, 4, 2, tzinfo=UTC),
    )
    assert len(got) == 1
    repo.close()
