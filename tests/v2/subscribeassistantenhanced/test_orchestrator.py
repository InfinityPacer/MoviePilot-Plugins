"""best_version/orchestrator.py 洗版编排单测。"""
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.schemas.types import MediaType

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


class TestModeLabel:
    """洗版模式标签只描述真实洗版订阅。"""

    def test_non_best_version_returns_empty_label(self):
        """普通订阅不是洗版形态，标签应为空避免日志误标。"""
        assert BestVersionOrchestrator._mode_label(_sub(best_version=0)) == ""

    def test_episode_and_full_best_version_labels(self):
        """分集 / 全集洗版按 best_version_full 区分。"""
        assert BestVersionOrchestrator._mode_label(_sub(best_version=1, best_version_full=0)) == "分集洗版"
        assert BestVersionOrchestrator._mode_label(_sub(best_version=1, best_version_full=1)) == "全集洗版"


class TestHistoryClear:
    """洗版清理：源文件 / 媒体库文件删除经注入回调（mock 不触达真实文件系统）。"""

    def _orch_clear(self, store=None, clear_history_type="all",
                    torrent_exists_fn=None, sleep_fn=None):
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
            notify_fn=lambda t, x=None, **kwargs: notifies.append((t, x, kwargs)),
            get_subscribe_image_fn=lambda subscribe: "subscribe.jpg",
            clear_history_type=clear_history_type,
            torrent_exists_fn=torrent_exists_fn,
            sleep_fn=sleep_fn,
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
        notifies = []
        orch, store, deletes, events, hist_deletes = self._orch_clear()
        orch._notify = lambda title, text=None, **kwargs: notifies.append((title, text, kwargs))
        orch._get_histories = lambda tmdbid, mtype, season=None: [h]
        sub = _sub(name="X", total_episode=0, lack_episode=0)
        orch.handle_resource_download_history_clear(sub)
        assert deletes == [{"path": "/src/a.mkv"}]
        assert events == [("/src/a.mkv", "hashA")]   # 携带旧 download_hash → 主程序删历史种子
        assert hist_deletes == ["1"]
        assert "100" in store["best_version_clear_histories"]   # 快照 key 为 str(tmdbid)
        assert notifies[0][0].endswith("即将开始全集洗版下载")
        assert "全集洗版" in notifies[0][1]
        assert notifies[0][2]["image"] == "subscribe.jpg"
        assert store["best_version_clear_histories"]["100"]["subscribe_image"] == "subscribe.jpg"

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

    def test_full_best_version_incomplete_resource_skips_history_clear_and_notifies(self):
        """全集资源明确未覆盖目标范围时不得删除旧文件，并通知用户人工检查。"""
        orch, _store, deletes, events, hist_deletes = self._orch_clear()
        orch._get_histories = MagicMock(return_value=[
            self._history("1", {"path": "/src/a.mkv"}, None, "/src/a.mkv", "hashA"),
        ])
        notify = MagicMock()
        orch._notify = notify
        context = SimpleNamespace(
            selected_episodes=None,
            torrent_info=SimpleNamespace(title="测试剧 S01E01-E02", description="两集资源"),
        )

        result = orch.handle_resource_download_history_clear(
            _sub(start_episode=1, total_episode=12),
            context=context,
            episodes=[1, 2],
        )

        assert result is True
        orch._get_histories.assert_not_called()
        assert deletes == []
        assert events == []
        assert hist_deletes == []
        assert notify.call_args.args[0].endswith("洗版资源未覆盖目标范围，已跳过历史清理")
        assert "目标集数：" in notify.call_args.args[1]
        assert "资源集数：" in notify.call_args.args[1]
        assert "来源：下载事件" in notify.call_args.args[1]
        assert "种子：测试剧 S01E01-E02" in notify.call_args.args[1]
        assert notify.call_args.kwargs["image"] == "subscribe.jpg"

    def test_movie_clear_type_skips_tv_subscription(self):
        """电影清理范围不应读取电视剧洗版历史。"""
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(clear_history_type="movie")
        orch._get_histories = MagicMock(return_value=[object()])
        sub = _sub()

        orch.handle_resource_download_history_clear(sub)

        orch._get_histories.assert_not_called()

    def test_tv_clear_type_processes_tv_subscription(self):
        """电视剧清理按主程序整理历史使用的 Sxx 季号查询。"""
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(clear_history_type="tv")
        orch._get_histories = MagicMock(return_value=[])
        sub = _sub()

        orch.handle_resource_download_history_clear(sub)

        orch._get_histories.assert_called_once_with(100, "电视剧", "S01")

    def test_tv_history_clear_skips_when_season_is_missing(self):
        """电视剧缺少季号时不得退化为查询并清理同一 TMDB 的全部季。"""
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(clear_history_type="tv")
        orch._get_histories = MagicMock()

        result = orch.handle_resource_download_history_clear(_sub(season=None))

        assert result is True
        orch._get_histories.assert_not_called()

    def test_tv_history_clear_skips_when_season_is_invalid(self):
        """电视剧季号无法格式化时不得退化为查询并清理全部季。"""
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(clear_history_type="tv")
        orch._get_histories = MagicMock()

        result = orch.handle_resource_download_history_clear(_sub(season="invalid"))

        assert result is True
        orch._get_histories.assert_not_called()

    def test_history_clear_waits_until_all_old_hashes_disappear(self):
        """旧种仍存在时每 5 秒复查，全部释放后才允许继续下载。"""
        histories = [
            self._history("1", {"path": "/src/a.mkv"}, None, "/src/a.mkv", "hashA"),
            self._history("2", {"path": "/src/b.mkv"}, None, "/src/b.mkv", "hashB"),
        ]
        states = {
            "hashA": iter([True, False]),
            "hashB": iter([True, True, False]),
        }
        checks = []
        sleeps = []

        def torrent_exists(download_hash):
            checks.append(download_hash)
            return next(states[download_hash])

        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(
            torrent_exists_fn=torrent_exists,
            sleep_fn=lambda seconds: sleeps.append(seconds),
        )
        orch._get_histories = MagicMock(return_value=histories)

        result = orch.handle_resource_download_history_clear(_sub())

        assert result is True
        assert sleeps == [5, 5, 5]
        assert checks.count("hashA") == 2
        assert checks.count("hashB") == 3

    def test_history_clear_always_waits_five_seconds_before_first_query(self):
        """即使旧种已不存在，也必须先等待删除事件处理 5 秒再查询。"""
        history = self._history("1", {"path": "/src/a.mkv"}, None, "/src/a.mkv", "hashA")
        actions = []
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(
            torrent_exists_fn=lambda _hash: actions.append("query") or False,
            sleep_fn=lambda seconds: actions.append(f"sleep:{seconds}"),
        )
        orch._get_histories = MagicMock(return_value=[history])

        result = orch.handle_resource_download_history_clear(_sub())

        assert result is True
        assert actions == ["sleep:5", "query"]

    def test_history_clear_without_hash_still_waits_five_seconds_and_allows(self):
        """整理记录没有 hash 时仍保留首轮删除处理窗口，随后直接放行。"""
        history = self._history("1", {"path": "/src/a.mkv"}, None, "/src/a.mkv", None)
        sleeps = []
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(
            torrent_exists_fn=MagicMock(),
            sleep_fn=lambda seconds: sleeps.append(seconds),
        )
        orch._get_histories = MagicMock(return_value=[history])

        result = orch.handle_resource_download_history_clear(_sub())

        assert result is True
        assert sleeps == [5]

    def test_history_clear_existing_hash_allows_after_three_minutes(self):
        """旧种持续存在时每 5 秒确认，最多等待 3 分钟后降级放行。"""
        history = self._history("1", {"path": "/src/a.mkv"}, None, "/src/a.mkv", "hashA")
        sleeps = []
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(
            torrent_exists_fn=lambda _hash: True,
            sleep_fn=lambda seconds: sleeps.append(seconds),
        )
        orch._get_histories = MagicMock(return_value=[history])

        result = orch.handle_resource_download_history_clear(_sub())

        assert result is True
        assert sleeps == [5] * 36

    def test_history_clear_query_failure_allows_after_one_minute(self):
        """下载器查询失败时每 5 秒重试，最多等待 1 分钟后降级放行。"""
        history = self._history("1", {"path": "/src/a.mkv"}, None, "/src/a.mkv", "hashA")
        sleeps = []
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(
            torrent_exists_fn=lambda _hash: None,
            sleep_fn=lambda seconds: sleeps.append(seconds),
        )
        orch._get_histories = MagicMock(return_value=[history])

        result = orch.handle_resource_download_history_clear(_sub())

        assert result is True
        assert sleeps == [5] * 12

    def test_history_clear_handles_mixed_hash_states_and_always_allows(self):
        """多 hash 分别不存在、查询失败和持续存在时，均按各自上限移除并最终放行。"""
        histories = [
            self._history("1", {"path": "/src/a.mkv"}, None, "/src/a.mkv", "absent"),
            self._history("2", {"path": "/src/b.mkv"}, None, "/src/b.mkv", "failed"),
            self._history("3", {"path": "/src/c.mkv"}, None, "/src/c.mkv", "present"),
        ]
        checks = {"absent": 0, "failed": 0, "present": 0}

        def torrent_exists(download_hash):
            checks[download_hash] += 1
            return {"absent": False, "failed": None, "present": True}[download_hash]

        sleeps = []
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(
            torrent_exists_fn=torrent_exists,
            sleep_fn=lambda seconds: sleeps.append(seconds),
        )
        orch._get_histories = MagicMock(return_value=histories)

        result = orch.handle_resource_download_history_clear(_sub())

        assert result is True
        assert checks == {"absent": 1, "failed": 12, "present": 36}
        assert sleeps == [5] * 36

    def test_transfer_intercept_clear_deletes_dest_and_removes_snapshot(self):
        notifies = []
        store = {"best_version_clear_histories": {"100": {
            "subscribe_desc": "X",
            "mode_label": "全集洗版",
            "subscribe_image": "subscribe.jpg",
            "histories": [{"dest_fileitem": {"path": "/dest/a.mkv"}}],
            "time": time.time(),
        }}}
        orch, store, deletes, _e, _h = self._orch_clear(store)
        orch._notify = lambda title, text=None, **kwargs: notifies.append((title, text, kwargs))
        event = SimpleNamespace(event_data=SimpleNamespace(
            cancel=False, mediainfo=SimpleNamespace(tmdb_id=100)))
        orch.handle_history_clear(event)
        assert deletes == [{"path": "/dest/a.mkv"}]
        assert "100" not in store["best_version_clear_histories"]
        assert notifies[0][0] == "X 即将开始全集洗版整理"
        assert "全集洗版" in notifies[0][1]
        assert notifies[0][2]["image"] == "subscribe.jpg"

    def test_transfer_intercept_without_snapshot_returns_false(self):
        """无洗版清理快照时整理拦截不产生日志噪音。"""
        orch, _store, _deletes, _events, _hist = self._orch_clear({})
        event = SimpleNamespace(event_data=SimpleNamespace(
            cancel=False, mediainfo=SimpleNamespace(tmdb_id=100)))

        assert orch.handle_history_clear(event) is False

    def test_transfer_intercept_clear_returns_true(self):
        """命中清理快照并完成清理时返回 True，供事件层输出结果日志。"""
        store = {"best_version_clear_histories": {"100": {
            "subscribe_desc": "X", "mode_label": "全集洗版", "histories": [], "time": time.time(),
        }}}
        orch, _store, _deletes, _events, _hist = self._orch_clear(store)
        event = SimpleNamespace(event_data=SimpleNamespace(
            cancel=False, mediainfo=SimpleNamespace(tmdb_id=100)))

        assert orch.handle_history_clear(event) is True

    def test_transfer_intercept_drops_expired_history_without_deleting_dest(self):
        """超过 72 小时的清理事务失效，不得删除旧媒体库目标文件。"""
        store = {"best_version_clear_histories": {"100": {
            "subscribe_desc": "X",
            "histories": [{"dest_fileitem": {"path": "/dest/a.mkv"}}],
            "time": time.time() - 73 * 3600,
        }}}
        orch, _store, deletes, _events, _histories = self._orch_clear(store)
        event = SimpleNamespace(event_data=SimpleNamespace(
            cancel=False, mediainfo=SimpleNamespace(tmdb_id=100)))

        assert orch.handle_history_clear(event) is False

        assert deletes == []
        assert "100" in store["best_version_clear_histories"]

    def test_cleanup_expired_clear_histories_keeps_recent_tasks(self):
        """通用清理只移除超过 72 小时的洗版清理事务。"""
        now = time.time()
        store = {"best_version_clear_histories": {
            "expired": {"time": now - 73 * 3600},
            "recent": {"time": now - 71 * 3600},
        }}
        orch, _store, _deletes, _events, _histories = self._orch_clear(store)

        assert orch.cleanup_expired_clear_histories() == 1

        assert set(store["best_version_clear_histories"]) == {"recent"}


