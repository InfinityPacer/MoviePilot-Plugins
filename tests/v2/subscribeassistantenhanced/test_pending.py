"""pending/judge.py 待定判定单测。"""
from types import SimpleNamespace
from datetime import date, timedelta
from unittest.mock import MagicMock

from subscribeassistantenhanced.pending.judge import PendingJudge
from subscribeassistantenhanced.pending.state import PendingStateCoordinator
from subscribeassistantenhanced.engine.types import (
    CompletionEvidence,
    CompletionObservationDecision,
    CompletionSignal,
)
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


def _judge(config=None, evaluate_result=None, evidence=None, store=None,
           notify=None, resolve_missing_fn=None):
    store = store if store is not None else {}
    cfg = config or PluginConfig({})
    signal = evaluate_result or CompletionSignal()
    evidence = evidence or CompletionEvidence(primary_signal=signal)
    j = PendingJudge.__new__(PendingJudge)
    j._config = cfg
    j._evidence_pipeline = MagicMock()
    j._evidence_pipeline.evaluate.return_value = evidence
    j._resolve_missing_fn = resolve_missing_fn
    j._subscribe_oper = MagicMock()
    j._timeout = MagicMock()
    j._timeout.check_observation.return_value = CompletionObservationDecision.hold("继续观察")
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
        """电影没有剧集列表时不得命中剧集的集数不足待定规则。"""
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
        assert reason == "集数不足（2 ≤ 3）"

    def test_season_info_episode_count_prevents_empty_episode_list_from_zero_pending(self):
        """优先使用 season_info 的 episode_count，不把分集详情空结果当 0 集。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 1}))
        mi = _mi(season_info=[{"season_number": 1, "episode_count": 190}])

        should, reason = j.should_enter_pending(_sub(total_episode=190), mi, [])

        assert should is False
        assert reason == ""

    def test_season_info_episode_count_can_enter_pending_when_explicitly_low(self):
        """season_info 明确给出低集数时，待定原因仍是集数不足。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 1}))
        mi = _mi(season_info=[{"season_number": 1, "episode_count": 0}])

        should, reason = j.should_enter_pending(_sub(total_episode=190), mi, [])

        assert should is True
        assert reason == "集数不足（0 ≤ 1）"

    def test_season_info_episodes_length_is_used_when_episode_count_missing(self):
        """season_info 没有 episode_count 时，使用同季 episodes 长度兜底。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 3}))
        mi = _mi(season_info=[{"season_number": 1, "episodes": [{"episode_number": 1}, {"episode_number": 2}]}])

        should, reason = j.should_enter_pending(_sub(), mi, [])

        assert should is True
        assert reason == "集数不足（2 ≤ 3）"

    def test_invalid_season_info_episode_count_falls_back_to_season_episodes(self):
        """season_info 的 episode_count 无效时，继续使用同季 episodes 长度兜底。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 3}))
        mi = _mi(season_info=[{
            "season_number": 1,
            "episode_count": "",
            "episodes": [{"episode_number": 1}, {"episode_number": 2}],
        }])

        should, reason = j.should_enter_pending(_sub(), mi, [])

        assert should is True
        assert reason == "集数不足（2 ≤ 3）"

    def test_unknown_episode_count_does_not_report_zero_episode_pending(self):
        """season_info 和分集表都拿不到时，不伪造成 0 集。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 1}))

        should, reason = j.should_enter_pending(_sub(total_episode=190), _mi(), [])

        assert should is False
        assert reason == ""

    def test_low_confidence_completion_does_not_skip_episode_pending(self):
        """低置信季级完结信号不能绕过剧集待定。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 1}))
        sig = CompletionSignal(completed=True, confidence="low", signals=["I:all_aired"])

        should, reason = j.should_enter_pending(_sub(), _mi(), [_ep(1)], signal=sig)

        assert should is True
        assert reason == "集数不足（1 ≤ 1）"

    def test_medium_confidence_completion_does_not_skip_episode_pending(self):
        """中置信完结信号不能绕过剧集待定。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 1}))
        sig = CompletionSignal(completed=True, confidence="medium", signals=["I:next_season"])

        should, reason = j.should_enter_pending(_sub(), _mi(), [_ep(1)], signal=sig)

        assert should is True
        assert reason == "集数不足（1 ≤ 1）"

    def test_high_confidence_completion_skips_episode_pending(self):
        """高置信完结事实应阻止剧集待定进入。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 1}))
        sig = CompletionSignal(completed=True, confidence="high", signals=["E:ended"])

        should, reason = j.should_enter_pending(_sub(), _mi(), [_ep(1)], signal=sig)

        assert should is False
        assert reason == ""

    def test_high_completion_from_pipeline_skips_episode_pending_when_signal_missing(self):
        """调用方未传 signal 时，命中待定前从流水线读取高置信完成事实。"""
        sig = CompletionSignal(completed=True, confidence="high", signals=["E:ended"])
        j = _judge(
            evaluate_result=sig,
            config=PluginConfig({"auto_tv_pending_episodes": 1}),
        )

        should, reason = j.should_enter_pending(_sub(), _mi(), [_ep(1)])

        assert should is False
        assert reason == ""
        j._evidence_pipeline.evaluate.assert_called_once()

    def test_l_signal_does_not_skip_episode_pending(self):
        """L 目标满足信号不参与 pending_judge 进入判定。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 1}))
        sig = CompletionSignal(completed=True, confidence="low", signals=["L:target_satisfied"])

        should, reason = j.should_enter_pending(_sub(), _mi(), [_ep(1)], signal=sig)

        assert should is True
        assert reason == "集数不足（1 ≤ 1）"

    def test_episode_count_above_threshold(self):
        """集数充足 → 不待定。"""
        j = _judge(config=PluginConfig({"auto_tv_pending_episodes": 2}))
        mi = _mi()
        eps = [_ep(1), _ep(2), _ep(3)]
        should, _ = j.should_enter_pending(_sub(), mi, eps)
        assert should is False

    def test_no_pending_risk_does_not_evaluate_completion_pipeline(self):
        """没有待定命中风险时不额外收集完成证据。"""
        j = _judge(config=PluginConfig({
            "auto_tv_pending_days": 0,
            "auto_tv_pending_episodes": 0,
            "pending_use_volatility": False,
        }))

        should, reason = j.should_enter_pending(_sub(), _mi(), [_ep(1), _ep(2)])

        assert should is False
        assert reason == ""
        j._evidence_pipeline.evaluate.assert_not_called()

    def test_pending_days_reason_uses_air_date_distance(self):
        """剧集待定原因应展示开播日期和相对当前的真实天数。"""
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

    def test_should_enter_pending_evaluates_primary_signal_when_signal_missing(self):
        """调用方未传 signal 时，待定判定从完成证据流水线取 primary_signal。"""
        sig = CompletionSignal(
            completed=False,
            stable=False,
            signals=["F:unstable"],
            scope_total=12,
            volatility_detail="10 -> 12",
        )
        evidence = CompletionEvidence(
            primary_signal=sig,
            unstable_signal=sig,
            scope_total=12,
            observation_kind="unstable",
        )
        j = _judge(
            evidence=evidence,
            config=PluginConfig({"pending_use_volatility": True, "auto_tv_pending_episodes": 0}),
        )

        should, reason = j.should_enter_pending(
            _sub(total_episode=12),
            _mi(),
            [_ep(i) for i in range(1, 12)],
        )

        assert should is True
        assert "目标总集数近期变化" in reason
        j._evidence_pipeline.evaluate.assert_called_once()

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
        """guard_veto P：完成观察仍需保持 → 保持 P。"""
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        sig = CompletionSignal(completed=False, stable=True)
        evidence = CompletionEvidence(primary_signal=sig)
        j = _judge(evidence=evidence, store=store)
        j._timeout.check_observation.return_value = CompletionObservationDecision.hold("继续观察")
        mi = _mi()
        result = j.check_exit(_sub(state="P"), mi, lambda *a: [])
        assert result is False
        j._timeout.check_observation.assert_called_once()

    def test_guard_veto_exits_when_completed(self):
        """guard_veto P：观察裁决允许完成 → 退出。"""
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        sig = CompletionSignal(completed=True, confidence="high")
        evidence = CompletionEvidence(primary_signal=sig)
        j = _judge(evidence=evidence, store=store)
        j._timeout.check_observation.return_value = CompletionObservationDecision.allow_complete("信号确认完结")
        mi = _mi()
        result = j.check_exit(_sub(state="P"), mi, lambda *a: [])
        assert result is True
        j._timeout.check_observation.assert_called_once()

    def test_guard_veto_uses_timeout_release_for_low_confidence_completion(self):
        """guard_veto 低置信完成按完成观察裁决释放。"""
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        sig = CompletionSignal(completed=True, confidence="low", stable=True, signals=["I:all_aired"])
        evidence = CompletionEvidence(primary_signal=sig, i_low_signal=sig, scope_total=2, observation_kind="low_i")
        j = _judge(evidence=evidence, store=store)
        j._timeout.check_observation.return_value = CompletionObservationDecision.release_with_token("完成前观察到期")

        subscribe = _sub(state="P", total_episode=2)
        result = j.check_exit(subscribe, _mi(), lambda *a: [])

        assert result is True
        j._timeout.check_observation.assert_called_once_with(subscribe, evidence, mode=j._config.completion_guard_mode)

    def test_guard_veto_low_confidence_stays_before_timeout_release(self):
        """guard_veto 低置信观察未满足退出裁决时继续保持 P。"""
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        sig = CompletionSignal(completed=True, confidence="low", stable=True, signals=["I:all_aired"])
        evidence = CompletionEvidence(primary_signal=sig, i_low_signal=sig, scope_total=2, observation_kind="low_i")
        j = _judge(evidence=evidence, store=store)
        j._timeout.check_observation.return_value = CompletionObservationDecision.hold("继续观察")

        subscribe = _sub(state="P", total_episode=2)
        result = j.check_exit(subscribe, _mi(), lambda *a: [])

        assert result is False
        j._timeout.check_observation.assert_called_once_with(subscribe, evidence, mode=j._config.completion_guard_mode)

    def test_guard_veto_recomputes_l_with_resolver_before_timeout_decision(self):
        """guard_veto 巡检必须带主程序缺集 resolver 重算 L 后再交给观察状态机。"""
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        low_l = CompletionSignal(
            completed=True,
            confidence="low",
            signals=["L:target_satisfied"],
            scope_total=12,
        )
        evidence = CompletionEvidence(
            primary_signal=low_l,
            local_signal=low_l,
            scope_total=12,
            observation_kind="low_l",
        )
        resolver = MagicMock(return_value=(True, {}))
        j = _judge(evidence=evidence, store=store, resolve_missing_fn=resolver)
        j._timeout.check_observation.return_value = CompletionObservationDecision.hold("继续观察")

        subscribe = _sub(state="P", total_episode=2)
        result = j.check_exit(subscribe, _mi(), lambda *a: [])

        assert result is False
        _, kwargs = j._evidence_pipeline.evaluate.call_args
        assert kwargs["resolve_missing_fn"] is resolver
        assert j._timeout.check_observation.call_args.args[1].local_signal is low_l

    def test_pending_judge_does_not_exit_on_medium_completion(self):
        """pending_judge P：中置信完结信号不能提前释放。"""
        store = {"subscribes": {"1": {"state": "P", "source": "pending_judge"}}}
        sig = CompletionSignal(completed=True, confidence="medium", signals=["I:next_season"])
        j = _judge(
            evaluate_result=sig,
            store=store,
            config=PluginConfig({"auto_tv_pending_episodes": 1}),
        )

        result = j.check_exit(_sub(state="P"), _mi(), lambda *a, **kwargs: [_ep(1)])

        assert result is False

    def test_pending_judge_does_not_exit_on_low_completion(self):
        """pending_judge P：低置信完结信号不能提前释放。"""
        store = {"subscribes": {"1": {"state": "P", "source": "pending_judge"}}}
        sig = CompletionSignal(completed=True, confidence="low", signals=["I:all_aired"])
        j = _judge(
            evaluate_result=sig,
            store=store,
            config=PluginConfig({"auto_tv_pending_episodes": 1}),
        )

        result = j.check_exit(_sub(state="P"), _mi(), lambda *a, **kwargs: [_ep(1)])

        assert result is False

    def test_pending_judge_exits_on_high_completion(self):
        """pending_judge P：高置信完结信号可提前释放。"""
        store = {"subscribes": {"1": {"state": "P", "source": "pending_judge"}}}
        sig = CompletionSignal(completed=True, confidence="high", signals=["E:ended"])
        j = _judge(evaluate_result=sig, store=store)

        result = j.check_exit(_sub(state="P"), _mi(), lambda *a: [_ep(1)])

        assert result is True
        assert store["subscribes"]["1"]["reason"] == "信号确认完结"

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

    def test_mark_pending_sends_pending_judge_status_notification(self):
        """剧集待定进入 P 时发送剧集待定通知。"""
        notify = MagicMock()
        j = _judge(notify=notify)

        j.mark_pending(_sub(), source="pending_judge", reason="集数不足")

        notify.assert_called_once()
        assert "剧集信息待确认，订阅已进入待定" in notify.call_args.args[1]
        assert notify.call_args.kwargs["detail"] == "集数不足"

    def test_mark_pending_sends_guard_veto_status_notification(self):
        """完成守卫进入 P 时发送完成前检查通知，并保留集数变化明细。"""
        notify = MagicMock()
        j = _judge(notify=notify)

        j.mark_pending(_sub(), source="guard_veto", reason="目标总集数近期变化（12 -> 13）")

        notify.assert_called_once()
        assert "完成前检查未通过，订阅已进入待定" in notify.call_args.args[1]
        assert notify.call_args.kwargs["detail"] == "目标总集数近期变化（12 -> 13）"

    def test_mark_pending_download_pending_stays_silent(self):
        """下载待定是短窗口内部状态，不发送用户通知。"""
        notify = MagicMock()
        j = _judge(notify=notify)

        j.mark_pending(_sub(), source="download_pending", reason="下载器已创建任务，等待整理入库")

        notify.assert_not_called()

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

    def test_mark_pending_refresh_log_does_not_claim_state_entry(self, monkeypatch):
        """已在 P 中的重复命中只记录刷新，不应再次写成进入待定。"""
        messages = []
        j = _judge()

        monkeypatch.setattr("subscribeassistantenhanced.pending.judge.detail", messages.append)

        j.mark_pending(_sub(state="P"), source="pending_judge", reason="目标总集数近期变化")

        assert len(messages) == 1
        assert "待定刷新" in messages[0]
        assert "待定进入" not in messages[0]
        assert "未触发状态切换" in messages[0]


class TestExitPending:

    def test_exit_clears_guard_observation(self):
        store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        j = _judge(store=store)
        j._exit_pending(_sub(), "测试退出")
        j._timeout.clear_observation.assert_called_once_with(1)
        assert store["subscribes"]["1"]["state"] == "R"

    def test_exit_pending_judge_keeps_guard_veto_block_when_guard_source_remains(self):
        store = {"subscribes": {"1": {
            "state": "P",
            "source": "pending_judge",
            "pending_sources": {
                "pending_judge": {"reason": "集数不足"},
                "guard_veto": {"reason": "未完结"},
            },
        }}}
        j = _judge(store=store)

        j._exit_pending(_sub(state="P"), "待定条件不再满足")

        j._timeout.clear_observation.assert_not_called()
        task = store["subscribes"]["1"]
        assert task["state"] == "P"
        assert task["source"] == "guard_veto"

    def test_exit_guard_veto_clears_guard_veto_observation(self):
        store = {"subscribes": {"1": {
            "state": "P",
            "source": "guard_veto",
            "pending_sources": {"guard_veto": {"reason": "未完结"}},
        }}}
        j = _judge(store=store)

        j._exit_pending(_sub(state="P"), "完成前观察结束")

        j._timeout.clear_observation.assert_called_once_with(1)
        assert store["subscribes"]["1"]["state"] == "R"

    def test_exit_sends_status_notification(self):
        """pending_judge 退出待定应发送剧集待定解除通知。"""
        notify = MagicMock()
        store = {"subscribes": {"1": {"state": "P", "source": "pending_judge"}}}
        j = _judge(store=store, notify=notify)

        j._exit_pending(_sub(state="P"), "待定条件不再满足")

        notify.assert_called_once()
        assert "剧集待定条件解除，订阅已恢复启用" in notify.call_args.args[1]

    def test_exit_guard_veto_sends_observation_end_notification(self):
        """guard_veto 退出待定应发送完成前观察结束通知。"""
        notify = MagicMock()
        store = {"subscribes": {"1": {
            "state": "P",
            "source": "guard_veto",
            "pending_sources": {"guard_veto": {"reason": "未完结"}},
        }}}
        j = _judge(store=store, notify=notify)

        j._exit_pending(_sub(state="P"), "完成前观察结束")

        notify.assert_called_once()
        assert "完成前观察结束，订阅已恢复启用" in notify.call_args.args[1]

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

    def test_exit_keeps_p_log_does_not_claim_pending_exit(self, monkeypatch):
        """仅解除一个待定来源时不应写成退出待定。"""
        messages = []
        store = {"subscribes": {"1": {
            "state": "P",
            "source": "pending_judge",
            "pending_sources": {
                "pending_judge": {"reason": "集数不足"},
                "download_pending": {"reason": "下载中"},
            },
        }}}
        j = _judge(store=store)
        monkeypatch.setattr("subscribeassistantenhanced.pending.judge.logger.info", messages.append)

        j._exit_pending(_sub(state="P"), "待定条件不再满足")

        assert not any("退出待定（P）" in message for message in messages)
        assert any("仍保持待定" in message for message in messages)
