"""
灵犀输入 — StyleProfileStore 持久化存储

单例模式的风格配置存储，将 StyleProfile 列表以 JSON 格式持久化到
~/.lingxi/profiles.json，首次启动自动填充 6 套预设风格。
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Optional

from lingxi.style.profile import StyleProfile, StyleProfileKind, PresetStyle
from lingxi.style.presets import PRESET_STYLES

logger = logging.getLogger(__name__)

# 与 main.py 保持一致的数据目录
APP_DIR = Path.home() / ".lingxi"
PROFILES_FILE = APP_DIR / "profiles.json"


class StyleProfileStore:
    """风格配置持久化存储（线程安全单例）。

    用法::

        store = StyleProfileStore()
        profiles = store.list_all()
        store.add(my_profile)
        store.delete(some_id)
    """

    _instance: Optional["StyleProfileStore"] = None
    _lock: threading.Lock = threading.Lock()

    def __new__(cls) -> "StyleProfileStore":
        if cls._instance is None:
            with cls._lock:
                # 双重检查锁定
                if cls._instance is None:
                    obj = super().__new__(cls)
                    obj._profiles: dict[str, StyleProfile] = {}
                    obj._rw_lock = threading.RLock()
                    obj._loaded = False
                    cls._instance = obj
        return cls._instance

    # ------------------------------------------------------------------
    # 持久化
    # ------------------------------------------------------------------

    def load(self) -> None:
        """从 JSON 文件加载所有 profile。

        如果文件不存在或为空，则自动用 6 套预设风格填充。
        """
        with self._rw_lock:
            if self._loaded:
                return

            APP_DIR.mkdir(parents=True, exist_ok=True)

            if PROFILES_FILE.exists():
                try:
                    raw = PROFILES_FILE.read_text(encoding="utf-8")
                    data: list[dict] = json.loads(raw) if raw.strip() else []
                    self._profiles = {
                        item["id"]: StyleProfile.from_dict(item)
                        for item in data
                    }
                    logger.info("已从 %s 加载 %d 个风格配置", PROFILES_FILE, len(self._profiles))
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    logger.warning("风格配置文件损坏，将用预设重建: %s", exc)
                    self._load_presets()
            else:
                self._load_presets()

            self._loaded = True

    def _load_presets(self) -> None:
        """使用 6 套预设风格填充存储。"""
        self._profiles = {}
        for preset_enum, profile in PRESET_STYLES.items():
            self._profiles[profile.id] = profile
        logger.info("已加载 %d 套预设风格", len(self._profiles))
        self.save()

    def save(self) -> None:
        """将所有 profile 写入 JSON 文件。"""
        with self._rw_lock:
            APP_DIR.mkdir(parents=True, exist_ok=True)
            data = [p.to_dict() for p in self._profiles.values()]
            PROFILES_FILE.write_text(
                json.dumps(data, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            logger.debug("已保存 %d 个风格配置到 %s", len(data), PROFILES_FILE)

    def reload(self) -> None:
        """强制重新从磁盘加载（丢弃内存中的修改）。"""
        with self._rw_lock:
            self._loaded = False
            self._profiles.clear()
        self.load()

    # ------------------------------------------------------------------
    # CRUD
    # ------------------------------------------------------------------

    def list_all(self) -> list[StyleProfile]:
        """返回所有风格 profile 的列表。

        预设在前，自定义在后（按创建时间排序）。
        """
        self.load()
        with self._rw_lock:
            profiles = list(self._profiles.values())

        presets = [p for p in profiles if p.kind == StyleProfileKind.PRESET]
        customs = [p for p in profiles if p.kind == StyleProfileKind.CUSTOM]
        presets.sort(key=lambda p: p.created_at)
        customs.sort(key=lambda p: p.created_at)
        return presets + customs

    def get(self, profile_id: str) -> Optional[StyleProfile]:
        """根据 ID 获取单个 profile。

        Args:
            profile_id: 风格配置唯一 ID。

        Returns:
            匹配的 StyleProfile，不存在时返回 None。
        """
        self.load()
        with self._rw_lock:
            return self._profiles.get(profile_id)

    def add(self, profile: StyleProfile) -> StyleProfile:
        """添加一个新的风格 profile。

        Args:
            profile: 要添加的 StyleProfile 实例。

        Returns:
            已添加的 profile（保持引用一致）。
        """
        self.load()
        with self._rw_lock:
            self._profiles[profile.id] = profile
            self._save_unlocked()
        logger.info("已添加风格: %s (%s)", profile.name, profile.id)
        return profile

    def update(self, profile: StyleProfile) -> StyleProfile:
        """更新已有的风格 profile（根据 profile.id 匹配）。

        Args:
            profile: 要更新的 StyleProfile 实例。

        Returns:
            更新后的 profile。

        Raises:
            KeyError: profile.id 不存在时抛出。
        """
        self.load()
        with self._rw_lock:
            if profile.id not in self._profiles:
                raise KeyError(f"风格不存在: {profile.id!r}")
            self._profiles[profile.id] = profile
            self._save_unlocked()
        logger.info("已更新风格: %s (%s)", profile.name, profile.id)
        return profile

    def delete(self, profile_id: str) -> bool:
        """删除指定 ID 的风格 profile。

        Args:
            profile_id: 要删除的风格唯一 ID。

        Returns:
            True 表示成功删除，False 表示 ID 不存在。
        """
        self.load()
        with self._rw_lock:
            if profile_id not in self._profiles:
                return False
            del self._profiles[profile_id]
            self._save_unlocked()
        logger.info("已删除风格: %s", profile_id)
        return True

    # ------------------------------------------------------------------
    # 内部
    # ------------------------------------------------------------------

    def _save_unlocked(self) -> None:
        """不加锁的写入（调用方必须持有 _rw_lock）。"""
        data = [p.to_dict() for p in self._profiles.values()]
        PROFILES_FILE.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear(self) -> None:
        """清空所有 profile（仅用于测试）。"""
        with self._rw_lock:
            self._profiles.clear()
            self._loaded = False

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（仅用于测试环境）。"""
        with cls._lock:
            cls._instance = None
