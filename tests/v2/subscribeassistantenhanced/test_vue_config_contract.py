import json
import re
from collections import OrderedDict
from pathlib import Path

from subscribeassistantenhanced import SubscribeAssistantEnhanced
from subscribeassistantenhanced.form import (
    CRON_FIELDS,
    HINTS,
    LABELS,
    MULTI_ITEMS,
    PERIODS,
    SELECT_ITEMS,
    TABS,
    TOP_SWITCHES,
)
from subscribeassistantenhanced.shared.config import PluginConfig


REPO_ROOT = Path(__file__).resolve().parents[3]
README_PATH = REPO_ROOT / "plugins.v2/subscribeassistantenhanced/README.md"
FRONTEND_PACKAGE_PATH = REPO_ROOT / "plugins.v2/subscribeassistantenhanced/frontend/package.json"
DEFAULTS_PATH = REPO_ROOT / "plugins.v2/subscribeassistantenhanced/frontend/src/config/defaults.ts"
FIELDS_PATH = REPO_ROOT / "plugins.v2/subscribeassistantenhanced/frontend/src/config/fields.ts"

TAB_GROUPS = {
    "订阅清理": "cleanup",
    "订阅待定": "pending",
    "订阅暂停": "pause",
    "订阅补全": "completion",
    "订阅洗版": "bestVersion",
    "完结信号": "guard",
    "识别增强": "recognition",
}

DANGER_KEYS = {
    "reset_task",
    "download_monitor_enabled",
    "manual_delete_listen",
    "tracker_response_listen",
    "subscription_cleanup_history_type",
    "subscription_cleanup_history_scenes",
    "no_download_actions",
    "best_version_type",
    "best_version_episode_to_full",
    "backfill_best_version_now",
    "recognition_guard_mode",
    "recognition_guard_custom_config",
}

ADVANCED_MARKERS = (
    "threshold",
    "cooldown",
    "retention",
    "interval",
    "window",
    "days",
    "hours",
    "minutes",
    "rounds",
    "limit",
    "maxsize",
    "custom_config",
    "default_tracker_response",
)


def _load_json_export(path: Path, marker: str):
    assert path.is_file(), f"缺少生成配置契约：{path.relative_to(REPO_ROOT)}"
    _, separator, suffix = path.read_text(encoding="utf-8").partition(marker)
    assert separator, f"缺少配置导出标记：{marker}"
    return json.loads(suffix.strip())


def _load_interface_types(path: Path, interface_name: str) -> OrderedDict[str, str]:
    assert path.is_file(), f"缺少生成配置契约：{path.relative_to(REPO_ROOT)}"
    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf"export interface {re.escape(interface_name)}\s*\{{(?P<body>.*?)^\}}",
        text,
        flags=re.DOTALL | re.MULTILINE,
    )
    assert match, f"缺少配置接口声明：{interface_name}"

    body = re.sub(r"/\*\*.*?\*/", "", match.group("body"), flags=re.DOTALL)
    interface_types = OrderedDict()
    for line in body.splitlines():
        declaration = line.strip().removesuffix(";")
        if not declaration:
            continue
        key, separator, value_type = declaration.partition(":")
        assert separator and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key), (
            f"无法解析 {interface_name} 属性声明：{declaration}"
        )
        assert key not in interface_types, f"{interface_name} 存在重复属性：{key}"
        interface_types[key] = value_type.strip()
    return interface_types


def _expected_interface_types(defaults: dict) -> OrderedDict[str, str]:
    list_keys = {key for key, value in defaults.items() if isinstance(value, list)}
    assert list_keys == set(MULTI_ITEMS), "列表默认值必须与多选配置键完全一致"

    expected_types = OrderedDict()
    for key, value in defaults.items():
        if isinstance(value, bool):
            value_type = "boolean"
        elif isinstance(value, (int, float)):
            value_type = "number"
        elif isinstance(value, str):
            value_type = "string"
        elif isinstance(value, list):
            value_type = "string[]"
        else:
            raise AssertionError(f"不支持的配置默认值类型：{key}={type(value).__name__}")
        expected_types[key] = value_type
    return expected_types


