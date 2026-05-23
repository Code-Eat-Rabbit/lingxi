# Context Awareness Layer
# 当前应用检测、窗口标题读取、联系人感知
#
# Usage:
#     from lingxi.context import AppDetector, ContactDetector, AppInfo, ContactInfo
#     detector = AppDetector()
#     app = detector.get_active_app()

from lingxi.context.app_detector import AppDetector, AppInfo
from lingxi.context.contact_detector import ContactDetector, ContactInfo

__all__ = [
    "AppDetector",
    "AppInfo",
    "ContactDetector",
    "ContactInfo",
]
