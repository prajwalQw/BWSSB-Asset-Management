import React, { useState } from 'react';
import {
  X,
  Zap,
  Activity,
  Gauge,
  Clock,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Sliders,
  Radio,
  MapPin,
  TrendingUp,
  Droplet,
  Waves,
  Building,
  ChevronRight,
  Filter,
  Check
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  AreaChart,
  Area
} from 'recharts';
import {
  PumpTelemetry,
  DeviceTelemetry,
  DivisionBoardSummary,
  StationOverview,
  WardMeterSummary
} from '../types';
import { MeterBoard } from './MeterBoard';
import { lpsToM3h, lpsToMld } from '../../../utils/unitConversion';
import { useIoTStore } from '../store/useIoTStore';

export interface IoTRightInspectorProps {
  selectedType: 'pump' | 'station' | 'stp' | 'flow_sensor' | 'meter' | 'tank' | 'division' | 'device' | null;
  selectedPump?: PumpTelemetry | null;
  selectedStation?: StationOverview | null;
  selectedDevice?: DeviceTelemetry | null;
  selectedDivision?: DivisionBoardSummary | null;
  onClose: () => void;
  onZoomTo?: (coords: [number, number]) => void;
  onSelectPump?: (pumpId: string) => void;
}

// Deterministic telemetry generators for 220px main charts and 96px sparklines
function generatePumpTrend(ratedV: number, ratedI: number, timeRange: string) {
  const points = [];
  const count = timeRange === '15m' ? 15 : timeRange === '1h' ? 24 : 30;
  for (let i = 0; i < count; i++) {
    const isStart = i === 3;
    const inrushMult = isStart ? 2.2 : 1.0;
    const v = ratedV * (isStart ? 0.94 : 0.99) + (Math.sin(i * 0.4) * 6.0);
    const curr = (ratedI * 0.85 * inrushMult) + (Math.sin(i * 0.3) * 2.5);
    points.push({
      time: `${i * (timeRange === '15m' ? 1 : 2)}m`,
      voltage: Math.round(v),
      voltageBandLow: Math.round(ratedV * 0.95),
      voltageBandHigh: Math.round(ratedV * 1.05),
      current: Number(curr.toFixed(1)),
      currentBandLow: Number((ratedI * 0.75).toFixed(1)),
      currentBandHigh: Number((ratedI * 0.95).toFixed(1)),
      isRunning: i >= 3 ? 1 : 0,
      isStartupMarker: isStart
    });
  }
  return points;
}

function generateStationTrend(basePowerKw: number, baseFlowMld: number) {
  const points = [];
  for (let i = 0; i < 24; i++) {
    points.push({
      time: `${i}:00`,
      powerKw: Number((basePowerKw * 0.9 + Math.sin(i * 0.3) * (basePowerKw * 0.12)).toFixed(1)),
      flowMld: Number((baseFlowMld * 0.92 + Math.cos(i * 0.3) * (baseFlowMld * 0.1)).toFixed(1)),
    });
  }
  return points;
}

function generateSensorTrend(baseVal: number, unit: string) {
  const points = [];
  for (let i = 0; i < 20; i++) {
    const val = baseVal + Math.sin(i * 0.5) * (baseVal * 0.06);
    points.push({
      time: `${i * 3}m`,
      value: Number(val.toFixed(1)),
    });
  }
  return points;
}

