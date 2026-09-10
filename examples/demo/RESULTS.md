# Synthetic scenario results

Seed: 42. Horizon: 7 days. All inputs are invented.

| Scenario | Import (kWh) | Peak (kW) | Illustrative cost ($) | CO2 (kg) |
| --- | ---: | ---: | ---: | ---: |
| grid_only | 3717.8 | 45.2 | 988.93 | 1412.7 |
| solar | 2417.6 | 45.2 | 781.73 | 918.7 |
| solar_storage | 1900.9 | 40.4 | 609.43 | 722.3 |
| solar_storage_ev_shift | 1767.6 | 34.9 | 538.50 | 671.7 |

## Eight-hour synthetic interruption

| Scenario | Critical load served (%) | Noncritical load shed (kWh) | Fuel (L) |
| --- | ---: | ---: | ---: |
| grid_only | 0.0 | 126.1 | 0.0 |
| solar_storage | 69.0 | 126.1 | 0.0 |
| solar_storage_backup | 100.0 | 126.1 | 12.2 |

## Interpretation boundaries

These are outputs of a transparent dispatch heuristic, not measured performance or optimal designs. One demand charge is applied to the observed peak even for this short horizon. Initial/final battery energy is reported; no terminal value correction is applied. Costs omit capital expenditure, degradation, maintenance, taxes, and value of lost load. Emissions factors are illustrative and exports receive no emissions credit. Do not annualize this short synthetic trace or compare outage cost without service quality.
