"""
灵犀输入 — 6 套预设风格定义

每种预设风格是一组经过调校的维度参数组合，用户可以直接使用
或基于预设创建自定义风格。
"""

from __future__ import annotations

from datetime import datetime
import uuid

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


# ---------------------------------------------------------------------------
# 预设定义
# ---------------------------------------------------------------------------

def _make_preset(
    preset: PresetStyle,
    name: str,
    icon: str,
    formality: float,
    intimacy: float,
    humor: float,
    directness: float,
    conciseness: float,
    address_form: AddressForm | None = None,
    closing_style: ClosingStyle | None = None,
    punctuation: Punctuation | None = None,
    person_form: PersonForm | None = None,
    profanity_filter: ProfanityLevel | None = None,
) -> StyleProfile:
    """创建预设风格 Profile 的工厂函数。"""
    now = datetime.now()
    return StyleProfile(
        id=f"preset-{preset.value}-{uuid.uuid4().hex[:8]}",
        name=name,
        icon=icon,
        kind=StyleProfileKind.PRESET,
        formality=formality,
        intimacy=intimacy,
        humor=humor,
        directness=directness,
        conciseness=conciseness,
        address_form=address_form,
        closing_style=closing_style,
        punctuation=punctuation,
        person_form=person_form,
        profanity_filter=profanity_filter,
        created_at=now,
        last_used_at=None,
        use_count=0,
        base_preset=preset,
    )


# --- 敬重 ---
RESPECTFUL = _make_preset(
    preset=PresetStyle.RESPECTFUL,
    name="敬重",
    icon="🎓",
    formality=0.9,
    intimacy=0.2,
    humor=0.0,
    directness=0.5,
    conciseness=0.7,
    address_form=AddressForm.NIN,
    closing_style=ClosingStyle.FORMAL,
    punctuation=Punctuation.STRICT,
    person_form=PersonForm.WO,
    profanity_filter=ProfanityLevel.STRICT,
)

# --- 亲热 ---
WARM = _make_preset(
    preset=PresetStyle.WARM,
    name="亲热",
    icon="❤️",
    formality=0.2,
    intimacy=0.9,
    humor=0.5,
    directness=0.8,
    conciseness=0.4,
    address_form=AddressForm.QIN,
    closing_style=ClosingStyle.CASUAL,
    punctuation=Punctuation.RELAXED,
    person_form=PersonForm.WO,
    profanity_filter=ProfanityLevel.STANDARD,
)

# --- 诙谐 ---
WITTY = _make_preset(
    preset=PresetStyle.WITTY,
    name="诙谐",
    icon="😎",
    formality=0.1,
    intimacy=0.7,
    humor=0.9,
    directness=0.7,
    conciseness=0.5,
    address_form=AddressForm.XIONGDI,
    closing_style=ClosingStyle.CASUAL,
    punctuation=Punctuation.RELAXED,
    person_form=PersonForm.ZAN,
    profanity_filter=ProfanityLevel.RELAXED,
)

# --- 严谨 ---
PRECISE = _make_preset(
    preset=PresetStyle.PRECISE,
    name="严谨",
    icon="📊",
    formality=0.85,
    intimacy=0.15,
    humor=0.0,
    directness=0.9,
    conciseness=0.85,
    address_form=AddressForm.NIN,
    closing_style=ClosingStyle.NONE,
    punctuation=Punctuation.STRICT,
    person_form=PersonForm.BENREN,
    profanity_filter=ProfanityLevel.STRICT,
)

# --- 日常 ---
CASUAL = _make_preset(
    preset=PresetStyle.CASUAL,
    name="日常",
    icon="🍃",
    formality=0.5,
    intimacy=0.5,
    humor=0.3,
    directness=0.7,
    conciseness=0.6,
    address_form=AddressForm.NI,
    closing_style=ClosingStyle.THANKS,
    punctuation=Punctuation.RELAXED,
    person_form=PersonForm.WO,
    profanity_filter=ProfanityLevel.STANDARD,
)

# --- 极简 ---
MINIMAL = _make_preset(
    preset=PresetStyle.MINIMAL,
    name="极简",
    icon="⚡",
    formality=0.5,
    intimacy=0.3,
    humor=0.0,
    directness=1.0,
    conciseness=1.0,
    address_form=None,
    closing_style=ClosingStyle.NONE,
    punctuation=Punctuation.SPACE,
    person_form=None,
    profanity_filter=ProfanityLevel.NONE,
)


# ---------------------------------------------------------------------------
# 导出字典
# ---------------------------------------------------------------------------

PRESET_STYLES: dict[PresetStyle, StyleProfile] = {
    PresetStyle.RESPECTFUL: RESPECTFUL,
    PresetStyle.WARM: WARM,
    PresetStyle.WITTY: WITTY,
    PresetStyle.PRECISE: PRECISE,
    PresetStyle.CASUAL: CASUAL,
    PresetStyle.MINIMAL: MINIMAL,
}


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def get_preset(preset: PresetStyle) -> StyleProfile:
    """根据预设枚举获取对应的 StyleProfile。

    Args:
        preset: 预设风格枚举值。

    Returns:
        对应的 StyleProfile 实例（深拷贝前的引用；若需修改请先 copy）。

    Raises:
        KeyError: 传入未知预设枚举时抛出。
    """
    if preset not in PRESET_STYLES:
        raise KeyError(f"未知预设风格: {preset!r}")
    return PRESET_STYLES[preset]
