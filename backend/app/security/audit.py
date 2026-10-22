"""
Append-Only Hash-Chained Audit Log.
Maintains cryptographic integrity for all sensitive actions:
- User logins / logouts
- Alert acknowledgements & snooze
- Leak & fault simulation injections
- Configuration changes
"""

import os
import time
import sqlite3
import hashlib
import json
import logging
from typing import Dict, List, Any, Optional

logger = logging.getLogger("bwssb.security.audit")

DB_PATH = os.path.join(os.path.dirname(__file__), "..", "..", "..", "data", "security.db")
GENESIS_HASH = "0" * 64

class HashChainedAuditLogger:
    def __init__(self, db_path: Optional[str] = None):
        self.db_path = str(db_path) if db_path else DB_PATH
        self._init_db()

    def _init_db(self):
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    who TEXT NOT NULL,
                    what TEXT NOT NULL,
                    from_where TEXT NOT NULL,
                    details TEXT NOT NULL,
                    prev_hash TEXT NOT NULL,
                    entry_hash TEXT NOT NULL
                )
            """)
            conn.commit()

    def record(self, who: str, what: str, from_where: str, details: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        timestamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        details_str = json.dumps(details or {})

        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT entry_hash FROM audit_log ORDER BY id DESC LIMIT 1")
            last_row = cur.fetchone()
            prev_hash = last_row["entry_hash"] if last_row else GENESIS_HASH

            # Cryptographic hash chaining: H(prev_hash || who || what || from_where || timestamp)
            raw = f"{prev_hash}|{who}|{what}|{from_where}|{details_str}|{timestamp}"
            entry_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()

            cur.execute("""
                INSERT INTO audit_log (timestamp, who, what, from_where, details, prev_hash, entry_hash)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (timestamp, who, what, from_where, details_str, prev_hash, entry_hash))
            conn.commit()

            return {
                "id": cur.lastrowid,
                "timestamp": timestamp,
                "who": who,
                "what": what,
                "from_where": from_where,
                "prev_hash": prev_hash,
                "entry_hash": entry_hash
            }

    def get_recent(self, limit: int = 50) -> List[Dict[str, Any]]:
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM audit_log ORDER BY id DESC LIMIT ?", (limit,))
            return [dict(row) for row in cur.fetchall()]

    def verify_chain(self) -> Dict[str, Any]:
        """
        Traverses the full audit trail from genesis to head, verifying each hash pointer.
        Returns validation status and record count.
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM audit_log ORDER BY id ASC")
            rows = cur.fetchall()

            if not rows:
                return {
                    "valid": True,
                    "total_records": 0,
                    "head_hash": GENESIS_HASH,
                    "message": "Audit chain empty. Genesis state valid."
                }

            expected_prev = GENESIS_HASH
            for row in rows:
                if row["prev_hash"] != expected_prev:
                    return {
                        "valid": False,
                        "broken_at_id": row["id"],
                        "expected_prev": expected_prev,
                        "found_prev": row["prev_hash"],
                        "error": f"Hash chain broken at record id {row['id']}!",
                        "message": f"Hash chain broken at record id {row['id']}!"
                    }

                raw = f"{row['prev_hash']}|{row['who']}|{row['what']}|{row['from_where']}|{row['details']}|{row['timestamp']}"
                recomputed = hashlib.sha256(raw.encode("utf-8")).hexdigest()
                if recomputed != row["entry_hash"]:
                    return {
                        "valid": False,
                        "broken_at_id": row["id"],
                        "error": f"Tampered entry detected: Hash mismatch at record id {row['id']}!",
                        "message": f"Tampered entry detected at record id {row['id']}!"
                    }

                expected_prev = row["entry_hash"]

            return {
                "valid": True,
                "total_records": len(rows),
                "head_hash": rows[-1]["entry_hash"],
                "message": f"Audit log verified. All {len(rows)} hash-chained records intact."
            }

AuditLogger = HashChainedAuditLogger
audit_logger = HashChainedAuditLogger()
