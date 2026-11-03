import React, { useEffect, useState } from 'react';
import { TopBar } from './components/topbar/TopBar';
import { LeftRail } from './components/panels/LeftRail';
import { DigitalTwinMap } from './components/map/DigitalTwinMap';
import { RightInspector } from './components/panels/RightInspector';
import { SimulatePopover } from './components/panels/SimulatePopover';
import { AdminDrawer } from './components/panels/AdminDrawer';
import { useTwinStore } from './store/useTwinStore';
import { sseManager } from './services/sseManager';
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
import { IoTLeakDetectionPopup } from './features/iot/components/IoTLeakDetectionPopup';
import { SupplyPlanPanel } from './features/iot/components/SupplyPlanPanel';
import { MonitorPanel } from './features/iot/components/MonitorPanel';
import { useIoTStore } from './features/iot/store/useIoTStore';
import { demoApi, DemoStatus } from './features/iot/services/demoApi';
import { ErrorBoundary } from './components/common/ErrorBoundary';
import { Map, GitCommit, Waves, Play, Calendar, ShieldAlert, RotateCcw } from 'lucide-react';

export const WARD_LEAK_LOCATIONS: Record<string, { coords: [number, number]; landmark: string }> = {
  Basavanagudi: { coords: [77.5380, 12.9050], landmark: 'Pipeline Road Chainage 6+400, Basavanagudi' },
  Hanumanthanagar: { coords: [77.5580, 12.9400], landmark: '50 Feet Main Road Chainage 4+200, Hanumanthanagar' },
  Chamarajpet: { coords: [77.5620, 12.9600], landmark: 'Bull Temple Road Chainage 7+800, Chamarajpet' },
  Padmanabhanagar: { coords: [77.5550, 12.9180], landmark: 'Kanakapura Link Chainage 3+100, Padmanabhanagar' },
};

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

  // Leak Response Demo state
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
      // 1. Redirect to map view immediately
      setIotCentreView('map');
      // 2. Zoom in where the leak is happening
      const loc = WARD_LEAK_LOCATIONS[ward] || WARD_LEAK_LOCATIONS['Basavanagudi'];
      setFlyToTarget(loc.coords);
      // 3. Start demo for selected ward
      await demoApi.startDemo(ward);
      const st = await demoApi.getStatus();
      setDemoStatus(st);
    } catch (e) {
      console.error('Failed to start leak demo:', e);
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
      console.error('Failed to reset leak demo:', e);
    }
  };

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

  const {
    kpis,
    setKpis,
    alerts: storeAlerts,
    setAlerts,
  } = useTwinStore();

  const criticalCount = storeAlerts.filter((a) => a.severity === 'CRITICAL').length;

  // Single SSE stream integration and snapshot hydration
  useEffect(() => {
    let isMounted = true;
    sseManager.retain();

    // 1. Initial snapshot hydration for KPIs & Alerts
    iotApi.getSnapshot().then((snapshot) => {
      if (!isMounted || !snapshot) return;
      if (snapshot.kpis) {
        setKpis(snapshot.kpis);
      }
      if (snapshot.alerts && Array.isArray(snapshot.alerts)) {
        setAlerts(mergeIoTAlertsWithTwinAlerts([], snapshot.alerts));
      }
    }).catch(() => {
      // Snapshot retried in IoTStreamProvider
    });

    // 2. SSE Subscriptions
    const unsubConn = sseManager.subscribe('connection', (c) => {
      if (!isMounted) return;
      setIsFeedFresh(c.isLive);
    });

    const unsubTelemetry = sseManager.subscribe('telemetry', (data) => {
      if (!isMounted || !data) return;
      if (typeof data.voltage_v === 'number') {
        setLiveVoltageV(data.voltage_v);
      }
      if (typeof data.motor_current_a === 'number') {
        setLiveCurrentA(data.motor_current_a);
      }
      setKpis({
        runningPumps: data.running_pumps ?? kpis.runningPumps,
        totalPumps: data.total_pumps ?? kpis.totalPumps,
        energyMwh: data.energy_mwh ?? kpis.energyMwh,
        energyCostLakhs: data.energy_cost_lakhs ?? kpis.energyCostLakhs,
      });
    });

    const unsubAlert = sseManager.subscribe('alert', (iotAlerts) => {
      if (!isMounted || !Array.isArray(iotAlerts)) return;
      const merged = mergeIoTAlertsWithTwinAlerts([], iotAlerts);
      setAlerts(merged);
    });

    const unsubLeak = sseManager.subscribe('leak', (leaks) => {
      if (!isMounted || !Array.isArray(leaks)) return;
      const totalLoss = leaks.reduce((acc: number, l: any) => acc + (l.leak_rate_lps || 0) * 86.4, 0);
      setKpis({ waterLossKld: Math.round(totalLoss * 10) / 10 });
    });

    return () => {
      isMounted = false;
      unsubConn();
      unsubTelemetry();
      unsubAlert();
      unsubLeak();
      sseManager.release();
    };
  }, []);

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
  const [iotCentreView, setIotCentreView] = useState<'map' | 'schematic' | 'sankey' | 'plan' | 'monitor'>('map');
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
        alertsCount={storeAlerts.length}
        criticalAlertsCount={criticalCount}
        waterLossKld={kpis.waterLossKld}
        runningPumps={kpis.runningPumps}
        totalPumps={kpis.totalPumps}
        energyMwh={kpis.energyMwh}
        energyCostLakhs={kpis.energyCostLakhs}
        onOpenAlerts={() => setLeftRailTab('alerts')}
        activeModule={activeModule}
        onModuleChange={handleModuleChange}
      />

      {/* 2. Main Workstation Area: Single persistent map with dynamic GIS/IoT sidebars */}
      <div className="h-full w-full overflow-hidden relative flex">
        {/* Left Rail (300px) */}
        {activeModule === 'GIS' ? (
          <LeftRail
            alerts={storeAlerts}
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
                {iotStore.stations.length > 0 && iotStore.stations.some((s) => s.pumps && s.pumps.length > 0) && (
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
                )}
                {iotStore.corridors.length > 0 && (
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
                )}

                <button
                  type="button"
                  onClick={() => setIotCentreView('plan')}
                  className={`px-3 py-1 rounded-md font-medium transition-all flex items-center gap-1.5 ${
                    iotCentreView === 'plan'
                      ? 'bg-sky-600 text-white shadow-sm font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <Calendar className="w-3.5 h-3.5" />
                  <span>Supply plan</span>
                </button>

                <button
                  type="button"
                  onClick={() => setIotCentreView('monitor')}
                  className={`px-3 py-1 rounded-md font-medium transition-all flex items-center gap-1.5 ${
                    iotCentreView === 'monitor'
                      ? 'bg-sky-600 text-white shadow-sm font-semibold'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  <ShieldAlert className="w-3.5 h-3.5" />
                  <span>Monitor</span>
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
                activeLeakPipeId={activeLeakPipeId || (demoStatus?.state && demoStatus.state !== 'IDLE' && demoStatus.state !== 'RESTORED' ? 'CORR_TATAGUNI_MOUNT_JOY' : undefined)}
                demoStatus={demoStatus}
                flyToTarget={flyToTarget}
                onNavigateToMonitor={() => {
                  setActiveModule('IOT');
                  setIotCentreView('monitor');
                }}
              />
            </div>

            {/* Schematic Overlay */}
            {activeModule === 'IOT' && iotCentreView === 'schematic' && iotStore.selectedStation && (
              <div className="absolute inset-0 bg-slate-950 z-10 overflow-auto">
                <ErrorBoundary fallbackTitle="Station Schematic Unavailable">
                  <StationSchematic
                    station={iotStore.selectedStation}
                    onSelectElement={(type, id) => {
                      if (type === 'pump') handleSelectIoTPump(id);
                      else if (type === 'meter' || type === 'flow_sensor') handleSelectIoTDevice(id);
                    }}
                    selectedElementId={iotStore.selectedPump?.pump_id || iotStore.selectedDevice?.tag}
                  />
                </ErrorBoundary>
              </div>
            )}

            {/* Sankey Flow Overlay */}
            {activeModule === 'IOT' && iotCentreView === 'sankey' && (
              <div className="absolute inset-0 bg-slate-950 z-10 overflow-auto">
                <ErrorBoundary fallbackTitle="Water Flow Balance Unavailable">
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
                </ErrorBoundary>
              </div>
            )}

            {/* Supply Plan Overlay */}
            {activeModule === 'IOT' && iotCentreView === 'plan' && (
              <div className="absolute inset-0 bg-slate-950 z-10 overflow-auto">
                <ErrorBoundary fallbackTitle="Supply Plan Unavailable">
                  <SupplyPlanPanel />
                </ErrorBoundary>
              </div>
            )}

            {/* Monitoring Agent Overlay */}
            {activeModule === 'IOT' && iotCentreView === 'monitor' && (
              <div className="absolute inset-0 bg-slate-950 z-10 overflow-auto">
                <ErrorBoundary fallbackTitle="Monitoring Agent Panel Unavailable">
                  <MonitorPanel />
                </ErrorBoundary>
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
            allAlerts={storeAlerts}
            isFeedFresh={isFeedFresh}
            liveVoltageV={liveVoltageV}
            liveCurrentA={liveCurrentA}
          />
        ) : (
          <IoTRightInspector
            selectedType={iotStore.selectedInspectorType}
            selectedPump={iotStore.selectedPump}
            selectedStation={iotStore.selectedStation}
            selectedDevice={iotStore.selectedDevice}
            selectedDivision={iotStore.selectedDivision}
            onClose={() => iotStore.setSelectedInspectorType(null)}
            onZoomTo={(coords) => setFlyToTarget(coords)}
            onSelectPump={handleSelectIoTPump}
          />
        )}
      </div>

      {/* 3. Simulate Popover Modal */}
      {isSimulateOpen && (
        <SimulatePopover
          onClose={() => setIsSimulateOpen(false)}
          onScenarioApplied={(scenario) => {
            setActiveScenario(scenario);
            iotApi.getSnapshot().then((snap) => {
              if (snap?.alerts) setAlerts(mergeIoTAlertsWithTwinAlerts([], snap.alerts));
            }).catch(() => {});
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

      {/* 4b. Top-Centre Leak Detection Popup */}
      <IoTLeakDetectionPopup
        alerts={iotStore.alerts}
        demoStatus={demoStatus}
        onShowOnMap={(coords) => {
          setFlyToTarget(coords);
          setIotCentreView('map');
        }}
        onAcknowledge={(id) => {
          iotStore.acknowledgeAlertLocally(id);
          iotApi.acknowledgeAlert(id).catch(console.error);
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
