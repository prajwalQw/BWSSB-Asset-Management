import React from 'react';
import { 
  Droplet, 
  AlertTriangle, 
  Activity, 
  Zap, 
  IndianRupee, 
  Settings, 
  Play, 
  Sun, 
  Moon, 
  Globe2, 
  Radio 
} from 'lucide-react';
import { useTwinStore, BasemapTheme } from '../../store/useTwinStore';

export interface TopBarProps {
  alertsCount: number;
  criticalAlertsCount: number;
  waterLossKld: number;
  runningPumps: number;
  totalPumps: number;
  energyMwh: number;
  energyCostLakhs: number;
  onOpenAlerts: () => void;
  activeModule?: 'GIS' | 'IOT';
  onModuleChange?: (module: 'GIS' | 'IOT') => void;
}

export const TopBar: React.FC<TopBarProps> = ({
  alertsCount,
  criticalAlertsCount,
  waterLossKld,
  runningPumps,
  totalPumps,
  energyMwh,
  energyCostLakhs,
  onOpenAlerts,
  activeModule = 'GIS',
  onModuleChange,
}) => {
  const {
    theme,
    setTheme,
    isFeedFresh,
    isAdminDrawerOpen,
    setIsAdminDrawerOpen,
    isSimulateOpen,
    setIsSimulateOpen,
  } = useTwinStore();

  return (
    <header className="h-14 px-4 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex items-center justify-between select-none z-30">
      {/* Brand Title */}
      <div className="flex items-center gap-2.5 min-w-[240px]">
        <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-600 dark:text-sky-400">
          <Droplet className="w-5 h-5 fill-current" />
        </div>
        <div className="flex flex-col">
          <h1 className="text-sm font-semibold tracking-tight text-slate-900 dark:text-slate-100 leading-tight">
            Bengaluru Water Digital Twin
          </h1>
          <span className="text-[11px] text-slate-500 font-normal">
            BWSSB Hydraulic & Asset Management
          </span>
        </div>
      </div>

      {/* "GIS | IoT" Switch */}
      {onModuleChange && (
        <div className="flex items-center rounded-lg border border-slate-200 dark:border-slate-700 p-0.5 bg-slate-100 dark:bg-slate-800 text-xs">
          <button
            type="button"
            onClick={() => onModuleChange('GIS')}
            className={`px-2.5 py-1 rounded-md font-medium transition-all ${
              activeModule === 'GIS'
                ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm font-bold'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            GIS
          </button>
          <button
            type="button"
            onClick={() => onModuleChange('IOT')}
            className={`px-2.5 py-1 rounded-md font-medium transition-all flex items-center gap-1.5 ${
              activeModule === 'IOT'
                ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm font-bold'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            <span>IoT</span>
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" />
          </button>
        </div>
      )}

      {/* 4 KPI Tiles */}
      <div className="hidden lg:flex items-center gap-2">
        {/* KPI 1: Active Alerts with Critical count */}
        <button
          type="button"
          onClick={onOpenAlerts}
          className={`h-9 px-3 rounded-lg border text-xs font-medium flex items-center gap-2 transition-colors ${
            criticalAlertsCount > 0
              ? 'bg-rose-50 dark:bg-rose-950/40 border-rose-300 dark:border-rose-900 text-rose-700 dark:text-rose-300'
              : 'bg-slate-50 dark:bg-slate-800/60 border-slate-200 dark:border-slate-700/60 text-slate-700 dark:text-slate-300'
          }`}
          title="View active operational alerts"
        >
          <AlertTriangle className={`w-3.5 h-3.5 ${criticalAlertsCount > 0 ? 'text-rose-500' : 'text-amber-500'}`} />
          <span className="font-mono tabular-nums font-semibold">
            {alertsCount} Alerts
          </span>
          {criticalAlertsCount > 0 && (
            <span className="text-[11px] font-semibold text-rose-600 dark:text-rose-400">
              ({criticalAlertsCount} Critical)
            </span>
          )}
        </button>

        {/* KPI 2: Estimated Water Loss Today (kL/d) */}
        <div className="h-9 px-3 rounded-lg border border-slate-200 dark:border-slate-700/60 bg-slate-50 dark:bg-slate-800/60 flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300">
          <Activity className="w-3.5 h-3.5 text-sky-500" />
          <span className="text-slate-500">Loss Today:</span>
          <span className="font-mono tabular-nums font-semibold">
            {waterLossKld.toFixed(1)} kL/d
          </span>
        </div>

        {/* KPI 3: Pumps Running x/y */}
        <div className="h-9 px-3 rounded-lg border border-slate-200 dark:border-slate-700/60 bg-slate-50 dark:bg-slate-800/60 flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300">
          <Zap className="w-3.5 h-3.5 text-emerald-500" />
          <span className="text-slate-500">Pumps:</span>
          <span className="font-mono tabular-nums font-semibold">
            {runningPumps}/{totalPumps} Running
          </span>
        </div>

        {/* KPI 4: Energy Today in MWh and Cost */}
        <div className="h-9 px-3 rounded-lg border border-slate-200 dark:border-slate-700/60 bg-slate-50 dark:bg-slate-800/60 flex items-center gap-2 text-xs text-slate-700 dark:text-slate-300">
          <IndianRupee className="w-3.5 h-3.5 text-amber-500" />
          <span className="text-slate-500">Energy:</span>
          <span className="font-mono tabular-nums font-semibold">
            {energyMwh.toFixed(1)} MWh (₹{energyCostLakhs.toFixed(2)}L)
          </span>
        </div>
      </div>

      {/* Right Controls: Basemap, Feed Chip, Simulate Button, Admin Gear */}
      <div className="flex items-center gap-2.5">
        {/* Basemap Switch: Light | Dark | Satellite */}
        <div className="flex items-center rounded-lg border border-slate-200 dark:border-slate-700 p-0.5 bg-slate-100 dark:bg-slate-800 text-xs">
          <button
            type="button"
            onClick={() => setTheme('light')}
            className={`px-2 py-1 rounded-md font-medium transition-all flex items-center gap-1 ${
              theme === 'light'
                ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            <Sun className="w-3 h-3" />
            <span className="hidden sm:inline">Light</span>
          </button>
          <button
            type="button"
            onClick={() => setTheme('dark')}
            className={`px-2 py-1 rounded-md font-medium transition-all flex items-center gap-1 ${
              theme === 'dark'
                ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            <Moon className="w-3 h-3" />
            <span className="hidden sm:inline">Dark</span>
          </button>
          <button
            type="button"
            onClick={() => setTheme('satellite')}
            className={`px-2 py-1 rounded-md font-medium transition-all flex items-center gap-1 ${
              theme === 'satellite'
                ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            <Globe2 className="w-3 h-3" />
            <span className="hidden sm:inline">Satellite</span>
          </button>
        </div>

        {/* Single Feed Status Chip (Live / Offline) */}
        <div
          className={`h-8 px-2.5 rounded-lg border text-xs font-medium flex items-center gap-1.5 transition-colors ${
            isFeedFresh
              ? 'bg-emerald-50 dark:bg-emerald-950/40 border-emerald-300 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300'
              : 'bg-slate-100 dark:bg-slate-800 border-slate-300 dark:border-slate-700 text-slate-500'
          }`}
          title={isFeedFresh ? 'IGNOAPI Live telemetry stream fresh (<= 3.0s)' : 'Telemetry stream offline'}
        >
          <Radio className={`w-3.5 h-3.5 ${isFeedFresh ? 'text-emerald-500 animate-pulse' : 'text-slate-400'}`} />
          <span>{isFeedFresh ? 'Live' : 'Offline'}</span>
        </div>

        {/* "Simulate" Button (triggers Popover) */}
        <button
          type="button"
          onClick={() => setIsSimulateOpen(!isSimulateOpen)}
          className={`h-8 px-3 rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm ${
            isSimulateOpen
              ? 'bg-purple-600 text-white'
              : 'bg-purple-50 dark:bg-purple-950/40 border border-purple-300 dark:border-purple-800 text-purple-700 dark:text-purple-300 hover:bg-purple-100 dark:hover:bg-purple-900/50'
          }`}
        >
          <Play className="w-3 h-3 fill-current" />
          <span>Simulate</span>
        </button>

        {/* Admin Gear Button (triggers slide-over drawer) */}
        <button
          type="button"
          onClick={() => setIsAdminDrawerOpen(!isAdminDrawerOpen)}
          className={`h-8 w-8 rounded-lg border flex items-center justify-center transition-colors ${
            isAdminDrawerOpen
              ? 'bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 border-transparent'
              : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-400 hover:bg-slate-100 dark:hover:bg-slate-800'
          }`}
          title="Open Admin configuration drawer"
        >
          <Settings className="w-4 h-4" />
        </button>
      </div>
    </header>
  );
};
