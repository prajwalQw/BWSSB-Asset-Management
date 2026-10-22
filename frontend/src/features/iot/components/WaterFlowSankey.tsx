import React, { useState } from 'react';
import { WaterFlowCorridor, WaterBalanceSummary } from '../types';
import { CheckCircle2, AlertTriangle, Info, ArrowRight } from 'lucide-react';

export interface WaterFlowSankeyProps {
  corridors: WaterFlowCorridor[];
  balance: WaterBalanceSummary;
}

interface SankeyNode {
  id: string;
  name: string;
  stage: number; // 0=Source, 1=WTP, 2=PS, 3=Reservoir, 4=DMA
  mld: number;
  capacity?: string;
  isVerified: boolean;
  citation?: string;
}

export const WaterFlowSankey: React.FC<WaterFlowSankeyProps> = ({ corridors, balance }) => {
  const [selectedNode, setSelectedNode] = useState<SankeyNode | null>(null);

  // Structural nodes across the Cauvery conveyance chain
  const nodes: SankeyNode[] = [
    // Stage 0: Sources
    { id: 'SRC_CAUVERY_I_IV', name: 'Cauvery River Intake (Stages I-IV)', stage: 0, mld: 1475.0, capacity: '1,475 MLD', isVerified: true, citation: 'JICA Phase 3 Final Report Part 4 (p. 17-9)' },
    { id: 'SRC_CAUVERY_V', name: 'Cauvery River Intake (Stage V)', stage: 0, mld: 775.0, capacity: '775 MLD', isVerified: true, citation: 'BWSSB Cauvery Stage V DPR & Commissioning (2023)' },

    // Stage 1: Water Treatment Plants
    { id: 'WTP_TKH', name: 'T.K. Halli Water Treatment Plant', stage: 1, mld: 1475.0, capacity: '1,475 MLD', isVerified: true, citation: 'Yokogawa 2015 Case Study, p. 1' },
    { id: 'WTP_HARO', name: 'Harohalli Intermediate Booster Headworks', stage: 1, mld: 775.0, capacity: '775 MLD', isVerified: true, citation: 'BWSSB Cauvery Stage V DPR' },

    // Stage 2: High-Lift Pumping Stations
    { id: 'PS_TATAGUNI', name: 'Tataguni Terminal Pumping Complex', stage: 2, mld: 2250.0, capacity: '2,250 MLD', isVerified: true, citation: 'BWSSB Annual Operations Report 2022-23' },

    // Stage 3: Service Reservoirs (GLRs)
    { id: 'GLR_HIGH_GROUNDS', name: 'High Grounds Ground Level Reservoir', stage: 3, mld: 460.0, capacity: '35 MLD storage', isVerified: true, citation: 'Yokogawa 2015 Case Study, GLR Supervisory Specs' },
    { id: 'GLR_MOUNT_JOY', name: 'Mount Joy Ground Level Reservoir', stage: 3, mld: 320.0, capacity: '22 MLD storage', isVerified: true, citation: 'Yokogawa 2015 Case Study, GLR Supervisory Specs' },
    { id: 'GLR_MACHILIBETTA', name: 'Machilibetta Balancing Reservoir', stage: 3, mld: 180.0, capacity: 'Unverified', isVerified: false, citation: 'Capacity not published in open verified records' },

    // Stage 4: Distribution / DMAs
    { id: 'DMA_CENTRAL', name: 'Central CBD & Vidhana Soudha DMA', stage: 4, mld: 420.0, isVerified: true },
    { id: 'DMA_SOUTH', name: 'Basavanagudi - Hanumanthanagar DMA', stage: 4, mld: 295.0, isVerified: true },
    { id: 'DMA_WEST', name: 'Rajajinagar & West Division DMAs', stage: 4, mld: 380.0, isVerified: true }
  ];

  const stageTitles = [
    'Raw Water Source',
    'Treatment Works (WTP)',
    'High-Lift Pumping',
    'Service Reservoirs (GLR)',
    'Distribution DMAs'
  ];

  return (
    <div className="w-full h-full bg-slate-950 p-6 flex flex-col select-none overflow-y-auto">
      {/* Header & Water Balance Check Tile */}
      <div className="flex flex-col md:flex-row items-start md:items-center justify-between pb-4 border-b border-slate-800 gap-4 mb-6">
        <div>
          <div className="flex items-center gap-2">
            <h2 className="text-base font-bold text-slate-100">
              Macro Water Flow & Conveyance Balance (MLD)
            </h2>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-400 border border-amber-500/30 font-bold">
              SIMULATED
            </span>
          </div>
          <p className="text-xs text-slate-400 mt-0.5">
            Volumetric flow chain from Cauvery River headworks to metropolitan distribution zones.
          </p>
        </div>

        {/* Water Balance Summary Box */}
        <div className="p-2.5 rounded-xl border border-slate-800 bg-slate-900/80 flex items-center gap-4 text-xs">
          <div>
            <span className="text-slate-500 block text-[11px]">Inflow</span>
            <span className="font-bold text-sky-400 font-mono tabular-nums">{balance.total_inflow_mld.toFixed(1)} MLD</span>
          </div>
          <div className="text-slate-600">-</div>
          <div>
            <span className="text-slate-500 block text-[11px]">Outflow</span>
            <span className="font-bold text-emerald-400 font-mono tabular-nums">{balance.total_outflow_mld.toFixed(1)} MLD</span>
          </div>
          <div className="text-slate-600">-</div>
          <div>
            <span className="text-slate-500 block text-[11px]">Δ Storage</span>
            <span className="font-bold text-slate-300 font-mono tabular-nums">{balance.storage_change_mld.toFixed(1)} MLD</span>
          </div>
          <div className="text-slate-600">=</div>
          <div className="pl-2 border-l border-slate-800">
            <span className="text-slate-500 block text-[11px]">Unaccounted (NRW)</span>
            <span className="font-bold text-amber-400 font-mono tabular-nums">
              {balance.unaccounted_mld.toFixed(1)} MLD ({balance.unaccounted_pct.toFixed(1)}%)
            </span>
          </div>
        </div>
      </div>

      {/* Sankey Stages Columns */}
      <div className="grid grid-cols-5 gap-4 flex-1">
        {stageTitles.map((title, stageIdx) => {
          const stageNodes = nodes.filter((n) => n.stage === stageIdx);
          return (
            <div key={stageIdx} className="flex flex-col gap-3">
              <div className="text-center pb-2 border-b border-slate-800/80">
                <span className="text-xs text-slate-400 font-semibold">
                  {title}
                </span>
              </div>

              <div className="flex flex-col gap-3 flex-1 justify-around">
                {stageNodes.map((node) => {
                  const isSelected = selectedNode?.id === node.id;
                  return (
                    <div
                      key={node.id}
                      onClick={() => setSelectedNode(node)}
                      className={`p-3 rounded-xl border transition-all cursor-pointer relative shadow-lg ${
                        isSelected
                          ? 'border-sky-500 bg-sky-950/40 shadow-sky-950'
                          : 'border-slate-800 bg-slate-900/60 hover:border-slate-700'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="text-xs font-semibold text-slate-200 line-clamp-1" title={node.name}>
                          {node.name}
                        </span>
                        {node.isVerified ? (
                          <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-emerald-950 text-emerald-400 border border-emerald-800 font-bold">
                            VERIFIED
                          </span>
                        ) : (
                          <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-rose-950 text-rose-400 border border-rose-800 font-bold">
                            UNVERIFIED
                          </span>
                        )}
                      </div>

                      <div className="flex items-baseline justify-between mt-2 pt-1 border-t border-slate-800/60 font-mono">
                        <span className="text-[10px] text-slate-500">Flow:</span>
                        <span className="text-sm font-bold text-sky-400 tabular-nums">
                          {node.mld.toFixed(1)} <span className="text-[10px] text-sky-600">MLD</span>
                        </span>
                      </div>

                      {node.capacity && (
                        <div className="flex items-center justify-between text-[10px] text-slate-400 font-mono mt-0.5">
                          <span>Capacity:</span>
                          <span className={node.isVerified ? 'text-slate-300' : 'text-rose-400 italic font-semibold'}>
                            {node.capacity}
                          </span>
                        </div>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>

      {/* Selected Node Provenance & Metadata Card */}
      {selectedNode && (
        <div className="mt-4 p-3 rounded-xl border border-slate-800 bg-slate-900/90 flex items-center justify-between text-xs">
          <div className="flex items-center gap-3">
            <Info className="w-4 h-4 text-sky-400 flex-shrink-0" />
            <div>
              <span className="font-bold text-slate-200 mr-2">{selectedNode.name}</span>
              <span className="text-slate-400">
                {selectedNode.citation
                  ? `Source: ${selectedNode.citation}`
                  : 'Derived from municipal consumption aggregations'}
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setSelectedNode(null)}
            className="text-[11px] text-slate-500 hover:text-slate-300 font-mono px-2 py-1"
          >
            Dismiss
          </button>
        </div>
      )}
    </div>
  );
};
