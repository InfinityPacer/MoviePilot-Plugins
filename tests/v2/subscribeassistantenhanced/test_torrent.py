"""download/torrent.py TorrentAdapter 单测。"""
from types import SimpleNamespace

from subscribeassistantenhanced.download.torrent import TorrentAdapter, TorrentInfo


class TestFromQB:

    def test_basic_mapping(self):
        qb = {
            "hash": "abc123", "name": "Test Torrent",
            "state": "downloading", "progress": 0.5,
            "total_size": 1000, "downloaded": 500,
            "uploaded": 100, "ratio": 0.2,
            "tags": "tag1, tag2",
        }
        info = TorrentAdapter.from_qb(qb)
        assert info.hash == "abc123"
        assert info.title == "Test Torrent"
        assert info.progress == 0.5
        assert info.completed is False
        assert info.tags == ["tag1", "tag2"]

    def test_completed_torrent(self):
        qb = {"hash": "done", "progress": 1.0}
        info = TorrentAdapter.from_qb(qb)
        assert info.completed is True
        assert info.completion_time == 0.0

    def test_completed_uses_selected_size(self):
        """QB 按已选文件大小 size 判断完成，避免部分选文件时被 total_size 误判未完成。"""
        qb = {
            "hash": "partial", "state": "downloading", "progress": 0.5,
            "downloaded": 500, "size": 500, "total_size": 1000,
        }
        info = TorrentAdapter.from_qb(qb)
        assert info.completed is True
        assert info.target_size == 500

    def test_tracker_responses_from_qb_trackers(self):
        """QB Tracker 响应沿用旧版 trackers.msg 口径，供删除关键字监听使用。"""
        qb = {
            "hash": "tracker", "state": "downloading",
            "downloaded": 100, "size": 1000, "total_size": 1000,
        }
        qb = SimpleNamespace(
            get=qb.get,
            trackers=[
                SimpleNamespace(tier=0, msg="torrent not registered"),
                SimpleNamespace(tier=-1, msg="ignored"),
                SimpleNamespace(tier=1, msg=""),
            ],
        )
        info = TorrentAdapter.from_qb(qb)
        assert info.tracker_responses == ["torrent not registered"]

    def test_empty_tags(self):
        info = TorrentAdapter.from_qb({"hash": "h", "tags": ""})
        assert info.tags == []


class TestFromTR:

    def test_basic_mapping(self):
        tr = SimpleNamespace(
            hashString="tr123", name="TR Torrent",
            status="downloading", progress=50.0,
            totalSize=2000, downloadedEver=1000,
            uploadedEver=500, uploadRatio=0.5,
            secondsDownloading=3600, secondsSeeding=0,
            rateUpload=1000, addedDate=0,
            labels=["label1"], trackers=[], trackerStats=[],
        )
        info = TorrentAdapter.from_tr(tr)
        assert info.hash == "tr123"
        assert info.progress == 0.5
        assert info.completed is False
        assert info.tags == ["label1"]

    def test_completed(self):
        tr = SimpleNamespace(
            hashString="tr", progress=100.0,
            name="", status="", totalSize=0,
            downloadedEver=0, uploadedEver=0,
            uploadRatio=0, secondsDownloading=0,
            secondsSeeding=0, rateUpload=0,
            addedDate=0, labels=[], trackers=[],
            trackerStats=[],
        )
        info = TorrentAdapter.from_tr(tr)
        assert info.completed is True

    def test_completed_uses_size_when_done(self):
        """TR 按 size_when_done 判断完成，兼容只选择部分文件下载的种子。"""
        tr = SimpleNamespace(
            hashString="tr-partial", progress=50.0,
            name="", status="downloading", totalSize=2000,
            size_when_done=1000, downloadedEver=1000,
            uploadedEver=0, uploadRatio=0, secondsDownloading=60,
            secondsSeeding=0, rateUpload=0, addedDate=0,
            labels=[], trackers=[], trackerStats=[],
            fields={"size_when_done"},
        )
        info = TorrentAdapter.from_tr(tr)
        assert info.completed is True
        assert info.target_size == 1000

    def test_legacy_snake_case_object_does_not_complete_early(self):
        """TR 旧版 snake_case 字段必须正确读取，不能因大小为 0 被误判完成。"""
        tr = SimpleNamespace(
            hashString="tr-snake", progress=50.0,
            name="", status="downloading", total_size=2000,
            size_when_done=1500, ratio=0, fields={"size_when_done"},
            date_done=None, date_added=None, date_active=None,
            tracker_stats=[], labels=[],
        )
        tr.get = lambda key, default=None: default
        info = TorrentAdapter.from_tr(tr)
        assert info.total_size == 2000
        assert info.target_size == 1500
        assert info.downloaded == 1000
        assert info.completed is False


class TestGetInfo:

    def test_qbittorrent(self):
        info = TorrentAdapter.get_info({"hash": "q", "progress": 0.5}, "qbittorrent")
        assert isinstance(info, TorrentInfo)
        assert info.hash == "q"

    def test_transmission(self):
        tr = SimpleNamespace(
            hashString="t", progress=50.0,
            name="", status="", totalSize=0,
            downloadedEver=0, uploadedEver=0,
            uploadRatio=0, secondsDownloading=0,
            secondsSeeding=0, rateUpload=0,
            addedDate=0, labels=[], trackers=[],
            trackerStats=[],
        )
        info = TorrentAdapter.get_info(tr, "transmission")
        assert info.hash == "t"

    def test_invalid_raises(self):
        import pytest
        with pytest.raises(ValueError):
            TorrentAdapter.get_info({}, "unknown")
