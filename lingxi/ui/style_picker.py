"""
灵犀输入 — StylePicker 风格选择器悬浮窗

长按热键（或双击 HUD）弹出的半透明悬浮窗，显示 6 套预设风格卡片。
支持键盘 ↑↓ 导航、Enter 确认、Esc 取消。

规格 §3.1 US-2: 风格选择器 Overlay。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QFrame, QSizePolicy,
)
from PySide6.QtCore import Qt, Signal, QEasingCurve, QPropertyAnimation, QRect
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QPainterPath,
    QPaintEvent, QKeyEvent, QResizeEvent, QShowEvent,
)

from lingxi.style.profile import StyleProfile, PresetStyle
from lingxi.style.presets import PRESET_STYLES

# ---------------------------------------------------------------------------
# 预设 → 简短描述（用于卡片副标题）
# ---------------------------------------------------------------------------

_PRESET_DESCRIPTIONS: dict[PresetStyle, str] = {
    PresetStyle.RESPECTFUL: "正式得体，适合工作沟通",
    PresetStyle.WARM:       "亲昵温暖，适合家人密友",
    PresetStyle.WITTY:      "幽默风趣，群聊活跃气氛",
    PresetStyle.PRECISE:    "严谨准确，信息密度高",
    PresetStyle.CASUAL:     "自然随和，日常通用",
    PresetStyle.MINIMAL:    "极简高效，要事优先",
}

# 预设排序（UI 展示顺序）
_PRESET_ORDER: list[PresetStyle] = [
    PresetStyle.CASUAL,
    PresetStyle.RESPECTFUL,
    PresetStyle.WARM,
    PresetStyle.WITTY,
    PresetStyle.PRECISE,
    PresetStyle.MINIMAL,
]


# ---------------------------------------------------------------------------
# StylePicker
# ---------------------------------------------------------------------------

class StylePicker(QWidget):
    """风格选择器半透明悬浮窗。

    纵向排列 6 张风格卡片，当前生效风格高亮。
    键盘 ↑↓ 切换选中，Enter 确认，Esc 取消。

    信号:
        style_selected(str):
            用户选中风格后发射，携带风格 ID（字符串）。
        dismissed:
            窗口关闭（Esc / 失去焦点）时发射。
    """

    # ── 尺寸常量 ──────────────────────────────────────────────────────
    CARD_HEIGHT: int = 62
    CARD_SPACING: int = 6
    PADDING_H: int = 16
    PADDING_V: int = 14
    CORNER_RADIUS: float = 16.0
    BORDER_WIDTH: float = 1.5
    MIN_WIDTH: int = 300

    # ── 动画 ──────────────────────────────────────────────────────────
    FADE_DURATION: int = 200

    # ── 信号 ──────────────────────────────────────────────────────────
    style_selected = Signal(str)
    dismissed = Signal()

    def __init__(
        self,
        profiles: Optional[list[StyleProfile]] = None,
        current_style_id: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        """初始化风格选择器。

        Args:
            profiles: 可选的自定义风格列表。若为 None 则使用 6 套系统预设。
            current_style_id: 当前生效的风格 ID，用于高亮标记。
            parent: 可选的父 widget。
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

        # ── 数据 ──────────────────────────────────────────────────────
        self._profiles: list[StyleProfile] = profiles or list(PRESET_STYLES.values())
        # 按展示顺序重排
        if profiles is None:
            order_map = {p.base_preset: p for p in self._profiles if p.base_preset}
            self._profiles = [
                order_map[ps] for ps in _PRESET_ORDER if ps in order_map
            ]
        self._selected_index: int = 0

        # ── 卡片行引用 ────────────────────────────────────────────────
        self._card_rows: list[_CardRow] = []

        # ── 动画 ──────────────────────────────────────────────────────
        self._fade_anim: Optional[QPropertyAnimation] = None

        self._init_ui()
        self._highlight_current(current_style_id)
        self._update_selected(0)
        self._size_to_fit()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """构建纵向卡片布局。"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            self.PADDING_H, self.PADDING_V,
            self.PADDING_H, self.PADDING_V,
        )
        main_layout.setSpacing(self.CARD_SPACING)

        # 标题
        title = QLabel("选择风格")
        title.setFont(QFont("", 13, QFont.Weight.Bold))
        title.setStyleSheet("color: white; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # 分隔线
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,0.15);")
        sep.setFixedHeight(1)
        main_layout.addWidget(sep)

        # 卡片列表
        for i, profile in enumerate(self._profiles):
            is_last = (i == len(self._profiles) - 1)
            row = _CardRow(profile, parent=self)
            row.setFixedHeight(self.CARD_HEIGHT)
            row.clicked.connect(lambda idx=i: self._select(idx))
            self._card_rows.append(row)
            main_layout.addWidget(row)

            if not is_last:
                card_sep = QFrame()
                card_sep.setFrameShape(QFrame.Shape.HLine)
                card_sep.setStyleSheet("color: rgba(255,255,255,0.06);")
                card_sep.setFixedHeight(1)
                main_layout.addWidget(card_sep)

        # 底部提示
        hint = QLabel("↑↓ 选择   Enter 确认   Esc 取消")
        hint.setFont(QFont("", 10))
        hint.setStyleSheet("color: rgba(255,255,255,0.35); background: transparent;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(hint)

    def _size_to_fit(self) -> None:
        """根据内容计算并设置窗口尺寸。"""
        card_count = len(self._profiles)
        separators = card_count - 1
        title_height = 36
        hint_height = 26
        total_height = (
            self.PADDING_V * 2
            + title_height
            + 1  # 标题分隔线
            + card_count * self.CARD_HEIGHT
            + separators * 1  # 卡片间分隔线
            + hint_height
            + self.CARD_SPACING * 2
        )
        self.setFixedSize(self.MIN_WIDTH, total_height)

    # ------------------------------------------------------------------
    # 高亮与选择
    # ------------------------------------------------------------------

    def _highlight_current(self, current_style_id: str) -> None:
        """标记当前生效的风格卡片。"""
        for i, profile in enumerate(self._profiles):
            if profile.id == current_style_id:
                self._card_rows[i].set_current(True)
                self._selected_index = i
                break

    def _update_selected(self, index: int) -> None:
        """更新键盘选中高亮（与「当前生效」高亮独立）。"""
        for i, row in enumerate(self._card_rows):
            row.set_hovered(i == index)

    def _select(self, index: int) -> None:
        """选中指定索引的风格并发射信号、关闭窗口。"""
        if 0 <= index < len(self._profiles):
            profile = self._profiles[index]
            self.style_selected.emit(profile.id)
        self._dismiss()

    # ------------------------------------------------------------------
    # 动画
    # ------------------------------------------------------------------

    def show_with_fade(self) -> None:
        """淡入显示。"""
        self.setWindowOpacity(0.0)
        self._center_on_screen()
        self.show()

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(self.FADE_DURATION)
        self._fade_anim.setStartValue(0.0)
        self._fade_anim.setEndValue(1.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._fade_anim.start()

    def _dismiss(self) -> None:
        """淡出关闭。"""
        if not self.isVisible():
            return

        self._fade_anim = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade_anim.setDuration(self.FADE_DURATION // 2)
        self._fade_anim.setStartValue(self.windowOpacity())
        self._fade_anim.setEndValue(0.0)
        self._fade_anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._fade_anim.finished.connect(self._on_dismiss_finished)
        self._fade_anim.start()

    def _on_dismiss_finished(self) -> None:
        """退场动画完成回调。"""
        self.hide()
        self.dismissed.emit()

    def _center_on_screen(self) -> None:
        """定位到屏幕中央。"""
        screen = self.screen()
        if screen is None:
            return
        screen_geo = screen.availableGeometry()
        x = screen_geo.center().x() - self.width() // 2
        y = screen_geo.center().y() - self.height() // 2
        self.move(max(0, x), max(0, y))

    # ------------------------------------------------------------------
    # 键盘导航
    # ------------------------------------------------------------------

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """↑↓ 选择 / Enter 确认 / Esc 取消。"""
        key = event.key()

        if key == Qt.Key.Key_Up or key == Qt.Key.Key_K:
            new_idx = (self._selected_index - 1) % len(self._profiles)
            self._selected_index = new_idx
            self._update_selected(new_idx)
            event.accept()

        elif key == Qt.Key.Key_Down or key == Qt.Key.Key_J:
            new_idx = (self._selected_index + 1) % len(self._profiles)
            self._selected_index = new_idx
            self._update_selected(new_idx)
            event.accept()

        elif key == Qt.Key.Key_Return or key == Qt.Key.Key_Enter:
            self._select(self._selected_index)
            event.accept()

        elif key == Qt.Key.Key_Escape:
            self._dismiss()
            event.accept()

        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # 自定义绘制 (半透明深色背景 + 圆角)
    # ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        """绘制半透明深色圆角背景。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        bw = int(self.BORDER_WIDTH)
        draw_rect = rect.adjusted(bw, bw, -bw, -bw)

        # 背景
        bg_path = QPainterPath()
        bg_path.addRoundedRect(draw_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        bg_color = QColor(28, 28, 30, 210)
        painter.fillPath(bg_path, QBrush(bg_color))

        # 细边框
        border_path = QPainterPath()
        border_path.addRoundedRect(draw_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        pen = QPen(QColor(255, 255, 255, 30))
        pen.setWidthF(self.BORDER_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(border_path)

        painter.end()


# ---------------------------------------------------------------------------
# _CardRow: 单张风格卡片行
# ---------------------------------------------------------------------------

class _CardRow(QFrame):
    """风格选择器中的单张卡片行。

    点击发射 clicked 信号。
    支持三种视觉状态: 普通 / hover (键盘选中) / current (当前生效)。
    """

    clicked = Signal()

    # 颜色常量
    _BG_NORMAL = QColor(255, 255, 255, 6)
    _BG_HOVER = QColor(255, 255, 255, 18)
    _BG_CURRENT = QColor(100, 180, 255, 25)
    _BORDER_CURRENT = QColor(100, 180, 255, 140)
    _CORNER_RADIUS: float = 10.0

    def __init__(
        self,
        profile: StyleProfile,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._profile = profile
        self._is_hovered: bool = False
        self._is_current: bool = False

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_ui()

    def _init_ui(self) -> None:
        """初始化卡片内部布局：图标 | 名称 + 描述。"""
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(12)

        # 图标
        icon_label = QLabel(self._profile.icon or "📝")
        icon_label.setFont(QFont("", 22))
        icon_label.setFixedWidth(34)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background: transparent;")
        layout.addWidget(icon_label)

        # 名称 + 描述
        text_col = QVBoxLayout()
        text_col.setSpacing(2)

        name_label = QLabel(self._profile.name)
        name_label.setFont(QFont("", 13, QFont.Weight.Medium))
        name_label.setStyleSheet("color: white; background: transparent;")
        text_col.addWidget(name_label)

        desc_text = _PRESET_DESCRIPTIONS.get(
            self._profile.base_preset, "自定义风格"
        )
        desc_label = QLabel(desc_text)
        desc_label.setFont(QFont("", 10))
        desc_label.setStyleSheet("color: rgba(255,255,255,0.5); background: transparent;")
        text_col.addWidget(desc_label)

        layout.addLayout(text_col, 1)

        # 当前生效标记
        self._check_label = QLabel("✓")
        self._check_label.setFont(QFont("", 14, QFont.Weight.Bold))
        self._check_label.setFixedWidth(24)
        self._check_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._check_label.setStyleSheet(
            "color: rgba(100, 180, 255, 200); background: transparent;"
        )
        self._check_label.setVisible(False)
        layout.addWidget(self._check_label)

    # ------------------------------------------------------------------
    # 状态设置
    # ------------------------------------------------------------------

    def set_hovered(self, hovered: bool) -> None:
        """设置键盘导航选中状态。"""
        if self._is_hovered != hovered:
            self._is_hovered = hovered
            self.update()

    def set_current(self, current: bool) -> None:
        """设置「当前生效风格」标记。"""
        if self._is_current != current:
            self._is_current = current
            self._check_label.setVisible(current)
            self.update()

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        """点击发射信号。"""
        self.clicked.emit()
        event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:
        """绘制卡片背景。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, self._CORNER_RADIUS, self._CORNER_RADIUS)

        # 选择背景色
        if self._is_current:
            bg = self._BG_CURRENT
            border = self._BORDER_CURRENT
        elif self._is_hovered:
            bg = self._BG_HOVER
            border = QColor(255, 255, 255, 40)
        else:
            bg = self._BG_NORMAL
            border = QColor(0, 0, 0, 0)  # 无边框

        painter.fillPath(path, QBrush(bg))

        if border.alpha() > 0:
            pen = QPen(border)
            pen.setWidthF(1.0)
            painter.setPen(pen)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPath(path)

        painter.end()
