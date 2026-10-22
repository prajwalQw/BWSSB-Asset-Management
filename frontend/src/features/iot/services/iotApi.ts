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

const API_BASE = '/api/v1/iot';

export const iotApi = {
  async getStations(): Promise<StationOverview[]> {
    const res = await fetch(`${API_BASE}/stations`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async getDevices(): Promise<DeviceTelemetry[]> {
    const res = await fetch(`${API_BASE}/devices`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async getTimeseries(tag: string, signal: string, from?: number, to?: number): Promise<TimeseriesResponse> {
    const params = new URLSearchParams({ tag, signal });
    if (from) params.set('from', String(from));
    if (to) params.set('to', String(to));
    const res = await fetch(`${API_BASE}/timeseries?${params.toString()}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async getMldFlows(): Promise<{ corridors: WaterFlowCorridor[]; water_balance: WaterBalanceSummary }> {
    const res = await fetch(`${API_BASE}/mld-flows`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async getSmartMeters(): Promise<DivisionBoardSummary[]> {
    const res = await fetch(`${API_BASE}/smart-meters`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  },

  async getSnapshot() {
    // Consolidated snapshot endpoint
    const res = await fetch('/api/v1/snapshot');
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

