"""
灵犀输入 — Ollama 客户端实现

基于 aiohttp 调用 Ollama HTTP API 的 LLM 客户端。
无需额外安装 ollama Python SDK。
"""

from __future__ import annotations

import json
import logging
from typing import Optional

from lingxi.llm.client import LLMConfig, StyleRequest
from lingxi.style.compiler import StylePromptCompiler

logger = logging.getLogger(__name__)


class OllamaClientError(Exception):
    """Ollama 客户端调用错误基类。"""
    pass


class OllamaClient:
    """Ollama LLM 客户端，实现 async rewrite() 接口。

    通过 Ollama 的 /api/chat HTTP 端点调用本地模型。
    """

    def __init__(self, config: LLMConfig) -> None:
        """初始化 Ollama 客户端。

        Args:
            config: LLM 配置对象。
        """
        self._config = config
        self._compiler = StylePromptCompiler(language="zh-CN")
        self._session: Optional[object] = None

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    async def rewrite(self, request: StyleRequest) -> str:
        """调用 Ollama API 执行风格改写。

        Args:
            request: 包含原始文本和风格配置的请求对象。

        Returns:
            改写后的文本。

        Raises:
            OllamaClientError: API 调用失败。
        """
        if not request.source_text.strip():
            return request.source_text

        system_prompt = self._build_system_prompt(request)
        payload = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": request.source_text},
            ],
            "stream": False,
            "options": {
                "temperature": self._config.temperature,
                "num_predict": self._config.max_tokens,
            },
        }

        url = f"{self._config.ollama_host.rstrip('/')}/api/chat"

        try:
            import aiohttp
        except ImportError:
            raise OllamaClientError(
                "缺少 aiohttp 包；请运行: pip install aiohttp"
            )

        session = self._get_session()

        try:
            timeout = aiohttp.ClientTimeout(total=self._config.timeout)
            async with session.post(
                url,
                json=payload,
                timeout=timeout,
            ) as resp:
                if resp.status == 404:
                    raise OllamaClientError(
                        f"Ollama 模型未找到: {self._config.model}。"
                        f" 请先执行: ollama pull {self._config.model}"
                    )
                if resp.status != 200:
                    body = await resp.text()
                    raise OllamaClientError(
                        f"Ollama HTTP {resp.status}: {body[:500]}"
                    )

                data = await resp.json()
                content: str = (
                    data.get("message", {}).get("content", "")
                )
                return content.strip()

        except aiohttp.ClientConnectorError as e:
            raise OllamaClientError(
                f"无法连接到 Ollama ({self._config.ollama_host}): {e}"
            )

        except aiohttp.ServerTimeoutError:
            raise OllamaClientError(
                f"Ollama 请求超时 ({self._config.timeout}s)"
            )

        except OllamaClientError:
            raise

        except Exception as e:
            raise OllamaClientError(f"Ollama 调用失败: {e}")

    # ------------------------------------------------------------------
    # 内部实现
    # ------------------------------------------------------------------

    def _get_session(self) -> object:
        """获取或延迟创建 aiohttp.ClientSession。

        Returns:
            aiohttp.ClientSession 实例。
        """
        import aiohttp

        if self._session is None:
            self._session = aiohttp.ClientSession()

        return self._session

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

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """关闭底层 HTTP 会话。"""
        if self._session is not None:
            await self._session.close()
            self._session = None
