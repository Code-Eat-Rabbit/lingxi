"""faster-whisper 适配器

实现 ASREngine 协议，封装 faster-whisper 库。
模型下载到 ~/.lingxi/models/whisper/ 目录。
"""

from __future__ import annotations

import io
import logging
import os
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, AsyncIterator

import numpy as np

from lingxi.engine.asr_engine import ASREngine, TranscriptionResult

logger = logging.getLogger(__name__)

# 默认模型目录
DEFAULT_MODEL_DIR = Path.home() / ".lingxi" / "models" / "whisper"


# ── 音频工具 ──────────────────────────────────────────────────────────

def _bytes_to_ndarray(audio_data: bytes) -> np.ndarray:
    """将 WAV 字节数据解码为 float32 归一化的 numpy 数组 (16kHz mono)"""
    with io.BytesIO(audio_data) as buf:
        with wave.open(buf, "rb") as wf:
            n_channels = wf.getnchannels()
            sample_width = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

    # 转换为 int16 数组
    dtype_map = {1: np.int8, 2: np.int16, 4: np.int32}
    dtype = dtype_map.get(sample_width, np.int16)
    samples = np.frombuffer(raw, dtype=dtype).astype(np.float32)

    # 多声道取平均
    if n_channels > 1:
        samples = samples.reshape(-1, n_channels).mean(axis=1)

    # 归一化
    max_val = np.max(np.abs(samples))
    if max_val > 0:
        samples /= max_val

    return samples, framerate


# ── faster-whisper 引擎 ───────────────────────────────────────────────

@dataclass
class FasterWhisperConfig:
    """faster-whisper 引擎配置"""
    model_size: str = "base"           # tiny / base / small / medium / large-v3
    device: str = "auto"              # auto / cpu / cuda
    compute_type: str = "auto"        # auto / float16 / int8
    model_dir: Path = DEFAULT_MODEL_DIR
    language: str = "zh"              # 默认转录语言
    beam_size: int = 5
    vad_filter: bool = True


@dataclass
class FasterWhisperEngine:
    """faster-whisper ASR 引擎，实现 ASREngine 协议"""

    config: FasterWhisperConfig = field(default_factory=FasterWhisperConfig)
    _model: Any = field(default=None, init=False, repr=False)

    # ── 模型管理 ──────────────────────────────────────────────────

    def load_model(self) -> Any:
        """加载/下载 faster-whisper 模型"""
        if self._model is not None:
            return self._model

        from faster_whisper import WhisperModel

        self.config.model_dir.mkdir(parents=True, exist_ok=True)

        logger.info(
            "正在加载 faster-whisper 模型: size=%s, device=%s, compute=%s",
            self.config.model_size,
            self.config.device,
            self.config.compute_type,
        )

        self._model = WhisperModel(
            model_size_or_path=self.config.model_size,
            device=self.config.device,
            compute_type=self.config.compute_type,
            download_root=str(self.config.model_dir),
        )

        logger.info("faster-whisper 模型加载完成")
        return self._model

    # ── ASREngine 协议实现 ────────────────────────────────────────

    def transcribe(self, audio_data: bytes) -> TranscriptionResult:
        """同步转录 WAV 字节数据"""
        model = self.load_model()
        audio_array, _ = _bytes_to_ndarray(audio_data)

        segments, info = model.transcribe(
            audio_array,
            language=self.config.language,
            beam_size=self.config.beam_size,
            vad_filter=self.config.vad_filter,
        )

        # 拼接所有片段文本
        text_parts: list[str] = []
        for segment in segments:
            text_parts.append(segment.text.strip())

        full_text = "".join(text_parts)

        return TranscriptionResult(
            text=full_text,
            is_final=True,
            emotion="neutral",
            emotion_confidence=0.0,
        )

    async def transcribe_stream(
        self, audio_stream: AsyncIterator[bytes]
    ) -> TranscriptionResult:
        """异步流式转录

        注意：faster-whisper 不支持原生流式，这里收集全部音频块后调用
        transcribe()。子类可覆盖此方法实现真正的流式处理。
        """
        chunks: list[bytes] = []
        async for chunk in audio_stream:
            chunks.append(chunk)

        combined = b"".join(chunks)
        return self.transcribe(combined)
