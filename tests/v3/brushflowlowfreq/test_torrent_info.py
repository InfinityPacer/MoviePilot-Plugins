"""BrushFlowLowFreq V3 SDK、种子信息与媒体识别合同测试。"""
import ast
import warnings
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from app.plugins.brushflowlowfreq import BrushFlowLowFreq
from app.schemas.types import MediaSource, MediaType
from app.sdk.queries import QueryPage, SubscriptionSnapshot
from .torrent_sdk_fixtures import force_transmission_plugin, make_tr_legacy_torrent, make_tr_v7_torrent


def _call(torrent):
    plugin = force_transmission_plugin(object.__new__(BrushFlowLowFreq))
    with patch.object(BrushFlowLowFreq, "service_info", new_callable=PropertyMock, return_value=object()):
        return plugin._BrushFlowLowFreq__get_torrent_info(torrent)


class TestTransmissionTorrentInfo:
    """TR 新旧 SDK 字段都应可转换为刷流统计信息。"""

    def test_transmission_rpc_v7_fields(self):
        with warnings.catch_warnings():
            warnings.simplefilter("error", DeprecationWarning)
            info = _call(make_tr_v7_torrent())

        assert info["hash"] == "tr_hash_1"
        assert info["seeding_time"] > 0
        assert info["dltime"] > 0
        assert info["iatime"] > 0
        assert info["add_on"] == 900
        assert info["tags"] == ["tag1"]
        assert info["tracker"] == "https://tracker/announce"

    def test_legacy_transmission_fields(self):
        info = _call(make_tr_legacy_torrent())

        assert info["hash"] == "tr_hash_1"
        assert info["seeding_time"] > 0
        assert info["dltime"] > 0
        assert info["iatime"] > 0
        assert info["add_on"] == 900
        assert info["tags"] == ["tag1"]
        assert info["tracker"] == "https://tracker/announce"

def test_subscribe_recognition_uses_v3_media_identity_contract():
    """订阅识别必须以来源和原生 ID 成对调用 V3 媒体识别合同。"""
    plugin = object.__new__(BrushFlowLowFreq)
    plugin._brush_config = SimpleNamespace(except_subscribe=True)
    plugin._subscribe_infos = {}
    subscription = SubscriptionSnapshot(
        id=1,
        name="测试电影",
        year="2026",
        season=None,
        type="电影",
        media_source=MediaSource.TMDB,
        media_id="12345",
    )
    plugin.chain = MagicMock()
    plugin.chain.recognize_media.return_value = SimpleNamespace(
        names=["Test Movie"],
        to_dict=lambda: {},
    )

    page = QueryPage(items=[subscription], total=1, page=1, count=200)
    with patch(
        "app.plugins.brushflowlowfreq.list_subscriptions",
        return_value=page,
    ) as list_subscriptions_mock, patch("app.plugins.brushflowlowfreq.MetaInfo"):
        titles = plugin._BrushFlowLowFreq__get_subscribe_titles()

    assert titles == {"测试电影", "Test Movie"}
    list_subscriptions_mock.assert_called_once()
    assert list_subscriptions_mock.call_args.kwargs["page"].count == 200
    kwargs = plugin.chain.recognize_media.call_args.kwargs
    assert kwargs["media_source"] == MediaSource.TMDB
    assert kwargs["media_id"] == "12345"
    assert "tmdbid" not in kwargs
    assert "doubanid" not in kwargs


def test_subscribe_recognition_ignores_non_video_media():
    """旧实现复用于 V3 时仍只处理电影和电视剧订阅。"""
    plugin = object.__new__(BrushFlowLowFreq)
    plugin._brush_config = SimpleNamespace(except_subscribe=True)
    plugin._subscribe_infos = {}
    subscription = SubscriptionSnapshot(
        id=2,
        name="测试音乐",
        type=MediaType.MUSIC.value,
    )
    plugin.chain = MagicMock()

    with patch(
        "app.plugins.brushflowlowfreq.list_subscriptions",
        return_value=QueryPage(items=[subscription], total=1, page=1, count=200),
    ):
        titles = plugin._BrushFlowLowFreq__get_subscribe_titles()

    assert titles == set()
    plugin.chain.recognize_media.assert_not_called()


