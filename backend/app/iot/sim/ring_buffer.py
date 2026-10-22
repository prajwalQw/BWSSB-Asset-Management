"""
High-Performance In-Memory Ring Buffer with Periodic SQLite Snapshot.
Stores 24h of telemetry at 5s resolution (17,280 points per channel).
Survives process restarts via sqlite snapshots.
"""

import collections
import time
import sqlite3
import os
import threading
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
import logging

logger = logging.getLogger("bwssb_iot.ring_buffer")

class RingBufferStore:
    def __init__(self, max_samples: int = 17280, db_path: Optional[str] = None):
        self.max_samples = max_samples
        self.db_path = db_path or "data/iot_history.db"
        # Key: (tag, signal) -> collections.deque([(timestamp, value, quality), ...])
        self._buffers: Dict[Tuple[str, str], collections.deque] = {}
        self._lock = threading.Lock()
        self._init_sqlite()
        self._load_from_sqlite()

    def _init_sqlite(self):
        try:
            os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
            with sqlite3.connect(self.db_path) as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS iot_telemetry (
                        tag TEXT NOT NULL,
                        signal TEXT NOT NULL,
                        timestamp REAL NOT NULL,
                        value REAL NOT NULL,
                        quality TEXT NOT NULL,
                        PRIMARY KEY (tag, signal, timestamp)
                    )
                """)
                conn.execute("CREATE INDEX IF NOT EXISTS idx_tag_signal_ts ON iot_telemetry (tag, signal, timestamp)")
        except Exception as e:
            logger.warning(f"Failed to initialize SQLite snapshot store: {e}")

    def append(self, tag: str, signal: str, timestamp: float, value: float, quality: str = "Good") -> None:
        key = (tag, signal)
        with self._lock:
            if key not in self._buffers:
                self._buffers[key] = collections.deque(maxlen=self.max_samples)
            self._buffers[key].append((timestamp, value, quality))

    def get_timeseries(
        self,
        tag: str,
        signal: str,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        step_s: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        key = (tag, signal)
        now = time.time()
        start = from_ts if from_ts is not None else (now - 3600.0) # default 1 hour
        end = to_ts if to_ts is not None else now
        step = step_s or 5.0

        with self._lock:
            if key not in self._buffers:
                return []
            raw = list(self._buffers[key])

        # Filter within range
        filtered = [pt for pt in raw if start <= pt[0] <= end]
        if not filtered:
            return []

        # Subsample if step is larger than native resolution
        result = []
        last_t = -1.0
        for pt in filtered:
            t, v, q = pt
            if last_t < 0 or (t - last_t) >= (step * 0.9):
                result.append({
                    "timestamp": round(t, 2),
                    "value": round(v, 3),
                    "quality": q
                })
                last_t = t

        return result

    def get_latest(self, tag: str, signal: str) -> Optional[Tuple[float, float, str]]:
        key = (tag, signal)
        with self._lock:
            if key in self._buffers and len(self._buffers[key]) > 0:
                return self._buffers[key][-1]
        return None

    def snapshot_to_sqlite(self) -> int:
        """Flushes recent samples into SQLite snapshot."""
        try:
            with self._lock:
                snapshot_data = []
                for (tag, sig), q in self._buffers.items():
                    # take recent 60 items per signal
                    recent = list(q)[-60:]
                    for ts, val, qual in recent:
                        snapshot_data.append((tag, sig, ts, val, qual))

            if not snapshot_data:
                return 0

            with sqlite3.connect(self.db_path) as conn:
                conn.executemany("""
                    INSERT OR REPLACE INTO iot_telemetry (tag, signal, timestamp, value, quality)
                    VALUES (?, ?, ?, ?, ?)
                """, snapshot_data)
                conn.commit()
            return len(snapshot_data)
        except Exception as e:
            logger.warning(f"Failed SQLite snapshot: {e}")
            return 0

    def _load_from_sqlite(self):
        """Loads last 2 hours from SQLite on startup."""
        if not os.path.exists(self.db_path):
            return
        try:
            cutoff = time.time() - 7200.0
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT tag, signal, timestamp, value, quality
                    FROM iot_telemetry
                    WHERE timestamp >= ?
                    ORDER BY timestamp ASC
                """, (cutoff,))
                rows = cursor.fetchall()

            with self._lock:
                for tag, sig, ts, val, qual in rows:
                    key = (tag, sig)
                    if key not in self._buffers:
                        self._buffers[key] = collections.deque(maxlen=self.max_samples)
                    self._buffers[key].append((ts, val, qual))
            logger.info(f"Loaded {len(rows)} telemetry history points from SQLite.")
        except Exception as e:
            logger.warning(f"Could not load SQLite history: {e}")

# Global ring buffer singleton
ring_buffer = RingBufferStore()
