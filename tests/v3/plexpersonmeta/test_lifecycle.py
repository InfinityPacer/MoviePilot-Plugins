"""PlexPersonMeta V3 插件初始化、调度和停用生命周期测试。"""

import threading
from types import ModuleType
from unittest.mock import MagicMock, patch

from app.testing import stub_modules


_pypinyin = ModuleType("pypinyin")
_pypinyin.lazy_pinyin = lambda *_args, **_kwargs: []

with stub_modules({"pypinyin": _pypinyin}):
    from app.plugins import plexpersonmeta as _plugin


def _plugin_instance():
    """创建不触发宿主数据库写入的插件对象。"""
    plugin = object.__new__(_plugin.PlexPersonMeta)
    plugin._event = threading.Event()
    plugin._scheduler = None
    plugin._transfer_time = None
    return plugin


def test_start_scheduler_does_not_start_running_scheduler():
    """重载或实时事件复用运行中的调度器时不得二次 start。"""
    plugin = _plugin_instance()
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = [object()]
    scheduler.running = True
    plugin._scheduler = scheduler

    plugin._start_scheduler()

    scheduler.print_jobs.assert_called_once_with()
    scheduler.start.assert_not_called()


def test_stop_service_is_idempotent_and_discards_pending_transfer():
    """停用必须移除任务、释放调度器并清理待处理入库时间。"""
    plugin = _plugin_instance()
    scheduler = MagicMock()
    scheduler.running = True
    plugin._scheduler = scheduler
    plugin._transfer_time = object()

    plugin.stop_service()
    plugin.stop_service()

    scheduler.remove_all_jobs.assert_called_once_with()
    scheduler.shutdown.assert_called_once_with()
    assert plugin._scheduler is None
    assert plugin._transfer_time is None
    assert not plugin._event.is_set()


def test_empty_config_resets_previous_state_and_uses_default_delay():
    """空配置代表停用，重复初始化不能残留上一轮运行状态。"""
    plugin = _plugin_instance()
    plugin._enabled = True
    plugin._transfer_time = object()
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = []

    with (
        patch.object(_plugin, "MediaServerHelper", return_value=MagicMock()),
        patch.object(_plugin, "BackgroundScheduler", return_value=scheduler),
    ):
        plugin.init_plugin({"enabled": True, "delay": None})
        assert plugin._enabled is True
        assert plugin._delay == 200

        plugin.init_plugin(None)

    assert plugin._enabled is False
    assert plugin._libraries == []
    assert plugin._transfer_time is None
    assert plugin.get_service() == []
