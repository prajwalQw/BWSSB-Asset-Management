import React, { useState } from 'react';
import { AlertItem } from '../../types';
import { 
  ShieldAlert, 
  AlertTriangle, 
  AlertOctagon, 
  Info, 
  MapPin, 
  ChevronRight, 
  Search, 
  Filter, 
  CheckCircle2,
  Compass,
  X
} from 'lucide-react';
import { ProvenanceChip } from '../common/ProvenanceChip';

interface AlertsDrawerProps {
  alerts: AlertItem[];
  onFlyToAlert: (alert: AlertItem) => void;
  isOpen: boolean;
  onToggle: () => void;
  isDarkTheme?: boolean;
}

export const AlertsDrawer: React.FC<AlertsDrawerProps> = ({
  alerts,
  onFlyToAlert,
  isOpen,
  onToggle,
  isDarkTheme = true
}) => {
  const [filter, setFilter] = useState<'ALL' | 'CRITICAL' | 'WARNING'>('ALL');
  const [search, setSearch] = useState('');

  const filteredAlerts = alerts.filter(a => {
    if (filter === 'CRITICAL' && a.severity !== 'CRITICAL') return false;
    if (filter === 'WARNING' && (a.severity !== 'WARNING' && a.severity !== 'HIGH')) return false;
    if (search && !a.title.toLowerCase().includes(search.toLowerCase()) && !a.location.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  if (!isOpen) {
    return (
      <button
        onClick={onToggle}
        className={`absolute top-20 left-4 z-30 px-3 py-2 rounded-xl border shadow-xl flex items-center gap-2 backdrop-blur-md transition-all font-mono text-xs ${
          isDarkTheme 
            ? 'bg-slate-900/90 border-slate-800 text-slate-200 hover:bg-slate-800' 
            : 'bg-white/95 border-slate-200 text-slate-800 hover:bg-slate-50'
        }`}
      >
        <ShieldAlert className="w-4 h-4 text-rose-500 animate-pulse" />
        <span className="font-semibold">Alerts ({alerts.length})</span>
        <ChevronRight className="w-3.5 h-3.5 text-slate-400" />
      </button>
    );
  }

  return (
    <div className={`absolute top-16 left-4 z-30 w-[360px] max-h-[calc(100vh-140px)] rounded-2xl border shadow-2xl backdrop-blur-xl flex flex-col font-sans transition-all duration-200 overflow-hidden ${
      isDarkTheme 
        ? 'bg-slate-900/95 border-slate-800 text-slate-100' 
        : 'bg-white/95 border-slate-200 text-slate-900'
    }`}>
      {/* Header */}
      <div className={`p-4 border-b flex items-center justify-between ${
        isDarkTheme ? 'border-slate-800' : 'border-slate-200'
      }`}>
        <div className="flex items-center gap-2">
          <div className="p-1.5 rounded-lg bg-rose-500/20 text-rose-400">
            <ShieldAlert className="w-4 h-4" />
          </div>
          <div>
            <h3 className="text-xs font-bold uppercase tracking-wider font-mono">
              Live Network Alerts ({alerts.length})
            </h3>
            <span className="text-[10px] text-slate-400 font-mono">Click card to fly on map</span>
          </div>
        </div>
        <button
          onClick={onToggle}
          className={`p-1 rounded-lg ${isDarkTheme ? 'text-slate-400 hover:text-white hover:bg-slate-800' : 'text-slate-500 hover:text-slate-900 hover:bg-slate-100'}`}
        >
          <X className="w-4 h-4" />
        </button>
      </div>

      {/* Filter & Search Bar */}
      <div className={`p-2.5 border-b space-y-2 ${
        isDarkTheme ? 'border-slate-800/80 bg-slate-950/40' : 'border-slate-200 bg-slate-50'
      }`}>
        <div className="relative">
          <Search className="w-3.5 h-3.5 text-slate-400 absolute left-2.5 top-2.5" />
          <input
            type="text"
            placeholder="Search alerts or locations..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className={`w-full pl-8 pr-3 py-1.5 rounded-lg text-xs font-mono outline-none border transition-all ${
              isDarkTheme 
                ? 'bg-slate-900 border-slate-800 text-slate-200 focus:border-cyan-500' 
                : 'bg-white border-slate-200 text-slate-800 focus:border-cyan-600'
            }`}
          />
        </div>

        <div className="flex items-center gap-1 font-mono text-[10px]">
          {(['ALL', 'CRITICAL', 'WARNING'] as const).map(tab => (
            <button
              key={tab}
              onClick={() => setFilter(tab)}
              className={`px-2.5 py-1 rounded-md font-semibold transition-all ${
                filter === tab
                  ? (tab === 'CRITICAL' ? 'bg-rose-600 text-white' : tab === 'WARNING' ? 'bg-amber-600 text-white' : 'bg-cyan-600 text-white')
                  : (isDarkTheme ? 'text-slate-400 hover:bg-slate-800' : 'text-slate-600 hover:bg-slate-200')
              }`}
            >
              {tab}
            </button>
          ))}
        </div>
      </div>

      {/* Alert Card List */}
      <div className="flex-1 overflow-y-auto p-3 space-y-2.5">
        {filteredAlerts.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500 font-mono">
            No active alerts matching filter.
          </div>
        ) : (
          filteredAlerts.map(alert => {
            const isCrit = alert.severity === 'CRITICAL';
            return (
              <div
                key={alert.alert_id}
                onClick={() => onFlyToAlert(alert)}
                className={`p-3 rounded-xl border cursor-pointer transition-all hover:scale-[1.01] ${
                  isCrit 
                    ? (isDarkTheme ? 'bg-rose-950/20 border-rose-900/60 hover:border-rose-500' : 'bg-rose-50 border-rose-200 hover:border-rose-400')
                    : (isDarkTheme ? 'bg-slate-900/80 border-slate-800 hover:border-slate-700' : 'bg-white border-slate-200 hover:border-slate-300')
                }`}
              >
                <div className="flex items-center justify-between text-[10px] font-mono">
                  <span className={`px-2 py-0.5 rounded font-bold ${
                    isCrit ? 'bg-rose-600 text-white' : 'bg-amber-600 text-white'
                  }`}>
                    {alert.severity}
                  </span>
                  <span className="text-slate-400 flex items-center gap-1 text-[9px]">
                    <Compass className="w-3 h-3 text-cyan-400" /> Click to Fly
                  </span>
                </div>

                <h4 className="text-xs font-bold mt-1.5 leading-snug">
                  {alert.title}
                </h4>

                <p className="text-[11px] text-slate-400 mt-1 line-clamp-2 font-mono">
                  {alert.metric_observed}
                </p>

                <div className="mt-2 pt-1.5 border-t border-slate-800/40 flex items-center justify-between text-[10px] text-slate-400 font-mono">
                  <span className="truncate max-w-[200px] flex items-center gap-1">
                    <MapPin className="w-3 h-3 text-amber-400 shrink-0" />
                    {alert.location.split('(')[0]}
                  </span>
                  <span>{alert.timestamp?.slice(11, 16) || 'Now'}</span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
