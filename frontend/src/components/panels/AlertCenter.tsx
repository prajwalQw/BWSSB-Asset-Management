import React, { useState, useEffect } from 'react';
import { AlertItem } from '../../types';
import { api } from '../../services/api';
import { ProvenanceChip } from '../common/ProvenanceChip';
import { 
  AlertOctagon, 
  CheckCircle2, 
  Clock, 
  UserCheck, 
  ShieldAlert, 
  Wrench, 
  X, 
  Send,
  Droplet,
  Zap,
  ArrowRight
} from 'lucide-react';

interface AlertCenterProps {
  onClose: () => void;
  onAlertSelect?: (alert: AlertItem) => void;
}

export const AlertCenter: React.FC<AlertCenterProps> = ({ onClose, onAlertSelect }) => {
  const [alerts, setAlerts] = useState<AlertItem[]>([]);
  const [selectedAlert, setSelectedAlert] = useState<AlertItem | null>(null);
  const [operatorName, setOperatorName] = useState('Chief Engineer (Water Operations)');
  const [decisionAction, setDecisionAction] = useState('DISPATCH_INSPECTION_CREW');
  const [operatorNotes, setOperatorNotes] = useState('');
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);

  useEffect(() => {
    loadAlerts();
  }, []);

  const loadAlerts = async () => {
    try {
      const data = await api.getAlerts();
      setAlerts(data.alerts || []);
    } catch (err) {
      console.error('Failed to load alerts:', err);
    }
  };

  const handleDecisionSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedAlert) return;

    setIsSubmitting(true);
    try {
      const res = await api.submitOperatorDecision(
        selectedAlert.alert_id,
        decisionAction,
        operatorName,
        operatorNotes
      );
      setSuccessMessage(res.message);
      await loadAlerts();
      setTimeout(() => {
        setSelectedAlert(null);
        setSuccessMessage(null);
      }, 1500);
    } catch (err) {
      console.error('Error submitting decision:', err);
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <div className="absolute top-16 left-4 z-30 w-[480px] bg-slate-900/95 border border-slate-800 rounded-2xl shadow-2xl backdrop-blur-xl p-5 text-slate-100 flex flex-col max-h-[calc(100vh-100px)] overflow-hidden font-sans animate-in slide-in-from-left duration-200">
      {/* Header */}
      <div className="flex items-center justify-between pb-3.5 border-b border-slate-800">
        <div className="flex items-center gap-2.5">
          <div className="p-2 rounded-lg bg-rose-950/80 border border-rose-800/80 text-rose-400">
            <AlertOctagon className="w-5 h-5" />
          </div>
          <div>
            <h2 className="text-base font-bold text-slate-100 tracking-tight">
              Operational Decision Support
            </h2>
            <p className="text-[11px] text-slate-400">
              Rule 6 Mandate: Alerts recommend; humans decide. Zero auto-control actions.
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

      {/* Main Alert List */}
      <div className="flex-1 overflow-y-auto space-y-3 py-3 pr-1 text-xs">
        {alerts.map((alert) => {
          const isPending = alert.human_decision_status === 'PENDING_OPERATOR_DECISION';
          return (
            <div
              key={alert.alert_id}
              onClick={() => {
                setSelectedAlert(alert);
                if (onAlertSelect) onAlertSelect(alert);
              }}
              className={`p-3.5 rounded-xl border transition-all cursor-pointer ${
                selectedAlert?.alert_id === alert.alert_id
                  ? 'bg-slate-800/90 border-cyan-500/80 shadow-lg'
                  : 'bg-slate-950/50 border-slate-800/80 hover:border-slate-700'
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-2">
                <div className="flex items-center gap-2">
                  <span
                    className={`px-2 py-0.5 rounded-full font-bold text-[10px] font-mono uppercase tracking-wider ${
                      alert.severity === 'CRITICAL'
                        ? 'bg-rose-950 text-rose-300 border border-rose-800'
                        : 'bg-amber-950 text-amber-300 border border-amber-800'
                    }`}
                  >
                    {alert.severity}
                  </span>
                  <ProvenanceChip tier={alert.data_tier} size="sm" showDetails={false} />
                </div>
                <span className="text-[10px] text-slate-500 font-mono">
                  {alert.timestamp.slice(11, 19)} UTC
                </span>
              </div>

              <h4 className="font-semibold text-slate-100 text-xs mb-1">{alert.title}</h4>
              <p className="text-[11px] text-slate-400 mb-2">{alert.location}</p>

              {/* Recommendation Box */}
              <div className="p-2.5 bg-slate-900/80 border border-slate-800 rounded-lg text-[11px] text-cyan-200/90 mb-2">
                <span className="font-semibold text-cyan-400">Recommendation: </span>
                {alert.recommendation}
              </div>

              {/* Decision Status Footer */}
              <div className="flex items-center justify-between text-[11px] pt-1">
                <span className="text-slate-500 flex items-center gap-1">
                  <UserCheck className="w-3.5 h-3.5 text-slate-400" />
                  Status:
                </span>
                <span
                  className={`font-semibold font-mono ${
                    isPending ? 'text-amber-400' : 'text-emerald-400'
                  }`}
                >
                  {alert.human_decision_status.replace(/_/g, ' ')}
                </span>
              </div>
            </div>
          );
        })}
      </div>

      {/* Operator Sign-off Modal / Drawer */}
      {selectedAlert && selectedAlert.human_decision_status === 'PENDING_OPERATOR_DECISION' && (
        <div className="pt-3 border-t border-slate-800 text-xs">
          <form onSubmit={handleDecisionSubmit} className="space-y-3">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-200 flex items-center gap-1.5">
                <UserCheck className="w-4 h-4 text-cyan-400" /> Operator Sign-off & Decision
              </span>
              <span className="text-[10px] font-mono text-slate-400">
                {selectedAlert.alert_id}
              </span>
            </div>

            <div className="space-y-1">
              <label className="text-[11px] text-slate-400">Authorized Action:</label>
              <select
                value={decisionAction}
                onChange={(e) => setDecisionAction(e.target.value)}
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-cyan-500"
              >
                <option value="DISPATCH_INSPECTION_CREW">
                  Approve Recommendation: Dispatch Inspection Crew
                </option>
                <option value="APPROVE_ISOLATION_PROCEDURE">
                  Approve Pipe Section Isolation (Manual Work Order)
                </option>
                <option value="DEFER_FOR_MONITORING">
                  Defer Action: Monitor for 30 Minutes
                </option>
                <option value="REJECT_FALSE_ALARM">
                  Reject: Operational Transient / False Alarm
                </option>
              </select>
            </div>

            <div className="space-y-1">
              <label className="text-[11px] text-slate-400">Officer Signature & Justification:</label>
              <input
                type="text"
                required
                value={operatorNotes}
                onChange={(e) => setOperatorNotes(e.target.value)}
                placeholder="Enter justification or dispatch reference (e.g., Crew Alpha dispatched)"
                className="w-full bg-slate-950 border border-slate-700 rounded-lg p-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-cyan-500 placeholder-slate-500"
              />
            </div>

            <div className="flex items-center justify-end gap-2 pt-1">
              <button
                type="button"
                onClick={() => setSelectedAlert(null)}
                className="px-3 py-1.5 rounded-lg border border-slate-700 text-slate-300 hover:bg-slate-800"
              >
                Cancel
              </button>
              <button
                type="submit"
                disabled={isSubmitting}
                className="px-4 py-1.5 rounded-lg bg-cyan-600 hover:bg-cyan-500 text-white font-medium flex items-center gap-1.5 shadow-md transition-colors"
              >
                <Send className="w-3.5 h-3.5" />
                <span>{isSubmitting ? 'Logging...' : 'Sign & Submit Decision'}</span>
              </button>
            </div>

            {successMessage && (
              <div className="p-2 bg-emerald-950/80 border border-emerald-800 rounded-lg text-emerald-300 text-[11px] flex items-center gap-1.5">
                <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                <span>{successMessage}</span>
              </div>
            )}
          </form>
        </div>
      )}
    </div>
  );
};
