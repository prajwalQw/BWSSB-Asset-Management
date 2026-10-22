"""
Main FastAPI Application Entrypoint.
Bengaluru Water Network Digital Twin Backend.
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

try:
    from slowapi import Limiter, _rate_limit_exceeded_handler
    from slowapi.util import get_remote_address
    from slowapi.errors import RateLimitExceeded
    from slowapi.middleware import SlowAPIMiddleware
    HAS_SLOWAPI = True
except ImportError:
    HAS_SLOWAPI = False
    Limiter = None
    _rate_limit_exceeded_handler = None
    RateLimitExceeded = Exception
    SlowAPIMiddleware = None

from .config import SERVER_HOST, SERVER_PORT
from .bridge.ignoapi_bridge import bridge
from .routers import assets, water_bodies, hydraulics, telemetry, alerts, admin, pumps
from .iot.config import IOT_ENABLED
from .iot.router import router as iot_router
from .iot.sim.engine import sim_engine
from .iot.scheduler.executor import plan_executor
from .agents.monitor import monitoring_agent
from .security.router import router as security_router

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("bwssb_digital_twin")

limiter = Limiter(key_func=get_remote_address, default_limits=["240/minute"]) if HAS_SLOWAPI else None

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Bengaluru Water Network Digital Twin Backend...")
    # Start background read-only IGNOAPI bridge
    await bridge.start()
    await monitoring_agent.start()
    sim_task = None
    if IOT_ENABLED:
        import asyncio
        async def supervised_sim_loop():
            logger.info("Starting supervised IoT simulation loop with auto-restart...")
            while True:
                try:
                    await sim_engine.start_loop()
                except asyncio.CancelledError:
                    break
                except Exception as ex:
                    logger.error(f"[SupervisedSimLoop] Unexpected error in simulation engine: {ex}. Auto-restarting loop in 2s...", exc_info=True)
                    await asyncio.sleep(2.0)

        sim_task = asyncio.create_task(supervised_sim_loop())
    yield
    if IOT_ENABLED:
        sim_engine.stop_loop()
        if sim_task and not sim_task.done():
            sim_task.cancel()
    await monitoring_agent.stop()
    logger.info("Shutting down Digital Twin Backend...")
    await bridge.stop()

app = FastAPI(
    title="Bengaluru Water Network Digital Twin API",
    description="Interactive map-based asset management and hydraulic simulation platform for BWSSB operations.",
    version="1.0.0",
    lifespan=lifespan
)

if HAS_SLOWAPI and limiter:
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
    app.add_middleware(SlowAPIMiddleware)

@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["X-XSS-Protection"] = "1; mode=block"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self' 'unsafe-inline' 'unsafe-eval' data: blob: http: https:;"
    )
    return response

# Exact development origins (no wildcard '*')
DEV_CORS_ORIGINS = [
    "http://localhost:5180",
    "http://127.0.0.1:5180",
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]

# Enable CORS for exact Vite frontend origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=DEV_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount API Routers
app.include_router(assets.router)
app.include_router(water_bodies.router)
app.include_router(hydraulics.router)
app.include_router(pumps.router)
app.include_router(telemetry.router)
app.include_router(alerts.router)
app.include_router(admin.router)
app.include_router(iot_router)
app.include_router(security_router)

@app.get("/api/v1/snapshot")
@app.get("/api/v1/iot/snapshot")
async def get_consolidated_snapshot():
    """
    Consolidated system snapshot endpoint.
    Fetched ONCE on app startup and reconnect. Delivers latest devices, active alerts,
    leaks, supply plan, monitoring agent status, and KPIs.
    """
    import time
    sim_time = sim_engine.sim_time if IOT_ENABLED else time.time()
    stations = sim_engine.get_stations() if IOT_ENABLED else []
    alerts_list = sim_engine.get_alerts_list() if IOT_ENABLED else []
    smart_meters = sim_engine.get_smart_meters() if IOT_ENABLED else []
    corridors, balance = sim_engine.get_water_flow_corridors() if IOT_ENABLED else ([], None)

    devices_latest = {}
    for stn in stations:
        for d in stn.devices:
            devices_latest[d.tag] = {
                "tag": d.tag,
                "type": d.type_code,
                "name": d.name,
                "quality": d.quality,
                "active": d.active,
                "comms": d.comms_state,
                "latest_values": d.latest_values
            }

    all_pumps = [p for s in stations for p in s.pumps]
    running_pumps = sum(1 for p in all_pumps if p.run_state == "RUNNING")
    total_pumps = len(all_pumps) if all_pumps else 3
    total_kwh = sum(p.energy_kwh for p in all_pumps) if all_pumps else 57100.0
    energy_mwh = round(total_kwh / 1000.0, 1)
    energy_cost_lakhs = round(total_kwh * 7.5 / 100000.0, 2)

    leak_entry = sim_engine.active_injections.get("leak") if IOT_ENABLED else None
    if isinstance(leak_entry, dict):
        leaks = [leak_entry]
    elif isinstance(sim_engine.active_injections.get("leaks"), dict):
        leaks = list(sim_engine.active_injections["leaks"].values())
    else:
        leaks = []
    water_loss_kld = round(sum(l.get("leak_rate_lps", 0.0) * 86.4 for l in leaks), 1)

    bridge_telemetry = bridge.get_latest_telemetry()

    plan_data = plan_executor.get_or_create_plan(sim_time) if IOT_ENABLED else {
        "status": "BALANCED",
        "mode": "AUTOMATIC",
        "current_dispatch_mld": balance.total_inflow_mld if balance else 2250.0,
        "target_storage_pct": 78.5,
        "updated_at": time.time()
    }
    water_movement = plan_executor.compute_water_movement(sim_time) if IOT_ENABLED else {}
    agent_status = monitoring_agent.get_status()

    return {
        "ts": sim_time,
        "clock_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sim_time)),
        "data_tier": "SIMULATED",
        "stations": [s.model_dump() for s in stations],
        "devices_latest": devices_latest,
        "alerts": [a.model_dump() for a in alerts_list],
        "smart_meters": [m.model_dump() for m in smart_meters],
        "corridors": [c.model_dump() for c in corridors] if corridors else [],
        "water_balance": balance.model_dump() if balance else {},
        "leaks": leaks,
        "active_injections": sim_engine.active_injections if IOT_ENABLED else {},
        "plan": plan_data,
        "water_movement": water_movement,
        "agent": agent_status,
        "kpis": {
            "running_pumps": running_pumps,
            "total_pumps": total_pumps,
            "energy_mwh": energy_mwh,
            "energy_cost_lakhs": energy_cost_lakhs,
            "water_loss_kld": water_loss_kld,
            "live_voltage_v": bridge_telemetry.get("voltage_v", 6590.0),
            "live_current_a": bridge_telemetry.get("motor_current_a", 108.2),
            "is_feed_fresh": bridge_telemetry.get("is_fresh", True)
        }
    }

@app.get("/api/v1/stream")
async def multiplexed_stream(request: Request):
    """
    Unified multiplexed Server-Sent Events (SSE) telemetry stream.
    Single app-wide stream delivering telemetry, alerts, leaks, plan, agent status,
    and 5-second heartbeats.
    """
    import json
    import time
    from fastapi.responses import StreamingResponse

    async def event_generator():
        last_heartbeat = time.time()
        while True:
            if await request.is_disconnected():
                break
            now = time.time()
            # 1. Heartbeat event every 5s
            if now - last_heartbeat >= 5.0:
                last_heartbeat = now
                yield f"event: heartbeat\ndata: {json.dumps({'ts': now, 'status': 'OK'})}\n\n"

            # 2. Telemetry packet (merging live bridge and IoT simulation)
            bridge_data = bridge.get_latest_telemetry()
            sim_time = sim_engine.sim_time if IOT_ENABLED else now
            stations = sim_engine.get_stations() if IOT_ENABLED else []
            all_pumps = [p for s in stations for p in s.pumps]
            running_pumps = sum(1 for p in all_pumps if p.run_state == "RUNNING")
            total_pumps = len(all_pumps) if all_pumps else 3
            total_kwh = sum(p.energy_kwh for p in all_pumps) if all_pumps else 57100.0

            telemetry_payload = {
                **bridge_data,
                "ts": sim_time,
                "clock_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sim_time)),
                "running_pumps": running_pumps,
                "total_pumps": total_pumps,
                "energy_mwh": round(total_kwh / 1000.0, 1),
                "energy_cost_lakhs": round(total_kwh * 7.5 / 100000.0, 2),
                "stations": [s.model_dump() for s in stations]
            }
            yield f"event: telemetry\ndata: {json.dumps(telemetry_payload)}\n\n"

            # 3. Alerts event
            alerts_list = sim_engine.get_alerts_list() if IOT_ENABLED else []
            yield f"event: alert\ndata: {json.dumps([a.model_dump() for a in alerts_list])}\n\n"

            # 4. Leaks event
            leak_item = sim_engine.active_injections.get("leak") if IOT_ENABLED else None
            stream_leaks = [leak_item] if isinstance(leak_item, dict) else (list(sim_engine.active_injections.get("leaks", {}).values()) if isinstance(sim_engine.active_injections.get("leaks"), dict) else [])
            yield f"event: leak\ndata: {json.dumps(stream_leaks)}\n\n"

            # 5. Plan and Water Movement event
            plan_payload = {
                "plan": plan_executor.get_or_create_plan(sim_time) if IOT_ENABLED else {},
                "water_movement": plan_executor.compute_water_movement(sim_time) if IOT_ENABLED else {}
            }
            yield f"event: plan\ndata: {json.dumps(plan_payload)}\n\n"

            # 6. Monitoring Agent event
            yield f"event: agent\ndata: {json.dumps(monitoring_agent.get_status())}\n\n"

            # 7. Default message
            yield f"data: {json.dumps(telemetry_payload)}\n\n"

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

@app.get("/api/v1/agent/status")
async def get_agent_status():
    return monitoring_agent.get_status()

@app.get("/api/v1/agent/log")
async def get_agent_log():
    return monitoring_agent.get_log()

@app.get("/healthz")
async def health_check():
    return {
        "status": "HEALTHY",
        "service": "BWSSB Digital Twin Backend",
        "governance_mode": "HUMAN_IN_THE_LOOP",
        "tiers_supported": ["REAL", "SIMULATED", "LIVE"],
        "hydraulic_engine": "WNTR (EPANET)"
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.app.main:app", host=SERVER_HOST, port=SERVER_PORT, reload=False)
