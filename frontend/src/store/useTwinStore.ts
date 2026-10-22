/**
 * Unified Zustand-compatible store for digital twin application state.
 * Built with React's useSyncExternalStore for zero-dependency reliability.
 */

import { useSyncExternalStore } from 'react';
import { SelectedAsset, AlertItem } from '../types';

export type BasemapTheme = 'light' | 'dark' | 'satellite';

export interface LayerSetting {
  visible: boolean;
  opacity: number;
}

export interface TwinState {
  // Theme
  theme: BasemapTheme;
  setTheme: (theme: BasemapTheme) => void;

  // Selected Asset
  selectedAsset: SelectedAsset | null;
  setSelectedAsset: (asset: SelectedAsset | null) => void;

  // Left Rail
  isLeftRailOpen: boolean;
  toggleLeftRail: () => void;
  leftRailTab: 'alerts' | 'layers';
  setLeftRailTab: (tab: 'alerts' | 'layers') => void;

  // Right Admin Drawer
  isAdminDrawerOpen: boolean;
  setIsAdminDrawerOpen: (open: boolean) => void;

  // Simulate Popover
  isSimulateOpen: boolean;
  setIsSimulateOpen: (open: boolean) => void;

  // Legend Overlay
  isLegendOpen: boolean;
  setIsLegendOpen: (open: boolean) => void;

  // Map Camera Navigation Target
  flyToTarget: [number, number] | null;
  setFlyToTarget: (target: [number, number] | null) => void;

  // Active Simulation Scenario
  activeScenario: string;
  setActiveScenario: (scenario: string) => void;

  // Active Suspect Leak Pipe ID
  activeLeakPipeId: string | null;
  setActiveLeakPipeId: (id: string | null) => void;

  // Live Telemetry Feed State & Watchdog
  isFeedFresh: boolean;
  setIsFeedFresh: (fresh: boolean) => void;
  lastFeedTime: number;
  setLastFeedTime: (time: number) => void;

  // Unified KPIs
  kpis: {
    runningPumps: number;
    totalPumps: number;
    energyMwh: number;
    energyCostLakhs: number;
    waterLossKld: number;
  };
  setKpis: (kpis: Partial<TwinState['kpis']>) => void;

  // Unified Alerts
  alerts: AlertItem[];
  setAlerts: (alerts: AlertItem[]) => void;

  // Simulated Time Clock
  simulatedHour: number;
  setSimulatedHour: (hour: number) => void;

  // Layer Visibility & Opacity Settings
  layers: {
    trunkMains: LayerSetting;
    distributionMains: LayerSetting;
    pumpingStations: LayerSetting;
    stps: LayerSetting;
    waterBodies: LayerSetting;
    divisionBoundaries: LayerSetting;
  };
  setLayerVisibility: (layer: keyof TwinState['layers'], visible: boolean) => void;
  setLayerOpacity: (layer: keyof TwinState['layers'], opacity: number) => void;
}

let state: TwinState;
const listeners = new Set<() => void>();

function notify() {
  listeners.forEach((listener) => listener());
}

state = {
  theme: 'light', // Light default as requested
  setTheme: (theme) => {
    state = { ...state, theme };
    notify();
  },

  selectedAsset: null,
  setSelectedAsset: (selectedAsset) => {
    state = { ...state, selectedAsset };
    notify();
  },

  isLeftRailOpen: true,
  toggleLeftRail: () => {
    state = { ...state, isLeftRailOpen: !state.isLeftRailOpen };
    notify();
  },
  leftRailTab: 'alerts',
  setLeftRailTab: (leftRailTab) => {
    state = { ...state, leftRailTab };
    notify();
  },

  isAdminDrawerOpen: false,
  setIsAdminDrawerOpen: (isAdminDrawerOpen) => {
    state = { ...state, isAdminDrawerOpen };
    notify();
  },

  isSimulateOpen: false,
  setIsSimulateOpen: (isSimulateOpen) => {
    state = { ...state, isSimulateOpen };
    notify();
  },

  isLegendOpen: false,
  setIsLegendOpen: (isLegendOpen) => {
    state = { ...state, isLegendOpen };
    notify();
  },

  flyToTarget: null,
  setFlyToTarget: (flyToTarget) => {
    state = { ...state, flyToTarget };
    notify();
  },

  activeScenario: 'BASELINE',
  setActiveScenario: (activeScenario) => {
    state = { ...state, activeScenario };
    notify();
  },

  activeLeakPipeId: null,
  setActiveLeakPipeId: (activeLeakPipeId) => {
    state = { ...state, activeLeakPipeId };
    notify();
  },

  isFeedFresh: false,
  setIsFeedFresh: (isFeedFresh) => {
    state = { ...state, isFeedFresh };
    notify();
  },
  lastFeedTime: 0,
  setLastFeedTime: (lastFeedTime) => {
    state = { ...state, lastFeedTime };
    notify();
  },

  kpis: {
    runningPumps: 2,
    totalPumps: 3,
    energyMwh: 57.1,
    energyCostLakhs: 4.28,
    waterLossKld: 0.0,
  },
  setKpis: (newKpis) => {
    state = { ...state, kpis: { ...state.kpis, ...newKpis } };
    notify();
  },

  alerts: [],
  setAlerts: (alerts) => {
    state = { ...state, alerts };
    notify();
  },

  simulatedHour: 12,
  setSimulatedHour: (simulatedHour) => {
    state = { ...state, simulatedHour };
    notify();
  },

  layers: {
    trunkMains: { visible: true, opacity: 1.0 },
    distributionMains: { visible: true, opacity: 1.0 },
    pumpingStations: { visible: true, opacity: 1.0 },
    stps: { visible: true, opacity: 1.0 },
    waterBodies: { visible: true, opacity: 0.8 },
    divisionBoundaries: { visible: true, opacity: 0.6 },
  },
  setLayerVisibility: (layer, visible) => {
    state = {
      ...state,
      layers: {
        ...state.layers,
        [layer]: { ...state.layers[layer], visible },
      },
    };
    notify();
  },
  setLayerOpacity: (layer, opacity) => {
    state = {
      ...state,
      layers: {
        ...state.layers,
        [layer]: { ...state.layers[layer], opacity },
      },
    };
    notify();
  },
};

export interface TwinStoreHook {
  (): TwinState;
  <T>(selector: (state: TwinState) => T): T;
  getState: () => TwinState;
  setState: (partial: Partial<TwinState>) => void;
}

export const useTwinStore: TwinStoreHook = Object.assign(
  function useTwinStore<T>(selector?: (state: TwinState) => T): T | TwinState {
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
    setState: (partial: Partial<TwinState>) => {
      state = { ...state, ...partial };
      notify();
    },
  }
);
