"""RCS controller — recursive controlled-system wrapper around dispatch.

Implements the L0/L1/L2/L3 hierarchy from the Recursive Controlled Systems
formalization (canonical parameters in research/rcs/data/parameters.toml):

    L0 — plant: base controller dispatches each hour (state → action)
    L1 — autonomic: adapts setpoints (min_soc) per-hour with anti-flap gate
    L2 — meta: proposes parameter mutations, shadow-evaluates on past 7 days
    L3 — governance: caps L2 mutation rate and enforces hard floors

Every level emits structured trace events so the bench runner can compute
per-level Lyapunov decay rates λ̂_k. PR #26 ships heuristic Python only;
PR #27 will replace the L1/L2 heuristics with LLM-as-controller calls.

This file deliberately matches the conventions in ``controllers.py``:
PEP 8, dataclasses for value types, type hints, and rule-based logic that
can be read top-to-bottom.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any

from .controllers import Controller, DispatchAction, RuleBasedController
from .scenario import HourState, SiteProfile

# ---------------------------------------------------------------------------
# Constants — knob defaults exposed for tuning by future PRs.
# ---------------------------------------------------------------------------

# L1 autonomic
L1_ROLLING_WINDOW_H = 24
L1_MIN_SWITCH_INTERVAL_H = 6  # anti-flap gate
L1_LOW_SOC_TREND_THRESHOLD = 35.0  # avg SOC below this for >6h → CONSERVATIVE
L1_LOW_SOC_TREND_DURATION_H = 6
L1_CLEAR_SKY_FRACTION = 0.55  # rolling solar/capacity ratio above this → AGGRESSIVE
L1_SETPOINT_DELTA = 5.0  # ±% min_soc per mode

# L2 meta
L2_DAY_HOURS = 24
L2_LOOKBACK_DAYS = 7
L2_UNSERVED_PER_DAY_THRESHOLD_KWH = 5.0
L2_DIESEL_IMPROVEMENT_FRACTION = 0.05  # 5%
L2_UNSERVED_TOLERANCE = 1.0  # candidate may not regress unserved at all

# L3 governance
L3_WEEK_HOURS = 24 * 7
L3_MAX_MUTATIONS_PER_WEEK = 2
L3_MIN_SOC_FLOOR = 10.0
L3_DIESEL_START_SOC_FLOOR = 15.0


# ---------------------------------------------------------------------------
# Trace event type
# ---------------------------------------------------------------------------


@dataclass
class TraceEvent:
    """One event emitted by the RCS layers.

    The bench runner reads ``trace()`` to compute λ̂_k per level. Each event's
    ``payload`` is a free-form dict describing what changed.
    """

    timestamp: int  # hour of year (0..8759)
    level: int  # 0..3
    kind: str  # 'dispatch', 'l1_mode_switch', 'l2_mutation_*', 'l3_block'
    payload: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "level": self.level,
            "kind": self.kind,
            "payload": dict(self.payload),
        }


# ---------------------------------------------------------------------------
# L1 autonomic — per-hour setpoint adaptation with hysteresis.
# ---------------------------------------------------------------------------


class HysteresisGate:
    """Enforces a minimum interval between mode switches (anti-flapping)."""

    def __init__(self, min_interval_h: int = L1_MIN_SWITCH_INTERVAL_H):
        self.min_interval_h = min_interval_h
        self._last_switch_h: int = -10_000  # far in the past so first switch fires

    def reset(self) -> None:
        self._last_switch_h = -10_000

    def allow(self, current_hour: int) -> bool:
        return (current_hour - self._last_switch_h) >= self.min_interval_h

    def stamp(self, current_hour: int) -> None:
        self._last_switch_h = current_hour


class L1Autonomic:
    """Per-hour setpoint adapter.

    Tracks a 24h rolling window of SOC + solar-available ratio and switches
    the wrapped controller's ``min_soc`` setpoint between three modes:

        BASE          — neutral (uses ``base_min_soc``)
        CONSERVATIVE  — +5% min_soc when SOC trajectory has been low
        AGGRESSIVE    — -5% min_soc when forecast-equivalent shows clear sky

    Anti-flap: at most one mode switch per ``L1_MIN_SWITCH_INTERVAL_H``.
    """

    BASE = "BASE"
    CONSERVATIVE = "CONSERVATIVE"
    AGGRESSIVE = "AGGRESSIVE"

    def __init__(
        self,
        base_min_soc: float,
        site: SiteProfile | None,
        floor: float = L3_MIN_SOC_FLOOR,
    ):
        self.base_min_soc = base_min_soc
        self.site = site
        self.floor = floor
        self.mode = self.BASE
        self.soc_window: deque[float] = deque(maxlen=L1_ROLLING_WINDOW_H)
        self.solar_ratio_window: deque[float] = deque(maxlen=L1_ROLLING_WINDOW_H)
        self.gate = HysteresisGate(L1_MIN_SWITCH_INTERVAL_H)

    def reset(self) -> None:
        self.mode = self.BASE
        self.soc_window.clear()
        self.solar_ratio_window.clear()
        self.gate.reset()

    def update_base(self, base_min_soc: float) -> None:
        """Called by L2 when the underlying setpoint changes via mutation."""
        self.base_min_soc = base_min_soc

    def observe(self, state: HourState) -> None:
        self.soc_window.append(state.battery_soc_pct)
        capacity = self.site.solar_capacity_kwp if self.site else 0.0
        if capacity > 0:
            self.solar_ratio_window.append(state.solar_available_kw / capacity)
        else:
            self.solar_ratio_window.append(0.0)

    def step(self, state: HourState) -> tuple[float, str | None]:
        """Compute the active min_soc and return any mode switch that fired.

        Returns:
            (effective_min_soc, switched_to_mode_or_None)
        """
        self.observe(state)

        # Need a full window before the gate can fire.
        if len(self.soc_window) < L1_LOW_SOC_TREND_DURATION_H:
            return self._effective_min_soc(), None

        # Recent trend: was avg SOC below threshold for the last
        # L1_LOW_SOC_TREND_DURATION_H hours?
        recent_soc = list(self.soc_window)[-L1_LOW_SOC_TREND_DURATION_H:]
        soc_trend_low = (
            sum(recent_soc) / len(recent_soc)
        ) < L1_LOW_SOC_TREND_THRESHOLD

        # 24h-mean solar ratio (forecast-equivalent for clear-sky inference).
        if self.solar_ratio_window:
            mean_solar_ratio = sum(self.solar_ratio_window) / len(self.solar_ratio_window)
        else:
            mean_solar_ratio = 0.0
        clear_sky = mean_solar_ratio >= L1_CLEAR_SKY_FRACTION

        target_mode = self.mode
        if soc_trend_low:
            target_mode = self.CONSERVATIVE
        elif clear_sky:
            target_mode = self.AGGRESSIVE
        else:
            target_mode = self.BASE

        switched: str | None = None
        if target_mode != self.mode and self.gate.allow(state.hour):
            self.mode = target_mode
            self.gate.stamp(state.hour)
            switched = target_mode

        return self._effective_min_soc(), switched

    def _effective_min_soc(self) -> float:
        if self.mode == self.CONSERVATIVE:
            value = self.base_min_soc + L1_SETPOINT_DELTA
        elif self.mode == self.AGGRESSIVE:
            value = self.base_min_soc - L1_SETPOINT_DELTA
        else:
            value = self.base_min_soc
        return max(self.floor, value)


# ---------------------------------------------------------------------------
# L2 meta — daily mutation proposer + shadow evaluator.
# ---------------------------------------------------------------------------


@dataclass
class _DayRecord:
    """One day of observed scenario inputs + realized base-controller outcome.

    Used by the L2 shadow evaluator to replay the past 7 days against a
    candidate parameter without disturbing the live simulation.
    """

    states: list[HourState] = field(default_factory=list)
    diesel_liters: float = 0.0
    unserved_kwh: float = 0.0


@dataclass
class _Candidate:
    name: str
    min_soc: float
    diesel_start_soc: float
    max_diesel_hours: float


class L2Meta:
    """Per-day mutation proposer with shadow evaluation.

    Every ``L2_DAY_HOURS`` (24h boundary) it inspects the last 7 days and,
    if average daily unserved exceeds the threshold, proposes one of three
    canonical mutations and replays the past 7 days against the candidate
    using a fresh ``RuleBasedController`` instance. Accept iff diesel drops
    by ≥ ``L2_DIESEL_IMPROVEMENT_FRACTION`` AND unserved does not grow.

    The shadow eval is deterministic: it replays recorded ``HourState``
    snapshots, never the scenario engine's RNG.
    """

    def __init__(self, enable_shadow_eval: bool = True):
        self.enable_shadow_eval = enable_shadow_eval
        self.history: deque[_DayRecord] = deque(maxlen=L2_LOOKBACK_DAYS)
        self.current: _DayRecord = _DayRecord()
        self._last_eval_hour: int = -1

    def reset(self) -> None:
        self.history.clear()
        self.current = _DayRecord()
        self._last_eval_hour = -1

    def record(self, state: HourState, action: DispatchAction, site: SiteProfile) -> None:
        """Append one hour of realized base-controller outcome to today."""
        self.current.states.append(state)
        if action.diesel_kw > 0:
            self.current.diesel_liters += (
                action.diesel_kw * site.diesel_consumption_l_per_kwh
            )
        self.current.unserved_kwh += action.load_shed_kw

    def maybe_close_day(self, current_hour: int) -> bool:
        """Roll today's record into history at every 24h boundary.

        Returns True if a day boundary was crossed this call.
        """
        # Day boundary = whenever current_hour is a positive multiple of 24
        # AND we haven't already closed at this boundary.
        if current_hour > 0 and current_hour % L2_DAY_HOURS == 0 and current_hour != self._last_eval_hour:
            self.history.append(self.current)
            self.current = _DayRecord()
            self._last_eval_hour = current_hour
            return True
        return False

    def should_mutate(self) -> bool:
        if len(self.history) < L2_LOOKBACK_DAYS:
            return False
        avg_unserved = sum(d.unserved_kwh for d in self.history) / len(self.history)
        return avg_unserved > L2_UNSERVED_PER_DAY_THRESHOLD_KWH

    def candidates(
        self, current: _Candidate
    ) -> list[_Candidate]:
        """Canonical mutation proposals (rank-ordered)."""
        return [
            _Candidate(
                name="raise_min_soc",
                min_soc=current.min_soc + 5.0,
                diesel_start_soc=current.diesel_start_soc,
                max_diesel_hours=current.max_diesel_hours,
            ),
            _Candidate(
                name="raise_diesel_start_soc",
                min_soc=current.min_soc,
                diesel_start_soc=current.diesel_start_soc + 5.0,
                max_diesel_hours=current.max_diesel_hours,
            ),
            _Candidate(
                name="extend_diesel_hours",
                min_soc=current.min_soc,
                diesel_start_soc=current.diesel_start_soc,
                max_diesel_hours=current.max_diesel_hours + 4.0,
            ),
        ]

    def shadow_eval(
        self, candidate: _Candidate, site: SiteProfile
    ) -> tuple[float, float]:
        """Replay the past 7 days against ``candidate``.

        Returns (simulated_diesel_liters, simulated_unserved_kwh).
        """
        sim = RuleBasedController(
            min_soc=candidate.min_soc,
            diesel_start_soc=candidate.diesel_start_soc,
            diesel_stop_soc=max(
                candidate.diesel_start_soc + 30.0,
                60.0,
            ),
            max_diesel_hours=candidate.max_diesel_hours,
        )
        diesel_l = 0.0
        unserved = 0.0
        for day in self.history:
            for state in day.states:
                action = sim.dispatch(state)
                if action.diesel_kw > 0:
                    diesel_l += action.diesel_kw * site.diesel_consumption_l_per_kwh
                unserved += action.load_shed_kw
        return diesel_l, unserved

    def baseline_totals(self) -> tuple[float, float]:
        """Realized totals across the 7-day history (under the live base ctl)."""
        diesel_l = sum(d.diesel_liters for d in self.history)
        unserved = sum(d.unserved_kwh for d in self.history)
        return diesel_l, unserved

    def evaluate(
        self, current: _Candidate, site: SiteProfile
    ) -> tuple[_Candidate | None, list[dict[str, Any]]]:
        """Try each candidate; return the first acceptance + per-candidate notes."""
        notes: list[dict[str, Any]] = []
        if not self.enable_shadow_eval:
            return None, notes

        baseline_diesel, baseline_unserved = self.baseline_totals()
        if baseline_diesel <= 0:
            return None, notes

        for cand in self.candidates(current):
            sim_diesel, sim_unserved = self.shadow_eval(cand, site)
            diesel_drop = (baseline_diesel - sim_diesel) / baseline_diesel
            unserved_growth = sim_unserved - baseline_unserved
            note = {
                "candidate": cand.name,
                "min_soc": cand.min_soc,
                "diesel_start_soc": cand.diesel_start_soc,
                "max_diesel_hours": cand.max_diesel_hours,
                "baseline_diesel_l": baseline_diesel,
                "sim_diesel_l": sim_diesel,
                "diesel_drop_pct": diesel_drop * 100.0,
                "baseline_unserved_kwh": baseline_unserved,
                "sim_unserved_kwh": sim_unserved,
                "unserved_growth_kwh": unserved_growth,
            }
            if (
                diesel_drop >= L2_DIESEL_IMPROVEMENT_FRACTION
                and unserved_growth <= L2_UNSERVED_TOLERANCE
            ):
                note["verdict"] = "accept"
                notes.append(note)
                return cand, notes
            note["verdict"] = "veto"
            notes.append(note)
        return None, notes


# ---------------------------------------------------------------------------
# L3 governance — weekly mutation budget + hard floors.
# ---------------------------------------------------------------------------


class L3Governance:
    """Caps L2 mutation rate and enforces hardcoded parameter floors.

    Stability constraint (per CLAUDE.md): governance changes must be rare.
    L3 is the narrowest stability margin; aggressive mutation would violate
    the workspace's stability budget.
    """

    def __init__(
        self,
        max_mutations_per_week: int = L3_MAX_MUTATIONS_PER_WEEK,
        min_soc_floor: float = L3_MIN_SOC_FLOOR,
        diesel_start_floor: float = L3_DIESEL_START_SOC_FLOOR,
    ):
        self.max_mutations_per_week = max_mutations_per_week
        self.min_soc_floor = min_soc_floor
        self.diesel_start_floor = diesel_start_floor
        self.week_start_hour = 0
        self.mutations_this_week = 0

    def reset(self) -> None:
        self.week_start_hour = 0
        self.mutations_this_week = 0

    def maybe_roll_week(self, current_hour: int) -> bool:
        """Reset the budget when the week boundary passes. Returns True if rolled."""
        if current_hour - self.week_start_hour >= L3_WEEK_HOURS:
            self.week_start_hour = (current_hour // L3_WEEK_HOURS) * L3_WEEK_HOURS
            self.mutations_this_week = 0
            return True
        return False

    def review(self, candidate: _Candidate) -> tuple[bool, str]:
        """Approve or block a candidate mutation.

        Returns (approved, reason). Floors are checked first so they act as
        absolute invariants regardless of budget.
        """
        if candidate.min_soc < self.min_soc_floor:
            return False, f"min_soc {candidate.min_soc:.1f} below L3 floor {self.min_soc_floor:.1f}"
        if candidate.diesel_start_soc < self.diesel_start_floor:
            return (
                False,
                f"diesel_start_soc {candidate.diesel_start_soc:.1f} below L3 floor {self.diesel_start_floor:.1f}",
            )
        if self.mutations_this_week >= self.max_mutations_per_week:
            return False, f"weekly mutation budget exhausted ({self.mutations_this_week}/{self.max_mutations_per_week})"
        return True, "approved"

    def record_mutation(self) -> None:
        self.mutations_this_week += 1


# ---------------------------------------------------------------------------
# RCSController — public surface.
# ---------------------------------------------------------------------------


class RCSController(Controller):
    """Recursive controlled-system controller for microgrid dispatch.

    Wraps a base controller (default RuleBasedController) and layers L1/L2/L3
    on top per the RCS hierarchy. Toggle levels via constructor args:

        RCSController(level=1)  # +autonomic
        RCSController(level=2)  # +meta
        RCSController(level=3)  # full
        RCSController(level=0)  # flat (just the base controller, used for testing)

    Determinism: this controller introduces no randomness of its own; any
    stochastic behavior comes from the wrapped base controller or scenario.

    Trace: every layer emits ``TraceEvent`` rows readable via ``trace()``.
    The bench runner consumes these to compute per-level Lyapunov decay
    rates λ̂_k.
    """

    _LEVEL_NAMES = {
        0: "rcs-flat",
        1: "rcs-+autonomic",
        2: "rcs-+meta",
        3: "rcs-full",
    }

    def __init__(
        self,
        base: Controller | None = None,
        level: int = 3,
        site: SiteProfile | None = None,
        enable_shadow_eval: bool = True,
    ):
        if level not in self._LEVEL_NAMES:
            raise ValueError(f"level must be in {sorted(self._LEVEL_NAMES)}; got {level}")

        self.base: Controller = base if base is not None else RuleBasedController()
        self.level = level
        self.site = site
        self.enable_shadow_eval = enable_shadow_eval

        # Snapshot the base setpoints so L1 has a stable reference and L2 can
        # mutate the live values. We only do this for RuleBasedController-like
        # bases; for others we skip L1/L2 setpoint surgery.
        self._tunable = isinstance(self.base, RuleBasedController)
        if self._tunable:
            base_min_soc = float(self.base.min_soc)  # type: ignore[attr-defined]
        else:
            base_min_soc = 20.0

        self._l1 = L1Autonomic(base_min_soc=base_min_soc, site=site)
        self._l2 = L2Meta(enable_shadow_eval=enable_shadow_eval)
        self._l3 = L3Governance()

        self._events: list[TraceEvent] = []

    # ------------------------------------------------------------------
    # Controller interface
    # ------------------------------------------------------------------

    def name(self) -> str:
        return self._LEVEL_NAMES[self.level]

    def reset(self) -> None:
        self.base.reset()
        self._l1.reset()
        self._l2.reset()
        self._l3.reset()
        self._events.clear()

    def trace(self) -> list[dict]:
        """Return a list of events emitted during dispatch.

        Used by the bench runner to compute λ̂_k. Each event has:
        ``{timestamp, level, kind, payload}``. Kinds:

            - 'dispatch'                  (L0)
            - 'l1_mode_switch'            (L1)
            - 'l2_mutation_proposed'      (L2)
            - 'l2_mutation_accepted'      (L2)
            - 'l2_mutation_vetoed'        (L2)
            - 'l3_block'                  (L3)
        """
        return [e.to_dict() for e in self._events]

    def dispatch(self, state: HourState) -> DispatchAction:
        # 1. Maybe fire L1 — adapt setpoints before the base dispatch.
        if self.level >= 1 and self._tunable:
            effective_min_soc, switched = self._l1.step(state)
            self.base.min_soc = effective_min_soc  # type: ignore[attr-defined]
            if switched is not None:
                self._emit(
                    state.hour,
                    1,
                    "l1_mode_switch",
                    {
                        "mode": switched,
                        "effective_min_soc": effective_min_soc,
                        "base_min_soc": self._l1.base_min_soc,
                    },
                )

        # 2. Get base dispatch.
        action = self.base.dispatch(state)
        self._emit(
            state.hour,
            0,
            "dispatch",
            {
                "diesel_kw": action.diesel_kw,
                "battery_discharge_kw": action.battery_discharge_kw,
                "load_shed_kw": action.load_shed_kw,
                "soc_pct": state.battery_soc_pct,
            },
        )

        # 3. Maybe fire L2 — daily mutation gate.
        if self.level >= 2 and self._tunable and self.site is not None:
            self._l2.record(state, action, self.site)
            if self._l2.maybe_close_day(state.hour) and self._l2.should_mutate():
                self._run_l2_cycle(state.hour)

        # 4. Maybe fire L3 — weekly budget bookkeeping. Floor enforcement
        #    runs inside review() during step 3; this call only rolls the
        #    weekly window so emits stay accurate over multi-week runs.
        if self.level >= 3 and self._l3.maybe_roll_week(state.hour):
            self._emit(
                state.hour,
                3,
                "l3_block",
                {"event": "week_rolled", "budget": self._l3.max_mutations_per_week},
            )

        # 5. Return action.
        return action

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _run_l2_cycle(self, hour: int) -> None:
        """Run one L2 evaluation cycle at a day boundary."""
        if not self._tunable or self.site is None:
            return
        current = _Candidate(
            name="current",
            min_soc=float(self.base.min_soc),  # type: ignore[attr-defined]
            diesel_start_soc=float(self.base.diesel_start_soc),  # type: ignore[attr-defined]
            max_diesel_hours=float(self.base.max_diesel_hours),  # type: ignore[attr-defined]
        )
        accepted, notes = self._l2.evaluate(current, self.site)

        for note in notes:
            kind = (
                "l2_mutation_accepted"
                if note.get("verdict") == "accept"
                else "l2_mutation_vetoed"
            )
            # Always emit a 'proposed' event before the accept/veto so the
            # bench runner can count proposals independently.
            self._emit(hour, 2, "l2_mutation_proposed", dict(note))
            if kind == "l2_mutation_vetoed":
                self._emit(hour, 2, "l2_mutation_vetoed", {**note, "reason": "shadow_eval_veto"})

        if accepted is None:
            return

        # L3 review — when level >= 3 we honor the budget + floors. When
        # level == 2 we still enforce the hardcoded floors (they are safety
        # invariants, not governance) but skip the budget check.
        approved, reason = self._l3.review(accepted)
        if self.level >= 3:
            if not approved:
                self._emit(
                    hour,
                    3,
                    "l3_block",
                    {"candidate": accepted.name, "reason": reason},
                )
                return
        else:
            # Floor-only enforcement at level=2.
            if accepted.min_soc < self._l3.min_soc_floor or (
                accepted.diesel_start_soc < self._l3.diesel_start_floor
            ):
                self._emit(
                    hour,
                    3,
                    "l3_block",
                    {"candidate": accepted.name, "reason": "floor_violation"},
                )
                return

        # Apply the mutation to the live base controller and notify L1.
        self.base.min_soc = accepted.min_soc  # type: ignore[attr-defined]
        self.base.diesel_start_soc = accepted.diesel_start_soc  # type: ignore[attr-defined]
        self.base.max_diesel_hours = accepted.max_diesel_hours  # type: ignore[attr-defined]
        self._l1.update_base(accepted.min_soc)
        if self.level >= 3:
            self._l3.record_mutation()

        self._emit(
            hour,
            2,
            "l2_mutation_accepted",
            {
                "candidate": accepted.name,
                "min_soc": accepted.min_soc,
                "diesel_start_soc": accepted.diesel_start_soc,
                "max_diesel_hours": accepted.max_diesel_hours,
                "weekly_budget_remaining": max(
                    0,
                    self._l3.max_mutations_per_week - self._l3.mutations_this_week,
                ),
            },
        )

    def _emit(
        self, hour: int, level: int, kind: str, payload: dict[str, Any]
    ) -> None:
        self._events.append(TraceEvent(timestamp=hour, level=level, kind=kind, payload=payload))
