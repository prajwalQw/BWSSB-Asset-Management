import React, { useState } from 'react';
import { ChevronDown, ChevronUp, Layers, Droplet, Activity, Gauge, Zap } from 'lucide-react';
import { BasemapTheme, MAP_THEMES } from '../../map/theme';

interface MapLegendProps {
  theme: BasemapTheme;
}

export const MapLegend: React.FC<MapLegendProps> = ({ theme }) => {
  const [isOpen, setIsOpen] = useState(false);
  const currentTheme = MAP_THEMES[theme];

  return (
    <div className="absolute bottom-8 left-4 z-20 font-sans text-xs select-none">
      <div
        className={`rounded-2xl border shadow-2xl backdrop-blur-md transition-all overflow-hidden ${
          theme === 'light'
            ? 'bg-white/95 border-slate-200 text-slate-800 shadow-slate-300'
            : 'bg-slate-900/95 border-slate-800 text-slate-200 shadow-black/60'
        }`}
      >
        {/* Collapsible Header */}
        <button
          onClick={() => setIsOpen(!isOpen)}
          className={`w-full px-3.5 py-2.5 flex items-center justify-between gap-3 text-left font-mono font-semibold transition-colors ${
            theme === 'light' ? 'hover:bg-slate-100' : 'hover:bg-slate-800/80'
          }`}
          title="Toggle Symbology & Engineering Legend"
        >
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-cyan-400" />
            <span className="text-[11px] tracking-tight uppercase">Network Legend</span>
          </div>
          {isOpen ? (
            <ChevronDown className="w-3.5 h-3.5 text-slate-400" />
          ) : (
            <ChevronUp className="w-3.5 h-3.5 text-slate-400" />
          )}
        </button>

        {/* Legend Content */}
        {isOpen && (
          <div className="p-3.5 pt-1 space-y-3.5 max-h-[380px] w-64 overflow-y-auto text-[11px]">
            {/* 1. Pipe Diameters */}
            <div className="space-y-1.5">
              <span className="font-mono text-[10px] uppercase font-bold text-slate-400 block tracking-wider">
                Transmission & Mains
              </span>
              <div className="space-y-1.5 font-mono text-[10px]">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-2 rounded bg-cyan-400 border border-slate-900" />
                    <span>Trunk Mains (&ge;600mm)</span>
                  </div>
                  <span className="text-slate-400">Core+Casing</span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-1.5 rounded bg-cyan-500 border border-slate-900" />
                    <span>Mains (300-600mm)</span>
                  </div>
                  <span className="text-slate-400">Scaled</span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-1 rounded bg-cyan-600 border border-slate-900" />
                    <span>Minor Lines (&lt;300mm)</span>
                  </div>
                  <span className="text-slate-400">Distribution</span>
                </div>
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <div className="w-6 h-1.5 rounded border border-dashed border-amber-600 bg-amber-800/40" />
                    <span>Sewer Lines</span>
                  </div>
                  <span className="text-slate-400">Olive Dashed</span>
                </div>
              </div>
            </div>

            {/* 2. P&ID Asset Symbology */}
            <div className="space-y-1.5 pt-2 border-t border-slate-700/50">
              <span className="font-mono text-[10px] uppercase font-bold text-slate-400 block tracking-wider">
                Asset Symbology (P&amp;ID / ISA)
              </span>
              <div className="grid grid-cols-1 gap-1.5">
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-950 border border-cyan-400 flex items-center justify-center text-[9px] font-bold text-cyan-400">
                    W
                  </div>
                  <span>Water Treatment Works (WTP)</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-950 border border-emerald-400 flex items-center justify-center text-[9px] font-bold text-emerald-400">
                    PS
                  </div>
                  <span>Pumping Station</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-950 border border-emerald-400 flex items-center justify-center text-[9px] font-bold text-emerald-300">
                    P
                  </div>
                  <span>Pump Unit (Motor+Volute)</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-950 border border-purple-400 flex items-center justify-center text-[9px] font-bold text-purple-400">
                    S
                  </div>
                  <span>Sewage Treatment (STP)</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-950 border border-sky-400 flex items-center justify-center text-[9px] font-bold text-sky-400">
                    T
                  </div>
                  <span>GLR / Balancing Tank</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-950 border border-blue-500 flex items-center justify-center text-[9px] font-bold text-blue-400">
                    B
                  </div>
                  <span>Public Borewell</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-950 border border-cyan-400 flex items-center justify-center text-[9px] font-bold text-cyan-300">
                    FM
                  </div>
                  <span>Electromagnetic Flow Meter</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-950 border border-amber-400 flex items-center justify-center text-[9px] font-bold text-amber-300">
                    PT
                  </div>
                  <span>Pressure Transmitter</span>
                </div>
                <div className="flex items-center gap-2.5">
                  <div className="w-5 h-5 rounded-full bg-slate-950 border border-emerald-500 flex items-center justify-center text-[9px] font-bold text-emerald-400">
                    &#x22C8;
                  </div>
                  <span>Isolation Valve (Open / Closed)</span>
                </div>
              </div>
            </div>

            {/* 3. Operational Status Rings */}
            <div className="space-y-1.5 pt-2 border-t border-slate-700/50">
              <span className="font-mono text-[10px] uppercase font-bold text-slate-400 block tracking-wider">
                Status Rings
              </span>
              <div className="grid grid-cols-2 gap-1.5 font-mono text-[10px]">
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 ring-2 ring-emerald-500/30" />
                  <span>Normal</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-amber-500 ring-2 ring-amber-500/30" />
                  <span>Watch</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-rose-500 ring-2 ring-rose-500/30 animate-pulse" />
                  <span>Alert</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="w-2.5 h-2.5 rounded-full bg-slate-500 ring-2 ring-slate-500/30" />
                  <span>No Data</span>
                </div>
              </div>
            </div>

            {/* 4. Data Provenance Tiers */}
            <div className="space-y-1.5 pt-2 border-t border-slate-700/50">
              <span className="font-mono text-[10px] uppercase font-bold text-slate-400 block tracking-wider">
                Data Provenance Tiers
              </span>
              <div className="space-y-1 font-mono text-[10px]">
                <div className="flex items-center gap-2">
                  <span className="px-1.5 py-0.2 rounded bg-cyan-950 border border-cyan-800 text-cyan-300 font-bold">
                    REAL
                  </span>
                  <span>Verified BWSSB GIS Records</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-1.5 py-0.2 rounded bg-purple-950 border border-purple-800 text-purple-300 font-bold">
                    SIM
                  </span>
                  <span>EPANET / WNTR Simulated</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="px-1.5 py-0.2 rounded bg-emerald-950 border border-emerald-800 text-emerald-300 font-bold">
                    LIVE
                  </span>
                  <span>Authentic IGNOAPI SCADA</span>
                </div>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
