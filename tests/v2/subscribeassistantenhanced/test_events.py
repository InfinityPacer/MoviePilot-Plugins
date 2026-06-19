"""events.py 事件薄代理单测——顺序和域分发。"""
from types import SimpleNamespace
from unittest.mock import MagicMock, call

from subscribeassistantenhanced.engine.types import CompletionSignal, PauseRecord
from subscribeassistantenhanced.events import EventProxy
from subscribeassistantenhanced.pause.airing import AiringPauseChecker


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
    defaults = dict(type="tv", next_episode_to_air=None, release_date=None, first_air_date=None)
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


class TestEventOrdering:
    """事件处理顺序验证。"""

    def test_episodes_refresh_f_before_pending(self):
        """EpisodesRefresh 中 F 记录在 pending 覆盖之前。"""
        call_order = []
        volatility = MagicMock()
        volatility.record.side_effect = lambda **kw: call_order.append("f_record")
        pending_refresh = MagicMock()
        pending_refresh.handle_refresh.side_effect = lambda ev: call_order.append("pending_refresh")

        proxy = EventProxy(volatility=volatility, pending_refresh=pending_refresh)
        event = SimpleNamespace(event_data=SimpleNamespace(current_total_episode=12, subscribe_id=1))
        proxy.on_episodes_refresh(event)

        assert call_order == ["f_record", "pending_refresh"]

    def test_episodes_refresh_uses_event_data_for_f_and_pending(self):
        """EpisodesRefresh 必须从 event.event_data 读写，主程序只读取该数据类。"""
        from app.schemas.event import SubscribeEpisodesRefreshEventData
        call_order = []
        volatility = MagicMock()
        volatility.record.side_effect = lambda **kw: call_order.append(("f", kw))

        def pending_handle(data):
            call_order.append(("pending", data.subscribe_id))
            data.updated = True
            data.total_episode = 8
            data.source = "subscribeassistantenhanced"
            data.reason = "待定中，锁定为已播出集数 8"

        pending_refresh = MagicMock()
        pending_refresh.handle_refresh.side_effect = pending_handle
        proxy = EventProxy(volatility=volatility, pending_refresh=pending_refresh)
        data = SubscribeEpisodesRefreshEventData(current_total_episode=12, subscribe_id=1, season=1)

        proxy.on_episodes_refresh(SimpleNamespace(event_data=data))

        assert call_order[0] == ("f", {"total": 12, "subscribe_id": 1})
        assert call_order[1] == ("pending", 1)
        assert data.updated is True
        assert data.total_episode == 8

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

    def test_download_added_registers_monitor_without_resuming(self):
        """DownloadAdded → 仅经 source 解析订阅后登记监控数据，不在此处恢复暂停。"""
        sub = _sub(id=1, state="S")
        oper = MagicMock()
        oper.get.return_value = sub
        monitor = MagicMock()
        pause_mgr = MagicMock()
        proxy = EventProxy(subscribe_oper=oper, download_monitor=monitor, pause_manager=pause_mgr)
        proxy.on_download_added(SimpleNamespace(event_data={
            "source": 'Subscribe|{"id": 1}', "hash": "h1", "episodes": [1, 2], "downloader": "qb",
        }))
        monitor.on_download.assert_called_once_with(
            1, "h1", episodes=[1, 2], downloader="qb",
            enclosure=None, page_url=None, title=None, description=None)
        # 下载添加事件不触发暂停恢复；恢复仅由元数据巡检的上映双向判定负责。
        pause_mgr.resume.assert_not_called()

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

    def test_transfer_complete_pauses_running_subscription_after_library_update(self):
        """订阅下载入库后，当天应立即按播出间隔暂停已进入 R 态的订阅。"""
        sub = _sub(id=1, state="R", lack_episode=5, note=list(range(31, 88)), total_episode=92)
        tm = MagicMock()
        tm.read.return_value = {"abc": {"subscribe_id": 1}}
        oper = MagicMock()
        oper.get.return_value = sub
        monitor = MagicMock()
        pause = MagicMock()
        airing = MagicMock()
        airing.check_pre_air.return_value = None
        record = PauseRecord(reason="airing_gap", detail="下一集 2026-06-21，距今 7 天")
        airing.check.return_value = record
        episodes = [SimpleNamespace(air_date="2026-06-21", episode_number=88)]
        mediainfo = _mi(next_episode_to_air=None)
        tmdb_episodes = MagicMock(return_value=episodes)
        proxy = EventProxy(
            download_monitor=monitor,
            task_manager=tm,
            subscribe_oper=oper,
            pause_manager=pause,
            airing_checker=airing,
            recognize_mediainfo_fn=MagicMock(return_value=mediainfo),
            is_tv_fn=lambda _mi: True,
            tmdb_episodes_fn=tmdb_episodes,
        )

        proxy.on_transfer_complete(SimpleNamespace(event_data={
            "download_hash": "abc", "transferinfo": None,
        }))

        monitor.clear_download_pending.assert_called_once_with(1, "abc")
        airing.check.assert_called_once_with(
            sub,
            mediainfo,
            next_episode=None,
            latest_episode=None,
            episodes=episodes,
        )
        pause.pause.assert_called_once_with(sub, record)

    def test_transfer_complete_does_not_pause_new_subscription(self):
        """订阅仍为 N 态时，入库事件不触发播出暂停。"""
        sub = _sub(id=1, state="N")
        tm = MagicMock()
        tm.read.return_value = {"abc": {"subscribe_id": 1}}
        oper = MagicMock()
        oper.get.return_value = sub
        pause = MagicMock()
        airing = MagicMock()
        proxy = EventProxy(
            task_manager=tm,
            subscribe_oper=oper,
            pause_manager=pause,
            airing_checker=airing,
            recognize_mediainfo_fn=MagicMock(return_value=_mi()),
        )

        proxy.on_transfer_complete(SimpleNamespace(event_data={
            "download_hash": "abc", "transferinfo": None,
        }))

        airing.check.assert_not_called()
        pause.pause.assert_not_called()

    def test_non_best_version_mode_label_is_empty(self):
        """普通订阅不应被洗版模式标签误标。"""
        assert EventProxy._best_version_mode_label(_sub(best_version=0)) == ""

    def test_best_version_mode_label_distinguishes_episode_and_full(self):
        """洗版订阅按 best_version_full 区分分集和全集。"""
        assert EventProxy._best_version_mode_label(_sub(best_version=1, best_version_full=0)) == "分集洗版"
        assert EventProxy._best_version_mode_label(_sub(best_version=1, best_version_full=1)) == "全集洗版"

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
        proxy = EventProxy()
        event = SimpleNamespace(event_data=SimpleNamespace(current_total_episode=12, subscribe_id=1))
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

    def test_modified_state_change_clears_pause(self):
        pause = MagicMock()
        sub = _sub(id=9)
        oper = MagicMock()
        oper.get.return_value = sub
        proxy = EventProxy(pause_manager=pause, subscribe_oper=oper)
        proxy.on_subscribe_modified(SimpleNamespace(event_data={
            "subscribe_id": 9,
            "subscribe_info": {"state": "R"},
            "old_subscribe_info": {"state": "S"},
        }))
        pause.clear_pause_record.assert_called_once_with(sub)

    def test_modified_without_state_change_noop(self):
        pause = MagicMock()
        oper = MagicMock()
        proxy = EventProxy(pause_manager=pause, subscribe_oper=oper)
        proxy.on_subscribe_modified(SimpleNamespace(event_data={
            "subscribe_id": 9,
            "subscribe_info": {"name": "X", "state": "R"},
            "old_subscribe_info": {"name": "Y", "state": "R"},
        }))
        pause.clear_pause_record.assert_not_called()

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
        priority.backfill_existing.assert_called_once_with(sub, [1, 2, 3])

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

    def test_added_runs_user_auto_pause(self):
        """SubscribeAdded → 按 subscribe_id 查库后跑用户名自动暂停。"""
        sub = _sub(id=7)
        oper = MagicMock()
        oper.get.return_value = sub
        pause = MagicMock()
        proxy = EventProxy(subscribe_oper=oper, pause_manager=pause)
        proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7}))
        pause.check_auto_pause_for_user.assert_called_once_with(sub)

    def test_added_full_best_version_skips_backfill_detection(self):
        """新增全集洗版订阅不探测媒体库已有集。"""
        sub = _sub(id=7, best_version=1, best_version_full=1)
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

        proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7}))

        detect_existing.assert_not_called()
        priority.backfill_existing.assert_not_called()

    def _added_proxy(self, sub, pending_result, airing_record):
        oper = MagicMock()
        oper.get.return_value = sub
        pause = MagicMock()
        pending = MagicMock()
        pending.should_enter_pending.return_value = pending_result
        airing = MagicMock()
        airing.check_pre_air.return_value = None
        airing.check.return_value = airing_record
        proxy = EventProxy(
            subscribe_oper=oper, pause_manager=pause, pending_judge=pending, airing_checker=airing,
            mediainfo_from_dict=lambda d: _mi(),
            is_tv_fn=lambda mi: True,
            tmdb_episodes_fn=lambda tmdbid, season, episode_group=None: [],
            evaluate_fn=lambda s, m: None,
        )
        return proxy, pause, pending, airing

    def test_added_tv_pending_enters_pending(self):
        """电视剧待定命中 → mark_pending，不再播出暂停。"""
        sub = _sub(id=7, best_version=0, tmdbid=100, season=1)
        proxy, pause, pending, airing = self._added_proxy(sub, (True, "集数不足"), None)
        proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {"x": 1}}))
        pending.mark_pending.assert_called_once_with(sub, source="pending_judge", reason="集数不足")
        airing.check.assert_not_called()

    def test_added_uses_episode_group_scope(self):
        """新增订阅评估待定时必须按订阅 episode_group 查询集列表。"""
        sub = _sub(id=7, best_version=0, tmdbid=100, season=1, episode_group="eg-1")
        oper = MagicMock()
        oper.get.return_value = sub
        tmdb_episodes = MagicMock(return_value=[])
        pending = MagicMock()
        pending.should_enter_pending.return_value = (False, "")
        airing = MagicMock()
        airing.check_pre_air.return_value = None
        proxy = EventProxy(
            subscribe_oper=oper,
            pending_judge=pending,
            airing_checker=airing,
            pause_manager=MagicMock(),
            mediainfo_from_dict=lambda _data: _mi(),
            is_tv_fn=lambda _mi: True,
            tmdb_episodes_fn=tmdb_episodes,
            evaluate_fn=lambda _subscribe, _mediainfo: None,
        )

        proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {"x": 1}}))

        tmdb_episodes.assert_called_once_with(100, 1, episode_group="eg-1")

    def test_added_new_subscription_does_not_airing_pause_when_not_pending(self):
        """新增订阅仍为 N 态时不做播出暂停，需等首轮搜索后进入 R 态。"""
        sub = _sub(id=7, best_version=0, tmdbid=100, season=1, state="N")
        record = object()
        oper = MagicMock()
        oper.get.return_value = sub
        pause = MagicMock()
        pending = MagicMock()
        pending.should_enter_pending.return_value = (False, "")
        airing = MagicMock()
        airing.check_pre_air.return_value = None
        airing.check.return_value = record
        episodes = [SimpleNamespace(air_date="2026-06-21", episode_number=12)]
        mediainfo = _mi(next_episode_to_air=None)
        proxy = EventProxy(
            subscribe_oper=oper,
            pause_manager=pause,
            pending_judge=pending,
            airing_checker=airing,
            mediainfo_from_dict=lambda _data: mediainfo,
            is_tv_fn=lambda _mi: True,
            tmdb_episodes_fn=lambda _tmdbid, _season, episode_group=None: episodes,
            evaluate_fn=lambda _subscribe, _mediainfo: None,
        )

        proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {"x": 1}}))

        pending.mark_pending.assert_not_called()
        airing.check.assert_not_called()
        pause.pause.assert_not_called()

    def test_added_history_season_without_next_episode_does_not_pause_by_latest_air_date(self):
        """新增历史季订阅没有下一集信息时，不按最后已播日期直接暂停。"""
        sub = _sub(id=7, best_version=0, tmdbid=100, season=1)
        oper = MagicMock()
        oper.get.return_value = sub
        pause = MagicMock()
        pending = MagicMock()
        pending.should_enter_pending.return_value = (False, "")
        airing = AiringPauseChecker(
            pause_days=14,
            evaluate_fn=MagicMock(return_value=CompletionSignal()),
        )
        proxy = EventProxy(
            subscribe_oper=oper,
            pause_manager=pause,
            pending_judge=pending,
            airing_checker=airing,
            mediainfo_from_dict=lambda _data: _mi(next_episode_to_air=None),
            is_tv_fn=lambda _mi: True,
            tmdb_episodes_fn=lambda tmdbid, season, episode_group=None: [
                SimpleNamespace(air_date="2000-01-01", episode_number=15)
            ],
            evaluate_fn=lambda _subscribe, _mediainfo: None,
        )

        proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {"x": 1}}))

        pending.mark_pending.assert_not_called()
        pause.pause.assert_not_called()

    def test_added_full_best_version_skips_pause_pending(self):
        """全集洗版只跑用户名暂停，不做按集播出暂停或待定。"""
        sub = _sub(id=7, best_version=1, best_version_full=1)
        proxy, pause, pending, _airing = self._added_proxy(sub, (False, ""), None)
        proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {"x": 1}}))
        pending.should_enter_pending.assert_not_called()
        pause.check_auto_pause_for_user.assert_called_once_with(sub)

    def test_added_episode_best_version_uses_same_pending_flow(self):
        """分集洗版使用按集订阅的待定判定流程。"""
        sub = _sub(id=7, best_version=1, best_version_full=0)
        proxy, _pause, pending, _airing = self._added_proxy(sub, (True, "集数不足"), None)

        proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {"x": 1}}))

        pending.should_enter_pending.assert_called_once()
        pending.mark_pending.assert_called_once_with(
            sub,
            source="pending_judge",
            reason="集数不足",
        )

    def test_complete_clears_tasks_and_snapshots(self):
        """SubscribeComplete → 先保存 H 快照再清实例数据，避免历史被清理丢失。"""
        order = []
        tm = MagicMock()
        tm.clear_tasks.side_effect = lambda _sid: order.append("clear")
        verifier = MagicMock()
        verifier.snapshot.side_effect = lambda **_kwargs: order.append("snapshot")
        sub = _sub(id=5, tmdbid=100, season=1)
        oper = MagicMock()
        oper.get.return_value = sub
        proxy = EventProxy(task_manager=tm, verifier=verifier, subscribe_oper=oper)
        proxy.on_subscribe_complete(SimpleNamespace(event_data={
            "subscribe_id": 5,
            "subscribe_info": {"tmdbid": 100, "season": 1},
        }))
        tm.clear_tasks.assert_called_once_with(5)
        verifier.snapshot.assert_called_once()
        assert order == ["snapshot", "clear"]
        _, kwargs = verifier.snapshot.call_args
        assert kwargs.get("subscribe") is sub

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


