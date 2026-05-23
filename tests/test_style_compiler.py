"""
灵犀输入 — StylePromptCompiler 单元测试

覆盖：
- 五维参数 → XML prompt 编译正确性（完整 XML 结构验证）
- 边界值 0.0/0.5/1.0 各维度的描述文本
- 场景模板字段 None 时不在 XML 中出现
- 情绪注入时 special_instruction 在 XML 中出现
- emotion_strength=0 时 emotion_override 的 active="false"
"""

from __future__ import annotations

import pytest

from lingxi.style.profile import (
    StyleProfile,
    AddressForm,
    ClosingStyle,
    Punctuation,
    PersonForm,
    ProfanityLevel,
    StyleProfileKind,
)
from lingxi.style.compiler import (
    StylePromptCompiler,
    _level_from_value,
    _DIMENSION_TEXTS,
)
from lingxi.engine.emotion import (
    Emotion,
    EmotionModulation,
    EMOTION_MODULATION_MAP,
)


# ======================================================================
# 辅助工具
# ======================================================================

def _xml_has_tag(xml: str, tag: str) -> bool:
    """检查 XML 字符串中是否包含指定的开始标签。"""
    return f"<{tag}" in xml


def _xml_tag_content(xml: str, tag: str) -> str:
    """提取 XML 中指定标签的文本内容（简单提取，不解析嵌套）。"""
    start = xml.find(f"<{tag}")
    if start == -1:
        return ""
    # 跳到 > 之后
    gt = xml.find(">", start)
    if gt == -1:
        return ""
    end = xml.find(f"</{tag}>", gt)
    if end == -1:
        # 自闭合标签
        return ""
    return xml[gt + 1 : end]


def _make_profile(**overrides) -> StyleProfile:
    """快速创建测试用 StyleProfile。"""
    defaults = dict(
        id="test-default",
        name="测试风格",
        kind=StyleProfileKind.CUSTOM,
        formality=0.5,
        intimacy=0.5,
        humor=0.3,
        directness=0.7,
        conciseness=0.6,
        address_form=None,
        closing_style=None,
        punctuation=None,
        person_form=None,
        profanity_filter=None,
    )
    defaults.update(overrides)
    return StyleProfile(**defaults)


# ======================================================================
# _level_from_value 区间划分
# ======================================================================

class TestLevelFromValue:
    """四级区间划分正确性。"""

    def test_low_boundaries(self) -> None:
        assert _level_from_value(0.0) == "low"
        assert _level_from_value(0.1) == "low"
        assert _level_from_value(0.2) == "low"

    def test_mid_low_boundaries(self) -> None:
        assert _level_from_value(0.21) == "mid_low"
        assert _level_from_value(0.3) == "mid_low"
        assert _level_from_value(0.5) == "mid_low"

    def test_mid_high_boundaries(self) -> None:
        assert _level_from_value(0.51) == "mid_high"
        assert _level_from_value(0.6) == "mid_high"
        assert _level_from_value(0.7) == "mid_high"

    def test_high_boundaries(self) -> None:
        assert _level_from_value(0.71) == "high"
        assert _level_from_value(0.8) == "high"
        assert _level_from_value(1.0) == "high"


# ======================================================================
# dimension_to_text 描述文本
# ======================================================================

