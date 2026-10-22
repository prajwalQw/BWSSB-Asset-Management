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
  Droplet
} from 'lucide-react';
import { ResponsiveContainer, LineChart, Line, XAxis, YAxis, Tooltip, AreaChart, Area } from 'recharts';
import { PumpTelemetry, DeviceTelemetry, DivisionBoardSummary } from '../types';
import { MeterBoard } from './MeterBoard';

export interface IoTRightInspectorProps {
  selectedType: 'pump' | 'station' | 'stp' | 'flow_sensor' | 'meter' | 'tank' | 'division' | 'device' | null;
  selectedPump?: PumpTelemetry | null;
  selectedDevice?: DeviceTelemetry | null;
  selectedDivision?: DivisionBoardSummary | null;
  onClose: () => void;
  onZoomTo?: (coords: [number, number]) => void;
}

// Generate realistic mock points for Voltage and Current with normal band and start marker
function generatePumpTrend(ratedV: number, ratedI: number, timeRange: string) {
  const points = [];
  const count = timeRange === '15m' ? 15 : timeRange === '1h' ? 24 : 30;
  for (let i = 0; i < count; i++) {
    const isStart = i === 3;
    const inrushMult = isStart ? 2.0 : 1.0;
    const v = ratedV * (isStart ? 0.94 : 0.99) + (Math.sin(i * 0.4) * 8.0);
    const curr = (ratedI * 0.85 * inrushMult) + (Math.sin(i * 0.3) * 2.5);
    points.push({
      time: `${i * (timeRange === '15m' ? 1 : 2)}m`,
      voltage: Math.round(v),
      voltageBandLow: Math.round(ratedV * 0.95),
      voltageBandHigh: Math.round(ratedV * 1.05),
      current: Math.round(curr * 10) / 10,
      currentBandLow: Math.round(ratedI * 0.75 * 10) / 10,
      currentBandHigh: Math.round(ratedI * 0.95 * 10) / 10,
      isRunning: i >= 3 ? 1 : 0,
      isStartupMarker: isStart
    });
  }
  return points;
}

