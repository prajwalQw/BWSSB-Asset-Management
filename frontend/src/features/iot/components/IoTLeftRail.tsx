import React, { useState } from 'react';
import {
  Search,
  SlidersHorizontal,
  ChevronRight,
  ChevronDown,
  Activity,
  AlertTriangle,
  Zap,
  Gauge,
  Radio,
  Layers,
  Building,
  CheckCircle2,
  X
} from 'lucide-react';
import { StationOverview, IoTAlertItem, DivisionBoardSummary } from '../types';

export interface IoTLeftRailProps {
  stations: StationOverview[];
  divisions: DivisionBoardSummary[];
  alerts: IoTAlertItem[];
  selectedId: string | null;
  onSelectStation: (stn: StationOverview) => void;
  onSelectPump: (pumpId: string) => void;
  onSelectDevice: (tag: string) => void;
  onSelectDivision: (divName: string) => void;
  onSelectAlert: (alert: IoTAlertItem) => void;
}

export const IoTLeftRail: React.FC<IoTLeftRailProps> = ({
  stations,
  divisions,
  alerts,
  selectedId,
  onSelectStation,
  onSelectPump,
  onSelectDevice,
  onSelectDivision,
  onSelectAlert,
}) => {
  const [activeTab, setActiveTab] = useState<'devices' | 'alerts'>('devices');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedStations, setExpandedStations] = useState<Record<string, boolean>>({
    PS_TATAGUNI: true,
  });
  const [expandedDivisions, setExpandedDivisions] = useState<Record<string, boolean>>({
    'South Division': false,
  });

  const toggleStation = (id: string) => {
    setExpandedStations((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const toggleDivision = (name: string) => {
    setExpandedDivisions((prev) => ({ ...prev, [name]: !prev[name] }));
  };

  // Filter alerts by search query
  const filteredAlerts = alerts.filter(
    (a) =>
      a.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
      a.location.toLowerCase().includes(searchQuery.toLowerCase())
  );

  return (
    <aside className="w-[300px] border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 text-xs">
      {/* 1. Header Tabs: Devices | Alerts */}
      <div className="flex border-b border-slate-200 dark:border-slate-800 p-1 bg-slate-100 dark:bg-slate-950">
        <button
          type="button"
          onClick={() => setActiveTab('devices')}
          className={`flex-1 py-1.5 rounded-md font-medium transition-all flex items-center justify-center gap-1.5 ${
            activeTab === 'devices'
              ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 shadow-sm font-semibold'
              : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
          }`}
        >
          <Layers className="w-3.5 h-3.5" />
          <span>Devices</span>
          <span className="text-[10px] font-mono px-1 rounded bg-slate-200 dark:bg-slate-700 text-slate-600 dark:text-slate-300">
            {stations.reduce((acc, s) => acc + s.pumps.length + s.devices.length, 0)}
          </span>
        </button>

        <button
          type="button"
          onClick={() => setActiveTab('alerts')}
          className={`flex-1 py-1.5 rounded-md font-medium transition-all flex items-center justify-center gap-1.5 ${
            activeTab === 'alerts'
              ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 shadow-sm font-semibold'
              : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
          }`}
        >
          <AlertTriangle className={`w-3.5 h-3.5 ${alerts.length > 0 ? 'text-rose-500' : 'text-slate-400'}`} />
          <span>Alerts</span>
          {alerts.length > 0 && (
            <span className="text-[10px] font-mono px-1 rounded bg-rose-100 dark:bg-rose-950 text-rose-700 dark:text-rose-300 font-bold">
              {alerts.length}
            </span>
          )}
        </button>
      </div>

      {/* 2. Search & Filter Bar */}
      <div className="p-2.5 border-b border-slate-200 dark:border-slate-800">
        <div className="relative">
          <Search className="w-3.5 h-3.5 absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400" />
          <input
            type="text"
            placeholder={activeTab === 'devices' ? 'Search stations, pumps, meters...' : 'Search alerts...'}
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-full pl-8 pr-3 py-1.5 rounded-md bg-slate-50 dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700 text-xs text-slate-900 dark:text-slate-100 placeholder-slate-400 focus:outline-none focus:ring-1 focus:ring-sky-500"
          />
          {searchQuery && (
            <button
              type="button"
              onClick={() => setSearchQuery('')}
              className="absolute right-2.5 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-600"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* 3. Content Scroll Area */}
      <div className="flex-1 overflow-y-auto p-2 space-y-3">
        {activeTab === 'devices' ? (
          <>
            {/* Pumping Stations Tree */}
            <div>
              <div className="px-1.5 py-1 text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider">
                Pumping Stations & Plant Assets
              </div>
              <div className="space-y-1 mt-1">
                {stations.map((stn) => {
                  const isExp = !!expandedStations[stn.id];
                  return (
                    <div key={stn.id} className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 overflow-hidden">
                      {/* Station Level */}
                      <button
                        type="button"
                        onClick={() => {
                          toggleStation(stn.id);
                          onSelectStation(stn);
                        }}
                        className="w-full px-2.5 py-2 flex items-center justify-between text-left hover:bg-slate-100 dark:hover:bg-slate-800/60 transition-colors"
                      >
                        <div className="flex items-center gap-1.5 truncate">
                          {isExp ? <ChevronDown className="w-3.5 h-3.5 text-slate-400" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-400" />}
                          <span className="font-semibold text-slate-800 dark:text-slate-200 truncate">
                            {stn.name}
                          </span>
                        </div>
                        <span className="text-[10px] font-mono px-1 rounded bg-sky-100 dark:bg-sky-950 text-sky-700 dark:text-sky-300">
                          {stn.pumps.length} Pumps
                        </span>
                      </button>

                      {/* Pumps & Devices Children */}
                      {isExp && (
                        <div className="pl-6 pr-2 pb-2 space-y-1 border-t border-slate-100 dark:border-slate-800/60 pt-1.5 text-[11px]">
                          {stn.pumps.map((p) => {
                            const isRunning = p.run_state === 'RUNNING';
                            return (
                              <button
                                key={p.pump_id}
                                type="button"
                                onClick={() => onSelectPump(p.pump_id)}
                                className={`w-full px-2 py-1.5 rounded flex items-center justify-between transition-colors ${
                                  selectedId === p.pump_id
                                    ? 'bg-sky-100 dark:bg-sky-950/70 text-sky-700 dark:text-sky-300 font-semibold'
                                    : 'hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-700 dark:text-slate-300'
                                }`}
                              >
                                <div className="flex items-center gap-1.5">
                                  <Zap className={`w-3 h-3 ${isRunning ? 'text-emerald-500' : 'text-slate-400'}`} />
                                  <span>{p.tag} Pump ({p.active_power_kw.toFixed(0)} kW)</span>
                                </div>
                                <span className={`text-[9px] font-mono font-bold ${isRunning ? 'text-emerald-600 dark:text-emerald-400' : 'text-slate-400'}`}>
                                  {p.run_state}
                                </span>
                              </button>
                            );
                          })}

                          {stn.devices.map((d) => (
                            <button
                              key={d.tag}
                              type="button"
                              onClick={() => onSelectDevice(d.tag)}
                              className={`w-full px-2 py-1 rounded flex items-center justify-between transition-colors ${
                                selectedId === d.tag
                                  ? 'bg-sky-100 dark:bg-sky-950/70 text-sky-700 dark:text-sky-300 font-semibold'
                                  : 'hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400'
                              }`}
                            >
                              <div className="flex items-center gap-1.5">
                                <Gauge className="w-3 h-3 text-slate-400" />
                                <span className="font-mono text-[10px]">{d.tag}</span>
                              </div>
                              <span className="text-[9px] text-slate-400 font-mono">
                                {d.type_code}
                              </span>
                            </button>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Smart Meter Divisions */}
            <div>
              <div className="px-1.5 py-1 text-[10px] font-mono font-bold text-slate-400 uppercase tracking-wider">
                BWSSB Divisions & Smart Meters
              </div>
              <div className="space-y-1 mt-1">
                {divisions.slice(0, 6).map((div) => {
                  const isExp = !!expandedDivisions[div.division_name];
                  return (
                    <div key={div.division_name} className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 overflow-hidden">
                      <button
                        type="button"
                        onClick={() => {
                          toggleDivision(div.division_name);
                          onSelectDivision(div.division_name);
                        }}
                        className="w-full px-2.5 py-2 flex items-center justify-between text-left hover:bg-slate-100 dark:hover:bg-slate-800/60 transition-colors"
                      >
                        <div className="flex items-center gap-1.5 truncate">
                          {isExp ? <ChevronDown className="w-3.5 h-3.5 text-slate-400" /> : <ChevronRight className="w-3.5 h-3.5 text-slate-400" />}
                          <Building className="w-3.5 h-3.5 text-sky-500" />
                          <span className="font-semibold text-slate-800 dark:text-slate-200 truncate">
                            {div.division_name}
                          </span>
                        </div>
                        <span className="text-[10px] font-mono text-slate-500">
                          {div.total_wards} Wards
                        </span>
                      </button>

                      {isExp && (
                        <div className="pl-6 pr-2 pb-2 space-y-1 border-t border-slate-100 dark:border-slate-800/60 pt-1.5 text-[11px]">
                          {div.wards.slice(0, 8).map((w) => (
                            <div key={w.ward_no} className="flex items-center justify-between py-0.5 text-slate-600 dark:text-slate-400">
                              <span className="truncate">W-{w.ward_no} {w.ward_name}</span>
                              <span className="font-mono text-[10px] tabular-nums font-medium text-slate-700 dark:text-slate-300">
                                {w.flow_lps.toFixed(1)} L/s
                              </span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          </>
        ) : (
          /* Alerts Tab */
          <div className="space-y-2">
            {filteredAlerts.length === 0 ? (
              <div className="p-4 text-center text-slate-400">
                <CheckCircle2 className="w-6 h-6 text-emerald-500 mx-auto mb-1.5" />
                <span className="text-xs">No active IoT alarms</span>
              </div>
            ) : (
              filteredAlerts.map((a) => (
                <div
                  key={a.alert_id}
                  onClick={() => onSelectAlert(a)}
                  className="p-3 rounded-lg border border-rose-200 dark:border-rose-900/60 bg-rose-50/50 dark:bg-rose-950/30 cursor-pointer hover:border-rose-300 transition-all"
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-mono font-bold px-1.5 py-0.2 rounded bg-rose-600 text-white">
                      {a.severity}
                    </span>
                    <span className="text-[10px] text-slate-400 font-mono">
                      {a.timestamp.slice(11, 19)}
                    </span>
                  </div>
                  <h4 className="font-semibold text-slate-900 dark:text-slate-100 text-xs mb-1">
                    {a.title}
                  </h4>
                  <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-snug">
                    {a.metric_observed}
                  </p>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </aside>
  );
};
