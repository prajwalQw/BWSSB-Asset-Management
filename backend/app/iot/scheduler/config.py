"""
Automatic Supply Plan Configuration & Topology.
Anchored to Tataguni Pumping Complex, Transmission Corridors, GLRs, and Division/Ward Baselines.
"""

from typing import List, Dict, Any
from dataclasses import dataclass, field

@dataclass
class TariffBand:
    name: str
    start_hour: int
    end_hour: int
    rate_inr_per_kwh: float

DEFAULT_TARIFFS = [
    TariffBand("Off-Peak", 22, 6, 4.50),   # 22:00 to 06:00
    TariffBand("Normal", 6, 18, 7.20),     # 06:00 to 18:00
    TariffBand("Peak", 18, 22, 10.50),     # 18:00 to 22:00
]

@dataclass
class PumpConfig:
    id: str
    tag: str
    name: str
    station_id: str
    rated_power_kw: float
    rated_flow_mld: float
    min_run_minutes: int = 15
    min_off_minutes: int = 15

DEFAULT_PUMPS = [
    PumpConfig("PUMP_TG_H1", "TG-HLP-01", "Tataguni High-Lift Pump 1", "PS_TATAGUNI", 1200.0, 76.8),
    PumpConfig("PUMP_TG_H2", "TG-HLP-02", "Tataguni High-Lift Pump 2", "PS_TATAGUNI", 1200.0, 76.8),
    PumpConfig("PUMP_TG_H3", "TG-HLP-03", "Tataguni High-Lift Pump 3", "PS_TATAGUNI", 1200.0, 76.8),
]

@dataclass
class ReservoirConfig:
    id: str
    name: str
    capacity_mld: float
    min_level_pct: float
    max_level_pct: float
    initial_level_pct: float
    coordinates: List[float]

DEFAULT_GLRS = [
    ReservoirConfig("GLR_MOUNT_JOY", "Mount Joy GLR", 22.0, 20.0, 90.0, 55.0, [77.5621, 12.9372]),
    ReservoirConfig("GLR_HIGH_GROUNDS", "High Grounds GLR", 35.0, 20.0, 90.0, 62.0, [77.5843, 12.9912]),
]

@dataclass
class SupplyZone:
    id: str
    name: str
    division: str
    daily_demand_mld: float
    assigned_glr_id: str
    coordinates: List[float]
    is_simulated_assignment: bool = True

DEFAULT_SUPPLY_ZONES = [
    SupplyZone("ZONE_SOUTH_BASAVANAGUDI", "South Basavanagudi & Chamarajpet", "South Division", 28.5, "GLR_MOUNT_JOY", [77.5700, 12.9420]),
    SupplyZone("ZONE_CENTRAL_CBD", "Central CBD Vidhana Soudha", "Central", 32.0, "GLR_HIGH_GROUNDS", [77.5910, 12.9780]),
    SupplyZone("ZONE_WEST_RAJAJINAGAR", "West Rajajinagar - Malleshwaram", "West Division", 26.8, "GLR_HIGH_GROUNDS", [77.5550, 12.9980]),
    SupplyZone("ZONE_SOUTH_PADMANABHANAGAR", "Padmanabhanagar & Banashankari", "South Division", 24.2, "GLR_MOUNT_JOY", [77.5580, 12.9150]),
]

@dataclass
class PipeConduit:
    id: str
    name: str
    from_node: str
    to_node: str
    length_km: float
    pipe_dn_mm: int
    coordinates: List[List[float]]

DEFAULT_PIPES = [
    PipeConduit(
        "CORR_TATAGUNI_MOUNT_JOY",
        "Tataguni to Mount Joy GLR Feeder",
        "PS_TATAGUNI",
        "GLR_MOUNT_JOY",
        12.8,
        1200,
        [[77.5148, 12.8690], [77.5380, 12.9050], [77.5621, 12.9372]]
    ),
    PipeConduit(
        "CORR_TATAGUNI_HIGH_GROUNDS",
        "Tataguni to High Grounds GLR Trunk",
        "PS_TATAGUNI",
        "GLR_HIGH_GROUNDS",
        18.2,
        1400,
        [[77.5148, 12.8690], [77.5510, 12.9350], [77.5843, 12.9912]]
    ),
    PipeConduit(
        "CORR_MOUNT_JOY_BASAVANAGUDI",
        "Mount Joy Booster to Basavanagudi Zone",
        "GLR_MOUNT_JOY",
        "ZONE_SOUTH_BASAVANAGUDI",
        2.1,
        600,
        [[77.5621, 12.9372], [77.5700, 12.9420]]
    ),
    PipeConduit(
        "CORR_MOUNT_JOY_PADMANABHANAGAR",
        "Mount Joy Booster to Padmanabhanagar Zone",
        "GLR_MOUNT_JOY",
        "ZONE_SOUTH_PADMANABHANAGAR",
        2.8,
        600,
        [[77.5621, 12.9372], [77.5580, 12.9150]]
    ),
    PipeConduit(
        "CORR_HIGH_GROUNDS_CBD",
        "High Grounds Booster to Central CBD Zone",
        "GLR_HIGH_GROUNDS",
        "ZONE_CENTRAL_CBD",
        2.6,
        800,
        [[77.5843, 12.9912], [77.5910, 12.9780]]
    ),
    PipeConduit(
        "CORR_HIGH_GROUNDS_WEST",
        "High Grounds Booster to West Rajajinagar Zone",
        "GLR_HIGH_GROUNDS",
        "ZONE_WEST_RAJAJINAGAR",
        3.4,
        700,
        [[77.5843, 12.9912], [77.5550, 12.9980]]
    ),
]
