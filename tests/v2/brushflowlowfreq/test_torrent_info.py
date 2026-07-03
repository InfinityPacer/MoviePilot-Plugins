"""BrushFlowLowFreq 种子信息映射测试。"""
from pathlib import Path
from unittest.mock import PropertyMock, patch

from brushflowlowfreq import BrushFlowLowFreq
from ..torrent_sdk_fixtures import force_transmission_plugin, make_tr_legacy_torrent, make_tr_v7_torrent


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

    def test_v1_source_keeps_original_transmission_fields(self):
        """v2 已有插件不改 v1，#258 带入的 v1 字段替换应回滚。"""
        source = (Path(__file__).resolve().parents[3] / "plugins" / "brushflowlowfreq" / "__init__.py").read_text()

        assert "torrent.done_date" not in source
        assert "torrent.date_done" in source
