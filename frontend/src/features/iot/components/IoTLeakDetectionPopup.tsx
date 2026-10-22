import React, { useState, useEffect } from 'react';
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

export interface IoTLeakDetectionPopupProps {
  alerts: IoTAlertItem[];
  onShowOnMap: (coords: [number, number]) => void;
  onAcknowledge: (alertId: string) => void;
  onSnooze: (alertId: string) => void;
}

const STORAGE_KEY = 'bwssb_iot_shown_popup_alerts';

function getShownAlertIds(): Set<string> {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch {
    return new Set();
  }
}

function markAlertAsShown(alertId: string) {
  try {
    const ids = getShownAlertIds();
    ids.add(alertId);
    localStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(ids)));
  } catch {
    // ignore
  }
}

export const IoTLeakDetectionPopup: React.FC<IoTLeakDetectionPopupProps> = ({
  alerts,
  onShowOnMap,
  onAcknowledge,
  onSnooze,
}) => {
  const [closedIds, setClosedIds] = useState<Set<string>>(new Set());

  // Find active leak alert that hasn't been shown in this browser session (per localStorage)
  // or dismissed in this component lifecycle
  const shownIds = getShownAlertIds();

  const activeLeakAlert = alerts.find((a) => {
    const isLeak = a.rule_id === 'RULE-IOT-LEAK-01' || a.category === 'HYDRAULIC_INTEGRITY' || a.title.toLowerCase().includes('leak');
    const isOngoing = a.active && a.status !== 'CLEARED';
    const notDismissed = !closedIds.has(a.alert_id);
    const notAlreadyShown = !shownIds.has(a.alert_id);
    return isLeak && isOngoing && notDismissed && notAlreadyShown;
  });

  if (!activeLeakAlert) {
    return null;
  }

  const handleClose = () => {
    markAlertAsShown(activeLeakAlert.alert_id);
    setClosedIds((prev) => new Set(prev).add(activeLeakAlert.alert_id));
  };

  const handleAcknowledge = () => {
    markAlertAsShown(activeLeakAlert.alert_id);
    setClosedIds((prev) => new Set(prev).add(activeLeakAlert.alert_id));
    onAcknowledge(activeLeakAlert.alert_id);
  };

  const handleSnooze = () => {
    markAlertAsShown(activeLeakAlert.alert_id);
    setClosedIds((prev) => new Set(prev).add(activeLeakAlert.alert_id));
    onSnooze(activeLeakAlert.alert_id);
  };

  const handleShowOnMap = () => {
    if (activeLeakAlert.coordinates) {
      onShowOnMap(activeLeakAlert.coordinates);
    }
  };

  const lossLps = activeLeakAlert.estimated_loss_lps ?? 45.0;
  const lossKld = activeLeakAlert.estimated_loss_kld ?? Math.round(lossLps * 86.4);
  const confidence = activeLeakAlert.confidence_pct ?? 92;

  return (
    <div className="fixed top-6 left-1/2 -translate-x-1/2 z-50 max-w-lg w-[92vw] sm:w-[480px] select-none animate-in fade-in slide-in-from-top-6 duration-300">
      <div className="p-4 rounded-2xl bg-white dark:bg-slate-900 border-2 border-rose-500 shadow-2xl shadow-rose-950/40 text-xs flex flex-col space-y-3">
        {/* Top Header: Red Icon + Title + Simulated Chip + Close */}
        <div className="flex items-start justify-between gap-2 pb-2 border-b border-slate-200 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-xl bg-rose-500 text-white shadow-md shadow-rose-500/30 animate-pulse">
              <AlertTriangle className="w-5 h-5" />
            </span>
            <div>
              <div className="flex items-center gap-1.5 flex-wrap">
                <h3 className="font-bold text-slate-900 dark:text-slate-100 text-sm">
                  {activeLeakAlert.title.replace('FIT_TG_DISCHARGE and FIT_MJ_INLET', 'Tataguni and Mount Joy GLR')}
                </h3>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold uppercase">
                  SIMULATED
                </span>
              </div>
              <span className="text-[11px] text-slate-500 font-mono">
                {activeLeakAlert.location || 'Pipeline Corridor Ch 6+400'}
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={handleClose}
            className="p-1 rounded text-slate-400 hover:text-slate-600 dark:hover:text-slate-200"
            title="Dismiss popup"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Loss & Confidence Grid */}
        <div className="grid grid-cols-2 gap-2 p-2.5 rounded-xl bg-rose-50 dark:bg-rose-950/40 border border-rose-200 dark:border-rose-900/50">
          <div>
            <span className="text-[10px] text-rose-600 dark:text-rose-400 uppercase font-mono block">
              Estimated Loss
            </span>
            <span className="font-bold font-mono text-base text-rose-700 dark:text-rose-300">
              {lossLps.toFixed(1)} L/s{' '}
              <span className="text-xs font-normal">({lossKld.toLocaleString()} kL/day)</span>
            </span>
          </div>

          <div className="text-right">
            <span className="text-[10px] text-rose-600 dark:text-rose-400 uppercase font-mono block">
              Confidence & Position
            </span>
            <span className="font-bold font-mono text-sm text-rose-700 dark:text-rose-300 block">
              {confidence}% Confidence
            </span>
            <span className="text-[10px] text-rose-600 dark:text-rose-400 font-mono">
              about 40 to 60% of the way
            </span>
          </div>
        </div>

        {/* What May Be Affected */}
        <div className="p-2.5 rounded-lg border border-slate-200 dark:border-slate-800 bg-slate-50 dark:bg-slate-950/50 space-y-1">
          <span className="font-semibold text-slate-800 dark:text-slate-200 block text-[11px]">
            Potential Hydraulic & Supply Impacts:
          </span>
          <ul className="list-disc list-inside space-y-0.5 text-slate-600 dark:text-slate-400 text-[10.5px]">
            <li>Downstream pressure reduction at receiving reservoir</li>
            <li>Accelerated tank drawdown rate at Mount Joy GLR</li>
            <li>Supply deficit to 3 southern BBMP wards</li>
            <li>Extra pumping energy and unmetered loss cost</li>
          </ul>
        </div>

        {/* Suggested Advisory Steps */}
        <div className="p-2 rounded bg-amber-500/10 border border-amber-500/20 text-amber-700 dark:text-amber-300 text-[10.5px]">
          <strong>Advisory Steps:</strong> Check on site for visible surface surfacing • Isolate the segment via motorized valve BFV-104 if loss increases • Deploy ground acoustic correlation survey.
        </div>

        {/* Action Buttons: Show on map | Acknowledge | Snooze */}
        <div className="flex items-center gap-2 pt-1">
          <button
            type="button"
            onClick={handleShowOnMap}
            className="flex-1 py-2 px-3 rounded-xl bg-sky-500 hover:bg-sky-600 text-white font-bold flex items-center justify-center gap-1.5 shadow-md shadow-sky-500/20 transition-colors"
          >
            <MapPin className="w-3.5 h-3.5" />
            <span>Show on map</span>
          </button>

          <button
            type="button"
            onClick={handleAcknowledge}
            className="py-2 px-3 rounded-xl bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700 text-slate-800 dark:text-slate-200 font-medium flex items-center gap-1.5 transition-colors"
          >
            <CheckCircle2 className="w-3.5 h-3.5" />
            <span>Acknowledge</span>
          </button>

          <button
            type="button"
            onClick={handleSnooze}
            className="py-2 px-3 rounded-xl border border-slate-300 dark:border-slate-700 hover:bg-slate-100 dark:hover:bg-slate-800 text-slate-600 dark:text-slate-400 font-medium flex items-center gap-1.5 transition-colors"
          >
            <Clock className="w-3.5 h-3.5" />
            <span>Snooze</span>
          </button>
        </div>
      </div>
    </div>
  );
};
