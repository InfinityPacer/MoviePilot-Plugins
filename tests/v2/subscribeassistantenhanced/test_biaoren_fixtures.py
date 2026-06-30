"""镖人真实脱敏样本集成测试，覆盖 S01/S02 低置信完结与历史状态链路。"""
import json
import time
from datetime import date
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.engine.evaluate import evaluate
from subscribeassistantenhanced.engine.signals import last_aired_episode
from subscribeassistantenhanced.engine.volatility import VolatilityTracker
from subscribeassistantenhanced.guard import CompletionGuard
from subscribeassistantenhanced.pause.airing import AiringPauseChecker
from subscribeassistantenhanced.postcheck.timeout import PendingTimeoutManager
from subscribeassistantenhanced.shared.config import PluginConfig
from subscribeassistantenhanced.shared.task import TaskDataManager


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def _load_fixture(name: str) -> dict:
    """读取脱敏 JSON fixture，避免测试依赖线上 TMDB 或本机数据库。"""
    return json.loads((FIXTURE_DIR / name).read_text(encoding="utf-8"))


def _obj(data):
    """把 TMDB fixture 转成属性对象，匹配插件运行时读取方式。"""
    if isinstance(data, dict):
        return SimpleNamespace(**{key: _obj(value) for key, value in data.items()})
    if isinstance(data, list):
        return [_obj(item) for item in data]
    return data


def _store(initial=None):
    """构造内存 TaskDataManager，用于跑真实 PendingTimeoutManager 状态转移。"""
    data = initial or {}
    return TaskDataManager(
        get_data_fn=lambda key: data.get(key, {}),
        save_data_fn=lambda key, value: data.__setitem__(key, value),
    ), data


def _tmdb_episodes(tmdb_fixture: dict):
    """按季返回 fixture 中的 TMDB 集信息，模拟线上 season API。"""
    def _episodes(_tmdbid, season, **_kwargs):
        season_data = tmdb_fixture["seasons"].get(str(season), {})
        return _obj(season_data.get("episodes", []))
    return _episodes


def _mediainfo(tmdb_fixture: dict):
    """构造镖人 MediaInfo，保留 season_info 为 dict 以覆盖 shared.media 分支。"""
    tv = tmdb_fixture["tv"]
    return SimpleNamespace(
        tmdb_id=tv["id"],
        type=SimpleNamespace(value="电视剧"),
        first_air_date="2023-06-01",
        release_date=None,
        season_info=tv["seasons"],
        tmdb_info=_obj({
            "status": tv["status"],
            "next_episode_to_air": tv["next_episode_to_air"],
            "last_episode_to_air": tv["last_episode_to_air"],
            "seasons": tv["seasons"],
            "episode_groups": tv["episode_groups"],
        }),
    )


def _subscribe(runtime_fixture: dict, key: str):
    """从 DB 脱敏订阅 fixture 还原订阅对象。"""
    data = dict(runtime_fixture["subscriptions"][key])
    data.setdefault("type", "电视剧")
    data.setdefault("episode_group", None)
    data.setdefault("best_version_full", 0)
    data.setdefault("episode_priority", {})
    data.setdefault("save_path", None)
    data.setdefault("sites", None)
    data.setdefault("filter", None)
    data.setdefault("filter_groups", [])
    data.setdefault("year", None)
    data.setdefault("username", "")
    data.setdefault("date", None)
    return SimpleNamespace(**data)


def _evaluate_fixture(subscribe, mediainfo, episodes_fn, as_of):
    """按默认配置和稳定 tracker 执行完结信号引擎。"""
    manager, _ = _store()
    tracker = VolatilityTracker(manager, window_days=7)
    return evaluate(subscribe, mediainfo, episodes_fn, tracker, PluginConfig({}), as_of=as_of)


def test_biaoren_s01_next_season_completes_and_current_pause_logic_does_not_pause():
    """S01 无 finale 但已有 S02，当前链路应完成且不再因无下一集走播出暂停。"""
    tmdb = _load_fixture("biaoren_tmdb.json")
    runtime = _load_fixture("biaoren_runtime.json")
    mediainfo = _mediainfo(tmdb)
    subscribe = _subscribe(runtime, "s01")
    episodes_fn = _tmdb_episodes(tmdb)

    signal = _evaluate_fixture(subscribe, mediainfo, episodes_fn, as_of=date(2026, 6, 12))

    assert signal.completed is True
    assert signal.confidence == "medium"
    assert signal.signals == ["I:next_season"]
    assert runtime["plugin_state"]["subscribes"]["41"]["pause_reason"] == "airing_gap"

    checker = AiringPauseChecker(
        pause_days=30,
        evaluate_fn=lambda _subscribe, _mediainfo: signal,
    )
    latest = last_aired_episode(episodes_fn(325228, 1), as_of=date(2026, 6, 12))

    assert checker.check(
        subscribe,
        mediainfo,
        next_episode=None,
        latest_episode=latest,
        as_of=date(2026, 6, 12),
    ) is None


