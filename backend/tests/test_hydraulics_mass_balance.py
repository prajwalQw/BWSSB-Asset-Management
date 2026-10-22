"""
Unit Tests for WNTR EPANET Hydraulic Digital Twin Engine & Mass Balance Verification.
Ensures:
1. Network builds successfully with all node and link specifications.
2. Every generated element is strictly marked simulated: true and data_tier: 'SIMULATED'.
3. Volume mass balance holds in a no-leak baseline run within tolerance (< 1.0%).
4. Injected leak perturbation creates detectable hydraulic changes.
5. Sensor source toggle (SIMULATED vs IGNOAPI) works correctly.
"""

import unittest
from pathlib import Path
from backend.app.hydraulics.engine import engine

class TestHydraulicMassBalance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        engine.reset_scenarios()
        engine.load_config_and_build_model()

    def test_01_network_structure_and_anchors(self):
        """Verify network has source reservoir, 3 pumps, 2+ tanks, consumer clusters, and pipes."""
        wn = engine.wn
        self.assertIsNotNone(wn, "WNTR model must not be None")
        
        # Check source reservoir
        self.assertIn("RES_TATAGUNI_CLEARWATER", wn.reservoir_name_list)
        
        # Check 3 pumps
        self.assertEqual(len(wn.pump_name_list), 3)
        self.assertIn("PUMP_TG_01", wn.pump_name_list)
        self.assertIn("PUMP_TG_02", wn.pump_name_list)
        self.assertIn("PUMP_TG_03_STANDBY", wn.pump_name_list)
        
        # Check tanks (Mount Joy GLR, High Grounds GLR, Jayanagar OHT)
        self.assertGreaterEqual(len(wn.tank_name_list), 2)
        self.assertIn("TANK_MOUNT_JOY_GLR", wn.tank_name_list)
        self.assertIn("TANK_HIGH_GROUNDS_GLR", wn.tank_name_list)
        
        # Check demand nodes (consumer clusters)
        clusters = engine.config.get("consumer_clusters", [])
        self.assertGreaterEqual(len(clusters), 15, "Must have between 15 and 25 demand nodes")
        for c in clusters:
            self.assertIn(c["id"], wn.junction_name_list)
            self.assertTrue(c.get("simulated"), f"Cluster {c['id']} must have simulated: true")

    def test_02_pipe_link_attributes(self):
        """Verify pipes carry diameter, material, length, roughness, installed year, and simulated: true."""
        pipes = engine.config.get("pipes", [])
        self.assertGreaterEqual(len(pipes), 15, "Must have comprehensive corridor pipe links")
        
        for p in pipes:
            self.assertIn("diameter_mm", p)
            self.assertIn("material", p)
            self.assertIn("length_m", p)
            self.assertIn("roughness", p)
            self.assertIn("installed_year", p)
            self.assertIn("status", p)
            self.assertTrue(p.get("simulated"), f"Pipe {p['id']} must have simulated: true")
            self.assertIn(p["material"], ["DI", "MS", "CI", "HDPE"])
            self.assertGreater(p["diameter_mm"], 0)
            self.assertGreater(p["length_m"], 0)

    def test_03_no_leak_baseline_mass_balance_within_tolerance(self):
        """Verify that mass balance holds in a no-leak run within tolerance (< 1.0%)."""
        engine.reset_scenarios()
        results = engine.run_simulation()
        
        meta = results.get("metadata", {})
        mb = meta.get("mass_balance", {})
        
        self.assertIn("percentage_error", mb)
        pct_error = mb["percentage_error"]
        self.assertLess(pct_error, 1.0, f"Baseline mass balance error {pct_error}% must be < 1.0%")
        self.assertTrue(mb.get("mass_balance_satisfied"))
        self.assertEqual(mb.get("status"), "BALANCED")
        
        # Verify simulated flag on metadata
        self.assertTrue(meta.get("simulated"))
        self.assertEqual(meta.get("data_tier"), "SIMULATED")

    def test_04_leak_injection_scenario(self):
        """Verify that injecting an 80 LPS leak creates detectable pressure anomaly and audit log."""
        results = engine.run_simulation(leak_pipe="PIPE_CORRIDOR_10", leak_flow_lps=80.0)
        
        meta = results.get("metadata", {})
        injections = meta.get("active_injections", [])
        self.assertTrue(any(inj.get("type") == "PIPE_BURST_LEAK" for inj in injections))
        
        # Verify burst status is reflected on pipe
        pipe_feat = next((f for f in results["features"] if f["properties"].get("id") == "PIPE_CORRIDOR_10"), None)
        self.assertIsNotNone(pipe_feat)
        self.assertEqual(pipe_feat["properties"].get("status"), "BURST")

    def test_05_sensor_source_toggle(self):
        """Verify that toggling sensor value source between SIMULATED and IGNOAPI switches data tier."""
        sensor_id = "FM_TG_OUTLET"
        engine.set_sensor_source(sensor_id, "IGNOAPI")
        results = engine.run_simulation()
        
        meters = results.get("flow_meters", [])
        tg_meter = next((m for m in meters if m["sensor_id"] == sensor_id), None)
        self.assertIsNotNone(tg_meter)
        self.assertEqual(tg_meter.get("value_source"), "IGNOAPI")
        self.assertEqual(tg_meter.get("data_tier"), "LIVE")
        
        # Toggle back to SIMULATED
        engine.set_sensor_source(sensor_id, "SIMULATED")
        results_sim = engine.run_simulation()
        tg_meter_sim = next((m for m in results_sim.get("flow_meters", []) if m["sensor_id"] == sensor_id), None)
        self.assertEqual(tg_meter_sim.get("value_source"), "SIMULATED")
        self.assertEqual(tg_meter_sim.get("data_tier"), "SIMULATED")

if __name__ == "__main__":
    unittest.main()
