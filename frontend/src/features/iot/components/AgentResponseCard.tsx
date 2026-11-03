import React, { useState } from 'react';
import {
  ShieldAlert,
  CheckCircle2,
  AlertTriangle,
  Clock,
  Lock,
  Wrench,
  RotateCcw,
  FileText,
  Download,
  XCircle,
  Play,
  PowerOff
} from 'lucide-react';
import { DemoStatus, demoApi } from '../services/demoApi';
import { WardNoticeBanner } from './WardNoticeBanner';

export interface AgentResponseCardProps {
  demoStatus: DemoStatus;
  onApprove?: () => void;
  onReject?: () => void;
  onReset?: () => void;
  className?: string;
  isCompact?: boolean;
}

export const AgentResponseCard: React.FC<AgentResponseCardProps> = ({
  demoStatus,
  onApprove,
  onReject,
  onReset,
  className = '',
  isCompact = false,
}) => {
  const [acting, setActing] = useState(false);
  const [operatorRole, setOperatorRole] = useState<'OPERATOR' | 'VIEWER'>('OPERATOR');
  const [errorMsg, setErrorMsg] = useState<string | null>(null);

  const {
    state,
    agent_response,
    repair_pct,
    repair_eta_s,
    incident_report,
    approval_mode,
    config,
    step_log = [],
    valve_state = 'OPEN',
  } = demoStatus;

  const steps = agent_response?.steps || [
    {
      label: 'Leak confirmed by pressure drop and flow imbalance',
      ts: 'Pending',
      done: ['AGENT_DIAGNOSED', 'AWAITING_APPROVAL', 'COUNTDOWN', 'ISOLATING', 'ISOLATED', 'REPAIR_DISPATCHED', 'REPAIR_IN_PROGRESS', 'VERIFYING', 'RESTORING', 'RESTORED'].includes(state),
    },
    {
      label: `Proposed action: switch OFF ${config?.feeding_pump_name || 'High-Lift Pump 1'} and close isolation valve ${config?.isolation_valve_name || 'BFV-104'} to stop supply into the leaking section`,
      ts: 'Pending',
      done: ['AGENT_DIAGNOSED', 'AWAITING_APPROVAL', 'COUNTDOWN', 'ISOLATING', 'ISOLATED', 'REPAIR_DISPATCHED', 'REPAIR_IN_PROGRESS', 'VERIFYING', 'RESTORING', 'RESTORED'].includes(state),
    },
    {
      label: `Impact if isolated: wards ${(config?.impacted_wards || ['Basavanagudi', 'Hanumanthanagar', 'Chamarajpet']).join(', ')} lose supply from this line; fallback: ${config?.alternate_source || 'Harohalli Stage V via High Grounds GLR'} covers ${config?.alternate_coverage_pct || 65}% for ${config?.alternate_coverage_hours || 4} hours (Simulated)`,
      ts: 'Pending',
      done: ['AGENT_DIAGNOSED', 'AWAITING_APPROVAL', 'COUNTDOWN', 'ISOLATING', 'ISOLATED', 'REPAIR_DISPATCHED', 'REPAIR_IN_PROGRESS', 'VERIFYING', 'RESTORING', 'RESTORED'].includes(state),
    },
  ];

  const countdown = agent_response?.countdown;
  const isAwaiting = state === 'AWAITING_APPROVAL';
  const isCountdown = state === 'COUNTDOWN' && typeof countdown === 'number' && countdown > 0;
  const isIsolating = state === 'ISOLATING';
  const isIsolated = state === 'ISOLATED';
  const isRepairDispatched = state === 'REPAIR_DISPATCHED';
  const isRepairInProgress = state === 'REPAIR_IN_PROGRESS';
  const isVerifying = state === 'VERIFYING';
  const isRestoring = state === 'RESTORING';
  const isRestored = state === 'RESTORED';

  const handleApprove = async () => {
    try {
      setActing(true);
      setErrorMsg(null);
      await demoApi.approveIsolation('CHIEF_ENGINEER', operatorRole);
      if (onApprove) onApprove();
    } catch (err: any) {
      setErrorMsg(err.message || 'Approval rejected');
    } finally {
      setActing(false);
    }
  };

  const handleReject = async () => {
    try {
      setActing(true);
      setErrorMsg(null);
      await demoApi.rejectIsolation('OPERATOR', operatorRole);
      if (onReject) onReject();
    } catch (err: any) {
      setErrorMsg(err.message || 'Rejection rejected');
    } finally {
      setActing(false);
    }
  };

  const handleCancelCountdown = async () => {
    try {
      setActing(true);
      await demoApi.resetDemo();
      if (onReset) onReset();
    } catch (err: any) {
      setErrorMsg(err.message);
    } finally {
      setActing(false);
    }
  };

  return (
    <div className={`p-3.5 rounded-xl border border-sky-500/30 bg-slate-900/90 text-xs text-slate-100 flex flex-col space-y-3 shadow-xl ${className}`}>
      {/* Header */}
      <div className="flex items-center justify-between pb-2 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-sky-500/10 text-sky-400 border border-sky-500/30">
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <div className="flex items-center gap-1.5">
              <h4 className="font-bold text-slate-100 text-xs">Autonomous Agent Response</h4>
              <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold">
                SIMULATED
              </span>
            </div>
            <span className="text-[10px] text-slate-400 font-mono">
              Mode: {approval_mode === 'auto' ? 'Automatic Isolation (3s countdown)' : 'Operator Approval Required'}
            </span>
          </div>
        </div>

        {/* Role toggle test helper for ask mode */}
        {isAwaiting && (
          <div className="flex items-center gap-1 bg-slate-950 p-0.5 rounded border border-slate-800 text-[10px] font-mono">
            <span className="text-slate-500 px-1">Role:</span>
            <button
              type="button"
              onClick={() => setOperatorRole('OPERATOR')}
              className={`px-1.5 py-0.5 rounded font-bold ${operatorRole === 'OPERATOR' ? 'bg-sky-600 text-white' : 'text-slate-400'}`}
            >
              OPERATOR
            </button>
            <button
              type="button"
              onClick={() => setOperatorRole('VIEWER')}
              className={`px-1.5 py-0.5 rounded font-bold ${operatorRole === 'VIEWER' ? 'bg-rose-600 text-white' : 'text-slate-400'}`}
            >
              VIEWER
            </button>
          </div>
        )}
      </div>

      {/* Step List with Timestamps & Checkmarks */}
      <div className="space-y-1.5">
        {steps.map((st, idx) => (
          <div
            key={idx}
            className={`p-2 rounded-lg border text-[11px] leading-relaxed flex items-start gap-2 ${
              st.done
                ? 'bg-emerald-950/20 border-emerald-500/30 text-emerald-200'
                : 'bg-slate-950/60 border-slate-800 text-slate-400'
            }`}
          >
            {st.done ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            ) : (
              <Clock className="w-4 h-4 text-slate-500 shrink-0 mt-0.5" />
            )}
            <div className="flex-1">
              <span>{st.label}</span>
              {st.ts && st.ts !== 'Pending' && (
                <span className="ml-2 font-mono text-[10px] text-slate-500">[{st.ts}]</span>
              )}
            </div>
          </div>
        ))}
      </div>

      {/* Error Message */}
      {errorMsg && (
        <div className="p-2 rounded bg-rose-500/10 border border-rose-500/30 text-rose-300 text-[11px]">
          {errorMsg}
        </div>
      )}

      {/* Action Zone: Auto Countdown or Ask Mode Buttons */}
      {isCountdown && (
        <div className="p-3 rounded-lg bg-sky-950/30 border border-sky-500/40 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="text-xl font-bold font-mono text-sky-400 animate-bounce">
              {countdown}
            </span>
            <span className="text-xs font-semibold text-sky-200">
              Isolating in {countdown}…
            </span>
          </div>
          <button
            type="button"
            onClick={handleCancelCountdown}
            disabled={acting}
            className="px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-rose-300 border border-rose-500/30 text-xs font-semibold transition-colors"
          >
            Cancel
          </button>
        </div>
      )}

      {isAwaiting && (
        <div className="p-3 rounded-lg bg-amber-500/10 border border-amber-500/30 flex flex-col space-y-2">
          <span className="font-semibold text-amber-300 text-xs">
            Approval Required: Authorize isolation of High-Lift Pump 1 and Valve BFV-104?
          </span>
          <div className="flex items-center gap-2">
            <button
              type="button"
              onClick={handleApprove}
              disabled={acting}
              className="flex-1 py-1.5 px-3 rounded-lg bg-rose-600 hover:bg-rose-500 text-white font-bold text-xs shadow-md shadow-rose-600/20 transition-all flex items-center justify-center gap-1.5"
            >
              <PowerOff className="w-3.5 h-3.5" />
              <span>Turn OFF the pump & Approve Isolation</span>
            </button>
            <button
              type="button"
              onClick={handleReject}
              disabled={acting}
              className="py-1.5 px-3 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium text-xs border border-slate-700 transition-colors flex items-center gap-1.5"
            >
              <XCircle className="w-3.5 h-3.5" />
              <span>Reject</span>
            </button>
          </div>
        </div>
      )}

      {/* Ward Notice Alert & Repair Action */}
      <WardNoticeBanner demoStatus={demoStatus} />

      {/* Status: Isolating / Isolated */}
      {(isIsolating || isIsolated) && (
        <div className="p-2.5 rounded-lg bg-slate-950/80 border border-slate-800 flex items-center justify-between font-mono text-[11px]">
          <div className="flex items-center gap-2">
            <Lock className="w-4 h-4 text-rose-400" />
            <div>
              <span className="font-bold text-rose-400">
                {isIsolating ? 'Pump STOPPING → OFF ramp active' : 'OFF - isolated by monitoring agent'}
              </span>
              <span className="text-[10px] text-slate-500 block">
                Valve BFV-104: {valve_state} • Pipe Flow: 0.0 L/s
              </span>
            </div>
          </div>
          <span className="px-1.5 py-0.5 rounded bg-rose-500/20 text-rose-300 border border-rose-500/40 text-[10px] font-bold">
            LOCKED
          </span>
        </div>
      )}

      {/* Repair Phase: Progress Bar & ETA */}
      {(isRepairDispatched || isRepairInProgress || isVerifying) && (
        <div className="p-3 rounded-lg bg-slate-950/80 border border-slate-800 space-y-2">
          <div className="flex items-center justify-between text-[11px]">
            <span className="font-semibold text-sky-300 flex items-center gap-1.5">
              <Wrench className="w-3.5 h-3.5 text-sky-400" />
              <span>{isRepairDispatched ? 'Repair crew dispatched' : isVerifying ? 'Hydrostatic pre-start verification' : 'Repair in progress'}</span>
            </span>
            <span className="font-mono text-slate-400">
              ETA: <strong className="text-slate-200">{repair_eta_s.toFixed(0)}s</strong>
            </span>
          </div>

          <div className="w-full bg-slate-800 rounded-full h-2 overflow-hidden">
            <div
              className="bg-gradient-to-r from-sky-500 to-emerald-500 h-2 transition-all duration-300"
              style={{ width: `${repair_pct}%` }}
            />
          </div>
          <div className="flex justify-between text-[10px] font-mono text-slate-500">
            <span>Excavation & joint collar replacement</span>
            <span>{repair_pct.toFixed(0)}%</span>
          </div>
        </div>
      )}

      {/* Restoring Phase */}
      {isRestoring && (
        <div className="p-2.5 rounded-lg bg-sky-950/30 border border-sky-500/30 flex items-center gap-2 text-[11px] text-sky-300">
          <RotateCcw className="w-4 h-4 animate-spin text-sky-400" />
          <span>Starting pump through soft-start profile: current spike then plateau…</span>
        </div>
      )}

      {/* Restored Phase & Incident Report Download */}
      {isRestored && incident_report && (
        <div className="p-3 rounded-xl bg-emerald-950/30 border border-emerald-500/40 space-y-2.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2 text-emerald-400 font-bold text-xs">
              <CheckCircle2 className="w-4 h-4" />
              <span>Incident Closed & Resolved</span>
            </div>
            <span className="text-[10px] font-mono text-emerald-300">
              Duration: {incident_report.duration_min} min
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 text-[10.5px] font-mono bg-slate-950/60 p-2 rounded-lg border border-emerald-500/20">
            <div>
              <span className="text-slate-500 block">Volume Lost:</span>
              <span className="font-bold text-rose-400">{incident_report.volume_lost_kl} kL</span>
            </div>
            <div>
              <span className="text-slate-500 block">Approved By:</span>
              <span className="font-bold text-slate-200">{incident_report.approved_by}</span>
            </div>
          </div>

          <div className="flex items-center gap-2 pt-1">
            <a
              href="/api/v1/demo/report/html"
              target="_blank"
              rel="noopener noreferrer"
              className="flex-1 py-1.5 px-3 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-bold text-xs shadow-md shadow-emerald-600/20 text-center flex items-center justify-center gap-1.5 transition-colors"
            >
              <Download className="w-3.5 h-3.5" />
              <span>Download Report (HTML/PDF)</span>
            </a>
          </div>
        </div>
      )}

      {/* Governance Notice */}
      <div className="text-[10px] text-slate-500 pt-1 border-t border-slate-800/80">
        Automatic isolation is simulated. Real field control is not enabled.
      </div>
    </div>
  );
};
