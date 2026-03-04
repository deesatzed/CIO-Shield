"""Phase 2b: Tests for core/undo_stack.py."""
from cognitiveio.core.undo_stack import UndoStack


class TestUndoStackPushPop:
    def test_push_returns_uuid(self):
        stack = UndoStack()
        uid = stack.push(app_name="Mail", before="teh", after="the")
        assert isinstance(uid, str)
        assert len(uid) == 36  # UUID format

    def test_pop_returns_lifo_order(self):
        stack = UndoStack()
        stack.push(app_name="Mail", before="a", after="b")
        stack.push(app_name="Mail", before="c", after="d")
        rec = stack.pop()
        assert rec is not None
        assert rec.before == "c"
        assert rec.after == "d"

    def test_peek_does_not_remove(self):
        stack = UndoStack()
        stack.push(app_name="Mail", before="x", after="y")
        r1 = stack.peek()
        r2 = stack.peek()
        assert r1 is not None and r2 is not None
        assert r1.id == r2.id
        assert stack.can_undo() is True

    def test_can_undo_true_when_has_items(self):
        stack = UndoStack()
        stack.push(app_name="Mail", before="a", after="b")
        assert stack.can_undo() is True

    def test_can_undo_false_when_empty(self):
        stack = UndoStack()
        assert stack.can_undo() is False

    def test_pop_empty_returns_none(self):
        stack = UndoStack()
        assert stack.pop() is None

    def test_peek_empty_returns_none(self):
        stack = UndoStack()
        assert stack.peek() is None


class TestUndoStackOverflow:
    def test_max_size_evicts_oldest(self):
        stack = UndoStack(max_size=3)
        stack.push(app_name="Mail", before="first", after="a")
        stack.push(app_name="Mail", before="second", after="b")
        stack.push(app_name="Mail", before="third", after="c")
        stack.push(app_name="Mail", before="fourth", after="d")
        # "first" should be evicted
        assert stack.can_undo() is True
        items = []
        while stack.can_undo():
            items.append(stack.pop())
        befores = [r.before for r in items]
        assert "first" not in befores
        assert len(items) == 3


class TestUndoRecordMetadata:
    def test_stores_app_metadata(self):
        stack = UndoStack()
        stack.push(
            app_name="Mail",
            before="teh",
            after="the",
            app_bundle_id="com.apple.mail",
            app_pid=42,
            cursor_pos=5,
            reason_tag="high_confidence",
        )
        rec = stack.peek()
        assert rec is not None
        assert rec.app_name == "Mail"
        assert rec.app_bundle_id == "com.apple.mail"
        assert rec.app_pid == 42
        assert rec.cursor_pos == 5
        assert rec.reason_tag == "high_confidence"
