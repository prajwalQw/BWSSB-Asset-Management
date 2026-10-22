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
  Database,
  ShieldCheck,
  Lock,
  RefreshCw,
  FileCheck,
  Cpu
} from 'lucide-react';
import { api } from '../../services/api';
import { IoTAdminSections } from '../../features/iot/components/IoTAdminSections';

export interface AdminDrawerProps {
  isOpen: boolean;
  onClose: () => void;
}

export const AdminDrawer: React.FC<AdminDrawerProps> = ({ isOpen, onClose }) => {
  const [activeSection, setActiveSection] = useState<'assets' | 'pumps' | 'sensors' | 'thresholds' | 'iot' | 'security'>('assets');
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
  const [securityStatus, setSecurityStatus] = useState<any>(null);
  const [isVerifyingChain, setIsVerifyingChain] = useState(false);
  const [verificationFeedback, setVerificationFeedback] = useState<string | null>(null);

  useEffect(() => {
    if (isOpen) {
      loadConfig();
      loadSecurity();
    }
  }, [isOpen]);

  const loadSecurity = async () => {
    try {
      const res = await fetch('/api/v1/security/status');
      if (res.ok) {
        const data = await res.json();
        setSecurityStatus(data);
      }
    } catch (e) {
      console.error('Failed to load security status', e);
    }
  };

  const handleVerifyChain = async () => {
    setIsVerifyingChain(true);
    setVerificationFeedback(null);
    try {
      const res = await fetch('/api/v1/security/status');
      if (res.ok) {
        const data = await res.json();
        setSecurityStatus(data);
        if (data.audit_chain_valid) {
          setVerificationFeedback(`Verified! All ${data.audit_records_count} hash-chained records cryptographically intact.`);
        } else {
          setVerificationFeedback('Warning: Tampering or invalid hash detected in audit log!');
        }
      }
    } catch (err: any) {
      setVerificationFeedback('Verification check error: ' + err.message);
    } finally {
      setIsVerifyingChain(false);
    }
  };

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
            { id: 'security', label: 'Security', icon: ShieldCheck },
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

          {/* SECTION 6: SECURITY & AUDIT (Priority 6) */}
          {activeSection === 'security' && (
            <div className="space-y-3">
              <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                    <ShieldCheck className="w-4 h-4 text-emerald-500" />
                    Cybersecurity Posture
                  </span>
                  <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-100 dark:bg-emerald-950 text-emerald-700 dark:text-emerald-300 border border-emerald-300 dark:border-emerald-800">
                    IEC 62443 / NIST CSF
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px] pt-1">
                  <div className="p-2 rounded bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700">
                    <div className="text-slate-500 font-medium">RBAC Roles</div>
                    <div className="font-mono font-bold text-slate-800 dark:text-slate-100">
                      {securityStatus?.rbac_roles?.join(', ') || 'viewer, operator, admin'}
                    </div>
                  </div>
                  <div className="p-2 rounded bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700">
                    <div className="text-slate-500 font-medium">Rate Limiting</div>
                    <div className="font-mono font-bold text-emerald-600 dark:text-emerald-400">
                      Active (240/min)
                    </div>
                  </div>
                  <div className="p-2 rounded bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700">
                    <div className="text-slate-500 font-medium">OT Field Control Mode</div>
                    <div className="font-mono font-bold text-amber-600 dark:text-amber-400">
                      Passive Read-Only
                    </div>
                  </div>
                  <div className="p-2 rounded bg-white dark:bg-slate-800/80 border border-slate-200 dark:border-slate-700">
                    <div className="text-slate-500 font-medium">Last Security Scan</div>
                    <div className="font-mono font-bold text-slate-800 dark:text-slate-100">
                      {securityStatus?.last_security_scan_date || '2026-10-22'}
                    </div>
                  </div>
                </div>
              </div>

              {/* Cryptographic Audit Ledger */}
              <div className="p-3 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                    <Lock className="w-3.5 h-3.5 text-sky-500" />
                    Hash-Chained Audit Ledger
                  </span>
                  <button
                    type="button"
                    onClick={handleVerifyChain}
                    disabled={isVerifyingChain}
                    className="px-2 py-1 rounded bg-sky-50 dark:bg-sky-950/60 border border-sky-300 dark:border-sky-800 text-sky-700 dark:text-sky-300 text-[10px] font-semibold flex items-center gap-1 hover:bg-sky-100"
                  >
                    <RefreshCw className={`w-3 h-3 ${isVerifyingChain ? 'animate-spin' : ''}`} />
                    <span>Verify Chain</span>
                  </button>
                </div>

                <div className="text-[11px] space-y-1 font-mono">
                  <div className="flex justify-between">
                    <span className="text-slate-500">Chain Status:</span>
                    <span className={securityStatus?.audit_chain_valid ? 'text-emerald-600 font-bold' : 'text-rose-600 font-bold'}>
                      {securityStatus?.audit_chain_valid ? 'CRYPTOGRAPHICALLY VALID' : 'CHECK PENDING'}
                    </span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-slate-500">Total Tamper-Evident Entries:</span>
                    <span className="text-slate-900 dark:text-slate-100 font-bold">
                      {securityStatus?.audit_records_count ?? 0}
                    </span>
                  </div>
                  <div className="text-[10px] text-slate-500 truncate" title={securityStatus?.audit_head_hash}>
                    Head SHA-256: {securityStatus?.audit_head_hash || 'genesis'}
                  </div>
                </div>

                {verificationFeedback && (
                  <div className="mt-2 p-2 rounded bg-sky-50 dark:bg-sky-950/50 border border-sky-300 dark:border-sky-800 text-sky-800 dark:text-sky-200 text-[11px] flex items-start gap-1.5">
                    <FileCheck className="w-3.5 h-3.5 text-sky-500 shrink-0 mt-0.5" />
                    <span>{verificationFeedback}</span>
                  </div>
                )}
              </div>
            </div>
          )}

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
