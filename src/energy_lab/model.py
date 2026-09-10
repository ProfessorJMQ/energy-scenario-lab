"""Hourly AC-bus energy accounting. Power is kW, stored energy is kWh.

Dispatch is an explicit rule-based heuristic, not an optimizer or a power-flow
solver. Every result retains the streams needed to independently check balance.
"""
from dataclasses import dataclass
import math
import numpy as np


@dataclass(frozen=True)
class Assets:
    pv_kw: float = 55.0
    battery_kwh: float = 100.0
    battery_kw: float = 30.0
    charge_efficiency: float = 0.95
    discharge_efficiency: float = 0.95
    initial_soc: float = 0.20
    reserve_soc: float = 0.20
    generator_kw: float = 0.0
    generator_liters_per_kwh: float = 0.28
    generator_idle_liters_per_hour: float = 0.8
    fuel_price_per_liter: float = 1.10
    grid_limit_kw: float = 100.0
    export_limit_kw: float = 15.0
    export_rate_per_kwh: float = 0.04
    demand_rate_per_kw: float = 8.0
    grid_kg_co2_per_kwh: float = 0.38
    fuel_kg_co2_per_liter: float = 2.68
    critical_fraction: float = 0.45
    strategy: str = "peak"
    peak_threshold: float = 0.20

    def __post_init__(self):
        for name, value in vars(self).items():
            if name == "strategy":
                continue
            if not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
                raise ValueError(f"{name} must be finite and nonnegative")
        for name in ("charge_efficiency", "discharge_efficiency"):
            if not 0 < getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in (0, 1]")
        for name in ("initial_soc", "reserve_soc", "critical_fraction"):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f"{name} must be in [0, 1]")
        if self.strategy not in {"self-consumption", "peak", "reserve"}:
            raise ValueError("strategy must be self-consumption, peak, or reserve")


@dataclass(frozen=True)
class Profiles:
    building_kw: np.ndarray
    ev_kw: np.ndarray
    solar_per_unit: np.ndarray
    import_rate: np.ndarray
    grid_available: np.ndarray

    @property
    def load_kw(self):
        return np.asarray(self.building_kw) + np.asarray(self.ev_kw)

    def validate(self):
        size = len(self.building_kw)
        if size == 0:
            raise ValueError("profiles must contain at least one hour")
        for name, values in vars(self).items():
            a = np.asarray(values)
            if a.shape != (size,) or not np.all(np.isfinite(a)):
                raise ValueError(f"{name} must be a finite one-dimensional array of length {size}")
            if np.any(a < 0):
                raise ValueError(f"{name} cannot be negative")
        if np.any(np.asarray(self.solar_per_unit) > 1):
            raise ValueError("solar_per_unit cannot exceed one")
        if not np.all(np.isin(self.grid_available, [0, 1])):
            raise ValueError("grid_available must contain booleans or 0/1")


def synthetic_profiles(days=7, seed=42, ev_mode="evening", outage=None):
    """Invent a generic community load; no location, records, or real tariff.

    outage is a half-open (start_hour, end_hour) interval. Each EV session uses
    28 kWh whether charged in the evening or shifted to solar hours.
    """
    if not isinstance(days, int) or isinstance(days, bool) or not 1 <= days <= 366:
        raise ValueError("days must be an integer from 1 to 366")
    if ev_mode not in {"evening", "solar"}:
        raise ValueError("ev_mode must be evening or solar")
    rng = np.random.default_rng(seed)
    h = np.arange(days * 24)
    hour = h % 24
    building = (15 + 9 * np.exp(-((hour - 8) / 2.5) ** 2)
                + 20 * np.exp(-((hour - 19) / 3.0) ** 2))
    building = np.maximum(1.0, building + rng.normal(0, 1.1, len(h)))
    cloud = np.repeat(rng.uniform(0.55, 1.0, days), 24)
    solar = np.clip(np.sin(np.pi * (hour - 6) / 12), 0, 1) * cloud
    start = 18 if ev_mode == "evening" else 11
    ev = np.where((hour >= start) & (hour < start + 4), 7.0, 0.0)
    rate = np.where((hour >= 16) & (hour < 21), 0.29, 0.11)
    available = np.ones(len(h), dtype=bool)
    if outage is not None:
        a, b = outage
        if not (isinstance(a, int) and isinstance(b, int) and 0 <= a < b <= len(h)):
            raise ValueError("outage must be an integer interval within the horizon")
        available[a:b] = False
    return Profiles(building, ev, solar, rate, available)


@dataclass
class Result:
    streams: dict
    metrics: dict