export const IoTRightInspector: React.FC<IoTRightInspectorProps> = ({
  selectedType,
  selectedPump,
  selectedDevice,
  selectedDivision,
  onClose,
  onZoomTo,
}) => {
  const [timeRange, setTimeRange] = useState<'15m' | '1h' | '6h' | '24h'>('1h');
  const [wardSortField, setWardSortField] = useState<'ward_no' | 'flow_lps'>('flow_lps');

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
        <div className="p-4 rounded-xl border border-dashed border-slate-300 dark:border-slate-800 text-center text-slate-400">
          <Gauge className="w-8 h-8 mx-auto mb-2 text-slate-400" />
          <p className="font-medium text-slate-700 dark:text-slate-300">No Asset Selected</p>
          <p className="text-[11px] text-slate-500 mt-1">
            Click any pump, meter, or sensor on the schematic or map to inspect real-time telemetry.
          </p>
        </div>
      </aside>
    );
  }

  // ---------------------------------------------------------------------------
  // 1. PUMP INSPECTOR
  // ---------------------------------------------------------------------------
  if (selectedType === 'pump' && selectedPump) {
    const isRunning = selectedPump.run_state === 'RUNNING' || selectedPump.run_state === 'STARTING';
    const trendData = generatePumpTrend(selectedPump.voltage_avg || 415.0, selectedPump.current_avg || 110.0, timeRange);

    return (
      <aside className="w-[380px] border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 overflow-y-auto p-4 text-xs space-y-4">
        {/* Header */}
        <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">
                {selectedPump.tag} Pump Set
              </h3>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 font-bold">
                SIMULATED
              </span>
            </div>
            <span className="text-[11px] text-slate-500 font-mono">
              {selectedPump.station_id} • Mode: {selectedPump.auto_control_mode}
            </span>
          </div>
          <button type="button" onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* State Badges */}
        <div className="grid grid-cols-2 gap-2">
          <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
            <span className="text-[10px] text-slate-500 block uppercase font-mono">Pump Run Status</span>
            <div className="flex items-center gap-1.5 mt-1">
              <span
                className={`w-2 h-2 rounded-full ${
                  selectedPump.run_state === 'RUNNING'
                    ? 'bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.8)]'
                    : selectedPump.run_state === 'STARTING'
                    ? 'bg-amber-400 animate-pulse'
                    : selectedPump.run_state === 'TRIPPED'
                    ? 'bg-rose-500'
                    : 'bg-slate-400'
                }`}
              />
              <span className="font-bold text-slate-800 dark:text-slate-200 font-mono">
                {selectedPump.run_state}
              </span>
              <span className="text-[10px] text-slate-500">
                ({isRunning ? 'Active' : 'Not active'})
              </span>
            </div>
          </div>

          <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
            <span className="text-[10px] text-slate-500 block uppercase font-mono">Operating Point</span>
            <div className="font-mono text-slate-800 dark:text-slate-200 font-bold mt-1">
              {selectedPump.flow_lps.toFixed(1)} L/s @ {selectedPump.head_m.toFixed(1)} m
            </div>
          </div>
        </div>

        {/* Electrical & Mechanical KPI Grid */}
        <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-1.5 font-mono text-[11px]">
          <div className="flex justify-between">
            <span className="text-slate-500">Current (R/Y/B):</span>
            <span className="tabular-nums font-bold text-slate-700 dark:text-slate-200">
              {selectedPump.current_r.toFixed(1)} / {selectedPump.current_y.toFixed(1)} / {selectedPump.current_b.toFixed(1)} A
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Voltage (R/Y/B):</span>
            <span className="tabular-nums font-bold text-slate-700 dark:text-slate-200">
              {selectedPump.voltage_r.toFixed(0)} / {selectedPump.voltage_y.toFixed(0)} / {selectedPump.voltage_b.toFixed(0)} V
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Active Power / PF:</span>
            <span className="tabular-nums text-slate-700 dark:text-slate-200">
              {selectedPump.active_power_kw.toFixed(1)} kW (PF {selectedPump.power_factor.toFixed(2)})
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Cumulative Energy:</span>
            <span className="tabular-nums text-slate-700 dark:text-slate-200">
              {Math.round(selectedPump.energy_kwh).toLocaleString()} kWh
            </span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Vibration (RMS):</span>
            <span className="tabular-nums text-slate-700 dark:text-slate-200">
              {selectedPump.vibration_rms_mms.toFixed(2)} mm/s RMS
            </span>
          </div>
          <div className="flex justify-between pt-1 border-t border-slate-200 dark:border-slate-800">
            <span className="text-slate-500">Run Hours / Starts:</span>
            <span className="tabular-nums text-slate-700 dark:text-slate-200">
              {selectedPump.run_hours.toFixed(1)} h ({selectedPump.starts_count} starts)
            </span>
          </div>
        </div>

        {/* Time-Range Selector */}
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

        {/* Current Chart (220px fixed height) */}
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 p-2.5 min-w-0" style={{ height: '220px' }}>
          <div className="flex justify-between text-[11px] font-mono mb-1">
            <span className="font-semibold text-sky-500">Motor Current (A)</span>
            <span className="text-[10px] text-slate-400">Normal Band shaded</span>
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
                <YAxis tick={{ fontSize: 9 }} stroke="#64748b" domain={['dataMin - 10', 'dataMax + 20']} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '10px' }} />
                <Area type="monotone" dataKey="currentBandHigh" stroke="none" fill="#38bdf8" fillOpacity={0.15} />
                <Area type="monotone" dataKey="current" stroke="#38bdf8" strokeWidth={2} fillOpacity={1} fill="url(#currentGrad)" />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Voltage Chart (220px fixed height) */}
        <div className="rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 p-2.5 min-w-0" style={{ height: '220px' }}>
          <div className="flex justify-between text-[11px] font-mono mb-1">
            <span className="font-semibold text-emerald-500">Bus Voltage (V)</span>
            <span className="text-[10px] text-slate-400">Normal: ±5%</span>
          </div>
          <div className="w-full h-[180px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={trendData} margin={{ top: 5, right: 10, left: -15, bottom: 0 }}>
                <XAxis dataKey="time" tick={{ fontSize: 9 }} stroke="#64748b" />
                <YAxis tick={{ fontSize: 9 }} stroke="#64748b" domain={['dataMin - 20', 'dataMax + 20']} />
                <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '10px' }} />
                <Line type="monotone" dataKey="voltage" stroke="#10b981" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* ON/OFF Step Strip */}
        <div className="p-2 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
          <div className="flex justify-between text-[10px] font-mono text-slate-400 mb-1">
            <span>Run State History</span>
            <span className="text-emerald-500 font-bold">100% Availability</span>
          </div>
          <div className="flex h-3 gap-0.5 rounded overflow-hidden">
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
  // 2. FLOW METER / METER BOARD INSPECTOR
  // ---------------------------------------------------------------------------
  if (selectedType === 'meter') {
    return (
      <aside className="w-[380px] border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 overflow-y-auto p-4 text-xs space-y-4">
        <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
          <div>
            <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">Bulk Flow Meter</h3>
            <span className="text-[11px] text-slate-500 font-mono">
              Meter reading: <strong className="text-emerald-500">Online</strong> • Meter: Active
            </span>
          </div>
          <button type="button" onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Real Meter Board Face Component */}
        <MeterBoard
          meterId="FIT-01"
          tag="FIT-TG-01"
          name="Tataguni Discharge Bulk Meter"
          flowRateLps={885.2}
          totaliserKl={451208.5}
          isOnline={true}
          hasAlarm={false}
          isFlowing={true}
          unit="L/s"
          pipeDnMm={800}
        />
      </aside>
    );
  }

  // ---------------------------------------------------------------------------
  // 3. DIVISION SMART METER BOARD INSPECTOR
  // ---------------------------------------------------------------------------
  if (selectedType === 'division' && selectedDivision) {
    const sortedWards = [...selectedDivision.wards].sort((a, b) => {
      if (wardSortField === 'flow_lps') return b.flow_lps - a.flow_lps;
      return a.ward_no - b.ward_no;
    });

    return (
      <aside className="w-[380px] border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 overflow-y-auto p-4 text-xs space-y-4">
        <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
          <div>
            <div className="flex items-center gap-2">
              <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">
                {selectedDivision.division_name}
              </h3>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 font-bold">
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

        {/* Division Meter Face */}
        <MeterBoard
          meterId={`DIV-${selectedDivision.division_name}`}
          tag={`DIV-${selectedDivision.division_name.slice(0, 4).toUpperCase()}`}
          name={`${selectedDivision.division_name} Intake`}
          flowRateLps={(selectedDivision.inlet_mld * 1e6) / 86400}
          totaliserKl={selectedDivision.cumulative_today_kl}
          isOnline={true}
          unit="L/s"
        />

        {/* Inflow vs Wards Consumption KPI Box */}
        <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-1.5 font-mono text-[11px]">
          <div className="flex justify-between">
            <span className="text-slate-500">Division Inlet Flow:</span>
            <span className="font-bold text-sky-600 dark:text-sky-400">{selectedDivision.inlet_mld.toFixed(2)} MLD</span>
          </div>
          <div className="flex justify-between">
            <span className="text-slate-500">Sum of Ward Consumption:</span>
            <span className="font-bold text-emerald-600 dark:text-emerald-400">{selectedDivision.sum_ward_consumption_mld.toFixed(2)} MLD</span>
          </div>
          <div className="flex justify-between pt-1 border-t border-slate-200 dark:border-slate-800">
            <span className="text-slate-500">Apparent Water Loss:</span>
            <span className="font-bold text-amber-500">
              {selectedDivision.apparent_loss_mld.toFixed(2)} MLD ({selectedDivision.apparent_loss_pct.toFixed(1)}%)
            </span>
          </div>
        </div>

        {/* Sortable Wards Table */}
        <div>
          <div className="flex items-center justify-between pb-1.5 border-b border-slate-200 dark:border-slate-800 mb-2">
            <span className="font-semibold text-slate-800 dark:text-slate-200">
              Wards Consumption ({sortedWards.length})
            </span>
            <div className="flex gap-1 text-[10px] font-mono">
              <button
                type="button"
                onClick={() => setWardSortField('flow_lps')}
                className={`px-1.5 py-0.5 rounded ${wardSortField === 'flow_lps' ? 'bg-sky-500 text-white font-bold' : 'text-slate-400'}`}
              >
                By Flow
              </button>
              <button
                type="button"
                onClick={() => setWardSortField('ward_no')}
                className={`px-1.5 py-0.5 rounded ${wardSortField === 'ward_no' ? 'bg-sky-500 text-white font-bold' : 'text-slate-400'}`}
              >
                By No.
              </button>
            </div>
          </div>

          <div className="max-h-60 overflow-y-auto space-y-1 pr-1">
            {sortedWards.map((w) => (
              <div
                key={w.ward_no}
                className="p-2 rounded-lg border border-slate-100 dark:border-slate-800/80 bg-slate-50/50 dark:bg-slate-900/30 flex items-center justify-between text-[11px]"
              >
                <div>
                  <span className="font-semibold text-slate-800 dark:text-slate-200">
                    W-{w.ward_no} {w.ward_name}
                  </span>
                  <span className="block text-[10px] text-slate-400 font-mono">
                    Baseline: {w.daily_baseline_mld} MLD
                  </span>
                </div>
                <div className="text-right font-mono">
                  <span className="font-bold text-slate-900 dark:text-slate-100 tabular-nums block">
                    {w.flow_lps.toFixed(1)} L/s
                  </span>
                  <span className="text-[10px] text-slate-500">
                    {((w.flow_lps * 86.4) / 1000).toFixed(2)} MLD
                  </span>
                </div>
              </div>
            ))}
          </div>
        </div>
      </aside>
    );
  }

  // ---------------------------------------------------------------------------
  // 4. GENERIC SENSOR INSPECTOR (Flow sensor, PIT, Level, Quality, Borewell)
  // ---------------------------------------------------------------------------
  return (
    <aside className="w-[380px] border-l border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col h-full select-none z-20 overflow-y-auto p-4 text-xs space-y-4">
      <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800">
        <div>
          <div className="flex items-center gap-1.5">
            <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">
              {selectedDevice?.name || 'Field Sensor'}
            </h3>
            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 font-bold">
              SIMULATED
            </span>
          </div>
          <span className="text-[11px] text-slate-500 font-mono">
            Sensor: Active • Comms: {selectedDevice?.comms_state || 'ONLINE'}
          </span>
        </div>
        <button type="button" onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-600">
          <X className="w-4 h-4" />
        </button>
      </div>

      <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40">
        <span className="text-slate-500 block uppercase text-[10px] font-mono mb-1">Latest Process Value</span>
        <div className="font-mono text-2xl font-bold text-sky-500">
          {selectedDevice?.latest_values?.value !== undefined ? String(selectedDevice.latest_values.value) : '885.2'}
        </div>
        <span className="text-[10px] text-slate-400 font-mono">
          Last seen: fresh (&lt; 2s) • Quality: Good (OPC-UA)
        </span>
      </div>
    </aside>
  );
};
