"""增强版订阅助手测试共享 fixtures。"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock


@pytest.fixture
def mock_task_manager():
    """模拟 TaskDataManager，内存存储。"""
    store = {}
    mgr = MagicMock()
    mgr.read.side_effect = lambda key: store.get(key, {})
    mgr.write.side_effect = lambda key, data: store.__setitem__(key, data)

    def update_fn(key, updater):
        data = store.get(key, {})
        result = updater(data)
        store[key] = result
        return result

    mgr.update.side_effect = update_fn
    mgr._store = store
    return mgr


@pytest.fixture
def make_subscribe():
    """构建 Subscribe 模拟对象。"""
    def _make(**kwargs):
        defaults = dict(
            id=1, name="测试剧", tmdbid=12345, doubanid=None,
            year=None, season=1, episode_group=None, type="电视剧",
            state="R", best_version=0, current_priority=0,
            best_version_full=0, episode_priority={},
            total_episode=12, start_episode=1, lack_episode=0,
            username="", filter=None, filter_groups=[],
            save_path=None, sites=None, date=None, last_update=None,
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)
    return _make


@pytest.fixture
def make_mediainfo():
    """构建 MediaInfo 模拟对象。"""
    def _make(**kwargs):
        defaults = dict(
            tmdb_id=12345,
            type=SimpleNamespace(value="电视剧"),
            season_info=[],
            release_date=None,
            first_air_date=None,
            next_episode_to_air=None,
            tmdb_info=SimpleNamespace(
                status="Returning Series",
                next_episode_to_air=None,
                last_episode_to_air=None,
                seasons=[],
            ),
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)
    return _make


@pytest.fixture
def make_episode():
    """构建 TmdbEpisode 模拟对象。"""
    def _make(**kwargs):
        defaults = dict(
            episode_number=1, season_number=1,
            air_date="2026-01-01", name="E1",
            episode_type="standard",
        )
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)
    return _make
