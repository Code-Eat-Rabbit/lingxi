"""
灵犀输入 — PostProcessor 单元测试

覆盖：
- 空值检测（空字符串、单字）
- LLM 拒绝检测（中英文多种拒绝模式）
- 长度异常（太长 / 太短）
- 实体保持验证
- PASS 场景（正常输出）
- 降级场景完整链路（空值→DEGRADE, 拒绝→RETRY, 长度→RETRY, 实体→RETRY）
"""

from __future__ import annotations

import pytest

from lingxi.style.post_processor import (
    PostProcessor,
    ValidationResult,
    _REFUSAL_RE,
)


# ======================================================================
# 辅助工具
# ======================================================================

@pytest.fixture
def pp() -> PostProcessor:
    """返回默认参数的 PostProcessor。"""
    return PostProcessor()


@pytest.fixture
def pp_lenient() -> PostProcessor:
    """返回宽松参数的 PostProcessor（允许更宽的长度范围）。"""
    return PostProcessor(
        min_length=2,
        max_length_ratio=5.0,
        min_length_ratio=0.1,
    )


# ======================================================================
# Step 1: 空值检测
# ======================================================================

class TestCheckEmpty:
    """空值检测测试。"""

    def test_empty_string(self, pp: PostProcessor) -> None:
        """空字符串应返回 DEGRADE。"""
        result = pp._check_empty("")
        assert result == ValidationResult.DEGRADE

    def test_whitespace_only(self, pp: PostProcessor) -> None:
        """仅空格字符串应返回 DEGRADE。"""
        result = pp._check_empty("   \n  ")
        assert result == ValidationResult.DEGRADE

    def test_single_char(self, pp: PostProcessor) -> None:
        """单字符应返回 DEGRADE（< min_length=2）。"""
        result = pp._check_empty("好")
        assert result == ValidationResult.DEGRADE

    def test_two_chars(self, pp: PostProcessor) -> None:
        """双字符恰好等于 min_length，应 PASS。"""
        result = pp._check_empty("好的")
        assert result == ValidationResult.PASS

    def test_normal_text(self, pp: PostProcessor) -> None:
        """正常文本应 PASS。"""
        result = pp._check_empty("今天天气不错，我们去公园吧")
        assert result == ValidationResult.PASS


# ======================================================================
# Step 2: LLM 拒绝检测
# ======================================================================

