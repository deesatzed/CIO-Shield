from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional


class LocalStore:
    """Local-only SQLite store with privacy-first minimal schema."""

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.db_path))
        self.conn.row_factory = sqlite3.Row
        self._init_schema()

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
                (error_pattern, intended_pattern, confidence, frequency, rejection_count, last_seen)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (error, intended, 0.1, 1, 0, now),
            )
        self.conn.commit()

    def get_candidates_for_token(self, token: str, limit: int = 5) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, error_pattern, intended_pattern, confidence, frequency, rejection_count, last_rejected
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
            if last_rejected and rejection_count >= 2 and (now - float(last_rejected)) < 300:
                continue

            conf = float(row["confidence"])
            adjusted = max(0.01, conf / (1.0 + 0.30 * rejection_count))
            out.append(
                {
                    "id": str(row["id"]),
                    "before": str(row["error_pattern"]),
                    "after": str(row["intended_pattern"]),
                    "count": int(row["frequency"]),
                    "confidence": adjusted,
                }
            )
        return out

    def record_feedback(self, before: str, after: str, accepted: bool) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, confidence, frequency, rejection_count
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
        now = datetime.now().timestamp()

        if accepted:
            freq += 1
            rejection = max(0, rejection - 1)
            conf = min(1.0, max(conf, freq / 10.0))
            cur.execute(
                """
                UPDATE error_patterns
                SET frequency=?, confidence=?, rejection_count=?, last_seen=?
                WHERE id=?
                """,
                (freq, conf, rejection, now, rid),
            )
        else:
            rejection += 1
            conf = max(0.01, conf * 0.82)
            cur.execute(
                """
                UPDATE error_patterns
                SET confidence=?, rejection_count=?, last_rejected=?
                WHERE id=?
                """,
                (conf, rejection, now, rid),
            )
        self.conn.commit()

    def top_patterns(self, limit: int = 5) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT error_pattern, intended_pattern, frequency, confidence
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
            }
            for r in cur.fetchall()
        ]

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

    def delete_all(self) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM error_patterns")
        cur.execute("DELETE FROM privacy_events")
        cur.execute("DELETE FROM proof_reports")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