class TestPluginActionToggle:
    """PluginAction /subscribe_toggle 切换订阅启用/禁用。"""

    def _event(self, **data):
        data.setdefault("action", "subscribe_toggle")
        return SimpleNamespace(event_data=data)

    @staticmethod
    def _assert_state_update(oper, subscribe_id: int, state: str):
        """断言真实订阅状态更新会同步刷新更新时间。"""
        oper.update.assert_called_once()
        assert oper.update.call_args.args[0] == subscribe_id
        payload = oper.update.call_args.args[1]
        assert payload["state"] == state
        assert payload["last_update"]

    def test_toggle_single_match_enables(self):
        sub = _sub(id=3, name="X", state="S")
        oper = MagicMock()
        oper.list.return_value = [sub]
        msgs = []
        proxy = EventProxy(subscribe_oper=oper, post_message=lambda **kw: msgs.append(kw))
        proxy.on_plugin_action(self._event(arg_str="3"))
        self._assert_state_update(oper, 3, "R")
        assert msgs and "启用" in msgs[0]["title"]

    def test_toggle_single_match_disables(self):
        sub = _sub(id=3, name="X", state="R")
        oper = MagicMock()
        oper.list.return_value = [sub]
        proxy = EventProxy(subscribe_oper=oper, post_message=lambda **kw: None)
        proxy.on_plugin_action(self._event(arg_str="3"))
        self._assert_state_update(oper, 3, "S")

    def test_toggle_by_name(self):
        sub = _sub(id=3, name="剧名", state="R")
        oper = MagicMock()
        oper.list.return_value = [sub]
        proxy = EventProxy(subscribe_oper=oper, post_message=lambda **kw: None)
        proxy.on_plugin_action(self._event(arg_str="剧名"))
        self._assert_state_update(oper, 3, "S")

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
