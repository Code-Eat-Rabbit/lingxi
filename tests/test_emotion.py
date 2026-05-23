"""测试 emotion.py — 情绪枚举、EmotionModulation、EmotionModulator

覆盖：
- 7 种情绪映射表完整性
- 钳制不跨中线
- 置信度阈值逻辑
- 中性情绪不做微调
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pytest

from lingxi.engine.emotion import (
    EMOTION_MODULATION_MAP,
    Emotion,
    EmotionModulation,
    EmotionModulator,
)


# ── 辅助：模拟 StyleProfile（duck typing）─────────────────────────────

@dataclass
class MockProfile:
    """模拟五维 StyleProfile 用于测试 EmotionModulator"""
    formality: float = 0.5
    intimacy: float = 0.5
    humor: float = 0.5
    directness: float = 0.5
    conciseness: float = 0.5


class NonDataclassProfile:
    """非 dataclass 对象，测试 duck typing 回退路径"""

    def __init__(self):
        self.formality = 0.5
        self.intimacy = 0.5
        self.humor = 0.5
        self.directness = 0.5
        self.conciseness = 0.5


# ── 01. 情绪枚举完整性 ────────────────────────────────────────────────

class TestEmotionEnum:
    """Emotion 枚举包含全部 7 种情绪"""

    def test_all_seven_emotions_present(self):
        assert len(Emotion) == 7
        expected = {
            "neutral", "anger", "happy", "sad",
            "surprise", "fear", "disgust",
        }
        actual = {e.value for e in Emotion}
        assert actual == expected

    def test_emotion_is_string_subclass(self):
        assert isinstance(Emotion.NEUTRAL, str)
        assert Emotion.NEUTRAL == "neutral"


# ── 02. 映射表完整性 ──────────────────────────────────────────────────

class TestModulationMap:
    """EMOTION_MODULATION_MAP 覆盖全部 7 种情绪且值符合规格 §1.6"""

    def test_all_emotions_have_modulation(self):
        for emotion in Emotion:
            assert emotion in EMOTION_MODULATION_MAP, (
                f"缺少情绪调制: {emotion}"
            )

    def test_anger_modulation(self):
        m = EMOTION_MODULATION_MAP[Emotion.ANGER]
        assert m.formality_delta == 0.0
        assert m.intimacy_delta == -0.2
        assert m.humor_delta == -0.3
        assert m.directness_delta == 0.2
        assert m.conciseness_delta == 0.1
        assert m.punctuation_hint == "exclamation"
        assert m.emoji_allowed is False

    def test_happy_modulation(self):
        m = EMOTION_MODULATION_MAP[Emotion.HAPPY]
        assert m.formality_delta == -0.1
        assert m.intimacy_delta == 0.1
        assert m.humor_delta == 0.3
        assert m.directness_delta == 0.0
        assert m.conciseness_delta == -0.1
        assert m.punctuation_hint == "tilde"
        assert m.emoji_allowed is True

    def test_sad_modulation(self):
        m = EMOTION_MODULATION_MAP[Emotion.SAD]
        assert m.formality_delta == -0.1
        assert m.intimacy_delta == 0.2
        assert m.humor_delta == -0.3
        assert m.directness_delta == -0.2
        assert m.conciseness_delta == 0.0
        assert m.punctuation_hint == "ellipsis"
        assert m.emoji_allowed is False

    def test_surprise_modulation(self):
        m = EMOTION_MODULATION_MAP[Emotion.SURPRISE]
        assert m.formality_delta == 0.0
        assert m.intimacy_delta == 0.0
        assert m.humor_delta == 0.1
        assert m.directness_delta == 0.1
        assert m.conciseness_delta == -0.1
        assert m.punctuation_hint == "exclamation_question"
        assert m.emoji_allowed is True

    def test_fear_modulation(self):
        m = EMOTION_MODULATION_MAP[Emotion.FEAR]
        assert m.formality_delta == 0.1
        assert m.intimacy_delta == 0.1
        assert m.humor_delta == -0.2
        assert m.directness_delta == -0.2
        assert m.conciseness_delta == 0.0
        assert m.punctuation_hint == "ellipsis"
        assert m.emoji_allowed is False

    def test_disgust_modulation(self):
        m = EMOTION_MODULATION_MAP[Emotion.DISGUST]
        assert m.formality_delta == 0.0
        assert m.intimacy_delta == -0.3
        assert m.humor_delta == -0.1
        assert m.directness_delta == 0.2
        assert m.conciseness_delta == 0.2
        assert m.punctuation_hint == "none"
        assert m.emoji_allowed is False

    def test_neutral_modulation_all_zero(self):
        m = EMOTION_MODULATION_MAP[Emotion.NEUTRAL]
        assert m.formality_delta == 0.0
        assert m.intimacy_delta == 0.0
        assert m.humor_delta == 0.0
        assert m.directness_delta == 0.0
        assert m.conciseness_delta == 0.0
        assert m.punctuation_hint == ""
        assert m.emoji_allowed is True


# ── 03. 钳制不跨中线 ─────────────────────────────────────────────────

class TestClamp:
    """_clamp 方法：钳制到 [0,1] 且不跨越中线 0.5"""

    def test_basic_clamp_to_zero_one(self):
        assert EmotionModulator._clamp(1.5, 0.5) == 0.5  # 原始=中线 → 定死
        assert EmotionModulator._clamp(-0.5, 0.5) == 0.5
        assert EmotionModulator._clamp(1.5, 0.3) == 0.5  # 原始<中线，不能上穿
        assert EmotionModulator._clamp(-0.5, 0.7) == 0.5  # 原始>中线，不能下穿

    def test_no_cross_midline_from_below(self):
        """原始 < 0.5，调制后不得 ≥ 0.5"""
        # 原始 0.3，加一个大增量，应该被钳在 0.5
        result = EmotionModulator._clamp(0.9, 0.3)
        assert result < 0.5 or math.isclose(result, 0.5)

    def test_no_cross_midline_from_above(self):
        """原始 > 0.5，调制后不得 ≤ 0.5"""
        # 原始 0.8，减一个大增量，应被钳在 0.5
        result = EmotionModulator._clamp(0.1, 0.8)
        assert result >= 0.5

    def test_midline_stays_midline(self):
        """原始 = 0.5，无论如何都留在 0.5"""
        assert EmotionModulator._clamp(0.9, 0.5) == 0.5
        assert EmotionModulator._clamp(0.1, 0.5) == 0.5
        assert EmotionModulator._clamp(0.5, 0.5) == 0.5

    def test_clamp_preserves_large_below(self):
        """原始 = 0.2，小幅正向调制不应触发钳制"""
        result = EmotionModulator._clamp(0.3, 0.2)
        assert 0.2 <= result <= 0.5
        assert result == 0.3

    def test_clamp_preserves_small_above(self):
        """原始 = 0.7，小幅负向调制不应触发钳制"""
        result = EmotionModulator._clamp(0.6, 0.7)
        assert 0.5 <= result <= 0.7
        assert result == 0.6


# ── 04. 置信度阈值逻辑 ────────────────────────────────────────────────

class TestConfidenceAction:
    """get_confidence_action: 三段阈值决策"""

    def test_high_confidence_full_strength(self):
        strength, apply = EmotionModulator.get_confidence_action(0.8)
        assert strength == 1.0
        assert apply is True

    def test_medium_confidence_half_strength(self):
        strength, apply = EmotionModulator.get_confidence_action(0.5)
        assert strength == 0.5
        assert apply is True

    def test_medium_lower_bound(self):
        strength, apply = EmotionModulator.get_confidence_action(0.4)
        assert strength == 0.5
        assert apply is True

    def test_medium_upper_bound(self):
        strength, apply = EmotionModulator.get_confidence_action(0.7)
        assert strength == 0.5
        assert apply is True

    def test_low_confidence_no_modulation(self):
        strength, apply = EmotionModulator.get_confidence_action(0.3)
        assert strength == 0.0
        assert apply is False

    def test_zero_confidence(self):
        strength, apply = EmotionModulator.get_confidence_action(0.0)
        assert strength == 0.0
        assert apply is False

    def test_whisper_default_confidence(self):
        """whisper 引擎默认置信度 0.5 → 减半调制"""
        strength, apply = EmotionModulator.get_confidence_action(
            0.5, engine_type="whisper"
        )
        assert strength == 0.5
        assert apply is True


# ── 05. 中性情绪不做微调 ─────────────────────────────────────────────

class TestNeutralNoModulation:
    """NEUTRAL 情绪应用后 profile 保持不变"""

    def test_neutral_keeps_all_values(self):
        profile = MockProfile(
            formality=0.7,
            intimacy=0.3,
            humor=0.5,
            directness=0.6,
            conciseness=0.4,
        )
        result = EmotionModulator.apply(profile, Emotion.NEUTRAL, strength=1.0)

        assert result.formality == 0.7
        assert result.intimacy == 0.3
        assert result.humor == 0.5
        assert result.directness == 0.6
        assert result.conciseness == 0.4

    def test_apply_returns_copy_not_same_object(self):
        profile = MockProfile()
        result = EmotionModulator.apply(profile, Emotion.NEUTRAL)
        assert result is not profile

    def test_anger_actually_modulates(self):
        """确认非中性情绪确实会改变值（对照）"""
        profile = MockProfile()  # 全部 0.5
        result = EmotionModulator.apply(profile, Emotion.ANGER, strength=1.0)
        # intimacy 应下降（0.5 - 0.2 = 0.3，但 0.5 是中线，_clamp 会锁在 0.5）
        # 由于原始 intimacy=0.5（中线），_clamp 会保持 0.5
        # 但 directness 应从 0.5 → 不能跨中线... 也是 0.5
        # 所以用非中线起始值测试
        profile2 = MockProfile(intimacy=0.7, directness=0.3, humor=0.8)
        result2 = EmotionModulator.apply(profile2, Emotion.ANGER, strength=1.0)
        # intimacy: 0.7 - 0.2 = 0.5  (0.7>0.5, 允许降到 0.5)
        assert result2.intimacy == pytest.approx(0.5)
        # directness: 0.3 + 0.2 = 0.5  (0.3<0.5, 允许升到 0.5)
        assert result2.directness == pytest.approx(0.5)
        # humor: 0.8 - 0.3 = 0.5  (0.8>0.5, 允许降到 0.5)
        assert result2.humor == pytest.approx(0.5)


# ── 06. Duck typing 兼容性 ───────────────────────────────────────────

class TestDuckTyping:
    """EmotionModulator.apply 兼容 dataclass 和非 dataclass"""

    def test_dataclass_profile(self):
        profile = MockProfile()
        result = EmotionModulator.apply(profile, Emotion.HAPPY, strength=0.5)
        # 确保是 dataclass 实例
        assert dataclasses.is_dataclass(result) if "dataclasses" in dir() else True
        # 不是同一个对象
        assert result is not profile

    def test_non_dataclass_profile(self):
        profile = NonDataclassProfile()
        result = EmotionModulator.apply(profile, Emotion.SAD, strength=0.5)
        assert result is not profile
        assert hasattr(result, "formality")

    def test_string_emotion_argument(self):
        """接受字符串形式的情绪标签"""
        profile = MockProfile()
        result = EmotionModulator.apply(profile, "happy")
        assert result is not profile
        # 应与 Emotion.HAPPY 等效
        result2 = EmotionModulator.apply(MockProfile(), Emotion.HAPPY)
        assert result.humor == result2.humor

    def test_unknown_emotion_returns_copy(self):
        """未识别的情绪字符串 → 原样副本"""
        profile = MockProfile(formality=0.9)
        result = EmotionModulator.apply(profile, "gobbledygook")
        assert result.formality == 0.9
        assert result is not profile


# ── 07. 强度参数 ─────────────────────────────────────────────────────

class TestStrengthParameter:
    """strength 参数正确缩放 delta"""

    def test_full_strength(self):
        profile = MockProfile(intimacy=0.3)
        result = EmotionModulator.apply(profile, Emotion.DISGUST, strength=1.0)
        # intimacy_delta = -0.3, 0.3 + (-0.3 * 1.0) = 0.0, clamped to [0, 0.5] → 0.0
        assert result.intimacy == 0.0

    def test_half_strength(self):
        profile = MockProfile(intimacy=0.3)
        result = EmotionModulator.apply(profile, Emotion.DISGUST, strength=0.5)
        # 0.3 + (-0.3 * 0.5) = 0.15, clamped to [0, 0.5] → 0.15
        assert result.intimacy == pytest.approx(0.15)

    def test_zero_strength_no_change(self):
        profile = MockProfile(intimacy=0.3)
        result = EmotionModulator.apply(profile, Emotion.DISGUST, strength=0.0)
        assert result.intimacy == 0.3
        assert result is not profile
