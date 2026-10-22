import React, { useState } from 'react';
import {
  X,
  Play,
  RotateCcw,
  AlertTriangle,
  Zap,
  Activity,
  Radio,
  Clock,
  CheckCircle2,
  List
} from 'lucide-react';
import { iotApi } from '../services/iotApi';
import { AuditLogEntry } from '../types';

export interface IoTSimulateModalProps {
  onClose: () => void;
  onRefresh: () => void;
}

export const IoTSimulateModal: React.FC<IoTSimulateModalProps> = ({ onClose, onRefresh }) => {
  const [activeTab, setActiveTab] = useState<'inject' | 'audit'>('inject');
  const [leakRate, setLeakRate] = useState<number>(18.5);
  const [pipeSegment, setPipeSegment] = useState<string>('CORR_TG_MJ');
  const [selectedPump, setSelectedPump] = useState<string>('PUMP_TG_H1');
  const [pumpFaultType, setPumpFaultType] = useState<string>('TRIP');
  const [sensorTag, setSensorTag] = useState<string>('FIT_TG_DISCHARGE');
  const [sensorFaultType, setSensorFaultType] = useState<string>('OFFLINE');
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([
    { action: 'INITIALIZE', timestamp: new Date().toLocaleTimeString(), details: 'Baseline physics online' }
  ]);
  const [actionStatus, setActionStatus] = useState<string | null>(null);

  const handleInjectLeak = async () => {
    try {
      await iotApi.injectLeak(pipeSegment, leakRate, 'Pipeline Road V-104 Ch 4+200');
      setAuditLog((prev) => [
        { action: 'INJECT_LEAK', timestamp: new Date().toLocaleTimeString(), details: `${leakRate} L/s on ${pipeSegment}` },
        ...prev
      ]);
      setActionStatus(`Leak of ${leakRate} L/s injected on ${pipeSegment}`);
      setTimeout(() => setActionStatus(null), 3000);
      onRefresh();
    } catch {
      setActionStatus('Failed to inject leak');
    }
  };

  const handleInjectPumpFault = async () => {
    try {
      await iotApi.injectPumpFault(selectedPump, pumpFaultType);
      setAuditLog((prev) => [
        { action: 'INJECT_PUMP_FAULT', timestamp: new Date().toLocaleTimeString(), details: `${pumpFaultType} on ${selectedPump}` },
        ...prev
      ]);
      setActionStatus(`Pump fault '${pumpFaultType}' injected on ${selectedPump}`);
      setTimeout(() => setActionStatus(null), 3000);
      onRefresh();
    } catch {
      setActionStatus('Failed to inject pump fault');
    }
  };

  const handleInjectSensorFault = async () => {
    try {
      await iotApi.injectSensorFault(sensorTag, sensorFaultType);
      setAuditLog((prev) => [
        { action: 'INJECT_SENSOR_FAULT', timestamp: new Date().toLocaleTimeString(), details: `${sensorFaultType} on ${sensorTag}` },
        ...prev
      ]);
      setActionStatus(`Sensor fault '${sensorFaultType}' applied to ${sensorTag}`);
      setTimeout(() => setActionStatus(null), 3000);
      onRefresh();
    } catch {
      setActionStatus('Failed to inject sensor fault');
    }
  };

  const handleReset = async () => {
    try {
      await iotApi.resetSimulation();
      setAuditLog((prev) => [
        { action: 'RESET_SIMULATION', timestamp: new Date().toLocaleTimeString(), details: 'Cleared all injected faults' },
        ...prev
      ]);
      setActionStatus('Simulation reset to baseline');
      setTimeout(() => setActionStatus(null), 3000);
      onRefresh();
    } catch {
      setActionStatus('Failed to reset simulation');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/60 backdrop-blur-sm select-none">
      <div className="w-full max-w-md bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col text-xs">
        {/* Header */}
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-950">
          <div className="flex items-center gap-2">
            <Play className="w-4 h-4 text-purple-500 fill-current" />
            <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">
              IoT Simulation Controls
            </h3>
            <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold uppercase">
              SIMULATED
            </span>
          </div>
          <button type="button" onClick={onClose} className="p-1 rounded text-slate-400 hover:text-slate-600">
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Tab switch */}
        <div className="flex border-b border-slate-200 dark:border-slate-800 p-1 bg-slate-100 dark:bg-slate-950/80">
          <button
            type="button"
            onClick={() => setActiveTab('inject')}
            className={`flex-1 py-1.5 rounded-md font-medium transition-all ${
              activeTab === 'inject' ? 'bg-white dark:bg-slate-800 shadow-sm text-slate-900 dark:text-slate-100 font-bold' : 'text-slate-400'
            }`}
          >
            Fault & Leak Injections
          </button>
          <button
            type="button"
            onClick={() => setActiveTab('audit')}
            className={`flex-1 py-1.5 rounded-md font-medium transition-all flex items-center justify-center gap-1.5 ${
              activeTab === 'audit' ? 'bg-white dark:bg-slate-800 shadow-sm text-slate-900 dark:text-slate-100 font-bold' : 'text-slate-400'
            }`}
          >
            <List className="w-3.5 h-3.5" />
            <span>Audit Log ({auditLog.length})</span>
          </button>
        </div>

        {/* Feedback message banner */}
        {actionStatus && (
          <div className="px-4 py-2 bg-purple-50 dark:bg-purple-950/40 border-b border-purple-200 dark:border-purple-800 text-purple-700 dark:text-purple-300 font-medium">
            {actionStatus}
          </div>
        )}

        {/* Body */}
        <div className="p-4 space-y-4 max-h-[420px] overflow-y-auto">
          {activeTab === 'inject' ? (
            <>
              {/* 1. Pipe Leak Injection */}
              <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-2.5">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                    <Activity className="w-3.5 h-3.5 text-rose-500" />
                    Transmission Pipe Leak
                  </span>
                  <span className="text-[10px] text-slate-400 font-mono">Mass-balance loss</span>
                </div>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[10px] text-slate-500 block mb-1">Target Conduit</label>
                    <select
                      value={pipeSegment}
                      onChange={(e) => setPipeSegment(e.target.value)}
                      className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-[11px]"
                    >
                      <option value="CORR_TG_MJ">Tataguni → Mount Joy Feeder</option>
                      <option value="CORR_TG_HG">Tataguni → High Grounds Trunk</option>
                      <option value="CORR_HARO_TG">Harohalli → Tataguni High-Lift</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 block mb-1">Leak Rate (L/s)</label>
                    <input
                      type="number"
                      step="0.5"
                      value={leakRate}
                      onChange={(e) => setLeakRate(parseFloat(e.target.value) || 0)}
                      className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-[11px]"
                    />
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleInjectLeak}
                  className="w-full py-2 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-semibold transition-colors flex items-center justify-center gap-1.5"
                >
                  <AlertTriangle className="w-3.5 h-3.5" />
                  <span>Inject Pipe Leak ({leakRate} L/s)</span>
                </button>
              </div>

              {/* 2. Pump Fault Injection */}
              <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-2.5">
                <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5 text-amber-500" />
                  Pump Set Trip / Fault
                </span>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[10px] text-slate-500 block mb-1">Pump Unit</label>
                    <select
                      value={selectedPump}
                      onChange={(e) => setSelectedPump(e.target.value)}
                      className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-[11px]"
                    >
                      <option value="PUMP_TG_H1">H1 (Tataguni 1200 kW)</option>
                      <option value="PUMP_TG_H2">H2 (Tataguni 1200 kW)</option>
                      <option value="PUMP_MJ_F1">F1 (Mount Joy 350 kW)</option>
                      <option value="PUMP_HG_F1">F1 (High Grounds 450 kW)</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 block mb-1">Fault Type</label>
                    <select
                      value={pumpFaultType}
                      onChange={(e) => setPumpFaultType(e.target.value)}
                      className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-[11px]"
                    >
                      <option value="TRIP">Electrical Trip</option>
                      <option value="DRY_RUN">Dry Run / Low Suction</option>
                      <option value="OVERCURRENT">Overcurrent Inrush Lock</option>
                      <option value="VIBRATION_HIGH">High Vibration Alarm</option>
                    </select>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleInjectPumpFault}
                  className="w-full py-2 rounded-lg bg-amber-600 hover:bg-amber-500 text-white font-semibold transition-colors flex items-center justify-center gap-1.5"
                >
                  <Zap className="w-3.5 h-3.5" />
                  <span>Trigger Pump Fault</span>
                </button>
              </div>

              {/* 3. Sensor Health Dropout */}
              <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-900/40 space-y-2.5">
                <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1.5">
                  <Radio className="w-3.5 h-3.5 text-sky-500" />
                  Sensor / Meter Anomaly
                </span>

                <div className="grid grid-cols-2 gap-2">
                  <div>
                    <label className="text-[10px] text-slate-500 block mb-1">Instrument</label>
                    <select
                      value={sensorTag}
                      onChange={(e) => setSensorTag(e.target.value)}
                      className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-[11px]"
                    >
                      <option value="FIT_TG_DISCHARGE">FIT_TG_DISCHARGE (Bulk)</option>
                      <option value="FIT_MJ_INLET">FIT_MJ_INLET (Bulk)</option>
                      <option value="PIT_MJ_F1">PIT_MJ_F1 (Pressure)</option>
                      <option value="AIT_TG_01">AIT_TG_01 (Water Quality)</option>
                    </select>
                  </div>
                  <div>
                    <label className="text-[10px] text-slate-500 block mb-1">State</label>
                    <select
                      value={sensorFaultType}
                      onChange={(e) => setSensorFaultType(e.target.value)}
                      className="w-full p-1.5 rounded bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 font-mono text-[11px]"
                    >
                      <option value="OFFLINE">Comms Lost (Offline)</option>
                      <option value="STUCK">Frozen / Stuck Value</option>
                      <option value="DRIFT">Slow Calibration Drift</option>
                      <option value="SPIKE">Erratic Signal Spikes</option>
                    </select>
                  </div>
                </div>

                <button
                  type="button"
                  onClick={handleInjectSensorFault}
                  className="w-full py-2 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold transition-colors flex items-center justify-center gap-1.5"
                >
                  <Radio className="w-3.5 h-3.5" />
                  <span>Apply Sensor Fault</span>
                </button>
              </div>

              {/* Reset Button */}
              <button
                type="button"
                onClick={handleReset}
                className="w-full py-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-300 font-semibold hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors flex items-center justify-center gap-1.5"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Reset All Injections to Baseline</span>
              </button>
            </>
          ) : (
            /* Audit Log View */
            <div className="space-y-2">
              {auditLog.map((entry, idx) => (
                <div
                  key={idx}
                  className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-900/40 text-[11px] font-mono"
                >
                  <div className="flex items-center justify-between text-slate-400 mb-1">
                    <span className="font-bold text-slate-700 dark:text-slate-200">{entry.action}</span>
                    <span>{entry.timestamp}</span>
                  </div>
                  <div className="text-slate-600 dark:text-slate-400">{String(entry.details || '')}</div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
};
