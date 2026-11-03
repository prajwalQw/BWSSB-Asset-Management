import React, { useState, useEffect } from 'react';
import { useTwinStore } from '../../store/useTwinStore';
import { IoTLeftRail } from './components/IoTLeftRail';
import { StationSchematic } from './components/StationSchematic';
import { WaterFlowSankey } from './components/WaterFlowSankey';
import { IoTRightInspector } from './components/IoTRightInspector';
import { IoTSimulateModal } from './components/IoTSimulateModal';
import { IoTAlertToasts } from './components/IoTAlertToasts';
import { IoTLeakDetectionPopup } from './components/IoTLeakDetectionPopup';
import { DigitalTwinMap } from '../../components/map/DigitalTwinMap';
import { iotApi } from './services/iotApi';
import {
  StationOverview,
  DivisionBoardSummary,
  WaterFlowCorridor,
  WaterBalanceSummary,
  IoTAlertItem,
  PumpTelemetry,
  DeviceTelemetry
} from './types';
import { useIoTStore } from './store/useIoTStore';
import { demoApi, DemoStatus } from './services/demoApi';
import { sseManager } from '../../services/sseManager';
import { ErrorBoundary } from '../../components/common/ErrorBoundary';
import { WARD_LEAK_LOCATIONS } from '../../App';
import { Map, GitCommit, Waves, Play, RotateCcw } from 'lucide-react';

