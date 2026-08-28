"""PlexPersonMeta V3 媒体身份与专用数据源边界测试。"""

import json
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

from app.schemas.types import MediaSource, MediaType
from app.sdk.utilities import convert
from app.testing import stub_modules

_pypinyin = ModuleType("pypinyin")
_pypinyin.lazy_pinyin = lambda *_args, **_kwargs: []

with stub_modules({"pypinyin": _pypinyin}):
    from app.plugins.plexpersonmeta import PlexPersonMeta as _plugin
    from app.plugins.plexpersonmeta import scrape as _scrape


def test_v3_plugin_uses_stable_sdk_imports():
    """V3 专用副本不应继续依赖已登记的旧导入兼容层。"""
    plugin_root = Path(__file__).parents[3] / "plugins.v3" / "plexpersonmeta"
    source = "\n".join(path.read_text(encoding="utf-8") for path in plugin_root.glob("*.py"))

    assert "from app.core." not in source
    assert "from app.helper." not in source
    assert "from app.log import" not in source
    assert "from app.utils." not in source
    assert "from app.sdk." in source

    plugin = object.__new__(_plugin)
    assert _plugin.get_command() == []
    assert plugin.get_api() == []
    assert plugin.get_page() == []


def test_v3_version_history_and_legacy_index_are_consistent():
    """V3 索引、插件类版本与旧代禁用标记必须保持一致。"""
    repo_root = Path(__file__).parents[3]
    package_v3 = json.loads((repo_root / "package.v3.json").read_text(encoding="utf-8"))
    package_v2 = json.loads((repo_root / "package.v2.json").read_text(encoding="utf-8"))
    metadata = package_v3["PlexPersonMeta"]

    assert _plugin.plugin_version == "2.7"
    assert metadata["version"] == _plugin.plugin_version
    assert list(metadata["history"]) == ["v2.7"]
    assert metadata["history"]["v2.7"]
    assert metadata["system_version"] == ">=3.0.0"
    assert package_v2["PlexPersonMeta"]["v3"] is False


def test_text_conversion_uses_host_sdk():
    """人物别名转换应由宿主 SDK 选择兼容当前解释器的实现。"""
    assert _scrape.convert is convert


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


def test_tmdb_media_rejects_invalid_source_id():
    """统一媒体身份不应把空值、零值或非数字 TMDB ID 送入识别链。"""
    helper = object.__new__(_scrape.ScrapeHelper)
    helper.chain = MagicMock()

    for tmdbid in (None, "", "0", "not-a-tmdb-id"):
        result = _scrape.ScrapeHelper.get_tmdb_media.__wrapped__(
            helper,
            tmdbid=tmdbid,
            title="测试媒体",
            mtype=MediaType.MOVIE,
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
