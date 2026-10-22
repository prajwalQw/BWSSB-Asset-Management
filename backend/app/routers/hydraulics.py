"""
Hydraulics Router for Single Simulated Representative Zone.
Exposes WNTR simulation endpoints, scenario injection controls,
sensor source toggles (SIMULATED vs IGNOAPI), and mass balance checks.
All returned simulated elements carry simulated: true and data_tier: 'SIMULATED'.
"""

from fastapi import APIRouter, Query, HTTPException
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from ..hydraulics.engine import engine
from ..hydraulics.leak_detector import leak_detector
from .alerts import register_leak_alert

router = APIRouter(prefix="/api/v1/hydraulics", tags=["Hydraulic Twin"])

class LeakInjectionRequest(BaseModel):
    pipe_id: str
    leak_flow_lps: float = 60.0

class ValveControlRequest(BaseModel):
    pipe_or_valve_id: str
    action: str = "CLOSED" # "CLOSED" | "THROTTLED"

class PumpTripRequest(BaseModel):
    pump_id: str

class DemandModulationRequest(BaseModel):
    demand_multiplier: float = 1.25

class SensorPerturbationRequest(BaseModel):
    sensor_id: str
    perturbation_type: str # "drift" | "stuck"
    value: float

class SensorSourceToggleRequest(BaseModel):
    source: str # "SIMULATED" | "IGNOAPI"

@router.get("/zone")
async def get_simulated_zone():
    """Returns current simulated network graph (nodes, pipes, sensors, valves)."""
    if not engine.last_results:
        return engine.run_simulation()
    return engine.last_results

@router.post("/simulate")
async def trigger_simulation(
    scenario: str = Query("BASELINE", description="Scenario: 'BASELINE', 'LEAK_INJECTION', 'PUMP_TRIP'"),
    target_pipe: Optional[str] = Query(None, description="Target pipe for leak")
):
    """Executes WNTR hydraulic simulation for chosen operational scenario."""
    if scenario == "LEAK_INJECTION":
        return engine.run_simulation(leak_pipe=target_pipe or "PIPE_CORRIDOR_10", leak_flow_lps=80.0)
    elif scenario == "PUMP_TRIP":
        return engine.run_simulation(pump_to_trip="PUMP_TG_01")
    else:
        engine.reset_scenarios()
        return engine.run_simulation()

@router.post("/scenarios/inject-leak")
async def inject_leak(req: LeakInjectionRequest):
    """Injects a pipe burst/leak anomaly at a chosen pipe with size/flow in LPS."""
    sim_res = engine.run_simulation(leak_pipe=req.pipe_id, leak_flow_lps=req.leak_flow_lps)
    leaks = sim_res.get("leak_events", [])
    if leaks:
        for leak in leaks:
            register_leak_alert(leak)
    return sim_res

@router.post("/scenarios/close-valve")
async def close_valve(req: ValveControlRequest):
    """Closes or throttles an isolation valve or pipe segment."""
    return engine.run_simulation(valve_to_close=req.pipe_or_valve_id)

@router.post("/scenarios/trip-pump")
async def trip_pump(req: PumpTripRequest):
    """Simulates an electromechanical trip on a chosen pumping station unit."""
    return engine.run_simulation(pump_to_trip=req.pump_id)

@router.post("/scenarios/modulate-demand")
async def modulate_demand(req: DemandModulationRequest):
    """Scales consumer cluster demand across the corridor."""
    return engine.run_simulation(demand_multiplier=req.demand_multiplier)

@router.post("/scenarios/sensor-perturbation")
async def perturb_sensor(req: SensorPerturbationRequest):
    """Applies sensor drift or stuck sensor value."""
    engine.set_sensor_perturbation(req.sensor_id, req.perturbation_type, req.value)
    return engine.run_simulation()

@router.post("/scenarios/reset")
async def reset_scenarios():
    """Clears all active perturbations back to baseline supply."""
    engine.reset_scenarios()
    return engine.run_simulation()

@router.post("/sensors/{sensor_id}/source")
async def toggle_sensor_source(sensor_id: str, req: SensorSourceToggleRequest):
    """Toggles sensor value source between 'SIMULATED' and 'IGNOAPI'."""
    engine.set_sensor_source(sensor_id, req.source)
    return {"sensor_id": sensor_id, "active_source": req.source, "status": "UPDATED"}

@router.get("/mass-balance")
async def get_mass_balance():
    """Returns network volume mass balance calculation for continuity verification."""
    if not engine.last_results or "metadata" not in engine.last_results:
        engine.run_simulation()
    return engine.last_results["metadata"]["mass_balance"]

@router.get("/audit-log")
async def get_scenario_audit_log():
    """Returns history of all simulated scenario injections."""
    return {"audit_log": engine.scenario_audit_log}

@router.get("/meters")
async def get_flow_meters():
    """Returns flow meters along the corridor."""
    if not engine.last_results:
        engine.run_simulation()
    return {"flow_meters": engine.last_results.get("flow_meters", []), "data_tier": "SIMULATED"}

@router.get("/sensors")
async def get_pressure_sensors():
    """Returns pressure sensors along the corridor."""
    if not engine.last_results:
        engine.run_simulation()
    return {"pressure_sensors": engine.last_results.get("pressure_sensors", []), "data_tier": "SIMULATED"}

@router.get("/pumps")
async def get_pump_metrics():
    """Returns pump status, power draw, and efficiency."""
    pumps = engine.config.get("pumps", [])
    output = []
    for p in pumps:
        is_running = (p["id"] != "PUMP_TG_03_STANDBY" and p.get("status") != "CLOSED")
        output.append({
            "id": p["id"],
            "name": p["name"],
            "status": "RUNNING" if is_running else "STANDBY",
            "speed_rpm": 1450 if is_running else 0,
            "active_power_kw": p.get("power_kw", 1200.0) if is_running else 0.0,
            "discharge_flow_lps": 320.0 if is_running else 0.0,
            "efficiency_pct": 81.2 if is_running else 0.0,
            "data_tier": "SIMULATED",
            "simulated": True
        })
    return {"pumps": output, "data_tier": "SIMULATED"}

@router.get("/leak-detection")
async def get_leak_detection_status():
    """
    Returns active leak detection analysis:
    - Segment-level mass balance evaluations
    - Verified leak events with confidence, start time, loss, and probabilistic localisation
    - Sensor fault integrity statuses
    """
    if not engine.last_results or "metadata" not in engine.last_results:
        engine.run_simulation()
    
    leak_data = engine.last_results.get("metadata", {}).get("leak_detection", {})
    return leak_data

@router.post("/leak-detection/run-validation")
async def run_leak_validation():
    """
    Runs automated validation suite with varying injected leak sizes (0, 5, 15, 30, 60, 100 LPS)
    and sensor fault checks. Generates and updates docs/LEAK_VALIDATION.md.
    """
    report = leak_detector.run_validation_benchmarks(engine)
    return report

