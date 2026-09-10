# Model specification

## Units and accounting

All flows are AC-side kW. The time step is exactly one hour, so each step's numeric kW value also equals interval kWh. Stored energy is kWh; efficiency is dimensionless. No variable time step is supported.

For every hour:

```text
PV + grid_import + generator + battery_discharge
    = served_load + battery_charge + export + curtailed_PV

served_load = requested_load - shed_noncritical - unserved_critical

E_next = E + charge * eta_charge - discharge / eta_discharge
loss = charge * (1 - eta_charge) + discharge * (1/eta_discharge - 1)
```

Charge and discharge have independent efficiency factors and the same power limit. Battery charging uses only excess PV. Simultaneous charge/discharge is excluded by construction and checked in tests. Capacity and reserve constrain withdrawals. An outage permits stored energy below the normal reserve to be used.

## Invented inputs

A shaped building load has morning/evening peaks and small Gaussian variation, floored at 1 kW. Solar is a clipped daytime sinusoid times one random daily cloud multiplier. EV load is 7 kW for four hours each day; shifting it preserves 28 kWh per day. The tariff is $0.29/kWh during hours 16 through 20 and $0.11 otherwise. Export credit, demand rate, and emissions factors are arbitrary configurable assumptions.

All time indices are relative to a synthetic midnight. No calendar, location, daylight saving, real tariff, facility, mission profile, or utility territory is represented.

## Dispatch policies

| Policy | Normal grid operation | Grid limit or outage |
| --- | --- | --- |
| `self-consumption` | Discharge to meet net demand above the SOC reserve | Cover remaining demand within limits |
| `peak` | Discharge when import price reaches the threshold | Cover remaining demand within limits |
| `reserve` | Retain energy under normal conditions | Use above-reserve energy for a grid shortfall; release reserve during outage |

The generator supplies residual load after grid and battery support. Fuel is an illustrative linear term plus an hourly idle term when it runs. There is no export from the generator and no generator charging of the battery.

## Reported cost and emissions

```text
cost = sum(grid_import * tariff) + peak_import * demand_rate
       + fuel_liters * fuel_price - export_kwh * export_credit
CO2 = grid_import_kwh * grid_factor + fuel_liters * fuel_factor
```

These are direct modeled operating terms. No avoided-emissions credit is assigned to exports. The sensitivity experiment varies capacity but does not include its capital cost, so it cannot identify the economically best design.

## Background

The implementation is independently authored. The following primary documentation is useful for understanding the computational building blocks and for comparing this simplified model with more capable tools:

- [NumPy array and numerical documentation](https://numpy.org/doc/stable/)
- [System Advisor Model project and source](https://github.com/NREL/SAM) — a separate, much more comprehensive modeling tool; no SAM source or models are included here.
- [Matplotlib documentation](https://matplotlib.org/stable/)
