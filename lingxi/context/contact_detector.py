"""联系人感知 — 从窗口标题提取联系人信息。

v1.0 仅支持白名单应用 + 窗口标题正则匹配：
- Telegram Desktop  — 标题格式 "联系人名 — Telegram"
- iMessage           — 标题格式 "联系人名"
- QQ NT              — 标题中包含联系人名

国产 IM（微信/企业微信/钉钉）v1.0 暂不支持，推迟到 v1.1。
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from typing import ClassVar, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# ContactInfo
# ---------------------------------------------------------------------------


@dataclass
class ContactInfo:
    """从窗口标题提取的联系人信息。

    Attributes:
        name:           联系人显示名
        app_identifier: 来源应用标识符
        confidence:     置信度 (0.0–1.0)，v1.0 白名单匹配固定为 0.9
    """

    name: str
    app_identifier: str
    confidence: float


# ---------------------------------------------------------------------------
# ContactDetector
# ---------------------------------------------------------------------------


class ContactDetector:
    """从窗口标题提取联系人信息。

    v1.0 策略：
        仅白名单应用支持联系人提取，通过正则匹配窗口标题。
        白名单外的应用一律返回 None。

    Usage:
        detector = ContactDetector()
        contact = detector.detect_contact("Telegram", "张三 — Telegram")
        if contact:
            print(f"正在与 {contact.name} 聊天")
    """

    # v1.0 白名单：应用标识符 → 标题正则
    # 正则必须包含一个捕获组，提取联系人名
    WHITELIST: ClassVar[dict[str, str]] = {
        # Telegram Desktop: "联系人名 — Telegram"
        "Telegram": r"^(.+?)\s*—\s*Telegram$",
        "telegram": r"^(.+?)\s*—\s*Telegram$",
        "TelegramDesktop": r"^(.+?)\s*—\s*Telegram$",
        "telegramdesktop": r"^(.+?)\s*—\s*Telegram$",
        "telegram.exe": r"^(.+?)\s*—\s*Telegram$",
        # iMessage: "联系人名"
        "com.apple.iChat": r"^(.+?)$",
        "com.apple.imessage": r"^(.+?)$",
        "Messages": r"^(.+?)$",
        "messages": r"^(.+?)$",
        # QQ NT: 标题即联系人名（贪婪匹配整行）
        "QQ": r"(.+)",
        "qq": r"(.+)",
        "QQ.exe": r"(.+)",
        "qq.exe": r"(.+)",
    }

    def __init__(self) -> None:
        # 预编译正则，提升性能
        self._compiled: dict[str, re.Pattern[str]] = {
            key: re.compile(pattern) for key, pattern in self.WHITELIST.items()
        }

    # ------------------------------------------------------------------
    # 公共 API
    # ------------------------------------------------------------------

    def detect_contact(
        self, app_identifier: str, window_title: str
    ) -> Optional[ContactInfo]:
        """从窗口标题检测联系人。

        Args:
            app_identifier: 应用标识符（如 "Telegram"）
            window_title:   窗口标题（如 "张三 — Telegram"）

        Returns:
            ContactInfo，无法提取时返回 None
        """
        if not app_identifier or not window_title:
            return None

        # 查找白名单中的正则
        pattern = self._compiled.get(app_identifier)
        if pattern is None:
            # 尝试小写匹配
            pattern = self._compiled.get(app_identifier.lower())

        if pattern is None:
            logger.debug("应用 %s 不在联系人感知白名单中", app_identifier)
            return None

        # 正则匹配窗口标题
        match = pattern.search(window_title)
        if not match:
            logger.debug(
                "窗口标题 '%s' 不匹配白名单模式 %s", window_title, pattern.pattern
            )
            return None

        contact_name = match.group(1).strip()
        if not contact_name:
            return None

        return ContactInfo(
            name=contact_name,
            app_identifier=app_identifier,
            confidence=0.9,  # v1.0 白名单固定置信度
        )

    def is_supported(self, app_identifier: str) -> bool:
        """检查应用是否在联系人感知白名单中。

        Args:
            app_identifier: 应用标识符

        Returns:
            是否支持联系人提取
        """
        return (
            app_identifier in self._compiled
            or app_identifier.lower() in self._compiled
        )
