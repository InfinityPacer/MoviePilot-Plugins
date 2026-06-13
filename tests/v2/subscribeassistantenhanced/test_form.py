"""配置入口契约单测：Vue 渲染模式 + 默认 model 覆盖 + 字段元数据。"""
import re
from pathlib import Path

from subscribeassistantenhanced.form import HINTS, LABELS
from subscribeassistantenhanced.form.components import field_for, multi_select_field
from subscribeassistantenhanced.shared.config import PluginConfig


class TestGetForm:
    """插件入口配置页契约。"""

    def test_plugin_uses_vue_render_mode(self):
        """配置页交给 Vue 联邦资源渲染，后端只声明资源目录。"""
        from subscribeassistantenhanced import SubscribeAssistantEnhanced

        assert SubscribeAssistantEnhanced().get_render_mode() == ("vue", "dist/assets")

    def test_vue_config_remote_entry_exists_under_render_assets(self):
        """联邦配置页入口文件必须落在 render mode 声明的产物目录下。"""
        from subscribeassistantenhanced import SubscribeAssistantEnhanced

        mode, assets_path = SubscribeAssistantEnhanced().get_render_mode()
        plugin_root = Path(__file__).resolve().parents[3] / "plugins.v2" / "subscribeassistantenhanced"

        assert mode == "vue"
        assert (plugin_root / assets_path / "remoteEntry.js").is_file()

    def test_plugin_get_form_returns_vue_model_defaults(self):
        """Vue 模式下后端不再返回 Vuetify schema，但仍提供完整默认 model。"""
        from subscribeassistantenhanced import SubscribeAssistantEnhanced

        conf, model = SubscribeAssistantEnhanced().get_form()

        assert conf is None
        assert isinstance(model, dict)
        assert model == dict(PluginConfig.defaults())
        assert model["completion_guard_mode"] == "balanced"
        assert model["verify_retention_days"] == 180
        for key in PluginConfig({}).declared_keys():
            assert key in model, f"表单 model 缺少配置键 {key}"


def test_int_default_renders_number_field():
    """字段 helper 按默认值类型选择数字输入控件，避免配置类型提示漂移。"""
    col = field_for("download_timeout_minutes", "下载超时", 180)
    assert col["content"][0]["props"]["type"] == "number"


def test_multi_select_field_renders_vselect_multiple():
    """多选字段 helper 保持 chips + multiple 组合，兼容旧 schema 生成路径。"""
    col = multi_select_field(
        "no_download_actions",
        "无下载处理策略",
        [{"title": "暂停剧集订阅", "value": "pause_tv"}],
    )
    sel = col["content"][0]
    assert sel["component"] == "VSelect"
    assert sel["props"]["multiple"] is True
    assert sel["props"]["chips"] is True
    assert sel["props"]["model"] == "no_download_actions"


def test_completion_signal_hints_explain_behavior_and_scope():
    """完结信号说明使用短中文句；允许待定（P）等已解释的状态码。"""
    keys = (
        "completion_guard_mode",
        "volatility_enabled",
        "volatility_window_days",
        "cadence_enabled",
        "cadence_multiplier",
        "cadence_min_window_days",
        "cadence_min_episodes",
        "season_cooldown_days",
        "verify_enabled",
        "verify_interval_hours",
        "verify_retention_days",
        "timeout_release_enabled",
        "timeout_release_days",
        "timeout_cadence_acceleration",
    )
    for key in keys:
        hint = HINTS[key]
        assert len(hint) <= 32, f"{key} hint 过长"
        assert "；" not in hint and ";" not in hint
        readable_hint = hint.replace("待定（P）", "待定")
        assert not re.search(r"[A-Za-z_]", readable_hint), f"{key} hint 含未解释英文"

    assert "总集数" in HINTS["volatility_enabled"]
    assert "不会直接判定完结" in HINTS["cadence_enabled"]
    assert "增加" in HINTS["verify_enabled"]
    assert "重新计时" in HINTS["timeout_release_enabled"]


def test_completion_labels_use_concise_names_without_enable_prefix():
    """完结信号配置使用简洁业务名称，不重复“启用”。"""
    assert LABELS["completion_guard_mode"] == "完结守卫模式"
    assert LABELS["volatility_enabled"] == "变更速率信号"
    assert LABELS["cadence_enabled"] == "播出节奏信号"
    assert LABELS["verify_enabled"] == "自动纠错"
    assert LABELS["verify_interval_hours"] == "自动纠错间隔（小时）"
    assert LABELS["timeout_release_enabled"] == "待定超时释放"
