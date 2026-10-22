/**
 * Global Zustand-compatible store for IoT Subsystem.
 * Built with React's useSyncExternalStore for zero-dependency reliability and route persistence.
 */

import { useSyncExternalStore } from 'react';
import {
  StationOverview,
  DivisionBoardSummary,
  WaterFlowCorridor,
  WaterBalanceSummary,
  IoTAlertItem,
  PumpTelemetry,
  DeviceTelemetry
} from '../types';

export interface IoTLayerToggles {
  pumpingStations: boolean;
  stps: boolean;
  tanks: boolean;
  wtps: boolean;
  flowMeters: boolean;
  pressureSensors: boolean;
  levelSensors: boolean;
  qualityAnalysers: boolean;
  borewells: boolean;
  valves: boolean;
  smartMeters: boolean;
  mldCorridors: boolean;
  gisPipes: boolean;
}

export interface IoTStoreState {
  // Telemetry & Assets
  stations: StationOverview[];
  divisions: DivisionBoardSummary[];
  corridors: WaterFlowCorridor[];
  waterBalance: WaterBalanceSummary | null;
  alerts: IoTAlertItem[];
  activeInjections: Record<string, any>;
  layerToggles: IoTLayerToggles;

  // Simulation Clock
  simClock: {
    ts: number;
    clock_utc: string;
  };

  // Selection
  selectedStation: StationOverview | null;
  selectedPump: PumpTelemetry | null;
  selectedDevice: DeviceTelemetry | null;
  selectedDivision: DivisionBoardSummary | null;
  selectedInspectorType: 'pump' | 'station' | 'stp' | 'flow_sensor' | 'meter' | 'tank' | 'division' | 'device' | null;

  // UI state
  apiErrorBanner: string | null;
  activeToast: { id: string; message: string; type: 'info' | 'error' | 'success' } | null;
  isSimulateOpen: boolean;
  acknowledgedAlertIds: string[];

  // Actions
  setSnapshot: (snapshot: {
    ts: number;
    clock_utc: string;
    stations: StationOverview[];
    alerts: IoTAlertItem[];
    smart_meters: DivisionBoardSummary[];
    corridors: WaterFlowCorridor[];
    water_balance: WaterBalanceSummary;
    active_injections?: any;
  }) => void;

  mergeSSEDeltas: (deltas: {
    ts: number;
    clock_utc: string;
    stations?: StationOverview[];
    alerts?: IoTAlertItem[];
  }) => void;

  setSelectedStation: (station: StationOverview | null) => void;
  setSelectedPump: (pump: PumpTelemetry | null) => void;
  setSelectedDevice: (device: DeviceTelemetry | null) => void;
  setSelectedDivision: (division: DivisionBoardSummary | null) => void;
  setSelectedInspectorType: (type: IoTStoreState['selectedInspectorType']) => void;

  setApiErrorBanner: (msg: string | null) => void;
  setActiveToast: (toast: IoTStoreState['activeToast']) => void;
  setIsSimulateOpen: (open: boolean) => void;

  toggleLayer: (layer: keyof IoTLayerToggles) => void;
  setLayerVisibility: (layer: keyof IoTLayerToggles, visible: boolean) => void;

  acknowledgeAlertLocally: (alertId: string) => void;
  snoozeAlertLocally: (alertId: string) => void;
  clearAlertLocally: (alertId: string) => void;
}

let state: IoTStoreState;
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((listener) => listener());
}

