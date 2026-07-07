"""搜索诊断协调器单测。

覆盖：首次登记不计轮、缺集未减少累计、达标发通知、冷却抑制、过冷却重发、
缺集减少重置、补齐后 prune、开关/阈值关闭时不动作。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.noresult import NoResultDiagnosticCoordinator
from subscribeassistantenhanced.noresult.diagnostic import NO_RESULT_TASK_KEY


def _sub(sid=1, lack=5, type="电视剧"):
    """构造仍缺集的启用订阅替身。"""
    return SimpleNamespace(
        id=sid,
        name=f"测试{sid}",
        tmdbid=100 + sid,
        season=1,
        type=type,
        state="R",
        total_episode=12,
        lack_episode=lack,
    )


def _cfg(**kwargs):
    """构造搜索诊断所需配置替身。"""
    defaults = dict(
        no_result_diagnostic_enabled=True,
        no_result_diagnostic_rounds=3,
        no_result_diagnostic_cooldown_hours=24,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _store(initial=None):
    """构造 TaskDataManager 兼容的内存读写闭包。"""
    data = {NO_RESULT_TASK_KEY: initial or {}}

    def read(key):
        return dict(data.get(key, {}))

    def update(key, updater):
        cur = data.get(key, {})
        data[key] = updater(cur)
        return data[key]

    return data, read, update


def _coordinator(subs, cfg=None, initial=None, now=1000.0):
    """组装被测协调器与内存存储、订阅查询、通知替身。"""
    data, read, update = _store(initial)
    oper = MagicMock()
    oper.list.return_value = subs
    notify = MagicMock()
    clock = {"t": now}
    coord = NoResultDiagnosticCoordinator(
        cfg or _cfg(),
        read,
        update,
        subscribe_oper=oper,
        notify_fn=notify,
        now_fn=lambda: clock["t"],
    )
    return coord, data, notify, clock


def _rounds(data, sid=1):
    return data[NO_RESULT_TASK_KEY].get(str(sid), {}).get("miss_rounds")


def test_first_round_only_records_baseline():
    """首次观察只登记基线缺集数，不计轮、不通知。"""
    coord, data, notify, _ = _coordinator([_sub(lack=5)])
    coord.run()
    assert _rounds(data) == 0
    assert data[NO_RESULT_TASK_KEY]["1"]["last_lack"] == 5
    notify.assert_not_called()


def test_unchanged_lack_accumulates_rounds():
    """缺集连续未减少时逐轮累计 miss_rounds。"""
    coord, data, notify, _ = _coordinator([_sub(lack=5)])
    coord.run()  # 基线
    coord.run()
    assert _rounds(data) == 1
    coord.run()
    assert _rounds(data) == 2
    notify.assert_not_called()


def test_reaching_threshold_sends_notification():
    """达到轮数阈值后发出一次诊断通知，且标记 diagnostic=True。"""
    coord, data, notify, _ = _coordinator([_sub(lack=5)], cfg=_cfg(no_result_diagnostic_rounds=3))
    for _ in range(4):  # 基线 + 3 轮未减少
        coord.run()
    assert notify.call_count == 1
    _, kwargs = notify.call_args
    assert kwargs.get("diagnostic") is True
    assert kwargs.get("action")


def test_cooldown_suppresses_repeat_notification():
    """冷却期内不重复通知。"""
    coord, data, notify, clock = _coordinator([_sub(lack=5)], cfg=_cfg(no_result_diagnostic_rounds=3))
    for _ in range(4):
        coord.run()
    assert notify.call_count == 1
    coord.run()  # 仍在 24h 冷却内
    assert notify.call_count == 1


def test_notification_resent_after_cooldown():
    """超过冷却时长后允许再次通知。"""
    coord, data, notify, clock = _coordinator([_sub(lack=5)], cfg=_cfg(no_result_diagnostic_rounds=3))
    for _ in range(4):
        coord.run()
    assert notify.call_count == 1
    clock["t"] += 25 * 3600
    coord.run()
    assert notify.call_count == 2


def test_lack_decrease_resets_rounds():
    """缺集减少（搜到并下载了新集）时重置轮数。"""
    sub = _sub(lack=5)
    coord, data, notify, _ = _coordinator([sub])
    coord.run()
    coord.run()
    assert _rounds(data) == 1
    sub.lack_episode = 3
    coord.run()
    assert _rounds(data) == 0


def test_completed_subscribe_is_pruned():
    """缺集补齐后订阅从跟踪记录中移除。"""
    sub = _sub(lack=5)
    coord, data, notify, _ = _coordinator([sub])
    coord.run()
    assert "1" in data[NO_RESULT_TASK_KEY]
    sub.lack_episode = 0
    coord.run()
    assert "1" not in data[NO_RESULT_TASK_KEY]


def test_disabled_switch_does_nothing():
    """总开关关闭时不观察、不写记录、不通知。"""
    coord, data, notify, _ = _coordinator([_sub(lack=5)], cfg=_cfg(no_result_diagnostic_enabled=False))
    for _ in range(5):
        coord.run()
    assert data[NO_RESULT_TASK_KEY] == {}
    notify.assert_not_called()


def test_zero_rounds_threshold_disables_diagnostic():
    """轮数阈值为 0 时视为关闭，不处理。"""
    coord, data, notify, _ = _coordinator([_sub(lack=5)], cfg=_cfg(no_result_diagnostic_rounds=0))
    for _ in range(5):
        coord.run()
    assert data[NO_RESULT_TASK_KEY] == {}
    notify.assert_not_called()


def test_no_candidate_truncation_covers_all_subscribes():
    """不做固定候选截断：订阅较多时尾部订阅同样累计，不漏诊断。"""
    subs = [_sub(sid=i, lack=5) for i in range(80)]
    coord, data, notify, _ = _coordinator(subs, cfg=_cfg(no_result_diagnostic_rounds=3))
    for _ in range(4):  # 基线 + 3 轮
        coord.run()
    # 80 个订阅合并为一条汇总通知（不再逐条），且尾部订阅状态被正确累计
    # （旧版 50 截断会漏后 30 个）
    assert notify.call_count == 1
    assert data[NO_RESULT_TASK_KEY]["79"]["miss_rounds"] == 3


def test_multiple_due_subscribes_merge_into_one_summary():
    """多个订阅同轮达标时合并为单条汇总通知，避免通知风暴。"""
    subs = [_sub(sid=i, lack=i + 1) for i in range(5)]
    coord, data, notify, _ = _coordinator(subs, cfg=_cfg(no_result_diagnostic_rounds=3))
    for _ in range(4):
        coord.run()
    assert notify.call_count == 1
    args, kwargs = notify.call_args
    # 标题体现订阅数量，正文包含逐条明细
    assert "5 个订阅" in args[0]
    assert kwargs["text"].count("·") == 5


def test_notification_wording_is_conservative():
    """诊断文案保守：不对具体原因下定论，标注仅供参考并回到原生订阅链路。"""
    coord, data, notify, _ = _coordinator([_sub(lack=5)], cfg=_cfg(no_result_diagnostic_rounds=3))
    for _ in range(4):
        coord.run()
    assert notify.call_count == 1
    _, kwargs = notify.call_args
    assert "仅供参考" in kwargs["action"]
    assert "可能原因" in kwargs["action"]
    assert kwargs.get("follow_up")
    assert kwargs.get("diagnostic") is True