export const IoTWorkstation: React.FC = () => {
  const { theme, flyToTarget, setFlyToTarget, activeLeakPipeId } = useTwinStore();
  const [demoStatus, setDemoStatus] = useState<DemoStatus | null>(null);
  const [isDemoStarting, setIsDemoStarting] = useState(false);

  useEffect(() => {
    demoApi.getStatus().then(setDemoStatus).catch(() => {});
    const unsubDemo = sseManager.subscribe('demo', (data: any) => {
      if (data) setDemoStatus(data);
    });
    const unsubAgent = sseManager.subscribe('agent', (data: any) => {
      if (data?.demo) setDemoStatus(data.demo);
    });
    return () => {
      unsubDemo();
      unsubAgent();
    };
  }, []);

  const [selectedWard, setSelectedWard] = useState<string>('Basavanagudi');

  const handleStartLeakDemo = async (wardToRun?: string) => {
    const ward = wardToRun || selectedWard;
    try {
      setIsDemoStarting(true);
      // 1. Immediately switch view to map
      setCentreView('map');
      // 2. Zoom in where the leak is happening
      const loc = WARD_LEAK_LOCATIONS[ward] || WARD_LEAK_LOCATIONS['Basavanagudi'];
      setFlyToTarget(loc.coords);
      // 3. Start demo for selected ward
      await demoApi.startDemo(ward);
      const st = await demoApi.getStatus();
      setDemoStatus(st);
    } catch (e) {
      console.error(e);
    } finally {
      setIsDemoStarting(false);
    }
  };

  const handleResetLeakDemo = async () => {
    try {
      await demoApi.resetDemo();
      const st = await demoApi.getStatus();
      setDemoStatus(st);
    } catch (e) {
      console.error(e);
    }
  };
  const {
    stations,
    divisions,
    corridors,
    waterBalance,
    alerts,
    selectedStation,
    selectedPump,
    selectedDevice,
    selectedDivision,
    selectedInspectorType,
    setSelectedStation,
    setSelectedPump,
    setSelectedDevice,
    setSelectedDivision,
    setSelectedInspectorType,
    isSimulateOpen,
    setIsSimulateOpen,
    acknowledgeAlertLocally,
    snoozeAlertLocally,
  } = useIoTStore();

  // Centre Segmented Control: Map | Station schematic | Water flow (MLD)
  const [centreView, setCentreView] = useState<'map' | 'schematic' | 'sankey'>('map');

  const balance = waterBalance || {
    total_inflow_mld: 2250.0,
    total_outflow_mld: 1845.0,
    storage_change_mld: 12.0,
    unaccounted_mld: 393.0,
    unaccounted_pct: 17.5,
    balanced: true,
    data_tier: 'SIMULATED'
  };

  useEffect(() => {
    if (stations.length > 0 && !selectedStation) {
      setSelectedStation(stations[0]);
    }
  }, [stations, selectedStation, setSelectedStation]);

  // Handlers
  const handleSelectPump = (pumpId: string) => {
    for (const s of stations) {
      const p = s.pumps.find((item) => item.pump_id === pumpId);
      if (p) {
        setSelectedPump(p);
        setSelectedInspectorType('pump');
        return;
      }
    }
  };

  const handleSelectDevice = (tag: string) => {
    for (const s of stations) {
      const d = s.devices.find((item) => item.tag === tag);
      if (d) {
        setSelectedDevice(d);
        setSelectedInspectorType(d.type_code === 'FIT' ? 'meter' : 'device');
        return;
      }
    }
  };

  const handleSelectDivision = (divName: string) => {
    const div = divisions.find((d) => d.division_name === divName);
    if (div) {
      setSelectedDivision(div);
      setSelectedInspectorType('division');
    }
  };

  const handleSelectAlert = (alert: IoTAlertItem) => {
    if (alert.coordinates) {
      setFlyToTarget(alert.coordinates);
      setCentreView('map');
    }
  };

  return (
    <div className="flex flex-col h-full w-full overflow-hidden bg-slate-950 text-slate-100 select-none relative">
      {/* 1. Subheader: Segmented Control & Controls */}
      <div className="h-10 px-4 border-b border-slate-800 bg-slate-900/90 flex items-center justify-between z-20">
        <div className="flex items-center gap-1.5 rounded-lg border border-slate-800 p-0.5 bg-slate-950 text-xs">
          <button
            type="button"
            onClick={() => setCentreView('map')}
            className={`px-3 py-1 rounded-md font-medium transition-all flex items-center gap-1.5 ${
              centreView === 'map'
                ? 'bg-sky-600 text-white shadow-sm font-semibold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Map className="w-3.5 h-3.5" />
            <span>Map</span>
          </button>
          <button
            type="button"
            onClick={() => setCentreView('schematic')}
            className={`px-3 py-1 rounded-md font-medium transition-all flex items-center gap-1.5 ${
              centreView === 'schematic'
                ? 'bg-sky-600 text-white shadow-sm font-semibold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <GitCommit className="w-3.5 h-3.5" />
            <span>Station schematic</span>
          </button>
          <button
            type="button"
            onClick={() => setCentreView('sankey')}
            className={`px-3 py-1 rounded-md font-medium transition-all flex items-center gap-1.5 ${
              centreView === 'sankey'
                ? 'bg-sky-600 text-white shadow-sm font-semibold'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Waves className="w-3.5 h-3.5" />
            <span>Water flow (MLD)</span>
          </button>
        </div>

        {/* Right side controls */}
        <div className="flex items-center gap-2">
          {centreView === 'schematic' && stations.length > 0 && (
            <select
              value={selectedStation?.id || ''}
              onChange={(e) => {
                const found = stations.find((s) => s.id === e.target.value);
                if (found) setSelectedStation(found);
              }}
              className="h-7 px-2.5 rounded bg-slate-800 border border-slate-700 text-xs font-mono text-slate-200"
            >
              {stations.map((s) => (
                <option key={s.id} value={s.id}>
                  {s.name}
                </option>
              ))}
            </select>
          )}

          <div className="flex items-center gap-1.5 bg-slate-800/90 border border-slate-700/80 rounded px-2 h-7" title="Select target ward for leak demo">
            <span className="text-[10px] text-slate-400 font-medium">Ward:</span>
            <select
              value={selectedWard}
              onChange={(e) => setSelectedWard(e.target.value)}
              disabled={Boolean(demoStatus?.state && demoStatus.state !== 'IDLE' && demoStatus.state !== 'RESTORED')}
              className="bg-transparent text-xs text-rose-300 font-semibold focus:outline-none cursor-pointer"
            >
              <option value="Basavanagudi" className="bg-slate-900 text-slate-200">Basavanagudi</option>
              <option value="Hanumanthanagar" className="bg-slate-900 text-slate-200">Hanumanthanagar</option>
              <option value="Chamarajpet" className="bg-slate-900 text-slate-200">Chamarajpet</option>
              <option value="Padmanabhanagar" className="bg-slate-900 text-slate-200">Padmanabhanagar</option>
            </select>
          </div>

          <button
            type="button"
            onClick={() => handleStartLeakDemo()}
            disabled={isDemoStarting || (demoStatus?.state !== 'IDLE' && demoStatus?.state !== 'RESTORED' && !!demoStatus?.state)}
            className={`h-7 px-3 rounded text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm ${
              demoStatus?.state && demoStatus.state !== 'IDLE' && demoStatus.state !== 'RESTORED'
                ? 'bg-rose-950 text-rose-300 border border-rose-500/50 cursor-not-allowed'
                : 'bg-rose-600 hover:bg-rose-500 text-white'
            }`}
          >
            <Play className="w-3 h-3 fill-current" />
            <span>{demoStatus?.state && demoStatus.state !== 'IDLE' && demoStatus.state !== 'RESTORED' ? `Demo: ${demoStatus.state}` : 'Run leak demo'}</span>
          </button>

          <button
            type="button"
            onClick={handleResetLeakDemo}
            className="h-7 px-2.5 rounded text-xs font-semibold flex items-center gap-1 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
            title="Reset demo to baseline"
          >
            <RotateCcw className="w-3 h-3" />
            <span>Reset demo</span>
          </button>

          <button
            type="button"
            onClick={() => setIsSimulateOpen(true)}
            className="h-7 px-3 rounded text-xs font-semibold flex items-center gap-1.5 bg-purple-600 hover:bg-purple-500 text-white transition-colors shadow-sm"
          >
            <Play className="w-3 h-3 fill-current" />
            <span>Simulate IoT</span>
          </button>
        </div>
      </div>

      {/* 2. Main 3-Column Workstation */}
      <div className="flex h-[calc(100%-40px)] w-full overflow-hidden relative">
        {/* Left Rail (300px) */}
        <IoTLeftRail
          stations={stations}
          divisions={divisions}
          alerts={alerts}
          selectedId={selectedPump?.pump_id || selectedDevice?.tag || selectedDivision?.division_name || null}
          onSelectStation={(stn) => {
            setSelectedStation(stn);
            if (stn.coordinates) setFlyToTarget(stn.coordinates);
          }}
          onSelectPump={(pid) => handleSelectPump(pid)}
          onSelectDevice={(tag) => handleSelectDevice(tag)}
          onSelectDivision={(divName) => handleSelectDivision(divName)}
          onSelectAlert={(alrt) => handleSelectAlert(alrt)}
        />

        {/* Centre Stage */}
        <main className="flex-1 h-full relative overflow-hidden bg-slate-950">
          {centreView === 'map' && (
            <DigitalTwinMap
              selectedAsset={null}
              onSelectAsset={(asset) => {
                if (asset?.properties?.is_pump) {
                  handleSelectPump(asset.id);
                } else if (asset?.properties?.is_division) {
                  handleSelectDivision(asset.name);
                }
              }}
              activeScenario="BASELINE"
              currentHour={12}
              isDarkTheme={theme === 'dark' || theme === 'satellite'}
              activeLeakPipeId={activeLeakPipeId || (demoStatus?.state && demoStatus.state !== 'IDLE' && demoStatus.state !== 'RESTORED' ? 'CORR_TATAGUNI_MOUNT_JOY' : undefined)}
              demoStatus={demoStatus}
              flyToTarget={flyToTarget}
              onNavigateToMonitor={() => {
                setCentreView('monitor' as any);
              }}
            />
          )}

          {centreView === 'schematic' && selectedStation && (
            <ErrorBoundary fallbackTitle="Station Schematic Unavailable">
              <StationSchematic
                station={selectedStation}
                onSelectElement={(type, id) => {
                  if (type === 'pump') handleSelectPump(id);
                  else if (type === 'meter' || type === 'flow_sensor') handleSelectDevice(id);
                }}
                selectedElementId={selectedPump?.pump_id || selectedDevice?.tag}
              />
            </ErrorBoundary>
          )}

          {centreView === 'sankey' && (
            <ErrorBoundary fallbackTitle="Water Flow Balance Unavailable">
              <WaterFlowSankey corridors={corridors} balance={balance} />
            </ErrorBoundary>
          )}
        </main>

        {/* Right Inspector (380px) */}
        <IoTRightInspector
          selectedType={selectedInspectorType}
          selectedPump={selectedPump}
          selectedDevice={selectedDevice}
          selectedDivision={selectedDivision}
          onClose={() => setSelectedInspectorType(null)}
          onZoomTo={(coords) => setFlyToTarget(coords)}
        />
      </div>

      {/* 3. Simulate Popover Modal */}
      {isSimulateOpen && (
        <IoTSimulateModal
          onClose={() => setIsSimulateOpen(false)}
          onRefresh={() => {}}
        />
      )}

      {/* 4. Top-Centre Leak Detection Popup (P5) */}
      <IoTLeakDetectionPopup
        alerts={alerts}
        demoStatus={demoStatus}
        onShowOnMap={(coords) => {
          setFlyToTarget(coords);
          setCentreView('map');
        }}
        onAcknowledge={(id) => {
          acknowledgeAlertLocally(id);
          iotApi.acknowledgeAlert(id).catch(console.error);
        }}
        onSnooze={(id) => {
          snoozeAlertLocally(id);
          iotApi.snoozeAlert(id).catch(console.error);
        }}
      />

      {/* 5. General Alert Toasts */}
      <IoTAlertToasts
        alerts={alerts.filter(a => a.rule_id !== 'RULE-IOT-LEAK-01')}
        onZoomTo={(coords) => {
          setFlyToTarget(coords);
          setCentreView('map');
        }}
        onAcknowledge={(id) => {
          acknowledgeAlertLocally(id);
          iotApi.acknowledgeAlert(id).catch(console.error);
        }}
        onSnooze={(id) => {
          snoozeAlertLocally(id);
          iotApi.snoozeAlert(id).catch(console.error);
        }}
      />

    </div>
  );
};
