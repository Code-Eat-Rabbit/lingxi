"""情绪枚举与 EmotionModulator

定义情绪标签、调制参数映射表，以及将情绪调制应用到 StyleProfile 的
EmotionModulator 静态方法集。

与规格文档 §1.6 保持一致。
"""

from __future__ import annotations

import copy
import dataclasses
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, ClassVar


# ── 情绪枚举 ──────────────────────────────────────────────────────────

class Emotion(str, Enum):
    """语音可检测的 7 种基本情绪"""
    NEUTRAL = "neutral"
    ANGER = "anger"
    HAPPY = "happy"
    SAD = "sad"
    SURPRISE = "surprise"
    FEAR = "fear"
    DISGUST = "disgust"


# ── 情绪调制参数 ──────────────────────────────────────────────────────

@dataclass
class EmotionModulation:
    """一种情绪对五维风格参数的偏移量，以及标点 / emoji 提示"""
    formality_delta: float = 0.0
    intimacy_delta: float = 0.0
    humor_delta: float = 0.0
    directness_delta: float = 0.0
    conciseness_delta: float = 0.0
    punctuation_hint: str = ""
    emoji_allowed: bool = True
    special_instruction: str = ""


# ── 完整情绪 → 调制参数映射表 (§1.6) ─────────────────────────────────

EMOTION_MODULATION_MAP: dict[Emotion, EmotionModulation] = {
    Emotion.NEUTRAL: EmotionModulation(
        formality_delta=0.0,
        intimacy_delta=0.0,
        humor_delta=0.0,
        directness_delta=0.0,
        conciseness_delta=0.0,
        punctuation_hint="",
        emoji_allowed=True,
        special_instruction="",
    ),
    Emotion.ANGER: EmotionModulation(
        formality_delta=0.0,
        intimacy_delta=-0.2,
        humor_delta=-0.3,
        directness_delta=+0.2,
        conciseness_delta=+0.1,
        punctuation_hint="exclamation",
        emoji_allowed=False,
        special_instruction="",
    ),
    Emotion.HAPPY: EmotionModulation(
        formality_delta=-0.1,
        intimacy_delta=+0.1,
        humor_delta=+0.3,
        directness_delta=0.0,
        conciseness_delta=-0.1,
        punctuation_hint="tilde",
        emoji_allowed=True,
        special_instruction="",
    ),
    Emotion.SAD: EmotionModulation(
        formality_delta=-0.1,
        intimacy_delta=+0.2,
        humor_delta=-0.3,
        directness_delta=-0.2,
        conciseness_delta=0.0,
        punctuation_hint="ellipsis",
        emoji_allowed=False,
        special_instruction="",
    ),
    Emotion.SURPRISE: EmotionModulation(
        formality_delta=0.0,
        intimacy_delta=0.0,
        humor_delta=+0.1,
        directness_delta=+0.1,
        conciseness_delta=-0.1,
        punctuation_hint="exclamation_question",
        emoji_allowed=True,
        special_instruction="",
    ),
    Emotion.FEAR: EmotionModulation(
        formality_delta=+0.1,
        intimacy_delta=+0.1,
        humor_delta=-0.2,
        directness_delta=-0.2,
        conciseness_delta=0.0,
        punctuation_hint="ellipsis",
        emoji_allowed=False,
        special_instruction="",
    ),
    Emotion.DISGUST: EmotionModulation(
        formality_delta=0.0,
        intimacy_delta=-0.3,
        humor_delta=-0.1,
        directness_delta=+0.2,
        conciseness_delta=+0.2,
        punctuation_hint="none",
        emoji_allowed=False,
        special_instruction="",
    ),
}


# ── EmotionModulator ──────────────────────────────────────────────────

