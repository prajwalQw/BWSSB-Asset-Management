import React, { useEffect, useState } from 'react';
import { Play, Pause, SkipBack, SkipForward, Clock, Moon, Sun, Flame, Droplets } from 'lucide-react';

interface TimelinePlayerProps {
  currentHour: number;
  onHourChange: (hour: number) => void;
  isDarkTheme?: boolean;
}

export const TimelinePlayer: React.FC<TimelinePlayerProps> = ({
  currentHour,
  onHourChange,
  isDarkTheme = true
}) => {
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [speedMultiplier, setSpeedMultiplier] = useState<number>(1); // 1x, 2x, 5x

  useEffect(() => {
    if (!isPlaying) return;
    const intervalMs = 1200 / speedMultiplier;
    const timer = setInterval(() => {
      onHourChange((currentHour + 1) % 24);
    }, intervalMs);
    return () => clearInterval(timer);
  }, [isPlaying, currentHour, speedMultiplier]);

  // Diurnal operational stage tag
  const getDiurnalStage = (h: number) => {
    if (h >= 2 && h <= 4) {
      return { label: 'MNF Window (Night Flow Leak Analysis)', color: 'text-purple-400', icon: Moon };
    }
    if (h >= 7 && h <= 10) {
      return { label: 'Morning Peak Demand (High Feeder Velocity)', color: 'text-amber-400', icon: Flame };
    }
    if (h >= 18 && h <= 21) {
      return { label: 'Evening Peak Demand', color: 'text-orange-400', icon: Droplets };
    }
    if (h >= 22 || h <= 1) {
      return { label: 'Nocturnal Tank Storage Refill', color: 'text-cyan-400', icon: Clock };
    }
    return { label: 'Midday Operating Baseline', color: 'text-blue-400', icon: Sun };
  };

  const stage = getDiurnalStage(currentHour);
  const StageIcon = stage.icon;

  return (
    <div className={`absolute bottom-6 left-1/2 -translate-x-1/2 z-30 px-5 py-3 rounded-2xl border shadow-2xl backdrop-blur-xl flex flex-col gap-2 font-sans transition-all w-[540px] max-w-[92vw] ${
      isDarkTheme 
        ? 'bg-slate-900/90 border-slate-800 text-slate-100 shadow-slate-950/80' 
        : 'bg-white/95 border-slate-200 text-slate-900 shadow-slate-300'
    }`}>
      {/* Upper Meta: Current Time + Operational Stage */}
      <div className="flex items-center justify-between font-mono text-xs">
        <div className="flex items-center gap-2">
          <Clock className="w-3.5 h-3.5 text-cyan-400" />
          <span className="font-bold text-sm tracking-tight">
            {currentHour.toString().padStart(2, '0')}:00 {currentHour < 12 ? 'AM' : 'PM'}
          </span>
          <span className="text-[10px] text-slate-400">(Step {currentHour + 1} / 24)</span>
        </div>

        <div className={`flex items-center gap-1.5 text-[11px] font-medium ${stage.color}`}>
          <StageIcon className="w-3.5 h-3.5" />
          <span>{stage.label}</span>
        </div>
      </div>

      {/* Center Controls + Slider */}
      <div className="flex items-center gap-3">
        {/* Playback Controls */}
        <div className="flex items-center gap-1">
          <button
            onClick={() => onHourChange((currentHour - 1 + 24) % 24)}
            className={`p-1.5 rounded-lg transition-colors ${
              isDarkTheme ? 'hover:bg-slate-800 text-slate-400 hover:text-white' : 'hover:bg-slate-100 text-slate-600 hover:text-slate-900'
            }`}
            title="Previous Hour"
          >
            <SkipBack className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={() => setIsPlaying(!isPlaying)}
            className={`p-2 rounded-xl transition-all shadow-md flex items-center justify-center ${
              isPlaying 
                ? 'bg-amber-600 hover:bg-amber-500 text-white' 
                : 'bg-cyan-600 hover:bg-cyan-500 text-white'
            }`}
            title={isPlaying ? 'Pause Replay' : 'Play 24h Hydraulic Cycle'}
          >
            {isPlaying ? <Pause className="w-4 h-4 fill-current" /> : <Play className="w-4 h-4 fill-current ml-0.5" />}
          </button>

          <button
            onClick={() => onHourChange((currentHour + 1) % 24)}
            className={`p-1.5 rounded-lg transition-colors ${
              isDarkTheme ? 'hover:bg-slate-800 text-slate-400 hover:text-white' : 'hover:bg-slate-100 text-slate-600 hover:text-slate-900'
            }`}
            title="Next Hour"
          >
            <SkipForward className="w-3.5 h-3.5" />
          </button>
        </div>

        {/* 24-Hour Slider */}
        <div className="flex-1 flex items-center relative">
          <input
            type="range"
            min={0}
            max={23}
            step={1}
            value={currentHour}
            onChange={(e) => onHourChange(Number(e.target.value))}
            className="w-full h-1.5 bg-slate-700/60 rounded-lg appearance-none cursor-pointer accent-cyan-500"
          />
        </div>

        {/* Speed Multiplier Pill */}
        <div className="flex items-center gap-1 font-mono text-[10px]">
          {[1, 2, 5].map((spd) => (
            <button
              key={spd}
              onClick={() => setSpeedMultiplier(spd)}
              className={`px-1.5 py-0.5 rounded font-bold transition-all ${
                speedMultiplier === spd
                  ? 'bg-cyan-600 text-white'
                  : (isDarkTheme ? 'text-slate-400 hover:bg-slate-800' : 'text-slate-600 hover:bg-slate-200')
              }`}
            >
              {spd}x
            </button>
          ))}
        </div>
      </div>
    </div>
  );
};
