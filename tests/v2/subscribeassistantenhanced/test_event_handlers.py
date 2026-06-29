"""事件处理器配置门控集成测试。"""
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.events import EventProxy
from subscribeassistantenhanced.pause.airing import AiringPauseChecker


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


def test_on_subscribe_added_movie_pre_air_pause():
    """电影订阅在上映窗口前新增时进入暂停。"""
    subscribe = _sub(season=0, type="电影")
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    pause_manager = MagicMock()
    airing_checker = AiringPauseChecker(
        pause_days=14,
        evaluate_fn=MagicMock(),
        movie_air_days=7,
        tv_air_days=0,
    )
    release_date = (date.today() + timedelta(days=30)).isoformat()
    mediainfo = SimpleNamespace(type="movie", release_date=release_date)
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        pause_manager=pause_manager,
        airing_checker=airing_checker,
        mediainfo_from_dict=lambda _data: mediainfo,
        is_tv_fn=lambda _mediainfo: False,
    )

    proxy.on_subscribe_added(
        SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {"release_date": release_date}})
    )

    pause_manager.pause.assert_called_once()
    assert pause_manager.pause.call_args.args[0] is subscribe
    assert pause_manager.pause.call_args.args[1].reason == "pre_air"


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
    """新建分集洗版订阅先回填媒体库已有集。"""
    subscribe = _sub(best_version=1)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    priority_manager = MagicMock()
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        priority_manager=priority_manager,
        detect_existing_episodes_fn=MagicMock(return_value=[1, 2]),
        backfill_enabled=True,
    )

    proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {}}))

    priority_manager.backfill_existing.assert_called_once_with(
        subscribe, [1, 2], scene="plugin_backfill<订阅助手（增强版）>"
    )
