"""form 配置表单单测：聚合契约 + model 键覆盖（不漂移）+ 控件类型。"""
import re

from subscribeassistantenhanced.form import HINTS, LABELS, MULTI_ITEMS, SELECT_ITEMS, build_form
from subscribeassistantenhanced.form.components import field_for
from subscribeassistantenhanced.shared.config import PluginConfig


def _controls_with_model(node):
    """递归提取带 model 的表单控件，不依赖具体 Vuetify 嵌套层级。"""
    controls = []
    if isinstance(node, dict):
        props = node.get("props", {})
        if props.get("model") or props.get("modelvalue"):
            controls.append(node)
        for child in node.get("content", []):
            controls.extend(_controls_with_model(child))
    elif isinstance(node, list):
        for child in node:
            controls.extend(_controls_with_model(child))
    return controls


def _component_nodes(node):
    """递归提取动态表单渲染节点；FormRender 要求 content 子节点可解析 component。"""
    nodes = []
    if isinstance(node, dict):
        nodes.append(node)
        for child in node.get("content", []):
            nodes.extend(_component_nodes(child))
        for slot in node.get("slots", {}).values():
            nodes.extend(_component_nodes(slot))
    elif isinstance(node, list):
        for child in node:
            nodes.extend(_component_nodes(child))
    return nodes


def _tab_titles(conf):
    """返回表单页签标题，避免断言依赖 Vuetify 嵌套实现细节。"""
    tabs_node = next(node for node in conf if node.get("component") == "VTabs")
    return [tab["text"] for tab in tabs_node["content"]]


def _tab_content(conf, title):
    """按页签标题读取对应窗口内容，保持布局测试和页签顺序解耦。"""
    titles = _tab_titles(conf)
    index = titles.index(title)
    window = next(node for node in conf if node.get("component") == "VWindow")
    return window["content"][index]["content"]


def _tab_models(conf, title):
    """提取指定页签内所有绑定 model 的字段键。"""
    return [
        field["props"].get("model") or field["props"].get("modelvalue")
        for field in _controls_with_model(_tab_content(conf, title))
    ]


class TestBuildForm:
    """build_form 聚合契约。"""

    def test_returns_conf_and_model(self):
        conf, model = build_form()
        assert isinstance(conf, list) and conf
        assert isinstance(model, dict)

    def test_model_covers_all_config_keys(self):
        """model 默认值必须覆盖 PluginConfig 所有键，否则 v-show 联动因缺键异常。"""
        _conf, model = build_form()
        for key in PluginConfig({}).declared_keys():
            assert key in model, f"表单 model 缺少配置键 {key}"

    def test_seven_tabs(self):
        """配置表单使用 7 个 Tab，诊断和补搜统一归入订阅补全。"""
        conf, _model = build_form()
        assert conf[3]["component"] == "VTabs"
        assert len(conf[3]["content"]) == 7
        assert _tab_titles(conf) == [
            "订阅清理",
            "订阅待定",
            "订阅暂停",
            "订阅补全",
            "订阅洗版",
            "完结信号",
            "识别增强",
        ]

    def test_beta_alert_precedes_form_controls(self):
        """BETA 风险提示固定显示在开关、周期和分页配置之前。"""
        conf, _model = build_form()
        assert conf[0]["component"] == "VRow"
        alert = conf[0]["content"][0]["content"][0]
        assert alert["component"] == "VAlert"
        assert "BETA 版本提示" in alert["props"]["text"]

    def test_completion_guard_mode_renders_select(self):
        conf, _model = build_form()
        fields = _controls_with_model(conf[4])
        control = next(field for field in fields
                       if field["props"].get("model") == "completion_guard_mode")
        assert control["component"] == "VSelect"
        assert control["props"]["items"] == [
            {"title": "关闭", "value": "off"},
            {"title": "严格", "value": "strict"},
            {"title": "平衡", "value": "balanced"},
            {"title": "宽松", "value": "loose"},
        ]

    def test_int_default_renders_number_field(self):
        col = field_for("download_timeout_minutes", "下载超时", 180)
        assert col["content"][0]["props"]["type"] == "number"

    def test_removed_download_pause_action_is_not_rendered(self):
        """下载超时删种后不暂停订阅，因此不再渲染下载暂停超期动作。"""
        conf, _model = build_form()
        fields = _controls_with_model(conf[4])
        models = {field["props"].get("model") for field in fields}
        assert "download_pause_max_days" not in models
        assert "download_pause_expire_action" not in models

    def test_only_one_verify_interval_is_exposed(self):
        """完成后验证只保留小时级周期，配置与调度不再存在重复口径。"""
        _conf, model = build_form()
        assert "verify_interval_hours" in model
        assert "verify_check_interval_minutes" not in model

    def test_auto_pause_users_is_editable_text_field(self):
        """用户名自动暂停名单须作为可编辑文本框出现在表单，否则该能力用户无法启用。
        conf[4] 为 VWindow；每个 VWindowItem.content 为若干 VRow，VRow.content 为 VCol 列表。
        """
        conf, _model = build_form()
        fields = _controls_with_model(conf[4])
        field = next((f for f in fields if f["props"].get("model") == "auto_pause_users"), None)
        assert field is not None, "表单暂停 Tab 缺少 auto_pause_users 可编辑项"
        assert field["component"] == "VTextField"

    def test_all_render_nodes_have_component(self):
        """表单渲染器会递归 resolveComponent，富文本 content 不能使用裸文本 dict。"""
        conf, _model = build_form()
        for node in _component_nodes(conf):
            assert node.get("component"), f"表单节点缺少 component: {node}"