class EmotionModulator:
    """将检测到的情绪调制应用到 StyleProfile 上。

    使用 duck typing：接受任何包含五维属性
    (formality, intimacy, humor, directness, conciseness)
    的对象，返回一个属性被调制后的副本。

    对 dataclass 优先使用 dataclasses.replace，否则回退到 deepcopy。
    """

    # 五维属性的字段名
    _DIM_FIELDS: ClassVar[tuple[str, ...]] = (
        "formality", "intimacy", "humor", "directness", "conciseness",
    )
    _DELTA_FIELDS: ClassVar[tuple[str, ...]] = (
        "formality_delta", "intimacy_delta", "humor_delta",
        "directness_delta", "conciseness_delta",
    )
    _MIDLINE: ClassVar[float] = 0.5

    # ── 公开 API ──────────────────────────────────────────────────

    @staticmethod
    def apply(
        profile: Any,
        emotion: Emotion | str,
        strength: float = 1.0,
    ) -> Any:
        """将情绪调制应用到 profile 上，返回调制后的**副本**。

        Args:
            profile: 具有五维属性的样式对象（duck typing）
            emotion: 情绪标签 (Emotion enum 或字符串)
            strength: 调制强度乘数 (0.0 ~ 1.0)

        Returns:
            调制后的样式对象副本
        """
        if isinstance(emotion, str):
            try:
                emotion = Emotion(emotion)
            except ValueError:
                # 未识别的情绪字符串 → 原样返回副本
                return EmotionModulator._copy_profile(profile)

        modulation = EMOTION_MODULATION_MAP.get(emotion)
        if modulation is None:
            # 未识别的情绪 → 原样返回副本
            return EmotionModulator._copy_profile(profile)

        # 计算调制后的字段值（带钳制）
        replacements: dict[str, float] = {}
        for dim_field, delta_field in zip(
            EmotionModulator._DIM_FIELDS, EmotionModulator._DELTA_FIELDS
        ):
            original = getattr(profile, dim_field, EmotionModulator._MIDLINE)
            delta = getattr(modulation, delta_field, 0.0)
            proposed = original + delta * strength
            replacements[dim_field] = EmotionModulator._clamp(proposed, original)

        # 复制 profile 并应用修改
        return EmotionModulator._copy_profile(profile, replacements)

    @staticmethod
    def get_confidence_action(
        confidence: float,
        engine_type: str = "whisper",
    ) -> tuple[float, bool]:
        """根据情绪置信度决定调制强度和应用开关。

        置信度阈值规则：
        - > 0.7  → 全量调制  (strength=1.0, apply=True)
        - 0.4~0.7 → 减半调制 (strength=0.5, apply=True)
        - < 0.4  → 不做微调  (strength=0.0, apply=False)

        对于 whisper 引擎（不原生支持情绪），默认置信度为 0.5，
        返回减半调制。

        Args:
            confidence: 情绪检测置信度 [0.0, 1.0]
            engine_type: ASR 引擎类型标识

        Returns:
            (modulation_strength, should_apply) 元组
        """
        if confidence > 0.7:
            return (1.0, True)
        elif confidence >= 0.4:
            return (0.5, True)
        else:
            return (0.0, False)

    # ── 内部工具 ──────────────────────────────────────────────────

    @staticmethod
    def _clamp(value: float, original: float) -> float:
        """将 value 钳制到 [0, 1] 范围内，且不允许跨越中线 0.5。

        规则：
        - 若原始值 < 0.5，调制后不得 ≥ 0.5
        - 若原始值 > 0.5，调制后不得 ≤ 0.5
        - 若原始值 = 0.5，调制后 = 0.5

        Args:
            value: 调制后的 proposed 值
            original: 调制前的原始值

        Returns:
            钳制后的安全值
        """
        # 标准 [0, 1] 钳制
        value = max(0.0, min(1.0, value))

        # 不跨中线
        if original < EmotionModulator._MIDLINE:
            value = min(value, EmotionModulator._MIDLINE)
        elif original > EmotionModulator._MIDLINE:
            value = max(value, EmotionModulator._MIDLINE)
        else:
            value = EmotionModulator._MIDLINE

        return value

    @staticmethod
    def _copy_profile(profile: Any, updates: dict[str, float] | None = None) -> Any:
        """创建 profile 的副本，可选应用字段更新。

        优先使用 dataclasses.replace（dataclass），
        回退到 copy.deepcopy + setattr（普通对象）。
        """
        if updates is None:
            updates = {}

        if dataclasses.is_dataclass(profile):
            return dataclasses.replace(profile, **updates)

        # Duck typing 回退：deepcopy + 手动设置属性
        new_profile = copy.deepcopy(profile)
        for field_name, new_value in updates.items():
            if hasattr(new_profile, field_name):
                setattr(new_profile, field_name, new_value)
        return new_profile
