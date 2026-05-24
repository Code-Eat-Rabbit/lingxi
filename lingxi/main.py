"""
灵犀输入 — 应用入口 + 系统托盘 + 语音管线编排 + Overlay HUD
"""

from __future__ import annotations

import sys
import signal
import logging
import threading
import asyncio
from pathlib import Path
from typing import Optional

from PySide6.QtWidgets import QApplication, QSystemTrayIcon, QMenu
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
from lingxi.ui.overlay import OverlayHUD

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

    recording_started = Signal(str, str)
    processing_started = Signal()
    result_ready = Signal(str, str, str, str)   # (text, emotion, style_name, style_icon)
    error_occurred = Signal(str)
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
        self._current_style: Optional[StyleProfile] = None

    def on_hotkey(self, is_long_press: bool) -> None:
        if self._processing:
            return
        if is_long_press:
            self.style_picker_requested.emit()
            return
        if self._recording:
            self._stop_recording()
        else:
            self._start_recording()

    def set_manual_style(self, style_id: str) -> None:
        self._resolver.set_manual_override(style_id)

    def clear_manual_style(self) -> None:
        self._resolver.set_manual_override(None)

    def _start_recording(self) -> None:
        try:
            app_info = self._app_detector.get_active_app()
            app_id = app_info.identifier if app_info else None
            result = self._resolver.resolve(app_identifier=app_id)
            self._current_style = result.profile

            self._audio.start_recording(sample_rate=16000, channels=1)
            self._recording = True

            self.recording_started.emit(
                self._current_style.name or "日常",
                self._current_style.icon or "🍃",
            )
            logger.info("开始录音 — 风格: %s", self._current_style.name)
        except Exception as e:
            self.error_occurred.emit(f"录音启动失败: {e}")

    def _stop_recording(self) -> None:
        if not self._recording:
            return
        self._recording = False
        try:
            audio_data = self._audio.stop_recording()
        except Exception as e:
            self.error_occurred.emit(f"录音停止失败: {e}")
            return

        if not audio_data or len(audio_data) < 1600:
            self.error_occurred.emit("录音太短，请重试")
            return

        self.processing_started.emit()
        logger.info("录音结束 — %d bytes，开始处理", len(audio_data))

        thread = threading.Thread(
            target=self._process_pipeline,
            args=(audio_data,),
            name="voice-pipeline",
            daemon=True,
        )
        thread.start()

    def _process_pipeline(self, audio_data: bytes) -> None:
        try:
            transcript = self._transcribe(audio_data)
            if not transcript or not transcript.strip():
                self.error_occurred.emit("未检测到语音内容")
                return

            styled = self._apply_style(transcript)
            if not styled or not styled.strip():
                styled = transcript

            self._injector.inject(styled)

            self.result_ready.emit(
                styled, "neutral",
                self._current_style.name or "日常",
                self._current_style.icon or "🍃",
            )
            self._save_history(transcript, styled)
        except Exception as e:
            logger.error("处理管线异常: %s", e)
            self.error_occurred.emit(f"处理失败: {e}")

    def _transcribe(self, audio_data: bytes) -> str:
        try:
            from lingxi.engine.asr_faster_whisper import FasterWhisperEngine
            engine = FasterWhisperEngine()
            result = engine.transcribe(audio_data)
            return result.text
        except Exception as e:
            logger.warning("ASR 转录失败 (%s)", e)
            return "语音转录功能需要下载模型，请先在设置中配置 ASR 引擎"

    def _apply_style(self, text: str) -> str:
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
        return await client.rewrite(request)

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
        return await client.rewrite(request)

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
        except Exception:
            pass


# ── Overlay HUD 管理 ──────────────────────────────────

