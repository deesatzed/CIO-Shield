from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from cognitiveio.config import Settings
from cognitiveio.context.profiles import AppContext, classify_profile
from cognitiveio.core.decision_engine import BudgetState, Candidate, decide
from cognitiveio.core.undo_stack import UndoStack
from cognitiveio.evidence.metrics import Metrics
from cognitiveio.evidence.report_generator import ProofReport, build_report
from cognitiveio.memory.local_store import LocalStore
from cognitiveio.policy.risk_scoring import RiskFlags


@dataclass
class PendingSuggestion:
    app_name: str
    app_bundle_id: Optional[str]
    app_pid: Optional[int]
    token: str
    replacement: str
    candidate_id: str
    confidence: float
    reason_tag: str
    boundary: str


@dataclass
class RuntimeEvent:
    kind: str  # boundary | accept | dismiss | panic | undo
    app_name: str = ""
    app_bundle_id: Optional[str] = None
    app_pid: Optional[int] = None
    token: str = ""
    boundary: str = " "
    idle_ms: int = 0
    typing_fast: bool = False
    flags: Optional[RiskFlags] = None


@dataclass
class RuntimeResult:
    action: str
    message: str
    protected_mode: bool
    paused: bool


class AppRuntime:
    """Deterministic runtime state machine for suggest-only intervention flow."""

    def __init__(self, settings: Settings, store: LocalStore):
        self.settings = settings
        self.store = store

        self.metrics = Metrics()
        self.undo_stack = UndoStack()

        self.pending: Optional[PendingSuggestion] = None
        self.paused = False
        self.protected_mode = False

        self._suggestion_ts: Deque[float] = deque(maxlen=1024)
        self._dismissal_streak = 0
        self._cooldown_until_ts = 0.0
        self._negative_event_ts: Deque[float] = deque(maxlen=512)
        self._trust_pause_until_ts = 0.0

    @staticmethod
    def _merge_candidates(*candidate_groups: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        merged: Dict[tuple[str, str], Dict[str, Any]] = {}
        for group in candidate_groups:
            for cand in group:
                before = str(cand.get("before", ""))
                after = str(cand.get("after", ""))
                key = (before.lower(), after.lower())
                existing = merged.get(key)
                if existing is None:
                    merged[key] = dict(cand)
                    continue
                if float(cand.get("confidence", 0.0)) > float(existing.get("confidence", 0.0)):
                    existing["confidence"] = cand.get("confidence", existing.get("confidence"))
                    existing["id"] = cand.get("id", existing.get("id"))
                existing["count"] = max(
                    int(existing.get("count", 0)),
                    int(cand.get("count", 0)),
                )
        return list(merged.values())

    @staticmethod
    def _now_ts() -> float:
        return datetime.now().timestamp()

    @staticmethod
    def _is_boundary(ch: str) -> bool:
        return ch in {" ", "\n", ".", "!", "?", ",", ";", ":"}

    @classmethod
    def _strip_shared_boundary(cls, before: str, after: str) -> tuple[str, str]:
        if before and after and before[-1] == after[-1] and cls._is_boundary(before[-1]):
            return before[:-1], after[:-1]
        return before.rstrip(), after.rstrip()

    def _recent_suggestions(self, now_ts: float) -> int:
        while self._suggestion_ts and (now_ts - self._suggestion_ts[0]) > 60.0:
            self._suggestion_ts.popleft()
        return len(self._suggestion_ts)

    def _result(self, action: str, message: str) -> RuntimeResult:
        return RuntimeResult(
            action=action,
            message=message,
            protected_mode=self.protected_mode,
            paused=self.paused,
        )

    def _record_negative_signal(self, now_ts: Optional[float] = None) -> None:
        now = now_ts if now_ts is not None else self._now_ts()
        self._negative_event_ts.append(now)
        window = float(self.settings.trust_circuit_window_seconds)
        while self._negative_event_ts and (now - self._negative_event_ts[0]) > window:
            self._negative_event_ts.popleft()

        if len(self._negative_event_ts) >= self.settings.trust_circuit_negative_events:
            cooldown = float(self.settings.trust_circuit_cooldown_seconds)
            self._trust_pause_until_ts = max(self._trust_pause_until_ts, now + cooldown)

    def _set_protected(self, on: bool, reason: str = "") -> None:
        self.protected_mode = on
        if on:
            self.metrics.inc("blocked", 1)
            self.store.log_privacy_event(kind="blocked", reason=reason or "protected_mode")

    def toggle_panic(self) -> RuntimeResult:
        self.paused = not self.paused
        if self.paused:
            self.store.log_privacy_event(kind="blocked", reason="paused")
            return self._result("do_nothing", "Paused - no capture, no suggestions.")
        return self._result("do_nothing", "Resumed - suggestions enabled.")

    def accept_pending(self) -> RuntimeResult:
        if not self.pending:
            return self._result("do_nothing", "No suggestion to accept.")

        p = self.pending
        self.metrics.inc("suggestion_accepted", 1)
        self.store.record_feedback(p.token, p.replacement, accepted=True)
        self.undo_stack.push(
            app_name=p.app_name,
            before=f"{p.token}{p.boundary}",
            after=f"{p.replacement}{p.boundary}",
            app_bundle_id=p.app_bundle_id,
            app_pid=p.app_pid,
            cursor_pos=len(p.replacement) + len(p.boundary),
            reason_tag=p.reason_tag,
        )
        self.store.log_privacy_event(
            kind="stored",
            reason="stored",
            app_name=p.app_name,
            event_type="suggestion_accepted",
            token_hash=self.store.hash_token(p.token),
            meta={"candidate_id": p.candidate_id, "confidence": p.confidence},
        )
        self.pending = None
        self._dismissal_streak = 0
        self._negative_event_ts.clear()
        self._trust_pause_until_ts = 0.0
        return self._result("accept", f"Accepted: {p.token} -> {p.replacement}")

    def dismiss_pending(self) -> RuntimeResult:
        if not self.pending:
            return self._result("do_nothing", "No suggestion to dismiss.")

        p = self.pending
        self.metrics.inc("suggestion_dismissed", 1)
        self.store.record_feedback(p.token, p.replacement, accepted=False)
        self.store.log_privacy_event(
            kind="stored",
            reason="stored",
            app_name=p.app_name,
            event_type="suggestion_dismissed",
            token_hash=self.store.hash_token(p.token),
            meta={"candidate_id": p.candidate_id},
        )

        self.pending = None
        self._dismissal_streak += 1
        self._record_negative_signal()
        if self._dismissal_streak >= self.settings.dismissals_before_cooldown:
            self._cooldown_until_ts = self._now_ts() + float(self.settings.cooldown_seconds)
        return self._result("dismiss", "Suggestion dismissed.")

    def undo_last(self) -> RuntimeResult:
        rec = self.undo_stack.pop()
        if not rec:
            return self._result("do_nothing", "Nothing to undo.")

        before_token, after_token = self._strip_shared_boundary(rec.before, rec.after)
        if before_token and after_token:
            self.store.record_undo_penalty(before_token, after_token)

        self.metrics.inc("undone", 1)
        self._record_negative_signal()
        self.store.log_privacy_event(
            kind="stored",
            reason="stored",
            app_name=rec.app_name,
            event_type="undo",
            meta={
                "undo_record_id": rec.id,
                "before_hash": self.store.hash_token(rec.before),
                "after_hash": self.store.hash_token(rec.after),
            },
        )
        return self._result("undo", f"Undo restored: {rec.after} -> {rec.before}")

    async def process_boundary_event(self, event: RuntimeEvent) -> RuntimeResult:
        now = self._now_ts()
        if self.paused:
            self.metrics.inc("blocked", 1)
            self.store.log_privacy_event(kind="blocked", reason="paused", app_name=event.app_name)
            return self._result("do_nothing", "Paused - ignored input.")

        if now < self._trust_pause_until_ts:
            self.metrics.inc("blocked", 1)
            self.store.log_privacy_event(
                kind="blocked",
                reason="trust_circuit_breaker",
                app_name=event.app_name,
            )
            return self._result("do_nothing", "Trust cooldown active - suggestions temporarily paused.")

        if not self._is_boundary(event.boundary):
            return self._result("do_nothing", "No boundary trigger.")

        if event.idle_ms < self.settings.idle_pause_ms:
            return self._result("do_nothing", "Idle threshold not met.")

        flags = event.flags or RiskFlags()
        if (
            flags.password_field
            or flags.blacklisted_app
            or flags.user_excluded
            or (flags.detector_uncertain and self.settings.protected_mode_blocks_all)
        ):
            self._set_protected(True, reason="password_or_excluded")
            return self._result("do_nothing", "Protected Mode Active - no capture, no suggestions.")

        self.protected_mode = False

        ctx = AppContext(app_name=event.app_name)
        profile = classify_profile(ctx)

        typo_candidates = self.store.get_candidates_for_token(event.token)
        phrase_candidates = self.store.get_phrase_candidates(event.token, profile=profile)
        concept_candidates = self.store.get_concept_candidates(event.token, profile=profile)
        candidates_raw = self._merge_candidates(typo_candidates, phrase_candidates, concept_candidates)
        if not candidates_raw:
            return self._result("do_nothing", "No local candidates.")

        candidates = [
            Candidate(
                id=str(c["id"]),
                before=str(c["before"]),
                after=str(c["after"]),
                count=int(c["count"]),
                confidence=float(c["confidence"]),
            )
            for c in candidates_raw
        ]

        budget = BudgetState(
            suggestions_shown_recent=self._recent_suggestions(now),
            recent_dismissals=self._dismissal_streak,
            typing_fast=event.typing_fast,
            cooldown_until_ts=self._cooldown_until_ts,
            now_ts=now,
        )

        decision = await decide(
            ctx=ctx,
            flags=flags,
            candidates=candidates,
            context_window={"left": "", "token": event.token, "right": ""},
            metrics=self.metrics,
            budget=budget,
            settings=self.settings,
            user_prefs={},
        )

        if decision.action == "do_nothing":
            blocked_reasons = {"candidate_conflict", "unknown_profile"}
            if decision.reason_tag.startswith("profile_block:"):
                blocked_reasons.add(decision.reason_tag)
            if decision.reason_tag.startswith("blocked") or decision.reason_tag in blocked_reasons:
                self.store.log_privacy_event(
                    kind="blocked",
                    reason=decision.reason_tag,
                    app_name=event.app_name,
                    profile=profile,
                    token_hash=self.store.hash_token(event.token),
                )
            return self._result("do_nothing", f"No intervention ({decision.reason_tag}).")

        if not decision.replacement or not decision.chosen_candidate_id:
            return self._result("do_nothing", "No replacement selected.")

        self._suggestion_ts.append(now)
        self.pending = PendingSuggestion(
            app_name=event.app_name,
            app_bundle_id=event.app_bundle_id,
            app_pid=event.app_pid,
            token=event.token,
            replacement=decision.replacement,
            candidate_id=decision.chosen_candidate_id,
            confidence=decision.confidence,
            reason_tag=decision.reason_tag,
            boundary=event.boundary,
        )

        self.store.log_privacy_event(
            kind="stored",
            reason="stored",
            app_name=event.app_name,
            profile=profile,
            event_type="suggestion_shown",
            token_hash=self.store.hash_token(event.token),
            meta={"candidate_id": decision.chosen_candidate_id, "reason": decision.reason_tag},
        )

        if decision.action == "auto_apply":
            self.metrics.inc("auto_applied", 1)
            return self.accept_pending()

        return self._result(
            "suggest",
            f"Ghost suggestion: {event.token} -> {decision.replacement} [Tab accept | Esc dismiss]",
        )

    async def process_event(self, event: RuntimeEvent) -> RuntimeResult:
        if event.kind == "panic":
            return self.toggle_panic()
        if event.kind == "accept":
            return self.accept_pending()
        if event.kind == "dismiss":
            return self.dismiss_pending()
        if event.kind == "undo":
            return self.undo_last()
        if event.kind == "boundary":
            return await self.process_boundary_event(event)
        return self._result("do_nothing", "Unknown event kind.")

    def build_report(self) -> ProofReport:
        events = self.store.get_privacy_events(limit=1000)
        block_counts: Dict[str, int] = {}
        for e in events:
            if e.get("kind") == "blocked":
                reason = str(e.get("reason") or "blocked")
                block_counts[reason] = block_counts.get(reason, 0) + 1

        top_block_reasons = [
            {"reason": reason, "count": count}
            for reason, count in sorted(block_counts.items(), key=lambda kv: kv[1], reverse=True)
        ]

        report = build_report(
            self.metrics,
            top_patterns=self.store.top_patterns(limit=5),
            top_block_reasons=top_block_reasons,
        )
        return report
