/**
 * Demo API Client for Leak Response Demo Flow
 */

export interface WardNotice {
  type: 'DISRUPTED' | 'RESTORED';
  ward: string;
  landmark: string;
  start_time: string;
  end_time: string;
  message: string;
  timestamp: string;
}

export interface DemoStatus {
  state: string;
  state_entered_at: number;
  demo_started_at: number | null;
  elapsed_s: number;
  alert_id: string | null;
  incident_id: string | null;
  step_log: Array<{ label: string; ts: string; elapsed_s: number }>;
  agent_response: {
    incident_id?: string;
    steps?: Array<{ label: string; ts: string; done: boolean }>;
    approval_mode?: string;
    countdown?: number | null;
  };
  valve_state: string;
  repair_pct: number;
  repair_eta_s: number;
  incident_report: any;
  approval_mode: string;
  selected_ward?: string;
  available_wards?: string[];
  ward_notice?: WardNotice | null;
  config: {
    pipe_segment_id: string;
    feeding_pump_id: string;
    feeding_pump_name: string;
    isolation_valve_name: string;
    from_station: string;
    to_station: string;
    leak_rate_lps: number;
    leak_coordinates: [number, number];
    landmark?: string;
    impacted_wards: string[];
    outage_hours?: number;
    alternate_source: string;
    alternate_coverage_pct: number;
    alternate_coverage_hours: number;
  };
  data_tier: string;
  disclaimer: string;
}

export const demoApi = {
  async startDemo(ward?: string): Promise<{ started: boolean; state: string; ward?: string }> {
    const res = await fetch('/api/v1/demo/start', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ward: ward || 'Basavanagudi' })
    });
    if (!res.ok) throw new Error(`Demo start failed: ${res.statusText}`);
    return res.json();
  },

  async resetDemo(): Promise<{ state: string }> {
    const res = await fetch('/api/v1/demo/reset', { method: 'POST' });
    if (!res.ok) throw new Error(`Demo reset failed: ${res.statusText}`);
    return res.json();
  },

  async markRepairDone(): Promise<{ marked_done: boolean; state: string; ward_notice?: WardNotice }> {
    const res = await fetch('/api/v1/demo/repair-done', { method: 'POST' });
    if (!res.ok) throw new Error(`Repair completion failed: ${res.statusText}`);
    return res.json();
  },

  async getStatus(): Promise<DemoStatus> {
    const res = await fetch('/api/v1/demo/status');
    if (!res.ok) throw new Error(`Demo get status failed: ${res.statusText}`);
    return res.json();
  },

  async approveIsolation(operator = 'OPERATOR', role = 'OPERATOR'): Promise<{ approved: boolean }> {
    const res = await fetch(`/api/v1/demo/approve?operator=${encodeURIComponent(operator)}&role=${encodeURIComponent(role)}`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Approval failed');
    }
    return res.json();
  },

  async rejectIsolation(operator = 'OPERATOR', role = 'OPERATOR'): Promise<{ rejected: boolean }> {
    const res = await fetch(`/api/v1/demo/reject?operator=${encodeURIComponent(operator)}&role=${encodeURIComponent(role)}`, {
      method: 'POST'
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      throw new Error(err.detail || 'Rejection failed');
    }
    return res.json();
  },

  getReportHtmlUrl(): string {
    return '/api/v1/demo/report/html';
  }
};
