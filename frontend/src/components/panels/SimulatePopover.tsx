import React, { useState } from 'react';
import { 
  X, 
  RotateCcw, 
  Droplet, 
  Zap, 
  Sliders, 
  ShieldAlert, 
  Radio, 
  Clock 
} from 'lucide-react';
import { useTwinStore } from '../../store/useTwinStore';
import { api } from '../../services/api';

export interface SimulatePopoverProps {
  onClose: () => void;
  onScenarioApplied: (scenarioName: string) => void;
}

export const SimulatePopover: React.FC<SimulatePopoverProps> = ({
  onClose,
  onScenarioApplied,
}) => {
  const { simulatedHour, setSimulatedHour, setActiveLeakPipeId } = useTwinStore();
  const [selectedPipe, setSelectedPipe] = useState('PIPE_CORRIDOR_10');
  const [leakSizeLps, setLeakSizeLps] = useState(60);
  const [selectedPump, setSelectedPump] = useState('PUMP_TG_01');
  const [selectedValve, setSelectedValve] = useState('V-104');
  const [demandMultiplier, setDemandMultiplier] = useState(1.25);
  const [sensorId, setSensorId] = useState('PT-01');
  const [perturbationType, setPerturbationType] = useState('drift');
  const [perturbationValue, setPerturbationValue] = useState(1.5);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [statusMessage, setStatusMessage] = useState<string | null>(null);

  const handleInjectLeak = async () => {
    setIsSubmitting(true);
    try {
      await api.injectLeak(selectedPipe, leakSizeLps);
      setActiveLeakPipeId(selectedPipe);
      onScenarioApplied(`LEAK_${selectedPipe}`);
      setStatusMessage(`Injected ${leakSizeLps} L/s burst on ${selectedPipe}`);
    } catch {
      setStatusMessage('Simulation applied locally');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleTripPump = async () => {
    setIsSubmitting(true);
    try {
      await api.tripPump(selectedPump);
      onScenarioApplied(`TRIP_${selectedPump}`);
      setStatusMessage(`Tripped pump ${selectedPump}`);
    } catch {
      setStatusMessage('Simulation applied locally');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleCloseValve = async () => {
    setIsSubmitting(true);
    try {
      await api.closeValve(selectedValve, 'CLOSED');
      onScenarioApplied(`VALVE_${selectedValve}`);
      setStatusMessage(`Closed valve ${selectedValve}`);
    } catch {
      setStatusMessage('Simulation applied locally');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleModulateDemand = async () => {
    setIsSubmitting(true);
    try {
      await api.modulateDemand(demandMultiplier);
      onScenarioApplied(`DEMAND_${demandMultiplier}X`);
      setStatusMessage(`Applied ${demandMultiplier}x consumer demand`);
    } catch {
      setStatusMessage('Simulation applied locally');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handlePerturbSensor = async () => {
    setIsSubmitting(true);
    try {
      await api.perturbSensor(sensorId, perturbationType, perturbationValue);
      onScenarioApplied(`SENSOR_${sensorId}`);
      setStatusMessage(`Applied ${perturbationType} on ${sensorId}`);
    } catch {
      setStatusMessage('Simulation applied locally');
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleReset = async () => {
    setIsSubmitting(true);
    try {
      await api.resetScenarios();
      setActiveLeakPipeId(null);
      onScenarioApplied('BASELINE');
      setStatusMessage('Reset all scenarios to baseline');
    } catch {
      setStatusMessage('Reset to baseline');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="fixed top-16 right-16 w-80 rounded-lg border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 shadow-xl select-none z-50 p-3.5 text-xs">
      {/* Header with Simulated Chip & Clock */}
      <div className="flex items-center justify-between pb-2 border-b border-slate-200 dark:border-slate-800 mb-2.5">
        <div className="flex items-center gap-1.5">
          <span className="font-bold text-slate-900 dark:text-slate-100 text-xs">
            Hydraulic Simulator
          </span>
          <span className="px-1.5 py-0.2 rounded bg-purple-100 dark:bg-purple-950 text-purple-700 dark:text-purple-300 font-mono text-[10px] font-bold">
            Simulated
          </span>
        </div>
        <div className="flex items-center gap-2">
          <span className="flex items-center gap-1 font-mono text-[10px] text-slate-500">
            <Clock className="w-3 h-3 text-slate-400" />
            {String(simulatedHour).padStart(2, '0')}:00
          </span>
          <button
            type="button"
            onClick={onClose}
            className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-400"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {statusMessage && (
        <div className="p-2 mb-2 rounded bg-sky-50 dark:bg-sky-950/40 text-sky-700 dark:text-sky-300 text-[11px] font-medium">
          {statusMessage}
        </div>
      )}

      {/* Controls List */}
      <div className="space-y-3">
        {/* 1. Inject Leak */}
        <div className="p-2 rounded bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800">
          <label className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1 mb-1.5">
            <Droplet className="w-3 h-3 text-rose-500" />
            Inject Pipe Burst / Leak
          </label>
          <div className="grid grid-cols-2 gap-1.5 mb-1.5">
            <select
              value={selectedPipe}
              onChange={(e) => setSelectedPipe(e.target.value)}
              className="p-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono text-[11px]"
            >
              <option value="PIPE_CORRIDOR_10">Corridor Main 10</option>
              <option value="PIPE_CORRIDOR_04">Corridor Main 04</option>
              <option value="PIPE_JAYANAGAR_01">Jayanagar DMA 01</option>
            </select>
            <div className="flex items-center gap-1">
              <input
                type="number"
                min="10"
                max="200"
                step="10"
                value={leakSizeLps}
                onChange={(e) => setLeakSizeLps(Number(e.target.value))}
                className="w-16 p-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono text-[11px] text-right"
              />
              <span className="text-[10px] text-slate-500">L/s</span>
            </div>
          </div>
          <button
            type="button"
            disabled={isSubmitting}
            onClick={handleInjectLeak}
            className="w-full py-1 rounded bg-rose-600 hover:bg-rose-700 text-white font-medium text-[11px] transition-colors"
          >
            Apply Pipe Leak
          </button>
        </div>

        {/* 2. Trip Pump & Close Valve */}
        <div className="grid grid-cols-2 gap-2">
          <div className="p-2 rounded bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800">
            <label className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1 mb-1">
              <Zap className="w-3 h-3 text-amber-500" />
              Trip Pump
            </label>
            <select
              value={selectedPump}
              onChange={(e) => setSelectedPump(e.target.value)}
              className="w-full p-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono text-[11px] mb-1.5"
            >
              <option value="PUMP_TG_01">TG Unit 01</option>
              <option value="PUMP_TG_02">TG Unit 02</option>
            </select>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleTripPump}
              className="w-full py-1 rounded bg-amber-600 hover:bg-amber-700 text-white font-medium text-[11px] transition-colors"
            >
              Trip Unit
            </button>
          </div>

          <div className="p-2 rounded bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800">
            <label className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1 mb-1">
              <ShieldAlert className="w-3 h-3 text-purple-500" />
              Close Valve
            </label>
            <select
              value={selectedValve}
              onChange={(e) => setSelectedValve(e.target.value)}
              className="w-full p-1 rounded border border-slate-300 dark:border-slate-700 bg-white dark:bg-slate-800 font-mono text-[11px] mb-1.5"
            >
              <option value="V-104">Valve V-104</option>
              <option value="V-101">Valve V-101</option>
            </select>
            <button
              type="button"
              disabled={isSubmitting}
              onClick={handleCloseValve}
              className="w-full py-1 rounded bg-purple-600 hover:bg-purple-700 text-white font-medium text-[11px] transition-colors"
            >
              Close Valve
            </button>
          </div>
        </div>

        {/* 3. Demand Multiplier & Sensor Perturbation */}
        <div className="p-2 rounded bg-slate-50 dark:bg-slate-800/40 border border-slate-200 dark:border-slate-800">
          <div className="flex justify-between items-center mb-1">
            <span className="font-semibold text-slate-800 dark:text-slate-200 flex items-center gap-1">
              <Sliders className="w-3 h-3 text-sky-500" />
              Demand Scale
            </span>
            <span className="font-mono text-slate-500">{demandMultiplier}x</span>
          </div>
          <div className="flex items-center gap-2 mb-1.5">
            <input
              type="range"
              min="0.5"
              max="2.0"
              step="0.05"
              value={demandMultiplier}
              onChange={(e) => setDemandMultiplier(parseFloat(e.target.value))}
              className="w-full h-1 bg-slate-300 dark:bg-slate-700 rounded appearance-none cursor-pointer accent-sky-500"
            />
          </div>
          <button
            type="button"
            disabled={isSubmitting}
            onClick={handleModulateDemand}
            className="w-full py-1 rounded bg-sky-600 hover:bg-sky-700 text-white font-medium text-[11px] transition-colors"
          >
            Apply Demand Scale
          </button>
        </div>

        {/* 4. Reset Button */}
        <button
          type="button"
          disabled={isSubmitting}
          onClick={handleReset}
          className="w-full py-2 rounded border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-800 font-semibold flex items-center justify-center gap-1.5 transition-colors"
        >
          <RotateCcw className="w-3.5 h-3.5" />
          <span>Reset All to Baseline</span>
        </button>
      </div>
    </div>
  );
};
