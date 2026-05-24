"""
灵犀输入 — 应用入口 + 系统托盘 + 语音管线编排
"""

from __future__ import annotations

import sys
import signal
import logging
import threading
import time
import asyncio
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu, QMessageBox
from PySide6.QtGui import QIcon, QAction
from PySide6.QtCore import Qt, QTimer, Signal, QObject

# ── 灵犀模块 ──────────────────────────────────────────
from lingxi.io.audio_recorder import AudioRecorder
from lingxi.io.hotkey_manager import HotkeyManager, HotkeyDef
from lingxi.io.text_injector import TextInjector
from lingxi.data.config_store import ConfigStore
from lingxi.data.history_store import HistoryStore
from lingxi.style.profile import StyleProfile
from lingxi.style.store import StyleProfileStore
from lingxi.style.resolver import StyleResolver
from lingxi.style.compiler import StylePromptCompiler
from lingxi.engine.emotion import Emotion
from lingxi.context.app_detector import AppDetector

# ── 配置 ──────────────────────────────────────────────
APP_NAME = "灵犀输入"
APP_DIR = Path.home() / ".lingxi"
CONFIG_FILE = APP_DIR / "config.json"
PROFILES_FILE = APP_DIR / "profiles.json"
HISTORY_DB = APP_DIR / "history.db"
MODELS_DIR = APP_DIR / "models"

logger = logging.getLogger(__name__)


def ensure_app_dirs() -> None:
    for d in [APP_DIR, MODELS_DIR]:
        d.mkdir(parents=True, exist_ok=True)


def create_app_icon() -> QIcon:
    return QApplication.style().standardIcon(
        QApplication.style().StandardPixmap.SP_MediaVolume
    )


# ── 语音管线编排器 ────────────────────────────────────