def test_configured_site_lookup_uses_site_sdk_index():
    """站点读取使用正式 SDK 返回的配置索引，不构造宿主 SiteOper。"""
    plugin = object.__new__(BrushFlowLowFreq)
    plugin.sites_helper = MagicMock()
    plugin.sites_helper.get_indexers.return_value = [
        {"id": 7, "name": "测试站点", "domain": "example.test"}
    ]

    assert plugin._BrushFlowLowFreq__get_configured_site(7) == {
        "id": 7,
        "name": "测试站点",
        "domain": "example.test",
    }
    assert plugin._BrushFlowLowFreq__get_configured_site(8) is None


def test_subscribe_recognition_reads_all_query_pages():
    """订阅排除匹配必须遍历查询 SDK 返回的全部分页。"""
    plugin = object.__new__(BrushFlowLowFreq)
    plugin._brush_config = SimpleNamespace(except_subscribe=True)
    plugin._subscribe_infos = {}
    subscriptions = [
        SubscriptionSnapshot(
            id=1,
            name="第一页电影",
            year="2026",
            season=None,
            type="电影",
            media_source=MediaSource.TMDB,
            media_id="1",
        ),
        SubscriptionSnapshot(
            id=2,
            name="第二页电影",
            year="2026",
            season=None,
            type="电影",
            media_source=MediaSource.TMDB,
            media_id="2",
        ),
    ]
    plugin.chain = MagicMock()
    plugin.chain.recognize_media.return_value = None

    with patch(
        "app.plugins.brushflowlowfreq.list_subscriptions",
        side_effect=[
            QueryPage(items=subscriptions[:1], total=2, page=1, count=1),
            QueryPage(items=subscriptions[1:], total=2, page=2, count=1),
        ],
    ) as list_subscriptions_mock, patch("app.plugins.brushflowlowfreq.MetaInfo"):
        titles = plugin._BrushFlowLowFreq__get_subscribe_titles()

    assert titles == set()
    assert list_subscriptions_mock.call_count == 2
    assert list_subscriptions_mock.call_args_list[0].kwargs["page"].page == 1
    assert list_subscriptions_mock.call_args_list[1].kwargs["page"].page == 2


def test_subscribe_recognition_skips_unknown_snapshot_media_type():
    """查询 DTO 允许旧脏类型为空或未知，刷流匹配应跳过而不是中断整批。"""
    plugin = object.__new__(BrushFlowLowFreq)
    plugin._brush_config = SimpleNamespace(except_subscribe=True)
    plugin._subscribe_infos = {}
    subscriptions = [
        SubscriptionSnapshot(id=1, name="空类型订阅", type=None),
        SubscriptionSnapshot(id=2, name="未知类型订阅", type="未知"),
    ]
    plugin.chain = MagicMock()

    with patch(
        "app.plugins.brushflowlowfreq.list_subscriptions",
        return_value=QueryPage(items=subscriptions, total=2, page=1, count=200),
    ):
        titles = plugin._BrushFlowLowFreq__get_subscribe_titles()

    assert titles == set()
    plugin.chain.recognize_media.assert_not_called()


def test_v3_plugin_version_increments_minor_version():
    assert BrushFlowLowFreq.plugin_version == "4.6"


def test_v3_plugin_uses_stable_sdk_imports():
    """V3 专用副本使用稳定能力入口且不触发宿主旧导入兼容层。"""
    source_path = Path(__file__).parents[3] / "plugins.v3/brushflowlowfreq/__init__.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert {
        "app.sdk.config",
        "app.sdk.logging",
        "app.sdk.media",
        "app.sdk.network",
        "app.sdk.queries",
        "app.sdk.services",
        "app.sdk.utilities",
    } <= imported_modules
    assert "app.core.config" not in imported_modules
    assert "app.core.context" not in imported_modules
    assert "app.core.metainfo" not in imported_modules
    assert "app.db.site_oper" not in imported_modules
    assert "app.db.subscribe_oper" not in imported_modules
    assert not any(
        module.startswith(
            (
                "app.compat",
                "app.db.models",
                "app.runtime.compat",
                "app.sdk._legacy",
            )
        )
        for module in imported_modules
    )
    assert "app.helper.downloader" not in imported_modules
    assert "app.helper.sites" not in imported_modules
    assert "app.log" not in imported_modules
    assert "app.utils.http" not in imported_modules
    assert "app.utils.string" not in imported_modules


def test_v3_plugin_has_no_http_api():
    assert object.__new__(BrushFlowLowFreq).get_api() == []