class TestGetForm:
    """插件入口 get_form 返回完整表单。"""

    def test_plugin_get_form_returns_full_form(self):
        from subscribeassistantenhanced import SubscribeAssistantEnhanced
        conf, model = SubscribeAssistantEnhanced().get_form()
        assert conf and isinstance(model, dict)
        assert model["completion_guard_mode"] == "balanced"
        assert model["auto_check_interval_minutes"] == 30
        assert model["site_completion_evidence_enabled"] is True
        assert model["verify_retention_days"] == 180
        assert "completion_guard_enabled" not in model


def test_multi_select_field_renders_vselect_multiple():
    from subscribeassistantenhanced.form.components import multi_select_field
    col = multi_select_field("no_download_actions", "无下载处理策略",
                             [{"title": "暂停剧集订阅", "value": "pause_tv"}])
    sel = col["content"][0]
    assert sel["component"] == "VSelect"
    assert sel["props"]["multiple"] is True
    assert sel["props"]["chips"] is True
    assert sel["props"]["model"] == "no_download_actions"


def test_tabs_renders_vtabs_and_vwindow():
    from subscribeassistantenhanced.form.components import tabs
    out = tabs(["A", "B"], [{"component": "VRow"}, {"component": "VRow"}])
    assert out[0]["component"] == "VTabs"
    assert out[1]["component"] == "VWindow"
    assert out[1]["props"]["style"]["padding-top"] == "24px"
    assert len(out[0]["content"]) == 2           # 两个 VTab
    assert out[0]["content"][0]["text"] == "A"
    assert out[1]["content"][0]["component"] == "VWindowItem"


def test_form_has_top_switches_periods_and_seven_tabs():
    """配置布局：顶部开关行 + 公共周期行 + 7 个 Tab；关键新参数可编辑；多选控件存在。"""
    import json
    conf, model = build_form()
    flat = json.dumps(conf, ensure_ascii=False)
    # 顶部 4 开关
    for key in ("enabled", "notify", "reset_task", "onlyonce"):
        assert f'"{key}"' in flat
    # 4 个公共周期（下载/元数据/通用巡检下拉 + 洗版 cron）
    for key in ("download_check_interval_minutes", "meta_check_interval_hours",
                "auto_check_interval_minutes", "best_version_cron"):
        assert f'"{key}"' in flat
    # 7 个 Tab + VTabs/VWindow 绑定
    assert flat.count('"VTab"') == 7
    assert '"_tab"' in flat
    # 关键新参数可编辑
    for key in ("best_version_type", "no_download_actions", "movie_air_pause_days",
                "best_version_episode_to_full", "best_version_movie_remaining_days",
                "best_version_tv_remaining_days",
                "manual_delete_listen", "subscription_cleanup_history_type",
                "subscription_cleanup_history_scenes"):
        assert f'"{key}"' in flat
    assert '"best_version_remaining_days"' not in flat
    assert '"pending_default_total_episodes"' not in flat
    assert '"best_version_clear_history_type"' not in flat
    assert "best_version_clear_history_type" not in model
    # 多选控件
    assert '"multiple": true' in flat or '"multiple":true' in flat


