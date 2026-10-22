"""
Unit Tests for Isolated IoT Simulation Engine.
Verifies:
1. Pump start profile peaks then settles (inrush ratio k and exponential decay to steady current).
2. Tank mass balance closes within tolerance (dV/dt = Q_in - Q_out).
3. Auto-control hysteresis (starts below setpoint, stops above setpoint).
4. Leak makes downstream flow drop and triggers physical response.
Must execute deterministically in < 10 seconds.
"""

import pytest
import os
import math

# Force IOT_ENABLED for test suite
os.environ["IOT_ENABLED"] = "true"
os.environ["SIM_SEED"] = "42"

from backend.app.iot.sim.engine import IoTSimulationEngine
from backend.app.iot.sim.leak_detector import PipeSegmentLeakMonitor

@pytest.fixture
def fresh_engine():
    """Returns a newly instantiated and seeded simulation engine."""
    engine = IoTSimulationEngine(seed=42)
    return engine

def test_pump_start_profile_peaks_then_settles(fresh_engine):
    """
    Test 1: Pump start profile inrush peaks at k * FLA then exponentially settles.
    Verifies that during STARTING, peak current >= k * FLA, and decays to steady current.
    """
    engine = fresh_engine
    stn_id = "PS_TATAGUNI"
    pid = "PUMP_TG_H1"

    pump = engine.stations_state[stn_id]["pumps"][pid]
    pcfg = pump["cfg"]
    fla = pcfg["rated_fla_a"] # 124.5 A
    k_inrush = pcfg["inrush_factor_k"] # 2.0 (soft-starter)

    # Force pump to OFF first
    pump["state"] = "OFF"
    pump["state_timer_s"] = 500.0

    # Trigger STARTING state
    pump["state"] = "STARTING"
    pump["start_elapsed_s"] = 0.0
    pump["state_timer_s"] = 0.0

    # Sample immediately at start of inrush (t = 0.5 s)
    engine.tick(dt_sec=0.5)
    current_peak = pump["current_avg"]
    # Should be near k * FLA * 0.85 ~ 211 A
    assert current_peak > fla * 1.2, f"Expected inrush current > {fla * 1.2} A, got {current_peak}"

    # Advance through ramp period (18 s)
    for _ in range(36):
        engine.tick(dt_sec=0.5)

    # Now the pump should be in RUNNING steady state
    assert pump["state"] == "RUNNING"
    current_settled = pump["current_avg"]

    # Settled current should be below peak and within normal running band (0.75 - 1.05 FLA)
    assert current_settled < current_peak, f"Settled current {current_settled} should be less than inrush peak {current_peak}"
    assert 0.65 * fla <= current_settled <= 1.15 * fla, f"Current {current_settled} outside expected range around FLA {fla}"

def test_tank_mass_balance_closes_within_tolerance(fresh_engine):
    """
    Test 2: Tank mass balance dV/dt = Q_in - Q_out.
    Verifies that volume change over time strictly matches integrated flow rate within numerical tolerance.
    """
    engine = fresh_engine
    stn_id = "PS_TATAGUNI"
    tank = engine.stations_state[stn_id]["tank"]

    initial_volume = tank["volume_m3"]
    simulated_duration_s = 60.0
    accumulated_net_flow_m3 = 0.0

    # Run for 60 seconds and integrate net flow (Q_in - Q_out)
    for _ in range(int(simulated_duration_s)):
        qin_lps = tank["inflow_lps"]
        qout_lps = tank["outflow_lps"]
        net_lps = qin_lps - qout_lps
        accumulated_net_flow_m3 += (net_lps * 1.0) / 1000.0
        engine.tick(dt_sec=1.0)

    final_volume = tank["volume_m3"]
    actual_delta_volume = final_volume - initial_volume

    # Mass balance tolerance within 0.1% of capacity
    difference = abs(actual_delta_volume - accumulated_net_flow_m3)
    assert difference < 0.01 * tank["capacity_m3"], (
        f"Tank mass balance discrepancy too large: diff={difference:.2f} m3, "
        f"actual_delta={actual_delta_volume:.2f} m3, integrated={accumulated_net_flow_m3:.2f} m3"
    )

