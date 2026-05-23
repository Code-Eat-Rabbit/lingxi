"""测试上下文感知模块 — AppDetector / ContactDetector / AppInfo / ContactInfo。"""

from __future__ import annotations

import pytest

from lingxi.context.app_detector import (
    AppDetector,
    AppInfo,
    _APP_NAME_MAP,
    _resolve_app_name,
)
from lingxi.context.contact_detector import ContactDetector, ContactInfo


# ===================================================================
# AppInfo dataclass
# ===================================================================


class TestAppInfo:
    """AppInfo dataclass 字段与构造。"""

    def test_create_appinfo_all_fields(self) -> None:
        app = AppInfo(name="微信", pid=12345, identifier="WeChat.exe", title="文件传输助手")
        assert app.name == "微信"
        assert app.pid == 12345
        assert app.identifier == "WeChat.exe"
        assert app.title == "文件传输助手"

    def test_create_appinfo_empty_title(self) -> None:
        app = AppInfo(name="Finder", pid=100, identifier="com.apple.finder", title="")
        assert app.title == ""

    def test_create_appinfo_negative_pid(self) -> None:
        """PID 获取失败时应允许 -1。"""
        app = AppInfo(name="未知", pid=-1, identifier="", title="")
        assert app.pid == -1

    def test_appinfo_is_dataclass(self) -> None:
        """验证 AppInfo 确实是 dataclass（支持自动 __init__/__repr__）。"""
        from dataclasses import is_dataclass

        assert is_dataclass(AppInfo)


# ===================================================================
# AppDetector 基本接口
# ===================================================================


class TestAppDetectorBasics:
    """AppDetector 导入与基本功能。"""

    def test_instantiate(self) -> None:
        detector = AppDetector()
        assert detector is not None
        assert hasattr(detector, "_system")

    def test_get_active_app_returns_none_or_appinfo(self) -> None:
        """get_active_app 应返回 None 或 AppInfo。"""
        detector = AppDetector()
        result = detector.get_active_app()
        # 在 CI/无桌面环境中可能返回 None
        assert result is None or isinstance(result, AppInfo)

    def test_is_known_app_positive(self) -> None:
        detector = AppDetector()
        assert detector.is_known_app("WeChat.exe") is True
        assert detector.is_known_app("WeCom.exe") is True
        assert detector.is_known_app("Telegram.exe") is True
        assert detector.is_known_app("QQ.exe") is True

    def test_is_known_app_negative(self) -> None:
        detector = AppDetector()
        assert detector.is_known_app("Firefox") is False
        assert detector.is_known_app("chrome.exe") is False
        assert detector.is_known_app("") is False

    def test_is_known_app_case_insensitive(self) -> None:
        detector = AppDetector()
        # 大小写不敏感
        assert detector.is_known_app("wechat.exe") is True
        assert detector.is_known_app("WECHAT.EXE") is True

    def test_known_identifiers_coverage(self) -> None:
        """确保已知应用标识符集合覆盖了所有关键 IM。"""
        detector = AppDetector()
        required = {
            "wechat.exe", "wecom.exe", "dingtalk.exe",
            "telegram.exe", "qq.exe",
            "outlook.exe", "microsoft outlook",
        }
        missing = required - detector.KNOWN_IDENTIFIERS
        assert not missing, f"缺少已知应用标识符: {missing}"


# ===================================================================
# 应用名映射表
# ===================================================================


class TestAppNameMap:
    """应用名映射表完整性测试。"""

    def test_map_has_required_entries(self) -> None:
        """映射表应包含所有 v1.0 约定的 IM 应用。"""
        required_pairs = {
            "微信": ["wechat.exe", "wechat", "weixin"],
            "企业微信": ["wecom.exe", "wecom", "wework"],
            "钉钉": ["dingtalk.exe", "dingtalk"],
            "邮件": ["outlook.exe", "microsoft outlook"],
            "Telegram": ["telegram.exe", "telegram", "telegram desktop", "telegramdesktop"],
            "QQ": ["qq.exe", "qq"],
            "短信": ["messages", "imessage", "com.apple.imessage"],
        }
        for display_name, keys in required_pairs.items():
            for key in keys:
                assert key in _APP_NAME_MAP, f"缺少键: {key}"
                assert _APP_NAME_MAP[key] == display_name, (
                    f"{key} → {_APP_NAME_MAP[key]}，期望 → {display_name}"
                )

    def test_resolve_known_apps(self) -> None:
        """_resolve_app_name 应对已知键返回正确中文名。"""
        cases = [
            ("WeChat.exe", "微信"),
            ("wechat", "微信"),
            ("WeCom.exe", "企业微信"),
            ("DingTalk.exe", "钉钉"),
            ("Outlook.exe", "邮件"),
            ("Microsoft Outlook", "邮件"),
            ("Telegram.exe", "Telegram"),
            ("telegramdesktop", "Telegram"),
            ("QQ.exe", "QQ"),
            ("com.apple.imessage", "短信"),
            ("Messages", "短信"),
        ]
        for identifier, expected in cases:
            result = _resolve_app_name(identifier)
            assert result == expected, f"{identifier}: {result} != {expected}"

    def test_resolve_unknown_app_returns_original(self) -> None:
        """未知标识符应原样返回。"""
        assert _resolve_app_name("Firefox") == "Firefox"
        assert _resolve_app_name("com.example.unknown") == "com.example.unknown"


