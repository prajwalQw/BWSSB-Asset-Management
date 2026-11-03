import React, { useState, useEffect } from 'react';
import {
  ShieldAlert,
  Activity,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  FileText,
  Clock,
  Radio,
  X,
  Play,
  RotateCcw,
  Download
} from 'lucide-react';
import { sseManager } from '../../../services/sseManager';
import { demoApi, DemoStatus } from '../services/demoApi';
import { DemoStepper } from './DemoStepper';
import { AgentResponseCard } from './AgentResponseCard';

export interface IncidentReport {
  id: string;
  title: string;
  severity: string;
  detected_at: string;
  duration_min: number;
  location: string;
  ranked_likely_cause: string;
  confidence_pct: number;
  what_happened: string;
  what_may_be_affected: string;
  advisory_next_steps: string[];
}

export const MonitorPanel: React.FC = () => {
  const [agentStatus, setAgentStatus] = useState<any>({
    status: 'ACTIVE',
    checks_passing: 6,
    total_checks: 6,
    last_heartbeat_s: 0,
    incidents_count: 0
  });
  const [demoStatus, setDemoStatus] = useState<DemoStatus | null>(null);
  const [incidents, setIncidents] = useState<IncidentReport[]>([]);
  const [activityFeed, setActivityFeed] = useState<string[]>([]);
  const [selectedIncident, setSelectedIncident] = useState<IncidentReport | null>(null);
  const [isDemoRunning, setIsDemoRunning] = useState(false);

  const fetchDemoStatus = () => {
    demoApi.getStatus()
      .then((data) => {
        if (data) setDemoStatus(data);
      })
      .catch(() => {});
  };

  useEffect(() => {
    // 1. Initial status fetch
    fetch('/api/v1/agent/status')
      .then((r) => r.json())
      .then((data) => {
        if (data) {
          setAgentStatus(data);
          if (data.incidents) setIncidents(data.incidents);
          if (data.demo) setDemoStatus(data.demo);
        }
      })
      .catch(() => {});

    fetch('/api/v1/agent/log')
      .then((r) => r.json())
      .then((logs) => {
        if (Array.isArray(logs)) setActivityFeed(logs);
      })
      .catch(() => {});

    fetchDemoStatus();

    // 2. SSE subscriptions
    const unsubAgent = sseManager.subscribe('agent', (data: any) => {
      if (data) {
        setAgentStatus(data);
        if (data.incidents) setIncidents(data.incidents);
        if (data.activity_feed) setActivityFeed(data.activity_feed);
        if (data.demo) setDemoStatus(data.demo);
      }
    });

    const unsubDemo = sseManager.subscribe('demo', (data: any) => {
      if (data) setDemoStatus(data);
    });

    // Fallback polling for demo status while active
    const pollInterval = setInterval(() => {
      fetchDemoStatus();
    }, 1500);

    return () => {
      unsubAgent();
      unsubDemo();
      clearInterval(pollInterval);
    };
  }, []);

  const handleStartDemo = async () => {
    try {
      setIsDemoRunning(true);
      await demoApi.startDemo();
      fetchDemoStatus();
    } catch (e) {
      console.error(e);
    } finally {
      setIsDemoRunning(false);
    }
  };

  const handleResetDemo = async () => {
    try {
      await demoApi.resetDemo();
      fetchDemoStatus();
    } catch (e) {
      console.error(e);
    }
  };

  const currentDemoState = demoStatus?.state || 'IDLE';
  const showDemoAgentCard = Boolean(
    demoStatus &&
    currentDemoState !== 'IDLE'
  );

  return (
    <div className="h-full w-full bg-slate-950 text-slate-100 p-4 select-none flex flex-col space-y-4 overflow-y-auto">
      {/* Header */}
      <div className="flex items-center justify-between pb-3 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse shadow-[0_0_8px_rgba(16,185,129,0.8)]" />
          <h2 className="text-base font-bold text-slate-100 flex items-center gap-2">
            <span>Autonomous Monitoring Agent</span>
          </h2>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 font-bold">
            ALWAYS-ON (supervised)
          </span>
          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold">
            SIMULATED
          </span>
        </div>

        {/* Demo trigger controls in monitor panel */}
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={handleStartDemo}
            disabled={isDemoRunning || (currentDemoState !== 'IDLE' && currentDemoState !== 'RESTORED')}
            className={`h-7 px-3 rounded text-xs font-semibold flex items-center gap-1.5 transition-colors shadow-sm ${
              currentDemoState !== 'IDLE' && currentDemoState !== 'RESTORED'
                ? 'bg-slate-800 text-slate-500 cursor-not-allowed'
                : 'bg-rose-600 hover:bg-rose-500 text-white'
            }`}
          >
            <Play className="w-3 h-3 fill-current" />
            <span>Run leak demo</span>
          </button>

          <button
            type="button"
            onClick={handleResetDemo}
            className="h-7 px-3 rounded text-xs font-semibold flex items-center gap-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition-colors"
          >
            <RotateCcw className="w-3 h-3" />
            <span>Reset demo</span>
          </button>
        </div>
      </div>

      {/* Slim Demo Status Stepper (Requirement) */}
      <DemoStepper
        state={currentDemoState}
        elapsedS={demoStatus?.elapsed_s || 0}
      />

      {/* Live Agent Response Card (Requirement) */}
      {showDemoAgentCard && demoStatus && (
        <AgentResponseCard
          demoStatus={demoStatus}
          onApprove={fetchDemoStatus}
          onReject={fetchDemoStatus}
          onReset={fetchDemoStatus}
        />
      )}

      {/* Grid: 3 Health Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/60 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-emerald-500/10 border border-emerald-500/30 flex items-center justify-center text-emerald-400">
            <CheckCircle2 className="w-4 h-4" />
          </div>
          <div>
            <span className="text-[11px] text-slate-400 block">Supervisor Health</span>
            <div className="font-mono text-sm font-bold text-emerald-400">
              Tasks All Healthy
            </div>
            <span className="text-[10px] text-slate-500 font-mono">Detector • Scheduler • Bridge</span>
          </div>
        </div>

        <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/60 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-sky-500/10 border border-sky-500/30 flex items-center justify-center text-sky-400">
            <Radio className="w-4 h-4 animate-pulse" />
          </div>
          <div>
            <span className="text-[11px] text-slate-400 block">SSE Heartbeat</span>
            <div className="font-mono text-sm font-bold text-sky-400">
              1s Stream Active
            </div>
            <span className="text-[10px] text-slate-500 font-mono">Event: telemetry • alert • demo</span>
          </div>
        </div>

        <div className="p-3 rounded-xl border border-slate-800 bg-slate-900/60 flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400">
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <span className="text-[11px] text-slate-400 block">Correlated Incidents</span>
            <div className="font-mono text-sm font-bold text-slate-100">
              {incidents.length} Active
            </div>
            <span className="text-[10px] text-purple-400 font-mono">Auto-Root-Cause Engine</span>
          </div>
        </div>
      </div>

      {/* Main Content: Incidents List & Activity Feed */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4 flex-1">
        {/* Open Incidents */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 flex flex-col space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-slate-200 text-xs flex items-center gap-1.5">
              <ShieldAlert className="w-4 h-4 text-rose-400" />
              <span>Correlated Incidents ({incidents.length})</span>
            </h3>
            <span className="text-[10px] font-mono text-slate-400">Click to view advisory report</span>
          </div>

          <div className="space-y-2 overflow-y-auto flex-1">
            {incidents.length === 0 ? (
              <div className="p-8 text-center text-slate-500 border border-dashed border-slate-800 rounded-xl">
                <CheckCircle2 className="w-6 h-6 mx-auto mb-2 text-emerald-500" />
                <p className="font-medium text-slate-300">No Active Incidents</p>
                <p className="text-[11px] mt-1 text-slate-500">
                  All telemetry streams, pipeline mass balance, and storage reservoirs within normal tolerance limits.
                </p>
              </div>
            ) : (
              incidents.map((inc) => (
                <div
                  key={inc.id}
                  onClick={() => setSelectedIncident(inc)}
                  className="p-3 rounded-lg border border-slate-800 bg-slate-950/80 hover:border-slate-700 cursor-pointer transition-all space-y-1.5"
                >
                  <div className="flex items-center justify-between">
                    <span className="font-mono text-[10px] font-bold text-rose-400 bg-rose-500/10 px-1.5 py-0.5 rounded border border-rose-500/30">
                      {inc.severity}
                    </span>
                    <span className="text-[10px] font-mono text-slate-500">{inc.detected_at}</span>
                  </div>
                  <div className="font-semibold text-slate-200 text-xs">{inc.title}</div>
                  <div className="text-[11px] text-slate-400">Location: {inc.location}</div>
                  <div className="text-[11px] text-amber-400 font-mono">
                    Likely cause: {inc.ranked_likely_cause} ({inc.confidence_pct}% conf)
                  </div>
                </div>
              ))
            )}
          </div>
        </div>

        {/* Activity Feed */}
        <div className="p-4 rounded-xl border border-slate-800 bg-slate-900/60 flex flex-col space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="font-bold text-slate-200 text-xs flex items-center gap-1.5">
              <Activity className="w-4 h-4 text-sky-400" />
              <span>Monitoring Agent Activity Feed</span>
            </h3>
            <span className="text-[10px] font-mono text-emerald-400">Always-On Feed</span>
          </div>

          <div className="space-y-1.5 overflow-y-auto flex-1 max-h-[320px] text-xs font-mono">
            {activityFeed.map((log, idx) => (
              <div key={idx} className="p-2 rounded bg-slate-950/60 border border-slate-800/40 text-slate-300">
                {log}
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* Incident Detail Modal with Download Report Button */}
      {selectedIncident && (
        <div className="fixed inset-0 bg-black/70 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="w-full max-w-lg rounded-xl border border-slate-800 bg-slate-900 shadow-2xl p-5 space-y-4 text-xs">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center gap-2">
                <FileText className="w-5 h-5 text-rose-400" />
                <h3 className="font-bold text-sm text-slate-100">
                  Incident Report: {selectedIncident.id}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setSelectedIncident(null)}
                className="p-1 rounded text-slate-400 hover:text-slate-200"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3 font-mono text-[11px]">
              <div>
                <span className="text-slate-500 uppercase tracking-wider block">What:</span>
                <span className="text-slate-200">{selectedIncident.what_happened}</span>
              </div>
              <div>
                <span className="text-slate-500 uppercase tracking-wider block">Where:</span>
                <span className="text-slate-200">{selectedIncident.location}</span>
              </div>
              <div>
                <span className="text-slate-500 uppercase tracking-wider block">Ranked Likely Cause:</span>
                <span className="text-amber-400 font-bold">
                  {selectedIncident.ranked_likely_cause} ({selectedIncident.confidence_pct}% confidence)
                </span>
              </div>
              <div>
                <span className="text-slate-500 uppercase tracking-wider block">What May Be Affected:</span>
                <span className="text-slate-300">{selectedIncident.what_may_be_affected}</span>
              </div>
              <div>
                <span className="text-slate-500 uppercase tracking-wider block">Advisory Next Steps:</span>
                <ul className="list-disc pl-4 space-y-1 mt-1 text-emerald-400">
                  {selectedIncident.advisory_next_steps.map((step, idx) => (
                    <li key={idx}>{step}</li>
                  ))}
                </ul>
              </div>
            </div>

            <div className="pt-3 border-t border-slate-800 flex justify-between items-center">
              <a
                href="/api/v1/demo/report/html"
                target="_blank"
                rel="noopener noreferrer"
                className="px-3 py-1.5 rounded-lg bg-sky-600 hover:bg-sky-500 text-white font-semibold flex items-center gap-1.5"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Download Report (HTML/PDF)</span>
              </a>

              <button
                type="button"
                onClick={() => setSelectedIncident(null)}
                className="px-4 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 font-semibold"
              >
                Close Report
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
