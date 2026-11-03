import React from 'react';
import {
  Droplet,
  AlertTriangle,
  Lock,
  Wrench,
  CheckCircle2,
  Clock,
  Sparkles
} from 'lucide-react';

export interface DemoStepperProps {
  state: string; // IDLE | LEAK_INJECTED | DETECTED | AGENT_DIAGNOSED | AWAITING_APPROVAL | COUNTDOWN | ISOLATING | ISOLATED | REPAIR_DISPATCHED | REPAIR_IN_PROGRESS | VERIFYING | RESTORING | RESTORED
  elapsedS?: number;
  className?: string;
}

interface StepDef {
  key: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  states: string[];
}

const STEPS: StepDef[] = [
  {
    key: 'leak',
    label: 'Leak',
    icon: Droplet,
    states: ['LEAK_INJECTED'],
  },
  {
    key: 'detected',
    label: 'Detected',
    icon: AlertTriangle,
    states: ['DETECTED', 'AGENT_DIAGNOSED', 'AWAITING_APPROVAL', 'COUNTDOWN'],
  },
  {
    key: 'isolated',
    label: 'Isolated',
    icon: Lock,
    states: ['ISOLATING', 'ISOLATED'],
  },
  {
    key: 'repair',
    label: 'Repair',
    icon: Wrench,
    states: ['REPAIR_DISPATCHED', 'REPAIR_IN_PROGRESS', 'VERIFYING'],
  },
  {
    key: 'restored',
    label: 'Restored',
    icon: CheckCircle2,
    states: ['RESTORING', 'RESTORED'],
  },
];

export const DemoStepper: React.FC<DemoStepperProps> = ({ state, elapsedS = 0, className = '' }) => {
  // Determine current active step index
  let activeIndex = -1;
  STEPS.forEach((step, idx) => {
    if (step.states.includes(state)) {
      activeIndex = idx;
    }
  });

  const isRestored = state === 'RESTORED';
  const isIdle = state === 'IDLE';

  return (
    <div className={`p-3 rounded-xl border border-slate-800 bg-slate-900/90 text-xs select-none shadow-lg ${className}`}>
      {/* Top Header Row */}
      <div className="flex items-center justify-between pb-2 mb-2 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Sparkles className="w-3.5 h-3.5 text-sky-400" />
          <span className="font-bold text-slate-200 uppercase tracking-wider text-[11px]">
            Demo Status Stepper
          </span>
          <span className="text-[10px] font-mono px-1.5 py-0.2 rounded bg-amber-500/10 text-amber-500 border border-amber-500/30 font-bold">
            SIMULATED
          </span>
        </div>

        <div className="flex items-center gap-2 font-mono text-[11px]">
          <span className="flex items-center gap-1 text-slate-400">
            <Clock className="w-3 h-3 text-sky-400" />
            <span>Elapsed:</span>
            <strong className="text-slate-200">{elapsedS.toFixed(1)}s</strong>
          </span>
          <span className={`px-2 py-0.5 rounded text-[10px] font-bold ${
            isIdle ? 'bg-slate-800 text-slate-400' :
            isRestored ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40' :
            'bg-sky-500/20 text-sky-300 border border-sky-500/40 animate-pulse'
          }`}>
            {state}
          </span>
        </div>
      </div>

      {/* Stepper Pipeline */}
      <div className="flex items-center justify-between relative py-1">
        {STEPS.map((step, idx) => {
          const StepIcon = step.icon;
          const isCurrent = idx === activeIndex;
          const isPassed = !isIdle && (activeIndex > idx || isRestored);

          return (
            <React.Fragment key={step.key}>
              {/* Step Node */}
              <div className="flex flex-col items-center z-10">
                <div
                  className={`w-7 h-7 rounded-full flex items-center justify-center transition-all ${
                    isCurrent
                      ? 'bg-rose-500 text-white ring-4 ring-rose-500/30 scale-110 shadow-lg'
                      : isPassed
                      ? 'bg-emerald-500 text-white'
                      : 'bg-slate-800 text-slate-500 border border-slate-700'
                  }`}
                >
                  <StepIcon className="w-3.5 h-3.5" />
                </div>
                <span
                  className={`mt-1.5 text-[10.5px] font-medium tracking-tight ${
                    isCurrent
                      ? 'text-rose-400 font-bold'
                      : isPassed
                      ? 'text-emerald-400 font-semibold'
                      : 'text-slate-500'
                  }`}
                >
                  {step.label}
                </span>
              </div>

              {/* Connecting Bar between nodes */}
              {idx < STEPS.length - 1 && (
                <div className="flex-1 h-0.5 mx-1 relative bg-slate-800">
                  <div
                    className={`absolute inset-0 transition-all duration-500 ${
                      isPassed || (isCurrent && activeIndex > idx)
                        ? 'bg-emerald-500'
                        : isCurrent
                        ? 'bg-gradient-to-r from-emerald-500 to-rose-500'
                        : 'bg-slate-800'
                    }`}
                  />
                </div>
              )}
            </React.Fragment>
          );
        })}
      </div>

      {/* Governance Disclaimer */}
      <div className="mt-2.5 pt-2 border-t border-slate-800/80 text-[10px] text-slate-500 flex items-center justify-between">
        <span>Automatic isolation is simulated. Real field control is not enabled.</span>
        <span className="font-mono text-slate-600">Read-Only Bridge</span>
      </div>
    </div>
  );
};
