"""Text Injector — 三级文本注入策略。

注入流程:
  1. 保存剪贴板 → 复制新文本 → 检测 CJK 输入法 → 切换 ASCII → 粘贴 → 恢复输入法 → 恢复剪贴板
  2. 若粘贴失败 → pynput 逐字输入
  3. 若 pynput 也失败 → 仅复制到剪贴板并提示用户手动粘贴

跨平台支持:
  - macOS:   subprocess defaults read 检测 CJK, Ctrl+Space (或 event taps) 切换
  - Windows: ctypes GetKeyboardLayout 检测, Win+Space 切换
  - Linux:   无自动检测 (返回 False), 尝试切换
"""

from __future__ import annotations

import logging
import platform
import subprocess
import time
from typing import Optional

from lingxi.io.clipboard import Clipboard, ClipboardError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_SYSTEM = platform.system()
_IS_MACOS = _SYSTEM == "Darwin"
_IS_WINDOWS = _SYSTEM == "Windows"
_IS_LINUX = _SYSTEM == "Linux"

# 粘贴快捷键
if _IS_MACOS:
    PASTE_MODIFIER = "command"
else:
    PASTE_MODIFIER = "ctrl"
PASTE_KEY = "v"


# ---------------------------------------------------------------------------
# 注入异常
# ---------------------------------------------------------------------------

class TextInjectionError(Exception):
    """文本注入失败（三级策略均未成功）。"""
    pass


# ---------------------------------------------------------------------------
# CJK 输入法检测 / 切换
# ---------------------------------------------------------------------------

def _detect_cjk_macos() -> bool:
    """macOS: 通过 defaults read 检测当前是否为 CJK 输入法。

    检查 com.apple.HIToolbox AppleCurrentKeyboardLayoutInputSource。
    若 InputSourceKind 是 "Input Mode" 且包含 CJK 相关 ID 则返回 True。
    """
    try:
        result = subprocess.run(
            [
                "defaults", "read",
                "com.apple.HIToolbox",
                "AppleCurrentKeyboardLayoutInputSource",
            ],
            capture_output=True,
            text=True,
            timeout=2,
        )
        output = result.stdout.lower()
        # CJK 输入法特征
        cjk_indicators = [
            "input mode",           # 输入模式（非 ASCII）
            "com.apple.inputmethod",  # 第三方输入法
            "pinyin", "shuangpin", "wubi",
            "cangjie", "zhuyin", "sucheng",
            "japanese", "kana", "romaji",
            "korean", "hangul",
            "sogou", "baidu", "rime",
            "tcim", "yahoo keykey",
        ]
        for indicator in cjk_indicators:
            if indicator in output:
                logger.debug("检测到 CJK 输入法 (macOS): %s", indicator)
                return True
        return False
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        logger.debug("CJK 检测失败 (macOS): %s", exc)
        return False


def _detect_cjk_windows() -> bool:
    """Windows: 通过 ctypes GetKeyboardLayout 检测 CJK 输入法。

    检查当前前台窗口的键盘布局 HKL。
    CJK 语言 ID: 0x04 (中文), 0x11 (日文), 0x12 (韩文)。
    """
    try:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.windll.user32
        # 获取前台窗口线程的键盘布局
        foreground_window = user32.GetForegroundWindow()
        thread_id = user32.GetWindowThreadProcessId(foreground_window, 0)
        hkl = user32.GetKeyboardLayout(thread_id)

        # 低字 (low word) 是语言 ID
        lang_id = hkl & 0xFFFF
        # CJK 语言 ID
        cjk_ids = {
            0x0004,   # zh-CHS (简体中文)
            0x0404,   # zh-TW (繁体中文)
            0x0804,   # zh-CN
            0x0c04,   # zh-HK
            0x1004,   # zh-SG
            0x1404,   # zh-MO
            0x0011,   # ja-JP
            0x0411,   # ja-JP
            0x0012,   # ko-KR
            0x0412,   # ko-KR
        }
        if lang_id in cjk_ids:
            logger.debug("检测到 CJK 键盘布局 (Windows): 0x%04X", lang_id)
            return True
        return False
    except Exception as exc:
        logger.debug("CJK 检测失败 (Windows): %s", exc)
        return False


