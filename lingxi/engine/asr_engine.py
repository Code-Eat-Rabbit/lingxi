"""ASR Engine 协议定义

定义语音转录引擎的抽象接口，包括：
- TranscriptionResult: 转录结果数据类
- ASREngine: 离线转录协议
- StreamingASREngine: 流式转录协议
- ASRSessionConfig: 会话配置
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Callable, Protocol, runtime_checkable


# ── 转录结果 ──────────────────────────────────────────────────────────

@dataclass
class TranscriptionResult:
    """单次/最终转录结果"""
    text: str
    is_final: bool
    emotion: str = "neutral"
    emotion_confidence: float = 0.0


# ── 流式转录中间状态 ──────────────────────────────────────────────────

@dataclass
class StreamingTranscriptionState:
    """流式转录过程中的累积状态快照"""
    full_text: str = ""
    last_delta: str = ""
    is_final: bool = False
    emotion: str = "neutral"
    emotion_confidence: float = 0.0


# ── 会话配置 ──────────────────────────────────────────────────────────

@dataclass
class ASRSessionConfig:
    """ASR 会话配置"""
    language: str = "zh-CN"
    engine_type: str = ""
    model_size: str = ""


# ── 离线转录引擎协议 ──────────────────────────────────────────────────

@runtime_checkable
class ASREngine(Protocol):
    """离线（整段）语音转录引擎协议"""

    def transcribe(self, audio_data: bytes) -> TranscriptionResult:
        """同步转录音频数据

        Args:
            audio_data: 原始音频字节（WAV/PCM16）

        Returns:
            转录结果，包含文本和情绪标注
        """
        ...

    async def transcribe_stream(
        self, audio_stream: AsyncIterator[bytes]
    ) -> TranscriptionResult:
        """流式转录音频数据（异步消费音频块）

        Args:
            audio_stream: 异步音频块迭代器

        Returns:
            最终转录结果
        """
        ...


# ── 流式转录引擎协议 ──────────────────────────────────────────────────

@runtime_checkable
class StreamingASREngine(Protocol):
    """流式实时语音转录引擎协议"""

    def start_session(self, config: ASRSessionConfig) -> None:
        """启动一个转录会话"""
        ...

    def send_audio_chunk(self, b64_frame: str) -> None:
        """发送一帧 Base64 编码的音频数据"""
        ...

    def commit(self) -> None:
        """标记当前音频边界（用于 VAD 辅助）"""
        ...

    def finalize(self) -> TranscriptionResult:
        """结束会话并返回最终转录结果"""
        ...

    def on_text_delta(self, callback: Callable[[str], None]) -> None:
        """注册文本增量回调

        Args:
            callback: 接收增量文本片段（delta）
        """
        ...

    def on_emotion_update(
        self, callback: Callable[[str, float], None]
    ) -> None:
        """注册情绪更新回调

        Args:
            callback: 接收 (emotion_label, confidence) 元组
        """
        ...
