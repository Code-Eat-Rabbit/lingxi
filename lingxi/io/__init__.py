# I/O Layer
# 音频录制、全局热键、文本注入

from lingxi.io.audio_recorder import AudioRecorder, AudioRecorderError, MicPermissionError
from lingxi.io.clipboard import Clipboard, ClipboardError
from lingxi.io.hotkey_manager import (
    HotkeyConflictError,
    HotkeyDef,
    HotkeyManager,
    Key,
)
from lingxi.io.text_injector import TextInjectionError, TextInjector

__all__ = [
    # Audio
    "AudioRecorder",
    "AudioRecorderError",
    "MicPermissionError",
    # Clipboard
    "Clipboard",
    "ClipboardError",
    # Hotkey
    "HotkeyConflictError",
    "HotkeyDef",
    "HotkeyManager",
    "Key",
    # Text Injection
    "TextInjectionError",
    "TextInjector",
]
