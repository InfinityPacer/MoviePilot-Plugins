"""download/torrent.py TorrentAdapter 单测。"""
from types import SimpleNamespace

from qbittorrentapi.torrents import TorrentInfoList

from subscribeassistantenhanced.download.torrent import TorrentAdapter, TorrentInfo
from ..torrent_sdk_fixtures import make_tr_v7_torrent


class TestTorrentInfoHelpers:
    """TorrentInfo 统一属性：下载器适配层和巡检逻辑共用。"""

    def test_tag_completion_and_progress_helpers(self):
        info = TorrentInfo(
            hash="abc",
            title="测试",
            progress=0.25,
            downloaded=25,
            target_size=100,
            completed=False,
            tags=["订阅", "洗版"],
        )

        assert TorrentAdapter.get_tags(info) == ["订阅", "洗版"]
        assert TorrentAdapter.is_completed(info) == (False, 0.0)
        assert TorrentAdapter.progress_percent(info) == 25.0


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

    def test_qbittorrent_api_torrent_dictionary(self):
        """qB SDK TorrentDictionary 应保持 dict 风格字段读取。"""
        qb = TorrentInfoList([{
            "hash": "sdk123", "name": "SDK Torrent",
            "state": "downloading", "progress": 0.5,
            "total_size": 1000, "size": 500, "downloaded": 500,
            "uploaded": 100, "ratio": 0.2,
            "tags": "tag1, tag2", "tracker": "https://tracker",
        }])[0]

        info = TorrentAdapter.from_qb(qb)

        assert info.hash == "sdk123"
        assert info.title == "SDK Torrent"
        assert info.completed is True
        assert info.target_size == 500
        assert info.tags == ["tag1", "tag2"]

    def test_qb_negative_completion_on_does_not_complete(self):
        """qB completion_on=-1 表示尚未完成，不能当做种时间或完成信号。"""
        qb = {
            "hash": "pending", "state": "downloading",
            "completion_on": -1, "downloaded": 10,
            "size": 100, "total_size": 100,
        }

        info = TorrentAdapter.from_qb(qb)

        assert info.completed is False
        assert info.seeding_time == 0

    def test_qb_positive_completion_on_builds_seeding_time(self, monkeypatch):
        """qB completion_on 为正数时表示完成时间戳，可换算为做种时长。"""
        monkeypatch.setattr("subscribeassistantenhanced.download.torrent.time.time", lambda: 2000)
        qb = {
            "hash": "done-time", "state": "downloading",
            "completion_on": 1900, "downloaded": 10,
            "size": 100, "total_size": 100,
        }

        info = TorrentAdapter.from_qb(qb)

        assert info.completed is True
        assert info.seeding_time == 100

    def test_qb_state_enum_complete_marks_done(self):
        """qB SDK state_enum.is_complete 为真时，应优先按下载器完成态处理。"""
        qb = SimpleNamespace(
            hash="enum-done", name="", state="downloading",
            state_enum=SimpleNamespace(is_complete=True),
            downloaded=10, size=100, total_size=100,
        )

        info = TorrentAdapter.from_qb(qb)

        assert info.completed is True

    def test_qb_state_enum_errors_fall_back_to_state(self):
        """qB SDK 动态属性异常不应打断映射，按普通状态和体积兜底判断。"""
        class _BrokenStateEnumTorrent(dict):
            @property
            def state_enum(self):
                raise RuntimeError("state enum unavailable")

        qb = _BrokenStateEnumTorrent({
            "hash": "enum-error", "state": "downloading",
            "downloaded": 10, "size": 100, "total_size": 100,
        })

        info = TorrentAdapter.from_qb(qb)

        assert info.completed is False

    def test_qb_state_enum_complete_flag_errors_are_ignored(self):
        """qB state_enum 对象存在但完成标记异常时，应继续走状态兜底。"""
        class _BrokenCompleteFlag:
            @property
            def is_complete(self):
                raise RuntimeError("complete flag unavailable")

        qb = SimpleNamespace(
            hash="enum-flag-error", name="", state="downloading",
            state_enum=_BrokenCompleteFlag(),
            downloaded=10, size=100, total_size=100,
        )

        info = TorrentAdapter.from_qb(qb)

        assert info.completed is False

    def test_qb_invalid_ratio_falls_back_to_zero(self):
        """qB ratio 可能来自外部 SDK 原始值，异常值按 0 处理。"""
        qb = {
            "hash": "bad-ratio", "state": "downloading",
            "downloaded": 10, "size": 100, "total_size": 100,
            "ratio": "bad",
        }

        info = TorrentAdapter.from_qb(qb)

        assert info.ratio == 0.0

    def test_tracker_lazy_load_failure_does_not_break_mapping(self):
        """qB tracker lazy API 异常不应打断主种子信息映射。"""
        class _QbTorrent(dict):
            @property
            def trackers(self):
                raise RuntimeError("tracker api unavailable")

        qb = _QbTorrent({
            "hash": "tracker-fail", "name": "Tracker Fail",
            "state": "downloading", "progress": 0.5,
            "total_size": 1000, "size": 1000, "downloaded": 500,
            "tags": "",
        })

        info = TorrentAdapter.from_qb(qb)

        assert info.hash == "tracker-fail"
        assert info.tracker_responses == []

    def test_completed_torrent(self):
        qb = {"hash": "done", "state": "uploading", "progress": 1.0}
        info = TorrentAdapter.from_qb(qb)
        assert info.completed is True
        assert info.completion_time == 0.0

    def test_qb_zero_target_size_does_not_complete_by_size(self):
        """qB 目标大小缺失时不能用 0>=0 提前释放下载待定。"""
        qb = {
            "hash": "zero", "state": "downloading",
            "downloaded": 0, "size": 0, "total_size": 0,
        }

        info = TorrentAdapter.from_qb(qb)

        assert info.completed is False
        assert info.progress == 0.0

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
        """QB Tracker 响应读取 trackers.msg，供删除关键字监听使用。"""
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

    def test_tracker_responses_from_qb_dict_trackers(self):
        """QB tracker 列表项可能是 dict 或 SDK 对象，均应读取 msg。"""
        qb = {
            "hash": "tracker", "state": "downloading",
            "downloaded": 100, "size": 1000, "total_size": 1000,
            "trackers": [
                {"tier": 0, "msg": "torrent not registered"},
                {"tier": -1, "msg": "ignored"},
                {"tier": 1, "msg": ""},
            ],
        }
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

    def test_transmission_rpc_v7_fields(self):
        """transmission-rpc 7.x 真实 Torrent 字段名应可正常读取。"""
        info = TorrentAdapter.from_tr(make_tr_v7_torrent(
            downloadedEver=4096000,
            totalSize=8192000,
            sizeWhenDone=4096000,
        ))

        assert info.hash == "tr_hash_1"
        assert info.target_size == 4096000
        assert info.completed is True
        assert info.dltime == 100
        assert info.seeding_time == 200
        assert info.avg_upspeed == 300
        assert info.add_on == 900
        assert info.tags == ["tag1"]
        assert info.tracker == "https://tracker/announce"
        assert info.tracker_responses == ["OK"]

    def test_completed(self):
        tr = SimpleNamespace(
            hashString="tr", progress=100.0,
            name="", status="", totalSize=1000,
            downloadedEver=1000, uploadedEver=0,
            uploadRatio=0, secondsDownloading=0,
            secondsSeeding=10, rateUpload=0,
            addedDate=0, labels=[], trackers=[],
            trackerStats=[],
        )
        info = TorrentAdapter.from_tr(tr)
        assert info.completed is True

    def test_tr_zero_target_size_does_not_complete_by_size(self):
        """TR 目标大小缺失时不能用 0>=0 提前释放下载待定。"""
        tr = SimpleNamespace(
            hashString="tr-zero", progress=0.0,
            name="", status="downloading", totalSize=0,
            downloadedEver=0, uploadedEver=0,
            uploadRatio=0, secondsDownloading=0,
            secondsSeeding=0, rateUpload=0,
            addedDate=0, labels=[], trackers=[],
            trackerStats=[],
        )

        info = TorrentAdapter.from_tr(tr)

        assert info.completed is False
        assert info.target_size == 0

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

    def test_zero_size_when_done_falls_back_to_total_size(self):
        """TR sizeWhenDone=0 不代表完成目标为 0，应回退到全种大小。"""
        tr = SimpleNamespace(
            hashString="tr-zero-selected", progress=0.0,
            name="", status="downloading", totalSize=2000,
            sizeWhenDone=0, downloadedEver=0,
            uploadedEver=0, uploadRatio=0, secondsDownloading=60,
            secondsSeeding=0, rateUpload=0, addedDate=0,
            labels=[], trackers=[], trackerStats=[],
            fields={"sizeWhenDone"},
        )

        info = TorrentAdapter.from_tr(tr)

        assert info.target_size == 2000
        assert info.completed is False

    def test_snake_case_object_does_not_complete_early(self):
        """TR snake_case 字段必须正确读取，不能因大小为 0 被误判完成。"""
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
