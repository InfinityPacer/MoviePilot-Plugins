"""BrushFlowLowFreq 种子信息与媒体识别合同测试。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, PropertyMock, patch

from app.plugins.brushflowlowfreq import BrushFlowLowFreq
from app.schemas.types import MediaSource, MediaType
from .torrent_sdk_fixtures import force_transmission_plugin, make_tr_legacy_torrent, make_tr_v7_torrent


def _call(torrent):
    plugin = force_transmission_plugin(object.__new__(BrushFlowLowFreq))
    with patch.object(BrushFlowLowFreq, "service_info", new_callable=PropertyMock, return_value=object()):
        return plugin._BrushFlowLowFreq__get_torrent_info(torrent)


class TestTransmissionTorrentInfo:
    """TR 新旧 SDK 字段都应可转换为刷流统计信息。"""

    def test_transmission_rpc_v7_fields(self):
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
    plugin.subscribe_oper = MagicMock()
    plugin.subscribe_oper.list.return_value = [
        SimpleNamespace(
            id=1,
            name="测试电影",
            year="2026",
            season=None,
            type="电影",
            media_source=MediaSource.TMDB,
            media_id="12345",
        )
    ]
    plugin.chain = MagicMock()
    plugin.chain.recognize_media.return_value = SimpleNamespace(
        names=["Test Movie"],
        to_dict=lambda: {},
    )

    titles = plugin._BrushFlowLowFreq__get_subscribe_titles()

    assert titles == {"测试电影", "Test Movie"}
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
    plugin.subscribe_oper = MagicMock()
    plugin.subscribe_oper.list.return_value = [
        SimpleNamespace(
            id=2,
            name="测试音乐",
            type=MediaType.MUSIC.value,
        )
    ]
    plugin.chain = MagicMock()

    titles = plugin._BrushFlowLowFreq__get_subscribe_titles()

    assert titles == set()
    plugin.chain.recognize_media.assert_not_called()


def test_v3_plugin_version_increments_minor_version():
    assert BrushFlowLowFreq.plugin_version == "4.5"
