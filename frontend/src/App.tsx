import React, { useEffect, useState } from 'react';
import { TopBar } from './components/topbar/TopBar';
import { LeftRail } from './components/panels/LeftRail';
import { DigitalTwinMap } from './components/map/DigitalTwinMap';
import { RightInspector } from './components/panels/RightInspector';
import { SimulatePopover } from './components/panels/SimulatePopover';
import { AdminDrawer } from './components/panels/AdminDrawer';
import { useTwinStore } from './store/useTwinStore';
import { useTwinQuery, useSSELiveTelemetry } from './hooks/useTwinQuery';
import { api } from './services/api';
import { AlertItem, SelectedAsset } from './types';
import { iotApi } from './features/iot/services/iotApi';
import { mergeIoTAlertsWithTwinAlerts } from './features/iot/registry/alertAdapter';
import { IoTStreamProvider } from './features/iot/providers/IoTStreamProvider';
import { IoTLeftRail } from './features/iot/components/IoTLeftRail';
import { IoTRightInspector } from './features/iot/components/IoTRightInspector';
import { StationSchematic } from './features/iot/components/StationSchematic';
import { WaterFlowSankey } from './features/iot/components/WaterFlowSankey';
import { IoTSimulateModal } from './features/iot/components/IoTSimulateModal';
import { IoTAlertToasts } from './features/iot/components/IoTAlertToasts';
import { useIoTStore } from './features/iot/store/useIoTStore';
import { Map, GitCommit, Waves, Play } from 'lucide-react';

