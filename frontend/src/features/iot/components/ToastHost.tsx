/**
 * ToastHost: High-priority Alert and Notification Host mounted at the app root.
 * Subscribes to store's alert events for HIGH and CRITICAL alerts (leak, pump trip, low pressure).
 * Lower severities remain visible only in the LeftRail Alerts list.
 * Deduplication uses key = `alert_{alert_id}_{first_seen}` in localStorage.
 */

import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  X,
  MapPin,
  CheckCircle2,
  Clock,
  Info,
  AlertCircle
} from 'lucide-react';
import { IoTAlertItem } from '../types';
import { useIoTStore } from '../store/useIoTStore';
import { iotApi } from '../services/iotApi';

export interface ToastHostProps {
  alerts?: IoTAlertItem[];
  onZoomTo?: (coords: [number, number]) => void;
  onAcknowledge?: (alertId: string) => void;
  onSnooze?: (alertId: string) => void;
}

export const ToastHost: React.FC<ToastHostProps> = ({
  alerts: propAlerts,
  onZoomTo,
  onAcknowledge,
  onSnooze,
}) => {
  const store = useIoTStore();
  const alertsList = propAlerts || store.alerts;
  const activeToast = store.activeToast;

  const [dismissedKeys, setDismissedKeys] = useState<Set<string>>(() => {
    const set = new Set<string>();
    if (typeof window !== 'undefined') {
      try {
        for (let i = 0; i < localStorage.length; i++) {
          const key = localStorage.key(i);
          if (key && key.startsWith('dismissed_alert_')) {
            set.add(key);
          }
        }
      } catch {
        // Ignore localStorage error
      }
    }
    return set;
  });

  // Filter for HIGH and CRITICAL active alerts that have not been dismissed for this occurrence
  const visibleAlerts = alertsList.filter((a) => {
    if (!a.active || a.status === 'CLEARED') return false;
    const isHighOrCritical = a.severity === 'HIGH' || a.severity === 'CRITICAL';
    if (!isHighOrCritical) return false;

    // Stable dedupe key = alert id + first_seen occurrence
    const dedupeKey = `dismissed_alert_${a.alert_id}_${a.first_seen || a.timestamp_epoch || a.timestamp || ''}`;
    return !dismissedKeys.has(dedupeKey);
  }).slice(0, 3); // Stack up to 3 highest priority alerts

  const handleDismiss = (alert: IoTAlertItem) => {
    const dedupeKey = `dismissed_alert_${alert.alert_id}_${alert.first_seen || alert.timestamp_epoch || alert.timestamp || ''}`;
    try {
      localStorage.setItem(dedupeKey, '1');
    } catch {
      // Ignore storage quota
    }
    setDismissedKeys((prev) => new Set(prev).add(dedupeKey));
  };

  const handleAck = (alertId: string) => {
    if (onAcknowledge) {
      onAcknowledge(alertId);
    } else {
      store.acknowledgeAlertLocally(alertId);
      iotApi.acknowledgeAlert(alertId).catch(console.error);
    }
  };

  const handleSnooze = (alertId: string) => {
    if (onSnooze) {
      onSnooze(alertId);
    } else {
      store.snoozeAlertLocally(alertId);
      iotApi.snoozeAlert(alertId, 900).catch(console.error);
    }
  };

  return (
    <div className="fixed bottom-6 right-6 z-50 flex flex-col gap-3 pointer-events-none max-w-md w-full select-none" data-testid="toast-host">
      {/* 1. Global Action / Error Toast (e.g. from POST simulate leak) */}
      {activeToast && (
        <div
          data-testid="error-toast"
          className={`pointer-events-auto w-full p-3.5 rounded-xl border shadow-xl backdrop-blur flex items-center justify-between text-xs transition-all animate-in slide-in-from-bottom-3 ${
            activeToast.type === 'error'
              ? 'bg-rose-950/90 border-rose-500 text-rose-100'
              : activeToast.type === 'success'
              ? 'bg-emerald-950/90 border-emerald-500 text-emerald-100'
              : 'bg-slate-900/90 border-slate-700 text-slate-100'
          }`}
        >
          <div className="flex items-center gap-2">
            {activeToast.type === 'error' ? (
              <AlertCircle className="w-4 h-4 text-rose-400 flex-shrink-0" />
            ) : (
              <Info className="w-4 h-4 text-sky-400 flex-shrink-0" />
            )}
            <span className="font-medium">{activeToast.message}</span>
          </div>
          <button
            type="button"
            onClick={() => store.setActiveToast(null)}
            className="p-1 text-slate-400 hover:text-slate-200"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </div>
      )}

      {/* 2. Critical & High Alert Popups */}
      {visibleAlerts.map((alert) => (
        <div
          key={alert.alert_id}
          data-testid={`alert-popup-${alert.alert_id}`}
          className="pointer-events-auto w-full p-4 rounded-2xl bg-white/95 dark:bg-slate-900/95 border-2 border-rose-500 shadow-2xl backdrop-blur-md text-xs transition-all animate-in slide-in-from-bottom-5"
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
                  <span className="text-[9px] font-mono font-bold px-1 rounded bg-rose-500/10 text-rose-500 border border-rose-500/30 uppercase">
                    {alert.severity}
                  </span>
                </div>
                <span className="text-[10px] text-slate-500 font-mono">
                  {alert.location || 'Pipeline Corridor'}
                </span>
              </div>
            </div>

            <button
              type="button"
              onClick={() => handleDismiss(alert)}
              className="text-slate-400 hover:text-slate-600 p-1"
              title="Dismiss toast"
              data-testid="dismiss-alert-btn"
            >
              <X className="w-4 h-4" />
            </button>
          </div>

          {/* Loss, Confidence and Position Range along Pipe */}
          {alert.estimated_loss_lps && (
            <div className="grid grid-cols-2 gap-2 my-2.5 p-2 rounded-lg bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/50">
              <div>
                <span className="text-[10px] text-rose-600 dark:text-rose-400 block font-mono">
                  Loss Estimate
                </span>
                <span className="font-bold font-mono text-sm text-rose-700 dark:text-rose-300">
                  {alert.estimated_loss_lps.toFixed(1)} L/s ({alert.estimated_loss_kld?.toFixed(0)} kL/day)
                </span>
              </div>
              <div className="text-right">
                <span className="text-[10px] text-rose-600 dark:text-rose-400 block font-mono">
                  Confidence & Corridor
                </span>
                <span className="font-bold font-mono text-xs text-rose-700 dark:text-rose-300">
                  {alert.confidence_pct || 88}% ({alert.uncertainty_corridor || '±350 m range'})
                </span>
              </div>
            </div>
          )}

          {/* What may be affected */}
          {alert.affected_elements && alert.affected_elements.length > 0 && (
            <div className="mb-2.5 text-[11px] text-slate-600 dark:text-slate-300">
              <span className="font-semibold block text-slate-800 dark:text-slate-200 mb-0.5">
                What May Be Affected:
              </span>
              <ul className="list-disc list-inside space-y-0.5 text-slate-500 dark:text-slate-400 text-[10px]">
                {alert.affected_elements.map((eff, i) => (
                  <li key={i}>{eff}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Advisory Steps */}
          {alert.suggested_steps && alert.suggested_steps.length > 0 && (
            <div className="mb-3 text-[10px] text-slate-500 italic border-l-2 border-amber-500 pl-2">
              Advisory: {alert.suggested_steps[0]}
            </div>
          )}

          {/* Buttons: Show on map, Acknowledge, Snooze */}
          <div className="flex items-center gap-2 pt-2 border-t border-slate-200 dark:border-slate-800">
            {alert.coordinates && onZoomTo && (
              <button
                type="button"
                onClick={() => onZoomTo(alert.coordinates!)}
                className="flex-1 py-1.5 px-2.5 rounded-lg bg-sky-50 dark:bg-sky-950/60 border border-sky-300 dark:border-sky-800 text-sky-700 dark:text-sky-300 font-semibold flex items-center justify-center gap-1 hover:bg-sky-100 transition-colors"
                data-testid="show-on-map-btn"
              >
                <MapPin className="w-3.5 h-3.5" />
                <span>Show on map</span>
              </button>
            )}

            <button
              type="button"
              onClick={() => handleAck(alert.alert_id)}
              className="py-1.5 px-3 rounded-lg bg-slate-100 dark:bg-slate-800 border border-slate-300 dark:border-slate-700 text-slate-700 dark:text-slate-300 font-medium hover:bg-slate-200 transition-colors flex items-center gap-1"
              data-testid="acknowledge-btn"
            >
              <CheckCircle2 className="w-3.5 h-3.5" />
              <span>Acknowledge</span>
            </button>

            <button
              type="button"
              onClick={() => handleSnooze(alert.alert_id)}
              className="py-1.5 px-2.5 rounded-lg border border-slate-200 dark:border-slate-700 text-slate-500 hover:text-slate-700 transition-colors flex items-center gap-1"
              title="Snooze for 15 minutes"
              data-testid="snooze-btn"
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

export const IoTAlertToasts = ToastHost;
