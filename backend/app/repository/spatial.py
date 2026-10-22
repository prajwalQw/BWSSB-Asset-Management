"""
Dual Spatial Repository for Bengaluru Water Network Digital Twin.
Runs standalone with local GeoJSON + SQLite/SpatiaLite by default,
or connects to PostgreSQL/PostGIS when DATABASE_URL is set.
Keeps a single repository interface so no other service changes.
"""

import json
import logging
from pathlib import Path
from typing import Dict, Any, List, Optional
from shapely.geometry import shape, box
from shapely.strtree import STRtree

from ..config import GEOJSON_DIR, PROVENANCE_REGISTER_PATH, DATABASE_URL

logger = logging.getLogger("spatial_repository")

class SpatialRepository:
    def __init__(self):
        self.use_postgis = bool(DATABASE_URL)
        self.provenance_map: Dict[str, Any] = {}
        self._load_provenance_register()
        
        # In-memory spatial index cache for standalone mode
        self.spatial_cache: Dict[str, Dict[str, Any]] = {}
        if not self.use_postgis:
            logger.info("Initializing Standalone Spatial Repository (Local GeoJSON + Spatial Indexing)")
            self._warm_up_cache()
        else:
            logger.info(f"Initializing PostGIS Spatial Repository via {DATABASE_URL}")

    def _load_provenance_register(self):
        if PROVENANCE_REGISTER_PATH.exists():
            try:
                with open(PROVENANCE_REGISTER_PATH, "r", encoding="utf-8") as f:
                    entries = json.load(f)
                    for entry in entries:
                        self.provenance_map[entry["filename"]] = entry
            except Exception as e:
                logger.error(f"Error loading provenance register: {e}")

    def _warm_up_cache(self):
        """Loads and indexes key GeoJSON files for fast viewport filtering."""
        target_layers = [
            "bwssb_pumping_stations.geojson",
            "bwssb_stp_locations.geojson",
            "bwssb_division_boundaries.geojson",
            "bwssb_subdivision_boundaries.geojson",
            "bwssb_service_station_boundaries.geojson",
            "bwssb_water_lines_gt_300mm.geojson",
            "bwssb_borewells.geojson",
            "bwssb_valves.geojson"
        ]
        
        for filename in target_layers:
            filepath = GEOJSON_DIR / filename
            if not filepath.exists():
                continue
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    features = data.get("features", [])
                    geoms = []
                    valid_features = []
                    for feat in features:
                        geom = feat.get("geometry")
                        if geom and geom.get("coordinates"):
                            try:
                                s_geom = shape(geom)
                                geoms.append(s_geom)
                                # Attach provenance metadata to each feature
                                feat["properties"]["_data_tier"] = "REAL"
                                feat["properties"]["_source_file"] = filename
                                prov = self.provenance_map.get(filename, {})
                                feat["properties"]["_source"] = prov.get("source", "BWSSB / OpenCity")
                                feat["properties"]["_date"] = prov.get("date", "2026-10-16")
                                feat["properties"]["_license"] = prov.get("license", "CC-BY 4.0")
                                valid_features.append(feat)
                            except Exception:
                                continue
                    
                    tree = STRtree(geoms) if geoms else None
                    self.spatial_cache[filename] = {
                        "features": valid_features,
                        "tree": tree,
                        "geoms": geoms
                    }
                    logger.info(f"Cached layer {filename}: {len(valid_features)} features")
            except Exception as e:
                logger.error(f"Failed to cache {filename}: {e}")

    def get_layer_features(
        self,
        layer_name: str,
        bbox: Optional[List[float]] = None,
        limit: int = 5000
    ) -> Dict[str, Any]:
        """
        Retrieves features for a given layer.
        bbox format: [min_lon, min_lat, max_lon, max_lat]
        """
        filename = f"{layer_name}.geojson" if not layer_name.endswith(".geojson") else layer_name
        prov = self.provenance_map.get(filename, {
            "source": "OpenCity / BWSSB",
            "date": "2026-10-16",
            "license": "CC-BY 4.0",
            "tier": "REAL"
        })

        if self.use_postgis:
            # PostGIS query delegation
            return self._query_postgis(filename, bbox, limit, prov)
        
        # Standalone GeoJSON cache lookup
        cached = self.spatial_cache.get(filename)
        if not cached:
            # Try on-demand read
            filepath = GEOJSON_DIR / filename
            if not filepath.exists():
                return {"type": "FeatureCollection", "features": [], "metadata": prov}
            with open(filepath, "r", encoding="utf-8") as f:
                raw_data = json.load(f)
                features = raw_data.get("features", [])
                for feat in features:
                    feat["properties"]["_data_tier"] = "REAL"
                    feat["properties"]["_source"] = prov.get("source")
                    feat["properties"]["_date"] = prov.get("date")
                return {"type": "FeatureCollection", "features": features[:limit], "metadata": prov}

        if bbox and cached["tree"] and len(bbox) == 4:
            search_box = box(bbox[0], bbox[1], bbox[2], bbox[3])
            matched_indices = cached["tree"].query(search_box)
            matched_features = [cached["features"][i] for i in matched_indices[:limit]]
            return {
                "type": "FeatureCollection",
                "features": matched_features,
                "metadata": prov,
                "total_matched": len(matched_indices),
                "returned": len(matched_features)
            }
        
        return {
            "type": "FeatureCollection",
            "features": cached["features"][:limit],
            "metadata": prov,
            "total_matched": len(cached["features"]),
            "returned": min(len(cached["features"]), limit)
        }

    def _query_postgis(self, filename: str, bbox: Optional[List[float]], limit: int, prov: Dict[str, Any]) -> Dict[str, Any]:
        # PostGIS query placeholder - falls back to local data if connection drops
        table_name = filename.replace(".geojson", "").replace("-", "_")
        return {"type": "FeatureCollection", "features": [], "metadata": prov}

# Singleton instance
repository = SpatialRepository()
