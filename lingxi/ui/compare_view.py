"""
灵犀输入 — CompareView 风格对比视图

三列并排预览不同风格对同一输入文本的转换效果。
用户可按 1/2/3 快速选择对应列的风格。

规格 §3.1 US-4: 风格对比视图。
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QLabel, QVBoxLayout, QHBoxLayout, QPushButton, QFrame,
    QSizePolicy, QTextEdit,
)
from PySide6.QtCore import Qt, Signal, QEasingCurve, QPropertyAnimation, QRect
from PySide6.QtGui import (
    QPainter, QColor, QBrush, QPen, QFont, QPainterPath,
    QPaintEvent, QKeyEvent, QResizeEvent, QShowEvent,
)

from lingxi.style.profile import StyleProfile, PresetStyle
from lingxi.style.presets import PRESET_STYLES


# ---------------------------------------------------------------------------
# 预设 → 模拟预览文本（实际 LLM 调用在下一阶段集成）
# ---------------------------------------------------------------------------

_SAMPLE_INPUT = "我今天加班，晚点回去"

_MOCK_PREVIEWS: dict[PresetStyle, str] = {
    PresetStyle.RESPECTFUL: (
        "尊敬的领导，本人今日需加班处理工作，"
        "预计稍晚返程，敬请谅解。\n此致\n敬礼"
    ),
    PresetStyle.WARM: (
        "亲爱的～我今天要加班呢，"
        "晚点回来陪你哦 ❤️ 辛苦啦！~"
    ),
    PresetStyle.WITTY: (
        "兄弟，今天加班搞事情 😎 "
        "晚点回来哈，别太想我～"
    ),
    PresetStyle.PRECISE: (
        "今日加班，预计返程时间延后。"
        "请知悉。"
    ),
    PresetStyle.CASUAL: (
        "我今天加班，晚点回去哈～ 谢谢！"
    ),
    PresetStyle.MINIMAL: (
        "加班 晚回"
    ),
}

# 预设排序（展示顺序）
_COMPARE_ORDER: list[PresetStyle] = [
    PresetStyle.CASUAL,
    PresetStyle.RESPECTFUL,
    PresetStyle.WARM,
    PresetStyle.WITTY,
    PresetStyle.PRECISE,
    PresetStyle.MINIMAL,
]


# ---------------------------------------------------------------------------
# CompareView
# ---------------------------------------------------------------------------

class CompareView(QWidget):
    """三列并排风格对比视图。

    布局:
        顶部: 源文本展示
        中部: 3 列并排，每列一个风格卡片 (名称 + 图标 + 模拟转换结果)
        底部: 提示栏 (1/2/3 选择, Esc 取消)

    信号:
        style_selected(str):
            用户选中某列风格后发射，携带风格 ID。
        dismissed:
            窗口关闭时发射。
    """

    # ── 尺寸常量 ──────────────────────────────────────────────────────
    COLUMN_WIDTH: int = 260
    COLUMN_MIN_HEIGHT: int = 200
    PADDING: int = 16
    CORNER_RADIUS: float = 16.0
    BORDER_WIDTH: float = 1.5

    # ── 动画 ──────────────────────────────────────────────────────────
    FADE_DURATION: int = 180

    # ── 信号 ──────────────────────────────────────────────────────────
    style_selected = Signal(str)
    dismissed = Signal()

    def __init__(
        self,
        source_text: str = "",
        profiles: Optional[list[StyleProfile]] = None,
        parent: Optional[QWidget] = None,
    ) -> None:
        """初始化风格对比视图。

        Args:
            source_text: 待转换的源文本。若为空则使用默认示例。
            profiles: 要对比的风格列表，最多取前 3 个。
                      若为 None 则取预设顺序的前 3 个。
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
        self._source_text: str = source_text or _SAMPLE_INPUT

        if profiles:
            self._profiles = profiles[:3]
        else:
            order_map = {
                p.base_preset: p
                for p in PRESET_STYLES.values()
                if p.base_preset
            }
            self._profiles = [
                order_map[ps]
                for ps in _COMPARE_ORDER[:3]
                if ps in order_map
            ]

        # ── 列引用 ────────────────────────────────────────────────────
        self._columns: list[_CompareColumn] = []

        # ── 动画 ──────────────────────────────────────────────────────
        self._fade_anim: Optional[QPropertyAnimation] = None

        self._init_ui()
        self._size_to_fit()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """构建三列并排布局。"""
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(
            self.PADDING, self.PADDING,
            self.PADDING, self.PADDING,
        )
        main_layout.setSpacing(10)

        # ── 标题栏 ──
        title = QLabel("风格对比")
        title.setFont(QFont("", 14, QFont.Weight.Bold))
        title.setStyleSheet("color: white; background: transparent;")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(title)

        # ── 源文本展示 ──
        source_frame = QFrame()
        source_frame.setStyleSheet(
            "background: rgba(255,255,255,0.06);"
            "border-radius: 8px;"
            "padding: 4px;"
        )
        source_layout = QHBoxLayout(source_frame)
        source_layout.setContentsMargins(12, 8, 12, 8)

        source_icon = QLabel("📝")
        source_icon.setFont(QFont("", 14))
        source_icon.setFixedWidth(24)
        source_layout.addWidget(source_icon)

        source_label = QLabel(self._source_text)
        source_label.setFont(QFont("", 12))
        source_label.setStyleSheet("color: rgba(255,255,255,0.7); background: transparent;")
        source_label.setWordWrap(True)
        source_layout.addWidget(source_label, 1)

        main_layout.addWidget(source_frame)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,0.1);")
        sep.setFixedHeight(1)
        main_layout.addWidget(sep)

        # ── 三列并排 ──
        columns_layout = QHBoxLayout()
        columns_layout.setSpacing(10)

        key_labels = ["1", "2", "3"]
        for i, profile in enumerate(self._profiles):
            preview_text = self._get_preview_text(profile)
            column = _CompareColumn(
                profile=profile,
                preview_text=preview_text,
                shortcut_key=key_labels[i],
                parent=self,
            )
            column.setMinimumHeight(self.COLUMN_MIN_HEIGHT)
            column.setMinimumWidth(self.COLUMN_WIDTH)
            column.clicked.connect(lambda idx=i: self._select(idx))
            self._columns.append(column)
            columns_layout.addWidget(column, 1)

        main_layout.addLayout(columns_layout, 1)

        # ── 底部提示 ──
        hint = QLabel("按 1 / 2 / 3 选择风格    Esc 取消")
        hint.setFont(QFont("", 10))
        hint.setStyleSheet("color: rgba(255,255,255,0.35); background: transparent;")
        hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        main_layout.addWidget(hint)

    def _get_preview_text(self, profile: StyleProfile) -> str:
        """获取风格的模拟预览文本。

        优先使用预设映射表，否则基于 profile 维度生成近似文本。
        实际 LLM 调用在下一阶段集成。
        """
        if profile.base_preset and profile.base_preset in _MOCK_PREVIEWS:
            return _MOCK_PREVIEWS[profile.base_preset]
        # 自定义风格：基于 formality 做简单区分
        if profile.formality > 0.7:
            return "（自定义正式风格预览 — 待 LLM 集成）"
        elif profile.formality < 0.3:
            return "（自定义口语风格预览 — 待 LLM 集成）"
        else:
            return "（自定义通用风格预览 — 待 LLM 集成）"

    def _size_to_fit(self) -> None:
        """根据列数计算窗口尺寸。"""
        col_count = len(self._profiles)
        total_width = (
            self.PADDING * 2
            + col_count * self.COLUMN_WIDTH
            + (col_count - 1) * 10  # 列间距
        )
        total_height = 480
        self.setFixedSize(total_width, total_height)

    # ------------------------------------------------------------------
    # 选择与动画
    # ------------------------------------------------------------------

    def _select(self, index: int) -> None:
        """选中指定列的风格，发射信号并关闭。"""
        if 0 <= index < len(self._profiles):
            self.style_selected.emit(self._profiles[index].id)
        self._dismiss()

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
        """键盘: 1/2/3 选择对应列，Esc 取消。"""
        key = event.key()

        if key == Qt.Key.Key_1:
            self._select(0)
            event.accept()
        elif key == Qt.Key.Key_2:
            self._select(1)
            event.accept()
        elif key == Qt.Key.Key_3:
            self._select(2)
            event.accept()
        elif key == Qt.Key.Key_Escape:
            self._dismiss()
            event.accept()
        else:
            super().keyPressEvent(event)

    # ------------------------------------------------------------------
    # 自定义绘制
    # ------------------------------------------------------------------

    def paintEvent(self, event: QPaintEvent) -> None:
        """半透明深色圆角背景。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect()
        bw = int(self.BORDER_WIDTH)
        draw_rect = rect.adjusted(bw, bw, -bw, -bw)

        bg_path = QPainterPath()
        bg_path.addRoundedRect(draw_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        bg_color = QColor(24, 24, 28, 220)
        painter.fillPath(bg_path, QBrush(bg_color))

        border_path = QPainterPath()
        border_path.addRoundedRect(draw_rect, self.CORNER_RADIUS, self.CORNER_RADIUS)
        pen = QPen(QColor(255, 255, 255, 25))
        pen.setWidthF(self.BORDER_WIDTH)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(border_path)

        painter.end()


# ---------------------------------------------------------------------------
# _CompareColumn: 单列风格预览卡片
# ---------------------------------------------------------------------------

class _CompareColumn(QFrame):
    """风格对比视图中的单列预览卡片。

    包含: 快捷键标记 + 风格图标 + 风格名 + 预览文本 + 选择按钮。
    """

    clicked = Signal()

    _BG_NORMAL = QColor(255, 255, 255, 5)
    _BG_HOVER = QColor(255, 255, 255, 12)
    _CORNER_RADIUS: float = 12.0

    def __init__(
        self,
        profile: StyleProfile,
        preview_text: str,
        shortcut_key: str = "",
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._profile = profile
        self._preview_text = preview_text
        self._shortcut_key = shortcut_key

        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._init_ui()

    def _init_ui(self) -> None:
        """初始化列内布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(8)

        # ── 顶部: 快捷键 + 风格名 ──
        header = QHBoxLayout()
        header.setSpacing(8)

        # 快捷键角标
        if self._shortcut_key:
            key_badge = QLabel(self._shortcut_key)
            key_badge.setFont(QFont("", 11, QFont.Weight.Bold))
            key_badge.setFixedSize(22, 22)
            key_badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
            key_badge.setStyleSheet(
                "background: rgba(255,255,255,0.12);"
                "color: rgba(255,255,255,0.6);"
                "border-radius: 4px;"
            )
            header.addWidget(key_badge)

        # 风格图标 + 名称
        icon_label = QLabel(self._profile.icon or "📝")
        icon_label.setFont(QFont("", 18))
        icon_label.setFixedWidth(28)
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("background: transparent;")
        header.addWidget(icon_label)

        name_label = QLabel(self._profile.name)
        name_label.setFont(QFont("", 13, QFont.Weight.Medium))
        name_label.setStyleSheet("color: white; background: transparent;")
        header.addWidget(name_label, 1)

        layout.addLayout(header)

        # ── 分隔线 ──
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: rgba(255,255,255,0.1);")
        sep.setFixedHeight(1)
        layout.addWidget(sep)

        # ── 预览文本 ──
        preview = QTextEdit()
        preview.setReadOnly(True)
        preview.setPlainText(self._preview_text)
        preview.setFont(QFont("", 12))
        preview.setStyleSheet(
            "QTextEdit {"
            "  background: rgba(255,255,255,0.04);"
            "  color: rgba(255,255,255,0.85);"
            "  border: none;"
            "  border-radius: 8px;"
            "  padding: 8px;"
            "}"
        )
        preview.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        layout.addWidget(preview, 1)

        # ── 选择按钮 ──
        select_btn = QPushButton(f"选择此风格 ({self._shortcut_key})")
        select_btn.setFont(QFont("", 11))
        select_btn.setFixedHeight(36)
        select_btn.setStyleSheet(
            "QPushButton {"
            "  background: rgba(255,255,255,0.12);"
            "  color: white;"
            "  border: 1px solid rgba(255,255,255,0.15);"
            "  border-radius: 8px;"
            "  padding: 4px 12px;"
            "}"
            "QPushButton:hover {"
            "  background: rgba(255,255,255,0.20);"
            "  border-color: rgba(255,255,255,0.3);"
            "}"
            "QPushButton:pressed {"
            "  background: rgba(255,255,255,0.10);"
            "}"
        )
        select_btn.clicked.connect(self.clicked.emit)
        layout.addWidget(select_btn)

    # ------------------------------------------------------------------
    # 事件
    # ------------------------------------------------------------------

    def mousePressEvent(self, event) -> None:
        """点击整列触发选择。"""
        self.clicked.emit()
        event.accept()

    def paintEvent(self, event: QPaintEvent) -> None:
        """绘制卡片圆角背景。"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        rect = self.rect().adjusted(1, 1, -1, -1)
        path = QPainterPath()
        path.addRoundedRect(rect, self._CORNER_RADIUS, self._CORNER_RADIUS)

        # 检测鼠标悬停
        under_mouse = self.rect().contains(self.mapFromGlobal(self.cursor().pos()))
        bg = self._BG_HOVER if under_mouse else self._BG_NORMAL
        painter.fillPath(path, QBrush(bg))

        # 边框
        pen = QPen(QColor(255, 255, 255, 18))
        pen.setWidthF(1.0)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

        painter.end()
