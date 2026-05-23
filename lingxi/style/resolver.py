"""
灵犀输入 — StyleResolver 4级优先级风格解析器

按优先级解析当前应使用的风格配置：
  1. 手动临时覆盖（最高）
  2. 应用绑定
  3. 联系人感知（v1.1 预留）
  4. 全局默认（最低）

支持情绪调制集成：解析后可通过 EmotionModulator.apply() 对结果
应用情绪偏移。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from lingxi.style.profile import StyleProfile, PresetStyle
from lingxi.style.presets import get_preset
from lingxi.style.store import StyleProfileStore
from lingxi.engine.emotion import Emotion, EmotionModulator

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 数据模型
# ---------------------------------------------------------------------------

@dataclass
class StyleAppBinding:
    """应用 → 风格绑定配置。"""
    app_name: str = ""
    app_identifier: str = ""
    style_id: str = ""
    match_mode: str = "prefix"  # "exact" | "prefix"
    is_enabled: bool = True


class ResolveSource(str, Enum):
    """风格解析来源。"""
    MANUAL = "manual"            # 手动临时覆盖
    APP_BINDING = "app_binding"  # 应用绑定
    CONTACT = "contact"          # 联系人感知 (v1.1)
    DEFAULT = "default"          # 全局默认


@dataclass
class ResolveResult:
    """风格解析结果，包含解析出的 profile 及其来源信息。"""
    profile: StyleProfile
    source: ResolveSource
    source_detail: str = ""  # 如 "企业微信应用绑定" 或 "手动临时覆盖"


# ---------------------------------------------------------------------------
# StyleResolver
# ---------------------------------------------------------------------------

class StyleResolver:
    """4 级优先级风格解析器。

    用法::

        resolver = StyleResolver(store, config)
        result = resolver.resolve(app_identifier="com.wechat")
        print(result.profile.name)  # 当前生效的风格名称
    """

    def __init__(self, store: StyleProfileStore, config) -> None:
        """初始化解析器。

        Args:
            store: StyleProfileStore 实例，用于查询风格配置。
            config: ConfigStore 实例，用于读取 default_style 等配置。
        """
        self._store = store
        self._config = config
        self._manual_override: Optional[str] = None
        self._app_bindings: list[StyleAppBinding] = []

    # ------------------------------------------------------------------
    # 手动覆盖
    # ------------------------------------------------------------------

    def set_manual_override(self, style_id: Optional[str]) -> None:
        """设置或取消临时手动覆盖。

        Args:
            style_id: 要覆盖的风格 ID；传入 None 表示取消覆盖。
        """
        if style_id is not None:
            logger.info("手动覆盖风格: %s", style_id)
        else:
            logger.info("取消手动覆盖")
        self._manual_override = style_id

    # ------------------------------------------------------------------
    # 应用绑定管理
    # ------------------------------------------------------------------

    def add_app_binding(self, binding: StyleAppBinding) -> None:
        """添加一条应用绑定。

        若已存在相同 app_identifier 的绑定，先移除旧的再添加新的。
        """
        self.remove_app_binding(binding.app_identifier)
        self._app_bindings.append(binding)
        logger.info(
            "添加应用绑定: %s (%s) → %s [%s]",
            binding.app_name, binding.app_identifier, binding.style_id, binding.match_mode,
        )

    def remove_app_binding(self, app_identifier: str) -> bool:
        """移除指定应用标识符的所有绑定。

        Returns:
            True 表示成功删除至少一条，False 表示未找到。
        """
        before = len(self._app_bindings)
        self._app_bindings = [
            b for b in self._app_bindings
            if b.app_identifier != app_identifier
        ]
        removed = before - len(self._app_bindings)
        if removed > 0:
            logger.info("移除应用绑定: %s (%d 条)", app_identifier, removed)
        return removed > 0

    def get_app_bindings(self) -> list[StyleAppBinding]:
        """返回当前所有应用绑定的副本。"""
        return list(self._app_bindings)

    # ------------------------------------------------------------------
    # 核心解析
    # ------------------------------------------------------------------

    def resolve(
        self,
        app_identifier: Optional[str] = None,
        contact_name: Optional[str] = None,
        emotion: Optional[Emotion] = None,
        emotion_strength: float = 0.0,
    ) -> ResolveResult:
        """按 4 级优先级解析当前应使用的风格。

        优先级：
          1. 手动覆盖 → 2. 应用绑定 → 3. 联系人感知 → 4. 全局默认

        如果提供了 emotion 且 emotion_strength > 0，对最终结果应用
        EmotionModulator.apply() 进行情绪偏移。

        Args:
            app_identifier: 当前活跃应用标识符（如 "com.wechat"）。
            contact_name: 联系人名称（v1.1 预留，当前忽略）。
            emotion: 检测到的情绪标签。
            emotion_strength: 情绪调制强度 [0.0, 1.0]。

        Returns:
            ResolveResult，包含解析出的 profile、来源及详情描述。
        """
        source: ResolveSource
        source_detail: str
        profile: Optional[StyleProfile] = None

        # --- 级别 1: 手动覆盖 ---
        if self._manual_override is not None:
            profile = self._store.get(self._manual_override)
            if profile is not None:
                source = ResolveSource.MANUAL
                source_detail = f"手动临时覆盖 ({profile.name})"
                logger.debug("解析: 手动覆盖 → %s", self._manual_override)

        # --- 级别 2: 应用绑定 ---
        if profile is None and app_identifier is not None:
            matched_style_id = self._match_app_binding(app_identifier)
            if matched_style_id is not None:
                profile = self._store.get(matched_style_id)
                if profile is not None:
                    source = ResolveSource.APP_BINDING
                    source_detail = f"应用绑定: {app_identifier} → {profile.name}"
                    logger.debug("解析: 应用绑定 %s → %s", app_identifier, matched_style_id)

        # --- 级别 3: 联系人感知 (v1.1 预留) ---
        # 当前跳过，待 v1.1 实现联系人→风格映射

        # --- 级别 4: 全局默认 ---
        if profile is None:
            profile = self._get_default_style()
            source = ResolveSource.DEFAULT
            source_detail = f"全局默认 ({profile.name})"
            logger.debug("解析: 全局默认 → %s", profile.name)

        # --- 情绪调制 ---
        if emotion is not None and emotion_strength > 0.0:
            profile = EmotionModulator.apply(profile, emotion, emotion_strength)
            logger.debug(
                "情绪调制: %s (strength=%.2f)", emotion.value, emotion_strength,
            )

        return ResolveResult(profile=profile, source=source, source_detail=source_detail)

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _match_app_binding(self, app_identifier: str) -> Optional[str]:
        """匹配应用绑定，返回命中的 style_id 或 None。

        仅检查 is_enabled=True 的绑定。支持两种匹配模式：
          - exact:   binding.app_identifier == app_identifier
          - prefix:  app_identifier.startswith(binding.app_identifier)

        返回第一个匹配的 style_id；无匹配返回 None。
        """
        for binding in self._app_bindings:
            if not binding.is_enabled:
                continue

            if binding.match_mode == "exact":
                if binding.app_identifier == app_identifier:
                    return binding.style_id
            elif binding.match_mode == "prefix":
                if app_identifier.startswith(binding.app_identifier):
                    return binding.style_id
            else:
                logger.warning("未知匹配模式: %s，跳过绑定 %s", binding.match_mode, binding.app_identifier)

        return None

    def _get_default_style(self) -> StyleProfile:
        """从 ConfigStore 读取 default_style，回退到预设 CASUAL。

        ConfigStore 中 default_style 存储预设枚举值字符串
        （如 "casual", "respectful"），通过 PresetStyle 枚举映射
        到对应预设 profile。
        """
        default_key: str = self._config.get("default_style", "casual")
        try:
            preset = PresetStyle(default_key)
            return get_preset(preset)
        except (ValueError, KeyError):
            logger.warning(
                "无效的 default_style 值 %r，回退到 CASUAL", default_key,
            )
            return get_preset(PresetStyle.CASUAL)