class TestDimensionToText:
    """dimension_to_text 边界值描述验证。"""

    # --- 正式度 ---

    def test_formality_low(self) -> None:
        text = StylePromptCompiler.dimension_to_text("formality", 0.0)
        assert "极口语" in text

    def test_formality_mid(self) -> None:
        text = StylePromptCompiler.dimension_to_text("formality", 0.5)
        assert "偏口语" in text

    def test_formality_high(self) -> None:
        text = StylePromptCompiler.dimension_to_text("formality", 1.0)
        assert "高度正式" in text
        assert "不使用任何口语" in text

    # --- 亲密度 ---

    def test_intimacy_low(self) -> None:
        text = StylePromptCompiler.dimension_to_text("intimacy", 0.0)
        assert "保持距离" in text

    def test_intimacy_mid(self) -> None:
        text = StylePromptCompiler.dimension_to_text("intimacy", 0.5)
        assert "礼貌疏离" in text

    def test_intimacy_high(self) -> None:
        text = StylePromptCompiler.dimension_to_text("intimacy", 1.0)
        assert "极度亲密" in text
        assert "emoji" in text

    # --- 幽默度 ---

    def test_humor_low(self) -> None:
        text = StylePromptCompiler.dimension_to_text("humor", 0.0)
        assert "严肃正经" in text
        assert "绝不玩笑" in text

    def test_humor_mid(self) -> None:
        text = StylePromptCompiler.dimension_to_text("humor", 0.5)
        assert "偏严肃" in text

    def test_humor_high(self) -> None:
        text = StylePromptCompiler.dimension_to_text("humor", 1.0)
        assert "极度诙谐" in text
        assert "梗" in text

    # --- 直接度 ---

    def test_directness_low(self) -> None:
        text = StylePromptCompiler.dimension_to_text("directness", 0.0)
        assert "极度委婉" in text
        assert "商询语气" in text

    def test_directness_mid(self) -> None:
        text = StylePromptCompiler.dimension_to_text("directness", 0.5)
        assert "偏委婉" in text

    def test_directness_high(self) -> None:
        text = StylePromptCompiler.dimension_to_text("directness", 1.0)
        assert "极度直接" in text
        assert "命令式" in text

    # --- 简练度 ---

    def test_conciseness_low(self) -> None:
        text = StylePromptCompiler.dimension_to_text("conciseness", 0.0)
        assert "详尽解释" in text
        assert "背景" in text

    def test_conciseness_mid(self) -> None:
        text = StylePromptCompiler.dimension_to_text("conciseness", 0.5)
        assert "偏详细" in text

    def test_conciseness_high(self) -> None:
        text = StylePromptCompiler.dimension_to_text("conciseness", 1.0)
        assert "极简" in text
        assert "短语" in text

    # --- 错误处理 ---

    def test_invalid_dimension_raises(self) -> None:
        with pytest.raises(KeyError, match="未知维度"):
            StylePromptCompiler.dimension_to_text("nonexistent", 0.5)

    # --- 全覆盖：20 种描述均有值 ---

    def test_all_20_descriptions_exist(self) -> None:
        """5 维度 × 4 级别 = 20 种描述，全部非空。"""
        for dim_name in _DIMENSION_TEXTS:
            for level in ("low", "mid_low", "mid_high", "high"):
                text = _DIMENSION_TEXTS[dim_name][level]
                assert text, f"{dim_name}.{level} 描述为空"
                assert len(text) > 5, f"{dim_name}.{level} 描述过短: {text!r}"


# ======================================================================
# compile_dimensions_xml
# ======================================================================

class TestCompileDimensionsXml:
    """<dimensions> XML 块编译。"""

    def test_all_five_dimensions_present(self) -> None:
        profile = _make_profile(
            formality=0.9, intimacy=0.2, humor=0.0,
            directness=0.5, conciseness=0.7,
        )
        xml = StylePromptCompiler.compile_dimensions_xml(profile)

        assert "<dimensions>" in xml
        assert "</dimensions>" in xml
        for tag in ("formality", "intimacy", "humor", "directness", "conciseness"):
            assert f"<{tag} " in xml, f"缺少 <{tag}> 标签"
            assert f"</{tag}>" in xml, f"缺少 </{tag}> 闭合标签"

    def test_level_attributes(self) -> None:
        profile = _make_profile(formality=0.88, directness=0.12)
        xml = StylePromptCompiler.compile_dimensions_xml(profile)

        assert 'level="0.88"' in xml
        assert 'level="0.12"' in xml

    def test_level_two_decimal_places(self) -> None:
        """level 属性精确到两位小数。"""
        profile = _make_profile(formality=1.0, intimacy=0.0)
        xml = StylePromptCompiler.compile_dimensions_xml(profile)

        assert 'level="1.00"' in xml
        assert 'level="0.00"' in xml

    def test_descriptions_embedded(self) -> None:
        """描述文本嵌入在标签内部。"""
        profile = _make_profile(formality=0.95)
        xml = StylePromptCompiler.compile_dimensions_xml(profile)

        assert "高度正式" in xml
        assert "<formality " in xml


