"""
灵犀输入 — HistoryStore SQLite 历史记录

线程安全的 SQLite 持久化层，记录每次语音转写 + 风格化的完整信息。
"""

from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# SQL
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL: str = """
CREATE TABLE IF NOT EXISTS recordings (
    id              TEXT PRIMARY KEY,
    timestamp       TEXT NOT NULL,
    original_text   TEXT NOT NULL,
    styled_text     TEXT,
    style_name      TEXT,
    emotion         TEXT DEFAULT 'neutral',
    asr_engine      TEXT,
    llm_provider    TEXT,
    duration_ms     INTEGER,
    success         INTEGER DEFAULT 1
)
"""


# ---------------------------------------------------------------------------
# HistoryStore
# ---------------------------------------------------------------------------

class HistoryStore:
    """SQLite 历史记录存储，线程安全。

    典型用法::

        store = HistoryStore()
        store.add({
            "id": "abc123",
            "timestamp": "2026-01-01T00:00:00",
            "original_text": "你好",
            "styled_text": "您好～",
            "style_name": "respectful",
            "emotion": "neutral",
            "asr_engine": "faster_whisper",
            "llm_provider": "openai",
            "duration_ms": 1200,
            "success": 1,
        })
        recent = store.get_recent(20)
        results = store.search("你好")
        print(store.count())

    测试时传入临时路径::

        store = HistoryStore(custom_path="/tmp/test_history.db")
    """

    def __init__(self, custom_path: str | None = None) -> None:
        if custom_path:
            self._db_path = Path(custom_path)
        else:
            self._db_path = Path.home() / ".lingxi" / "history.db"

        self._db_path.parent.mkdir(parents=True, exist_ok=True)

        # 线程局部存储：每个线程持有一个独立的 sqlite3 连接
        self._local = threading.local()
        self._init_table()

    # ------------------------------------------------------------------
    # 连接管理
    # ------------------------------------------------------------------

    def _get_conn(self) -> sqlite3.Connection:
        """获取当前线程的数据库连接，若不存在则创建。"""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = sqlite3.connect(str(self._db_path), check_same_thread=False)
            conn.row_factory = sqlite3.Row
            self._local.conn = conn
        return conn

    def _init_table(self) -> None:
        """确保 recordings 表已创建。"""
        conn = self._get_conn()
        conn.execute(CREATE_TABLE_SQL)
        conn.commit()

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def add(self, recording: dict[str, Any]) -> None:
        """添加一条录音记录。

        recording 字典应包含表结构中的所有字段；
        缺失的可选字段将使用默认值（None / 'neutral' / 1）。
        """
        conn = self._get_conn()
        conn.execute(
            """
            INSERT OR REPLACE INTO recordings
                (id, timestamp, original_text, styled_text, style_name,
                 emotion, asr_engine, llm_provider, duration_ms, success)
            VALUES
                (:id, :timestamp, :original_text, :styled_text, :style_name,
                 :emotion, :asr_engine, :llm_provider, :duration_ms, :success)
            """,
            {
                "id": recording.get("id"),
                "timestamp": recording.get("timestamp"),
                "original_text": recording.get("original_text"),
                "styled_text": recording.get("styled_text"),
                "style_name": recording.get("style_name"),
                "emotion": recording.get("emotion", "neutral"),
                "asr_engine": recording.get("asr_engine"),
                "llm_provider": recording.get("llm_provider"),
                "duration_ms": recording.get("duration_ms"),
                "success": recording.get("success", 1),
            },
        )
        conn.commit()

    def get_recent(self, limit: int = 50) -> list[dict[str, Any]]:
        """返回最近的 N 条记录，按时间降序。"""
        conn = self._get_conn()
        rows = conn.execute(
            "SELECT * FROM recordings ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def search(self, query: str, limit: int = 50) -> list[dict[str, Any]]:
        """在 original_text 和 styled_text 中进行模糊搜索（LIKE）。"""
        conn = self._get_conn()
        pattern = f"%{query}%"
        rows = conn.execute(
            """
            SELECT * FROM recordings
            WHERE original_text LIKE ? OR styled_text LIKE ?
            ORDER BY timestamp DESC
            LIMIT ?
            """,
            (pattern, pattern, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def clear(self) -> None:
        """清空所有历史记录。"""
        conn = self._get_conn()
        conn.execute("DELETE FROM recordings")
        conn.commit()

    def count(self) -> int:
        """返回历史记录总数。"""
        conn = self._get_conn()
        row = conn.execute("SELECT COUNT(*) AS cnt FROM recordings").fetchone()
        return row["cnt"]  # type: ignore[no-any-return]
