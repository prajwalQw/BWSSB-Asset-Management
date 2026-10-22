import React from 'react';
import { Radio, AlertTriangle, Zap, Activity } from 'lucide-react';

export interface MeterBoardProps {
  meterId: string;
  tag: string;
  name: string;
  flowRateLps: number;
  totaliserKl: number;
  isOnline: boolean;
  hasAlarm?: boolean;
  isFlowing?: boolean;
  unit?: string;
  pipeDnMm?: number;
  lastReadingTime?: string;
  batteryPct?: number;
  dataTier?: 'SIMULATED';
}

export const MeterBoard: React.FC<MeterBoardProps> = ({
  meterId,
  tag,
  name,
  flowRateLps,
  totaliserKl,
  isOnline,
  hasAlarm = false,
  isFlowing = true,
  unit = 'L/s',
  pipeDnMm,
  lastReadingTime,
  batteryPct,
  dataTier = 'SIMULATED',
}) => {
  // Format totaliser to 8 digits with leading zeros (e.g. 00045218)
  const integerPart = Math.floor(totaliserKl);
  const totaliserStr = integerPart.toString().padStart(8, '0');
  const digits = totaliserStr.slice(-8).split('');

  return (
    <div className="w-full rounded-xl bg-slate-950 p-3.5 border-2 border-slate-800 shadow-xl text-slate-100 font-sans select-none relative overflow-hidden">
      {/* Decorative Bevel and Screws */}
      <div className="absolute top-1.5 left-2 w-1.5 h-1.5 rounded-full bg-slate-700/80 border border-slate-600" />
      <div className="absolute top-1.5 right-2 w-1.5 h-1.5 rounded-full bg-slate-700/80 border border-slate-600" />
      <div className="absolute bottom-1.5 left-2 w-1.5 h-1.5 rounded-full bg-slate-700/80 border border-slate-600" />
      <div className="absolute bottom-1.5 right-2 w-1.5 h-1.5 rounded-full bg-slate-700/80 border border-slate-600" />

      {/* Top Header: Tag, Name, Simulated Badge */}
      <div className="flex items-center justify-between pb-2 border-b border-slate-800/80 mb-2.5">
        <div className="flex items-center gap-1.5">
          <span className="font-mono text-[11px] font-bold text-sky-400 bg-sky-950/60 px-1.5 py-0.5 rounded border border-sky-800/60">
            {tag}
          </span>
          <span className="text-xs font-semibold text-slate-300 truncate max-w-[170px]" title={name}>
            {name}
          </span>
        </div>
        <span className="text-[10px] font-mono font-bold uppercase tracking-wider px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30">
          {dataTier}
        </span>
      </div>

      {/* Dark LCD Screen Face */}
      <div className="rounded-lg bg-[#08120e] p-3 border border-emerald-950 shadow-inner relative">
        {/* LCD Backlight Glow Effect */}
        <div className="absolute inset-0 bg-emerald-500/[0.03] pointer-events-none rounded-lg" />

        {/* 8-Digit Mechanical/LCD Totaliser Register */}
        <div className="mb-2">
          <div className="flex items-center justify-between text-[10px] text-emerald-600/80 font-mono uppercase tracking-wider mb-1">
            <span>Cumulative Volume</span>
            <span>kL</span>
          </div>
          <div className="flex items-center justify-center gap-1 bg-black/60 p-1.5 rounded border border-emerald-950">
            {digits.map((digit, idx) => (
              <div
                key={idx}
                className="w-5 h-7 rounded bg-slate-900 border border-emerald-900/40 flex items-center justify-center font-mono text-base font-bold text-emerald-400 shadow-sm"
              >
                {digit}
              </div>
            ))}
            <span className="text-xs font-mono font-bold text-emerald-500 ml-1">kL</span>
          </div>
        </div>

        {/* Instantaneous Flow Rate Readout */}
        <div className="flex items-baseline justify-between pt-1 border-t border-emerald-950/60">
          <span className="text-[10px] text-emerald-600/80 font-mono uppercase tracking-wider">
            Flow Rate
          </span>
          <div className="flex items-baseline gap-1">
            <span className="font-mono text-xl font-bold tracking-tight text-emerald-300 tabular-nums">
              {flowRateLps.toFixed(1)}
            </span>
            <span className="font-mono text-xs text-emerald-500 font-semibold">{unit}</span>
          </div>
        </div>
      </div>

      {/* 4 Status LEDs: Power, Comms, Flow, Alarm */}
      <div className="grid grid-cols-4 gap-2 pt-2.5 mt-2.5 border-t border-slate-800/80 text-[10px] font-mono">
        {/* LED 1: Power */}
        <div className="flex flex-col items-center gap-1">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_6px_rgba(16,185,129,0.8)]" />
          <span className="text-slate-400 flex items-center gap-0.5">
            <Zap className="w-2.5 h-2.5" /> PWR
          </span>
        </div>

        {/* LED 2: Comms */}
        <div className="flex flex-col items-center gap-1">
          <div
            className={`w-2.5 h-2.5 rounded-full ${
              isOnline
                ? 'bg-sky-400 shadow-[0_0_6px_rgba(56,189,248,0.8)]'
                : 'bg-slate-700'
            }`}
          />
          <span className="text-slate-400 flex items-center gap-0.5">
            <Radio className="w-2.5 h-2.5" /> COMM
          </span>
        </div>

        {/* LED 3: Flow */}
        <div className="flex flex-col items-center gap-1">
          <div
            className={`w-2.5 h-2.5 rounded-full ${
              isFlowing && flowRateLps > 0.05
                ? 'bg-emerald-400 shadow-[0_0_6px_rgba(52,211,153,0.8)]'
                : 'bg-slate-700'
            }`}
          />
          <span className="text-slate-400 flex items-center gap-0.5">
            <Activity className="w-2.5 h-2.5" /> FLOW
          </span>
        </div>

        {/* LED 4: Alarm */}
        <div className="flex flex-col items-center gap-1">
          <div
            className={`w-2.5 h-2.5 rounded-full ${
              hasAlarm
                ? 'bg-rose-500 animate-pulse shadow-[0_0_8px_rgba(244,63,94,0.9)]'
                : 'bg-slate-700'
            }`}
          />
          <span className="text-slate-400 flex items-center gap-0.5">
            <AlertTriangle className="w-2.5 h-2.5" /> ALM
          </span>
        </div>
      </div>

      {/* Footer Info: Pipe DN, Battery, Last Seen */}
      <div className="flex items-center justify-between pt-2 text-[10px] text-slate-500 font-mono">
        <span>{pipeDnMm ? `DN ${pipeDnMm} mm` : (batteryPct ? `Batt: ${batteryPct}%` : 'Mains Powered')}</span>
        <span>{lastReadingTime || 'Fresh (< 2s)'}</span>
      </div>
    </div>
  );
};
