"""pending/refresh.py EpisodesRefresh 观察单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.pending.refresh import PendingRefresh


def _event(subscribe_id=1, current_total=12, season=1, mediainfo=None):
    return SimpleNamespace(
        subscribe_id=subscribe_id,
        current_total_episode=current_total,
        season=season,
        mediainfo=mediainfo or SimpleNamespace(season_info=[], tmdb_info={}),
        total_episode=None,
        updated=False,
        source="main",
        reason="keep",
    )


def _refresh(store=None):
    store = store if store is not None else {}

    def update_fn(key, updater):
        data = store.get(key, {})
        result = updater(data)
        store[key] = result
        return result

    r = PendingRefresh(
        task_data_read=lambda key: store.get(key, {}),
        task_data_update=update_fn,
        subscribe_get_fn=lambda subscribe_id: SimpleNamespace(
            id=subscribe_id, tmdbid=100, season=1, episode_group=None
        ),
        tmdb_episodes_fn=lambda *_args, **_kwargs: [],
    )
    r._store = store
    return r


def _mi_with_eps(episodes):
    return SimpleNamespace(season_info=[{
        "season_number": 1,
        "episodes": episodes,
    }], tmdb_info={})


def _ep(num, air_date="2026-01-01"):
    return SimpleNamespace(episode_number=num, air_date=air_date, episode_type="standard")


class TestPendingRefresh:

    def test_pending_does_not_override_total(self):
        """P 状态只保护生命周期，不覆盖主程序计算出的 total。"""
        store = {"subscribes": {"1": {"state": "P"}}}
        r = _refresh(store)
        mi = _mi_with_eps([_ep(1), _ep(2), _ep(3)])
        ev = _event(current_total=12, mediainfo=mi)

        r.handle_refresh(ev)

        assert ev.updated is False
        assert ev.total_episode is None
        assert ev.source == "main"
        assert ev.reason == "keep"
        assert "max_effective_total" not in store["subscribes"]["1"]

    def test_pending_does_not_inject_total_when_tmdb_total_missing(self):
        """TMDB 总集数缺失时，P 状态也不注入虚拟 total。"""
        store = {"subscribes": {"1": {"state": "P"}}}
        mi = _mi_with_eps([_ep(i) for i in range(1, 6)])

        event = _event(current_total=0, mediainfo=mi)
        _refresh(store).handle_refresh(event)

        assert event.updated is False
        assert event.total_episode is None
        assert event.source == "main"
        assert event.reason == "keep"

    def test_not_pending_no_override(self):
        """R 状态时不覆盖。"""
        store = {"subscribes": {"1": {"state": "R"}}}
        r = _refresh(store)
        mi = _mi_with_eps([_ep(1), _ep(2)])
        ev = _event(current_total=12, mediainfo=mi)
        r.handle_refresh(ev)
        assert ev.updated is False

    def test_no_subscribe_id_skips(self):
        """subscribe_id=None 时跳过。"""
        store = {"subscribes": {"1": {"state": "P"}}}
        r = _refresh(store)
        ev = _event(subscribe_id=None)
        r.handle_refresh(ev)
        assert ev.updated is False

    def test_existing_max_effective_total_is_ignored(self):
        """历史 max_effective_total 只作为旧数据残留，不再影响刷新事件。"""
        store = {"subscribes": {"1": {"state": "P", "max_effective_total": 5}}}
        r = _refresh(store)
        mi = _mi_with_eps([_ep(1), _ep(2), _ep(3)])
        ev = _event(current_total=12, mediainfo=mi)

        r.handle_refresh(ev)

        assert ev.updated is False
        assert ev.total_episode is None
        assert store["subscribes"]["1"]["max_effective_total"] == 5

    def test_aired_count_does_not_update_max_effective_total(self):
        """已播集数增长不再写入待定搜索范围。"""
        store = {"subscribes": {"1": {"state": "P", "max_effective_total": 3}}}
        r = _refresh(store)
        mi = _mi_with_eps([_ep(1), _ep(2), _ep(3), _ep(4), _ep(5)])
        ev = _event(current_total=12, mediainfo=mi)

        r.handle_refresh(ev)

        assert ev.updated is False
        assert ev.total_episode is None
        assert store["subscribes"]["1"]["max_effective_total"] == 3

    def test_aired_equals_total_no_override(self):
        """已播数 >= total 时不覆盖。"""
        store = {"subscribes": {"1": {"state": "P"}}}
        r = _refresh(store)
        mi = _mi_with_eps([_ep(i) for i in range(1, 13)])  # aired=12
        ev = _event(current_total=12, mediainfo=mi)
        r.handle_refresh(ev)
        assert ev.updated is False

    def test_no_episodes_no_override(self):
        """无集信息时不覆盖。"""
        store = {"subscribes": {"1": {"state": "P"}}}
        r = _refresh(store)
        ev = _event(current_total=12, mediainfo=SimpleNamespace(season_info=[], tmdb_info={}))
        r.handle_refresh(ev)
        assert ev.updated is False

    def test_episode_group_does_not_override_total_or_query_scope(self):
        """P 刷新不再查询剧集组并覆盖 total。"""
        store = {"subscribes": {"1": {"state": "P"}}}
        subscribe = SimpleNamespace(
            id=1,
            name="测试剧",
            tmdbid=100,
            season=1,
            episode_group="eg-1",
            total_episode=12,
            lack_episode=0,
        )
        tmdb_episodes = MagicMock(return_value=[_ep(1), _ep(2), _ep(3)])
        refresh = PendingRefresh(
            task_data_read=lambda key: store.get(key, {}),
            task_data_update=lambda key, updater: store.__setitem__(
                key, updater(store.get(key, {}))
            ),
            subscribe_get_fn=lambda _subscribe_id: subscribe,
            tmdb_episodes_fn=tmdb_episodes,
        )
        event = _event(
            current_total=12,
            mediainfo=_mi_with_eps([_ep(i) for i in range(1, 13)]),
        )

        refresh.handle_refresh(event)

        assert event.updated is False
        assert event.total_episode is None
        assert event.source == "main"
        assert event.reason == "keep"
        tmdb_episodes.assert_not_called()
