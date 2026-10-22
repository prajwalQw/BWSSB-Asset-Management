import React from 'react';
import { AlertCircle, RefreshCw, BarChart2 } from 'lucide-react';

export interface ChartContainerProps {
  title?: string;
  unit?: string;
  latestValue?: number | string;
  heightPx: number; // Mandatory fixed pixel height
  isLoading?: boolean;
  isError?: boolean;
  onRetry?: () => void;
  dataPointsCount: number;
  emptyMessage?: string;
  children: React.ReactNode;
}

/**
 * Robust Chart Wrapper enforcing:
 * 1. Fixed pixel height on container (never flex parent dependent)
 * 2. Mandatory 3 states: Loading Skeleton, Error with Retry, Empty State (< 2 points)
 * 3. Never renders an empty axis box
 * 4. Tabular numerals and explicit units
 */
export const ChartContainer: React.FC<ChartContainerProps> = ({
  title,
  unit,
  latestValue,
  heightPx,
  isLoading,
  isError,
  onRetry,
  dataPointsCount,
  emptyMessage = 'No data available: simulated only',
  children,
}) => {
  return (
    <div className="w-full flex flex-col mb-3">
      {/* Header with Title and Tabular Value */}
      {(title || latestValue !== undefined) && (
        <div className="flex items-center justify-between text-xs mb-1 px-0.5">
          {title && <span className="text-slate-500 font-medium">{title}</span>}
          {latestValue !== undefined && (
            <span className="font-mono tabular-nums text-slate-800 dark:text-slate-200 font-semibold text-[13px]">
              {typeof latestValue === 'number'
                ? latestValue.toFixed(1)
                : latestValue}
              {unit && <span className="ml-1 text-[11px] text-slate-500 font-normal">{unit}</span>}
            </span>
          )}
        </div>
      )}

      {/* Explicit Fixed Height Container with min-w-0 */}
      <div
        style={{ height: `${heightPx}px`, minWidth: 0 }}
        className="w-full relative rounded-md border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-1 flex items-center justify-center overflow-hidden"
      >
        {/* STATE 1: LOADING SKELETON */}
        {isLoading && (
          <div className="w-full h-full flex flex-col justify-end p-2 gap-1.5 animate-pulse">
            <div className="w-full bg-slate-200 dark:bg-slate-800 h-2 rounded" />
            <div className="w-3/4 bg-slate-200 dark:bg-slate-800 h-3 rounded" />
            <div className="w-1/2 bg-slate-200 dark:bg-slate-800 h-4 rounded" />
          </div>
        )}

        {/* STATE 2: ERROR WITH RETRY */}
        {!isLoading && isError && (
          <div className="flex flex-col items-center justify-center text-center p-2">
            <AlertCircle className="w-4 h-4 text-rose-500 mb-1" />
            <span className="text-[11px] text-rose-600 dark:text-rose-400 font-medium mb-1.5">
              Failed to load series
            </span>
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="inline-flex items-center gap-1 text-[10px] px-2 py-0.5 rounded border border-rose-300 dark:border-rose-800 text-rose-700 dark:text-rose-300 hover:bg-rose-50 dark:hover:bg-rose-950 transition-colors"
              >
                <RefreshCw className="w-2.5 h-2.5" />
                Retry
              </button>
            )}
          </div>
        )}

        {/* STATE 3: EMPTY STATE (Fewer than 2 points) */}
        {!isLoading && !isError && dataPointsCount < 2 && (
          <div className="flex flex-col items-center justify-center text-center text-slate-400 dark:text-slate-600 p-2">
            <BarChart2 className="w-4 h-4 mb-1 opacity-50" />
            <span className="text-[11px] font-normal">{emptyMessage}</span>
          </div>
        )}

        {/* DATA RENDER: Only when not loading, no error, and >= 2 points */}
        {!isLoading && !isError && dataPointsCount >= 2 && (
          <div className="w-full h-full min-w-0" style={{ height: `${heightPx - 8}px` }}>
            {children}
          </div>
        )}
      </div>
    </div>
  );
};