# ======================================================================
# compile_scenario_xml
# ======================================================================

class TestCompileScenarioXml:
    """<scenario> XML 块编译。"""

    def test_all_none_returns_empty(self) -> None:
        profile = _make_profile(
            address_form=None, closing_style=None,
            punctuation=None, person_form=None,
        )
        xml = StylePromptCompiler.compile_scenario_xml(profile)
        assert xml == ""

    def test_some_fields_present(self) -> None:
        profile = _make_profile(
            address_form=AddressForm.NIN,
            closing_style=None,
            punctuation=Punctuation.STRICT,
            person_form=None,
        )
        xml = StylePromptCompiler.compile_scenario_xml(profile)

        assert "<scenario>" in xml
        assert "</scenario>" in xml
        assert "<address_form>您</address_form>" in xml
        assert "<punctuation>严谨标点</punctuation>" in xml
        # None 字段不应出现
        assert "closing_style" not in xml
        assert "person_form" not in xml

    def test_all_fields_present(self) -> None:
        profile = _make_profile(
            address_form=AddressForm.QIN,
            closing_style=ClosingStyle.CASUAL,
            punctuation=Punctuation.RELAXED,
            person_form=PersonForm.ZAN,
        )
        xml = StylePromptCompiler.compile_scenario_xml(profile)

        assert "<address_form>亲</address_form>" in xml
        assert "<closing_style>😄/~</closing_style>" in xml
        assert "<punctuation>宽松标点</punctuation>" in xml
        assert "<person_form>咱</person_form>" in xml

    def test_minimal_preset_has_none_fields(self) -> None:
        """极简预设：address_form=None, person_form=None，不应出现。"""
        from lingxi.style.presets import MINIMAL

        xml = StylePromptCompiler.compile_scenario_xml(MINIMAL)
        assert "address_form" not in xml
        assert "person_form" not in xml
        assert "<scenario>" in xml  # closing_style 和 punctuation 存在
        assert "无结尾" in xml


# ======================================================================
# compile_emotion_xml
# ======================================================================

class TestCompileEmotionXml:
    """<emotion_override> XML 块编译。"""

    def test_inactive_no_modulation(self) -> None:
        xml = StylePromptCompiler.compile_emotion_xml(
            modulation=None, active=False,
        )
        assert 'active="false"' in xml
        assert "/>" in xml

    def test_inactive_with_modulation(self) -> None:
        """即使有 modulation，active=False 时也不输出 special_instruction。"""
        mod = EmotionModulation(special_instruction="注入情绪: 开心")
        xml = StylePromptCompiler.compile_emotion_xml(
            modulation=mod, active=False,
        )
        assert 'active="false"' in xml
        assert "注入情绪" not in xml

    def test_active_no_special_instruction(self) -> None:
        mod = EmotionModulation(special_instruction="")
        xml = StylePromptCompiler.compile_emotion_xml(
            modulation=mod, active=True,
        )
        assert 'active="true"' in xml
        assert "/>" in xml

    def test_active_with_special_instruction(self) -> None:
        mod = EmotionModulation(
            special_instruction="当前用户情绪激动，请使用短句和感叹号"
        )
        xml = StylePromptCompiler.compile_emotion_xml(
            modulation=mod, active=True,
        )
        assert 'active="true"' in xml
        assert "当前用户情绪激动" in xml
        assert "短句和感叹号" in xml

    def test_none_modulation_active_true(self) -> None:
        """modulation=None 但 active=True —— 不应崩溃。"""
        xml = StylePromptCompiler.compile_emotion_xml(
            modulation=None, active=True,
        )
        assert 'active="true"' in xml
        assert "/>" in xml


