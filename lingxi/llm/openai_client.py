"""
灵犀输入 — OpenAI 客户端实现

基于 openai Python SDK (AsyncOpenAI) 的 LLM 客户端，
兼容所有 OpenAI 兼容 API（通过 base_url 自定义）。
"""

from __future__ import annotations

import logging
from typing import Optional

from lingxi.llm.client import LLMConfig, StyleRequest
from lingxi.style.compiler import StylePromptCompiler

logger = logging.getLogger(__name__)


class OpenAIClientError(Exception):
    """OpenAI 客户端调用错误基类。"""
    pass


class OpenAIClient:
    """OpenAI 兼容 LLM 客户端，实现 async rewrite() 接口。"""

    def __init__(self, config: LLMConfig) -> None:
        """初始化 OpenAI 客户端。

        Args:
            config: LLM 配置对象。
        """
        self._config = config
        self._compiler = StylePromptCompiler(language="zh-CN")
        self._client: Optional[object] = None

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def rewrite(self, request: StyleRequest) -> str:
        """调用 OpenAI API 执行风格改写。

        Args:
            request: 包含原始文本和风格配置的请求对象。

        Returns:
            改写后的文本。

        Raises:
            OpenAIClientError: API 调用失败。
        """
        if not request.source_text.strip():
            return request.source_text

        client = self._get_client()
        system_prompt = self._build_system_prompt(request)

        try:
            response = await client.chat.completions.create(
                model=self._config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": request.source_text},
                ],
                temperature=self._config.temperature,
                max_tokens=self._config.max_tokens,
            )
        except Exception as e:
            raise self._wrap_error(e)

        content: str = response.choices[0].message.content or ""
        return content.strip()

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _get_client(self) -> object:
        """获取或延迟创建 AsyncOpenAI 实例。

        Returns:
            AsyncOpenAI 客户端实例。
        """
        if self._client is not None:
            return self._client

        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise OpenAIClientError(
                "缺少 openai 包；请运行: pip install openai"
            )

        kwargs: dict = {
            "api_key": self._config.api_key,
            "timeout": float(self._config.timeout),
            "max_retries": 0,
        }
        if self._config.base_url:
            kwargs["base_url"] = self._config.base_url

        self._client = AsyncOpenAI(**kwargs)
        return self._client

    def _build_system_prompt(self, request: StyleRequest) -> str:
        """为当前请求构建 system prompt。

        使用 StylePromptCompiler 将 StyleProfile + Emotion
        编译为 XML 格式的系统提示。

        Args:
            request: 风格改写请求。

        Returns:
            格式化的系统提示 XML 字符串。
        """
        self._compiler.language = request.language
        return self._compiler.compile(
            style=request.style_profile,
            emotion=request.emotion,
            emotion_strength=request.emotion_strength,
        )

    def _wrap_error(self, error: Exception) -> OpenAIClientError:
        """将 openai SDK 异常封装为 OpenAIClientError。

        识别三类典型错误：
          - APITimeoutError → 超时
          - APIStatusError  → HTTP 状态错误
          - APIError        → 其他 API 错误

        Args:
            error: 原始异常对象。

        Returns:
            OpenAIClientError 实例。
        """
        # 尝试按 openai SDK 异常类型分类
        error_type = type(error).__name__

        # APIStatusError / RateLimitError / AuthenticationError 等
        if hasattr(error, "status_code"):
            status = getattr(error, "status_code", 0)
            msg = getattr(error, "message", str(error))
            return OpenAIClientError(
                f"OpenAI HTTP {status}: {msg}"
            )

        # APITimeoutError / APIConnectionError
        if "Timeout" in error_type or "timeout" in str(error).lower():
            return OpenAIClientError(
                f"OpenAI 请求超时 ({self._config.timeout}s): {error}"
            )

        # 其他
        return OpenAIClientError(f"OpenAI 调用失败: {error}")