state = {
  stations: [],
  divisions: [],
  corridors: [],
  waterBalance: null,
  alerts: [],
  activeInjections: {},
  layerToggles: {
    pumpingStations: true,
    stps: true,
    tanks: true,
    wtps: true,
    flowMeters: true,
    pressureSensors: true,
    levelSensors: true,
    qualityAnalysers: true,
    borewells: true,
    valves: true,
    smartMeters: true,
    mldCorridors: true,
    gisPipes: true,
  },
  simClock: {
    ts: Date.now() / 1000,
    clock_utc: new Date().toISOString()
  },

  selectedStation: null,
  selectedPump: null,
  selectedDevice: null,
  selectedDivision: null,
  selectedInspectorType: null,

  apiErrorBanner: null,
  activeToast: null,
  isSimulateOpen: false,
  acknowledgedAlertIds: [],

  setSnapshot: (snapshot) => {
    state = {
      ...state,
      simClock: {
        ts: snapshot.ts,
        clock_utc: snapshot.clock_utc
      },
      stations: snapshot.stations || [],
      alerts: snapshot.alerts || [],
      divisions: snapshot.smart_meters || [],
      corridors: snapshot.corridors || [],
      waterBalance: snapshot.water_balance || null,
      activeInjections: snapshot.active_injections || {}
    };
    notify();
  },

  mergeSSEDeltas: (deltas) => {
    const updatedStations = deltas.stations || state.stations;
    let updatedAlerts = state.alerts;
    if (deltas.alerts) {
      const alertMap = new Map<string, IoTAlertItem>();
      state.alerts.forEach((a) => alertMap.set(a.alert_id, a));
      deltas.alerts.forEach((a) => alertMap.set(a.alert_id, a));
      updatedAlerts = Array.from(alertMap.values()).sort((a, b) => (b.last_seen || 0) - (a.last_seen || 0));
    }

    // Keep selected pump/device updated with fresh telemetry
    let updatedSelectedPump = state.selectedPump;
    if (updatedSelectedPump) {
      for (const s of updatedStations) {
        const found = s.pumps.find((p) => p.pump_id === updatedSelectedPump?.pump_id);
        if (found) {
          updatedSelectedPump = found;
          break;
        }
      }
    }

    let updatedSelectedDevice = state.selectedDevice;
    if (updatedSelectedDevice) {
      for (const s of updatedStations) {
        const found = s.devices.find((d) => d.tag === updatedSelectedDevice?.tag);
        if (found) {
          updatedSelectedDevice = found;
          break;
        }
      }
    }

    state = {
      ...state,
      simClock: {
        ts: deltas.ts,
        clock_utc: deltas.clock_utc
      },
      stations: updatedStations,
      alerts: updatedAlerts,
      selectedPump: updatedSelectedPump,
      selectedDevice: updatedSelectedDevice
    };
    notify();
  },

  setSelectedStation: (selectedStation) => {
    state = { ...state, selectedStation };
    notify();
  },

  setSelectedPump: (selectedPump) => {
    state = { ...state, selectedPump, selectedInspectorType: selectedPump ? 'pump' : null };
    notify();
  },

  setSelectedDevice: (selectedDevice) => {
    state = {
      ...state,
      selectedDevice,
      selectedInspectorType: selectedDevice ? (selectedDevice.type_code === 'FIT' ? 'meter' : 'device') : null
    };
    notify();
  },

  setSelectedDivision: (selectedDivision) => {
    state = { ...state, selectedDivision, selectedInspectorType: selectedDivision ? 'division' : null };
    notify();
  },

  setSelectedInspectorType: (selectedInspectorType) => {
    state = { ...state, selectedInspectorType };
    notify();
  },

  setApiErrorBanner: (apiErrorBanner) => {
    state = { ...state, apiErrorBanner };
    notify();
  },

  setActiveToast: (activeToast) => {
    state = { ...state, activeToast };
    notify();
  },

  setIsSimulateOpen: (isSimulateOpen) => {
    state = { ...state, isSimulateOpen };
    notify();
  },

  acknowledgeAlertLocally: (alertId) => {
    state = {
      ...state,
      alerts: state.alerts.map((a) =>
        a.alert_id === alertId ? { ...a, status: 'ACKNOWLEDGED', acknowledged: true } : a
      ),
      acknowledgedAlertIds: [...state.acknowledgedAlertIds, alertId]
    };
    notify();
  },

  snoozeAlertLocally: (alertId) => {
    state = {
      ...state,
      alerts: state.alerts.map((a) =>
        a.alert_id === alertId ? { ...a, status: 'SHELVED', shelved: true } : a
      )
    };
    notify();
  },

  toggleLayer: (layer) => {
    state = {
      ...state,
      layerToggles: {
        ...state.layerToggles,
        [layer]: !state.layerToggles[layer]
      }
    };
    notify();
  },

  setLayerVisibility: (layer, visible) => {
    state = {
      ...state,
      layerToggles: {
        ...state.layerToggles,
        [layer]: visible
      }
    };
    notify();
  },

  clearAlertLocally: (alertId) => {
    state = {
      ...state,
      alerts: state.alerts.map((a) =>
        a.alert_id === alertId ? { ...a, status: 'CLEARED', active: false } : a
      )
    };
    notify();
  }
};


export interface IoTStoreHook {
  (): IoTStoreState;
  <T>(selector: (state: IoTStoreState) => T): T;
  getState: () => IoTStoreState;
  setState: (partial: Partial<IoTStoreState>) => void;
}

export const useIoTStore: IoTStoreHook = Object.assign(
  function useIoTStore<T>(selector?: (state: IoTStoreState) => T): T | IoTStoreState {
    return useSyncExternalStore(
      (onStoreChange) => {
        listeners.add(onStoreChange);
        return () => listeners.delete(onStoreChange);
      },
      () => (selector ? selector(state) : state),
      () => (selector ? selector(state) : state)
    );
  },
  {
    getState: () => state,
    setState: (partial: Partial<IoTStoreState>) => {
      state = { ...state, ...partial };
      notify();
    }
  }
);
