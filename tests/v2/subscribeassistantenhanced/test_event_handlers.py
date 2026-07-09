"""事件处理器配置门控集成测试。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.events import EventProxy


def _sub(**kwargs):
    """构造完整订阅替身。"""
    defaults = dict(
        id=7,
        name="测试",
        tmdbid=100,
        season=1,
        episode_group=None,
        type="电视剧",
        best_version=0,
        best_version_full=0,
        total_episode=12,
        lack_episode=0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_skip_deletion_controls_deleted_resource_filtering():
    """删除指纹过滤仅在 skip_deletion 开启时剔除候选。"""
    candidate = SimpleNamespace(
        torrent_info=SimpleNamespace(
            enclosure="http://x/deleted.torrent",
            page_url="http://x/details/1",
        )
    )
    deletes_store = MagicMock()
    deletes_store.match.return_value = True

    allowed_data = SimpleNamespace(
        contexts=[candidate],
        updated=False,
        updated_contexts=None,
        source="",
    )
    EventProxy(
        deletes_store=deletes_store,
        skip_deletion=False,
    ).on_resource_selection(SimpleNamespace(event_data=allowed_data))

    assert allowed_data.updated is False
    assert allowed_data.contexts == [candidate]

    filtered_data = SimpleNamespace(
        contexts=[candidate],
        updated=False,
        updated_contexts=None,
        source="",
    )
    EventProxy(
        deletes_store=deletes_store,
        skip_deletion=True,
    ).on_resource_selection(SimpleNamespace(event_data=filtered_data))

    assert filtered_data.updated is True
    assert filtered_data.updated_contexts == []


def test_on_subscribe_added_delegates_lifecycle_with_mediainfo():
    """SubscribeAdded 只负责取订阅和媒体信息，状态流转交给 lifecycle。"""
    subscribe = _sub(season=0, type="电影")
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    lifecycle = MagicMock()
    mediainfo = SimpleNamespace(type="movie")
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        lifecycle=lifecycle,
        mediainfo_from_dict=lambda _data: mediainfo,
    )

    proxy.on_subscribe_added(
        SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {"release_date": "2026-08-01"}})
    )

    lifecycle.handle_subscribe_added.assert_called_once_with(subscribe, mediainfo)


def test_on_subscribe_added_missing_mediainfo_skips_lifecycle():
    """事件缺少媒体信息时不进入 lifecycle，避免生命周期层收到无效上下文。"""
    subscribe = _sub()
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    lifecycle = MagicMock()
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        lifecycle=lifecycle,
        mediainfo_from_dict=lambda _data: None,
    )

    proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": None}))

    lifecycle.handle_subscribe_added.assert_not_called()


def test_subscribe_modified_skips_backfill_when_disabled():
    """关闭回填开关时，普通转洗版不写入已有集优先级。"""
    subscribe = _sub(best_version=1)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    priority_manager = MagicMock()
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        priority_manager=priority_manager,
        detect_existing_episodes_fn=MagicMock(return_value=[3]),
        backfill_enabled=False,
    )

    proxy.on_subscribe_modified(SimpleNamespace(event_data={
        "subscribe_id": 7,
        "subscribe_info": {"best_version": 1},
        "old_subscribe_info": {"best_version": 0},
    }))

    priority_manager.backfill_existing.assert_not_called()


def test_subscribe_modified_backfills_existing_episodes_when_enabled():
    """开启回填开关时，普通转洗版为媒体库已有集写入优先级。"""
    subscribe = _sub(best_version=1)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    priority_manager = MagicMock()
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        priority_manager=priority_manager,
        detect_existing_episodes_fn=MagicMock(return_value=[3]),
        backfill_enabled=True,
    )

    proxy.on_subscribe_modified(SimpleNamespace(event_data={
        "subscribe_id": 7,
        "subscribe_info": {"best_version": 1},
        "old_subscribe_info": {"best_version": 0},
    }))

    priority_manager.backfill_existing.assert_called_once_with(
        subscribe, [3], scene="plugin_backfill<订阅助手（增强版）>"
    )


def test_subscribe_added_backfills_episode_best_version():
    """新建分集洗版订阅先回填媒体库已有集，再交给 lifecycle。"""
    call_order = []
    subscribe = _sub(best_version=1)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    priority_manager = MagicMock()
    priority_manager.can_backfill.return_value = True
    priority_manager.backfill_existing.side_effect = lambda *_args, **_kwargs: call_order.append("backfill")
    lifecycle = MagicMock()
    lifecycle.handle_subscribe_added.side_effect = lambda *_args, **_kwargs: call_order.append("lifecycle")
    mediainfo = SimpleNamespace(type="tv")
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        priority_manager=priority_manager,
        detect_existing_episodes_fn=MagicMock(return_value=[1, 2]),
        backfill_enabled=True,
        lifecycle=lifecycle,
        mediainfo_from_dict=lambda _data: mediainfo,
    )

    proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {}}))

    priority_manager.backfill_existing.assert_called_once_with(
        subscribe, [1, 2], scene="plugin_backfill<订阅助手（增强版）>"
    )
    lifecycle.handle_subscribe_added.assert_called_once_with(subscribe, mediainfo)
    assert call_order == ["backfill", "lifecycle"]
