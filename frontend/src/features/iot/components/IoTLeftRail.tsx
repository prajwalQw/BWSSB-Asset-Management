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
  X,
  Eye,
  EyeOff
} from 'lucide-react';
import { StationOverview, IoTAlertItem, DivisionBoardSummary } from '../types';
import { useIoTStore, IoTLayerToggles } from '../store/useIoTStore';

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
  const [activeTab, setActiveTab] = useState<'devices' | 'alerts' | 'layers'>('devices');
  const [searchQuery, setSearchQuery] = useState('');
  const [expandedStations, setExpandedStations] = useState<Record<string, boolean>>({
    PS_TATAGUNI: true,
  });
  const [expandedDivisions, setExpandedDivisions] = useState<Record<string, boolean>>({});

  const { layerToggles, toggleLayer } = useIoTStore();

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
      {/* 1. Header Tabs: Devices | Alerts | Layers */}
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

        <button
          type="button"
          onClick={() => setActiveTab('layers')}
          className={`flex-1 py-1.5 rounded-md font-medium transition-all flex items-center justify-center gap-1.5 ${
            activeTab === 'layers'
              ? 'bg-white dark:bg-slate-800 text-slate-900 dark:text-slate-100 shadow-sm font-semibold'
              : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
          }`}
        >
          <SlidersHorizontal className="w-3.5 h-3.5" />
          <span>Layers</span>
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
                {divisions.map((div) => {
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
                        <div className="pl-6 pr-2 pb-2 space-y-1 border-t border-slate-100 dark:border-slate-800/60 pt-1.5 text-[11px] max-h-60 overflow-y-auto">
                          {div.wards.map((w) => (
                            <div key={w.ward_no} className="flex items-center justify-between py-0.5 text-slate-600 dark:text-slate-400 hover:text-slate-900 dark:hover:text-slate-200">
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
        ) : activeTab === 'alerts' ? (
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
        ) : (
          /* Layers Tab with Toggles and Legend */
          <div className="space-y-3 p-1">
            <div className="space-y-1">
              <span className="text-[10px] font-mono uppercase font-bold text-slate-400 block tracking-wider">
                Map Layer Visibility
              </span>
              <p className="text-[11px] text-slate-500">
                Toggle live IoT layers and telemetry overlays on the map stage.
              </p>
            </div>

            <div className="space-y-1.5">
              {[
                { key: 'pumpingStations' as keyof IoTLayerToggles, label: 'Pumping Stations', desc: 'Status rings, running pump counts, site plans' },
                { key: 'stps' as keyof IoTLayerToggles, label: 'Sewage Treatment Plants (STP)', desc: 'Aeration blowers, lift pumps, effluent quality' },
                { key: 'tanks' as keyof IoTLayerToggles, label: 'GLR / OHT Reservoirs', desc: 'Water levels and storage volume' },
                { key: 'wtps' as keyof IoTLayerToggles, label: 'Water Treatment Plants (WTP)', desc: 'Clarifiers, filtration beds' },
                { key: 'flowMeters' as keyof IoTLayerToggles, label: 'Flow Meters (FIT)', desc: 'Discharge & corridor totalisers' },
                { key: 'pressureSensors' as keyof IoTLayerToggles, label: 'Pressure Transmitters (PIT)', desc: 'Header pressure bar / alarms' },
                { key: 'levelSensors' as keyof IoTLayerToggles, label: 'Level Sensors (LIT)', desc: 'Sump & tank depth transmitters' },
                { key: 'qualityAnalysers' as keyof IoTLayerToggles, label: 'Quality Analysers (AIT)', desc: 'pH, turbidity, residual chlorine' },
                { key: 'borewells' as keyof IoTLayerToggles, label: 'Borewells', desc: 'Groundwater extraction points' },
                { key: 'valves' as keyof IoTLayerToggles, label: 'Control Valves', desc: 'Isolation & flow control valves' },
                { key: 'smartMeters' as keyof IoTLayerToggles, label: 'Smart Meter Boards', desc: 'Division supply centroids & NRW' },
                { key: 'mldCorridors' as keyof IoTLayerToggles, label: 'MLD Corridors', desc: 'Animated bulk transmission flow' },
                { key: 'gisPipes' as keyof IoTLayerToggles, label: 'GIS Pipes Context', desc: 'Dimmed background network (35% opacity)' },
              ].map(({ key, label, desc }) => {
                const isEnabled = layerToggles[key];
                return (
                  <button
                    key={key}
                    type="button"
                    onClick={() => toggleLayer(key)}
                    className={`w-full p-2.5 rounded-lg border text-left flex items-start justify-between gap-2 transition-all ${
                      isEnabled
                        ? 'border-sky-500/50 bg-sky-50/50 dark:bg-sky-950/30 text-slate-800 dark:text-slate-100'
                        : 'border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 text-slate-400 opacity-60'
                    }`}
                  >
                    <div className="flex-1 min-w-0">
                      <div className="font-semibold text-xs flex items-center gap-1.5">
                        <span>{label}</span>
                      </div>
                      <span className="text-[10px] text-slate-500 dark:text-slate-400 leading-tight block mt-0.5">
                        {desc}
                      </span>
                    </div>
                    <div className="mt-0.5">
                      {isEnabled ? (
                        <Eye className="w-4 h-4 text-sky-500 shrink-0" />
                      ) : (
                        <EyeOff className="w-4 h-4 text-slate-400 shrink-0" />
                      )}
                    </div>
                  </button>
                );
              })}
            </div>

            {/* Symbology Legend Reference */}
            <div className="pt-3 border-t border-slate-200 dark:border-slate-800 space-y-2">
              <span className="text-[10px] font-mono uppercase font-bold text-slate-400 block tracking-wider">
                Symbology Legend
              </span>
              <div className="space-y-1.5 text-[11px] font-mono text-slate-600 dark:text-slate-300">
                <div className="flex items-center gap-2">
                  <span className="w-3.5 h-3.5 rounded-full border-2 border-emerald-500 bg-emerald-500/20 inline-block" />
                  <span>Normal Asset (Healthy / Active)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3.5 h-3.5 rounded-full border-2 border-rose-500 bg-rose-500/20 inline-block" />
                  <span>Alarm Triggered (High / Trip / Leak)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-3.5 h-3.5 rounded-full border-2 border-purple-500 bg-purple-500/20 inline-block" />
                  <span>Smart Meter Board Centroid</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-4 h-1.5 rounded bg-sky-500 inline-block" />
                  <span>MLD Bulk Corridor (Flow animated)</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-4 h-1 rounded bg-slate-500 opacity-35 inline-block" />
                  <span>GIS Pipes (Dimmed 35% context)</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </aside>
  );
};
