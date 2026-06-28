"""Canonical metric codes + unit registry.

Each metric code has exactly one canonical unit. Adapters that receive a
sample in a different unit MUST convert at the adapter boundary BEFORE
constructing the domain sample.
"""

from __future__ import annotations

from enum import StrEnum
from types import MappingProxyType
from typing import Final

__all__ = ["METRIC_UNITS", "MetricCode"]


class MetricCode(StrEnum):
    """Canonical metric identifiers.

    Naming convention: SCREAMING_SNAKE_CASE for the member, lower_snake_case
    for the string value (matches SQL column convention). Add new metrics by
    appending; never rename a string value without a migration.
    """

    # Heart
    HEART_RATE = "heart_rate"
    RESTING_HEART_RATE = "resting_heart_rate"
    HRV_OVERNIGHT = "hrv_overnight"
    HR_VARIABILITY_RMSSD = "hr_variability_rmssd"

    # Energy / activity
    STEPS = "steps"
    FLOORS_CLIMBED = "floors_climbed"
    ACTIVE_KCAL = "active_kcal"
    BASAL_KCAL = "basal_kcal"
    DISTANCE_M = "distance_m"
    ACTIVE_SECONDS = "active_seconds"

    # Body
    WEIGHT_KG = "weight_kg"
    BODY_FAT_PCT = "body_fat_pct"
    LEAN_MASS_KG = "lean_mass_kg"
    BMI = "bmi"

    # Composite metrics (often vendor-proprietary)
    BODY_BATTERY = "body_battery"
    TRAINING_READINESS = "training_readiness"
    TRAINING_STATUS = "training_status"
    STRESS = "stress"
    VO2_MAX = "vo2_max"
    FITNESS_AGE = "fitness_age"
    TRAINING_LOAD_CTL = "training_load_ctl"  # synthesis-derived
    TRAINING_LOAD_ATL = "training_load_atl"  # synthesis-derived
    TRAINING_LOAD_TSB = "training_load_tsb"  # synthesis-derived

    # Sleep
    SLEEP_DURATION = "sleep_duration"
    SLEEP_SCORE = "sleep_score"
    SLEEP_STAGE = "sleep_stage"  # category sample
    SLEEP_DEBT = "sleep_debt"

    # Respiration / SpO2
    RESPIRATION_RPM = "respiration_rpm"
    SPO2_PCT = "spo2_pct"

    # Hydration / nutrition
    HYDRATION_ML = "hydration_ml"

    # Blood pressure (correlation: systolic + diastolic + pulse)
    BLOOD_PRESSURE = "blood_pressure"
    BLOOD_PRESSURE_SYSTOLIC = "blood_pressure_systolic"
    BLOOD_PRESSURE_DIASTOLIC = "blood_pressure_diastolic"

    # Women's health
    MENSTRUAL_FLOW = "menstrual_flow"  # category sample
    CYCLE_PHASE = "cycle_phase"  # category sample

    # Glucose
    GLUCOSE_MG_DL = "glucose_mg_dl"


METRIC_UNITS: Final[MappingProxyType[MetricCode, str]] = MappingProxyType(
    {
        MetricCode.HEART_RATE: "bpm",
        MetricCode.RESTING_HEART_RATE: "bpm",
        MetricCode.HRV_OVERNIGHT: "ms",
        MetricCode.HR_VARIABILITY_RMSSD: "ms",
        MetricCode.STEPS: "count",
        MetricCode.FLOORS_CLIMBED: "count",
        MetricCode.ACTIVE_KCAL: "kcal",
        MetricCode.BASAL_KCAL: "kcal",
        MetricCode.DISTANCE_M: "m",
        MetricCode.ACTIVE_SECONDS: "s",
        MetricCode.WEIGHT_KG: "kg",
        MetricCode.BODY_FAT_PCT: "%",
        MetricCode.LEAN_MASS_KG: "kg",
        MetricCode.BMI: "kg/m^2",
        MetricCode.BODY_BATTERY: "score_0_100",
        MetricCode.TRAINING_READINESS: "score_0_100",
        MetricCode.TRAINING_STATUS: "category",
        MetricCode.STRESS: "score_0_100",
        MetricCode.VO2_MAX: "ml/kg/min",
        MetricCode.FITNESS_AGE: "years",
        MetricCode.TRAINING_LOAD_CTL: "tss/day",
        MetricCode.TRAINING_LOAD_ATL: "tss/day",
        MetricCode.TRAINING_LOAD_TSB: "tss/day",
        MetricCode.SLEEP_DURATION: "s",
        MetricCode.SLEEP_SCORE: "score_0_100",
        MetricCode.SLEEP_STAGE: "category",
        MetricCode.SLEEP_DEBT: "s",
        MetricCode.RESPIRATION_RPM: "rpm",
        MetricCode.SPO2_PCT: "%",
        MetricCode.HYDRATION_ML: "ml",
        MetricCode.BLOOD_PRESSURE: "mmHg",
        MetricCode.BLOOD_PRESSURE_SYSTOLIC: "mmHg",
        MetricCode.BLOOD_PRESSURE_DIASTOLIC: "mmHg",
        MetricCode.MENSTRUAL_FLOW: "category",
        MetricCode.CYCLE_PHASE: "category",
        MetricCode.GLUCOSE_MG_DL: "mg/dL",
    }
)


def canonical_unit(metric: MetricCode) -> str:
    """Return the canonical unit for a metric. Raises KeyError if missing."""
    return METRIC_UNITS[metric]
