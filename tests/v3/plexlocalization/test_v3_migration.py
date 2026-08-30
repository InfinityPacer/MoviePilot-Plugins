"""Plex 中文本地化 V3 导入、事件和生命周期边界测试。"""

import json
import tomllib
import threading
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, patch

from app.schemas.system import ServiceInfo
from app.schemas.types import EventType
from app.sdk.events import Event
from app.testing import stub_modules


_pypinyin = ModuleType("pypinyin")
_pypinyin.Style = type("Style", (), {"FIRST_LETTER": "first_letter"})
_pypinyin.pinyin = lambda *args, **kwargs: [["A"]]

with stub_modules({"pypinyin": _pypinyin}):
    from app.plugins.plexlocalization import PlexLocalization


def test_v3_plugin_uses_stable_imports_for_migrated_boundaries():
    """V3 副本不能继续依赖已登记的历史 core/helper/log/utils 路径。"""
    plugin_root = Path(__file__).parents[3] / "plugins.v3" / "plexlocalization"
    source = "\n".join(path.read_text(encoding="utf-8") for path in plugin_root.glob("*.py"))

    assert "from app.core." not in source
    assert "from app.helper." not in source
    assert "from app.log import" not in source
    assert "from app.utils." not in source
    assert "from app.modules." not in source
    assert "from app.sdk." in source


def test_v3_version_and_legacy_index_disable_fallback():
    """V3 专用版本应与索引一致，并禁止 V2 实现再次回退加载。"""
    repo_root = Path(__file__).parents[3]
    package_v3 = json.loads((repo_root / "package.v3.json").read_text(encoding="utf-8"))
    package_v2 = json.loads((repo_root / "package.v2.json").read_text(encoding="utf-8"))

    metadata = package_v3["PlexLocalization"]
    assert PlexLocalization.plugin_version == "3.0.0"
    assert metadata["version"] == PlexLocalization.plugin_version
    assert list(metadata["history"]) == ["v3.0.0"]
    assert metadata["system_version"] == ">=3.0.0"
    assert package_v2["PlexLocalization"]["v3"] is False


def test_v3_dependency_manifest_declares_pypinyin():
    """V3 插件的额外依赖必须由现代清单声明。"""
    manifest = Path(__file__).parents[3] / "plugins.v3" / "plexlocalization" / "pyproject.toml"
    with manifest.open("rb") as file:
        project = tomllib.load(file)["project"]

    assert project["name"] == "moviepilot-plugin-plexlocalization"
    assert project["dynamic"] == ["version"]
    assert project["dependencies"] == ["pypinyin~=0.51.0"]


def test_transfer_event_uses_typed_snapshot_payload():
    """整理完成事件应经 SDK 快照读取稳定的媒体和元数据字段。"""
    plugin = object.__new__(PlexLocalization)
    plugin._enabled = True
    plugin._execute_transfer = True
    plugin._delay = 0
    plugin._transfer_time = None
    plugin._scheduler = None
    plugin._scheduler_lock = threading.Lock()
    plugin._event = threading.Event()
    scheduler = MagicMock()
    scheduler.running = False
    scheduler.get_jobs.return_value = [object()]
    event = Event(
        EventType.TransferComplete,
        {
            "meta": {"season_episode": "S01E02"},
            "mediainfo": {"title_year": "测试 (2026)"},
        },
    )

    with patch("app.plugins.plexlocalization.BackgroundScheduler", return_value=scheduler):
        plugin.execute_transfer(event)

    scheduler.add_job.assert_called_once()
    assert plugin._transfer_time is not None


def test_transfer_event_with_invalid_snapshot_does_not_schedule_work():
    """缺少稳定事件载荷时应安全跳过，而不是依赖旧字典字段。"""
    plugin = object.__new__(PlexLocalization)
    plugin._enabled = True
    plugin._execute_transfer = True
    plugin._scheduler = None
    plugin._scheduler_lock = threading.Lock()
    plugin._event = threading.Event()
    event = Event(EventType.TransferComplete, {"unexpected": True})

    with patch("app.plugins.plexlocalization.BackgroundScheduler") as scheduler_cls:
        plugin.execute_transfer(event)

    scheduler_cls.assert_not_called()


def test_consecutive_transfer_events_reuse_running_scheduler():
    """连续入库只重排同一调度器任务，不能重复启动已运行的 Scheduler。"""
    plugin = object.__new__(PlexLocalization)
    plugin._enabled = True
    plugin._execute_transfer = True
    plugin._delay = 60
    plugin._transfer_time = None
    plugin._scheduler = None
    plugin._scheduler_lock = threading.Lock()
    plugin._event = threading.Event()
    scheduler = MagicMock()
    scheduler.get_jobs.return_value = [object()]
    scheduler.running = False
    event = Event(
        EventType.TransferComplete,
        {
            "meta": {"season_episode": "S01E02"},
            "mediainfo": {"title_year": "测试 (2026)"},
        },
    )

    with patch("app.plugins.plexlocalization.BackgroundScheduler", return_value=scheduler):
        plugin.execute_transfer(event)
        scheduler.running = True
        plugin.execute_transfer(event)

    assert scheduler.remove_all_jobs.call_count == 2
    assert scheduler.add_job.call_count == 2
    scheduler.start.assert_called_once_with()


def test_consecutive_transfer_events_with_real_scheduler():
    """真实 APScheduler 运行后仍可被连续入库事件安全重排。"""
    plugin = object.__new__(PlexLocalization)
    plugin._enabled = True
    plugin._execute_transfer = True
    plugin._delay = 60
    plugin._transfer_time = None
    plugin._scheduler = None
    plugin._scheduler_lock = threading.Lock()
    plugin._event = threading.Event()
    event = Event(
        EventType.TransferComplete,
        {
            "meta": {"season_episode": "S01E02"},
            "mediainfo": {"title_year": "测试 (2026)"},
        },
    )

    try:
        plugin.execute_transfer(event)
        plugin.execute_transfer(event)
        assert plugin._scheduler is not None
        assert plugin._scheduler.running is True
        assert len(plugin._scheduler.get_jobs()) == 1
    finally:
        plugin.stop_service()


def test_service_info_handles_unavailable_service_instance():
    """媒体服务配置存在但实例尚未建立时不得调用空对象方法。"""
    plugin = object.__new__(PlexLocalization)
    plugin.mediaserver_helper = MagicMock()
    plugin.mediaserver_helper.get_service.return_value = ServiceInfo(name="Plex")

    with patch("app.plugins.plexlocalization.logger") as logger:
        assert plugin.service_info(name="Plex") is None

    logger.warning.assert_called_once_with("媒体服务器 Plex 未连接，请检查配置")


def test_invalid_cron_returns_no_service_instead_of_raising():
    """非法周期配置不应阻断插件列表和其它插件的加载。"""
    plugin = object.__new__(PlexLocalization)
    plugin._enabled = True
    plugin._cron = "not a cron"

    with patch("app.plugins.plexlocalization.logger") as logger:
        assert plugin.get_service() == []

    logger.error.assert_called_once()


def test_empty_config_resets_previous_lifecycle_state():
    """空配置表示停用，重载不能残留上一轮调度和入库时间。"""
    plugin = object.__new__(PlexLocalization)
    plugin._scheduler = None
    plugin._scheduler_lock = threading.Lock()
    plugin._enabled = True
    plugin._transfer_time = object()

    with patch("app.plugins.plexlocalization.MediaServerHelper"):
        plugin.init_plugin(None)

    assert plugin._enabled is False
    assert plugin._libraries == []
    assert plugin._transfer_time is None
    assert plugin.get_service() == []
