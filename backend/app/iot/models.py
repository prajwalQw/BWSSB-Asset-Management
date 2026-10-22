"""
Domain and Telemetry Data Models for BWSSB IoT Subsystem.
Strict validation with Pydantic. All simulated values carry data_tier: "SIMULATED".
"""

from typing import Optional, List, Dict, Any, Literal
from pydantic import BaseModel, Field
import time

DataTier = Literal["SIMULATED"]
Quality = Literal["Good", "Uncertain", "Bad"]
CommsState = Literal["ONLINE", "STALE", "OFFLINE"]
PumpRunState = Literal["OFF", "STARTING", "RUNNING", "STOPPING", "TRIPPED"]
AlertSeverity = Literal["CRITICAL", "HIGH", "WARNING", "INFO"]

class MessageEnvelope(BaseModel):
    ts_utc: float = Field(default_factory=lambda: time.time())
    tag: str
    signal: str
    value: float
    unit: str
    quality: Quality = "Good"
    tier: DataTier = "SIMULATED"
    comms_state: CommsState = "ONLINE"

class DeviceStatus(BaseModel):
    tag: str
    type_code: str
    name: str
    asset_link: str
    location: Dict[str, Any]
    active: bool = True
    comms_state: CommsState = "ONLINE"
    last_seen: float
    quality: Quality = "Good"
    data_tier: DataTier = "SIMULATED"
    latest_values: Dict[str, Any] = Field(default_factory=dict)

class PumpTelemetryState(BaseModel):
    pump_id: str
    tag: str
    display_name: Optional[str] = None
    role: Optional[str] = None
    station_id: str
    run_state: PumpRunState
    auto_control_mode: str = "Automatic"
    run_hours: float
    starts_count: int
    flow_lps: float
    head_m: float
    current_r: float
    current_y: float
    current_b: float
    current_avg: float
    voltage_r: float
    voltage_y: float
    voltage_b: float
    voltage_avg: float
    active_power_kw: float
    power_factor: float
    vibration_rms_mms: float
    inrush_peak_a: float = 0.0
    energy_kwh: float
    data_tier: DataTier = "SIMULATED"
    updated_at: float

class TankState(BaseModel):
    tank_id: str
    station_id: str
    name: str
    level_m: float
    level_pct: float
    volume_m3: float
    capacity_m3: float
    inflow_lps: float
    outflow_lps: float
    data_tier: DataTier = "SIMULATED"

class StationOverview(BaseModel):
    id: str
    name: str
    zone: str
    station_class: str
    coordinates: List[float]
    site_rotation_deg: float
    tank: TankState
    pumps: List[PumpTelemetryState]
    devices: List[DeviceStatus]
    data_tier: DataTier = "SIMULATED"

AlertStatus = Literal["ACTIVE", "ACKNOWLEDGED", "CLEARED", "SHELVED"]

class IoTAlert(BaseModel):
    alert_id: str
    rule_id: str
    asset_id: Optional[str] = None
    category: str
    severity: AlertSeverity
    title: str
    location: str
    coordinates: Optional[List[float]] = None
    metric_observed: str
    recommendation: str
    requires_human_approval: bool = True
    human_decision_status: str = "PENDING_REVIEW"
    status: AlertStatus = "ACTIVE"
    first_seen: float = Field(default_factory=lambda: time.time())
    last_seen: float = Field(default_factory=lambda: time.time())
    cleared_at: Optional[float] = None
    acknowledged_by: Optional[str] = None
    acknowledged_at: Optional[float] = None
    timestamp: str = Field(default_factory=lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()))
    timestamp_epoch: float = Field(default_factory=lambda: time.time())
    data_tier: DataTier = "SIMULATED"
    source: str = "IOT"
    estimated_loss_lps: Optional[float] = None
    estimated_loss_kld: Optional[float] = None
    confidence_pct: Optional[float] = None
    uncertainty_corridor: Optional[str] = None
    nearest_landmark: Optional[str] = None
    affected_elements: Optional[List[str]] = None
    suggested_steps: Optional[List[str]] = None
    active: bool = True
    acknowledged: bool = False
    shelved: bool = False

class WardMeterSummary(BaseModel):
    ward_no: int
    ward_name: str
    bbmp_zone: str
    bwssb_division: str
    meter_tag: str
    flow_lps: float
    daily_baseline_mld: float
    current_day_volume_kl: float
    cumulative_totaliser_kl: float
    status: CommsState
    battery_pct: float
    signal_strength_dbm: float
    flags: List[str] = Field(default_factory=list)
    provenance_note: str = "Daily baseline: real data.gov.in; hourly readings: simulated"
    data_tier: DataTier = "SIMULATED"

class DivisionBoardSummary(BaseModel):
    division_name: str
    centroid_coordinates: List[float]
    inlet_mld: float
    sum_ward_consumption_mld: float
    apparent_loss_mld: float
    apparent_loss_pct: float
    total_wards: int
    wards_online: int
    wards_offline: int
    active_alerts_count: int
    alerts_by_type: Dict[str, int]
    top_wards_by_usage: List[Dict[str, Any]]
    hourly_inlet_profile: List[float]
    hourly_ward_sum_profile: List[float]
    cumulative_today_kl: float
    wards: List[WardMeterSummary]
    data_tier: DataTier = "SIMULATED"

class WaterFlowCorridor(BaseModel):
    id: str
    name: str
    from_node: str
    to_node: str
    flow_mld: float
    design_flow_mld: float
    pipe_dn_mm: int
    coordinates: List[List[float]]
    status: str
    data_tier: DataTier = "SIMULATED"

class WaterBalanceSummary(BaseModel):
    total_inflow_mld: float
    total_outflow_mld: float
    storage_change_mld: float
    unaccounted_mld: float
    unaccounted_pct: float
    balanced: bool
    data_tier: DataTier = "SIMULATED"

# Request Payloads
class LeakInjectionRequest(BaseModel):
    pipe_segment_id: str
    leak_rate_lps: float = 18.5
    duration_minutes: Optional[int] = 30
    nearest_landmark: Optional[str] = "Pipeline Road Chainage 4+200"

class PumpFaultInjectionRequest(BaseModel):
    pump_id: str
    fault_type: Literal["TRIP", "DRY_RUN", "OVERCURRENT", "VIBRATION_HIGH"] = "TRIP"

class SensorFaultInjectionRequest(BaseModel):
    device_tag: str
    fault_type: Literal["STUCK", "DRIFT", "OFFLINE", "SPIKE"] = "OFFLINE"
