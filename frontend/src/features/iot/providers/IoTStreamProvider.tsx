/**
 * Single App-Level SSE Provider for IoT Digital Twin.
 * Ensures only ONE EventSource connection exists across route transitions and page refreshes.
 * Handles snapshot hydration, reconnect with exponential backoff, and error banner notifications.
 */

import React, { useEffect, useRef, useState } from 'react';
import { useIoTStore } from '../store/useIoTStore';
import { iotApi } from '../services/iotApi';
import { AlertCircle, X } from 'lucide-react';

interface IoTStreamProviderProps {
  children: React.ReactNode;
}

const SSE_URL =
  typeof window !== 'undefined' && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1')
    ? 'http://127.0.0.1:8000/api/v1/iot/stream'
    : '/api/v1/iot/stream';

export const IoTStreamProvider: React.FC<IoTStreamProviderProps> = ({ children }) => {
  const { setSnapshot, mergeSSEDeltas, apiErrorBanner, setApiErrorBanner } = useIoTStore();
  const eventSourceRef = useRef<EventSource | null>(null);
  const reconnectTimeoutRef = useRef<any>(null);
  const backoffDelayRef = useRef<number>(1000);
  const isMountedRef = useRef<boolean>(true);
  const [isConnected, setIsConnected] = useState<boolean>(false);

  useEffect(() => {
    isMountedRef.current = true;

    // 1. Initial Snapshot Hydration
    const hydrateSnapshot = async () => {
      try {
        const snapshot = await iotApi.getSnapshot();
        if (isMountedRef.current) {
          setSnapshot(snapshot);
          setApiErrorBanner(null);
        }
      } catch (err: any) {
        console.warn('[IoTStreamProvider] Initial snapshot fetch failed, falling back to local defaults:', err);
        if (isMountedRef.current) {
          // Attempt standard station/meter fetch if /snapshot endpoint is not yet ready
          try {
            const [stns, divs, flowsData, alrts] = await Promise.all([
              iotApi.getStations(),
              iotApi.getSmartMeters(),
              iotApi.getMldFlows(),
              iotApi.getAlerts()
            ]);
            if (isMountedRef.current) {
              setSnapshot({
                ts: Date.now() / 1000,
                clock_utc: new Date().toISOString(),
                stations: stns,
                alerts: alrts,
                smart_meters: divs,
                corridors: flowsData.corridors,
                water_balance: flowsData.water_balance
              });
            }
          } catch (fallbackErr) {
            setApiErrorBanner('Unable to connect to IoT Telemetry Service. Retrying...');
          }
        }
      }
    };

    hydrateSnapshot();

    // 2. Connect SSE Stream with Exponential Backoff
    const connectSSE = () => {
      if (!isMountedRef.current) return;
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }

      try {
        const es = new EventSource(SSE_URL);
        eventSourceRef.current = es;

        es.onopen = () => {
          if (!isMountedRef.current) return;
          setIsConnected(true);
          backoffDelayRef.current = 1000; // Reset backoff
          setApiErrorBanner(null);
        };

        es.onmessage = (event) => {
          if (!isMountedRef.current) return;
          try {
            const payload = JSON.parse(event.data);
            mergeSSEDeltas(payload);
          } catch (parseErr) {
            console.error('[IoTStreamProvider] SSE message JSON parse error:', parseErr);
          }
        };

        es.onerror = (err) => {
          if (!isMountedRef.current) return;
          setIsConnected(false);
          es.close();
          eventSourceRef.current = null;

          // Exponential backoff up to 10 seconds
          const delay = backoffDelayRef.current;
          backoffDelayRef.current = Math.min(delay * 2, 10000);

          reconnectTimeoutRef.current = setTimeout(() => {
            if (isMountedRef.current) {
              connectSSE();
            }
          }, delay);
        };
      } catch (e: any) {
        console.error('[IoTStreamProvider] Error establishing EventSource:', e);
      }
    };

    connectSSE();

    return () => {
      isMountedRef.current = false;
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
        eventSourceRef.current = null;
      }
    };
  }, []);

  return (
    <>
      {/* In-app Small Error Banner for Failed API Calls */}
      {apiErrorBanner && (
        <div className="fixed top-14 left-1/2 -translate-x-1/2 z-50 flex items-center gap-2 px-3 py-1.5 rounded-md bg-amber-500/90 text-white text-xs font-medium shadow-lg backdrop-blur animate-in fade-in slide-in-from-top-2">
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
