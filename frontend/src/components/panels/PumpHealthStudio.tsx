import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import { 
  PumpStatus, 
  PumpAlert, 
  PumpStartEvent, 
  PumpTrendPoint, 
  PumpDriftForecast, 
  PumpEnergyReport 
} from '../../types';
import { 
  Zap, 
  Activity, 
  Clock, 
  AlertTriangle, 
  TrendingUp, 
  ShieldAlert, 
  Play, 
  RotateCcw, 
  CheckCircle2, 
  Info, 
  IndianRupee, 
  BarChart3, 
  Sparkles, 
  Sliders, 
  RefreshCw,
  Gauge,
  Thermometer,
  Compass,
  ArrowRight
} from 'lucide-react';
import { 
  ResponsiveContainer, 
  LineChart, 
  Line, 
  XAxis, 
  YAxis, 
  Tooltip, 
  CartesianGrid, 
  ReferenceLine, 
  AreaChart, 
  Area 
} from 'recharts';
import { ProvenanceChip } from '../common/ProvenanceChip';

interface PumpHealthStudioProps {
  onClose: () => void;
  onSelectOnMap?: (coordinates: [number, number]) => void;
}

export const PumpHealthStudio: React.FC<PumpHealthStudioProps> = ({ onClose, onSelectOnMap }) => {
  const [activeTab, setActiveTab] = useState<'trends' | 'startup' | 'energy' | 'anomalies' | 'forecast' | 'scenarios'>('trends');
  const [selectedPumpId, setSelectedPumpId] = useState<string>('PUMP_TG_01');
  
  // State
  const [monitorsData, setMonitorsData] = useState<any>(null);
  const [trendData, setTrendData] = useState<any>(null);
  const [startEvents, setStartEvents] = useState<PumpStartEvent[]>([]);
  const [energyReport, setEnergyReport] = useState<PumpEnergyReport | null>(null);
  const [anomaliesData, setAnomaliesData] = useState<PumpAlert[]>([]);
  const [driftForecast, setDriftForecast] = useState<PumpDriftForecast | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [selectedAlert, setSelectedAlert] = useState<PumpAlert | null>(null);
  const [actionMessage, setActionMessage] = useState<string | null>(null);

  // Initial Load
  const fetchAllData = async () => {
    setLoading(true);
    try {
      const [monitors, trends, starts, energy, anomalies, forecast] = await Promise.all([
        api.getPumpMonitors(),
        api.getPumpTrends(selectedPumpId),
        api.getPumpStartEvents(selectedPumpId),
        api.getPumpEnergyReport(),
        api.getPumpAnomalies(),
        api.getPumpForecast(selectedPumpId, 48)
      ]);
      setMonitorsData(monitors);
      setTrendData(trends);
      setStartEvents(starts.events || []);
      setEnergyReport(energy);
      setAnomaliesData(anomalies.active_alerts || []);
      setDriftForecast(forecast);
      if (anomalies.active_alerts && anomalies.active_alerts.length > 0 && !selectedAlert) {
        setSelectedAlert(anomalies.active_alerts[0]);
      }
    } catch (err) {
      console.error('Failed loading pump data:', err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchAllData();
    const interval = setInterval(fetchAllData, 8000);
    return () => clearInterval(interval);
  }, [selectedPumpId]);

  const handleInject = async (type: string, severity: number = 1.0) => {
    try {
      await api.injectPumpScenario(selectedPumpId, type, severity);
      setActionMessage(`Injected scenario: ${type} on ${selectedPumpId}`);
      setTimeout(() => setActionMessage(null), 4000);
      fetchAllData();
    } catch (err) {
      console.error(err);
    }
  };

  const handleClear = async () => {
    try {
      await api.clearPumpScenario(selectedPumpId);
      setActionMessage(`Cleared fault injection on ${selectedPumpId}`);
      setTimeout(() => setActionMessage(null), 4000);
      fetchAllData();
    } catch (err) {
      console.error(err);
    }
  };

  const currentPump = monitorsData?.pumps?.find((p: any) => p.pump_id === selectedPumpId);

  return (
    <div className="absolute inset-0 z-40 bg-slate-950/95 backdrop-blur-xl flex flex-col text-slate-100 overflow-hidden select-none">
      {/* Top Header */}
      <div className="h-14 border-b border-slate-800 px-6 flex items-center justify-between bg-slate-900/80">
        <div className="flex items-center gap-3">
          <div className="p-2 rounded-xl bg-amber-500/20 text-amber-400 border border-amber-500/30 shadow-lg">
            <Zap className="w-5 h-5 fill-current animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-sm font-bold tracking-tight text-white uppercase font-mono">
                Pump Power & Electromechanical Health Studio
              </h1>
              <ProvenanceChip tier="SIMULATED" size="sm" showDetails={false} />
              <span className="px-2 py-0.5 rounded text-[10px] font-mono bg-cyan-950 border border-cyan-800/80 text-cyan-300">
                Tataguni Stage Pumping Station (3x 1200 kW)
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              3-Phase Monitoring • Robust Median/MAD Learned Bands • Multi-Fault Advisory Diagnostics • Predictive Drift Forecasting
            </p>
          </div>
        </div>

        {/* Pump Unit Selector */}
        <div className="flex items-center gap-2 bg-slate-950 p-1 rounded-xl border border-slate-800">
          {monitorsData?.pumps?.map((p: PumpStatus) => {
            const hasAlert = p.active_anomalies && p.active_anomalies.length > 0;
            const isSelected = selectedPumpId === p.pump_id;
            return (
              <button
                key={p.pump_id}
                onClick={() => setSelectedPumpId(p.pump_id)}
                className={`px-3 py-1.5 rounded-lg text-xs font-medium flex items-center gap-2 transition-all ${
                  isSelected
                    ? 'bg-amber-600 text-white shadow-md'
                    : 'text-slate-400 hover:text-white hover:bg-slate-900'
                }`}
              >
                <Gauge className="w-3.5 h-3.5" />
                <span>{p.name.split('(')[0]}</span>
                <span className={`px-1.5 py-0.2 rounded text-[9px] font-mono ${
                  p.status === 'STEADY_RUNNING' ? 'bg-emerald-950 text-emerald-400' : 'bg-slate-800 text-slate-400'
                }`}>
                  {p.status}
                </span>
                {hasAlert && (
                  <span className="w-2 h-2 rounded-full bg-rose-500 animate-ping" />
                )}
              </button>
            );
          })}

          <button
            onClick={onClose}
            className="ml-2 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white transition-all"
          >
            Close Studio
          </button>
        </div>
      </div>

      {/* Advisory Banner */}
      <div className="bg-amber-950/40 border-b border-amber-900/60 px-6 py-1.5 flex items-center justify-between text-xs text-amber-200/90">
        <div className="flex items-center gap-2">
          <Info className="w-4 h-4 text-amber-400 shrink-0" />
          <span>
            <strong>ADVISORY DECISION SUPPORT:</strong> All pump anomaly diagnostics, causes, forward consequences, and actions are advisory recommendations. Field inspection and human operator sign-off is mandatory before switching or isolating units.
          </span>
        </div>
        {actionMessage && (
          <span className="px-2 py-0.5 rounded bg-emerald-900/80 text-emerald-200 border border-emerald-700 font-mono text-[11px] animate-fade-in">
            {actionMessage}
          </span>
        )}
      </div>

      {/* Sub-Navigation Tabs */}
      <div className="border-b border-slate-800/80 px-6 bg-slate-900/50 flex items-center justify-between">
        <div className="flex items-center gap-1">
          <button
            onClick={() => setActiveTab('trends')}
            className={`px-4 py-2.5 text-xs font-medium border-b-2 flex items-center gap-2 transition-all ${
              activeTab === 'trends'
                ? 'border-amber-500 text-amber-400 bg-amber-500/10'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
            }`}
          >
            <TrendingUp className="w-4 h-4" />
            <span>Trend Charts & Learned Bands</span>
          </button>

          <button
            onClick={() => setActiveTab('startup')}
            className={`px-4 py-2.5 text-xs font-medium border-b-2 flex items-center gap-2 transition-all ${
              activeTab === 'startup'
                ? 'border-cyan-500 text-cyan-400 bg-cyan-500/10'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
            }`}
          >
            <Clock className="w-4 h-4" />
            <span>Start-Up Event Viewer ({startEvents.length})</span>
          </button>

          <button
            onClick={() => setActiveTab('energy')}
            className={`px-4 py-2.5 text-xs font-medium border-b-2 flex items-center gap-2 transition-all ${
              activeTab === 'energy'
                ? 'border-emerald-500 text-emerald-400 bg-emerald-500/10'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
            }`}
          >
            <IndianRupee className="w-4 h-4" />
            <span>Energy & Tariff Report</span>
          </button>

          <button
            onClick={() => setActiveTab('anomalies')}
            className={`px-4 py-2.5 text-xs font-medium border-b-2 flex items-center gap-2 transition-all relative ${
              activeTab === 'anomalies'
                ? 'border-rose-500 text-rose-400 bg-rose-500/10'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
            }`}
          >
            <ShieldAlert className="w-4 h-4" />
            <span>Anomaly Timeline & Knowledge Base</span>
            {anomaliesData.length > 0 && (
              <span className="px-1.5 py-0.2 rounded-full bg-rose-600 text-white text-[10px] font-bold">
                {anomaliesData.length}
              </span>
            )}
          </button>

          <button
            onClick={() => setActiveTab('forecast')}
            className={`px-4 py-2.5 text-xs font-medium border-b-2 flex items-center gap-2 transition-all ${
              activeTab === 'forecast'
                ? 'border-purple-500 text-purple-400 bg-purple-500/10'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
            }`}
          >
            <Sparkles className="w-4 h-4" />
            <span>Drift Forecast & Backtest</span>
          </button>

          <button
            onClick={() => setActiveTab('scenarios')}
            className={`px-4 py-2.5 text-xs font-medium border-b-2 flex items-center gap-2 transition-all ${
              activeTab === 'scenarios'
                ? 'border-orange-500 text-orange-400 bg-orange-500/10'
                : 'border-transparent text-slate-400 hover:text-slate-200 hover:bg-slate-800/40'
            }`}
          >
            <Sliders className="w-4 h-4" />
            <span>Fault Injection Sandbox</span>
          </button>
        </div>

        <button
          onClick={fetchAllData}
          className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-all text-xs flex items-center gap-1.5"
          title="Refresh Telemetry"
        >
          <RefreshCw className="w-3.5 h-3.5" />
          <span>Sync Now</span>
        </button>
      </div>

      {/* Main Studio Body */}
      <div className="flex-1 overflow-y-auto p-6 space-y-6">
        {/* KPI Summary Cards */}
        {currentPump && (
          <div className="grid grid-cols-2 md:grid-cols-6 gap-3">
            <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">3-Phase Voltage</span>
              <div className="text-lg font-bold text-cyan-400 font-mono mt-0.5">
                {currentPump.latest_telemetry?.voltage_avg} V
              </div>
              <span className="text-[10px] text-slate-500">
                Imbalance: <strong className={currentPump.latest_telemetry?.voltage_imbalance_pct > 2 ? 'text-rose-400' : 'text-emerald-400'}>
                  {currentPump.latest_telemetry?.voltage_imbalance_pct}%
                </strong>
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">Current per Phase</span>
              <div className="text-lg font-bold text-amber-400 font-mono mt-0.5">
                {currentPump.latest_telemetry?.current_avg} A
              </div>
              <span className="text-[10px] text-slate-500">
                Band: [{currentPump.steady_band?.current_a?.band_low} - {currentPump.steady_band?.current_a?.band_high} A]
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">Active Power & PF</span>
              <div className="text-lg font-bold text-purple-400 font-mono mt-0.5">
                {currentPump.latest_telemetry?.active_power_kw} kW
              </div>
              <span className="text-[10px] text-slate-500">
                PF: <strong>{currentPump.latest_telemetry?.power_factor}</strong> (Rated 0.88)
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">Discharge Flow & Head</span>
              <div className="text-lg font-bold text-blue-400 font-mono mt-0.5">
                {currentPump.latest_telemetry?.flow_lps} LPS
              </div>
              <span className="text-[10px] text-slate-500">
                Press: <strong>{currentPump.latest_telemetry?.discharge_pressure_bar} bar</strong>
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">Specific Energy</span>
              <div className="text-lg font-bold text-emerald-400 font-mono mt-0.5">
                {currentPump.latest_telemetry?.specific_energy_kwh_per_m3} kWh/m³
              </div>
              <span className="text-[10px] text-slate-500">
                Benchmark: &le; 0.58 kWh/m³
              </span>
            </div>

            <div className="p-3.5 rounded-xl bg-slate-900/80 border border-slate-800">
              <span className="text-[10px] text-slate-400 uppercase tracking-wider block font-mono">Daily Operating Cost</span>
              <div className="text-lg font-bold text-amber-300 font-mono mt-0.5">
                ₹{currentPump.latest_telemetry?.daily_cost_inr?.toLocaleString('en-IN')}
              </div>
              <span className="text-[10px] text-slate-500">
                Tariff: ₹7.50/kWh ({currentPump.latest_telemetry?.kwh_24h} kWh)
              </span>
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 1: TREND CHARTS & LEARNED BANDS */}
        {/* ============================================================== */}
        {activeTab === 'trends' && trendData && (
          <div className="space-y-6">
            {/* Chart 1: Current per Phase with Learned Steady-State Band */}
            <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                    <Activity className="w-4 h-4 text-amber-400" />
                    <span>3-Phase Current & Learned Steady-State Band (Robust Median / MAD)</span>
                  </h3>
                  <p className="text-xs text-slate-400">
                    Normal operating band [Median &plusmn; 2.5 &times; MAD] = [{trendData.steady_band?.current_a?.band_low} A - {trendData.steady_band?.current_a?.band_high} A]. Updated only from healthy steady-state intervals.
                  </p>
                </div>
                <div className="flex items-center gap-4 text-xs font-mono">
                  <span className="flex items-center gap-1.5 text-rose-400">
                    <span className="w-2.5 h-0.5 bg-rose-500" /> Phase R
                  </span>
                  <span className="flex items-center gap-1.5 text-amber-400">
                    <span className="w-2.5 h-0.5 bg-amber-500" /> Phase Y
                  </span>
                  <span className="flex items-center gap-1.5 text-blue-400">
                    <span className="w-2.5 h-0.5 bg-blue-500" /> Phase B
                  </span>
                  <span className="flex items-center gap-1.5 text-emerald-400">
                    <span className="w-2.5 h-0.5 bg-emerald-500" /> Band High/Low
                  </span>
                </div>
              </div>

              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={trendData.timeseries} margin={{ top: 10, right: 20, left: 0, bottom: 0 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="time_label" stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis stroke="#64748b" tick={{ fontSize: 10 }} domain={['auto', 'auto']} unit=" A" />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '11px' }} />
                    <ReferenceLine y={trendData.steady_band?.current_a?.band_high} stroke="#10b981" strokeDasharray="4 4" label={{ value: 'Band High', fill: '#10b981', fontSize: 10 }} />
                    <ReferenceLine y={trendData.steady_band?.current_a?.band_low} stroke="#10b981" strokeDasharray="4 4" label={{ value: 'Band Low', fill: '#10b981', fontSize: 10 }} />
                    <Line type="monotone" dataKey="current_r" stroke="#f43f5e" strokeWidth={1.5} dot={false} name="Current R (A)" />
                    <Line type="monotone" dataKey="current_y" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="Current Y (A)" />
                    <Line type="monotone" dataKey="current_b" stroke="#3b82f6" strokeWidth={1.5} dot={false} name="Current B (A)" />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Chart 2: 3-Phase Supply Voltage */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                      <Zap className="w-4 h-4 text-cyan-400" />
                      <span>3-Phase Supply Voltage (6.6 kV Medium Voltage)</span>
                    </h3>
                    <p className="text-xs text-slate-400">
                      Grid tolerance bounds: 90% (5940 V) to 110% (7260 V). Max imbalance &le; 2.0%.
                    </p>
                  </div>
                </div>
                <div className="h-56 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trendData.timeseries} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="time_label" stroke="#64748b" tick={{ fontSize: 10 }} />
                      <YAxis stroke="#64748b" tick={{ fontSize: 10 }} domain={[5800, 7400]} unit=" V" />
                      <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '11px' }} />
                      <ReferenceLine y={6600} stroke="#64748b" strokeDasharray="3 3" />
                      <ReferenceLine y={7260} stroke="#f43f5e" strokeDasharray="3 3" label={{ value: '+10% Limit', fill: '#f43f5e', fontSize: 9 }} />
                      <ReferenceLine y={5940} stroke="#f43f5e" strokeDasharray="3 3" label={{ value: '-10% Limit', fill: '#f43f5e', fontSize: 9 }} />
                      <Line type="monotone" dataKey="voltage_r" stroke="#f43f5e" strokeWidth={1.5} dot={false} name="Voltage R (V)" />
                      <Line type="monotone" dataKey="voltage_y" stroke="#f59e0b" strokeWidth={1.5} dot={false} name="Voltage Y (V)" />
                      <Line type="monotone" dataKey="voltage_b" stroke="#3b82f6" strokeWidth={1.5} dot={false} name="Voltage B (V)" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>

              {/* Chart 3: Active Power & Hydraulic Flow Correlation */}
              <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                      <BarChart3 className="w-4 h-4 text-purple-400" />
                      <span>Active Power Draw (kW) & Power Factor</span>
                    </h3>
                    <p className="text-xs text-slate-400">
                      Normal power band: [{trendData.steady_band?.power_kw?.band_low} kW - {trendData.steady_band?.power_kw?.band_high} kW].
                    </p>
                  </div>
                </div>
                <div className="h-56 w-full">
                  <ResponsiveContainer width="100%" height="100%">
                    <LineChart data={trendData.timeseries} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                      <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                      <XAxis dataKey="time_label" stroke="#64748b" tick={{ fontSize: 10 }} />
                      <YAxis stroke="#64748b" tick={{ fontSize: 10 }} domain={['auto', 'auto']} unit=" kW" />
                      <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '11px' }} />
                      <ReferenceLine y={1200} stroke="#8b5cf6" strokeDasharray="3 3" label={{ value: 'Rated 1200 kW', fill: '#8b5cf6', fontSize: 9 }} />
                      <ReferenceLine y={trendData.steady_band?.power_kw?.band_high} stroke="#10b981" strokeDasharray="4 4" />
                      <Line type="monotone" dataKey="active_power_kw" stroke="#a855f7" strokeWidth={2} dot={false} name="Active Power (kW)" />
                    </LineChart>
                  </ResponsiveContainer>
                </div>
              </div>
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 2: START-UP EVENT VIEWER */}
        {/* ============================================================== */}
        {activeTab === 'startup' && (
          <div className="space-y-6">
            <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4">
              <div>
                <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                  <Clock className="w-4 h-4 text-cyan-400" />
                  <span>Start-Up Inrush Waveform Recorder</span>
                </h3>
                <p className="text-xs text-slate-400">
                  Records inrush current peak and exponential ramp-down decay profile. Flags excessive starts (&gt; 3/hr) and thermal lockouts.
                </p>
              </div>

              {startEvents.length > 0 && startEvents[0].decay_profile && (
                <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-3">
                  <div className="flex items-center justify-between text-xs font-mono">
                    <span className="text-cyan-300">
                      Latest Start Event: <strong>{startEvents[0].event_id}</strong> ({startEvents[0].timestamp})
                    </span>
                    <span className="text-amber-400">
                      Inrush Peak: <strong>{startEvents[0].inrush_peak_current_a} A</strong> ({startEvents[0].inrush_ratio}x Rated)
                    </span>
                    <span className="text-emerald-400">
                      Ramp Duration: <strong>{startEvents[0].ramp_down_duration_sec}s</strong>
                    </span>
                  </div>

                  <div className="h-56 w-full">
                    <ResponsiveContainer width="100%" height="100%">
                      <AreaChart data={startEvents[0].decay_profile} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                        <defs>
                          <linearGradient id="inrushGrad" x1="0" y1="0" x2="0" y2="1">
                            <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.8}/>
                            <stop offset="95%" stopColor="#06b6d4" stopOpacity={0}/>
                          </linearGradient>
                        </defs>
                        <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                        <XAxis dataKey="time_sec" stroke="#64748b" tick={{ fontSize: 10 }} unit="s" />
                        <YAxis stroke="#64748b" tick={{ fontSize: 10 }} unit=" A" domain={[0, 'auto']} />
                        <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '11px' }} />
                        <ReferenceLine y={124.5} stroke="#10b981" strokeDasharray="3 3" label={{ value: 'Rated Steady 124.5 A', fill: '#10b981', fontSize: 10 }} />
                        <Area type="monotone" dataKey="current_a" stroke="#06b6d4" strokeWidth={2} fillOpacity={1} fill="url(#inrushGrad)" name="Transient Current (A)" />
                      </AreaChart>
                    </ResponsiveContainer>
                  </div>
                </div>
              )}

              {/* Start Events History Table */}
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs border border-slate-800 rounded-xl overflow-hidden">
                  <thead className="bg-slate-950/80 text-slate-400 font-mono text-[11px] border-b border-slate-800">
                    <tr>
                      <th className="p-3">Event ID</th>
                      <th className="p-3">Timestamp (UTC)</th>
                      <th className="p-3">Inrush Peak (A)</th>
                      <th className="p-3">Inrush Ratio</th>
                      <th className="p-3">Ramp Duration</th>
                      <th className="p-3">State / Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-800/60 font-mono">
                    {startEvents.map((evt) => (
                      <tr key={evt.event_id} className="hover:bg-slate-800/30">
                        <td className="p-3 text-cyan-400">{evt.event_id}</td>
                        <td className="p-3 text-slate-300">{evt.timestamp}</td>
                        <td className="p-3 font-bold text-amber-400">{evt.inrush_peak_current_a} A</td>
                        <td className="p-3 text-slate-300">{evt.inrush_ratio}x</td>
                        <td className="p-3 text-slate-300">{evt.ramp_down_duration_sec} sec</td>
                        <td className="p-3">
                          <span className={`px-2 py-0.5 rounded text-[10px] ${
                            evt.status === 'NORMAL_RAMP' ? 'bg-emerald-950 text-emerald-300 border border-emerald-800' : 'bg-rose-950 text-rose-300 border border-rose-800'
                          }`}>
                            {evt.status}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 3: ENERGY & TARIFF REPORT */}
        {/* ============================================================== */}
        {activeTab === 'energy' && energyReport && (
          <div className="space-y-6">
            <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
              <div className="p-5 rounded-2xl bg-gradient-to-br from-slate-900 to-slate-950 border border-slate-800">
                <span className="text-xs text-slate-400 uppercase font-mono block">Station Total Energy (24h)</span>
                <div className="text-2xl font-bold text-purple-400 font-mono mt-1">
                  {energyReport.total_kwh_24h.toLocaleString()} kWh
                </div>
                <span className="text-xs text-slate-500 mt-1 block">Tataguni Terminal Station Incomer</span>
              </div>

              <div className="p-5 rounded-2xl bg-gradient-to-br from-slate-900 to-slate-950 border border-slate-800">
                <span className="text-xs text-slate-400 uppercase font-mono block">Station Daily Power Cost</span>
                <div className="text-2xl font-bold text-amber-400 font-mono mt-1">
                  ₹{energyReport.total_cost_inr_24h.toLocaleString('en-IN')}
                </div>
                <span className="text-xs text-slate-500 mt-1 block">At config tariff ₹{energyReport.tariff_inr_per_kwh}/kWh</span>
              </div>

              <div className="p-5 rounded-2xl bg-gradient-to-br from-slate-900 to-slate-950 border border-slate-800">
                <span className="text-xs text-slate-400 uppercase font-mono block">Bulk Water Delivered</span>
                <div className="text-2xl font-bold text-blue-400 font-mono mt-1">
                  {energyReport.total_volume_mld_24h} MLD
                </div>
                <span className="text-xs text-slate-500 mt-1 block">({energyReport.total_volume_m3_24h.toLocaleString()} m³/day)</span>
              </div>

              <div className="p-5 rounded-2xl bg-gradient-to-br from-slate-900 to-slate-950 border border-slate-800">
                <span className="text-xs text-slate-400 uppercase font-mono block">Station Specific Energy</span>
                <div className="text-2xl font-bold text-emerald-400 font-mono mt-1">
                  {energyReport.station_specific_energy_kwh_per_m3} kWh/m³
                </div>
                <span className="text-xs text-emerald-500 mt-1 block">Benchmark target: &le; 0.58 kWh/m³</span>
              </div>
            </div>

            {/* Per-Pump Breakdown Table */}
            <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-3">
              <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                <IndianRupee className="w-4 h-4 text-amber-400" />
                <span>Unit-Level Energy & Specific Consumption Breakdown</span>
              </h3>

              <table className="w-full text-left text-xs border border-slate-800 rounded-xl overflow-hidden font-mono">
                <thead className="bg-slate-950 text-slate-400 text-[11px] border-b border-slate-800">
                  <tr>
                    <th className="p-3">Pump Unit</th>
                    <th className="p-3">Status</th>
                    <th className="p-3">Avg Power (kW)</th>
                    <th className="p-3">24h Energy (kWh)</th>
                    <th className="p-3">24h Cost (₹)</th>
                    <th className="p-3">Delivered (MLD)</th>
                    <th className="p-3">Specific Energy (kWh/m³)</th>
                    <th className="p-3">Efficiency</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {energyReport.pumps.map((p) => (
                    <tr key={p.pump_id} className="hover:bg-slate-800/30">
                      <td className="p-3 text-slate-200 font-bold">{p.name}</td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] ${
                          p.status === 'STEADY_RUNNING' ? 'bg-emerald-950 text-emerald-400' : 'bg-slate-800 text-slate-400'
                        }`}>
                          {p.status}
                        </span>
                      </td>
                      <td className="p-3 text-purple-400">{p.avg_power_kw} kW</td>
                      <td className="p-3 text-slate-200">{p.kwh_24h.toLocaleString()}</td>
                      <td className="p-3 text-amber-400 font-bold">₹{p.cost_inr_24h.toLocaleString('en-IN')}</td>
                      <td className="p-3 text-blue-400">{p.volume_mld_24h}</td>
                      <td className="p-3 text-emerald-400 font-bold">{p.specific_energy_kwh_per_m3}</td>
                      <td className="p-3">
                        <span className={`px-2 py-0.5 rounded text-[10px] ${
                          p.efficiency_rating === 'OPTIMAL' ? 'bg-emerald-950 text-emerald-300' : 'bg-amber-950 text-amber-300'
                        }`}>
                          {p.efficiency_rating}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 4: ANOMALY TIMELINE & KNOWLEDGE BASE */}
        {/* ============================================================== */}
        {activeTab === 'anomalies' && (
          <div className="grid grid-cols-1 md:grid-cols-12 gap-6">
            {/* Left Column: Anomaly Alert Cards */}
            <div className="md:col-span-5 space-y-3">
              <h3 className="text-sm font-bold text-slate-200 flex items-center justify-between">
                <span className="flex items-center gap-2">
                  <ShieldAlert className="w-4 h-4 text-rose-400" />
                  Active Pump Anomalies ({anomaliesData.length})
                </span>
                <span className="text-[11px] font-mono text-slate-500">Live Detector</span>
              </h3>

              {anomaliesData.length === 0 ? (
                <div className="p-8 rounded-2xl bg-slate-900/60 border border-slate-800 text-center space-y-2">
                  <CheckCircle2 className="w-10 h-10 text-emerald-400 mx-auto" />
                  <h4 className="text-sm font-bold text-slate-200">All Pumps Operating in Normal Bands</h4>
                  <p className="text-xs text-slate-400">
                    No voltage imbalance, dry-run cavitation, blockage, or thermal drift anomalies detected.
                  </p>
                </div>
              ) : (
                anomaliesData.map((alert) => {
                  const isSelected = selectedAlert?.alert_id === alert.alert_id;
                  return (
                    <div
                      key={alert.alert_id}
                      onClick={() => setSelectedAlert(alert)}
                      className={`p-4 rounded-xl border cursor-pointer transition-all ${
                        isSelected
                          ? 'bg-rose-950/40 border-rose-500 shadow-lg shadow-rose-950/50'
                          : 'bg-slate-900/80 border-slate-800 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between">
                        <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                          alert.severity === 'CRITICAL' ? 'bg-rose-600 text-white' : 'bg-amber-600 text-white'
                        }`}>
                          {alert.severity} • {alert.anomaly_type}
                        </span>
                        <span className="text-[10px] text-slate-400 font-mono">
                          Duration: {alert.duration_minutes} min
                        </span>
                      </div>

                      <h4 className="text-xs font-bold text-slate-100 mt-2">
                        {alert.pump_name}: {alert.anomaly_name}
                      </h4>

                      <div className="mt-2 text-[11px] font-mono space-y-1 text-slate-300">
                        <div>Variable: <strong className="text-cyan-400">{alert.variable}</strong> ({alert.phase})</div>
                        <div>Current Value: <strong className="text-rose-400">{alert.current_value} {alert.unit}</strong></div>
                        <div>Deviation: <strong className="text-amber-400">{alert.how_far_from_normal}</strong></div>
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Right Column: Advisory Knowledge Base Detail Drawer */}
            <div className="md:col-span-7">
              {selectedAlert ? (
                <div className="p-6 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-5">
                  <div className="flex items-start justify-between border-b border-slate-800 pb-4">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-rose-600 text-white">
                          {selectedAlert.severity}
                        </span>
                        <h3 className="text-base font-bold text-white">
                          {selectedAlert.anomaly_name}
                        </h3>
                      </div>
                      <p className="text-xs text-slate-400 mt-1">
                        Station: <strong>{selectedAlert.station_name}</strong> • Unit: <strong>{selectedAlert.pump_name}</strong>
                      </p>
                    </div>

                    <div className="text-right font-mono text-[11px] text-slate-400">
                      <div>Zone: {selectedAlert.zone}</div>
                      <div>Since: {selectedAlert.since_when}</div>
                    </div>
                  </div>

                  {/* Deviation Metrics Card */}
                  <div className="p-3.5 rounded-xl bg-slate-950 border border-slate-800 grid grid-cols-3 gap-3 text-xs font-mono">
                    <div>
                      <span className="text-slate-500 block text-[10px]">OBSERVED VALUE</span>
                      <strong className="text-rose-400 text-sm">{selectedAlert.current_value} {selectedAlert.unit}</strong>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px]">NORMAL THRESHOLD</span>
                      <strong className="text-emerald-400 text-sm">{selectedAlert.normal_threshold}</strong>
                    </div>
                    <div>
                      <span className="text-slate-500 block text-[10px]">DEVIATION</span>
                      <strong className="text-amber-400 text-sm">{selectedAlert.how_far_from_normal}</strong>
                    </div>
                  </div>

                  {/* Likely Causes (Advisory KB) */}
                  <div className="space-y-2">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5 font-mono">
                      <AlertTriangle className="w-3.5 h-3.5" />
                      Likely Causes (Advisory Knowledge Base)
                    </h4>
                    <ul className="space-y-1 text-xs text-slate-300">
                      {selectedAlert.likely_causes.map((c, idx) => (
                        <li key={idx} className="flex items-start gap-2 bg-slate-950/60 p-2 rounded-lg border border-slate-800/80">
                          <span className="text-amber-500 font-bold shrink-0">•</span>
                          <span>{c}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Future Consequences */}
                  <div className="space-y-2">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-rose-400 flex items-center gap-1.5 font-mono">
                      <Thermometer className="w-3.5 h-3.5" />
                      Forward Operational Consequences (If Unaddressed)
                    </h4>
                    <ul className="space-y-1 text-xs text-slate-300">
                      {selectedAlert.future_consequences.map((c, idx) => (
                        <li key={idx} className="flex items-start gap-2 bg-rose-950/20 p-2 rounded-lg border border-rose-900/40 text-rose-200">
                          <span className="text-rose-400 font-bold shrink-0">!</span>
                          <span>{c}</span>
                        </li>
                      ))}
                    </ul>
                  </div>

                  {/* Suggested Actions Checklist */}
                  <div className="space-y-2">
                    <h4 className="text-xs font-bold uppercase tracking-wider text-cyan-400 flex items-center gap-1.5 font-mono">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      Suggested Human Remedial Actions
                    </h4>
                    <ul className="space-y-1 text-xs text-slate-300">
                      {selectedAlert.suggested_actions.map((act, idx) => (
                        <li key={idx} className="flex items-start gap-2 bg-cyan-950/20 p-2 rounded-lg border border-cyan-900/40 text-cyan-200">
                          <span className="text-cyan-400 font-bold shrink-0">[{idx + 1}]</span>
                          <span>{act}</span>
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              ) : (
                <div className="p-8 rounded-2xl bg-slate-900/40 border border-slate-800 text-center text-xs text-slate-500">
                  Select an alert card on the left to view technical diagnostic causes, impacts, and actions.
                </div>
              )}
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 5: DRIFT FORECAST & BACKTEST */}
        {/* ============================================================== */}
        {activeTab === 'forecast' && driftForecast && (
          <div className="space-y-6">
            {/* Header / Countdown */}
            <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 flex flex-col md:flex-row items-start md:items-center justify-between gap-4">
              <div>
                <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                  <Sparkles className="w-4 h-4 text-purple-400" />
                  <span>Predictive Steady-State Drift Forecast & Time-to-Alarm</span>
                </h3>
                <p className="text-xs text-slate-400">
                  Ordinary least squares trend projection with 95% confidence uncertainty prediction intervals vs critical trip limit ({driftForecast.alarm_limit_kw} kW).
                </p>
              </div>

              <div className="p-3 rounded-xl bg-purple-950/60 border border-purple-800/80 font-mono text-xs">
                <span className="text-purple-300 block text-[10px] uppercase">Time to Critical Alarm Limit:</span>
                <strong className="text-base text-purple-200">
                  {driftForecast.time_to_alarm.formatted_advisory}
                </strong>
              </div>
            </div>

            {/* Projection Chart */}
            <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-3">
              <div className="flex items-center justify-between text-xs font-mono">
                <span className="text-slate-300">
                  Current Power: <strong>{driftForecast.current_power_kw} kW</strong> | Drift Slope: <strong>{driftForecast.drift_slope_kw_per_hour} kW/hr</strong>
                </span>
                <span className="flex items-center gap-4">
                  <span className="text-purple-400">● Predicted kW</span>
                  <span className="text-slate-500">░ 95% Confidence Cone</span>
                  <span className="text-rose-400">--- Trip Limit (1344 kW)</span>
                </span>
              </div>

              <div className="h-64 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={driftForecast.forecast_timeseries} margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                    <defs>
                      <linearGradient id="driftCone" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="#a855f7" stopOpacity={0.4}/>
                        <stop offset="95%" stopColor="#a855f7" stopOpacity={0.05}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="time_iso" stroke="#64748b" tick={{ fontSize: 10 }} />
                    <YAxis stroke="#64748b" tick={{ fontSize: 10 }} domain={[1100, 1450]} unit=" kW" />
                    <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '11px' }} />
                    <ReferenceLine y={driftForecast.alarm_limit_kw} stroke="#f43f5e" strokeWidth={2} strokeDasharray="4 4" label={{ value: 'Trip Limit 1344 kW', fill: '#f43f5e', fontSize: 10 }} />
                    <Area type="monotone" dataKey="upper_bound_95" stroke="none" fill="#a855f7" fillOpacity={0.2} name="95% Upper Bound (kW)" />
                    <Area type="monotone" dataKey="lower_bound_95" stroke="none" fill="#0f172a" fillOpacity={1} name="95% Lower Bound (kW)" />
                    <Line type="monotone" dataKey="predicted_kw" stroke="#a855f7" strokeWidth={2.5} dot={false} name="Projected Mean (kW)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Backtest Comparison Card */}
            {driftForecast.backtest && (
              <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4">
                <div className="flex items-center justify-between">
                  <div>
                    <h3 className="text-sm font-bold text-slate-200 font-mono">
                      Backtest Validation: Proposed Drift+MAD Model vs Simple Threshold Baseline
                    </h3>
                    <p className="text-xs text-slate-400">
                      Evaluated against: {driftForecast.backtest.test_scenario} ({driftForecast.backtest.benchmark_steps_evaluated} steps)
                    </p>
                  </div>
                  <span className="px-3 py-1 rounded-lg bg-emerald-950 border border-emerald-800 text-emerald-300 font-mono text-xs font-bold">
                    {driftForecast.backtest.performance_gain}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div className="p-4 rounded-xl bg-purple-950/30 border border-purple-900/60 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-purple-300 font-mono">
                        {driftForecast.backtest.proposed_drift_model.name}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] bg-purple-900 text-purple-200">PROPOSED</span>
                    </div>
                    <div className="text-xs font-mono space-y-1 text-slate-300">
                      <div>Early Warning Lead Time: <strong className="text-emerald-400">+{driftForecast.backtest.proposed_drift_model.early_warning_lead_time_hours} hours</strong></div>
                      <div>False Alarms on Baseline: <strong className="text-emerald-400">{driftForecast.backtest.proposed_drift_model.false_alarms_in_stable_baseline}</strong></div>
                      <div>Action Window: <span className="text-purple-200">{driftForecast.backtest.proposed_drift_model.recommendation_window}</span></div>
                    </div>
                  </div>

                  <div className="p-4 rounded-xl bg-slate-950/80 border border-slate-800 space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-bold text-slate-300 font-mono">
                        {driftForecast.backtest.simple_threshold_baseline.name}
                      </span>
                      <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">STATIC BASELINE</span>
                    </div>
                    <div className="text-xs font-mono space-y-1 text-slate-400">
                      <div>Early Warning Lead Time: <strong className="text-rose-400">0.0 hours (Zero lead time)</strong></div>
                      <div>False Alarms on Baseline: <strong className="text-amber-400">{driftForecast.backtest.simple_threshold_baseline.false_alarms_in_stable_baseline}</strong></div>
                      <div>Action Window: <span className="text-slate-400">{driftForecast.backtest.simple_threshold_baseline.recommendation_window}</span></div>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>
        )}

        {/* ============================================================== */}
        {/* TAB 6: FAULT INJECTION SANDBOX */}
        {/* ============================================================== */}
        {activeTab === 'scenarios' && (
          <div className="space-y-6">
            <div className="p-5 rounded-2xl bg-slate-900/90 border border-slate-800 space-y-4">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="text-sm font-bold text-slate-200 flex items-center gap-2">
                    <Sliders className="w-4 h-4 text-orange-400" />
                    <span>Operational Drill & Scenario Fault Injection</span>
                  </h3>
                  <p className="text-xs text-slate-400">
                    Inject electromechanical anomalies to test alarms, advisory diagnostics, and operator workflows on <strong>{selectedPumpId}</strong>.
                  </p>
                </div>

                <button
                  onClick={handleClear}
                  className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center gap-1.5 transition-all"
                >
                  <RotateCcw className="w-3.5 h-3.5" />
                  <span>Clear Injections</span>
                </button>
              </div>

              <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                  <div className="text-xs font-bold text-rose-400 flex items-center gap-1.5">
                    <ShieldAlert className="w-4 h-4" />
                    <span>Hydraulic Starvation & Blockage</span>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Test differential current vs flow trip logic.
                  </p>
                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => handleInject('RUNNING_DRY')}
                      className="px-3 py-2 rounded-lg bg-rose-950/60 hover:bg-rose-900/80 border border-rose-800 text-rose-200 text-xs text-left font-medium flex items-center justify-between"
                    >
                      <span>Inject Running Dry</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => handleInject('BLOCKAGE')}
                      className="px-3 py-2 rounded-lg bg-rose-950/60 hover:bg-rose-900/80 border border-rose-800 text-rose-200 text-xs text-left font-medium flex items-center justify-between"
                    >
                      <span>Inject Delivery Blockage</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                  <div className="text-xs font-bold text-amber-400 flex items-center gap-1.5">
                    <Zap className="w-4 h-4" />
                    <span>Grid & Power Quality Faults</span>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Test 3-phase asymmetry, undervoltage, and capacitor bank failure.
                  </p>
                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => handleInject('VOLTAGE_IMBALANCE', 1.8)}
                      className="px-3 py-2 rounded-lg bg-amber-950/60 hover:bg-amber-900/80 border border-amber-800 text-amber-200 text-xs text-left font-medium flex items-center justify-between"
                    >
                      <span>Inject Voltage Imbalance (&gt; 2.5%)</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => handleInject('UNDERVOLTAGE', 1.0)}
                      className="px-3 py-2 rounded-lg bg-amber-950/60 hover:bg-amber-900/80 border border-amber-800 text-amber-200 text-xs text-left font-medium flex items-center justify-between"
                    >
                      <span>Inject Grid Undervoltage (5.7 kV)</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => handleInject('LOW_POWER_FACTOR', 1.0)}
                      className="px-3 py-2 rounded-lg bg-amber-950/60 hover:bg-amber-900/80 border border-amber-800 text-amber-200 text-xs text-left font-medium flex items-center justify-between"
                    >
                      <span>Inject Low Power Factor (0.74)</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>

                <div className="p-4 rounded-xl bg-slate-950 border border-slate-800 space-y-3">
                  <div className="text-xs font-bold text-purple-400 flex items-center gap-1.5">
                    <Sparkles className="w-4 h-4" />
                    <span>Thermal Drift & Wear Degradation</span>
                  </div>
                  <p className="text-[11px] text-slate-400">
                    Test progressive wear ring clearance and hunting cycles.
                  </p>
                  <div className="flex flex-col gap-2">
                    <button
                      onClick={() => handleInject('BEARING_FRICTION_DRIFT', 1.5)}
                      className="px-3 py-2 rounded-lg bg-purple-950/60 hover:bg-purple-900/80 border border-purple-800 text-purple-200 text-xs text-left font-medium flex items-center justify-between"
                    >
                      <span>Inject Bearing Friction Drift</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                    <button
                      onClick={() => handleInject('FREQUENT_STARTS', 1.0)}
                      className="px-3 py-2 rounded-lg bg-purple-950/60 hover:bg-purple-900/80 border border-purple-800 text-purple-200 text-xs text-left font-medium flex items-center justify-between"
                    >
                      <span>Inject Frequent Starts (&gt; 3/hr)</span>
                      <ArrowRight className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
