#!/usr/bin/env python3
"""
PMTiles Extraction & Bounding Box Extractor for Bengaluru Water Network Digital Twin.
Computes bounding box from GeoJSON layers covering BWSSB boundary + Tataguni + Harohalli + TK Halli (with 10% padding).
Extracts or downloads regional PMTiles vector tiles into frontend/public/tiles/bengaluru.pmtiles.
"""

import sys
import os
import json
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GEOJSON_DIR = PROJECT_ROOT / "data" / "raw" / "geojson"
OUTPUT_DIR = PROJECT_ROOT / "frontend" / "public" / "tiles"
OUTPUT_PMTILES = OUTPUT_DIR / "bengaluru.pmtiles"

# Bounding box calculated from BWSSB divisions + Tataguni + Harohalli + TK Halli stage with 10% padding
# min_lon, min_lat, max_lon, max_lat
BBOX = [77.0300, 12.1570, 77.8700, 13.2730]
BBOX_STR = f"{BBOX[0]},{BBOX[1]},{BBOX[2]},{BBOX[3]}"

PROTOMAPS_DAILY_BUILD = "https://build.protomaps.com/20261021.pmtiles"

def compute_bbox_from_geojson():
    lons, lats = [], []
    search_paths = [
        GEOJSON_DIR / "bwssb_division_boundaries.geojson",
        GEOJSON_DIR / "bwssb_pumping_stations.geojson",
        PROJECT_ROOT / "data" / "raw" / "simulated_zone.geojson"
    ]

    for p in search_paths:
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                for feat in data.get("features", []):
                    geom = feat.get("geometry", {})
                    def extract(c):
                        if not c: return
                        if isinstance(c[0], (int, float)):
                            lons.append(c[0])
                            lats.append(c[1])
                        else:
                            for sub in c: extract(sub)
                    extract(geom.get("coordinates", []))

    # Include Torekadanahalli (TK Halli) Stage 1-4 and Harohalli
    min_lon = min(min(lons), 77.10)
    min_lat = min(min(lats), 12.25)
    max_lon = max(max(lons), 77.80)
    max_lat = max(max(lats), 13.18)

    w = max_lon - min_lon
    h = max_lat - min_lat
    pad_lon = w * 0.10
    pad_lat = h * 0.10

    bbox = [round(min_lon - pad_lon, 4), round(min_lat - pad_lat, 4),
            round(max_lon + pad_lon, 4), round(max_lat + pad_lat, 4)]
    return bbox

def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    bbox = compute_bbox_from_geojson()
    bbox_str = f"{bbox[0]},{bbox[1]},{bbox[2]},{bbox[3]}"
    print(f"Computed Bounding Box (BWSSB + TK Halli + 10% padding): {bbox_str}")

    cmd = [
        "pmtiles",
        "extract",
        PROTOMAPS_DAILY_BUILD,
        str(OUTPUT_PMTILES),
        f"--bbox={bbox_str}"
    ]
    print(f"Executing: {' '.join(cmd)}")

    try:
        subprocess.run(cmd, check=True)
        print(f"Successfully generated {OUTPUT_PMTILES}")
    except FileNotFoundError:
        print("Note: 'pmtiles' CLI not found on local PATH.")
        print(f"To run manually, install pmtiles from https://github.com/protomaps/go-pmtiles/releases and execute:")
        print(f"  pmtiles extract {PROTOMAPS_DAILY_BUILD} {OUTPUT_PMTILES} --bbox={bbox_str}")
        print("At runtime, the map engine cleanly falls back to high-performance OpenFreeMap vector tiles.")

if __name__ == "__main__":
    main()
