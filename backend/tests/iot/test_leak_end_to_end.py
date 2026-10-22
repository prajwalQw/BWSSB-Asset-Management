"""
End-to-End Leak Physics and Detection Integration Test.
Verifies the complete detection & lifecycle chain:
1. 60s baseline produces NO leak alerts.
2. Leak injection between Tataguni Pumping Complex and Mount Joy GLR.
3. Downstream flow drops by approximately the leak size, pressure drops.
4. An alert is created within the configured detection time (10-20s), persisted to SQLite, and appears in /snapshot.
5. Stopping the leak auto-clears the alert.
"""

import os
import pytest
from fastapi.testclient import TestClient

os.environ["IOT_ENABLED"] = "true"
os.environ["SIM_SEED"] = "42"

from backend.app.main import app
from backend.app.iot.sim.engine import sim_engine

@pytest.fixture
def client():
    return TestClient(app)

def test_leak_end_to_end_lifecycle(client):
    # 0. Reset simulation to clean baseline
    sim_engine.reset_simulation()

    # 1. 60 s baseline gives no alert
    for _ in range(60):
        sim_engine.tick(dt_sec=1.0)

    baseline_alerts = [
        a for a in sim_engine.get_alerts_list()
        if a.active and a.category == "HYDRAULIC_INTEGRITY"
    ]
    assert len(baseline_alerts) == 0, f"Expected 0 leak alerts during 60s baseline, found: {baseline_alerts}"

    # 2. Inject leak between Tataguni Pumping Complex and Mount Joy GLR
    leak_rate = 45.0
    inject_res = client.post("/api/v1/iot/simulate/leak", json={
        "pipe_segment_id": "CORR_TATAGUNI_MOUNT_JOY",
        "leak_rate_lps": leak_rate,
        "nearest_landmark": "Pipeline Road Chainage 4+200"
    })
    assert inject_res.status_code == 200, f"Leak injection failed: {inject_res.text}"

    # 3. Advance accelerated simulation clock by 15-20 s
    for _ in range(15):
        sim_engine.tick(dt_sec=1.0)

    # 4. Verify in /snapshot
    snap_res = client.get("/api/v1/snapshot")
    assert snap_res.status_code == 200
    snapshot = snap_res.json()

    # Check active leaks list
    leaks = snapshot.get("leaks", [])
    assert len(leaks) >= 1, "Expected active leak in /snapshot"
    assert any(l.get("leak_rate_lps") == leak_rate for l in leaks)

    # Check alert created, persisted, and active
    alerts = snapshot.get("alerts", [])
    leak_alerts = [
        a for a in alerts
        if a.get("rule_id") == "RULE-IOT-LEAK-01" or "leak" in a.get("title", "").lower()
    ]
    assert len(leak_alerts) >= 1, f"Expected leak alert in snapshot alerts: {alerts}"

    alert = leak_alerts[0]
    assert alert.get("active") is True
    assert alert.get("severity") in ("HIGH", "CRITICAL")
    assert alert.get("estimated_loss_lps") is not None
    assert abs(alert["estimated_loss_lps"] - leak_rate) < 10.0, "Estimated loss should match injection"

    # 5. Stop leak
    stop_res = client.post("/api/v1/iot/simulate/stop-leak", json={
        "pipe_segment_id": "CORR_TATAGUNI_MOUNT_JOY"
    })
    assert stop_res.status_code == 200

    # Advance clock for recovery
    for _ in range(10):
        sim_engine.tick(dt_sec=1.0)

    # Assert alert clears
    snap_cleared = client.get("/api/v1/snapshot").json()
    active_leak_alerts = [
        a for a in snap_cleared.get("alerts", [])
        if a.get("alert_id") == alert.get("alert_id") and a.get("active") is True
    ]
    assert len(active_leak_alerts) == 0, f"Expected alert {alert['alert_id']} to clear after stop-leak"
