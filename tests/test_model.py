import unittest
from dataclasses import replace
import numpy as np
from energy_lab import Assets, Profiles, dispatch, synthetic_profiles


def flat(load, solar, available=None):
    n = len(load)
    return Profiles(np.array(load, dtype=float), np.zeros(n), np.array(solar, dtype=float),
                    np.full(n, 0.3), np.ones(n, dtype=bool) if available is None else np.array(available))


class ModelTests(unittest.TestCase):
    def test_grid_only_hand_calculation(self):
        r = dispatch(flat([10, 20], [0, 0]), Assets(pv_kw=0, battery_kwh=0, demand_rate_per_kw=2))
        self.assertAlmostEqual(r.metrics["operating_cost"], 9 + 40)
        self.assertEqual(r.metrics["grid_import_kwh"], 30)

    def test_efficiency_and_storage_balance(self):
        a = Assets(pv_kw=10, battery_kwh=10, initial_soc=0, reserve_soc=0,
                   charge_efficiency=0.8, discharge_efficiency=0.9, strategy="self-consumption")
        r = dispatch(flat([0, 10], [1, 0]), a)
        self.assertAlmostEqual(r.streams["discharge_kw"][1], 7.2)
        self.assertAlmostEqual(r.metrics["battery_loss_kwh"], 2.8)
        self.assertAlmostEqual(r.metrics["final_stored_kwh"], 0)

    def test_outage_prioritizes_critical_and_disables_export(self):
        a = Assets(pv_kw=0, battery_kwh=0, generator_kw=3, critical_fraction=0.4)
        r = dispatch(flat([10], [0], [False]), a)
        self.assertEqual(r.metrics["unserved_critical_kwh"], 1)
        self.assertEqual(r.metrics["shed_noncritical_kwh"], 6)
        self.assertEqual(r.metrics["outage_critical_served_fraction"], 0.75)
        self.assertEqual(r.metrics["grid_import_kwh"], 0)

    def test_online_shortfall_sheds_noncritical_first(self):
        r = dispatch(flat([10], [0]), Assets(pv_kw=0, battery_kwh=0, grid_limit_kw=5, critical_fraction=0.4))
        self.assertEqual(r.metrics["unserved_critical_kwh"], 0)
        self.assertEqual(r.metrics["shed_noncritical_kwh"], 5)

    def test_randomized_physical_invariants(self):
        for seed in range(12):
            for strategy in ("peak", "reserve", "self-consumption"):
                a = Assets(strategy=strategy, pv_kw=seed * 12, battery_kwh=seed * 20,
                           grid_limit_kw=12, generator_kw=5)
                r = dispatch(synthetic_profiles(7, seed, outage=(35, 50)), a)
                s = r.streams
                self.assertLess(r.metrics["max_balance_error_kw"], 1e-10)
                self.assertTrue(np.all(s["stored_kwh"] >= -1e-10))
                self.assertTrue(np.all(s["stored_kwh"] <= a.battery_kwh + 1e-10))
                self.assertTrue(np.all(s["charge_kw"] * s["discharge_kw"] == 0))
                expected = (r.metrics["initial_stored_kwh"] + s["charge_kw"].sum()
                            - s["discharge_kw"].sum() - s["battery_loss_kwh"].sum())
                self.assertAlmostEqual(r.metrics["final_stored_kwh"], expected)

    def test_ev_shift_preserves_energy_and_seed(self):
        a = synthetic_profiles(7, 42)
        b = synthetic_profiles(7, 42, "solar")
        np.testing.assert_array_equal(a.building_kw, b.building_kw)
        self.assertEqual(a.ev_kw.sum(), b.ev_kw.sum())
        self.assertEqual(a.ev_kw.sum(), 7 * 28)

    def test_invalid_inputs(self):
        for config in ({"pv_kw": float("nan")}, {"charge_efficiency": 0},
                       {"critical_fraction": 2}, {"strategy": "optimal"}):
            with self.assertRaises(ValueError):
                Assets(**config)
        with self.assertRaises(ValueError):
            dispatch(flat([10], [1.1]), Assets())
        with self.assertRaises(ValueError):
            synthetic_profiles(1, outage=(23, 25))


if __name__ == "__main__":
    unittest.main()
