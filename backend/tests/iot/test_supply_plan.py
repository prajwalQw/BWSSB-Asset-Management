import os
import pytest
from fastapi.testclient import TestClient

os.environ["IOT_ENABLED"] = "true"

from backend.app.main import app
from backend.app.iot.scheduler.planner import SupplyPlanner
from backend.app.iot.scheduler.executor import plan_executor
from backend.app.iot.sim.engine import sim_engine

@pytest.fixture
def client():
    return TestClient(app)

def test_planner_feasibility_and_bounds():
    planner = SupplyPlanner()
    plan = planner.solve(start_sim_time=0.0)
    
    assert plan["status"] == "OPTIMAL"
    assert len(plan["pump_schedule"]) == 96
    assert len(plan["valve_schedule"]) == 96
    assert len(plan["tank_forecast"]) == 96
    assert len(plan["ward_windows"]) == 4
    
    # Check KPI metrics
    kpis = plan["kpis"]
    assert kpis["demand_met_pct"] > 80.0
    assert kpis["energy_cost_inr"] > 0.0
    
    # Check that tank forecast levels stay within bounds (20% - 92%)
    for step in plan["tank_forecast"]:
        assert 15.0 <= step["GLR_MOUNT_JOY"] <= 95.0
        assert 15.0 <= step["GLR_HIGH_GROUNDS"] <= 95.0

def test_water_movement_corridors_and_velocity():
    movement = plan_executor.compute_water_movement(sim_time=3600.0 * 2.0) # 02:00 AM (off-peak pumping)
    
    assert "corridors" in movement
    assert len(movement["corridors"]) > 0
    
    # Assert velocities are physically reasonable (< 4 m/s for municipal transmission)
    for c in movement["corridors"]:
        assert 0.0 <= c["velocity_ms"] <= 4.0
        assert c["pipe_dn_mm"] > 0
        assert len(c["coordinates"]) >= 2
        
    assert "trips" in movement
    # At 2 AM, pumps are running so trips trails should exist
    assert len(movement["trips"]) > 0

def test_clock_control_and_endpoints(client):
    # Test setting simulation clock speed
    res = client.post("/api/v1/iot/sim/clock", json={"speed": 60, "paused": False})
    assert res.status_code == 200
    data = res.json()
    assert data["speed"] == 60.0
    assert data["paused"] is False
    
    # Test GET /api/v1/iot/plan/current
    plan_res = client.get("/api/v1/iot/plan/current")
    assert plan_res.status_code == 200
    plan_data = plan_res.json()
    assert "pump_schedule" in plan_data
    assert "ward_windows" in plan_data
    
    # Test GET /api/v1/iot/water-movement
    wm_res = client.get("/api/v1/iot/water-movement")
    assert wm_res.status_code == 200
    wm_data = wm_res.json()
    assert "corridors" in wm_data
    
    # Restore clock to 1x
    client.post("/api/v1/iot/sim/clock", json={"speed": 1, "paused": False})
