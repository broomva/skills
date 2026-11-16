"""Apple Health source — imports the iPhone's "Export All Health Data" archive.

Apple Health has no API off the phone. The owner exports it once (Health app →
profile picture → Export All Health Data), moves ``export.zip`` to this Mac, and
puts it in ``<data_dir>/exports/apple_health/`` (or sets
``[apple_health] export_path``). ``health backfill --source apple_health``
then stream-parses it over the requested window: nothing is extracted to disk
and nothing leaves the machine.

The export holds every app and device that ever wrote to Health (Apple Watch,
Oura, Whoop, Withings, phone step counts, ...). Each sample keeps its producer:
``device`` gets the manufacturer and model, ``metadata`` the writing app
(``source_name``) and its version. Mixing producers is a projection decision,
never an import one (``References/healthkit-data-model.md``).

Apple's HRV is SDNN, Garmin's and Oura's are RMSSD. They are different
statistics and are stored under different metric codes; never compare them
directly.
"""

from __future__ import annotations

import logging
import re
import zipfile
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import IO, Any, Final
from xml.etree import ElementTree as ET

from broomva_health.config.paths import HealthPaths
from broomva_health.domain.device import Device
from broomva_health.domain.errors import SourceUnavailable
from broomva_health.domain.metrics import MetricCode
from broomva_health.domain.results import BackfillResult, SourceStatus, SyncResult
from broomva_health.domain.samples import CategorySample, QuantitySample
from broomva_health.domain.source import Source
from broomva_health.domain.time import utc_now
from broomva_health.ports.mfa import MFAProvider
from broomva_health.ports.rate_limiter import RateLimiter
from broomva_health.ports.repository import TraceRepository
from broomva_health.ports.token_store import TokenStore

__all__ = ["AppleHealthTraceSource", "find_export", "iter_samples"]

logger = logging.getLogger(__name__)

_BATCH: Final = 5000
_HK = "HKQuantityTypeIdentifier"

# HealthKit unit -> factor to the canonical unit (None: unit not convertible, skip).
_Conv = Callable[[float, str], float | None]


def _same(units: dict[str, float]) -> _Conv:
    return lambda v, u: v * units[u] if u in units else None


_BPM = _same({"count/min": 1.0})
_MS = _same({"ms": 1.0})
_COUNT = _same({"count": 1.0})
_KCAL = _same({"kcal": 1.0, "Cal": 1.0, "kJ": 1 / 4.184})
_METRES = _same({"m": 1.0, "km": 1000.0, "cm": 0.01, "mi": 1609.344, "ft": 0.3048, "yd": 0.9144})
_KG = _same({"kg": 1.0, "g": 0.001, "lb": 0.45359237, "st": 6.35029318})
_FRACTION_PCT = _same({"%": 100.0})  # HealthKit stores percentages as 0-1 fractions in "%"
_MMHG = _same({"mmHg": 1.0})
_VO2 = _same({"mL/min·kg": 1.0, "ml/(kg*min)": 1.0, "mL/(kg·min)": 1.0})
_GLUCOSE = _same({"mg/dL": 1.0, "mmol<180.1558800000541>/L": 18.0156, "mmol/L": 18.0156})

QUANTITY_MAP: Final[dict[str, tuple[MetricCode, str, _Conv]]] = {
    f"{_HK}HeartRate": (MetricCode.HEART_RATE, "bpm", _BPM),
    f"{_HK}RestingHeartRate": (MetricCode.RESTING_HEART_RATE, "bpm", _BPM),
    f"{_HK}HeartRateVariabilitySDNN": (MetricCode.HR_VARIABILITY_SDNN, "ms", _MS),
    f"{_HK}RespiratoryRate": (MetricCode.RESPIRATION_RPM, "rpm", _BPM),
    f"{_HK}OxygenSaturation": (MetricCode.SPO2_PCT, "%", _FRACTION_PCT),
    f"{_HK}StepCount": (MetricCode.STEPS, "count", _COUNT),
    f"{_HK}FlightsClimbed": (MetricCode.FLOORS_CLIMBED, "count", _COUNT),
    f"{_HK}ActiveEnergyBurned": (MetricCode.ACTIVE_KCAL, "kcal", _KCAL),
    f"{_HK}BasalEnergyBurned": (MetricCode.BASAL_KCAL, "kcal", _KCAL),
    f"{_HK}DistanceWalkingRunning": (MetricCode.DISTANCE_M, "m", _METRES),
    f"{_HK}BodyMass": (MetricCode.WEIGHT_KG, "kg", _KG),
    f"{_HK}LeanBodyMass": (MetricCode.LEAN_MASS_KG, "kg", _KG),
    f"{_HK}BodyFatPercentage": (MetricCode.BODY_FAT_PCT, "%", _FRACTION_PCT),
    f"{_HK}BodyMassIndex": (MetricCode.BMI, "kg/m^2", _same({"count": 1.0})),
    f"{_HK}VO2Max": (MetricCode.VO2_MAX, "ml/kg/min", _VO2),
    f"{_HK}BloodPressureSystolic": (MetricCode.BLOOD_PRESSURE_SYSTOLIC, "mmHg", _MMHG),
    f"{_HK}BloodPressureDiastolic": (MetricCode.BLOOD_PRESSURE_DIASTOLIC, "mmHg", _MMHG),
    f"{_HK}BloodGlucose": (MetricCode.GLUCOSE_MG_DL, "mg/dL", _GLUCOSE),
    f"{_HK}DietaryWater": (
        MetricCode.HYDRATION_ML,
        "ml",
        _same({"mL": 1.0, "L": 1000.0, "fl_oz_us": 29.5735}),
    ),
}

