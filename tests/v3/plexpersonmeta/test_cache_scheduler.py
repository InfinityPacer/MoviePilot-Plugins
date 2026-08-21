"""PlexPersonMeta 缓存清理任务的调度与执行测试。"""

from types import ModuleType
from unittest.mock import MagicMock, call, patch

from apscheduler.schedulers.background import BackgroundScheduler
from app.testing import stub_modules


_pypinyin = ModuleType("pypinyin")
_pypinyin.lazy_pinyin = lambda *_args, **_kwargs: []

with stub_modules({"pypinyin": _pypinyin}):
    from app.plugins.plexpersonmeta import helper as _helper
    from app.plugins.plexpersonmeta import scrape as _scrape


def test_clear_cache_can_be_registered_as_a_no_argument_job():
    """清理缓存任务必须能被 APScheduler 按无参数函数注册。"""
    scheduler = BackgroundScheduler()
    try:
        job = scheduler.add_job(func=_scrape.ScrapeHelper.clear_cache, trigger="date")
        assert job.func is _scrape.ScrapeHelper.clear_cache
    finally:
        scheduler.remove_all_jobs()


def test_clear_cache_clears_the_regions_used_by_cache_decorator():
    """清理操作应作用于装饰器实际使用的三个缓存分区。"""
    cache_backend = MagicMock()

    with patch.object(_scrape, "cache_backend", cache_backend):
        _scrape.ScrapeHelper.clear_cache()

    assert cache_backend.clear.call_args_list == [
        call(region="plex_tmdb_media"),
        call(region="plex_tmdb_person"),
        call(region="plex_douban_media"),
    ]
    cache_backend.close.assert_not_called()


def test_cache_decorator_preserves_none_sentinel_and_hit_semantics():
    """缓存装饰器仍应缓存限流结果，并在命中时跳过业务函数。"""
    cache_backend = MagicMock()
    calls = MagicMock()

    @_helper.cache_with_logging("plex_tmdb_person", "PERSON")
    def fetch_person():
        calls()
        return None

    with patch.object(_helper, "cache_backend", cache_backend):
        cache_backend.exists.return_value = False
        assert fetch_person() is None

        cache_backend.exists.return_value = True
        cache_backend.get.return_value = "None"
        assert fetch_person() is None

    assert calls.call_count == 1
    cache_backend.set.assert_called_once()