# ======================================================================
# get_rewrite_rules
# ======================================================================

class TestRewriteRules:
    """<rewrite_rules> XML 块编译。"""

    def test_all_six_rules_present(self) -> None:
        profile = _make_profile(humor=0.3)
        xml = StylePromptCompiler.get_rewrite_rules(profile)

        assert "<rewrite_rules>" in xml
        assert "</rewrite_rules>" in xml
        for i in range(1, 7):
            assert f"{i}." in xml, f"缺少规则 {i}"

    def test_humor_high_allows_emoji(self) -> None:
        profile = _make_profile(humor=0.9)
        xml = StylePromptCompiler.get_rewrite_rules(profile)
        assert "允许使用 emoji" in xml
        assert "禁止使用 emoji" not in xml

    def test_humor_low_forbids_emoji(self) -> None:
        profile = _make_profile(humor=0.1)
        xml = StylePromptCompiler.get_rewrite_rules(profile)
        assert "禁止使用 emoji" in xml

    def test_humor_exact_07(self) -> None:
        """humor=0.7 恰好等于阈值——应视为不高于 0.7。"""
        profile = _make_profile(humor=0.7)
        xml = StylePromptCompiler.get_rewrite_rules(profile)
        # humor > 0.7 才允许，0.7 正好不满足
        assert "禁止使用 emoji" in xml

    def test_emoji_allowed_explicit_override(self) -> None:
        """emoji_allowed 显式参数覆盖 humor 判断。"""
        profile = _make_profile(humor=0.1)  # 通常禁 emoji
        xml = StylePromptCompiler.get_rewrite_rules(
            profile, emoji_allowed=True,
        )
        assert "允许使用 emoji" in xml

        profile2 = _make_profile(humor=0.9)  # 通常允许 emoji
        xml2 = StylePromptCompiler.get_rewrite_rules(
            profile2, emoji_allowed=False,
        )
        assert "禁止使用 emoji" in xml2


# ======================================================================
# compile — 完整 XML Prompt 集成测试
# ======================================================================

