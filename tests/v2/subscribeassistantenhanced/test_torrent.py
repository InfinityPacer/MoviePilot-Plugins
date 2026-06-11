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
