import React, { useState, useEffect } from 'react';
import {
  AlertTriangle,
  X,
  MapPin,
  CheckCircle2,
  Clock,
  Droplet,
  PowerOff,
  Check,
  ShieldAlert,
  ArrowRight
} from 'lucide-react';
import { IoTAlertItem } from '../types';
import { DemoStatus, demoApi } from '../services/demoApi';
import { AgentResponseCard } from './AgentResponseCard';
import { WardNoticeBanner } from './WardNoticeBanner';

export interface IoTLeakDetectionPopupProps {
  alerts: IoTAlertItem[];
  demoStatus?: DemoStatus | null;
  onShowOnMap: (coords: [number, number]) => void;
  onAcknowledge: (alertId: string) => void;
  onSnooze?: (alertId: string) => void;
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
  demoStatus,
  onShowOnMap,
  onAcknowledge,
  onSnooze,
}) => {
  const [closedIds, setClosedIds] = useState<Set<string>>(new Set());
  const [shuttingDown, setShuttingDown] = useState(false);

  const shownIds = getShownAlertIds();

  // Find active leak alert
  const activeLeakAlert = alerts.find((a) => {
    const isLeak =
      a.rule_id === 'RULE-IOT-LEAK-01' ||
      a.category === 'HYDRAULIC_INTEGRITY' ||
      a.title.toLowerCase().includes('leak');
    const isOngoing = a.active && a.status !== 'CLEARED';
    const notDismissed = !closedIds.has(a.alert_id);
    const notAlreadyShown = !shownIds.has(a.alert_id);
    return isLeak && isOngoing && notDismissed && notAlreadyShown;
  });

  // If demo is running in diagnosis or action stage, ensure popup is visible even if dismissed
  const isDemoActive = Boolean(
    demoStatus &&
    demoStatus.state !== 'IDLE' &&
    demoStatus.state !== 'RESTORED'
  );

  // If there's neither a detected alert nor active demo in detected+ stage, don't show
  if (!activeLeakAlert && (!isDemoActive || demoStatus?.state === 'LEAK_INJECTED')) {
    return null;
  }

  const alertId = activeLeakAlert?.alert_id || demoStatus?.alert_id || 'ALT-LEAK-CORR_TATAGUNI_MOUNT_JOY';

  const handleClose = () => {
    markAlertAsShown(alertId);
    setClosedIds((prev) => new Set(prev).add(alertId));
  };

  const handleAcknowledge = () => {
    markAlertAsShown(alertId);
    setClosedIds((prev) => new Set(prev).add(alertId));
    onAcknowledge(alertId);
  };

  const handleShowOnMap = () => {
    const coords = activeLeakAlert?.coordinates || demoStatus?.config?.leak_coordinates || [77.5380, 12.9050];
    onShowOnMap(coords as [number, number]);
  };

  const handleTurnOffPump = async () => {
    try {
      setShuttingDown(true);
      await demoApi.approveIsolation('CHIEF_ENGINEER', 'OPERATOR');
    } catch (err) {
      console.error('Failed to turn off pump:', err);
    } finally {
      setShuttingDown(false);
    }
  };

  const lossLps = activeLeakAlert?.estimated_loss_lps ?? demoStatus?.config?.leak_rate_lps ?? 45.0;
  const lossKld = activeLeakAlert?.estimated_loss_kld ?? Math.round(lossLps * 86.4);
  const confidence = activeLeakAlert?.confidence_pct ?? 94;

  const fromStation = demoStatus?.config?.from_station || 'Tataguni';
  const toStation = demoStatus?.config?.to_station || 'Mount Joy GLR';
  const feedingPump = demoStatus?.config?.feeding_pump_name || 'High-Lift Pump 1 (TG-HLP-01)';
  const isolationValve = demoStatus?.config?.isolation_valve_name || 'BFV-104 (Motorised Butterfly Valve)';
  const wardName = demoStatus?.selected_ward || demoStatus?.config?.impacted_wards?.[0] || 'Basavanagudi';
  const exactLocation = demoStatus?.config?.landmark || activeLeakAlert?.location || 'Pipeline Road Chainage 6+400, Basavanagudi';
  const coordinates = demoStatus?.config?.leak_coordinates || [77.5380, 12.9050];

  const isPumpStopped = demoStatus && ['ISOLATING', 'ISOLATED', 'REPAIR_DISPATCHED', 'REPAIR_IN_PROGRESS', 'VERIFYING', 'RESTORING'].includes(demoStatus.state);
  const canTurnOffPump = demoStatus && ['LEAK_DETECTED', 'AGENT_DIAGNOSED', 'AWAITING_APPROVAL', 'COUNTDOWN'].includes(demoStatus.state);

  return (
    <div className="fixed top-5 left-1/2 -translate-x-1/2 z-50 max-w-xl w-[94vw] sm:w-[560px] select-none animate-in fade-in slide-in-from-top-6 duration-300">
      <div className="p-4 rounded-2xl bg-slate-900/95 backdrop-blur-md border-2 border-rose-500 shadow-2xl shadow-rose-950/70 text-xs flex flex-col space-y-3 max-h-[88vh] overflow-y-auto">
        {/* Top Header */}
        <div className="flex items-start justify-between gap-2 pb-2 border-b border-slate-800">
          <div className="flex items-center gap-2.5">
            <span className="p-2.5 rounded-xl bg-rose-600 text-white shadow-lg shadow-rose-600/40 animate-pulse">
              <AlertTriangle className="w-5 h-5" />
            </span>
            <div>
              <div className="flex items-center gap-1.5 flex-wrap">
                <h3 className="font-bold text-slate-100 text-sm">
                  Active Pipe Leak Alert — Ward: {wardName}
                </h3>
                <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-rose-500/20 text-rose-400 border border-rose-500/30 font-bold uppercase">
                  CRITICAL
                </span>
              </div>
              <span className="text-[11px] text-slate-400 font-mono flex items-center gap-1 mt-0.5">
                <MapPin className="w-3 h-3 text-rose-400 inline shrink-0" />
                <span className="text-slate-200 font-semibold">{exactLocation}</span>
                <span className="text-slate-500">({coordinates[1].toFixed(4)}°N, {coordinates[0].toFixed(4)}°E)</span>
              </span>
            </div>
          </div>

          <button
            type="button"
            onClick={handleClose}
            className="p-1 rounded text-slate-400 hover:text-slate-200"
            title="Dismiss popup"
          >
            <X className="w-4 h-4" />
          </button>
        </div>

        {/* Leaking Amount & Loss Metric Grid */}
        <div className="grid grid-cols-2 gap-2 p-3 rounded-xl bg-rose-950/40 border border-rose-800/60">
          <div>
            <span className="text-[10px] text-rose-300 uppercase font-mono tracking-wider block">
              🔴 Approx Water Leaking
            </span>
            <span className="font-bold font-mono text-base text-rose-200">
              ~{lossLps.toFixed(1)} L/s{' '}
              <span className="text-xs font-normal text-rose-300">({lossKld.toLocaleString()} kL/day)</span>
            </span>
            <span className="text-[10px] text-rose-400/80 block mt-0.5">
              Rapid pressure loss detected downstream
            </span>
          </div>

          <div className="text-right">
            <span className="text-[10px] text-rose-300 uppercase font-mono tracking-wider block">
              Confidence & Pipe Corridor
            </span>
            <span className="font-bold font-mono text-sm text-rose-200 block">
              {confidence}% Confidence
            </span>
            <span className="text-[10px] text-rose-300 font-mono">
              {fromStation} &rarr; {toStation}
            </span>
          </div>
        </div>

        {/* Recommended Solution Box */}
        <div className="p-3 rounded-xl border border-sky-500/30 bg-sky-950/20 space-y-1.5">
          <div className="flex items-center gap-1.5 text-sky-400 font-bold text-[11.5px]">
            <ShieldAlert className="w-4 h-4 shrink-0" />
            <span>Recommended Engineering Solution:</span>
          </div>
          <p className="text-slate-300 text-[11px] leading-relaxed">
            Immediately <strong>turn OFF {feedingPump}</strong> and seal <strong>{isolationValve}</strong> to stop water pressure to the ruptured main. Divert emergency supply from {demoStatus?.config?.alternate_source || 'Harohalli Stage V via High Grounds GLR'} ({demoStatus?.config?.alternate_coverage_pct || 65}% coverage) and broadcast outage notice to residents of <strong>{wardName}</strong>.
          </p>
        </div>

        {/* Direct Action: Turn OFF the pump Button */}
        <div className="p-2.5 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-between gap-3">
          <div className="flex items-center gap-2 text-[11px]">
            <PowerOff className={`w-4 h-4 ${isPumpStopped ? 'text-emerald-400' : 'text-rose-400 animate-pulse'}`} />
            <div>
              <span className="font-semibold text-slate-200 block">
                Feeding Pump Status: {isPumpStopped ? 'HALTED & ISOLATED' : 'RUNNING (Pumping into leak)'}
              </span>
              <span className="text-[10px] text-slate-400">
                {feedingPump}
              </span>
            </div>
          </div>

          {canTurnOffPump && (
            <button
              type="button"
              onClick={handleTurnOffPump}
              disabled={shuttingDown}
              className="py-2 px-3.5 rounded-xl bg-rose-600 hover:bg-rose-500 active:bg-rose-700 text-white font-bold text-xs shadow-lg shadow-rose-600/30 flex items-center gap-1.5 transition-all shrink-0 animate-bounce"
            >
              <PowerOff className="w-3.5 h-3.5" />
              <span>{shuttingDown ? 'Shutting down…' : 'Turn OFF the pump'}</span>
            </button>
          )}

          {isPumpStopped && (
            <span className="px-2.5 py-1 rounded-lg bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 text-[10.5px] font-bold flex items-center gap-1 shrink-0">
              <Check className="w-3.5 h-3.5" />
              <span>Pump Turned OFF</span>
            </span>
          )}
        </div>

        {/* Automatic Citizen Alert Message (Ward Notice Banner) */}
        {demoStatus && (
          <WardNoticeBanner demoStatus={demoStatus} />
        )}

        {/* Action Buttons: Show on map | Acknowledge */}
        <div className="flex items-center gap-2 pt-1 border-t border-slate-800">
          <button
            type="button"
            onClick={handleShowOnMap}
            className="flex-1 py-2 px-3 rounded-xl bg-sky-500 hover:bg-sky-600 text-white font-bold flex items-center justify-center gap-1.5 shadow-md shadow-sky-500/20 transition-colors"
          >
            <MapPin className="w-3.5 h-3.5" />
            <span>Show on map & Zoom in</span>
          </button>

          <button
            type="button"
            onClick={handleAcknowledge}
            className="py-2 px-3 rounded-xl bg-slate-800 hover:bg-slate-700 text-slate-200 font-medium flex items-center gap-1.5 transition-colors border border-slate-700"
          >
            <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
            <span>Acknowledge</span>
          </button>
        </div>
      </div>
    </div>
  );
};

