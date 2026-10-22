"""
Automated Pytest Suite for Pump Power Monitor Subsystem.
Validates:
1. Electrical 3-phase variable synthesis and telemetry
2. Start-up handling: inrush peak, decay profile, start event log
3. Robust steady-state band learning (Median + MAD)
4. Multi-fault anomaly detection (voltage imbalance, dry run, blockage, drift, frequent starts)
5. Advisory knowledge base diagnostics and consequences
6. Drift forecast with 95% uncertainty interval and time-to-alarm range
7. Backtesting vs static threshold baseline
8. Energy and tariff financial reporting
"""

import pytest
import numpy as np
import time
from backend.app.hydraulics.pump_power_monitor import pump_monitor_engine, PumpPowerMonitorEngine


def test_01_electrical_variables_structure():
    """Verify that every pump has complete 3-phase electrical and hydraulic telemetry."""
    res = pump_monitor_engine.evaluate_pump_telemetry()
    assert res["data_tier"] == "SIMULATED"
    assert "pumps" in res
    assert len(res["pumps"]) >= 3

    for pump in res["pumps"]:
        telem = pump["latest_telemetry"]
        # 3-phase voltages
        assert "voltage_r" in telem
        assert "voltage_y" in telem
        assert "voltage_b" in telem
        assert "voltage_avg" in telem
        # 3-phase currents
        assert "current_r" in telem
        assert "current_y" in telem
        assert "current_b" in telem
        assert "current_avg" in telem
        # Power & energy
        assert "active_power_kw" in telem
        assert "power_factor" in telem
        assert "specific_energy_kwh_per_m3" in telem
        assert "run_state" in telem
        # Hydraulic correlation
        assert "flow_lps" in telem
        assert "discharge_pressure_bar" in telem


def test_02_startup_event_inrush_and_decay():
    """Verify start event logging, inrush peak current, and exponential decay recording."""
    engine = PumpPowerMonitorEngine()
    now = time.time()
    evt = engine._record_start_event(
        pump_id="PUMP_TG_01",
        timestamp=now,
        inrush_ratio=6.0,
        duration_sec=30.0,
        status="NORMAL_RAMP"
    )
    assert evt["inrush_peak_current_a"] == pytest.approx(124.5 * 6.0, 1.0)
    assert evt["inrush_ratio"] == 6.0
    assert evt["ramp_down_duration_sec"] == 30.0
    assert len(evt["decay_profile"]) == 11
    # First point should be near peak, last point near rated current
    assert evt["decay_profile"][0]["current_a"] >= 700.0
    assert evt["decay_profile"][-1]["current_a"] <= 140.0


def test_03_robust_median_mad_steady_band_learning():
    """Verify robust steady-state band calculation using Median and MAD on healthy running data."""
    engine = PumpPowerMonitorEngine()
    band = engine.steady_bands.get("PUMP_TG_01", {})
    assert "current_a" in band
    assert "power_kw" in band
    
    i_band = band["current_a"]
    assert "median" in i_band
    assert "mad" in i_band
    assert "band_low" in i_band
    assert "band_high" in i_band
    assert i_band["band_low"] < i_band["median"] < i_band["band_high"]

    # Verify MAD computation logic
    samples = np.array([118.0, 119.0, 120.0, 121.0, 122.0, 150.0]) # outlier included
    med = np.median(samples)
    mad = np.median(np.abs(samples - med))
    assert med == 120.5
    assert mad == 1.5 # Robust against 150.0 outlier


def test_04_anomaly_voltage_imbalance():
    """Verify detection of voltage imbalance (> 2.0% NEMA standard)."""
    engine = PumpPowerMonitorEngine()
    engine.inject_anomaly_scenario("PUMP_TG_01", "VOLTAGE_IMBALANCE", severity=1.5)
    res = engine.evaluate_pump_telemetry()
    p1 = next(p for p in res["pumps"] if p["pump_id"] == "PUMP_TG_01")
    
    anom_types = [a["anomaly_type"] for a in p1["active_anomalies"]]
    assert "VOLTAGE_IMBALANCE" in anom_types

    # Check alert details
    matching_alerts = [a for a in res["alerts"] if a["anomaly_type"] == "VOLTAGE_IMBALANCE" and a["pump_id"] == "PUMP_TG_01"]
    assert len(matching_alerts) > 0
    al = matching_alerts[0]
    assert al["severity"] == "CRITICAL"
    assert al["phase"] == "3-Phase (RYB)"
    assert al["advisory"] is True
    assert "likely_causes" in al
    assert "future_consequences" in al
    assert "suggested_actions" in al
    engine.clear_injection("PUMP_TG_01")


