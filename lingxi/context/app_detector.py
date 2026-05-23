"""上下文感知 — 当前应用检测与窗口标题读取。

跨平台支持 macOS、Windows、Linux。
- macOS:    osascript (AppleScript)
- Windows:  ctypes + Win32 API
- Linux:    xdotool（fallback: /proc）
"""

from __future__ import annotations

import logging
import platform
import re
import subprocess
from dataclasses import dataclass
from typing import ClassVar, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# 进程标识符 → 应用显示名 映射表
# ---------------------------------------------------------------------------
_APP_NAME_MAP: dict[str, str] = {
    # 微信
    "wechat.exe": "微信",
    "wechat": "微信",
    "weixin": "微信",
    # 企业微信
    "wecom.exe": "企业微信",
    "wecom": "企业微信",
    "wework": "企业微信",
    # 钉钉
    "dingtalk.exe": "钉钉",
    "dingtalk": "钉钉",
    # Outlook / 邮件
    "outlook.exe": "邮件",
    "microsoft outlook": "邮件",
    "microsoftoutlook": "邮件",
    # Telegram
    "telegram.exe": "Telegram",
    "telegram": "Telegram",
    "telegram desktop": "Telegram",
    "telegramdesktop": "Telegram",
    # QQ
    "qq.exe": "QQ",
    "qq": "QQ",
    # iMessage / 短信
    "messages": "短信",
    "imessage": "短信",
    "com.apple.imessage": "短信",
    "com.apple.mobile sms": "短信",
    "com.apple.mobilesms": "短信",
}


def _resolve_app_name(identifier: str) -> str:
    """将进程标识符映射为中文显示名。

    Args:
        identifier: 进程名（如 "WeCom.exe"）或 bundle identifier

    Returns:
        中文显示名（如 "企业微信"）；未匹配时返回原标识符
    """
    key = identifier.lower().strip()
    if key in _APP_NAME_MAP:
        return _APP_NAME_MAP[key]
    # 模糊匹配：尝试匹配前缀（处理版本后缀等）
    for known_key, display_name in _APP_NAME_MAP.items():
        if key.startswith(known_key) or known_key.startswith(key):
            return display_name
    return identifier


# ---------------------------------------------------------------------------
# AppInfo
# ---------------------------------------------------------------------------


@dataclass
class AppInfo:
    """当前前台应用信息。

    Attributes:
        name:       应用显示名（如 "企业微信"）
        pid:        进程 ID，获取失败时为 -1
        identifier: 进程名或 bundle identifier（如 "WeCom.exe"）
        title:      窗口标题，获取失败时为空字符串
    """

    name: str
    pid: int
    identifier: str
    title: str


# ---------------------------------------------------------------------------
# AppDetector
# ---------------------------------------------------------------------------


