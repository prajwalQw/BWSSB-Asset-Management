/**
 * API Service for IoT Endpoints.
 * Interacts with /api/v1/iot/*
 */

import {
  StationOverview,
  DeviceTelemetry,
  IoTAlertItem,
  DivisionBoardSummary,
  WaterFlowCorridor,
  WaterBalanceSummary,
  TimeseriesResponse
} from '../types';

const API_BASE =
  typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://127.0.0.1:8000/api/v1/iot'
    : '/api/v1/iot';

export const iotApi = {
  async getStations(): Promise<StationOverview[]> {
    try {
      const res = await fetch(`${API_BASE}/stations`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      return getFallbackStations();
    }
  },

  async getDevices(): Promise<DeviceTelemetry[]> {
    try {
      const res = await fetch(`${API_BASE}/devices`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      return [];
    }
  },

  async getTimeseries(tag: string, signal: string, from?: number, to?: number): Promise<TimeseriesResponse> {
    try {
      const params = new URLSearchParams({ tag, signal });
      if (from) params.set('from', String(from));
      if (to) params.set('to', String(to));
      const res = await fetch(`${API_BASE}/timeseries?${params.toString()}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      return {
        tag,
        signal,
        data_tier: 'SIMULATED',
        points_count: 0,
        data: []
      };
    }
  },

  async getMldFlows(): Promise<{ corridors: WaterFlowCorridor[]; water_balance: WaterBalanceSummary }> {
    try {
      const res = await fetch(`${API_BASE}/mld-flows`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      return getFallbackFlows();
    }
  },

  async getSmartMeters(): Promise<DivisionBoardSummary[]> {
    try {
      const res = await fetch(`${API_BASE}/smart-meters`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      return getFallbackSmartMeters();
    }
  },

  async getSnapshot() {
    const res = await fetch(`${API_BASE}/snapshot`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async getAlerts(status?: string): Promise<IoTAlertItem[]> {
    try {
      const url = status ? `${API_BASE}/alerts?status=${encodeURIComponent(status)}` : `${API_BASE}/alerts`;
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 2500);
      const res = await fetch(url, { signal: controller.signal });
      clearTimeout(timeoutId);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      return [];
    }
  },

  async acknowledgeAlert(alertId: string, operator: string = 'OPERATOR'): Promise<IoTAlertItem> {
    const res = await fetch(`${API_BASE}/alerts/${encodeURIComponent(alertId)}/acknowledge?operator=${encodeURIComponent(operator)}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async snoozeAlert(alertId: string, durationS: number = 3600): Promise<IoTAlertItem> {
    const res = await fetch(`${API_BASE}/alerts/${encodeURIComponent(alertId)}/snooze?duration_s=${durationS}`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async clearAlert(alertId: string): Promise<IoTAlertItem> {
    const res = await fetch(`${API_BASE}/alerts/${encodeURIComponent(alertId)}/clear`, {
      method: 'POST'
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async injectLeak(pipe_segment_id: string, leak_rate_lps: number, landmark?: string) {
    const res = await fetch(`${API_BASE}/simulate/leak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pipe_segment_id, leak_rate_lps, nearest_landmark: landmark })
    });
    return await res.json();
  },

  async stopLeak(pipe_segment_id?: string) {
    const res = await fetch(`${API_BASE}/simulate/stop-leak`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pipe_segment_id })
    });
    return await res.json();
  },

  async injectPumpFault(pump_id: string, fault_type: string) {
    const res = await fetch(`${API_BASE}/simulate/pump-fault`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pump_id, fault_type })
    });
    return await res.json();
  },

  async injectSensorFault(device_tag: string, fault_type: string) {
    const res = await fetch(`${API_BASE}/simulate/sensor-fault`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ device_tag, fault_type })
    });
    return await res.json();
  },

  async resetSimulation() {
    const res = await fetch(`${API_BASE}/simulate/reset`, { method: 'POST' });
    return await res.json();
  },

  async getAdminConfig() {
    try {
      const res = await fetch(`${API_BASE}/admin/config`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      return await res.json();
    } catch {
      return { stations: {}, rules: {}, simulation: {}, audit_log: [], data_tier: 'SIMULATED' };
    }
  }
};

// Fallbacks for zero-crash frontend resilience
function getFallbackStations(): StationOverview[] {
  return [
    {
      id: 'PS_TATAGUNI',
      name: 'Tataguni Terminal Pumping Station',
      zone: 'South',
      station_class: 'high-lift',
      coordinates: [77.5148, 12.8690],
      site_rotation_deg: 35.0,
      tank: {
        tank_id: 'TANK_TG_01',
        station_id: 'PS_TATAGUNI',
        name: 'Tataguni Balancing Reservoir',
        level_m: 6.2,
        level_pct: 62.0,
        height_m: 10.0,
        volume_m3: 27900.0,
        capacity_m3: 45000.0,
        inflow_lps: 888.0,
        outflow_lps: 840.0,
        data_tier: 'SIMULATED'
      },
      pumps: [
        {
          pump_id: 'PUMP_TG_H1',
          tag: 'TG-HLP-01',
          display_name: 'High-Lift Pump 1',
          role: 'High-Lift Pump',
          station_id: 'PS_TATAGUNI',
          run_state: 'RUNNING',
          auto_control_mode: 'Automatic',
          run_hours: 4210.5,
          starts_count: 320,
          flow_lps: 885.2,
          head_m: 95.2,
          current_r: 108.5,
          current_y: 107.9,
          current_b: 108.2,
          current_avg: 108.2,
          voltage_r: 6580.0,
          voltage_y: 6605.0,
          voltage_b: 6590.0,
          voltage_avg: 6591.7,
          active_power_kw: 1085.4,
          power_factor: 0.88,
          vibration_rms_mms: 2.1,
          inrush_peak_a: 249.0,
          energy_kwh: 145200.0,
          data_tier: 'SIMULATED',
          updated_at: Date.now() / 1000
        },
        {
          pump_id: 'PUMP_TG_H2',
          tag: 'TG-HLP-02',
          display_name: 'High-Lift Pump 2',
          role: 'High-Lift Pump',
          station_id: 'PS_TATAGUNI',
          run_state: 'RUNNING',
          auto_control_mode: 'Automatic',
          run_hours: 3890.2,
          starts_count: 285,
          flow_lps: 881.0,
          head_m: 95.0,
          current_r: 107.8,
          current_y: 108.0,
          current_b: 107.5,
          current_avg: 107.8,
          voltage_r: 6585.0,
          voltage_y: 6600.0,
          voltage_b: 6592.0,
          voltage_avg: 6592.3,
          active_power_kw: 1080.1,
          power_factor: 0.88,
          vibration_rms_mms: 2.0,
          inrush_peak_a: 249.0,
          energy_kwh: 132100.0,
          data_tier: 'SIMULATED',
          updated_at: Date.now() / 1000
        },
        {
          pump_id: 'PUMP_TG_H3',
          tag: 'TG-HLP-03',
          display_name: 'High-Lift Pump 3',
          role: 'High-Lift Pump',
          station_id: 'PS_TATAGUNI',
          run_state: 'OFF',
          auto_control_mode: 'Automatic',
          run_hours: 2150.0,
          starts_count: 140,
          flow_lps: 0.0,
          head_m: 0.0,
          current_r: 0.0,
          current_y: 0.0,
          current_b: 0.0,
          current_avg: 0.0,
          voltage_r: 6600.0,
          voltage_y: 6600.0,
          voltage_b: 6600.0,
          voltage_avg: 6600.0,
          active_power_kw: 0.0,
          power_factor: 0.88,
          vibration_rms_mms: 0.1,
          inrush_peak_a: 0.0,
          energy_kwh: 78500.0,
          data_tier: 'SIMULATED',
          updated_at: Date.now() / 1000
        }
      ],
      devices: [
        {
          tag: 'FIT_TG_H1',
          type_code: 'FIT',
          name: 'Discharge Flow Meter',
          asset_link: 'PUMP_TG_H1',
          location: { station_id: 'PS_TATAGUNI', offset_m: [2.0, -8.0] },
          active: true,
          comms_state: 'ONLINE',
          last_seen: Date.now() / 1000,
          quality: 'Good',
          data_tier: 'SIMULATED',
          latest_values: { value: 885.2, unit: 'L/s' }
        },
        {
          tag: 'PIT_TG_H1',
          type_code: 'PIT',
          name: 'Discharge Pressure',
          asset_link: 'PUMP_TG_H1',
          location: { station_id: 'PS_TATAGUNI', offset_m: [8.0, -8.0] },
          active: true,
          comms_state: 'ONLINE',
          last_seen: Date.now() / 1000,
          quality: 'Good',
          data_tier: 'SIMULATED',
          latest_values: { value: 9.5, unit: 'bar' }
        }
      ],
      data_tier: 'SIMULATED'
    }
  ];
}

function getFallbackFlows() {
  return {
    corridors: [
      {
        id: 'CORR_CAUVERY_TKH',
        name: 'Cauvery Raw Water Conveyance',
        from_node: 'Cauvery River Intake',
        to_node: 'T.K. Halli WTP',
        flow_mld: 1475.0,
        design_flow_mld: 1475.0,
        pipe_dn_mm: 2000,
        coordinates: [[77.1652, 12.3021], [77.1850, 12.3780], [77.2031, 12.4512]],
        status: 'verified',
        data_tier: 'SIMULATED' as const
      },
      {
        id: 'CORR_TKH_HAROHALLI',
        name: 'T.K. Halli to Harohalli Transmission Conduit',
        from_node: 'T.K. Halli WTP',
        to_node: 'Harohalli Headworks',
        flow_mld: 1420.0,
        design_flow_mld: 1420.0,
        pipe_dn_mm: 1800,
        coordinates: [[77.2031, 12.4512], [77.3050, 12.5530], [77.4124, 12.6548]],
        status: 'verified',
        data_tier: 'SIMULATED' as const
      },
      {
        id: 'CORR_HAROHALLI_TATAGUNI',
        name: 'Harohalli to Tataguni High-Lift Corridor',
        from_node: 'Harohalli Headworks',
        to_node: 'Tataguni Terminal PS',
        flow_mld: 1390.0,
        design_flow_mld: 1390.0,
        pipe_dn_mm: 1800,
        coordinates: [[77.4124, 12.6548], [77.4650, 12.7610], [77.5148, 12.8690]],
        status: 'verified',
        data_tier: 'SIMULATED' as const
      },
      {
        id: 'CORR_TATAGUNI_MOUNT_JOY',
        name: 'Tataguni to Mount Joy GLR Feeder',
        from_node: 'Tataguni Terminal PS',
        to_node: 'Mount Joy GLR',
        flow_mld: 320.0,
        design_flow_mld: 320.0,
        pipe_dn_mm: 1200,
        coordinates: [[77.5148, 12.8690], [77.5380, 12.9050], [77.5621, 12.9372]],
        status: 'verified',
        data_tier: 'SIMULATED' as const
      }
    ],
    water_balance: {
      total_inflow_mld: 2250.0,
      total_outflow_mld: 1845.0,
      storage_change_mld: 12.0,
      unaccounted_mld: 393.0,
      unaccounted_pct: 17.5,
      balanced: true,
      data_tier: 'SIMULATED' as const
    }
  };
}

function getFallbackSmartMeters(): DivisionBoardSummary[] {
  return [
    {
      division_name: 'South Division',
      centroid_coordinates: [77.5750, 12.9250],
      inlet_mld: 154.2,
      sum_ward_consumption_mld: 125.7,
      apparent_loss_mld: 28.5,
      apparent_loss_pct: 18.5,
      total_wards: 36,
      wards_online: 36,
      wards_offline: 0,
      active_alerts_count: 0,
      alerts_by_type: { leak_suspected: 0, continuous_flow: 0, high_usage: 0 },
      top_wards_by_usage: [
        { ward_no: 154, ward_name: 'Basavanagudi', mld: 4.8 },
        { ward_no: 155, ward_name: 'Hanumanthanagar', mld: 4.5 },
        { ward_no: 156, ward_name: 'Giriragar', mld: 4.2 }
      ],
      hourly_inlet_profile: [5.2, 4.8, 4.5, 4.9, 7.5, 9.8, 11.2, 11.5, 10.2, 8.5, 7.8, 7.5, 7.2, 6.8, 6.5, 6.7, 7.8, 9.5, 10.8, 10.2, 8.8, 7.2, 6.1, 5.5],
      hourly_ward_sum_profile: [4.2, 3.8, 3.6, 3.9, 6.1, 8.0, 9.1, 9.4, 8.3, 6.9, 6.3, 6.1, 5.8, 5.5, 5.2, 5.4, 6.3, 7.8, 8.8, 8.3, 7.1, 5.8, 4.9, 4.4],
      cumulative_today_kl: 62850.0,
      wards: [],
      data_tier: 'SIMULATED'
    }
  ];
}