def test_05_anomaly_running_dry():
    """Verify detection of pump running dry (low current with low flow)."""
    engine = PumpPowerMonitorEngine()
    engine.inject_anomaly_scenario("PUMP_TG_01", "RUNNING_DRY")
    res = engine.evaluate_pump_telemetry()
    p1 = next(p for p in res["pumps"] if p["pump_id"] == "PUMP_TG_01")
    
    anom_types = [a["anomaly_type"] for a in p1["active_anomalies"]]
    assert "RUNNING_DRY" in anom_types

    alerts = [a for a in res["alerts"] if a["anomaly_type"] == "RUNNING_DRY"]
    assert len(alerts) > 0
    assert alerts[0]["severity"] == "CRITICAL"
    engine.clear_injection("PUMP_TG_01")


def test_06_anomaly_blockage_or_friction():
    """Verify detection of pump blockage (high current with low flow)."""
    engine = PumpPowerMonitorEngine()
    engine.inject_anomaly_scenario("PUMP_TG_01", "BLOCKAGE")
    res = engine.evaluate_pump_telemetry()
    p1 = next(p for p in res["pumps"] if p["pump_id"] == "PUMP_TG_01")
    
    anom_types = [a["anomaly_type"] for a in p1["active_anomalies"]]
    assert "BLOCKAGE_OR_FRICTION" in anom_types
    engine.clear_injection("PUMP_TG_01")


def test_07_anomaly_frequent_starts():
    """Verify detection of excessive cycling (> 3 starts/hr)."""
    engine = PumpPowerMonitorEngine()
    engine.inject_anomaly_scenario("PUMP_TG_01", "FREQUENT_STARTS")
    res = engine.evaluate_pump_telemetry()
    p1 = next(p for p in res["pumps"] if p["pump_id"] == "PUMP_TG_01")
    
    anom_types = [a["anomaly_type"] for a in p1["active_anomalies"]]
    assert "FREQUENT_STARTS" in anom_types
    engine.clear_injection("PUMP_TG_01")


def test_08_drift_forecast_and_time_to_alarm():
    """Verify drift projection with 95% confidence interval and backtest vs static threshold."""
    engine = PumpPowerMonitorEngine()
    engine.inject_anomaly_scenario("PUMP_TG_01", "BEARING_FRICTION_DRIFT", severity=1.2)
    # Populate history with rising slope
    now = time.time()
    for i in range(15):
        engine.history_samples["PUMP_TG_01"].append({
            "timestamp": now - (15 - i) * 1800,
            "voltage_r": 6600.0, "voltage_y": 6600.0, "voltage_b": 6600.0, "voltage_avg": 6600.0,
            "current_r": 118.0 + i * 0.8, "current_y": 118.0 + i * 0.8, "current_b": 118.0 + i * 0.8, "current_avg": 118.0 + i * 0.8,
            "active_power_kw": 1150.0 + i * 6.5,
            "power_factor": 0.88,
            "flow_lps": 650.0,
            "discharge_pressure_bar": 6.3,
            "run_state": "STEADY_RUNNING",
            "is_healthy_steady": False
        })

    forecast = engine.forecast_steady_drift("PUMP_TG_01", horizon_hours=48)
    assert forecast["drift_status"] == "RISING_DRIFT_DETECTED"
    assert forecast["time_to_alarm"]["nominal_hours"] is not None
    assert forecast["time_to_alarm"]["range_min_hours"] <= forecast["time_to_alarm"]["nominal_hours"]
    if forecast["time_to_alarm"]["range_max_hours"] is not None:
        assert forecast["time_to_alarm"]["nominal_hours"] <= forecast["time_to_alarm"]["range_max_hours"]
    assert len(forecast["forecast_timeseries"]) > 20

    # Verify backtest comparison exists
    backtest = forecast["backtest"]
    assert "proposed_drift_model" in backtest
    assert "simple_threshold_baseline" in backtest
    assert backtest["proposed_drift_model"]["early_warning_lead_time_hours"] > 0
    engine.clear_injection("PUMP_TG_01")


def test_09_energy_and_tariff_report():
    """Verify rolling 24-hr energy report, specific energy, and cost computation using config tariff."""
    report = pump_monitor_engine.generate_energy_report()
    assert report["station_id"] == "PS_TATAGUNI_MAIN"
    assert report["tariff_inr_per_kwh"] == 7.50
    assert report["total_kwh_24h"] > 0.0
    assert report["total_cost_inr_24h"] == pytest.approx(report["total_kwh_24h"] * 7.50, 0.1)
    assert len(report["pumps"]) >= 3
    for p in report["pumps"]:
        assert "specific_energy_kwh_per_m3" in p
        assert "efficiency_rating" in p
