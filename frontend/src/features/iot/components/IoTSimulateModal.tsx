import React, { useState } from 'react';
import {
  X,
  Play,
  Square,
  AlertTriangle,
  ChevronDown,
  ChevronUp,
  Droplet,
  Activity,
  Radio,
  Sliders,
  CheckCircle2
} from 'lucide-react';
import { iotApi } from '../services/iotApi';
import { useIoTStore } from '../store/useIoTStore';
import { AuditLogEntry } from '../types';

export interface IoTSimulateModalProps {
  onClose: () => void;
  onRefresh?: () => void;
}

// Network Graph topology from config/iot/network_flows.yaml
const NETWORK_NODES: Record<string, { label: string; type: string }> = {
  WTP_TATAGUNI: { label: 'Tataguni Pumping Complex', type: 'Pumping Complex' },
  GLR_MOUNT_JOY: { label: 'Mount Joy Ground Level Reservoir', type: 'GLR Reservoir' },
  GLR_HIGH_GROUNDS: { label: 'High Grounds Ground Level Reservoir', type: 'GLR Reservoir' },
  WTP_HAROHALLI: { label: 'Harohalli Intermediate Booster PS', type: 'Booster Station' },
  WTP_TK_HALLI: { label: 'T.K. Halli Water Treatment Plant', type: 'Water Treatment Plant' },
  DMA_SOUTH_BASAVANAGUDI: { label: 'Basavanagudi - Hanumanthanagar DMA', type: 'DMA Zone' },
  DMA_CENTRAL_CBD: { label: 'Central CBD Vidhana Soudha DMA', type: 'DMA Zone' },
};

const NETWORK_EDGES: Record<string, Array<{ toId: string; corridorId: string; distanceKm: number }>> = {
  WTP_TATAGUNI: [
    { toId: 'GLR_MOUNT_JOY', corridorId: 'CORR_TATAGUNI_MOUNT_JOY', distanceKm: 12.8 },
    { toId: 'GLR_HIGH_GROUNDS', corridorId: 'CORR_TATAGUNI_HIGH_GROUNDS', distanceKm: 18.2 },
  ],
  WTP_HAROHALLI: [
    { toId: 'WTP_TATAGUNI', corridorId: 'CORR_HAROHALLI_TATAGUNI', distanceKm: 30.1 },
  ],
  WTP_TK_HALLI: [
    { toId: 'WTP_HAROHALLI', corridorId: 'CORR_TKH_HAROHALLI', distanceKm: 32.4 },
  ],
  GLR_MOUNT_JOY: [
    { toId: 'DMA_SOUTH_BASAVANAGUDI', corridorId: 'CORR_MOUNT_JOY_BASAVANAGUDI', distanceKm: 2.1 },
  ],
  GLR_HIGH_GROUNDS: [
    { toId: 'DMA_CENTRAL_CBD', corridorId: 'CORR_HIGH_GROUNDS_CBD', distanceKm: 2.6 },
  ],
};