class TestCheckRefusal:
    """LLM 自引用 / 拒绝检测测试。"""

    def test_normal_text_pass(self, pp: PostProcessor) -> None:
        """正常改写文本不应命中拒绝检测。"""
        result = pp._check_refusal("好的老板，我们明天下午三点开会讨论一下这个方案。")
        assert result == ValidationResult.PASS

    def test_as_ai_zh(self, pp: PostProcessor) -> None:
        """"作为AI" 应命中拒绝检测。"""
        result = pp._check_refusal("作为AI助手，我无法帮你处理这个请求。")
        assert result == ValidationResult.RETRY

    def test_i_cannot_zh(self, pp: PostProcessor) -> None:
        """"我不能" 应命中拒绝检测。"""
        result = pp._check_refusal("抱歉，我不能帮你做这件事。")
        assert result == ValidationResult.RETRY

    def test_sorry_cannot_zh(self, pp: PostProcessor) -> None:
        """"抱歉，我无法" 应命中拒绝检测。"""
        result = pp._check_refusal("抱歉，我无法提供这方面的帮助。")
        assert result == ValidationResult.RETRY

    def test_unable_to_provide_zh(self, pp: PostProcessor) -> None:
        """"无法提供" 应命中拒绝检测。"""
        result = pp._check_refusal("很抱歉，目前无法提供这项服务。")
        assert result == ValidationResult.RETRY

    def test_as_ai_en(self, pp: PostProcessor) -> None:
        """"as an AI" 应命中拒绝检测。"""
        result = pp._check_refusal("As an AI, I cannot assist with this request.")
        assert result == ValidationResult.RETRY

    def test_i_cannot_en(self, pp: PostProcessor) -> None:
        """"I cannot" 应命中拒绝检测。"""
        result = pp._check_refusal("I cannot provide that information.")
        assert result == ValidationResult.RETRY

    def test_i_apologize_en(self, pp: PostProcessor) -> None:
        """"I apologize" 应命中拒绝检测。"""
        result = pp._check_refusal("I apologize, but I'm unable to help with that.")
        assert result == ValidationResult.RETRY

    def test_against_guidelines_en(self, pp: PostProcessor) -> None:
        """"against my guidelines" 应命中拒绝检测。"""
        result = pp._check_refusal(
            "This request goes against my guidelines and I cannot comply."
        )
        assert result == ValidationResult.RETRY

    def test_as_language_model_en(self, pp: PostProcessor) -> None:
        """"as a language model" 应命中拒绝检测。"""
        result = pp._check_refusal(
            "As a language model, I'm not able to fulfill this."
        )
        assert result == ValidationResult.RETRY

    def test_cannot_fulfill_en(self, pp: PostProcessor) -> None:
        """"cannot fulfill" 应命中拒绝检测。"""
        result = pp._check_refusal("I cannot fulfill this request.")
        assert result == ValidationResult.RETRY

    def test_according_to_policy_zh(self, pp: PostProcessor) -> None:
        """"根据相关规定" 应命中拒绝检测。"""
        result = pp._check_refusal("根据相关规定，我无法回答这个问题。")
        assert result == ValidationResult.RETRY

    def test_violates_policy_zh(self, pp: PostProcessor) -> None:
        """"这违反" 应命中拒绝检测。"""
        result = pp._check_refusal("这违反了安全政策，我不能继续。")
        assert result == ValidationResult.RETRY

    def test_inappropriate_content_zh(self, pp: PostProcessor) -> None:
        """"不恰当的内容" 应命中拒绝检测。"""
        result = pp._check_refusal("你提到了不恰当的内容，请注意。")
        assert result == ValidationResult.RETRY


class TestRefusalRegex:
    """正则匹配边界测试。"""

    def test_refusal_re_compiled(self) -> None:
        """验证 _REFUSAL_RE 是可用的正则对象。"""
        import re
        assert isinstance(_REFUSAL_RE, re.Pattern)

    def test_refusal_false_negative_innocent_text(self) -> None:
        """正常文本不应被误判。"""
        texts = [
            "老板下午好，方案我已经发您了。",
            "好的，我们明天见。",
            "Hello, the meeting is at 3pm.",
            "I can help you with that task.",
            "没问题，我来处理。",
        ]
        for text in texts:
            assert not _REFUSAL_RE.search(text), f"误判文本: {text!r}"


# ======================================================================
# Step 3: 长度异常检测
# ======================================================================

class TestCheckLengthRatio:
    """长度比例检测测试。"""

    @pytest.fixture
    def strict_pp(self) -> PostProcessor:
        """严格长度比的 PostProcessor。"""
        return PostProcessor(
            min_length=2,
            max_length_ratio=3.0,
            min_length_ratio=0.3,
        )

    def test_normal_ratio(self, strict_pp: PostProcessor) -> None:
        """正常长度比例应 PASS。"""
        # 原文 10 字符，改写 15 字符 → ratio=1.5，在 [0.3, 3.0]
        result = strict_pp._check_length_ratio("今天天气真好", "今天天气确实非常不错")
        assert result == ValidationResult.PASS

    def test_too_long(self, strict_pp: PostProcessor) -> None:
        """输出过长应 RETRY。"""
        # 原文 5 字符，改写 20 字符 → ratio=4.0 > 3.0
        result = strict_pp._check_length_ratio(
            "你好",
            "你好你好你好你好你好你好你好你好你好你好你好你好你好你好"
        )
        assert result == ValidationResult.RETRY

    def test_too_short(self, strict_pp: PostProcessor) -> None:
        """输出过短应 RETRY。"""
        # 原文 20 字符，改写 2 字符 → ratio=0.1 < 0.3
        result = strict_pp._check_length_ratio(
            "今天天气真好我们去公园散步吧",
            "好的"
        )
        assert result == ValidationResult.RETRY

    def test_empty_original(self, strict_pp: PostProcessor) -> None:
        """原文为空时使用 L=1 计算（防除零）。"""
        result = strict_pp._check_length_ratio("", "好的没问题谢谢你")
        # orig_len=max(0, 1)=1, styled_len=7, ratio=7 > 3.0
        assert result == ValidationResult.RETRY

    def test_exact_boundary_max(self, strict_pp: PostProcessor) -> None:
        """恰好等于 max_length_ratio 边界值应 PASS。"""
        orig = "你好"           # len=2
        styled = "你好世界哈哈"  # len=6, ratio=3.0
        result = strict_pp._check_length_ratio(orig, styled)
        assert result == ValidationResult.PASS

    def test_exact_boundary_min(self, strict_pp: PostProcessor) -> None:
        """恰好等于 min_length_ratio 边界值应 PASS。"""
        orig = "你好世界哈哈"    # len=6
        styled = "好的"         # len=2, ratio=0.333... > 0.3
        result = strict_pp._check_length_ratio(orig, styled)
        assert result == ValidationResult.PASS