class TestCompileIntegration:
    """compile() 方法端到端测试。"""

    compiler: StylePromptCompiler

    @pytest.fixture(autouse=True)
    def _setup(self) -> None:
        self.compiler = StylePromptCompiler(language="zh-CN")

    # --- 完整 XML 结构 ---

    def test_complete_xml_structure(self) -> None:
        """编译结果包含所有预期的顶级 XML 块。"""
        profile = _make_profile(
            formality=0.9, intimacy=0.2, humor=0.0,
            directness=0.5, conciseness=0.7,
            address_form=AddressForm.NIN,
            closing_style=ClosingStyle.FORMAL,
            punctuation=Punctuation.STRICT,
            person_form=PersonForm.WO,
        )
        xml = self.compiler.compile(profile)

        # 顶级块
        assert xml.startswith("<session_config>")
        assert "<voice_style_profile>" in xml
        assert "</voice_style_profile>" in xml
        assert "<rewrite_rules>" in xml
        assert "</rewrite_rules>" in xml

        # session_config 内容
        assert "<language>zh-CN</language>" in xml
        assert "<output_modality>text</output_modality>" in xml

        # dimensions
        assert "<dimensions>" in xml
        assert "</dimensions>" in xml

        # scenario
        assert "<scenario>" in xml
        assert "<address_form>您</address_form>" in xml

        # emotion_override (默认 inactive)
        assert "<emotion_override" in xml
        assert 'active="false"' in xml

        # 以换行结尾
        assert xml.endswith("\n")

    # --- 场景字段 None ---

    def test_scenario_all_none_not_in_xml(self) -> None:
        """所有场景字段为 None 时 <scenario> 不出现。"""
        profile = _make_profile()
        xml = self.compiler.compile(profile)
        assert "<scenario>" not in xml

    def test_scenario_partial_none(self) -> None:
        """部分场景字段为 None 时只出现非 None 的。"""
        profile = _make_profile(
            address_form=AddressForm.NI,
            closing_style=None,
            punctuation=None,
            person_form=None,
        )
        xml = self.compiler.compile(profile)
        assert "<scenario>" in xml
        assert "<address_form>你</address_form>" in xml
        assert "closing_style" not in xml
        assert "punctuation" not in xml
        assert "person_form" not in xml

    # --- 情绪注入 ---

    def test_emotion_strength_zero_inactive(self) -> None:
        """emotion_strength=0 → emotion_override active="false"。"""
        profile = _make_profile()
        xml = self.compiler.compile(
            profile,
            emotion=Emotion.ANGER,
            emotion_strength=0.0,
        )
        assert 'active="false"' in xml

    def test_emotion_strength_positive_active(self) -> None:
        """emotion_strength > 0 → emotion_override active="true"。"""
        profile = _make_profile()
        xml = self.compiler.compile(
            profile,
            emotion=Emotion.ANGER,
            emotion_strength=0.5,
        )
        assert 'active="true"' in xml

    def test_neutral_emotion_no_special_instruction(self) -> None:
        """NEUTRAL 情绪的 special_instruction 为空，不注入。"""
        profile = _make_profile()
        xml = self.compiler.compile(
            profile,
            emotion=Emotion.NEUTRAL,
            emotion_strength=0.8,
        )
        assert 'active="true"' in xml
        assert "/>" in xml.split("emotion_override")[-1]

    # --- 情绪调制 emoji_allowed 传递 ---

    def test_anger_emotion_forbids_emoji(self) -> None:
        """ANGER 情绪 emoji_allowed=False，即使 humor 高也应禁止。"""
        profile = _make_profile(humor=0.9)  # 通常允许 emoji
        xml = self.compiler.compile(
            profile,
            emotion=Emotion.ANGER,
            emotion_strength=0.6,
        )
        # ANGER 的 emoji_allowed=False
        assert "禁止使用 emoji" in xml

    def test_happy_emotion_allows_emoji(self) -> None:
        """HAPPY 情绪 emoji_allowed=True。"""
        profile = _make_profile(humor=0.3)  # 通常禁止 emoji
        xml = self.compiler.compile(
            profile,
            emotion=Emotion.HAPPY,
            emotion_strength=0.6,
        )
        # HAPPY 的 emoji_allowed=True
        assert "允许使用 emoji" in xml

    # --- 预置风格集成 ---

    def test_respectful_preset_compiles(self) -> None:
        from lingxi.style.presets import RESPECTFUL
        xml = self.compiler.compile(RESPECTFUL)
        assert "<session_config>" in xml
        assert "高度正式" in xml
        assert "<address_form>您</address_form>" in xml
        assert "<closing_style>此致敬礼</closing_style>" in xml

    def test_witty_preset_compiles(self) -> None:
        from lingxi.style.presets import WITTY
        xml = self.compiler.compile(WITTY)
        assert "极度诙谐" in xml
        assert "允许使用 emoji" in xml

    def test_minimal_preset_compiles(self) -> None:
        from lingxi.style.presets import MINIMAL
        xml = self.compiler.compile(MINIMAL)
        assert "极简" in xml
        # address_form/person_form 为 None，不出现
        assert "<address_form>" not in xml
        assert "<person_form>" not in xml


# ======================================================================
# language 自定义
# ======================================================================

class TestLanguage:
    """语言参数测试。"""

    def test_default_language(self) -> None:
        compiler = StylePromptCompiler()
        profile = _make_profile()
        xml = compiler.compile(profile)
        assert "<language>zh-CN</language>" in xml

    def test_custom_language(self) -> None:
        compiler = StylePromptCompiler(language="en-US")
        profile = _make_profile()
        xml = compiler.compile(profile)
        assert "<language>en-US</language>" in xml
