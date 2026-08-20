"""PlexPersonMeta V3 媒体身份与专用数据源边界测试。"""

from types import ModuleType
from unittest.mock import MagicMock

from app.schemas.types import MediaSource, MediaType
from app.testing import stub_modules


_pypinyin = ModuleType("pypinyin")
_pypinyin.lazy_pinyin = lambda *_args, **_kwargs: []

with stub_modules({"pypinyin": _pypinyin}):
    from app.plugins import plexpersonmeta as _plugin
    from app.plugins.plexpersonmeta import scrape as _scrape


def test_v3_plugin_version_increments_minor_version():
    """V3 插件入口沿用现有主版本并提升小版本。"""
    assert _plugin.PlexPersonMeta.plugin_version == "2.4.1"


def test_tmdb_media_uses_unified_source_identity():
    """通用媒体识别必须用 TMDB 来源与原生 ID 组成显式身份。"""
    helper = object.__new__(_scrape.ScrapeHelper)
    helper.chain = MagicMock()
    expected = object()
    helper.chain.recognize_media.return_value = expected

    result = _scrape.ScrapeHelper.get_tmdb_media.__wrapped__(
        helper,
        tmdbid=550,
        title="搏击俱乐部",
        mtype=MediaType.MOVIE,
    )

    assert result is expected
    helper.chain.recognize_media.assert_called_once_with(
        mtype=MediaType.MOVIE,
        media_source=MediaSource.TMDB,
        media_id="550",
    )


def test_tmdb_media_rejects_non_video_media():
    """人物刮削只支持电影和电视剧，不把 V3 音乐身份传入影视识别链。"""
    helper = object.__new__(_scrape.ScrapeHelper)
    helper.chain = MagicMock()

    result = _scrape.ScrapeHelper.get_tmdb_media.__wrapped__(
        helper,
        tmdbid=550,
        title="测试音乐",
        mtype=MediaType.MUSIC,
    )

    assert result is None
    helper.chain.recognize_media.assert_not_called()


def test_tmdb_person_detail_keeps_dedicated_tmdb_chain():
    """人物详情属于 TMDB 专用能力，不经过通用媒体识别链。"""
    helper = object.__new__(_scrape.ScrapeHelper)
    helper.tmdb_chain = MagicMock()
    expected = object()
    helper.tmdb_chain.person_detail.return_value = expected

    result = _scrape.ScrapeHelper.get_tmdb_person_detail.__wrapped__(
        helper,
        person_tmdbid=287,
    )

    assert result is expected
    helper.tmdb_chain.person_detail.assert_called_once_with(287)


def test_plex_tmdb_guid_is_only_used_to_extract_external_identity():
    """Plex 外部 GUID 仅负责提取 TMDB ID，不承担媒体识别。"""
    item = {
        "Guid": [
            {"id": "imdb://tt0137523"},
            {"id": "tmdb://550"},
        ],
    }

    assert _scrape.ScrapeHelper.get_tmdb_id(item) == 550