export const IoTRightInspector: React.FC<IoTRightInspectorProps> = ({
  selectedType,
  selectedPump,
  selectedStation,
  selectedDevice,
  selectedDivision,
  onClose,
  onZoomTo,
  onSelectPump,
}) => {
  const [timeRange, setTimeRange] = useState<'15m' | '1h' | '6h' | '24h'>('1h');
  const [wardSortField, setWardSortField] = useState<'ward_no' | 'flow_lps' | 'volume' | 'alerts'>('flow_lps');
  const [selectedWard, setSelectedWard] = useState<WardMeterSummary | null>(null);

  const store = useIoTStore();
  const effectiveStation = selectedStation || store.selectedStation || (store.stations.length > 0 ? store.stations[0] : null);
  const effectivePump = selectedPump || store.selectedPump || effectiveStation?.pumps?.[0] || null;
  const effectiveDevice = selectedDevice || store.selectedDevice || null;
  const effectiveDivision = selectedDivision || store.selectedDivision || (store.divisions.length > 0 ? store.divisions[0] : null);

  if (!selectedType) {
    return (
      <aside className="w-[380px] border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 p-4 text-xs overflow-y-auto">
        <div className="flex items-center justify-between pb-3 border-b border-slate-200 dark:border-slate-800 mb-3">
          <div className="flex items-center gap-2">
            <Radio className="w-4 h-4 text-sky-500 animate-pulse" />
            <h3 className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
              IoT Telemetry Inspector
            </h3>
          </div>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold">
            SIMULATED
          </span>
        </div>
        <div className="p-6 rounded-xl border border-dashed border-slate-300 dark:border-slate-800 text-center text-slate-400">
          <Gauge className="w-8 h-8 mx-auto mb-2 text-slate-400" />
          <p className="font-medium text-slate-700 dark:text-slate-300">No Asset Selected</p>
          <p className="text-[11px] text-slate-500 mt-1 leading-relaxed">
            Click any pump, pumping station, STP, flow meter, or sensor on the map to inspect live telemetry.
          </p>
        </div>
      </aside>
    );
  }

  // ---------------------------------------------------------------------------
  // 1. PUMP INSPECTOR
  // ---------------------------------------------------------------------------
  if (selectedType === 'pump' && effectivePump) {
    const pumpData = effectivePump;
    const isRunning = pumpData.run_state === 'RUNNING' || pumpData.run_state === 'STARTING';
    const trendData = generatePumpTrend(pumpData.voltage_avg || 415.0, pumpData.current_avg || 110.0, timeRange);
    const flowMld = Number(lpsToMld(pumpData.flow_lps).toFixed(1));
    const dischargePressureBar = Number((pumpData.head_m / 10.2).toFixed(1));

    return (
      <aside className="w-[380px] border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 overflow-y-auto p-4 text-xs space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">
                {pumpData.display_name || `${pumpData.tag} Pump Set`}
              </h3>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold">
                SIMULATED
              </span>
            </div>
            <span className="text-[11px] text-slate-500 font-mono">
              Tag: {pumpData.tag} • Mode: Automatic
            </span>
          </div>
          <button type="button" onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Status Chips */}
        <div className="grid grid-cols-2 gap-2">
          <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
            <span className="text-xs text-slate-500 block">Pump run status</span>
            <div className="flex items-center gap-1.5 mt-1">
              <span
                className={`w-2 h-2 rounded-full ${
                  isRunning ? 'bg-emerald-500' : 'bg-slate-400'
                }`}
              />
              <span className="font-semibold text-slate-800 dark:text-slate-200 text-xs">
                {pumpData.run_state}
              </span>
              <span className="text-[11px] text-slate-500">
                ({isRunning ? 'Active' : 'Not active'})
              </span>
            </div>
          </div>

          <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
            <span className="text-xs text-slate-500 block">Hydraulic output</span>
            <div className="text-slate-800 dark:text-slate-200 font-semibold text-xs mt-1 tabular-nums">
              {pumpData.flow_lps.toFixed(1)} L/s ({dischargePressureBar} bar)
            </div>
          </div>
        </div>

        {/* Value Row: Voltage, Current, Power, PF, Energy, Run Hours */}
        <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-1.5 font-mono text-[11px]">
          <div className="flex justify-between">
            <span className="text-slate-500">Voltage (R/Y/B):</span>
            <span className="tabular-nums font-bold text-slate-700 dark:text-slate-200">
              {pumpData.voltage_r.toFixed(0)} / {pumpData.voltage_y.toFixed(0)} / {pumpData.voltage_b.toFixed(0)} V
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Current (R/Y/B):</span>
            <span className="tabular-nums font-bold text-slate-700 dark:text-slate-200">
              {pumpData.current_r.toFixed(1)} / {pumpData.current_y.toFixed(1)} / {pumpData.current_b.toFixed(1)} A
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Active Power / PF:</span>
            <span className="tabular-nums text-slate-700 dark:text-slate-200">
              {pumpData.active_power_kw.toFixed(1)} kW (PF {pumpData.power_factor.toFixed(2)})
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Cumulative Energy:</span>
            <span className="tabular-nums text-slate-700 dark:text-slate-200">
              {Math.round(pumpData.energy_kwh).toLocaleString()} kWh
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Hydraulic Delivery:</span>
            <span className="tabular-nums text-slate-700 dark:text-slate-200">
              {pumpData.flow_lps.toFixed(1)} L/s ({flowMld} MLD)
            </span>
          </div>
          <div className="flex justify-between pt-1 border-t border-slate-200 dark:border-slate-800">
            <span className="text-slate-500">Run Hours / Starts:</span>
            <span className="tabular-nums text-slate-700 dark:text-slate-200">
              {pumpData.run_hours.toFixed(1)} h ({pumpData.starts_count} starts)
            </span>
          </div>
        </div>

        {/* Time-Range Buttons */}
        <div className="flex items-center justify-between">
          <span className="text-xs font-semibold text-slate-800 dark:text-slate-200">Telemetry Trends</span>
          <div className="flex rounded-md border border-slate-200 dark:border-slate-700 p-0.5 bg-slate-100 dark:bg-slate-800 text-[10px] font-mono">
            {(['15m', '1h', '6h', '24h'] as const).map((r) => (
              <button
                key={r}
                type="button"
                onClick={() => setTimeRange(r)}
                className={`px-2 py-0.5 rounded font-medium transition-all ${
                  timeRange === r
                    ? 'bg-white dark:bg-slate-700 text-slate-900 dark:text-slate-100 shadow-sm font-bold'
                    : 'text-slate-500 hover:text-slate-900 dark:hover:text-slate-300'
                }`}
              >
                {r}
              </button>
            ))}
          </div>
        </div>

        {/* Chart 1: Voltage vs Time (220px fixed height) */}
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 p-2.5 min-w-0" style={{ height: '220px' }}>
          <div className="flex justify-between text-[11px] font-mono mb-1">
            <span className="font-semibold text-emerald-500">Bus Voltage (V)</span>
            <span className="text-[10px] text-slate-400">Normal Band: ±5% (395-435 V)</span>
          </div>
          <div className="w-full h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendData} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
                <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="#64748b" />
                <YAxis tick={{ fontSize: 9 }} stroke="#64748b" domain={['dataMin - 15', 'dataMax + 15']} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '10px' }} />
                <Area type="monotone" dataKey="voltageBandHigh" stroke="none" fill="#10b981" fillOpacity={0.12} />
                <Line type="monotone" dataKey="voltage" stroke="#10b981" strokeWidth={2} dot={false} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 2: Current vs Time (220px fixed height) */}
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 p-2.5 min-w-0" style={{ height: '220px' }}>
          <div className="flex justify-between text-[11px] font-mono mb-1">
            <span className="font-semibold text-sky-500">Motor Current (A)</span>
            <span className="text-[10px] text-slate-400">Start Spike Marker & Normal Band</span>
          </div>
          <div className="w-full h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={trendData} margin={{ top: 5, right: 10, left: -20, bottom: 0 }}>
                <defs>
                  <linearGradient id="currentGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.4} />
                    <stop offset="95%" stopColor="#38bdf8" stopOpacity={0.0} />
                  </linearGradient>
                </defs>
                <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="#64748b" />
                <YAxis tick={{ fontSize: 9 }} stroke="#64748b" domain={['dataMin - 10', 'dataMax + 25']} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '10px' }} />
                <Area type="monotone" dataKey="currentBandHigh" stroke="none" fill="#38bdf8" fillOpacity={0.15} />
                <Area type="monotone" dataKey="current" stroke="#38bdf8" strokeWidth={2} fillOpacity={1} fill="url(#currentGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Thin ON/OFF Strip below both charts */}
        <div className="p-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
          <div className="flex justify-between text-[10px] font-mono text-slate-400 mb-1">
            <span>ON / OFF Step Strip</span>
            <span className="text-emerald-500 font-bold">In Operation</span>
          </div>
          <div className="flex h-2.5 gap-0.5 rounded overflow-hidden">
            {trendData.map((d, i) => (
              <div
                key={i}
                className={`flex-1 ${d.isRunning ? 'bg-emerald-500' : 'bg-slate-700'}`}
                title={`${d.time}: ${d.isRunning ? 'RUNNING' : 'STOPPED'}`}
              />
            ))}
          </div>
        </div>
      </aside>
    );
  }

  // ---------------------------------------------------------------------------
  // 2. PUMPING STATION INSPECTOR
  // ---------------------------------------------------------------------------
  if (selectedType === 'station' && effectiveStation) {
    const stationData = effectiveStation;
    const runningPumps = stationData.pumps.filter((p) => p.run_state === 'RUNNING').length;
    const totalPumps = stationData.pumps.length;
    const totalPowerKw = stationData.total_power_kw ?? stationData.pumps.reduce((acc, p) => acc + (p.run_state === 'RUNNING' ? p.active_power_kw : 0), 0);
    const dischargeFlowMld = stationData.discharge_flow_mld ?? Number(((stationData.pumps.reduce((acc, p) => acc + (p.run_state === 'RUNNING' ? p.flow_lps : 0), 0) * 86.4) / 1000).toFixed(1));
    const stationTrends = generateStationTrend(totalPowerKw || 1200, dischargeFlowMld || 45.0);

    return (
      <aside className="w-[380px] border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 overflow-y-auto p-4 text-xs space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">
                {stationData.name}
              </h3>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold">
                SIMULATED
              </span>
            </div>
            <span className="text-[11px] text-slate-500 font-mono">
              Pumping Station • {totalPumps} Pump Sets
            </span>
          </div>
          <button type="button" onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Summary Row */}
        <div className="grid grid-cols-2 gap-2">
          <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
            <span className="text-xs text-slate-500 block">Pumps running</span>
            <div className="text-base font-bold text-emerald-500 mt-0.5 tabular-nums">
              {runningPumps} <span className="text-xs text-slate-400 font-normal">of {totalPumps}</span>
            </div>
          </div>
          <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
            <span className="text-xs text-slate-500 block">Discharge flow</span>
            <div className="text-base font-bold text-sky-500 mt-0.5 tabular-nums">
              {dischargeFlowMld.toFixed(1)} <span className="text-xs text-slate-400 font-normal">MLD</span>
            </div>
          </div>
          <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
            <span className="text-xs text-slate-500 block">Total power</span>
            <div className="text-base font-bold text-amber-500 mt-0.5 tabular-nums">
              {totalPowerKw.toFixed(1)} <span className="text-xs text-slate-400 font-normal">kW</span>
            </div>
          </div>
          <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
            <span className="text-xs text-slate-500 block">Tank level</span>
            <div className="text-base font-bold text-slate-700 dark:text-slate-200 mt-0.5 tabular-nums">
              {stationData.tank ? `${stationData.tank.level_pct.toFixed(1)}%` : 'Not published'}
            </div>
          </div>
        </div>

        {/* Pump List with 96px Sparklines */}
        <div>
          <span className="font-semibold text-slate-800 dark:text-slate-200 block mb-2">
            Pumping Units (Click to open pump telemetry)
          </span>
          <div className="space-y-2">
            {stationData.pumps.map((pump) => {
              const isPumpRunning = pump.run_state === 'RUNNING';
              const sparklineData = generatePumpTrend(415, pump.current_avg || 110, '15m').slice(0, 10);

              return (
                <button
                  key={pump.pump_id}
                  type="button"
                  onClick={() => onSelectPump && onSelectPump(pump.pump_id)}
                  className="w-full p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30 hover:border-sky-500 text-left transition-all flex flex-col gap-1.5"
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-1.5">
                      <Zap className={`w-3.5 h-3.5 ${isPumpRunning ? 'text-emerald-500' : 'text-slate-400'}`} />
                      <span className="font-semibold text-slate-800 dark:text-slate-200">
                        {pump.display_name || `${pump.tag} Pump`}
                      </span>
                    </div>
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-xs font-bold text-slate-700 dark:text-slate-300 tabular-nums">
                        {pump.active_power_kw.toFixed(1)} kW
                      </span>
                      <span className={`text-[10px] font-mono font-bold px-1.5 py-0.2 rounded ${
                        isPumpRunning ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300' : 'bg-slate-200 dark:bg-slate-800 text-slate-500'
                      }`}>
                        {isPumpRunning ? 'Active' : 'Not active'}
                      </span>
                      <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                    </div>
                  </div>

                  {/* 96px Sparkline */}
                  <div className="w-full min-w-0" style={{ height: '96px' }}>
                    <div className="text-[10px] font-mono text-slate-400 flex justify-between">
                      <span>Current Trend</span>
                      <span className="font-bold text-sky-500">{pump.current_avg.toFixed(1)} A</span>
                    </div>
                    <div className="w-full h-[76px]">
                      <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={sparklineData} margin={{ top: 2, right: 5, left: -25, bottom: 0 }}>
                          <YAxis domain={['dataMin - 5', 'dataMax + 5']} hide />
                          <Line type="monotone" dataKey="current" stroke="#0ea5e9" strokeWidth={1.5} dot={false} />
                        </LineChart>
                      </ResponsiveContainer>
                    </div>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* 220px Main Chart 1: Total Power kW */}
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 p-2.5 min-w-0" style={{ height: '220px' }}>
          <div className="flex justify-between text-[11px] font-mono mb-1">
            <span className="font-semibold text-amber-500">Total Station Power (kW)</span>
            <span className="text-[10px] text-slate-400">24h Profile</span>
          </div>
          <div className="w-full h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stationTrends} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
                <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="#64748b" />
                <YAxis tick={{ fontSize: 9 }} stroke="#64748b" domain={['dataMin - 50', 'dataMax + 50']} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '10px' }} />
                <Line type="monotone" dataKey="powerKw" stroke="#f59e0b" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* 220px Main Chart 2: Discharge Flow MLD */}
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 p-2.5 min-w-0" style={{ height: '220px' }}>
          <div className="flex justify-between text-[11px] font-mono mb-1">
            <span className="font-semibold text-sky-500">Discharge Flow (MLD)</span>
            <span className="text-[10px] text-slate-400">Continuous Bulk Measurement</span>
          </div>
          <div className="w-full h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stationTrends} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
                <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="#64748b" />
                <YAxis tick={{ fontSize: 9 }} stroke="#64748b" domain={['dataMin - 2', 'dataMax + 2']} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '10px' }} />
                <Line type="monotone" dataKey="flowMld" stroke="#38bdf8" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </aside>
    );
  }

  // ---------------------------------------------------------------------------
  // 3. STP (SEWAGE TREATMENT PLANT) INSPECTOR
  // ---------------------------------------------------------------------------
  if (selectedType === 'stp' && selectedStation) {
    const rawDischarge = selectedStation.discharge_flow_mld ?? 32.5;
    const inletMld = Number((rawDischarge * 1.08).toFixed(1));
    const outletMld = Number(rawDischarge.toFixed(1));
    const treatedPct = Number(((outletMld / Math.max(0.1, inletMld)) * 100).toFixed(1));
    const runningEquipment = selectedStation.pumps.filter((p) => p.run_state === 'RUNNING').length;
    const totalEquipment = selectedStation.pumps.length;
    const stpTrends = generateStationTrend(selectedStation.total_power_kw ?? 450, outletMld);

    return (
      <aside className="w-[380px] border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 overflow-y-auto p-4 text-xs space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">
                {selectedStation.name}
              </h3>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-purple-500/10 text-purple-400 border border-purple-500/30 font-bold">
                STP
              </span>
            </div>
            <span className="text-[11px] text-slate-500 font-mono">
              Sewage Treatment Plant • Aerobic Activated Sludge
            </span>
          </div>
          <button type="button" onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Summary Row */}
        <div className="grid grid-cols-2 gap-2">
          <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
            <span className="text-xs text-slate-500 block">Inlet and outlet flow</span>
            <div className="text-sm font-bold text-sky-500 mt-0.5 tabular-nums">
              {inletMld.toFixed(1)} / {outletMld.toFixed(1)} MLD
            </div>
          </div>
          <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
            <span className="text-xs text-slate-500 block">Treatment efficiency</span>
            <div className="text-sm font-bold text-emerald-500 mt-0.5 tabular-nums">
              {treatedPct}% Treated
            </div>
          </div>
        </div>

        {/* Quality Values & Limits */}
        <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-1.5 font-mono text-[11px]">
          <span className="font-sans font-semibold text-slate-800 dark:text-slate-200 block mb-1">
            Effluent Quality & Emission Limits
          </span>
          <div className="flex justify-between">
            <span className="text-slate-500">pH:</span>
            <span className="font-bold text-emerald-600 dark:text-emerald-400">7.3 (Limit: 6.5–8.5)</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Dissolved Oxygen (DO):</span>
            <span className="font-bold text-emerald-600 dark:text-emerald-400">4.5 mg/L (Limit: &gt; 4.0)</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Turbidity:</span>
            <span className="font-bold text-emerald-600 dark:text-emerald-400">1.8 NTU (Limit: &lt; 5.0)</span>
          </div>
        </div>

        {/* Equipment List (Lift pumps & Aeration Blowers) */}
        <div>
          <span className="font-semibold text-slate-800 dark:text-slate-200 block mb-2">
            Active Equipment ({runningEquipment} of {totalEquipment} running)
          </span>
          <div className="space-y-1.5">
            {selectedStation.pumps.map((eq) => {
              const isRunning = eq.run_state === 'RUNNING';
              return (
                <button
                  key={eq.pump_id}
                  type="button"
                  onClick={() => onSelectPump && onSelectPump(eq.pump_id)}
                  className="w-full p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30 hover:border-sky-500 text-left transition-all flex items-center justify-between"
                >
                  <div className="flex items-center gap-2">
                    <Activity className={`w-3.5 h-3.5 ${isRunning ? 'text-emerald-500' : 'text-slate-400'}`} />
                    <span className="font-medium text-slate-800 dark:text-slate-200">
                      {eq.display_name || eq.tag}
                    </span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-xs tabular-nums text-slate-500">
                      {eq.active_power_kw.toFixed(1)} kW
                    </span>
                    <span className={`text-[10px] font-mono font-bold px-1.5 py-0.2 rounded ${
                      isRunning ? 'bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300' : 'bg-slate-200 dark:bg-slate-800 text-slate-500'
                    }`}>
                      {isRunning ? 'Active' : 'Not active'}
                    </span>
                    <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* 220px Trend: Inlet vs Outlet Flow Trend */}
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 p-2.5 min-w-0" style={{ height: '220px' }}>
          <div className="flex justify-between text-[11px] font-mono mb-1">
            <span className="font-semibold text-sky-500">Effluent Flow Trend (MLD)</span>
            <span className="text-[10px] text-slate-400">IS Compliant</span>
          </div>
          <div className="w-full h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={stpTrends} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
                <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="#64748b" />
                <YAxis tick={{ fontSize: 9 }} stroke="#64748b" domain={['dataMin - 2', 'dataMax + 2']} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '10px' }} />
                <Line type="monotone" dataKey="flowMld" stroke="#10b981" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </aside>
    );
  }

  // ---------------------------------------------------------------------------
  // 4. SENSOR INSPECTOR (Flow Meter, Pressure, Level, Quality, Valve, Borewell)
  // ---------------------------------------------------------------------------
  if (selectedType === 'meter' || selectedType === 'flow_sensor' || selectedType === 'device') {
    const dev = effectiveDevice || {
      tag: 'FM-01',
      name: 'Discharge Flow Meter',
      type_code: 'FIT',
      comms_state: 'ONLINE',
      latest_values: { value: 0.0, unit: 'L/s' }
    };

    const isFlowMeter = dev.type_code === 'FIT' || selectedType === 'meter' || selectedType === 'flow_sensor';
    const isPressure = dev.type_code === 'PIT';
    const isLevel = dev.type_code === 'LIT';
    const isQuality = dev.type_code === 'AIT';
    const isValve = dev.type_code === 'VALVE';
    const isBorewell = dev.type_code === 'BOREWELL';
    const isCorridor = dev.type_code === 'CORRIDOR' || dev.type_code === 'PIPE';

    const sensorTrends = generateSensorTrend(dev.latest_values?.value || 50.0, dev.latest_values?.unit || '');
    const currentFlowLps = dev.latest_values?.value || 0.0;

    return (
      <aside className="w-[380px] border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 overflow-y-auto p-4 text-xs space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">
                {dev.name || 'Instrumentation Sensor'}
              </h3>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold">
                SIMULATED
              </span>
            </div>
            <span className="text-[11px] text-slate-500 font-mono">
              Tag: {dev.tag} • Type: {dev.type_code}
            </span>
          </div>
          <button type="button" onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Status Chips: Sensor active / Comms online / Quality */}
        <div className="grid grid-cols-2 gap-2">
          <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
            <span className="text-xs text-slate-500 block">Sensor state</span>
            <div className="flex items-center gap-1.5 mt-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="font-semibold text-slate-800 dark:text-slate-200 text-xs">
                Sensor active
              </span>
            </div>
          </div>

          <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
            <span className="text-xs text-slate-500 block">Comms channel</span>
            <div className="flex items-center gap-1.5 mt-1">
              <span className="w-2 h-2 rounded-full bg-emerald-500" />
              <span className="font-semibold text-slate-800 dark:text-slate-200 text-xs">
                {dev.comms_state || 'ONLINE'} (Good)
              </span>
            </div>
          </div>
        </div>

        {/* Sensor-Specific Readout */}
        {isFlowMeter && (
          <>
            <MeterBoard
              meterId={dev.tag}
              tag={dev.tag}
              name={dev.name}
              flowRateLps={currentFlowLps}
              totaliserKl={451208.5}
              isOnline={true}
              hasAlarm={false}
              isFlowing={currentFlowLps > 0}
              unit="L/s"
              pipeDnMm={800}
            />

            <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-1.5 font-mono text-[11px]">
              <div className="flex justify-between">
                <span className="text-slate-500">Flow in m³/h:</span>
                <span className="font-bold tabular-nums">
                  {lpsToM3h(currentFlowLps).toFixed(1)} m³/h
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Flow in MLD:</span>
                <span className="font-bold text-sky-500 tabular-nums">
                  {lpsToMld(currentFlowLps).toFixed(1)} MLD
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Flow Flags:</span>
                <span className="text-emerald-500 font-bold">Pipe Full • Forward Flow</span>
              </div>
            </div>
          </>
        )}

        {isPressure && (
          <div className="p-3.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-2">
            <span className="text-slate-500 block text-xs">
              Line pressure
            </span>
            <div className="font-mono text-3xl font-bold text-sky-500 tabular-nums">
              {(dev.latest_values?.value || 3.8).toFixed(1)}{' '}
              <span className="text-sm font-normal text-slate-400">bar</span>
            </div>
            <div className="pt-2 border-t border-slate-200 dark:border-slate-800 text-[11px] font-mono text-slate-500 space-y-1">
              <div className="flex justify-between">
                <span>Low Alarm Limit:</span>
                <span className="text-rose-500 font-bold">1.5 bar</span>
              </div>
              <div className="flex justify-between">
                <span>High Alarm Limit:</span>
                <span className="text-amber-500 font-bold">6.0 bar</span>
              </div>
            </div>
          </div>
        )}

        {isLevel && (
          <div className="p-3.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-2">
            <span className="text-slate-500 block text-xs">
              Reservoir and sump water level
            </span>
            <div className="font-mono text-3xl font-bold text-sky-500 tabular-nums">
              {(dev.latest_values?.value || 78.5).toFixed(1)}{' '}
              <span className="text-sm font-normal text-slate-400">%</span>
            </div>
            <div className="text-[11px] font-mono text-slate-500">
              Equivalent Depth: <strong className="text-slate-200">{((dev.latest_values?.value || 78.5) * 0.06).toFixed(1)} m</strong>
            </div>
          </div>
        )}

        {isQuality && (
          <div className="p-3.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-2.5">
            <span className="font-semibold text-slate-800 dark:text-slate-200 block">
              Water Quality (IS 10500:2012 Specifications)
            </span>
            <div className="space-y-1.5 font-mono text-[11px]">
              <div className="flex justify-between py-1 border-b border-slate-200 dark:border-slate-800">
                <span className="text-slate-500">pH:</span>
                <span className="font-bold text-emerald-500 tabular-nums">7.2 pH (Limit: 6.5–8.5)</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-200 dark:border-slate-800">
                <span className="text-slate-500">Turbidity:</span>
                <span className="font-bold text-emerald-500 tabular-nums">0.8 NTU (Acceptable &lt; 1.0, Max 5.0)</span>
              </div>
              <div className="flex justify-between py-1 border-b border-slate-200 dark:border-slate-800">
                <span className="text-slate-500">Free Residual Chlorine:</span>
                <span className="font-bold text-emerald-500 tabular-nums">0.5 mg/L (Min 0.2, Max 1.0)</span>
              </div>
            </div>
            <span className="text-[10px] text-slate-400 block italic">
              Verified against Bureau of Indian Standards IS 10500:2012 Drinking Water Specification.
            </span>
          </div>
        )}

        {isValve && (
          <div className="p-3.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-2">
            <span className="text-slate-500 block text-xs">
              Control valve position
            </span>
            <div className="font-mono text-2xl font-bold text-emerald-500">
              OPEN (100% Open)
            </div>
            <span className="text-[11px] text-slate-400 font-mono block">
              Mode: Remote Supervisory Control
            </span>
          </div>
        )}

        {isBorewell && (
          <div className="p-3.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-2">
            <span className="text-slate-500 block text-xs">
              Borewell extraction package
            </span>
            <div className="space-y-1.5 font-mono text-[11px]">
              <div className="flex justify-between">
                <span className="text-slate-500">Groundwater Depth:</span>
                <span className="font-bold tabular-nums">142.5 m</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Extraction Flow:</span>
                <span className="font-bold text-sky-500 tabular-nums">12.5 L/s</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Submersible Pump:</span>
                <span className="font-bold text-emerald-500">RUNNING</span>
              </div>
            </div>
          </div>
        )}

        {isCorridor && (
          <div className="space-y-3 font-mono text-[11px]">
            <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-2">
              <span className="text-slate-500 font-sans font-semibold block text-xs">
                Hydraulic Pipeline Status
              </span>
              <div className="flex justify-between">
                <span className="text-slate-500">Flow Rate:</span>
                <span className="font-bold text-sky-500 text-sm">{(dev.latest_values?.value ?? 0).toFixed(1)} MLD</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Water Velocity:</span>
                <span className="font-bold text-emerald-500">{((dev.latest_values as any)?.velocity_mps ?? 1.45).toFixed(2)} m/s</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Travel Delay:</span>
                <span className="font-bold text-slate-200">{((dev.latest_values as any)?.travel_delay_min ?? 18.2).toFixed(1)} mins</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Nominal Diameter:</span>
                <span className="font-bold text-slate-200">{(dev.latest_values as any)?.diameter_mm || 1200} mm DI</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-500">Acoustic Leak Risk:</span>
                <span className="font-bold text-emerald-500">LOW (Continuous balance)</span>
              </div>
            </div>
          </div>
        )}

        {/* 220px Trend Chart */}
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 p-2.5 min-w-0" style={{ height: '220px' }}>
          <div className="flex justify-between text-[11px] font-mono mb-1">
            <span className="font-semibold text-sky-500">{dev.name} Trend</span>
            <span className="text-[10px] text-slate-400">Fixed 220px</span>
          </div>
          <div className="w-full h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sensorTrends} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
                <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="#64748b" />
                <YAxis tick={{ fontSize: 9 }} stroke="#64748b" domain={['dataMin - 5', 'dataMax + 5']} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '10px' }} />
                <Line type="monotone" dataKey="value" stroke="#38bdf8" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>
      </aside>
    );
  }

  // ---------------------------------------------------------------------------
  // 5. DIVISION & WARD SMART METER BOARD INSPECTOR (P4)
  // ---------------------------------------------------------------------------
  if (selectedType === 'division' && selectedDivision) {
    if (selectedWard) {
      const avgLps = (selectedWard.daily_baseline_mld * 1e6) / 86400;
      const diurnalProfile = [
        0.45, 0.38, 0.32, 0.35, 0.58, 0.95,
        1.45, 1.62, 1.48, 1.25, 1.10, 1.05,
        0.98, 0.92, 0.88, 0.90, 1.05, 1.35,
        1.55, 1.48, 1.25, 0.95, 0.72, 0.55
      ];
      const wardHourlyTrend = diurnalProfile.map((factor, h) => {
        const hourLabel = `${String(h).padStart(2, '0')}:00`;
        const flow = Number((avgLps * factor).toFixed(1));
        return { hour: hourLabel, flowLps: flow };
      });

      return (
        <aside className="w-[380px] border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 overflow-y-auto p-4 text-xs space-y-4">
          {/* Header with Back Button */}
          <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
            <div>
              <button
                type="button"
                onClick={() => setSelectedWard(null)}
                className="text-sky-500 hover:text-sky-400 font-mono text-[11px] flex items-center gap-1 mb-1 transition-colors"
              >
                ← {selectedDivision.division_name}
              </button>
              <div className="flex items-center gap-2">
                <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">
                  Ward {selectedWard.ward_no}: {selectedWard.ward_name}
                </h3>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold">
                  SIMULATED
                </span>
              </div>
              <span className="text-[11px] text-slate-500 font-mono">
                Tag: {selectedWard.meter_tag} • Zone: {selectedWard.bbmp_zone}
              </span>
            </div>
            <button type="button" onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-600">
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Ward Meter Board (LCD Register) */}
          <MeterBoard
            meterId={selectedWard.meter_tag}
            tag={selectedWard.meter_tag}
            name={`Ward ${selectedWard.ward_no} Consumer Meter`}
            flowRateLps={selectedWard.flow_lps}
            totaliserKl={selectedWard.cumulative_totaliser_kl}
            isOnline={selectedWard.status === 'ONLINE'}
            hasAlarm={selectedWard.flags.length > 0}
            unit="L/s"
            pipeDnMm={300}
          />

          {/* Mandatory Provenance Chip */}
          <div className="p-2 rounded bg-sky-500/10 border border-sky-500/30 text-sky-400 font-mono text-[10.5px] leading-relaxed">
            Daily baseline: real (data.gov.in). Hourly readings: simulated.
          </div>

          {/* Diagnostics: Comms, Battery, Signal */}
          <div className="grid grid-cols-3 gap-2">
            <div className="p-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
              <span className="text-[11px] text-slate-500 block">Comms</span>
              <div className="text-xs font-bold mt-0.5 flex items-center gap-1">
                <span className={`w-2 h-2 rounded-full ${selectedWard.status === 'ONLINE' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                <span className={selectedWard.status === 'ONLINE' ? 'text-emerald-500' : 'text-rose-500'}>
                  {selectedWard.status}
                </span>
              </div>
            </div>

            <div className="p-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
              <span className="text-[11px] text-slate-500 block">Battery</span>
              <div className={`text-xs font-bold mt-0.5 ${selectedWard.battery_pct < 15.0 ? 'text-amber-500 font-bold' : 'text-slate-200'}`}>
                {selectedWard.battery_pct.toFixed(1)}%
              </div>
            </div>

            <div className="p-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
              <span className="text-[11px] text-slate-500 block">Signal</span>
              <div className="text-xs font-bold text-slate-200 mt-0.5">
                {selectedWard.signal_strength_dbm.toFixed(0)} dBm
              </div>
            </div>
          </div>

          {/* Alert Flags / Anomaly Tags */}
          {selectedWard.flags.length > 0 && (
            <div className="p-2.5 rounded-lg border border-rose-500/40 bg-rose-950/20 space-y-1">
              <span className="font-semibold text-rose-400 block text-[11px]">
                Active Smart Meter Anomalies ({selectedWard.flags.length})
              </span>
              <div className="flex flex-wrap gap-1 pt-1">
                {selectedWard.flags.map((flag) => {
                  let badge = { text: flag, color: 'bg-rose-500/20 text-rose-300 border-rose-500/40' };
                  if (flag === 'leak_suspected') badge = { text: 'Suspected Leak (Night Flow Rise)', color: 'bg-rose-500/20 text-rose-300 border-rose-500/40' };
                  if (flag === 'continuous_flow') badge = { text: 'Continuous Flow (24h Runaway)', color: 'bg-amber-500/20 text-amber-300 border-amber-500/40' };
                  if (flag === 'high_usage') badge = { text: 'Unusually High Consumption (>3x MAD)', color: 'bg-amber-500/20 text-amber-300 border-amber-500/40' };
                  if (flag === 'reverse_flow') badge = { text: 'Reverse Flow Detected', color: 'bg-red-600/20 text-red-300 border-red-500/40' };
                  if (flag === 'tamper_event') badge = { text: 'Enclosure Tamper Detected', color: 'bg-purple-500/20 text-purple-300 border-purple-500/40' };
                  if (flag === 'comms_lost') badge = { text: 'LoRaWAN Uplink Timeout', color: 'bg-slate-700 text-slate-300 border-slate-600' };
                  if (flag === 'low_battery') badge = { text: 'Lithium Battery Depleted (<15%)', color: 'bg-amber-500/20 text-amber-300 border-amber-500/40' };
                  return (
                    <span key={flag} className={`px-2 py-0.5 rounded text-[10px] font-mono border ${badge.color}`}>
                      ⚠️ {badge.text}
                    </span>
                  );
                })}
              </div>
            </div>
          )}

          {/* Consumption Metrics */}
          <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-1.5 font-mono text-[11px]">
            <div className="flex justify-between">
              <span className="text-slate-500">Daily Baseline (data.gov.in):</span>
              <span className="font-bold text-slate-200">{selectedWard.daily_baseline_mld.toFixed(2)} MLD</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Today's Cumulative Volume:</span>
              <span className="font-bold text-sky-500">{Math.round(selectedWard.current_day_volume_kl).toLocaleString()} kL</span>
            </div>
            <div className="flex justify-between">
              <span className="text-slate-500">Current Instantaneous Flow:</span>
              <span className="font-bold text-emerald-500">{selectedWard.flow_lps.toFixed(1)} L/s ({((selectedWard.flow_lps * 86.4) / 1000).toFixed(2)} MLD)</span>
            </div>
          </div>

          {/* 220px Hourly Profile Chart */}
          <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 p-2.5 min-w-0" style={{ height: '220px' }}>
            <div className="flex justify-between text-[11px] font-mono mb-1">
              <span className="font-semibold text-sky-500">24-Hour Diurnal Demand Profile</span>
              <span className="text-[10px] text-slate-400">Anchored to {selectedWard.daily_baseline_mld} MLD</span>
            </div>
            <div className="w-full h-[180px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={wardHourlyTrend} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
                  <XAxis dataKey="hour" tick={{ fontSize: 9 }} stroke="#64748b" interval={3} />
                  <YAxis tick={{ fontSize: 9 }} stroke="#64748b" domain={['dataMin - 2', 'dataMax + 2']} />
                  <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '10px' }} />
                  <Line type="monotone" dataKey="flowLps" stroke="#38bdf8" strokeWidth={2} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>
        </aside>
      );
    }

    const sortedWards = [...selectedDivision.wards].sort((a, b) => {
      if (wardSortField === 'flow_lps') return b.flow_lps - a.flow_lps;
      if (wardSortField === 'volume') return b.current_day_volume_kl - a.current_day_volume_kl;
      if (wardSortField === 'alerts') return b.flags.length - a.flags.length;
      return a.ward_no - b.ward_no;
    });

    return (
      <aside className="w-[380px] border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 overflow-y-auto p-4 text-xs space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">
                {selectedDivision.division_name}
              </h3>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold">
                SIMULATED
              </span>
            </div>
            <span className="text-[11px] text-slate-500 font-mono">
              Division Smart Meter Board • {selectedDivision.total_wards} Wards
            </span>
          </div>
          <button type="button" onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Division Meter Face (LCD Style Register) */}
        <MeterBoard
          meterId={`DIV-${selectedDivision.division_name}`}
          tag={`DIV-${selectedDivision.division_name.slice(0, 4).toUpperCase()}`}
          name={`${selectedDivision.division_name} Bulk Supply`}
          flowRateLps={(selectedDivision.inlet_mld * 1e6) / 86400}
          totaliserKl={selectedDivision.cumulative_today_kl}
          isOnline={true}
          unit="L/s"
          pipeDnMm={1200}
        />

        {/* Inflow vs Wards Consumption KPI Box */}
        <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-1.5 font-mono text-[11px]">
          <div className="flex justify-between">
            <span className="text-slate-500">Cumulative Volume Today:</span>
            <span className="font-bold text-slate-200">{Math.round(selectedDivision.cumulative_today_kl).toLocaleString()} kL</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Inlet Bulk Flow:</span>
            <span className="font-bold text-sky-500">{selectedDivision.inlet_mld.toFixed(1)} MLD</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Sum of All Ward Consumption:</span>
            <span className="font-bold text-emerald-500">{selectedDivision.sum_ward_consumption_mld.toFixed(1)} MLD</span>
          </div>
          <div className="flex justify-between pt-1 border-t border-slate-200 dark:border-slate-800">
            <span className="text-slate-500">Apparent Water Loss:</span>
            <span className="font-bold text-amber-500">
              {selectedDivision.apparent_loss_mld.toFixed(1)} MLD ({selectedDivision.apparent_loss_pct.toFixed(1)}%)
            </span>
          </div>
          <div className="flex justify-between pt-1 border-t border-slate-200 dark:border-slate-800">
            <span className="text-slate-500">Wards Operational State:</span>
            <span className="font-bold text-slate-200">
              <span className="text-emerald-500">{selectedDivision.wards_online} online</span> • <span className="text-rose-400">{selectedDivision.wards_offline} offline</span>
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Active Smart Meter Alerts:</span>
            <span className={`font-bold ${selectedDivision.active_alerts_count > 0 ? 'text-amber-400' : 'text-emerald-500'}`}>
              {selectedDivision.active_alerts_count} active
            </span>
          </div>
        </div>

        {/* Sortable Wards Table */}
        <div>
          <div className="flex items-center justify-between pb-1.5 border-b border-slate-200 dark:border-slate-800 mb-2">
            <span className="font-semibold text-slate-800 dark:text-slate-200">
              Constituent Wards ({sortedWards.length})
            </span>
            <div className="flex gap-1 text-[10px] font-mono">
              <button
                type="button"
                onClick={() => setWardSortField('flow_lps')}
                className={`px-1.5 py-0.5 rounded transition-colors ${wardSortField === 'flow_lps' ? 'bg-sky-500 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
              >
                Flow
              </button>
              <button
                type="button"
                onClick={() => setWardSortField('volume')}
                className={`px-1.5 py-0.5 rounded transition-colors ${wardSortField === 'volume' ? 'bg-sky-500 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
              >
                Volume
              </button>
              <button
                type="button"
                onClick={() => setWardSortField('ward_no')}
                className={`px-1.5 py-0.5 rounded transition-colors ${wardSortField === 'ward_no' ? 'bg-sky-500 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
              >
                No.
              </button>
              <button
                type="button"
                onClick={() => setWardSortField('alerts')}
                className={`px-1.5 py-0.5 rounded transition-colors ${wardSortField === 'alerts' ? 'bg-sky-500 text-white font-bold' : 'text-slate-400 hover:text-slate-200'}`}
              >
                Alerts
              </button>
            </div>
          </div>

          <div className="max-h-64 overflow-y-auto space-y-1.5 pr-1">
            {sortedWards.map((w) => (
              <div
                key={w.ward_no}
                onClick={() => setSelectedWard(w)}
                className="p-2.5 rounded-lg border border-slate-200/80 dark:border-slate-800/80 bg-slate-50/50 dark:bg-slate-900/30 hover:border-sky-500 cursor-pointer flex items-center justify-between text-[11px] transition-all group"
              >
                <div className="space-y-0.5">
                  <div className="flex items-center gap-1.5">
                    <span className={`w-1.5 h-1.5 rounded-full ${w.status === 'ONLINE' ? 'bg-emerald-500' : 'bg-rose-500'}`} />
                    <span className="font-semibold text-slate-800 dark:text-slate-200 group-hover:text-sky-400 transition-colors">
                      W-{w.ward_no} {w.ward_name}
                    </span>
                  </div>
                  <div className="flex items-center gap-2 text-[10px] text-slate-400 font-mono">
                    <span>Baseline: {w.daily_baseline_mld.toFixed(2)} MLD</span>
                    <span>•</span>
                    <span>Vol: {Math.round(w.current_day_volume_kl).toLocaleString()} kL</span>
                  </div>
                  {w.flags.length > 0 && (
                    <div className="flex flex-wrap gap-1 pt-0.5">
                      {w.flags.map((f) => (
                        <span key={f} className="px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 text-[9px] font-mono">
                          ⚠️ {f.replace('_', ' ')}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="text-right font-mono flex items-center gap-1.5">
                  <div>
                    <span className="font-bold text-slate-900 dark:text-slate-100 tabular-nums block">
                      {w.flow_lps.toFixed(1)} L/s
                    </span>
                    <span className="text-[10px] text-slate-500">
                      {((w.flow_lps * 86.4) / 1000).toFixed(2)} MLD
                    </span>
                  </div>
                  <ChevronRight className="w-3.5 h-3.5 text-slate-400 group-hover:text-sky-400 transition-colors" />
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>
    );
  }

  // Fallback / Loading / Asset Selector
  return (
    <aside className="w-[380px] border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 p-4 text-xs overflow-y-auto space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
        <div className="flex items-center gap-2">
          <Activity className="w-4 h-4 text-sky-500" />
          <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">Asset Telemetry</h3>
        </div>
        <button type="button" onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-600">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-3.5 rounded-xl border border-sky-500/20 bg-sky-500/5 space-y-2">
        <div className="flex items-center justify-between">
          <span className="font-semibold text-slate-800 dark:text-slate-200 text-xs">
            Digital Twin Telemetry Feed
          </span>
          <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300">
            STREAM ACTIVE
          </span>
        </div>
        <p className="text-[11px] text-slate-500 dark:text-slate-400 leading-relaxed">
          Click any pump, GLR reservoir, or transmission corridor on the map, or select a major facility below to inspect real-time telemetry.
        </p>
      </div>

      {/* Quick Select Stations */}
      {store.stations && store.stations.length > 0 && (
        <div className="space-y-2">
          <span className="text-xs font-semibold text-slate-700 dark:text-slate-300 block">
            Major Facilities ({store.stations.length})
          </span>
          <div className="space-y-1.5">
            {store.stations.slice(0, 5).map((stn) => (
              <button
                key={stn.id}
                type="button"
                onClick={() => {
                  store.setSelectedStation(stn);
                  store.setSelectedInspectorType(stn.station_class === 'stp' ? 'stp' : 'station');
                }}
                className="w-full p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/30 hover:border-sky-500 text-left transition-all flex items-center justify-between"
              >
                <div>
                  <div className="font-medium text-slate-800 dark:text-slate-200">
                    {stn.name}
                  </div>
                  <div className="text-[10px] font-mono text-slate-500">
                    {stn.pumps.length} pumps • {stn.tank ? `Tank: ${stn.tank.level_pct.toFixed(0)}%` : 'Booster'}
                  </div>
                </div>
                <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
              </button>
            ))}
          </div>
        </div>
      )}
    </aside>
  );
};