class HUDManager:
    """管理 OverlayHUD 的生命周期：展示、状态更新、自动隐藏。"""

    RESULT_DISPLAY_MS = 2500   # 结果显示时长
    ERROR_DISPLAY_MS = 3000    # 错误显示时长

    def __init__(self) -> None:
        self._hud: Optional[OverlayHUD] = None
        self._hide_timer = QTimer()
        self._hide_timer.setSingleShot(True)
        self._hide_timer.timeout.connect(self._hide)

    def _ensure_hud(self) -> OverlayHUD:
        if self._hud is None:
            self._hud = OverlayHUD()
        return self._hud

    def show_recording(self, style_name: str, style_icon: str) -> None:
        hud = self._ensure_hud()
        hud.update_state(
            state=OverlayHUD.State.RECORDING,
            text="",
            style_name=style_name,
            style_icon=style_icon,
        )
        if not hud.isVisible():
            hud.show_with_animation()

    def show_processing(self) -> None:
        hud = self._ensure_hud()
        hud.update_state(state=OverlayHUD.State.PROCESSING)

    def show_result(self, text: str, style_name: str, style_icon: str) -> None:
        hud = self._ensure_hud()
        preview = text[:80] + "…" if len(text) > 80 else text
        hud.update_state(
            state=OverlayHUD.State.RESULT,
            text=preview,
            style_name=style_name,
            style_icon=style_icon,
        )
        self._hide_timer.start(self.RESULT_DISPLAY_MS)

    def show_error(self, message: str) -> None:
        hud = self._ensure_hud()
        hud.update_state(
            state=OverlayHUD.State.ERROR,
            text=message[:80],
        )
        self._hide_timer.start(self.ERROR_DISPLAY_MS)

    def _hide(self) -> None:
        if self._hud and self._hud.isVisible():
            self._hud.hide_with_animation()


# ── 系统托盘 ──────────────────────────────────────────

class SystemTray:
    def __init__(self, app: QApplication, pipeline: VoicePipeline) -> None:
        self.app = app
        self.pipeline = pipeline
        self.tray = QSystemTrayIcon()
        self.tray.setIcon(create_app_icon())
        self.tray.setToolTip(APP_NAME)

        menu = QMenu()
        self.record_action = QAction("🎤 开始录音", menu)
        self.record_action.triggered.connect(lambda: pipeline.on_hotkey(False))
        menu.addAction(self.record_action)
        menu.addSeparator()
        self.style_menu = QMenu("风格切换")
        self._populate_style_menu()
        menu.addMenu(self.style_menu)
        menu.addSeparator()
        menu.addAction("设置...").triggered.connect(self._open_settings)
        menu.addSeparator()
        menu.addAction("退出").triggered.connect(self._quit)

        self.tray.setContextMenu(menu)
        self.tray.show()
        self.tray.activated.connect(self._on_tray_activated)
        logger.info("系统托盘已启动")

    def _populate_style_menu(self) -> None:
        self.style_menu.clear()
        try:
            for style in StyleProfileStore().list_all():
                icon = style.icon or "🍃"
                action = QAction(f"{icon} {style.name}", self.style_menu)
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

    def _quit(self) -> None:
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

    pipeline = VoicePipeline()
    tray = SystemTray(app, pipeline)
    hud = HUDManager()

    # ── 热键 ──────────────────────────────────────
    hotkey = HotkeyManager()
    try:
        hotkey.register_default(pipeline.on_hotkey)
        hotkey.start()
        hotkey.attach_pynput_listener()
        logger.info("pynput 全局热键监听已启动")
    except ImportError:
        logger.warning("pynput 未安装，请使用托盘菜单触发录音")
    except Exception as e:
        logger.warning("pynput 启动失败: %s，请使用托盘菜单触发录音", e)

    # ── 信号 → Overlay HUD ────────────────────────
    pipeline.recording_started.connect(hud.show_recording)
    pipeline.processing_started.connect(hud.show_processing)
    pipeline.result_ready.connect(hud.show_result)
    pipeline.error_occurred.connect(hud.show_error)
    pipeline.style_picker_requested.connect(
        lambda: logger.info("长按热键 — 弹出风格选择器（待实现 Overlay）")
    )

    # ── 清理 ──────────────────────────────────────
    signal.signal(signal.SIGINT, lambda sig, frame: app.quit())
    signal.signal(signal.SIGTERM, lambda sig, frame: app.quit())
    app.aboutToQuit.connect(hotkey.stop)

    logger.info(
        f"{APP_NAME} 就绪 — 按 {HotkeyDef.default_for_platform()} 开始录音"
    )
    exit_code = app.exec()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
