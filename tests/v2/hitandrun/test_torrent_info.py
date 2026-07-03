"""HitAndRun 种子信息映射测试。"""
from importlib import import_module

from ..torrent_sdk_fixtures import (
    install_app_plugin_alias,
    make_tr_legacy_torrent,
    make_tr_v7_torrent,
)

install_app_plugin_alias("hitandrun")
TorrentHelper = import_module("app.plugins.hitandrun.helper").TorrentHelper


def _call(torrent):
    helper = object.__new__(TorrentHelper)
    helper.dl_type = "transmission"
    return helper.get_torrent_info(torrent)


class TestTransmissionTorrentInfo:
    """TR 新旧 SDK 字段都应可转换为 H&R 统计信息。"""

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
