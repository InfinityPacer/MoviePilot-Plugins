"""TorrentClassifier 种子信息映射测试。"""
from unittest.mock import PropertyMock, patch

from ..torrent_sdk_fixtures import (
    force_transmission_plugin,
    install_app_plugin_alias,
    make_tr_legacy_torrent,
    make_tr_v7_torrent,
)

install_app_plugin_alias("torrentclassifier")

from torrentclassifier import TorrentClassifier  # noqa: E402


def _call(torrent):
    plugin = force_transmission_plugin(object.__new__(TorrentClassifier))
    with patch.object(TorrentClassifier, "service_info", new_callable=PropertyMock, return_value=object()):
        return plugin._TorrentClassifier__get_torrent_info(torrent)


class TestTransmissionTorrentInfo:
    """TR 新旧 SDK 字段都应可转换为分类整理统计信息。"""

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