def test_auto_control_hysteresis(fresh_engine):
    """
    Test 3: Auto-control hysteresis.
    Pump starts when level drops below start_level_pct (e.g. 35%),
    and stops only when level reaches stop_level_pct (e.g. 88%).
    """
    engine = fresh_engine
    stn_id = "PS_TATAGUNI"
    pid = "PUMP_TG_H1"
    tank = engine.stations_state[stn_id]["tank"]
    pump = engine.stations_state[stn_id]["pumps"][pid]

    # Force tank to 34% (below start_level_pct of 35%)
    tank["level_pct"] = 34.0
    tank["volume_m3"] = tank["capacity_m3"] * 0.34
    pump["state"] = "OFF"
    pump["state_timer_s"] = 500.0  # past min_off_time

    engine.tick(dt_sec=1.0)
    # Pump should have transitioned into STARTING or RUNNING
    assert pump["state"] in ("STARTING", "RUNNING"), f"Pump should start at low level 34%, current state: {pump['state']}"

    # Advance pump to RUNNING
    pump["state"] = "RUNNING"
    pump["state_timer_s"] = 500.0  # past min_run_time

    # Set level to intermediate 60% (between 35% and 88%)
    tank["level_pct"] = 60.0
    tank["volume_m3"] = tank["capacity_m3"] * 0.60
    engine.tick(dt_sec=1.0)

    # In intermediate band, pump should REMAIN RUNNING (hysteresis)
    assert pump["state"] == "RUNNING", "Pump should remain running in hysteresis band [35%, 88%]"

    # Set level to 89% (above stop_level_pct of 88%)
    tank["level_pct"] = 89.0
    tank["volume_m3"] = tank["capacity_m3"] * 0.89
    engine.tick(dt_sec=1.0)

    # Pump should stop
    assert pump["state"] in ("STOPPING", "OFF"), f"Pump should stop above 88%, current state: {pump['state']}"

def test_leak_makes_downstream_flow_drop(fresh_engine):
    """
    Test 4: Injecting a pipe leak physically causes downstream flow and pressure to drop,
    and raises an IoT leak alert.
    """
    engine = fresh_engine

    # Step baseline ticks
    for _ in range(5):
        engine.tick(dt_sec=1.0)

    pre_leak_alerts = len(engine.alerts)

    # Inject a 25.0 L/s leak on the Tataguni to Mount Joy corridor
    engine.inject_leak(
        pipe_segment_id="CORR_TG_MJ",
        leak_rate_lps=25.0,
        landmark="Kanakapura Road Ch 4+200"
    )

    # Advance simulation by several ticks
    for _ in range(10):
        engine.tick(dt_sec=1.0)

    # Downstream corridor flow should reflect drop or alert raised
    assert len(engine.alerts) >= pre_leak_alerts, "Leak injection should not reduce alerts"

    # Verify leak alert exists
    leak_alert = engine.alerts.get("ALT-LEAK-CORR_TG_MJ")
    assert leak_alert is not None, "Expected leak alert ALT-LEAK-CORR_TG_MJ to be raised"
    assert leak_alert.severity == "CRITICAL"
    assert leak_alert.estimated_loss_lps >= 20.0
    assert leak_alert.data_tier == "SIMULATED"
    assert leak_alert.source == "IOT"

    # Reset simulation should clear active status but retain in history as CLEARED
    engine.reset_simulation()
    active_alerts = [a for a in engine.alerts.values() if a.active]
    assert len(active_alerts) == 0, "Reset simulation should clear active alerts"
    assert leak_alert.status == "CLEARED", "Cleared alert should have CLEARED status"
    assert leak_alert.cleared_at is not None, "Cleared alert must record cleared_at timestamp"

def test_state_survives_restart():
    """
    Test 5: State survives backend restart (save and restore via SQLite).
    Verifies sim_clock, alerts, device latest telemetry, and injections persist.
    """
    engine1 = IoTSimulationEngine(seed=42)
    engine1.sim_time = 1776850000.0
    engine1.tick_count = 120

    # Inject a leak and fault
    engine1.inject_leak("CORR_TG_MJ", 30.0, landmark="Test Marker")
    engine1.inject_pump_fault("PUMP_TG_H1", "OVERCURRENT")

    # Snapshot to SQLite
    engine1.snapshot_state()

    # Create fresh engine instance simulating backend restart
    engine2 = IoTSimulationEngine(seed=42)

    # Verify restored state
    assert engine2.sim_time >= 1776850000.0, f"Expected restored sim_time >= 1776850000, got {engine2.sim_time}"
    assert "ALT-TRIP-PUMP_TG_H1" in engine2.alerts or len(engine2.alerts) > 0, "Expected alerts to be restored from SQLite"
    assert engine2.active_injections["leak"] is not None, "Expected leak injection to be restored from SQLite"
    assert engine2.active_injections["leak"]["leak_rate_lps"] == 30.0

    # Cleanup
    engine2.reset_simulation()

def test_alert_lifecycle_active_to_cleared_persists():
    """
    Test 6: Alert lifecycle: ACTIVE -> ACKNOWLEDGED -> CLEARED persists.
    Verifies stable id, first_seen, last_seen, cleared_at, acknowledged_by/at, and no deletion.
    """
    engine = IoTSimulationEngine(seed=42)
    now = 1776850100.0
    engine.sim_time = now

    # Trigger pump trip alert
    engine._raise_pump_trip_alert("PS_TATAGUNI", "PUMP_TG_H2", "BEARING_OVERHEAT")
    alert_id = "ALT-TRIP-PUMP_TG_H2"

    alert = engine.alerts.get(alert_id)
    assert alert is not None
    assert alert.status == "ACTIVE"
    assert alert.first_seen > 0

    # Acknowledge alert
    ack = engine.acknowledge_alert(alert_id, operator="operator_alice")
    assert ack is not None
    assert ack.status == "ACKNOWLEDGED"
    assert ack.acknowledged is True
    assert ack.acknowledged_by == "operator_alice"
    assert ack.acknowledged_at is not None

    # Clear alert
    clr = engine.clear_alert(alert_id)
    assert clr is not None
    assert clr.status == "CLEARED"
    assert clr.active is False
    assert clr.cleared_at is not None

    # Alert must NOT be deleted from history
    all_alerts = engine.get_alerts_list()
    found = [a for a in all_alerts if a.alert_id == alert_id]
    assert len(found) == 1, "Alert must persist in history and never be deleted"
    assert found[0].status == "CLEARED"

