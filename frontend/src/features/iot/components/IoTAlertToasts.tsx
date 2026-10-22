import React, { useState } from 'react';
import {
  AlertTriangle,
  X,
  MapPin,
  CheckCircle2,
  Clock,
  ShieldAlert,
  ChevronRight,
  Droplet
} from 'lucide-react';
import { IoTAlertItem } from '../types';

export interface IoTAlertToastsProps {
  alerts: IoTAlertItem[];
  onZoomTo: (coords: [number, number]) => void;
  onAcknowledge: (alertId: string) => void;
  onSnooze: (alertId: string) => void;
}

export const IoTAlertToasts: React.FC<IoTAlertToastsProps> = ({
  alerts,
  onZoomTo,
  onAcknowledge,
  onSnooze,
}) => {
  const [dismissedIds, setDismissedIds] = useState<Set<string>>(new Set());

  // Show only active, non-dismissed alerts (max 3 stacked)
  const visibleAlerts = alerts
    .filter((a) => a.active && !dismissedIds.has(a.alert_id))
    .slice(0, 3);

  if (visibleAlerts.length === 0) return null;

  return (
    <div className="fixed bottom-6 right-6 z-40 flex flex-col gap-3 pointer-events-none max-w-md w-full select-none">
      {visibleAlerts.map((alert) => (
        <div
          key={alert.alert_id}
          className="pointer-events-auto w-full p-4 rounded-2xl bg-white/95 dark:bg-slate-900/95 border-2 border-rose-500/80 shadow-2xl backdrop-blur-md text-xs transition-all animate-in slide-in-from-bottom-5"
        >
          {/* Header */}
          <div className="flex items-start justify-between gap-2 pb-2 border-b border-slate-200 dark:border-slate-800">
            <div className="flex items-center gap-2">
              <span className="p-1.5 rounded-lg bg-rose-500 text-white shadow-sm animate-pulse">
                <AlertTriangle className="w-4 h-4" />
              </span>
              <div>
                <div className="flex items-center gap-1.5">
                  <h4 className="font-bold text-slate-900 dark:text-slate-100 text-xs">
                    {alert.title}
                  </h4>
                  <span className="text-[9px] font-mono font-bold px-1 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 uppercase">
                    SIMULATED
                  </span>
                </div>
                <span className="text-[10px] text-slate-500 font-mono">
                  {alert.location || 'Transmission Main Corridor'}
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={() => setDismissedIds((prev) => new Set(prev).add(alert.alert_id))}
              className="text-slate-400 hover:text-slate-600 p-1"
              title="Dismiss toast"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Loss Estimate & Uncertainty Range */}
          {alert.estimated_loss_lps && (
            <div className="grid grid-cols-2 gap-2 my-2.5 p-2 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/50">
              <div>
                <span className="text-[10px] text-rose-600 dark:text-rose-400 block font-mono">
                  Estimated Loss
                </span>
                <span className="font-bold font-mono text-sm text-rose-700 dark:text-rose-300">
                  {alert.estimated_loss_lps.toFixed(1)} L/s ({alert.estimated_loss_kld?.toFixed(0)} kL/d)
                </span>
              </div>
              <div className="text-right">
                <span className="text-[10px] text-rose-600 dark:text-rose-400 block font-mono">
                  Confidence / Range
                </span>
                <span className="font-bold font-mono text-xs text-rose-700 dark:text-rose-300">
                  {alert.confidence_pct || 88}% (±350 m corridor)
                </span>
              </div>
            </div>
          )}

          {/* Affected Systems Summary */}
          {alert.affected_elements && alert.affected_elements.length > 0 && (
            <div className="mb-2.5 text-[11px] text-slate-600 dark:text-slate-300">
              <span className="font-semibold block text-slate-800 dark:text-slate-200 mb-0.5">
                Potential Impact:
              </span>
              <ul className="list-disc list-inside space-y-0.5 text-slate-500 dark:text-slate-400 text-[10px]">
                {alert.affected_elements.map((eff, i) => (
                  <li key={i}>{eff}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Suggested Advisory Steps */}
          {alert.suggested_steps && alert.suggested_steps.length > 0 && (
            <div className="mb-3 text-[10px] text-slate-500 italic border-l-2 border-slate-300 dark:border-slate-700 pl-2">
              Advisory: {alert.suggested_steps[0]}
            </div>
          )}

          {/* Action Buttons: Zoom to Location | Acknowledge | Snooze */}
          <div className="flex items-center gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
            {alert.coordinates && (
              <button
                type="button"
                onClick={() => onZoomTo(alert.coordinates!)}
                className="flex-1 py-1.5 px-2.5 rounded-lg bg-sky-50 dark:bg-sky-950/60 border border-sky-300 dark:border-sky-800 text-sky-700 dark:text-sky-300 font-semibold flex items-center justify-center gap-1 hover:bg-sky-100 transition-colors"
              >
                <MapPin className="w-3.5 h-3.5" />
                <span>Zoom to Location</span>
              </button>
            )}

            <button
              type="button"
              onClick={() => onAcknowledge(alert.alert_id)}
              className="py-1.5 px-3 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 font-medium hover:bg-slate-200 transition-colors flex items-center gap-1"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Acknowledge</span>
            </button>

            <button
              type="button"
              onClick={() => onSnooze(alert.alert_id)}
              className="py-1.5 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-slate-700 transition-colors flex items-center gap-1"
              title="Snooze for 15 minutes"
            >
              <Clock className="w-3.5 h-3.5" />
              <span>Snooze</span>
            </button>
          </div>
        </div>
      ))}
    </div>
  );
};