SLEEP_TYPE: Final = "HKCategoryTypeIdentifierSleepAnalysis"
SLEEP_STAGES: Final[dict[str, str]] = {
    "HKCategoryValueSleepAnalysisInBed": "in_bed",
    "HKCategoryValueSleepAnalysisAsleep": "asleep",
    "HKCategoryValueSleepAnalysisAsleepUnspecified": "asleep",
    "HKCategoryValueSleepAnalysisAsleepCore": "light",
    "HKCategoryValueSleepAnalysisAsleepDeep": "deep",
    "HKCategoryValueSleepAnalysisAsleepREM": "rem",
    "HKCategoryValueSleepAnalysisAwake": "awake",
}

# A value runs to the next ", key:" (hardware ids like "Watch6,1" carry commas).
_DEVICE_FIELD = re.compile(r"(\w+):(.*?)(?=, \w+:|>\s*$|$)")


def parse_device(raw: str | None) -> Device | None:
    """``<<HKDevice: 0x..>, name:Apple Watch, manufacturer:Apple Inc., model:Watch, ...>``."""
    if not raw:
        return None
    fields = {k: v.strip() for k, v in _DEVICE_FIELD.findall(raw)}
    manufacturer = fields.get("manufacturer") or fields.get("name")
    if not manufacturer:
        return None
    return Device(
        manufacturer=manufacturer,
        product=fields.get("hardware") or fields.get("model") or fields.get("name"),
        software_version=fields.get("software"),
    )


def parse_ts(raw: str) -> datetime:
    """Export timestamps look like ``2024-03-01 23:14:05 -0500``."""
    return datetime.strptime(raw, "%Y-%m-%d %H:%M:%S %z")


def _local_day(raw: str) -> date:
    return date.fromisoformat(raw[:10])


@contextmanager
def open_export(path: Path) -> Iterator[IO[bytes]]:
    """Yield the export XML stream, from ``export.zip`` or an extracted ``.xml``.

    Apple localises the XML's file name, so inside a zip the HealthData document
    is found by content: the first non-CDA ``.xml`` member whose root is
    ``<HealthData``.
    """
    if path.suffix.lower() != ".zip":
        with path.open("rb") as fh:
            yield fh
        return
    with zipfile.ZipFile(path) as zf:
        names = [n for n in zf.namelist() if n.lower().endswith(".xml") and "cda" not in n.lower()]
        for name in sorted(names, key=lambda n: -zf.getinfo(n).file_size):
            with zf.open(name) as probe:
                if b"<HealthData" in probe.read(64 * 1024):
                    with zf.open(name) as fh:
                        yield fh
                    return
    raise SourceUnavailable(f"no Apple Health export XML inside {path.name}")


def iter_samples(
    stream: IO[bytes], *, start: date, end: date
) -> Iterator[QuantitySample | CategorySample]:
    """Stream-parse ``<Record>`` elements whose local start day is in ``[start, end]``."""
    # Exports run to gigabytes: drop every finished top-level element from the
    # root, or the tree keeps millions of empty nodes alive.
    # S314: this is the owner's own local export; expat >= 2.4.1 caps entity
    # expansion and never fetches external entities.
    root = None
    for event, elem in ET.iterparse(stream, events=("start", "end")):  # noqa: S314
        if root is None:
            root = elem
            continue
        if event != "end" or elem.tag != "Record":
            if event == "end" and elem.tag in (
                "Workout",
                "ActivitySummary",
                "ClinicalRecord",
                "Correlation",
                "Me",
                "ExportDate",
            ):
                root.clear()
            continue
        try:
            sample = _to_sample(elem.attrib, start=start, end=end)
        except (ValueError, KeyError) as exc:
            logger.debug("apple_health: skipped a record: %s", exc)
            sample = None
        root.clear()
        if sample is not None:
            yield sample


