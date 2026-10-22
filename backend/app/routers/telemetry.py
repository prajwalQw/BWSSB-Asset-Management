"""
Telemetry Router for Live IGNOAPI Ingestion.
Streams real-time metrics over Server-Sent Events (SSE).
All measurements arriving through IGNOAPI bridge carry data_tier: 'LIVE'.
"""

import json
import asyncio
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from ..bridge.ignoapi_bridge import bridge

router = APIRouter(prefix="/api/v1/telemetry", tags=["Live Telemetry"])

@router.get("/current")
async def get_current_telemetry():
    """Returns instantaneous live telemetry snapshot."""
    return bridge.get_latest_telemetry()

@router.get("/feed-health")
async def get_sensor_feed_health():
    """Returns feed health status for all digital twin sensors."""
    return bridge.get_sensor_feed_health()

@router.get("/stream")
async def stream_live_telemetry():
    """
    SSE stream emitting live sensor updates and 5-second heartbeats.
    Carries data_tier: 'LIVE' chip on every packet.
    """
    import time

    async def event_generator():
        last_heartbeat = time.time()
        while True:
            now = time.time()
            if now - last_heartbeat >= 5.0:
                last_heartbeat = now
                yield f"event: heartbeat\ndata: {json.dumps({'ts': now, 'status': 'OK'})}\n\n"

            data = bridge.get_latest_telemetry()
            payload = json.dumps(data)
            yield f"event: telemetry\ndata: {payload}\n\n"
            yield f"data: {payload}\n\n"
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
