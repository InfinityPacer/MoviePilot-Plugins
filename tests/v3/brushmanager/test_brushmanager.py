"""BrushManager V3 的下载器字段、公开边界和生命周期合同测试。"""

import ast
import threading
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
    # 延迟任务交给宿主调度器或一次性守护线程，插件不再自建常驻调度器
    assert not any(module.startswith("apscheduler") for module in imported_modules)


def test_v3_lifecycle_and_empty_capabilities_are_explicit():
    """未配置下载器时插件停用，并显式声明没有额外命令、API 和详情页。"""
    plugin = object.__new__(BrushManager)

    assert plugin.get_state() is False
    assert plugin.get_command() == []
    assert plugin.get_api() == []
    assert plugin.get_page() is None


def test_v3_plugin_version():
    assert BrushManager.plugin_version == "2.0.2"


def _organize_plugin(*, mp_tag=True, remove_brush_tag=False, brush_plugin=None):
    """构造只覆盖整理后续任务所需字段的插件实例。"""
    plugin = object.__new__(BrushManager)
    plugin._mp_tag = mp_tag
    plugin._remove_brush_tag = remove_brush_tag
    plugin._brush_plugin = brush_plugin
    plugin._timers = []
    return plugin


def test_after_organize_uses_host_once_jobs_without_own_scheduler(monkeypatch):
    """新版宿主上整理后续任务交给宿主一次性任务，插件不再自建调度器。"""
    plugin = _organize_plugin(remove_brush_tag=True, brush_plugin="BrushFlowLowFreq")
    add_once = MagicMock(return_value=True)
    monkeypatch.setattr("app.plugins.brushmanager.scheduler_sdk.add_plugin_once_job", add_once, raising=False)

    plugin._BrushManager__run_after_organize()

    calls = {call.args[1]: call for call in add_once.call_args_list}
    assert set(calls) == {"brush_check", "transfer"}
    assert calls["brush_check"].args[0] == "BrushManager"
    assert calls["brush_check"].kwargs["func_kwargs"] == {"job_id": "BrushFlowLowFreqCheck"}
    # 绑定实例方法，宿主才能在插件重载后丢弃旧实例的待执行任务
    assert calls["transfer"].args[2].__self__ is plugin
    assert plugin._timers == []


def test_after_organize_falls_back_to_daemon_timer_on_old_host(monkeypatch):
    """旧宿主没有一次性任务接口时用守护线程延迟执行，执行完即退出。"""
    plugin = _organize_plugin()
    monkeypatch.delattr("app.plugins.brushmanager.scheduler_sdk.add_plugin_once_job", raising=False)
    transfer = MagicMock()
    monkeypatch.setattr("app.plugins.brushmanager.TransferChain", lambda: transfer)
    monkeypatch.setattr(BrushManager, "_BrushManager__after_organize_delay", 0)

    plugin._BrushManager__run_after_organize()
    plugin._timers[0].join(5)

    transfer.process.assert_called_once_with()
    assert not plugin._timers[0].is_alive()


def test_repeated_organize_does_not_accumulate_threads(monkeypatch):
    """多次整理后不应留下常驻线程（旧版每次新建 BackgroundScheduler 且从不释放）。"""
    plugin = _organize_plugin()
    monkeypatch.delattr("app.plugins.brushmanager.scheduler_sdk.add_plugin_once_job", raising=False)
    monkeypatch.setattr("app.plugins.brushmanager.TransferChain", MagicMock)
    monkeypatch.setattr(BrushManager, "_BrushManager__after_organize_delay", 0)
    before = threading.active_count()

    for _ in range(5):
        plugin._BrushManager__run_after_organize()
    for timer in list(plugin._timers):
        timer.join(5)

    assert threading.active_count() == before


def test_stop_service_cancels_pending_after_organize_jobs(monkeypatch):
    """停止插件时取消尚未执行的延迟任务，与旧版关闭调度器的语义一致。"""
    plugin = _organize_plugin()
    timer = MagicMock()
    plugin._timers = [timer]
    remove_once = MagicMock()
    monkeypatch.setattr("app.plugins.brushmanager.scheduler_sdk.remove_plugin_once_job", remove_once, raising=False)

    plugin.stop_service()

    timer.cancel.assert_called_once_with()
    assert plugin._timers == []
    assert {call.args for call in remove_once.call_args_list} == {
        ("BrushManager", "brush_check"),
        ("BrushManager", "transfer"),
    }
