"""
测试 ConfigStore — JSON 配置持久化与线程安全。
"""

from __future__ import annotations

import json
import tempfile
import threading
from pathlib import Path

import pytest

from lingxi.data.config_store import ConfigStore, DEFAULT_CONFIG


# ---------------------------------------------------------------------------
# 辅助 — 每次测试使用全新的单例实例
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singleton(monkeypatch):
    """每个测试前重置 ConfigStore 单例，避免状态污染。"""
    monkeypatch.setattr("lingxi.data.config_store.ConfigStore._instance", None)


@pytest.fixture
def temp_config_file():
    """在临时目录中创建一个独立配置文件。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir) / "config.json"


# ---------------------------------------------------------------------------
# 测试用例
# ---------------------------------------------------------------------------

class TestDefaultConfig:
    """验证默认配置结构。"""

    def test_default_config_has_expected_keys(self, temp_config_file):
        store = ConfigStore(custom_path=str(temp_config_file))
        data = store.all()

        assert "asr" in data
        assert "llm" in data
        assert "hotkey" in data
        assert "emotion" in data
        assert "default_style" in data
        assert "language" in data
        assert "onboarding" in data
        assert "app_bindings" in data
        assert "privacy" in data

    def test_default_asr_values(self, temp_config_file):
        store = ConfigStore(custom_path=str(temp_config_file))

        assert store.get("asr.primary") == "faster_whisper"
        assert store.get("asr.fallback") == "faster_whisper"
        assert store.get("asr.auto_fallback") is True
        assert store.get("asr.model_size") == "small"

    def test_default_emotion_values(self, temp_config_file):
        store = ConfigStore(custom_path=str(temp_config_file))

        assert store.get("emotion.enabled") is True
        assert store.get("emotion.strength") == 0.7

    def test_default_language(self, temp_config_file):
        store = ConfigStore(custom_path=str(temp_config_file))

        assert store.get("language.code") == "zh-CN"
        assert store.get("language.display_name") == "简体中文"

    def test_default_onboarding(self, temp_config_file):
        store = ConfigStore(custom_path=str(temp_config_file))

        assert store.get("onboarding.completed") is False
        assert store.get("onboarding.completed_at") is None
        assert store.get("onboarding.current_step") == 1

    def test_get_with_default(self, temp_config_file):
        store = ConfigStore(custom_path=str(temp_config_file))

        assert store.get("nonexistent.key", 42) == 42
        assert store.get("nonexistent") is None


class TestJSONRoundTrip:
    """JSON 读写往返。"""

    def test_set_get_roundtrip_simple(self, temp_config_file):
        store = ConfigStore(custom_path=str(temp_config_file))
        store.set("default_style", "witty")
        assert store.get("default_style") == "witty"

    def test_save_load_roundtrip(self, temp_config_file):
        # 第一次实例
        store1 = ConfigStore(custom_path=str(temp_config_file))
        store1.set("asr.primary", "funasr")
        store1.set("emotion.strength", 0.42)
        store1.save()

        # 模拟新进程加载
        ConfigStore._instance = None
        store2 = ConfigStore(custom_path=str(temp_config_file))
        assert store2.get("asr.primary") == "funasr"
        assert store2.get("emotion.strength") == 0.42

    def test_dot_path_nested_write(self, temp_config_file):
        store = ConfigStore(custom_path=str(temp_config_file))

        store.set("asr.primary", "whisper")
        assert store.get("asr.primary") == "whisper"
        # 确保其他兄弟字段不受影响
        assert store.get("asr.fallback") == "faster_whisper"

    def test_dot_path_create_intermediate(self, temp_config_file):
        store = ConfigStore(custom_path=str(temp_config_file))

        store.set("a.b.c", 99)
        assert store.get("a.b.c") == 99

    def test_reset_restores_defaults(self, temp_config_file):
        store = ConfigStore(custom_path=str(temp_config_file))
        store.set("asr.primary", "modified")
        store.reset()

        assert store.get("asr.primary") == "faster_whisper"


class TestCorruptedConfig:
    """JSON 损坏恢复测试。"""

    def test_corrupted_json_backup_and_rebuild(self, temp_config_file):
        # 先创建一个合法配置文件
        store1 = ConfigStore(custom_path=str(temp_config_file))
        store1.set("asr.primary", "custom_value")
        store1.save()

        # 模拟文件损坏：写入非法 JSON
        temp_config_file.write_text("this is not json{{{", encoding="utf-8")

        # 重新加载（模拟新进程）
        ConfigStore._instance = None
        store2 = ConfigStore(custom_path=str(temp_config_file))
        # 应回退到默认配置
        assert store2.get("asr.primary") == "faster_whisper"

        # 应存在 .corrupted 备份文件
        corrupted = temp_config_file.with_suffix(".corrupted")
        assert corrupted.exists()
        assert corrupted.read_text(encoding="utf-8") == "this is not json{{{"

    def test_empty_file_treated_as_corrupted(self, temp_config_file):
        """空文件应被视为配置损坏并重建。"""
        temp_config_file.write_text("", encoding="utf-8")

        store = ConfigStore(custom_path=str(temp_config_file))
        assert store.get("asr.primary") == "faster_whisper"


class TestThreadSafety:
    """线程安全基本测试。"""

    def test_concurrent_set_get_no_crash(self, temp_config_file):
        store = ConfigStore(custom_path=str(temp_config_file))
        errors: list[Exception] = []

        def worker(i: int):
            try:
                for j in range(100):
                    store.set(f"test.worker_{i}.value_{j}", j)
                    _ = store.get(f"test.worker_{i}.value_{j}")
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0

    def test_concurrent_save_no_crash(self, temp_config_file):
        store = ConfigStore(custom_path=str(temp_config_file))
        errors: list[Exception] = []

        def worker(i: int):
            try:
                for _ in range(50):
                    store.set(f"concurrent.key_{i}", i)
                    store.save()
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(errors) == 0
