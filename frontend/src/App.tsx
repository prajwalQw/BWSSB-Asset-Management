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
import { IoTWorkstation } from './features/iot/IoTWorkstation';
import { iotApi } from './features/iot/services/iotApi';
import { mergeIoTAlertsWithTwinAlerts } from './features/iot/registry/alertAdapter';

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

  return (
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

      {/* 2. Main Workstation Area: GIS Workstation or IoT Workstation */}
      {activeModule === 'IOT' ? (
        <IoTWorkstation />
      ) : (
        <div className="flex h-full w-full overflow-hidden relative">
          {/* Left Rail (300px, Collapsible) */}
          <LeftRail
            alerts={alertsList}
            onFlyToAlert={handleFlyToAlert}
            onGoToShortcut={handleGoToShortcut}
          />

          {/* Center Map Stage (Full Height) */}
          <main className="flex-1 h-full relative overflow-hidden bg-slate-950">
            <DigitalTwinMap
              selectedAsset={selectedAsset}
              onSelectAsset={setSelectedAsset}
              activeScenario={activeScenario}
              currentHour={12}
              isDarkTheme={theme === 'dark' || theme === 'satellite'}
              activeLeakPipeId={activeLeakPipeId || undefined}
              flyToTarget={flyToTarget}
            />
          </main>

          {/* Right Inspector (380px, Context-Sensitive, Never Blank) */}
          <RightInspector
            asset={selectedAsset}
            onClose={() => setSelectedAsset(null)}
            onZoomTo={(coords) => setFlyToTarget(coords)}
            allAlerts={alertsList}
            isFeedFresh={isFeedFresh}
            liveVoltageV={liveVoltageV}
            liveCurrentA={liveCurrentA}
          />
        </div>
      )}

      {/* 3. Simulate Popover (Anchored, not a separate page, NO time slider bar) */}
      {isSimulateOpen && (
        <SimulatePopover
          onClose={() => setIsSimulateOpen(false)}
          onScenarioApplied={(scenario) => {
            setActiveScenario(scenario);
            refetchAlerts();
          }}
        />
      )}

      {/* 4. Admin Drawer (Right Slide-over, 420px) */}
      <AdminDrawer
        isOpen={isAdminDrawerOpen}
        onClose={() => setIsAdminDrawerOpen(false)}
      />
    </div>
  );
};

export default App;