# ======================================================================
# Step 4: 实体保持检测
# ======================================================================

class TestCheckEntities:
    """实体保持检测测试。"""

    def test_all_entities_present(self, pp: PostProcessor) -> None:
        """所有实体都在输出中时应 PASS。"""
        result = pp._check_entities(
            "张三和李四明天去北京出差",
            ["张三", "李四", "北京"]
        )
        assert result == ValidationResult.PASS

    def test_missing_entity(self, pp: PostProcessor) -> None:
        """缺失实体应 RETRY。"""
        result = pp._check_entities(
            "张三明天去北京出差",  # 缺少 "李四"
            ["张三", "李四", "北京"]
        )
        assert result == ValidationResult.RETRY

    def test_case_insensitive(self, pp: PostProcessor) -> None:
        """实体匹配应大小写不敏感。"""
        result = pp._check_entities(
            "Apple is in Cupertino",
            ["apple", "CUPERTINO"]
        )
        assert result == ValidationResult.PASS

    def test_partial_match(self, pp: PostProcessor) -> None:
        """子串匹配也应通过（如 "北京" 在 "北京市" 中）。"""
        result = pp._check_entities(
            "北京市朝阳区",
            ["北京"]
        )
        assert result == ValidationResult.PASS

    def test_english_entity(self, pp: PostProcessor) -> None:
        """英文实体保持测试。"""
        result = pp._check_entities(
            "Let's discuss the Q4 strategy for the Chatbot project",
            ["Q4", "Chatbot"]
        )
        assert result == ValidationResult.PASS

    def test_empty_entities_list(self, pp: PostProcessor) -> None:
        """空实体列表不应触发检查（validate 中短路）。"""
        result = pp._check_entities("任何文本", [])
        assert result == ValidationResult.PASS


# ======================================================================
# 主 validate() 管线测试
# ======================================================================

