from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import math
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional


class LocalStore:
    """Local-only SQLite store with privacy-first minimal schema."""
    STALE_DECAY_HALF_LIFE_DAYS = 45.0

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self._ensure_error_pattern_columns()

    def _init_schema(self) -> None:
        cur = self.conn.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS error_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                error_pattern TEXT NOT NULL,
                intended_pattern TEXT NOT NULL,
                confidence REAL DEFAULT 0.1,
                frequency INTEGER DEFAULT 1,
                rejection_count INTEGER DEFAULT 0,
                last_seen REAL,
                last_rejected REAL,
                success_count INTEGER DEFAULT 0,
                failure_count INTEGER DEFAULT 0,
                lifecycle_state TEXT DEFAULT 'embryonic',
                last_transition REAL,
                UNIQUE(error_pattern, intended_pattern)
            );

            CREATE TABLE IF NOT EXISTS privacy_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                kind TEXT NOT NULL,
                reason TEXT NOT NULL,
                app_name TEXT,
                profile TEXT,
                event_type TEXT,
                token_hash TEXT,
                meta_json TEXT
            );

            CREATE TABLE IF NOT EXISTS proof_reports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                report_json TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_patterns_lookup ON error_patterns(error_pattern, confidence DESC);
            CREATE INDEX IF NOT EXISTS idx_privacy_ts ON privacy_events(ts DESC);
            """
        )
        self.conn.commit()

    def _ensure_error_pattern_columns(self) -> None:
        """Migrate existing databases in place without destructive operations."""
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(error_patterns)")
        existing = {str(row["name"]) for row in cur.fetchall()}

        migrations = [
            ("success_count", "ALTER TABLE error_patterns ADD COLUMN success_count INTEGER DEFAULT 0"),
            ("failure_count", "ALTER TABLE error_patterns ADD COLUMN failure_count INTEGER DEFAULT 0"),
            ("lifecycle_state", "ALTER TABLE error_patterns ADD COLUMN lifecycle_state TEXT DEFAULT 'embryonic'"),
            ("last_transition", "ALTER TABLE error_patterns ADD COLUMN last_transition REAL"),
        ]
        for column_name, sql in migrations:
            if column_name not in existing:
                cur.execute(sql)
        self.conn.commit()

    @staticmethod
    def _derive_lifecycle_state(
        *,
        success_count: int,
        failure_count: int,
        confidence: float,
    ) -> str:
        total = success_count + failure_count
        if success_count >= 5 and confidence >= 0.75 and failure_count <= max(1, success_count // 2):
            return "thriving"
        if total >= 3 and failure_count >= max(2, success_count):
            return "declining"
        if success_count >= 2 and success_count > failure_count:
            return "viable"
        return "embryonic"

    def _update_lifecycle(
        self,
        *,
        pattern_id: int,
        success_count: int,
        failure_count: int,
        confidence: float,
    ) -> None:
        cur = self.conn.cursor()
        cur.execute("SELECT lifecycle_state FROM error_patterns WHERE id=?", (pattern_id,))
        row = cur.fetchone()
        old_state = str(row["lifecycle_state"] or "embryonic") if row else "embryonic"
        new_state = self._derive_lifecycle_state(
            success_count=success_count,
            failure_count=failure_count,
            confidence=confidence,
        )
        if new_state != old_state:
            cur.execute(
                """
                UPDATE error_patterns
                SET lifecycle_state=?, last_transition=?
                WHERE id=?
                """,
                (new_state, datetime.now().timestamp(), pattern_id),
            )
            self.conn.commit()

    @staticmethod
    def hash_token(token: str) -> str:
        return sha256(token.encode("utf-8")).hexdigest()[:16]

    def upsert_pattern(self, error: str, intended: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, frequency, rejection_count
            FROM error_patterns
            WHERE lower(error_pattern)=lower(?) AND lower(intended_pattern)=lower(?)
            """,
            (error, intended),
        )
        row = cur.fetchone()
        now = datetime.now().timestamp()

        if row:
            freq = int(row["frequency"]) + 1
            rejection = max(0, int(row["rejection_count"] or 0) - 1)
            base_conf = min(freq / 10.0, 1.0)
            adjusted_conf = max(0.05, base_conf / (1.0 + 0.25 * rejection))
            cur.execute(
                """
                UPDATE error_patterns
                SET frequency=?, confidence=?, rejection_count=?, last_seen=?
                WHERE id=?
                """,
                (freq, adjusted_conf, rejection, now, int(row["id"])),
            )
        else:
            cur.execute(
                """
                INSERT INTO error_patterns
                (
                    error_pattern, intended_pattern, confidence, frequency, rejection_count,
                    last_seen, success_count, failure_count, lifecycle_state, last_transition
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (error, intended, 0.1, 1, 0, now, 0, 0, "embryonic", now),
            )
        self.conn.commit()

    def get_candidates_for_token(self, token: str, limit: int = 5) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT
                id, error_pattern, intended_pattern, confidence, frequency,
                rejection_count, last_rejected, last_seen
            FROM error_patterns
            WHERE lower(error_pattern)=lower(?)
            ORDER BY confidence DESC, frequency DESC
            LIMIT ?
            """,
            (token, limit),
        )
        rows = cur.fetchall()

        out: List[Dict[str, Any]] = []
        now = datetime.now().timestamp()
        for row in rows:
            rejection_count = int(row["rejection_count"] or 0)
            last_rejected = row["last_rejected"]
            if last_rejected and rejection_count >= 4 and (now - float(last_rejected)) < 300:
                continue

            conf = float(row["confidence"])
            adjusted = max(0.01, conf / (1.0 + 0.30 * rejection_count))
            last_seen = float(row["last_seen"] or now)
            age_days = max(0.0, (now - last_seen) / 86400.0)
            decay = math.pow(0.5, age_days / self.STALE_DECAY_HALF_LIFE_DAYS)
            adjusted = max(0.01, adjusted * decay)
            out.append(
                {
                    "id": str(row["id"]),
                    "before": str(row["error_pattern"]),
                    "after": str(row["intended_pattern"]),
                    "count": int(row["frequency"]),
                    "confidence": adjusted,
                    "age_days": age_days,
                }
            )
        return out

    def record_feedback(self, before: str, after: str, accepted: bool) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, confidence, frequency, rejection_count, success_count, failure_count
            FROM error_patterns
            WHERE lower(error_pattern)=lower(?) AND lower(intended_pattern)=lower(?)
            """,
            (before, after),
        )
        row = cur.fetchone()
        if not row:
            return

        rid = int(row["id"])
        conf = float(row["confidence"])
        freq = int(row["frequency"])
        rejection = int(row["rejection_count"] or 0)
        success_count = int(row["success_count"] or 0)
        failure_count = int(row["failure_count"] or 0)
        now = datetime.now().timestamp()

        if accepted:
            freq += 1
            rejection = max(0, rejection - 1)
            conf = min(1.0, max(conf, freq / 10.0))
            success_count += 1
            cur.execute(
                """
                UPDATE error_patterns
                SET frequency=?, confidence=?, rejection_count=?, success_count=?, last_seen=?
                WHERE id=?
                """,
                (freq, conf, rejection, success_count, now, rid),
            )
            self.conn.commit()
            self._update_lifecycle(
                pattern_id=rid,
                success_count=success_count,
                failure_count=failure_count,
                confidence=conf,
            )
        else:
            rejection += 1
            conf = max(0.01, conf * 0.82)
            failure_count += 1
            cur.execute(
                """
                UPDATE error_patterns
                SET confidence=?, rejection_count=?, failure_count=?, last_rejected=?
                WHERE id=?
                """,
                (conf, rejection, failure_count, now, rid),
            )
            self.conn.commit()
            self._update_lifecycle(
                pattern_id=rid,
                success_count=success_count,
                failure_count=failure_count,
                confidence=conf,
            )

    def record_undo_penalty(self, before: str, after: str) -> None:
        """Apply a stronger negative-learning penalty after explicit undo."""
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, confidence, rejection_count, success_count, failure_count
            FROM error_patterns
            WHERE lower(error_pattern)=lower(?) AND lower(intended_pattern)=lower(?)
            """,
            (before, after),
        )
        row = cur.fetchone()
        if not row:
            return

        rid = int(row["id"])
        conf = float(row["confidence"])
        rejection = int(row["rejection_count"] or 0)
        success_count = int(row["success_count"] or 0)
        failure_count = int(row["failure_count"] or 0)
        now = datetime.now().timestamp()

        # Undo carries stronger negative evidence than a dismissal.
        rejection += 2
        conf = max(0.01, conf * 0.70)
        failure_count += 2
        cur.execute(
            """
            UPDATE error_patterns
            SET confidence=?, rejection_count=?, failure_count=?, last_rejected=?
            WHERE id=?
            """,
            (conf, rejection, failure_count, now, rid),
        )
        self.conn.commit()
        self._update_lifecycle(
            pattern_id=rid,
            success_count=success_count,
            failure_count=failure_count,
            confidence=conf,
        )

    def top_patterns(self, limit: int = 5) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT error_pattern, intended_pattern, frequency, confidence
                 , success_count, failure_count, lifecycle_state
            FROM error_patterns
            ORDER BY frequency DESC, confidence DESC
            LIMIT ?
            """,
            (limit,),
        )
        return [
            {
                "before": r["error_pattern"],
                "after": r["intended_pattern"],
                "count": int(r["frequency"]),
                "confidence": float(r["confidence"]),
                "success_count": int(r["success_count"] or 0),
                "failure_count": int(r["failure_count"] or 0),
                "lifecycle_state": str(r["lifecycle_state"] or "embryonic"),
            }
            for r in cur.fetchall()
        ]

    def get_pattern_state(self, before: str, after: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT
                confidence, frequency, rejection_count,
                success_count, failure_count, lifecycle_state, last_transition
            FROM error_patterns
            WHERE lower(error_pattern)=lower(?) AND lower(intended_pattern)=lower(?)
            """,
            (before, after),
        )
        row = cur.fetchone()
        if not row:
            return None
        return {
            "confidence": float(row["confidence"] or 0.0),
            "frequency": int(row["frequency"] or 0),
            "rejection_count": int(row["rejection_count"] or 0),
            "success_count": int(row["success_count"] or 0),
            "failure_count": int(row["failure_count"] or 0),
            "lifecycle_state": str(row["lifecycle_state"] or "embryonic"),
            "last_transition": row["last_transition"],
        }

    def log_privacy_event(
        self,
        kind: str,
        reason: str,
        app_name: str = "",
        profile: str = "",
        event_type: str = "",
        token_hash: str = "",
        meta: Optional[Dict[str, Any]] = None,
    ) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO privacy_events
            (ts, kind, reason, app_name, profile, event_type, token_hash, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().timestamp(),
                kind,
                reason,
                app_name,
                profile,
                event_type,
                token_hash,
                json.dumps(meta or {}),
            ),
        )
        self.conn.commit()

    def get_privacy_events(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT ts, kind, reason, app_name, profile, event_type, token_hash, meta_json
            FROM privacy_events
            ORDER BY ts DESC
            LIMIT ?
            """,
            (limit,),
        )
        out: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            d = dict(row)
            d["meta"] = json.loads(d.pop("meta_json") or "{}")
            out.append(d)
        return out

    def export_privacy_ledger(self, path: Path) -> None:
        payload = {
            "version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "events": self.get_privacy_events(limit=10000),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def save_proof_report(self, report: Dict[str, Any]) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO proof_reports (ts, report_json)
            VALUES (?, ?)
            """,
            (datetime.now().timestamp(), json.dumps(report)),
        )
        self.conn.commit()

    def latest_proof_report(self) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT ts, report_json
            FROM proof_reports
            ORDER BY id DESC
            LIMIT 1
            """
        )
        row = cur.fetchone()
        if not row:
            return None
        data = json.loads(row["report_json"])
        data["timestamp"] = row["ts"]
        return data

    def list_proof_reports(self, limit: int = 10) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT ts, report_json
            FROM proof_reports
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
        out: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            data = json.loads(row["report_json"])
            data["timestamp"] = row["ts"]
            out.append(data)
        return out

    def delete_all(self) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM error_patterns")
        cur.execute("DELETE FROM privacy_events")
        cur.execute("DELETE FROM proof_reports")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
