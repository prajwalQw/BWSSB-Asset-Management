import React, { useState } from 'react';
import { Settings, Save, CheckCircle2, Zap, Gauge, Sliders, Radio } from 'lucide-react';
import { iotApi } from '../services/iotApi';

export const IoTAdminSections: React.FC = () => {
  const [subTab, setSubTab] = useState<'pumps' | 'names' | 'devices' | 'meters' | 'simulation'>('names');
  const [isSaved, setIsSaved] = useState(false);

  // Form states
  const [pump1Name, setPump1Name] = useState('High-Lift Pump 1');
  const [pump2Name, setPump2Name] = useState('High-Lift Pump 2');
  const [pump3Name, setPump3Name] = useState('High-Lift Pump 3');
  const [fit1Name, setFit1Name] = useState('Discharge Flow Meter');
  const [pit1Name, setPit1Name] = useState('Discharge Pressure');
  const [lit1Name, setLit1Name] = useState('Balancing Reservoir Tank Level');

  const [pumpFla, setPumpFla] = useState(124.5);
  const [pumpStarter, setPumpStarter] = useState('soft-starter');
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
      <div className="flex border-b border-slate-200 dark:border-slate-800 pb-2 gap-1 overflow-x-auto text-[11px]">
        <button
          type="button"
          onClick={() => setSubTab('names')}
          className={`px-2.5 py-1 rounded-md font-medium transition-all ${
            subTab === 'names' ? 'bg-sky-500 text-white font-bold' : 'text-slate-500 hover:text-slate-900'
          }`}
        >
          Display Names
        </button>
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
          <span>IoT Display Names and parameters saved successfully.</span>
        </div>
      )}

      <form onSubmit={handleSave} className="space-y-3">
        {subTab === 'names' && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-2.5">
              <span className="font-semibold text-slate-800 dark:text-slate-200 block text-xs">
                Asset & Instrument Display Names
              </span>
              <p className="text-[11px] text-slate-500">
                Configure human-readable display names shown in UI headings. Raw tags appear as small secondary text.
              </p>

              <div className="space-y-2 pt-1">
                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] text-slate-600 dark:text-slate-400 font-medium">Pump 1 Display Name</label>
                    <span className="text-[10px] font-mono text-slate-400">[TG-HLP-01]</span>
                  </div>
                  <input
                    type="text"
                    value={pump1Name}
                    onChange={(e) => setPump1Name(e.target.value)}
                    className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs text-slate-900 dark:text-slate-100"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] text-slate-600 dark:text-slate-400 font-medium">Pump 2 Display Name</label>
                    <span className="text-[10px] font-mono text-slate-400">[TG-HLP-02]</span>
                  </div>
                  <input
                    type="text"
                    value={pump2Name}
                    onChange={(e) => setPump2Name(e.target.value)}
                    className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs text-slate-900 dark:text-slate-100"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] text-slate-600 dark:text-slate-400 font-medium">Pump 3 Display Name</label>
                    <span className="text-[10px] font-mono text-slate-400">[TG-HLP-03]</span>
                  </div>
                  <input
                    type="text"
                    value={pump3Name}
                    onChange={(e) => setPump3Name(e.target.value)}
                    className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs text-slate-900 dark:text-slate-100"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] text-slate-600 dark:text-slate-400 font-medium">Flow Meter Display Name</label>
                    <span className="text-[10px] font-mono text-slate-400">[FIT_TG_H1]</span>
                  </div>
                  <input
                    type="text"
                    value={fit1Name}
                    onChange={(e) => setFit1Name(e.target.value)}
                    className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs text-slate-900 dark:text-slate-100"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] text-slate-600 dark:text-slate-400 font-medium">Pressure Sensor Display Name</label>
                    <span className="text-[10px] font-mono text-slate-400">[PIT_TG_H1]</span>
                  </div>
                  <input
                    type="text"
                    value={pit1Name}
                    onChange={(e) => setPit1Name(e.target.value)}
                    className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs text-slate-900 dark:text-slate-100"
                  />
                </div>

                <div>
                  <div className="flex items-center justify-between mb-1">
                    <label className="text-[11px] text-slate-600 dark:text-slate-400 font-medium">Level Sensor Display Name</label>
                    <span className="text-[10px] font-mono text-slate-400">[LIT_TG_01]</span>
                  </div>
                  <input
                    type="text"
                    value={lit1Name}
                    onChange={(e) => setLit1Name(e.target.value)}
                    className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-xs text-slate-900 dark:text-slate-100"
                  />
                </div>
              </div>
            </div>
          </div>
        )}

        {subTab === 'pumps' && (
          <div className="space-y-3">
            <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-2">
              <span className="font-semibold text-slate-800 dark:text-slate-200 block">
                Tataguni High-Lift Pump Sets 1–3 (6.6 kV)
              </span>
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="text-[10px] text-slate-500 block mb-1">Rated FLA (A)</label>
                  <input
                    type="number"
                    step="0.5"
                    value={pumpFla}
                    onChange={(e) => setPumpFla(parseFloat(e.target.value) || 0)}
                    className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-xs"
                  />
                </div>
                <div>
                  <label className="text-[10px] text-slate-500 block mb-1">Starter Type</label>
                  <select
                    value={pumpStarter}
                    onChange={(e) => setPumpStarter(e.target.value)}
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
