"""Audio Recorder — PyAudio 录音模块。

支持 PyAudio 和 sounddevice 优雅回退。
上下文管理器支持:  with AudioRecorder() as recorder: ...
"""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)


class AudioRecorderError(Exception):
    """音频录制相关异常基类。"""
    pass


class MicPermissionError(AudioRecorderError):
    """麦克风权限未授予。"""
    pass


class AudioRecorder:
    """跨平台音频录音器。

    优先使用 PyAudio，回退到 sounddevice。
    支持上下文管理器。

    Usage:
        recorder = AudioRecorder()
        recorder.start_recording(sample_rate=16000, channels=1)
        while recorder.is_recording:
            chunk = recorder.read_chunk()
            # process chunk...
        audio_data = recorder.stop_recording()

        # 或使用上下文管理器:
        with AudioRecorder() as recorder:
            # 自动开始录制
            ...
            audio_data = recorder.stop_recording()
    """

    MIN_RECORD_SECONDS = 1.0  # 最短录音时长，小于此值可能无有效数据

    def __init__(self) -> None:
        self._audio: Optional[object] = None
        self._stream: Optional[object] = None
        self._frames: list[bytes] = []
        self._recording: bool = False
        self._sample_rate: int = 16000
        self._channels: int = 1
        self._chunk_size: int = 1024
        self._backend: Optional[str] = None  # 'pyaudio' | 'sounddevice' | None
        self._lock = threading.Lock()
        self._start_time: float = 0.0
        self._auto_started: bool = False  # 是否由上下文管理器自动启动

    # ------------------------------------------------------------------
    # 属性
    # ------------------------------------------------------------------

    @property
    def is_recording(self) -> bool:
        """是否正在录制。"""
        return self._recording

    @property
    def recording_duration(self) -> float:
        """当前/最近一次录制时长（秒）。"""
        if not self._start_time:
            return 0.0
        if self._recording:
            return time.monotonic() - self._start_time
        return 0.0

    @property
    def backend(self) -> Optional[str]:
        """当前使用的音频后端名称。"""
        return self._backend

    # ------------------------------------------------------------------
    # 后端探测与初始化
    # ------------------------------------------------------------------

    def _init_pyaudio(self) -> bool:
        """尝试初始化 PyAudio 后端。"""
        try:
            import pyaudio

            self._audio = pyaudio.PyAudio()
            # 探测默认输入设备，验证麦克风可用
            try:
                default_input = self._audio.get_default_input_device_info()
                logger.debug("PyAudio 默认输入设备: %s", default_input.get("name"))
            except OSError as exc:
                raise MicPermissionError(
                    f"麦克风权限未授予或未找到输入设备。请检查系统麦克风权限设置。\n"
                    f"  macOS: 系统偏好设置 → 安全性与隐私 → 麦克风\n"
                    f"  Windows: 设置 → 隐私 → 麦克风\n"
                    f"  原始错误: {exc}"
                ) from exc

            self._backend = "pyaudio"
            logger.info("音频后端: PyAudio (已就绪)")
            return True
        except ImportError:
            logger.debug("PyAudio 未安装，尝试 sounddevice...")
            return False
        except MicPermissionError:
            raise
        except Exception as exc:
            logger.warning("PyAudio 初始化失败: %s", exc)
            return False

    def _init_sounddevice(self) -> bool:
        """尝试初始化 sounddevice 后端。"""
        try:
            import sounddevice as sd

            # 验证输入设备存在
            devices = sd.query_devices()
            input_devices = [d for d in devices if d.get("max_input_channels", 0) > 0]
            if not input_devices:
                raise MicPermissionError(
                    "未找到可用的音频输入设备。请检查麦克风连接和权限设置。"
                )

            self._audio = sd
            self._backend = "sounddevice"
            logger.info("音频后端: sounddevice (已就绪)")
            return True
        except ImportError:
            logger.debug("sounddevice 未安装。")
            return False
        except MicPermissionError:
            raise
        except Exception as exc:
            logger.warning("sounddevice 初始化失败: %s", exc)
            return False

    def _ensure_backend(self) -> None:
        """确保至少有一个后端可用，否则抛出异常。"""
        if self._backend is not None:
            return
        if self._init_pyaudio():
            return
        if self._init_sounddevice():
            return
        raise AudioRecorderError(
            "无可用的音频后端。请安装 PyAudio 或 sounddevice:\n"
            "  pip install pyaudio\n"
            "  pip install sounddevice"
        )

    # ------------------------------------------------------------------
    # 录制控制
    # ------------------------------------------------------------------

    def start_recording(
        self,
        sample_rate: int = 16000,
        channels: int = 1,
        chunk_size: int = 1024,
    ) -> None:
        """开始录制音频。

        Args:
            sample_rate: 采样率 (Hz)，默认 16000
            channels: 声道数，默认 1 (单声道)
            chunk_size: 每帧样本数，默认 1024
        """
        if self._recording:
            logger.warning("已在录制中，忽略重复调用。")
            return

        self._ensure_backend()

        self._sample_rate = sample_rate
        self._channels = channels
        self._chunk_size = chunk_size
        self._frames = []
        self._start_time = time.monotonic()

        try:
            if self._backend == "pyaudio":
                self._start_pyaudio_stream()
            elif self._backend == "sounddevice":
                self._start_sounddevice_stream()
            else:
                raise AudioRecorderError(f"未知后端: {self._backend}")

            self._recording = True
            logger.info(
                "开始录制 (sr=%d, ch=%d, chunk=%d, backend=%s)",
                sample_rate,
                channels,
                chunk_size,
                self._backend,
            )
        except Exception:
            self._backend = None  # 重置后端，下次可重新尝试
            raise

    def _start_pyaudio_stream(self) -> None:
        """启动 PyAudio 录制流。"""
        import pyaudio

        def callback(in_data, frame_count, time_info, status):
            if status:
                logger.warning("PyAudio 状态标志: %s", status)
            self._frames.append(in_data)
            return (in_data, pyaudio.paContinue)

        self._stream = self._audio.open(
            format=pyaudio.paInt16,
            channels=self._channels,
            rate=self._sample_rate,
            input=True,
            frames_per_buffer=self._chunk_size,
            stream_callback=callback,
        )
        self._stream.start_stream()

    def _start_sounddevice_stream(self) -> None:
        """启动 sounddevice 录制流。"""
        import sounddevice as sd

        self._stream = sd.InputStream(
            samplerate=self._sample_rate,
            channels=self._channels,
            blocksize=self._chunk_size,
            callback=self._sd_callback,
            dtype="int16",
        )
        self._stream.start()

    def _sd_callback(self, indata, frames, time_info, status) -> None:
        """sounddevice 回调：将输入数据追加到帧列表。"""
        if status:
            logger.warning("sounddevice 状态: %s", status)
        self._frames.append(indata.tobytes())

    def read_chunk(self) -> bytes:
        """读取一个音频块。

        对于 PyAudio，从内部帧缓冲区弹出最早的 chunk；
        对于 sounddevice，回调已自动写入帧列表。
        如果没有可用数据，返回空字节串。

        Returns:
            bytes: 音频数据块
        """
        if not self._recording:
            logger.warning("未在录制中，read_chunk 返回空。")
            return b""

        with self._lock:
            if self._frames:
                return self._frames.pop(0)
            return b""

    def stop_recording(self) -> bytes:
        """停止录制并返回完整音频数据。

        Returns:
            bytes: 完整的 PCM int16 音频数据

        Raises:
            AudioRecorderError: 未在录制中时调用
        """
        if not self._recording:
            raise AudioRecorderError("未在录制中，无法停止。")

        # 保护最短录音时长
        elapsed = time.monotonic() - self._start_time
        if elapsed < self.MIN_RECORD_SECONDS:
            remaining = self.MIN_RECORD_SECONDS - elapsed
            logger.debug("录音时长 %.2fs 不足，等待 %.2fs...", elapsed, remaining)
            time.sleep(remaining)

        self._recording = False

        # 停止流
        if self._stream is not None:
            try:
                if self._backend == "pyaudio":
                    self._stream.stop_stream()
                    self._stream.close()
                elif self._backend == "sounddevice":
                    self._stream.stop()
                    self._stream.close()
            except Exception as exc:
                logger.warning("关闭音频流时出错: %s", exc)
            finally:
                self._stream = None

        # 汇总所有帧
        with self._lock:
            audio_data = b"".join(self._frames)
            self._frames = []

        duration = time.monotonic() - self._start_time
        logger.info("录制结束，时长 %.2fs，数据 %d bytes", duration, len(audio_data))
        return audio_data

    # ------------------------------------------------------------------
    # 上下文管理器
    # ------------------------------------------------------------------

    def __enter__(self) -> "AudioRecorder":
        """进入上下文：自动开始录制。"""
        self._ensure_backend()
        self.start_recording()
        self._auto_started = True
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """退出上下文：如果仍在录制则停止。"""
        try:
            if self._recording:
                self.stop_recording()
        except AudioRecorderError:
            pass  # 静默处理已在 __exit__ 阶段
        self._auto_started = False
        return None  # 不抑制异常

    # ------------------------------------------------------------------
    # 清理
    # ------------------------------------------------------------------

    def close(self) -> None:
        """释放资源。"""
        if self._recording:
            try:
                self.stop_recording()
            except AudioRecorderError:
                pass
        if self._audio is not None and self._backend == "pyaudio":
            try:
                self._audio.terminate()
            except Exception as exc:
                logger.warning("PyAudio terminate 失败: %s", exc)
        self._audio = None
        self._backend = None

    def __del__(self) -> None:
        """析构时释放资源。"""
        self.close()
