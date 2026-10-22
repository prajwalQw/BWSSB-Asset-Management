"""
Pump Power Monitor & Health Subsystem Router.
Provides endpoints for electrical telemetry, start-up inrush analysis,
learned steady-state bands, anomaly detection, drift forecasting,
backtesting, and editable knowledge base advisory diagnostics.
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional, Dict, Any, List
from ..hydraulics.pump_power_monitor import pump_monitor_engine
from ..routers.alerts import ALERTS_STATE
import time

router = APIRouter(prefix="/api/v1/pumps", tags=["Pump Power & Health Monitor"])


class AnomalyInjectionRequest(BaseModel):
    pump_id: str
    anomaly_type: str # "RUNNING_DRY", "BLOCKAGE", "VOLTAGE_IMBALANCE", "BEARING_FRICTION_DRIFT", "LOW_POWER_FACTOR", "FREQUENT_STARTS", "UNDERVOLTAGE", "OVERVOLTAGE"
    severity: float = 1.0


class ClearInjectionRequest(BaseModel):
    pump_id: str


@router.get("/monitors")
async def get_pump_monitors():
    """Returns current electrical and hydraulic power monitoring status for every pump."""
    eval_result = pump_monitor_engine.evaluate_pump_telemetry()
    
    # Synchronize any critical or warning pump alerts into the general ALERTS_STATE for decision support
    for alert in eval_result.get("alerts", []):
        alert_id = alert["alert_id"]
        if not any(a.get("alert_id") == alert_id for a in ALERTS_STATE):
            ALERTS_STATE.insert(0, {
                "alert_id": alert_id,
                "rule_id": f"RULE-PUMP-{alert['anomaly_type']}",
                "category": "PUMP_POWER",
                "severity": alert["severity"],
                "title": f"Pump Health Alert: {alert['pump_name']} - {alert['anomaly_name']}",
                "location": f"{alert['station_name']} ({alert['pump_id']})",
                "coordinates": alert["coordinates"],
                "metric_observed": f"{alert['variable']} ({alert['phase']}) = {alert['current_value']} {alert['unit']} ({alert['how_far_from_normal']}, threshold {alert['normal_threshold']})",
                "recommendation": f"Advisory Recommendation: {'; '.join(alert['suggested_actions'][:2])}. (Requires human sign-off; no automated control action).",
                "requires_human_approval": True,
                "human_decision_status": "PENDING_OPERATOR_DECISION",
                "operator_decision": None,
                "timestamp": alert["since_when"],
                "data_tier": "SIMULATED",
                "simulated": True
            })

    return eval_result


@router.get("/{pump_id}/trends")
async def get_pump_trends(pump_id: str):
    """Returns 48-sample historical trend series with learned steady-state bands."""
    result = pump_monitor_engine.get_pump_timeseries(pump_id)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.get("/{pump_id}/start-events")
async def get_pump_start_events(pump_id: str):
    """Returns recorded start-up inrush events and decay waveforms."""
    if pump_id not in pump_monitor_engine.pump_configs:
        raise HTTPException(status_code=404, detail=f"Unknown pump {pump_id}")
    events = pump_monitor_engine.get_start_events(pump_id)
    return {
        "pump_id": pump_id,
        "pump_name": pump_monitor_engine.pump_configs[pump_id].get("name", pump_id),
        "events": events,
        "total_recorded_starts": len(events),
        "provenance": "SIMULATED",
        "simulated": True
    }


@router.get("/energy-report")
async def get_energy_report():
    """Returns rolling 24h energy consumption, cost (₹ at config tariff), and specific energy (kWh/m3)."""
    return pump_monitor_engine.generate_energy_report()


@router.get("/anomalies")
async def get_anomaly_timeline():
    """Returns active and historical pump anomalies with advisory knowledge base diagnostics."""
    eval_result = pump_monitor_engine.evaluate_pump_telemetry()
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "active_alerts": eval_result.get("alerts", []),
        "disclaimer": "All anomaly classifications and remedial actions are advisory decision support recommendations.",
        "provenance": "SIMULATED",
        "simulated": True
    }


@router.get("/{pump_id}/forecast")
async def get_drift_forecast(pump_id: str, horizon_hours: int = Query(72, ge=6, le=168)):
    """
    Returns steady-state drift forecast with 95% uncertainty prediction intervals,
    time to alarm limit range, and backtest comparison vs static threshold.
    """
    result = pump_monitor_engine.forecast_steady_drift(pump_id, horizon_hours=horizon_hours)
    if "error" in result:
        raise HTTPException(status_code=404, detail=result["error"])
    return result


@router.post("/inject-scenario")
async def inject_pump_anomaly(req: AnomalyInjectionRequest):
    """Scenario control to inject pump faults for operational drills."""
    result = pump_monitor_engine.inject_anomaly_scenario(
        pump_id=req.pump_id,
        anomaly_type=req.anomaly_type,
        severity=req.severity
    )
    if "error" in result:
        raise HTTPException(status_code=400, detail=result["error"])
    return result


@router.post("/clear-scenario")
async def clear_pump_anomaly(req: ClearInjectionRequest):
    """Clears injected pump fault scenario."""
    return pump_monitor_engine.clear_injection(req.pump_id)


@router.get("/knowledge-base")
async def get_knowledge_base():
    """Returns the editable advisory knowledge base rules and diagnostic causes."""
    return pump_monitor_engine.kb
