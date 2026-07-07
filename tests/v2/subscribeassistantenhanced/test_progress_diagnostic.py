"""无进展诊断协调器单测。"""
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import subscribeassistantenhanced.progress.diagnostic as diagnostic_module
from subscribeassistantenhanced.progress import ProgressDiagnosticCoordinator


STATE_KEY = "subscribes"
ROUNDS_FIELD = "progress_diagnostic_stalled_rounds"
MISSING_FIELD = "progress_diagnostic_last_missing_count"
NOTIFIED_FIELD = "progress_diagnostic_notified_at"
PROGRESS_FIELDS = {ROUNDS_FIELD, MISSING_FIELD, NOTIFIED_FIELD}


def _sub(sid=1, missing=5, media_type="电视剧", name=None, season=1, state="R"):
    """构造含固定 Subscribe 字段的订阅替身。"""
    return SimpleNamespace(
        id=sid,
        name=name or f"测试{sid}",
        season=season,
        type=media_type,
        state=state,
        lack_episode=missing,
    )


def _cfg(**kwargs):
    """构造无进展诊断所需配置替身。"""
    defaults = dict(
        progress_diagnostic_mode="notify",
        progress_diagnostic_stalled_rounds=3,
        progress_diagnostic_cooldown_hours=24,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _store(initial=None):
    """构造 TaskDataManager 兼容的内存读写闭包。"""
    data = {STATE_KEY: initial or {}}
    update_calls = []

    def read(key):
        return {sid: dict(record) for sid, record in data.get(key, {}).items()}

    def update(key, updater):
        update_calls.append(key)
        current = data.get(key, {})
        data[key] = updater(current)
        return data[key]

    return data, read, update, update_calls


def _coordinator(subs, cfg=None, initial=None, now=1000.0):
    """组装被测协调器与内存存储、订阅查询、通知替身。"""
    data, read, update, update_calls = _store(initial)
    oper = MagicMock()
    oper.list.return_value = subs
    notify = MagicMock()
    clock = {"t": now}
    coord = ProgressDiagnosticCoordinator(
        cfg or _cfg(),
        read,
        update,
        subscribe_oper=oper,
        notify_fn=notify,
        now_fn=lambda: clock["t"],
    )
    return coord, data, notify, oper, clock, update_calls


def _record(data, sid=1):
    return data[STATE_KEY].get(str(sid), {})


def _run_to_threshold(subs, cfg=None, initial=None):
    coord, data, notify, oper, clock, update_calls = _coordinator(subs, cfg=cfg, initial=initial)
    for _ in range(4):
        coord.run()
    return coord, data, notify, oper, clock, update_calls


def test_disabled_switch_does_not_write_state():
    """诊断关闭时不读订阅、不写状态。"""
    coord, data, notify, oper, _clock, update_calls = _coordinator(
        [_sub()],
        cfg=_cfg(progress_diagnostic_mode="off"),
    )

    coord.run()

    oper.list.assert_not_called()
    assert data[STATE_KEY] == {}
    assert update_calls == []
    notify.assert_not_called()


def test_enabled_subscription_list_uses_running_state():
    """每轮只读取启用中的订阅。"""
    coord, _data, _notify, oper, _clock, _update_calls = _coordinator([_sub()])

    coord.run()

    oper.list.assert_called_once_with(state="R")


def test_first_observation_records_baseline_in_subscribe_task():
    """首次观察只写入订阅任务记录，不通知。"""
    coord, data, notify, _oper, _clock, update_calls = _coordinator(
        [_sub(sid=7, missing=5)],
        initial={"7": {"unrelated": "keep"}},
    )

    coord.run()

    assert _record(data, 7) == {
        "unrelated": "keep",
        ROUNDS_FIELD: 0,
        MISSING_FIELD: 5,
    }
    assert update_calls == [STATE_KEY]
    notify.assert_not_called()


def test_unchanged_missing_count_increments_stalled_rounds():
    """缺失数量不变时累计无进展轮数。"""
    coord, data, notify, _oper, _clock, _update_calls = _coordinator([_sub(missing=5)])

    coord.run()
    coord.run()

    assert _record(data)[ROUNDS_FIELD] == 1
    assert _record(data)[MISSING_FIELD] == 5
    notify.assert_not_called()


def test_missing_count_decrease_resets_rounds():
    """缺失数量减少表示已有进展，重置无进展轮数。"""
    sub = _sub(missing=5)
    coord, data, _notify, _oper, _clock, _update_calls = _coordinator([sub])
    coord.run()
    coord.run()

    sub.lack_episode = 3
    coord.run()

    assert _record(data)[ROUNDS_FIELD] == 0
    assert _record(data)[MISSING_FIELD] == 3


def test_missing_count_increase_also_increments_rounds():
    """缺失数量不降也属于无进展，增加时继续累计。"""
    sub = _sub(missing=5)
    coord, data, _notify, _oper, _clock, _update_calls = _coordinator([sub])
    coord.run()

    sub.lack_episode = 6
    coord.run()

    assert _record(data)[ROUNDS_FIELD] == 1
    assert _record(data)[MISSING_FIELD] == 6


def test_completed_tv_clears_only_progress_fields_and_preserves_record():
    """剧集缺失补齐时只清理本模块字段，不删除整个订阅任务记录。"""
    initial = {
        "1": {
            "unrelated": "keep",
            ROUNDS_FIELD: 2,
            MISSING_FIELD: 1,
            NOTIFIED_FIELD: 123.0,
        }
    }
    coord, data, notify, _oper, _clock, update_calls = _coordinator(
        [_sub(missing=0)],
        initial=initial,
    )

    coord.run()

    assert _record(data) == {"unrelated": "keep"}
    assert update_calls == [STATE_KEY]
    notify.assert_not_called()


def test_movie_subscription_uses_missing_count_one_and_movie_detail_text():
    """电影按仍未完成处理，并使用电影明细文案。"""
    subs = [_sub(media_type="电影", name="电影A")]
    _coord, data, notify, _oper, _clock, _update_calls = _run_to_threshold(subs)

    assert _record(data)[MISSING_FIELD] == 1
    notify.assert_called_once()
    assert "· 电影A（仍未完成）" in notify.call_args.kwargs["text"]


def test_unsupported_media_type_is_skipped_and_logs_detail(monkeypatch):
    """非电影/电视剧订阅跳过，并输出 detail 便于排查配置来源。"""
    detail = MagicMock()
    monkeypatch.setattr(diagnostic_module, "detail", detail)
    coord, data, notify, _oper, _clock, update_calls = _coordinator([
        _sub(media_type="动漫", name="非标准"),
    ])

    coord.run()

    assert data[STATE_KEY] == {}
    assert update_calls == []
    notify.assert_not_called()
    assert any("不支持的媒体类型" in call.args[0] for call in detail.call_args_list)


def test_below_threshold_does_not_notify():
    """未达到阈值前只更新状态，不发送通知。"""
    coord, data, notify, _oper, _clock, _update_calls = _coordinator([_sub(missing=5)])

    coord.run()
    coord.run()
    coord.run()

    assert _record(data)[ROUNDS_FIELD] == 2
    notify.assert_not_called()


def test_threshold_hit_sends_spec_summary_notification():
    """达到阈值时发送符合规格的单订阅汇总通知。"""
    _coord, data, notify, _oper, _clock, _update_calls = _run_to_threshold([
        _sub(name="剧A", missing=5),
    ])

    notify.assert_called_once()
    args, kwargs = notify.call_args
    assert args[0] == "订阅无进展：剧A"
    assert kwargs["text"] == "· 剧A S1（仍缺 5 集）"
    assert kwargs["reason"] == "连续 3 轮巡检未观察到订阅进展"
    assert kwargs["action"] == (
        "可能原因包括资源暂未发布、仍在播出/上映窗口、订阅规则或站点范围较窄、识别或下载异常等；"
        "本提示仅供参考"
    )
    assert kwargs["follow_up"] == "如确认规则或站点范围过窄，可在原生订阅中调整后由订阅链路继续补全"
    assert kwargs["link"] == "#/subscribe/tv?tab=mysub"
    assert "image" not in kwargs
    assert kwargs["diagnostic"] is True
    assert _record(data)[NOTIFIED_FIELD] == 1000.0


def test_cooldown_within_window_suppresses_repeat_notification():
    """冷却期内不重复通知。"""
    _coord, data, notify, _oper, _clock, _update_calls = _run_to_threshold([
        _sub(missing=5),
    ])
    assert notify.call_count == 1

    coord, data, notify, _oper, _clock, _update_calls = _coordinator(
        [_sub(missing=5)],
        initial=data[STATE_KEY],
        now=1000.0 + 3600,
    )
    coord.run()

    assert notify.call_count == 0
    assert _record(data)[ROUNDS_FIELD] == 4
    assert _record(data)[NOTIFIED_FIELD] == 1000.0


def test_after_cooldown_re_notifies_and_updates_notified_time():
    """超过冷却期后允许再次通知并刷新通知时间。"""
    _coord, data, notify, _oper, _clock, _update_calls = _run_to_threshold([
        _sub(missing=5),
    ])
    assert notify.call_count == 1

    coord, data, notify, _oper, _clock, _update_calls = _coordinator(
        [_sub(missing=5)],
        initial=data[STATE_KEY],
        now=1000.0 + 25 * 3600,
    )
    coord.run()

    notify.assert_called_once()
    assert _record(data)[NOTIFIED_FIELD] == 1000.0 + 25 * 3600


def test_multiple_due_subscriptions_merge_into_one_summary():
    """多个订阅同轮达标时合并为单条通知。"""
    subs = [
        _sub(sid=1, name="剧A", missing=5),
        _sub(sid=2, name="电影B", media_type="电影"),
    ]

    _coord, _data, notify, _oper, _clock, _update_calls = _run_to_threshold(subs)

    notify.assert_called_once()
    args, kwargs = notify.call_args
    assert args[0] == "订阅无进展：2 个订阅"
    assert kwargs["text"].splitlines() == [
        "· 剧A S1（仍缺 5 集）",
        "· 电影B（仍未完成）",
    ]


def test_more_than_twenty_due_subscriptions_truncates_detail():
    """超过 20 个订阅时截断明细并保留总数提示。"""
    subs = [_sub(sid=i, name=f"剧{i}", missing=5) for i in range(21)]

    _coord, _data, notify, _oper, _clock, _update_calls = _run_to_threshold(subs)

    lines = notify.call_args.kwargs["text"].splitlines()
    assert len(lines) == 21
    assert lines[-1] == "…… 等共 21 个订阅"
    assert lines[0] == "· 剧0 S1（仍缺 5 集）"


def test_notification_failure_does_not_write_notified_time():
    """通知失败时保留进度计数但不写 notified_at，下一轮可重试。"""
    coord, data, notify, _oper, _clock, _update_calls = _coordinator([
        _sub(missing=5),
    ])
    notify.side_effect = RuntimeError("notify failed")

    for _ in range(4):
        coord.run()

    assert notify.call_count == 1
    assert _record(data)[ROUNDS_FIELD] == 3
    assert _record(data)[MISSING_FIELD] == 5
    assert NOTIFIED_FIELD not in _record(data)


def test_notification_success_writes_notified_time_after_summary():
    """通知成功后才写 notified_at。"""
    coord, data, notify, _oper, _clock, _update_calls = _coordinator([
        _sub(missing=5),
    ])
    seen_notified_values = []

    def notify_side_effect(*_args, **_kwargs):
        seen_notified_values.append(_record(data).get(NOTIFIED_FIELD))

    notify.side_effect = notify_side_effect
    for _ in range(4):
        coord.run()

    assert seen_notified_values == [None]
    assert _record(data)[NOTIFIED_FIELD] == 1000.0


def test_updater_preserves_lock_current_unrelated_fields():
    """批量更新只合并本模块字段，不能覆盖锁内当前记录的并发字段。"""
    data = {STATE_KEY: {"1": {"unrelated": "from-snapshot"}}}
    update_calls = []

    def read(key):
        return {sid: dict(record) for sid, record in data.get(key, {}).items()}

    def update(key, updater):
        update_calls.append(key)
        data[key]["1"]["concurrent"] = "keep"
        data[key] = updater(data[key])
        return data[key]

    oper = MagicMock()
    oper.list.return_value = [_sub(sid=1, missing=5)]
    notify = MagicMock()
    coord = ProgressDiagnosticCoordinator(
        _cfg(),
        read,
        update,
        subscribe_oper=oper,
        notify_fn=notify,
        now_fn=lambda: 1000.0,
    )

    coord.run()

    assert data[STATE_KEY]["1"] == {
        "unrelated": "from-snapshot",
        "concurrent": "keep",
        ROUNDS_FIELD: 0,
        MISSING_FIELD: 5,
    }
    assert update_calls == [STATE_KEY]


def test_non_running_subscription_clears_stale_progress_fields_only():
    """离开启用列表的订阅清理诊断字段，保留同记录中的其他任务状态。"""
    initial = {
        "9": {
            "unrelated": "keep",
            ROUNDS_FIELD: 3,
            MISSING_FIELD: 5,
            NOTIFIED_FIELD: 1000.0,
        }
    }
    coord, data, notify, oper, _clock, update_calls = _coordinator([], initial=initial)

    coord.run()

    oper.list.assert_called_once_with(state="R")
    assert data[STATE_KEY]["9"] == {"unrelated": "keep"}
    assert update_calls == [STATE_KEY]
    notify.assert_not_called()


def test_one_run_performs_one_subscribes_update_when_state_changes():
    """单轮多订阅状态变化时只批量写一次 subscribes。"""
    coord, data, _notify, _oper, _clock, update_calls = _coordinator([
        _sub(sid=1, missing=5),
        _sub(sid=2, missing=7),
    ])

    coord.run()

    assert update_calls == [STATE_KEY]
    assert set(data[STATE_KEY]) == {"1", "2"}


def test_progress_state_uses_subscribe_task_record_fields():
    """无进展诊断状态写入订阅任务记录，并只暴露本模块字段。"""
    assert diagnostic_module.SUBSCRIBES_TASK_KEY == STATE_KEY
    assert {
        diagnostic_module.STALLED_ROUNDS_FIELD,
        diagnostic_module.LAST_MISSING_FIELD,
        diagnostic_module.NOTIFIED_AT_FIELD,
    } == PROGRESS_FIELDS


def test_diagnostic_does_not_use_getattr_for_stable_subscribe_fields():
    """Subscribe 固定字段必须直接属性访问，避免掩盖契约漂移。"""
    impl_source = Path(diagnostic_module.__file__).read_text(encoding="utf-8")

    assert "getattr(subscribe" not in impl_source