class VoicePipeline(QObject):
    """串联 录音 → ASR → 风格解析 → LLM → 注入 的完整管线。"""

    # 信号（用于跨线程更新 UI）
    recording_started = Signal(str, str)       # (style_name, style_icon)
    transcription_update = Signal(str)         # 实时转录文本
    processing_started = Signal()
    result_ready = Signal(str, str)            # (styled_text, emotion)
    error_occurred = Signal(str)               # 错误信息
    style_picker_requested = Signal()

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._audio = AudioRecorder()
        self._injector = TextInjector()
        self._config = ConfigStore()
        self._style_store = StyleProfileStore()
        self._resolver = StyleResolver(self._style_store, self._config)
        self._app_detector = AppDetector()
        self._compiler = StylePromptCompiler()

        self._recording = False
        self._processing = False

    # ── 热键回调 ───────────────────────────────────

    def on_hotkey(self, is_long_press: bool) -> None:
        """热键触发：短按=录音开关，长按=风格选择器。"""
        if self._processing:
            logger.info("正在处理中，忽略热键")
            return

        if is_long_press:
            self.style_picker_requested.emit()
            return

        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def set_manual_style(self, style_id: str) -> None:
        """设置手动临时覆盖风格（从 StylePicker 选择后调用）。"""
        self._resolver.set_manual_override(style_id)
        logger.info("手动覆盖风格: %s", style_id)

    def clear_manual_style(self) -> None:
        self._resolver.set_manual_override(None)

    # ── 录音流程 ───────────────────────────────────

    def _start_recording(self) -> None:
        """开始录音。"""
        try:
            # 解析当前风格
            app_info = self._app_detector.get_active_app()
            app_id = app_info.identifier if app_info else None
            result = self._resolver.resolve(app_identifier=app_id)
            self._current_style = result.profile

            self._audio.start_recording(sample_rate=16000, channels=1)
            self._recording = True
            self._audio_buffer = bytearray()

            self.recording_started.emit(
                self._current_style.name,
                self._current_style.icon
            )
            logger.info("开始录音 — 风格: %s", self._current_style.name)

        except Exception as e:
            self.error_occurred.emit(f"录音启动失败: {e}")
            logger.error("录音启动失败: %s", e)

    def _stop_recording(self) -> None:
        """停止录音并启动处理管线。"""
        if not self._recording:
            return

        self._recording = False
        try:
            audio_data = self._audio.stop_recording()
        except Exception as e:
            self.error_occurred.emit(f"录音停止失败: {e}")
            return

        if not audio_data or len(audio_data) < 1600:  # < 0.1s 视为无效
            self.error_occurred.emit("录音太短，请重试")
            return

        self.processing_started.emit()
        logger.info("录音结束 — %d bytes，开始处理", len(audio_data))

        # 在后台线程执行处理
        thread = threading.Thread(
            target=self._process_pipeline,
            args=(audio_data,),
            name="voice-pipeline",
            daemon=True,
        )
        thread.start()

    # ── 处理管线（后台线程） ─────────────────────────

    def _process_pipeline(self, audio_data: bytes) -> None:
        """转录 → 风格转换 → 注入（在后台线程中执行）。"""
        try:
            # 1. ASR 转录
            transcript = self._transcribe(audio_data)

            if not transcript or not transcript.strip():
                self.error_occurred.emit("未检测到语音内容")
                return

            # 2. 风格转换
            styled = self._apply_style(transcript)

            if not styled or not styled.strip():
                self.error_occurred.emit("风格转换失败，已注入原文")
                styled = transcript

            # 3. 文本注入
            success = self._injector.inject(styled)

            if success:
                self.result_ready.emit(styled, "neutral")
            else:
                self.error_occurred.emit("文本注入失败，已复制到剪贴板")

            # 4. 记录历史
            self._save_history(transcript, styled)

        except Exception as e:
            logger.error("处理管线异常: %s", e)
            self.error_occurred.emit(f"处理失败: {e}")

    def _transcribe(self, audio_data: bytes) -> str:
        """调用 ASR 引擎转录（简化版：使用 faster-whisper 或回退到模拟）。"""
        try:
            from lingxi.engine.asr_faster_whisper import FasterWhisperEngine
            engine = FasterWhisperEngine()
            result = engine.transcribe(audio_data)
            return result.text
        except Exception as e:
            logger.warning("ASR 转录失败 (%s)，使用模拟转录", e)
            # 回退：返回占位文本（实际应提示用户配置 ASR 引擎）
            return "语音转录功能需要下载模型，请先在设置中配置 ASR 引擎"

    def _apply_style(self, text: str) -> str:
        """调用 LLM 进行风格转换。"""
        try:
            llm_config = self._config.get("llm")
            provider = llm_config.get("provider", "openai")

            if provider == "ollama":
                return asyncio.run(self._apply_ollama(text))
            else:
                return asyncio.run(self._apply_openai(text))
        except Exception as e:
            logger.warning("LLM 风格转换失败 (%s)，使用原文", e)
            return text

    async def _apply_openai(self, text: str) -> str:
        from lingxi.llm.openai_client import OpenAIClient
        from lingxi.llm.client import LLMConfig, StyleRequest

        config = LLMConfig.from_config_store(self._config)
        client = OpenAIClient(config)
        request = StyleRequest(
            source_text=text,
            style_profile=self._current_style,
            emotion="neutral",
            emotion_strength=0.0,
        )
        result = await client.rewrite(request)
        return result

    async def _apply_ollama(self, text: str) -> str:
        from lingxi.llm.ollama_client import OllamaClient
        from lingxi.llm.client import LLMConfig, StyleRequest

        config = LLMConfig.from_config_store(self._config)
        client = OllamaClient(config)
        request = StyleRequest(
            source_text=text,
            style_profile=self._current_style,
            emotion="neutral",
            emotion_strength=0.0,
        )
        result = await client.rewrite(request)
        return result

    def _save_history(self, original: str, styled: str) -> None:
        try:
            store = HistoryStore()
            store.add({
                "original_text": original,
                "styled_text": styled,
                "style_name": self._current_style.name,
                "emotion": "neutral",
                "asr_engine": "faster_whisper",
                "llm_provider": self._config.get("llm.provider", "openai"),
                "success": 1,
            })
        except Exception as e:
            logger.debug("历史记录保存失败: %s", e)


# ── 系统托盘 ──────────────────────────────────────────

