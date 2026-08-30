"""BrushManager V3 的下载器字段、公开边界和生命周期合同测试。"""

import ast
import warnings
from pathlib import Path
from unittest.mock import MagicMock, PropertyMock, patch

from app.plugins.brushmanager import BrushManager

from .torrent_sdk_fixtures import (
    force_transmission_plugin,
    make_tr_legacy_torrent,
    make_tr_v7_torrent,
)


def _call(torrent):
    """在不连接下载器的情况下调用种子信息转换。"""
    plugin = force_transmission_plugin(object.__new__(BrushManager))
    with patch.object(
        BrushManager,
        "service_info",
        new_callable=PropertyMock,
        return_value=object(),
    ):
        return plugin._BrushManager__get_torrent_info(torrent)


class TestTransmissionTorrentInfo:
    """Transmission 新旧 SDK 字段都应转换为刷流统计信息。"""

    def test_transmission_rpc_v7_fields_without_deprecation_warning(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            info = _call(make_tr_v7_torrent())

        assert info["hash"] == "tr_hash_1"
        assert info["seeding_time"] > 0
        assert info["dltime"] > 0
        assert info["iatime"] > 0
        assert info["add_on"] == 900
        assert info["tags"] == ["tag1"]
        assert info["tracker"] == "https://tracker/announce"

    def test_legacy_transmission_fields(self):
        info = _call(make_tr_legacy_torrent())

        assert info["hash"] == "tr_hash_1"
        assert info["seeding_time"] > 0
        assert info["dltime"] > 0
        assert info["iatime"] > 0
        assert info["add_on"] == 900
        assert info["tags"] == ["tag1"]
        assert info["tracker"] == "https://tracker/announce"


def test_v3_source_uses_public_sdk_boundaries():
    """V3 源码使用稳定 SDK，不引入旧路径或调度器内部门面。"""
    source_path = Path(__file__).parents[3] / "plugins.v3" / "brushmanager" / "__init__.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert {
        "app.chain.transfer",
        "app.sdk.config",
        "app.sdk.logging",
        "app.sdk.plugins",
        "app.sdk.scheduler",
        "app.sdk.services",
        "app.modules.qbittorrent",
        "app.modules.transmission",
    } <= imported_modules
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
    assert "app.scheduler" not in imported_modules


def test_v3_lifecycle_and_empty_capabilities_are_explicit():
    """未配置下载器时插件停用，并显式声明没有额外命令、API 和详情页。"""
    plugin = object.__new__(BrushManager)

    assert plugin.get_state() is False
    assert plugin.get_command() == []
    assert plugin.get_api() == []
    assert plugin.get_page() is None


def test_v3_plugin_version():
    assert BrushManager.plugin_version == "2.0.0"


def test_mp_tag_schedules_transfer_without_brush_plugin(monkeypatch):
    """MP 标签整理不应依赖可选刷流插件的检查任务。"""
    plugin = object.__new__(BrushManager)
    plugin._mp_tag = True
    plugin._remove_brush_tag = False
    plugin._brush_plugin = None
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = [object()]
    monkeypatch.setattr(
        "app.plugins.brushmanager.BackgroundScheduler",
        lambda **_kwargs: scheduler,
    )

    plugin._BrushManager__run_after_organize()

    scheduler.add_job.assert_called_once()
    scheduler.start.assert_called_once_with()