def _detect_cjk_linux() -> bool:
    """Linux: 通过环境变量检查当前输入法。

    常见环境变量: XMODIFIERS, GTK_IM_MODULE, QT_IM_MODULE。
    """
    try:
        import os

        for var in ("XMODIFIERS", "GTK_IM_MODULE", "QT_IM_MODULE", "IM_CONFIG_PHASE"):
            val = os.environ.get(var, "")
            if val and val != "@im=none":
                cjk_indicators = [
                    "fcitx", "ibus", "scim", "uim", "gcin", "hime",
                    "pinyin", "chewing", "mozc", "anthy",
                ]
                for indicator in cjk_indicators:
                    if indicator in val.lower():
                        logger.debug("检测到 CJK 输入法框架 (Linux): %s=%s", var, val)
                        return True
        return False
    except Exception as exc:
        logger.debug("CJK 检测失败 (Linux): %s", exc)
        return False


def _detect_cjk_input_method() -> bool:
    """跨平台 CJK 输入法检测。

    Returns:
        bool: 当前激活 CJK 输入法则返回 True
    """
    if _IS_MACOS:
        return _detect_cjk_macos()
    elif _IS_WINDOWS:
        return _detect_cjk_windows()
    else:
        return _detect_cjk_linux()


# ---------------------------------------------------------------------------
# 输入法切换
# ---------------------------------------------------------------------------

def _switch_input_method_macos(to_ascii: bool = True) -> bool:
    """macOS 输入法切换。

    使用 Ctrl+Space 切换（macOS 默认快捷键）。
    也可使用 osascript 调用系统方法。

    Returns:
        bool: 切换操作是否已执行
    """
    try:
        import pyautogui

        if to_ascii:
            # macOS: 切换到上一个输入法（通常是 ABC/ASCII）
            pyautogui.hotkey("ctrl", "space", interval=0.05)
            logger.debug("macOS 输入法切换: Ctrl+Space")
        else:
            # 切回去也是同一个快捷键
            pyautogui.hotkey("ctrl", "space", interval=0.05)
            logger.debug("macOS 输入法恢复: Ctrl+Space")
        return True
    except ImportError:
        logger.warning("pyautogui 未安装，尝试 osascript 切换输入法...")
        try:
            # 回退: 使用 AppleScript 切换到 ABC 输入法
            if to_ascii:
                script = '''
                tell application "System Events"
                    key code 49 using {control down}
                end tell
                '''
            else:
                script = '''
                tell application "System Events"
                    key code 49 using {control down}
                end tell
                '''
            subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                timeout=2,
            )
            logger.debug("macOS 输入法切换 (osascript)")
            return True
        except Exception as exc:
            logger.warning("osascript 输入法切换失败: %s", exc)
            return False
    except Exception as exc:
        logger.warning("macOS 输入法切换失败: %s", exc)
        return False


def _switch_input_method_windows(to_ascii: bool = True) -> bool:
    """Windows 输入法切换。

    使用 Win+Space 切换输入法。
    """
    try:
        import pyautogui

        # Windows: Win+Space 循环输入法
        pyautogui.hotkey("win", "space", interval=0.05)
        logger.debug("Windows 输入法切换: Win+Space")
        return True
    except ImportError:
        logger.warning("pyautogui 未安装，无法自动切换 Windows 输入法")
        return False
    except Exception as exc:
        logger.warning("Windows 输入法切换失败: %s", exc)
        return False


def _switch_input_method_linux(to_ascii: bool = True) -> bool:
    """Linux 输入法切换。尽力而为。"""
    try:
        import pyautogui

        # 大多数 Linux 输入法框架使用 Ctrl+Space 或 Shift
        pyautogui.hotkey("ctrl", "space", interval=0.05)
        logger.debug("Linux 输入法切换: Ctrl+Space")
        return True
    except ImportError:
        return False
    except Exception as exc:
        logger.warning("Linux 输入法切换失败: %s", exc)
        return False


