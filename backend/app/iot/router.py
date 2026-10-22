"""
IoT FastApi Router.
Exposes REST endpoints and SSE telemetry deltas for the IoT subsystem.
Prefix: /api/v1/iot
All responses carry data_tier: "SIMULATED".
"""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from typing import Optional, List, Dict, Any
import json
import asyncio
import time
import logging

from .config import IOT_ENABLED, SIM_SEED, STATIONS_PATH, SMART_METER_RULES_PATH, SIMULATION_PARAMS_PATH, load_yaml
from .models import (
    StationOverview,
    DeviceStatus,
    IoTAlert,
    DivisionBoardSummary,
    LeakInjectionRequest,
    PumpFaultInjectionRequest,
    SensorFaultInjectionRequest,
    MessageEnvelope
)
from .sim.engine import sim_engine
from .sim.ring_buffer import ring_buffer
from .bus import event_bus

logger = logging.getLogger("bwssb_iot.router")

router = APIRouter(prefix="/api/v1/iot", tags=["IoT Digital Twin"])

def check_iot_enabled():
    if not IOT_ENABLED:
        raise HTTPException(
            status_code=404,
            detail="IoT Subsystem is disabled. Set IOT_ENABLED=true in environment or configuration to activate."
        )

@router.get("/stations", response_model=List[StationOverview])
async def get_stations():
    check_iot_enabled()
    return sim_engine.get_stations()

@router.get("/devices", response_model=List[DeviceStatus])
async def get_all_devices():
    check_iot_enabled()
    stations = sim_engine.get_stations()
    all_devs = []
    for s in stations:
        all_devs.extend(s.devices)
    return all_devs

@router.get("/devices/{tag}", response_model=DeviceStatus)
async def get_device_by_tag(tag: str):
    check_iot_enabled()
    for s in sim_engine.get_stations():
        for d in s.devices:
            if d.tag == tag:
                return d
    raise HTTPException(status_code=404, detail=f"Device with tag '{tag}' not found.")

@router.get("/timeseries")
async def get_timeseries(
    tag: str = Query(..., description="Device or Pump Tag (e.g. H1, FIT_TG_H1)"),
    signal: str = Query(..., description="Signal Name (e.g. current_avg, voltage_avg, flow_lps)"),
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
    step: Optional[float] = Query(5.0)
):
    check_iot_enabled()
    points = ring_buffer.get_timeseries(tag=tag, signal=signal, from_ts=from_ts, to_ts=to_ts, step_s=step)
    return {
        "tag": tag,
        "signal": signal,
        "data_tier": "SIMULATED",
        "points_count": len(points),
        "data": points
    }

@router.get("/mld-flows")
async def get_mld_flows():
    check_iot_enabled()
    corridors, balance = sim_engine.get_water_flow_corridors()
    return {
        "corridors": [c.model_dump() for c in corridors],
        "water_balance": balance.model_dump(),
        "data_tier": "SIMULATED"
    }

@router.get("/smart-meters", response_model=List[DivisionBoardSummary])
async def get_smart_meters():
    check_iot_enabled()
    return sim_engine.get_smart_meters()

@router.get("/smart-meters/{division_id}")
async def get_smart_meter_division(division_id: str):
    check_iot_enabled()
    all_divs = sim_engine.get_smart_meters()
    for d in all_divs:
        if d.division_name.lower() == division_id.lower() or d.division_name.lower().startswith(division_id.lower()):
            return d
    raise HTTPException(status_code=404, detail=f"Division '{division_id}' smart meter board not found.")

@router.get("/snapshot")
async def get_iot_snapshot():
    check_iot_enabled()
    stations = sim_engine.get_stations()
    alerts = sim_engine.get_alerts_list()
    smart_meters = sim_engine.get_smart_meters()
    corridors, balance = sim_engine.get_water_flow_corridors()
    return {
        "ts": sim_engine.sim_time,
        "clock_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sim_engine.sim_time)),
        "stations": [s.model_dump() for s in stations],
        "alerts": [a.model_dump() for a in alerts],
        "smart_meters": [m.model_dump() for m in smart_meters],
        "corridors": [c.model_dump() for c in corridors],
        "water_balance": balance.model_dump(),
        "active_injections": sim_engine.active_injections,
        "data_tier": "SIMULATED"
    }

@router.get("/alerts", response_model=List[IoTAlert])
async def get_iot_alerts(status: Optional[str] = Query(None, description="ACTIVE, ACKNOWLEDGED, CLEARED, SHELVED or None for active + 24h history")):
    check_iot_enabled()
    return sim_engine.get_alerts_list(status=status)

@router.post("/alerts/{alert_id}/acknowledge", response_model=IoTAlert)
async def acknowledge_alert(alert_id: str, operator: str = Query("OPERATOR")):
    check_iot_enabled()
    alert = sim_engine.acknowledge_alert(alert_id, operator=operator)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    return alert