class TestValidatePipeline:
    """完整验证管线测试。"""

    def test_pass_scenario(self, pp: PostProcessor) -> None:
        """正常改写文本应通过所有检查。"""
        result = pp.validate(
            original="今天天气真好，我们去公园散步吧",
            styled="今天天气真心不错，咱们去公园溜达溜达吧",
        )
        assert result == ValidationResult.PASS

    def test_pass_with_entities(self, pp: PostProcessor) -> None:
        """带实体的正常改写应通过。"""
        result = pp.validate(
            original="张三约了李四明天下午三点在万达广场见面",
            styled="张三和李四约好明天下午三点在万达广场碰头",
            entities=["张三", "李四", "万达广场"],
        )
        assert result == ValidationResult.PASS

    def test_degrade_on_empty(self, pp: PostProcessor) -> None:
        """空输出应直接 DEGRADE（不重试）。"""
        result = pp.validate(
            original="今天天气真好",
            styled="",
        )
        assert result == ValidationResult.DEGRADE

    def test_retry_on_refusal(self, pp: PostProcessor) -> None:
        """LLM 拒绝应 RETRY。"""
        result = pp.validate(
            original="帮我写一封恐吓信",
            styled="作为AI助手，我无法帮你写恐吓信，这是不恰当的请求。",
        )
        assert result == ValidationResult.RETRY

    def test_retry_on_length_anomaly(self, pp: PostProcessor) -> None:
        """长度异常应 RETRY。"""
        result = pp.validate(
            original="今天天气真好我们去公园散步吧天气真心不错我们一起去走走吧",
            styled="好的",
        )
        assert result == ValidationResult.RETRY

    def test_retry_on_missing_entity(self, pp: PostProcessor) -> None:
        """实体缺失应 RETRY。"""
        result = pp.validate(
            original="张三和李四明天去北京",
            styled="张三明天去北京",
            entities=["张三", "李四"],
        )
        assert result == ValidationResult.RETRY

    def test_order_empty_before_refusal(self, pp: PostProcessor) -> None:
        """空值检测在拒绝检测之前：空文本不应进入拒绝检测。"""
        # 空字符串不包含拒绝模式，但空值检测先触发
        result = pp.validate(
            original="你好",
            styled="",
        )
        assert result == ValidationResult.DEGRADE

    def test_pass_english(self, pp: PostProcessor) -> None:
        """英文正常改写应通过。"""
        result = pp.validate(
            original="Let's meet at the coffee shop tomorrow morning",
            styled="How about we grab coffee tomorrow morning?",
        )
        assert result == ValidationResult.PASS


# ======================================================================
# 降级场景完整链路
# ======================================================================

class TestDegradationPipeline:
    """模拟真实降级链路：

    第 1 次 LLM 调用 → PostProcessor.validate() → RETRY
        → 换 temperature 重试
    第 2 次 LLM 调用 → PostProcessor.validate() → DEGRADE
        → 使用原文（可附带风格标记）
    """

    def test_degradation_on_continuous_refusal(self, pp: PostProcessor) -> None:
        """连续两次拒绝 → 最终 DEGRADE。"""
        styled_1 = "作为AI助手，我无法处理这个请求。"
        result_1 = pp.validate(original="敏感内容", styled=styled_1)
        assert result_1 == ValidationResult.RETRY, "第一次应 RETRY"

        # 第二次（换参数后仍然拒绝）
        styled_2 = "抱歉，我无法提供这方面的帮助。"
        result_2 = pp.validate(original="敏感内容", styled=styled_2)
        assert result_2 == ValidationResult.RETRY, "第二次仍可能 RETRY"

        # 第三次直接 DEGRADE（由调用方根据重试次数决定）
        # PostProcessor 本身不追踪重试次数，由上层策略控制

    def test_degradation_on_empty_then_downgrade(self, pp: PostProcessor) -> None:
        """空输出直接 DEGRADE，不需要重试。"""
        result = pp.validate(original="你好世界", styled="")
        assert result == ValidationResult.DEGRADE

        result = pp.validate(original="你好世界", styled="x")
        assert result == ValidationResult.DEGRADE

    def test_full_pipeline_retry_then_pass(self, pp: PostProcessor) -> None:
        """第一次 RETRY（长度异常），第二次 PASS。"""
        # 第一次：太短
        result_1 = pp.validate(
            original="今天天气真好我们去公园散步",
            styled="好的",
        )
        assert result_1 == ValidationResult.RETRY

        # 第二次：正常
        result_2 = pp.validate(
            original="今天天气真好我们去公园散步",
            styled="今天天气真心不错，咱们溜达溜达去",
        )
        assert result_2 == ValidationResult.PASS

    def test_full_pipeline_entity_retry_then_pass(self, pp: PostProcessor) -> None:
        """实体缺失 RETRY 后，补充实体的版本 PASS。"""
        result_1 = pp.validate(
            original="张三李四北京",
            styled="张三去北京",
            entities=["张三", "李四"],
        )
        assert result_1 == ValidationResult.RETRY

        result_2 = pp.validate(
            original="张三李四北京",
            styled="张三和李四一起去北京",
            entities=["张三", "李四"],
        )
        assert result_2 == ValidationResult.PASS