export const IoTSimulateModal: React.FC<IoTSimulateModalProps> = ({ onClose, onRefresh }) => {
  const store = useIoTStore();
  const activeInjections = store.activeInjections;

  // Form Fields
  const [fromNode, setFromNode] = useState<string>('WTP_TATAGUNI');
  const validToNodes = NETWORK_EDGES[fromNode] || [];
  const [toNode, setToNode] = useState<string>(validToNodes[0]?.toId || 'GLR_MOUNT_JOY');
  const [leakRate, setLeakRate] = useState<number>(45.0);
  const [pipePositionPct, setPipePositionPct] = useState<number>(50);

  // Accordion state
  const [isAccordionOpen, setIsAccordionOpen] = useState<boolean>(false);
  const [selectedPump, setSelectedPump] = useState<string>('PUMP_TG_H1');
  const [selectedSensor, setSelectedSensor] = useState<string>('FIT_TG_DISCHARGE');
  const [selectedMeter, setSelectedMeter] = useState<string>('FIT_MJ_INLET');
  const [auditLog, setAuditLog] = useState<AuditLogEntry[]>([
    { action: 'INITIALIZE', timestamp: new Date().toLocaleTimeString(), details: 'Simulation engine active' }
  ]);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  // Check if target corridor currently has active leak
  const selectedEdge = validToNodes.find((edge) => edge.toId === toNode);
  const currentCorridorId = selectedEdge?.corridorId || 'CORR_TATAGUNI_MOUNT_JOY';
  const isCurrentCorridorLeaking = Boolean(
    activeInjections?.leak &&
    (activeInjections.leak.pipe_segment_id === currentCorridorId ||
     activeInjections.leak.pipe_segment_id === 'CORR_TG_MJ')
  );

  const handleFromChange = (newFrom: string) => {
    setFromNode(newFrom);
    const availableTos = NETWORK_EDGES[newFrom] || [];
    if (availableTos.length > 0) {
      setToNode(availableTos[0].toId);
    }
  };

  const handleStartLeak = async () => {
    try {
      const edge = validToNodes.find((e) => e.toId === toNode);
      const corridorId = edge?.corridorId || 'CORR_TATAGUNI_MOUNT_JOY';
      const approxKm = edge ? (edge.distanceKm * (pipePositionPct / 100)).toFixed(1) : '6.4';
      const landmark = `Pipeline Corridor Chainage ~${approxKm} km (${pipePositionPct}% along pipe)`;

      await iotApi.injectLeak(corridorId, leakRate, landmark);

      setAuditLog((prev) => [
        {
          action: 'START_LEAK',
          timestamp: new Date().toLocaleTimeString(),
          details: `${leakRate} L/s on ${corridorId} at ${pipePositionPct}%`
        },
        ...prev
      ]);
      setStatusMsg(`Started ${leakRate} L/s leak on ${NETWORK_NODES[fromNode]?.label} → ${NETWORK_NODES[toNode]?.label}`);
      setTimeout(() => setStatusMsg(null), 3000);
      if (onRefresh) onRefresh();
    } catch {
      setStatusMsg('Failed to inject leak');
    }
  };

  const handleStopLeak = async (corridorId?: string) => {
    try {
      const target = corridorId || currentCorridorId;
      await iotApi.stopLeak(target);
      setAuditLog((prev) => [
        { action: 'STOP_LEAK', timestamp: new Date().toLocaleTimeString(), details: `Cleared leak on ${target}` },
        ...prev
      ]);
      setStatusMsg('Leak stopped. Physics restoring to baseline.');
      setTimeout(() => setStatusMsg(null), 3000);
      if (onRefresh) onRefresh();
    } catch {
      setStatusMsg('Failed to stop leak');
    }
  };

  const handlePumpTrip = async () => {
    try {
      await iotApi.injectPumpFault(selectedPump, 'TRIP');
      setAuditLog((prev) => [
        { action: 'PUMP_TRIP', timestamp: new Date().toLocaleTimeString(), details: `Trip signal sent to ${selectedPump}` },
        ...prev
      ]);
      setStatusMsg(`Trip command dispatched to ${selectedPump}`);
      setTimeout(() => setStatusMsg(null), 3000);
    } catch {
      setStatusMsg('Failed to trip pump');
    }
  };

  const handleSensorOffline = async () => {
    try {
      await iotApi.injectSensorFault(selectedSensor, 'OFFLINE');
      setAuditLog((prev) => [
        { action: 'SENSOR_OFFLINE', timestamp: new Date().toLocaleTimeString(), details: `${selectedSensor} forced offline` },
        ...prev
      ]);
      setStatusMsg(`${selectedSensor} telemetry forced offline`);
      setTimeout(() => setStatusMsg(null), 3000);
    } catch {
      setStatusMsg('Failed to set sensor offline');
    }
  };

  const handleMeterOffline = async () => {
    try {
      await iotApi.injectSensorFault(selectedMeter, 'OFFLINE');
      setAuditLog((prev) => [
        { action: 'METER_OFFLINE', timestamp: new Date().toLocaleTimeString(), details: `${selectedMeter} comms cut` },
        ...prev
      ]);
      setStatusMsg(`${selectedMeter} bulk meter offline`);
      setTimeout(() => setStatusMsg(null), 3000);
    } catch {
      setStatusMsg('Failed to set meter offline');
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/65 backdrop-blur-sm select-none">
      <div className="w-full max-w-lg bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col text-xs animate-in fade-in zoom-in-95">
        {/* Header */}
        <div className="p-4 border-b border-slate-200 dark:border-slate-800 flex items-center justify-between bg-slate-50 dark:bg-slate-950">
          <div className="flex items-center gap-2">
            <span className="p-1 rounded bg-sky-500/10 text-sky-500 border border-sky-500/30">
              <Droplet className="w-4 h-4" />
            </span>
            <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">
              Create a leak
            </h3>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold uppercase">
              SIMULATED
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Status Notification */}
        {statusMsg && (
          <div className="px-4 py-2 bg-sky-500/10 border-b border-sky-500/20 text-sky-400 font-mono text-[11px] flex items-center gap-1.5">
            <CheckCircle2 className="w-3.5 h-3.5 text-sky-500" />
            <span>{statusMsg}</span>
          </div>
        )}

        <div className="p-5 space-y-4 max-h-[80vh] overflow-y-auto">
          {/* 1. From & To Pipeline Segment Selector */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="text-[10px] font-mono uppercase text-slate-500 block mb-1 font-semibold">
                From Asset
              </label>
              <select
                value={fromNode}
                onChange={(e) => handleFromChange(e.target.value)}
                className="w-full p-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 font-medium"
              >
                {Object.keys(NETWORK_EDGES).map((id) => (
                  <option key={id} value={id}>
                    {NETWORK_NODES[id]?.label || id}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label className="text-[10px] font-mono uppercase text-slate-500 block mb-1 font-semibold">
                To (Connected Node)
              </label>
              <select
                value={toNode}
                onChange={(e) => setToNode(e.target.value)}
                className="w-full p-2 rounded-lg border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 text-slate-800 dark:text-slate-200 font-medium"
              >
                {validToNodes.map((edge) => (
                  <option key={edge.toId} value={edge.toId}>
                    {NETWORK_NODES[edge.toId]?.label || edge.toId} ({edge.distanceKm} km)
                  </option>
                ))}
              </select>
            </div>
          </div>

          {/* 2. Leak Size Slider + Preset Buttons */}
          <div className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-800 dark:text-slate-200">
                Leak Size: <strong className="text-sky-500 font-mono text-sm">{leakRate.toFixed(1)} L/s</strong>
              </span>
              <span className="text-[10px] text-slate-400 font-mono">
                {Math.round(leakRate * 86.4).toLocaleString()} kL/day
              </span>
            </div>

            <input
              type="range"
              min="5"
              max="100"
              step="1"
              value={leakRate}
              onChange={(e) => setLeakRate(Number(e.target.value))}
              className="w-full accent-sky-500 cursor-pointer"
            />

            <div className="flex items-center gap-2 pt-1">
              <span className="text-[10px] text-slate-500 font-mono">Presets:</span>
              <button
                type="button"
                onClick={() => setLeakRate(15.0)}
                className={`px-2.5 py-1 rounded font-mono text-[10px] transition-colors ${
                  leakRate === 15 ? 'bg-sky-500 text-white font-bold' : 'bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-300'
                }`}
              >
                Small (15 L/s)
              </button>
              <button
                type="button"
                onClick={() => setLeakRate(45.0)}
                className={`px-2.5 py-1 rounded font-mono text-[10px] transition-colors ${
                  leakRate === 45 ? 'bg-sky-500 text-white font-bold' : 'bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-300'
                }`}
              >
                Medium (45 L/s)
              </button>
              <button
                type="button"
                onClick={() => setLeakRate(85.0)}
                className={`px-2.5 py-1 rounded font-mono text-[10px] transition-colors ${
                  leakRate === 85 ? 'bg-sky-500 text-white font-bold' : 'bg-slate-200 dark:bg-slate-800 text-slate-600 dark:text-slate-300'
                }`}
              >
                Large (85 L/s)
              </button>
            </div>
          </div>

          {/* 3. Where along the pipe slider */}
          <div className="p-3.5 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50/50 dark:bg-slate-950/40 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-800 dark:text-slate-200">
                Where Along the Pipe: <strong className="text-sky-500 font-mono text-sm">{pipePositionPct}%</strong>
              </span>
              <span className="text-[10px] text-slate-400 font-mono">
                Chainage ~{((selectedEdge?.distanceKm || 12.8) * (pipePositionPct / 100)).toFixed(1)} km
              </span>
            </div>

            <input
              type="range"
              min="10"
              max="90"
              step="5"
              value={pipePositionPct}
              onChange={(e) => setPipePositionPct(Number(e.target.value))}
              className="w-full accent-sky-500 cursor-pointer"
            />
            <div className="flex justify-between text-[10px] text-slate-400 font-mono">
              <span>10% (Near upstream)</span>
              <span>50% (Midway)</span>
              <span>90% (Near downstream)</span>
            </div>
          </div>

          {/* 4. Action Buttons: Start Leak & Stop Leak */}
          <div className="flex gap-2">
            <button
              type="button"
              onClick={handleStartLeak}
              className="flex-1 py-2.5 px-4 rounded-xl bg-sky-500 hover:bg-sky-600 text-white font-bold text-xs flex items-center justify-center gap-1.5 shadow-lg shadow-sky-500/25 transition-all"
            >
              <Play className="w-4 h-4 fill-current" />
              <span>Start leak</span>
            </button>

            <button
              type="button"
              onClick={() => handleStopLeak(currentCorridorId)}
              className="py-2.5 px-4 rounded-xl border border-rose-500/50 hover:bg-rose-500/10 text-rose-500 font-semibold text-xs flex items-center justify-center gap-1.5 transition-all"
            >
              <Square className="w-4 h-4 fill-current" />
              <span>Stop leak</span>
            </button>
          </div>

          {/* 5. "Running now" Active Leaks List */}
          <div className="p-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/60 space-y-2">
            <span className="font-semibold text-slate-800 dark:text-slate-200 block text-[11px]">
              Running now
            </span>
            {activeInjections?.leak ? (
              <div className="p-2.5 rounded-lg border border-rose-500/40 bg-rose-950/20 flex items-center justify-between">
                <div>
                  <div className="flex items-center gap-1.5 font-bold text-rose-400">
                    <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
                    <span>{activeInjections.leak.pipe_segment_id}</span>
                  </div>
                  <span className="text-[10px] text-slate-400 font-mono block">
                    Loss: {activeInjections.leak.leak_rate_lps} L/s • {activeInjections.leak.landmark || 'Corridor Main'}
                  </span>
                </div>
                <button
                  type="button"
                  onClick={() => handleStopLeak(activeInjections.leak.pipe_segment_id)}
                  className="px-2.5 py-1 rounded bg-rose-500 text-white font-mono text-[10px] font-bold hover:bg-rose-600 transition-colors"
                >
                  Stop
                </button>
              </div>
            ) : (
              <p className="text-[11px] text-slate-400 italic">No physical leaks currently injected.</p>
            )}
          </div>

          {/* 6. Collapsed "More tests" Accordion */}
          <div className="border border-slate-200 dark:border-slate-800 rounded-xl overflow-hidden">
            <button
              type="button"
              onClick={() => setIsAccordionOpen(!isAccordionOpen)}
              className="w-full p-3 bg-slate-100 dark:bg-slate-950/80 hover:bg-slate-200/60 dark:hover:bg-slate-900 flex items-center justify-between font-medium text-slate-700 dark:text-slate-300 transition-colors"
            >
              <div className="flex items-center gap-2">
                <Sliders className="w-3.5 h-3.5 text-slate-400" />
                <span>More tests (Equipment & Sensor Faults)</span>
              </div>
              {isAccordionOpen ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
            </button>

            {isAccordionOpen && (
              <div className="p-3.5 space-y-3 bg-white dark:bg-slate-900 border-t border-slate-200 dark:border-slate-800">
                {/* Pump Trip */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex-1">
                    <span className="text-[10px] text-slate-500 font-mono block">Pump Protection Trip</span>
                    <select
                      value={selectedPump}
                      onChange={(e) => setSelectedPump(e.target.value)}
                      className="w-full p-1.5 rounded border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-[11px]"
                    >
                      <option value="PUMP_TG_H1">Tataguni Pump TG-H1</option>
                      <option value="PUMP_TG_H2">Tataguni Pump TG-H2</option>
                      <option value="PUMP_TG_H3">Tataguni Pump TG-H3</option>
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={handlePumpTrip}
                    className="mt-3 px-3 py-1.5 rounded bg-amber-500 hover:bg-amber-600 text-white font-medium text-[11px] transition-colors"
                  >
                    Trip Pump
                  </button>
                </div>

                {/* Sensor Offline */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex-1">
                    <span className="text-[10px] text-slate-500 font-mono block">Station Sensor Fault</span>
                    <select
                      value={selectedSensor}
                      onChange={(e) => setSelectedSensor(e.target.value)}
                      className="w-full p-1.5 rounded border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-[11px]"
                    >
                      <option value="FIT_TG_DISCHARGE">FIT_TG_DISCHARGE (Flow Transmitter)</option>
                      <option value="PIT_MJ_F1">PIT_MJ_F1 (Pressure Transmitter)</option>
                      <option value="AIT_PS_TATAGUNI">AIT_PS_TATAGUNI (Quality Analyser)</option>
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={handleSensorOffline}
                    className="mt-3 px-3 py-1.5 rounded border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 text-[11px] transition-colors"
                  >
                    Set Offline
                  </button>
                </div>

                {/* Meter Offline */}
                <div className="flex items-center justify-between gap-2">
                  <div className="flex-1">
                    <span className="text-[10px] text-slate-500 font-mono block">Bulk Meter Comms Cut</span>
                    <select
                      value={selectedMeter}
                      onChange={(e) => setSelectedMeter(e.target.value)}
                      className="w-full p-1.5 rounded border border-slate-300 dark:border-slate-700 bg-slate-50 dark:bg-slate-800 text-[11px]"
                    >
                      <option value="FIT_MJ_INLET">FIT_MJ_INLET (Mount Joy Inlet)</option>
                      <option value="FIT_WTP_TKH_IN">FIT_WTP_TKH_IN (T.K. Halli Bulk In)</option>
                      <option value="FIT_DMA_SOUTH_01">FIT_DMA_SOUTH_01 (Basavanagudi DMA)</option>
                    </select>
                  </div>
                  <button
                    type="button"
                    onClick={handleMeterOffline}
                    className="mt-3 px-3 py-1.5 rounded border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 text-[11px] transition-colors"
                  >
                    Cut Comms
                  </button>
                </div>

                {/* Audit Log (Small list inside accordion) */}
                <div className="pt-2 border-t border-slate-200 dark:border-slate-800">
                  <span className="text-[10px] text-slate-500 font-mono uppercase block mb-1">
                    Audit Log
                  </span>
                  <div className="max-h-24 overflow-y-auto space-y-1 pr-1 font-mono text-[10px]">
                    {auditLog.map((entry, idx) => (
                      <div key={idx} className="flex justify-between text-slate-400 py-0.5 border-b border-slate-100 dark:border-slate-800/60">
                        <span>{entry.timestamp} • {entry.action}</span>
                        <span className="truncate max-w-[180px] text-slate-300">{entry.details}</span>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