def test_biaoren_s02_low_confidence_enters_guard_observation_before_snapshot():
    """S02 当前 TMDB 只给 2 集且无 next_episode，低置信 I 完结必须先进入观察。"""
    tmdb = _load_fixture("biaoren_tmdb.json")
    runtime = _load_fixture("biaoren_runtime.json")
    mediainfo = _mediainfo(tmdb)
    subscribe = _subscribe(runtime, "s02_best_version")
    subscribe.best_version = 0
    episodes_fn = _tmdb_episodes(tmdb)
    signal = _evaluate_fixture(subscribe, mediainfo, episodes_fn, as_of=date(2026, 6, 12))
    manager, store = _store()

    guard = CompletionGuard(
        evaluate_fn=MagicMock(return_value=signal),
        has_active_downloads_fn=MagicMock(return_value=False),
        mark_pending_fn=MagicMock(),
        timeout_manager=PendingTimeoutManager(manager.read, manager.update, timeout_days=7),
        mode="balanced",
        pending_download_enabled=True,
    )
    event = SimpleNamespace(event_data=SimpleNamespace(
        subscribe=subscribe,
        mediainfo=mediainfo,
        cancel=False,
        reason="",
        source="",
    ))

    guard.handle(event)

    assert signal.completed is True
    assert signal.confidence == "low"
    assert signal.signals == ["I:all_aired"]
    assert event.event_data.cancel is True
    assert store["blocks"]["45"]["signals"] == ["I:all_aired"]
    assert store["blocks"]["45"]["total_episode"] == 2
    guard.mark_pending_fn.assert_called_once()


def test_biaoren_s02_observation_timeout_records_release_and_next_guard_snapshots():
    """低置信观察到期后只放行匹配同一信号的下一次完成检查，并登记 H 快照。"""
    tmdb = _load_fixture("biaoren_tmdb.json")
    runtime = _load_fixture("biaoren_runtime.json")
    mediainfo = _mediainfo(tmdb)
    subscribe = _subscribe(runtime, "s02_best_version")
    subscribe.best_version = 0
    episodes_fn = _tmdb_episodes(tmdb)
    signal = _evaluate_fixture(subscribe, mediainfo, episodes_fn, as_of=date(2026, 6, 12))
    manager, store = _store()
    timeout = PendingTimeoutManager(manager.read, manager.update, timeout_days=7)
    timeout.record_block(subscribe, signal=signal, total_episode=2)
    store["blocks"]["45"]["blocked_at"] = time.time() - 8 * 86400

    assert timeout.check_release(subscribe, signal, total_episode=2) is True
    assert store["releases"]["45"]["total_episode"] == 2

    guard = CompletionGuard(
        evaluate_fn=MagicMock(return_value=signal),
        has_active_downloads_fn=MagicMock(return_value=False),
        mark_pending_fn=MagicMock(),
        timeout_manager=timeout,
        mode="balanced",
        pending_download_enabled=True,
    )
    event = SimpleNamespace(event_data=SimpleNamespace(
        subscribe=subscribe,
        mediainfo=mediainfo,
        cancel=False,
        reason="",
        source="",
    ))

    guard.handle(event)

    assert event.event_data.cancel is False
    assert "45" not in store.get("releases", {})


def test_biaoren_s02_total_growth_releases_observation_without_allowing_completion():
    """观察期内 TMDB 增集代表当前目标范围变化：释放 guard_veto，但不授予完成放行 token。"""
    manager, store = _store({"blocks": {"45": {
        "blocked_at": time.time() - 8 * 86400,
        "reason": "guard_veto",
        "signals": ["I:all_aired"],
        "confidence": "low",
        "total_episode": 2,
    }}})
    timeout = PendingTimeoutManager(manager.read, manager.update, timeout_days=7)
    signal = SimpleNamespace(
        completed=False,
        confidence="none",
        stable=True,
        cadence_expired=False,
        signals=["none"],
        scope_total=3,
    )

    assert timeout.check_release(45, signal, total_episode=2) is True
    assert store.get("releases", {}) == {}


def test_biaoren_runtime_fixture_captures_historical_db_completion_chain():
    """DB 脱敏 fixture 固化 S01 暂停事故与 S02 完成洗版链路。"""
    runtime = _load_fixture("biaoren_runtime.json")

    assert runtime["subscriptions"]["s01"]["state"] == "S"
    assert runtime["plugin_state"]["subscribes"]["41"]["pause_reason"] == "airing_gap"
    assert runtime["subscriptions"]["s02_best_version"]["state"] == "R"
    assert runtime["subscriptions"]["s02_best_version"]["current_priority"] == 98
    assert runtime["plugin_state"]["snapshots"][0]["total_at_completion"] == 2

    transferred = {(item["seasons"], item["episodes"]) for item in runtime["transferhistory"]}
    downloaded = {(item["seasons"], item["episodes"]) for item in runtime["downloadhistory"]}

    assert ("S02", "E01") in transferred
    assert ("S02", "E02") in transferred
    assert ("S02", "E01") in downloaded
    assert ("S02", "E02") in downloaded
