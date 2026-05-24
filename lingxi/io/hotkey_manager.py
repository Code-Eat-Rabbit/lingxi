"""Hotkey Manager — pynput 全局热键管理。

支持:
- 全局热键注册/注销
- 300ms 防抖（避免双击误触发）
- 长按检测（长按=弹出风格选择器，阈值可配置，默认 500ms）
- 热键注册冲突检测
- 跨平台: macOS / Windows / Linux
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Callable, Dict, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 类型别名
# ---------------------------------------------------------------------------

# 回调签名: callback(is_long_press: bool) -> None
HotkeyCallback = Callable[[bool], None]


# ---------------------------------------------------------------------------
# 热键定义
# ---------------------------------------------------------------------------

class Key(str, Enum):
    """pynput 键名枚举别名。"""

    CTRL = "ctrl"
    CTRL_L = "ctrl_l"
    CTRL_R = "ctrl_r"
    SHIFT = "shift"
    SHIFT_L = "shift_l"
    SHIFT_R = "shift_r"
    ALT = "alt"
    ALT_L = "alt_l"
    ALT_R = "alt_r"
    CMD = "cmd"
    CMD_L = "cmd_l"
    CMD_R = "cmd_r"
    FN = "fn"
    SPACE = "space"
    ESC = "esc"
    TAB = "tab"


@dataclass
class HotkeyDef:
    """热键定义。"""

    key: str  # pynput Key 字符串
    modifiers: Set[str] = field(default_factory=set)

    @classmethod
    def ctrl(cls, extra_key: Optional[str] = None) -> "HotkeyDef":
        """创建 Ctrl 热键（Windows/Linux 默认）。"""
        mods = {Key.CTRL.value}
        key = extra_key or Key.SPACE.value
        return cls(key=key, modifiers=mods)

    @classmethod
    def command(cls, extra_key: Optional[str] = None) -> "HotkeyDef":
        """创建 Command 热键（macOS 默认）。"""
        mods = {Key.CMD.value}
        key = extra_key or Key.SPACE.value
        return cls(key=key, modifiers=mods)

    @classmethod
    def fn(cls, extra_key: Optional[str] = None) -> "HotkeyDef":
        """创建 Fn 热键。"""
        key = extra_key or Key.FN.value
        return cls(key=key)

    @classmethod
    def fn_command(cls) -> "HotkeyDef":
        """创建 Fn+Command 热键（macOS 推荐，避免与 Spotlight 冲突）。"""
        return cls(key=Key.FN.value, modifiers={Key.CMD.value})

    @classmethod
    def default_for_platform(cls) -> "HotkeyDef":
        """返回平台默认热键。"""
        import platform

        system = platform.system()
        if system == "Darwin":
            return cls.fn_command()  # macOS: Fn+Cmd (避免与 Cmd+Space 冲突)
        else:
            return cls.ctrl()  # Windows/Linux: Ctrl+Space

    def to_pynput_combo(self) -> str:
        """转换为 pynput hotkey 格式的快捷键组合字符串。

        例如: '<ctrl>+<space>'
        """
        parts = [f"<{m}>" for m in sorted(self.modifiers)]
        parts.append(self.key if self.key in ("<fn>",) else f"<{self.key}>")
        return "+".join(parts)

    def __str__(self) -> str:
        return self.to_pynput_combo()


# ---------------------------------------------------------------------------
# 热键状态
# ---------------------------------------------------------------------------

class PressState(Enum):
    """按键状态。"""

    IDLE = auto()
    PRESSED = auto()  # 刚按下，等待判定
    HOLDING = auto()  # 长按中


@dataclass
class HotkeyState:
    """单个热键的运行时状态。"""

    definition: HotkeyDef
    callback: HotkeyCallback
    last_trigger_time: float = 0.0
    press_time: float = 0.0  # 按下时刻
    release_time: float = 0.0  # 释放时刻
    state: PressState = PressState.IDLE
    long_press_triggered: bool = False


# ---------------------------------------------------------------------------
# HotkeyManager
# ---------------------------------------------------------------------------


class HotkeyConflictError(Exception):
    """热键注册冲突异常。"""
    pass


class HotkeyManager:
    """全局热键管理器。

    Usage:
        mgr = HotkeyManager()
        mgr.register_hotkey(HotkeyDef.ctrl(), on_hotkey)
        mgr.start()
        ...
        mgr.stop()
    """

    DEBOUNCE_MS: float = 300.0  # 防抖间隔（毫秒）
    LONG_PRESS_THRESHOLD_MS: float = 500.0  # 长按判定阈值（毫秒）
    POLL_INTERVAL: float = 0.05  # 状态轮询间隔（秒）

    def __init__(
        self,
        debounce_ms: float = 300.0,
        long_press_threshold_ms: float = 500.0,
    ) -> None:
        """
        Args:
            debounce_ms: 防抖间隔（毫秒），期间重复触发被忽略
            long_press_threshold_ms: 长按判定阈值（毫秒）
        """
        self.DEBOUNCE_MS = debounce_ms
        self.LONG_PRESS_THRESHOLD_MS = long_press_threshold_ms

        self._hotkeys: Dict[str, HotkeyState] = {}  # combo_str -> HotkeyState
        self._listener: Optional[object] = None  # pynput GlobalHotKeys
        self._lock = threading.Lock()
        self._running: bool = False
        self._watcher_thread: Optional[threading.Thread] = None
        self._keyboard_controller: Optional[object] = None  # pynput Controller (用于判断修饰键状态)

    # ------------------------------------------------------------------
    # 热键注册
    # ------------------------------------------------------------------

    def register_hotkey(
        self,
        hotkey: HotkeyDef,
        callback: HotkeyCallback,
    ) -> bool:
        """注册全局热键。

        Args:
            hotkey: 热键定义
            callback: 回调函数，签名为 callback(is_long_press: bool)

        Returns:
            bool: 注册成功返回 True

        Raises:
            HotkeyConflictError: 热键已被注册
        """
        combo = hotkey.to_pynput_combo()

        with self._lock:
            if combo in self._hotkeys:
                raise HotkeyConflictError(
                    f"热键 '{combo}' 已被注册。请先调用 unregister_hotkey 注销。"
                )
            self._hotkeys[combo] = HotkeyState(
                definition=hotkey,
                callback=callback,
            )
            logger.info("注册热键: %s", combo)
            return True

    def unregister_hotkey(self, hotkey: HotkeyDef) -> bool:
        """注销全局热键。

        Args:
            hotkey: 热键定义

        Returns:
            bool: 注销成功返回 True；热键未注册返回 False
        """
        combo = hotkey.to_pynput_combo()

        with self._lock:
            if combo not in self._hotkeys:
                logger.warning("热键 '%s' 未注册，无需注销。", combo)
                return False
            del self._hotkeys[combo]
            logger.info("注销热键: %s", combo)
            return True

    def register_default(self, callback: HotkeyCallback) -> bool:
        """注册平台默认热键。"""
        return self.register_hotkey(HotkeyDef.default_for_platform(), callback)

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    def start(self) -> None:
        """启动热键监听。

        需要在主线程或事件循环中调用。使用独立的 watcher 线程进行长按检测。
        """
        if self._running:
            logger.warning("HotkeyManager 已在运行中。")
            return

        self._running = True
        self._watcher_thread = threading.Thread(
            target=self._watcher_loop,
            name="hotkey-watcher",
            daemon=True,
        )
        self._watcher_thread.start()
        logger.info("HotkeyManager 已启动 (debounce=%dms, long_press=%dms)",
                     self.DEBOUNCE_MS, self.LONG_PRESS_THRESHOLD_MS)

    def stop(self) -> None:
        """停止热键监听并清理资源。"""
        self._running = False
        if self._watcher_thread and self._watcher_thread.is_alive():
            self._watcher_thread.join(timeout=2.0)
        logger.info("HotkeyManager 已停止")

    # ------------------------------------------------------------------
    # 按键事件处理 (由外部 UI 层或事件循环调用)
    # ------------------------------------------------------------------

    def on_key_press(self, key_str: str, modifiers: Set[str]) -> None:
        """处理按键按下事件。

        由 pynput 的 on_press 回调或 UI 事件循环调用。

        Args:
            key_str: 按键字符串表示（如 'space', 'a'）
            modifiers: 当前激活的修饰键集合
        """
        now = time.monotonic()

        with self._lock:
            for combo, state in self._hotkeys.items():
                if not self._match_combo(key_str, modifiers, state.definition):
                    continue

                # 防抖检查
                if now - state.last_trigger_time < self.DEBOUNCE_MS / 1000.0:
                    logger.debug("热键 %s 防抖中，忽略。", combo)
                    return

                # 记录按下
                state.press_time = now
                state.state = PressState.PRESSED
                state.long_press_triggered = False
                state.last_trigger_time = now
                logger.debug("热键 %s 按下", combo)

    def on_key_release(self, key_str: str, modifiers: Set[str]) -> None:
        """处理按键释放事件。

        如果是短按（未触发长按），则立即调用回调。

        Args:
            key_str: 按键字符串表示
            modifiers: 当前激活的修饰键集合
        """
        now = time.monotonic()

        with self._lock:
            for combo, state in self._hotkeys.items():
                if not self._match_combo(key_str, modifiers, state.definition):
                    continue

                if state.state == PressState.IDLE:
                    continue

                # 判定是否长按
                hold_duration_ms = (now - state.press_time) * 1000
                is_long = hold_duration_ms >= self.LONG_PRESS_THRESHOLD_MS

                if state.long_press_triggered:
                    # 长按已被 watcher 触发，忽略 release
                    pass
                else:
                    # 短按：直接触发
                    try:
                        state.callback(False)
                    except Exception as exc:
                        logger.error("热键回调异常 (short_press): %s", exc)

                state.release_time = now
                state.state = PressState.IDLE
                logger.debug(
                    "热键 %s 释放 (hold=%dms, long=%s)",
                    combo, int(hold_duration_ms), is_long,
                )

    # ------------------------------------------------------------------
    # 内部方法
    # ------------------------------------------------------------------

    def _match_combo(
        self, key_str: str, modifiers: Set[str], hotkey: HotkeyDef
    ) -> bool:
        """检查当前按键+修饰键是否匹配热键定义。"""
        # 修饰键全部匹配
        expected_mods = {m for m in hotkey.modifiers}
        actual_mods = {m for m in modifiers}
        if expected_mods and expected_mods != actual_mods:
            return False

        # 主键匹配
        return key_str == hotkey.key

    def _watcher_loop(self) -> None:
        """后台线程：检测长按。"""
        while self._running:
            time.sleep(self.POLL_INTERVAL)
            now = time.monotonic()

            with self._lock:
                for combo, state in self._hotkeys.items():
                    if state.state == PressState.PRESSED and not state.long_press_triggered:
                        hold_ms = (now - state.press_time) * 1000
                        if hold_ms >= self.LONG_PRESS_THRESHOLD_MS:
                            state.long_press_triggered = True
                            state.state = PressState.HOLDING
                            logger.info("热键 %s 触发长按 (hold=%dms)", combo, int(hold_ms))
                            try:
                                state.callback(True)
                            except Exception as exc:
                                logger.error("热键回调异常 (long_press): %s", exc)

    # ------------------------------------------------------------------
    # 便捷方法：直接使用 pynput
    # ------------------------------------------------------------------

    def attach_pynput_listener(self) -> object:
        """创建并启动 pynput GlobalHotKeys 监听器，返回 listener 对象。

        调用方需要自行 join() 或使用非阻塞模式。

        Returns:
            pynput.keyboard.GlobalHotKeys: 监听器实例

        Raises:
            ImportError: pynput 未安装
        """
        try:
            from pynput import keyboard
        except ImportError:
            raise ImportError(
                "pynput 未安装。请运行: pip install pynput\n"
                "或使用 HotkeyManager.on_key_press / on_key_release 手动喂入事件。"
            )

        combo_map: Dict[str, Callable] = {}
        with self._lock:
            for combo, state in self._hotkeys.items():
                combo_map[combo] = self._make_pynput_handler(state)

        self._listener = keyboard.GlobalHotKeys(combo_map)
        self._listener.start()
        logger.info("pynput GlobalHotKeys 已启动，注册 %d 个热键", len(combo_map))
        return self._listener

    def _make_pynput_handler(self, state: HotkeyState):
        """为 pynput 创建按键处理器。"""
        def handler():
            now = time.monotonic()

            # 防抖
            if now - state.last_trigger_time < self.DEBOUNCE_MS / 1000.0:
                logger.debug("热键防抖中")
                return

            state.press_time = now
            state.last_trigger_time = now

            # 等待长按判定窗口
            time.sleep(self.LONG_PRESS_THRESHOLD_MS / 1000.0)
            hold_duration = (time.monotonic() - state.press_time) * 1000
            is_long = hold_duration >= self.LONG_PRESS_THRESHOLD_MS

            try:
                state.callback(is_long)
            except Exception as exc:
                logger.error("热键回调异常: %s", exc)

        return handler

    def __enter__(self) -> "HotkeyManager":
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop()
        return None
