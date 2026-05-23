"""
灵犀输入 — StyleProfile 核心数据模型

定义风格配置的所有数据结构，包括枚举类型和 StyleProfile dataclass。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional
import uuid


# ---------------------------------------------------------------------------
# 枚举定义
# ---------------------------------------------------------------------------

class StyleProfileKind(str, Enum):
    """风格类型：预设或自定义。"""
    PRESET = "preset"
    CUSTOM = "custom"


class AddressForm(str, Enum):
    """称呼方式。"""
    NIN = "您"
    NI = "你"
    QIN = "亲"
    XIONGDI = "兄弟"
    LAOBAN = "老板"


class ClosingStyle(str, Enum):
    """结尾风格。"""
    NONE = "无结尾"
    THANKS = "谢谢/辛苦了"
    FORMAL = "此致敬礼"
    WARM = "祝好/安好"
    CASUAL = "😄/~"


class Punctuation(str, Enum):
    """标点风格。"""
    STRICT = "严谨标点"
    RELAXED = "宽松标点"
    SPACE = "空格代替标点"


class PersonForm(str, Enum):
    """第一人称代词。"""
    WO = "我"
    ZAN = "咱"
    AN = "俺"
    BENREN = "本人"


class ProfanityLevel(str, Enum):
    """脏话过滤级别。"""
    STRICT = "严格过滤"
    STANDARD = "标准过滤"
    RELAXED = "宽松过滤"
    NONE = "不过滤"


class PresetStyle(str, Enum):
    """预设风格标识。"""
    RESPECTFUL = "respectful"
    WARM = "warm"
    WITTY = "witty"
    PRECISE = "precise"
    CASUAL = "casual"
    MINIMAL = "minimal"


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------

def _enum_from_str(enum_cls: type[Enum], value: str | None) -> Optional[Enum]:
    """将字符串（或 None）转换为对应的枚举成员。"""
    if value is None:
        return None
    if isinstance(value, enum_cls):
        return value
    return enum_cls(value)


def _optional_enum_to_str(value: Optional[Enum]) -> Optional[str]:
    """将枚举成员（或 None）转换为其值字符串。"""
    if value is None:
        return None
    return value.value


# ---------------------------------------------------------------------------
# StyleProfile
# ---------------------------------------------------------------------------

@dataclass
class StyleProfile:
    """风格配置画像。

    包含风格的所有可调维度参数，支持序列化到 JSON 和从 JSON 反序列化。
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "新风格"
    icon: str = ""
    kind: StyleProfileKind = StyleProfileKind.CUSTOM

    # --- 核心维度 (0.0 ~ 1.0) ---
    formality: float = 0.5        # 正式度
    intimacy: float = 0.5         # 亲密感
    humor: float = 0.3            # 幽默感
    directness: float = 0.7       # 直接度
    conciseness: float = 0.6      # 简洁度

    # --- 细粒度控制 ---
    address_form: Optional[AddressForm] = None
    closing_style: Optional[ClosingStyle] = None
    punctuation: Optional[Punctuation] = None
    person_form: Optional[PersonForm] = None
    profanity_filter: Optional[ProfanityLevel] = None

    # --- 元数据 ---
    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    base_preset: Optional[PresetStyle] = None

    # ------------------------------------------------------------------
    # 序列化
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """将 StyleProfile 序列化为纯字典，用于 JSON 持久化。"""
        return {
            "id": self.id,
            "name": self.name,
            "icon": self.icon,
            "kind": self.kind.value,
            "formality": self.formality,
            "intimacy": self.intimacy,
            "humor": self.humor,
            "directness": self.directness,
            "conciseness": self.conciseness,
            "address_form": _optional_enum_to_str(self.address_form),
            "closing_style": _optional_enum_to_str(self.closing_style),
            "punctuation": _optional_enum_to_str(self.punctuation),
            "person_form": _optional_enum_to_str(self.person_form),
            "profanity_filter": _optional_enum_to_str(self.profanity_filter),
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "use_count": self.use_count,
            "base_preset": self.base_preset.value if self.base_preset else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "StyleProfile":
        """从字典反序列化创建 StyleProfile 实例。"""
        def _dt(val: Optional[str]) -> Optional[datetime]:
            if val is None:
                return None
            return datetime.fromisoformat(val)

        return cls(
            id=data.get("id", ""),
            name=data.get("name", "新风格"),
            icon=data.get("icon", ""),
            kind=StyleProfileKind(data.get("kind", "custom")),
            formality=float(data.get("formality", 0.5)),
            intimacy=float(data.get("intimacy", 0.5)),
            humor=float(data.get("humor", 0.3)),
            directness=float(data.get("directness", 0.7)),
            conciseness=float(data.get("conciseness", 0.6)),
            address_form=_enum_from_str(AddressForm, data.get("address_form")),
            closing_style=_enum_from_str(ClosingStyle, data.get("closing_style")),
            punctuation=_enum_from_str(Punctuation, data.get("punctuation")),
            person_form=_enum_from_str(PersonForm, data.get("person_form")),
            profanity_filter=_enum_from_str(ProfanityLevel, data.get("profanity_filter")),
            created_at=_dt(data.get("created_at")) or datetime.now(),
            last_used_at=_dt(data.get("last_used_at")),
            use_count=int(data.get("use_count", 0)),
            base_preset=_enum_from_str(PresetStyle, data.get("base_preset")),
        )
