import React, { useState, useEffect } from 'react';
import { Play, Pause, FastForward, Clock } from 'lucide-react';
import { sseManager } from '../../services/sseManager';

export const SimClockControl: React.FC = () => {
  const [isPaused, setIsPaused] = useState(false);
  const [speed, setSpeed] = useState<1 | 60 | 600>(1);
  const [simClock, setSimClock] = useState('06:00');

  useEffect(() => {
    const unsub = sseManager.subscribe('plan', (data: any) => {
      if (data?.water_movement?.clock_str) {
        setSimClock(data.water_movement.clock_str);
      }
      if (typeof data?.water_movement?.is_paused === 'boolean') {
        setIsPaused(data.water_movement.is_paused);
      }
      if (data?.water_movement?.speed_multiplier) {
        setSpeed(data.water_movement.speed_multiplier);
      }
    });

    const unsubTele = sseManager.subscribe('telemetry', (data: any) => {
      if (data?.clock_utc) {
        // Format HH:MM from clock_utc (e.g. 2026-10-22T06:15:00Z)
        const parts = data.clock_utc.split('T');
        if (parts[1]) {
          setSimClock(parts[1].slice(0, 5));
        }
      }
    });

    return () => {
      unsub();
      unsubTele();
    };
  }, []);

  const updateClock = async (newSpeed: 1 | 60 | 600, newPaused: boolean) => {
    try {
      setSpeed(newSpeed);
      setIsPaused(newPaused);
      await fetch('/api/v1/iot/sim/clock', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ speed: newSpeed, paused: newPaused })
      });
    } catch {
      // ignore
    }
  };

  return (
    <div className="flex items-center gap-1.5 px-2 py-1 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/60 text-xs font-mono select-none">
      <div className="flex items-center gap-1 text-sky-500 font-bold tabular-nums pr-1 border-r border-slate-200 dark:border-slate-800">
        <Clock className="w-3.5 h-3.5" />
        <span>{simClock}</span>
      </div>

      <button
        type="button"
        onClick={() => updateClock(speed, !isPaused)}
        className={`p-1 rounded transition-colors ${
          isPaused
            ? 'bg-amber-500/20 text-amber-500 hover:bg-amber-500/30'
            : 'bg-emerald-500/20 text-emerald-500 hover:bg-emerald-500/30'
        }`}
        title={isPaused ? 'Resume Simulation' : 'Pause Simulation'}
      >
        {isPaused ? <Play className="w-3 h-3 fill-current" /> : <Pause className="w-3 h-3 fill-current" />}
      </button>

      <div className="flex items-center gap-0.5">
        {([1, 60, 600] as const).map((s) => (
          <button
            key={s}
            type="button"
            onClick={() => updateClock(s, isPaused)}
            className={`px-1.5 py-0.5 rounded text-[10px] font-bold transition-colors ${
              speed === s
                ? 'bg-sky-600 text-white shadow-sm'
                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-800'
            }`}
          >
            {s}x
          </button>
        ))}
      </div>
    </div>
  );
};
