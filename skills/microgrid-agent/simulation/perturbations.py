"""Perturbation injectors for controlled microgrid simulation experiments.

This module wraps a :class:`ScenarioEngine` and overlays scheduled disturbances
on the generated :class:`HourState` stream. The wrapper does not re-roll the
scenario RNG — it lets the underlying scenario produce its hour, then mutates
the relevant fields (solar/load/diesel/battery availability) before yielding.

The primary motivation is to enable empirical measurement of controller
recovery dynamics. In particular, by injecting a calibrated cloud burst and
observing how the battery state-of-charge returns to its setpoint, we obtain
an estimate of the L0 plant's natural recovery rate λ̂_0 and can compare it to
the analytic value λ_0 = 1.45 reported in the RCS foundations paper.

Pure stdlib. No extra deps. Composes with :class:`ScenarioEngine` rather than
subclassing it, so the underlying scenario invariants (SOC update, fuel
consumption, failure pre-rolls) are preserved verbatim.

Usage::

    from simulation.scenario import INIRIDA, ScenarioEngine
    from simulation.perturbations import (
        PerturbationInjector,
        cloud_burst_perturbation,
    )

    scenario = ScenarioEngine(INIRIDA, seed=42)
    injector = PerturbationInjector(scenario, [cloud_burst_perturbation()])
    for state in injector:
        action = controller.dispatch(state)
        net_battery = action.solar_to_battery_kw - action.battery_discharge_kw
        injector.apply_dispatch(action.diesel_kw, net_battery)
"""

from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Iterator, Protocol, runtime_checkable

from .scenario import HourState, ScenarioEngine, SiteProfile


# Recognized perturbation kinds. Any other string raises in __iter__.
_KINDS = frozenset(
    {"cloud_burst", "demand_spike", "diesel_outage", "battery_fault"}
)


@dataclass
class PerturbationEvent:
    """A scheduled disturbance to inject into a scenario stream.

    Attributes:
        start_hour:      Hour-of-year when the perturbation begins (0..8759).
        duration_hours:  How many hours the perturbation lasts.
        kind:            One of ``"cloud_burst"``, ``"demand_spike"``,
                         ``"diesel_outage"``, ``"battery_fault"``.
        amplitude:       Severity in [0, 1]. 0.0 = no effect, 1.0 = full
                         disturbance. Interpretation is kind-specific (see
                         module docstring and :class:`PerturbationInjector`).
        metadata:        Optional kind-specific parameters. Currently
                         understood keys:
                           - ``battery_fault``:
                             ``"affect": "charge" | "discharge" | "both"``
                             (default ``"both"``).
    """

    start_hour: int
    duration_hours: int
    kind: str
    amplitude: float
    metadata: dict | None = None

    def covers(self, hour: int) -> bool:
        """Return True if this event is active at ``hour``."""
        return self.start_hour <= hour < self.start_hour + self.duration_hours


@runtime_checkable
class _ScenarioLike(Protocol):
    """Structural type — anything that quacks like a ScenarioEngine."""

    site: SiteProfile

    def __iter__(self) -> Iterator[HourState]: ...
    def apply_dispatch(self, diesel_kw: float, battery_kw: float) -> None: ...


