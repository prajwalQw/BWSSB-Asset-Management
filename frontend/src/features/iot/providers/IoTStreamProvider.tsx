/**
 * App-Level SSE & State Hydration Provider for IoT Digital Twin.
 * Uses the module-level singleton SSEManager to guarantee ONE EventSource app-wide.
 * Hydrates consolidated /api/v1/snapshot and merges typed SSE deltas.
 * Shows "Backend unreachable. Retrying…" when snapshot fails without using local defaults.
 */

import React, { useEffect, useRef, useState, useCallback } from 'react';
import { useIoTStore } from '../store/useIoTStore';
import { iotApi } from '../services/iotApi';
import { sseManager } from '../../../services/sseManager';
import { AlertCircle, X } from 'lucide-react';

interface IoTStreamProviderProps {
  children: React.ReactNode;
}

export const IoTStreamProvider: React.FC<IoTStreamProviderProps> = ({ children }) => {
  const { setSnapshot, mergeSSEDeltas, apiErrorBanner, setApiErrorBanner } = useIoTStore();
  const isMountedRef = useRef<boolean>(true);
  const [retryCount, setRetryCount] = useState(0);

  const hydrateSnapshot = useCallback(async () => {
    try {
      const snapshot = await iotApi.getSnapshot();
      if (isMountedRef.current) {
        setSnapshot(snapshot);
        setApiErrorBanner(null);
      }
    } catch (err: any) {
      if (isMountedRef.current) {
        setApiErrorBanner('Backend unreachable. Retrying…');
        // Retry snapshot with backoff
        setTimeout(() => {
          if (isMountedRef.current) {
            setRetryCount((prev) => prev + 1);
          }
        }, 5000);
      }
    }
  }, [setSnapshot, setApiErrorBanner]);

  useEffect(() => {
    hydrateSnapshot();
  }, [hydrateSnapshot, retryCount]);

  useEffect(() => {
    isMountedRef.current = true;
    sseManager.retain();

    // Subscribe to typed SSE deltas
    const unsubTelemetry = sseManager.subscribe('telemetry', (payload) => {
      if (!isMountedRef.current) return;
      mergeSSEDeltas(payload);
    });

    const unsubAlert = sseManager.subscribe('alert', (alerts) => {
      if (!isMountedRef.current) return;
      mergeSSEDeltas({
        ts: Date.now() / 1000,
        clock_utc: new Date().toISOString(),
        alerts: Array.isArray(alerts) ? alerts : [],
      });
    });

    const unsubLeak = sseManager.subscribe('leak', (leaks) => {
      if (!isMountedRef.current) return;
      const store = useIoTStore.getState();
      const currentInjections = { ...store.activeInjections };
      const leakMap: Record<string, any> = {};
      if (Array.isArray(leaks)) {
        leaks.forEach((l) => {
          if (l.pipe_segment_id) leakMap[l.pipe_segment_id] = l;
        });
      }
      currentInjections.leaks = leakMap;
      useIoTStore.setState({ activeInjections: currentInjections });
    });

    const unsubConn = sseManager.subscribe('connection', (conn) => {
      if (!isMountedRef.current) return;
      if (conn.isLive && apiErrorBanner === 'Backend unreachable. Retrying…') {
        setApiErrorBanner(null);
      }
    });

    return () => {
      isMountedRef.current = false;
      unsubTelemetry();
      unsubAlert();
      unsubLeak();
      unsubConn();
      sseManager.release();
    };
  }, [mergeSSEDeltas, apiErrorBanner, setApiErrorBanner]);

  return (
    <>
      {/* Small Banner for API Unreachability */}
      {apiErrorBanner && (
        <div className="fixed top-14 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 px-3 py-1.5 rounded-md bg-amber-500/95 text-white text-xs font-medium shadow-lg backdrop-blur animate-in fade-in slide-in-from-top-2">
          <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
          <span>{apiErrorBanner}</span>
          <button
            onClick={() => setApiErrorBanner(null)}
            className="ml-2 hover:bg-amber-600/50 rounded p-0.5"
            aria-label="Dismiss error"
          >
            <X className="w-3 h-3" />
          </button>
        </div>
      )}
      {children}
    </>
  );
};
