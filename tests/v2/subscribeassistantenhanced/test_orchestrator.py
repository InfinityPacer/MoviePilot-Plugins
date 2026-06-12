"""best_version/orchestrator.py 洗版编排单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.best_version.orchestrator import BestVersionOrchestrator
from subscribeassistantenhanced.best_version.priority import PriorityManager
from subscribeassistantenhanced.engine.types import CompletionSignal


def _mediainfo():
    """构造洗版通知需要的媒体信息替身。"""
    return SimpleNamespace(
        vote_average=8.8,
        get_message_image=lambda: "poster.jpg",
        to_dict=lambda: {"title": "测试剧"},
    )


def _sub(ep_priority=None, episode_group=None, **kwargs):
    defaults = dict(
        id=1, name="测试剧", tmdbid=100, season=1,
        episode_priority=ep_priority or {}, current_priority=0,
        episode_group=episode_group,
        save_path="/media", sites="site1", filter="rule1", filter_groups=["group1"],
        best_version=1, best_version_full=1, type="电视剧",
        total_episode=12, lack_episode=0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _orch(priority_complete=True, signal_stable=True):
    pm = MagicMock(spec=PriorityManager)
    pm.is_complete.return_value = priority_complete
    sig = CompletionSignal(stable=signal_stable)
    evaluate_fn = MagicMock(return_value=sig)
    return BestVersionOrchestrator(
        priority_manager=pm,
        evaluate_fn=evaluate_fn,
    )


class TestCheckComplete:

    def test_all_conditions_met(self):
        """priority 达标 + F 稳定 + 无缺失集 → 完成。"""
        orch = _orch(priority_complete=True, signal_stable=True)
        assert orch.check_complete(_sub(), None, no_exists_episodes=None) is True

    def test_priority_not_complete(self):
        orch = _orch(priority_complete=False, signal_stable=True)
        assert orch.check_complete(_sub(), None) is False

    def test_f_unstable(self):
        orch = _orch(priority_complete=True, signal_stable=False)
        assert orch.check_complete(_sub(), None) is False

    def test_missing_episodes(self):
        """有缺失集 → 不完成。"""
        orch = _orch(priority_complete=True, signal_stable=True)
        assert orch.check_complete(_sub(), None, no_exists_episodes=[5, 6]) is False


class TestBuildPayload:

    def test_preserves_episode_group(self):
        """payload 保留 episode_group。"""
        orch = _orch()
        payload = orch.build_payload(_sub(episode_group="eg-abc"))
        assert payload["episode_group"] == "eg-abc"
        assert payload["best_version"] == 1

    def test_includes_subscribe_fields(self):
        orch = _orch()
        payload = orch.build_payload(_sub())
        assert "name" in payload
        assert "tmdbid" in payload
        assert "season" in payload
        assert "save_path" in payload
        assert payload["filter"] == "rule1"
        assert payload["filter_groups"] == ["group1"]

    def test_no_episode_group(self):
        orch = _orch()
        payload = orch.build_payload(_sub(episode_group=None))
        assert "episode_group" not in payload or payload.get("episode_group") is None


class TestHistoryClear:
    """洗版清理：源文件 / 媒体库文件删除经注入回调（mock 不触达真实文件系统）。"""

    def _orch_clear(self, store=None, clear_history_type="all"):
        """构造可观测清理副作用的洗版编排器。"""
        store = store if store is not None else {}
        deletes, events, notifies, hist_deletes = [], [], [], []
        orch = BestVersionOrchestrator(
            priority_manager=MagicMock(spec=PriorityManager),
            evaluate_fn=MagicMock(),
            task_data_read=lambda k: store.get(k, {}),
            task_data_update=lambda k, fn: store.__setitem__(k, fn(store.get(k, {}))),
            delete_media_file_fn=lambda fi: deletes.append(fi),
            delete_history_fn=lambda hid: hist_deletes.append(hid),
            send_download_file_deleted_fn=lambda src, h: events.append((src, h)),
            notify_fn=lambda t, x=None: notifies.append((t, x)),
            clear_history_type=clear_history_type,
        )
        return orch, store, deletes, events, hist_deletes

    def _history(self, hid, src_fi, dest_fi, src, dl_hash):
        return SimpleNamespace(
            id=hid, src=src, download_hash=dl_hash,
            src_fileitem=src_fi, dest_fileitem=dest_fi,
            to_dict=lambda: {"id": hid, "src": src, "download_hash": dl_hash,
                             "src_fileitem": src_fi, "dest_fileitem": dest_fi},
        )

    def test_resource_download_clear_deletes_src_and_emits_event(self):
        h = self._history("1", {"path": "/src/a.mkv"}, {"path": "/dest/a.mkv"}, "/src/a.mkv", "hashA")
        orch, store, deletes, events, hist_deletes = self._orch_clear()
        orch._get_histories = lambda tmdbid, mtype, season=None: [h]
        sub = _sub(name="X", total_episode=0, lack_episode=0)
        orch.handle_resource_download_history_clear(sub)
        assert deletes == [{"path": "/src/a.mkv"}]
        assert events == [("/src/a.mkv", "hashA")]   # 携带旧 download_hash → 主程序删历史种子
        assert hist_deletes == ["1"]
        assert "100" in store["best_version_clear_histories"]   # 快照 key 为 str(tmdbid)

    def test_clear_type_no_skips(self):
        """清理范围为 no 时不触发任何破坏性历史清理。"""
        orch, store, deletes, _e, _h = self._orch_clear(clear_history_type="no")
        orch._get_histories = lambda *a, **k: [object()]
        sub = _sub()
        orch.handle_resource_download_history_clear(sub)
        assert deletes == []

    def test_partial_best_version_skips(self):
        orch, store, deletes, _e, _h = self._orch_clear()
        orch._get_histories = lambda *a, **k: [object()]
        sub = _sub(best_version_full=0)
        orch.handle_resource_download_history_clear(sub)
        assert deletes == []   # 分集洗版跳过整季清理

    def test_movie_clear_type_skips_tv_subscription(self):
        """电影清理范围不应读取电视剧洗版历史。"""
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(clear_history_type="movie")
        orch._get_histories = MagicMock(return_value=[object()])
        sub = _sub()

        orch.handle_resource_download_history_clear(sub)

        orch._get_histories.assert_not_called()

    def test_tv_clear_type_processes_tv_subscription(self):
        """电视剧清理范围应继续读取电视剧洗版历史。"""
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(clear_history_type="tv")
        orch._get_histories = MagicMock(return_value=[])
        sub = _sub()

        orch.handle_resource_download_history_clear(sub)

        orch._get_histories.assert_called_once_with(100, "电视剧", 1)

    def test_transfer_intercept_clear_deletes_dest_and_removes_snapshot(self):
        store = {"best_version_clear_histories": {"100": {
            "subscribe_desc": "X", "histories": [{"dest_fileitem": {"path": "/dest/a.mkv"}}]}}}
        orch, store, deletes, _e, _h = self._orch_clear(store)
        event = SimpleNamespace(event_data=SimpleNamespace(
            cancel=False, mediainfo=SimpleNamespace(tmdb_id=100)))
        orch.handle_history_clear(event)
        assert deletes == [{"path": "/dest/a.mkv"}]
        assert "100" not in store["best_version_clear_histories"]


class TestStartBestVersion:
    """订阅完成后按洗版类型自动创建洗版订阅。"""

    def _orch(self, oper, best_version_type="all"):
        """构造带自动洗版类型范围的编排器。"""
        return BestVersionOrchestrator(
            priority_manager=MagicMock(spec=PriorityManager), evaluate_fn=MagicMock(),
            subscribe_oper=oper, best_version_type=best_version_type)

    def test_creates_best_version_when_type_enabled(self):
        """创建洗版订阅成功时应发 SubscribeAdded 事件并发送订阅通知。"""
        oper = MagicMock()
        oper.add.return_value = (5, "")
        send_event = MagicMock()
        notify = MagicMock()
        orch = BestVersionOrchestrator(
            priority_manager=MagicMock(spec=PriorityManager),
            evaluate_fn=MagicMock(),
            subscribe_oper=oper,
            best_version_type="all",
            send_subscribe_added_fn=send_event,
            notify_fn=notify,
        )
        sub = _sub(best_version=0, season=1, save_path="/m", sites="s",
                   filter="r", filter_groups=["g1"], episode_group=None)
        sid = orch.start_best_version(sub, mediainfo=_mediainfo())

        assert sid == 5
        send_event.assert_called_once()
        assert send_event.call_args.args[0] == 5
        notify.assert_called_once()
        assert notify.call_args.args[0].endswith("已添加洗版订阅")
        _args, kwargs = oper.add.call_args
        assert kwargs["best_version"] == 1 and kwargs["season"] == 1
        assert kwargs["filter"] == "r"
        assert kwargs["filter_groups"] == ["g1"]

    def test_skips_when_already_best_version(self):
        oper = MagicMock()
        self._orch(oper).start_best_version(_sub(best_version=1), object())
        oper.add.assert_not_called()

    def test_skips_without_mediainfo(self):
        oper = MagicMock()
        self._orch(oper).start_best_version(_sub(best_version=0), None)
        oper.add.assert_not_called()

    def test_tv_type_skips_movie_subscription(self):
        """电视剧洗版范围不应为电影订阅创建洗版。"""
        oper = MagicMock()
        sub = _sub(best_version=0, type="电影")

        sid = self._orch(oper, best_version_type="tv").start_best_version(sub, object())

        assert sid is None
        oper.add.assert_not_called()

    def test_movie_type_creates_movie_subscription(self):
        """电影洗版范围应为电影订阅创建洗版。"""
        oper = MagicMock()
        oper.add.return_value = (6, "")
        sub = _sub(best_version=0, type="电影")

        sid = self._orch(oper, best_version_type="movie").start_best_version(sub, object())

        assert sid == 6
        oper.add.assert_called_once()

    def test_no_type_skips_all_subscriptions(self):
        """关闭洗版类型范围时不应创建任何洗版订阅。"""
        oper = MagicMock()
        sub = _sub(best_version=0, type="电影")

        sid = self._orch(oper, best_version_type="no").start_best_version(sub, object())

        assert sid is None
        oper.add.assert_not_called()
