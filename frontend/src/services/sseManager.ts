/**
 * Module-level Singleton SSE Manager with reference counting.
 * Guarantees exactly ONE EventSource connection across the entire application.
 * Features:
 * - Reference counting (retain / release) to prevent multiple connections
 * - Single multiplexed endpoint /api/v1/stream
 * - Watchdog timer: 15s without any event or heartbeat marks connection as Offline
 * - Exponential backoff auto-reconnect (1s to 10s)
 * - Typed event dispatching ('telemetry', 'alert', 'leak', 'plan', 'agent', 'heartbeat', 'connection')
 */

import { useEffect, useState, useRef } from 'react';

type SSEListener = (data: any) => void;

class SSEManager {
  private eventSource: EventSource | null = null;
  private refCount = 0;
  private listeners: Map<string, Set<SSEListener>> = new Map();
  private reconnectTimeout: any = null;
  private backoffDelay = 1000;
  private watchdogTimer: any = null;
  private isLive = false;
  private isConnected = false;
  private readonly WATCHDOG_TIMEOUT_MS = 15000;

  constructor() {
    // Initial state
  }

  public retain() {
    this.refCount++;
    if (this.refCount === 1) {
      this.connect();
    }
  }

  public release() {
    this.refCount = Math.max(0, this.refCount - 1);
    if (this.refCount === 0) {
      this.disconnect();
    }
  }

  public subscribe(event: string, listener: SSEListener): () => void {
    if (!this.listeners.has(event)) {
      this.listeners.set(event, new Set());
    }
    this.listeners.get(event)!.add(listener);

    return () => {
      const set = this.listeners.get(event);
      if (set) {
        set.delete(listener);
        if (set.size === 0) {
          this.listeners.delete(event);
        }
      }
    };
  }

  public getStatus() {
    return {
      isConnected: this.isConnected,
      isLive: this.isLive,
    };
  }

  private resetWatchdog() {
    if (this.watchdogTimer) {
      clearTimeout(this.watchdogTimer);
    }
    if (!this.isLive) {
      this.isLive = true;
      this.emit('connection', { isConnected: this.isConnected, isLive: true });
    }
    this.watchdogTimer = setTimeout(() => {
      this.isLive = false;
      this.emit('connection', { isConnected: this.isConnected, isLive: false });
    }, this.WATCHDOG_TIMEOUT_MS);
  }

  private emit(event: string, data: any) {
    const handlers = this.listeners.get(event);
    if (handlers) {
      handlers.forEach((fn) => {
        try {
          fn(data);
        } catch (e) {
          console.error(`[SSEManager] Error in handler for event ${event}:`, e);
        }
      });
    }
  }

  private connect() {
    if (typeof window === 'undefined') return;
    if (this.eventSource) return;

    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }

    try {
      const es = new EventSource('/api/v1/stream');
      this.eventSource = es;

      es.onopen = () => {
        this.isConnected = true;
        this.backoffDelay = 1000; // Reset backoff
        this.resetWatchdog();
        this.emit('connection', { isConnected: true, isLive: this.isLive });
      };

      const handleRawMessage = (e: MessageEvent, fallbackType?: string) => {
        this.resetWatchdog();
        try {
          const parsed = JSON.parse(e.data);
          const type = (e as any).type || fallbackType || 'message';
          this.emit(type, parsed);
        } catch {
          // ignore parsing error
        }
      };

      es.onmessage = (e) => handleRawMessage(e, 'message');

      // Typed SSE listeners
      const typedEvents = ['heartbeat', 'telemetry', 'alert', 'leak', 'plan', 'agent', 'demo'];
      typedEvents.forEach((eventType) => {
        es.addEventListener(eventType, (e: any) => {
          this.resetWatchdog();
          try {
            const parsed = JSON.parse(e.data);
            this.emit(eventType, parsed);
          } catch {
            // ignore
          }
        });
      });

      es.onerror = () => {
        this.isConnected = false;
        this.isLive = false;
        this.emit('connection', { isConnected: false, isLive: false });

        if (this.eventSource) {
          this.eventSource.close();
          this.eventSource = null;
        }

        if (this.watchdogTimer) {
          clearTimeout(this.watchdogTimer);
          this.watchdogTimer = null;
        }

        // Reconnect with exponential backoff if there are still consumers
        if (this.refCount > 0 && !this.reconnectTimeout) {
          const delay = this.backoffDelay;
          this.backoffDelay = Math.min(this.backoffDelay * 1.5, 10000);
          this.reconnectTimeout = setTimeout(() => {
            this.reconnectTimeout = null;
            if (this.refCount > 0) {
              this.connect();
            }
          }, delay);
        }
      };
    } catch (err) {
      console.warn('[SSEManager] Failed to create EventSource:', err);
    }
  }

  private disconnect() {
    if (this.watchdogTimer) {
      clearTimeout(this.watchdogTimer);
      this.watchdogTimer = null;
    }
    if (this.reconnectTimeout) {
      clearTimeout(this.reconnectTimeout);
      this.reconnectTimeout = null;
    }
    if (this.eventSource) {
      this.eventSource.close();
      this.eventSource = null;
    }
    this.isConnected = false;
    this.isLive = false;
    this.emit('connection', { isConnected: false, isLive: false });
  }
}

export const sseManager = new SSEManager();

/**
 * Hook to subscribe to SSE connection status.
 */
export function useSSEConnectionStatus() {
  const [status, setStatus] = useState(() => sseManager.getStatus());

  useEffect(() => {
    sseManager.retain();
    const unsubscribe = sseManager.subscribe('connection', (s) => {
      setStatus({ isConnected: s.isConnected, isLive: s.isLive });
    });
    return () => {
      unsubscribe();
      sseManager.release();
    };
  }, []);

  return status;
}

/**
 * Hook to subscribe to a typed SSE event with auto-ref-counting.
 */
export function useSSEEvent<T = any>(event: string, callback: (data: T) => void) {
  const callbackRef = useRef(callback);
  callbackRef.current = callback;

  useEffect(() => {
    sseManager.retain();
    const unsubscribe = sseManager.subscribe(event, (data) => {
      callbackRef.current(data);
    });

    return () => {
      unsubscribe();
      sseManager.release();
    };
  }, [event]);
}