def _switch_to_ascii() -> bool:
    """跨平台切换到 ASCII 输入模式。

    Returns:
        bool: 切换是否成功
    """
    if _IS_MACOS:
        return _switch_input_method_macos(to_ascii=True)
    elif _IS_WINDOWS:
        return _switch_input_method_windows(to_ascii=True)
    else:
        return _switch_input_method_linux(to_ascii=True)


def _restore_input_method() -> None:
    """恢复之前的输入法（切换回去）。"""
    if _IS_MACOS:
        _switch_input_method_macos(to_ascii=False)
    elif _IS_WINDOWS:
        _switch_input_method_windows(to_ascii=False)
    else:
        _switch_input_method_linux(to_ascii=False)


# ---------------------------------------------------------------------------
# 粘贴操作
# ---------------------------------------------------------------------------

def _paste_via_pyautogui() -> bool:
    """使用 pyautogui 发送粘贴快捷键。"""
    try:
        import pyautogui

        pyautogui.hotkey(PASTE_MODIFIER, PASTE_KEY, interval=0.05)
        logger.debug("粘贴快捷键已发送: %s+%s", PASTE_MODIFIER, PASTE_KEY)
        return True
    except ImportError:
        logger.warning("pyautogui 未安装，无法发送粘贴快捷键")
        return False
    except Exception as exc:
        logger.warning("粘贴快捷键失败: %s", exc)
        return False


# ---------------------------------------------------------------------------
# 逐字输入 (第二级回退)
# ---------------------------------------------------------------------------

def _type_via_pynput(text: str) -> bool:
    """使用 pynput 逐字输入文本。

    Args:
        text: 要输入的文本

    Returns:
        bool: 是否成功
    """
    try:
        from pynput.keyboard import Controller as KeyboardController

        controller = KeyboardController()
        for char in text:
            controller.type(char)
            time.sleep(0.001)  # 微延迟，避免丢字
        logger.debug("pynput 逐字输入完成，%d 字符", len(text))
        return True
    except ImportError:
        logger.warning("pynput 未安装，无法逐字输入")
        return False
    except Exception as exc:
        logger.error("pynput 逐字输入失败: %s", exc)
        return False


# ---------------------------------------------------------------------------
# TextInjector
# ---------------------------------------------------------------------------