# ===================================================================
# ContactInfo dataclass
# ===================================================================


class TestContactInfo:
    """ContactInfo dataclass 字段与构造。"""

    def test_create_contactinfo(self) -> None:
        contact = ContactInfo(name="张三", app_identifier="Telegram", confidence=0.9)
        assert contact.name == "张三"
        assert contact.app_identifier == "Telegram"
        assert contact.confidence == 0.9

    def test_contactinfo_is_dataclass(self) -> None:
        from dataclasses import is_dataclass
        assert is_dataclass(ContactInfo)

    def test_contactinfo_confidence_range(self) -> None:
        """置信度应在 0.0–1.0 范围内。"""
        contact = ContactInfo(name="test", app_identifier="test", confidence=0.5)
        assert 0.0 <= contact.confidence <= 1.0


# ===================================================================
# ContactDetector
# ===================================================================


class TestContactDetector:
    """ContactDetector 联系人提取。"""

    def test_instantiate(self) -> None:
        detector = ContactDetector()
        assert detector is not None
        assert hasattr(detector, "_compiled")

    def test_detect_telegram_contact(self) -> None:
        detector = ContactDetector()
        result = detector.detect_contact("Telegram", "张三 — Telegram")
        assert result is not None
        assert result.name == "张三"
        assert result.app_identifier == "Telegram"
        assert result.confidence == 0.9

    def test_detect_telegram_contact_no_spaces(self) -> None:
        """测试不同空白字符的 Telegram 标题格式。"""
        detector = ContactDetector()
        # 无空格
        result = detector.detect_contact("Telegram", "张三—Telegram")
        assert result is not None
        assert result.name == "张三"

    def test_detect_imessage_contact(self) -> None:
        detector = ContactDetector()
        result = detector.detect_contact("com.apple.iChat", "李四")
        assert result is not None
        assert result.name == "李四"

    def test_detect_qq_contact(self) -> None:
        detector = ContactDetector()
        # QQ NT 标题格式可能包含额外文本
        result = detector.detect_contact("QQ", "王五的聊天窗口")
        assert result is not None
        assert "王五" in result.name

    def test_detect_unsupported_app_returns_none(self) -> None:
        detector = ContactDetector()
        result = detector.detect_contact("WeChat", "张三")
        assert result is None

    def test_detect_empty_title_returns_none(self) -> None:
        detector = ContactDetector()
        result = detector.detect_contact("Telegram", "")
        assert result is None

    def test_detect_empty_identifier_returns_none(self) -> None:
        detector = ContactDetector()
        result = detector.detect_contact("", "张三 — Telegram")
        assert result is None

    def test_is_supported_positive(self) -> None:
        detector = ContactDetector()
        assert detector.is_supported("Telegram") is True
        assert detector.is_supported("telegram") is True
        assert detector.is_supported("com.apple.iChat") is True
        assert detector.is_supported("QQ") is True

    def test_is_supported_negative(self) -> None:
        detector = ContactDetector()
        assert detector.is_supported("WeChat") is False
        assert detector.is_supported("DingTalk") is False

    def test_whitelist_has_required_entries(self) -> None:
        """白名单应包含 Telegram、iMessage、QQ。"""
        whitelist_keys_lower = {k.lower() for k in ContactDetector.WHITELIST}
        assert "telegram" in whitelist_keys_lower
        assert "com.apple.ichat" in whitelist_keys_lower or "com.apple.imessage" in whitelist_keys_lower
        assert "qq" in whitelist_keys_lower
