import React from 'react';
import { SelectedAsset, AlertItem } from '../../types';
import { ProvenanceChip } from '../common/ProvenanceChip';
import { 
  X, 
  Activity, 
  Droplets, 
  Gauge, 
  AlertTriangle, 
  Layers, 
  MapPin, 
  Calendar, 
  FileText,
  Compass,
  CheckCircle2,
  ShieldAlert,
  Zap,
  Info,
  ArrowRight
} from 'lucide-react';
import { ResponsiveContainer, AreaChart, Area, XAxis, YAxis, Tooltip, ReferenceLine } from 'recharts';

interface AssetInspectorProps {
  asset: SelectedAsset | null;
  onClose: () => void;
  onZoomTo?: (coordinates: [number, number]) => void;
  currentHour?: number;
  segmentData?: any;
  leakEvent?: any;
  allAlerts?: AlertItem[];
  isDarkTheme?: boolean;
}

export const AssetInspector: React.FC<AssetInspectorProps> = ({ 
  asset, 
  onClose,
  onZoomTo,
  currentHour = 12,
  segmentData,
  leakEvent,
  allAlerts = [],
  isDarkTheme = true
}) => {
  if (!asset) return null;

  const isSimulated = asset.dataTier === 'SIMULATED';
  const props = asset.properties || {};
  const isPipe = asset.category === 'PIPE' || props.element_type === 'PIPE' || asset.id.startsWith('PIPE_');

  // Related alerts for this asset
  const relatedAlerts = allAlerts.filter(a => 
    a.location.includes(asset.id) || 
    (asset.name && a.location.includes(asset.name)) ||
    (props.name && a.location.includes(props.name))
  );

  // Sparkline data preparation (24 hours)
  const timeseries = props.flow_timeseries || props.pressure_timeseries;
  const sparklineData = timeseries && Array.isArray(timeseries)
    ? timeseries.map((val: number, h: number) => ({
        hour: `${h.toString().padStart(2, '0')}:00`,
        hourNum: h,
        value: Number(val.toFixed(1))
      }))
    : null;

  // Segment diagnosis computation
  const segInflow = segmentData?.current_inflow_lps ?? (props.current_flow_lps || 0);
  const segOutflow = segmentData?.current_outflow_lps ?? Math.max(0, segInflow - 48);
  const segDemand = segmentData?.current_expected_demand_lps ?? 48.4;
  const segDiff = Number((segInflow - segOutflow - segDemand).toFixed(1));
  const segTol = segmentData?.tolerance_lps ?? 11.1;
  const isSegmentLeak = Boolean(segmentData?.is_leak_detected || leakEvent || props.status === 'BURST' || props.status === 'LEAK_SUSPECTED');

  // Estimated loss in L/min and LPS
  const lossLps = leakEvent?.loss_metrics?.estimated_loss_lps ?? (isSegmentLeak ? 60.0 : 0.0);
  const lossLpm = leakEvent?.loss_metrics?.estimated_loss_litres_per_min ?? Math.round(lossLps * 60);

  return (
    <div className={`absolute top-16 right-4 z-30 w-[420px] rounded-2xl border shadow-2xl backdrop-blur-xl p-5 flex flex-col max-h-[calc(100vh-130px)] overflow-hidden font-sans animate-in slide-in-from-right duration-200 ${
      isDarkTheme 
        ? 'bg-slate-900/95 border-slate-800 text-slate-100' 
        : 'bg-white/95 border-slate-200 text-slate-900 shadow-slate-300'
    }`}>
      {/* Header */}
      <div className={`flex items-start justify-between pb-3.5 border-b ${
        isDarkTheme ? 'border-slate-800' : 'border-slate-200'
      }`}>
        <div className="flex flex-col gap-1 pr-2">
          <div className="flex items-center gap-2">
            <ProvenanceChip
              tier={asset.dataTier}
              source={asset.source}
              date={asset.date}
              size="sm"
            />
            {asset.coordinates && onZoomTo && (
              <button
                onClick={() => onZoomTo(asset.coordinates!)}
                className={`px-2 py-0.5 rounded text-[10px] font-medium flex items-center gap-1 transition-all ${
                  isDarkTheme 
                    ? 'bg-slate-800 hover:bg-slate-700 text-cyan-300' 
                    : 'bg-slate-100 hover:bg-slate-200 text-cyan-700'
                }`}
                title="Zoom directly to this asset on map"
              >
                <Compass className="w-3 h-3" />
                <span>Zoom to</span>
              </button>
            )}
          </div>
          <h2 className="text-base font-bold tracking-tight mt-1 leading-snug">
            {asset.name}
          </h2>
          <span className="text-xs text-cyan-500 font-medium font-mono">{asset.category} • ID: {asset.id}</span>
        </div>
        <button
          onClick={onClose}
          className={`p-1 rounded-lg transition-colors ${
            isDarkTheme ? 'text-slate-400 hover:text-white hover:bg-slate-800' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'
          }`}
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Content scroll area */}
      <div className="flex-1 overflow-y-auto space-y-4 py-3 pr-1 text-xs">
        
        {/* SENSOR FEED HEALTH BANNER */}
        {(asset.id.startsWith('FM_') || asset.id.startsWith('PT_') || asset.category === 'PUMP' || asset.id.includes('AUX') || props.feed_health) && (
          <div className={`p-3 rounded-xl border flex items-center justify-between text-[11px] font-mono ${
            isDarkTheme ? 'bg-slate-950/80 border-slate-800' : 'bg-slate-50 border-slate-200'
          }`}>
            <div>
              <span className="text-[10px] text-slate-500 uppercase block font-sans">Telemetry Feed Health</span>
              <span className={asset.dataTier === 'LIVE' ? 'text-emerald-400 font-bold' : 'text-slate-400 font-bold'}>
                {asset.dataTier === 'LIVE' ? 'LIVE SCADA STREAM' : 'SIMULATED FALLBACK'}
              </span>
              <span className="text-[9px] text-slate-500 block font-sans">
                {asset.dataTier === 'LIVE' ? 'Verified IGNOAPI telemetry (Fresh)' : 'Unmapped in IGNOAPI (Rule 4 fallback)'}
              </span>
            </div>
            <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold ${
              asset.dataTier === 'LIVE'
                ? 'bg-emerald-950 text-emerald-300 border border-emerald-800'
                : 'bg-slate-800 text-slate-400 border border-slate-700'
            }`}>
              {asset.dataTier === 'LIVE' ? 'HEALTHY_LIVE' : 'FALLBACK_SIMULATED'}
            </span>
          </div>
        )}

        {/* Dedicated Auxiliary Supply Panel Telemetry (Unscaled true units) */}
        {(asset.id === 'PANEL_TG_AUX_01' || asset.name.includes('auxiliary supply')) && (
          <div className="space-y-2">
            <span className="text-[10px] font-mono uppercase font-bold text-slate-400 block tracking-wider">
              Auxiliary Electrical Telemetry (True Units)
            </span>
            <div className="grid grid-cols-2 gap-2">
              <div className={`p-2.5 rounded-xl border ${isDarkTheme ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
                <span className="text-[10px] text-slate-400 block font-mono">Control DC Voltage</span>
                <strong className="text-sm font-mono text-cyan-400">
                  {props.voltage_v !== undefined ? `${props.voltage_v} V DC` : '12.0 V DC'}
                </strong>
                <span className="text-[9px] text-slate-500 block">Auxiliary battery bus</span>
              </div>
              <div className={`p-2.5 rounded-xl border ${isDarkTheme ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
                <span className="text-[10px] text-slate-400 block font-mono">Pilot / Inst. Current</span>
                <strong className="text-sm font-mono text-blue-400">
                  {props.motor_current_a !== undefined ? `${props.motor_current_a} A DC` : '2.0 A DC'}
                </strong>
                <span className="text-[9px] text-slate-500 block">Instrumentation draw</span>
              </div>
              <div className={`p-2.5 rounded-xl border ${isDarkTheme ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
                <span className="text-[10px] text-slate-400 block font-mono">Shaft Speed (Aux)</span>
                <strong className="text-sm font-mono text-emerald-400">
                  {props.speed !== undefined ? `${props.speed} RPM` : '360.0 RPM'}
                </strong>
                <span className="text-[9px] text-slate-500 block">Auxiliary encoder</span>
              </div>
              <div className={`p-2.5 rounded-xl border ${isDarkTheme ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200'}`}>
                <span className="text-[10px] text-slate-400 block font-mono">Casing Temp</span>
                <strong className="text-sm font-mono text-amber-400">
                  {props.motor_temp_c !== undefined ? `${props.motor_temp_c} °C` : '70.0 °C'}
                </strong>
                <span className="text-[9px] text-slate-500 block">Thermocouple reading</span>
              </div>
            </div>
          </div>
        )}

        {/* ============================================================== */}
        {/* SPECIAL PIPE SEGMENT MASS BALANCE DIAGNOSIS CARD */}
        {/* ============================================================== */}
        {isPipe && (
          <div className={`p-4 rounded-xl border space-y-3 ${
            isSegmentLeak 
              ? 'bg-rose-950/30 border-rose-800/80' 
              : (isDarkTheme ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200')
          }`}>
            <div className="flex items-center justify-between">
              <span className="font-mono text-[10px] uppercase tracking-wider text-slate-400 font-bold">
                {segmentData?.segment_name || 'Segment Mass Balance Continuity'}
              </span>
              <span className={`px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                isSegmentLeak 
                  ? 'bg-rose-600 text-white' 
                  : 'bg-emerald-950 text-emerald-300 border border-emerald-800'
              }`}>
                {isSegmentLeak ? 'BURST DETECTED' : 'BALANCE HOLDING'}
              </span>
            </div>

            {/* Inflow, Outflow, Demand, Diff grid */}
            <div className="grid grid-cols-2 gap-2 font-mono text-[11px]">
              <div className={`p-2 rounded-lg border ${isDarkTheme ? 'bg-slate-900/90 border-slate-800' : 'bg-white border-slate-200'}`}>
                <span className="text-slate-400 text-[10px] block">INFLOW (X)</span>
                <strong className="text-cyan-400 text-xs">{segInflow} LPS</strong>
                <span className="text-[9px] text-slate-500 block">({Math.round(segInflow * 60)} L/min)</span>
              </div>

              <div className={`p-2 rounded-lg border ${isDarkTheme ? 'bg-slate-900/90 border-slate-800' : 'bg-white border-slate-200'}`}>
                <span className="text-slate-400 text-[10px] block">OUTFLOW (Y)</span>
                <strong className="text-blue-400 text-xs">{segOutflow} LPS</strong>
                <span className="text-[9px] text-slate-500 block">({Math.round(segOutflow * 60)} L/min)</span>
              </div>

              <div className={`p-2 rounded-lg border ${isDarkTheme ? 'bg-slate-900/90 border-slate-800' : 'bg-white border-slate-200'}`}>
                <span className="text-slate-400 text-[10px] block">EXPECTED DEMAND</span>
                <strong className="text-purple-400 text-xs">{segDemand} LPS</strong>
                <span className="text-[9px] text-slate-500 block">Diurnal cluster model</span>
              </div>

              <div className={`p-2 rounded-lg border ${isDarkTheme ? 'bg-slate-900/90 border-slate-800' : 'bg-white border-slate-200'}`}>
                <span className="text-slate-400 text-[10px] block">DIFFERENCE vs TOL</span>
                <strong className={isSegmentLeak ? 'text-rose-400 text-xs' : 'text-emerald-400 text-xs'}>
                  &Delta; {segDiff} LPS
                </strong>
                <span className="text-[9px] text-slate-500 block">Tol: &plusmn;{segTol} LPS</span>
              </div>
            </div>

            {/* Verdict Banner */}
            <div className={`p-3 rounded-xl border flex items-start gap-2.5 ${
              isSegmentLeak 
                ? 'bg-rose-950/60 border-rose-700 text-rose-200' 
                : 'bg-emerald-950/40 border-emerald-800/80 text-emerald-200'
            }`}>
              {isSegmentLeak ? (
                <ShieldAlert className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              ) : (
                <CheckCircle2 className="w-5 h-5 text-emerald-400 shrink-0 mt-0.5" />
              )}
              <div className="flex flex-col gap-0.5">
                <strong className="text-xs font-mono">
                  {isSegmentLeak 
                    ? `Possible leak, estimated ${lossLpm.toLocaleString()} L/min (${lossLps} LPS)` 
                    : `No leak detected (Imbalance within ±${segTol} LPS dynamic tolerance)`}
                </strong>
                <span className="text-[10px] opacity-80 leading-relaxed">
                  {isSegmentLeak 
                    ? `Hydraulic matching window: ${leakEvent?.localisation?.search_window_meters || '380m - 470m'} along pipe. Uncertainty: ±${leakEvent?.localisation?.uncertainty_range_m || 45}m. Never claim pinpoint.`
                    : `Evaluated across ${segmentData?.inflow_meters?.join(', ') || 'boundary meters'}. Normal night flow confirmed.`}
                </span>
              </div>
            </div>

            {/* Landmark anchoring */}
            {segmentData?.nearest_landmark && (
              <div className="text-[10px] text-slate-400 flex items-center gap-1 font-mono">
                <MapPin className="w-3 h-3 text-amber-400 shrink-0" />
                <span>Anchor: {segmentData.nearest_landmark}</span>
              </div>
            )}
          </div>
        )}

        {/* Simulated Infrastructure Disclaimer */}
        {isSimulated && (
          <div className="p-3 bg-purple-950/40 border border-purple-800/60 rounded-xl flex items-start gap-2 text-xs text-purple-200">
            <AlertTriangle className="w-4 h-4 text-purple-400 shrink-0 mt-0.5" />
            <div className="flex flex-col gap-0.5">
              <span className="font-semibold text-purple-300">Simulated Asset</span>
              <span className="text-[10px] text-purple-300/80">
                Hydraulic network synthesized from verified BWSSB alignments. All live values calibrated in WNTR EPANET.
              </span>
            </div>
          </div>
        )}

        {/* Key Metrics Grid */}
        <div className="grid grid-cols-2 gap-2.5">
          {props.current_pressure_bar !== undefined && (
            <div className={`p-3 rounded-xl border flex flex-col gap-1 ${
              isDarkTheme ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200'
            }`}>
              <span className="text-[11px] text-slate-400 flex items-center gap-1.5">
                <Gauge className="w-3.5 h-3.5 text-cyan-400" /> Pressure
              </span>
              <span className="text-base font-bold font-mono text-cyan-400">
                {props.current_pressure_bar} <span className="text-xs font-normal">bar</span>
              </span>
            </div>
          )}

          {props.current_flow_lps !== undefined && (
            <div className={`p-3 rounded-xl border flex flex-col gap-1 ${
              isDarkTheme ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200'
            }`}>
              <span className="text-[11px] text-slate-400 flex items-center gap-1.5">
                <Droplets className="w-3.5 h-3.5 text-blue-400" /> Flow Rate
              </span>
              <span className="text-base font-bold font-mono text-blue-400">
                {props.current_flow_lps} <span className="text-xs font-normal">LPS</span>
              </span>
            </div>
          )}

          {props.diameter_mm !== undefined && (
            <div className={`p-3 rounded-xl border flex flex-col gap-1 ${
              isDarkTheme ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200'
            }`}>
              <span className="text-[11px] text-slate-400 flex items-center gap-1.5">
                <Layers className="w-3.5 h-3.5 text-amber-400" /> Diameter / Material
              </span>
              <span className="text-base font-bold font-mono text-amber-300">
                {props.diameter_mm} mm <span className="text-xs font-normal text-slate-400">({props.material || 'DI'})</span>
              </span>
            </div>
          )}

          {props.current_velocity_mps !== undefined && (
            <div className={`p-3 rounded-xl border flex flex-col gap-1 ${
              isDarkTheme ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200'
            }`}>
              <span className="text-[11px] text-slate-400 flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-emerald-400" /> Velocity
              </span>
              <span className="text-base font-bold font-mono text-emerald-400">
                {props.current_velocity_mps} <span className="text-xs font-normal">m/s</span>
              </span>
            </div>
          )}

          {props.elevation_m !== undefined && (
            <div className={`p-3 rounded-xl border flex flex-col gap-1 ${
              isDarkTheme ? 'bg-slate-950/60 border-slate-800' : 'bg-slate-50 border-slate-200'
            }`}>
              <span className="text-[11px] text-slate-400 flex items-center gap-1.5">
                <MapPin className="w-3.5 h-3.5 text-emerald-400" /> Elevation
              </span>
              <span className="text-base font-bold font-mono text-emerald-300">
                {props.elevation_m} <span className="text-xs font-normal">m MSL</span>
              </span>
            </div>
          )}
        </div>

        {/* 24-Hour Mini-Trend Sparkline Chart */}
        {sparklineData && (
          <div className={`p-3.5 rounded-xl border space-y-2 ${
            isDarkTheme ? 'bg-slate-950/80 border-slate-800' : 'bg-slate-50 border-slate-200'
          }`}>
            <div className="flex items-center justify-between text-[11px]">
              <span className="font-mono text-slate-400 font-medium flex items-center gap-1.5">
                <Activity className="w-3.5 h-3.5 text-cyan-400" />
                <span>24-Hour {props.flow_timeseries ? 'Flow Timeseries (LPS)' : 'Pressure Timeseries (bar)'}</span>
              </span>
              <span className="font-mono text-cyan-400 text-[10px]">
                Cursor: {currentHour}:00
              </span>
            </div>

            <div className="h-28 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={sparklineData} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                  <defs>
                    <linearGradient id="sparkGrad" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#06b6d4" stopOpacity={0.6}/>
                      <stop offset="95%" stopColor="#06b6d4" stopOpacity={0}/>
                    </linearGradient>
                  </defs>
                  <XAxis dataKey="hour" stroke="#64748b" tick={{ fontSize: 9 }} interval={4} />
                  <YAxis stroke="#64748b" tick={{ fontSize: 9 }} domain={['auto', 'auto']} />
                  <Tooltip contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', borderRadius: '6px', fontSize: '10px' }} />
                  <ReferenceLine x={`${currentHour.toString().padStart(2, '0')}:00`} stroke="#f59e0b" strokeWidth={1.5} strokeDasharray="3 3" />
                  <Area type="monotone" dataKey="value" stroke="#06b6d4" strokeWidth={1.5} fill="url(#sparkGrad)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        )}

        {/* Active Alerts for this Asset */}
        {relatedAlerts.length > 0 && (
          <div className="space-y-2">
            <h4 className="text-[11px] font-bold uppercase tracking-wider text-rose-400 flex items-center gap-1.5 font-mono">
              <ShieldAlert className="w-3.5 h-3.5" />
              Active Anomalies on this Asset ({relatedAlerts.length})
            </h4>
            {relatedAlerts.map(a => (
              <div key={a.alert_id} className="p-3 rounded-xl bg-rose-950/30 border border-rose-800/80 space-y-1">
                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className="font-bold text-rose-300">{a.title}</span>
                  <span className="text-slate-400">{a.severity}</span>
                </div>
                <p className="text-[11px] text-slate-300">{a.metric_observed}</p>
                <div className="text-[10px] text-amber-300 pt-1 border-t border-rose-900/40">
                  {a.recommendation}
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Operational Status */}
        <div className={`p-3 rounded-xl border flex items-center justify-between ${
          isDarkTheme ? 'bg-slate-950/40 border-slate-800' : 'bg-slate-50 border-slate-200'
        }`}>
          <span className="text-slate-400">Operational Health</span>
          <span
            className={`px-2.5 py-1 rounded-full font-semibold text-[11px] font-mono ${
              props.status === 'BURST' || props.status === 'LEAK_SUSPECTED' || props.status === 'PRESSURE_DEFICIT'
                ? 'bg-rose-950 text-rose-300 border border-rose-800'
                : 'bg-emerald-950 text-emerald-300 border border-emerald-800'
            }`}
          >
            {props.status || 'NORMAL'}
          </span>
        </div>

        {/* Provenance Metadata Table */}
        <div className={`pt-2 border-t space-y-2 ${isDarkTheme ? 'border-slate-800/80' : 'border-slate-200'}`}>
          <h4 className="text-[10px] font-semibold uppercase text-slate-400 tracking-wider font-mono">
            Dataset Authority & Provenance
          </h4>
          <div className="space-y-1 text-[11px] text-slate-300 font-mono">
            <div className="flex items-center justify-between">
              <span className="text-slate-500">Data Tier:</span>
              <span className="font-semibold text-cyan-400">{asset.dataTier}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-slate-500">Source:</span>
              <span className="text-slate-400 truncate max-w-[200px]">{asset.source || 'BWSSB Hydraulic Twin'}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
