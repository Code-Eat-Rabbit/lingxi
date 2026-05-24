"""
灵犀输入 — ConfigStore 配置持久化

单例模式 JSON 配置存储，支持点号路径嵌套读写、
JSON 损坏自动恢复、线程安全。
"""

from __future__ import annotations

import json
import os
import shutil
import threading
from copy import deepcopy
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# 默认配置结构
# ---------------------------------------------------------------------------

DEFAULT_CONFIG: dict[str, Any] = {
    "asr": {
        "primary": "faster_whisper",
        "fallback": "faster_whisper",
        "auto_fallback": True,
        "model_size": "small",
    },
    "llm": {
        "provider": "openai",
        "model": "gpt-4o-mini",
        "api_key": None,
        "base_url": None,
        "ollama_host": "http://localhost:11434",
    },
    "hotkey": {
        "record": "fn+cmd",
        "style_picker": "fn+cmd_long",
    },
    "emotion": {
        "enabled": True,
        "strength": 0.7,
    },
    "default_style": "casual",
    "language": {
        "code": "zh-CN",
        "display_name": "简体中文",
    },
    "onboarding": {
        "completed": False,
        "completed_at": None,
        "current_step": 1,
    },
    "app_bindings": [],
    "privacy": {
        "history_enabled": False,
    },
}


# ---------------------------------------------------------------------------
# ConfigStore (Singleton)
# ---------------------------------------------------------------------------

class ConfigStore:
    """单例 JSON 配置存储，线程安全，支持点号路径。

    典型用法::

        store = ConfigStore()
        engine = store.get("asr.primary")       # "faster_whisper"
        store.set("emotion.strength", 0.8)
        store.save()

    测试时传入临时路径::

        store = ConfigStore(custom_path="/tmp/test_config.json")
    """

    _instance: ConfigStore | None = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls, custom_path: str | None = None, **kwargs: Any) -> ConfigStore:
        # Singleton: 仅首次构造时允许 custom_path
        if cls._instance is None:
            obj = super().__new__(cls)
            obj._initialized = False
            obj._data_lock = threading.RLock()
            cls._instance = obj
        return cls._instance

    def __init__(self, custom_path: str | None = None) -> None:
        if self._initialized:
            # 若传入了与首次不同的 custom_path，发出警告但不覆盖
            return
        self._initialized = True

        if custom_path:
            self._config_path = Path(custom_path)
        else:
            self._config_path = Path.home() / ".lingxi" / "config.json"

        self._data: dict[str, Any] = {}
        self.load()

    # ------------------------------------------------------------------
    # 点号路径工具
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_path(
        data: dict[str, Any], key: str, *, create_missing: bool = False
    ) -> tuple[dict[str, Any], str]:
        """解析点号路径 key 并返回 (父级字典, 最终键名)。

        当 create_missing=True 时，缺失的中间节点将被自动创建为 dict。
        """
        parts = key.split(".")
        if len(parts) == 1:
            return data, key

        current: dict[str, Any] = data
        for part in parts[:-1]:
            if part not in current or not isinstance(current.get(part), dict):
                if create_missing:
                    current[part] = {}
                else:
                    # 只读模式：中间节点不在则返回空 dict，让 get 回退
                    return {}, parts[-1]
            current = current[part]  # type: ignore[assignment]
        return current, parts[-1]

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值，支持点号路径。"""
        with self._data_lock:
            parent, last_key = self._resolve_path(self._data, key)
            return parent.get(last_key, default)

    def set(self, key: str, value: Any) -> None:
        """设置配置值，支持点号路径。不自动保存到磁盘。"""
        with self._data_lock:
            parent, last_key = self._resolve_path(self._data, key, create_missing=True)
            parent[last_key] = value

    def all(self) -> dict[str, Any]:
        """返回当前全部配置的深拷贝。"""
        with self._data_lock:
            return deepcopy(self._data)

    def save(self) -> None:
        """将当前配置写入磁盘。"""
        with self._data_lock:
            self._config_path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._config_path.with_suffix(".tmp")
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self._data, f, ensure_ascii=False, indent=2)
            tmp.replace(self._config_path)

    def load(self) -> None:
        """从磁盘加载配置；若不存在或损坏则重建默认配置。"""
        with self._data_lock:
            if not self._config_path.exists():
                self._data = deepcopy(DEFAULT_CONFIG)
                self.save()
                return

            try:
                with open(self._config_path, "r", encoding="utf-8") as f:
                    loaded = json.load(f)
                if not isinstance(loaded, dict):
                    raise ValueError("config root is not a dict")
                self._data = loaded
            except (json.JSONDecodeError, ValueError, OSError):
                # 备份损坏文件
                corrupted = self._config_path.with_suffix(".corrupted")
                shutil.copy2(self._config_path, corrupted)
                self._data = deepcopy(DEFAULT_CONFIG)
                self.save()

    def reset(self) -> None:
        """重置为默认配置并写入磁盘。"""
        with self._data_lock:
            self._data = deepcopy(DEFAULT_CONFIG)
            self.save()

    def reload(self) -> None:
        """从磁盘重新加载配置（丢弃内存中的修改）。"""
        self.load()
