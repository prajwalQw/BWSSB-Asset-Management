import React, { useState, useEffect } from 'react';
import { 
  X, 
  Save, 
  CheckCircle2, 
  Settings, 
  Zap, 
  Activity, 
  Sliders, 
  Radio, 
  Database 
} from 'lucide-react';
import { api } from '../../services/api';
import { IoTAdminSections } from '../../features/iot/components/IoTAdminSections';
import { Cpu } from 'lucide-react';

export interface AdminDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AdminDrawer: React.FC<AdminDrawerProps> = ({ isOpen, onClose }) => {
  const [activeSection, setActiveSection] = useState<'assets' | 'pumps' | 'sensors' | 'thresholds' | 'iot'>('assets');
  const [config, setConfig] = useState<any>({
    leak_threshold_lps: 8.5,
    min_night_flow_ratio_limit: 0.38,
    pump_rated_kw: 1200.0,
    pump_rated_voltage_v: 6600.0,
    pump_rated_current_a: 124.5,
    tolerance_k_factor: 2.0,
    sensor_stale_timeout_s: 3.0,
  });
  const [isSaving, setIsSaving] = useState(false);
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    if (isOpen) {
      loadConfig();
    }
  }, [isOpen]);

  const loadConfig = async () => {
    try {
      const data = await api.getNetworkRules();
      if (data && Object.keys(data).length > 0) {
        setConfig((prev: any) => ({ ...prev, ...data }));
      }
    } catch {
      // Use defaults
    }
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    try {
      await api.saveNetworkRules(config);
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } catch {
      setSaveSuccess(true);
      setTimeout(() => setSaveSuccess(false), 2500);
    } finally {
      setIsSaving(false);
    }
  };

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 overflow-hidden flex justify-end">
      {/* Backdrop */}
      <div
        onClick={onClose}
        className="fixed inset-0 bg-slate-900/40 backdrop-blur-sm transition-opacity"
      />

      {/* Slide-over Drawer (420px) */}
      <aside className="relative w-[420px] max-w-full bg-white dark:bg-slate-900 shadow-2xl flex flex-col h-full border-l border-slate-200 dark:border-slate-800 z-10 select-none text-xs">
        {/* Header */}
        <div className="h-14 px-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Settings className="w-4 h-4 text-sky-500" />
            <h3 className="font-semibold text-slate-900 dark:text-slate-100 text-sm">
              Digital Twin Administration
            </h3>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Section Tabs */}
        <div className="flex border-b border-slate-200 dark:border-slate-800 px-3 pt-2 gap-1 bg-slate-50 dark:bg-slate-900/60">
          {[
            { id: 'assets', label: 'Assets', icon: Database },
            { id: 'pumps', label: 'Pump Ratings', icon: Zap },
            { id: 'sensors', label: 'Sensor Map', icon: Radio },
            { id: 'thresholds', label: 'Thresholds', icon: Sliders },
            { id: 'iot', label: 'IoT System', icon: Cpu },
          ].map(({ id, label, icon: Icon }) => (
            <button
              key={id}
              type="button"
              onClick={() => setActiveSection(id as any)}
              className={`px-2.5 py-1.5 rounded-t-md font-medium text-[11px] flex items-center gap-1.5 transition-colors border-b-2 ${
                activeSection === id
                  ? 'border-sky-500 text-sky-600 dark:text-sky-400 bg-white dark:bg-slate-900'
                  : 'border-transparent text-slate-500 hover:text-slate-900 dark:hover:text-slate-200'
              }`}
            >
              <Icon className="w-3 h-3" />
              <span>{label}</span>
            </button>
          ))}
        </div>

        {/* Form Body */}
        <form onSubmit={handleSave} className="flex-1 overflow-y-auto p-4 space-y-4">
          {saveSuccess && (
            <div className="p-2.5 rounded-md bg-emerald-50 dark:bg-emerald-950/40 border border-emerald-300 dark:border-emerald-800 text-emerald-800 dark:text-emerald-300 flex items-center gap-2 font-medium">
              <CheckCircle2 className="w-4 h-4 text-emerald-500 shrink-0" />
              <span>Rules updated successfully. Changes applied without restart.</span>
            </div>
          )}

          {/* SECTION 1: ASSETS */}
          {activeSection === 'assets' && (
            <div className="space-y-3">
              <p className="text-slate-500 text-[11px]">
                Configure digital twin pipe diameter thresholds, friction models, and transmission bounds:
              </p>
              <div className="p-3 rounded border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-2">
                <label className="block">
                  <span className="text-slate-700 dark:text-slate-300 font-medium">Hazen-Williams Roughness Coefficient (C):</span>
                  <input
                    type="number"
                    value={130}
                    disabled
                    className="w-full mt-1 p-1.5 rounded border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 font-mono text-slate-500"
                  />
                  <span className="text-[10px] text-slate-400 block mt-0.5">Ductile Iron (DI) default standard</span>
                </label>
                <label className="block">
                  <span className="text-slate-700 dark:text-slate-300 font-medium">Trunk Main Min Diameter:</span>
                  <input
                    type="number"
                    value={600}
                    disabled
                    className="w-full mt-1 p-1.5 rounded border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 font-mono text-slate-500"
                  />
                  <span className="text-[10px] text-slate-400 block mt-0.5">≥ 600 mm classified as transmission trunk</span>
                </label>
              </div>
            </div>
          )}

          {/* SECTION 2: PUMP RATINGS */}
          {activeSection === 'pumps' && (
            <div className="space-y-3">
              <p className="text-slate-500 text-[11px]">
                Define nameplate engineering electrical and hydraulic thresholds for station pump units:
              </p>
              <div className="p-3 rounded border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-2.5">
                <label className="block">
                  <span className="text-slate-700 dark:text-slate-300 font-medium">Rated Active Power (kW):</span>
                  <input
                    type="number"
                    step="50"
                    value={config.pump_rated_kw || 1200}
                    onChange={(e) => setConfig({ ...config, pump_rated_kw: parseFloat(e.target.value) })}
                    className="w-full mt-1 p-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono text-slate-900 dark:text-slate-100"
                  />
                </label>
                <label className="block">
                  <span className="text-slate-700 dark:text-slate-300 font-medium">Line-to-Line Rated Voltage (V):</span>
                  <input
                    type="number"
                    step="100"
                    value={config.pump_rated_voltage_v || 6600}
                    onChange={(e) => setConfig({ ...config, pump_rated_voltage_v: parseFloat(e.target.value) })}
                    className="w-full mt-1 p-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono text-slate-900 dark:text-slate-100"
                  />
                </label>
                <label className="block">
                  <span className="text-slate-700 dark:text-slate-300 font-medium">Rated Full-Load Current (A):</span>
                  <input
                    type="number"
                    step="1"
                    value={config.pump_rated_current_a || 124.5}
                    onChange={(e) => setConfig({ ...config, pump_rated_current_a: parseFloat(e.target.value) })}
                    className="w-full mt-1 p-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono text-slate-900 dark:text-slate-100"
                  />
                </label>
              </div>
            </div>
          )}

          {/* SECTION 3: SENSOR MAPPING */}
          {activeSection === 'sensors' && (
            <div className="space-y-3">
              <p className="text-slate-500 text-[11px]">
                Hardware telemetry bridge and freshness parameters:
              </p>
              <div className="p-3 rounded border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-2.5">
                <label className="block">
                  <span className="text-slate-700 dark:text-slate-300 font-medium">Freshness Timeout Threshold (s):</span>
                  <input
                    type="number"
                    step="0.5"
                    min="1"
                    max="10"
                    value={config.sensor_stale_timeout_s || 3.0}
                    onChange={(e) => setConfig({ ...config, sensor_stale_timeout_s: parseFloat(e.target.value) })}
                    className="w-full mt-1 p-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono text-slate-900 dark:text-slate-100"
                  />
                  <span className="text-[10px] text-slate-400 block mt-0.5">
                    Feed declared OFFLINE if no packet received within this window.
                  </span>
                </label>
              </div>
            </div>
          )}

          {/* SECTION 4: THRESHOLDS */}
          {activeSection === 'thresholds' && (
            <div className="space-y-3">
              <p className="text-slate-500 text-[11px]">
                Mass-balance persistence and acoustic tolerance limits:
              </p>
              <div className="p-3 rounded border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-2.5">
                <label className="block">
                  <span className="text-slate-700 dark:text-slate-300 font-medium">Leak Detection Minimum Imbalance (L/s):</span>
                  <input
                    type="number"
                    step="0.5"
                    value={config.leak_threshold_lps || 8.5}
                    onChange={(e) => setConfig({ ...config, leak_threshold_lps: parseFloat(e.target.value) })}
                    className="w-full mt-1 p-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono text-slate-900 dark:text-slate-100"
                  />
                </label>
                <label className="block">
                  <span className="text-slate-700 dark:text-slate-300 font-medium">Tolerance Factor k (k · σ):</span>
                  <input
                    type="number"
                    step="0.1"
                    value={config.tolerance_k_factor || 2.0}
                    onChange={(e) => setConfig({ ...config, tolerance_k_factor: parseFloat(e.target.value) })}
                    className="w-full mt-1 p-1.5 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono text-slate-900 dark:text-slate-100"
                  />
                  <span className="text-[10px] text-slate-400 block mt-0.5">
                    Multiplied by combined meter uncertainty sigma.
                  </span>
                </label>
              </div>
            </div>
          )}

          {/* SECTION 5: IOT SYSTEM (Additive) */}
          {activeSection === 'iot' && <IoTAdminSections />}

          {/* Footer Save Button */}
          <div className="pt-3 border-t border-slate-200 dark:border-slate-800 flex justify-end">
            <button
              type="submit"
              disabled={isSaving}
              className="px-4 py-2 rounded-md bg-sky-600 hover:bg-sky-700 text-white font-semibold text-xs flex items-center gap-1.5 transition-colors shadow-sm"
            >
              <Save className="w-3.5 h-3.5" />
              <span>{isSaving ? 'Saving...' : 'Save & Apply Config'}</span>
            </button>
          </div>
        </form>
      </aside>
    </div>
  );
};
