import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import { Settings, Save, CheckCircle2, Sliders, X, AlertCircle, Activity, Radio, ShieldCheck, RefreshCw } from 'lucide-react';

interface AdminConfigPortalProps {
  onClose: () => void;
}

export const AdminConfigPortal: React.FC<AdminConfigPortalProps> = ({ onClose }) => {
  const [config, setConfig] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<'pumps' | 'thresholds' | 'feed_health' | 'raw'>('pumps');
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);
  const [rawJson, setRawJson] = useState('');
  const [feedHealthData, setFeedHealthData] = useState<any>(null);
  const [feedFilter, setFeedFilter] = useState<'ALL' | 'FLOW_METER' | 'PRESSURE_SENSOR' | 'PUMP_CHANNEL'>('ALL');
  const [searchTerm, setSearchTerm] = useState('');

  useEffect(() => {
    loadConfig();
    loadFeedHealth();
    const interval = setInterval(loadFeedHealth, 2000);
    return () => clearInterval(interval);
  }, []);

  const loadConfig = async () => {
    try {
      const data = await api.getNetworkRules();
      setConfig(data);
      setRawJson(JSON.stringify(data, null, 2));
    } catch (err) {
      console.error('Failed to load rules:', err);
    }
  };

  const loadFeedHealth = async () => {
    try {
      const data = await api.getFeedHealth();
      setFeedHealthData(data);
    } catch (err) {
      console.error('Failed to load feed health:', err);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    try {
      const payload = activeTab === 'raw' ? JSON.parse(rawJson) : config;
      await api.saveNetworkRules(payload);
      setSaveSuccess(true);
      setConfig(payload);
      setTimeout(() => setSaveSuccess(false), 2000);
    } catch (err) {
      console.error('Failed to save config:', err);
      alert('Error parsing or saving configuration JSON.');
    } finally {
      setIsSaving(false);
    }
  };

  if (!config) {
    return (
      <div className="absolute inset-0 z-40 bg-slate-950/80 backdrop-blur-md flex items-center justify-center text-xs text-slate-300">
        Loading Admin Configuration...
      </div>
    );
  }

  // Filtered feed health items
  const sensorsList = feedHealthData?.sensors ? Object.values(feedHealthData.sensors) as any[] : [];
  const filteredSensors = sensorsList.filter(s => {
    const matchesFilter = feedFilter === 'ALL' || s.type === feedFilter;
    const matchesSearch = !searchTerm || 
      s.sensor_id.toLowerCase().includes(searchTerm.toLowerCase()) ||
      (s.name && s.name.toLowerCase().includes(searchTerm.toLowerCase())) ||
      (s.source_variable && s.source_variable.toLowerCase().includes(searchTerm.toLowerCase()));
    return matchesFilter && matchesSearch;
  });

  return (
    <div className="absolute inset-x-8 inset-y-10 z-40 bg-slate-900 border border-slate-800 rounded-3xl shadow-2xl backdrop-blur-2xl p-6 text-slate-100 flex flex-col font-sans max-w-5xl mx-auto overflow-hidden animate-in fade-in duration-200">
      {/* Top Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800">
        <div className="flex items-center gap-3">
          <div className="p-2.5 rounded-xl bg-cyan-950 border border-cyan-800 text-cyan-400">
            <Settings className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-lg font-bold text-slate-100">
              Admin Configuration & Dynamic Rules Portal
            </h2>
            <p className="text-xs text-slate-400">
              Rule 2 & Rule 4 Enforcement: Zero hardcoding. Read-only IGNOAPI bridge mapping, tolerances & feed health.
            </p>
          </div>
        </div>

        <div className="flex items-center gap-3">
          {saveSuccess && (
            <span className="text-xs text-emerald-400 flex items-center gap-1 font-mono">
              <CheckCircle2 className="w-4 h-4" /> Changes Applied Live
            </span>
          )}
          {activeTab !== 'feed_health' && (
            <button
              onClick={handleSave}
              disabled={isSaving}
              className="px-4 py-2 bg-cyan-600 hover:bg-cyan-500 text-white text-xs font-semibold rounded-xl flex items-center gap-2 shadow-lg transition-all"
            >
              <Save className="w-4 h-4" />
              <span>{isSaving ? 'Saving...' : 'Save & Hot-Reload'}</span>
            </button>
          )}
          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white rounded-lg hover:bg-slate-800"
          >
            <X className="w-5 h-5" />
          </button>
        </div>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-2 pt-4 pb-2 border-b border-slate-800 text-xs">
        <button
          onClick={() => setActiveTab('pumps')}
          className={`px-3 py-1.5 font-medium rounded-lg transition-colors ${
            activeTab === 'pumps'
              ? 'bg-cyan-950 text-cyan-300 border border-cyan-800'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Pump Rating Curves
        </button>
        <button
          onClick={() => setActiveTab('thresholds')}
          className={`px-3 py-1.5 font-medium rounded-lg transition-colors ${
            activeTab === 'thresholds'
              ? 'bg-cyan-950 text-cyan-300 border border-cyan-800'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Pressure & Leak Tolerances
        </button>
        <button
          onClick={() => setActiveTab('feed_health')}
          className={`px-3 py-1.5 font-medium rounded-lg transition-colors flex items-center gap-1.5 ${
            activeTab === 'feed_health'
              ? 'bg-cyan-950 text-cyan-300 border border-cyan-800'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <Activity className="w-3.5 h-3.5 text-cyan-400" />
          <span>IGNOAPI & Sensor Feed Health</span>
          {feedHealthData?.summary?.total_sensors && (
            <span className="px-1.5 py-0.2 rounded-full bg-slate-800 text-[10px] font-mono text-cyan-300">
              {feedHealthData.summary.total_sensors}
            </span>
          )}
        </button>
        <button
          onClick={() => setActiveTab('raw')}
          className={`px-3 py-1.5 font-medium rounded-lg transition-colors ${
            activeTab === 'raw'
              ? 'bg-cyan-950 text-cyan-300 border border-cyan-800'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Raw JSON Config
        </button>
      </div>

      {/* Tab Panels */}
      <div className="flex-1 overflow-y-auto py-4 text-xs space-y-4">
        {activeTab === 'pumps' && (
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-200">
              Centrifugal Pump Specifications & Tolerance Bands
            </h3>
            <div className="grid grid-cols-2 gap-4">
              {Object.entries(config.pump_ratings || {}).map(([pumpKey, val]: [string, any]) => (
                <div key={pumpKey} className="p-4 bg-slate-950/60 border border-slate-800 rounded-2xl space-y-3">
                  <span className="font-mono font-bold text-cyan-300 text-xs block">{pumpKey}</span>
                  <div className="grid grid-cols-2 gap-2 text-[11px]">
                    <div>
                      <label className="text-slate-500 block">Rated Power (kW)</label>
                      <input
                        type="number"
                        value={val.rated_power_kw}
                        onChange={(e) => {
                          const updated = { ...config };
                          updated.pump_ratings[pumpKey].rated_power_kw = Number(e.target.value);
                          setConfig(updated);
                        }}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg p-1.5 font-mono text-slate-200"
                      />
                    </div>
                    <div>
                      <label className="text-slate-500 block">Rated Voltage (V)</label>
                      <input
                        type="number"
                        value={val.rated_voltage_v}
                        onChange={(e) => {
                          const updated = { ...config };
                          updated.pump_ratings[pumpKey].rated_voltage_v = Number(e.target.value);
                          setConfig(updated);
                        }}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg p-1.5 font-mono text-slate-200"
                      />
                    </div>
                    <div>
                      <label className="text-slate-500 block">Rated Current (A)</label>
                      <input
                        type="number"
                        value={val.rated_current_a}
                        onChange={(e) => {
                          const updated = { ...config };
                          updated.pump_ratings[pumpKey].rated_current_a = Number(e.target.value);
                          setConfig(updated);
                        }}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg p-1.5 font-mono text-slate-200"
                      />
                    </div>
                    <div>
                      <label className="text-slate-500 block">Rated Speed (RPM)</label>
                      <input
                        type="number"
                        value={val.rated_speed_rpm}
                        onChange={(e) => {
                          const updated = { ...config };
                          updated.pump_ratings[pumpKey].rated_speed_rpm = Number(e.target.value);
                          setConfig(updated);
                        }}
                        className="w-full bg-slate-900 border border-slate-700 rounded-lg p-1.5 font-mono text-slate-200"
                      />
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {activeTab === 'thresholds' && (
          <div className="space-y-4">
            <h3 className="text-sm font-semibold text-slate-200">
              Operational Pressure & Hydraulic Leak Tolerances
            </h3>
            <div className="grid grid-cols-2 gap-4">
              <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-2xl space-y-3">
                <span className="font-semibold text-slate-200 block">Static Pressure Limits (bar)</span>
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="text-slate-400 block mb-1">Min Target Pressure</label>
                    <input
                      type="number"
                      step="0.1"
                      value={config.operational_thresholds?.pressure_bar?.min_target}
                      onChange={(e) => {
                        const updated = { ...config };
                        updated.operational_thresholds.pressure_bar.min_target = Number(e.target.value);
                        setConfig(updated);
                      }}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 font-mono"
                    />
                  </div>
                  <div>
                    <label className="text-slate-400 block mb-1">Max Allowable Pressure</label>
                    <input
                      type="number"
                      step="0.1"
                      value={config.operational_thresholds?.pressure_bar?.max_allowable}
                      onChange={(e) => {
                        const updated = { ...config };
                        updated.operational_thresholds.pressure_bar.max_allowable = Number(e.target.value);
                        setConfig(updated);
                      }}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 font-mono"
                    />
                  </div>
                </div>
              </div>

              <div className="p-4 bg-slate-950/60 border border-slate-800 rounded-2xl space-y-3">
                <span className="font-semibold text-slate-200 block">DMA Leak & Minimum Night Flow (MNF)</span>
                <div className="space-y-2">
                  <div>
                    <label className="text-slate-400 block mb-1">MNF Ratio Threshold (Leak Suspected)</label>
                    <input
                      type="number"
                      step="0.01"
                      value={config.operational_thresholds?.dma_leak_tolerances?.minimum_night_flow_ratio_threshold}
                      onChange={(e) => {
                        const updated = { ...config };
                        updated.operational_thresholds.dma_leak_tolerances.minimum_night_flow_ratio_threshold = Number(e.target.value);
                        setConfig(updated);
                      }}
                      className="w-full bg-slate-900 border border-slate-700 rounded-lg p-2 font-mono"
                    />
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* FEED HEALTH TAB */}
        {activeTab === 'feed_health' && (
          <div className="space-y-4">
            {/* Top KPI row */}
            <div className="grid grid-cols-4 gap-3">
              <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-2xl">
                <span className="text-[10px] text-slate-500 font-mono block">BRIDGE STATE</span>
                <div className="flex items-center gap-2 mt-1">
                  <span className={`w-2.5 h-2.5 rounded-full ${feedHealthData?.bridge_connected ? 'bg-emerald-400 animate-pulse' : 'bg-amber-400'}`} />
                  <strong className="text-xs font-mono text-slate-200">
                    {feedHealthData?.bridge_connected ? 'IGNOAPI TCP LIVE' : 'PASSIVE FILE / STANDBY'}
                  </strong>
                </div>
                <span className="text-[9px] text-slate-500 font-mono mt-0.5 block">Strict Read-Only (Port 8899)</span>
              </div>

              <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-2xl">
                <span className="text-[10px] text-slate-500 font-mono block">HEALTHY LIVE FEEDS</span>
                <strong className="text-lg font-mono text-emerald-400 mt-0.5 block">
                  {feedHealthData?.summary?.healthy_live ?? 0}
                </strong>
                <span className="text-[9px] text-slate-500 font-mono block">Active & Verified within range</span>
              </div>

              <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-2xl">
                <span className="text-[10px] text-slate-500 font-mono block">SIMULATED FALLBACKS</span>
                <strong className="text-lg font-mono text-sky-400 mt-0.5 block">
                  {feedHealthData?.summary?.simulated_fallback ?? 0}
                </strong>
                <span className="text-[9px] text-slate-500 font-mono block">Variables missing from IGNOAPI</span>
              </div>

              <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-2xl">
                <span className="text-[10px] text-slate-500 font-mono block">TOTAL SENSORS MAPPED</span>
                <strong className="text-lg font-mono text-cyan-400 mt-0.5 block">
                  {feedHealthData?.summary?.total_sensors ?? 0}
                </strong>
                <span className="text-[9px] text-slate-500 font-mono block">Flow, Pressure & Pump Channels</span>
              </div>
            </div>

            {/* Filter and search bar */}
            <div className="flex items-center justify-between gap-3 pt-2">
              <div className="flex items-center gap-1.5 bg-slate-950 p-1 rounded-xl border border-slate-800 text-[11px]">
                {(['ALL', 'FLOW_METER', 'PRESSURE_SENSOR', 'PUMP_CHANNEL'] as const).map(tab => (
                  <button
                    key={tab}
                    onClick={() => setFeedFilter(tab)}
                    className={`px-2.5 py-1 rounded-lg font-medium transition-colors ${
                      feedFilter === tab ? 'bg-cyan-950 text-cyan-300 border border-cyan-800' : 'text-slate-400 hover:text-slate-200'
                    }`}
                  >
                    {tab.replace('_', ' ')}
                  </button>
                ))}
              </div>

              <input
                type="text"
                placeholder="Search sensor ID, name, or variable..."
                value={searchTerm}
                onChange={e => setSearchTerm(e.target.value)}
                className="bg-slate-950 border border-slate-800 rounded-xl px-3 py-1.5 text-xs text-slate-200 w-64 placeholder-slate-600 focus:outline-none focus:border-cyan-600"
              />
            </div>

            {/* Sensor Feed Health Table */}
            <div className="border border-slate-800 rounded-2xl overflow-hidden bg-slate-950/60 max-h-[360px] overflow-y-auto">
              <table className="w-full text-left text-[11px] font-mono border-collapse">
                <thead className="bg-slate-900/90 text-slate-400 uppercase text-[10px] tracking-wider sticky top-0 border-b border-slate-800">
                  <tr>
                    <th className="py-2.5 px-3">Sensor ID & Name</th>
                    <th className="py-2.5 px-3">Type</th>
                    <th className="py-2.5 px-3">IGNOAPI Variable</th>
                    <th className="py-2.5 px-3">Unit</th>
                    <th className="py-2.5 px-3">Feed Health</th>
                    <th className="py-2.5 px-3">Data Tier</th>
                    <th className="py-2.5 px-3">Diagnostic Status</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {filteredSensors.map((s: any) => {
                    const isHealthy = s.feed_health === 'HEALTHY_LIVE';
                    const isStale = s.feed_health === 'STALE_LIVE';
                    const isOutOfBounds = s.feed_health === 'OUT_OF_BOUNDS';
                    const isFallback = s.feed_health === 'FALLBACK_SIMULATED';

                    return (
                      <tr key={s.sensor_id} className="hover:bg-slate-900/50 transition-colors">
                        <td className="py-2.5 px-3">
                          <strong className="text-slate-200 block text-xs">{s.sensor_id}</strong>
                          <span className="text-[10px] text-slate-500 font-sans block truncate max-w-[220px]">{s.name}</span>
                        </td>
                        <td className="py-2.5 px-3 text-slate-400 text-[10px]">
                          {s.type}
                        </td>
                        <td className="py-2.5 px-3">
                          {s.source_variable ? (
                            <span className="text-cyan-400 font-bold">{s.source_variable}</span>
                          ) : (
                            <span className="text-slate-600 italic">None (Unmapped)</span>
                          )}
                        </td>
                        <td className="py-2.5 px-3 text-slate-300">
                          {s.unit}
                        </td>
                        <td className="py-2.5 px-3">
                          <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
                            isHealthy
                              ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                              : isStale
                              ? 'bg-amber-950 text-amber-300 border border-amber-800'
                              : isOutOfBounds
                              ? 'bg-rose-950 text-rose-300 border border-rose-800'
                              : 'bg-sky-950 text-sky-300 border border-sky-800'
                          }`}>
                            {s.feed_health}
                          </span>
                        </td>
                        <td className="py-2.5 px-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                            s.data_tier === 'LIVE' ? 'bg-cyan-500 text-slate-950' : 'bg-slate-800 text-slate-300'
                          }`}>
                            {s.data_tier}
                          </span>
                        </td>
                        <td className="py-2.5 px-3 text-[10px] text-slate-400 font-sans max-w-[240px]">
                          {s.reason}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {activeTab === 'raw' && (
          <div className="h-full flex flex-col">
            <textarea
              value={rawJson}
              onChange={(e) => setRawJson(e.target.value)}
              className="w-full flex-1 bg-slate-950 font-mono text-xs text-slate-200 p-4 border border-slate-800 rounded-xl focus:outline-none focus:ring-1 focus:ring-cyan-500 min-h-[350px]"
            />
          </div>
        )}
      </div>
    </div>
  );
};
