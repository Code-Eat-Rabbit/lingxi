"""
测试 HistoryStore — SQLite 历史记录持久化与线程安全。
"""

from __future__ import annotations

import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from lingxi.data.history_store import HistoryStore


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

@pytest.fixture
def temp_db_path() -> str:
    """在临时目录中创建一个独立 SQLite 数据库路径。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield str(Path(tmpdir) / "test_history.db")


def _make_recording(**overrides) -> dict:
    """快速创建一个测试用录音字典。"""
    ts = datetime.now(timezone.utc).isoformat()
    rec = {
        "id": str(uuid.uuid4()),
        "timestamp": ts,
        "original_text": "你好世界",
        "styled_text": "你好世界～",
        "style_name": "casual",
        "emotion": "neutral",
        "asr_engine": "faster_whisper",
        "llm_provider": "openai",
        "duration_ms": 1200,
        "success": 1,
    }
    rec.update(overrides)
    return rec


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestTableCreation:
    """验证表结构创建。"""

    def test_table_exists_after_init(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)

        conn = store._get_conn()
        row = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='recordings'"
        ).fetchone()
        assert row is not None
        assert row["name"] == "recordings"

    def test_count_zero_on_empty(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        assert store.count() == 0

    def test_idempotent_init(self, temp_db_path):
        """多次初始化不会报错。"""
        HistoryStore(custom_path=temp_db_path)
        HistoryStore(custom_path=temp_db_path)
        # 不抛出异常即通过


class TestAddAndCount:
    """添加记录与计数。"""

    def test_add_one_increments_count(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        assert store.count() == 0

        store.add(_make_recording())
        assert store.count() == 1

    def test_add_multiple(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        for _ in range(10):
            store.add(_make_recording())
        assert store.count() == 10

    def test_upsert_on_duplicate_id(self, temp_db_path):
        """相同 id 应执行 UPSERT（INSERT OR REPLACE）。"""
        store = HistoryStore(custom_path=temp_db_path)
        rec_id = "fixed-id-001"
        store.add(_make_recording(id=rec_id, original_text="first"))
        store.add(_make_recording(id=rec_id, original_text="second"))
        assert store.count() == 1

        # 验证为最新的值
        recent = store.get_recent(1)
        assert recent[0]["original_text"] == "second"


class TestGetRecent:
    """get_recent 测试。"""

    def test_get_recent_returns_correct_number(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        for i in range(10):
            store.add(_make_recording(original_text=f"test_{i:03d}"))

        results = store.get_recent(3)
        assert len(results) == 3

    def test_get_recent_order_desc(self, temp_db_path):
        """最近的在前面。"""
        store = HistoryStore(custom_path=temp_db_path)
        rec1 = _make_recording(timestamp="2026-01-01T00:00:00", original_text="old")
        rec2 = _make_recording(timestamp="2026-01-02T00:00:00", original_text="new")
        store.add(rec1)
        store.add(rec2)

        results = store.get_recent(2)
        assert results[0]["original_text"] == "new"
        assert results[1]["original_text"] == "old"

    def test_get_recent_default_limit(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        for _ in range(60):
            store.add(_make_recording())

        results = store.get_recent()  # 默认 50
        assert len(results) == 50

    def test_get_recent_empty_db(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        assert store.get_recent() == []


class TestSearch:
    """search 模糊搜索。"""

    def test_search_finds_in_original_text(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        store.add(_make_recording(original_text="今天天气真好"))
        store.add(_make_recording(original_text="明天可能会下雨"))

        results = store.search("天气")
        assert len(results) == 1
        assert "天气" in results[0]["original_text"]

    def test_search_finds_in_styled_text(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        store.add(_make_recording(
            original_text="hello",
            styled_text="您好～",
        ))

        results = store.search("您好")
        assert len(results) == 1
        assert results[0]["styled_text"] == "您好～"

    def test_search_no_match(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        store.add(_make_recording(original_text="abc"))

        results = store.search("xyz")
        assert results == []

    def test_search_respects_limit(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        for _ in range(10):
            store.add(_make_recording(original_text="包含关键词的文本"))

        results = store.search("关键词", limit=3)
        assert len(results) == 3


class TestClear:
    """clear 清空。"""

    def test_clear_removes_all_records(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        for _ in range(5):
            store.add(_make_recording())

        assert store.count() == 5
        store.clear()
        assert store.count() == 0

    def test_clear_on_empty_db(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        store.clear()  # 不抛异常
        assert store.count() == 0


class TestThreadSafety:
    """线程安全测试。"""

    def test_concurrent_adds(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        errors: list[Exception] = []

        def worker(n: int):
            try:
                for i in range(50):
                    store.add(_make_recording(
                        original_text=f"thread_{n}_msg_{i}",
                    ))
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
        # 8 * 50 = 400
        assert store.count() == 400

    def test_concurrent_count(self, temp_db_path):
        store = HistoryStore(custom_path=temp_db_path)
        for _ in range(100):
            store.add(_make_recording())

        results: list[int] = []
        lock = threading.Lock()

        def worker():
            c = store.count()
            with lock:
                results.append(c)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # 所有 count 都应为 100
        assert all(c == 100 for c in results)
