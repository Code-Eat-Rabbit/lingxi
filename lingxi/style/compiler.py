"""
灵犀输入 — StylePromptCompiler

将 StyleProfile + 情绪编译为 LLM System Prompt (XML 格式)。
严格遵循规格文档 §4.1 和 §4.2。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from lingxi.style.profile import (
    StyleProfile,
    AddressForm,
    ClosingStyle,
    Punctuation,
    PersonForm,
)
from lingxi.engine.emotion import (
    Emotion,
    EmotionModulation,
    EMOTION_MODULATION_MAP,
)

# ---------------------------------------------------------------------------
# 维度 → 自然语言映射表 (§4.2)
# ---------------------------------------------------------------------------

# 5 维度 × 4 级别 = 20 种描述
_DIMENSION_TEXTS: dict[str, dict[str, str]] = {
    "formality": {
        "low":      "极口语化，可使用网络用语、方言、语气词",
        "mid_low":  "偏口语化，可适度使用口语和日常表达",
        "mid_high": "偏正式，用词规范，避免口语化表达",
        "high":     "高度正式书面语，敬语，不使用任何口语",
    },
    "intimacy": {
        "low":      "保持距离，不表达情感",
        "mid_low":  "礼貌疏离，适度表达尊重",
        "mid_high": "友好亲切，表达关心和温暖",
        "high":     "极度亲密，可使用爱称、emoji、情感化表达",
    },
    "humor": {
        "low":      "严肃正经，绝不玩笑",
        "mid_low":  "偏严肃，偶尔可适当轻松",
        "mid_high": "偏诙谐，适度使用幽默和轻松表达",
        "high":     "极度诙谐，可使用比喻、自嘲、梗、表情包语言",
    },
    "directness": {
        "low":      "极度委婉，多层铺垫，商询语气",
        "mid_low":  "偏委婉，适当铺垫，建议语气",
        "mid_high": "偏直接，开门见山，陈述语气",
        "high":     "极度直接，无铺垫，命令式",
    },
    "conciseness": {
        "low":      "详尽解释，提供背景和上下文",
        "mid_low":  "偏详细，适度展开说明",
        "mid_high": "偏简洁，去除冗余，聚焦要点",
        "high":     "极简，仅核心信息，可用短语代替句子",
    },
}

# 维度 → XML 标签名映射
_DIMENSION_TAGS: dict[str, str] = {
    "formality":    "formality",
    "intimacy":     "intimacy",
    "humor":        "humor",
    "directness":   "directness",
    "conciseness":  "conciseness",
}


def _level_from_value(value: float) -> str:
    """根据维度值返回四级区间标签。

    区间划分（含右端点）：
        [0.0, 0.2] → "low"
        (0.2, 0.5] → "mid_low"
        (0.5, 0.7] → "mid_high"
        (0.7, 1.0] → "high"
    """
    if value <= 0.2:
        return "low"
    elif value <= 0.5:
        return "mid_low"
    elif value <= 0.7:
        return "mid_high"
    else:
        return "high"


# ---------------------------------------------------------------------------
# StylePromptCompiler
# ---------------------------------------------------------------------------

@dataclass
class StylePromptCompiler:
    """将 StyleProfile + 情绪编译为 LLM System Prompt (XML 格式)。"""

    language: str = "zh-CN"

    # ── 主编译入口 ──────────────────────────────────────────────────

    def compile(
        self,
        style: StyleProfile,
        emotion: Emotion = Emotion.NEUTRAL,
        emotion_strength: float = 0.0,
    ) -> str:
        """编译完整 XML prompt。

        Args:
            style:           风格配置画像。
            emotion:         检测到的情绪标签。
            emotion_strength: 情绪调制强度 (0.0 ~ 1.0)。

        Returns:
            格式化的 XML 字符串，可作为 LLM System Prompt。
        """
        active_emotion = emotion_strength > 0.0
        modulation: Optional[EmotionModulation] = None

        if active_emotion:
            modulation = EMOTION_MODULATION_MAP.get(emotion)

        parts: list[str] = []

        # --- session_config ---
        parts.append(self._compile_session_config())

        # --- voice_style_profile ---
        parts.append("<voice_style_profile>")

        # dimensions
        parts.append(self.compile_dimensions_xml(style))

        # scenario
        scenario = self.compile_scenario_xml(style)
        if scenario:
            parts.append(scenario)

        # emotion_override
        parts.append(
            self.compile_emotion_xml(
                modulation=modulation,
                active=active_emotion,
            )
        )

        parts.append("</voice_style_profile>")

        # --- rewrite_rules ---
        emoji_allowed: Optional[bool] = None
        if modulation is not None and active_emotion:
            emoji_allowed = modulation.emoji_allowed
        parts.append(self.get_rewrite_rules(style, emoji_allowed=emoji_allowed))

        return "\n".join(parts) + "\n"

    # ── session_config ──────────────────────────────────────────────

    def _compile_session_config(self) -> str:
        """生成 <session_config> XML 块。"""
        return (
            "<session_config>\n"
            f"  <language>{self.language}</language>\n"
            "  <output_modality>text</output_modality>\n"
            "</session_config>"
        )

    # ── 维度文本映射 ────────────────────────────────────────────────

    @staticmethod
    def dimension_to_text(dimension: str, value: float) -> str:
        """将维度值映射为自然语言描述。

        四级区间：0.0-0.2 低, 0.2-0.5 中低, 0.5-0.7 中高, 0.7-1.0 高。
        每个维度的四级描述按 spec §4.2 表格。

        Args:
            dimension: 维度名称 (formality/intimacy/humor/directness/conciseness)
            value:     维度值 [0.0, 1.0]

        Returns:
            自然语言描述文本。

        Raises:
            KeyError: 维度名称不合法。
        """
        level = _level_from_value(value)
        try:
            return _DIMENSION_TEXTS[dimension][level]
        except KeyError:
            raise KeyError(
                f"未知维度: {dimension!r}，"
                f"合法值: {', '.join(sorted(_DIMENSION_TEXTS.keys()))}"
            )

    # ── dimensions XML ──────────────────────────────────────────────

    @staticmethod
    def compile_dimensions_xml(style: StyleProfile) -> str:
        """生成 <dimensions> XML 块。

        遍历五个核心维度，为每个维度生成带有 level 属性和
        自然语言描述的 <dimension> 标签。

        Returns:
            缩进的 <dimensions>...</dimensions> XML 字符串。
        """
        lines: list[str] = ["  <dimensions>"]

        for dim_name, tag_name in _DIMENSION_TAGS.items():
            value: float = getattr(style, dim_name, 0.5)
            text = StylePromptCompiler.dimension_to_text(dim_name, value)
            lines.append(f'    <{tag_name} level="{value:.2f}">{text}</{tag_name}>')

        lines.append("  </dimensions>")
        return "\n".join(lines)

    # ── scenario XML ────────────────────────────────────────────────

    @staticmethod
    def compile_scenario_xml(style: StyleProfile) -> str:
        """生成 <scenario> XML 块。

        仅在对应字段非 None 时包含标签。覆盖：
        - address_form (称呼方式)
        - closing_style (结尾风格)
        - punctuation   (标点风格)
        - person_form   (第一人称)

        Returns:
            如果至少有一个字段非 None 则返回缩进的 XML 字符串，
            否则返回空字符串。
        """
        fields: list[tuple[str, Optional[object]]] = [
            ("address_form",  style.address_form),
            ("closing_style", style.closing_style),
            ("punctuation",   style.punctuation),
            ("person_form",   style.person_form),
        ]

        active = [(tag, val) for tag, val in fields if val is not None]
        if not active:
            return ""

        lines: list[str] = ["  <scenario>"]
        for tag, val in active:
            # Enum 成员取 .value 得到中文显示名
            text: str = val.value if hasattr(val, "value") else str(val)
            lines.append(f"    <{tag}>{text}</{tag}>")
        lines.append("  </scenario>")

        return "\n".join(lines)

    # ── emotion_override XML ────────────────────────────────────────

    @staticmethod
    def compile_emotion_xml(
        modulation: Optional[EmotionModulation],
        active: bool,
    ) -> str:
        """生成 <emotion_override> XML 块。

        Args:
            modulation: 情绪调制参数（可为 None）。
            active:     是否激活情绪微调。

        Returns:
            <emotion_override active="true|false">...</emotion_override>
        """
        active_str = "true" if active else "false"

        if active and modulation is not None and modulation.special_instruction:
            return (
                f'  <emotion_override active="{active_str}">\n'
                f"    {modulation.special_instruction}\n"
                f"  </emotion_override>"
            )
        else:
            return f'  <emotion_override active="{active_str}" />'

    # ── rewrite_rules XML ───────────────────────────────────────────

    @staticmethod
    def get_rewrite_rules(
        style: StyleProfile,
        emoji_allowed: Optional[bool] = None,
    ) -> str:
        """生成 <rewrite_rules> XML 块。

        - humor > 0.7 时允许 emoji（除非 emoji_allowed 显式覆盖）。
        - emoji_allowed=False 时在规则 5 中注明"禁止使用 emoji"。

        Args:
            style:         风格配置画像。
            emoji_allowed: 显式覆盖 emoji 许可。None 时根据 humor 判断。

        Returns:
            <rewrite_rules>...</rewrite_rules> XML 字符串。
        """
        if emoji_allowed is None:
            emoji_allowed = style.humor > 0.7

        emoji_rule = (
            "允许使用 emoji 增强表达"
            if emoji_allowed
            else "禁止使用 emoji"
        )

        rules = [
            "1. 必须保留原始口述的核心信息，不得添加虚构内容",
            "2. 按 voice_style_profile 的要求调整语气、用词和句式",
            "3. 保守纠错策略：仅修复明显的语音识别错误",
            "4. 中英混杂处理：英文技术术语保持原样",
            f"5. 输出纯文本，不得包含 markdown；{emoji_rule}",
            "6. 语言一致性：输出语言必须与 session_config.language 一致",
        ]

        lines = ["<rewrite_rules>"]
        for rule in rules:
            lines.append(f"  {rule}")
        lines.append("</rewrite_rules>")

        return "\n".join(lines)
