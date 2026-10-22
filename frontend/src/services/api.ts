import { AlertItem } from '../types';

const API_BASE = '/api/v1';

async function safeJson<T = any>(res: Response, fallback: T): Promise<T> {
  if (!res || !res.ok) {
    return fallback;
  }
  try {
    return await res.json();
  } catch {
    return fallback;
  }
}

export const api = {
  // Real Assets
  getPumpingStations: async () => {
    try {
      const res = await fetch(`${API_BASE}/assets/pumping-stations`);
      return safeJson(res, { features: [] });
    } catch {
      return { features: [] };
    }
  },

  getSTPs: async () => {
    try {
      const res = await fetch(`${API_BASE}/assets/stps`);
      return safeJson(res, { features: [] });
    } catch {
      return { features: [] };
    }
  },

  getWaterLinesMains: async () => {
    try {
      const res = await fetch(`${API_BASE}/assets/water-lines-mains?limit=2500`);
      return safeJson(res, { features: [] });
    } catch {
      return { features: [] };
    }
  },

  getValves: async () => {
    try {
      const res = await fetch(`${API_BASE}/assets/valves?limit=1000`);
      return safeJson(res, { features: [] });
    } catch {
      return { features: [] };
    }
  },

  getBorewells: async () => {
    try {
      const res = await fetch(`${API_BASE}/assets/borewells?limit=1500`);
      return safeJson(res, { features: [] });
    } catch {
      return { features: [] };
    }
  },

  getDivisionBoundaries: async () => {
    try {
      const res = await fetch(`${API_BASE}/assets/divisions`);
      return safeJson(res, { features: [] });
    } catch {
      return { features: [] };
    }
  },

  getCauveryCorridor: async () => {
    try {
      const res = await fetch(`${API_BASE}/assets/cauvery-corridor`);
      return safeJson(res, { features: [] });
    } catch {
      return { features: [] };
    }
  },

  // Water Bodies
  getWaterBodies: async () => {
    try {
      const res = await fetch(`${API_BASE}/water-bodies`);
      return safeJson(res, { features: [] });
    } catch {
      return { features: [] };
    }
  },

  // Simulated Hydraulics
  getSimulatedZone: async () => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/zone`);
      return safeJson(res, { features: [] });
    } catch {
      return { features: [] };
    }
  },

  triggerSimulation: async (scenario: string, targetPipe?: string) => {
    try {
      const url = targetPipe
        ? `${API_BASE}/hydraulics/simulate?scenario=${scenario}&target_pipe=${targetPipe}`
        : `${API_BASE}/hydraulics/simulate?scenario=${scenario}`;
      const res = await fetch(url, { method: 'POST' });
      return safeJson(res, { status: 'ERROR' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  injectLeak: async (pipeId: string, leakFlowLps: number) => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/scenarios/inject-leak`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pipe_id: pipeId, leak_flow_lps: leakFlowLps }),
      });
      return safeJson(res, { status: 'ERROR' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  closeValve: async (pipeOrValveId: string, action: string = 'CLOSED') => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/scenarios/close-valve`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pipe_or_valve_id: pipeOrValveId, action }),
      });
      return safeJson(res, { status: 'ERROR' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  tripPump: async (pumpId: string) => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/scenarios/trip-pump`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pump_id: pumpId }),
      });
      return safeJson(res, { status: 'ERROR' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  modulateDemand: async (multiplier: number) => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/scenarios/modulate-demand`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ demand_multiplier: multiplier }),
      });
      return safeJson(res, { status: 'ERROR' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  perturbSensor: async (sensorId: string, type: string, value: number) => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/scenarios/sensor-perturbation`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sensor_id: sensorId, perturbation_type: type, value }),
      });
      return safeJson(res, { status: 'ERROR' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  simulatePipeBurst: async (pipeId: string) => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/scenarios/pipe-burst`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pipe_id: pipeId }),
      });
      return safeJson(res, { status: 'ERROR' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  simulateContamination: async (nodeId: string, concentration: number) => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/scenarios/contamination`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ node_id: nodeId, concentration_mg_l: concentration }),
      });
      return safeJson(res, { status: 'ERROR' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  simulateDroughtStress: async (reductionPct: number) => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/scenarios/drought-stress`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ reduction_percentage: reductionPct }),
      });
      return safeJson(res, { status: 'ERROR' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  simulatePowerOutage: async (subdivision: string) => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/scenarios/power-outage`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ subdivision }),
      });
      return safeJson(res, { status: 'ERROR' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  resetSimulation: async () => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/reset`, { method: 'POST' });
      return safeJson(res, { status: 'OK' });
    } catch {
      return { status: 'OK' };
    }
  },

  resetScenarios: async () => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/scenarios/reset`, { method: 'POST' });
      return safeJson(res, { status: 'OK' });
    } catch {
      return { status: 'OK' };
    }
  },

  getPumpMetrics: async () => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/pumps`);
      return safeJson(res, { pumps: [], data_tier: 'SIMULATED' });
    } catch {
      return { pumps: [], data_tier: 'SIMULATED' };
    }
  },

  getFlowMeters: async () => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/meters`);
      return safeJson(res, { flow_meters: [], data_tier: 'SIMULATED' });
    } catch {
      return { flow_meters: [], data_tier: 'SIMULATED' };
    }
  },

  getMassBalance: async () => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/mass-balance`);
      return safeJson(res, {});
    } catch {
      return {};
    }
  },

  getScenarioAuditLog: async () => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/audit-log`);
      return safeJson(res, { audit_log: [] });
    } catch {
      return { audit_log: [] };
    }
  },

  getLeakDetectionStatus: async () => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/leak-detection`);
      return safeJson(res, { segments: [], leak_events: [], sensor_faults: [] });
    } catch {
      return { segments: [], leak_events: [], sensor_faults: [] };
    }
  },

  runLeakValidation: async () => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/leak-detection/run-validation`, { method: 'POST' });
      return safeJson(res, { total_scenarios_tested: 0, results: [] });
    } catch {
      return { total_scenarios_tested: 0, results: [] };
    }
  },

  toggleSensorSource: async (sensorId: string, source: string) => {
    try {
      const res = await fetch(`${API_BASE}/hydraulics/sensors/${sensorId}/source`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ source }),
      });
      return safeJson(res, { sensor_id: sensorId, active_source: source, status: 'UPDATED' });
    } catch {
      return { sensor_id: sensorId, active_source: source, status: 'ERROR' };
    }
  },

  // Alerts & Governance
  getAlerts: async (): Promise<{ alerts: AlertItem[]; governance: string }> => {
    try {
      const res = await fetch(`${API_BASE}/alerts`);
      return safeJson(res, { alerts: [], governance: 'HUMAN_IN_THE_LOOP' });
    } catch {
      return { alerts: [], governance: 'HUMAN_IN_THE_LOOP' };
    }
  },

  submitOperatorDecision: async (
    alertId: string,
    decision: string,
    operatorName: string,
    notes: string
  ): Promise<{ status: string; message: string; alert?: any }> => {
    try {
      const res = await fetch(`${API_BASE}/alerts/${alertId}/decision`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          decision,
          operator_name: operatorName,
          operator_notes: notes,
        }),
      });
      return safeJson(res, {
        status: 'DECISION_RECORDED',
        message: `Action '${decision}' submitted by ${operatorName}.`,
      });
    } catch {
      return { status: 'ERROR', message: 'Failed submitting operator decision.' };
    }
  },

  // Admin Config
  getNetworkRules: async () => {
    try {
      const res = await fetch(`${API_BASE}/admin/rules`);
      return safeJson(res, {});
    } catch {
      return {};
    }
  },

  saveNetworkRules: async (payload: any) => {
    try {
      const res = await fetch(`${API_BASE}/admin/rules`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      return safeJson(res, { status: 'SAVED' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  // Pump Analytics & Health Engine
  getPumpsOverview: async () => {
    try {
      const res = await fetch(`${API_BASE}/pumps/overview`);
      return safeJson(res, null);
    } catch {
      return null;
    }
  },

  getPumpMonitors: async () => {
    try {
      const res = await fetch(`${API_BASE}/pumps/monitors`);
      return safeJson(res, []);
    } catch {
      return [];
    }
  },

  getPumpTrends: async (pumpId: string) => {
    try {
      const res = await fetch(`${API_BASE}/pumps/${pumpId}/trends`);
      return safeJson(res, []);
    } catch {
      return [];
    }
  },

  getPumpStartEvents: async (pumpId: string): Promise<{ events: any[]; total_recorded_starts: number }> => {
    try {
      const res = await fetch(`${API_BASE}/pumps/${pumpId}/start-events`);
      return safeJson(res, { events: [], total_recorded_starts: 0 });
    } catch {
      return { events: [], total_recorded_starts: 0 };
    }
  },

  getPumpEnergyReport: async () => {
    try {
      const res = await fetch(`${API_BASE}/pumps/energy-report`);
      return safeJson(res, null);
    } catch {
      return null;
    }
  },

  getPumpAnomalies: async (): Promise<{ active_alerts: any[]; disclaimer?: string }> => {
    try {
      const res = await fetch(`${API_BASE}/pumps/anomalies`);
      return safeJson(res, { active_alerts: [] });
    } catch {
      return { active_alerts: [] };
    }
  },

  getPumpForecast: async (pumpId: string, horizonHours: number = 72) => {
    try {
      const res = await fetch(`${API_BASE}/pumps/${pumpId}/forecast?horizon_hours=${horizonHours}`);
      return safeJson(res, null);
    } catch {
      return null;
    }
  },

  injectPumpScenario: async (pumpId: string, anomalyType: string, severity: number = 1.0) => {
    try {
      const res = await fetch(`${API_BASE}/pumps/inject-scenario`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          pump_id: pumpId,
          anomaly_type: anomalyType,
          severity,
        }),
      });
      return safeJson(res, { status: 'ERROR' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  clearPumpScenario: async (pumpId: string) => {
    try {
      const res = await fetch(`${API_BASE}/pumps/clear-scenario`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pump_id: pumpId }),
      });
      return safeJson(res, { status: 'ERROR' });
    } catch {
      return { status: 'ERROR' };
    }
  },

  getPumpKnowledgeBase: async () => {
    try {
      const res = await fetch(`${API_BASE}/pumps/knowledge-base`);
      return safeJson(res, []);
    } catch {
      return [];
    }
  },

  getFeedHealth: async () => {
    try {
      const res = await fetch(`${API_BASE}/telemetry/feed-health`);
      return safeJson(res, {});
    } catch {
      return {};
    }
  },
};
