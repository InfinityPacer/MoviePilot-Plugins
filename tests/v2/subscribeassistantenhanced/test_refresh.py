"""pending/refresh.py EpisodesRefresh 覆盖单测。"""
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
        source="",
        reason="",
    )


def _refresh(store=None):
    store = store if store is not None else {}

    def update_fn(key, updater):
        data = store.get(key, {})
        result = updater(data)
        store[key] = result
        return result

    def test_scope_builder(_subscribe, mediainfo, _tmdb_episodes):
        """从测试媒体对象构造最小 scope，生产代码仍统一使用 build_scope。"""
        episodes = []
        for info in mediainfo.season_info:
            if info["season_number"] == 1:
                episodes = info["episodes"]
                break
        return SimpleNamespace(episodes=episodes)

    r = PendingRefresh(
        task_data_read=lambda key: store.get(key, {}),
        task_data_update=update_fn,
        subscribe_get_fn=lambda subscribe_id: SimpleNamespace(
            id=subscribe_id, tmdbid=100, season=1, episode_group=None
        ),
        tmdb_episodes_fn=lambda *_args, **_kwargs: [],
        scope_builder_fn=test_scope_builder,
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

    def test_pending_overrides_total(self):
        """P 状态时覆盖 total 为已播出集数。"""
        store = {"subscribes": {"1": {"state": "P"}}}
        r = _refresh(store)
        mi = _mi_with_eps([_ep(1), _ep(2), _ep(3)])
        ev = _event(current_total=12, mediainfo=mi)
        r.handle_refresh(ev)
        assert ev.updated is True
        assert ev.total_episode == 3

    def test_pending_uses_aired_count_when_tmdb_total_missing(self):
        """TMDB 总集数缺失时直接按已播集数覆盖，不依赖虚拟默认总集数配置。"""
        store = {"subscribes": {"1": {"state": "P"}}}
        mi = _mi_with_eps([_ep(i) for i in range(1, 6)])

        event = _event(current_total=0, mediainfo=mi)
        _refresh(store).handle_refresh(event)

        assert event.updated is True
        assert event.total_episode == 5

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

    def test_max_effective_total_monotonic(self):
        """max_effective_total 单调递增。"""
        store = {"subscribes": {"1": {"state": "P", "max_effective_total": 5}}}
        r = _refresh(store)
        mi = _mi_with_eps([_ep(1), _ep(2), _ep(3)])  # aired=3 < max=5
        ev = _event(current_total=12, mediainfo=mi)
        r.handle_refresh(ev)
        assert ev.total_episode == 5  # 使用 max(5, 3)=5

    def test_aired_count_increases_max(self):
        """新集播出递增 max。"""
        store = {"subscribes": {"1": {"state": "P", "max_effective_total": 3}}}
        r = _refresh(store)
        mi = _mi_with_eps([_ep(1), _ep(2), _ep(3), _ep(4), _ep(5)])  # aired=5 > max=3
        ev = _event(current_total=12, mediainfo=mi)
        r.handle_refresh(ev)
        assert ev.total_episode == 5
        assert store["subscribes"]["1"]["max_effective_total"] == 5

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

    def test_episode_group_uses_unified_scope(self):
        """P 刷新必须按订阅 episode_group 查询集列表，而不是读取主季 season_info。"""
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

        assert event.total_episode == 3
        tmdb_episodes.assert_called_once_with(100, 1, episode_group="eg-1")
