"""
IoT Configuration and Feature Flag Module.
Reads IOT_ENABLED and all simulation / configuration paths.
"""

import os
from pathlib import Path
import yaml
import json

IOT_ENABLED = os.environ.get("IOT_ENABLED", "false").lower() in ("true", "1", "yes")
SIM_SEED = int(os.environ.get("SIM_SEED", "42"))

# Directory paths
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
PROJECT_ROOT = BACKEND_DIR.parent if BACKEND_DIR.name == "backend" else BACKEND_DIR
CONFIG_IOT_DIR = PROJECT_ROOT / "config" / "iot"
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
GEOJSON_DIR = RAW_DATA_DIR / "geojson"

DEVICE_TYPES_PATH = CONFIG_IOT_DIR / "device_types.yaml"
STATIONS_PATH = CONFIG_IOT_DIR / "stations.yaml"
NETWORK_FLOWS_PATH = CONFIG_IOT_DIR / "network_flows.yaml"
SMART_METER_RULES_PATH = CONFIG_IOT_DIR / "smart_meter_rules.yaml"
SIMULATION_PARAMS_PATH = CONFIG_IOT_DIR / "simulation_params.yaml"
ADVISORY_KB_PATH = CONFIG_IOT_DIR / "advisory_kb.json"
BOREWELLS_PATH = CONFIG_IOT_DIR / "borewells.yaml"
DIVISION_ALIASES_PATH = CONFIG_IOT_DIR / "division_aliases.yaml"
WARD_CONSUMPTION_CSV_PATH = RAW_DATA_DIR / "bwssb_ward_water_consumption_2026.csv"
DIVISION_BOUNDARIES_GEOJSON_PATH = GEOJSON_DIR / "bwssb_division_boundaries.geojson"

def load_yaml(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)
