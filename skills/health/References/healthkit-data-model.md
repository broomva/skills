# HealthKit data model — why our sample types are shaped this way

## The decision

The Health skill's domain layer is shaped on **Apple HealthKit's `HKSample` hierarchy**:

| Our domain type | HealthKit equivalent | Use |
|---|---|---|
| `QuantitySample` | `HKQuantitySample` | Single numeric value over an interval (HR, steps, weight, VO2max) |
| `CategorySample` | `HKCategorySample` | Categorical state over an interval (sleep stage, menstrual flow, cycle phase) |
| `CorrelationSample` | `HKCorrelationSample` | Composite where multiple values must travel together (blood pressure: systolic + diastolic + pulse) |
| `Workout` | `HKWorkout` | A top-level activity container with derived per-second sample streams |

This is **not** a coincidence and **not** an Apple-fan choice. HealthKit's shape is what 17 years of Apple HealthKit field experience has settled on as the right vocabulary for personal health data, and adopting it gives us three things for free:

1. **A clean future Apple Health adapter** — the v2 Apple Health adapter is a thin translation from `HKSample` → our domain type. Zero impedance.
2. **The right shape for non-Apple sources too** — Garmin, Whoop, Oura all produce data that fits the three shapes cleanly. The HealthKit grammar generalizes.
3. **Reconciliation as projection** — see below.

---

## Reconciliation is a projection, not a column

Multiple sources can record the "same" metric. If Garmin says my RHR at 6 AM was 51 and Apple Watch (via HealthKit) says 53, **which one wins?**

The wrong answer is to store a `is_primary` column or a `reconciled_value` field. That's:
- a data-loss decision baked into the trace
- a moving target as adapter-priority rules evolve
- a violation of the trace store's append-only invariant

The right answer is what HealthKit itself does: **store everything with provenance**, and answer "which one wins" as a *projection above the trace*. Sample rows carry:
- `source` — the integration (Garmin, Apple, Whoop, Oura, …)
- `device` — the wearable / sensor / app metadata (optional)
- `metadata` — source-specific extras (raw vendor flags)

Reconciliation rules (e.g. "for `RESTING_HEART_RATE`, prefer Garmin over Apple over Whoop") live in the **projection layer**, not the trace layer. When the rule changes, you re-project; you do not migrate data.

The `DailyProjection.sources_synced` field is a *projection artifact* — it records which sources contributed to today's note, not which source "owns" the day.

---

## The Dogsheep precedent

