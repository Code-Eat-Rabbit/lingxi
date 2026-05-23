"""
灵犀输入 — LLM 客户端协议与请求模型

定义:
- StyleRequest: 风格改写请求数据模型
- LLMClient:   LLM 客户端异步协议
- LLMConfig:   从 ConfigStore 解析的 LLM 配置
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Protocol

from lingxi.engine.emotion import Emotion


# ---------------------------------------------------------------------------
# StyleRequest
# ---------------------------------------------------------------------------

@dataclass
class StyleRequest:
    """风格改写请求，封装一次 LLM 调用所需的全部输入。

    Attributes:
        source_text:      原始转录文本（ASR 输出）。
        style_profile:    StyleProfile 对象，定义目标风格。
        emotion:          检测到的情绪标签（默认 neutral）。
        emotion_strength: 情绪调制强度 [0.0, 1.0]。
        language:         输出语言代码（默认 zh-CN）。
    """
    source_text: str
    style_profile: object                     # StyleProfile 实例（避免循环导入）
    emotion: str = "neutral"
    emotion_strength: float = 1.0
    language: str = "zh-CN"


# ---------------------------------------------------------------------------
# LLMClient Protocol
# ---------------------------------------------------------------------------

class LLMClient(Protocol):
    """LLM 客户端异步协议。

    所有 LLM 客户端（OpenAI、Ollama 等）都实现此接口，
    供上层引擎通过统一协议调用。
    """

    async def rewrite(self, request: StyleRequest) -> str:
        """执行风格改写。

        Args:
            request: 包含原始文本和风格配置的请求对象。

        Returns:
            改写后的文本字符串。

        Raises:
            LLMError: 所有 LLM 调用错误的基类。
        """
        ...


# ---------------------------------------------------------------------------
# LLMConfig
# ---------------------------------------------------------------------------

@dataclass
class LLMConfig:
    """LLM 客户端配置，可来源于 ConfigStore 或硬编码默认值。

    对应 config.json 中 ``llm`` 字段的结构。
    """
    provider: str = "openai"                 # openai | ollama | custom
    model: str = "gpt-4o-mini"
    api_key: Optional[str] = None
    base_url: Optional[str] = None           # 自定义 OpenAI 兼容端点
    ollama_host: str = "http://localhost:11434"
    temperature: float = 0.3
    max_tokens: int = 256
    timeout: int = 30

    @classmethod
    def from_config_store(cls, config_store: object) -> "LLMConfig":
        """从 ConfigStore 实例创建 LLMConfig。

        从 ``config_store.get("llm.xxx")`` 读取各字段，
        缺失字段使用 LLMConfig 默认值。

        Args:
            config_store: ConfigStore 实例（duck typing）。

        Returns:
            LLMConfig 实例。
        """
        def _get(key: str, default):
            return config_store.get(f"llm.{key}", default)

        return cls(
            provider=_get("provider", "openai"),
            model=_get("model", "gpt-4o-mini"),
            api_key=_get("api_key", None),
            base_url=_get("base_url", None),
            ollama_host=_get("ollama_host", "http://localhost:11434"),
            temperature=float(_get("temperature", 0.3)),
            max_tokens=int(_get("max_tokens", 256)),
            timeout=int(_get("timeout", 30)),
        )
