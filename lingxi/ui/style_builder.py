"""
灵犀输入 — Style Builder UI

PySide6 三栏布局风格构建器，提供预设选择、五维滑块调节、
场景微调和实时规则引擎预览。

规格 §1.3: 三栏布局 — 预设起点 | 五维滑块 + 场景微调 | 实时预览
"""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QSlider, QComboBox, QPushButton, QLineEdit,
    QGroupBox, QRadioButton, QScrollArea, QTextEdit,
    QMessageBox, QFrame, QButtonGroup, QSizePolicy, QSpacerItem,
)
from PySide6.QtCore import Qt, Signal

from lingxi.style.profile import (
    StyleProfile,
    StyleProfileKind,
    PresetStyle,
    AddressForm,
    ClosingStyle,
    Punctuation,
    PersonForm,
    ProfanityLevel,
)
from lingxi.style.presets import PRESET_STYLES, get_preset
from lingxi.style.store import StyleProfileStore

# ---------------------------------------------------------------------------
# 维度定义（供 UI 循环使用）
# ---------------------------------------------------------------------------

_DIMENSION_DEFS: list[dict[str, str | float]] = [
    {"key": "formality",    "label": "正式度", "default": 0.5},
    {"key": "intimacy",     "label": "亲密度", "default": 0.5},
    {"key": "humor",        "label": "幽默度", "default": 0.3},
    {"key": "directness",   "label": "直接度", "default": 0.7},
    {"key": "conciseness",  "label": "简练度", "default": 0.6},
]

# 预设中文名称映射
_PRESET_LABELS: dict[PresetStyle | None, str] = {
    None:                    "从零开始",
    PresetStyle.RESPECTFUL:  "敬重",
    PresetStyle.WARM:        "亲热",
    PresetStyle.WITTY:       "诙谐",
    PresetStyle.PRECISE:     "严谨",
    PresetStyle.CASUAL:      "日常",
    PresetStyle.MINIMAL:     "极简",
}

# ---------------------------------------------------------------------------
# StyleBuilder
# ---------------------------------------------------------------------------