[Simon Willison's Dogsheep](https://dogsheep.github.io/) project (active since 2019) is the canonical precedent for this approach in the open-source space. Dogsheep's `healthkit-to-sqlite` tool reads an Apple Health export and writes raw `HKSample` rows into SQLite — provenance preserved, no reconciliation pre-baked, queryable forever.

Our trace store does the same shape, except:
- Multi-source from the start (not Apple-only)
- Per-source DB files for isolation (`~/broomva/health/traces/<source>.db`)
- A separate `synthesis.db` for derived views

References:
- https://dogsheep.github.io/
- https://github.com/dogsheep/healthkit-to-sqlite
- Simon Willison, "Personal Data Warehouses" — https://simonwillison.net/2020/Nov/14/personal-data-warehouses/

---

## Sample shapes in detail

### `QuantitySample`

```python
QuantitySample(
    source=Source.GARMIN,
    device=Device(manufacturer="garmin", product="fenix 7x sapphire solar"),
    metric=MetricCode.HEART_RATE,
    value=64.0,
    unit="bpm",
    start_ts=...,
    end_ts=...,
    metadata={...},
)
```

- `metric` is a `MetricCode` enum member (`HEART_RATE`, `STEPS`, `VO2_MAX`, …)
- `value` is `float`
- `unit` MUST match the canonical unit for that metric (see `METRIC_UNITS` registry in `domain/metrics.py`). Adapters convert at the boundary; the domain only ever sees canonical units.
- `start_ts == end_ts` for instantaneous readings; `start_ts < end_ts` for interval-averaged readings (e.g. average HR over a 30-second window).

### `CategorySample`

```python
CategorySample(
    source=Source.GARMIN,
    metric=MetricCode.SLEEP_STAGE,
    category="deep",
    start_ts=...,
    end_ts=...,
)
```

- `metric` is the *dimension* (`SLEEP_STAGE`, `MENSTRUAL_FLOW`, `CYCLE_PHASE`)
- `category` is the *value* — a free-form string (`"deep"`, `"rem"`, `"awake"`, `"light"` for sleep stages; `"light"`, `"medium"`, `"heavy"` for flow)
- The category vocabulary is documented per-metric in the synthesis layer's reader; we deliberately do **not** lock it down with an enum because vendors disagree on stage labels.

### `CorrelationSample`

```python
CorrelationSample(
    source=Source.MANUAL,
    metric=MetricCode.BLOOD_PRESSURE,
    components={"systolic": 121.0, "diastolic": 78.0, "pulse": 64.0},
    unit_by_component={"systolic": "mmHg", "diastolic": "mmHg", "pulse": "bpm"},
    start_ts=...,
    end_ts=...,
)
```

- For metrics where multiple values must travel together. The clearest case is blood pressure: systolic without diastolic is meaningless.
- `components` and `unit_by_component` MUST have the same key set (model_validator enforces).
- The trace DB stores `components_json` and `units_json` as deterministically-serialized JSON (sort_keys=True) — see `migrations/001_initial.sql`.

### `Workout`

```python
Workout(
    source=Source.GARMIN,
    activity_id="...",
    activity_type="running",
    start_ts=...,
    end_ts=...,
    duration_s=3420,
    distance_m=9600.0,
    kcal=540.0,
    avg_hr=148.0,
    max_hr=178.0,
    training_effect=3.2,
    training_stress_score=82.0,    # Coggan TSS for synthesis
    fit_blob_sha256="...",         # SHA-256 of the original FIT blob, if exported
    raw_summary={...},
)
```

- Idempotency key: `(source, activity_id)`. The activity_id is whatever the source returns and is stable per source.
- Per-second sample streams (HR, power, pace) are stored as `QuantitySample` rows with the activity's `start_ts/end_ts` window. Joining workouts to their streams is a query, not a foreign key — the trace store is intentionally denormalized.
- The raw FIT blob is referenced by `fit_blob_sha256` and lives on disk under `~/broomva/health/exports/<source>/fit/<sha256>.fit`. We keep the original so any future re-projection (different aggregator, different smoothing) reads the source of truth, not a re-derivation.

---

## Frozen, immutable, validated

Every sample type is a **frozen Pydantic v2 model** (`ConfigDict(frozen=True, extra="forbid")`). This gives us:

- **Immutability** — `sample.value = 99` raises. No accidental mutation after construction.
- **`extra="forbid"`** — unknown fields raise at construction time. Catches schema drift early.
- **`str_strip_whitespace=True`** — defensive against vendor-supplied strings with stray whitespace.
- **UTC normalization** — every datetime field goes through `ensure_utc` via a `field_validator`. Naive datetimes raise; non-UTC tz-aware datetimes are converted to UTC. **The trace store sees only UTC.**
- **Interval order** — `end_ts < start_ts` raises (`_interval_ordered` model_validator).

This is the *domain layer's* job — it guarantees that anything reaching the repository is well-formed. The repository doesn't re-validate; it serializes via `.model_dump(mode="json")`.

---

## Unit registry

`MetricCode` has **exactly one canonical unit per metric**. Documented in `domain/metrics.py`:

| Metric category | Examples | Canonical unit |
|---|---|---|
| Heart | HEART_RATE, RESTING_HEART_RATE | `bpm` |
| HRV | HRV_OVERNIGHT, HR_VARIABILITY_RMSSD | `ms` |
| Activity | STEPS, FLOORS_CLIMBED | `count` |
| Energy | ACTIVE_KCAL, BASAL_KCAL | `kcal` |
| Distance | DISTANCE_M | `m` |
| Sleep | SLEEP_DURATION, SLEEP_DEBT | `s` (seconds) |
| Sleep score | SLEEP_SCORE | `score_0_100` |
| Composite vendor scores | BODY_BATTERY, TRAINING_READINESS, STRESS | `score_0_100` |
| VO2max | VO2_MAX | `ml/kg/min` |
| Training load | TRAINING_LOAD_CTL, _ATL, _TSB | `tss/day` |
| Blood pressure | BLOOD_PRESSURE | `mmHg` |
| Glucose | GLUCOSE_MG_DL | `mg/dL` |

Adapters that receive a sample in a different unit **MUST convert at the adapter boundary** before constructing the domain sample. The domain layer never sees a non-canonical unit. If an adapter cannot convert (e.g. an unfamiliar vendor unit), it should raise `SourceUnavailable` — silently storing a mis-unit value is a P20 failure mode.

---

## Schema versioning

- **Sample table schemas** (`quantity_sample`, `category_sample`, `correlation_sample`, `workout`) are versioned via numbered SQL migrations under `src/broomva_health/migrations/`. Additive changes only within v1.x; breaking changes require a major bump and a v→v migration.
- **`DailyProjection.schema_version`** is independent and tracks the *frontmatter shape* exposed to downstream consumers (Obsidian Dataview, healthOS readers). Bumps require coordinated changes to all consumers — see [../Workflows/DailyNote.md](../Workflows/DailyNote.md).
- **`MetricCode` enum members** can be added freely; existing string values must never be renamed without a migration (the string is the on-disk identifier in the `metric` column).

---

## References

- Apple HealthKit Developer Documentation: https://developer.apple.com/documentation/healthkit
- `HKQuantitySample`: https://developer.apple.com/documentation/healthkit/hkquantitysample
- `HKCategorySample`: https://developer.apple.com/documentation/healthkit/hkcategorysample
- `HKCorrelationSample`: https://developer.apple.com/documentation/healthkit/hkcorrelation
- `HKWorkout`: https://developer.apple.com/documentation/healthkit/hkworkout
- Dogsheep: https://dogsheep.github.io/
- `healthkit-to-sqlite`: https://github.com/dogsheep/healthkit-to-sqlite
- Simon Willison, "Personal Data Warehouses": https://simonwillison.net/2020/Nov/14/personal-data-warehouses/