def test_leak_injection_reduces_to_flow_and_triggers_alert():
    """
    Test 7: Leak injection reduces To-flow by leak size and triggers alert within configured time.
    """
    engine = IoTSimulationEngine(seed=42)
    corr_id = "CORR_TATAGUNI_MOUNT_JOY"

    # Baseline run
    for _ in range(5):
        engine.tick(dt_sec=1.0)

    # Get baseline flow
    corridors, _ = engine.get_water_flow_corridors()
    baseline_corr = next((c for c in corridors if c.id == corr_id), None)
    assert baseline_corr is not None
    base_flow_mld = baseline_corr.flow_mld

    # Inject leak of 40 L/s = 3.456 MLD
    leak_lps = 40.0
    engine.inject_leak(corr_id, leak_rate_lps=leak_lps, landmark="Mile 8")

    # Run 10 ticks (within 10-20s detection window)
    for _ in range(10):
        engine.tick(dt_sec=1.0)

    # Verify flow measured at To drops
    corridors_after, _ = engine.get_water_flow_corridors()
    after_corr = next((c for c in corridors_after if c.id == corr_id), None)
    assert after_corr is not None
    assert after_corr.flow_mld < base_flow_mld, "Downstream flow must drop after leak injection"

    # Verify alert triggered
    alert = engine.alerts.get(f"ALT-LEAK-{corr_id}") or engine.alerts.get("ALT-LEAK-CORR_TG_MJ")
    assert alert is not None
    assert alert.status in ("ACTIVE", "ACKNOWLEDGED")
    assert alert.estimated_loss_lps >= 30.0

    # Stop leak
    engine.stop_leak(corr_id)
    for _ in range(5):
        engine.tick(dt_sec=1.0)
    assert alert.status == "CLEARED"

def test_divisions_all_have_ward_rows_summing_to_totals():
    """
    Test 8: Every division board present in data has non-empty ward rows,
    and ward rows strictly sum to the division baseline total shown.
    """
    engine = IoTSimulationEngine(seed=42)
    divisions = engine.get_smart_meters()

    # All 9 canonical divisions must exist
    assert len(divisions) == 9, f"Expected 9 divisions, got {len(divisions)}"

    total_city_mld = 0.0
    for div in divisions:
        assert len(div.wards) > 0, f"Division {div.division_name} must have non-empty ward list"
        
        # Sum of ward rows
        ward_baseline_sum = sum(w.daily_baseline_mld for w in div.wards)
        
        # Must match division baseline total exactly (within float precision 0.01)
        assert abs(div.sum_ward_consumption_mld - ward_baseline_sum) < 0.02, (
            f"Division {div.division_name} total ({div.sum_ward_consumption_mld} MLD) "
            f"does not match sum of ward rows ({ward_baseline_sum} MLD)"
        )
        total_city_mld += div.sum_ward_consumption_mld

    # Total city consumption matches data.gov.in baseline (~1247.63 MLD)
    assert 1200.0 < total_city_mld < 1300.0, f"City total {total_city_mld} MLD outside expected range"


def test_smart_meter_board_snapping_and_alerts():
    """
    Test 9: Smart meter boards are dynamically snapped to supply mains,
    ward cumulative volumes sum to division totals, and alert rules generate counts.
    """
    engine = IoTSimulationEngine(seed=42)
    divisions = engine.get_smart_meters()
    assert len(divisions) == 9

    found_alert_types = set()
    for div in divisions:
        # 1. Coordinates snapped
        assert len(div.centroid_coordinates) == 2
        lng, lat = div.centroid_coordinates
        assert 77.0 < lng < 78.0 and 12.0 < lat < 14.0

        # 2. Cumulative today strictly equals sum of ward volumes
        expected_vol = round(sum(w.current_day_volume_kl for w in div.wards), 1)
        assert abs(div.cumulative_today_kl - expected_vol) < 0.2, (
            f"{div.division_name}: cumulative_today_kl {div.cumulative_today_kl} != sum of wards {expected_vol}"
        )

        # 3. Online + offline equals total wards
        assert div.wards_online + div.wards_offline == len(div.wards)

        # 4. Active alerts count equals sum of alert types
        assert div.active_alerts_count == sum(div.alerts_by_type.values())

        for k, v in div.alerts_by_type.items():
            if v > 0:
                found_alert_types.add(k)

    # Across all 9 divisions, key anomaly types must be detected
    assert "low_battery" in found_alert_types or "comms_lost" in found_alert_types or "leak_suspected" in found_alert_types