def _to_sample(
    a: dict[str, str], *, start: date, end: date
) -> QuantitySample | CategorySample | None:
    kind = a.get("type", "")
    if kind not in QUANTITY_MAP and kind != SLEEP_TYPE:
        return None
    day = _local_day(a["startDate"])
    if day < start or day > end:
        return None
    common: dict[str, Any] = {
        "source": Source.APPLE_HEALTH,
        "device": parse_device(a.get("device")),
        "start_ts": parse_ts(a["startDate"]),
        "end_ts": parse_ts(a["endDate"]),
        "metadata": {
            k: v
            for k, v in (
                ("source_name", a.get("sourceName")),
                ("source_version", a.get("sourceVersion")),
                ("hk_type", kind),
            )
            if v
        },
    }
    if kind == SLEEP_TYPE:
        stage = SLEEP_STAGES.get(a.get("value", ""))
        if stage is None:
            return None
        return CategorySample(metric=MetricCode.SLEEP_STAGE, category=stage, **common)
    metric, unit, conv = QUANTITY_MAP[kind]
    value = conv(float(a["value"]), a.get("unit", ""))
    if value is None:
        logger.debug("apple_health: unit %r not convertible for %s", a.get("unit"), kind)
        return None
    return QuantitySample(metric=metric, value=value, unit=unit, **common)


def find_export(paths: HealthPaths, configured: str | None = None) -> Path | None:
    """The configured export, else the newest ``.zip``/``.xml`` in ``exports/apple_health/``."""
    if configured:
        p = Path(configured).expanduser()
        return p if p.is_file() else None
    folder = paths.exports_dir / "apple_health"
    if not folder.is_dir():
        return None
    found = [p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in (".zip", ".xml")]
    return max(found, key=lambda p: p.stat().st_mtime) if found else None


class AppleHealthTraceSource:
    """File-based TraceSource: no auth, no network, no rate limit."""

    def __init__(self, *, paths: HealthPaths, export_path: str | None = None) -> None:
        self._paths = paths
        self._configured = export_path

    @property
    def name(self) -> Source:
        return Source.APPLE_HEALTH

    def _export(self) -> Path:
        path = find_export(self._paths, self._configured)
        if path is None:
            where = self._configured or str(self._paths.exports_dir / "apple_health")
            raise SourceUnavailable(
                f"no Apple Health export found at {where}. On the iPhone: Health → profile → "
                "Export All Health Data, then put export.zip there."
            )
        return path

    def authenticate(
        self,
        *,
        token_store: TokenStore,
        mfa: MFAProvider,
        email: str | None = None,
        password: str | None = None,
        profile: str = "default",
    ) -> None:
        """Nothing to authenticate: the export is a local file."""

    def backfill(
        self,
        *,
        repo: TraceRepository,
        token_store: TokenStore,  # noqa: ARG002
        rate_limiter: RateLimiter,  # noqa: ARG002
        start: date,
        end: date,
        profile: str = "default",  # noqa: ARG002
    ) -> BackfillResult:
        if end < start:
            raise SourceUnavailable(
                f"backfill end ({end.isoformat()}) precedes start ({start.isoformat()})"
            )
        n = self._ingest(repo, start, end)
        return BackfillResult(
            source=self.name,
            range_start=start,
            range_end=end,
            samples_ingested=n,
            workouts_ingested=0,
        )

    def sync(
        self,
        *,
        repo: TraceRepository,
        token_store: TokenStore,  # noqa: ARG002
        rate_limiter: RateLimiter,  # noqa: ARG002
        since: datetime | None = None,
        profile: str = "default",  # noqa: ARG002
    ) -> SyncResult:
        """Re-read the export from ``since`` (or from the last stored sample) to today."""
        started = utc_now()
        if since is None:
            since = repo.last_sample_ts(self.name, MetricCode.HEART_RATE)
        # The cursor is UTC but the window is the record's local day: back off a
        # day so evening samples west of UTC are not skipped (upserts are idempotent).
        start = since.date() - timedelta(days=1) if since else date(2000, 1, 1)
        n = self._ingest(repo, start, started.date())
        return SyncResult(
            source=self.name,
            started_at=started,
            finished_at=utc_now(),
            samples_ingested=n,
            workouts_ingested=0,
        )

    def status(self, *, token_store: TokenStore, profile: str = "default") -> SourceStatus:  # noqa: ARG002
        path = find_export(self._paths, self._configured)
        return SourceStatus(
            source=self.name,
            token_valid=path is not None,
            last_error=None if path else "no Apple Health export file",
        )

    def _ingest(self, repo: TraceRepository, start: date, end: date) -> int:
        quantity: list[QuantitySample] = []
        category: list[CategorySample] = []
        total = 0

        def flush() -> int:
            n = (repo.upsert_quantity(quantity) if quantity else 0) + (
                repo.upsert_category(category) if category else 0
            )
            quantity.clear()
            category.clear()
            return n

        path = self._export()
        try:
            with open_export(path) as stream:
                for s in iter_samples(stream, start=start, end=end):
                    (quantity if isinstance(s, QuantitySample) else category).append(s)  # type: ignore[arg-type]
                    if len(quantity) + len(category) >= _BATCH:
                        total += flush()
        except (zipfile.BadZipFile, zipfile.LargeZipFile, ET.ParseError, OSError, EOFError) as exc:
            # Samples flushed before the fault stay (idempotent); re-export and re-run.
            raise SourceUnavailable(
                f"Apple Health export {path.name} is unreadable ({type(exc).__name__}: {exc}); "
                "export it again from the iPhone"
            ) from exc
        return total + flush()