class StyleBuilder(QWidget):
    """三栏布局的风格构建器。

    信号:
        style_saved(str): 保存成功后发射，携带已保存的风格 ID。
    """

    style_saved = Signal(str)

    # 滑块范围常量
    _SLIDER_MIN = 0
    _SLIDER_MAX = 100
    _SLIDER_STEP = 10

    def __init__(self, parent: Optional[QWidget] = None) -> None:
        super().__init__(parent)
        self._current_profile = StyleProfile()
        self._editing_id: Optional[str] = None  # 编辑模式下的现有 ID
        self._init_ui()
        self._apply_style_to_ui(self._current_profile)

    # ------------------------------------------------------------------
    # UI 初始化
    # ------------------------------------------------------------------

    def _init_ui(self) -> None:
        """初始化三栏布局。"""
        self.setWindowTitle("风格构建器 · 灵犀输入")
        self.resize(900, 600)

        main_layout = QHBoxLayout(self)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_layout.setSpacing(12)

        # 左栏: 预设起点
        left = self._create_preset_column()
        main_layout.addWidget(left, 1)

        # 中栏: 五维滑块 + 场景微调
        center = self._create_slider_column()
        main_layout.addWidget(center, 2)

        # 右栏: 实时预览
        right = self._create_preview_column()
        main_layout.addWidget(right, 2)

    # ------------------------------------------------------------------
    # 左栏: 预设选择
    # ------------------------------------------------------------------

    def _create_preset_column(self) -> QWidget:
        """创建预设起点列（radio buttons）。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        # 标题
        title = QLabel("预设起点")
        title_font = title.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 1)
        title.setFont(title_font)
        layout.addWidget(title)

        # 分隔线
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # Radio buttons group
        self._preset_group = QButtonGroup(self)
        self._preset_radios: dict[Optional[PresetStyle], QRadioButton] = {}
        self._preset_group.setExclusive(True)

        preset_order: list[Optional[PresetStyle]] = [
            None,
            PresetStyle.RESPECTFUL,
            PresetStyle.WARM,
            PresetStyle.WITTY,
            PresetStyle.PRECISE,
            PresetStyle.CASUAL,
            PresetStyle.MINIMAL,
        ]

        for preset in preset_order:
            label = _PRESET_LABELS[preset]
            if preset is not None:
                p = get_preset(preset)
                label = f"{label}  {p.icon}"

            radio = QRadioButton(label)
            self._preset_group.addButton(radio)
            self._preset_radios[preset] = radio
            layout.addWidget(radio)

        # 默认选中 "从零开始"
        self._preset_radios[None].setChecked(True)
        self._preset_group.buttonClicked.connect(self._on_preset_radio_clicked)

        # 底部弹簧
        layout.addStretch()

        return container

    # ------------------------------------------------------------------
    # 中栏: 五维滑块 + 场景微调
    # ------------------------------------------------------------------

    def _create_slider_column(self) -> QWidget:
        """创建中栏: 五维滑块 + 场景微调 + 保存区域。

        使用 QScrollArea 包裹，以应对窗口缩小时的内容溢出。
        """
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # -- 标题 --
        title = QLabel("风格调节")
        title_font = title.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 1)
        title.setFont(title_font)
        layout.addWidget(title)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # -- 五维滑块 --
        self._sliders: dict[str, QSlider] = {}
        self._slider_labels: dict[str, QLabel] = {}

        for dim in _DIMENSION_DEFS:
            dim_key: str = dim["key"]  # type: ignore[assignment]
            dim_label: str = dim["label"]  # type: ignore[assignment]
            default_val: float = dim["default"]  # type: ignore[assignment]

            row = QHBoxLayout()
            row.setSpacing(6)

            name_lbl = QLabel(dim_label)
            name_lbl.setMinimumWidth(48)
            name_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(name_lbl)

            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(self._SLIDER_MIN, self._SLIDER_MAX)
            slider.setSingleStep(self._SLIDER_STEP)
            slider.setPageStep(self._SLIDER_STEP)
            slider.setTickPosition(QSlider.TickPosition.TicksBelow)
            slider.setTickInterval(self._SLIDER_STEP)
            slider.setValue(int(default_val * 100))
            row.addWidget(slider, 1)

            pct_lbl = QLabel(f"{int(default_val * 100)}%")
            pct_lbl.setMinimumWidth(36)
            pct_lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(pct_lbl)

            self._sliders[dim_key] = slider
            self._slider_labels[dim_key] = pct_lbl

            slider.valueChanged.connect(self._on_slider_changed)

            layout.addLayout(row)

        # -- 分隔 --
        layout.addSpacing(8)
        line2 = QFrame()
        line2.setFrameShape(QFrame.Shape.HLine)
        line2.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line2)

        # -- 场景微调 --
        scenario_title = QLabel("场景微调")
        scenario_title_font = scenario_title.font()
        scenario_title_font.setBold(True)
        scenario_title.setFont(scenario_title_font)
        layout.addWidget(scenario_title)

        self._scenario_combos: dict[str, QComboBox] = {}
        self._scenario_enums: dict[str, type] = {
            "address_form":    AddressForm,
            "closing_style":   ClosingStyle,
            "punctuation":     Punctuation,
            "person_form":     PersonForm,
            "profanity_filter": ProfanityLevel,
        }
        _scenario_labels: dict[str, str] = {
            "address_form":    "称呼",
            "closing_style":   "结尾",
            "punctuation":     "标点",
            "person_form":     "人称",
            "profanity_filter": "过滤",
        }

        for field_key, enum_cls in self._scenario_enums.items():
            row = QHBoxLayout()
            row.setSpacing(6)

            lbl = QLabel(_scenario_labels[field_key])
            lbl.setMinimumWidth(48)
            lbl.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            row.addWidget(lbl)

            combo = QComboBox()
            combo.addItem("不指定", None)
            for member in enum_cls:
                combo.addItem(member.value, member)

            combo.currentIndexChanged.connect(self._on_slider_changed)
            self._scenario_combos[field_key] = combo
            row.addWidget(combo, 1)

            layout.addLayout(row)

        # -- 分隔 --
        layout.addSpacing(8)
        line3 = QFrame()
        line3.setFrameShape(QFrame.Shape.HLine)
        line3.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line3)

        # -- 保存区域 --
        save_title = QLabel("保存风格")
        save_title_font = save_title.font()
        save_title_font.setBold(True)
        save_title.setFont(save_title_font)
        layout.addWidget(save_title)

        name_row = QHBoxLayout()
        name_row.setSpacing(6)

        self._name_input = QLineEdit()
        self._name_input.setPlaceholderText("输入风格名称...")
        self._name_input.setText(self._current_profile.name)
        name_row.addWidget(self._name_input, 1)

        self._save_btn = QPushButton("保存")
        self._save_btn.setMinimumWidth(60)
        self._save_btn.clicked.connect(self._on_save)
        name_row.addWidget(self._save_btn)

        layout.addLayout(name_row)

        # 弹簧
        layout.addStretch()

        scroll.setWidget(container)
        return scroll

    # ------------------------------------------------------------------
    # 右栏: 实时预览
    # ------------------------------------------------------------------

    def _create_preview_column(self) -> QWidget:
        """创建实时预览列。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # 标题
        title = QLabel("实时预览")
        title_font = title.font()
        title_font.setBold(True)
        title_font.setPointSize(title_font.pointSize() + 1)
        title.setFont(title_font)
        layout.addWidget(title)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

        # 测试输入
        input_lbl = QLabel("输入测试文本:")
        layout.addWidget(input_lbl)

        self._test_input = QLineEdit()
        self._test_input.setPlaceholderText("输入一段文本，查看风格效果...")
        self._test_input.setText("我今天加班，晚点回去")
        self._test_input.textChanged.connect(self._on_slider_changed)
        layout.addWidget(self._test_input)

        # 预览输出标签
        output_lbl = QLabel("预览输出:")
        layout.addWidget(output_lbl)

        self._preview_output = QTextEdit()
        self._preview_output.setReadOnly(True)
        self._preview_output.setPlaceholderText("调整左侧风格参数后，此处将显示规则引擎预览效果...")
        self._preview_output.setMinimumHeight(150)
        layout.addWidget(self._preview_output, 1)

        # 说明
        note = QLabel("预览效果，实际输出以 LLM 为准")
        note.setAlignment(Qt.AlignmentFlag.AlignCenter)
        note.setStyleSheet("color: #888; font-size: 11px;")
        layout.addWidget(note)

        return container

    # ------------------------------------------------------------------
    # 信号处理
    # ------------------------------------------------------------------

    def _on_slider_changed(self) -> None:
        """任意滑块或场景组合框变化时，同步 profile 并更新预览。"""
        self._sync_ui_to_profile()
        self._update_preview()

    def _on_preset_radio_clicked(self, radio: QRadioButton) -> None:
        """预设 radio 选中时，加载对应预设到 UI。"""
        for preset, r in self._preset_radios.items():
            if r is radio:
                if preset is None:
                    # "从零开始": 重置为默认值
                    self._reset_to_defaults()
                else:
                    self._load_preset(preset)
                return

    # ------------------------------------------------------------------
    # 数据同步
    # ------------------------------------------------------------------

    def _sync_ui_to_profile(self) -> None:
        """将 UI 控件值同步到 _current_profile。"""
        p = self._current_profile

        # 五维
        for dim in _DIMENSION_DEFS:
            dim_key: str = dim["key"]  # type: ignore[assignment]
            slider = self._sliders.get(dim_key)
            if slider is not None:
                setattr(p, dim_key, slider.value() / 100.0)

        # 场景微调
        for field_key, combo in self._scenario_combos.items():
            data = combo.currentData()
            setattr(p, field_key, data)  # None 或枚举成员

    def _apply_style_to_ui(self, profile: StyleProfile) -> None:
        """将 StyleProfile 的值应用到 UI 控件（不触发信号）。"""
        # 阻断信号以避免循环更新
        for dim in _DIMENSION_DEFS:
            dim_key: str = dim["key"]  # type: ignore[assignment]
            slider = self._sliders.get(dim_key)
            label = self._slider_labels.get(dim_key)
            if slider is not None:
                val = getattr(profile, dim_key, 0.5)
                slider.blockSignals(True)
                slider.setValue(int(val * 100))
                slider.blockSignals(False)
            if label is not None:
                val = getattr(profile, dim_key, 0.5)
                label.setText(f"{int(val * 100)}%")

        for field_key, combo in self._scenario_combos.items():
            val = getattr(profile, field_key, None)
            combo.blockSignals(True)
            idx = combo.findData(val)
            if idx >= 0:
                combo.setCurrentIndex(idx)
            else:
                combo.setCurrentIndex(0)  # "不指定"
            combo.blockSignals(False)

        self._name_input.setText(profile.name)

        # 检查是否匹配某个预设
        base = profile.base_preset
        radio = self._preset_radios.get(base)
        if radio is not None:
            radio.blockSignals(True)
            radio.setChecked(True)
            radio.blockSignals(False)
        else:
            self._preset_radios[None].blockSignals(True)
            self._preset_radios[None].setChecked(True)
            self._preset_radios[None].blockSignals(False)

    def _reset_to_defaults(self) -> None:
        """重置所有控件为默认值。"""
        default = StyleProfile()
        default.base_preset = None
        self._current_profile = default
        self._apply_style_to_ui(default)
        self._update_preview()

    def _load_preset(self, preset: PresetStyle) -> None:
        """加载预设风格到 UI。"""
        profile = get_preset(preset)
        # 创建副本以避免修改预设原始数据
        self._current_profile = StyleProfile(
            name=profile.name,
            icon=profile.icon,
            kind=StyleProfileKind.CUSTOM,
            formality=profile.formality,
            intimacy=profile.intimacy,
            humor=profile.humor,
            directness=profile.directness,
            conciseness=profile.conciseness,
            address_form=profile.address_form,
            closing_style=profile.closing_style,
            punctuation=profile.punctuation,
            person_form=profile.person_form,
            profanity_filter=profile.profanity_filter,
            base_preset=preset,
        )
        self._apply_style_to_ui(self._current_profile)
        self._update_preview()

    # ------------------------------------------------------------------
    # 规则引擎预览
    # ------------------------------------------------------------------

    def _update_preview(self) -> None:
        """使用规则引擎更新预览文本。

        基于五维值和场景微调做简单文本变换：
        - formality > 0.7: 替换"你"为"您"，添加正式用词
        - intimacy > 0.7: 添加亲昵语气词/emoji
        - humor > 0.7: 添加诙谐表达
        - directness < 0.3: 添加委婉前缀
        - conciseness < 0.3: 添加解释性前缀
        - conciseness > 0.7: 压缩为极简形式
        - scenario: 替换称呼、附加结尾等
        """
        text = self._test_input.text().strip()
        if not text:
            self._preview_output.clear()
            return

        p = self._current_profile
        result = self._apply_preview_rules(text, p)

        # 展示多风格对比预览
        lines: list[str] = []
        lines.append(result)

        self._preview_output.setPlainText("\n".join(lines))

    # 规则引擎 v1.0 有在 _update_preview 中直接展示单条结果，
    # 下面的 _apply_preview_rules 执行实际的文本变换。

    def _apply_preview_rules(self, text: str, p: StyleProfile) -> str:
        """对输入文本应用规则引擎变换并返回结果字符串。"""
        result = text

        # --- 1. 正式度 ---
        if p.formality > 0.7:
            # 高正式度: 替换"你"→"您"、"我"→"本人"、去口语
            result = result.replace("你", "您")
            result = result.replace("我", "本人")
            result = result.replace("晚点", "延后")
            result = result.replace("加班", "需加班处理")
            result = result.replace("回去", "返程")
        elif p.formality < 0.3:
            # 低正式度: 口语化
            result = result.replace("加班", "赶个工")
            if "回去" in result:
                result = result.replace("回去", "回去哈")

        # --- 2. 亲密度 ---
        if p.intimacy > 0.7:
            # 高亲密: 加亲昵后缀/emoji
            if not result.endswith("~"):
                result = result.rstrip("。！!？?") + "~"
        elif p.intimacy < 0.3:
            # 低亲密: 保持距离
            pass

        # --- 3. 幽默度 ---
        if p.humor > 0.7:
            # 高幽默: 添加轻松表达
            if "加班" in result and "😅" not in result:
                result = result.rstrip("~。！!？?") + " 😅"

        # --- 4. 直接度 ---
        if p.directness < 0.3:
            # 低直接度: 委婉前缀
            if not result.startswith("请问"):
                result = "请问，" + result
            if "晚点" in result or "延后" in result:
                result = result.replace("回去", "是否可以稍后回去")
        elif p.directness > 0.7:
            # 高直接度: 去掉委婉词
            result = result.replace("请问，", "")

        # --- 5. 简练度 ---
        if p.conciseness < 0.3:
            # 低简练度: 添加解释
            if "加班" in result and "需要" not in result:
                result = "今天因为工作需要，" + result
        elif p.conciseness > 0.7:
            # 高简练度: 精简
            result = result.replace("我今天", "")
            result = result.replace("今天因为工作需要，", "")
            result = result.replace("，", " ").replace("。", " ")
            # 去掉多余空格
            result = " ".join(result.split())

        # --- 6. 场景微调: 称呼 ---
        if p.address_form is not None:
            af = p.address_form
            if af == AddressForm.NIN:
                result = result.replace("你", "您")
            elif af == AddressForm.NI:
                # 确保不用"您"，但保持原有（默认已是"你"）
                pass
            elif af == AddressForm.QIN:
                result = result.replace("你", "亲")
                result = result.replace("您", "亲")
            elif af == AddressForm.XIONGDI:
                # 兄弟 → 在文本前加称呼
                if "兄弟" not in result:
                    result = "兄弟，" + result
            elif af == AddressForm.LAOBAN:
                if "老板" not in result:
                    result = "老板，" + result

        # --- 7. 场景微调: 结尾 ---
        if p.closing_style is not None:
            cs = p.closing_style
            endings: dict[ClosingStyle, str] = {
                ClosingStyle.NONE:   "",
                ClosingStyle.THANKS: " 谢谢！",
                ClosingStyle.FORMAL: " 此致\n敬礼",
                ClosingStyle.WARM:   " 祝好！",
                ClosingStyle.CASUAL: " 😄~",
            }
            suffix = endings.get(cs, "")
            if suffix and not result.endswith(suffix):
                # 清理已有结尾标记
                result = result.rstrip("~。！!？?😄😅 ") + suffix

        # --- 8. 场景微调: 标点 ---
        if p.punctuation is not None:
            if p.punctuation == Punctuation.STRICT:
                # 确保以句号结尾
                result = result.rstrip("~。！!？?😄😅 ,， ")
                if result and not result[-1] in "。！!？?":
                    result += "。"
            elif p.punctuation == Punctuation.SPACE:
                # 用空格代替标点
                result = result.replace("，", " ").replace("。", " ").replace("！", " ").replace("？", " ")
                result = " ".join(result.split())

        # --- 9. 场景微调: 人称 ---
        if p.person_form is not None:
            pf = p.person_form
            replacements: dict[PersonForm, str] = {
                PersonForm.WO:     "我",
                PersonForm.ZAN:    "咱",
                PersonForm.AN:     "俺",
                PersonForm.BENREN: "本人",
            }
            target = replacements.get(pf, "我")
            # 替换第一人称
            for old_word in ("我", "咱", "俺", "本人"):
                if old_word != target:
                    result = result.replace(old_word, target)

        return result.strip()

    # ------------------------------------------------------------------
    # 保存
    # ------------------------------------------------------------------

    def _on_save(self) -> None:
        """保存风格: 收集所有字段 → StyleProfileStore.add() → emit signal。"""
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "保存失败", "请输入风格名称。")
            return

        # 同步最新的 UI 值
        self._sync_ui_to_profile()

        # 设置名称和元数据
        profile = self._current_profile
        profile.name = name
        profile.icon = ""
        profile.kind = StyleProfileKind.CUSTOM

        store = StyleProfileStore()
        store.load()

        if self._editing_id:
            # 编辑模式: 复用已有 ID
            profile.id = self._editing_id
            try:
                store.update(profile)
            except KeyError:
                store.add(profile)
        else:
            store.add(profile)

        self._editing_id = profile.id
        self.style_saved.emit(profile.id)

        QMessageBox.information(
            self,
            "保存成功",
            f"风格「{name}」已保存。",
        )

    # ------------------------------------------------------------------
    # 公开 API
    # ------------------------------------------------------------------

    def load_style(self, profile: StyleProfile) -> None:
        """从外部加载风格（编辑模式）。

        Args:
            profile: 要编辑的 StyleProfile 实例。
        """
        self._current_profile = StyleProfile(
            id=profile.id,
            name=profile.name,
            icon=profile.icon,
            kind=profile.kind,
            formality=profile.formality,
            intimacy=profile.intimacy,
            humor=profile.humor,
            directness=profile.directness,
            conciseness=profile.conciseness,
            address_form=profile.address_form,
            closing_style=profile.closing_style,
            punctuation=profile.punctuation,
            person_form=profile.person_form,
            profanity_filter=profile.profanity_filter,
            base_preset=profile.base_preset,
        )
        self._editing_id = profile.id
        self._apply_style_to_ui(self._current_profile)
        self._update_preview()