def test_recognition_guard_tab_and_controls_are_rendered():
    import json
    conf, model = build_form()
    flat = json.dumps(conf, ensure_ascii=False)

    assert flat.count('"VTab"') == 7
    assert "识别增强" in flat
    for key in (
        "recognition_guard_mode",
        "recognition_guard_notify",
        "recognition_guard_notify_interval",
        "recognition_guard_tmdb_recheck_mode",
        "recognition_guard_cache_maxsize",
        "recognition_guard_custom_config",
    ):
        assert key in model
        assert f'"{key}"' in flat
    for key in (
        "recognition_guard_missing_year_policy",
        "recognition_guard_target_mode",
        "recognition_guard_keyword_config",
        "recognition_guard_enabled",
        "recognition_guard_active",
    ):
        assert key not in model
        assert f'"{key}"' not in flat


def test_recognition_guard_custom_config_uses_yaml_ace_editor():
    conf, _model = build_form()
    window = next(node for node in conf if node.get("component") == "VWindow")
    fields = _controls_with_model(window)
    control = next(field for field in fields
                   if field["props"].get("modelvalue") == "recognition_guard_custom_config")

    assert control["component"] == "VAceEditor"
    assert control["props"]["modelvalue"] == "recognition_guard_custom_config"
    assert control["props"]["lang"] == "yaml"
    assert control["props"]["theme"] == "monokai"
    assert control["props"]["style"] == "height: 30rem"


def test_recognition_guard_mode_select_values():
    conf, _model = build_form()
    window = next(node for node in conf if node.get("component") == "VWindow")
    fields = _controls_with_model(window)
    control = next(field for field in fields
                   if field["props"].get("model") == "recognition_guard_mode")

    assert control["component"] == "VSelect"
    assert control["props"]["items"] == [
        {"title": "关闭", "value": "off"},
        {"title": "审计", "value": "audit"},
        {"title": "宽松", "value": "loose"},
        {"title": "平衡", "value": "balanced"},
        {"title": "严格", "value": "strict"},
    ]


def test_recognition_guard_notify_and_recheck_select_values():
    conf, _model = build_form()
    window = next(node for node in conf if node.get("component") == "VWindow")
    fields = _controls_with_model(window)
    controls = {field["props"].get("model"): field for field in fields if field["props"].get("model")}

    assert controls["recognition_guard_notify"]["component"] == "VSelect"
    assert controls["recognition_guard_notify"]["props"]["items"] == [
        {"title": "关闭", "value": "off"},
        {"title": "摘要", "value": "summary"},
        {"title": "明细", "value": "detail"},
        {"title": "全部", "value": "all"},
    ]
    assert controls["recognition_guard_tmdb_recheck_mode"]["component"] == "VSelect"
    assert controls["recognition_guard_tmdb_recheck_mode"]["props"]["items"] == [
        {"title": "关闭", "value": "off"},
        {"title": "全部", "value": "all"},
        {"title": "严格", "value": "strict"},
        {"title": "平衡和严格", "value": "balanced_strict"},
    ]


def test_form_model_covers_all_keys_after_restructure():
    """重排后 model 依然覆盖全部 PluginConfig 键，不允许因重排丢失键。"""
    from subscribeassistantenhanced.shared.config import PluginConfig
    _conf, model = build_form()
    for key in PluginConfig({}).declared_keys():
        assert key in model, f"model 缺少 {key}"


def test_periods_use_dropdown_and_cron():
    """公共周期控件类型：分钟/小时周期为下拉，洗版为 cron 输入框。"""
    conf, _model = build_form()
    period_ctrls = {col["content"][0]["props"]["model"]: col["content"][0]["component"]
                    for col in conf[2]["content"]}
    assert period_ctrls["download_check_interval_minutes"] == "VSelect"
    assert period_ctrls["meta_check_interval_hours"] == "VSelect"
    assert period_ctrls["auto_check_interval_minutes"] == "VSelect"
    assert period_ctrls["best_version_cron"] == "VCronField"


def test_auto_check_interval_lives_in_public_period_row_only():
    """通用巡检周期属于公共周期，不混在「订阅清理」业务页里。"""
    import json
    conf, _model = build_form()
    period_models = [col["content"][0]["props"]["model"] for col in conf[2]["content"]]
    seed_tab = conf[4]["content"][0]["content"]

    assert "auto_check_interval_minutes" in period_models
    assert '"auto_check_interval_minutes"' not in json.dumps(seed_tab, ensure_ascii=False)


