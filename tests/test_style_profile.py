"""
灵犀输入 — StyleProfile 单元测试

覆盖：JSON 序列化往返、预设枚举映射、6 套预设值验证、
StyleProfileStore CRUD。
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime

import pytest

from lingxi.style.profile import (
    StyleProfile,
    StyleProfileKind,
    AddressForm,
    ClosingStyle,
    Punctuation,
    PersonForm,
    ProfanityLevel,
    PresetStyle,
)
from lingxi.style.presets import (
    PRESET_STYLES,
    get_preset,
    RESPECTFUL,
    WARM,
    WITTY,
    PRECISE,
    CASUAL,
    MINIMAL,
)
from lingxi.style.store import StyleProfileStore


# ======================================================================
# JSON 序列化 / 反序列化 往返测试
# ======================================================================

class TestSerialization:
    """测试 StyleProfile 的 to_dict / from_dict 往返。"""

    def test_roundtrip_default(self) -> None:
        """默认值的 StyleProfile 往返后数据一致。"""
        profile = StyleProfile()
        data = profile.to_dict()
        restored = StyleProfile.from_dict(data)

        assert restored.id == profile.id
        assert restored.name == profile.name
        assert restored.kind == profile.kind
        assert restored.formality == pytest.approx(profile.formality)
        assert restored.intimacy == pytest.approx(profile.intimacy)
        assert restored.humor == pytest.approx(profile.humor)
        assert restored.directness == pytest.approx(profile.directness)
        assert restored.conciseness == pytest.approx(profile.conciseness)

    def test_roundtrip_full(self) -> None:
        """所有字段均显式设置的往返测试。"""
        now = datetime(2026, 5, 24, 12, 0, 0)
        last = datetime(2026, 5, 24, 12, 30, 0)
        profile = StyleProfile(
            id="test-id-001",
            name="测试风格",
            icon="🧪",
            kind=StyleProfileKind.CUSTOM,
            formality=0.7,
            intimacy=0.3,
            humor=0.6,
            directness=0.8,
            conciseness=0.5,
            address_form=AddressForm.NIN,
            closing_style=ClosingStyle.THANKS,
            punctuation=Punctuation.STRICT,
            person_form=PersonForm.WO,
            profanity_filter=ProfanityLevel.STANDARD,
            created_at=now,
            last_used_at=last,
            use_count=42,
            base_preset=PresetStyle.WARM,
        )

        data = profile.to_dict()
        restored = StyleProfile.from_dict(data)

        assert restored.id == "test-id-001"
        assert restored.name == "测试风格"
        assert restored.icon == "🧪"
        assert restored.kind == StyleProfileKind.CUSTOM
        assert restored.formality == pytest.approx(0.7)
        assert restored.intimacy == pytest.approx(0.3)
        assert restored.humor == pytest.approx(0.6)
        assert restored.directness == pytest.approx(0.8)
        assert restored.conciseness == pytest.approx(0.5)
        assert restored.address_form == AddressForm.NIN
        assert restored.closing_style == ClosingStyle.THANKS
        assert restored.punctuation == Punctuation.STRICT
        assert restored.person_form == PersonForm.WO
        assert restored.profanity_filter == ProfanityLevel.STANDARD
        assert restored.created_at == now
        assert restored.last_used_at == last
        assert restored.use_count == 42
        assert restored.base_preset == PresetStyle.WARM

    def test_roundtrip_none_optional(self) -> None:
        """Optional 枚举字段为 None 时往返正常。"""
        profile = StyleProfile(
            address_form=None,
            closing_style=None,
            punctuation=None,
            person_form=None,
            profanity_filter=None,
            base_preset=None,
            last_used_at=None,
        )
        data = profile.to_dict()
        restored = StyleProfile.from_dict(data)

        assert restored.address_form is None
        assert restored.closing_style is None
        assert restored.punctuation is None
        assert restored.person_form is None
        assert restored.profanity_filter is None
        assert restored.base_preset is None
        assert restored.last_used_at is None

    def test_to_dict_types(self) -> None:
        """to_dict 输出的值类型正确。"""
        profile = StyleProfile(
            address_form=AddressForm.NIN,
            base_preset=PresetStyle.CASUAL,
        )
        data = profile.to_dict()

        assert isinstance(data["id"], str)
        assert isinstance(data["formality"], float)
        assert data["kind"] == "custom"        # str, not Enum
        assert data["address_form"] == "您"    # str, not Enum
        assert data["base_preset"] == "casual"  # str, not Enum
        assert isinstance(data["created_at"], str)

    def test_from_dict_missing_keys(self) -> None:
        """from_dict 缺失字段时使用默认值。"""
        restored = StyleProfile.from_dict({})
        assert restored.name == "新风格"
        assert restored.kind == StyleProfileKind.CUSTOM
        assert restored.formality == pytest.approx(0.5)
        assert restored.use_count == 0
        assert restored.base_preset is None

    def test_json_serializable(self) -> None:
        """to_dict 输出可直接用 json.dumps 序列化。"""
        profile = StyleProfile(name="JSON 兼容测试")
        data = profile.to_dict()
        json_str = json.dumps(data, ensure_ascii=False)
        parsed = json.loads(json_str)
        assert parsed["name"] == "JSON 兼容测试"


# ======================================================================
# 枚举 & 预设映射测试
# ======================================================================

class TestEnums:
    """Enum 值正确映射。"""

    def test_preset_enum_values(self) -> None:
        assert PresetStyle.RESPECTFUL.value == "respectful"
        assert PresetStyle.WARM.value == "warm"
        assert PresetStyle.WITTY.value == "witty"
        assert PresetStyle.PRECISE.value == "precise"
        assert PresetStyle.CASUAL.value == "casual"
        assert PresetStyle.MINIMAL.value == "minimal"

    def test_preset_from_string(self) -> None:
        assert PresetStyle("respectful") == PresetStyle.RESPECTFUL
        assert PresetStyle("warm") == PresetStyle.WARM
        assert PresetStyle("casual") == PresetStyle.CASUAL

    def test_address_form_values(self) -> None:
        assert AddressForm.NIN.value == "您"
        assert AddressForm.NI.value == "你"
        assert AddressForm.QIN.value == "亲"

    def test_closing_style_values(self) -> None:
        assert ClosingStyle.NONE.value == "无结尾"
        assert ClosingStyle.FORMAL.value == "此致敬礼"
        assert ClosingStyle.CASUAL.value == "😄/~"

    def test_presets_dict_has_6_entries(self) -> None:
        assert len(PRESET_STYLES) == 6
        for preset_enum in PresetStyle:
            assert preset_enum in PRESET_STYLES

    def test_get_preset_returns_correct_type(self) -> None:
        for preset_enum in PresetStyle:
            profile = get_preset(preset_enum)
            assert isinstance(profile, StyleProfile)
            assert profile.kind == StyleProfileKind.PRESET
            assert profile.base_preset == preset_enum

    def test_get_preset_invalid_raises(self) -> None:
        with pytest.raises(KeyError, match="未知预设风格"):
            get_preset("nonexistent")  # type: ignore[arg-type]


# ======================================================================
# 6 套预设值精确验证
# ======================================================================

class TestPresetValues:
    """验证每套预设的维度数值与定义完全一致。"""

    def test_respectful(self) -> None:
        p = RESPECTFUL
        assert p.name == "敬重"
        assert p.icon == "🎓"
        assert p.formality == pytest.approx(0.9)
        assert p.intimacy == pytest.approx(0.2)
        assert p.humor == pytest.approx(0.0)
        assert p.directness == pytest.approx(0.5)
        assert p.conciseness == pytest.approx(0.7)
        assert p.address_form == AddressForm.NIN
        assert p.closing_style == ClosingStyle.FORMAL
        assert p.punctuation == Punctuation.STRICT
        assert p.person_form == PersonForm.WO
        assert p.profanity_filter == ProfanityLevel.STRICT
        assert p.kind == StyleProfileKind.PRESET
        assert p.base_preset == PresetStyle.RESPECTFUL

    def test_warm(self) -> None:
        p = WARM
        assert p.name == "亲热"
        assert p.icon == "❤️"
        assert p.formality == pytest.approx(0.2)
        assert p.intimacy == pytest.approx(0.9)
        assert p.humor == pytest.approx(0.5)
        assert p.directness == pytest.approx(0.8)
        assert p.conciseness == pytest.approx(0.4)
        assert p.address_form == AddressForm.QIN
        assert p.closing_style == ClosingStyle.CASUAL
        assert p.punctuation == Punctuation.RELAXED
        assert p.person_form == PersonForm.WO
        assert p.profanity_filter == ProfanityLevel.STANDARD
        assert p.base_preset == PresetStyle.WARM

    def test_witty(self) -> None:
        p = WITTY
        assert p.name == "诙谐"
        assert p.icon == "😎"
        assert p.formality == pytest.approx(0.1)
        assert p.intimacy == pytest.approx(0.7)
        assert p.humor == pytest.approx(0.9)
        assert p.directness == pytest.approx(0.7)
        assert p.conciseness == pytest.approx(0.5)
        assert p.address_form == AddressForm.XIONGDI
        assert p.closing_style == ClosingStyle.CASUAL
        assert p.punctuation == Punctuation.RELAXED
        assert p.person_form == PersonForm.ZAN
        assert p.profanity_filter == ProfanityLevel.RELAXED
        assert p.base_preset == PresetStyle.WITTY

    def test_precise(self) -> None:
        p = PRECISE
        assert p.name == "严谨"
        assert p.icon == "📊"
        assert p.formality == pytest.approx(0.85)
        assert p.intimacy == pytest.approx(0.15)
        assert p.humor == pytest.approx(0.0)
        assert p.directness == pytest.approx(0.9)
        assert p.conciseness == pytest.approx(0.85)
        assert p.address_form == AddressForm.NIN
        assert p.closing_style == ClosingStyle.NONE
        assert p.punctuation == Punctuation.STRICT
        assert p.person_form == PersonForm.BENREN
        assert p.profanity_filter == ProfanityLevel.STRICT
        assert p.base_preset == PresetStyle.PRECISE

    def test_casual(self) -> None:
        p = CASUAL
        assert p.name == "日常"
        assert p.icon == "🍃"
        assert p.formality == pytest.approx(0.5)
        assert p.intimacy == pytest.approx(0.5)
        assert p.humor == pytest.approx(0.3)
        assert p.directness == pytest.approx(0.7)
        assert p.conciseness == pytest.approx(0.6)
        assert p.address_form == AddressForm.NI
        assert p.closing_style == ClosingStyle.THANKS
        assert p.punctuation == Punctuation.RELAXED
        assert p.person_form == PersonForm.WO
        assert p.profanity_filter == ProfanityLevel.STANDARD
        assert p.base_preset == PresetStyle.CASUAL

    def test_minimal(self) -> None:
        p = MINIMAL
        assert p.name == "极简"
        assert p.icon == "⚡"
        assert p.formality == pytest.approx(0.5)
        assert p.intimacy == pytest.approx(0.3)
        assert p.humor == pytest.approx(0.0)
        assert p.directness == pytest.approx(1.0)
        assert p.conciseness == pytest.approx(1.0)
        assert p.address_form is None
        assert p.closing_style == ClosingStyle.NONE
        assert p.punctuation == Punctuation.SPACE
        assert p.person_form is None
        assert p.profanity_filter == ProfanityLevel.NONE
        assert p.base_preset == PresetStyle.MINIMAL


# ======================================================================
# StyleProfileStore CRUD 测试
# ======================================================================

class TestStoreCRUD:
    """测试 StyleProfileStore 各项操作（使用临时目录）。"""

    @pytest.fixture(autouse=True)
    def setup_teardown(self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
        """每个测试使用独立的临时存储目录。"""
        import lingxi.style.store as store_module

        self.tmp_profiles = tmp_path / "profiles.json"
        monkeypatch.setattr(store_module, "APP_DIR", tmp_path)
        monkeypatch.setattr(store_module, "PROFILES_FILE", self.tmp_profiles)

        # 重置单例以确保干净的测试状态
        StyleProfileStore.reset_instance()
        self.store = StyleProfileStore()
        yield
        StyleProfileStore.reset_instance()

    def test_singleton(self) -> None:
        """多次构造返回同一实例。"""
        s1 = StyleProfileStore()
        s2 = StyleProfileStore()
        assert s1 is s2

    def test_first_load_populates_presets(self) -> None:
        """首次加载自动填充 6 套预设。"""
        profiles = self.store.list_all()
        assert len(profiles) == 6
        presets = [p for p in profiles if p.kind == StyleProfileKind.PRESET]
        assert len(presets) == 6

    def test_add_and_get(self) -> None:
        """添加后可通过 get 获取。"""
        profile = StyleProfile(id="test-add", name="添加测试")
        self.store.add(profile)

        fetched = self.store.get("test-add")
        assert fetched is not None
        assert fetched.name == "添加测试"

    def test_get_missing(self) -> None:
        """获取不存在的 ID 返回 None。"""
        assert self.store.get("nonexistent-id") is None

    def test_update_existing(self) -> None:
        """更新已有 profile。"""
        original = StyleProfile(id="test-update", name="旧名称")
        self.store.add(original)

        updated = StyleProfile(id="test-update", name="新名称")
        self.store.update(updated)

        fetched = self.store.get("test-update")
        assert fetched is not None
        assert fetched.name == "新名称"

    def test_update_missing_raises(self) -> None:
        """更新不存在的 profile 抛出 KeyError。"""
        profile = StyleProfile(id="nonexistent-update", name="不存在")
        with pytest.raises(KeyError, match="nonexistent-update"):
            self.store.update(profile)

    def test_delete_existing(self) -> None:
        """删除已有 profile。"""
        profile = StyleProfile(id="test-delete", name="待删除")
        self.store.add(profile)

        assert self.store.delete("test-delete") is True
        assert self.store.get("test-delete") is None

    def test_delete_missing(self) -> None:
        """删除不存在的 profile 返回 False。"""
        assert self.store.delete("nonexistent-id") is False

    def test_list_all_order(self) -> None:
        """list_all 按预设优先、创建时间排序。"""
        # 清空后重新初始化（用预设填充）
        self.store.clear()
        self.store._loaded = False

        profiles = self.store.list_all()
        assert len(profiles) == 6

        # 预设在前
        kinds = [p.kind for p in profiles]
        assert all(k == StyleProfileKind.PRESET for k in kinds)

    def test_list_all_custom_after_presets(self) -> None:
        """添加自定义风格后，list_all 预设在前、自定义在后。"""
        custom = StyleProfile(id="custom-1", name="自定义", kind=StyleProfileKind.CUSTOM)
        self.store.add(custom)

        profiles = self.store.list_all()
        kinds = [p.kind for p in profiles]
        # 确保预设都在自定义前面
        first_custom_idx = next(i for i, k in enumerate(kinds) if k == StyleProfileKind.CUSTOM)
        assert first_custom_idx >= 6  # 6 个预设在前
        assert profiles[-1].id == "custom-1"

    def test_persistence_roundtrip(self) -> None:
        """profile 写入文件后重新加载数据一致。"""
        profile = StyleProfile(
            id="persist-1",
            name="持久化测试",
            formality=0.88,
            address_form=AddressForm.NIN,
            base_preset=PresetStyle.PRECISE,
        )
        self.store.add(profile)

        # 强制重新加载
        self.store._loaded = False
        self.store._profiles.clear()
        self.store.load()

        fetched = self.store.get("persist-1")
        assert fetched is not None
        assert fetched.name == "持久化测试"
        assert fetched.formality == pytest.approx(0.88)
        assert fetched.address_form == AddressForm.NIN
        assert fetched.base_preset == PresetStyle.PRECISE

    def test_save_creates_valid_json(self) -> None:
        """save 后的文件是合法 JSON 数组。"""
        profile = StyleProfile(id="json-check", name="JSON 检查")
        self.store.add(profile)

        assert self.tmp_profiles.exists()
        raw = self.tmp_profiles.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        assert isinstance(parsed, list)
        assert len(parsed) >= 1
        assert any(p["id"] == "json-check" for p in parsed)

    def test_delete_persists(self) -> None:
        """删除后 reload 确认已持久化删除。"""
        profile = StyleProfile(id="del-persist", name="删除持久化")
        self.store.add(profile)
        self.store.delete("del-persist")

        # 重新加载
        self.store._loaded = False
        self.store._profiles.clear()
        self.store.load()

        assert self.store.get("del-persist") is None