class PerturbationInjector:
    """Wraps a :class:`ScenarioEngine` and injects controlled perturbations.

    Use this in place of ``ScenarioEngine`` for controlled-disturbance
    experiments::

        site = INIRIDA
        scenario = ScenarioEngine(site, seed=42)
        # Inject a 1-hour cloud burst at hour 10 of year (day 1, 10 AM)
        injector = PerturbationInjector(scenario, [
            PerturbationEvent(start_hour=10, duration_hours=1,
                              kind="cloud_burst", amplitude=0.9),
        ])
        for state in injector:
            ...   # state.solar_available_kw is reduced by 90% during hours 10..10

    Implementation notes:

    * The wrapper iterates the underlying scenario and mutates the yielded
      ``HourState`` via :func:`dataclasses.replace`. We treat ``HourState`` as
      effectively frozen even though the source dataclass is not declared
      ``frozen=True`` — this preserves call-site semantics if/when the
      scenario locks it down.
    * Perturbations only adjust *available* generation/demand fields. They do
      NOT re-seed the scenario RNG, so two runs with the same ``seed`` and the
      same event list produce byte-identical outputs.
    * Battery faults are realised by attaching ``battery_max_charge_kw`` /
      ``battery_max_discharge_kw`` attributes to the yielded state. The base
      ``HourState`` does not declare those fields, so they only appear when a
      ``battery_fault`` is active. Controllers that wish to honour the limits
      must check ``getattr(state, "battery_max_charge_kw", None)``.
    """

    def __init__(
        self,
        scenario: ScenarioEngine,
        events: list[PerturbationEvent],
    ):
        self.scenario = scenario
        self.events: list[PerturbationEvent] = list(events)

        # Validate event kinds eagerly so misuses fail fast rather than mid-run.
        for ev in self.events:
            if ev.kind not in _KINDS:
                raise ValueError(
                    f"Unknown perturbation kind: {ev.kind!r}. "
                    f"Expected one of {sorted(_KINDS)}."
                )
            if not (0.0 <= ev.amplitude <= 1.0):
                raise ValueError(
                    f"Perturbation amplitude must be in [0, 1], got {ev.amplitude}"
                )
            if ev.duration_hours <= 0:
                raise ValueError(
                    f"Perturbation duration_hours must be > 0, got {ev.duration_hours}"
                )

    # ------------------------------------------------------------------
    # Iteration
    # ------------------------------------------------------------------

    def __iter__(self) -> Iterator[HourState]:
        """Yield :class:`HourState` instances with active perturbations applied."""
        for state in self.scenario:
            event = self.perturbation_active(state.hour)
            if event is None:
                yield state
            else:
                yield self._apply(state, event)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def perturbation_active(self, hour: int) -> PerturbationEvent | None:
        """Return the event active at ``hour``, or ``None``.

        If multiple events overlap (which is allowed but unusual), the first
        event that contains ``hour`` is returned.
        """
        for ev in self.events:
            if ev.covers(hour):
                return ev
        return None

    # ------------------------------------------------------------------
    # Dispatch passthrough
    # ------------------------------------------------------------------

    def apply_dispatch(self, diesel_kw: float, net_battery_kw: float) -> None:
        """Pass-through to the wrapped ``scenario.apply_dispatch``.

        The injector does NOT modify the dispatch outcome — it only modifies
        the *observed* state stream. Battery SOC and fuel-tank updates remain
        the responsibility of the underlying :class:`ScenarioEngine`, which
        guarantees scenario invariants (SOC bounded, fuel non-negative) are
        preserved across perturbations.

        Args:
            diesel_kw:        Diesel output this hour, in kW.
            net_battery_kw:   Net battery flow (positive = charge,
                              negative = discharge), in kW.
        """
        self.scenario.apply_dispatch(diesel_kw, net_battery_kw)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _apply(self, state: HourState, ev: PerturbationEvent) -> HourState:
        """Return a perturbed copy of ``state`` for event ``ev``."""
        if ev.kind == "cloud_burst":
            # Reduce solar by `amplitude` fraction.
            new_solar = state.solar_available_kw * (1.0 - ev.amplitude)
            return dataclasses.replace(state, solar_available_kw=new_solar)

        if ev.kind == "demand_spike":
            # Increase load demand by `amplitude` fraction.
            new_load = state.load_demand_kw * (1.0 + ev.amplitude)
            return dataclasses.replace(state, load_demand_kw=new_load)

        if ev.kind == "diesel_outage":
            # Force diesel availability to zero (or scale by 1 - amplitude).
            # We treat amplitude=1.0 as a hard outage by also flipping the
            # diesel_ok flag to False, which most controllers already check.
            if ev.amplitude >= 1.0:
                return dataclasses.replace(
                    state, diesel_ok=False, diesel_fuel_liters=state.diesel_fuel_liters
                )
            # Partial degradation: reduce reported fuel as a soft proxy for
            # constrained delivery while keeping the diesel breaker closed.
            new_fuel = state.diesel_fuel_liters * (1.0 - ev.amplitude)
            return dataclasses.replace(state, diesel_fuel_liters=new_fuel)

        if ev.kind == "battery_fault":
            # Reduce battery throughput by `amplitude` fraction. Default site
            # battery max is approximated via the C-rate convention battery
            # capacity / 2 hours (i.e. 0.5C). We expose this as extra
            # attributes on the returned HourState so controllers that want to
            # honour the limit can read it; controllers that ignore these
            # fields keep working unchanged.
            site = self.scenario.site
            base_throughput = site.battery_capacity_kwh / 2.0  # 0.5C nominal
            scale = max(0.0, 1.0 - ev.amplitude)
            affect = (ev.metadata or {}).get("affect", "both")

            new_state = dataclasses.replace(state)
            if affect in ("charge", "both"):
                object.__setattr__(
                    new_state, "battery_max_charge_kw", base_throughput * scale
                )
            if affect in ("discharge", "both"):
                object.__setattr__(
                    new_state, "battery_max_discharge_kw", base_throughput * scale
                )
            return new_state

        # Unreachable — validated in __init__.
        raise ValueError(f"Unknown perturbation kind: {ev.kind!r}")