class SystemTray:
    """系统托盘管理。"""

    def __init__(self, app: QApplication, pipeline: VoicePipeline):
        self.app = app
        self.pipeline = pipeline
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(create_app_icon())
        self.tray.setToolTip(APP_NAME)

        menu = QMenu()

        # 录音开关
        self.record_action = QAction("🎤 开始录音 (Fn)", menu)
        self.record_action.triggered.connect(lambda: pipeline.on_hotkey(False))
        menu.addAction(self.record_action)

        menu.addSeparator()

        # 风格切换子菜单
        self.style_menu = QMenu("风格切换")
        self._populate_style_menu()
        menu.addMenu(self.style_menu)

        menu.addSeparator()

        # 设置
        settings_action = QAction("设置...", menu)
        settings_action.triggered.connect(self._open_settings)
        menu.addAction(settings_action)

        menu.addSeparator()

        # 退出
        quit_action = QAction("退出", menu)
        quit_action.triggered.connect(self._quit)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.show()
        self.tray.activated.connect(self._on_tray_activated)

        # 状态提示定时器
        self._status_timer = QTimer()
        self._status_timer.setSingleShot(True)
        self._status_timer.timeout.connect(self._clear_status)

        logger.info("系统托盘已启动")

    def _populate_style_menu(self) -> None:
        self.style_menu.clear()
        try:
            store = StyleProfileStore()
            styles = store.list_all()
            for style in styles:
                icon = style.icon or "🍃"
                action = QAction(
                    f"{icon} {style.name}", self.style_menu
                )
                action.triggered.connect(
                    lambda checked, sid=style.id: self.pipeline.set_manual_style(sid)
                )
                self.style_menu.addAction(action)
        except Exception:
            pass

    def _on_tray_activated(self, reason: QSystemTrayIcon.ActivationReason) -> None:
        if reason == QSystemTrayIcon.ActivationReason.DoubleClick:
            self._open_settings()

    def _open_settings(self) -> None:
        logger.info("打开设置窗口（未实现）")

    def show_status(self, message: str) -> None:
        if hasattr(self.tray, 'showMessage'):
            self.tray.showMessage(APP_NAME, message, QSystemTrayIcon.MessageIcon.Information, 2000)

    def _clear_status(self) -> None:
        pass

    def _quit(self) -> None:
        logger.info("用户请求退出")
        self.app.quit()


# ── 主入口 ────────────────────────────────────────────

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    logger.info(f"{APP_NAME} 启动中...")
    ensure_app_dirs()

    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    if sys.platform == "darwin":
        app.setAttribute(Qt.ApplicationAttribute.AA_DontShowIconsInMenus, False)

    # 初始化语音管线
    pipeline = VoicePipeline()

    # 启动系统托盘
    tray = SystemTray(app, pipeline)

    # ── 注册全局热键 ──────────────────────────────
    hotkey = HotkeyManager()
    try:
        # macOS 默认 Cmd+Space，其他 Ctrl+Space
        hotkey.register_default(pipeline.on_hotkey)
        hotkey.start()

        # 尝试用 pynput 监听（如果安装了）
        try:
            listener = hotkey.attach_pynput_listener()
            logger.info("pynput 全局热键监听已启动")
        except ImportError:
            logger.warning("pynput 未安装，热键仅支持手动触发（托盘菜单）")
        except Exception as e:
            logger.warning("pynput 启动失败: %s，使用托盘菜单触发", e)

    except Exception as e:
        logger.warning("热键注册失败: %s", e)

    # ── 信号处理 ──────────────────────────────────

    def on_recording_started(name: str, icon: str) -> None:
        logger.info("🔴 录音中 — 风格: %s %s", icon, name)
        tray.show_status(f"录音中 — {icon} {name}")

    def on_processing_started() -> None:
        logger.info("⏳ 处理中...")
        tray.show_status("正在处理语音...")

    def on_result_ready(text: str, emotion: str) -> None:
        preview = text[:50] + "..." if len(text) > 50 else text
        logger.info("✅ 已注入: %s", preview)
        tray.show_status(f"已注入: {preview}")

    def on_error(msg: str) -> None:
        logger.error("❌ %s", msg)
        tray.show_status(f"错误: {msg}")

    def on_style_picker() -> None:
        logger.info("长按热键 — 弹出风格选择器")
        # TODO: 弹出 StylePicker overlay

    pipeline.recording_started.connect(on_recording_started)
    pipeline.processing_started.connect(on_processing_started)
    pipeline.result_ready.connect(on_result_ready)
    pipeline.error_occurred.connect(on_error)
    pipeline.style_picker_requested.connect(on_style_picker)

    # ── 清理 ──────────────────────────────────────
    signal.signal(signal.SIGINT, lambda sig, frame: app.quit())
    signal.signal(signal.SIGTERM, lambda sig, frame: app.quit())

    def cleanup() -> None:
        hotkey.stop()
        logger.info(f"{APP_NAME} 已退出")

    app.aboutToQuit.connect(cleanup)

    logger.info(f"{APP_NAME} 就绪 — 按 {HotkeyDef.default_for_platform()} 开始录音")
    exit_code = app.exec()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
