"""暂停订阅低频补搜协调器单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.engine.types import PauseRecord
from subscribeassistantenhanced.pause.probe import (
    PROBE_LAST_SCHEDULED_AT,
    PROBE_REASON,
    PROBE_SCHEDULED_RUN_AT,
    PausedProbeCoordinator,
)


class FakeTimer:
    """测试用 Timer，记录调度参数并由测试显式触发回调。"""

    instances = []

    def __init__(self, delay, callback):
        self.delay = delay
        self.callback = callback
        self.started = False
        self.cancelled = False
        FakeTimer.instances.append(self)

    def start(self):
        self.started = True

    def cancel(self):
        self.cancelled = True

    def fire(self):
        self.callback()


def _sub(sid=1, state="S", best_version=0):
    """构造暂停订阅替身。"""
    return SimpleNamespace(
        id=sid,
        name=f"测试{sid}",
        tmdbid=100 + sid,
        season=1,
        episode_group=None,
        type="电视剧",
        state=state,
        best_version=best_version,
        best_version_full=0,
        total_episode=12,
        lack_episode=0,
    )


def _cfg(**kwargs):
    """构造 probe 所需配置替身。"""
    defaults = dict(
        pause_enhanced_enabled=True,
        paused_probe_reasons=["no_download"],
        paused_probe_min_pause_days=14,
        paused_probe_interval_hours=72,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _store(initial=None):
    """构造 TaskDataManager 兼容的内存读写闭包。"""
    data = {"subscribes": initial or {}}

    def read(key):
        return data.get(key, {})

    def update(key, updater):
        current = data.get(key, {})
        data[key] = updater(current)
        return data[key]

    return data, read, update


def _coordinator(subscribes, records, *, cfg=None, initial=None,
                 active_downloads=False, search_side_effect=None, now=1_000_000):
    """组装协调器与常用 mock。"""
    FakeTimer.instances = []
    data, read, update = _store(initial)
    subscribe_oper = MagicMock()
    by_id = {sub.id: sub for sub in subscribes}
    subscribe_oper.list.return_value = list(subscribes)
    subscribe_oper.get.side_effect = lambda sid: by_id.get(sid)
    subscribe_chain = MagicMock()
    if search_side_effect:
        subscribe_chain.search.side_effect = search_side_effect
    pause_manager = MagicMock()
    pause_manager.get_pause_record.side_effect = lambda sub: records.get(sub.id)

    def clear_probe_schedule(subscribe, include_last=False):
        sid = str(subscribe.id)

        def updater(current):
            task = current.get(sid, {})
            task.pop(PROBE_SCHEDULED_RUN_AT, None)
            task.pop(PROBE_REASON, None)
            if include_last:
                task.pop(PROBE_LAST_SCHEDULED_AT, None)
            current[sid] = task
            return current

        update("subscribes", updater)

    pause_manager.clear_probe_schedule.side_effect = clear_probe_schedule
    download_monitor = MagicMock()
    download_monitor.has_active_downloads.return_value = active_downloads
    coordinator = PausedProbeCoordinator(
        cfg or _cfg(),
        read,
        update,
        subscribe_oper,
        subscribe_chain,
        pause_manager,
        download_monitor=download_monitor,
        timer_factory=FakeTimer,
        now_fn=lambda: now,
        delay_fn=lambda: 120,
    )
    return coordinator, data, subscribe_oper, subscribe_chain, pause_manager, download_monitor


def test_empty_reasons_adopts_external_but_does_not_schedule():
    """空场景只登记外部暂停，不主动安排搜索。"""
    sub = _sub()
    records = {sub.id: None}
    coordinator, data, _oper, chain, pause, _monitor = _coordinator(
        [sub],
        records,
        cfg=_cfg(paused_probe_reasons=[]),
    )
    pause.adopt_external.side_effect = lambda subscribe: records.__setitem__(
        subscribe.id, PauseRecord(reason="external", since=1, detail="外部暂停")
    ) or True

    coordinator.run()

    pause.adopt_external.assert_called_once_with(sub)
    assert FakeTimer.instances == []
    chain.search.assert_not_called()
    assert data["subscribes"] == {}


def test_no_download_after_pause_and_interval_schedules_probe():
    """暂停满最小天数且超过间隔时写入调度字段并启动 Timer。"""
    sub = _sub()
    now = 1_000_000
    records = {sub.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载")}
    coordinator, data, _oper, chain, _pause, monitor = _coordinator([sub], records, now=now)

    coordinator.run()

    task = data["subscribes"][str(sub.id)]
    assert task[PROBE_LAST_SCHEDULED_AT] == now
    assert task[PROBE_SCHEDULED_RUN_AT] == now + 120
    assert task[PROBE_REASON] == "no_download"
    assert FakeTimer.instances[0].started is True
    monitor.has_active_downloads.assert_called_once_with(sub.id)
    chain.search.assert_not_called()


def test_min_pause_days_and_interval_skip_candidates():
    """未满暂停天数或未到间隔时不安排 probe。"""
    now = 1_000_000
    young = _sub(sid=1)
    frequent = _sub(sid=2)
    records = {
        young.id: PauseRecord(reason="no_download", since=now - 13 * 86400, detail="无下载"),
        frequent.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载"),
    }
    initial = {str(frequent.id): {PROBE_LAST_SCHEDULED_AT: now - 71 * 3600}}
    coordinator, data, _oper, _chain, _pause, _monitor = _coordinator(
        [young, frequent],
        records,
        initial=initial,
        now=now,
    )

    coordinator.run()

    assert FakeTimer.instances == []
    assert data["subscribes"] == initial


def test_zero_min_pause_days_disables_active_probe():
    """暂停满天数配置为 0 时不安排主动补搜。"""
    sub = _sub()
    now = 1_000_000
    records = {sub.id: PauseRecord(reason="no_download", since=now - 30 * 86400, detail="无下载")}
    coordinator, data, _oper, chain, _pause, _monitor = _coordinator(
        [sub],
        records,
        cfg=_cfg(paused_probe_min_pause_days=0),
        now=now,
    )

    coordinator.run()

    assert FakeTimer.instances == []
    assert data["subscribes"] == {}
    chain.search.assert_not_called()


def test_all_allows_known_future_external_and_unknown_without_excluding_best_version():
    """all 开放匹配全部原因，洗版订阅不被补搜额外排除。"""
    now = 1_000_000
    subs = [_sub(sid=1), _sub(sid=2), _sub(sid=3), _sub(sid=4, best_version=1)]
    reasons = ["no_download", "future_reason", "external", "airing_gap"]
    records = {
        sub.id: PauseRecord(reason=reason, since=now - 15 * 86400, detail=reason)
        for sub, reason in zip(subs, reasons)
    }
    coordinator, data, _oper, _chain, _pause, _monitor = _coordinator(
        subs,
        records,
        cfg=_cfg(paused_probe_reasons=["all", "no_download"]),
        now=now,
    )

    coordinator.run()

    assert len(FakeTimer.instances) == 4
    assert {task[PROBE_REASON] for task in data["subscribes"].values()} == set(reasons)


def test_without_all_unknown_reason_is_not_scheduled():
    """未选择 all 时，未知原因不参与主动补搜。"""
    now = 1_000_000
    sub = _sub()
    records = {sub.id: PauseRecord(reason="future_reason", since=now - 15 * 86400, detail="future")}
    coordinator, _data, _oper, chain, _pause, _monitor = _coordinator([sub], records, now=now)

    coordinator.run()

    assert FakeTimer.instances == []
    chain.search.assert_not_called()


def test_each_round_schedules_at_most_ten_candidates():
    """单轮最多安排 10 个候选。"""
    now = 1_000_000
    subs = [_sub(sid=i) for i in range(1, 13)]
    records = {
        sub.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载")
        for sub in subs
    }
    coordinator, data, _oper, _chain, _pause, _monitor = _coordinator(subs, records, now=now)

    coordinator.run()

    assert len(FakeTimer.instances) == 10
    assert len(data["subscribes"]) == 10


def test_existing_active_download_skips_probe():
    """已有进行中下载的暂停订阅不安排补搜。"""
    now = 1_000_000
    sub = _sub()
    records = {sub.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载")}
    coordinator, _data, _oper, _chain, _pause, _monitor = _coordinator(
        [sub],
        records,
        active_downloads=True,
        now=now,
    )

    coordinator.run()

    assert FakeTimer.instances == []


def test_timer_success_cleans_temporary_fields_and_keeps_last_scheduled():
    """Timer 成功执行后清理本轮临时字段，保留 last_scheduled 用于限频。"""
    now = 1_000_000
    sub = _sub()
    records = {sub.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载")}
    coordinator, data, _oper, chain, _pause, _monitor = _coordinator([sub], records, now=now)
    coordinator.run()

    FakeTimer.instances[0].fire()

    chain.search.assert_called_once_with(sid=sub.id)
    task = data["subscribes"][str(sub.id)]
    assert task[PROBE_LAST_SCHEDULED_AT] == now
    assert PROBE_SCHEDULED_RUN_AT not in task
    assert PROBE_REASON not in task


def test_timer_exception_counts_attempt_and_does_not_reschedule():
    """搜索异常仍保留 last_scheduled，不立即重试或通知。"""
    now = 1_000_000
    sub = _sub()
    records = {sub.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载")}
    coordinator, data, _oper, chain, _pause, _monitor = _coordinator(
        [sub],
        records,
        search_side_effect=RuntimeError("boom"),
        now=now,
    )
    coordinator.run()

    FakeTimer.instances[0].fire()

    chain.search.assert_called_once_with(sid=sub.id)
    task = data["subscribes"][str(sub.id)]
    assert task[PROBE_LAST_SCHEDULED_AT] == now
    assert PROBE_SCHEDULED_RUN_AT not in task
    assert PROBE_REASON not in task
    assert len(FakeTimer.instances) == 1


def test_timer_finally_cleans_schedule_when_search_deletes_subscribe():
    """搜索执行期间订阅被删除时仍按 sid 清理本轮调度字段。"""
    now = 1_000_000
    sub = _sub()
    records = {sub.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载")}
    coordinator, data, oper, chain, _pause, _monitor = _coordinator([sub], records, now=now)

    def delete_during_search(sid):
        oper.get.side_effect = lambda _sid: None

    chain.search.side_effect = delete_during_search
    coordinator.run()

    FakeTimer.instances[0].fire()

    chain.search.assert_called_once_with(sid=sub.id)
    task = data["subscribes"][str(sub.id)]
    assert task[PROBE_LAST_SCHEDULED_AT] == now
    assert PROBE_SCHEDULED_RUN_AT not in task
    assert PROBE_REASON not in task


def test_timer_preflight_skips_changed_state_and_keeps_last_scheduled():
    """执行前状态已非暂停时跳过搜索，并保留 last_scheduled 作为本轮尝试。"""
    now = 1_000_000
    sub = _sub()
    records = {sub.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载")}
    coordinator, data, _oper, chain, _pause, _monitor = _coordinator([sub], records, now=now)
    coordinator.run()

    sub.state = "R"
    FakeTimer.instances[0].fire()
    chain.search.assert_not_called()
    task = data["subscribes"][str(sub.id)]
    assert task[PROBE_LAST_SCHEDULED_AT] == now
    assert PROBE_SCHEDULED_RUN_AT not in task
    assert PROBE_REASON not in task

    coordinator.run()
    assert len(FakeTimer.instances) == 1


def test_timer_preflight_clears_last_when_reason_changes():
    """执行前暂停原因变化时跳过搜索，并清理 last 让新原因重新判断。"""
    now = 1_000_000
    sub = _sub()
    records = {sub.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载")}
    coordinator, data, _oper, chain, _pause, _monitor = _coordinator([sub], records, now=now)
    coordinator.run()
    records[sub.id] = PauseRecord(reason="airing_gap", since=now - 15 * 86400, detail="间隔")

    FakeTimer.instances[0].fire()

    chain.search.assert_not_called()
    task = data["subscribes"][str(sub.id)]
    assert PROBE_LAST_SCHEDULED_AT not in task
    assert PROBE_SCHEDULED_RUN_AT not in task
    assert PROBE_REASON not in task


def test_timer_preflight_skips_when_min_pause_days_disabled():
    """执行前补搜天数改为 0 时跳过搜索，并清理 last 让新配置重新判断。"""
    now = 1_000_000
    sub = _sub()
    cfg = _cfg()
    records = {sub.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载")}
    coordinator, data, _oper, chain, _pause, _monitor = _coordinator([sub], records, cfg=cfg, now=now)
    coordinator.run()
    cfg.paused_probe_min_pause_days = 0

    FakeTimer.instances[0].fire()

    chain.search.assert_not_called()
    task = data["subscribes"][str(sub.id)]
    assert PROBE_LAST_SCHEDULED_AT not in task
    assert PROBE_SCHEDULED_RUN_AT not in task
    assert PROBE_REASON not in task


def test_timer_preflight_cleans_schedule_when_subscribe_deleted():
    """执行前订阅已不存在时按 sid 清理本轮调度字段。"""
    now = 1_000_000
    sub = _sub()
    records = {sub.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载")}
    coordinator, data, oper, chain, _pause, _monitor = _coordinator([sub], records, now=now)
    coordinator.run()
    oper.get.return_value = None
    oper.get.side_effect = lambda _sid: None

    FakeTimer.instances[0].fire()

    chain.search.assert_not_called()
    task = data["subscribes"][str(sub.id)]
    assert task[PROBE_LAST_SCHEDULED_AT] == now
    assert PROBE_SCHEDULED_RUN_AT not in task
    assert PROBE_REASON not in task


def test_stop_invalidates_pending_timer():
    """stop 后旧 Timer 不会继续搜索。"""
    now = 1_000_000
    sub = _sub()
    records = {sub.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载")}
    coordinator, _data, _oper, chain, _pause, _monitor = _coordinator([sub], records, now=now)
    coordinator.run()

    coordinator.stop()
    FakeTimer.instances[0].fire()

    assert FakeTimer.instances[0].cancelled is True
    chain.search.assert_not_called()


def test_stale_generation_timer_does_not_clear_new_schedule_fields():
    """旧 generation Timer 失效后不得清理新一轮调度字段。"""
    now = 1_000_000
    sub = _sub()
    records = {sub.id: PauseRecord(reason="no_download", since=now - 15 * 86400, detail="无下载")}
    coordinator, data, _oper, chain, _pause, _monitor = _coordinator([sub], records, now=now)
    coordinator.run()
    old_timer = FakeTimer.instances[0]

    coordinator.stop()
    data["subscribes"][str(sub.id)] = {
        PROBE_LAST_SCHEDULED_AT: now + 3600,
        PROBE_SCHEDULED_RUN_AT: now + 3720,
        PROBE_REASON: "external",
    }

    old_timer.fire()

    chain.search.assert_not_called()
    assert data["subscribes"][str(sub.id)] == {
        PROBE_LAST_SCHEDULED_AT: now + 3600,
        PROBE_SCHEDULED_RUN_AT: now + 3720,
        PROBE_REASON: "external",
    }