def test_pending_numeric_fields_share_one_row_after_internal_total_removed():
    """订阅待定只暴露开播窗口和低集数阈值，内部总集数兜底不再作为表单项。"""
    conf, _model = build_form()
    pending_rows = conf[4]["content"][1]["content"]
    numeric_cols = pending_rows[1]["content"]

    assert [col["content"][0]["props"]["model"] for col in numeric_cols] == [
        "auto_tv_pending_days",
        "auto_tv_pending_episodes",
    ]
    assert [col["props"]["md"] for col in numeric_cols] == [6, 6]


def test_pending_switches_share_one_row_with_three_equal_columns():
    """订阅待定前三个开关应在桌面宽度同一行显示，避免表单视觉上被拆成两段。"""
    conf, _model = build_form()
    pending_rows = conf[4]["content"][1]["content"]
    switch_cols = pending_rows[0]["content"]

    assert [col["content"][0]["props"]["model"] for col in switch_cols] == [
        "pending_download_enabled",
        "pending_enhanced_enabled",
        "pending_use_volatility",
    ]
    assert [col["props"]["md"] for col in switch_cols] == [4, 4, 4]


def test_best_version_tab_uses_type_without_extra_flow_switch():
    """洗版 Tab 以枚举字段作为用户入口，不再暴露冗余布尔开关。"""
    import json
    conf, model = build_form()
    best_tab = _tab_content(conf, "订阅洗版")
    flat = json.dumps(best_tab, ensure_ascii=False)

    assert '"best_version_type"' in flat
    assert '"best_version_clear_history_type"' not in flat
    assert "best_version_clear_history_type" not in model
    for key in ("best_version_enabled", "auto_best_version_on_complete",
                "best_version_clear_history_enabled"):
        assert key not in model
        assert f'"{key}"' not in flat


def test_best_version_type_and_remaining_days_use_third_width_columns():
    """订阅洗版首行展示洗版类型、电影洗版时限和剧集洗版时限。"""
    conf, _model = build_form()
    best_tab = _tab_content(conf, "订阅洗版")
    first_row_cols = best_tab[0]["content"]

    assert [col["content"][0]["props"]["model"] for col in first_row_cols] == [
        "best_version_type",
        "best_version_movie_remaining_days",
        "best_version_tv_remaining_days",
    ]
    assert [col["props"]["md"] for col in first_row_cols] == [4, 4, 4]


def test_best_version_remaining_days_labels_are_split_by_media_type():
    """电影和剧集洗版时限使用独立配置项，旧统一字段不再暴露。"""
    assert "best_version_remaining_days" not in LABELS
    assert "best_version_remaining_days" not in HINTS
    assert LABELS["best_version_movie_remaining_days"] == "电影洗版时限（天）"
    assert LABELS["best_version_tv_remaining_days"] == "剧集洗版时限（天）"
    assert "电影洗版订阅" in HINTS["best_version_movie_remaining_days"]
    assert "剧集洗版订阅达到指定天数后自动终止" in HINTS["best_version_tv_remaining_days"]


def test_completion_tab_contains_paused_probe_and_site_total_fields():
    """订阅补全只承载暂停补搜和站点集数探测。"""
    conf, model = build_form()
    completion_tab = _tab_content(conf, "订阅补全")
    completion_models = _tab_models(conf, "订阅补全")
    pause_models = _tab_models(conf, "订阅暂停")
    guard_models = _tab_models(conf, "完结信号")

    for key in (
        "paused_probe_reasons",
        "paused_probe_min_pause_days",
        "paused_probe_interval_hours",
        "site_total_probe_enabled",
    ):
        assert key in completion_models
        assert key not in pause_models

    assert "site_total_probe_enabled" not in guard_models
    assert "site_completion_evidence_enabled" in guard_models
    assert len(completion_tab) == 2
    assert [
        [
            col["content"][0]["props"].get("model") or col["content"][0]["props"].get("modelvalue")
            for col in row["content"]
        ]
        for row in completion_tab
    ] == [
        ["site_total_probe_enabled"],
        ["paused_probe_reasons", "paused_probe_min_pause_days", "paused_probe_interval_hours"],
    ]
    assert [[col["props"]["md"] for col in row["content"]] for row in completion_tab] == [
        [12],
        [4, 4, 4],
    ]
    assert model["paused_probe_reasons"] == ["no_download"]
    assert model["paused_probe_min_pause_days"] == 14
    assert model["paused_probe_interval_hours"] == 72
    assert model["site_total_probe_enabled"] is False


