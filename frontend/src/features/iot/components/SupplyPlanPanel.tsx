import React, { useState, useEffect } from 'react';
import {
  Calendar,
  Clock,
  Zap,
  Activity,
  Layers,
  CheckCircle2,
  AlertTriangle,
  RotateCcw,
  Sparkles,
  Info,
  Sliders,
  ChevronRight,
  TrendingDown,
  Droplet
} from 'lucide-react';
import {
  ResponsiveContainer,
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  BarChart,
  Bar
} from 'recharts';
import { sseManager } from '../../../services/sseManager';

export const SupplyPlanPanel: React.FC = () => {
  const [planData, setPlanData] = useState<any>(null);
  const [currentTimeStr, setCurrentTimeStr] = useState('06:00');
  const [isRecalculating, setIsRecalculating] = useState(false);

  useEffect(() => {
    // 1. Initial fetch
    fetch('/api/v1/iot/plan/current')
      .then((r) => r.json())
      .then((data) => setPlanData(data))
      .catch(() => {});

    // 2. SSE subscription
    const unsub = sseManager.subscribe('plan', (data: any) => {
      if (data?.plan) {
        setPlanData(data.plan);
      }
      if (data?.water_movement?.clock_str) {
        setCurrentTimeStr(data.water_movement.clock_str);
      }
    });

    const unsubTele = sseManager.subscribe('telemetry', (data: any) => {
      if (data?.clock_utc) {
        const parts = data.clock_utc.split('T');
        if (parts[1]) {
          setCurrentTimeStr(parts[1].slice(0, 5));
        }
      }
    });

    return () => {
      unsub();
      unsubTele();
    };
  }, []);

  const handleRecalculate = async () => {
    setIsRecalculating(true);
    try {
      const res = await fetch('/api/v1/iot/plan/recalculate', { method: 'POST' });
      const data = await res.json();
      setPlanData(data);
    } catch {
      // ignore
    } finally {
      setIsRecalculating(false);
    }
  };

  const kpis = planData?.kpis || {
    energy_cost_lakhs: 4.82,
    demand_met_pct: 94.2,
    unserved_mld: 6.4,
    total_demand_mld: 111.5,
    total_delivered_mld: 105.1
  };

  const wardWindows = planData?.ward_windows || [
    { zone_name: 'South Basavanagudi & Chamarajpet', division: 'South Division', daily_demand_mld: 28.5, delivered_mld: 28.5, met_pct: 100 },
    { zone_name: 'Central CBD Vidhana Soudha', division: 'Central', daily_demand_mld: 32.0, delivered_mld: 30.4, met_pct: 95 },
    { zone_name: 'West Rajajinagar - Malleshwaram', division: 'West Division', daily_demand_mld: 26.8, delivered_mld: 24.1, met_pct: 90 },
    { zone_name: 'Padmanabhanagar & Banashankari', division: 'South Division', daily_demand_mld: 24.2, delivered_mld: 24.2, met_pct: 100 },
  ];

  const tankForecast = planData?.tank_forecast || [];
  const actionLog = planData?.action_log || [
    '06:00 Start High-Lift Pump 1: Mount Joy GLR 38%, off-peak tariff',
    '08:00 Open Valve Zone Basavanagudi: Scheduled 4h morning supply window',
    '22:00 Switch to Off-Peak pumping: Tariff ₹4.50/kWh, filling Mount Joy & High Grounds'
  ];

  // Calculate now-cursor percentage (00:00 to 24:00)
  const [currH, currM] = currentTimeStr.split(':').map(Number);
  const nowMinute = ((currH || 0) * 60 + (currM || 0));
  const nowCursorPct = Math.min(100, Math.max(0, (nowMinute / 1440) * 100));

  return (
    <div className="h-full w-full bg-slate-950 text-slate-100 flex flex-col overflow-y-auto p-4 select-none space-y-4">
      {/* 1. Header Banner & Disclaimers */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between pb-3 border-b border-slate-800 gap-2">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
              <Calendar className="w-5 h-5 text-sky-400" />
              <span>Automatic Supply Plan & Optimization</span>
            </h2>
            <span className="text-[10px] font-mono font-bold px-1.5 py-0.5 rounded bg-sky-500/10 text-sky-400 border border-sky-500/30">
              Automatic (simulated)
            </span>
          </div>
          <div className="flex items-center gap-3 text-[11px] text-slate-400 mt-1">
            <span>• Ward-to-reservoir assignment is simulated</span>
            <span>• Decision-support schedule, not BWSSB's actual schedule</span>
          </div>
        </div>

        <button
          type="button"
          onClick={handleRecalculate}
          disabled={isRecalculating}
          className="px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold text-xs flex items-center gap-1.5 transition-colors self-start shadow-sm disabled:opacity-50"
        >
          <RotateCcw className={`w-3.5 h-3.5 ${isRecalculating ? 'animate-spin' : ''}`} />
          <span>{isRecalculating ? 'Recomputing…' : 'Recompute Plan'}</span>
        </button>
      </div>

      {/* 2. Top KPI Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-4 gap-3">
        <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/60 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400 shrink-0">
            <CheckCircle2 className="w-5 h-5" />
          </div>
          <div>
            <span className="text-[11px] text-slate-400 block">Demand Met</span>
            <div className="font-mono text-xl font-bold text-slate-100">
              {kpis.demand_met_pct}%
            </div>
            <span className="text-[10px] text-emerald-400 font-mono">
              {kpis.total_delivered_mld} / {kpis.total_demand_mld} MLD
            </span>
          </div>
        </div>

        <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/60 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 shrink-0">
            <Zap className="w-5 h-5" />
          </div>
          <div>
            <span className="text-[11px] text-slate-400 block">Energy Cost (24h)</span>
            <div className="font-mono text-xl font-bold text-slate-100">
              ₹{kpis.energy_cost_lakhs} <span className="text-xs font-normal text-slate-400">Lakhs</span>
            </div>
            <span className="text-[10px] text-amber-400 font-mono">
              Time-of-Use Optimized
            </span>
          </div>
        </div>

        <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/60 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-rose-500/10 border border-rose-500/30 flex items-center justify-center text-rose-400 shrink-0">
            <TrendingDown className="w-5 h-5" />
          </div>
          <div>
            <span className="text-[11px] text-slate-400 block">Unserved Volume</span>
            <div className="font-mono text-xl font-bold text-slate-100">
              {kpis.unserved_mld} <span className="text-xs font-normal text-slate-400">MLD</span>
            </div>
            <span className="text-[10px] text-slate-400 font-mono">
              Reserve Deficit
            </span>
          </div>
        </div>

        <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/60 flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400 shrink-0">
            <Clock className="w-5 h-5" />
          </div>
          <div>
            <span className="text-[11px] text-slate-400 block">Simulated Clock</span>
            <div className="font-mono text-xl font-bold text-sky-400 tabular-nums">
              {currentTimeStr}
            </div>
            <span className="text-[10px] text-slate-400 font-mono">
              Lookahead 24h
            </span>
          </div>
        </div>
      </div>

      {/* 3. Gantt Chart: Ward x Time with Now-Cursor */}
      <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Layers className="w-4 h-4 text-sky-400" />
            <h3 className="font-bold text-slate-200 text-xs">
              Supply Windows Gantt Chart (00:00 - 24:00)
            </h3>
          </div>
          <div className="flex items-center gap-3 text-[11px] font-mono">
            <div className="flex items-center gap-1.5">
              <span className="w-3 h-2 rounded bg-sky-500" />
              <span className="text-slate-400">Scheduled Supply</span>
            </div>
            <div className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500" />
              <span className="text-slate-400">Now-Cursor ({currentTimeStr})</span>
            </div>
          </div>
        </div>

        {/* Timeline Header */}
        <div className="relative pl-52 pr-4 pt-1">
          <div className="flex justify-between text-[10px] text-slate-500 font-mono border-b border-slate-800 pb-1">
            <span>00:00</span>
            <span>04:00</span>
            <span>08:00</span>
            <span>12:00</span>
            <span>16:00</span>
            <span>20:00</span>
            <span>24:00</span>
          </div>
        </div>

        {/* Gantt Rows */}
        <div className="space-y-2 relative">
          {/* Vertical Now-Cursor Line across all rows */}
          <div
            className="absolute top-0 bottom-0 w-0.5 bg-emerald-400 shadow-[0_0_8px_rgba(52,211,153,0.8)] z-10 pointer-events-none"
            style={{ left: `calc(13rem + ${nowCursorPct * 0.72}%)` }}
          />

          {wardWindows.map((ward: any, idx: number) => {
            return (
              <div key={idx} className="flex items-center gap-3 text-xs">
                {/* Zone Label */}
                <div className="w-52 shrink-0 truncate" title={ward.zone_name}>
                  <div className="font-semibold text-slate-200 truncate">{ward.zone_name}</div>
                  <div className="text-[10px] text-slate-500 font-mono">
                    {ward.division} • {ward.daily_demand_mld} MLD
                  </div>
                </div>

                {/* 24h Bar Track */}
                <div className="flex-1 h-6 bg-slate-950 rounded border border-slate-800/80 relative overflow-hidden flex items-center">
                  {/* Morning Window (05:00 - 09:00 = 20.8% to 37.5%) */}
                  <div
                    className="absolute top-1 bottom-1 bg-sky-600/80 border border-sky-400/80 rounded px-1.5 flex items-center text-[10px] font-mono text-sky-100"
                    style={{ left: '20.8%', width: '16.7%' }}
                  >
                    05-09h
                  </div>

                  {/* Evening Window (17:00 - 21:00 = 70.8% to 87.5%) */}
                  <div
                    className="absolute top-1 bottom-1 bg-sky-600/80 border border-sky-400/80 rounded px-1.5 flex items-center text-[10px] font-mono text-sky-100"
                    style={{ left: '70.8%', width: '16.7%' }}
                  >
                    17-21h
                  </div>
                </div>

                {/* Demand Met % */}
                <span className="w-12 text-right font-mono text-[11px] font-bold text-emerald-400 shrink-0">
                  {ward.met_pct}%
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* 4. Bottom Grid: Reservoir Forecast & Next Action Log */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        {/* Tank Level Forecast Chart */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 space-y-2">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-slate-200 text-xs flex items-center gap-1.5">
              <Droplet className="w-4 h-4 text-sky-400" />
              <span>24-Hour Tank Level Forecast (%)</span>
            </h3>
            <span className="text-[10px] font-mono text-slate-400">Min 20% Reserve Guard</span>
          </div>

          <div className="h-[180px] w-full pt-2">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={tankForecast}>
                <XAxis dataKey="time" stroke="#64748b" tick={{ fontSize: 10 }} interval={15} />
                <YAxis domain={[0, 100]} stroke="#64748b" tick={{ fontSize: 10 }} />
                <Tooltip
                  contentStyle={{ backgroundColor: '#0f172a', borderColor: '#334155', fontSize: '11px' }}
                />
                <Line
                  type="monotone"
                  dataKey="GLR_MOUNT_JOY"
                  name="Mount Joy (22 MLD)"
                  stroke="#38bdf8"
                  strokeWidth={2}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="GLR_HIGH_GROUNDS"
                  name="High Grounds (35 MLD)"
                  stroke="#a855f7"
                  strokeWidth={2}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Automated Action Log & Schedule */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 flex flex-col justify-between space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-slate-200 text-xs flex items-center gap-1.5">
              <Clock className="w-4 h-4 text-amber-400" />
              <span>Next Actions & Event Log</span>
            </h3>
            <span className="text-[10px] font-mono text-emerald-400">Supervisor Active</span>
          </div>

          <div className="space-y-1.5 overflow-y-auto max-h-[160px] text-xs font-mono">
            {actionLog.map((act: string, idx: number) => (
              <div
                key={idx}
                className="p-2 rounded bg-slate-950/80 border border-slate-800/60 flex items-start gap-2"
              >
                <ChevronRight className="w-3.5 h-3.5 text-sky-400 shrink-0 mt-0.5" />
                <span className="text-slate-300 leading-snug">{act}</span>
              </div>
            ))}
          </div>

          <div className="text-[10px] text-slate-500 border-t border-slate-800 pt-2 flex justify-between">
            <span>TOU Tariff bands: Off-Peak (₹4.50) • Normal (₹7.20) • Peak (₹10.50)</span>
            <span className="text-sky-400">Replan on pump trip / leak</span>
          </div>
        </div>
      </div>
    </div>
  );
};
