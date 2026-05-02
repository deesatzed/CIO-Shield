from __future__ import annotations

from datetime import datetime
from hashlib import sha256
import math
import json
from pathlib import Path
import sqlite3
from typing import Any, Dict, List, Optional

from cognitiveio.security.redaction import redact_payload

class LocalStore:
    """Local-only SQLite store with privacy-first minimal schema."""
    STALE_DECAY_HALF_LIFE_DAYS = 45.0

    def __init__(
        self,
        db_path: Path,
        *,
        encryption_mode: str = "optional",
        db_key: Optional[str] = None,
    ):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = self._connect(
            str(self.db_path),
            encryption_mode=encryption_mode,
            db_key=db_key,
        )
        self.conn.row_factory = sqlite3.Row
        self._init_schema()
        self._ensure_error_pattern_columns()

    @staticmethod
    def _connect(db_uri: str, *, encryption_mode: str, db_key: Optional[str]):
        mode = (encryption_mode or "optional").lower()
        if mode not in {"off", "optional", "required"}:
            mode = "optional"

        if mode == "off":
            return sqlite3.connect(db_uri)

        try:
            import sqlcipher3
        except Exception:
            if mode == "required":
                raise RuntimeError("Database encryption required but sqlcipher3 is unavailable.")
            return sqlite3.connect(db_uri)

        if not db_key:
            if mode == "required":
                raise RuntimeError("Database encryption required but no key was provided.")
            return sqlite3.connect(db_uri)

        conn = sqlcipher3.connect(db_uri)
        escaped = db_key.replace("'", "''")
        conn.execute(f"PRAGMA key='{escaped}'")
        return conn

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

            CREATE TABLE IF NOT EXISTS secret_access_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ts REAL NOT NULL,
                alias TEXT NOT NULL,
                provider TEXT NOT NULL,
                status TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS secret_alias_registry (
                alias TEXT PRIMARY KEY,
                description TEXT DEFAULT '',
                usage_count INTEGER DEFAULT 0,
                first_seen REAL NOT NULL,
                last_seen REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS phrase_patterns (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                phrase_before TEXT NOT NULL,
                phrase_after TEXT NOT NULL,
                profile TEXT DEFAULT '',
                confidence REAL DEFAULT 0.1,
                frequency INTEGER DEFAULT 1,
                UNIQUE(phrase_before, phrase_after, profile)
            );

            CREATE TABLE IF NOT EXISTS concept_lexicon (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                canonical TEXT NOT NULL,
                synonym TEXT NOT NULL,
                domain TEXT DEFAULT '',
                profile TEXT DEFAULT '',
                confidence REAL DEFAULT 0.88,
                UNIQUE(canonical, synonym, profile)
            );

            CREATE INDEX IF NOT EXISTS idx_patterns_lookup ON error_patterns(error_pattern, confidence DESC);
            CREATE INDEX IF NOT EXISTS idx_privacy_ts ON privacy_events(ts DESC);
            CREATE INDEX IF NOT EXISTS idx_secret_access_ts ON secret_access_events(ts DESC);
            CREATE INDEX IF NOT EXISTS idx_secret_alias_last_seen ON secret_alias_registry(last_seen DESC);
            CREATE INDEX IF NOT EXISTS idx_phrase_lookup ON phrase_patterns(phrase_before, profile, confidence DESC);
            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT UNIQUE NOT NULL,
                start_ts REAL NOT NULL,
                end_ts REAL,
                warmth_state TEXT DEFAULT 'embryonic',
                suggestions_shown INTEGER DEFAULT 0,
                suggestions_accepted INTEGER DEFAULT 0,
                suggestions_dismissed INTEGER DEFAULT 0,
                undone INTEGER DEFAULT 0,
                blocked INTEGER DEFAULT 0,
                dominant_app TEXT DEFAULT '',
                dominant_profile TEXT DEFAULT '',
                meta_json TEXT DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_sessions_start ON sessions(start_ts DESC);
            CREATE INDEX IF NOT EXISTS idx_concept_lookup ON concept_lexicon(synonym, profile, confidence DESC);
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

    def log_secret_access(self, alias: str, provider: str, status: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO secret_access_events (ts, alias, provider, status)
            VALUES (?, ?, ?, ?)
            """,
            (datetime.now().timestamp(), alias, provider, status),
        )
        self.conn.commit()

    def register_secret_alias(self, alias: str, description: str = "") -> None:
        now = datetime.now().timestamp()
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO secret_alias_registry (alias, description, usage_count, first_seen, last_seen)
            VALUES (?, ?, 1, ?, ?)
            ON CONFLICT(alias) DO UPDATE SET
                usage_count=usage_count + 1,
                description=CASE
                    WHEN excluded.description != '' THEN excluded.description
                    ELSE secret_alias_registry.description
                END,
                last_seen=excluded.last_seen
            """,
            (alias, description, now, now),
        )
        self.conn.commit()

    def list_secret_aliases(self, limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT alias, description, usage_count, first_seen, last_seen
            FROM secret_alias_registry
            ORDER BY last_seen DESC
            LIMIT ?
            """,
            (limit,),
        )
        out: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            out.append(
                {
                    "alias": str(row["alias"]),
                    "description": str(row["description"] or ""),
                    "usage_count": int(row["usage_count"] or 0),
                    "first_seen": float(row["first_seen"] or 0.0),
                    "last_seen": float(row["last_seen"] or 0.0),
                }
            )
        return out

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

    def upsert_phrase_pattern(
        self,
        phrase_before: str,
        phrase_after: str,
        profile: str = "",
        confidence: float = 0.1,
    ) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, frequency, confidence
            FROM phrase_patterns
            WHERE lower(phrase_before)=lower(?) AND lower(phrase_after)=lower(?) AND profile=?
            """,
            (phrase_before, phrase_after, profile),
        )
        row = cur.fetchone()
        if row:
            freq = int(row["frequency"] or 0) + 1
            conf = min(1.0, max(float(row["confidence"] or 0.1), confidence, freq / 10.0))
            cur.execute(
                """
                UPDATE phrase_patterns
                SET frequency=?, confidence=?
                WHERE id=?
                """,
                (freq, conf, int(row["id"])),
            )
        else:
            cur.execute(
                """
                INSERT INTO phrase_patterns
                (phrase_before, phrase_after, profile, confidence, frequency)
                VALUES (?, ?, ?, ?, ?)
                """,
                (phrase_before, phrase_after, profile, confidence, 1),
            )
        self.conn.commit()

    def get_phrase_candidates(self, phrase: str, profile: str = "", limit: int = 5) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, phrase_before, phrase_after, confidence, frequency, profile
            FROM phrase_patterns
            WHERE lower(phrase_before)=lower(?)
              AND (profile='' OR profile=?)
            ORDER BY confidence DESC, frequency DESC
            LIMIT ?
            """,
            (phrase, profile, limit),
        )
        out: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            out.append(
                {
                    "id": f"phrase:{row['id']}",
                    "before": str(row["phrase_before"]),
                    "after": str(row["phrase_after"]),
                    "count": int(row["frequency"] or 1),
                    "confidence": float(row["confidence"] or 0.1),
                }
            )
        return out

    def list_phrase_patterns(self, profile: str = "", limit: int = 100) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        if profile:
            cur.execute(
                """
                SELECT id, phrase_before, phrase_after, profile, confidence, frequency
                FROM phrase_patterns
                WHERE profile=?
                ORDER BY profile ASC, phrase_before ASC, confidence DESC
                LIMIT ?
                """,
                (profile, limit),
            )
        else:
            cur.execute(
                """
                SELECT id, phrase_before, phrase_after, profile, confidence, frequency
                FROM phrase_patterns
                ORDER BY profile ASC, phrase_before ASC, confidence DESC
                LIMIT ?
                """,
                (limit,),
            )

        out: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            out.append(
                {
                    "id": int(row["id"]),
                    "before": str(row["phrase_before"]),
                    "after": str(row["phrase_after"]),
                    "profile": str(row["profile"] or ""),
                    "confidence": float(row["confidence"] or 0.1),
                    "frequency": int(row["frequency"] or 1),
                }
            )
        return out

    def delete_phrase_pattern(self, phrase_before: str, profile: str = "") -> int:
        cur = self.conn.cursor()
        if profile:
            cur.execute(
                """
                DELETE FROM phrase_patterns
                WHERE lower(phrase_before)=lower(?) AND profile=?
                """,
                (phrase_before, profile),
            )
        else:
            cur.execute(
                """
                DELETE FROM phrase_patterns
                WHERE lower(phrase_before)=lower(?)
                """,
                (phrase_before,),
            )
        self.conn.commit()
        return int(cur.rowcount or 0)

    def upsert_concept(
        self,
        canonical: str,
        synonym: str,
        domain: str = "",
        profile: str = "",
        confidence: float = 0.88,
    ) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO concept_lexicon (canonical, synonym, domain, profile, confidence)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(canonical, synonym, profile)
            DO UPDATE SET confidence=excluded.confidence
            """,
            (canonical, synonym, domain, profile, confidence),
        )
        self.conn.commit()

    def get_concept_candidates(self, token: str, profile: str = "", limit: int = 5) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT id, canonical, synonym, confidence
            FROM concept_lexicon
            WHERE lower(synonym)=lower(?)
              AND (profile='' OR profile=?)
            ORDER BY confidence DESC
            LIMIT ?
            """,
            (token, profile, limit),
        )
        out: List[Dict[str, Any]] = []
        for row in cur.fetchall():
            out.append(
                {
                    "id": f"concept:{row['id']}",
                    "before": str(row["synonym"]),
                    "after": str(row["canonical"]),
                    "count": 1,
                    "confidence": float(row["confidence"] or 0.88),
                }
            )
        return out

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
        safe_reason = str(redact_payload(reason))
        safe_app_name = str(redact_payload(app_name))
        safe_profile = str(redact_payload(profile))
        safe_event_type = str(redact_payload(event_type))
        safe_token_hash = str(redact_payload(token_hash))
        safe_meta = redact_payload(meta or {})

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
                safe_reason,
                safe_app_name,
                safe_profile,
                safe_event_type,
                safe_token_hash,
                json.dumps(safe_meta),
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
            "events": redact_payload(self.get_privacy_events(limit=10000)),
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def save_proof_report(self, report: Dict[str, Any]) -> None:
        safe_report = redact_payload(report)
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT INTO proof_reports (ts, report_json)
            VALUES (?, ?)
            """,
            (datetime.now().timestamp(), json.dumps(safe_report)),
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

    # ------------------------------------------------------------------
    # Compliance & retention (corporate shield)
    # ------------------------------------------------------------------

    def prune_by_retention(self, days: int) -> int:
        """Delete privacy events and proof reports older than *days*.

        Returns the total number of rows deleted across all pruned tables.
        """
        if days < 1:
            return 0
        cutoff = datetime.now().timestamp() - (days * 86400.0)
        cur = self.conn.cursor()
        total = 0

        cur.execute("DELETE FROM privacy_events WHERE ts < ?", (cutoff,))
        total += cur.rowcount or 0

        cur.execute("DELETE FROM proof_reports WHERE ts < ?", (cutoff,))
        total += cur.rowcount or 0

        cur.execute("DELETE FROM secret_access_events WHERE ts < ?", (cutoff,))
        total += cur.rowcount or 0

        self.conn.commit()
        return total

    def export_compliance_report(
        self,
        output_path: Path,
        *,
        include_pattern_stats: bool = True,
        include_secret_registry: bool = True,
        include_block_reasons: bool = True,
    ) -> Dict[str, Any]:
        """Generate a redacted compliance report (no secret values, ever).

        The report contains only categorical/aggregate data suitable for
        corporate audit. Written to *output_path* as JSON.
        """
        import hashlib
        import platform

        report: Dict[str, Any] = {
            "schema_version": 1,
            "generated_at": datetime.now().isoformat(),
            "machine_id_hash": hashlib.sha256(
                platform.node().encode("utf-8")
            ).hexdigest()[:16],
        }

        # Block reason summary.
        if include_block_reasons:
            cur = self.conn.cursor()
            cur.execute(
                """
                SELECT reason, COUNT(*) AS cnt
                FROM privacy_events
                WHERE kind = 'blocked'
                GROUP BY reason
                ORDER BY cnt DESC
                """
            )
            report["block_reasons"] = [
                {"reason": str(r["reason"]), "count": int(r["cnt"])}
                for r in cur.fetchall()
            ]

        # Pattern lifecycle distribution.
        if include_pattern_stats:
            cur = self.conn.cursor()
            cur.execute(
                """
                SELECT lifecycle_state, COUNT(*) AS cnt
                FROM error_patterns
                GROUP BY lifecycle_state
                """
            )
            report["pattern_lifecycle"] = {
                str(r["lifecycle_state"] or "embryonic"): int(r["cnt"])
                for r in cur.fetchall()
            }

        # Secret alias names + usage counts (NEVER values).
        if include_secret_registry:
            report["secret_aliases"] = [
                {"alias": a["alias"], "usage_count": a["usage_count"]}
                for a in self.list_secret_aliases(limit=1000)
            ]

        # Accept / dismiss / undo rates from latest proof report.
        latest = self.latest_proof_report()
        if latest:
            report["rates"] = {
                "accept_rate": float(latest.get("accept_rate", 0.0)),
                "dismiss_rate": float(latest.get("dismiss_rate", 0.0)),
                "undo_rate": float(latest.get("undo_rate", 0.0)),
            }

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            json.dumps(report, indent=2), encoding="utf-8"
        )
        return report

    # ── Session management ──────────────────────────────────────────

    WARMUP_SUGGESTION_THRESHOLD = 15
    WARMUP_ACCEPT_RATE_MIN = 0.35

    @staticmethod
    def derive_warmth_state(
        suggestions_shown: int, suggestions_accepted: int
    ) -> str:
        """Derive warmth state from session metrics.

        - embryonic: fewer than WARMUP_SUGGESTION_THRESHOLD suggestions
        - learning: threshold met but accept rate below WARMUP_ACCEPT_RATE_MIN
        - mature: threshold met and accept rate >= WARMUP_ACCEPT_RATE_MIN
        """
        if suggestions_shown < LocalStore.WARMUP_SUGGESTION_THRESHOLD:
            return "embryonic"
        accept_rate = suggestions_accepted / max(suggestions_shown, 1)
        if accept_rate >= LocalStore.WARMUP_ACCEPT_RATE_MIN:
            return "mature"
        return "learning"

    def start_session(self, session_id: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO sessions (session_id, start_ts)
            VALUES (?, ?)
            """,
            (session_id, datetime.now().timestamp()),
        )
        self.conn.commit()

    def update_session(
        self,
        session_id: str,
        *,
        suggestions_shown: int = 0,
        suggestions_accepted: int = 0,
        suggestions_dismissed: int = 0,
        undone: int = 0,
        blocked: int = 0,
        dominant_app: str = "",
        dominant_profile: str = "",
    ) -> None:
        warmth = self.derive_warmth_state(suggestions_shown, suggestions_accepted)
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE sessions
            SET suggestions_shown=?, suggestions_accepted=?,
                suggestions_dismissed=?, undone=?, blocked=?,
                dominant_app=?, dominant_profile=?,
                warmth_state=?
            WHERE session_id=?
            """,
            (
                suggestions_shown, suggestions_accepted,
                suggestions_dismissed, undone, blocked,
                dominant_app, dominant_profile,
                warmth, session_id,
            ),
        )
        self.conn.commit()

    def end_session(self, session_id: str) -> None:
        cur = self.conn.cursor()
        cur.execute(
            "UPDATE sessions SET end_ts=? WHERE session_id=?",
            (datetime.now().timestamp(), session_id),
        )
        self.conn.commit()

    def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM sessions WHERE session_id=?", (session_id,))
        row = cur.fetchone()
        if not row:
            return None
        return dict(row)

    def list_sessions(self, limit: int = 20) -> List[Dict[str, Any]]:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT * FROM sessions ORDER BY start_ts DESC LIMIT ?", (limit,)
        )
        return [dict(r) for r in cur.fetchall()]

    def session_count(self) -> int:
        cur = self.conn.cursor()
        cur.execute("SELECT COUNT(*) FROM sessions")
        return int(cur.fetchone()[0])

    def overall_warmth_state(self) -> str:
        """Derive the overall warmth state across all sessions.

        Considers the last 5 sessions to determine the user's overall
        comfort level with the system.
        """
        recent = self.list_sessions(limit=5)
        if not recent:
            return "embryonic"
        total_shown = sum(s.get("suggestions_shown", 0) for s in recent)
        total_accepted = sum(s.get("suggestions_accepted", 0) for s in recent)
        return self.derive_warmth_state(total_shown, total_accepted)

    def delete_all(self) -> None:
        cur = self.conn.cursor()
        cur.execute("DELETE FROM error_patterns")
        cur.execute("DELETE FROM privacy_events")
        cur.execute("DELETE FROM proof_reports")
        cur.execute("DELETE FROM secret_access_events")
        cur.execute("DELETE FROM secret_alias_registry")
        cur.execute("DELETE FROM phrase_patterns")
        cur.execute("DELETE FROM concept_lexicon")
        cur.execute("DELETE FROM sessions")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()
