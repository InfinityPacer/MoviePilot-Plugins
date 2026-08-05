"""PlexPersonMeta 缓存清理任务的调度与执行测试。"""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock, call, patch

from apscheduler.schedulers.background import BackgroundScheduler
from app.testing import stub_modules


def _load_source_module():
    """直接加载插件源码，避免测试误用后端运行时副本。"""
    source_path = Path(__file__).parents[3] / "plugins.v2" / "plexpersonmeta" / "scrape.py"
    module_name = "_plexpersonmeta_source_scrape"
    spec = importlib.util.spec_from_file_location(module_name, source_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


_pypinyin = ModuleType("pypinyin")
_pypinyin.lazy_pinyin = lambda *_args, **_kwargs: []

with stub_modules({"pypinyin": _pypinyin}):
    _scrape = _load_source_module()


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