class AppDetector:
    """跨平台当前应用检测器。

    检测当前前台应用的名称、PID 和窗口标题。
    平台适配：
        macOS   — osascript (AppleScript)
        Windows — ctypes + Win32 API
        Linux   — xdotool（fallback: /proc）

    Usage:
        detector = AppDetector()
        app = detector.get_active_app()
        if app:
            print(f"{app.name}: {app.title}")
    """

    # v1.0 已知 IM 应用标识符集合（用于快速 is_known_app 检查）
    KNOWN_IDENTIFIERS: ClassVar[set[str]] = {
        "wechat.exe", "wechat", "weixin",
        "wecom.exe", "wecom", "wework",
        "dingtalk.exe", "dingtalk",
        "outlook.exe", "microsoft outlook", "microsoftoutlook",
        "telegram.exe", "telegram", "telegram desktop", "telegramdesktop",
        "qq.exe", "qq",
        "messages", "imessage",
        "com.apple.imessage", "com.apple.mobile sms", "com.apple.mobilesms",
    }

    def __init__(self) -> None:
        self._system: str = platform.system()

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def get_active_app(self) -> Optional[AppInfo]:
        """获取当前前台应用信息。

        Returns:
            AppInfo，检测失败时返回 None
        """
        try:
            if self._system == "Darwin":
                return self._get_macos_active_app()
            elif self._system == "Windows":
                return self._get_windows_active_app()
            else:
                return self._get_linux_active_app()
        except Exception:
            logger.debug("获取前台应用信息失败", exc_info=True)
            return None

    def is_known_app(self, identifier: str) -> bool:
        """检查是否为已知支持的 IM 应用。

        Args:
            identifier: 进程标识符（如 "WeCom.exe"）

        Returns:
            是否在已知应用映射表中
        """
        return identifier.lower().strip() in self.KNOWN_IDENTIFIERS

    # ------------------------------------------------------------------
    # macOS
    # ------------------------------------------------------------------

    @staticmethod
    def _get_macos_active_app() -> Optional[AppInfo]:
        """macOS: 使用 osascript 获取前台应用信息。

        AppleScript 一次性获取 {进程名, PID, 窗口标题}，
        减少 subprocess 调用次数。
        """
        script = (
            'tell application "System Events"\n'
            '  tell first process whose frontmost is true\n'
            '    return {name, unix id, title of front window}\n'
            '  end tell\n'
            'end tell'
        )
        try:
            result = subprocess.run(
                ["osascript", "-e", script],
                capture_output=True,
                text=True,
                timeout=3,
            )
            if result.returncode != 0:
                logger.debug("osascript 失败: %s", result.stderr.strip())
                return None

            # AppleScript 输出格式: "App Name, 12345, Window Title"
            output = result.stdout.strip()
            parts = _parse_osascript_output(output)
            if parts is None:
                return None

            identifier, pid, title = parts
            display_name = _resolve_app_name(identifier)

            return AppInfo(
                name=display_name,
                pid=pid,
                identifier=identifier,
                title=title,
            )
        except FileNotFoundError:
            logger.debug("osascript 不可用")
            return None
        except subprocess.TimeoutExpired:
            logger.debug("osascript 超时")
            return None

    # ------------------------------------------------------------------
    # Windows
    # ------------------------------------------------------------------

    @staticmethod
    def _get_windows_active_app() -> Optional[AppInfo]:
        """Windows: 使用 ctypes + Win32 API 获取前台应用信息。

        调用链：
            GetForegroundWindow → GetWindowTextW (标题)
                              → GetWindowThreadProcessId (PID)
                              → OpenProcess + QueryFullProcessImageNameW (进程名)
        """
        import ctypes
        from ctypes import wintypes

        try:
            user32 = ctypes.windll.user32
            kernel32 = ctypes.windll.kernel32
        except AttributeError:
            logger.debug("Win32 API 不可用（非 Windows 平台）")
            return None

        try:
            hwnd = user32.GetForegroundWindow()
            if not hwnd:
                return None

            # 窗口标题
            title_buf = ctypes.create_unicode_buffer(512)
            user32.GetWindowTextW(hwnd, title_buf, 512)
            title = title_buf.value or ""

            # 进程 ID
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            pid_value = pid.value

            # 进程名 — 优先使用 psutil
            identifier = _get_win_process_name(pid_value)
            if not identifier:
                identifier = _get_win_process_name_via_api(kernel32, pid_value)

            display_name = _resolve_app_name(identifier)

            return AppInfo(
                name=display_name,
                pid=pid_value,
                identifier=identifier,
                title=title,
            )
        except Exception:
            logger.debug("Windows 前台应用检测失败", exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Linux
    # ------------------------------------------------------------------

    @staticmethod
    def _get_linux_active_app() -> Optional[AppInfo]:
        """Linux: 使用 xdotool 获取前台应用信息。

        xdotool getactivewindow          → 窗口 ID
        xdotool getwindowname <id>       → 窗口标题
        xdotool getwindowpid <id>        → 进程 PID
        """
        try:
            # 获取活动窗口 ID
            win_id = _xdotool("getactivewindow")
            if not win_id:
                return _get_linux_fallback()

            # 窗口标题
            title = _xdotool("getwindowname", win_id) or ""

            # 进程 PID
            pid_str = _xdotool("getwindowpid", win_id)
            pid = -1
            if pid_str:
                try:
                    pid = int(pid_str)
                except ValueError:
                    pass

            # 从 PID 获取进程名
            identifier = _get_linux_process_name(pid) if pid > 0 else ""

            display_name = _resolve_app_name(identifier) if identifier else title

            return AppInfo(
                name=display_name,
                pid=pid,
                identifier=identifier,
                title=title,
            )
        except Exception:
            logger.debug("Linux 前台应用检测失败", exc_info=True)
            return None


# ===================================================================
# 内部辅助函数
# ===================================================================


def _parse_osascript_output(output: str) -> Optional[tuple[str, int, str]]:
    """解析 osascript 返回值。

    AppleScript list → "item1, item2, item3"
    只按最外层逗号分割，防止窗口标题中的逗号被错误拆分。
    """
    # 用正则匹配：非贪婪捕获任意字符直到逗号+空格
    m = re.match(r"^(.+?), (-?\d+)(?:, (.*))?$", output)
    if not m:
        return None
    identifier = m.group(1)
    try:
        pid = int(m.group(2))
    except ValueError:
        pid = -1
    title = m.group(3) or ""
    return identifier, pid, title


def _xdotool(*args: str) -> Optional[str]:
    """调用 xdotool 并返回 stdout 的第一行。"""
    try:
        result = subprocess.run(
            ["xdotool", *args],
            capture_output=True,
            text=True,
            timeout=2,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return None


def _get_linux_fallback() -> Optional[AppInfo]:
    """Linux fallback：无 xdotool 时无法准确检测前台窗口。"""
    logger.debug("Linux: xdotool 不可用，无法获取前台应用信息")
    return None


def _get_linux_process_name(pid: int) -> str:
    """Linux: 从 PID 获取进程名。

    优先使用 psutil，fallback 到 /proc/<pid>/comm。
    """
    try:
        import psutil  # noqa: F811
        return psutil.Process(pid).name()
    except ImportError:
        pass
    except Exception:
        logger.debug("psutil.Process(%d) 失败", pid, exc_info=True)

    # /proc fallback
    try:
        comm_path = f"/proc/{pid}/comm"
        with open(comm_path, "r") as f:
            return f.read().strip()
    except Exception:
        logger.debug("/proc/%d/comm 读取失败", pid, exc_info=True)
    return ""


def _get_win_process_name(pid: int) -> str:
    """Windows: 使用 psutil 从 PID 获取进程名。"""
    try:
        import psutil
        return psutil.Process(pid).name()
    except ImportError:
        pass
    except Exception:
        logger.debug("psutil.Process(%d) 失败", pid, exc_info=True)
    return ""


def _get_win_process_name_via_api(kernel32, pid: int) -> str:
    """Windows: 使用 Win32 API 从 PID 获取进程名（psutil 不可用时的 fallback）。"""
    import ctypes
    from ctypes import wintypes

    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
    try:
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if not handle:
            return ""
        exe_buf = ctypes.create_unicode_buffer(260)
        size = wintypes.DWORD(260)
        if kernel32.QueryFullProcessImageNameW(handle, 0, exe_buf, ctypes.byref(size)):
            return exe_buf.value.rsplit("\\", 1)[-1]
        kernel32.CloseHandle(handle)
    except Exception:
        pass
    return ""