class TestStartBestVersion:
    """订阅完成后按洗版类型自动创建洗版订阅。"""

    def _orch(self, oper, best_version_type="all", related_downloads_fn=None):
        """构造带自动洗版类型范围的编排器。"""
        return BestVersionOrchestrator(
            priority_manager=MagicMock(spec=PriorityManager), evaluate_fn=MagicMock(),
            subscribe_oper=oper, best_version_type=best_version_type,
            related_downloads_fn=related_downloads_fn)

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
        assert notify.call_args.args[0].endswith("已添加全集洗版订阅")
        _args, kwargs = oper.add.call_args
        assert kwargs["best_version"] == 1 and kwargs["season"] == 1
        assert kwargs["best_version_full"] == 1
        assert kwargs["filter"] == "r"
        assert kwargs["filter_groups"] == ["g1"]

    def test_create_failure_notifies_error_and_image(self):
        """自动创建洗版订阅失败时应推送主程序返回的错误原因。"""
        oper = MagicMock()
        oper.add.return_value = (None, "订阅已存在")
        notify = MagicMock()
        orch = BestVersionOrchestrator(
            priority_manager=MagicMock(spec=PriorityManager),
            evaluate_fn=MagicMock(),
            subscribe_oper=oper,
            best_version_type="all",
            notify_fn=notify,
        )
        sub = _sub(best_version=0)

        sid = orch.start_best_version(sub, mediainfo=_mediainfo())

        assert sid is None
        notify.assert_called_once()
        assert notify.call_args.args[0].endswith("添加洗版订阅失败！")
        assert notify.call_args.args[1] == "订阅已存在"
        assert notify.call_args.kwargs["image"] == "poster.jpg"

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
        sub = _sub(best_version=0, type=MediaType.MOVIE)

        sid = self._orch(oper, best_version_type="movie").start_best_version(sub, object())

        assert sid == 6
        oper.add.assert_called_once()
        _args, kwargs = oper.add.call_args
        assert "best_version_full" not in kwargs

    def test_unknown_media_type_skips_all_scope(self):
        """未知媒体类型不能被 all 范围误当成剧集创建洗版。"""
        oper = MagicMock()
        sub = _sub(best_version=0, type=MediaType.UNKNOWN)

        sid = self._orch(oper, best_version_type="all").start_best_version(sub, object())

        assert sid is None
        oper.add.assert_not_called()

    def test_no_type_skips_all_subscriptions(self):
        """关闭洗版类型范围时不应创建任何洗版订阅。"""
        oper = MagicMock()
        sub = _sub(best_version=0, type="电影")

        sid = self._orch(oper, best_version_type="no").start_best_version(sub, object())

        assert sid is None
        oper.add.assert_not_called()

    def test_tv_episode_skips_without_related_episode_downloads(self):
        """分集洗版：没有关联分集下载历史时不自动创建洗版订阅。"""
        oper = MagicMock()
        sub = _sub(best_version=0, type="电视剧")
        related = MagicMock(return_value=[])

        sid = self._orch(
            oper,
            best_version_type="tv_episode",
            related_downloads_fn=related,
        ).start_best_version(sub, object())

        assert sid is None
        related.assert_called_once_with(sub)
        oper.add.assert_not_called()

    def test_tv_episode_skips_single_related_episode_download(self):
        """分集洗版：只有 1 条关联下载历史视为合集/单次下载，不自动洗版。"""
        oper = MagicMock()
        sub = _sub(best_version=0, type="电视剧")

        sid = self._orch(
            oper,
            best_version_type="tv_episode",
            related_downloads_fn=MagicMock(return_value=[object()]),
        ).start_best_version(sub, object())

        assert sid is None
        oper.add.assert_not_called()

    def test_tv_episode_creates_when_multiple_related_episode_downloads(self):
        """分集洗版：存在多条关联分集下载历史时创建洗版订阅。"""
        oper = MagicMock()
        oper.add.return_value = (7, "")
        sub = _sub(best_version=0, type="电视剧")

        sid = self._orch(
            oper,
            best_version_type="tv_episode",
            related_downloads_fn=MagicMock(return_value=[object(), object()]),
        ).start_best_version(sub, object())

        assert sid == 7
        oper.add.assert_called_once()
        _args, kwargs = oper.add.call_args
        assert kwargs["best_version_full"] == 1
