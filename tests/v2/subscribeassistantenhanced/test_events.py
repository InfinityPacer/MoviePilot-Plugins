"""events.py 事件薄代理单测——顺序和域分发。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, call

from subscribeassistantenhanced.events import EventProxy
from subscribeassistantenhanced.lifecycle import LifecycleResult


def _sub(**kwargs):
    """构造完整订阅替身，默认包含 Subscribe 固定字段。"""
    defaults = dict(
        id=1,
        name="测试剧",
        tmdbid=100,
        season=1,
        episode_group=None,
        state="R",
        type="电视剧",
        best_version=0,
        best_version_full=0,
        total_episode=12,
        start_episode=1,
        lack_episode=0,
        note=[],
        episode_priority={},
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _mi(**kwargs):
    """构造完整 MediaInfo 替身，默认包含事件处理会读取的固定字段。"""
    defaults = dict(
        type="tv",
        next_episode_to_air=None,
        release_date=None,
        first_air_date=None,
        get_message_image=lambda: "media.jpg",
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestEventOrdering:
    """事件处理顺序验证。"""

    def test_episodes_refresh_site_refresh_between_f_and_pending_observer(self):
        """EpisodesRefresh 中 F 记录、站点证据消费、待定观察按固定顺序执行。"""
        from app.schemas.event import SubscribeEpisodesRefreshEventData

        call_order = []
        volatility = MagicMock()
        volatility.record.side_effect = lambda **kw: call_order.append("f_record")
        site_refresh = MagicMock()
        site_refresh.handle_refresh.side_effect = lambda ev: call_order.append("site_refresh")
        pending_refresh = MagicMock()
        pending_refresh.handle_refresh.side_effect = lambda ev: call_order.append("pending_refresh")

        proxy = EventProxy(volatility=volatility, site_refresh=site_refresh, pending_refresh=pending_refresh)
        event = SimpleNamespace(event_data=SubscribeEpisodesRefreshEventData(current_total_episode=12, subscribe_id=1))
        proxy.on_episodes_refresh(event)

        assert call_order == ["f_record", "site_refresh", "pending_refresh"]

    def test_episodes_refresh_uses_event_data_for_f_and_pending_observer(self):
        """EpisodesRefresh 必须从 event.event_data 读写，主程序只读取该数据类。"""
        from app.schemas.event import SubscribeEpisodesRefreshEventData
        call_order = []
        volatility = MagicMock()
        volatility.record.side_effect = lambda **kw: call_order.append(("f", kw))

        def pending_handle(data):
            call_order.append(("pending", data.subscribe_id))

        pending_refresh = MagicMock()
        pending_refresh.handle_refresh.side_effect = pending_handle
        proxy = EventProxy(volatility=volatility, pending_refresh=pending_refresh)
        data = SubscribeEpisodesRefreshEventData(current_total_episode=12, subscribe_id=1, season=1)

        proxy.on_episodes_refresh(SimpleNamespace(event_data=data))

        assert call_order[0] == ("f", {"total": 12, "subscribe_id": 1})
        assert call_order[1] == ("pending", 1)
        assert data.updated is False
        assert data.total_episode is None

    def test_episodes_refresh_label_uses_media_when_subscribe_missing(self):
        """集数刷新事件查不到订阅时，日志标签应回退到事件携带的媒体信息。"""
        from app.schemas.event import SubscribeEpisodesRefreshEventData

        data = SubscribeEpisodesRefreshEventData(
            current_total_episode=15,
            subscribe_id=32,
            season=1,
            tmdbid=325228,
            mediainfo={"title": "镖人", "year": 2023},
            scene="refresh",
        )

        assert EventProxy._format_episodes_refresh_label(data) == "镖人 (2023) S1(id=32, tmdbid=325228, scene=refresh)"

    def test_episodes_refresh_label_uses_mediainfo_contract(self):
        """集数刷新标签支持主程序 MediaInfo 对象。"""
        from app.core.context import MediaInfo
        from app.schemas.event import SubscribeEpisodesRefreshEventData

        data = SubscribeEpisodesRefreshEventData(
            current_total_episode=15,
            subscribe_id=32,
            season=1,
            mediainfo=MediaInfo(title="镖人", year="2023", tmdb_id=325228),
            scene="refresh",
        )

        assert EventProxy._format_episodes_refresh_label(data) == "镖人 (2023) S1(id=32, tmdbid=325228, scene=refresh)"

    def test_download_added_registers_monitor_then_lifecycle_and_notifies_once(self):
        """DownloadAdded 先登记下载事实，再按 lifecycle 结果发送一次恢复通知。"""
        call_order = []
        sub = _sub(id=1, state="S")
        oper = MagicMock()
        oper.get.return_value = sub
        monitor = MagicMock()
        monitor.on_download.side_effect = lambda *_args, **_kwargs: call_order.append("monitor")
        lifecycle = MagicMock()
        lifecycle.handle_download_added_for_subscribe.side_effect = (
            lambda _subscribe: call_order.append("lifecycle")
            or LifecycleResult(changed=True, state="R", reason="no_download")
        )
        notify = MagicMock(side_effect=lambda *_args, **_kwargs: call_order.append("notify"))
        proxy = EventProxy(
            subscribe_oper=oper,
            download_monitor=monitor,
            lifecycle=lifecycle,
            notify_fn=notify,
            notification_image_fn=lambda _subscribe: "subscribe.jpg",
        )
        proxy.on_download_added(SimpleNamespace(event_data={
            "source": 'Subscribe|{"id": 1}', "hash": "h1", "episodes": [1, 2], "downloader": "qb",
        }))
        assert call_order == ["monitor", "lifecycle", "notify"]
        monitor.on_download.assert_called_once_with(
            1, "h1", episodes=[1, 2], downloader="qb",
            enclosure=None, page_url=None, title=None, description=None)
        lifecycle.handle_download_added_for_subscribe.assert_called_once_with(sub)
        notify.assert_called_once()
        assert "已恢复暂停订阅" in notify.call_args.args[0]
        assert notify.call_args.kwargs["reason"] == "无下载暂停"
        assert notify.call_args.kwargs["follow_up"] == "48小时内不会因同一原因再次自动暂停"
        assert notify.call_args.kwargs["image"] == "subscribe.jpg"

    def test_download_added_external_result_uses_external_notification(self):
        """外部暂停归属由 lifecycle 处理，事件层只按结果生成外部恢复通知。"""
        sub = _sub(id=1, state="S")
        oper = MagicMock()
        oper.get.return_value = sub
        lifecycle = MagicMock()
        lifecycle.handle_download_added_for_subscribe.return_value = LifecycleResult(
            changed=True,
            state="R",
            reason="external",
        )
        notify = MagicMock()
        proxy = EventProxy(
            subscribe_oper=oper,
            lifecycle=lifecycle,
            notify_fn=notify,
            notification_image_fn=lambda _subscribe: "subscribe.jpg",
        )

        proxy.on_download_added(SimpleNamespace(event_data={
            "source": 'Subscribe|{"id": 1}', "hash": "h1",
        }))

        lifecycle.handle_download_added_for_subscribe.assert_called_once_with(sub)
        notify.assert_called_once()
        assert "已恢复外部暂停订阅" in notify.call_args.args[0]
        assert notify.call_args.kwargs["follow_up"] == "用户再次手动暂停仍会立即生效"
        assert notify.call_args.kwargs["image"] == "subscribe.jpg"

    def test_download_added_only_notifies_when_lifecycle_changes(self):
        """source 无法解析不进 lifecycle；已解析订阅是否恢复由 lifecycle 结果决定。"""
        notify = MagicMock()
        lifecycle = MagicMock()
        oper = MagicMock()
        oper.get.return_value = None
        EventProxy(subscribe_oper=oper, lifecycle=lifecycle, notify_fn=notify).on_download_added(
            SimpleNamespace(event_data={"source": "bad", "hash": "h1"})
        )
        lifecycle.handle_download_added_for_subscribe.assert_not_called()
        notify.assert_not_called()

        running = _sub(id=2, state="R")
        oper.get.return_value = running
        lifecycle.handle_download_added_for_subscribe.return_value = LifecycleResult()
        EventProxy(subscribe_oper=oper, lifecycle=lifecycle, notify_fn=notify).on_download_added(
            SimpleNamespace(event_data={"source": 'Subscribe|{"id": 2}', "hash": "h2"})
        )
        lifecycle.handle_download_added_for_subscribe.assert_called_once_with(running)
        notify.assert_not_called()

    def test_download_added_skips_torrent_index_when_both_download_toggles_disabled(self):
        """下载待定和下载管理都关闭时，不写无消费方的 torrents 索引。"""
        sub = _sub(id=1)
        oper = MagicMock()
        oper.get.return_value = sub
        monitor = MagicMock()
        proxy = EventProxy(
            subscribe_oper=oper,
            download_monitor=monitor,
            pending_download_enabled=False,
            download_monitor_enabled=False,
        )

        proxy.on_download_added(SimpleNamespace(event_data={
            "source": 'Subscribe|{"id": 1}', "hash": "h1", "episodes": [1], "downloader": "qb",
        }))

        monitor.on_download.assert_not_called()

    def test_download_added_writes_torrent_index_for_pending_only(self):
        """只开启下载待定时仍写 torrents，供下载任务检查释放 P 状态。"""
        sub = _sub(id=1)
        oper = MagicMock()
        oper.get.return_value = sub
        monitor = MagicMock()
        proxy = EventProxy(
            subscribe_oper=oper,
            download_monitor=monitor,
            pending_download_enabled=True,
            download_monitor_enabled=False,
        )

        proxy.on_download_added(SimpleNamespace(event_data={
            "source": 'Subscribe|{"id": 1}', "hash": "h1", "episodes": [1], "downloader": "qb",
        }))

        monitor.on_download.assert_called_once()

    def test_transfer_complete_clears_download_pending(self):
        """TransferComplete 经 torrents 反查订阅后清 download_pending。"""
        monitor = MagicMock()
        tm = MagicMock()
        tm.read.return_value = {"abc123": {"subscribe_id": 1}}
        proxy = EventProxy(download_monitor=monitor, task_manager=tm)
        proxy.on_transfer_complete(SimpleNamespace(event_data={
            "download_hash": "abc123", "transferinfo": None,
        }))
        monitor.clear_download_pending.assert_called_once_with(1, "abc123")

    def test_transfer_complete_move_cleans_torrent_tasks(self):
        """移动模式整理完成 → 同步清理种子任务记录。"""
        tm = MagicMock()
        tm.read.return_value = {"abc": {"subscribe_id": 1}}
        proxy = EventProxy(download_monitor=MagicMock(), task_manager=tm)
        proxy.on_transfer_complete(SimpleNamespace(event_data={
            "download_hash": "abc", "transferinfo": SimpleNamespace(transfer_type="move"),
        }))
        tm.clean_torrent_tasks.assert_called_once_with("abc")

    def test_transfer_complete_clears_pending_and_move_tasks_before_lifecycle(self):
        """TransferComplete 先清下载待定和移动任务，再把媒体库更新交给 lifecycle。"""
        call_order = []
        tm = MagicMock()
        tm.read.return_value = {"abc": {"subscribe_id": 1}}
        tm.clean_torrent_tasks.side_effect = lambda _hash: call_order.append("clean")
        monitor = MagicMock()
        monitor.clear_download_pending.side_effect = lambda *_args: call_order.append("clear")
        lifecycle = MagicMock()
        lifecycle.handle_library_updated.side_effect = lambda _subscribe_id: call_order.append("lifecycle")
        proxy = EventProxy(
            download_monitor=monitor,
            task_manager=tm,
            lifecycle=lifecycle,
        )

        proxy.on_transfer_complete(SimpleNamespace(event_data={
            "download_hash": "abc", "transferinfo": SimpleNamespace(transfer_type="move"),
        }))

        assert call_order == ["clear", "clean", "lifecycle"]
        monitor.clear_download_pending.assert_called_once_with(1, "abc")
        tm.clean_torrent_tasks.assert_called_once_with("abc")
        lifecycle.handle_library_updated.assert_called_once_with(1)

    def test_transfer_complete_delegates_library_update_state_decision(self):
        """订阅状态是否需要播出暂停由 lifecycle 判断，事件层只传递订阅 id。"""
        tm = MagicMock()
        tm.read.return_value = {"abc": {"subscribe_id": 1}}
        lifecycle = MagicMock()
        proxy = EventProxy(
            task_manager=tm,
            lifecycle=lifecycle,
        )

        proxy.on_transfer_complete(SimpleNamespace(event_data={
            "download_hash": "abc", "transferinfo": None,
        }))

        lifecycle.handle_library_updated.assert_called_once_with(1)

    def test_non_best_version_mode_label_is_empty(self):
        """普通订阅不应被洗版模式标签误标。"""
        assert EventProxy._best_version_mode_label(_sub(best_version=0)) == ""

    def test_best_version_mode_label_distinguishes_episode_and_full(self):
        """真正洗版和分集洗版使用不同标签。"""
        assert EventProxy._best_version_mode_label(_sub(best_version=1, best_version_full=0)) == "分集洗版"
        assert EventProxy._best_version_mode_label(_sub(best_version=1, best_version_full=1)) == "洗版"

    def test_movie_best_version_mode_label_uses_wash_label(self):
        """电影洗版使用真正洗版标签，不应被 best_version_full=0 误标成分集洗版。"""
        assert EventProxy._best_version_mode_label(
            _sub(type="电影", best_version=1, best_version_full=0)
        ) == "洗版"

    def test_transfer_complete_converts_ready_episode_best_version_to_full(self):
        """分集洗版整理完成且目标集齐全时，当前订阅立即转全集洗版。"""
        sub = _sub(
            id=1,
            best_version=1,
            best_version_full=0,
            lack_episode=0,
            episode_priority={str(ep): 10 for ep in range(1, 13)},
        )
        media = SimpleNamespace(tmdb_id=100)
        tm = MagicMock()
        tm.read.return_value = {"abc": {"subscribe_id": 1}}
        oper = MagicMock()
        oper.get.return_value = sub
        converter = MagicMock()
        proxy = EventProxy(
            task_manager=tm,
            subscribe_oper=oper,
            download_monitor=MagicMock(),
            converter=converter,
            best_version_episode_to_full=True,
            detect_missing_episodes_fn=MagicMock(return_value=[]),
            recognize_mediainfo_fn=MagicMock(return_value=media),
        )

        proxy.on_transfer_complete(SimpleNamespace(event_data={
            "download_hash": "abc", "transferinfo": None,
        }))

        converter.convert_to_full.assert_called_once_with(sub, media)

    def test_transfer_complete_uses_target_satisfied_resolver_for_episode_best_version(self):
        """分集洗版转全集按主程序目标满足口径判断，允许任意已下载版本满足目标集。"""
        sub = _sub(
            id=1,
            best_version=1,
            best_version_full=0,
            lack_episode=1,
            total_episode=3,
            note=[1],
            episode_priority={"2": 80, "3": 99},
        )
        media = SimpleNamespace(tmdb_id=100)
        tm = MagicMock()
        tm.read.return_value = {"abc": {"subscribe_id": 1}}
        oper = MagicMock()
        oper.get.return_value = sub
        converter = MagicMock()
        resolver = MagicMock(return_value=(True, {}))
        proxy = EventProxy(
            task_manager=tm,
            subscribe_oper=oper,
            download_monitor=MagicMock(),
            converter=converter,
            best_version_episode_to_full=True,
            resolve_missing_fn=resolver,
            recognize_mediainfo_fn=MagicMock(return_value=media),
        )

        proxy.on_transfer_complete(SimpleNamespace(event_data={
            "download_hash": "abc", "transferinfo": None,
        }))

        resolver.assert_called_once_with(
            subscribe=sub,
            mediainfo=media,
            best_version_accept_downloaded=True,
        )
        converter.convert_to_full.assert_called_once_with(sub, media)

    def test_transfer_complete_keeps_episode_best_version_when_target_missing(self):
        """分集洗版整理完成但目标集未齐全时，不提前转全集。"""
        sub = _sub(
            id=1,
            best_version=1,
            best_version_full=0,
            lack_episode=0,
            episode_priority={str(ep): 10 for ep in range(1, 13)},
        )
        tm = MagicMock()
        tm.read.return_value = {"abc": {"subscribe_id": 1}}
        oper = MagicMock()
        oper.get.return_value = sub
        converter = MagicMock()
        proxy = EventProxy(
            task_manager=tm,
            subscribe_oper=oper,
            download_monitor=MagicMock(),
            converter=converter,
            best_version_episode_to_full=True,
            resolve_missing_fn=MagicMock(return_value=(False, {})),
            detect_missing_episodes_fn=MagicMock(return_value=[2]),
            recognize_mediainfo_fn=MagicMock(return_value=SimpleNamespace(tmdb_id=100)),
        )

        proxy.on_transfer_complete(SimpleNamespace(event_data={
            "download_hash": "abc", "transferinfo": None,
        }))

        converter.convert_to_full.assert_not_called()

    def test_transfer_complete_skips_library_check_when_episodes_still_missing(self):
        """分集洗版目标集仍有未下载集时，不触发媒体库缺集探测。"""
        sub = _sub(id=1, best_version=1, best_version_full=0, lack_episode=1, episode_priority={"1": 100})
        tm = MagicMock()
        tm.read.return_value = {"abc": {"subscribe_id": 1}}
        oper = MagicMock()
        oper.get.return_value = sub
        detect_missing = MagicMock(return_value=[])
        converter = MagicMock()
        proxy = EventProxy(
            task_manager=tm,
            subscribe_oper=oper,
            download_monitor=MagicMock(),
            converter=converter,
            best_version_episode_to_full=True,
            resolve_missing_fn=MagicMock(return_value=(False, {})),
            detect_missing_episodes_fn=detect_missing,
            recognize_mediainfo_fn=MagicMock(return_value=SimpleNamespace(tmdb_id=100)),
        )

        proxy.on_transfer_complete(SimpleNamespace(event_data={
            "download_hash": "abc", "transferinfo": None,
        }))

        detect_missing.assert_not_called()
        converter.convert_to_full.assert_not_called()

    def test_subscribe_complete_triggers_snapshot(self):
        """SubscribeComplete 触发 H snapshot（subscribe 由 subscribe_info 重建）。"""
        verifier = MagicMock()
        proxy = EventProxy(verifier=verifier)
        event = SimpleNamespace(event_data={
            "subscribe_id": 5,
            "subscribe_info": {"tmdbid": 100, "season": 1, "name": "测试"},
        })
        proxy.on_subscribe_complete(event)
        verifier.snapshot.assert_called_once()


class TestDomainGating:
    """未注册的域不触发。"""

    def test_no_guard_no_error(self):
        proxy = EventProxy()
        event = SimpleNamespace(cancel=False, reason="")
        proxy.on_completion_check(event)
        assert event.cancel is False

    def test_no_volatility_no_error(self):
        from app.schemas.event import SubscribeEpisodesRefreshEventData

        proxy = EventProxy()
        event = SimpleNamespace(event_data=SubscribeEpisodesRefreshEventData(current_total_episode=12, subscribe_id=1))
        proxy.on_episodes_refresh(event)

    def test_no_monitor_no_error(self):
        proxy = EventProxy()
        event = SimpleNamespace(event_data=SimpleNamespace(
            origin='Subscribe|{"id": 1}', context=None, episodes=[], cancel=False))
        proxy.on_resource_download(event)


class TestSubscribeLifecycle:
    """订阅删除/修改事件：任务清理与状态变更时的暂停重置。"""

    def test_deleted_clears_tasks(self):
        tm = MagicMock()
        proxy = EventProxy(task_manager=tm)
        proxy.on_subscribe_deleted(SimpleNamespace(event_data={"subscribe_id": 9}))
        tm.clear_tasks.assert_called_once_with(9)

    def test_deleted_label_uses_event_subscribe_snapshot(self):
        """删除事件发生后订阅可能已不可查，日志标签应使用事件携带的订阅快照。"""
        proxy = EventProxy()
        label = proxy._format_subscribe_label(
            9,
            {"id": 9, "name": "将夜", "season": 1},
        )
        assert label == "将夜 S1(id=9)"

    def test_deleted_without_id_noop(self):
        tm = MagicMock()
        proxy = EventProxy(task_manager=tm)
        proxy.on_subscribe_deleted(SimpleNamespace(event_data={}))
        tm.clear_tasks.assert_not_called()

    def test_modified_state_change_delegates_pause_record_cleanup(self):
        lifecycle = MagicMock()
        sub = _sub(id=9)
        oper = MagicMock()
        oper.get.return_value = sub
        proxy = EventProxy(lifecycle=lifecycle, subscribe_oper=oper)
        proxy.on_subscribe_modified(SimpleNamespace(event_data={
            "subscribe_id": 9,
            "subscribe_info": {"state": "R"},
            "old_subscribe_info": {"state": "S"},
        }))
        lifecycle.handle_subscribe_modified_state_change.assert_called_once_with(
            sub, old_state="S", new_state="R"
        )

    def test_modified_to_paused_delegates_external_ownership(self):
        """非 S → S 的外部暂停归属由 lifecycle 统一处理。"""
        lifecycle = MagicMock()
        sub = _sub(id=9, state="S")
        oper = MagicMock()
        oper.get.return_value = sub
        proxy = EventProxy(lifecycle=lifecycle, subscribe_oper=oper)
        proxy.on_subscribe_modified(SimpleNamespace(event_data={
            "subscribe_id": 9,
            "subscribe_info": {"state": "S"},
            "old_subscribe_info": {"state": "R"},
        }))
        lifecycle.handle_subscribe_modified_state_change.assert_called_once_with(
            sub, old_state="R", new_state="S"
        )

    def test_modified_without_state_change_noop(self):
        lifecycle = MagicMock()
        oper = MagicMock()
        oper.get.return_value = _sub(id=9)
        proxy = EventProxy(lifecycle=lifecycle, subscribe_oper=oper)
        proxy.on_subscribe_modified(SimpleNamespace(event_data={
            "subscribe_id": 9,
            "subscribe_info": {"name": "X", "state": "R"},
            "old_subscribe_info": {"name": "Y", "state": "R"},
        }))
        lifecycle.handle_subscribe_modified_state_change.assert_not_called()

    def test_modified_convert_to_best_version_backfills(self):
        """普通转洗版（best_version 假→真）→ 媒体库已有集回填 priority=100。"""
        sub = _sub(id=9, best_version=1)
        oper = MagicMock()
        oper.get.return_value = sub
        priority = MagicMock()
        priority.can_backfill.return_value = True
        proxy = EventProxy(subscribe_oper=oper, priority_manager=priority,
                           detect_existing_episodes_fn=lambda s: [1, 2, 3])
        proxy.on_subscribe_modified(SimpleNamespace(event_data={
            "subscribe_id": 9,
            "subscribe_info": {"best_version": 1},
            "old_subscribe_info": {"best_version": 0},
        }))
        priority.backfill_existing.assert_called_once_with(
            sub, [1, 2, 3], scene="plugin_backfill<订阅助手（增强版）>"
        )

    def test_modified_convert_to_best_version_uses_backfill_candidates(self):
        """普通转洗版回填使用 note + 媒体库候选，不只看当前媒体库范围。"""
        sub = _sub(id=9, best_version=1, start_episode=2, note=[1, 2, 3, 4])
        oper = MagicMock()
        oper.get.return_value = sub
        priority = MagicMock()
        priority.can_backfill.return_value = True
        detect_backfill = MagicMock(return_value=[1, 2, 3, 4])
        proxy = EventProxy(
            subscribe_oper=oper,
            priority_manager=priority,
            detect_backfill_episodes_fn=detect_backfill,
        )

        proxy.on_subscribe_modified(SimpleNamespace(event_data={
            "subscribe_id": 9,
            "subscribe_info": {"best_version": 1},
            "old_subscribe_info": {"best_version": 0},
        }))

        detect_backfill.assert_called_once_with(sub)
        priority.backfill_existing.assert_called_once_with(
            sub, [1, 2, 3, 4], scene="plugin_backfill<订阅助手（增强版）>"
        )

    def test_modified_convert_directly_to_full_skips_backfill(self):
        """普通订阅直接转全集洗版时不探测媒体库，也不回填按集优先级。"""
        sub = _sub(id=9, best_version=1, best_version_full=1)
        oper = MagicMock()
        oper.get.return_value = sub
        priority = MagicMock()
        priority.can_backfill.return_value = False
        detect_existing = MagicMock(return_value=[1, 2, 3])
        proxy = EventProxy(
            subscribe_oper=oper,
            priority_manager=priority,
            detect_existing_episodes_fn=detect_existing,
            backfill_enabled=True,
        )

        proxy.on_subscribe_modified(SimpleNamespace(event_data={
            "subscribe_id": 9,
            "subscribe_info": {"best_version": 1, "best_version_full": 1},
            "old_subscribe_info": {"best_version": 0, "best_version_full": 0},
        }))

        detect_existing.assert_not_called()
        priority.backfill_existing.assert_not_called()

    def test_modified_already_best_version_no_backfill(self):
        """已是洗版（非边沿）→ 不回填。"""
        oper = MagicMock()
        oper.get.return_value = _sub(id=9)
        priority = MagicMock()
        proxy = EventProxy(subscribe_oper=oper, priority_manager=priority,
                           detect_existing_episodes_fn=lambda s: [1])
        proxy.on_subscribe_modified(SimpleNamespace(event_data={
            "subscribe_id": 9,
            "subscribe_info": {"best_version": 1, "name": "X"},
            "old_subscribe_info": {"best_version": 1, "name": "Y"},
        }))
        priority.backfill_existing.assert_not_called()

    def test_modified_reset_backfills_episode_best_version(self):
        """reset 场景只在明确 reset 事件下触发分集洗版回填。"""
        sub = _sub(id=9, best_version=1, best_version_full=0)
        oper = MagicMock()
        oper.get.return_value = sub
        priority = MagicMock()
        priority.can_backfill.return_value = True
        detect = MagicMock(return_value=[1, 2])
        proxy = EventProxy(
            subscribe_oper=oper,
            priority_manager=priority,
            detect_backfill_episodes_fn=detect,
            backfill_enabled=True,
        )

        proxy.on_subscribe_modified(SimpleNamespace(event_data={
            "subscribe_id": 9,
            "scene": "reset",
            "fields": ["note", "lack_episode", "episode_priority", "state"],
            "subscribe_info": {"note": [], "lack_episode": 12, "episode_priority": {}, "state": "R"},
            "old_subscribe_info": {"note": [1], "lack_episode": 11, "episode_priority": {"1": 100}, "state": "R"},
        }))

        detect.assert_called_once_with(sub)
        priority.backfill_existing.assert_called_once_with(
            sub, [1, 2], scene="reset_backfill<订阅助手（增强版）>"
        )

    def test_modified_reset_without_scene_does_not_guess_by_fields(self):
        """缺少 reset scene 的旧事件不按字段差异猜测 reset。"""
        sub = _sub(id=9, best_version=1, best_version_full=0)
        oper = MagicMock()
        oper.get.return_value = sub
        priority = MagicMock()
        priority.can_backfill.return_value = True
        proxy = EventProxy(
            subscribe_oper=oper,
            priority_manager=priority,
            detect_backfill_episodes_fn=MagicMock(return_value=[1, 2]),
            backfill_enabled=True,
        )

        proxy.on_subscribe_modified(SimpleNamespace(event_data={
            "subscribe_id": 9,
            "fields": ["note", "lack_episode", "episode_priority", "state"],
            "subscribe_info": {"note": [], "lack_episode": 12, "episode_priority": {}, "state": "R"},
            "old_subscribe_info": {"note": [1], "lack_episode": 11, "episode_priority": {"1": 100}, "state": "R"},
        }))

        priority.backfill_existing.assert_not_called()

    def test_modified_reset_reentry_guard(self):
        """reset 回填写库引发的同步事件不应递归触发回填。"""
        sub = _sub(id=9, best_version=1, best_version_full=0)
        oper = MagicMock()
        oper.get.return_value = sub
        priority = MagicMock()
        priority.can_backfill.return_value = True
        proxy = EventProxy(
            subscribe_oper=oper,
            priority_manager=priority,
            detect_backfill_episodes_fn=MagicMock(return_value=[1, 2]),
            backfill_enabled=True,
        )
        proxy._reset_backfilling_ids.add(9)

        proxy.on_subscribe_modified(SimpleNamespace(event_data={
            "subscribe_id": 9,
            "scene": "reset",
            "fields": ["note", "lack_episode", "episode_priority", "state"],
            "subscribe_info": {"note": [], "lack_episode": 12, "episode_priority": {}, "state": "R"},
            "old_subscribe_info": {"note": [1], "lack_episode": 11, "episode_priority": {"1": 100}, "state": "R"},
        }))

        priority.backfill_existing.assert_not_called()

    def test_added_delegates_lifecycle_after_loading_mediainfo(self):
        """SubscribeAdded 事件层只保留取数职责，状态流转委托 lifecycle。"""
        sub = _sub(id=7)
        oper = MagicMock()
        oper.get.return_value = sub
        lifecycle = MagicMock()
        mediainfo = _mi()
        proxy = EventProxy(
            subscribe_oper=oper,
            lifecycle=lifecycle,
            mediainfo_from_dict=lambda _data: mediainfo,
        )

        proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {"x": 1}}))

        lifecycle.handle_subscribe_added.assert_called_once_with(sub, mediainfo)

    def test_added_missing_mediainfo_skips_lifecycle(self):
        """SubscribeAdded 无媒体信息时不进入生命周期判定。"""
        sub = _sub(id=7)
        oper = MagicMock()
        oper.get.return_value = sub
        lifecycle = MagicMock()
        proxy = EventProxy(
            subscribe_oper=oper,
            lifecycle=lifecycle,
            mediainfo_from_dict=lambda _data: None,
        )

        proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": None}))

        lifecycle.handle_subscribe_added.assert_not_called()

    def test_added_backfill_uses_backfill_candidates(self):
        """新增洗版订阅回填使用 note + 媒体库候选，并先于 lifecycle。"""
        call_order = []
        sub = _sub(id=7, best_version=1, best_version_full=0, start_episode=2, note=[1, 2, 3, 4])
        oper = MagicMock()
        oper.get.return_value = sub
        priority = MagicMock()
        priority.can_backfill.return_value = True
        priority.backfill_existing.side_effect = lambda *_args, **_kwargs: call_order.append("backfill")
        detect_backfill = MagicMock(return_value=[1, 2, 3, 4])
        lifecycle = MagicMock()
        lifecycle.handle_subscribe_added.side_effect = lambda *_args, **_kwargs: call_order.append("lifecycle")
        mediainfo = _mi()
        proxy = EventProxy(
            subscribe_oper=oper,
            priority_manager=priority,
            detect_backfill_episodes_fn=detect_backfill,
            backfill_enabled=True,
            lifecycle=lifecycle,
            mediainfo_from_dict=lambda _data: mediainfo,
        )

        proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {"x": 1}}))

        detect_backfill.assert_called_once_with(sub)
        priority.backfill_existing.assert_called_once_with(
            sub, [1, 2, 3, 4], scene="plugin_backfill<订阅助手（增强版）>"
        )
        lifecycle.handle_subscribe_added.assert_called_once_with(sub, mediainfo)
        assert call_order == ["backfill", "lifecycle"]

    def test_complete_clears_tasks_and_snapshots(self):
        """SubscribeComplete → 先保存 H 快照再清实例数据，避免历史被清理丢失。"""
        order = []
        tm = MagicMock()
        tm.clear_tasks.side_effect = lambda _sid: order.append("clear")
        verifier = MagicMock()
        verifier.snapshot.side_effect = lambda **_kwargs: order.append("snapshot")
        mediainfo = _mi()
        sub = _sub(id=5, tmdbid=100, season=1)
        oper = MagicMock()
        oper.get.return_value = sub
        proxy = EventProxy(
            task_manager=tm,
            verifier=verifier,
            subscribe_oper=oper,
            mediainfo_from_dict=lambda _data: mediainfo,
        )
        proxy.on_subscribe_complete(SimpleNamespace(event_data={
            "subscribe_id": 5,
            "subscribe_info": {"tmdbid": 100, "season": 1},
        }))
        tm.clear_tasks.assert_called_once_with(5)
        verifier.snapshot.assert_called_once()
        assert order == ["snapshot", "clear"]
        _, kwargs = verifier.snapshot.call_args
        assert kwargs.get("subscribe") is sub
        assert kwargs.get("mediainfo") is mediainfo

    def test_complete_without_subscribe_snapshot_still_clears_instance_state(self):
        """完成事件缺少订阅快照时仍按 ID 清理实例状态。"""
        task_manager = MagicMock()
        verifier = MagicMock()
        proxy = EventProxy(task_manager=task_manager, verifier=verifier)

        proxy.on_subscribe_complete(SimpleNamespace(event_data={
            "subscribe_id": 5,
            "subscribe_info": {},
        }))

        task_manager.clear_tasks.assert_called_once_with(5)
        verifier.snapshot.assert_not_called()

    def test_complete_media_parse_failure_still_snapshots_and_clears_tasks(self):
        """完成事件媒体补充解析失败时，快照与任务清理仍必须继续。"""
        order = []
        task_manager = MagicMock()
        task_manager.clear_tasks.side_effect = lambda _sid: order.append("clear")
        verifier = MagicMock()
        verifier.snapshot.side_effect = lambda **_kwargs: order.append("snapshot")
        subscribe = _sub(id=5)
        subscribe_oper = MagicMock()
        subscribe_oper.get.return_value = subscribe

        proxy = EventProxy(
            task_manager=task_manager,
            verifier=verifier,
            subscribe_oper=subscribe_oper,
            mediainfo_from_dict=MagicMock(side_effect=ValueError("invalid media payload")),
        )

        proxy.on_subscribe_complete(SimpleNamespace(event_data={
            "subscribe_id": 5,
            "mediainfo": {"broken": True},
        }))

        assert order == ["snapshot", "clear"]
        assert verifier.snapshot.call_args.kwargs["mediainfo"] is None

    def test_complete_triggers_best_version_creation(self):
        """SubscribeComplete → 委托洗版编排创建洗版订阅（mediainfo 由事件重建）。"""
        sub = _sub(id=5, tmdbid=100, season=1, best_version=0)
        oper = MagicMock()
        oper.get.return_value = sub
        orch = MagicMock()
        proxy = EventProxy(
            task_manager=MagicMock(), verifier=MagicMock(), subscribe_oper=oper,
            orchestrator=orch, mediainfo_from_dict=lambda d: SimpleNamespace(payload=d))
        proxy.on_subscribe_complete(SimpleNamespace(event_data={
            "subscribe_id": 5, "subscribe_info": {"tmdbid": 100}, "mediainfo": {"y": 1}}))
        orch.start_best_version.assert_called_once()
        args, _kwargs = orch.start_best_version.call_args
        assert args[0] is sub

    def test_complete_uses_event_snapshot_when_finished_subscribe_deleted(self):
        """SubscribeComplete → 完成后订阅表已删除时，自动洗版应使用事件快照。"""
        oper = MagicMock()
        oper.get.return_value = None
        orch = MagicMock()
        proxy = EventProxy(
            task_manager=MagicMock(), verifier=MagicMock(), subscribe_oper=oper,
            orchestrator=orch, mediainfo_from_dict=lambda d: SimpleNamespace(payload=d))

        proxy.on_subscribe_complete(SimpleNamespace(event_data={
            "subscribe_id": 5,
            "subscribe_info": {
                "id": 5,
                "name": "测试电影",
                "type": "电影",
                "tmdbid": 100,
                "season": None,
                "best_version": 0,
                "current_priority": 90,
            },
            "mediainfo": {"y": 1},
        }))

        orch.start_best_version.assert_called_once()
        args, _kwargs = orch.start_best_version.call_args
        assert args[0].current_priority == 90


class TestPluginActionToggle:
    """PluginAction /subscribe_toggle 切换订阅启用/禁用。"""

    def _event(self, **data):
        data.setdefault("action", "subscribe_toggle")
        return SimpleNamespace(event_data=data)

    @staticmethod
    def _oper_with_subscribe(sub):
        """构造只返回一个订阅的订阅表替身。"""
        oper = MagicMock()
        oper.list.return_value = [sub]
        return oper

    def test_toggle_single_match_enables(self):
        sub = _sub(id=3, name="X", state="S")
        oper = self._oper_with_subscribe(sub)
        lifecycle = MagicMock()
        lifecycle.toggle_subscribe_by_user_command.return_value = LifecycleResult(changed=True, state="R")
        msgs = []
        proxy = EventProxy(subscribe_oper=oper, lifecycle=lifecycle, post_message=lambda **kw: msgs.append(kw))
        proxy.on_plugin_action(self._event(arg_str="3"))
        lifecycle.toggle_subscribe_by_user_command.assert_called_once_with(sub)
        oper.update.assert_not_called()
        assert msgs and "启用" in msgs[0]["title"]

    def test_toggle_single_match_disables(self):
        sub = _sub(id=3, name="X", state="R")
        oper = self._oper_with_subscribe(sub)
        lifecycle = MagicMock()
        lifecycle.toggle_subscribe_by_user_command.return_value = LifecycleResult(changed=True, state="S")
        proxy = EventProxy(subscribe_oper=oper, lifecycle=lifecycle, post_message=lambda **kw: None)
        proxy.on_plugin_action(self._event(arg_str="3"))
        lifecycle.toggle_subscribe_by_user_command.assert_called_once_with(sub)
        oper.update.assert_not_called()

    def test_toggle_by_name(self):
        sub = _sub(id=3, name="剧名", state="R")
        oper = self._oper_with_subscribe(sub)
        lifecycle = MagicMock()
        lifecycle.toggle_subscribe_by_user_command.return_value = LifecycleResult(changed=True, state="S")
        proxy = EventProxy(subscribe_oper=oper, lifecycle=lifecycle, post_message=lambda **kw: None)
        proxy.on_plugin_action(self._event(arg_str="剧名"))
        lifecycle.toggle_subscribe_by_user_command.assert_called_once_with(sub)
        oper.update.assert_not_called()

    def test_toggle_without_lifecycle_notifies_without_update(self):
        """生命周期未注入时不直接写状态，避免事件层重新成为状态 owner。"""
        sub = _sub(id=3, name="X", state="R")
        oper = self._oper_with_subscribe(sub)
        msgs = []
        proxy = EventProxy(subscribe_oper=oper, post_message=lambda **kw: msgs.append(kw))
        proxy.on_plugin_action(self._event(arg_str="3"))
        oper.update.assert_not_called()
        assert msgs and "生命周期未就绪" in msgs[0]["title"]

    def test_no_match_notifies_without_update(self):
        oper = MagicMock()
        oper.list.return_value = [SimpleNamespace(id=1, name="A", state="R")]
        msgs = []
        proxy = EventProxy(subscribe_oper=oper, post_message=lambda **kw: msgs.append(kw))
        proxy.on_plugin_action(self._event(arg_str="999"))
        oper.update.assert_not_called()
        assert msgs and "没有找到" in msgs[0]["title"]

    def test_wrong_action_ignored(self):
        oper = MagicMock()
        proxy = EventProxy(subscribe_oper=oper, post_message=lambda **kw: None)
        proxy.on_plugin_action(SimpleNamespace(event_data={"action": "other"}))
        oper.list.assert_not_called()


class TestResourceSelectionDedup:
    """ResourceSelection 剔除已删除资源，防止刚删的种子被立即重选。"""

    def _ctx(self, enclosure="", page_url=""):
        return SimpleNamespace(torrent_info=SimpleNamespace(enclosure=enclosure, page_url=page_url))

    def test_filters_deleted_candidates(self):
        keep = self._ctx(enclosure="http://x/keep.torrent")
        drop = self._ctx(enclosure="http://x/deleted.torrent")
        deletes = MagicMock()
        deletes.match.side_effect = lambda enclosure=None, page_url=None: enclosure == "http://x/deleted.torrent"
        proxy = EventProxy(deletes_store=deletes)
        data = SimpleNamespace(contexts=[keep, drop], updated=False, updated_contexts=None, source="")
        proxy.on_resource_selection(SimpleNamespace(event_data=data))
        assert data.updated is True
        assert data.updated_contexts == [keep]

    def test_no_deleted_match_leaves_unchanged(self):
        keep = self._ctx(enclosure="http://x/a.torrent")
        deletes = MagicMock()
        deletes.match.return_value = False
        proxy = EventProxy(deletes_store=deletes)
        data = SimpleNamespace(contexts=[keep], updated=False, updated_contexts=None, source="")
        proxy.on_resource_selection(SimpleNamespace(event_data=data))
        assert data.updated is False

    def test_no_deletes_store_noop(self):
        proxy = EventProxy()
        data = SimpleNamespace(contexts=[self._ctx(enclosure="x")], updated=False,
                               updated_contexts=None, source="")
        proxy.on_resource_selection(SimpleNamespace(event_data=data))
        assert data.updated is False

    def _serial_proxy(self, pending_episodes, best_version_full=0):
        sub = _sub(id=1, best_version=1, best_version_full=best_version_full)
        oper = MagicMock()
        oper.get.return_value = sub
        tm = MagicMock()
        tm.read.side_effect = lambda key: {
            "subscribes": {"1": {"download_pending": {"h1": {}}}},
            "torrents": {"h1": {"episodes": pending_episodes}},
        }.get(key, {})
        return EventProxy(subscribe_oper=oper, task_manager=tm)

    def _ep_ctx(self, episodes):
        return SimpleNamespace(torrent_info=SimpleNamespace(enclosure="", page_url=""), episodes=episodes)

    def test_pending_serial_blocks_candidate_covering_pending_episode(self):
        """洗版待定集 {3} 下载中 → 覆盖 E3 的候选被挡，覆盖 E4 的并行放行。"""
        keep, drop = self._ep_ctx([4]), self._ep_ctx([3])
        proxy = self._serial_proxy(pending_episodes=[3])
        data = SimpleNamespace(origin='Subscribe|{"id": 1}', contexts=[keep, drop],
                               updated=False, updated_contexts=None, source="")
        proxy.on_resource_selection(SimpleNamespace(event_data=data))
        assert data.updated is True
        assert data.updated_contexts == [keep]

    def test_pending_serial_disabled_by_config(self):
        """关闭下载中待定后，洗版下载待定不再过滤候选。"""
        keep, drop = self._ep_ctx([4]), self._ep_ctx([3])
        proxy = self._serial_proxy(pending_episodes=[3])
        proxy._modules["pending_download_enabled"] = False
        data = SimpleNamespace(origin='Subscribe|{"id": 1}', contexts=[keep, drop],
                               updated=False, updated_contexts=None, source="")
        proxy.on_resource_selection(SimpleNamespace(event_data=data))
        assert data.updated is False

    def test_pending_serial_unknown_episodes_blocks_all(self):
        """待定种子集数未知 → 保守全挡。"""
        proxy = self._serial_proxy(pending_episodes=[])
        data = SimpleNamespace(origin='Subscribe|{"id": 1}', contexts=[self._ep_ctx([4])],
                               updated=False, updated_contexts=None, source="")
        proxy.on_resource_selection(SimpleNamespace(event_data=data))
        assert data.updated is True
        assert data.updated_contexts == []

    def test_full_best_version_pending_blocks_all_candidates(self):
        """全集洗版已有下载待定时，不再选择其他候选资源。"""
        proxy = self._serial_proxy(
            pending_episodes=list(range(1, 21)),
            best_version_full=1,
        )
        data = SimpleNamespace(
            origin='Subscribe|{"id": 1}',
            contexts=[self._ep_ctx([]), self._ep_ctx(list(range(1, 21)))],
            updated=False,
            updated_contexts=None,
            source="",
        )

        proxy.on_resource_selection(SimpleNamespace(event_data=data))

        assert data.updated is True
        assert data.updated_contexts == []


class TestResourceDownloadHistoryClear:
    """ResourceDownload 触发订阅清理。"""

    def test_best_version_triggers_subscription_cleanup(self):
        sub = _sub(id=1, best_version=1)
        oper = MagicMock()
        oper.get.return_value = sub
        cleanup = MagicMock()
        cleanup.handle_resource_download_history_clear.return_value = True
        proxy = EventProxy(subscribe_oper=oper, subscription_cleanup=cleanup)
        ctx = object()
        proxy.on_resource_download(SimpleNamespace(event_data=SimpleNamespace(
            origin='Subscribe|{"id": 1}', context=ctx, episodes=[1],
            downloader="下载", cancel=False)))
        cleanup.handle_resource_download_history_clear.assert_called_once_with(
            sub, context=ctx, episodes=[1])

    def test_history_clear_degraded_result_does_not_cancel_download(self):
        """清理链路的返回值不得转换为取消下载，最终始终放行。"""
        sub = _sub(id=1, best_version=1)
        oper = MagicMock()
        oper.get.return_value = sub
        cleanup = MagicMock()
        cleanup.handle_resource_download_history_clear.return_value = False
        proxy = EventProxy(subscribe_oper=oper, subscription_cleanup=cleanup)
        data = SimpleNamespace(
            origin='Subscribe|{"id": 1}',
            context=SimpleNamespace(torrent_info=None),
            episodes=[1],
            downloader="下载",
            cancel=False,
            source="",
            reason="",
        )

        proxy.on_resource_download(SimpleNamespace(event_data=data))

        assert data.cancel is False

    def test_non_best_version_runs_subscription_cleanup_and_marks_download_started(self):
        """普通订阅 ResourceDownload 也进入订阅清理模块，是否清理由模块配置判定。"""
        sub = _sub(id=1, best_version=0)
        oper = MagicMock()
        oper.get.return_value = sub
        cleanup = MagicMock()
        monitor = MagicMock()
        torrent_info = SimpleNamespace(
            enclosure="https://example/torrent",
            page_url="https://example/page",
            title="测试剧 S01E01",
            description="首集资源",
        )
        ctx = SimpleNamespace(torrent_info=torrent_info)
        proxy = EventProxy(subscribe_oper=oper, subscription_cleanup=cleanup, download_monitor=monitor)

        proxy.on_resource_download(SimpleNamespace(event_data=SimpleNamespace(
            origin='Subscribe|{"id": 1}', context=ctx, episodes=[1], downloader="qb", cancel=False)))

        cleanup.handle_resource_download_history_clear.assert_called_once_with(
            sub, context=ctx, episodes=[1])
        monitor.mark_download_started.assert_called_once_with(
            sub,
            episodes=[1],
            downloader="qb",
            enclosure="https://example/torrent",
            page_url="https://example/page",
            title="测试剧 S01E01",
            description="首集资源",
        )

    def test_cancelled_event_skipped(self):
        cleanup = MagicMock()
        proxy = EventProxy(subscribe_oper=MagicMock(), subscription_cleanup=cleanup)
        proxy.on_resource_download(SimpleNamespace(event_data=SimpleNamespace(
            origin='Subscribe|{"id": 1}', cancel=True)))
        cleanup.handle_resource_download_history_clear.assert_not_called()

    def test_captures_priority_baseline_by_enclosure(self):
        """洗版订阅 → 按种子 enclosure 记录优先级基线（贡献档位=pri_order）。"""
        sub = _sub(id=1, best_version=1, total_episode=12, start_episode=1)
        oper = MagicMock()
        oper.get.return_value = sub
        priority = MagicMock()
        torrent_info = SimpleNamespace(enclosure="http://x/t.torrent", pri_order=80)
        ctx = SimpleNamespace(torrent_info=torrent_info)
        proxy = EventProxy(subscribe_oper=oper, priority_manager=priority)
        proxy.on_resource_download(SimpleNamespace(event_data=SimpleNamespace(
            origin='Subscribe|{"id": 1}', context=ctx, episodes=[3], cancel=False)))
        priority.capture_torrent_baseline.assert_called_once()
        args, kwargs = priority.capture_torrent_baseline.call_args
        assert args[1] == "http://x/t.torrent"
        assert kwargs.get("contributed_priority") == 80

    def test_non_best_version_skips_baseline(self):
        sub = _sub(id=1, best_version=0)
        oper = MagicMock()
        oper.get.return_value = sub
        priority = MagicMock()
        ctx = SimpleNamespace(torrent_info=SimpleNamespace(enclosure="x", pri_order=80))
        proxy = EventProxy(subscribe_oper=oper, priority_manager=priority)
        proxy.on_resource_download(SimpleNamespace(event_data=SimpleNamespace(
            origin='Subscribe|{"id": 1}', context=ctx, episodes=[3], cancel=False)))
        priority.capture_torrent_baseline.assert_not_called()
