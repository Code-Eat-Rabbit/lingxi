"""
灵犀输入 — Overlay HUD 弹性胶囊

半透明毛玻璃 HUD，显示在屏幕中下方，支持弹性入场/退场动画、
情绪颜色边框和文本驱动的弹性变宽。

规格 §3.1 US-0: 弹性胶囊规格。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import QWidget, QLabel, QHBoxLayout, QGraphicsBlurEffect
from PySide6.QtCore import (
    Qt, QPropertyAnimation, QEasingCurve, QRect, Signal,
    QParallelAnimationGroup, QPoint, QSize,
)
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QPainterPath, QFontMetrics,
    QPaintEvent, QMouseEvent, QKeyEvent, QResizeEvent,
)

# 尝试导入 Emotion 枚举
try:
    from lingxi.engine.emotion import Emotion as EmotionEnum
except ImportError:
    from enum import Enum as _Enum

    class EmotionEnum(str, _Enum):
        NEUTRAL = "neutral"
        ANGER = "anger"
        HAPPY = "happy"
        SAD = "sad"
        SURPRISE = "surprise"
        FEAR = "fear"
        DISGUST = "disgust"


# ---------------------------------------------------------------------------
# 情绪 → 颜色映射表
# ---------------------------------------------------------------------------

EMOTION_COLORS: dict[str, QColor] = {
    "neutral":  QColor(128, 128, 128),       # 灰色
    "anger":    QColor(220, 50, 50),         # 红色
    "happy":    QColor(50, 180, 50),         # 绿色
    "sad":      QColor(50, 100, 220),        # 蓝色
    "surprise": QColor(255, 140, 0),         # 橙色
    "fear":     QColor(150, 50, 200),        # 紫色
    "disgust":  QColor(139, 90, 43),         # 棕色
}

EMOTION_LABELS: dict[str, str] = {
    "neutral":  "平静",
    "anger":    "愤怒",
    "happy":    "开心",
    "sad":      "悲伤",
    "surprise": "惊讶",
    "fear":     "恐惧",
    "disgust":  "厌恶",
}


# ---------------------------------------------------------------------------
# OverlayHUD
# ---------------------------------------------------------------------------

class OverlayHUD(QWidget):
    """屏幕中下方的弹性胶囊 HUD。

    半透明毛玻璃背景 + 情绪颜色边框 + 弹性动画。
    显示风格信息、转录/结果文本和情绪指示器。

    信号:
        dismissed:
            HUD 退场动画完成后发射。
        style_pick_requested:
            用户双击 HUD 请求切换风格时发射。
    """

    # ── 状态枚举 ──────────────────────────────────────────────────────
    class State:
        IDLE = "idle"
        RECORDING = "recording"
        PROCESSING = "processing"
        RESULT = "result"
        WARNING = "warning"
        ERROR = "error"

    # ── 尺寸常量 ──────────────────────────────────────────────────────
    MIN_WIDTH: int = 280
    MAX_WIDTH: int = 680
    HEIGHT: int = 60
    CORNER_RADIUS: float = 24.0
    BORDER_WIDTH: float = 2.0

    # ── 动画时长 (ms) ─────────────────────────────────────────────────
    SHOW_DURATION: int = 350
    HIDE_DURATION: int = 220
    RESIZE_DURATION: int = 200

    # ── 信号 ──────────────────────────────────────────────────────────
    dismissed = Signal()
    style_pick_requested = Signal()

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        """初始化 OverlayHUD。

        Args:
            parent: 可选的父 widget（通常为 None，作为独立顶层窗口）。
        """
        super().__init__(parent)

        # ── 窗口标志 ──────────────────────────────────────────────────
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
            | Qt.WindowType.NoDropShadowWindowHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WidgetAttribute.WA_MacAlwaysShowToolWindow)

        # ── 内部状态 ──────────────────────────────────────────────────
        self._state: str = self.State.IDLE
        self._emotion: str = "neutral"
        self._emotion_color: QColor = EMOTION_COLORS["neutral"]
        self._current_style_name: str = ""
        self._current_style_icon: str = ""

        # ── 动画引用 ──────────────────────────────────────────────────
        self._show_group: Optional[QParallelAnimationGroup] = None
        self._hide_group: Optional[QParallelAnimationGroup] = None
        self._resize_anim: Optional[QPropertyAnimation] = None

        # ── 模糊容器 ──────────────────────────────────────────────────
        self._blur_widget: Optional[QWidget] = None

        # 初始尺寸
        self.resize(self.MIN_WIDTH, self.HEIGHT)

        self._init_ui()
        self._init_blur()
        self._center_on_screen()

    # ------------------------------------------------------------------
    # UI 初始化
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """初始化 UI 子控件和布局。"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 10, 18, 10)
        layout.setSpacing(8)

        # 风格图标
        self.style_icon = QLabel("🍃")
        self.style_icon.setFont(QFont("", 18))
        self.style_icon.setMinimumWidth(28)
        self.style_icon.setAlignment(Qt.AlignmentFlag.AlignCenter)

        # 风格名称
        self.style_name = QLabel("日常")
        self.style_name.setFont(QFont("", 12, QFont.Weight.Bold))
        self.style_name.setStyleSheet("color: white; background: transparent;")
        self.style_name.setMinimumWidth(32)

        # 转录 / 结果文本
        self.text_label = QLabel("灵犀输入就绪")
        self.text_label.setFont(QFont("", 12))
        self.text_label.setStyleSheet(
            "color: rgba(255, 255, 255, 0.92); background: transparent;"
        )
        self.text_label.setWordWrap(False)
        self.text_label.setMinimumWidth(40)

        # 情绪指示器圆点
        self.emotion_dot = QLabel("●")
        self.emotion_dot.setFont(QFont("", 9))
        self.emotion_dot.setFixedWidth(16)
        self.emotion_dot.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_emotion_dot_style()

        # 添加到布局
        layout.addWidget(self.style_icon)
        layout.addWidget(self.style_name)
        layout.addWidget(self.text_label, 1)
        layout.addWidget(self.emotion_dot)

    def _init_blur(self) -> None:
        """初始化背景模糊效果层。

        Win/Linux: 使用 QGraphicsBlurEffect 对底层 widget 做视觉近似。
        macOS: QGraphicsBlurEffect 同样可用（Qt6 跨平台一致）。
        真正的 NSVisualEffectView 需 PyObjC，留待后续平台专项优化。
        """
        self._blur_widget = QWidget(self)
        self._blur_widget.setGeometry(self.rect())
        self._blur_widget.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._blur_widget.setStyleSheet(
            "background: rgba(0, 0, 0, 60); border-radius: 24px;"
        )

        blur_effect = QGraphicsBlurEffect()
        blur_effect.setBlurRadius(8)
        blur_effect.setBlurHints(QGraphicsBlurEffect.BlurHint.PerformanceHint)
        self._blur_widget.setGraphicsEffect(blur_effect)
        self._blur_widget.lower()

    # ------------------------------------------------------------------
    # 入场 / 退场动画
    # ------------------------------------------------------------------

    def show_with_animation(self) -> None:
        """入场弹簧动画 (0.35s, ease-out-back)。

        效果: 窗口从 0.8 倍尺寸弹性放大至 1.0 倍，opacity 从 0 到 1。
        中心点保持不变。
        """
        if self.isVisible():
            return

        # 停止已有动画
        self._stop_animations()

        # 确保定位正确
        self._center_on_screen()
        target_geo = QRect(self.geometry())
        target_size = target_geo.size()

        # 起始尺寸: 0.8 倍，同中心
        start_w = max(60, int(target_size.width() * 0.8))
        start_h = max(40, int(target_size.height() * 0.8))
        start_x = target_geo.x() + (target_size.width() - start_w) // 2
        start_y = target_geo.y() + (target_size.height() - start_h) // 2
        start_geo = QRect(start_x, start_y, start_w, start_h)

        # 设置起始状态并显示
        self.setGeometry(start_geo)
        self.setWindowOpacity(0.0)
        self.show()

        # 并行动画组: geometry + opacity
        self._show_group = QParallelAnimationGroup(self)

        geo_anim = QPropertyAnimation(self, b"geometry", self)
        geo_anim.setDuration(self.SHOW_DURATION)
        geo_anim.setStartValue(start_geo)
        geo_anim.setEndValue(target_geo)
        geo_anim.setEasingCurve(QEasingCurve.Type.OutBack)

        opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        opacity_anim.setDuration(self.SHOW_DURATION)
        opacity_anim.setStartValue(0.0)
        opacity_anim.setEndValue(1.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        self._show_group.addAnimation(geo_anim)
        self._show_group.addAnimation(opacity_anim)
        self._show_group.start()

    def hide_with_animation(self) -> None:
        """退场缩放动画 (0.22s, ease-in)。

        效果: 窗口从 1.0 倍缩小至 0.85 倍，opacity 从 1 到 0。
        动画完成后隐藏窗口并发射 dismissed 信号。
        """
        if not self.isVisible():
            return

        self._stop_animations()

        current_geo = QRect(self.geometry())
        current_size = current_geo.size()

        # 目标尺寸: 0.85 倍，同中心
        end_w = max(40, int(current_size.width() * 0.85))
        end_h = max(30, int(current_size.height() * 0.85))
        end_x = current_geo.x() + (current_size.width() - end_w) // 2
        end_y = current_geo.y() + (current_size.height() - end_h) // 2
        end_geo = QRect(end_x, end_y, end_w, end_h)

        self._hide_group = QParallelAnimationGroup(self)

        geo_anim = QPropertyAnimation(self, b"geometry", self)
        geo_anim.setDuration(self.HIDE_DURATION)
        geo_anim.setStartValue(current_geo)
        geo_anim.setEndValue(end_geo)
        geo_anim.setEasingCurve(QEasingCurve.Type.InQuad)

        opacity_anim = QPropertyAnimation(self, b"windowOpacity", self)
        opacity_anim.setDuration(self.HIDE_DURATION)
        opacity_anim.setStartValue(self.windowOpacity())
        opacity_anim.setEndValue(0.0)
        opacity_anim.setEasingCurve(QEasingCurve.Type.InQuad)

        self._hide_group.addAnimation(geo_anim)
        self._hide_group.addAnimation(opacity_anim)
        self._hide_group.finished.connect(self._on_hide_finished)
        self._hide_group.start()

    def _on_hide_finished(self) -> None:
        """退场动画完成回调：隐藏窗口并发射信号。"""
        self.hide()
        self.dismissed.emit()

    def _stop_animations(self) -> None:
        """停止所有进行中的动画。"""
        for anim in (self._show_group, self._hide_group, self._resize_anim):
            if anim is not None:
                anim.stop()

    # ------------------------------------------------------------------
    # 状态更新
    # ------------------------------------------------------------------

    def update_state(
        self,
        state: str,
        text: str = "",
        style_name: str = "",
        style_icon: str = "",
        emotion: str = "neutral",
    ) -> None:
        """更新 HUD 状态和显示内容。

        Args:
            state: 新状态 (idle / recording / processing / result / warning / error)。
            text: 转录文本或处理结果文本。
            style_name: 当前生效的风格名称。
            style_icon: 当前生效的风格图标 emoji。
            emotion: 情绪标签字符串 ("neutral", "anger", "happy" 等)。
        """
        self._state = state

        # ── 风格信息 ──
        if style_name:
            self.style_name.setText(style_name)
            self._current_style_name = style_name
        if style_icon:
            self.style_icon.setText(style_icon)
            self._current_style_icon = style_icon

        # ── 文本（含状态前缀） ──
        self._set_state_text(state, text)

        # ── 情绪（变化时更新颜色并触发重绘） ──
        if emotion != self._emotion:
            self._emotion = emotion
            self._emotion_color = EMOTION_COLORS.get(
                emotion, EMOTION_COLORS["neutral"]
            )
            self._update_emotion_dot_style()
            self.update()

        # ── 弹性变宽 ──
        self._update_size_to_fit()

    def _set_state_text(self, state: str, text: str) -> None:
        """根据状态设置显示文本（若无自定义文本则用默认占位）。"""
        defaults: dict[str, str] = {
            self.State.IDLE:       "灵犀输入就绪",
            self.State.RECORDING:  "🎤 正在聆听...",
            self.State.PROCESSING: "⏳ 处理中...",
            self.State.RESULT:     "",
            self.State.WARNING:    "⚠️ 降级模式",
            self.State.ERROR:      "❌ 出错了",
        }
        self.text_label.setText(text or defaults.get(state, text))

    def _update_emotion_dot_style(self) -> None:
        """根据当前情绪更新圆点颜色样式表。"""
        color_name = self._emotion_color.name()
        self.emotion_dot.setStyleSheet(
            f"color: {color_name}; background: transparent; font-size: 10px;"
        )

    # ------------------------------------------------------------------
    # 弹性变宽
    # ------------------------------------------------------------------

    def _update_size_to_fit(self) -> None:
        """根据 text_label 内容弹性变宽（最小 280px，最大 680px）。

        使用 QPropertyAnimation 平滑过渡到目标宽度，保持垂直中心不变。
        变化幅度小于 10px 时跳过，避免微小抖动。
        """
        fm = QFontMetrics(self.text_label.font())
        text_width = fm.horizontalAdvance(self.text_label.text())

        # 固定元素宽度估算: 图标(28) + 风格名(~50) + 圆点(16) + margins(36) + 间距(24)
        fixed_width = 154
        needed_width = max(self.MIN_WIDTH, fixed_width + text_width)
        needed_width = min(needed_width, self.MAX_WIDTH)

        current_width = self.width()
        if abs(current_width - needed_width) < 10:
            return  # 变化太小，跳过

        # 停止之前的 resize 动画
        if self._resize_anim is not None:
            self._resize_anim.stop()
            self._resize_anim = None

        current_geo = QRect(self.geometry())
        dx = (current_width - needed_width) // 2
        target_geo = QRect(
            current_geo.x() + dx,
            current_geo.y(),
            needed_width,
            self.HEIGHT,
        )

        self._resize_anim = QPropertyAnimation(self, b"geometry", self)
        self._resize_anim.setDuration(self.RESIZE_DURATION)
        self._resize_anim.setStartValue(current_geo)
        self._resize_anim.setEndValue(target_geo)
        self._resize_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._resize_anim.start()

    # ------------------------------------------------------------------
    # 定位
    # ------------------------------------------------------------------

    def _center_on_screen(self) -> None:
        """定位到屏幕中下方（垂直约 68% 处，即中偏下区域）。"""
        screen = self.screen()
        if screen is None:
            return

        screen_geo = screen.availableGeometry()
        x = screen_geo.center().x() - self.width() // 2
        y = screen_geo.top() + int(screen_geo.height() * 0.68)
        self.move(max(0, x), max(0, y))

    # ------------------------------------------------------------------
    # 自定义绘制
    # ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        """自定义绘制：半透明深色背景 + 圆角胶囊 + 情绪颜色边框 + 顶部微高光。

        背景色: rgba(28, 28, 30, 185)，近似 macOS 毛玻璃的深色模式质感。
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        bw = int(self.BORDER_WIDTH)
        draw_rect = rect.adjusted(bw, bw, -bw, -bw)

        # ── 背景填充 ──
        bg_path = QPainterPath()
        bg_path.addRoundedRect(draw_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        bg_color = QColor(28, 28, 30, 185)
        painter.fillPath(bg_path, QBrush(bg_color))

        # ── 顶部高光线（模拟玻璃反光） ──
        highlight_path = QPainterPath()
        hl_rect = draw_rect.adjusted(3, 3, -3, -draw_rect.height() // 2 + 2)
        highlight_path.addRoundedRect(
            hl_rect, self.CORNER_RADIUS - 3, self.CORNER_RADIUS - 3,
        )
        hl_color = QColor(255, 255, 255, 12)
        painter.fillPath(highlight_path, QBrush(hl_color))

        # ── 情绪颜色边框 ──
        border_path = QPainterPath()
        border_path.addRoundedRect(draw_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)

        pen = QPen(self._emotion_color)
        pen.setWidthF(self.BORDER_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(border_path)

        painter.end()

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------

    def resizeEvent(self, event: QResizeEvent) -> None:
        """窗口大小变化时同步更新模糊底层。"""
        super().resizeEvent(event)
        if self._blur_widget is not None:
            self._blur_widget.setGeometry(self.rect())

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        """双击 HUD 触发风格选择器请求。"""
        self.style_pick_requested.emit()
        event.accept()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Esc 键退场。"""
        if event.key() == Qt.Key.Key_Escape:
            self.hide_with_animation()
            event.accept()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # 便捷工厂方法
    # ------------------------------------------------------------------

    @classmethod
    def create_and_show(
        cls,
        state: str = State.IDLE,
        text: str = "",
        style_name: str = "日常",
        style_icon: str = "🍃",
        emotion: str = "neutral",
        parent: Optional[QWidget] = None,
    ) -> "OverlayHUD":
        """创建 HUD 实例、设置初始状态并以动画入场。

        Args:
            state: 初始状态。
            text: 初始文本。
            style_name: 风格名称。
            style_icon: 风格图标。
            emotion: 情绪标签。
            parent: 可选的父 widget。

        Returns:
            已显示并带动画入场的 OverlayHUD 实例。
        """
        hud = cls(parent=parent)
        hud.update_state(
            state=state,
            text=text,
            style_name=style_name,
            style_icon=style_icon,
            emotion=emotion,
        )
        hud.show_with_animation()
        return hud
