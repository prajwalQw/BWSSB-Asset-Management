"""
Configuration module for Bengaluru Water Network Digital Twin backend.
Externalizes all paths, thresholds, and operational flags.
"""
import os
from pathlib import Path
# Configuration constants
BACKEND_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
RAW_DATA_DIR = DATA_DIR / "raw"
GEOJSON_DIR = RAW_DATA_DIR / "geojson"
CONFIG_DIR = PROJECT_ROOT / "config"

NETWORK_RULES_PATH = CONFIG_DIR / "network_rules.json"
SIMULATED_ZONE_PATH = CONFIG_DIR / "simulated_zone.yaml"
VARIABLES_YAML_PATH = CONFIG_DIR / "variables.yaml"
SENSOR_MAP_PATH = CONFIG_DIR / "sensor_map.yaml"
PROVENANCE_REGISTER_PATH = RAW_DATA_DIR / "checksums_and_origins.json"

# Database Configuration
DATABASE_URL = os.environ.get("DATABASE_URL", None) # If set, connects to PostgreSQL/PostGIS
SQLITE_DB_PATH = DATA_DIR / "asset_intelligence.db"

# IGNOAPI Bridge Configuration
IGNOAPI_HOST = os.environ.get("IGNOAPI_HOST", "127.0.0.1")
IGNOAPI_PORT = int(os.environ.get("IGNOAPI_PORT", 8899))
IGNOAPI_ALLOW_WRITES = os.environ.get("IGNOAPI_ALLOW_WRITES", "false").lower() in ("true", "1", "yes")

# Service Configuration
SERVER_HOST = "127.0.0.1"
SERVER_PORT = 8000
TELEMETRY_BROADCAST_INTERVAL_SEC = 1.0
