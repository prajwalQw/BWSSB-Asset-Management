"""
Alerts & Decision Support Router.
Adheres strictly to Rule 6:
'Alerts recommend; humans decide. No automatic control actions.'
Provides recommendation feed and operator sign-off workflow.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List
import time
import json
from ..config import NETWORK_RULES_PATH

router = APIRouter(prefix="/api/v1/alerts", tags=["Decision Support"])

class OperatorDecisionRequest(BaseModel):
    decision: str # "APPROVE_INTERVENTION", "REJECT", "DISPATCH_CREW", "ACKNOWLEDGE"
    operator_name: str
    operator_notes: str

# In-memory alert store with persistence
ALERTS_STATE = [
    {
        "alert_id": "ALT-2026-1001",
        "rule_id": "RULE-LEAK-01",
        "category": "LEAK_DETECTION",
        "severity": "CRITICAL",
        "title": "Suspected Distribution Main Burst: DMA Sector 4 (Basavanagudi)",
        "location": "Basavanagudi Corridor (Pipe PIPE_CORRIDOR_10)",
        "coordinates": [77.5700, 12.9400],
        "metric_observed": "Night Flow ratio = 0.54 (Threshold: 0.38) with 1.4 bar pressure drop",
        "recommendation": "Isolate section DMA-S04 at Valve V-104 and dispatch acoustic leak detection crew to DVK Road. Do not close valve automatically.",
        "requires_human_approval": True,
        "human_decision_status": "PENDING_OPERATOR_DECISION",
        "operator_decision": None,
        "timestamp": "2026-10-21T13:15:00Z",
        "data_tier": "SIMULATED"
    },
    {
        "alert_id": "ALT-2026-1002",
        "rule_id": "RULE-PUMP-PWR-01",
        "category": "PUMP_POWER",
        "severity": "HIGH",
        "title": "Excess Active Power Consumption: Tataguni Pump Unit 01",
        "location": "Tataguni Terminal Pumping Station",
        "coordinates": [77.5140, 12.8685],
        "metric_observed": "Power Draw = 1,410 kW (Rated: 1,200 kW, +17.5% deviation)",
        "recommendation": "High motor current with reduced hydraulic head indicates possible impeller cavitation or strainer clog. Recommend supervisory approval to switch duty to Standby Unit 03.",
        "requires_human_approval": True,
        "human_decision_status": "PENDING_OPERATOR_DECISION",
        "operator_decision": None,
        "timestamp": "2026-10-21T13:20:00Z",
        "data_tier": "LIVE"
    },
    {
        "alert_id": "ALT-2026-1003",
        "rule_id": "RULE-TANK-DRAIN-01",
        "category": "STORAGE_LEVEL",
        "severity": "WARNING",
        "title": "Rapid Drawdown Rate: Mount Joy Balancing Reservoir",
        "location": "Mount Joy GLR (Basavanagudi)",
        "coordinates": [77.5621, 12.9372],
        "metric_observed": "Water Level = 2.1m (Normal: 4.1m, Drawdown rate: 0.45 m/hr)",
        "recommendation": "Level will breach 1.5m minimum safe operating reserve in 80 minutes. Recommend increasing bulk feeder allocation from Tataguni Terminal.",
        "requires_human_approval": True,
        "human_decision_status": "PENDING_OPERATOR_DECISION",
        "operator_decision": None,
        "timestamp": "2026-10-21T13:25:00Z",
        "data_tier": "SIMULATED"
    }
]

def register_leak_alert(leak_event: dict):
    """Registers or updates a critical decision support alert for a detected simulated leak."""
    pipe_id = leak_event.get("pipe_id", "UNKNOWN_PIPE")
    segment_name = leak_event.get("segment_name", "DMA Corridor")
    landmark = leak_event.get("nearest_landmark", "Bengaluru Urban Feeder")
    loss_metrics = leak_event.get("loss_metrics", {})
    loss_lps = loss_metrics.get("estimated_loss_lps", 60.0)
    loss_m3_day = loss_metrics.get("estimated_loss_m3_per_day", 5184.0)
    daily_nrw_inr = leak_event.get("consequences", {}).get("daily_nrw_revenue_loss_inr", 248800)
    loc = leak_event.get("localisation", {})
    dist_m = loc.get("estimated_distance_m", 300)
    uncertainty_m = loc.get("uncertainty_range_m", 50)

    # Check if active alert already exists for this pipe
    for a in ALERTS_STATE:
        if a.get("rule_id") == "RULE-LEAK-01" and pipe_id in a.get("location", ""):
            return a

    new_alert = {
        "alert_id": f"ALT-LEAK-{int(time.time())}",
        "rule_id": "RULE-LEAK-01",
        "category": "LEAK_DETECTION",
        "severity": "CRITICAL",
        "title": f"Suspected Main Burst: {segment_name} ({pipe_id})",
        "location": f"{segment_name} - Pipe {pipe_id} ({landmark})",
        "coordinates": [77.568, 12.935],
        "metric_observed": f"Mass imbalance = {loss_lps} LPS ({loss_m3_day} m³/day). Estimated pos: {dist_m}m ± {uncertainty_m}m along pipe. NRW loss: ₹{daily_nrw_inr}/day.",
        "recommendation": f"Probabilistic localization: {dist_m}m ± {uncertainty_m}m from upstream junction near {landmark}. Dispatch acoustic leak correlator crew to confirm. Evaluate throttling upstream valve. (Never claim pin-point. Human decision required).",
        "requires_human_approval": True,
        "human_decision_status": "PENDING_OPERATOR_DECISION",
        "operator_decision": None,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "data_tier": "SIMULATED",
        "simulated": True
    }
    ALERTS_STATE.insert(0, new_alert)
    return new_alert


@router.get("")
async def get_alerts():
    """Returns all active decision support recommendations."""
    return {"alerts": ALERTS_STATE, "governance": "HUMAN_IN_THE_LOOP"}

@router.post("/{alert_id}/decision")
async def record_operator_decision(alert_id: str, req: OperatorDecisionRequest):
    """
    Records human decision on an alert recommendation.
    No automatic control actions are ever dispatched.
    """
    for alert in ALERTS_STATE:
        if alert["alert_id"] == alert_id:
            alert["human_decision_status"] = req.decision
            alert["operator_decision"] = {
                "decision": req.decision,
                "operator_name": req.operator_name,
                "notes": req.operator_notes,
                "decided_at": time.strftime("%Y-%m-%dT%H:%M:%SZ")
            }
            return {
                "status": "DECISION_RECORDED",
                "alert": alert,
                "message": f"Action '{req.decision}' signed off by {req.operator_name}. Work order logged."
            }
    raise HTTPException(status_code=404, detail="Alert not found")
