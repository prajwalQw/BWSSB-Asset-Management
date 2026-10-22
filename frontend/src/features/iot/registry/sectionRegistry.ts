import React from 'react';
import { useIoTStore } from '../store/useIoTStore';
import { IoTRightInspector } from '../components/IoTRightInspector';

/**
 * Additive Section Registry for RightInspector.
 * Allows new inspector sections to be mounted dynamically based on asset predicate.
 */

export interface InspectorSectionProvider {
  predicate: (asset: any) => boolean;
  render: (asset: any, onClose: () => void, onZoomTo?: (coords: [number, number]) => void) => React.ReactNode;
}

const sectionProviders: InspectorSectionProvider[] = [];

export const sectionRegistry = {
  register(provider: InspectorSectionProvider) {
    sectionProviders.push(provider);
  },

  renderSection(asset: any, onClose: () => void, onZoomTo?: (coords: [number, number]) => void): React.ReactNode | null {
    for (const provider of sectionProviders) {
      if (provider.predicate(asset)) {
        return provider.render(asset, onClose, onZoomTo);
      }
    }
    return null;
  }
};

// Auto-register IoT inspector section provider for GIS view
sectionRegistry.register({
  predicate: (asset: any) => {
    if (!asset) return false;
    const cat = asset.category || '';
    if (cat === 'PUMPING_STATION' || cat === 'STP' || cat === 'PUMP' || cat === 'FLOW_METER' || cat === 'PRESSURE_TRANSMITTER' || cat === 'BOREWELL') {
      return true;
    }
    if (asset.dataTier === 'SIMULATED' || asset.properties?._data_tier === 'SIMULATED' || asset.properties?.is_simulated) {
      return true;
    }
    return false;
  },
  render: (asset: any, onClose: () => void, onZoomTo?: (coords: [number, number]) => void) => {
    const store = useIoTStore.getState();
    const cat = asset.category || '';
    let selectedType: any = 'device';
    let selectedStation = null;
    let selectedPump = null;

    if (cat === 'PUMPING_STATION') {
      selectedType = 'station';
      selectedStation = store.stations.find((s) => s.id === asset.id || s.name === asset.name) || store.stations[0];
    } else if (cat === 'STP') {
      selectedType = 'stp';
      selectedStation = store.stations.find((s) => s.id === asset.id || s.name === asset.name) || store.stations.find((s) => s.station_class === 'stp') || store.stations[0];
    } else if (cat === 'PUMP') {
      selectedType = 'pump';
      for (const s of store.stations) {
        const p = s.pumps.find((p) => p.pump_id === asset.id || p.tag === asset.id);
        if (p) { selectedPump = p; break; }
      }
      if (!selectedPump && store.stations[0]?.pumps[0]) {
        selectedPump = store.stations[0].pumps[0];
      }
    } else if (cat === 'FLOW_METER') {
      selectedType = 'meter';
    }

    return React.createElement(IoTRightInspector, {
      selectedType,
      selectedStation,
      selectedPump,
      selectedDevice: {
        tag: asset.id || 'INST-01',
        name: asset.name || 'Instrumentation Device',
        type_code: cat === 'FLOW_METER' ? 'FIT' : cat === 'PRESSURE_TRANSMITTER' ? 'PIT' : 'FIT',
        asset_link: asset.id || 'INST-01',
        location: { coordinates: asset.coordinates },
        active: true,
        comms_state: 'ONLINE',
        last_seen: Date.now() / 1000,
        quality: 'Good',
        data_tier: 'SIMULATED',
        latest_values: { value: Number(asset.properties?.flow_lps ?? asset.properties?.value ?? 0.0), unit: 'L/s' }
      },
      onClose,
      onZoomTo,
      onSelectPump: (pid: string) => {
        store.setSelectedInspectorType('pump');
        for (const s of store.stations) {
          const p = s.pumps.find((item) => item.pump_id === pid);
          if (p) { store.setSelectedPump(p); break; }
        }
      }
    });
  }
});