def _expected_fields(defaults: dict) -> list[dict]:
    group_by_key = {key: "global" for key in [*TOP_SWITCHES, *PERIODS]}
    for title, rows in TABS:
        for row in rows:
            for item in row:
                key = item[0] if isinstance(item, tuple) else item
                group_by_key[key] = TAB_GROUPS[title]
    group_by_key["default_tracker_response"] = "cleanup"

    def kind_for(key: str) -> str:
        if key in CRON_FIELDS:
            return "cron"
        if key in MULTI_ITEMS:
            return "multi-select"
        if key in SELECT_ITEMS:
            return "select"
        if key in {"default_tracker_response", "recognition_guard_custom_config"}:
            return "textarea"
        if isinstance(defaults[key], bool):
            return "switch"
        if isinstance(defaults[key], (int, float)):
            return "number"
        return "text"

    expected = []
    for key in defaults:
        field = {
            "key": key,
            "label": LABELS[key],
            "group": group_by_key[key],
            "kind": kind_for(key),
        }
        if HINTS.get(key):
            field["hint"] = HINTS[key]
        if key in SELECT_ITEMS:
            field["options"] = SELECT_ITEMS[key]
        if key in MULTI_ITEMS:
            field["options"] = MULTI_ITEMS[key]
        if key == "default_tracker_response":
            field["dialogOnly"] = True
            field["advanced"] = True
        if key in DANGER_KEYS:
            field["risk"] = "danger"
        elif any(marker in key for marker in ADVANCED_MARKERS):
            field["advanced"] = True
        expected.append(field)
    return expected


def test_render_mode_uses_vue_assets():
    plugin = SubscribeAssistantEnhanced()

    assert plugin.get_render_mode() == ("vue", "frontend/dist/assets")


def test_frontend_package_exposes_watch_build_script():
    package = json.loads(FRONTEND_PACKAGE_PATH.read_text(encoding="utf-8"))

    assert package.get("scripts", {}).get("dev") == "vite build --watch"


def test_summary_api_uses_bear_auth_and_coarse_payload_shape():
    plugin = SubscribeAssistantEnhanced()
    apis = plugin.get_api()

    summary_api = next(api for api in apis if api["path"] == "/summary")
    assert summary_api["auth"] == "bear"
    assert summary_api["methods"] == ["GET"]

    plugin.init_plugin({})
    payload = plugin._api_summary()

    assert set(payload) == {"domains", "pending_count", "monitored_torrents"}
    assert isinstance(payload["domains"], dict)
    assert isinstance(payload["pending_count"], int)
    assert isinstance(payload["monitored_torrents"], int)


def test_generated_vue_config_contract_matches_python_sources():
    defaults = PluginConfig.defaults()
    generated_types = _load_interface_types(DEFAULTS_PATH, "SaeConfig")
    generated_defaults = _load_json_export(DEFAULTS_PATH, "export const configDefaults: SaeConfig = ")
    generated_fields = _load_json_export(FIELDS_PATH, "export const fields: FieldMeta[] = ")

    assert generated_types == _expected_interface_types(defaults)
    assert generated_defaults == defaults
    assert generated_fields == _expected_fields(defaults)
    for field in generated_fields:
        if field["key"] in MULTI_ITEMS:
            assert all(isinstance(option["value"], str) for option in field["options"])


def test_readme_wash_schedule_registration_requires_nonempty_cron():
    service_row = next(
        line
        for line in README_PATH.read_text(encoding="utf-8").splitlines()
        if line.startswith("| 洗版订阅检查 |")
    )
    description = service_row.strip("|").split("|")[3].strip()
    _details, separator, registration_condition = description.rpartition("；")

    assert separator
    assert registration_condition == "仅「洗版类型」不是关闭且「洗版检查周期」非空时注册"