def test_paused_probe_labels_hints_and_interval_select_are_human_readable():
    """补搜场景说明使用面向用户的简短文案。"""
    assert LABELS["paused_probe_reasons"] == "暂停订阅补搜场景"
    assert LABELS["paused_probe_min_pause_days"] == "暂停满N天后补搜"
    assert LABELS["paused_probe_interval_hours"] == "补搜间隔（小时）"
    assert HINTS["paused_probe_reasons"] == "选择允许低频补搜的暂停原因"
    assert HINTS["paused_probe_min_pause_days"] == "暂停达到天数后开始补搜，0 表示不处理"
    assert HINTS["paused_probe_interval_hours"] == "同一订阅两次补搜的最小间隔"
    assert MULTI_ITEMS["paused_probe_reasons"] == [
        {"title": "无下载", "value": "no_download"},
        {"title": "上映/开播", "value": "pre_air"},
        {"title": "播出间隔", "value": "airing_gap"},
        {"title": "用户名", "value": "auto_user"},
        {"title": "外部暂停", "value": "external"},
        {"title": "全部", "value": "all"},
    ]
    assert SELECT_ITEMS["paused_probe_interval_hours"] == [
        {"title": "24", "value": 24},
        {"title": "48", "value": 48},
        {"title": "72", "value": 72},
        {"title": "96", "value": 96},
        {"title": "120", "value": 120},
        {"title": "144", "value": 144},
    ]
    conf, _model = build_form()
    fields = _controls_with_model(conf[4])
    interval = next(field for field in fields
                    if field["props"].get("model") == "paused_probe_interval_hours")
    assert interval["component"] == "VSelect"
    assert interval["props"]["items"] == SELECT_ITEMS["paused_probe_interval_hours"]


def test_site_total_probe_label_and_hint_belong_to_completion_tab():
    """站点集数探测属于订阅补全，站点完结信号仍属于完结信号。"""
    conf, _model = build_form()

    assert LABELS["site_total_probe_enabled"] == "站点集数探测"
    assert HINTS["site_total_probe_enabled"] == "用站点缓存资源辅助发现目标集数不足"
    assert "site_total_probe_enabled" in _tab_models(conf, "订阅补全")
    assert "site_total_probe_enabled" not in _tab_models(conf, "完结信号")
    assert "site_completion_evidence_enabled" in _tab_models(conf, "完结信号")


def test_subscription_cleanup_tab_replaces_seed_delete_title():
    """旧入口统一调整为订阅清理，不再暴露种子删除页签命名。"""
    import json
    conf, _model = build_form()
    flat = json.dumps(conf, ensure_ascii=False)

    assert '"订阅清理"' in flat
    assert '"种子删除"' not in flat


def test_subscription_cleanup_fields_live_in_cleanup_tab():
    """订阅清理页签承载清理整理记录范围/场景，洗版页签不再承载清理配置。"""
    import json
    conf, model = build_form()
    cleanup_tab = _tab_content(conf, "订阅清理")
    wash_tab = _tab_content(conf, "订阅洗版")
    cleanup_history_cols = cleanup_tab[2]["content"]
    cleanup_flat = json.dumps(cleanup_tab, ensure_ascii=False)
    wash_flat = json.dumps(wash_tab, ensure_ascii=False)

    assert model["subscription_cleanup_history_type"] == "no"
    assert model["subscription_cleanup_history_scenes"] == []
    assert '"subscription_cleanup_history_type"' in cleanup_flat
    assert '"subscription_cleanup_history_scenes"' in cleanup_flat
    assert '"best_version_clear_history_type"' not in cleanup_flat
    assert '"best_version_clear_history_type"' not in wash_flat
    assert LABELS["subscription_cleanup_history_type"] == "清理整理记录范围"
    assert LABELS["subscription_cleanup_history_scenes"] == "清理整理记录场景"
    assert {"title": "洗版订阅", "value": "best_version"} in MULTI_ITEMS["subscription_cleanup_history_scenes"]
    assert {"title": "分集洗版", "value": "best_version_episode"} in MULTI_ITEMS[
        "subscription_cleanup_history_scenes"
    ]
    assert {"title": "分集洗版", "value": "best_version"} not in MULTI_ITEMS[
        "subscription_cleanup_history_scenes"
    ]
    assert {"title": "洗版", "value": "best_version_full"} not in MULTI_ITEMS[
        "subscription_cleanup_history_scenes"
    ]
    assert {"title": "全集洗版", "value": "best_version_full"} not in MULTI_ITEMS[
        "subscription_cleanup_history_scenes"
    ]
    assert [col["content"][0]["props"]["model"] for col in cleanup_history_cols] == [
        "subscription_cleanup_history_type",
        "subscription_cleanup_history_scenes",
    ]
    assert [col["props"]["md"] for col in cleanup_history_cols] == [4, 8]