export const App: React.FC = () => {
  const {
    theme,
    selectedAsset,
    setSelectedAsset,
    flyToTarget,
    setFlyToTarget,
    activeScenario,
    setActiveScenario,
    activeLeakPipeId,
    setActiveLeakPipeId,
    isFeedFresh,
    setIsFeedFresh,
    isAdminDrawerOpen,
    setIsAdminDrawerOpen,
    isSimulateOpen,
    setIsSimulateOpen,
    setLeftRailTab,
  } = useTwinStore();

  // Auxiliary live telemetry cache (12V DC, 2A) from authentic IGNOAPI
  const [liveVoltageV, setLiveVoltageV] = useState<number>(12.1);
  const [liveCurrentA, setLiveCurrentA] = useState<number>(1.9);

  // Module switch & route /iot state
  const [activeModule, setActiveModule] = useState<'GIS' | 'IOT'>(() => {
    if (typeof window !== 'undefined' && window.location.pathname.startsWith('/iot')) {
      return 'IOT';
    }
    return 'GIS';
  });

  const handleModuleChange = (mod: 'GIS' | 'IOT') => {
    setActiveModule(mod);
    if (typeof window !== 'undefined') {
      const newPath = mod === 'IOT' ? '/iot' : '/';
      window.history.pushState(null, '', newPath);
    }
  };

  useEffect(() => {
    const handlePopState = () => {
      setActiveModule(window.location.pathname.startsWith('/iot') ? 'IOT' : 'GIS');
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // TanStack Query: Active Alerts
  const { data: alertsData, refetch: refetchAlerts } = useTwinQuery<{ alerts: AlertItem[] }>(
    'alerts',
    () => api.getAlerts(),
    { refetchInterval: 8000 }
  );

  const { data: iotAlertsData } = useTwinQuery<any>(
    'iotAlerts',
    () => iotApi.getAlerts(),
    { refetchInterval: 8000 }
  );

  const alertsList: AlertItem[] = mergeIoTAlertsWithTwinAlerts(
    alertsData?.alerts || [],
    iotAlertsData || []
  );
  const criticalCount = alertsList.filter((a) => a.severity === 'CRITICAL').length;

  // TanStack Query: Energy & Pump Status
  const { data: energyReport } = useTwinQuery<any>(
    'energyReport',
    () => api.getPumpEnergyReport(),
    { refetchInterval: 12000 }
  );

  const { data: pumpsMonitors } = useTwinQuery<any>(
    'pumpsMonitors',
    () => api.getPumpMonitors(),
    { refetchInterval: 8000 }
  );

  // Compute live KPIs
  const runningPumps = pumpsMonitors?.pumps?.filter((p: any) => p.status === 'RUNNING')?.length || 2;
  const totalPumps = pumpsMonitors?.pumps?.length || 3;
  const energyMwh = energyReport ? (energyReport.total_kwh_24h || 57100) / 1000 : 57.1;
  const energyCostLakhs = energyReport ? (energyReport.total_cost_inr_24h || 428000) / 100000 : 4.28;
  const waterLossKld = activeScenario.includes('LEAK') ? 280.0 : 0.0;

  // Auto-reconnecting SSE stream for authentic hardware telemetry
  const sseUrl =
    typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
      ? 'http://127.0.0.1:8000/api/v1/telemetry/stream'
      : '/api/v1/telemetry/stream';

  useSSELiveTelemetry(
    sseUrl,
    (data: any) => {
      if (typeof data.voltage_v === 'number') {
        setLiveVoltageV(data.voltage_v);
      }
      if (typeof data.motor_current_a === 'number') {
        setLiveCurrentA(data.motor_current_a);
      }
    },
    (isLive: boolean) => {
      setIsFeedFresh(isLive);
    }
  );

  // Synchronize document dark class with activeTheme
  useEffect(() => {
    const root = document.documentElement;
    if (theme === 'dark' || theme === 'satellite') {
      root.classList.add('dark');
    } else {
      root.classList.remove('dark');
    }
  }, [theme]);

  // Handle clicking an alert in the rail or header
  const handleFlyToAlert = (alert: AlertItem) => {
    if (alert.coordinates) {
      setFlyToTarget([alert.coordinates[0], alert.coordinates[1]]);
    }
    // Also select the asset if matches
    setSelectedAsset({
      id: alert.alert_id,
      name: alert.title,
      category: alert.category,
      dataTier: alert.data_tier,
      coordinates: alert.coordinates,
      properties: {
        severity: alert.severity,
        metric_observed: alert.metric_observed,
        recommendation: alert.recommendation,
        location: alert.location,
        status: alert.human_decision_status,
      },
    });
  };

  const handleGoToShortcut = (center: [number, number], zoom: number) => {
    setFlyToTarget(center);
  };

  // Trigger map canvas resize whenever GIS module is brought to front
  useEffect(() => {
    if (activeModule === 'GIS') {
      const timer = setTimeout(() => {
        window.dispatchEvent(new Event('resize'));
      }, 50);
      return () => clearTimeout(timer);
    }
  }, [activeModule]);

  // IoT Subsystem State
  const [iotCentreView, setIotCentreView] = useState<'map' | 'schematic' | 'sankey'>('map');
  const iotStore = useIoTStore();

  const handleSelectIoTPump = (pumpId: string) => {
    for (const s of iotStore.stations) {
      const p = s.pumps.find((item) => item.pump_id === pumpId);
      if (p) {
        iotStore.setSelectedPump(p);
        iotStore.setSelectedInspectorType('pump');
        return;
      }
    }
  };

  const handleSelectIoTDevice = (tag: string) => {
    for (const s of iotStore.stations) {
      const d = s.devices.find((item) => item.tag === tag);
      if (d) {
        iotStore.setSelectedDevice(d);
        iotStore.setSelectedInspectorType(d.type_code === 'FIT' ? 'meter' : 'device');
        return;
      }
    }
  };

  const handleSelectIoTDivision = (divName: string) => {
    const div = iotStore.divisions.find((d) => d.division_name === divName);
    if (div) {
      iotStore.setSelectedDivision(div);
      iotStore.setSelectedInspectorType('division');
    }
  };

  const handleSelectIoTAlert = (alert: any) => {
    if (alert.coordinates) {
      setFlyToTarget(alert.coordinates);
      setIotCentreView('map');
    }
  };

  return (
    <IoTStreamProvider>
      <div className="h-screen w-screen overflow-hidden grid grid-rows-[56px_1fr] bg-slate-100 dark:bg-slate-950 text-slate-900 dark:text-slate-100 font-sans antialiased">
      {/* 1. Top Bar 56px */}
      <TopBar
        alertsCount={alertsList.length}
        criticalAlertsCount={criticalCount}
        waterLossKld={waterLossKld}
        runningPumps={runningPumps}
        totalPumps={totalPumps}
        energyMwh={energyMwh}
        energyCostLakhs={energyCostLakhs}
        onOpenAlerts={() => setLeftRailTab('alerts')}
        activeModule={activeModule}
        onModuleChange={handleModuleChange}
      />

      {/* 2. Main Workstation Area: Single persistent map with dynamic GIS/IoT sidebars */}
      <div className="h-full w-full overflow-hidden relative flex">
        {/* Left Rail (300px) */}
        {activeModule === 'GIS' ? (
          <LeftRail
            alerts={alertsList}
            onFlyToAlert={handleFlyToAlert}
            onGoToShortcut={handleGoToShortcut}
          />
        ) : (
          <IoTLeftRail
            stations={iotStore.stations}
            divisions={iotStore.divisions}
            alerts={iotStore.alerts}
            selectedId={iotStore.selectedPump?.pump_id || iotStore.selectedDevice?.tag || iotStore.selectedDivision?.division_name || null}
            onSelectStation={(stn) => {
              iotStore.setSelectedStation(stn);
              if (stn.coordinates) setFlyToTarget(stn.coordinates);
            }}
            onSelectPump={handleSelectIoTPump}
            onSelectDevice={handleSelectIoTDevice}
            onSelectDivision={handleSelectIoTDivision}
            onSelectAlert={handleSelectIoTAlert}
          />
        )}

        {/* Center Main Stage */}
        <main className="flex-1 h-full relative overflow-hidden bg-slate-950 flex flex-col">
          {/* Subheader when in IoT mode */}
          {activeModule === 'IOT' && (
            <div className="h-10 px-4 border-b border-slate-800 bg-slate-900/90 flex items-center justify-between z-20 shrink-0">
              <div className="flex items-center gap-1.5 rounded-lg border border-slate-800 p-0.5 bg-slate-950 text-xs">
                <button
                  type="button"
                  onClick={() => setIotCentreView('map')}
                  className={`px-3 py-1 rounded-md font-medium transition-all flex items-center gap-1.5 ${
                    iotCentreView === 'map'
                      ? 'bg-sky-600 text-white shadow-sm font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Map className="w-3.5 h-3.5" />
                  <span>Map</span>
                </button>
                <button
                  type="button"
                  onClick={() => setIotCentreView('schematic')}
                  className={`px-3 py-1 rounded-md font-medium transition-all flex items-center gap-1.5 ${
                    iotCentreView === 'schematic'
                      ? 'bg-sky-600 text-white shadow-sm font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <GitCommit className="w-3.5 h-3.5" />
                  <span>Station schematic</span>
                </button>
                <button
                  type="button"
                  onClick={() => setIotCentreView('sankey')}
                  className={`px-3 py-1 rounded-md font-medium transition-all flex items-center gap-1.5 ${
                    iotCentreView === 'sankey'
                      ? 'bg-sky-600 text-white shadow-sm font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Waves className="w-3.5 h-3.5" />
                  <span>Water flow (MLD)</span>
                </button>
              </div>

              <div className="flex items-center gap-2">
                {iotCentreView === 'schematic' && iotStore.stations.length > 0 && (
                  <select
                    value={iotStore.selectedStation?.id || ''}
                    onChange={(e) => {
                      const found = iotStore.stations.find((s) => s.id === e.target.value);
                      if (found) iotStore.setSelectedStation(found);
                    }}
                    className="h-7 px-2.5 rounded bg-slate-800 border border-slate-700 text-xs font-mono text-slate-200"
                  >
                    {iotStore.stations.map((s) => (
                      <option key={s.id} value={s.id}>
                        {s.name}
                      </option>
                    ))}
                  </select>
                )}

                <button
                  type="button"
                  onClick={() => iotStore.setIsSimulateOpen(true)}
                  className="h-7 px-3 rounded text-xs font-semibold flex items-center gap-1.5 bg-purple-600 hover:bg-purple-500 text-white transition-colors shadow-sm"
                >
                  <Play className="w-3 h-3 fill-current" />
                  <span>Simulate IoT</span>
                </button>
              </div>
            </div>
          )}

          {/* Central Stage Display: Map and Schematic/Sankey Overlays */}
          <div className="flex-1 w-full h-full relative overflow-hidden">
            {/* The Persistent Map: Never recreated on route switch */}
            <div className={`w-full h-full ${activeModule === 'IOT' && iotCentreView !== 'map' ? 'invisible pointer-events-none' : 'visible'}`}>
              <DigitalTwinMap
                activeModule={activeModule}
                selectedAsset={selectedAsset}
                onSelectAsset={(asset) => {
                  setSelectedAsset(asset);
                }}
                activeScenario={activeScenario}
                currentHour={12}
                isDarkTheme={theme === 'dark' || theme === 'satellite'}
                activeLeakPipeId={activeLeakPipeId || undefined}
                flyToTarget={flyToTarget}
              />
            </div>

            {/* Schematic Overlay */}
            {activeModule === 'IOT' && iotCentreView === 'schematic' && iotStore.selectedStation && (
              <div className="absolute inset-0 bg-slate-950 z-10 overflow-auto">
                <StationSchematic
                  station={iotStore.selectedStation}
                  onSelectElement={(type, id) => {
                    if (type === 'pump') handleSelectIoTPump(id);
                    else if (type === 'meter' || type === 'flow_sensor') handleSelectIoTDevice(id);
                  }}
                  selectedElementId={iotStore.selectedPump?.pump_id || iotStore.selectedDevice?.tag}
                />
              </div>
            )}

            {/* Sankey Flow Overlay */}
            {activeModule === 'IOT' && iotCentreView === 'sankey' && (
              <div className="absolute inset-0 bg-slate-950 z-10 overflow-auto">
                <WaterFlowSankey
                  corridors={iotStore.corridors}
                  balance={iotStore.waterBalance || {
                    total_inflow_mld: 2250.0,
                    total_outflow_mld: 1845.0,
                    storage_change_mld: 12.0,
                    unaccounted_mld: 393.0,
                    unaccounted_pct: 17.5,
                    balanced: true,
                    data_tier: 'SIMULATED'
                  }}
                />
              </div>
            )}
          </div>
        </main>

        {/* Right Inspector (380px) */}
        {activeModule === 'GIS' ? (
          <RightInspector
            asset={selectedAsset}
            onClose={() => setSelectedAsset(null)}
            onZoomTo={(coords) => setFlyToTarget(coords)}
            allAlerts={alertsList}
            isFeedFresh={isFeedFresh}
            liveVoltageV={liveVoltageV}
            liveCurrentA={liveCurrentA}
          />
        ) : (
          <IoTRightInspector
            selectedType={iotStore.selectedInspectorType}
            selectedPump={iotStore.selectedPump}
            selectedDevice={iotStore.selectedDevice}
            selectedDivision={iotStore.selectedDivision}
            onClose={() => iotStore.setSelectedInspectorType(null)}
            onZoomTo={(coords) => setFlyToTarget(coords)}
          />
        )}
      </div>

      {/* 3. Simulate Popover Modal */}
      {isSimulateOpen && (
        <SimulatePopover
          onClose={() => setIsSimulateOpen(false)}
          onScenarioApplied={(scenario) => {
            setActiveScenario(scenario);
            refetchAlerts();
          }}
        />
      )}

      {iotStore.isSimulateOpen && (
        <IoTSimulateModal
          onClose={() => iotStore.setIsSimulateOpen(false)}
          onRefresh={() => {}}
        />
      )}

      {/* 4. IoT Alert Toasts */}
      <IoTAlertToasts
        alerts={iotStore.alerts}
        onZoomTo={(coords) => {
          setFlyToTarget(coords);
          setIotCentreView('map');
        }}
        onAcknowledge={(id) => {
          iotStore.acknowledgeAlertLocally(id);
          iotApi.acknowledgeAlert(id).catch(console.error);
        }}
        onSnooze={(id) => {
          iotStore.snoozeAlertLocally(id);
          iotApi.snoozeAlert(id).catch(console.error);
        }}
      />

      {/* 5. Admin Drawer */}
      <AdminDrawer
        isOpen={isAdminDrawerOpen}
        onClose={() => setIsAdminDrawerOpen(false)}
      />
      </div>
    </IoTStreamProvider>
  );
};

export default App;
