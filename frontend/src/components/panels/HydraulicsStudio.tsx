import React, { useState, useEffect } from 'react';
import { api } from '../../services/api';
import { ProvenanceChip } from '../common/ProvenanceChip';
import { 
  Cpu, 
  Droplet, 
  Zap, 
  Activity, 
  AlertTriangle, 
  Play, 
  RotateCcw, 
  Radio, 
  X,
  Gauge,
  Sliders,
  CheckCircle2,
  Scale,
  FileText,
  ToggleLeft,
  ToggleRight,
  ShieldAlert,
  Target,
  BarChart3,
  TrendingDown,
  DollarSign,
  AlertOctagon,
  HelpCircle,
  Clock,
  MapPin
} from 'lucide-react';
import { 
  LineChart, 
  Line, 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  Tooltip, 
  ResponsiveContainer, 
  CartesianGrid 
} from 'recharts';

interface HydraulicsStudioProps {
  onClose: () => void;
  activeScenario: string;
  onScenarioChange: (scenario: string) => void;
  initialTab?: 'scenarios' | 'leak_detection' | 'validation' | 'sensors' | 'mass_balance' | 'audit_log';
}

export const HydraulicsStudio: React.FC<HydraulicsStudioProps> = ({
  onClose,
  activeScenario,
  onScenarioChange,
  initialTab = 'scenarios',
}) => {
  const [activeTab, setActiveTab] = useState<'scenarios' | 'leak_detection' | 'validation' | 'sensors' | 'mass_balance' | 'audit_log'>(initialTab);
  const [pumps, setPumps] = useState<any[]>([]);
  const [meters, setMeters] = useState<any[]>([]);
  const [sensors, setSensors] = useState<any[]>([]);
  const [massBalance, setMassBalance] = useState<any>(null);
  const [auditLog, setAuditLog] = useState<any[]>([]);
  const [leakAnalysis, setLeakAnalysis] = useState<any>(null);
  const [validationReport, setValidationReport] = useState<any>(null);
  const [isValidating, setIsValidating] = useState<boolean>(false);
  const [telemetry, setTelemetry] = useState<any>({
    speed: 1450.0,
    motor_temp_c: 68.5,
    motor_current_a: 95.2,
    status: 'LIVE_STREAM',
    data_tier: 'LIVE',
  });
  const [pressureProfile, setPressureProfile] = useState<any[]>([]);

  // Scenario form inputs
  const [selectedLeakPipe, setSelectedLeakPipe] = useState('PIPE_CORRIDOR_10');
  const [leakSizeLps, setLeakSizeLps] = useState(60);
  const [selectedValve, setSelectedValve] = useState('VALVE_BVG_ISO');
  const [selectedPumpTrip, setSelectedPumpTrip] = useState('PUMP_TG_01');
  const [demandMultiplier, setDemandMultiplier] = useState(1.25);
  const [perturbSensorId, setPerturbSensorId] = useState('FM_KANAKAPURA');
  const [perturbType, setPerturbType] = useState('stuck');
  const [perturbValue, setPerturbValue] = useState(45.0);
  const [isApplying, setIsApplying] = useState(false);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);

  useEffect(() => {
    loadAllData();
    const eventSource = new EventSource('/api/v1/telemetry/stream');
    eventSource.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        setTelemetry(data);
      } catch (err) {
        console.error('SSE parse error:', err);
      }
    };

    return () => {
      eventSource.close();
    };
  }, []);

  const loadAllData = async () => {
    try {
      const pData = await api.getPumpMetrics();
      setPumps(pData.pumps || []);

      const mData = await api.getFlowMeters();
      setMeters(mData.flow_meters || []);

      const zoneData = await api.getSimulatedZone();
      const nodeFeatures = (zoneData.features || []).filter(
        (f: any) => f.geometry.type === 'Point' && f.properties.current_pressure_bar !== undefined
      );

      const profile = nodeFeatures.map((f: any) => ({
        name: f.properties.id.replace('N_', ''),
        pressure: f.properties.current_pressure_bar,
        elevation: f.properties.elevation_m,
      }));
      setPressureProfile(profile);

      const mb = await api.getMassBalance();
      setMassBalance(mb);

      const audit = await api.getScenarioAuditLog();
      setAuditLog(audit.audit_log || []);

      const lData = await api.getLeakDetectionStatus();
      setLeakAnalysis(lData);
    } catch (err) {
      console.error('Error loading hydraulics studio data:', err);
    }
  };

  const notifyAction = (msg: string) => {
    setActionSuccess(msg);
    setTimeout(() => setActionSuccess(null), 2500);
  };

  const handleInjectLeak = async () => {
    setIsApplying(true);
    try {
      await api.injectLeak(selectedLeakPipe, leakSizeLps);
      onScenarioChange('LEAK_INJECTION');
      notifyAction(`Injected ${leakSizeLps} LPS leak on ${selectedLeakPipe}`);
      await loadAllData();
      setActiveTab('leak_detection');
    } finally {
      setIsApplying(false);
    }
  };

  const handleCloseValve = async () => {
    setIsApplying(true);
    try {
      await api.closeValve(selectedValve, 'CLOSED');
      onScenarioChange('VALVE_CLOSURE');
      notifyAction(`Closed valve/pipe ${selectedValve}`);
      await loadAllData();
    } finally {
      setIsApplying(false);
    }
  };

  const handleTripPump = async () => {
    setIsApplying(true);
    try {
      await api.tripPump(selectedPumpTrip);
      onScenarioChange('PUMP_TRIP');
      notifyAction(`Tripped pump ${selectedPumpTrip}`);
      await loadAllData();
    } finally {
      setIsApplying(false);
    }
  };

  const handleModulateDemand = async () => {
    setIsApplying(true);
    try {
      await api.modulateDemand(demandMultiplier);
      onScenarioChange('DEMAND_MODULATION');
      notifyAction(`Scaled demand by ${demandMultiplier}x`);
      await loadAllData();
    } finally {
      setIsApplying(false);
    }
  };

  const handlePerturbSensor = async () => {
    setIsApplying(true);
    try {
      await api.perturbSensor(perturbSensorId, perturbType, perturbValue);
      onScenarioChange('SENSOR_PERTURBATION');
      notifyAction(`Applied ${perturbType} (${perturbValue}) to ${perturbSensorId}`);
      await loadAllData();
    } finally {
      setIsApplying(false);
    }
  };

  const handleReset = async () => {
    setIsApplying(true);
    try {
      await api.resetScenarios();
      onScenarioChange('BASELINE');
      notifyAction('Reset all scenarios to baseline supply');
      await loadAllData();
    } finally {
      setIsApplying(false);
    }
  };

  const handleToggleSensorSource = async (sensorId: string, currentSource: string) => {
    const nextSource = currentSource === 'SIMULATED' ? 'IGNOAPI' : 'SIMULATED';
    await api.toggleSensorSource(sensorId, nextSource);
    notifyAction(`Sensor ${sensorId} source: ${nextSource}`);
    await loadAllData();
  };

  const handleRunValidation = async () => {
    setIsValidating(true);
    try {
      const rep = await api.runLeakValidation();
      setValidationReport(rep);
      notifyAction(`Completed validation across ${rep.total_scenarios_tested} scenarios`);
      await loadAllData();
    } catch (err) {
      console.error('Validation error:', err);
    } finally {
      setIsValidating(false);
    }
  };

  const activeLeakEvents = leakAnalysis?.leak_events || [];

  return (
    <div className="absolute top-16 right-4 z-30 w-[640px] bg-slate-900/95 border border-slate-800 rounded-2xl shadow-2xl backdrop-blur-xl p-5 text-slate-100 flex flex-col max-h-[calc(100vh-100px)] overflow-hidden font-sans animate-in slide-in-from-right duration-200">
      {/* Header */}
      <div className="flex items-center justify-between pb-3.5 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-purple-950/80 border border-purple-800/80 text-purple-400">
            <Cpu className="w-5 h-5" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-base font-bold text-slate-100 tracking-tight">
                Hydraulics & Leak Detection Studio
              </h2>
              <ProvenanceChip tier="SIMULATED" size="sm" showDetails={false} />
            </div>
            <p className="text-[11px] text-slate-400">
              WNTR / EPANET Hydraulic Twin • Mass Balance • Probabilistic Localisation
            </p>
          </div>
        </div>
        <button
          onClick={onClose}
          className="p-1 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition-colors"
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Tabs */}
      <div className="flex items-center gap-1 pt-3 pb-2 border-b border-slate-800 text-xs overflow-x-auto">
        <button
          onClick={() => setActiveTab('scenarios')}
          className={`px-2.5 py-1.5 font-medium rounded-lg transition-colors whitespace-nowrap ${
            activeTab === 'scenarios'
              ? 'bg-purple-950 text-purple-200 border border-purple-800'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Scenarios
        </button>

        <button
          onClick={() => setActiveTab('leak_detection')}
          className={`px-2.5 py-1.5 font-medium rounded-lg transition-colors flex items-center gap-1.5 whitespace-nowrap relative ${
            activeTab === 'leak_detection'
              ? 'bg-rose-950 text-rose-200 border border-rose-800'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <ShieldAlert className="w-3.5 h-3.5 text-rose-400" />
          <span>Leak Analysis</span>
          {activeLeakEvents.length > 0 && (
            <span className="w-2 h-2 rounded-full bg-rose-500 animate-pulse" />
          )}
        </button>

        <button
          onClick={() => setActiveTab('validation')}
          className={`px-2.5 py-1.5 font-medium rounded-lg transition-colors flex items-center gap-1 whitespace-nowrap ${
            activeTab === 'validation'
              ? 'bg-amber-950 text-amber-200 border border-amber-800'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          <BarChart3 className="w-3.5 h-3.5 text-amber-400" />
          <span>Validation Suite</span>
        </button>

        <button
          onClick={() => setActiveTab('sensors')}
          className={`px-2.5 py-1.5 font-medium rounded-lg transition-colors whitespace-nowrap ${
            activeTab === 'sensors'
              ? 'bg-purple-950 text-purple-200 border border-purple-800'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Sensors
        </button>

        <button
          onClick={() => setActiveTab('mass_balance')}
          className={`px-2.5 py-1.5 font-medium rounded-lg transition-colors whitespace-nowrap ${
            activeTab === 'mass_balance'
              ? 'bg-purple-950 text-purple-200 border border-purple-800'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Mass Balance
        </button>

        <button
          onClick={() => setActiveTab('audit_log')}
          className={`px-2.5 py-1.5 font-medium rounded-lg transition-colors whitespace-nowrap ${
            activeTab === 'audit_log'
              ? 'bg-purple-950 text-purple-200 border border-purple-800'
              : 'text-slate-400 hover:text-slate-200'
          }`}
        >
          Audit Log
        </button>
      </div>

      {actionSuccess && (
        <div className="my-2 p-2 bg-emerald-950/80 border border-emerald-800 rounded-lg text-emerald-300 text-xs flex items-center gap-2 animate-in fade-in">
          <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0" />
          <span>{actionSuccess}</span>
        </div>
      )}

      {/* Tab Panels */}
      <div className="flex-1 overflow-y-auto space-y-4 py-3 pr-1 text-xs">
        
        {/* Tab 1: Scenarios & Injection Controls */}
        {activeTab === 'scenarios' && (
          <div className="space-y-4">
            {/* Live Hardware Telemetry Banner (IGNOAPI) */}
            <div className="p-3 bg-gradient-to-r from-cyan-950/40 to-slate-950/60 border border-cyan-800/60 rounded-xl space-y-2">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-cyan-300 flex items-center gap-1.5 text-xs">
                  <Radio className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />
                  Live Motor Telemetry (IGNOAPI Port 8899)
                </span>
                <ProvenanceChip tier="LIVE" size="sm" showDetails={false} />
              </div>

              <div className="grid grid-cols-3 gap-2 font-mono text-[11px]">
                <div className="p-2 bg-slate-950/80 rounded border border-slate-800">
                  <span className="text-[10px] text-slate-400 block font-sans">Shaft Speed</span>
                  <span className="font-bold text-cyan-300">{telemetry.speed} RPM</span>
                </div>
                <div className="p-2 bg-slate-950/80 rounded border border-slate-800">
                  <span className="text-[10px] text-slate-400 block font-sans">Stator Temp</span>
                  <span className="font-bold text-emerald-300">{telemetry.motor_temp_c} °C</span>
                </div>
                <div className="p-2 bg-slate-950/80 rounded border border-slate-800">
                  <span className="text-[10px] text-slate-400 block font-sans">Current Draw</span>
                  <span className="font-bold text-amber-300">{telemetry.motor_current_a} A</span>
                </div>
              </div>
            </div>

            {/* Pressure Profile Chart */}
            <div className="p-3 bg-slate-950/70 border border-slate-800 rounded-xl space-y-1.5">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200 text-xs flex items-center gap-1.5">
                  <Gauge className="w-3.5 h-3.5 text-cyan-400" />
                  Corridor Hydraulic Pressure Profile (bar)
                </span>
                <span className="text-[10px] text-slate-500 font-mono">20 Corridor Nodes</span>
              </div>

              <div className="h-32 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={pressureProfile} margin={{ top: 5, right: 10, left: -25, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                    <XAxis dataKey="name" tick={{ fontSize: 8, fill: '#64748b' }} interval={2} />
                    <YAxis domain={[0, 4.5]} tick={{ fontSize: 8, fill: '#64748b' }} />
                    <Tooltip
                      contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '11px' }}
                    />
                    <Line type="monotone" dataKey="pressure" stroke="#38bdf8" strokeWidth={2} dot={{ r: 2 }} />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Scenario Injection Controls */}
            <div className="p-4 bg-slate-950/70 border border-slate-800 rounded-xl space-y-3">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200 text-xs flex items-center gap-1.5">
                  <Sliders className="w-4 h-4 text-purple-400" />
                  Scenario Injection Controls (All Labelled SIMULATED)
                </span>
                <button
                  onClick={handleReset}
                  disabled={isApplying}
                  className="px-2.5 py-1 text-[11px] bg-slate-800 hover:bg-slate-700 text-slate-200 rounded-md font-medium flex items-center gap-1 transition-colors"
                >
                  <RotateCcw className="w-3 h-3" />
                  Reset Baseline
                </button>
              </div>

              {/* 1. Pipe Burst / Leak Injection */}
              <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-200 text-xs flex items-center gap-1.5">
                    <Droplet className="w-3.5 h-3.5 text-rose-400" />
                    Inject Pipe Burst / Leak
                  </span>
                  <span className="text-[10px] text-slate-500 font-mono">Modifies EPANET Base Demand</span>
                </div>
                <div className="grid grid-cols-3 gap-2">
                  <select
                    value={selectedLeakPipe}
                    onChange={(e) => setSelectedLeakPipe(e.target.value)}
                    className="col-span-2 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-rose-500"
                  >
                    <option value="PIPE_CORRIDOR_10">PIPE_CORRIDOR_10 (Basavanagudi Feeder)</option>
                    <option value="PIPE_CORRIDOR_04">PIPE_CORRIDOR_04 (Kanakapura Road Metro)</option>
                    <option value="PIPE_CORRIDOR_05">PIPE_CORRIDOR_05 (Sarakki Signal Feeder)</option>
                    <option value="PIPE_CORRIDOR_01">PIPE_CORRIDOR_01 (Tataguni Transmission)</option>
                    <option value="PIPE_CORRIDOR_15">PIPE_CORRIDOR_15 (City Market Avenue)</option>
                  </select>
                  <div className="flex items-center gap-1 bg-slate-950 border border-slate-700 rounded-lg px-2">
                    <input
                      type="number"
                      value={leakSizeLps}
                      onChange={(e) => setLeakSizeLps(Number(e.target.value))}
                      className="w-full bg-transparent text-xs text-slate-200 focus:outline-none font-mono"
                      min={5}
                      max={200}
                    />
                    <span className="text-[10px] text-slate-500">LPS</span>
                  </div>
                </div>
                <button
                  onClick={handleInjectLeak}
                  disabled={isApplying}
                  className="w-full py-1.5 bg-rose-600/90 hover:bg-rose-500 text-white rounded-lg font-medium text-xs flex items-center justify-center gap-1.5 shadow-sm transition-all"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Inject Leak & Run Leak Detector</span>
                </button>
              </div>

              {/* 2. Isolation Valve Closure */}
              <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg space-y-2">
                <span className="font-medium text-slate-200 text-xs flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 text-amber-400" />
                  Close / Throttle Isolation Valve
                </span>
                <div className="flex gap-2">
                  <select
                    value={selectedValve}
                    onChange={(e) => setSelectedValve(e.target.value)}
                    className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-amber-500"
                  >
                    <option value="VALVE_BVG_ISO">VALVE_BVG_ISO (Basavanagudi V-104)</option>
                    <option value="VALVE_BSK_PRV">VALVE_BSK_PRV (Banashankari PRV)</option>
                    <option value="VALVE_HG_TCV">VALVE_HG_TCV (High Grounds Throttle)</option>
                  </select>
                  <button
                    onClick={handleCloseValve}
                    disabled={isApplying}
                    className="px-3 py-1.5 bg-amber-600/90 hover:bg-amber-500 text-white rounded-lg font-medium text-xs transition-colors"
                  >
                    Close Valve
                  </button>
                </div>
              </div>

              {/* 3. Pump Unit Trip */}
              <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg space-y-2">
                <span className="font-medium text-slate-200 text-xs flex items-center gap-1.5">
                  <Zap className="w-3.5 h-3.5 text-yellow-400" />
                  Trip Pumping Station Unit
                </span>
                <div className="flex gap-2">
                  <select
                    value={selectedPumpTrip}
                    onChange={(e) => setSelectedPumpTrip(e.target.value)}
                    className="flex-1 bg-slate-950 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 focus:outline-none focus:border-yellow-500"
                  >
                    <option value="PUMP_TG_01">PUMP_TG_01 (Tataguni Stage Pump 1 - Duty)</option>
                    <option value="PUMP_TG_02">PUMP_TG_02 (Tataguni Stage Pump 2 - Duty)</option>
                  </select>
                  <button
                    onClick={handleTripPump}
                    disabled={isApplying}
                    className="px-3 py-1.5 bg-yellow-600/90 hover:bg-yellow-500 text-slate-950 rounded-lg font-medium text-xs transition-colors"
                  >
                    Trip Pump
                  </button>
                </div>
              </div>

              {/* 4. Consumer Demand Scaling */}
              <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg space-y-2">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-slate-200 text-xs">Scale Corridor Demand</span>
                  <span className="text-cyan-400 font-mono text-xs">{demandMultiplier}x</span>
                </div>
                <div className="flex items-center gap-2">
                  <input
                    type="range"
                    min="0.5"
                    max="2.0"
                    step="0.05"
                    value={demandMultiplier}
                    onChange={(e) => setDemandMultiplier(Number(e.target.value))}
                    className="flex-1 accent-cyan-500"
                  />
                  <button
                    onClick={handleModulateDemand}
                    disabled={isApplying}
                    className="px-3 py-1 bg-cyan-600/90 hover:bg-cyan-500 text-white rounded-lg font-medium text-xs transition-colors"
                  >
                    Apply Scale
                  </button>
                </div>
              </div>

              {/* 5. Sensor Fault Injection (Drift / Stuck) */}
              <div className="p-3 bg-slate-900/60 border border-slate-800 rounded-lg space-y-2">
                <span className="font-medium text-slate-200 text-xs flex items-center gap-1.5">
                  <AlertTriangle className="w-3.5 h-3.5 text-orange-400" />
                  Sensor Fault Injection (Stuck / Drift)
                </span>
                <div className="grid grid-cols-3 gap-2">
                  <select
                    value={perturbSensorId}
                    onChange={(e) => setPerturbSensorId(e.target.value)}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-200 focus:outline-none"
                  >
                    <option value="FM_KANAKAPURA">FM_KANAKAPURA (Flow)</option>
                    <option value="FM_BASAVANAGUDI">FM_BASAVANAGUDI (Flow)</option>
                    <option value="PT_BASAVANAGUDI">PT_BASAVANAGUDI (Press)</option>
                    <option value="PT_TALAGHATTAPURA">PT_TALAGHATTAPURA (Press)</option>
                  </select>
                  <select
                    value={perturbType}
                    onChange={(e) => setPerturbType(e.target.value)}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-200 focus:outline-none"
                  >
                    <option value="stuck">Stuck Sensor</option>
                    <option value="drift">Sensor Drift</option>
                  </select>
                  <input
                    type="number"
                    step="0.1"
                    value={perturbValue}
                    onChange={(e) => setPerturbValue(Number(e.target.value))}
                    className="bg-slate-950 border border-slate-700 rounded-lg px-2 py-1 text-xs text-slate-200 focus:outline-none font-mono"
                  />
                </div>
                <button
                  onClick={handlePerturbSensor}
                  disabled={isApplying}
                  className="w-full py-1.5 bg-orange-600/90 hover:bg-orange-500 text-white rounded-lg font-medium text-xs transition-colors"
                >
                  Perturb Sensor & Check False Alarm Suppression
                </button>
              </div>
            </div>
          </div>
        )}

        {/* Tab 2: Leak Detection & Probabilistic Localisation */}
        {activeTab === 'leak_detection' && (
          <div className="space-y-4">
            {/* Active Leak Events List */}
            {activeLeakEvents.length === 0 ? (
              <div className="p-4 bg-emerald-950/40 border border-emerald-800/80 rounded-xl space-y-2 text-center">
                <CheckCircle2 className="w-8 h-8 text-emerald-400 mx-auto" />
                <h3 className="font-bold text-emerald-300 text-sm">No Active Leaks Detected</h3>
                <p className="text-[11px] text-slate-300 leading-relaxed max-w-md mx-auto">
                  Continuity mass balance holds within dynamic sensor noise limits (N=3 of M=4 intervals) across all DMA corridors. Minimum Night Flow (MNF) analysis indicates nominal baseline consumption.
                </p>
                <button
                  onClick={() => setActiveTab('scenarios')}
                  className="mt-2 px-3 py-1.5 bg-purple-900/60 hover:bg-purple-800 border border-purple-700 rounded-lg text-purple-200 font-medium text-xs inline-flex items-center gap-1.5"
                >
                  <Play className="w-3.5 h-3.5" />
                  <span>Go to Scenarios to Inject a Leak</span>
                </button>
              </div>
            ) : (
              activeLeakEvents.map((evt: any) => (
                <div key={evt.leak_id} className="p-4 bg-rose-950/40 border border-rose-800/80 rounded-2xl space-y-3.5 shadow-lg">
                  {/* Event Header */}
                  <div className="flex items-start justify-between">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="px-2 py-0.5 rounded-full bg-rose-900 text-rose-200 text-[10px] font-mono font-bold">
                          {evt.leak_id}
                        </span>
                        <ProvenanceChip tier="SIMULATED" size="sm" showDetails={false} />
                        <span className="text-[10px] bg-slate-800 text-slate-300 px-2 py-0.5 rounded-full font-mono font-semibold">
                          Confidence: {evt.confidence_pct}%
                        </span>
                      </div>
                      <h3 className="text-sm font-bold text-slate-100 mt-1">
                        {evt.segment_name}
                      </h3>
                      <p className="text-[11px] text-slate-300 flex items-center gap-1 mt-0.5">
                        <MapPin className="w-3 h-3 text-rose-400" />
                        <span>Near {evt.nearest_landmark}</span>
                      </p>
                    </div>

                    <div className="text-right font-mono">
                      <span className="text-[10px] text-slate-400 block font-sans">Detected At</span>
                      <span className="text-xs text-rose-300 font-bold">{evt.start_time}</span>
                    </div>
                  </div>

                  {/* Estimated Loss KPI Cards */}
                  <div className="grid grid-cols-3 gap-2 font-mono">
                    <div className="p-2.5 bg-slate-950/80 rounded-xl border border-rose-900/60">
                      <span className="text-[10px] text-slate-400 font-sans block">Loss Rate</span>
                      <span className="text-sm font-bold text-rose-400">
                        {evt.loss_metrics.estimated_loss_lps} <span className="text-[10px] font-normal">LPS</span>
                      </span>
                    </div>
                    <div className="p-2.5 bg-slate-950/80 rounded-xl border border-rose-900/60">
                      <span className="text-[10px] text-slate-400 font-sans block">Volume Flow</span>
                      <span className="text-sm font-bold text-rose-300">
                        {evt.loss_metrics.estimated_loss_litres_per_min} <span className="text-[10px] font-normal">L/min</span>
                      </span>
                    </div>
                    <div className="p-2.5 bg-slate-950/80 rounded-xl border border-rose-900/60">
                      <span className="text-[10px] text-slate-400 font-sans block">Daily Volume</span>
                      <span className="text-sm font-bold text-amber-300">
                        {evt.loss_metrics.estimated_loss_m3_per_day} <span className="text-[10px] font-normal">m³/day</span>
                      </span>
                    </div>
                  </div>

                  {/* Probabilistic Localisation Box */}
                  <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl space-y-2">
                    <div className="flex items-center justify-between">
                      <span className="font-semibold text-slate-200 text-xs flex items-center gap-1.5">
                        <Target className="w-3.5 h-3.5 text-cyan-400" />
                        Probabilistic Position Along Pipe ({evt.pipe_id})
                      </span>
                      <span className="text-[10px] text-cyan-400 font-mono">
                        Pipe Length: {evt.pipe_length_m}m
                      </span>
                    </div>

                    <div className="p-2 bg-amber-950/50 border border-amber-800/80 rounded-lg text-[11px] text-amber-300 flex items-start gap-2">
                      <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                      <div>
                        <strong>Safety & Governance Mandate:</strong> {evt.localisation.disclaimer}
                      </div>
                    </div>

                    <div className="grid grid-cols-2 gap-2 font-mono text-[11px] pt-1">
                      <div className="p-2 bg-slate-900 rounded border border-slate-800">
                        <span className="text-[10px] text-slate-400 font-sans block">Estimated Distance</span>
                        <span className="font-bold text-cyan-300 text-xs">
                          {evt.localisation.estimated_distance_m}m ± {evt.localisation.uncertainty_range_m}m
                        </span>
                        <span className="text-[9px] text-slate-500 font-sans block">({evt.localisation.estimated_pct_along_pipe}% along pipe)</span>
                      </div>
                      <div className="p-2 bg-slate-900 rounded border border-slate-800">
                        <span className="text-[10px] text-slate-400 font-sans block">90% Confidence Window</span>
                        <span className="font-bold text-purple-300 text-xs">
                          {evt.localisation.confidence_interval_90_m[0]}m – {evt.localisation.confidence_interval_90_m[1]}m
                        </span>
                        <span className="text-[9px] text-slate-500 font-sans block">Span: {Math.round(evt.localisation.confidence_interval_90_m[1] - evt.localisation.confidence_interval_90_m[0])}m search zone</span>
                      </div>
                    </div>

                    {/* Localisation Probability Curve */}
                    <div className="pt-2">
                      <span className="text-[10px] text-slate-400 block pb-1">
                        Acoustic Correlation Probability Density Curve across Pipe Length:
                      </span>
                      <div className="h-28 w-full">
                        <ResponsiveContainer width="100%" height="100%">
                          <AreaChart data={evt.localisation.probability_curve} margin={{ top: 5, right: 10, left: -25, bottom: 5 }}>
                            <defs>
                              <linearGradient id="probGradient" x1="0" y1="0" x2="0" y2="1">
                                <stop offset="5%" stopColor="#38bdf8" stopOpacity={0.8}/>
                                <stop offset="95%" stopColor="#38bdf8" stopOpacity={0}/>
                              </linearGradient>
                            </defs>
                            <CartesianGrid strokeDasharray="3 3" stroke="#1e293b" />
                            <XAxis dataKey="distance_m" tick={{ fontSize: 8, fill: '#64748b' }} unit="m" />
                            <YAxis tick={{ fontSize: 8, fill: '#64748b' }} />
                            <Tooltip
                              contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '8px', fontSize: '11px' }}
                              formatter={(val: any) => [`${val}`, 'PDF Density']}
                              labelFormatter={(label) => `${label} meters from upstream`}
                            />
                            <Area type="monotone" dataKey="probability_density" stroke="#38bdf8" strokeWidth={2} fillOpacity={1} fill="url(#probGradient)" />
                          </AreaChart>
                        </ResponsiveContainer>
                      </div>
                    </div>
                  </div>

                  {/* Consequences & Financial Loss */}
                  <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl space-y-2">
                    <span className="font-semibold text-slate-200 text-xs flex items-center gap-1.5">
                      <TrendingDown className="w-3.5 h-3.5 text-rose-400" />
                      Assessed Consequences & Non-Revenue Water (NRW) Impact
                    </span>
                    <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
                      <div className="p-2 bg-slate-900 rounded border border-slate-800">
                        <span className="text-[10px] text-slate-400 font-sans block">Affected Consumers</span>
                        <span className="font-bold text-amber-300">{evt.consequences.affected_consumer_connections.toLocaleString()} connections</span>
                        <span className="text-[9px] text-slate-500 font-sans block">Downstream terminal pressure deficit</span>
                      </div>
                      <div className="p-2 bg-slate-900 rounded border border-slate-800">
                        <span className="text-[10px] text-slate-400 font-sans block">Pressure Drop</span>
                        <span className="font-bold text-rose-400">{evt.consequences.downstream_pressure_drop_bar} bar</span>
                        <span className="text-[9px] text-slate-500 font-sans block">At downstream consumer clusters</span>
                      </div>
                      <div className="p-2 bg-slate-900 rounded border border-slate-800">
                        <span className="text-[10px] text-slate-400 font-sans block">Daily NRW Cost (Tariff ₹{evt.consequences.applied_tariff_inr_per_kl}/kL)</span>
                        <span className="font-bold text-rose-400">₹{evt.consequences.daily_nrw_revenue_loss_inr.toLocaleString()} / day</span>
                        <span className="text-[9px] text-slate-500 font-sans block">Non-Revenue Water physical loss</span>
                      </div>
                      <div className="p-2 bg-slate-900 rounded border border-slate-800">
                        <span className="text-[10px] text-slate-400 font-sans block">Extra Pump Energy</span>
                        <span className="font-bold text-purple-300">{evt.consequences.extra_pump_energy_kwh_day} kWh / day</span>
                        <span className="text-[9px] text-slate-500 font-sans block">₹{evt.consequences.daily_energy_cost_inr.toLocaleString()} daily energy cost</span>
                      </div>
                    </div>
                  </div>

                  {/* Recommended Operational Steps */}
                  <div className="p-3 bg-slate-950/80 border border-slate-800 rounded-xl space-y-2">
                    <span className="font-semibold text-slate-200 text-xs flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      Recommended Response Checklist (Human in the Loop)
                    </span>
                    <div className="space-y-1.5">
                      {evt.recommended_steps.map((st: any) => (
                        <div key={st.step_order} className="p-2 bg-slate-900 rounded-lg flex items-start gap-2 text-[11px]">
                          <span className="w-4 h-4 rounded-full bg-slate-800 text-slate-300 font-mono text-[10px] flex items-center justify-center shrink-0 mt-0.5">
                            {st.step_order}
                          </span>
                          <div className="flex-1">
                            <span className="font-bold text-slate-200 block text-[11px]">{st.action.replace(/_/g, ' ')}</span>
                            <span className="text-slate-400 text-[10px]">{st.description}</span>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                </div>
              ))
            )}

            {/* Segment Mass Balance Overview Cards */}
            <div className="space-y-2 pt-2">
              <span className="font-semibold text-slate-200 text-xs block">
                Corridor DMA Segment Mass Balance Registers
              </span>
              <div className="space-y-2">
                {(leakAnalysis?.segment_evaluations || []).map((seg: any) => (
                  <div key={seg.segment_id} className="p-3 bg-slate-950/60 border border-slate-800 rounded-xl space-y-2">
                    <div className="flex items-center justify-between">
                      <div>
                        <span className="font-bold text-slate-200 text-xs block">{seg.segment_name}</span>
                        <span className="text-[10px] text-slate-400 font-mono">{seg.segment_id} • {seg.nearest_landmark}</span>
                      </div>
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-mono font-bold ${
                        seg.is_leak_detected
                          ? 'bg-rose-950 text-rose-300 border border-rose-800 animate-pulse'
                          : (seg.has_sensor_fault ? 'bg-orange-950 text-orange-300 border border-orange-800' : 'bg-emerald-950 text-emerald-300 border border-emerald-800')
                      }`}>
                        {seg.is_leak_detected ? 'LEAK DETECTED' : (seg.has_sensor_fault ? 'SENSOR FAULT' : 'NORMAL')}
                      </span>
                    </div>

                    <div className="grid grid-cols-4 gap-2 font-mono text-[10px]">
                      <div className="p-1.5 bg-slate-900 rounded border border-slate-800">
                        <span className="text-slate-500 block font-sans">Inflow</span>
                        <span className="font-bold text-cyan-300">{seg.current_inflow_lps} LPS</span>
                      </div>
                      <div className="p-1.5 bg-slate-900 rounded border border-slate-800">
                        <span className="text-slate-500 block font-sans">Outflow</span>
                        <span className="font-bold text-slate-300">{seg.current_outflow_lps} LPS</span>
                      </div>
                      <div className="p-1.5 bg-slate-900 rounded border border-slate-800">
                        <span className="text-slate-500 block font-sans">Exp Demand</span>
                        <span className="font-bold text-purple-300">{seg.current_expected_demand_lps} LPS</span>
                      </div>
                      <div className="p-1.5 bg-slate-900 rounded border border-slate-800">
                        <span className="text-slate-500 block font-sans">Net Imbalance</span>
                        <span className={`font-bold ${seg.current_leak_estimate_lps > seg.tolerance_lps ? 'text-rose-400' : 'text-emerald-400'}`}>
                          {seg.current_leak_estimate_lps} LPS
                        </span>
                      </div>
                    </div>

                    {seg.night_flow_analysis && (
                      <div className="p-2 bg-slate-900/60 rounded flex items-center justify-between text-[10px] font-mono">
                        <span className="text-slate-400 font-sans">Night Flow (02:00-04:00 MNF):</span>
                        <span className={`font-semibold ${seg.night_flow_analysis.is_mnf_breached ? 'text-rose-300' : 'text-slate-300'}`}>
                          Observed {seg.night_flow_analysis.observed_mnf_lps} LPS (Baseline {seg.night_flow_analysis.baseline_mnf_lps} LPS, +{seg.night_flow_analysis.mnf_rise_pct}%)
                        </span>
                      </div>
                    )}
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}

        {/* Tab 3: Validation Suite */}
        {activeTab === 'validation' && (
          <div className="space-y-4">
            <div className="p-4 bg-slate-950/70 border border-slate-800 rounded-2xl space-y-3">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-slate-100 text-xs">
                    Automated Leak Detection Validation Suite
                  </h3>
                  <p className="text-[10px] text-slate-400">
                    Executes benchmark sweep across varying injected leak sizes & sensor fault scenarios
                  </p>
                </div>
                <button
                  onClick={handleRunValidation}
                  disabled={isValidating}
                  className="px-3 py-1.5 bg-amber-600/90 hover:bg-amber-500 text-slate-950 font-bold rounded-lg text-xs flex items-center gap-1.5 shadow-sm transition-all"
                >
                  <Play className={`w-3.5 h-3.5 fill-current ${isValidating ? 'animate-spin' : ''}`} />
                  <span>{isValidating ? 'Running Suite...' : 'Run Benchmarks'}</span>
                </button>
              </div>

              {validationReport && (
                <div className="space-y-3 pt-2">
                  <div className="grid grid-cols-4 gap-2 font-mono text-[11px]">
                    <div className="p-2 bg-slate-900 rounded-xl border border-slate-800 text-center">
                      <span className="text-[9px] text-slate-400 font-sans block">Detection Rate</span>
                      <span className="text-base font-bold text-emerald-400">{validationReport.detection_rate_pct}%</span>
                    </div>
                    <div className="p-2 bg-slate-900 rounded-xl border border-slate-800 text-center">
                      <span className="text-[9px] text-slate-400 font-sans block">Mean Delay</span>
                      <span className="text-base font-bold text-cyan-300">{validationReport.mean_detection_delay_hours}h</span>
                    </div>
                    <div className="p-2 bg-slate-900 rounded-xl border border-slate-800 text-center">
                      <span className="text-[9px] text-slate-400 font-sans block">False Alarms</span>
                      <span className="text-base font-bold text-emerald-300">{validationReport.false_alarms_per_day}/day</span>
                    </div>
                    <div className="p-2 bg-slate-900 rounded-xl border border-slate-800 text-center">
                      <span className="text-[9px] text-slate-400 font-sans block">Localisation Err</span>
                      <span className="text-base font-bold text-purple-300">{validationReport.mean_localisation_error_meters}m</span>
                    </div>
                  </div>

                  {/* Benchmark Scenarios Table */}
                  <div className="overflow-x-auto border border-slate-800 rounded-xl">
                    <table className="w-full text-[10px] text-left">
                      <thead className="bg-slate-950 text-slate-400 font-mono border-b border-slate-800">
                        <tr>
                          <th className="p-2">ID</th>
                          <th className="p-2">Scenario</th>
                          <th className="p-2">Size</th>
                          <th className="p-2">Detected</th>
                          <th className="p-2">Delay</th>
                          <th className="p-2">Loc Error</th>
                          <th className="p-2">Status</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y divide-slate-800/60 font-mono">
                        {validationReport.benchmark_results.map((r: any) => (
                          <tr key={r.scenario_id} className="hover:bg-slate-900/60">
                            <td className="p-2 text-cyan-400 font-bold">{r.scenario_id}</td>
                            <td className="p-2 text-slate-200 font-sans">{r.scenario_name}</td>
                            <td className="p-2 text-slate-300">{r.injected_leak_lps} LPS</td>
                            <td className="p-2">
                              {r.detected ? (
                                <span className="text-emerald-400 font-bold">YES ({r.confidence_pct}%)</span>
                              ) : (
                                <span className="text-slate-500">{r.injected_leak_lps === 5 ? 'Sub-noise' : '—'}</span>
                              )}
                            </td>
                            <td className="p-2 text-slate-300">{r.detection_delay_hours ? `${r.detection_delay_hours}h` : '—'}</td>
                            <td className="p-2 text-slate-300">{r.localisation_error_m !== null ? `${r.localisation_error_m}m` : '—'}</td>
                            <td className="p-2">
                              <span className="px-1.5 py-0.5 rounded text-[9px] bg-emerald-950 text-emerald-300 border border-emerald-800">
                                {r.status}
                              </span>
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>

                  <div className="p-2.5 bg-slate-900/50 rounded-xl border border-slate-800 text-[10px] text-slate-400 leading-relaxed">
                    📄 Full mathematical documentation, formulas, and sensitivity curves generated in <code className="text-cyan-300 font-mono">docs/LEAK_VALIDATION.md</code>. All metrics marked <strong className="text-purple-300">SIMULATED</strong>.
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Tab 4: Sensors & Value Source Toggle */}
        {activeTab === 'sensors' && (
          <div className="space-y-3">
            <div className="flex items-center justify-between pb-1">
              <span className="font-semibold text-slate-200 text-xs">
                Sensor Value Source Configuration
              </span>
              <span className="text-[10px] text-slate-400">
                Switch between SIMULATED and IGNOAPI live stream
              </span>
            </div>

            <div className="space-y-2">
              {meters.map((m: any) => (
                <div
                  key={m.sensor_id}
                  className="p-3 bg-slate-950/60 border border-slate-800 rounded-xl flex items-center justify-between"
                >
                  <div className="flex flex-col">
                    <span className="font-mono font-semibold text-slate-200 text-xs">{m.sensor_id}</span>
                    <span className="text-[10px] text-slate-400">{m.name}</span>
                    <span className="text-[10px] text-cyan-400 font-mono mt-0.5">
                      Reading: {m.reading_lps} LPS (Noise σ = ±{m.noise_std_lps})
                    </span>
                  </div>

                  <button
                    onClick={() => handleToggleSensorSource(m.sensor_id, m.value_source)}
                    className={`px-3 py-1.5 rounded-lg border font-mono text-[11px] font-semibold flex items-center gap-1.5 transition-all ${
                      m.value_source === 'IGNOAPI'
                        ? 'bg-cyan-950 text-cyan-300 border-cyan-500 shadow-sm'
                        : 'bg-purple-950 text-purple-300 border-purple-800'
                    }`}
                  >
                    <span>{m.value_source}</span>
                    {m.value_source === 'IGNOAPI' ? (
                      <ToggleRight className="w-4 h-4 text-cyan-400" />
                    ) : (
                      <ToggleLeft className="w-4 h-4 text-purple-400" />
                    )}
                  </button>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Tab 5: Mass Balance Continuity Verification */}
        {activeTab === 'mass_balance' && massBalance && (
          <div className="space-y-4">
            <div className="p-4 bg-slate-950/70 border border-slate-800 rounded-2xl space-y-3">
              <div className="flex items-center justify-between">
                <span className="font-semibold text-slate-200 text-xs flex items-center gap-1.5">
                  <Scale className="w-4 h-4 text-cyan-400" />
                  Network Continuity & Mass Balance Check
                </span>
                <span
                  className={`px-2.5 py-0.5 rounded-full font-bold text-[10px] font-mono ${
                    massBalance.status === 'BALANCED'
                      ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                      : 'bg-rose-950 text-rose-300 border border-rose-800'
                  }`}
                >
                  {massBalance.status}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-3 text-xs font-mono">
                <div className="p-3 bg-slate-900/80 rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-400 font-sans block">Total Inflow (24h)</span>
                  <span className="text-base font-bold text-cyan-300">{massBalance.total_inflow_m3} m³</span>
                </div>
                <div className="p-3 bg-slate-900/80 rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-400 font-sans block">Total Consumption (24h)</span>
                  <span className="text-base font-bold text-slate-200">{massBalance.total_consumption_m3} m³</span>
                </div>
                <div className="p-3 bg-slate-900/80 rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-400 font-sans block">Tank Storage Change (ΔV)</span>
                  <span className="text-base font-bold text-purple-300">{massBalance.net_tank_storage_change_m3} m³</span>
                </div>
                <div className="p-3 bg-slate-900/80 rounded-xl border border-slate-800">
                  <span className="text-[10px] text-slate-400 font-sans block">Continuity Error</span>
                  <span className="text-base font-bold text-emerald-400">{massBalance.percentage_error}%</span>
                  <span className="text-[9px] text-slate-500 font-sans block">Tolerance limit: &lt;1.0%</span>
                </div>
              </div>

              <div className="p-3 bg-slate-900/50 rounded-xl text-[11px] text-slate-300 font-sans leading-relaxed border border-slate-800/80">
                <strong>Mass Balance Theorem:</strong> Total volume pumped from Tataguni Clear Water Sump equals sum of customer cluster withdrawals plus net storage delta across Mount Joy GLR, High Grounds GLR, and Jayanagar OHT. Error is verified within &lt;1.0% tolerance in automated pytest.
              </div>
            </div>
          </div>
        )}

        {/* Tab 6: Scenario Audit Log */}
        {activeTab === 'audit_log' && (
          <div className="space-y-2">
            <span className="font-semibold text-slate-300 text-xs block pb-1">
              Recorded Scenario Injections (All Marked SIMULATED)
            </span>

            {auditLog.length === 0 ? (
              <div className="p-4 bg-slate-950/40 rounded-xl text-center text-slate-500 text-xs">
                No perturbations injected yet. Network running on verified baseline.
              </div>
            ) : (
              auditLog.map((log: any, i: number) => (
                <div
                  key={i}
                  className="p-3 bg-slate-950/60 border border-slate-800 rounded-xl space-y-1"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono font-semibold text-purple-300 text-xs">
                      {log.type}
                    </span>
                    <ProvenanceChip tier="SIMULATED" size="sm" showDetails={false} />
                  </div>
                  <div className="text-[11px] text-slate-300">{log.label || JSON.stringify(log)}</div>
                  <div className="text-[10px] text-slate-500 font-mono">{log.timestamp}</div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </div>
  );
};
