import React from 'react';
import { DataTier } from '../../types';
import { ShieldCheck, Cpu, Radio } from 'lucide-react';

interface ProvenanceChipProps {
  tier: DataTier;
  source?: string;
  date?: string;
  size?: 'sm' | 'md' | 'lg';
  showDetails?: boolean;
}

export const ProvenanceChip: React.FC<ProvenanceChipProps> = ({
  tier,
  source,
  date,
  size = 'md',
  showDetails = true,
}) => {
  const getBadgeStyle = () => {
    switch (tier) {
      case 'REAL':
        return {
          bg: 'bg-emerald-950/80 border-emerald-500/40 text-emerald-300',
          dot: 'bg-emerald-400',
          icon: <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />,
          label: 'REAL',
          defaultSource: 'OpenCity / BWSSB Published',
        };
      case 'SIMULATED':
        return {
          bg: 'bg-purple-950/80 border-purple-500/40 text-purple-300',
          dot: 'bg-purple-400',
          icon: <Cpu className="w-3.5 h-3.5 text-purple-400" />,
          label: 'SIMULATED',
          defaultSource: 'WNTR / EPANET Simulator',
        };
      case 'LIVE':
        return {
          bg: 'bg-cyan-950/80 border-cyan-500/40 text-cyan-300',
          dot: 'bg-cyan-400 animate-pulse',
          icon: <Radio className="w-3.5 h-3.5 text-cyan-400 animate-pulse" />,
          label: 'LIVE',
          defaultSource: 'IGNOAPI Bridge (Port 8899)',
        };
    }
  };

  const style = getBadgeStyle();
  const textSize = size === 'sm' ? 'text-[10px] px-2 py-0.5' : size === 'lg' ? 'text-xs px-3 py-1.5' : 'text-xs px-2.5 py-1';

  return (
    <div className="inline-flex items-center gap-1.5 flex-wrap">
      <span
        className={`inline-flex items-center gap-1.5 font-semibold tracking-wider uppercase rounded-full border backdrop-blur-sm shadow-sm font-mono ${style.bg} ${textSize}`}
      >
        {style.icon}
        <span>{style.label}</span>
      </span>

      {showDetails && (
        <span className="text-[11px] text-slate-400 font-sans truncate max-w-[240px]">
          {source || style.defaultSource}
          {date ? ` • ${date}` : ''}
        </span>
      )}
    </div>
  );
};
