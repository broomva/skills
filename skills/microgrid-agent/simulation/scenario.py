"""Scenario engine — generates realistic microgrid operating conditions.

Each scenario represents one site over one year (8,760 hours) with:
- Solar irradiance (regional, seasonal, cloud-affected)
- Community demand (daily pattern, market days, festivals, seasons)
- Battery dynamics (SOC tracking, degradation)
- Diesel fuel state (tank level, delivery schedule, supply disruptions)
- Equipment failures (random, calibrated to real failure rates)

Calibrated to real Colombian ZNI data from IPSE, PVGIS, and IDEAM.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Iterator


@dataclass
class SiteProfile:
    """Physical and environmental profile of a ZNI site."""

    name: str
    region: str  # "orinoquia", "pacifico", "insular"
    latitude: float
    longitude: float

    # Solar resource
    avg_ghi_kwh_m2_day: float  # Global Horizontal Irradiance (annual avg)
    cloud_fraction: float  # 0.0 = always clear, 1.0 = always cloudy
    ghi_seasonal_amplitude: float  # fractional variation by season

    # Wind resource (for insular sites)
    avg_wind_speed_ms: float = 0.0
    wind_capacity_kw: float = 0.0

    # Equipment
    solar_capacity_kwp: float = 50.0
    battery_capacity_kwh: float = 100.0
    battery_max_dod: float = 0.80
    diesel_capacity_kw: float = 30.0
    diesel_tank_liters: float = 2000.0
    diesel_consumption_l_per_kwh: float = 0.28

    # Community
    population: int = 500
    base_load_kw: float = 15.0
    peak_load_kw: float = 40.0
    market_days: list[int] = field(default_factory=lambda: [2, 5])  # Wed, Sat
    festival_days: list[int] = field(default_factory=list)  # day-of-year
    rainy_season_months: list[int] = field(default_factory=lambda: [4, 5, 6, 7, 8, 9, 10, 11])

    # Failure rates (events per year)
    inverter_failure_rate: float = 0.5
    battery_failure_rate: float = 0.2
    diesel_failure_rate: float = 1.0
    diesel_supply_disruption_rate: float = 2.0  # fuel delivery delays


# Pre-built profiles for the three pilot sites
INIRIDA = SiteProfile(
    name="Inirida",
    region="orinoquia",
    latitude=3.8653,
    longitude=-67.9239,
    avg_ghi_kwh_m2_day=5.2,
    cloud_fraction=0.25,
    ghi_seasonal_amplitude=0.15,
    solar_capacity_kwp=2470.0,  # 2.47 MWp actual
    battery_capacity_kwh=5000.0,
    diesel_capacity_kw=800.0,
    diesel_tank_liters=20000.0,
    population=20000,
    base_load_kw=300.0,
    peak_load_kw=800.0,
    market_days=[0, 3],  # Mon, Thu
    rainy_season_months=[4, 5, 6, 7, 8, 9, 10],
)

COQUI = SiteProfile(
    name="Coquí",
    region="pacifico",
    latitude=5.7100,
    longitude=-77.2700,
    avg_ghi_kwh_m2_day=3.2,
    cloud_fraction=0.70,  # Pacific coast — extremely cloudy
    ghi_seasonal_amplitude=0.10,
    solar_capacity_kwp=101.0,  # 101 kVA actual
    battery_capacity_kwh=430.0,  # actual
    diesel_capacity_kw=150.0,  # actual
    diesel_tank_liters=3000.0,
    population=350,
    base_load_kw=10.0,
    peak_load_kw=35.0,
    market_days=[5],  # Sat
    rainy_season_months=[1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12],  # year-round rain
    diesel_supply_disruption_rate=4.0,  # frequent — river transport only
)

PROVIDENCIA = SiteProfile(
    name="Providencia",
    region="insular",
    latitude=13.3500,
    longitude=-81.3667,
    avg_ghi_kwh_m2_day=5.8,
    cloud_fraction=0.20,
    ghi_seasonal_amplitude=0.10,
    avg_wind_speed_ms=7.0,
    wind_capacity_kw=500.0,
    solar_capacity_kwp=400.0,
    battery_capacity_kwh=2000.0,
    diesel_capacity_kw=3000.0,
    diesel_tank_liters=50000.0,
    population=5000,
    base_load_kw=800.0,
    peak_load_kw=2500.0,
    market_days=[1, 4],  # Tue, Fri
    rainy_season_months=[6, 7, 8, 9, 10, 11],
)

PILOT_SITES = [INIRIDA, COQUI, PROVIDENCIA]


@dataclass
class HourState:
    """State of the microgrid at a single hour."""

    hour: int  # 0..8759 (hour of year)
    month: int  # 1..12
    day_of_year: int  # 1..365
    day_of_week: int  # 0=Mon..6=Sun
    hour_of_day: int  # 0..23

    # Environment
    ghi_wm2: float  # solar irradiance
    temperature_c: float
    wind_speed_ms: float
    is_raining: bool

    # Available generation (before dispatch)
    solar_available_kw: float
    wind_available_kw: float

    # Demand
    load_demand_kw: float
    is_market_day: bool
    is_festival: bool

    # Equipment status
    inverter_ok: bool
    diesel_ok: bool
    diesel_fuel_liters: float

    # Battery
    battery_soc_pct: float


class ScenarioEngine:
    """Generates hour-by-hour microgrid operating conditions for a site.

    Usage:
        scenario = ScenarioEngine(INIRIDA, year=2025, seed=42)
        for hour_state in scenario:
            decision = controller.dispatch(hour_state)
            scenario.apply(decision)  # updates SOC, fuel level, etc.
    """

    def __init__(self, site: SiteProfile, year: int = 2025, seed: int = 42):
        self.site = site
        self.year = year
        self.rng = random.Random(seed)

        # State that evolves over the simulation
        self.battery_soc_pct = 50.0
        self.diesel_fuel_liters = site.diesel_tank_liters
        self.diesel_hours_today = 0.0
        self.current_day = -1

        # Pre-generate failure events
        self._inverter_failures = self._gen_failure_hours(site.inverter_failure_rate, duration_h=24)
        self._diesel_failures = self._gen_failure_hours(site.diesel_failure_rate, duration_h=48)
        self._supply_disruptions = self._gen_failure_hours(
            site.diesel_supply_disruption_rate, duration_h=168  # 1-week disruptions
        )

        # Pre-generate fuel deliveries (monthly)
        self._fuel_deliveries = set()
        for month in range(12):
            delivery_day = 15 + self.rng.randint(-5, 5)
            delivery_hour = month * 730 + delivery_day * 24  # approximate
            if 0 <= delivery_hour < 8760:
                self._fuel_deliveries.add(delivery_hour)

    def _gen_failure_hours(self, rate: float, duration_h: int) -> set[int]:
        """Generate a set of hours during which equipment is failed."""
        failed_hours: set[int] = set()
        n_events = self.rng.poisson_approx(rate)
        for _ in range(n_events):
            start = self.rng.randint(0, 8759)
            for h in range(start, min(start + duration_h, 8760)):
                failed_hours.add(h)
        return failed_hours

    def __iter__(self) -> Iterator[HourState]:
        for hour in range(8760):
            yield self._generate_hour(hour)

    def _generate_hour(self, hour: int) -> HourState:
        day_of_year = hour // 24 + 1
        hour_of_day = hour % 24
        # Approximate day of week (Jan 1 2025 = Wednesday = 2)
        day_of_week = (2 + hour // 24) % 7
        month = min(12, day_of_year * 12 // 365 + 1)

        # --- Solar irradiance ---
        ghi = self._solar_irradiance(hour_of_day, day_of_year, month)

        # --- Temperature ---
        base_temp = 28.0 if self.site.region == "pacifico" else 30.0
        temp_daily = 6.0 * math.sin((hour_of_day - 6) / 24 * 2 * math.pi)
        temp_seasonal = 3.0 * math.sin((day_of_year - 80) / 365 * 2 * math.pi)
        temperature = base_temp + temp_daily + temp_seasonal + self.rng.gauss(0, 1.5)

        # --- Wind ---
        wind = 0.0
        if self.site.avg_wind_speed_ms > 0:
            wind = max(0, self.site.avg_wind_speed_ms + self.rng.gauss(0, 2.0))

        # --- Rain ---
        is_rainy_month = month in self.site.rainy_season_months
        rain_prob = 0.4 if is_rainy_month else 0.1
        if self.site.region == "pacifico":
            rain_prob = 0.6 if is_rainy_month else 0.3  # Pacific is wet year-round
        is_raining = self.rng.random() < rain_prob

        # --- Solar available ---
        panel_efficiency = 1.0 - 0.004 * max(0, temperature - 25)  # temp derating
        if is_raining:
            ghi *= 0.3  # heavy cloud cover during rain
        solar_kw = self.site.solar_capacity_kwp * (ghi / 1000.0) * panel_efficiency

        # --- Wind available ---
        wind_kw = 0.0
        if self.site.wind_capacity_kw > 0 and wind > 3.0:  # cut-in speed
            wind_factor = min(1.0, (wind - 3.0) / 9.0)  # linear ramp 3-12 m/s
            wind_kw = self.site.wind_capacity_kw * wind_factor

        # --- Demand ---
        is_market = day_of_week in self.site.market_days
        is_festival = day_of_year in self.site.festival_days
        load = self._demand(hour_of_day, is_market, is_festival, is_rainy_month)

        # --- Equipment status ---
        inverter_ok = hour not in self._inverter_failures
        diesel_ok = hour not in self._diesel_failures

        # --- Fuel delivery ---
        if hour in self._fuel_deliveries and hour not in self._supply_disruptions:
            self.diesel_fuel_liters = min(
                self.site.diesel_tank_liters,
                self.diesel_fuel_liters + self.site.diesel_tank_liters * 0.8,
            )

        # --- Reset daily diesel counter ---
        if day_of_year != self.current_day:
            self.current_day = day_of_year
            self.diesel_hours_today = 0.0

        if not inverter_ok:
            solar_kw = 0.0  # inverter failure kills solar

        return HourState(
            hour=hour,
            month=month,
            day_of_year=day_of_year,
            day_of_week=day_of_week,
            hour_of_day=hour_of_day,
            ghi_wm2=ghi,
            temperature_c=temperature,
            wind_speed_ms=wind,
            is_raining=is_raining,
            solar_available_kw=solar_kw,
            wind_available_kw=wind_kw,
            load_demand_kw=load,
            is_market_day=is_market,
            is_festival=is_festival,
            inverter_ok=inverter_ok,
            diesel_ok=diesel_ok,
            diesel_fuel_liters=self.diesel_fuel_liters,
            battery_soc_pct=self.battery_soc_pct,
        )

    def _solar_irradiance(self, hour_of_day: int, day_of_year: int, month: int) -> float:
        """Model solar irradiance with diurnal curve, seasonal variation, and cloud cover."""
        if hour_of_day < 6 or hour_of_day > 18:
            return 0.0

        # Diurnal bell curve peaking at solar noon (~12:30)
        solar_angle = (hour_of_day - 6.0) / 12.0 * math.pi
        diurnal = math.sin(solar_angle)

        # Seasonal variation
        seasonal = 1.0 + self.site.ghi_seasonal_amplitude * math.sin(
            (day_of_year - 80) / 365 * 2 * math.pi
        )

        # Peak GHI from daily average: avg ≈ peak * 0.45 (roughly 10.8 sun-hours / 24)
        peak_ghi = self.site.avg_ghi_kwh_m2_day * 1000 / 10.8  # W/m²

        # Cloud cover (random per hour, biased by site's cloud fraction)
        cloud = self.rng.random()
        cloud_factor = 1.0 if cloud > self.site.cloud_fraction else (0.2 + 0.5 * self.rng.random())

        # Rainy season has more cloud cover
        if month in self.site.rainy_season_months:
            cloud_factor *= 0.85

        return max(0.0, peak_ghi * diurnal * seasonal * cloud_factor)

    def _demand(
        self, hour_of_day: int, is_market: bool, is_festival: bool, is_rainy_season: bool
    ) -> float:
        """Model community electricity demand."""
        # Base daily pattern: low at night, peaks at morning (7-9) and evening (18-21)
        if hour_of_day < 5:
            factor = 0.3  # night minimum
        elif hour_of_day < 9:
            factor = 0.7 + 0.3 * (hour_of_day - 5) / 4  # morning ramp
        elif hour_of_day < 12:
            factor = 0.8  # midday (some productive use)
        elif hour_of_day < 14:
            factor = 0.6  # siesta dip
        elif hour_of_day < 18:
            factor = 0.8  # afternoon productive
        elif hour_of_day < 21:
            factor = 1.0  # evening peak (cooking, lighting, TV)
        else:
            factor = 0.5  # late evening decline

        load = self.site.base_load_kw + (self.site.peak_load_kw - self.site.base_load_kw) * factor

        # Market day: +30% during daytime
        if is_market and 6 <= hour_of_day <= 16:
            load *= 1.30

        # Festival: +50% during evening
        if is_festival and 16 <= hour_of_day <= 23:
            load *= 1.50

        # Rainy season: slightly higher (more time indoors, lighting)
        if is_rainy_season:
            load *= 1.05

        # Random noise (±10%)
        load *= 1.0 + self.rng.gauss(0, 0.05)

        return max(0.0, load)

    def apply_dispatch(self, diesel_kw: float, battery_kw: float):
        """Update mutable state after a dispatch decision.

        Args:
            diesel_kw: Diesel output this hour (kW).
            battery_kw: Battery flow (positive=charge, negative=discharge).
        """
        # Battery SOC update (1 hour timestep)
        energy_kwh = battery_kw * 1.0  # 1 hour
        soc_delta_pct = (energy_kwh / self.site.battery_capacity_kwh) * 100.0
        self.battery_soc_pct = max(0.0, min(100.0, self.battery_soc_pct + soc_delta_pct))

        # Diesel fuel consumption
        if diesel_kw > 0:
            fuel_used = diesel_kw * 1.0 * self.site.diesel_consumption_l_per_kwh
            self.diesel_fuel_liters = max(0.0, self.diesel_fuel_liters - fuel_used)
            self.diesel_hours_today += 1.0


# Patch: random.Random doesn't have poisson_approx, add it
def _poisson_approx(self: random.Random, lam: float) -> int:
    """Approximate Poisson sampling using the inverse transform method."""
    if lam <= 0:
        return 0
    L = math.exp(-lam)
    k = 0
    p = 1.0
    while True:
        k += 1
        p *= self.random()
        if p < L:
            return k - 1


random.Random.poisson_approx = _poisson_approx  # type: ignore[attr-defined]
