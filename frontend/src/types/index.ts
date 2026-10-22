export type DataTier = 'REAL' | 'SIMULATED' | 'LIVE';

export interface ProvenanceMetadata {
  tier: DataTier;
  source: string;
  date?: string;
  license?: string;
  notes?: string;
}

export interface MapLayerConfig {
  id: string;
  name: string;
  category: 'water' | 'sewer' | 'simulated' | 'water_bodies' | 'admin';
  visible: boolean;
  opacity: number;
  dataTier: DataTier;
  color: string;
  featureCount?: number;
}

export interface SelectedAsset {
  id: string;
  name: string;
  category: string;
  dataTier: DataTier;
  source?: string;
  date?: string;
  coordinates?: [number, number];
  properties: Record<string, any>;
}

export interface TelemetryPacket {
  speed: number;
  LEFT_MOTOR_ENCODER_VAL: number;
  RIGHT_MOTOR_ENCODER_VAL: number;
  motor_temp_c: number;
  motor_current_a: number;
  voltage_v?: number;
  alarmLM: number;
  alarmRM: number;
  status: string;
  data_tier: 'LIVE';
  last_packet_time: number;
}

export interface AlertItem {
  alert_id: string;
  rule_id: string;
  category: string;
  severity: 'CRITICAL' | 'HIGH' | 'WARNING' | 'INFO';
  title: string;
  location: string;
  coordinates?: [number, number];
  metric_observed: string;
  recommendation: string;
  requires_human_approval: boolean;
  human_decision_status: string;
  operator_decision?: {
    decision: string;
    operator_name: string;
    notes: string;
    decided_at: string;
  };
  timestamp: string;
  data_tier: DataTier;
}

export interface PumpTelemetry {
  timestamp: number;
  voltage_r: number;
  voltage_y: number;
  voltage_b: number;
  voltage_avg: number;
  current_r: number;
  current_y: number;
  current_b: number;
  current_avg: number;
  active_power_kw: number;
  power_factor: number;
  voltage_imbalance_pct: number;
  flow_lps: number;
  discharge_pressure_bar: number;
  specific_energy_kwh_per_m3: number;
  kwh_24h: number;
  daily_cost_inr: number;
  run_state: 'STOPPED' | 'STARTING' | 'STEADY_RUNNING' | 'TRIPPED' | 'STANDBY';
  is_healthy_steady: boolean;
}

export interface PumpSteadyBand {
  current_a?: {
    median: number;
    mad: number;
    sigma_robust: number;
    band_low: number;
    band_high: number;
  };
  power_kw?: {
    median: number;
    mad: number;
    sigma_robust: number;
    band_low: number;
    band_high: number;
  };
  specific_energy_kwh_per_m3?: {
    median: number;
    band_low?: number;
    band_high: number;
  };
  samples_count?: number;
  last_updated?: string;
}

export interface PumpStatus {
  pump_id: string;
  name: string;
  station_id: string;
  station_name: string;
  zone: string;
  coordinates: [number, number];
  status: string;
  rated_specs: {
    voltage_v: number;
    current_a: number;
    power_kw: number;
    number_of_phases: number;
    power_factor: number;
    startup_window_seconds: number;
  };
  latest_telemetry: PumpTelemetry;
  steady_band: PumpSteadyBand;
  active_anomalies: Array<{
    anomaly_type: string;
    variable: string;
    phase: string;
    current_value: any;
    normal_threshold: string;
    deviation_pct: number;
    unit: string;
  }>;
  active_injection?: {
    type: string;
    severity: number;
    injected_at_iso: string;
  };
  data_tier: DataTier;
  simulated: boolean;
}

export interface PumpAlert {
  alert_id: string;
  pump_id: string;
  pump_name: string;
  station_name: string;
  zone: string;
  coordinates: [number, number];
  anomaly_type: string;
  anomaly_name: string;
  severity: 'CRITICAL' | 'WARNING' | 'ADVISORY' | 'INFO';
  variable: string;
  phase: string;
  current_value: any;
  normal_threshold: string;
  how_far_from_normal: string;
  unit: string;
  since_when: string;
  duration_minutes: number;
  likely_causes: string[];
  future_consequences: string[];
  suggested_actions: string[];
  advisory: boolean;
  disclaimer: string;
  data_tier: DataTier;
  simulated: boolean;
}

export interface PumpStartEvent {
  event_id: string;
  pump_id: string;
  pump_name: string;
  timestamp: string;
  timestamp_epoch: number;
  inrush_peak_current_a: number;
  inrush_ratio: number;
  ramp_down_duration_sec: number;
  decay_profile: Array<{
    time_sec: number;
    current_a: number;
  }>;
  status: string;
  provenance: DataTier;
  simulated: boolean;
}

export interface PumpTrendPoint {
  step: number;
  time_label: string;
  voltage_r: number;
  voltage_y: number;
  voltage_b: number;
  voltage_avg: number;
  voltage_upper_limit: number;
  voltage_lower_limit: number;
  current_r: number;
  current_y: number;
  current_b: number;
  current_avg: number;
  current_band_high: number;
  current_band_low: number;
  current_median: number;
  active_power_kw: number;
  power_band_high: number;
  power_band_low: number;
  power_factor: number;
  flow_lps: number;
  discharge_pressure_bar: number;
  specific_energy_kwh_per_m3: number;
}

export interface PumpDriftForecast {
  pump_id: string;
  pump_name: string;
  current_power_kw: number;
  alarm_limit_kw: number;
  drift_slope_kw_per_hour: number;
  drift_status: string;
  time_to_alarm: {
    nominal_hours: number | null;
    range_min_hours: number | null;
    range_max_hours: number | null;
    confidence_level: string;
    formatted_advisory: string;
  };
  forecast_timeseries: Array<{
    hour_ahead: number;
    time_iso: string;
    predicted_kw: number;
    lower_bound_95: number;
    upper_bound_95: number;
    alarm_limit_kw: number;
  }>;
  backtest: {
    test_scenario: string;
    benchmark_steps_evaluated: number;
    proposed_drift_model: {
      name: string;
      first_warning_step: number;
      early_warning_lead_time_hours: number;
      false_alarms_in_stable_baseline: number;
      detection_delay_minutes: number;
      recommendation_window: string;
    };
    simple_threshold_baseline: {
      name: string;
      alarm_step: number;
      early_warning_lead_time_hours: number;
      false_alarms_in_stable_baseline: number;
      detection_delay_minutes: number;
      recommendation_window: string;
    };
    performance_gain: string;
  };
}

export interface PumpEnergyReport {
  station_id: string;
  station_name: string;
  reporting_period: string;
  tariff_inr_per_kwh: number;
  total_kwh_24h: number;
  total_cost_inr_24h: number;
  total_volume_m3_24h: number;
  total_volume_mld_24h: number;
  station_specific_energy_kwh_per_m3: number;
  pumps: Array<{
    pump_id: string;
    name: string;
    status: string;
    avg_power_kw: number;
    avg_flow_lps: number;
    kwh_24h: number;
    volume_m3_24h: number;
    volume_mld_24h: number;
    cost_inr_24h: number;
    specific_energy_kwh_per_m3: number;
    efficiency_rating: string;
  }>;
}

