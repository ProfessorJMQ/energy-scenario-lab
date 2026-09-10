"""Generate reproducible scenario reports and a small sensitivity experiment."""
import argparse
import csv
from dataclasses import asdict, replace
import json
from pathlib import Path
import numpy as np
from .model import Assets, dispatch, synthetic_profiles


def write_rows(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def run(output, days=7, seed=42, custom=None, sweep=False):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    base = Assets(**(custom or {}))
    scenarios = {
        "grid_only": replace(base, pv_kw=0, battery_kwh=0, battery_kw=0, generator_kw=0),
        "solar": replace(base, battery_kwh=0, battery_kw=0, generator_kw=0),
        "solar_storage": base,
        "solar_storage_ev_shift": base,
    }
    all_results = {}
    for name, assets in scenarios.items():
        profiles = synthetic_profiles(days, seed, "solar" if name.endswith("shift") else "evening")
        result = dispatch(profiles, assets)
        all_results[name] = result
        write_rows(output / f"{name}_hourly.csv", [
            {"hour": t, **{k: float(v[t]) for k, v in result.streams.items()},
             "import_rate": float(profiles.import_rate[t])} for t in range(days * 24)])
    # Compare identical outage hours and demand across configurations.
    outage_start = min(42, days * 24 - 8)
    outage_profiles = synthetic_profiles(days, seed, outage=(outage_start, outage_start + 8))
    outage_results = {
        "grid_only": dispatch(outage_profiles, scenarios["grid_only"]),
        "solar_storage": dispatch(outage_profiles, replace(base, generator_kw=0)),
        "solar_storage_backup": dispatch(outage_profiles, replace(base, generator_kw=25)),
    }
    summary = {
        "provenance": "Synthetic demonstration; no measured or sponsored research data.",
        "seed": seed, "days": days, "assets": asdict(base),
        "normal_operation": {k: v.metrics for k, v in all_results.items()},
        "outage": {"hours": [outage_start, outage_start + 8],
                   "scenarios": {k: v.metrics for k, v in outage_results.items()}},
    }
    (output / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    plt.rcParams.update({"font.size": 10, "axes.spines.top": False, "axes.spines.right": False})
    fig, axes = plt.subplots(3, 1, figsize=(12, 10), layout="constrained")
    hours = np.arange(min(72, days * 24))
    s = all_results["solar_storage_ev_shift"].streams
    axes[0].plot(hours, s["load_kw"][hours], label="Demand", color="#18324b")
    axes[0].plot(hours, s["pv_kw"][hours], label="Synthetic PV", color="#de8b1a")
    axes[0].plot(hours, s["grid_import_kw"][hours], label="Grid import", color="#137e82")
    axes[0].set(ylabel="Power (kW)", xlabel="Hour", title="Energy Scenario Lab / synthetic demonstration")
    axes[0].legend(ncol=3)
    axes[1].plot(hours, s["stored_kwh"][hours], color="#7048a5")
    axes[1].set(ylabel="Stored energy (kWh)", xlabel="Hour", ylim=(0, max(1, base.battery_kwh)))
    names = list(all_results)
    axes[2].bar([n.replace("_", "\n") for n in names],
                [all_results[n].metrics["operating_cost"] for n in names], color="#137e82")
    axes[2].set(ylabel="Illustrative cost ($)", title=f"{days}-day energy charges + one demand charge; no capital costs")
    fig.savefig(output / "overview.png", dpi=150)
    plt.close(fig)
    lines = ["# Synthetic scenario results", "", f"Seed: {seed}. Horizon: {days} days. All inputs are invented.", "",
             "| Scenario | Import (kWh) | Peak (kW) | Illustrative cost ($) | CO2 (kg) |", "| --- | ---: | ---: | ---: | ---: |"]
    for name, result in all_results.items():
        m = result.metrics
        lines.append(f"| {name} | {m['grid_import_kwh']:.1f} | {m['grid_peak_kw']:.1f} | {m['operating_cost']:.2f} | {m['co2_kg']:.1f} |")
    lines += ["", "## Eight-hour synthetic interruption", "",
              "| Scenario | Critical load served (%) | Noncritical load shed (kWh) | Fuel (L) |", "| --- | ---: | ---: | ---: |"]
    for name, result in outage_results.items():
        m = result.metrics
        lines.append(f"| {name} | {100 * m['outage_critical_served_fraction']:.1f} | {m['shed_noncritical_kwh']:.1f} | {m['fuel_liters']:.1f} |")
    lines += ["", "## Interpretation boundaries", "",
              "These are outputs of a transparent dispatch heuristic, not measured performance or optimal designs. "
              "One demand charge is applied to the observed peak even for this short horizon. "
              "Initial/final battery energy is reported; no terminal value correction is applied. "
              "Costs omit capital expenditure, degradation, maintenance, taxes, and value of lost load. "
              "Emissions factors are illustrative and exports receive no emissions credit. "
              "Do not annualize this short synthetic trace or compare outage cost without service quality.", ""]
    (output / "RESULTS.md").write_text("\n".join(lines), encoding="utf-8")
    if sweep:
        rows = []
        for weather_seed in range(seed, seed + 5):
            p = synthetic_profiles(days, weather_seed)
            for pv in (25, 55, 85):
                for capacity in (0, 50, 100, 150):
                    a = replace(base, pv_kw=pv, battery_kwh=capacity)
                    rows.append({"seed": weather_seed, "pv_kw": pv, "battery_kwh": capacity,
                                 **dispatch(p, a).metrics})
        write_rows(output / "sensitivity.csv", rows)
        fig, ax = plt.subplots(figsize=(8, 5), layout="constrained")
        for pv in (25, 55, 85):
            capacities = (0, 50, 100, 150)
            values = [[r["operating_cost"] for r in rows if r["pv_kw"] == pv and r["battery_kwh"] == c] for c in capacities]
            ax.errorbar(capacities, np.mean(values, axis=1), yerr=np.std(values, axis=1), marker="o", capsize=4, label=f"PV {pv} kW")
        ax.set(xlabel="Battery capacity (kWh)", ylabel="Illustrative cost ($)",
               title="Sensitivity: mean +/- standard deviation across 5 synthetic weather seeds")
        ax.legend()
        fig.savefig(output / "sensitivity.png", dpi=150)
        plt.close(fig)
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="outputs/demo")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--config", type=Path, help="JSON overrides of Assets fields")
    parser.add_argument("--sweep", action="store_true")
    args = parser.parse_args()
    try:
        config = json.loads(args.config.read_text(encoding="utf-8")) if args.config else None
        run(args.output, args.days, args.seed, config, args.sweep)
    except (ValueError, TypeError, OSError) as error:
        parser.error(str(error))
    print(f"Wrote results to {args.output}")


if __name__ == "__main__":
    main()
