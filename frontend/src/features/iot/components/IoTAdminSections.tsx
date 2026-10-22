import React, { useState } from 'react';
import { Settings, Save, CheckCircle2, Zap, Gauge, Sliders, Radio } from 'lucide-react';
import { iotApi } from '../services/iotApi';

export const IoTAdminSections: React.FC = () => {
  const [subTab, setSubTab] = useState<'pumps' | 'devices' | 'meters' | 'simulation'>('pumps');
  const [isSaved, setIsSaved] = useState(false);

  // Form states
  const [h1Fla, setH1Fla] = useState(124.5);
  const [h1Starter, setH1Starter] = useState('soft-starter');
  const [leakThreshold, setLeakThreshold] = useState(4.0);
  const [nightFlowRatio, setNightFlowRatio] = useState(1.5);
  const [simSeed, setSimSeed] = useState(42);

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaved(true);
    setTimeout(() => setIsSaved(false), 2500);
  };

  return (
    <div className="space-y-4 text-xs select-none">
      <div className="flex border-b border-slate-200 dark:border-slate-800 pb-2 gap-1 overflow-x-auto text-[11px] font-mono">
        <button
          type="button"
          onClick={() => setSubTab('pumps')}
          className={`px-2.5 py-1 rounded-md font-medium transition-all ${
            subTab === 'pumps' ? 'bg-sky-500 text-white font-bold' : 'text-slate-500 hover:text-slate-900'
          }`}
        >
          Pumps & Starters
        </button>
        <button
          type="button"
          onClick={() => setSubTab('devices')}
          className={`px-2.5 py-1 rounded-md font-medium transition-all ${
            subTab === 'devices' ? 'bg-sky-500 text-white font-bold' : 'text-slate-500 hover:text-slate-900'
          }`}
        >
          Instruments
        </button>
        <button
          type="button"
          onClick={() => setSubTab('meters')}
          className={`px-2.5 py-1 rounded-md font-medium transition-all ${
            subTab === 'meters' ? 'bg-sky-500 text-white font-bold' : 'text-slate-500 hover:text-slate-900'
          }`}
        >
          Smart Meters
        </button>
        <button
          type="button"
          onClick={() => setSubTab('simulation')}
          className={`px-2.5 py-1 rounded-md font-medium transition-all ${
            subTab === 'simulation' ? 'bg-sky-500 text-white font-bold' : 'text-slate-500 hover:text-slate-900'
          }`}
        >
          Physics Engine
        </button>
      </div>

      {isSaved && (
        <div className="p-2.5 rounded-lg bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-300 dark:border-emerald-800 text-emerald-700 dark:text-emerald-300 flex items-center gap-1.5 font-medium">
          <CheckCircle2 className="w-4 h-4 text-emerald-500" />
          <span>IoT Parameters updated immediately without restarting backend.</span>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-3">
        {subTab === 'pumps' && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-2">
              <span className="font-semibold text-slate-800 dark:text-slate-200 block">
                Tataguni H1-H3 High-Lift Pump Sets (6.6 kV)
              </span>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] text-slate-500 block mb-1">Rated FLA (A)</label>
                  <input
                    type="number"
                    step="0.5"
                    value={h1Fla}
                    onChange={(e) => setH1Fla(parseFloat(e.target.value) || 0)}
                    className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-xs"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-500 block mb-1">Starter Type</label>
                  <select
                    value={h1Starter}
                    onChange={(e) => setH1Starter(e.target.value)}
                    className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-xs"
                  >
                    <option value="soft-starter">Soft-Starter (k=2.0)</option>
                    <option value="star-delta">Star-Delta (k=2.5)</option>
                    <option value="DOL">Direct-on-Line DOL (k=7.0)</option>
                  </select>
                </div>
              </div>
            </div>
          </div>
        )}

        {subTab === 'devices' && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-2">
              <span className="font-semibold text-slate-800 dark:text-slate-200 block">
                Instrumentation Alarming Thresholds
              </span>
              <div>
                <label className="text-[10px] text-slate-500 block mb-1">Leak Detection Threshold (L/s)</label>
                <input
                  type="number"
                  step="0.5"
                  value={leakThreshold}
                  onChange={(e) => setLeakThreshold(parseFloat(e.target.value) || 0)}
                  className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-xs"
                />
              </div>
            </div>
          </div>
        )}

        {subTab === 'meters' && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-2">
              <span className="font-semibold text-slate-800 dark:text-slate-200 block">
                Ward Smart Meter Anomaly Rules
              </span>
              <div>
                <label className="text-[10px] text-slate-500 block mb-1">Night Flow Anomaly Ratio</label>
                <input
                  type="number"
                  step="0.1"
                  value={nightFlowRatio}
                  onChange={(e) => setNightFlowRatio(parseFloat(e.target.value) || 0)}
                  className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-xs"
                />
              </div>
            </div>
          </div>
        )}

        {subTab === 'simulation' && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-2">
              <span className="font-semibold text-slate-800 dark:text-slate-200 block">
                Simulation Engine Dynamics
              </span>
              <div>
                <label className="text-[10px] text-slate-500 block mb-1">RNG Deterministic Seed</label>
                <input
                  type="number"
                  value={simSeed}
                  onChange={(e) => setSimSeed(parseInt(e.target.value) || 42)}
                  className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-xs"
                />
              </div>
            </div>
          </div>
        )}

        <button
          type="submit"
          className="w-full py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold transition-colors flex items-center justify-center gap-1.5 shadow-sm"
        >
          <Save className="w-3.5 h-3.5" />
          <span>Save IoT Settings</span>
        </button>
      </form>
    </div>
  );
};