class TextInjector:
    """三级文本注入器。

    注入策略:
      Level 1 — 剪贴板粘贴 (复制到剪贴板 → 切换输入法 → 发送粘贴快捷键)
      Level 2 — pynput 逐字键入 (如果粘贴失败)
      Level 3 — 仅复制到剪贴板，提示用户手动粘贴

    Usage:
        injector = TextInjector()
        success = injector.inject("你好，世界")
    """

    def __init__(self) -> None:
        self._clipboard = Clipboard()
        self._cjk_was_detected: bool = False
        self._last_injection_level: int = 0

    @property
    def last_injection_level(self) -> int:
        """最近一次注入所使用的策略级别 (1/2/3)。"""
        return self._last_injection_level

    # ------------------------------------------------------------------
    # 主入口
    # ------------------------------------------------------------------

    def inject(self, text: str) -> bool:
        """注入文本到当前活动应用。

        三级注入策略:
          1. 剪贴板粘贴 (默认)
          2. pynput 逐字输入
          3. Overlay 手动复制

        Args:
            text: 要注入的文本

        Returns:
            bool: 注入成功返回 True（Level 1 或 Level 2 成功）

        Raises:
            TextInjectionError: 三级策略均失败
        """
        if not text:
            logger.warning("空文本，跳过注入。")
            return False

        # --- Level 1: 剪贴板粘贴 ---
        if self._inject_via_clipboard_paste(text):
            self._last_injection_level = 1
            return True

        # --- Level 2: pynput 逐字输入 ---
        if self._inject_via_keystroke(text):
            self._last_injection_level = 2
            return True

        # --- Level 3: 仅复制到剪贴板 + 提示 ---
        self._inject_via_clipboard_only(text)
        self._last_injection_level = 3
        raise TextInjectionError(
            "文本注入失败。三级策略均未成功。\n"
            "文本已复制到剪贴板，请手动粘贴 (Ctrl+V / Cmd+V)。"
        )

    # ------------------------------------------------------------------
    # Level 1: 剪贴板粘贴
    # ------------------------------------------------------------------

    def _inject_via_clipboard_paste(self, text: str) -> bool:
        """Level 1: 保存剪贴板 → 复制新文本 → 检测CJK → 切换ASCII → 粘贴 → 恢复输入法 → 恢复剪贴板。"""
        try:
            # Step 1: 保存当前剪贴板
            original = self._save_clipboard()

            # Step 2: 复制新文本
            self._clipboard.copy(text)

            # Step 3: 检测 CJK 输入法
            self._cjk_was_detected = _detect_cjk_input_method()

            # Step 4: 若检测到 CJK，临时切换到 ASCII
            input_switched = False
            if self._cjk_was_detected:
                input_switched = _switch_to_ascii()
                if input_switched:
                    time.sleep(0.1)  # 等待切换生效

            # Step 5: 发送粘贴快捷键
            paste_ok = _paste_via_pyautogui()
            time.sleep(0.05)

            # Step 6: 恢复输入法
            if input_switched:
                _restore_input_method()
                time.sleep(0.05)

            # Step 7: 恢复剪贴板
            self._restore_clipboard(original)

            if paste_ok:
                logger.info("Level 1 剪贴板粘贴成功 (%d 字符)", len(text))
                return True
            else:
                logger.warning("Level 1 粘贴快捷键发送失败")
                return False

        except ClipboardError as exc:
            logger.warning("Level 1 剪贴板操作失败: %s", exc)
            return False
        except Exception as exc:
            logger.error("Level 1 注入异常: %s", exc, exc_info=True)
            return False

    # ------------------------------------------------------------------
    # Level 2: pynput 逐字输入
    # ------------------------------------------------------------------

    def _inject_via_keystroke(self, text: str) -> bool:
        """Level 2: pynput 逐字键入。"""
        try:
            # 检测并切换输入法
            self._cjk_was_detected = _detect_cjk_input_method()
            input_switched = False
            if self._cjk_was_detected:
                input_switched = _switch_to_ascii()
                time.sleep(0.1)

            # 逐字输入
            ok = _type_via_pynput(text)

            # 恢复输入法
            if input_switched:
                _restore_input_method()
                time.sleep(0.05)

            if ok:
                logger.info("Level 2 pynput 逐字输入成功 (%d 字符)", len(text))
                return True
            return False

        except Exception as exc:
            logger.error("Level 2 逐字输入异常: %s", exc)
            return False

    # ------------------------------------------------------------------
    # Level 3: 仅复制到剪贴板
    # ------------------------------------------------------------------

    def _inject_via_clipboard_only(self, text: str) -> None:
        """Level 3: 仅复制到剪贴板，用户手动粘贴。"""
        try:
            self._clipboard.copy(text)
            logger.info("Level 3: 文本已复制到剪贴板，请手动粘贴 (%d 字符)", len(text))
        except ClipboardError as exc:
            logger.error("Level 3 剪贴板操作也失败了: %s", exc)

    # ------------------------------------------------------------------
    # 剪贴板保存 / 恢复 (便捷方法)
    # ------------------------------------------------------------------

    def _save_clipboard(self) -> str:
        """保存当前剪贴板内容。

        Returns:
            str: 原始剪贴板文本
        """
        try:
            return self._clipboard.paste()
        except ClipboardError:
            logger.warning("无法读取当前剪贴板内容")
            return ""

    def _restore_clipboard(self, original: str) -> None:
        """恢复剪贴板为原始内容。

        Args:
            original: 原始剪贴板文本
        """
        try:
            if original:
                self._clipboard.copy(original)
            else:
                # 如果之前剪贴板为空，清空它
                self._clipboard.copy("")
            logger.debug("剪贴板已恢复")
        except ClipboardError as exc:
            logger.warning("恢复剪贴板失败: %s", exc)