def test_form_does_not_expose_retired_tracker_dialog_state():
    """旧 Form 不再暴露仅用于控制弹窗开关的持久化字段。"""
    import json
    conf, model = build_form()

    assert "open_tracker_dialog" not in model
    assert "open_tracker_dialog" not in json.dumps(conf, ensure_ascii=False)


def test_completion_signal_hints_explain_behavior_and_scope():
    """完结信号说明使用短中文句；允许待定（P）等已解释的状态码。"""
    keys = (
        "completion_guard_mode", "volatility_enabled", "volatility_window_days",
        "cadence_enabled", "cadence_multiplier", "cadence_min_window_days",
        "cadence_min_episodes", "season_cooldown_days", "verify_enabled",
        "verify_interval_hours", "verify_retention_days",
        "timeout_release_days", "timeout_cadence_acceleration",
        "site_completion_evidence_enabled",
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
    assert "完成前观察" in HINTS["timeout_release_days"]


def test_common_check_interval_uses_reduced_options():
    """通用巡检允许追更场景高频采样，下载检查仍保留自身选项。"""
    conf, _model = build_form()
    controls = {
        col["content"][0]["props"]["model"]: col["content"][0]
        for col in conf[2]["content"]
    }

    common_items = controls["auto_check_interval_minutes"]["props"]["items"]
    download_items = controls["download_check_interval_minutes"]["props"]["items"]
    assert [item["value"] for item in common_items] == [10, 20, 30, 60, 120, 240]
    assert [item["value"] for item in download_items] == [5, 10, 15, 30, 60, 120]


def test_completion_labels_use_concise_names_without_enable_prefix():
    """完结信号配置使用简洁业务名称，不重复“启用”。"""
    assert LABELS["completion_guard_mode"] == "完结守卫模式"
    assert LABELS["volatility_enabled"] == "变更速率信号"
    assert LABELS["cadence_enabled"] == "播出节奏信号"
    assert LABELS["site_completion_evidence_enabled"] == "站点完结信号"
    assert LABELS["verify_enabled"] == "自动纠错"
    assert LABELS["verify_interval_hours"] == "自动纠错间隔（小时）"
    assert LABELS["timeout_release_days"] == "完成前观察天数"
    assert HINTS["auto_check_interval_minutes"] == "站点采样、待定释放、无下载处理和清理周期"
    assert HINTS["site_completion_evidence_enabled"] == "使用站点资源标题佐证完结信号"


def test_completion_tab_uses_original_flat_grid():
    """完结信号页保持统一平铺，不增加分组标题或卡片容器。"""
    conf, _model = build_form()
    completion_rows = _tab_content(conf, "完结信号")
    assert len(completion_rows) == 5
    assert all(row["component"] == "VRow" for row in completion_rows)
    assert not any(item.get("component") == "VCard" for item in completion_rows)
    assert [
        [col["content"][0]["props"]["model"] for col in row["content"]]
        for row in completion_rows
    ] == [
        ["verify_enabled", "site_completion_evidence_enabled", "volatility_enabled"],
        ["cadence_enabled", "timeout_cadence_acceleration", "completion_guard_mode"],
        ["volatility_window_days", "cadence_multiplier", "cadence_min_window_days"],
        ["cadence_min_episodes", "season_cooldown_days", "verify_interval_hours"],
        ["verify_retention_days", "timeout_release_days"],
    ]


def test_completion_flat_grid_keeps_persistent_hints():
    """平铺布局继续保留全部字段说明。"""
    conf, model = build_form()
    completion_items = _tab_content(conf, "完结信号")
    controls = _controls_with_model(completion_items)
    assert {key for key in model if key.startswith("timeout_release")} == {"timeout_release_days"}
    assert {control["props"]["model"] for control in controls} == {
        "completion_guard_mode",
        "volatility_enabled",
        "cadence_enabled",
        "site_completion_evidence_enabled",
        "volatility_window_days",
        "cadence_multiplier",
        "cadence_min_window_days",
        "cadence_min_episodes",
        "season_cooldown_days",
        "timeout_cadence_acceleration",
        "timeout_release_days",
        "verify_enabled",
        "verify_interval_hours",
        "verify_retention_days",
    }
    assert all(control["props"].get("persistent-hint") is True for control in controls)