@router.post("/alerts/{alert_id}/snooze", response_model=IoTAlert)
async def snooze_alert(alert_id: str, duration_s: float = Query(3600.0)):
    check_iot_enabled()
    alert = sim_engine.snooze_alert(alert_id, duration_s=duration_s)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    return alert

@router.post("/alerts/{alert_id}/clear", response_model=IoTAlert)
async def clear_alert(alert_id: str):
    check_iot_enabled()
    alert = sim_engine.clear_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail=f"Alert '{alert_id}' not found")
    return alert

@router.post("/simulate/leak")
async def simulate_leak(payload: LeakInjectionRequest):
    check_iot_enabled()
    sim_engine.inject_leak(
        pipe_segment_id=payload.pipe_segment_id,
        leak_rate_lps=payload.leak_rate_lps,
        landmark=payload.nearest_landmark
    )
    # Perform a few simulation ticks to advance physics and raise alarm immediately
    for _ in range(5):
        sim_engine.tick(1.0)

    return {
        "status": "LEAK_INJECTED",
        "segment_id": payload.pipe_segment_id,
        "leak_rate_lps": payload.leak_rate_lps,
        "data_tier": "SIMULATED",
        "active_alerts": [a.model_dump() for a in sim_engine.get_alerts_list(status="ACTIVE")]
    }

@router.post("/simulate/stop-leak")
async def stop_leak(payload: Optional[Dict[str, Any]] = None):
    check_iot_enabled()
    seg = payload.get("pipe_segment_id") if payload else None
    sim_engine.stop_leak(seg)
    for _ in range(5):
        sim_engine.tick(1.0)
    return {
        "status": "LEAKS_STOPPED",
        "data_tier": "SIMULATED",
        "active_alerts": [a.model_dump() for a in sim_engine.get_alerts_list(status="ACTIVE")]
    }

@router.post("/simulate/pump-fault")
async def simulate_pump_fault(payload: PumpFaultInjectionRequest):
    check_iot_enabled()
    sim_engine.inject_pump_fault(pump_id=payload.pump_id, fault_type=payload.fault_type)
    sim_engine.tick(1.0)
    return {
        "status": "PUMP_FAULT_INJECTED",
        "pump_id": payload.pump_id,
        "fault_type": payload.fault_type,
        "data_tier": "SIMULATED"
    }

@router.post("/simulate/sensor-fault")
async def simulate_sensor_fault(payload: SensorFaultInjectionRequest):
    check_iot_enabled()
    sim_engine.inject_sensor_fault(tag=payload.device_tag, fault_type=payload.fault_type)
    sim_engine.tick(1.0)
    return {
        "status": "SENSOR_FAULT_INJECTED",
        "device_tag": payload.device_tag,
        "fault_type": payload.fault_type,
        "data_tier": "SIMULATED"
    }

@router.post("/simulate/reset")
async def simulate_reset():
    check_iot_enabled()
    sim_engine.reset_simulation()
    return {
        "status": "SIMULATION_RESET_COMPLETE",
        "data_tier": "SIMULATED"
    }

@router.get("/admin/config")
async def get_iot_admin_config():
    check_iot_enabled()
    return {
        "stations": load_yaml(STATIONS_PATH),
        "rules": load_yaml(SMART_METER_RULES_PATH),
        "simulation": load_yaml(SIMULATION_PARAMS_PATH),
        "audit_log": sim_engine.injection_audit_log,
        "data_tier": "SIMULATED"
    }

@router.get("/stream")
async def iot_sse_stream(request: Request):
    """
    Server-Sent Events (SSE) telemetry stream.
    Multiplexes real-time deltas, alerts, leaks, and 5-second heartbeats.
    """
    check_iot_enabled()

    async def event_generator():
        last_heartbeat = time.time()
        while True:
            if await request.is_disconnected():
                break
            now = time.time()
            # 1. 5-second Heartbeat
            if now - last_heartbeat >= 5.0:
                last_heartbeat = now
                yield f"event: heartbeat\ndata: {json.dumps({'ts': now, 'status': 'OK'})}\n\n"

            try:
                stations = sim_engine.get_stations()
                alerts = sim_engine.get_alerts_list()
                sim_time = sim_engine.sim_time
                event_id = int(sim_time * 1000)

                payload = {
                    "ts": sim_time,
                    "clock_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sim_time)),
                    "data_tier": "SIMULATED",
                    "stations": [s.model_dump() for s in stations],
                    "alerts": [a.model_dump() for a in alerts]
                }
                # Emit typed telemetry event
                yield f"event: telemetry\ndata: {json.dumps(payload)}\n\n"
                # Emit typed alert event
                yield f"event: alert\ndata: {json.dumps([a.model_dump() for a in alerts])}\n\n"
                # Emit typed leak event
                leaks = list(sim_engine.active_injections.get("leaks", {}).values())
                yield f"event: leak\ndata: {json.dumps(leaks)}\n\n"
                # Default data packet
                yield f"id: {event_id}\ndata: {json.dumps(payload)}\n\n"
            except Exception as e:
                logger.error(f"SSE serialization error: {e}")
            await asyncio.sleep(1.0)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no"
        }
    )

