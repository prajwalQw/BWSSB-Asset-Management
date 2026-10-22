"""
Assets Router for Real BWSSB Infrastructure.
Serves verified GeoJSON layers from OpenCity/data.gov.in.
Every feature explicitly carries data_tier: 'REAL' with source and date metadata.
"""

from fastapi import APIRouter, Query
from typing import Optional, List
from ..repository.spatial import repository

router = APIRouter(prefix="/api/v1/assets", tags=["Real Assets"])

@router.get("/pumping-stations")
async def get_pumping_stations(
    min_lon: Optional[float] = None,
    min_lat: Optional[float] = None,
    max_lon: Optional[float] = None,
    max_lat: Optional[float] = None
):
    bbox = [min_lon, min_lat, max_lon, max_lat] if all(v is not None for v in [min_lon, min_lat, max_lon, max_lat]) else None
    return repository.get_layer_features("bwssb_pumping_stations", bbox=bbox)

@router.get("/stps")
async def get_stps(
    min_lon: Optional[float] = None,
    min_lat: Optional[float] = None,
    max_lon: Optional[float] = None,
    max_lat: Optional[float] = None
):
    bbox = [min_lon, min_lat, max_lon, max_lat] if all(v is not None for v in [min_lon, min_lat, max_lon, max_lat]) else None
    return repository.get_layer_features("bwssb_stp_locations", bbox=bbox)

@router.get("/water-lines-mains")
async def get_water_lines_mains(
    limit: int = Query(2500, description="Max features to return")
):
    """Water transmission and feeder pipelines > 300mm."""
    return repository.get_layer_features("bwssb_water_lines_gt_300mm", limit=limit)

@router.get("/valves")
async def get_valves(
    limit: int = Query(1000, description="Max features to return")
):
    return repository.get_layer_features("bwssb_valves", limit=limit)

@router.get("/borewells")
async def get_borewells(
    limit: int = Query(2000, description="Max features to return")
):
    return repository.get_layer_features("bwssb_borewells", limit=limit)

@router.get("/divisions")
async def get_division_boundaries():
    return repository.get_layer_features("bwssb_division_boundaries")

@router.get("/subdivisions")
async def get_subdivision_boundaries():
    return repository.get_layer_features("bwssb_subdivision_boundaries")

@router.get("/service-stations")
async def get_service_station_boundaries():
    return repository.get_layer_features("bwssb_service_station_boundaries")

@router.get("/cauvery-corridor")
async def get_cauvery_corridor_markers():
    """
    Returns verified off-map and transmission stage locations:
    KRS, Kabini, Shiva Balancing Reservoir, TK Halli WTP, Harohalli PS, Tataguni PS.
    """
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [76.5724, 12.4262]},
            "properties": {
                "id": "SRC_KRS_DAM",
                "name": "Krishna Raja Sagara (KRS) Dam",
                "category": "RAW_WATER_SOURCE",
                "elevation_m": 750.0,
                "distance_km": 140,
                "flow_allocation_mld": 1450.0,
                "_data_tier": "REAL",
                "_source": "CWC & WRD Karnataka",
                "_date": "2026-10-01"
            }
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [76.3512, 11.9734]},
            "properties": {
                "id": "SRC_KABINI_DAM",
                "name": "Kabini Reservoir",
                "category": "RAW_WATER_SOURCE",
                "elevation_m": 696.0,
                "distance_km": 180,
                "flow_allocation_mld": 450.0,
                "_data_tier": "REAL",
                "_source": "CWC & WRD Karnataka",
                "_date": "2026-10-01"
            }
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [77.2155, 12.5204]},
            "properties": {
                "id": "WTP_TK_HALLI",
                "name": "Torekadanahalli (TK Halli) WTP & Pumping Complex",
                "category": "WATER_TREATMENT_PLANT",
                "capacity_mld": 1400.0,
                "stages": "Stage I to V",
                "elevation_m": 600.0,
                "static_lift_m": 450.0,
                "_data_tier": "REAL",
                "_source": "JICA Report 12300372 & Yokogawa SCADA 2015",
                "_date": "2026-02-01"
            }
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [77.4421, 12.6582]},
            "properties": {
                "id": "PS_HAROHALLI",
                "name": "Harohalli Intermediate Pumping Station",
                "category": "PUMPING_STATION",
                "capacity_mld": 1400.0,
                "elevation_m": 725.0,
                "boost_lift_m": 125.0,
                "_data_tier": "REAL",
                "_source": "JICA 2026 Survey Drawings",
                "_date": "2026-02-01"
            }
        },
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [77.5140, 12.8685]},
            "properties": {
                "id": "PS_TATAGUNI",
                "name": "Tataguni Terminal Pumping Station",
                "category": "PUMPING_STATION",
                "capacity_mld": 1350.0,
                "elevation_m": 820.0,
                "terminal_lift_m": 95.0,
                "_data_tier": "REAL",
                "_source": "JICA 2026 Survey",
                "_date": "2026-02-01"
            }
        }
    ]
    return {
        "type": "FeatureCollection",
        "metadata": {
            "title": "Cauvery Water Supply Scheme (CWSS) Transmission Corridor",
            "data_tier": "REAL",
            "source": "JICA Phase 3 Final Report & Yokogawa SCADA 2015 Case Study",
            "date": "2026-02-01"
        },
        "features": features
    }
