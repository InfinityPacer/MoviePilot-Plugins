"""SmartRename V3 的 SDK 边界、全局配置生命周期和重命名合同测试。"""

from __future__ import annotations

import ast
import json
from pathlib import Path

from app.domain.meta.customization import CustomizationMatcher
from app.plugins.smartrename import SmartRename
from app.sdk.media import set_custom_separator


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_SOURCE = REPO_ROOT / "plugins.v3/smartrename/__init__.py"


def _plugin() -> SmartRename:
    """构造不启动宿主 Runtime 的 SmartRename 实例。"""
    return object.__new__(SmartRename)


def test_v3_source_uses_sdk_boundaries() -> None:
    """V3 实现只通过公开 SDK 访问媒体、事件和日志能力。"""
    source = PLUGIN_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(PLUGIN_SOURCE))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert {
        "app.sdk.events",
        "app.sdk.logging",
        "app.sdk.media",
    } <= imported_modules
    assert "app.domain.meta.customization" not in imported_modules
    assert not any(
        module.startswith(("app.compat", "app.core", "app.helper", "app.log", "app.utils"))
        for module in imported_modules
    )
    assert "set_custom_separator" in source


def test_v3_metadata_and_version_contract_are_consistent() -> None:
    """V3 索引、类版本和旧代回退阻断标志保持一致。"""
    package_v3 = json.loads((REPO_ROOT / "package.v3.json").read_text(encoding="utf-8"))
    package_v2 = json.loads((REPO_ROOT / "package.v2.json").read_text(encoding="utf-8"))
    metadata = package_v3["SmartRename"]

    assert SmartRename.plugin_version == "2.0.0"
    assert metadata["version"] == SmartRename.plugin_version
    assert metadata["system_version"] == ">=3.0.0"
    assert list(metadata["history"]) == ["v2.0.0"]
    assert metadata["history"]["v2.0.0"]
    assert package_v2["SmartRename"]["v3"] is False


def test_custom_separator_uses_sdk_and_is_cleared_on_disable() -> None:
    """插件启停必须通过 SDK 管理宿主全局分隔符，避免停用后残留配置。"""
    matcher = CustomizationMatcher()
    plugin = _plugin()

    set_custom_separator(None)
    plugin.init_plugin({"enabled": True, "custom_separator": "#"})
    assert matcher.custom_separator == "#"

    plugin.init_plugin({"enabled": False, "custom_separator": "$"})
    assert matcher.custom_separator is None

    plugin.init_plugin({"enabled": True, "custom_separator": "%"})
    plugin.stop_service()
    assert matcher.custom_separator is None


def test_rename_preserves_field_separator_behavior() -> None:
    """V3 副本保留字段分隔符的原有渲染语义。"""
    plugin = _plugin()
    plugin._separator = "."
    plugin._separator_types = ["videoCodec"]
    plugin._field_separators = {}

    assert plugin.rename("{{ videoCodec }}", {"videoCodec": "H 264"}) == "H.264"
