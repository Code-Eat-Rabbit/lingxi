"""
灵犀输入 — PostProcessor 输出验证器

验证管线（spec §4.4）：
  1. 空值检测（< 2 字符）
  2. LLM 自引用检测（"作为AI"、"我不能"等）
  3. 长度异常（0.3× ~ 3× 原文长度）
  4. 实体保持（关键实体必须在输出中出现）

降级策略：
  第一次失败 → RETRY（调用方可换 temperature 重试）
  第二次失败 → DEGRADE（注入原文+风格标记 → 纯原文）
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ValidationResult(Enum):
    """验证结果枚举。

    PASS     — 通过，可直接使用输出。
    RETRY    — 可重试（换参数重试一次）。
    DEGRADE  — 降级，不再调用 LLM，使用原文。
    """
    PASS = "pass"
    RETRY = "retry"
    DEGRADE = "degrade"


# ---------------------------------------------------------------------------
# 拒绝检测模式
# ---------------------------------------------------------------------------

# 中文拒绝模式
_REFUSAL_PATTERNS_ZH: list[str] = [
    "作为AI",
    "作为人工智能",
    "作为语言模型",
    "我不能",
    "我无法",
    "我做不到",
    "抱歉，我无法",
    "抱歉，我不能",
    "对不起，我无法",
    "对不起，我不能",
    "很抱歉，我无法",
    "很抱歉，我不能",
    "无法提供",
    "不能提供",
    "无法回答",
    "无法完成",
    "超出我的能力",
    "这超出了",
    "请理解",
    "请谅解",
    "请见谅",
    "根据相关规定",
    "根据安全政策",
    "这违反",
    "这不符合",
    "不恰当的内容",
    "不当内容",
    "有害内容",
    "不适合讨论",
    "我建议你",
    "建议您",
    "请注意",
    "请谨慎",
    "你可以尝试",
    "您可以尝试",
]

# 英文拒绝模式
_REFUSAL_PATTERNS_EN: list[str] = [
    "I cannot",
    "I can't",
    "I am unable",
    "I'm unable",
    "I apologize",
    "I'm sorry",
    "I am sorry",
    "as an AI",
    "as a language model",
    "I cannot provide",
    "I can't provide",
    "unable to provide",
    "unable to fulfill",
    "cannot fulfill",
    "cannot comply",
    "against my guidelines",
    "against my policy",
    "I would suggest",
    "instead, I recommend",
    "it would be better",
    "happy to help with",
    "I'm not able",
    "I am not able",
    "not appropriate",
    "inappropriate",
    "this request",
    "your request",
]

# 编译为单个正则（OR 连接）
_REFUSAL_RE: re.Pattern = re.compile(
    "|".join(
        re.escape(p) for p in _REFUSAL_PATTERNS_ZH + _REFUSAL_PATTERNS_EN
    ),
    re.IGNORECASE,
)


# ---------------------------------------------------------------------------
# PostProcessor
# ---------------------------------------------------------------------------

@dataclass
class PostProcessor:
    """输出验证器，对 LLM 输出执行多层验证。"""

    min_length: int = 2
    """最短合法输出字符数。"""

    max_length_ratio: float = 3.0
    """输出/原文最大长度比。"""

    min_length_ratio: float = 0.3
    """输出/原文最小长度比。"""

    # ── 公开 API ──────────────────────────────────────────────────────

    def validate(
        self,
        original: str,
        styled: str,
        entities: Optional[list[str]] = None,
    ) -> ValidationResult:
        """执行完整验证管线。

        按顺序检查：空值 → 拒绝 → 长度 → 实体。
        第一个未通过的结果直接返回。

        Args:
            original: 原始转录文本。
            styled:   LLM 改写后的文本。
            entities: 需保持的关键实体列表（可选）。

        Returns:
            PASS / RETRY / DEGRADE。
        """
        # Step 1: 空值检测
        result = self._check_empty(styled)
        if result != ValidationResult.PASS:
            return result

        # Step 2: LLM 自引用 / 拒绝检测
        result = self._check_refusal(styled)
        if result != ValidationResult.PASS:
            return result

        # Step 3: 长度异常检测
        result = self._check_length_ratio(original, styled)
        if result != ValidationResult.PASS:
            return result

        # Step 4: 实体保持检测
        if entities:
            result = self._check_entities(styled, entities)
            if result != ValidationResult.PASS:
                return result

        return ValidationResult.PASS

    # ── 各检查步骤 ────────────────────────────────────────────────────

    def _check_empty(self, styled: str) -> ValidationResult:
        """检测空输出或过短输出。

        Returns:
            PASS    — 长度 >= min_length。
            DEGRADE — 空值或 < min_length（不值得重试）。
        """
        stripped = styled.strip()
        if len(stripped) < self.min_length:
            return ValidationResult.DEGRADE
        return ValidationResult.PASS

    def _check_refusal(self, styled: str) -> ValidationResult:
        """检测 LLM 自引用 / 拒绝回答模式。

        匹配中英文常见拒绝句式："作为AI"、"I cannot" 等。

        Returns:
            PASS   — 未命中任何拒绝模式。
            RETRY  — 命中拒绝模式（可能换温度重试）。
        """
        if _REFUSAL_RE.search(styled):
            return ValidationResult.RETRY
        return ValidationResult.PASS

    def _check_length_ratio(
        self, original: str, styled: str
    ) -> ValidationResult:
        """检测输出长度与原文的比例是否在合理范围。

        合理范围：[min_length_ratio × L, max_length_ratio × L]，
        其中 L = max(len(original), 1)。

        Returns:
            PASS    — 比例正常。
            RETRY   — 长度异常（可重试）。
        """
        orig_len = max(len(original.strip()), 1)
        styled_len = len(styled.strip())
        ratio = styled_len / orig_len

        if ratio < self.min_length_ratio or ratio > self.max_length_ratio:
            return ValidationResult.RETRY
        return ValidationResult.PASS

    def _check_entities(
        self, styled: str, entities: list[str]
    ) -> ValidationResult:
        """验证关键实体是否在输出中保持。

        每个实体必须在 styled 中出现（大小写不敏感，子串匹配）。

        Args:
            styled:   LLM 改写后的文本。
            entities: 需保持的实体列表。

        Returns:
            PASS    — 所有实体均存在。
            RETRY   — 至少一个实体缺失（可重试）。
        """
        styled_lower = styled.lower()
        for entity in entities:
            if entity.lower() not in styled_lower:
                return ValidationResult.RETRY
        return ValidationResult.PASS
