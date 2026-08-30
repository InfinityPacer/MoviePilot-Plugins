"""PlexRefreshRecent V3 的服务、刷新和生命周期合同测试。"""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.plugins.plexrefreshrecent as plexrefreshrecent
from app.runtime.extensions.plugin.contracts import supports_plugin_hook


PLUGIN = plexrefreshrecent.PlexRefreshRecent


def _plugin(*, enabled: bool = True, force: bool = False) -> PLUGIN:
    """构造不依赖真实服务目录的插件实例。"""
    plugin = object.__new__(PLUGIN)
    plugin.mediaserver_helper = MagicMock()
    plugin._enabled = enabled
    plugin._cron = "0 */3 * * *"
    plugin._offset_days = 3
    plugin._onlyonce = False
    plugin._notify = False
    plugin._limit = 1000
    plugin._force = force
    plugin._mediaservers = ["Plex A"]
    plugin._scheduler = None
    plugin._event.clear()
    return plugin


def _item(
        key: str,
        *,
        item_type: str = "episode",
        summary: str = "",
        parent: str | None = None,
        grandparent: str | None = None,
        title: str | None = None,
) -> SimpleNamespace:
    """构造带 Plex 外部对象字段的媒体项。"""
    return SimpleNamespace(
        ratingKey=key,
        parentRatingKey=parent,
        grandparentRatingKey=grandparent,
        summary=summary,
        parentTitle="Season 1" if parent else None,
        grandparentTitle="Show" if grandparent else None,
        title=title or key,
        type=item_type,
        TYPE=item_type,
        refresh=MagicMock(),
    )


def _service(name: str, items=None, *, inactive: bool = False) -> SimpleNamespace:
    """构造媒体服务信息及 Plex library 查询对象。"""
    plex = SimpleNamespace(
        library=SimpleNamespace(search=MagicMock(return_value=items or []))
    )
    instance = SimpleNamespace(
        is_inactive=MagicMock(return_value=inactive),
        get_plex=MagicMock(return_value=plex),
    )
    return SimpleNamespace(name=name, instance=instance, type="plex")


def test_v3_entry_uses_sdk_boundaries_and_version() -> None:
    """V3 插件入口应只通过公开 SDK 访问配置、事件、日志和媒体服务。"""
    source_path = Path(__file__).parents[3] / "plugins.v3" / "plexrefreshrecent" / "__init__.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert PLUGIN.plugin_version == "2.0.0"
    assert "app.sdk.config" in imported_modules
    assert "app.sdk.events" in imported_modules
    assert "app.sdk.logging" in imported_modules
    assert "app.sdk.services" in imported_modules
    assert "NotificationType" not in source_path.read_text(encoding="utf-8")
    assert not any(
        module.startswith(("app.compat", "app.core", "app.db", "app.helper", "app.log"))
        for module in imported_modules
    )


def test_service_infos_filters_selected_plex_services_and_drops_inactive() -> None:
    """只保留选中的已连接 Plex 服务，非 Plex/未连接项由服务端口过滤或丢弃。"""
    plugin = _plugin()
    active = _service("Plex A")
    inactive = _service("Plex B", inactive=True)
    plugin.mediaserver_helper.get_services.return_value = {
        "Plex A": active,
        "Plex B": inactive,
    }

    result = plugin.service_infos()

    assert result == {"Plex A": active}
    plugin.mediaserver_helper.get_services.assert_called_once_with(
        name_filters=["Plex A"],
        type_filter="plex",
    )


def test_service_infos_returns_none_without_selection_or_active_service() -> None:
    """没有选择媒体服务器或没有可用实例时不执行远端刷新。"""
    plugin = _plugin()
    plugin._mediaservers = []
    assert plugin.service_infos() is None
    plugin._mediaservers = ["Plex A"]
    plugin.mediaserver_helper.get_services.return_value = {
        "Plex A": _service("Plex A", inactive=True),
    }
    assert plugin.service_infos() is None


def test_refresh_queries_time_window_and_counts_each_item_once(monkeypatch) -> None:
    """查询使用配置的时间窗口和上限，多个服务的刷新计数不重复累加。"""
    plugin = _plugin()
    plugin._mediaservers = ["Plex A", "Plex B"]
    first_items = [_item("1"), _item("2", parent="1")]
    second_items = [_item("3", summary="已有摘要"), _item("4")]
    first = _service("Plex A", first_items)
    second = _service("Plex B", second_items)
    plugin.mediaserver_helper.get_services.return_value = {
        "Plex A": first,
        "Plex B": second,
    }
    monkeypatch.setattr(
        PLUGIN,
        "_PlexRefreshRecent__get_timestamp",
        staticmethod(lambda offset_day: 123456),
    )

    success, count = plugin._PlexRefreshRecent__refresh_plex()

    assert (success, count) == (True, 2)
    first.instance.get_plex.return_value.library.search.assert_called_once_with(
        limit=1000,
        **{"addedAt>": 123456},
    )
    second.instance.get_plex.return_value.library.search.assert_called_once_with(
        limit=1000,
        **{"addedAt>": 123456},
    )
    first_items[0].refresh.assert_called_once_with()
    first_items[1].refresh.assert_not_called()
    second_items[0].refresh.assert_not_called()
    second_items[1].refresh.assert_called_once_with()


def test_refresh_metadata_honors_force_summary_and_season_rules() -> None:
    """非强制模式跳过已有摘要，强制模式刷新；season 始终不直接请求刷新。"""
    plugin = _plugin(force=False)
    with_summary = _item("1", summary="已有摘要")
    without_summary = _item("2")
    season = _item("3", item_type="season")
    refreshed = {}

    for item in (with_summary, without_summary, season):
        plugin._PlexRefreshRecent__refresh_metadata(item, refreshed)

    with_summary.refresh.assert_not_called()
    without_summary.refresh.assert_called_once_with()
    season.refresh.assert_not_called()
    assert refreshed == {"2": True}

    forced = _plugin(force=True)
    forced_item = _item("4", summary="已有摘要")
    forced._PlexRefreshRecent__refresh_metadata(forced_item, refreshed)
    forced_item.refresh.assert_called_once_with()
    assert refreshed["4"] is True


