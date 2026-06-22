"""pending/judge.py 待定判定单测。"""
from types import SimpleNamespace
from datetime import date, timedelta
from unittest.mock import MagicMock

from subscribeassistantenhanced.pending.judge import PendingJudge
from subscribeassistantenhanced.pending.state import PendingStateCoordinator
from subscribeassistantenhanced.engine.types import CompletionSignal
from subscribeassistantenhanced.shared.config import PluginConfig


def _ep(num, air_date="2026-01-01"):
    return SimpleNamespace(episode_number=num, air_date=air_date, episode_type="standard")


def _sub(sid=1, season=1, state="R", episode_group=None, total_episode=12,
         media_type="电视剧"):
    return SimpleNamespace(
        id=sid,
        name="测试剧",
        type=media_type,
        tmdbid=100,
        season=season,
        state=state,
        episode_group=episode_group,
        total_episode=total_episode,
        lack_episode=0,
    )


def _mi(**kwargs):
    defaults = dict(
        season_info=[],
        first_air_date=None,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _judge(config=None, evaluate_result=None, store=None, notify=None):
    store = store if store is not None else {}
    cfg = config or PluginConfig({})
    j = PendingJudge.__new__(PendingJudge)
    j._config = cfg
    j._evaluate = MagicMock(return_value=evaluate_result or CompletionSignal())
    j._subscribe_oper = MagicMock()
    j._timeout = MagicMock()
    j._timeout.check_release.return_value = False
    j._read = lambda key: store.get(key, {})
    j._notify = notify

    def update_fn(key, updater):
        data = store.get(key, {})
        result = updater(data)
        store[key] = result
        return result

    j._update = update_fn
    j._state = PendingStateCoordinator(j._read, j._update, subscribe_oper=j._subscribe_oper)
    j._store = store
    return j


class TestShouldEnterPending:

    def test_movie_skips_tv_episode_pending_rules(self):
        """电影没有剧集列表时不得命中电视剧的集数不足待定规则。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 3}))
        should, reason = j.should_enter_pending(
            _sub(season=0, media_type="电影"),
            _mi(),
            [],
        )
        assert should is False
        assert reason == ""

    def test_episode_count_below_threshold(self):
        """集数不足 → 待定。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 3}))
        mi = _mi()
        eps = [_ep(1), _ep(2)]
        should, reason = j.should_enter_pending(_sub(), mi, eps)
        assert should is True
        assert "集数不足" in reason

    def test_episode_count_above_threshold(self):
        """集数充足 → 不待定。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 2}))
        mi = _mi()
        eps = [_ep(1), _ep(2), _ep(3)]
        should, _ = j.should_enter_pending(_sub(), mi, eps)
        assert should is False

    def test_pending_days_reason_uses_air_date_distance(self):
        """上映待定原因应展示开播日期和相对当前的真实天数。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_days": 7}))
        mi = _mi(season_info=[{"season_number": 1, "air_date": (date.today() + timedelta(days=3)).isoformat()}])

        should, reason = j.should_enter_pending(_sub(), mi, [_ep(1)])

        assert should is True
        assert "开播日期：" in reason
        assert "距今 3 天" in reason
        assert "开播待定窗口" in reason

    def test_f_unstable_triggers_pending(self):
        """F 不稳定且接近完结 → 待定。"""
        j = _judge(config=PluginConfig({"pending_use_volatility": True, "auto_tv_pending_episodes": 0}))
        mi = _mi()
        sig = CompletionSignal(stable=False)
        should, reason = j.should_enter_pending(_sub(), mi, [_ep(1), _ep(2), _ep(3)], signal=sig)
        assert should is True
        assert reason == "目标总集数近期变化"

    def test_f_unstable_pending_reason_carries_total_change_detail(self):
        """总集数波动触发待定时，原因应携带旧集数到新集数的变化明细。"""
        j = _judge(config=PluginConfig({"pending_use_volatility": True, "auto_tv_pending_episodes": 0}))
        sig = CompletionSignal(stable=False, volatility_detail="10 -> 15")

        should, reason = j.should_enter_pending(
            _sub(),
            _mi(),
            [_ep(1), _ep(2), _ep(3)],
            signal=sig,
        )

        assert should is True
        assert reason == "目标总集数近期变化（10 -> 15）"

    def test_mid_airing_total_shrink_does_not_enter_pending_from_volatility(self):
        """播出中段 total 校准只记录风险，不触发 pending_judge 待定。"""
        j = _judge(config=PluginConfig({"pending_use_volatility": True, "auto_tv_pending_episodes": 0}))
        sig = CompletionSignal(stable=False, scope_total=33)
        aired_date = (date.today() - timedelta(days=16)).isoformat()
        future_date = (date.today() + timedelta(days=4)).isoformat()
        episodes = [_ep(i, air_date=aired_date) for i in range(1, 18)]
        episodes.extend(_ep(i, air_date=future_date) for i in range(18, 34))

        should, reason = j.should_enter_pending(
            _sub(total_episode=33),
            _mi(),
            episodes,
            signal=sig,
        )

        assert should is False
        assert reason == ""

    def test_near_completion_volatility_still_enters_pending(self):
        """接近完结时 total 近期变化仍进入 pending_judge 待定。"""
        j = _judge(config=PluginConfig({"pending_use_volatility": True, "auto_tv_pending_episodes": 0}))
        sig = CompletionSignal(stable=False, scope_total=33)
        episodes = [_ep(i, air_date="2026-06-01") for i in range(1, 33)]
        episodes.append(_ep(33, air_date=date.today().isoformat()))

        should, reason = j.should_enter_pending(
            _sub(total_episode=33),
            _mi(),
            episodes,
            signal=sig,
        )

        assert should is True
        assert reason == "目标总集数近期变化"

    def test_no_air_date_triggers_pending(self):
        """无 air_date → 待定。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 0}))
        mi = _mi()
        eps = [SimpleNamespace(episode_number=1, air_date=None)]
        should, reason = j.should_enter_pending(_sub(), mi, eps)
        assert should is True
        assert "air_date" in reason


class TestCheckExit:

    def test_pending_judge_exits_when_conditions_clear(self):
        """pending_judge P：条件不再满足 → 退出。"""
        store = {"subscribes": {"1": {"state": "P", "source": "pending_judge"}}}
        sig = CompletionSignal(completed=False, stable=True)
        j = _judge(evaluate_result=sig, store=store,
                   config=PluginConfig({"auto_tv_pending_episodes": 0}))

        def tmdb_fn(tmdbid, season, episode_group=None): return [_ep(i) for i in range(1, 13)]
        mi = _mi()
        result = j.check_exit(_sub(state="P"), mi, tmdb_fn)
        assert result is True
        assert j._subscribe_oper.update.called

    def test_pending_judge_exit_uses_episode_group_scope(self):
        """pending_judge P 退出复查必须沿用订阅剧集组，不回落到主季范围。"""
        store = {"subscribes": {"1": {"state": "P", "source": "pending_judge"}}}
        sig = CompletionSignal(completed=False, stable=True)
        j = _judge(evaluate_result=sig, store=store,
                   config=PluginConfig({"auto_tv_pending_episodes": 0}))
        tmdb_fn = MagicMock(return_value=[_ep(i) for i in range(1, 13)])

        result = j.check_exit(_sub(state="P", episode_group="eg-1"), _mi(), tmdb_fn)

        assert result is True
        tmdb_fn.assert_called_once_with(100, 1, episode_group="eg-1")

    def test_pending_judge_exits_when_unstable_but_not_near_completion(self):
        """pending_judge P 退出时，播出中段 total 波动不应独占整个观察窗口。"""
        store = {"subscribes": {"1": {"state": "P", "source": "pending_judge"}}}
        sig = CompletionSignal(completed=False, stable=False, scope_total=33)
        j = _judge(
            evaluate_result=sig,
            store=store,
            config=PluginConfig({"pending_use_volatility": True, "auto_tv_pending_episodes": 0}),
        )
        aired_date = (date.today() - timedelta(days=16)).isoformat()
        future_date = (date.today() + timedelta(days=4)).isoformat()
        episodes = [_ep(i, air_date=aired_date) for i in range(1, 18)]
        episodes.extend(_ep(i, air_date=future_date) for i in range(18, 34))
        tmdb_fn = MagicMock(return_value=episodes)

        result = j.check_exit(_sub(state="P", total_episode=33), _mi(), tmdb_fn)

        assert result is True
        tmdb_fn.assert_called_once_with(100, 1, episode_group=None)

    def test_guard_veto_stays_until_signal_confirms(self):
        """guard_veto P：信号未确认 → 保持 P。"""
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        sig = CompletionSignal(completed=False, stable=True)
        j = _judge(evaluate_result=sig, store=store)
        mi = _mi()
        result = j.check_exit(_sub(state="P"), mi, lambda *a: [])
        assert result is False

    def test_guard_veto_exits_when_completed(self):
        """guard_veto P：信号确认完结 → 退出。"""
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        sig = CompletionSignal(completed=True, confidence="high")
        j = _judge(evaluate_result=sig, store=store)
        mi = _mi()
        result = j.check_exit(_sub(state="P"), mi, lambda *a: [])
        assert result is True

    def test_guard_veto_uses_timeout_release_for_low_confidence_completion(self):
        """guard_veto 低置信完成需等待 timeout_manager 释放。"""
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        sig = CompletionSignal(completed=True, confidence="low", stable=True, signals=["I:all_aired"])
        j = _judge(evaluate_result=sig, store=store)
        j._timeout.check_release.return_value = True

        subscribe = _sub(state="P", total_episode=2)
        result = j.check_exit(subscribe, _mi(), lambda *a: [])

        assert result is True
        j._timeout.check_release.assert_called_once_with(subscribe, sig, total_episode=2)

    def test_guard_veto_low_confidence_stays_before_timeout_release(self):
        """guard_veto 低置信完成未超观察期时继续保持 P。"""
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        sig = CompletionSignal(completed=True, confidence="low", stable=True, signals=["I:all_aired"])
        j = _judge(evaluate_result=sig, store=store)
        j._timeout.check_release.return_value = False

        subscribe = _sub(state="P", total_episode=2)
        result = j.check_exit(subscribe, _mi(), lambda *a: [])

        assert result is False
        j._timeout.check_release.assert_called_once_with(subscribe, sig, total_episode=2)

    def test_guard_veto_uses_signal_scope_total_when_available(self):
        """guard_veto 释放判断优先使用本轮 TMDB scope 总数。"""
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        sig = CompletionSignal(completed=True, confidence="low", stable=True,
                               signals=["I:all_aired"], scope_total=3)
        j = _judge(evaluate_result=sig, store=store)
        j._timeout.check_release.return_value = True

        subscribe = _sub(state="P", total_episode=2)
        result = j.check_exit(subscribe, _mi(), lambda *a: [])

        assert result is True
        j._timeout.check_release.assert_called_once_with(subscribe, sig, total_episode=3)

    def test_pending_judge_exits_on_completion(self):
        """pending_judge P：信号确认完结 → 退出。"""
        store = {"subscribes": {"1": {"state": "P", "source": "pending_judge"}}}
        sig = CompletionSignal(completed=True, confidence="medium")
        j = _judge(evaluate_result=sig, store=store)
        mi = _mi()
        result = j.check_exit(_sub(state="P"), mi, lambda *a: [])
        assert result is True

    def test_not_pending_returns_false(self):
        """非 P 状态 → 返回 False。"""
        store = {"subscribes": {"1": {"state": "R"}}}
        j = _judge(store=store)
        mi = _mi()
        result = j.check_exit(_sub(), mi, lambda *a: [])
        assert result is False


class TestMarkPending:

    def test_mark_pending_writes_state_and_source(self):
        store = {}
        j = _judge(store=store)
        j.mark_pending(_sub(), source="guard_veto", reason="test")
        assert j._subscribe_oper.update.called
        task = store.get("subscribes", {}).get("1", {})
        assert task["state"] == "P"
        assert task["source"] == "guard_veto"

    def test_mark_pending_sends_status_notification(self):
        """进入待定应发送状态通知。"""
        notify = MagicMock()
        j = _judge(notify=notify)

        j.mark_pending(_sub(), source="pending_judge", reason="集数不足")

        notify.assert_called_once()
        assert "满足上映待定，已标记待定" in notify.call_args.args[1]

    def test_mark_pending_notifies_only_on_state_transition(self):
        """重复命中同一待定来源时，只刷新任务归属，不重复发送进入待定通知。"""
        notify = MagicMock()
        store = {}
        j = _judge(store=store, notify=notify)

        j.mark_pending(_sub(state="R"), source="pending_judge", reason="集数不足")
        j.mark_pending(_sub(state="P"), source="pending_judge", reason="上映窗口期内")

        notify.assert_called_once()
        task = store["subscribes"]["1"]
        assert task["state"] == "P"
        assert task["source"] == "pending_judge"
        assert task["pending_sources"]["pending_judge"]["reason"] == "上映窗口期内"


class TestExitPending:

    def test_exit_clears_j_block(self):
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        j = _judge(store=store)
        j._exit_pending(_sub(), "测试退出")
        j._timeout.clear_block.assert_called_once_with(1)
        assert store["subscribes"]["1"]["state"] == "R"

    def test_exit_sends_status_notification(self):
        """退出待定应发送状态通知。"""
        notify = MagicMock()
        store = {"subscribes": {"1": {"state": "P", "source": "pending_judge"}}}
        j = _judge(store=store, notify=notify)

        j._exit_pending(_sub(state="P"), "待定条件不再满足")

        notify.assert_called_once()
        assert "不再满足上映待定，已标记订阅中" in notify.call_args.args[1]

    def test_exit_keeps_p_when_download_pending_active(self):
        """业务待定退出时若下载待定仍活跃，则订阅保持 P。"""
        notify = MagicMock()
        store = {"subscribes": {"1": {
            "state": "P",
            "source": "pending_judge",
            "pending_sources": {
                "pending_judge": {"reason": "集数不足"},
                "download_pending": {"reason": "下载中"},
            },
        }}}
        j = _judge(store=store, notify=notify)

        j._exit_pending(_sub(state="P"), "待定条件不再满足")

        assert store["subscribes"]["1"]["state"] == "P"
        assert store["subscribes"]["1"]["source"] == "download_pending"
        assert "pending_judge" not in store["subscribes"]["1"]["pending_sources"]
        assert not any(
            call_args.args[1]["state"] == "R"
            for call_args in j._subscribe_oper.update.call_args_list
        )
        notify.assert_not_called()
