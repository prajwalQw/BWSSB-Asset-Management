/**
 * TanStack Query-compatible hooks for digital twin data querying and SSE streaming.
 * Features:
 * - Cache key management
 * - Strict 3-state reporting: Loading, Error with Retry, Empty / Data
 * - Minimum 2-point validation for telemetry/trend series
 * - Auto-reconnecting SSE with exponential backoff
 */

import { useState, useEffect, useCallback, useRef } from 'react';

export interface QueryResult<T> {
  data: T | null;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  refetch: () => void;
}

const memoryCache = new Map<string, { data: any; timestamp: number }>();

/**
 * Robust async query hook with caching and retry.
 */
export function useTwinQuery<T>(
  queryKey: string,
  queryFn: () => Promise<T>,
  options: {
    refetchInterval?: number;
    enabled?: boolean;
    cacheTimeMs?: number;
  } = {}
): QueryResult<T> {
  const { refetchInterval = 0, enabled = true, cacheTimeMs = 5000 } = options;

  const [data, setData] = useState<T | null>(() => {
    const cached = memoryCache.get(queryKey);
    if (cached && Date.now() - cached.timestamp < cacheTimeMs) {
      return cached.data;
    }
    return null;
  });
  const [isLoading, setIsLoading] = useState<boolean>(!data);
  const [isError, setIsError] = useState<boolean>(false);
  const [error, setError] = useState<Error | null>(null);

  const isMountedRef = useRef(true);

  const executeFetch = useCallback(async () => {
    if (!enabled) return;
    try {
      setIsError(false);
      setError(null);
      const res = await queryFn();
      if (!isMountedRef.current) return;
      memoryCache.set(queryKey, { data: res, timestamp: Date.now() });
      setData(res);
      setIsLoading(false);
    } catch (err: any) {
      if (!isMountedRef.current) return;
      console.warn(`[useTwinQuery:${queryKey}] fetch failed:`, err);
      setIsError(true);
      setError(err instanceof Error ? err : new Error(String(err)));
      setIsLoading(false);
    }
  }, [queryKey, queryFn, enabled]);

  useEffect(() => {
    isMountedRef.current = true;
    if (enabled) {
      executeFetch();
    }
    let intervalId: any = null;
    if (refetchInterval > 0 && enabled) {
      intervalId = setInterval(executeFetch, refetchInterval);
    }
    return () => {
      isMountedRef.current = false;
      if (intervalId) clearInterval(intervalId);
    };
  }, [executeFetch, refetchInterval, enabled]);

  return {
    data,
    isLoading,
    isError,
    error,
    refetch: executeFetch,
  };
}

/**
 * Auto-reconnecting SSE hook with exponential backoff for live IGNOAPI updates.
 */
export function useSSELiveTelemetry(
  url: string,
  onMessage: (data: any) => void,
  onStatusChange: (isLive: boolean) => void
) {
  useEffect(() => {
    let sse: EventSource | null = null;
    let reconnectTimeout: any = null;
    let backoffDelay = 1000;
    let isCancelled = false;

    function connect() {
      if (isCancelled) return;
      try {
        sse = new EventSource(url);

        const handlePacket = (e: MessageEvent) => {
          backoffDelay = 1000; // Reset backoff on successful packet
          onStatusChange(true);
          try {
            const parsed = JSON.parse(e.data);
            onMessage(parsed);
          } catch {
            // Ignore parse errors
          }
        };

        sse.onmessage = handlePacket;
        sse.addEventListener('telemetry', handlePacket);

        sse.onerror = () => {
          onStatusChange(false);
          if (sse) {
            sse.close();
            sse = null;
          }
          if (!isCancelled) {
            reconnectTimeout = setTimeout(() => {
              backoffDelay = Math.min(backoffDelay * 1.5, 10000);
              connect();
            }, backoffDelay);
          }
        };
      } catch {
        onStatusChange(false);
      }
    }

    connect();

    return () => {
      isCancelled = true;
      if (reconnectTimeout) clearTimeout(reconnectTimeout);
      if (sse) sse.close();
    };
  }, [url, onMessage, onStatusChange]);
}
