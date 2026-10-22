"""
SQLite Persistence Layer for BWSSB IoT Subsystem.
Persists simulation state, devices latest readings, 24h timeseries,
alerts with complete lifecycle (ACTIVE -> ACKNOWLEDGED -> CLEARED),
alert audit events, and simulation injections.
"""

import sqlite3
import os
import time
import json
import logging
from typing import Dict, List, Optional, Any, Tuple
from pathlib import Path

logger = logging.getLogger("bwssb_iot.storage")

DEFAULT_DB_PATH = Path(__file__).resolve().parent.parent.parent.parent / "data" / "iot_state.db"

class IoTStorage:
    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = str(db_path or DEFAULT_DB_PATH)
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(os.path.abspath(self.db_path)), exist_ok=True)
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                conn.executescript("""
                    CREATE TABLE IF NOT EXISTS sim_state (
                        key TEXT PRIMARY KEY,
                        value TEXT NOT NULL,
                        updated_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS devices_latest (
                        tag TEXT NOT NULL,
                        signal TEXT NOT NULL,
                        value REAL NOT NULL,
                        unit TEXT,
                        quality TEXT NOT NULL DEFAULT 'Good',
                        updated_at REAL NOT NULL,
                        PRIMARY KEY (tag, signal)
                    );

                    CREATE TABLE IF NOT EXISTS timeseries (
                        tag TEXT NOT NULL,
                        signal TEXT NOT NULL,
                        ts REAL NOT NULL,
                        value REAL NOT NULL,
                        quality TEXT NOT NULL DEFAULT 'Good',
                        PRIMARY KEY (tag, signal, ts)
                    );
                    CREATE INDEX IF NOT EXISTS idx_ts_query ON timeseries (tag, signal, ts);

                    CREATE TABLE IF NOT EXISTS alerts (
                        alert_id TEXT PRIMARY KEY,
                        rule_id TEXT NOT NULL,
                        asset_id TEXT,
                        category TEXT NOT NULL,
                        severity TEXT NOT NULL,
                        title TEXT NOT NULL,
                        location TEXT NOT NULL,
                        coordinates_json TEXT,
                        metric_observed TEXT,
                        recommendation TEXT,
                        requires_human_approval INTEGER DEFAULT 1,
                        human_decision_status TEXT DEFAULT 'PENDING_REVIEW',
                        status TEXT NOT NULL DEFAULT 'ACTIVE',
                        first_seen REAL NOT NULL,
                        last_seen REAL NOT NULL,
                        cleared_at REAL,
                        acknowledged_by TEXT,
                        acknowledged_at REAL,
                        extra_json TEXT,
                        data_tier TEXT NOT NULL DEFAULT 'SIMULATED',
                        source TEXT NOT NULL DEFAULT 'IOT'
                    );
                    CREATE INDEX IF NOT EXISTS idx_alerts_status ON alerts (status, last_seen);

                    CREATE TABLE IF NOT EXISTS alert_events (
                        event_id TEXT PRIMARY KEY,
                        alert_id TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        ts REAL NOT NULL,
                        details_json TEXT,
                        FOREIGN KEY (alert_id) REFERENCES alerts (alert_id)
                    );

                    CREATE TABLE IF NOT EXISTS injections (
                        injection_type TEXT NOT NULL,
                        target_id TEXT NOT NULL,
                        params_json TEXT NOT NULL,
                        active INTEGER NOT NULL DEFAULT 1,
                        created_at REAL NOT NULL,
                        PRIMARY KEY (injection_type, target_id)
                    );
                """)
        except Exception as e:
            logger.error(f"Failed to initialize SQLite storage at {self.db_path}: {e}")

    # -------------------------------------------------------------------------
    # Simulation State
    # -------------------------------------------------------------------------
    def set_sim_state(self, key: str, value: Any):
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO sim_state (key, value, updated_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(key) DO UPDATE SET
                        value = excluded.value,
                        updated_at = excluded.updated_at
                """, (key, json.dumps(value), time.time()))
        except Exception as e:
            logger.warning(f"Error saving sim_state key {key}: {e}")

    def get_sim_state(self, key: str, default: Any = None) -> Any:
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT value FROM sim_state WHERE key = ?", (key,))
                row = cursor.fetchone()
                if row:
                    return json.loads(row["value"])
        except Exception as e:
            logger.warning(f"Error reading sim_state key {key}: {e}")
        return default

    # -------------------------------------------------------------------------
    # Devices Latest Readings
    # -------------------------------------------------------------------------
    def save_device_latest_batch(self, rows: List[Tuple[str, str, float, str, str, float]]):
        if not rows:
            return
        try:
            with self._get_connection() as conn:
                conn.executemany("""
                    INSERT INTO devices_latest (tag, signal, value, unit, quality, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(tag, signal) DO UPDATE SET
                        value = excluded.value,
                        unit = excluded.unit,
                        quality = excluded.quality,
                        updated_at = excluded.updated_at
                """, rows)
        except Exception as e:
            logger.warning(f"Error saving devices_latest batch: {e}")

    def get_all_devices_latest(self) -> Dict[Tuple[str, str], Dict[str, Any]]:
        results = {}
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT tag, signal, value, unit, quality, updated_at FROM devices_latest")
                for r in cursor.fetchall():
                    results[(r["tag"], r["signal"])] = {
                        "value": r["value"],
                        "unit": r["unit"],
                        "quality": r["quality"],
                        "updated_at": r["updated_at"]
                    }
        except Exception as e:
            logger.warning(f"Error reading devices_latest: {e}")
        return results

    # -------------------------------------------------------------------------
    # Timeseries & Retention (24h)
    # -------------------------------------------------------------------------
    def save_timeseries_batch(self, rows: List[Tuple[str, str, float, float, str]]):
        if not rows:
            return
        try:
            with self._get_connection() as conn:
                conn.executemany("""
                    INSERT OR REPLACE INTO timeseries (tag, signal, ts, value, quality)
                    VALUES (?, ?, ?, ?, ?)
                """, rows)
        except Exception as e:
            logger.warning(f"Error saving timeseries batch: {e}")

    def get_timeseries(
        self,
        tag: str,
        signal: str,
        from_ts: Optional[float] = None,
        to_ts: Optional[float] = None,
        step_s: Optional[float] = None
    ) -> List[Dict[str, Any]]:
        now = time.time()
        start = from_ts if from_ts is not None else (now - 3600.0)
        end = to_ts if to_ts is not None else now
        step = step_s or 5.0

        results = []
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT ts, value, quality
                    FROM timeseries
                    WHERE tag = ? AND signal = ? AND ts >= ? AND ts <= ?
                    ORDER BY ts ASC
                """, (tag, signal, start, end))
                rows = cursor.fetchall()

            last_t = -1.0
            for r in rows:
                t = r["ts"]
                if last_t < 0 or (t - last_t) >= (step * 0.9):
                    results.append({
                        "timestamp": round(t, 2),
                        "value": round(r["value"], 3),
                        "quality": r["quality"]
                    })
                    last_t = t
        except Exception as e:
            logger.warning(f"Error fetching timeseries for {tag}.{signal}: {e}")
        return results

    def prune_old_timeseries(self, retention_hours: float = 24.0) -> int:
        cutoff = time.time() - (retention_hours * 3600.0)
        deleted = 0
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("DELETE FROM timeseries WHERE ts < ?", (cutoff,))
                deleted = cursor.rowcount
        except Exception as e:
            logger.warning(f"Error pruning timeseries older than {retention_hours}h: {e}")
        return deleted

    # -------------------------------------------------------------------------
    # Alert Persistence & Complete Lifecycle
    # -------------------------------------------------------------------------
    def save_alert(self, alert_data: Dict[str, Any]):
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO alerts (
                        alert_id, rule_id, asset_id, category, severity, title,
                        location, coordinates_json, metric_observed, recommendation,
                        requires_human_approval, human_decision_status, status,
                        first_seen, last_seen, cleared_at, acknowledged_by,
                        acknowledged_at, extra_json, data_tier, source
                    ) VALUES (
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                    )
                    ON CONFLICT(alert_id) DO UPDATE SET
                        severity = excluded.severity,
                        title = excluded.title,
                        metric_observed = excluded.metric_observed,
                        recommendation = excluded.recommendation,
                        human_decision_status = excluded.human_decision_status,
                        status = excluded.status,
                        last_seen = excluded.last_seen,
                        cleared_at = excluded.cleared_at,
                        acknowledged_by = excluded.acknowledged_by,
                        acknowledged_at = excluded.acknowledged_at,
                        extra_json = excluded.extra_json
                """, (
                    alert_data["alert_id"],
                    alert_data.get("rule_id", "RULE-IOT"),
                    alert_data.get("asset_id"),
                    alert_data.get("category", "HYDRAULIC"),
                    alert_data.get("severity", "WARNING"),
                    alert_data.get("title", "Alert"),
                    alert_data.get("location", "Bengaluru"),
                    json.dumps(alert_data.get("coordinates") or []),
                    alert_data.get("metric_observed", ""),
                    alert_data.get("recommendation", ""),
                    1 if alert_data.get("requires_human_approval", True) else 0,
                    alert_data.get("human_decision_status", "PENDING_REVIEW"),
                    alert_data.get("status", "ACTIVE"),
                    alert_data.get("first_seen", time.time()),
                    alert_data.get("last_seen", time.time()),
                    alert_data.get("cleared_at"),
                    alert_data.get("acknowledged_by"),
                    alert_data.get("acknowledged_at"),
                    json.dumps({
                        "estimated_loss_lps": alert_data.get("estimated_loss_lps"),
                        "estimated_loss_kld": alert_data.get("estimated_loss_kld"),
                        "confidence_pct": alert_data.get("confidence_pct"),
                        "uncertainty_corridor": alert_data.get("uncertainty_corridor"),
                        "nearest_landmark": alert_data.get("nearest_landmark"),
                        "affected_elements": alert_data.get("affected_elements"),
                        "suggested_steps": alert_data.get("suggested_steps")
                    }),
                    alert_data.get("data_tier", "SIMULATED"),
                    alert_data.get("source", "IOT")
                ))
        except Exception as e:
            logger.warning(f"Error saving alert {alert_data.get('alert_id')}: {e}")

    def record_alert_event(self, alert_id: str, event_type: str, details: Optional[Dict[str, Any]] = None):
        event_id = f"EVT-{int(time.time() * 1000)}-{os.urandom(2).hex()}"
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO alert_events (event_id, alert_id, event_type, ts, details_json)
                    VALUES (?, ?, ?, ?, ?)
                """, (event_id, alert_id, event_type, time.time(), json.dumps(details or {})))
        except Exception as e:
            logger.warning(f"Error recording alert event for {alert_id}: {e}")

    def get_alerts(self, status: Optional[str] = None, hours_history: float = 24.0) -> List[Dict[str, Any]]:
        results = []
        cutoff = time.time() - (hours_history * 3600.0)
        try:
            with self._get_connection() as conn:
                if status:
                    cursor = conn.execute("""
                        SELECT * FROM alerts
                        WHERE status = ? AND (status = 'ACTIVE' OR last_seen >= ?)
                        ORDER BY last_seen DESC
                    """, (status.upper(), cutoff))
                else:
                    cursor = conn.execute("""
                        SELECT * FROM alerts
                        WHERE status IN ('ACTIVE', 'ACKNOWLEDGED') OR last_seen >= ?
                        ORDER BY last_seen DESC
                    """, (cutoff,))

                for row in cursor.fetchall():
                    extra = json.loads(row["extra_json"]) if row["extra_json"] else {}
                    coords = json.loads(row["coordinates_json"]) if row["coordinates_json"] else []
                    results.append({
                        "alert_id": row["alert_id"],
                        "rule_id": row["rule_id"],
                        "asset_id": row["asset_id"],
                        "category": row["category"],
                        "severity": row["severity"],
                        "title": row["title"],
                        "location": row["location"],
                        "coordinates": coords if coords else None,
                        "metric_observed": row["metric_observed"],
                        "recommendation": row["recommendation"],
                        "requires_human_approval": bool(row["requires_human_approval"]),
                        "human_decision_status": row["human_decision_status"],
                        "status": row["status"],
                        "first_seen": row["first_seen"],
                        "last_seen": row["last_seen"],
                        "cleared_at": row["cleared_at"],
                        "acknowledged_by": row["acknowledged_by"],
                        "acknowledged_at": row["acknowledged_at"],
                        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(row["last_seen"])),
                        "timestamp_epoch": row["last_seen"],
                        "data_tier": row["data_tier"],
                        "source": row["source"],
                        "active": row["status"] in ("ACTIVE", "ACKNOWLEDGED"),
                        "acknowledged": row["status"] == "ACKNOWLEDGED",
                        "shelved": row["status"] == "SHELVED",
                        **extra
                    })
        except Exception as e:
            logger.warning(f"Error fetching alerts: {e}")
        return results

    # -------------------------------------------------------------------------
    # Injections Persistence
    # -------------------------------------------------------------------------
    def save_injection(self, injection_type: str, target_id: str, params: Dict[str, Any], active: bool = True):
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO injections (injection_type, target_id, params_json, active, created_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT(injection_type, target_id) DO UPDATE SET
                        params_json = excluded.params_json,
                        active = excluded.active
                """, (injection_type, target_id, json.dumps(params), 1 if active else 0, time.time()))
        except Exception as e:
            logger.warning(f"Error saving injection {injection_type}:{target_id}: {e}")

    def clear_injection(self, injection_type: str, target_id: str):
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    UPDATE injections SET active = 0 WHERE injection_type = ? AND target_id = ?
                """, (injection_type, target_id))
        except Exception as e:
            logger.warning(f"Error clearing injection {injection_type}:{target_id}: {e}")

    def get_active_injections(self) -> List[Dict[str, Any]]:
        results = []
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("SELECT * FROM injections WHERE active = 1")
                for row in cursor.fetchall():
                    results.append({
                        "injection_type": row["injection_type"],
                        "target_id": row["target_id"],
                        "params": json.loads(row["params_json"]),
                        "created_at": row["created_at"]
                    })
        except Exception as e:
            logger.warning(f"Error reading active injections: {e}")
        return results

    def reset_all_injections(self):
        try:
            with self._get_connection() as conn:
                conn.execute("UPDATE injections SET active = 0")
        except Exception as e:
            logger.warning(f"Error resetting injections: {e}")

# Global storage singleton
iot_storage = IoTStorage()
