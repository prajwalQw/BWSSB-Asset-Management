/**
 * TypeScript Interfaces and Types for IoT Digital Twin Module.
 */

export type DataTier = 'SIMULATED';
export type Quality = 'Good' | 'Uncertain' | 'Bad';
export type CommsState = 'ONLINE' | 'STALE' | 'OFFLINE';
export type PumpRunState = 'OFF' | 'STARTING' | 'RUNNING' | 'STOPPING' | 'TRIPPED';
export type AlertSeverity = 'CRITICAL' | 'HIGH' | 'WARNING' | 'INFO';

export interface DeviceTelemetry {
  tag: string;
  type_code: string;
  name: string;
  asset_link: string;
  location: {
    station_id?: string;
    offset_m?: [number, number];
    coordinates?: [number, number];
  };
  active: boolean;
  comms_state: CommsState;
  last_seen: number;
  quality: Quality;
  data_tier: DataTier;
  latest_values: Record<string, any>;
}

export interface PumpTelemetry {
  pump_id: string;
  tag: string;
  display_name?: string;
  role?: string;
  station_id: string;
  run_state: PumpRunState;
  auto_control_mode: string;
  run_hours: number;
  starts_count: number;
  flow_lps: number;
  head_m: number;
  current_r: number;
  current_y: number;
  current_b: number;
  current_avg: number;
  voltage_r: number;
  voltage_y: number;
  voltage_b: number;
  voltage_avg: number;
  active_power_kw: number;
  power_factor: number;
  vibration_rms_mms: number;
  inrush_peak_a: number;
  energy_kwh: number;
  data_tier: DataTier;
  updated_at: number;
}

export interface TankTelemetry {
  tank_id: string;
  station_id: string;
  name: string;
  level_m: number;
  level_pct: number;
  height_m: number;
  volume_m3: number;
  capacity_m3: number;
  inflow_lps: number;
  outflow_lps: number;
  data_tier: DataTier;
}

export interface StationOverview {
  id: string;
  name: string;
  zone: string;
  station_class: string;
  coordinates: [number, number];
  site_rotation_deg: number;
  tank: TankTelemetry;
  pumps: PumpTelemetry[];
  devices: DeviceTelemetry[];
  data_tier: DataTier;
  total_power_kw?: number;
  discharge_flow_mld?: number;
  active_alerts_count?: number;
}

export interface IoTAlertItem {
  alert_id: string;
  rule_id: string;
  category: string;
  severity: AlertSeverity;
  title: string;
  location: string;
  asset_id?: string;
  coordinates?: [number, number];
  metric_observed: string;
  recommendation: string;
  requires_human_approval: boolean;
  human_decision_status: string;
  timestamp: string;
  timestamp_epoch: number;
  data_tier: DataTier;
  source: 'IOT';
  estimated_loss_lps?: number;
  estimated_loss_kld?: number;
  confidence_pct?: number;
  uncertainty_corridor?: string;
  nearest_landmark?: string;
  affected_elements?: string[];
  suggested_steps?: string[];
  active: boolean;
  status?: 'ACTIVE' | 'ACKNOWLEDGED' | 'CLEARED' | 'SHELVED';
  first_seen?: number;
  last_seen?: number;
  cleared_at?: number | null;
  acknowledged_by?: string | null;
  acknowledged_at?: number | null;
  acknowledged?: boolean;
  shelved?: boolean;
}

export interface WardMeterSummary {
  ward_no: number;
  ward_name: string;
  bbmp_zone: string;
  bwssb_division: string;
  meter_tag: string;
  flow_lps: number;
  daily_baseline_mld: number;
  current_day_volume_kl: number;
  cumulative_totaliser_kl: number;
  status: CommsState;
  battery_pct: number;
  signal_strength_dbm: number;
  flags: string[];
  provenance_note: string;
  data_tier: DataTier;
}

export interface DivisionBoardSummary {
  division_name: string;
  centroid_coordinates: [number, number];
  inlet_mld: number;
  sum_ward_consumption_mld: number;
  apparent_loss_mld: number;
  apparent_loss_pct: number;
  total_wards: number;
  wards_online: number;
  wards_offline: number;
  active_alerts_count: number;
  alerts_by_type: Record<string, number>;
  top_wards_by_usage: Array<{ ward_no: number; ward_name: string; mld: number }>;
  hourly_inlet_profile: number[];
  hourly_ward_sum_profile: number[];
  cumulative_today_kl: number;
  wards: WardMeterSummary[];
  data_tier: DataTier;
}

export interface WaterFlowCorridor {
  id: string;
  name: string;
  from_node: string;
  to_node: string;
  flow_mld: number;
  design_flow_mld: number;
  pipe_dn_mm: number;
  coordinates: [number, number][] | number[][];
  status: string;
  data_tier: DataTier;
}

export interface WaterBalanceSummary {
  total_inflow_mld: number;
  total_outflow_mld: number;
  storage_change_mld: number;
  unaccounted_mld: number;
  unaccounted_pct: number;
  balanced: boolean;
  data_tier: DataTier;
}

export interface TimeseriesPoint {
  timestamp: number;
  value: number;
  quality: Quality;
}

export interface TimeseriesResponse {
  tag: string;
  signal: string;
  data_tier: DataTier;
  points_count: number;
  data: TimeseriesPoint[];
}

export interface AuditLogEntry {
  action: string;
  timestamp: string;
  details?: any;
  pump_id?: string;
  fault_type?: string;
  device_tag?: string;
}
