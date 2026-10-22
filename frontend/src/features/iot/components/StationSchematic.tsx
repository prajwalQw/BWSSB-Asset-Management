import React from 'react';
import { StationOverview, PumpTelemetry } from '../types';
import { Zap, Activity, Radio, Droplet, ArrowRight, Gauge } from 'lucide-react';

export interface StationSchematicProps {
  station: StationOverview;
  onSelectElement: (type: 'pump' | 'flow_sensor' | 'meter' | 'tank', id: string) => void;
  selectedElementId?: string;
}

export const StationSchematic: React.FC<StationSchematicProps> = ({
  station,
  onSelectElement,
  selectedElementId,
}) => {
  const { pumps, tank } = station;

  return (
    <div className="w-full h-full bg-slate-950 p-6 flex flex-col select-none overflow-y-auto">
      {/* Schematic Header */}
      <div className="flex items-center justify-between pb-4 border-b border-slate-800 mb-6">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-slate-100">{station.name}</h2>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-sky-950 text-sky-400 border border-sky-800 font-semibold uppercase">
              {station.station_class}
            </span>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 font-bold">
              SIMULATED
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Process & Instrumentation Diagram: Pump Array → Flow Sensors → Bulk Meters → Balancing Tank
          </p>
        </div>
        <div className="text-right text-xs font-mono text-slate-400">
          <div>Tank Level: <span className="text-emerald-400 font-bold">{tank.level_pct.toFixed(1)}%</span> ({tank.level_m.toFixed(2)} m)</div>
          <div>Total Inflow: <span className="text-sky-400 font-bold">{tank.inflow_lps.toFixed(1)} L/s</span></div>
        </div>
      </div>

      {/* Main Process Topology Flow: Rows of Pumps feeding common header to Tank */}
      <div className="grid grid-cols-[1fr_auto_280px] gap-6 items-center flex-1">
        {/* Left: Pump Train Branches (Pump -> Flow Sensor -> Flow Meter) */}
        <div className="flex flex-col gap-4">
          {pumps.map((p, idx) => {
            const isSelected = selectedElementId === p.pump_id;
            const isRunning = p.run_state === 'RUNNING' || p.run_state === 'STARTING';
            const statusColor =
              p.run_state === 'RUNNING'
                ? 'emerald'
                : p.run_state === 'STARTING'
                ? 'amber'
                : p.run_state === 'TRIPPED'
                ? 'rose'
                : 'slate';

            return (
              <div
                key={p.pump_id}
                className="flex items-center gap-3 p-3 rounded-xl bg-slate-900/80 border border-slate-800 shadow-lg relative overflow-hidden"
              >
                {/* 1. IoT Board Glyph (V, I, State) */}
                <button
                  type="button"
                  onClick={() => onSelectElement('pump', p.pump_id)}
                  className={`w-40 p-2.5 rounded-lg border text-left transition-all flex flex-col justify-between ${
                    isSelected
                      ? 'border-sky-500 bg-sky-950/40'
                      : 'border-slate-800 bg-slate-950/80 hover:border-slate-700'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1.5">
                    <span className="font-mono text-xs font-bold text-sky-400">IOT-{p.tag}</span>
                    <span
                      className={`text-[10px] font-mono px-1.5 py-0.2 rounded font-bold uppercase ${
                        p.run_state === 'RUNNING'
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800'
                          : p.run_state === 'STARTING'
                          ? 'bg-amber-950 text-amber-400 border border-amber-800 animate-pulse'
                          : p.run_state === 'TRIPPED'
                          ? 'bg-rose-950 text-rose-400 border border-rose-800'
                          : 'bg-slate-800 text-slate-400'
                      }`}
                    >
                      {p.run_state}
                    </span>
                  </div>

                  <div className="grid grid-cols-2 gap-1 text-[11px] font-mono">
                    <div className="flex justify-between">
                      <span className="text-slate-500">I avg:</span>
                      <span className="text-slate-200 font-bold tabular-nums">{p.current_avg.toFixed(1)} A</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">V avg:</span>
                      <span className="text-slate-200 tabular-nums">{p.voltage_avg.toFixed(0)} V</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">Power:</span>
                      <span className="text-slate-200 tabular-nums">{p.active_power_kw.toFixed(1)} kW</span>
                    </div>
                    <div className="flex justify-between">
                      <span className="text-slate-500">PF:</span>
                      <span className="text-slate-200 tabular-nums">{p.power_factor.toFixed(2)}</span>
                    </div>
                  </div>

                  <div className="text-[10px] text-slate-500 mt-1 flex justify-between border-t border-slate-800/60 pt-1">
                    <span>Mode: <strong className="text-slate-400">Automatic</strong></span>
                    <span>Vib: {p.vibration_rms_mms.toFixed(1)} mm/s</span>
                  </div>
                </button>

                {/* Arrow to Pump Element */}
                <ArrowRight className="w-4 h-4 text-slate-600 flex-shrink-0" />

                {/* 2. Pump Glyphs */}
                <button
                  type="button"
                  onClick={() => onSelectElement('pump', p.pump_id)}
                  className={`w-28 p-2 rounded-lg border text-center transition-all ${
                    isSelected
                      ? 'border-sky-500 bg-sky-950/40'
                      : 'border-slate-800 bg-slate-950 hover:border-slate-700'
                  }`}
                >
                  <div className="w-10 h-10 mx-auto rounded-full border-2 border-slate-700 bg-slate-900 flex items-center justify-center mb-1">
                    <Zap className={`w-5 h-5 ${isRunning ? 'text-emerald-400 animate-pulse' : 'text-slate-600'}`} />
                  </div>
                  <span className="font-mono text-xs font-bold text-slate-200 block">{p.tag} Pump</span>
                  <span className="text-[10px] text-slate-400 font-mono">{p.head_m.toFixed(1)} m head</span>
                </button>

                {/* Pipe Line Connector */}
                <div className="flex-1 h-1.5 bg-slate-800 relative min-w-[24px]">
                  {isRunning && (
                    <div className="absolute inset-0 bg-sky-500/80 animate-pulse" />
                  )}
                </div>

                {/* 3. Flow Sensor Element */}
                <button
                  type="button"
                  onClick={() => onSelectElement('flow_sensor', `FIT_${station.id}_${p.tag}_SEN`)}
                  className="w-24 p-2 rounded-lg border border-slate-800 bg-slate-950 text-center hover:border-slate-700 transition-all"
                  title="Electromagnetic Flow Sensor Element"
                >
                  <Activity className="w-4 h-4 text-sky-400 mx-auto mb-0.5" />
                  <span className="font-mono text-[10px] text-slate-400 block">Sensor</span>
                  <span className="font-mono text-[11px] font-bold text-sky-300">
                    {p.flow_lps.toFixed(1)} <span className="text-[9px]">L/s</span>
                  </span>
                </button>

                {/* Pipe Line Connector */}
                <div className="flex-1 h-1.5 bg-slate-800 relative min-w-[24px]">
                  {isRunning && (
                    <div className="absolute inset-0 bg-sky-500/80 animate-pulse" />
                  )}
                </div>

                {/* 4. Bulk Flow Meter */}
                <button
                  type="button"
                  onClick={() => onSelectElement('meter', `FIT_${station.id}_${p.tag}`)}
                  className="w-32 p-2 rounded-lg border border-slate-800 bg-slate-950 text-center hover:border-slate-700 transition-all"
                  title="Electromagnetic Bulk Flow Meter with Register"
                >
                  <Gauge className="w-4 h-4 text-emerald-400 mx-auto mb-0.5" />
                  <span className="font-mono text-[10px] text-slate-400 block">FIT-{p.tag}</span>
                  <span className="font-mono text-xs font-bold text-emerald-300">
                    {p.flow_lps.toFixed(1)} L/s
                  </span>
                  <span className="text-[9px] text-slate-500 font-mono block">
                    {((p.flow_lps * 86.4) / 1000).toFixed(2)} MLD
                  </span>
                </button>
              </div>
            );
          })}
        </div>

        {/* Middle: Common Header Manifold */}
        <div className="h-full flex items-center px-3">
          <div className="w-2 h-4/5 bg-slate-700 rounded-full flex flex-col justify-between items-center py-2 relative shadow-md">
            <span className="text-[9px] font-mono text-slate-400 uppercase -rotate-90 whitespace-nowrap">
              Common Discharge Manifold
            </span>
          </div>
          <ArrowRight className="w-5 h-5 text-sky-400 ml-2" />
        </div>

        {/* Right: Balancing Tank / Reservoir */}
        <div
          onClick={() => onSelectElement('tank', tank.tank_id)}
          className={`p-4 rounded-xl border cursor-pointer transition-all flex flex-col items-center justify-between min-h-[300px] ${
            selectedElementId === tank.tank_id
              ? 'border-sky-500 bg-sky-950/30'
              : 'border-slate-800 bg-slate-900/60 hover:border-slate-700'
          }`}
        >
          <div className="flex items-center gap-2 mb-3">
            <Droplet className="w-5 h-5 text-sky-400" />
            <h3 className="text-xs font-bold text-slate-200">{tank.name}</h3>
          </div>

          {/* Graphical Tank Column with Liquid Fill */}
          <div className="w-32 h-44 rounded-xl border-2 border-slate-700 bg-slate-950 relative overflow-hidden flex flex-col justify-end p-1 shadow-inner">
            {/* Level Scale Ticks */}
            <div className="absolute top-2 left-1.5 text-[9px] font-mono text-slate-500">100%</div>
            <div className="absolute top-1/2 left-1.5 -translate-y-1/2 text-[9px] font-mono text-slate-500">50%</div>
            <div className="absolute bottom-2 left-1.5 text-[9px] font-mono text-slate-500">0%</div>

            {/* Setpoint Reference Marker Lines */}
            <div
              className="absolute left-0 right-0 border-t border-dashed border-amber-500/80 z-10"
              style={{ bottom: `${tank.level_pct}%` }}
              title={`Current: ${tank.level_pct}%`}
            />

            {/* Animated Water Liquid */}
            <div
              className="w-full bg-gradient-to-t from-sky-700 to-sky-500 rounded-lg transition-all duration-700 relative overflow-hidden"
              style={{ height: `${tank.level_pct}%` }}
            >
              <div className="absolute inset-0 bg-white/10 animate-pulse" />
            </div>
          </div>

          {/* Tank Level Figures */}
          <div className="w-full mt-3 text-center">
            <div className="font-mono text-xl font-bold text-slate-100">
              {tank.level_pct.toFixed(1)}%
            </div>
            <div className="text-[11px] font-mono text-slate-400">
              {tank.level_m.toFixed(2)} m / {tank.height_m.toFixed(1)} m
            </div>
            <div className="text-[10px] text-slate-500 font-mono mt-1">
              Vol: {Math.round(tank.volume_m3).toLocaleString()} m³ / {tank.capacity_m3.toLocaleString()} m³
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