# ----------------------------------------------------------------------
# Standard helper constructors
# ----------------------------------------------------------------------


def cloud_burst_perturbation(
    start_hour: int = 240,  # day 10 by default — well into normal operation
    duration_hours: int = 1,
    amplitude: float = 0.9,
) -> PerturbationEvent:
    """Standard cloud-burst perturbation for λ̂_0 calibration.

    A 1-hour, 90%-solar-occlusion event placed on day 10. Day 10 is far
    enough from the simulation cold-start that battery SOC and diesel-tank
    state have settled, so the post-burst SOC trajectory cleanly reveals the
    plant's natural recovery rate.
    """
    return PerturbationEvent(
        start_hour=start_hour,
        duration_hours=duration_hours,
        kind="cloud_burst",
        amplitude=amplitude,
    )


def demand_spike_perturbation(
    start_hour: int = 240,
    duration_hours: int = 2,
    amplitude: float = 0.5,
) -> PerturbationEvent:
    """Standard demand-spike perturbation (default: +50% for 2 h)."""
    return PerturbationEvent(
        start_hour=start_hour,
        duration_hours=duration_hours,
        kind="demand_spike",
        amplitude=amplitude,
    )


def diesel_outage_perturbation(
    start_hour: int = 240,
    duration_hours: int = 4,
    amplitude: float = 1.0,
) -> PerturbationEvent:
    """Standard diesel-outage perturbation (default: full outage for 4 h)."""
    return PerturbationEvent(
        start_hour=start_hour,
        duration_hours=duration_hours,
        kind="diesel_outage",
        amplitude=amplitude,
    )


def battery_fault_perturbation(
    start_hour: int = 240,
    duration_hours: int = 12,
    amplitude: float = 0.5,
    affect: str = "both",
) -> PerturbationEvent:
    """Standard battery-fault perturbation (default: half throughput, 12 h)."""
    return PerturbationEvent(
        start_hour=start_hour,
        duration_hours=duration_hours,
        kind="battery_fault",
        amplitude=amplitude,
        metadata={"affect": affect},
    )


def standard_perturbation_battery() -> list[PerturbationEvent]:
    """Standard 4-perturbation experimental battery for λ̂ measurement.

    Includes:

      * **cloud_burst** at day 10 hour 10  (amplitude 0.9, 1 h)
      * **demand_spike** at day 30 hour 18 (amplitude 0.6, 2 h)
      * **diesel_outage** at day 60 hour 0 (amplitude 1.0, 4 h)
      * **battery_fault** at day 90 hour 0 (amplitude 0.5, 12 h)

    Events are placed on days 10, 30, 60, and 90 so each has at least two
    weeks (and typically 30 days) of steady-state recovery between events.
    Returned in chronological order.
    """
    # day_of_year is 1-indexed in HourState, but the simulation hour grid is
    # 0-indexed (hour = (day-1)*24 + hour_of_day). The constants below follow
    # the 0-indexed convention so they line up with HourState.hour directly.
    return [
        # day 10, 10:00
        cloud_burst_perturbation(
            start_hour=9 * 24 + 10, duration_hours=1, amplitude=0.9
        ),
        # day 30, 18:00
        demand_spike_perturbation(
            start_hour=29 * 24 + 18, duration_hours=2, amplitude=0.6
        ),
        # day 60, 00:00
        diesel_outage_perturbation(
            start_hour=59 * 24 + 0, duration_hours=4, amplitude=1.0
        ),
        # day 90, 00:00
        battery_fault_perturbation(
            start_hour=89 * 24 + 0, duration_hours=12, amplitude=0.5
        ),
    ]


