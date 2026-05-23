"""
灵犀输入 — UI Layer

PySide6 桌面界面组件:
- StyleBuilder: 三栏风格构建器
- OverlayHUD: 半透明弹性胶囊 HUD
- StylePicker: 风格选择器悬浮窗
- CompareView: 三列风格对比视图
"""

from lingxi.ui.overlay import OverlayHUD, EMOTION_COLORS, EMOTION_LABELS
from lingxi.ui.style_picker import StylePicker
from lingxi.ui.compare_view import CompareView

__all__ = [
    "OverlayHUD",
    "StylePicker",
    "CompareView",
    "EMOTION_COLORS",
    "EMOTION_LABELS",
]