def test_refresh_metadata_deduplicates_parent_and_grandparent() -> None:
    """同一媒体树中已刷新的当前项、父项或祖父项均阻止后续重复请求。"""
    plugin = _plugin()
    refreshed = {}
    root = _item("root")
    child = _item("child", parent="root")
    grandchild = _item("grandchild", grandparent="root")
    plugin._PlexRefreshRecent__refresh_metadata(root, refreshed)
    plugin._PlexRefreshRecent__refresh_metadata(child, refreshed)
    plugin._PlexRefreshRecent__refresh_metadata(grandchild, refreshed)

    root.refresh.assert_called_once_with()
    child.refresh.assert_not_called()
    grandchild.refresh.assert_not_called()
    assert refreshed == {"root": True}


def test_refresh_isolates_item_and_service_exceptions() -> None:
    """单个媒体项或某个服务失败时继续处理其它工作，并保留已成功计数。"""
    plugin = _plugin()
    failed_item = _item("failed")
    failed_item.refresh.side_effect = RuntimeError("refresh failed")
    good_item = _item("good")
    failing_service = _service("Plex A", [failed_item, good_item])
    healthy_item = _item("healthy")
    healthy_service = _service("Plex B", [healthy_item])
    failing_search = _service("Plex C")
    failing_search.instance.get_plex.return_value.library.search.side_effect = RuntimeError(
        "search failed"
    )
    plugin._mediaservers = ["Plex A", "Plex B", "Plex C"]
    plugin.mediaserver_helper.get_services.return_value = {
        "Plex A": failing_service,
        "Plex B": healthy_service,
        "Plex C": failing_search,
    }

    success, count = plugin._PlexRefreshRecent__refresh_plex()

    assert (success, count) == (True, 2)
    failed_item.refresh.assert_called_once_with()
    good_item.refresh.assert_called_once_with()
    healthy_item.refresh.assert_called_once_with()


def test_refresh_recent_accepts_only_declared_action_and_posts_summary() -> None:
    """事件入口过滤远程命令，成功执行后按配置发送摘要通知。"""
    plugin = _plugin()
    plugin._notify = True
    plugin._PlexRefreshRecent__check_plex_media_server = MagicMock(return_value=True)
    plugin._PlexRefreshRecent__refresh_plex = MagicMock(return_value=(True, 7))
    plugin.post_message = MagicMock()

    plugin.refresh_recent(SimpleNamespace(event_data={"action": "other"}))
    plugin._PlexRefreshRecent__refresh_plex.assert_not_called()

    plugin.refresh_recent(
        SimpleNamespace(event_data={"action": "refresh_plex_recent_event"})
    )
    plugin._PlexRefreshRecent__refresh_plex.assert_called_once_with()
    plugin.post_message.assert_called_once_with(
        mtype=plexrefreshrecent.MessageType.SiteMessage,
        title="【Plex最近3天元数据刷新】",
        text="元数据刷新完成，刷新条数：7",
    )


def test_init_plugin_schedules_onlyonce_and_stop_releases_scheduler(monkeypatch) -> None:
    """配置重载先停止旧调度器，一次性任务加入后启动，并可再次停止。"""
    plugin = _plugin(enabled=False)
    plugin._scheduler = None
    helper = MagicMock()
    scheduler = MagicMock()
    scheduler.get_jobs.side_effect = [["job"], ["job"]]
    scheduler.running = False
    monkeypatch.setattr(plexrefreshrecent, "MediaServerHelper", MagicMock(return_value=helper))
    monkeypatch.setattr(plexrefreshrecent, "BackgroundScheduler", MagicMock(return_value=scheduler))
    plugin.update_config = MagicMock()

    plugin.init_plugin(
        {
            "enabled": True,
            "notify": True,
            "onlyonce": True,
            "force": True,
            "cron": "0 8 * * *",
            "offset_days": "2",
            "limit": "25",
            "mediaservers": ["Plex A"],
        }
    )

    assert plugin.get_state() is True
    scheduler.add_job.assert_called_once()
    assert scheduler.add_job.call_args.kwargs["trigger"] == "date"
    scheduler.start.assert_called_once_with()
    plugin.update_config.assert_called_once_with(
        {
            "onlyonce": False,
            "cron": "0 8 * * *",
            "enabled": True,
            "offset_days": 2,
            "notify": True,
            "limit": 25,
            "force": True,
            "mediaservers": ["Plex A"],
        }
    )

    plugin.stop_service()

    scheduler.remove_all_jobs.assert_called_once_with()
    assert plugin._scheduler is None


def test_get_service_exposes_cron_registration_and_rejects_invalid_expression() -> None:
    """周期服务通过宿主服务注册合同暴露，非法 cron 不应让插件加载失败。"""
    plugin = _plugin()
    services = plugin.get_service()
    assert len(services) == 1
    assert services[0]["id"] == "PlexRefreshRecent"
    assert services[0]["func"] == plugin.refresh_recent

    plugin._cron = "invalid"
    assert plugin.get_service() == []


def test_empty_api_and_page_capability_are_explicit() -> None:
    """没有扩展 API 或详情页时不向宿主声明对应能力。"""
    plugin = _plugin()
    assert plugin.get_api() == []
    assert plugin.get_page() is None
    assert supports_plugin_hook(plugin, "get_page") is False
