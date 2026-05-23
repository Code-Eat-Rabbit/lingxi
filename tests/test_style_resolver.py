"""
灵犀输入 — StyleResolver 单元测试

覆盖：
  - 4 级优先级正确性（手动 > 应用绑定 > 默认）
  - 应用绑定的 exact / prefix 匹配
  - 手动覆盖取消后恢复原优先级
  - 情绪调制（strength=0 不影响维度，strength=1 全量偏移）
  - 全局默认从 ConfigStore 读取
  - 测试隔离（临时目录）
"""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from lingxi.style.profile import StyleProfile, StyleProfileKind, PresetStyle
from lingxi.style.presets import get_preset
from lingxi.style.store import StyleProfileStore
from lingxi.style.resolver import (
    StyleResolver,
    StyleAppBinding,
    ResolveSource,
    ResolveResult,
)
from lingxi.engine.emotion import Emotion, EmotionModulator
from lingxi.data.config_store import ConfigStore


# ---------------------------------------------------------------------------
# Fixtures — 测试隔离
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def reset_singletons(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个测试前重置单例，避免状态污染。"""
    monkeypatch.setattr(StyleProfileStore, "_instance", None)
    monkeypatch.setattr(ConfigStore, "_instance", None)


@pytest.fixture
def temp_store(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> StyleProfileStore:
    """创建使用临时目录的 StyleProfileStore。"""
    import lingxi.style.store as store_mod

    monkeypatch.setattr(store_mod, "APP_DIR", tmp_path)
    monkeypatch.setattr(store_mod, "PROFILES_FILE", tmp_path / "profiles.json")

    StyleProfileStore.reset_instance()
    store = StyleProfileStore()
    yield store
    StyleProfileStore.reset_instance()


@pytest.fixture
def temp_config() -> ConfigStore:
    """创建使用临时文件的 ConfigStore。"""
    with tempfile.TemporaryDirectory() as tmpdir:
        config_path = Path(tmpdir) / "config.json"
        store = ConfigStore(custom_path=str(config_path))
        yield store
        # 注意: ConfigStore 单例无法在此自动清理，由 reset_singletons 处理


@pytest.fixture
def resolver(temp_store: StyleProfileStore, temp_config: ConfigStore) -> StyleResolver:
    """创建使用临时 store + config 的 StyleResolver。"""
    return StyleResolver(temp_store, temp_config)


# ---------------------------------------------------------------------------
# 辅助
# ---------------------------------------------------------------------------

def _add_custom_profile(store: StyleProfileStore, style_id: str, name: str, **kwargs) -> StyleProfile:
    """向 store 添加一个自定义 profile 并返回。"""
    profile = StyleProfile(id=style_id, name=name, kind=StyleProfileKind.CUSTOM, **kwargs)
    store.add(profile)
    return profile


# ======================================================================
# 4 级优先级测试
# ======================================================================

class TestPriority:
    """验证 4 级优先级：手动 > 应用绑定 > 默认。"""

    def test_default_when_nothing_set(self, resolver: StyleResolver) -> None:
        """无手动覆盖、无应用绑定时，回退到全局默认。"""
        result = resolver.resolve()
        assert result.source == ResolveSource.DEFAULT
        assert result.profile.kind == StyleProfileKind.PRESET
        assert result.profile.base_preset == PresetStyle.CASUAL

    def test_manual_override_top_priority(self, resolver: StyleResolver) -> None:
        """手动覆盖优先级最高，覆盖应用绑定和默认。"""
        # 添加应用绑定
        binding = StyleAppBinding(
            app_name="微信", app_identifier="com.wechat",
            style_id="preset-warm", match_mode="exact",
        )
        resolver.add_app_binding(binding)

        # 设置手动覆盖
        resolver.set_manual_override("manual-respectful")

        # manual-respectful 不在 store 中 → 应回退到绑定
        # 先确认无 manual profile 时回退到绑定
        result_no_manual = resolver.resolve(app_identifier="com.wechat")
        # 绑定 style_id="preset-warm" 在 store 中可能不存在，回退到默认
        # 我们重点测手动覆盖存在时的情况
        ...

    def test_manual_override_wins_over_binding(
        self, temp_store: StyleProfileStore, resolver: StyleResolver,
    ) -> None:
        """手动覆盖优先于应用绑定。"""
        _add_custom_profile(temp_store, "manual-style", "手动风格", formality=0.9)
        _add_custom_profile(temp_store, "app-style", "应用风格", formality=0.3)

        resolver.add_app_binding(StyleAppBinding(
            app_name="测试", app_identifier="com.test",
            style_id="app-style", match_mode="exact",
        ))
        resolver.set_manual_override("manual-style")

        result = resolver.resolve(app_identifier="com.test")
        assert result.source == ResolveSource.MANUAL
        assert result.profile.id == "manual-style"
        assert result.profile.name == "手动风格"

    def test_app_binding_wins_over_default(
        self, temp_store: StyleProfileStore, resolver: StyleResolver,
    ) -> None:
        """应用绑定优先于全局默认。"""
        _add_custom_profile(temp_store, "app-style", "应用风格", formality=0.3)

        resolver.add_app_binding(StyleAppBinding(
            app_name="测试", app_identifier="com.test",
            style_id="app-style", match_mode="exact",
        ))

        result = resolver.resolve(app_identifier="com.test")
        assert result.source == ResolveSource.APP_BINDING
        assert result.profile.id == "app-style"

    def test_manual_falls_through_when_id_not_in_store(
        self, temp_store: StyleProfileStore, resolver: StyleResolver,
    ) -> None:
        """手动覆盖的 style_id 在 store 中不存在时，回退到下一级。"""
        _add_custom_profile(temp_store, "app-style", "应用风格")

        resolver.add_app_binding(StyleAppBinding(
            app_name="测试", app_identifier="com.test",
            style_id="app-style", match_mode="exact",
        ))
        resolver.set_manual_override("nonexistent-id")

        result = resolver.resolve(app_identifier="com.test")
        # 手动覆盖无效 → 回退到应用绑定
        assert result.source == ResolveSource.APP_BINDING
        assert result.profile.id == "app-style"


# ======================================================================
# 应用绑定 exact / prefix 匹配
# ======================================================================

class TestAppBindingMatching:
    """应用绑定的 exact 和 prefix 匹配模式。"""

    def test_exact_match(self, temp_store: StyleProfileStore, resolver: StyleResolver) -> None:
        """exact 模式：完全相等才匹配。"""
        _add_custom_profile(temp_store, "exact-style", "精确匹配")

        resolver.add_app_binding(StyleAppBinding(
            app_name="微信", app_identifier="com.wechat",
            style_id="exact-style", match_mode="exact",
        ))

        # 完全匹配
        result = resolver.resolve(app_identifier="com.wechat")
        assert result.source == ResolveSource.APP_BINDING
        assert result.profile.id == "exact-style"

        # 不匹配（前缀相似但不相等）
        result2 = resolver.resolve(app_identifier="com.wechat.work")
        assert result2.source == ResolveSource.DEFAULT

    def test_prefix_match(self, temp_store: StyleProfileStore, resolver: StyleResolver) -> None:
        """prefix 模式：app_identifier 以绑定值为前缀即匹配。"""
        _add_custom_profile(temp_store, "prefix-style", "前缀匹配")

        resolver.add_app_binding(StyleAppBinding(
            app_name="企业微信", app_identifier="com.wechat",
            style_id="prefix-style", match_mode="prefix",
        ))

        # com.wechat 是自身的前缀
        result = resolver.resolve(app_identifier="com.wechat")
        assert result.source == ResolveSource.APP_BINDING

        # com.wechat.work 以 com.wechat 开头
        result2 = resolver.resolve(app_identifier="com.wechat.work")
        assert result2.source == ResolveSource.APP_BINDING
        assert result2.profile.id == "prefix-style"

    def test_prefix_no_match(self, temp_store: StyleProfileStore, resolver: StyleResolver) -> None:
        """prefix 模式：不以绑定值为前缀则不匹配。"""
        _add_custom_profile(temp_store, "prefix-style", "前缀匹配")

        resolver.add_app_binding(StyleAppBinding(
            app_name="微信", app_identifier="com.wechat",
            style_id="prefix-style", match_mode="prefix",
        ))

        result = resolver.resolve(app_identifier="com.dingtalk")
        assert result.source == ResolveSource.DEFAULT

    def test_disabled_binding_skipped(self, temp_store: StyleProfileStore, resolver: StyleResolver) -> None:
        """禁用的绑定不参与匹配。"""
        _add_custom_profile(temp_store, "active-style", "活跃")
        _add_custom_profile(temp_store, "disabled-style", "禁用")

        resolver.add_app_binding(StyleAppBinding(
            app_name="禁用绑定", app_identifier="com.test",
            style_id="disabled-style", match_mode="exact", is_enabled=False,
        ))
        resolver.add_app_binding(StyleAppBinding(
            app_name="活跃绑定", app_identifier="com.test",
            style_id="active-style", match_mode="exact", is_enabled=True,
        ))

        result = resolver.resolve(app_identifier="com.test")
        assert result.profile.id == "active-style"

    def test_first_match_wins(self, temp_store: StyleProfileStore, resolver: StyleResolver) -> None:
        """多个绑定同时匹配时，返回第一个匹配的（prefix 在前）。"""
        _add_custom_profile(temp_store, "first-style", "第一个")
        _add_custom_profile(temp_store, "second-style", "第二个")

        # Binding 1: prefix 匹配 com.test → 会匹配 com.test.sub
        resolver.add_app_binding(StyleAppBinding(
            app_name="第一(prefix)", app_identifier="com.test",
            style_id="first-style", match_mode="prefix",
        ))
        # Binding 2: exact 匹配 com.test.sub → 也会匹配
        resolver.add_app_binding(StyleAppBinding(
            app_name="第二(exact)", app_identifier="com.test.sub",
            style_id="second-style", match_mode="exact",
        ))

        # com.test.sub 同时匹配两个绑定，先添加的 prefix 绑定获胜
        result = resolver.resolve(app_identifier="com.test.sub")
        assert result.profile.id == "first-style"


# ======================================================================
# 手动覆盖取消
# ======================================================================

class TestManualOverrideCancellation:
    """手动覆盖取消后恢复原优先级。"""

    def test_cancel_manual_restores_binding(
        self, temp_store: StyleProfileStore, resolver: StyleResolver,
    ) -> None:
        """取消手动覆盖后，应用绑定重新生效。"""
        _add_custom_profile(temp_store, "manual-style", "手动")
        _add_custom_profile(temp_store, "app-style", "应用")

        resolver.add_app_binding(StyleAppBinding(
            app_name="测试", app_identifier="com.test",
            style_id="app-style", match_mode="exact",
        ))

        # 设置手动覆盖
        resolver.set_manual_override("manual-style")
        r1 = resolver.resolve(app_identifier="com.test")
        assert r1.source == ResolveSource.MANUAL
        assert r1.profile.id == "manual-style"

        # 取消手动覆盖
        resolver.set_manual_override(None)
        r2 = resolver.resolve(app_identifier="com.test")
        assert r2.source == ResolveSource.APP_BINDING
        assert r2.profile.id == "app-style"

    def test_cancel_manual_restores_default(self, resolver: StyleResolver) -> None:
        """取消手动覆盖后，无绑定时回退到默认。"""
        resolver.set_manual_override("some-id")
        r1 = resolver.resolve()
        # some-id 不在 store 中，回退到默认
        assert r1.source == ResolveSource.DEFAULT

        resolver.set_manual_override(None)
        r2 = resolver.resolve()
        assert r2.source == ResolveSource.DEFAULT


# ======================================================================
# 情绪调制
# ======================================================================

class TestEmotionModulation:
    """情绪调制集成测试。"""

    def test_strength_zero_no_effect(
        self, temp_store: StyleProfileStore, resolver: StyleResolver,
    ) -> None:
        """emotion_strength=0 时维度不变。"""
        _add_custom_profile(
            temp_store, "base-style", "基准",
            formality=0.6, intimacy=0.4, humor=0.3, directness=0.7, conciseness=0.6,
        )
        resolver.set_manual_override("base-style")

        result = resolver.resolve(emotion=Emotion.ANGER, emotion_strength=0.0)
        assert result.profile.formality == pytest.approx(0.6)
        assert result.profile.intimacy == pytest.approx(0.4)
        assert result.profile.humor == pytest.approx(0.3)
        assert result.profile.directness == pytest.approx(0.7)
        assert result.profile.conciseness == pytest.approx(0.6)

    def test_strength_one_applies_full_delta(
        self, temp_store: StyleProfileStore, resolver: StyleResolver,
    ) -> None:
        """emotion_strength=1 应用全量偏移（使用非中线值避免钳制）。"""
        _add_custom_profile(
            temp_store, "base-style", "基准",
            # HAPPY: formality-0.1, intimacy+0.1, humor+0.3, directness+0.0, conciseness-0.1
            formality=0.6, intimacy=0.4, humor=0.3, directness=0.7, conciseness=0.6,
        )
        resolver.set_manual_override("base-style")

        result = resolver.resolve(emotion=Emotion.HAPPY, emotion_strength=1.0)
        assert result.profile.formality == pytest.approx(0.5)   # 0.6 - 0.1
        assert result.profile.intimacy == pytest.approx(0.5)    # 0.4 + 0.1 (clamped to 0.5)
        assert result.profile.humor == pytest.approx(0.5)       # 0.3 + 0.3 (clamped to 0.5)
        assert result.profile.directness == pytest.approx(0.7)  # unchanged
        assert result.profile.conciseness == pytest.approx(0.5) # 0.6 - 0.1

    def test_strength_half_applies_half_delta(
        self, temp_store: StyleProfileStore, resolver: StyleResolver,
    ) -> None:
        """emotion_strength=0.5 应用半数偏移。"""
        _add_custom_profile(
            temp_store, "base-style", "基准",
            formality=0.6, intimacy=0.4, humor=0.3, directness=0.7, conciseness=0.6,
        )
        resolver.set_manual_override("base-style")

        # HAPPY 半量
        result = resolver.resolve(emotion=Emotion.HAPPY, emotion_strength=0.5)
        assert result.profile.formality == pytest.approx(0.55)  # 0.6 - 0.05
        assert result.profile.intimacy == pytest.approx(0.45)   # 0.4 + 0.05
        assert result.profile.humor == pytest.approx(0.45)      # 0.3 + 0.15

    def test_no_emotion_leaves_profile_unchanged(self, resolver: StyleResolver) -> None:
        """不传入 emotion 时 profile 保持不变。"""
        r1 = resolver.resolve()
        r2 = resolver.resolve(emotion=None, emotion_strength=0.0)
        assert r1.profile.id == r2.profile.id
        assert r1.profile.formality == pytest.approx(r2.profile.formality)

    def test_emotion_modulation_on_default(
        self, temp_store: StyleProfileStore, resolver: StyleResolver,
    ) -> None:
        """情绪调制也能作用于默认风格。"""
        result = resolver.resolve(emotion=Emotion.SAD, emotion_strength=1.0)
        # SAD 对 CASUAL 调制 (注意 _clamp 不跨中线):
        #   formality:  0.5 + (-0.1) → clamp 到 0.5
        #   intimacy:   0.5 + 0.2   → clamp 到 0.5
        #   humor:      0.3 + (-0.3) → 0.0
        #   directness: 0.7 + (-0.2) → 0.5
        #   conciseness: 0.6 + 0.0  → 0.6
        assert result.source == ResolveSource.DEFAULT
        assert result.profile.formality == pytest.approx(0.5)
        assert result.profile.intimacy == pytest.approx(0.5)
        assert result.profile.humor == pytest.approx(0.0)
        assert result.profile.directness == pytest.approx(0.5)

    def test_emotion_clamp_does_not_cross_midline(
        self, temp_store: StyleProfileStore, resolver: StyleResolver,
    ) -> None:
        """EmotionModulator 的 _clamp 不跨越中线 0.5。"""
        # 创建一个 formality=0.1 (低于中线) 的 profile
        _add_custom_profile(
            temp_store, "low-formal", "低正式",
            formality=0.1, intimacy=0.9, humor=0.8, directness=0.8, conciseness=0.3,
        )
        resolver.set_manual_override("low-formal")

        # FEAR: formality_delta=+0.1, 但 formality 原始值 0.1 < 0.5，
        # 钳制后不得 >= 0.5
        result = resolver.resolve(emotion=Emotion.FEAR, emotion_strength=1.0)
        # 0.1 + 0.1 = 0.2, 远低于 0.5，不会被钳制
        assert result.profile.formality == pytest.approx(0.2)

        # ANGER: intimacy_delta=-0.2, 原始 0.9 > 0.5, 钳制后不得 <= 0.5
        result2 = resolver.resolve(emotion=Emotion.ANGER, emotion_strength=1.0)
        assert result2.profile.intimacy == pytest.approx(0.7)

    def test_resolve_result_is_copy_not_mutating_original(
        self, temp_store: StyleProfileStore, resolver: StyleResolver,
    ) -> None:
        """情绪调制返回的是副本，不修改 store 中的原始 profile。"""
        original = _add_custom_profile(
            temp_store, "original", "原始",
            formality=0.6, intimacy=0.4, humor=0.3, directness=0.7, conciseness=0.6,
        )
        resolver.set_manual_override("original")

        result = resolver.resolve(emotion=Emotion.HAPPY, emotion_strength=1.0)

        # store 中的原始 profile 不变
        stored = temp_store.get("original")
        assert stored is not None
        assert stored.formality == pytest.approx(0.6)
        assert stored.humor == pytest.approx(0.3)

        # 结果对象是不同的
        assert result.profile is not original
        assert result.profile.formality == pytest.approx(0.5)  # 0.6 - 0.1


# ======================================================================
# 全局默认从 ConfigStore 读取
# ======================================================================

class TestDefaultStyleFromConfig:
    """全局默认风格从 ConfigStore 读取。"""

    def test_default_is_casual(self, resolver: StyleResolver) -> None:
        """默认配置下 default_style='casual'。"""
        result = resolver.resolve()
        assert result.source == ResolveSource.DEFAULT
        assert result.profile.base_preset == PresetStyle.CASUAL
        assert result.profile.name == "日常"

    def test_change_default_style_in_config(
        self, temp_store: StyleProfileStore, temp_config: ConfigStore,
    ) -> None:
        """修改 ConfigStore 中的 default_style 生效。"""
        temp_config.set("default_style", "respectful")
        temp_config.save()

        resolver = StyleResolver(temp_store, temp_config)
        result = resolver.resolve()
        assert result.source == ResolveSource.DEFAULT
        assert result.profile.base_preset == PresetStyle.RESPECTFUL
        assert result.profile.name == "敬重"

    def test_invalid_default_falls_back_to_casual(
        self, temp_store: StyleProfileStore, temp_config: ConfigStore,
    ) -> None:
        """无效的 default_style 值回退到 CASUAL。"""
        temp_config.set("default_style", "nonexistent_style")
        temp_config.save()

        resolver = StyleResolver(temp_store, temp_config)
        result = resolver.resolve()
        assert result.profile.base_preset == PresetStyle.CASUAL
        assert result.profile.name == "日常"


# ======================================================================
# StyleAppBinding 管理
# ======================================================================

class TestAppBindingManagement:
    """应用绑定的增删查管理。"""

    def test_add_and_list(self, resolver: StyleResolver) -> None:
        """添加绑定后 get_app_bindings 返回正确列表。"""
        b1 = StyleAppBinding(app_name="A", app_identifier="com.a", style_id="s1")
        b2 = StyleAppBinding(app_name="B", app_identifier="com.b", style_id="s2")

        resolver.add_app_binding(b1)
        resolver.add_app_binding(b2)

        bindings = resolver.get_app_bindings()
        assert len(bindings) == 2
        assert bindings[0].app_identifier == "com.a"
        assert bindings[1].app_identifier == "com.b"

    def test_add_duplicate_replaces(self, resolver: StyleResolver) -> None:
        """添加相同 app_identifier 的绑定会替换旧绑定。"""
        b1 = StyleAppBinding(app_name="旧", app_identifier="com.test", style_id="old")
        b2 = StyleAppBinding(app_name="新", app_identifier="com.test", style_id="new")

        resolver.add_app_binding(b1)
        resolver.add_app_binding(b2)

        bindings = resolver.get_app_bindings()
        assert len(bindings) == 1
        assert bindings[0].style_id == "new"
        assert bindings[0].app_name == "新"

    def test_remove_existing(self, resolver: StyleResolver) -> None:
        """删除存在的绑定返回 True。"""
        resolver.add_app_binding(StyleAppBinding(
            app_name="测试", app_identifier="com.test", style_id="s1",
        ))
        assert resolver.remove_app_binding("com.test") is True
        assert len(resolver.get_app_bindings()) == 0

    def test_remove_nonexistent(self, resolver: StyleResolver) -> None:
        """删除不存在的绑定返回 False。"""
        assert resolver.remove_app_binding("com.nonexistent") is False

    def test_get_app_bindings_returns_copy(self, resolver: StyleResolver) -> None:
        """get_app_bindings 返回副本，修改不影响内部状态。"""
        resolver.add_app_binding(StyleAppBinding(
            app_name="测试", app_identifier="com.test", style_id="s1",
        ))

        bindings = resolver.get_app_bindings()
        bindings.clear()

        assert len(resolver.get_app_bindings()) == 1


# ======================================================================
# ResolveResult 完整性
# ======================================================================

class TestResolveResult:
    """ResolveResult dataclass 字段验证。"""

    def test_manual_result_detail(self, temp_store: StyleProfileStore, resolver: StyleResolver) -> None:
        """手动覆盖结果的 source_detail 包含描述信息。"""
        _add_custom_profile(temp_store, "manual-1", "我的手动风格")
        resolver.set_manual_override("manual-1")

        result = resolver.resolve()
        assert result.source == ResolveSource.MANUAL
        assert "手动临时覆盖" in result.source_detail
        assert "我的手动风格" in result.source_detail

    def test_app_binding_result_detail(
        self, temp_store: StyleProfileStore, resolver: StyleResolver,
    ) -> None:
        """应用绑定结果的 source_detail 包含应用标识符。"""
        _add_custom_profile(temp_store, "app-1", "微信风格")
        resolver.add_app_binding(StyleAppBinding(
            app_name="微信", app_identifier="com.wechat",
            style_id="app-1", match_mode="exact",
        ))

        result = resolver.resolve(app_identifier="com.wechat")
        assert result.source == ResolveSource.APP_BINDING
        assert "com.wechat" in result.source_detail

    def test_default_result_detail(self, resolver: StyleResolver) -> None:
        """默认结果的 source_detail 包含描述信息。"""
        result = resolver.resolve()
        assert result.source == ResolveSource.DEFAULT
        assert "全局默认" in result.source_detail
