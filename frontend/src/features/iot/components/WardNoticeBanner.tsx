import React, { useState } from 'react';
import {
  Megaphone,
  CheckCircle2,
  Clock,
  AlertTriangle,
  Copy,
  Check,
  Wrench,
  Send
} from 'lucide-react';
import { DemoStatus, WardNotice, demoApi } from '../services/demoApi';

export interface WardNoticeBannerProps {
  demoStatus: DemoStatus;
  onRepairCompleted?: () => void;
}

export const WardNoticeBanner: React.FC<WardNoticeBannerProps> = ({
  demoStatus,
  onRepairCompleted,
}) => {
  const [copied, setCopied] = useState(false);
  const [submittingRepair, setSubmittingRepair] = useState(false);

  const { state, selected_ward, ward_notice, config } = demoStatus;
  const wardName = selected_ward || config?.impacted_wards?.[0] || 'Basavanagudi';
  const landmark = config?.landmark || 'Pipeline Road Chainage 6+400';

  // Determine if repair task is started and repair done button should be shown
  const isRepairActive = ['ISOLATED', 'REPAIR_DISPATCHED', 'REPAIR_IN_PROGRESS'].includes(state);
  const isRestored = state === 'RESTORED';

  // If no notice yet and not in active disruption or restored state, do not render
  if (!ward_notice && !isRepairActive && !isRestored) {
    return null;
  }

  const isRestoredNotice = ward_notice?.type === 'RESTORED' || isRestored;

  // Format message text
  const messageText = ward_notice?.message || (
    isRestoredNotice
      ? `Notice to residents of ${wardName}: Emergency pipeline repair at ${landmark} has been completed. Thanks for your cooperation, you can use water now.`
      : `Notice to residents of ${wardName}: There is a leakage in this area at ${landmark}, so emergency repair work is underway. Water will not be available from 09:00 AM to 01:00 PM. Sorry for the inconvenience caused, please cooperate with us.`
  );

  const handleCopy = () => {
    navigator.clipboard.writeText(messageText);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleRepairDone = async () => {
    try {
      setSubmittingRepair(true);
      await demoApi.markRepairDone();
      if (onRepairCompleted) onRepairCompleted();
    } catch (err) {
      console.error('Failed to mark repair as done:', err);
    } finally {
      setSubmittingRepair(false);
    }
  };

  return (
    <div
      className={`p-3.5 rounded-xl border text-xs flex flex-col space-y-2.5 shadow-lg transition-all ${
        isRestoredNotice
          ? 'bg-emerald-950/40 border-emerald-500/50 text-emerald-100'
          : 'bg-amber-950/40 border-amber-500/50 text-amber-100'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between pb-1.5 border-b border-white/10">
        <div className="flex items-center gap-2">
          <span
            className={`p-1.5 rounded-lg ${
              isRestoredNotice
                ? 'bg-emerald-500/20 text-emerald-400'
                : 'bg-amber-500/20 text-amber-400 animate-pulse'
            }`}
          >
            {isRestoredNotice ? (
              <CheckCircle2 className="w-4 h-4" />
            ) : (
              <Megaphone className="w-4 h-4" />
            )}
          </span>
          <div>
            <span className="font-bold uppercase tracking-wider text-[11px] block">
              {isRestoredNotice
                ? `BWSSB Public Advisory — Water Supply Restored`
                : `BWSSB Public Alert — Citizen Disruption Notice`}
            </span>
            <span className="text-[10px] text-slate-300 font-mono">
              Broadcast Ward: <strong className="text-white">{wardName}</strong> • {landmark}
            </span>
          </div>
        </div>

        <button
          type="button"
          onClick={handleCopy}
          className="flex items-center gap-1 px-2 py-1 rounded bg-black/30 hover:bg-black/50 text-[10px] font-mono text-slate-200 transition-colors border border-white/10"
          title="Copy alert message to clipboard"
        >
          {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
          <span>{copied ? 'Copied' : 'Copy'}</span>
        </button>
      </div>

      {/* Message Content */}
      <div className="p-2.5 rounded-lg bg-black/40 border border-white/10 text-[11.5px] leading-relaxed font-sans">
        <p className="font-medium text-slate-100 italic">
          "{messageText}"
        </p>
      </div>

      {/* Footer Details & Action Button */}
      <div className="flex items-center justify-between pt-1 gap-2">
        <div className="flex items-center gap-1.5 text-[10px] font-mono text-slate-400">
          <Send className="w-3 h-3 text-sky-400" />
          <span>Dispatched automatically to ward resident portal & SMS</span>
        </div>

        {/* Display 'Repair Done' button once repair task is started */}
        {isRepairActive && (
          <button
            type="button"
            onClick={handleRepairDone}
            disabled={submittingRepair}
            className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 active:bg-emerald-700 text-white font-bold text-xs shadow-md shadow-emerald-600/30 transition-all flex items-center gap-1.5 shrink-0"
          >
            <Wrench className="w-3.5 h-3.5" />
            <span>{submittingRepair ? 'Marking Done…' : 'Repair Done'}</span>
          </button>
        )}
      </div>
    </div>
  );
};
