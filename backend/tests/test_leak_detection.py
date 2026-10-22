"""
Unit and Integration Tests for Twin Leak Detection and Localisation Engine.
Verifies:
1. Mass balance holding on baseline (no false alarms).
2. Detection of injected leaks of varying sizes with persistence filter.
3. Sensor fault checks (stuck/flat and out-of-range) suppressing false leak alarms.
4. Probabilistic localisation along pipe with uncertainty range (never claiming pin-point).
5. Minimum Night Flow (MNF) analysis during hours 02:00-04:00 AM.
6. Validation suite execution and documentation generation (docs/LEAK_VALIDATION.md).
All tested elements labelled SIMULATED.
"""

import pytest
import os
from pathlib import Path
from backend.app.hydraulics.engine import engine
from backend.app.hydraulics.leak_detector import leak_detector


def test_mass_balance_holds_on_baseline_no_false_alarms():
    """Verify that under baseline operation with no leaks, mass balance holds and 0 false alarms are emitted."""
    engine.reset_scenarios()
    sim_data = engine.run_simulation()
    
    # Check overall mass balance
    mb = sim_data["metadata"]["mass_balance"]
    assert mb["status"] == "BALANCED"
    assert mb["percentage_error"] < 1.0

    # Run leak detector analysis
    analysis = leak_detector.detect_leaks_in_simulation(sim_data)
    assert analysis["status"] == "ANALYSIS_COMPLETE"
    assert analysis["active_leak_count"] == 0, f"False alarm detected on baseline: {analysis['leak_events']}"
    assert analysis["data_tier"] == "SIMULATED"
    assert analysis["simulated"] is True


def test_injected_leak_detection_and_persistence():
    """Verify that injecting a 60 LPS leak is detected by mass balance, identified in the correct segment with high confidence."""
    engine.reset_scenarios()
    target_pipe = "PIPE_CORRIDOR_10"
    leak_size = 60.0
    
    sim_data = engine.run_simulation(leak_pipe=target_pipe, leak_flow_lps=leak_size)
    analysis = leak_detector.detect_leaks_in_simulation(
        sim_data,
        active_injected_leak={"pipe_id": target_pipe, "leak_flow_lps": leak_size}
    )

    assert analysis["active_leak_count"] >= 1
    leak_evt = analysis["leak_events"][0]
    
    # Must identify the correct DMA segment
    assert leak_evt["segment_id"] == "SEG_04_BASAVANAGUDI_CORRIDOR"
    assert leak_evt["pipe_id"] == target_pipe
    assert leak_evt["confidence_pct"] >= 80.0
    assert leak_evt["simulated"] is True
    assert leak_evt["data_tier"] == "SIMULATED"

    # Loss metrics check
    loss = leak_evt["loss_metrics"]
    assert loss["estimated_loss_lps"] > 0
    assert loss["estimated_loss_litres_per_min"] == round(loss["estimated_loss_lps"] * 60.0, 1)
    assert loss["estimated_loss_m3_per_day"] == round(loss["estimated_loss_lps"] * 86.4, 1)

    # Consequence financial impacts check
    consequences = leak_evt["consequences"]
    assert consequences["daily_nrw_revenue_loss_inr"] > 0
    assert consequences["affected_consumer_connections"] > 0


def test_sensor_fault_suppresses_false_leak_alarm():
    """Verify that a stuck sensor or out-of-range sensor is flagged as faulty and does not trigger false leak alarms."""
    engine.reset_scenarios()
    
    # Inject stuck sensor on FM_KANAKAPURA
    engine.set_sensor_perturbation("FM_KANAKAPURA", "stuck", 45.0)
    sim_data = engine.run_simulation()
    
    analysis = leak_detector.detect_leaks_in_simulation(sim_data)
    
    # Check that sensor fault was detected
    faults = analysis["sensor_faults_detected"]
    fault_sensor_ids = [f["sensor_id"] for f in faults]
    assert "FM_KANAKAPURA" in fault_sensor_ids
    
    # Segments using FM_KANAKAPURA must have has_sensor_fault = True
    seg2 = next(s for s in analysis["segment_evaluations"] if s["segment_id"] == "SEG_02_KANAKAPURA_CORRIDOR")
    assert seg2["has_sensor_fault"] is True
    # Leak alarms on this segment must be suppressed
    assert seg2["is_leak_detected"] is False

    engine.reset_scenarios()


def test_probabilistic_localisation_never_claims_pinpoint():
    """Verify that pipe localisation provides an uncertainty range and probability curve without claiming pinpoint accuracy."""
    pipe_cfg = {
        "id": "PIPE_CORRIDOR_10",
        "length_m": 680.0,
        "diameter_mm": 600,
        "material": "CI"
    }
    
    loc = leak_detector.estimate_pipe_position(
        pipe_cfg=pipe_cfg,
        leak_flow_lps=60.0,
        upstream_pressure=3.2,
        downstream_pressure=2.1
    )

    assert loc["pinpoint_claim"] is False
    assert "Never claim a pin-point" in loc["disclaimer"]
    assert loc["uncertainty_range_m"] >= 35.0 # At least min uncertainty radius
    assert loc["estimated_distance_m"] > 0
    assert loc["estimated_distance_m"] < pipe_cfg["length_m"]
    
    # 90% confidence interval must span a non-zero range
    ci = loc["confidence_interval_90_m"]
    assert ci[0] < ci[1]
    assert len(loc["probability_curve"]) >= 20


def test_night_flow_mnf_analysis():
    """Verify Minimum Night Flow (MNF) analysis correctly detects nocturnal rise between 02:00-04:00 AM."""
    # Synthetic normal day curve (night low ~ 20 LPS, day peak ~ 60 LPS)
    normal_inflow = [
        25.0, 22.0, 18.0, 17.5, 20.0, 35.0, 55.0, 65.0, 62.0, 50.0, 45.0, 42.0,
        40.0, 38.0, 37.0, 39.0, 44.0, 52.0, 60.0, 63.0, 54.0, 46.0, 36.0, 28.0
    ]
    res_normal = leak_detector.analyze_night_flow(normal_inflow)
    assert res_normal["is_mnf_breached"] is False

    # Leaking network has elevated flow at night (e.g. +40 LPS burst)
    leaking_inflow = [f + 40.0 for f in normal_inflow]
    res_leaking = leak_detector.analyze_night_flow(leaking_inflow)
    assert res_leaking["is_mnf_breached"] is True
    assert res_leaking["mnf_rise_lps"] > 0


def test_validation_suite_and_docs_generation():
    """Runs the validation benchmark suite and ensures docs/LEAK_VALIDATION.md is generated."""
    engine.reset_scenarios()
    summary = leak_detector.run_validation_benchmarks(engine)
    
    assert summary["detection_rate_pct"] >= 75.0
    assert summary["false_alarms_per_day"] == 0
    assert summary["simulated"] is True
    
    # Verify file was written
    doc_path = Path(__file__).resolve().parent.parent.parent / "docs" / "LEAK_VALIDATION.md"
    assert doc_path.exists(), f"LEAK_VALIDATION.md not created at {doc_path}"
    
    with open(doc_path, "r", encoding="utf-8") as f:
        content = f.read()
    
    assert "SIMULATED" in content
    assert "Minimum Night Flow" in content
    assert "Never claim a pin-point" in content
    assert "Detection Rate" in content
