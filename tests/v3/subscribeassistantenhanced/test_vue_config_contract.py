import json
import re
from collections import OrderedDict
from pathlib import Path

from app.plugins.subscribeassistantenhanced import SubscribeAssistantEnhanced
from app.plugins.subscribeassistantenhanced.shared.config import PluginConfig


REPO_ROOT = Path(__file__).resolve().parents[3]
README_PATH = REPO_ROOT / "plugins.v3/subscribeassistantenhanced/README.md"
FRONTEND_PACKAGE_PATH = REPO_ROOT / "plugins.v3/subscribeassistantenhanced/frontend/package.json"
DEFAULTS_PATH = REPO_ROOT / "plugins.v3/subscribeassistantenhanced/frontend/src/config/defaults.ts"
FIELDS_PATH = REPO_ROOT / "plugins.v3/subscribeassistantenhanced/frontend/src/config/fields.ts"

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


def test_render_mode_uses_vue_assets():
    plugin = SubscribeAssistantEnhanced()

    conf, model = plugin.get_form()
    assert conf == []
    assert model == PluginConfig.defaults()
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
    assert len(generated_fields) == len(defaults)
    assert {field["key"] for field in generated_fields} == set(defaults)
    for field in generated_fields:
        assert field["label"].strip()
        assert "advanced" not in field
        if field["kind"] == "multi-select":
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
