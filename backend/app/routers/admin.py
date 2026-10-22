"""
Admin Configuration Router.
Adheres strictly to Rule 2:
'Nothing hardcoded: network geometry, assets, sensor-to-variable mappings,
thresholds, tolerances, pump ratings and rules all live in config files or a database,
editable through an admin screen.'
"""

import json
import yaml
from fastapi import APIRouter, HTTPException
from typing import Dict, Any
from ..config import NETWORK_RULES_PATH, SIMULATED_ZONE_PATH
from ..hydraulics.engine import engine

router = APIRouter(prefix="/api/v1/admin", tags=["Admin Configuration"])

@router.get("/rules")
async def get_network_rules():
    """Returns current editable network thresholds, pump ratings, and alert rules."""
    if not NETWORK_RULES_PATH.exists():
        raise HTTPException(status_code=404, detail="Rules config file not found")
    with open(NETWORK_RULES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

@router.put("/rules")
async def update_network_rules(payload: Dict[str, Any]):
    """Saves updated thresholds, pump ratings, and rules without code modifications."""
    try:
        with open(NETWORK_RULES_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)
        return {"status": "SUCCESS", "message": "Network rules and thresholds updated successfully."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to save rules: {e}")

@router.get("/zone-config")
async def get_zone_config():
    """Returns YAML configuration for the single simulated zone."""
    if not SIMULATED_ZONE_PATH.exists():
        raise HTTPException(status_code=404, detail="Simulated zone config file not found")
    with open(SIMULATED_ZONE_PATH, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

@router.put("/zone-config")
async def update_zone_config(payload: Dict[str, Any]):
    """Updates simulated zone configuration and triggers immediate WNTR model rebuild."""
    try:
        with open(SIMULATED_ZONE_PATH, "w", encoding="utf-8") as f:
            yaml.safe_dump(payload, f, sort_keys=False)
        # Hot-reload WNTR engine
        engine.load_config_and_build_model()
        return {"status": "SUCCESS", "message": "Simulated zone config updated and WNTR model re-synthesized."}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update zone config: {e}")