def dispatch(profiles: Profiles, assets: Assets) -> Result:
    profiles.validate()
    load = profiles.load_kw
    size = len(load)
    keys = ("load_kw", "pv_kw", "charge_kw", "discharge_kw", "grid_import_kw",
            "export_kw", "curtailment_kw", "generator_kw", "fuel_liters",
            "unserved_critical_kw", "shed_noncritical_kw", "stored_kwh",
            "battery_loss_kwh", "balance_error_kw")
    s = {key: np.zeros(size) for key in keys}
    energy = assets.battery_kwh * assets.initial_soc
    initial_energy = energy
    for t in range(size):
        online = bool(profiles.grid_available[t])
        critical = load[t] * assets.critical_fraction
        target = load[t] if online else critical
        s["shed_noncritical_kw"][t] = load[t] - target
        pv = assets.pv_kw * profiles.solar_per_unit[t]
        s["load_kw"][t], s["pv_kw"][t] = load[t], pv
        surplus = max(0.0, pv - target)
        deficit = max(0.0, target - pv)
        charge = min(surplus, assets.battery_kw,
                     max(0.0, assets.battery_kwh - energy) / assets.charge_efficiency)
        energy += charge * assets.charge_efficiency  # one-hour interval
        surplus -= charge
        floor = assets.reserve_soc * assets.battery_kwh if online else 0.0
        grid_cap = assets.grid_limit_kw if online else 0.0
        can_discharge = (not online or assets.strategy == "self-consumption"
                         or (assets.strategy == "peak" and profiles.import_rate[t] >= assets.peak_threshold))
        # Even during cheap hours, use available energy above reserve to cover a grid shortfall.
        requested = deficit if can_discharge else max(0.0, deficit - grid_cap)
        discharge = min(requested, assets.battery_kw,
                        max(0.0, energy - floor) * assets.discharge_efficiency)
        energy -= discharge / assets.discharge_efficiency
        deficit -= discharge
        imported = min(deficit, grid_cap)
        deficit -= imported
        generated = min(deficit, assets.generator_kw)
        deficit -= generated
        # Online shortfalls shed noncritical load first; outage target is already critical-only.
        noncritical = min(deficit, load[t] - critical) if online else 0.0
        s["shed_noncritical_kw"][t] += noncritical
        unserved = max(0.0, deficit - noncritical)
        exported = min(surplus, assets.export_limit_kw) if online else 0.0
        curtailed = surplus - exported
        fuel = (generated * assets.generator_liters_per_kwh
                + assets.generator_idle_liters_per_hour) if generated > 0 else 0.0
        loss = charge * (1 - assets.charge_efficiency) + discharge * (1 / assets.discharge_efficiency - 1)
        for key, value in (("charge_kw", charge), ("discharge_kw", discharge),
                           ("grid_import_kw", imported), ("export_kw", exported),
                           ("curtailment_kw", curtailed), ("generator_kw", generated),
                           ("fuel_liters", fuel), ("unserved_critical_kw", unserved),
                           ("stored_kwh", energy), ("battery_loss_kwh", loss)):
            s[key][t] = value
        served = load[t] - s["shed_noncritical_kw"][t] - unserved
        s["balance_error_kw"][t] = pv + discharge + imported + generated - served - charge - exported - curtailed
    energy_cost = float(np.dot(s["grid_import_kw"], profiles.import_rate))
    export_credit = float(s["export_kw"].sum() * assets.export_rate_per_kwh)
    demand_cost = float(s["grid_import_kw"].max() * assets.demand_rate_per_kw)
    fuel_cost = float(s["fuel_liters"].sum() * assets.fuel_price_per_liter)
    outage_mask = ~np.asarray(profiles.grid_available, dtype=bool)
    outage_critical = float(np.sum(load[outage_mask]) * assets.critical_fraction)
    outage_unserved = float(s["unserved_critical_kw"][outage_mask].sum())
    metrics = {
        "hours": size,
        "load_kwh": float(load.sum()),
        "pv_kwh": float(s["pv_kw"].sum()),
        "grid_import_kwh": float(s["grid_import_kw"].sum()),
        "grid_peak_kw": float(s["grid_import_kw"].max()),
        "export_kwh": float(s["export_kw"].sum()),
        "curtailed_kwh": float(s["curtailment_kw"].sum()),
        "fuel_liters": float(s["fuel_liters"].sum()),
        "unserved_critical_kwh": float(s["unserved_critical_kw"].sum()),
        "shed_noncritical_kwh": float(s["shed_noncritical_kw"].sum()),
        "outage_critical_served_fraction": min(1.0, max(0.0, 1 - outage_unserved / outage_critical)) if outage_critical else None,
        "energy_cost": energy_cost, "demand_cost": demand_cost,
        "export_credit": export_credit, "fuel_cost": fuel_cost,
        "operating_cost": energy_cost + demand_cost + fuel_cost - export_credit,
        "co2_kg": float(s["grid_import_kw"].sum() * assets.grid_kg_co2_per_kwh
                        + s["fuel_liters"].sum() * assets.fuel_kg_co2_per_liter),
        "initial_stored_kwh": initial_energy,
        "final_stored_kwh": float(energy),
        "battery_loss_kwh": float(s["battery_loss_kwh"].sum()),
        "max_balance_error_kw": float(np.max(np.abs(s["balance_error_kw"]))),
    }
    return Result(s, metrics)
