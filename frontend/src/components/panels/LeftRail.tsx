import React from 'react';
import { 
  AlertTriangle, 
  Layers, 
  ChevronLeft, 
  ChevronRight, 
  Compass, 
  MapPin, 
  Sliders, 
  Info,
  Clock
} from 'lucide-react';
import { useTwinStore } from '../../store/useTwinStore';
import { AlertItem } from '../../types';

export interface LeftRailProps {
  alerts: AlertItem[];
  onFlyToAlert: (alert: AlertItem) => void;
  onGoToShortcut: (target: [number, number], zoom: number) => void;
}

const SHORTCUTS = [
  { name: 'City View', center: [77.5946, 12.9716] as [number, number], zoom: 11.2 },
  { name: 'Tataguni Corridor', center: [77.5255, 12.8715] as [number, number], zoom: 14.5 },
  { name: 'Jayanagar DMA', center: [77.5855, 12.9285] as [number, number], zoom: 15.0 },
  { name: 'Tataguni Site Plan', center: [77.5140, 12.8685] as [number, number], zoom: 17.8 },
  { name: 'TK Halli WTP Site', center: [77.1650, 12.3320] as [number, number], zoom: 16.5 },
];

export const LeftRail: React.FC<LeftRailProps> = ({
  alerts,
  onFlyToAlert,
  onGoToShortcut,
}) => {
  const {
    isLeftRailOpen,
    toggleLeftRail,
    leftRailTab,
    setLeftRailTab,
    layers,
    setLayerVisibility,
    setLayerOpacity,
    isLegendOpen,
    setIsLegendOpen,
  } = useTwinStore();

  if (!isLeftRailOpen) {
    return (
      <div className="w-10 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col items-center py-3 select-none z-20">
        <button
          type="button"
          onClick={toggleLeftRail}
          className="p-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-500 mb-4"
          title="Expand Left Rail"
        >
          <ChevronRight className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => {
            setLeftRailTab('alerts');
            toggleLeftRail();
          }}
          className={`p-2 rounded-md mb-2 ${leftRailTab === 'alerts' ? 'text-rose-500 bg-rose-50 dark:bg-rose-950/40' : 'text-slate-500'}`}
          title="Alerts Tab"
        >
          <AlertTriangle className="w-4 h-4" />
        </button>
        <button
          type="button"
          onClick={() => {
            setLeftRailTab('layers');
            toggleLeftRail();
          }}
          className={`p-2 rounded-md ${leftRailTab === 'layers' ? 'text-sky-500 bg-sky-50 dark:bg-sky-950/40' : 'text-slate-500'}`}
          title="Layers Tab"
        >
          <Layers className="w-4 h-4" />
        </button>
      </div>
    );
  }

  return (
    <aside className="w-[300px] border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 overflow-hidden">
      {/* Header with Tabs & Collapse Button */}
      <div className="h-11 px-3 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <button
            type="button"
            onClick={() => setLeftRailTab('alerts')}
            className={`px-3 py-1 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-colors ${
              leftRailTab === 'alerts'
                ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            <AlertTriangle className="w-3.5 h-3.5 text-rose-500" />
            <span>Alerts</span>
            <span className="ml-1 text-[10px] px-1.5 py-0.2 rounded-full bg-slate-200 dark:bg-slate-700 font-mono">
              {alerts.length}
            </span>
          </button>
          <button
            type="button"
            onClick={() => setLeftRailTab('layers')}
            className={`px-3 py-1 rounded-md text-xs font-semibold flex items-center gap-1.5 transition-colors ${
              leftRailTab === 'layers'
                ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100'
                : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
            }`}
          >
            <Layers className="w-3.5 h-3.5 text-sky-500" />
            <span>Layers</span>
          </button>
        </div>

        <button
          type="button"
          onClick={toggleLeftRail}
          className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
          title="Collapse rail"
        >
          <ChevronLeft className="w-4 h-4" />
        </button>
      </div>

      {/* Content Area */}
      <div className="flex-1 overflow-y-auto p-3 text-xs">
        {leftRailTab === 'alerts' ? (
          <div className="flex flex-col gap-2">
            {alerts.length === 0 ? (
              <div className="p-6 text-center text-slate-400">
                <AlertTriangle className="w-8 h-8 mx-auto mb-2 opacity-30 text-emerald-500" />
                <p className="font-medium text-slate-700 dark:text-slate-300">All clear</p>
                <p className="text-[11px] mt-0.5">No active alerts detected</p>
              </div>
            ) : (
              alerts.map((alert) => {
                const isCrit = alert.severity === 'CRITICAL';
                const isHigh = alert.severity === 'HIGH';
                const colorBorder = isCrit
                  ? 'border-l-rose-500'
                  : isHigh
                  ? 'border-l-amber-500'
                  : 'border-l-sky-500';

                return (
                  <div
                    key={alert.alert_id}
                    onClick={() => onFlyToAlert(alert)}
                    className={`p-2.5 rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 hover:border-slate-300 dark:hover:border-slate-700 cursor-pointer transition-all border-l-4 ${colorBorder}`}
                  >
                    <div className="flex items-center justify-between mb-1">
                      <span className={`text-[10px] font-bold uppercase tracking-wider ${
                        isCrit ? 'text-rose-600 dark:text-rose-400' : isHigh ? 'text-amber-600 dark:text-amber-400' : 'text-sky-600 dark:text-sky-400'
                      }`}>
                        {alert.severity}
                      </span>
                      <span className="text-[10px] text-slate-400 flex items-center gap-1 font-mono">
                        <Clock className="w-2.5 h-2.5" />
                        {alert.timestamp ? alert.timestamp.split('T')[1]?.slice(0, 5) || '12:00' : '12:00'}
                      </span>
                    </div>

                    <h4 className="font-semibold text-slate-900 dark:text-slate-100 text-[12px] leading-snug line-clamp-2 mb-1">
                      {alert.title}
                    </h4>

                    <div className="flex items-center gap-1 text-[11px] text-slate-500 dark:text-slate-400">
                      <MapPin className="w-3 h-3 shrink-0 text-slate-400" />
                      <span className="truncate">{alert.location}</span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        ) : (
          <div className="flex flex-col gap-4">
            {/* Quick Navigation Shortcuts */}
            <div>
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-2">
                Quick Shortcuts
              </span>
              <div className="grid grid-cols-1 gap-1">
                {SHORTCUTS.map((sc) => (
                  <button
                    key={sc.name}
                    type="button"
                    onClick={() => onGoToShortcut(sc.center, sc.zoom)}
                    className="w-full text-left px-2.5 py-1.5 rounded-md hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300 flex items-center justify-between transition-colors"
                  >
                    <span>{sc.name}</span>
                    <Compass className="w-3.5 h-3.5 text-slate-400" />
                  </button>
                ))}
              </div>
            </div>

            {/* Layer Toggles & Opacity Sliders */}
            <div>
              <span className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider block mb-2">
                Network Layers
              </span>
              <div className="flex flex-col gap-3">
                {[
                  { key: 'trunkMains', label: 'Trunk Mains (≥600mm)', tag: 'Transmission' },
                  { key: 'distributionMains', label: 'Distribution Mains (300-600mm)', tag: 'Network' },
                  { key: 'pumpingStations', label: 'Pumping Stations', tag: 'Assets' },
                  { key: 'stps', label: 'Sewage Treatment Plants', tag: 'Assets' },
                  { key: 'waterBodies', label: 'Lakes & Reservoirs', tag: 'Hydrology' },
                  { key: 'divisionBoundaries', label: 'Division Boundaries', tag: 'Jurisdiction' },
                ].map(({ key, label, tag }) => {
                  const setting = layers[key as keyof typeof layers];
                  return (
                    <div key={key} className="p-2 rounded-md border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
                      <div className="flex items-center justify-between mb-1.5">
                        <label className="flex items-center gap-2 cursor-pointer font-medium text-slate-800 dark:text-slate-200">
                          <input
                            type="checkbox"
                            checked={setting.visible}
                            onChange={(e) => setLayerVisibility(key as any, e.target.checked)}
                            className="rounded border-slate-300 text-sky-600 focus:ring-sky-500 w-3.5 h-3.5"
                          />
                          <span>{label}</span>
                        </label>
                        <span className="text-[10px] text-slate-400">{tag}</span>
                      </div>

                      {setting.visible && (
                        <div className="flex items-center gap-2 pt-1 pl-5">
                          <Sliders className="w-3 h-3 text-slate-400 shrink-0" />
                          <input
                            type="range"
                            min="0.1"
                            max="1"
                            step="0.05"
                            value={setting.opacity}
                            onChange={(e) => setLayerOpacity(key as any, parseFloat(e.target.value))}
                            className="w-full h-1 bg-slate-200 dark:bg-slate-700 rounded-lg appearance-none cursor-pointer accent-sky-500"
                          />
                          <span className="text-[10px] font-mono tabular-nums text-slate-400 w-7 text-right">
                            {Math.round(setting.opacity * 100)}%
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Network Legend Trigger */}
            <div className="pt-2 border-t border-slate-200 dark:border-slate-800">
              <button
                type="button"
                onClick={() => setIsLegendOpen(!isLegendOpen)}
                className="w-full px-3 py-2 rounded-md border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 flex items-center justify-between font-medium transition-colors"
              >
                <span className="flex items-center gap-2">
                  <Info className="w-4 h-4 text-sky-500" />
                  <span>P&ID Symbology Legend</span>
                </span>
                <span className="text-[10px] text-slate-400">{isLegendOpen ? 'Hide' : 'Show'}</span>
              </button>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
