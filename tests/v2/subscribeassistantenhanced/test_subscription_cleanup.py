"""cleanup/subscription.py 订阅清理单测。"""
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.schemas.types import MediaType

from subscribeassistantenhanced.cleanup.subscription import SubscriptionCleanup


def _sub(**kwargs):
    """构造完整订阅替身，默认包含 Subscribe 固定字段。"""
    defaults = dict(
        id=1, name="测试剧", tmdbid=100, season=1,
        episode_group=None,
        state="R", type="电视剧",
        best_version=1, best_version_full=1,
        start_episode=1, total_episode=12, lack_episode=0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestHistoryClear:
    """订阅清理：源文件 / 媒体库文件删除经注入回调（mock 不触达真实文件系统）。"""

    def _orch_clear(self, store=None, cleanup_history_type="all", cleanup_history_scenes=None,
                    torrent_exists_fn=None, sleep_fn=None):
        """构造可观测清理副作用的订阅清理编排器。"""
        store = store if store is not None else {}
        cleanup_history_scenes = ["best_version_full"] if cleanup_history_scenes is None else cleanup_history_scenes
        sleep_fn = sleep_fn or (lambda _seconds: None)
        deletes, events, notifies, hist_deletes = [], [], [], []
        orch = SubscriptionCleanup(
            task_data_read=lambda k: store.get(k, {}),
            task_data_update=lambda k, fn: store.__setitem__(k, fn(store.get(k, {}))),
            delete_media_file_fn=lambda fi: deletes.append(fi),
            delete_history_fn=lambda hid: hist_deletes.append(hid),
            send_download_file_deleted_fn=lambda src, h: events.append((src, h)),
            notify_fn=lambda t, x=None, **kwargs: notifies.append((t, x, kwargs)),
            get_subscribe_image_fn=lambda subscribe: "subscribe.jpg",
            cleanup_history_type=cleanup_history_type,
            cleanup_history_scenes=cleanup_history_scenes,
            torrent_exists_fn=torrent_exists_fn,
            sleep_fn=sleep_fn,
        )
        return orch, store, deletes, events, hist_deletes

    def _history(self, hid, src_fi, dest_fi, src, dl_hash, episodes="E01"):
        return SimpleNamespace(
            id=hid, src=src, download_hash=dl_hash,
            src_fileitem=src_fi, dest_fileitem=dest_fi, episodes=episodes,
            to_dict=lambda: {"id": hid, "src": src, "download_hash": dl_hash,
                             "src_fileitem": src_fi, "dest_fileitem": dest_fi,
                             "episodes": episodes},
        )

    def _transfer_event(self, episode=1, tmdb_id=100, season=1):
        """构造带目标文件集数的整理拦截事件。"""
        return SimpleNamespace(event_data=SimpleNamespace(
            cancel=False,
            mediainfo=SimpleNamespace(tmdb_id=tmdb_id, type=MediaType.TV, season=season),
            fileitem=SimpleNamespace(path=f"/src/测试剧 S01E{episode:02d}.mkv"),
            target_path=f"/dest/测试剧 S01E{episode:02d}.mkv",
        ))

    def test_resource_download_clear_deletes_src_and_emits_event(self):
        h = self._history("1", {"path": "/src/a.mkv"}, {"path": "/dest/a.mkv"}, "/src/a.mkv", "hashA")
        notifies = []
        orch, store, deletes, events, hist_deletes = self._orch_clear()
        orch._notify = lambda title, text=None, **kwargs: notifies.append((title, text, kwargs))
        orch._get_histories = lambda tmdbid, mtype, season=None: [h]
        sub = _sub(name="X", total_episode=1, lack_episode=0)
        orch.handle_resource_download_history_clear(sub)
        assert deletes == [{"path": "/src/a.mkv"}]
        assert events == [("/src/a.mkv", "hashA")]   # 携带旧 download_hash → 主程序删历史种子
        assert hist_deletes == ["1"]
        assert len(store["subscription_cleanup_histories"]) == 1
        task = next(iter(store["subscription_cleanup_histories"].values()))
        assert task["tmdbid"] == 100
        assert task["target_episodes"] == [1]
        assert notifies[0][0].endswith("即将开始全集洗版下载，已删除 1 条整理记录对应的源文件")
        assert notifies[0][1] == "清理路径：\n/src/a.mkv"
        assert "reason" not in notifies[0][2]
        assert "action" not in notifies[0][2]
        assert notifies[0][2]["image"] == "subscribe.jpg"
        assert task["subscribe_image"] == "subscribe.jpg"

    def test_source_history_clear_logs_final_summary(self, monkeypatch):
        """源文件清理完成后输出最终摘要，便于用户确认破坏性动作结果。"""
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.cleanup.subscription.logger.info", messages.append)
        histories = [
            self._history("1", {"path": "/src/a.mkv"}, {"path": "/dest/a.mkv"}, "/src/a.mkv", "hashA"),
            self._history("2", None, {"path": "/dest/b.mkv"}, "/src/b.mkv", "hashB"),
        ]
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear()

        orch.clear_transfer_src_histories(_sub(), histories)

        assert any(
            "源文件清理完成" in message
            and "整理记录 2/2 条" in message
            and "源文件 1/2 个" in message
            and "下载记录通知 1/1 个" in message
            for message in messages
        )

    def test_dest_history_clear_logs_final_summary(self, monkeypatch):
        """媒体库目标文件清理完成后输出最终摘要，避免只有事前警示。"""
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.cleanup.subscription.logger.info", messages.append)
        histories = [
            {"dest_fileitem": {"path": "/dest/a.mkv"}},
            {"dest_fileitem": None},
        ]
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear()

        assert orch.clear_transfer_dest_histories({
            "subscribe_desc": "测试剧",
            "mode_label": "全集洗版",
            "histories": histories,
        }) is True

        assert any(
            "媒体库文件清理完成" in message
            and "目标文件 1/2 个" in message
            for message in messages
        )

    def test_clear_type_no_skips(self):
        """清理范围为 no 时不触发任何破坏性历史清理。"""
        orch, store, deletes, _e, _h = self._orch_clear(cleanup_history_type="no")
        orch._get_histories = lambda *a, **k: [object()]
        sub = _sub()
        orch.handle_resource_download_history_clear(sub)
        assert deletes == []

    def test_normal_subscription_cleans_when_scene_enabled(self):
        """普通订阅命中订阅清理场景时，复用现有源文件/事件/整理记录清理链路。"""
        h = self._history("1", {"path": "/src/e1.mkv"}, None, "/src/e1.mkv", "hashA", episodes="E01")
        orch, _store, deletes, events, hist_deletes = self._orch_clear(
            cleanup_history_type="tv",
            cleanup_history_scenes=["normal"],
        )
        orch._get_histories = MagicMock(return_value=[h])

        result = orch.handle_resource_download_history_clear(
            _sub(best_version=0, best_version_full=0, total_episode=12),
            episodes=[1],
        )

        assert result is True
        assert deletes == [{"path": "/src/e1.mkv"}]
        assert events == [("/src/e1.mkv", "hashA")]
        assert hist_deletes == ["1"]

    def test_normal_subscription_skips_when_scene_disabled(self):
        """普通订阅未命中订阅清理场景时，不读取也不删除整理记录。"""
        orch, _store, deletes, events, hist_deletes = self._orch_clear(
            cleanup_history_type="tv",
            cleanup_history_scenes=["best_version_full"],
        )
        orch._get_histories = MagicMock(return_value=[object()])

        result = orch.handle_resource_download_history_clear(_sub(best_version=0), episodes=[1])

        assert result is True
        orch._get_histories.assert_not_called()
        assert deletes == []
        assert events == []
        assert hist_deletes == []

    def test_partial_best_version_skips(self):
        orch, store, deletes, _e, _h = self._orch_clear()
        orch._get_histories = lambda *a, **k: [object()]
        sub = _sub(best_version_full=0)
        orch.handle_resource_download_history_clear(sub)
        assert deletes == []   # 场景未命中时分集洗版不触发清理。

    def test_episode_best_version_cleans_when_scene_enabled(self):
        """分集洗版命中订阅清理场景时，不再无条件跳过清理链路。"""
        h = self._history("1", {"path": "/src/e3.mkv"}, None, "/src/e3.mkv", "hashA", episodes="E03")
        orch, _store, deletes, events, hist_deletes = self._orch_clear(
            cleanup_history_type="tv",
            cleanup_history_scenes=["best_version_episode"],
        )
        orch._get_histories = MagicMock(return_value=[h])

        result = orch.handle_resource_download_history_clear(
            _sub(best_version=1, best_version_full=0),
            episodes=[3],
        )

        assert result is True
        assert deletes == [{"path": "/src/e3.mkv"}]
        assert events == [("/src/e3.mkv", "hashA")]
        assert hist_deletes == ["1"]

    def test_tv_history_clear_filters_to_target_episode(self):
        """剧集订阅清理只删除与本次目标集相交的整理记录。"""
        h1 = self._history("1", {"path": "/src/e1.mkv"}, None, "/src/e1.mkv", "h1", episodes="E01")
        h2 = self._history("2", {"path": "/src/e2.mkv"}, None, "/src/e2.mkv", "h2", episodes="E02")
        orch, _store, deletes, events, hist_deletes = self._orch_clear(
            cleanup_history_type="tv",
            cleanup_history_scenes=["normal"],
        )
        orch._get_histories = MagicMock(return_value=[h1, h2])

        result = orch.handle_resource_download_history_clear(_sub(best_version=0), episodes=[2])

        assert result is True
        assert deletes == [{"path": "/src/e2.mkv"}]
        assert events == [("/src/e2.mkv", "h2")]
        assert hist_deletes == ["2"]

    def test_tv_history_clear_matches_episode_ranges(self):
        """整理记录集数为范围时，只要覆盖目标集就纳入清理事务。"""
        history = self._history(
            "1", {"path": "/src/e1e2.mkv"}, None, "/src/e1e2.mkv", "h1", episodes="E01-E02"
        )
        orch, _store, deletes, events, hist_deletes = self._orch_clear(
            cleanup_history_type="tv",
            cleanup_history_scenes=["normal"],
        )
        orch._get_histories = MagicMock(return_value=[history])

        result = orch.handle_resource_download_history_clear(_sub(best_version=0), episodes=[2])

        assert result is True
        assert deletes == [{"path": "/src/e1e2.mkv"}]
        assert events == [("/src/e1e2.mkv", "h1")]
        assert hist_deletes == ["1"]

    def test_tv_history_clear_skips_when_target_episodes_unknown(self):
        """普通订阅无法识别本次目标集时不得退化为整季清理。"""
        orch, _store, deletes, events, hist_deletes = self._orch_clear(
            cleanup_history_type="tv",
            cleanup_history_scenes=["normal"],
        )
        orch._get_histories = MagicMock(return_value=[
            self._history("1", {"path": "/src/e1.mkv"}, None, "/src/e1.mkv", "h1", episodes="E01")
        ])

        result = orch.handle_resource_download_history_clear(_sub(best_version=0), episodes=[])

        assert result is True
        orch._get_histories.assert_not_called()
        assert deletes == []
        assert events == []
        assert hist_deletes == []

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
        assert notify.call_args.kwargs["text"] == (
            "目标集数：E01-E12\n"
            "资源集数：E01-E02\n"
            "种子：测试剧 S01E01-E02"
        )
        assert "reason" not in notify.call_args.kwargs
        assert "action" not in notify.call_args.kwargs
        assert notify.call_args.kwargs["follow_up"] == "请人工核对资源覆盖范围"
        assert notify.call_args.kwargs["diagnostic"] is True
        assert notify.call_args.kwargs["image"] == "subscribe.jpg"

    def test_movie_clear_type_skips_tv_subscription(self):
        """电影清理范围不应读取电视剧洗版历史。"""
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(cleanup_history_type="movie")
        orch._get_histories = MagicMock(return_value=[object()])
        sub = _sub()

        orch.handle_resource_download_history_clear(sub)

        orch._get_histories.assert_not_called()

    def test_tv_clear_type_processes_tv_subscription(self):
        """电视剧清理按主程序整理历史使用的 Sxx 季号查询。"""
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(cleanup_history_type="tv")
        orch._get_histories = MagicMock(return_value=[])
        sub = _sub()

        orch.handle_resource_download_history_clear(sub)

        orch._get_histories.assert_called_once_with(100, "电视剧", "S01")

    def test_tv_history_clear_skips_when_season_is_missing(self):
        """电视剧缺少季号时不得退化为查询并清理同一 TMDB 的全部季。"""
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(cleanup_history_type="tv")
        orch._get_histories = MagicMock()

        result = orch.handle_resource_download_history_clear(_sub(season=None))

        assert result is True
        orch._get_histories.assert_not_called()

    def test_tv_history_clear_skips_when_season_is_invalid(self):
        """电视剧季号无法格式化时不得退化为查询并清理全部季。"""
        orch, _store, _deletes, _events, _hist_deletes = self._orch_clear(cleanup_history_type="tv")
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
        """整理记录没有 hash 时仍按原洗版清理逻辑发送事件，并保留首轮删除处理窗口。"""
        history = self._history("1", {"path": "/src/a.mkv"}, None, "/src/a.mkv", None)
        sleeps = []
        orch, _store, _deletes, events, _hist_deletes = self._orch_clear(
            torrent_exists_fn=MagicMock(),
            sleep_fn=lambda seconds: sleeps.append(seconds),
        )
        orch._get_histories = MagicMock(return_value=[history])

        result = orch.handle_resource_download_history_clear(_sub())

        assert result is True
        assert events == [("/src/a.mkv", None)]
        assert sleeps == [5]

    def test_history_without_hash_and_src_still_emits_deleted_event(self):
        """整理记录缺少 hash 和 src 时也保持原洗版清理的事件发送语义。"""
        history = self._history("1", {"path": "/src/a.mkv"}, None, None, None)
        orch, _store, _deletes, events, _hist_deletes = self._orch_clear(
            sleep_fn=lambda _seconds: None,
        )
        orch._get_histories = MagicMock(return_value=[history])

        result = orch.handle_resource_download_history_clear(_sub())

        assert result is True
        assert events == [(None, None)]

    def test_history_without_src_fileitem_does_not_emit_deleted_event(self):
        """整理记录没有源文件元数据时不发送删种事件，即使路径和 hash 仍有值。"""
        history = self._history("1", None, None, "/src/a.mkv", "hashA")
        orch, _store, _deletes, events, _hist_deletes = self._orch_clear(
            sleep_fn=lambda _seconds: None,
        )
        orch._get_histories = MagicMock(return_value=[history])

        result = orch.handle_resource_download_history_clear(_sub())

        assert result is True
        assert events == []

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

    def test_same_tmdb_episode_tasks_do_not_overwrite_each_other(self):
        """同一 TMDB 的不同集清理事务必须并存，并在整理拦截时按集消费。"""
        h1 = self._history("1", {"path": "/src/e1.mkv"}, {"path": "/dest/e1.mkv"},
                           "/src/e1.mkv", "h1", episodes="E01")
        h2 = self._history("2", {"path": "/src/e2.mkv"}, {"path": "/dest/e2.mkv"},
                           "/src/e2.mkv", "h2", episodes="E02")
        orch, store, deletes, _events, _hist_deletes = self._orch_clear(
            cleanup_history_type="tv",
            cleanup_history_scenes=["normal"],
            sleep_fn=lambda _seconds: None,
        )
        orch._get_histories = MagicMock(return_value=[h1, h2])

        assert orch.handle_resource_download_history_clear(_sub(best_version=0), episodes=[1]) is True
        assert orch.handle_resource_download_history_clear(_sub(best_version=0), episodes=[2]) is True
        assert len(store["subscription_cleanup_histories"]) == 2

        assert orch.handle_history_clear(self._transfer_event(episode=1)) is True
        assert deletes[-1] == {"path": "/dest/e1.mkv"}
        assert len(store["subscription_cleanup_histories"]) == 1
        assert next(iter(store["subscription_cleanup_histories"].values()))["target_episodes"] == [2]

        assert orch.handle_history_clear(self._transfer_event(episode=2)) is True
        assert deletes[-1] == {"path": "/dest/e2.mkv"}
        assert store["subscription_cleanup_histories"] == {}

    def test_transfer_intercept_out_of_order_episode_consumes_matching_task(self):
        """整理事件乱序到达时不得把 S01E02 路径中的 S01 误当作 E01 消费。"""
        store = {"subscription_cleanup_histories": {
            "task-e1": {
                "tmdbid": 100,
                "type": "电视剧",
                "season": "S01",
                "target_episodes": [1],
                "subscribe_desc": "X",
                "mode_label": "普通订阅",
                "histories": [{"dest_fileitem": {"path": "/dest/e1.mkv"}}],
                "time": time.time(),
            },
            "task-e2": {
                "tmdbid": 100,
                "type": "电视剧",
                "season": "S01",
                "target_episodes": [2],
                "subscribe_desc": "X",
                "mode_label": "普通订阅",
                "histories": [{"dest_fileitem": {"path": "/dest/e2.mkv"}}],
                "time": time.time(),
            },
        }}
        orch, _store, deletes, _events, _histories = self._orch_clear(store)

        assert orch.handle_history_clear(self._transfer_event(episode=2)) is True

        assert deletes == [{"path": "/dest/e2.mkv"}]
        assert set(store["subscription_cleanup_histories"]) == {"task-e1"}

    def test_transfer_intercept_tv_task_requires_matching_season(self):
        """电视剧清理事务有季号时，整理事件缺少季号不得降级消费。"""
        store = {"subscription_cleanup_histories": {"task-e1": {
            "tmdbid": 100,
            "type": "电视剧",
            "season": "S01",
            "target_episodes": [1],
            "subscribe_desc": "X",
            "mode_label": "普通订阅",
            "histories": [{"dest_fileitem": {"path": "/dest/e1.mkv"}}],
            "time": time.time(),
        }}}
        orch, _store, deletes, _events, _histories = self._orch_clear(store)
        event = SimpleNamespace(event_data=SimpleNamespace(
            cancel=False,
            mediainfo=SimpleNamespace(tmdb_id=100, type=MediaType.TV),
            fileitem=SimpleNamespace(path="/src/测试剧 S01E01.mkv"),
            target_path="/dest/测试剧 S01E01.mkv",
        ))

        assert orch.handle_history_clear(event) is False

        assert deletes == []
        assert "task-e1" in store["subscription_cleanup_histories"]

    def test_transfer_intercept_clear_deletes_dest_and_removes_snapshot(self):
        notifies = []
        store = {"subscription_cleanup_histories": {"task-1": {
            "tmdbid": 100,
            "type": "电视剧",
            "season": "S01",
            "scene": "best_version_full",
            "target_episodes": [1],
            "subscribe_desc": "X",
            "mode_label": "全集洗版",
            "subscribe_image": "subscribe.jpg",
            "histories": [{"dest_fileitem": {"path": "/dest/a.mkv"}}],
            "time": time.time(),
        }}}
        orch, store, deletes, _e, _h = self._orch_clear(store)
        orch._notify = lambda title, text=None, **kwargs: notifies.append((title, text, kwargs))
        event = self._transfer_event(episode=1)
        orch.handle_history_clear(event)
        assert deletes == [{"path": "/dest/a.mkv"}]
        assert "task-1" not in store["subscription_cleanup_histories"]
        assert notifies[0][0] == "X 即将开始全集洗版整理，已删除 1 条整理记录对应的媒体库文件"
        assert notifies[0][1] == "清理路径：\n/dest/a.mkv"
        assert "reason" not in notifies[0][2]
        assert "action" not in notifies[0][2]
        assert notifies[0][2]["image"] == "subscribe.jpg"

    def test_transfer_intercept_without_snapshot_returns_false(self):
        """无订阅清理快照时整理拦截不产生日志噪音。"""
        orch, _store, _deletes, _events, _hist = self._orch_clear({})
        event = SimpleNamespace(event_data=SimpleNamespace(
            cancel=False, mediainfo=SimpleNamespace(tmdb_id=100)))

        assert orch.handle_history_clear(event) is False

    def test_transfer_intercept_clear_returns_true(self):
        """命中清理快照并完成清理时返回 True，供事件层输出结果日志。"""
        store = {"subscription_cleanup_histories": {"task-1": {
            "tmdbid": 100, "type": "电视剧", "season": "S01",
            "target_episodes": [1],
            "subscribe_desc": "X", "mode_label": "全集洗版", "histories": [], "time": time.time(),
        }}}
        orch, _store, _deletes, _events, _hist = self._orch_clear(store)
        event = self._transfer_event(episode=1)

        assert orch.handle_history_clear(event) is True

    def test_transfer_intercept_drops_expired_history_without_deleting_dest(self):
        """超过 72 小时的清理事务失效，不得删除旧媒体库目标文件。"""
        store = {"subscription_cleanup_histories": {"task-1": {
            "tmdbid": 100,
            "type": "电视剧",
            "season": "S01",
            "target_episodes": [1],
            "subscribe_desc": "X",
            "histories": [{"dest_fileitem": {"path": "/dest/a.mkv"}}],
            "time": time.time() - 73 * 3600,
        }}}
        orch, _store, deletes, _events, _histories = self._orch_clear(store)
        event = self._transfer_event(episode=1)

        assert orch.handle_history_clear(event) is False

        assert deletes == []
        assert "task-1" in store["subscription_cleanup_histories"]

    def test_cleanup_expired_clear_histories_keeps_recent_tasks(self):
        """通用清理只移除超过 72 小时的订阅清理事务。"""
        now = time.time()
        store = {"subscription_cleanup_histories": {
            "expired": {"time": now - 73 * 3600},
            "recent": {"time": now - 71 * 3600},
        }}
        orch, _store, _deletes, _events, _histories = self._orch_clear(store)

        assert orch.cleanup_expired_clear_histories() == 1

        assert set(store["subscription_cleanup_histories"]) == {"recent"}
