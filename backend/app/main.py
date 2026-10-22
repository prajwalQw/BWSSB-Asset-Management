"""
Main FastAPI Application Entrypoint.
Bengaluru Water Network Digital Twin Backend.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
import logging

from .config import SERVER_HOST, SERVER_PORT
from .bridge.ignoapi_bridge import bridge
from .routers import assets, water_bodies, hydraulics, telemetry, alerts, admin, pumps

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(name)s] %(message)s"
)
logger = logging.getLogger("bwssb_digital_twin")

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Bengaluru Water Network Digital Twin Backend...")
    # Start background read-only IGNOAPI bridge
    await bridge.start()
    yield
    logger.info("Shutting down Digital Twin Backend...")
    await bridge.stop()

app = FastAPI(
    title="Bengaluru Water Network Digital Twin API",
    description="Interactive map-based asset management and hydraulic simulation platform for BWSSB operations.",
    version="1.0.0",
    lifespan=lifespan
)

# Enable CORS for Vite frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
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
    uvicorn.run("backend.app.main:app", host=SERVER_HOST, port=SERVER_PORT, reload=True)
