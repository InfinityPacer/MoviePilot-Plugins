"""HitAndRun V3 的公开边界、索引和配置模型合同测试。"""

import ast
import json
from pathlib import Path
from types import SimpleNamespace

from app.plugins.hitandrun import HitAndRun
from app.plugins.hitandrun.helper import TorrentHelper


REPO_ROOT = Path(__file__).parents[3]
PLUGIN_SOURCE = REPO_ROOT / "plugins.v3/hitandrun/__init__.py"


def test_v3_source_uses_public_boundaries_and_relative_modules():
    """V3 实现不依赖旧兼容路径或插件包的宿主内部导入。"""
    source = PLUGIN_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(PLUGIN_SOURCE))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert {
        "app.sdk.config",
        "app.sdk.events",
        "app.sdk.logging",
        "app.sdk.media",
        "app.sdk.network",
        "app.sdk.plugins",
        "app.sdk.services",
        "app.sdk.utilities",
    } <= imported_modules
    assert "app.db.oper.site" in imported_modules
    assert not any(
        module.startswith(("app.compat", "app.core", "app.helper", "app.log", "app.utils", "app.db.models"))
        for module in imported_modules
    )
    assert "app.plugins.hitandrun" not in source


def test_v3_metadata_and_empty_capabilities_are_explicit():
    """V3 版本索引与插件元数据一致，空能力直接返回空列表。"""
    package_v3 = json.loads((REPO_ROOT / "package.v3.json").read_text(encoding="utf-8"))
    package_v2 = json.loads((REPO_ROOT / "package.v2.json").read_text(encoding="utf-8"))

    assert HitAndRun.plugin_version == "2.0.0"
    assert package_v3["HitAndRun"]["version"] == HitAndRun.plugin_version
    assert package_v3["HitAndRun"]["system_version"] == ">=3.0.0"
    assert package_v2["HitAndRun"]["v3"] is False
    assert HitAndRun.get_command() == []
    assert HitAndRun().get_api() == []


def test_v3_supports_pydantic_v2_model_serialization():
    """配置模型可在 Pydantic V2 下完成 JSON 序列化。"""
    from app.plugins.hitandrun.hnrconfig import HNRConfig

    config = HNRConfig()

    assert config.model_dump()
    assert config.model_dump_json()


def test_transmission_hash_prefers_current_rpc_field():
    """Transmission 新字段优先读取，避免 V3 运行时触发旧属性告警。"""
    torrent = SimpleNamespace(hash_string="new-hash", hashString="legacy-hash")

    assert TorrentHelper._get_transmission_hash(torrent) == "new-hash"
