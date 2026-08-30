"""TorrentClassifier V3 公开宿主边界与种子分类合同测试。"""

import ast
import json
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from app.plugins.torrentclassifier import TorrentClassifier
from app.plugins.torrentclassifier.classifierconfig import TorrentFilter, TorrentTarget

from .torrent_sdk_fixtures import (
    force_transmission_plugin,
    make_tr_legacy_torrent,
    make_tr_v7_torrent,
)


REPO_ROOT = Path(__file__).parents[3]
PLUGIN_SOURCE = REPO_ROOT / "plugins.v3/torrentclassifier/__init__.py"


def _call_torrent_info(torrent):
    """在不启动宿主服务的情况下调用种子信息映射。"""
    plugin = force_transmission_plugin(object.__new__(TorrentClassifier))
    with patch.object(TorrentClassifier, "service_info", new_callable=PropertyMock, return_value=object()):
        return plugin._TorrentClassifier__get_torrent_info(torrent)


def test_v3_source_uses_public_sdk_and_relative_plugin_imports():
    """V3 实现使用公开 SDK，且不依赖旧导入兼容层或宿主内部会话。"""
    source = PLUGIN_SOURCE.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(PLUGIN_SOURCE))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert {
        "app.sdk.config",
        "app.sdk.logging",
        "app.sdk.services",
    } <= imported_modules
    assert "app.plugins.torrentclassifier" not in source
    assert "from .classifierconfig import" in source
    assert not any(
        module.startswith(
            (
                "app.compat",
                "app.core",
                "app.helper",
                "app.log",
                "app.utils",
                "app.db.models",
                "app.sdk._legacy",
            )
        )
        for module in imported_modules
    )


def test_v3_metadata_and_legacy_index_are_consistent():
    """V3 索引、源码版本和旧代回退阻断标志保持一致。"""
    package_v3 = json.loads((REPO_ROOT / "package.v3.json").read_text(encoding="utf-8"))
    package_v2 = json.loads((REPO_ROOT / "package.v2.json").read_text(encoding="utf-8"))
    metadata = package_v3["TorrentClassifier"]

    assert TorrentClassifier.plugin_version == "2.0.0"
    assert metadata["version"] == TorrentClassifier.plugin_version
    assert metadata["system_version"] == ">=3.0.0"
    assert list(metadata["history"]) == ["v2.0.0"]
    assert metadata["history"]["v2.0.0"]
    assert package_v2["TorrentClassifier"]["v3"] is False


def test_v3_empty_capabilities_are_explicit():
    """未注册命令和 API 时直接返回空列表，保持 V3 合同类型一致。"""
    plugin = object.__new__(TorrentClassifier)

    assert plugin.get_command() == []
    assert plugin.get_api() == []


def test_transmission_rpc_v7_fields_are_read_without_deprecation_warnings():
    """Transmission 新字段和标签映射应保持可用且不触发旧属性告警。"""
    with warnings.catch_warnings():
        warnings.simplefilter("error", DeprecationWarning)
        info = _call_torrent_info(make_tr_v7_torrent())

    assert info["hash"] == "tr_hash_1"
    assert info["seeding_time"] > 0
    assert info["dltime"] > 0
    assert info["iatime"] > 0
    assert info["add_on"] == 900
    assert info["tags"] == ["tag1"]
    assert info["tracker"] == "https://tracker/announce"


def test_legacy_transmission_fields_remain_supported():
    """旧 transmission-rpc 字段仍可映射为分类整理所需统计信息。"""
    info = _call_torrent_info(make_tr_legacy_torrent())

    assert info["hash"] == "tr_hash_1"
    assert info["seeding_time"] > 0
    assert info["dltime"] > 0
    assert info["iatime"] > 0
    assert info["add_on"] == 900
    assert info["tags"] == ["tag1"]
    assert info["tracker"] == "https://tracker/announce"


def test_transmission_hash_prefers_current_rpc_field():
    """优先使用新版 hash_string，避免读取可能已弃用的 hashString。"""
    torrent = SimpleNamespace(hash_string="new-hash", hashString="legacy-hash")

    assert TorrentClassifier._TorrentClassifier__get_transmission_hash(torrent) == "new-hash"


def test_yaml_config_and_target_matching_preserve_classifier_contract():
    """YAML 规则和目标前置过滤应保留标签清理及目录匹配语义。"""
    plugin = object.__new__(TorrentClassifier)
    configs = plugin._TorrentClassifier__load_configs(
        "- torrent_filter:\n"
        "    torrent_title: 'Test'\n"
        "    torrent_tags: ['tag1', '']\n"
        "  torrent_target:\n"
        "    change_directory: '/downloads'\n"
        "    add_tags: ['tag2', '']\n"
        "    remove_tags: ['tag1', '']\n"
    )

    assert len(configs) == 1
    assert configs[0].torrent_filter == TorrentFilter(torrent_title="Test", torrent_tags=["tag1"])
    target = configs[0].torrent_target
    assert target == TorrentTarget(
        change_directory="/downloads",
        add_tags=["tag2"],
        remove_tags=["tag1"],
    )
    assert TorrentClassifier._TorrentClassifier__matches_target_settings(
        target,
        "/downloads",
        None,
        ["tag2"],
        False,
    )[0] is True
