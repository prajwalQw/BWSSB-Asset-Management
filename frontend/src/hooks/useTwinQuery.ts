/**
 * TanStack Query-compatible hooks for digital twin data querying and SSE streaming.
 * Features:
 * - Cache key management
 * - Stable query keys
 * - refetchInterval >= 5000 ms and only for visible queries
 * - refetchOnWindowFocus: false
 * - Max 2 retries with exponential backoff
 * - AbortController cleanup on unmount & StrictMode safe
 * - Delegated SSE streaming via sseManager singleton
 */

import { useState, useEffect, useCallback, useRef } from 'react';
import { sseManager } from '../services/sseManager';

export interface QueryResult<T> {
  data: T | null;
  isLoading: boolean;
  isError: boolean;
  error: Error | null;
  refetch: () => void;
}

const memoryCache = new Map<string, { data: any; timestamp: number }>();

/**
 * Robust async query hook with caching, AbortController, backoff retry, and visibility-aware polling.
 */
export function useTwinQuery<T>(
  queryKey: string,
  queryFn: (signal?: AbortSignal) => Promise<T>,
  options: {
    refetchInterval?: number;
    enabled?: boolean;
    cacheTimeMs?: number;
    refetchOnWindowFocus?: boolean;
    retry?: number;
  } = {}
): QueryResult<T> {
  const {
    refetchInterval = 0,
    enabled = true,
    cacheTimeMs = 5000,
    retry = 2,
  } = options;

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
  const abortControllerRef = useRef<AbortController | null>(null);
  const retryCountRef = useRef(0);
  const queryFnRef = useRef(queryFn);
  queryFnRef.current = queryFn;

  const executeFetch = useCallback(async () => {
    if (!enabled) return;
    if (typeof document !== 'undefined' && document.visibilityState === 'hidden' && refetchInterval > 0) {
      // Don't refetch background tabs
      return;
    }

    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const ac = new AbortController();
    abortControllerRef.current = ac;

    const runAttempt = async (attempt: number): Promise<void> => {
      try {
        setIsError(false);
        setError(null);
        const res = await queryFnRef.current(ac.signal);
        if (!isMountedRef.current || ac.signal.aborted) return;
        memoryCache.set(queryKey, { data: res, timestamp: Date.now() });
        setData(res);
        setIsLoading(false);
        retryCountRef.current = 0;
      } catch (err: any) {
        if (!isMountedRef.current || ac.signal.aborted) return;
        if (attempt < retry) {
          const delay = Math.pow(2, attempt) * 1000;
          await new Promise((resolve) => setTimeout(resolve, delay));
          if (!isMountedRef.current || ac.signal.aborted) return;
          return runAttempt(attempt + 1);
        }
        console.warn(`[useTwinQuery:${queryKey}] fetch failed after retries:`, err);
        setIsError(true);
        setError(err instanceof Error ? err : new Error(String(err)));
        setIsLoading(false);
      }
    };

    await runAttempt(0);
  }, [queryKey, enabled, refetchInterval, retry]);

  useEffect(() => {
    isMountedRef.current = true;
    if (enabled) {
      executeFetch();
    }

    let intervalId: any = null;
    // Enforce refetchInterval >= 5000 ms to eliminate request storms
    const safeInterval = refetchInterval > 0 ? Math.max(refetchInterval, 5000) : 0;
    if (safeInterval > 0 && enabled) {
      intervalId = setInterval(() => {
        if (typeof document !== 'undefined' && document.visibilityState === 'visible') {
          executeFetch();
        }
      }, safeInterval);
    }

    return () => {
      isMountedRef.current = false;
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
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
 * Singleton-backed SSE hook for backward compatibility.
 * Redirects to the global sseManager.
 */
export function useSSELiveTelemetry(
  _url: string,
  onMessage: (data: any) => void,
  onStatusChange: (isLive: boolean) => void
) {
  const onMessageRef = useRef(onMessage);
  onMessageRef.current = onMessage;
  const onStatusChangeRef = useRef(onStatusChange);
  onStatusChangeRef.current = onStatusChange;

  useEffect(() => {
    sseManager.retain();
    const unsubTelemetry = sseManager.subscribe('telemetry', (payload) => {
      onMessageRef.current(payload);
    });
    const unsubConn = sseManager.subscribe('connection', (status) => {
      onStatusChangeRef.current(status.isLive);
    });

    return () => {
      unsubTelemetry();
      unsubConn();
      sseManager.release();
    };
  }, []);
}
