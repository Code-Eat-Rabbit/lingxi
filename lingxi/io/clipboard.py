"""Clipboard — pyperclip 跨平台剪贴板封装。

提供 copy / paste / backup / restore 基础能力，
以及上下文管理器用于自动保存/恢复。
"""

from __future__ import annotations

import logging
from contextlib import contextmanager
from typing import Generator, Optional

logger = logging.getLogger(__name__)


class ClipboardError(Exception):
    """剪贴板操作异常。"""
    pass


class Clipboard:
    """跨平台剪贴板封装。

    基于 pyperclip，提供 copy / paste / backup / restore。

    Usage:
        cb = Clipboard()

        # 基础用法
        cb.copy("Hello")
        text = cb.paste()  # "Hello"

        # 上下文管理器：自动保存和恢复
        cb.copy("original")
        with cb.backup():
            cb.copy("temporary text")
            # ... 使用临时文本 ...
        # 自动恢复为 "original"
    """

    def __init__(self) -> None:
        self._backup_text: Optional[str] = None
        self._pyperclip = None
        self._import_attempted = False

    # ------------------------------------------------------------------
    # 懒加载 pyperclip
    # ------------------------------------------------------------------

    def _ensure_pyperclip(self):
        """确保 pyperclip 可用，否则抛出异常。"""
        if self._pyperclip is not None:
            return
        if self._import_attempted:
            raise ClipboardError(
                "pyperclip 不可用，剪贴板操作无法执行。"
            )
        self._import_attempted = True
        try:
            import pyperclip

            self._pyperclip = pyperclip
            logger.debug("pyperclip 已加载")
        except ImportError:
            raise ClipboardError(
                "pyperclip 未安装。请运行: pip install pyperclip"
            )

    # ------------------------------------------------------------------
    # 基础操作
    # ------------------------------------------------------------------

    def copy(self, text: str) -> None:
        """将文本复制到系统剪贴板。

        Args:
            text: 要复制的文本
        """
        self._ensure_pyperclip()
        try:
            self._pyperclip.copy(text)
        except Exception as exc:
            raise ClipboardError(f"复制到剪贴板失败: {exc}") from exc

    def paste(self) -> str:
        """从系统剪贴板获取文本。

        Returns:
            str: 剪贴板文本内容
        """
        self._ensure_pyperclip()
        try:
            result = self._pyperclip.paste()
            return result or ""
        except Exception as exc:
            raise ClipboardError(f"从剪贴板读取失败: {exc}") from exc

    # ------------------------------------------------------------------
    # 备份 / 恢复
    # ------------------------------------------------------------------

    def save_backup(self) -> None:
        """保存当前剪贴板内容到内部备份。"""
        try:
            self._backup_text = self.paste()
        except ClipboardError:
            self._backup_text = ""  # 读取失败时回退为空字符串

    def restore_backup(self) -> None:
        """用内部备份恢复剪贴板内容。"""
        if self._backup_text is None:
            logger.warning("没有备份数据，跳过恢复。")
            return
        try:
            self.copy(self._backup_text)
            self._backup_text = None
        except ClipboardError as exc:
            logger.warning("恢复剪贴板失败: %s", exc)

    @contextmanager
    def backup(self) -> Generator[None, None, None]:
        """上下文管理器：进入时备份剪贴板，退出时自动恢复。

        Usage:
            cb = Clipboard()
            with cb.backup():
                cb.copy("temp")
                # ... 做一些需要临时剪贴板的事 ...
            # 剪贴板已自动恢复
        """
        self.save_backup()
        try:
            yield
        finally:
            self.restore_backup()