# ----------------------------------------------------------------------
# Inline self-tests
# ----------------------------------------------------------------------

if __name__ == "__main__":
    from .scenario import INIRIDA, ScenarioEngine

    def _states_equal(a: HourState, b: HourState) -> bool:
        return dataclasses.astuple(a) == dataclasses.astuple(b)

    # ---- Test 1: empty event list is a true pass-through. ----
    s1 = ScenarioEngine(INIRIDA, seed=42)
    s2 = ScenarioEngine(INIRIDA, seed=42)
    inj = PerturbationInjector(s2, [])

    iter1 = iter(s1)
    iter2 = iter(inj)
    for _ in range(72):  # first 3 days
        a = next(iter1)
        b = next(iter2)
        assert _states_equal(a, b), (
            f"empty-injector mismatch at hour {a.hour}: {a} vs {b}"
        )
    print("ok  empty-event injector matches scenario byte-for-byte (72 hours)")

    # ---- Test 2: cloud_burst reduces solar_available_kw on covered hours. ----
    s_base = ScenarioEngine(INIRIDA, seed=42)
    s_pert = ScenarioEngine(INIRIDA, seed=42)
    burst = PerturbationEvent(
        start_hour=240, duration_hours=2, kind="cloud_burst", amplitude=0.9
    )
    inj = PerturbationInjector(s_pert, [burst])

    base_states = []
    pert_states = []
    it_base = iter(s_base)
    it_pert = iter(inj)
    for _ in range(244):  # cover the burst window plus a bit
        base_states.append(next(it_base))
        pert_states.append(next(it_pert))

    # Pre-burst hours: identical.
    for h in range(240):
        assert _states_equal(base_states[h], pert_states[h]), (
            f"pre-burst divergence at hour {h}"
        )
    # During the burst (hours 240, 241): solar reduced to 10% of baseline.
    for h in (240, 241):
        base_solar = base_states[h].solar_available_kw
        pert_solar = pert_states[h].solar_available_kw
        # Allow tiny float slop.
        expected = base_solar * (1.0 - 0.9)
        assert abs(pert_solar - expected) < 1e-9, (
            f"hour {h}: expected solar {expected}, got {pert_solar} "
            f"(baseline {base_solar})"
        )
        # And every other field should match the baseline.
        a = dataclasses.replace(base_states[h], solar_available_kw=pert_solar)
        assert _states_equal(a, pert_states[h]), (
            f"hour {h}: non-solar field mutated unexpectedly"
        )
    # Post-burst hours: identical.
    for h in (242, 243):
        assert _states_equal(base_states[h], pert_states[h]), (
            f"post-burst divergence at hour {h}"
        )
    print("ok  cloud_burst reduces solar_available_kw only on covered hours")

    # ---- Test 3: perturbation_active query. ----
    assert inj.perturbation_active(239) is None
    assert inj.perturbation_active(240) is burst
    assert inj.perturbation_active(241) is burst
    assert inj.perturbation_active(242) is None
    print("ok  perturbation_active() correctly bounds active window")

    # ---- Test 4: demand_spike inflates load_demand_kw. ----
    s_base = ScenarioEngine(INIRIDA, seed=7)
    s_pert = ScenarioEngine(INIRIDA, seed=7)
    spike = PerturbationEvent(
        start_hour=100, duration_hours=1, kind="demand_spike", amplitude=0.5
    )
    inj = PerturbationInjector(s_pert, [spike])
    base_states = []
    pert_states = []
    it_base = iter(s_base)
    it_pert = iter(inj)
    for _ in range(105):
        base_states.append(next(it_base))
        pert_states.append(next(it_pert))
    assert abs(
        pert_states[100].load_demand_kw - base_states[100].load_demand_kw * 1.5
    ) < 1e-9
    assert pert_states[99].load_demand_kw == base_states[99].load_demand_kw
    print("ok  demand_spike scales load_demand_kw by (1 + amplitude)")

    # ---- Test 5: diesel_outage at amplitude 1.0 forces diesel_ok = False. ----
    s_pert = ScenarioEngine(INIRIDA, seed=11)
    outage = PerturbationEvent(
        start_hour=50, duration_hours=3, kind="diesel_outage", amplitude=1.0
    )
    inj = PerturbationInjector(s_pert, [outage])
    states = []
    it = iter(inj)
    for _ in range(55):
        states.append(next(it))
    for h in (50, 51, 52):
        assert states[h].diesel_ok is False, (
            f"hour {h}: expected diesel_ok=False, got {states[h].diesel_ok}"
        )
    assert states[53].diesel_ok in (True, False)  # depends on pre-rolled failures
    print("ok  diesel_outage forces diesel_ok=False during the outage")

    # ---- Test 6: battery_fault attaches throughput limits. ----
    s_pert = ScenarioEngine(INIRIDA, seed=13)
    fault = PerturbationEvent(
        start_hour=20, duration_hours=2, kind="battery_fault", amplitude=0.5,
        metadata={"affect": "both"},
    )
    inj = PerturbationInjector(s_pert, [fault])
    states = []
    it = iter(inj)
    for _ in range(25):
        states.append(next(it))
    nominal = INIRIDA.battery_capacity_kwh / 2.0
    expected_limit = nominal * 0.5
    for h in (20, 21):
        chg = getattr(states[h], "battery_max_charge_kw", None)
        dchg = getattr(states[h], "battery_max_discharge_kw", None)
        assert chg is not None and abs(chg - expected_limit) < 1e-9, (
            f"hour {h}: expected charge limit {expected_limit}, got {chg}"
        )
        assert dchg is not None and abs(dchg - expected_limit) < 1e-9
    assert getattr(states[19], "battery_max_charge_kw", None) is None
    assert getattr(states[22], "battery_max_charge_kw", None) is None
    print("ok  battery_fault attaches max-charge/discharge limits during window")

    # ---- Test 7: apply_dispatch is a pass-through. ----
    s = ScenarioEngine(INIRIDA, seed=17)
    inj = PerturbationInjector(s, [])
    soc_before = s.battery_soc_pct
    inj.apply_dispatch(diesel_kw=10.0, net_battery_kw=5.0)
    soc_after = s.battery_soc_pct
    # 5 kW × 1 h = 5 kWh into a battery of capacity INIRIDA.battery_capacity_kwh
    expected_delta = (5.0 / INIRIDA.battery_capacity_kwh) * 100.0
    assert abs((soc_after - soc_before) - expected_delta) < 1e-9, (
        f"apply_dispatch did not update SOC as expected: "
        f"before={soc_before}, after={soc_after}, expected_delta={expected_delta}"
    )
    print("ok  apply_dispatch passes through to scenario.apply_dispatch")

    # ---- Test 8: standard_perturbation_battery is well-formed. ----
    bat = standard_perturbation_battery()
    assert len(bat) == 4
    kinds = {ev.kind for ev in bat}
    assert kinds == _KINDS, f"missing kinds: {_KINDS - kinds}"
    # Strictly chronological. Spec calls for events on days 10, 30, 60, 90 —
    # i.e. the 10→30 gap is 20 days; subsequent gaps are 30+ days. Either way,
    # every gap should leave at least ~14 days of steady-state recovery.
    starts = [ev.start_hour for ev in bat]
    assert starts == sorted(starts)
    for a, b in zip(starts, starts[1:]):
        assert (b - a) >= 24 * 14, f"events too close: {a} -> {b}"
    print("ok  standard_perturbation_battery covers all 4 kinds, chronological")

    # ---- Test 9: invalid input is rejected. ----
    try:
        PerturbationInjector(
            ScenarioEngine(INIRIDA, seed=1),
            [PerturbationEvent(0, 1, "earthquake", 0.5)],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for unknown kind")

    try:
        PerturbationInjector(
            ScenarioEngine(INIRIDA, seed=1),
            [PerturbationEvent(0, 1, "cloud_burst", 1.5)],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for amplitude > 1")

    try:
        PerturbationInjector(
            ScenarioEngine(INIRIDA, seed=1),
            [PerturbationEvent(0, 0, "cloud_burst", 0.5)],
        )
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError for duration_hours <= 0")
    print("ok  validation rejects unknown kind / out-of-range amplitude / zero duration")

    print("\nAll perturbation injector self-tests passed.")
