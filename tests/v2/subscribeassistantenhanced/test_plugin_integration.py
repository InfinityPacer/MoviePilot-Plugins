"""端到端集成：插件入口装配 + 事件委托 + 扩展点 smoke（证明集成层真正接通）。"""
import time
from datetime import date
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced import SubscribeAssistantEnhanced
from subscribeassistantenhanced.engine.types import PauseRecord


def _sub(**kwargs):
    """构造完整订阅替身，默认包含 Subscribe 固定字段。"""
    defaults = dict(
        id=1,
        name="测试",
        year=None,
        tmdbid=100,
        season=1,
        episode_group=None,
        type="电视剧",
        state="R",
        best_version=0,
        best_version_full=0,
        total_episode=12,
        start_episode=1,
        lack_episode=0,
        episode_priority={},
        current_priority=0,
        username="",
        filter=None,
        filter_groups=[],
        save_path=None,
        sites=None,
        date=None,
        last_update=None,
    )
    defaults.update(kwargs)
    subscribe = SimpleNamespace(**defaults)
    subscribe.to_dict = lambda: dict(defaults)
    return subscribe


def _mediainfo(**kwargs):
    """构造插件状态通知使用的 MediaInfo 替身。"""
    defaults = dict(
        tmdb_id=100,
        title_year="测试 (2026)",
        vote_average=8.0,
        season_info=[],
        first_air_date=None,
        release_date=None,
        type=SimpleNamespace(value="电视剧"),
    )
    defaults.update(kwargs)
    media = SimpleNamespace(**defaults)
    media.to_dict = lambda: {"tmdb_id": media.tmdb_id}
    media.get_message_image = lambda: "poster.jpg"
    return media


def test_converter_is_wired():
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    assert plugin._modules.get("converter") is not None


def test_episode_to_full_converts_when_current_episodes_covered():
    sub = _sub(id=5, name="X", best_version=1, best_version_full=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_episode_to_full": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))
    plugin._detect_missing_episodes = MagicMock(return_value=[])
    conv = plugin._modules["converter"]
    conv.convert_to_full = MagicMock(return_value=True)

    plugin.run_best_version_check()

    conv.convert_to_full.assert_called_once_with(sub, plugin._recognize_mediainfo.return_value)


def test_episode_to_full_converts_when_download_chain_reports_all_exists(monkeypatch):
    """主程序明确返回全部在库时，分集洗版仍可升级为全集洗版。"""
    sub = _sub(id=5, name="X", best_version=1, best_version_full=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_episode_to_full": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))

    class FakeDownloadChain:
        """避免访问真实媒体库，只模拟主程序全部存在的返回值。"""

        def get_no_exists_info(self, meta, mediainfo):
            return True, {}

    monkeypatch.setattr("app.chain.download.DownloadChain", FakeDownloadChain)
    conv = plugin._modules["converter"]
    conv.convert_to_full = MagicMock(return_value=True)

    plugin.run_best_version_check()

    conv.convert_to_full.assert_called_once_with(sub, plugin._recognize_mediainfo.return_value)


def test_episode_to_full_skipped_when_missing_episodes():
    sub = _sub(id=5, name="X", best_version=1, best_version_full=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_episode_to_full": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))
    plugin._detect_missing_episodes = MagicMock(return_value=[3])
    conv = plugin._modules["converter"]
    conv.convert_to_full = MagicMock(return_value=True)

    plugin.run_best_version_check()

    conv.convert_to_full.assert_not_called()


def test_episode_to_full_skips_when_missing_info_uses_relative_episode_numbers(monkeypatch):
    """媒体库缺集返回相对集号时，绝对集号订阅不能被误判为已全覆盖。"""
    sub = _sub(
        id=32,
        name="航海王",
        season=22,
        best_version=1,
        best_version_full=0,
        total_episode=9999,
        start_episode=1089,
        lack_episode=8844,
        episode_priority={str(ep): 100 for ep in range(1089, 1156)},
        current_priority=100,
    )
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_episode_to_full": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))

    class RelativeNoExistsInfo:
        """模拟主程序按季内相对集号返回缺集范围。"""

        episodes = list(range(1, 68))
        total_episode = 67
        start_episode = 1

    class FakeDownloadChain:
        """避免访问真实媒体库，只返回生产复现场景的缺集结构。"""

        def get_no_exists_info(self, meta, mediainfo):
            return False, {100: {22: RelativeNoExistsInfo()}}

    monkeypatch.setattr("app.chain.download.DownloadChain", FakeDownloadChain)
    conv = plugin._modules["converter"]
    conv.convert_to_full = MagicMock(return_value=True)

    plugin.run_best_version_check()

    conv.convert_to_full.assert_not_called()


def test_best_version_check_marks_overdue_subscription_complete():
    """洗版订阅最近活动超过时限时终止洗版。"""
    now = time.time()
    sub = _sub(id=5, name="X", best_version=1, best_version_full=1)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_remaining_days": 3})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))
    plugin._task_manager.read = MagicMock(side_effect=lambda key: {
        "torrents": {"hash": {"subscribe_id": 5, "time": now - 10 * 86400}},
        "subscribes": {"5": {"best_version_anchor": now - 10 * 86400}},
    }.get(key, {}))
    priority = plugin._modules["priority_manager"]
    priority.mark_complete = MagicMock()
    plugin._modules["orchestrator"].check_complete = MagicMock(return_value=False)

    plugin.run_best_version_check()

    priority.mark_complete.assert_called_once_with(sub)


def test_best_version_check_skips_when_type_closed():
    """洗版类型为关闭时，手动巡检也不推进已有洗版订阅。"""
    sub = _sub(id=5, name="X", best_version=1, best_version_full=1)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "no"})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]

    plugin.run_best_version_check()

    plugin._subscribe_oper.list.assert_not_called()


def test_best_version_check_does_not_expire_when_remaining_days_unlimited():
    """洗版时限为零时不走超时终止。"""
    now = time.time()
    sub = _sub(id=5, name="X", best_version=1, best_version_full=1)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_remaining_days": 0})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))
    plugin._task_manager.read = MagicMock(return_value={
        "hash": {"subscribe_id": 5, "time": now - 10 * 86400},
    })
    priority = plugin._modules["priority_manager"]
    priority.mark_complete = MagicMock()
    plugin._modules["orchestrator"].check_complete = MagicMock(return_value=False)

    plugin.run_best_version_check()

    priority.mark_complete.assert_not_called()


def test_best_version_check_keeps_subscription_with_recent_activity():
    """洗版订阅最近活动仍在时限内时继续巡检。"""
    now = time.time()
    sub = _sub(id=5, name="X", best_version=1, best_version_full=1)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_remaining_days": 3})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))
    plugin._task_manager.read = MagicMock(side_effect=lambda key: {
        "torrents": {"hash": {"subscribe_id": 5, "time": now - 86400}},
        "subscribes": {"5": {"best_version_anchor": now - 10 * 86400}},
    }.get(key, {}))
    priority = plugin._modules["priority_manager"]
    priority.mark_complete = MagicMock()
    plugin._modules["orchestrator"].check_complete = MagicMock(return_value=False)

    plugin.run_best_version_check()

    priority.mark_complete.assert_not_called()


def test_get_state_uses_global_enabled():
    """插件总状态由 enabled 决定。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"enabled": False})
    assert plugin.get_state() is False

    enabled_plugin = SubscribeAssistantEnhanced()
    enabled_plugin.init_plugin({"enabled": True, "completion_guard_enabled": False})
    assert enabled_plugin.get_state() is True


def test_disabled_plugin_registers_no_services():
    """enabled=False 时不注册任何定时任务。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"enabled": False})
    assert plugin.get_service() == []


def test_meta_check_service_registered():
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"enabled": True, "meta_check_interval_hours": 6})
    svc = {s["id"]: s for s in plugin.get_service()}
    assert "SubscribeAssistantEnhanced_meta_check" in svc
    assert svc["SubscribeAssistantEnhanced_meta_check"]["kwargs"] == {"hours": 6}


def test_common_check_service_registered():
    """插件启用时只注册一个通用巡检服务。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"enabled": True, "auto_check_interval_minutes": 45})
    svc = {s["id"]: s for s in plugin.get_service()}

    assert "SubscribeAssistantEnhanced_common_check" in svc
    assert svc["SubscribeAssistantEnhanced_common_check"]["name"] == "通用巡检"
    assert svc["SubscribeAssistantEnhanced_common_check"]["kwargs"] == {"minutes": 45}
    assert not any(service_id.endswith(("_pending_release", "_no_download", "_deletes_cleanup"))
                   for service_id in svc)


def test_run_meta_check_reevaluates_pending_subscriptions():
    sub = _sub(id=7, state="P", name="X")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))
    judge = plugin._modules["pending_judge"]
    judge.check_exit = MagicMock(return_value=True)
    plugin.run_meta_check()
    judge.check_exit.assert_called_once()


def test_run_meta_check_calls_pause_when_pre_air_condition_holds():
    """活动订阅命中上映前暂停条件时，run_meta_check 调用 pause_manager.pause。"""
    from subscribeassistantenhanced.engine.types import PauseRecord

    sub = _sub(id=3, state="R", name="X", best_version=0, type="电影",
               season=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))

    # 让 airing_checker.check_pre_air 返回一条暂停记录；airing_checker 存在于 _modules
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(
        return_value=PauseRecord(reason="pre_air", since=0.0, detail="上映日期未知，暂停等待")
    )
    pause_manager = plugin._modules["pause_manager"]
    pause_manager.pause = MagicMock()

    plugin.run_meta_check()

    pause_manager.pause.assert_called_once()
    call_args = pause_manager.pause.call_args
    assert call_args.args[1].reason == "pre_air"


def test_run_meta_check_resumes_when_airing_condition_no_longer_holds():
    """上映/播出暂停（reason=pre_air，state=S）条件已不成立时，run_meta_check 双向自动恢复。

    上映前暂停条件解除后，S 态订阅恢复为 R。
    """
    sub = _sub(id=3, state="S", name="X", best_version=0, type="电影",
               season=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))

    pause_manager = plugin._modules["pause_manager"]
    # 当前记录为上映暂停（pre_air，非标记暂停），不应触发顶部跳过/清标记
    pause_manager.get_pause_record = MagicMock(
        return_value=PauseRecord(reason="pre_air", since=0.0, detail="上映日期未知，暂停等待"))
    pause_manager.resume = MagicMock()
    pause_manager.pause = MagicMock()
    pause_manager.clear_pause_record = MagicMock()

    # 上映前/播出检查均返回 None（条件已解除）
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)

    plugin.run_meta_check()

    pause_manager.resume.assert_called_once_with(sub)
    pause_manager.pause.assert_not_called()
    pause_manager.clear_pause_record.assert_not_called()


def test_run_meta_check_skips_flag_paused_no_download_subscription():
    """无下载标记暂停（reason=no_download，state=S）的订阅被 run_meta_check 跳过，不触发恢复。

    标记暂停且仍为 S 态时直接跳过，避免被上映检查自动恢复或重复处理。
    """
    sub = _sub(id=11, state="S", name="X", best_version=0, type="电影",
               season=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.get_pause_record = MagicMock(
        return_value=PauseRecord(reason="no_download", since=0.0, detail="上映后超期且无下载"))
    pause_manager.resume = MagicMock()
    pause_manager.pause = MagicMock()
    pause_manager.clear_pause_record = MagicMock()

    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)

    plugin.run_meta_check()

    # 标记暂停 + S → 完全跳过：不恢复、不暂停、不清标记、连媒体识别都不到
    pause_manager.resume.assert_not_called()
    pause_manager.pause.assert_not_called()
    pause_manager.clear_pause_record.assert_not_called()
    plugin._recognize_mediainfo.assert_not_called()


def test_run_meta_check_clears_flag_when_user_reenabled():
    """标记暂停但用户已重新启用（reason=no_download，state!=S）→ 清插件标记后继续后续判定。

    用户已重新启用后，插件侧暂停记录应交还状态归属并被清理。
    """
    sub = _sub(id=12, state="R", name="X", best_version=0, type="电影",
               season=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.get_pause_record = MagicMock(
        return_value=PauseRecord(reason="no_download", since=0.0, detail="上映后超期且无下载"))
    pause_manager.resume = MagicMock()
    pause_manager.pause = MagicMock()
    pause_manager.clear_pause_record = MagicMock()

    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)

    plugin.run_meta_check()

    pause_manager.clear_pause_record.assert_called_once_with(sub)
    # 已是 R 且上映条件不成立 → 不再调用 resume（仅 state==S 才双向恢复）
    pause_manager.resume.assert_not_called()
    pause_manager.pause.assert_not_called()


def test_run_meta_check_marks_pending_when_should_enter_pending():
    """活动订阅未命中暂停但 pending 条件成立时，run_meta_check 调用 pending_judge.mark_pending。"""
    sub = _sub(id=4, state="R", name="X", best_version=0, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))
    plugin._tmdb_episodes = MagicMock(return_value=[])
    plugin._evaluate_fn = MagicMock(return_value=None)

    # 暂停检查器均返回 None（不暂停）；airing_checker 存在于 _modules
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)

    judge = plugin._modules["pending_judge"]
    judge.should_enter_pending = MagicMock(return_value=(True, "集数不足"))
    judge.mark_pending = MagicMock()

    plugin.run_meta_check()

    judge.mark_pending.assert_called_once()
    call_args = judge.mark_pending.call_args
    assert call_args.kwargs.get("source") == "pending_judge"


def test_run_meta_check_check_exit_called_for_p_state_sub():
    """P 状态订阅在巡检中仍调用 check_exit，避免被暂停分支覆盖。"""
    sub = _sub(id=7, state="P", name="X", best_version=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))

    judge = plugin._modules["pending_judge"]
    judge.check_exit = MagicMock(return_value=False)

    plugin.run_meta_check()

    judge.check_exit.assert_called_once()


def test_run_meta_check_p_state_skips_pre_air_pause():
    """P 状态由待定域负责退出，默认上映前暂停不能覆盖成 S。"""
    sub = _sub(id=7, state="P", name="X", best_version=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))

    judge = plugin._modules["pending_judge"]
    judge.check_exit = MagicMock(return_value=False)
    pause_manager = plugin._modules["pause_manager"]
    pause_manager.pause = MagicMock()

    plugin.run_meta_check()

    judge.check_exit.assert_called_once()
    pause_manager.pause.assert_not_called()


def test_run_all_checks_invokes_each_runner():
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"enabled": True})
    mocks = {}
    for name in ("run_meta_check", "run_download_timeout_check", "run_best_version_check",
                 "run_completion_verify", "run_common_check"):
        mocks[name] = MagicMock()
        setattr(plugin, name, mocks[name])
    plugin.run_all_checks()
    for name in ("run_meta_check", "run_download_timeout_check", "run_best_version_check",
                 "run_completion_verify", "run_common_check"):
        mocks[name].assert_called_once()


def test_run_common_check_runs_enabled_subtasks():
    """通用巡检按域开关执行待定释放、无下载处理和删除记录清理。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "timeout_release_enabled": True,
        "download_monitor_enabled": True,
    })
    plugin.run_pending_release = MagicMock()
    plugin.run_no_download_check = MagicMock()
    plugin.run_deletes_cleanup = MagicMock()

    plugin.run_common_check()

    plugin.run_pending_release.assert_called_once()
    plugin.run_no_download_check.assert_called_once()
    plugin.run_deletes_cleanup.assert_called_once()


def test_run_common_check_isolates_subtask_failures():
    """一个通用巡检子任务失败时，后续子任务仍继续执行。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "timeout_release_enabled": True,
        "download_monitor_enabled": True,
    })
    plugin.run_pending_release = MagicMock(side_effect=RuntimeError("pending failed"))
    plugin.run_no_download_check = MagicMock()
    plugin.run_deletes_cleanup = MagicMock()

    plugin.run_common_check()

    plugin.run_no_download_check.assert_called_once()
    plugin.run_deletes_cleanup.assert_called_once()


def test_run_common_check_respects_domain_switches():
    """关闭对应域后，通用巡检不执行待定释放和删除记录清理。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "timeout_release_enabled": False,
        "download_monitor_enabled": False,
    })
    plugin.run_pending_release = MagicMock()
    plugin.run_no_download_check = MagicMock()
    plugin.run_deletes_cleanup = MagicMock()

    plugin.run_common_check()

    plugin.run_pending_release.assert_not_called()
    plugin.run_no_download_check.assert_called_once()
    plugin.run_deletes_cleanup.assert_not_called()


def test_onlyonce_registers_one_shot_and_resets_flag():
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()
    plugin.init_plugin({"enabled": True, "onlyonce": True})
    assert plugin._onlyonce is True
    ids = {s["id"] for s in plugin.get_service()}
    assert "SubscribeAssistantEnhanced_onlyonce" in ids
    plugin.update_config.assert_called()


def test_reset_task_clears_data_and_resets_flag():
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()
    plugin.save_data = MagicMock()
    plugin.init_plugin({"reset_task": True})
    cleared = {c.args[0] for c in plugin.save_data.call_args_list}
    assert {"subscribes", "torrents", "blocks", "snapshots", "deletes", "volatility"} <= cleared
    plugin.update_config.assert_called()


def test_backfill_best_version_now_scans_existing_subscriptions_and_resets_flag(monkeypatch):
    """立即回填会扫描存量洗版订阅，并在执行后关闭一次性标志。"""
    sub = _sub(id=5, name="X", best_version=1)
    subscribe_oper = MagicMock()
    subscribe_oper.list.return_value = [sub]
    priority_manager = MagicMock()
    monkeypatch.setattr("subscribeassistantenhanced.SubscribeOper", MagicMock(return_value=subscribe_oper))
    monkeypatch.setattr("subscribeassistantenhanced.PriorityManager", MagicMock(return_value=priority_manager))
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()
    plugin._detect_existing_episodes = MagicMock(return_value=[3])

    plugin.init_plugin({"backfill_best_version_now": True})

    priority_manager.backfill_existing.assert_called_once_with(sub, [3])
    plugin.update_config.assert_called_once()
    assert plugin.update_config.call_args.args[0]["backfill_best_version_now"] is False


def test_notify_gate_blocks_when_disabled():
    """notify=False 时不发送消息，notify=True 时发送。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"notify": False})
    plugin.post_message = MagicMock()
    plugin._notify_subscribe("测试通知", "通知正文")
    plugin.post_message.assert_not_called()

    notifying_plugin = SubscribeAssistantEnhanced()
    notifying_plugin.init_plugin({"notify": True})
    notifying_plugin.post_message = MagicMock()
    notifying_plugin._notify_subscribe("测试通知", "通知正文")
    notifying_plugin.post_message.assert_called_once()


def test_manual_delete_listen_off_disables_present_fn():
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"manual_delete_listen": False})
    assert plugin._modules["download_monitor"]._present_fn is None

    plugin2 = SubscribeAssistantEnhanced()
    plugin2.init_plugin({"manual_delete_listen": True})
    assert plugin2._modules["download_monitor"]._present_fn is not None


def test_tracker_listen_off_clears_keywords():
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "tracker_response_listen": False,
        "default_tracker_response": "unregistered\nnot found",
    })
    assert plugin._modules["download_monitor"]._tracker_keywords == []


def test_blank_tracker_defaults_are_persisted_for_form_model():
    """旧配置若已保存空字符串，初始化时回写安全默认值，避免表单合并 stored config 后继续显示为空。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()

    plugin.init_plugin({
        "delete_exclude_tags": "",
        "default_tracker_response": "",
    })

    plugin.update_config.assert_called_once()
    updated = plugin.update_config.call_args.args[0]
    assert updated["delete_exclude_tags"] == "H&R"
    assert "torrent not registered" in updated["default_tracker_response"]


def test_auto_search_off_disables_search_fn():
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"auto_search_when_delete": False})
    assert plugin._modules["torrent_cleanup"]._search is None


def test_pending_refresh_does_not_depend_on_default_total_config():
    """待定缺总集数时由 PendingRefresh 直接按已播集覆盖，不依赖配置注入。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    assert not hasattr(plugin._modules["pending_refresh"], "_default_total")


def test_airing_checker_receives_pre_air_days():
    """插件入口必须把电影和电视剧上映前暂停天数注入播出判定器。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "pause_enhanced_enabled": True,
        "movie_air_pause_days": 7,
        "tv_air_pause_days": 5,
    })
    airing_checker = plugin._event_proxy.get("airing_checker")

    assert airing_checker._movie_air_days == 7
    assert airing_checker._tv_air_days == 5


def test_orchestrator_receives_type_filters():
    """插件入口必须把洗版和清理媒体类型范围注入编排器。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "best_version_type": "tv",
        "best_version_clear_history_type": "movie",
    })
    orchestrator = plugin._modules["orchestrator"]

    assert orchestrator._best_version_type == "tv"
    assert orchestrator._clear_history_type == "movie"


class TestPluginWiring:
    """init_plugin 后各域模块、事件代理依赖、扩展点均就位。"""

    def test_all_domain_modules_populated(self):
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"best_version_type": "all"})
        for name in ("priority_manager", "download_monitor", "torrent_cleanup",
                     "deletes_store", "orchestrator", "guard", "pause_manager",
                     "pending_judge", "verifier", "timeout_manager"):
            assert name in plugin._modules, f"缺少模块 {name}"

    def test_event_proxy_has_cross_cutting_deps(self):
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"best_version_type": "all"})
        proxy = plugin._event_proxy
        assert proxy.get("task_manager") is not None
        assert proxy.get("subscribe_oper") is not None
        assert proxy.get("post_message") is not None
        assert proxy.get("deletes_store") is not None

    def test_extension_points_active(self):
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"enabled": True})
        assert plugin.get_command()            # /subscribe_toggle
        conf, model = plugin.get_form()
        assert conf and model
        assert plugin.get_service()            # 启用后有定时任务

    def test_pause_manager_receives_subscribe_oper(self):
        """插件入口必须给 PauseManager 注入 subscribe_oper，pause/resume 才能改 DB 状态。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"pause_enhanced_enabled": True})
        pause_manager = plugin._modules["pause_manager"]
        assert pause_manager._subscribe_oper is plugin._subscribe_oper

    def test_pause_manager_receives_auto_pause_users(self):
        """入口须把逗号分隔的 auto_pause_users 解析为列表注入 PauseManager，否则用户名自动暂停永不命中。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"pause_enhanced_enabled": True, "auto_pause_users": "alice, bob ,"})
        pause_manager = plugin._modules["pause_manager"]
        # 去空白、丢空项：用户配置里的多余空格和尾随分隔符不应进入匹配名单
        assert pause_manager._auto_pause_users == ["alice", "bob"]

    def test_download_monitor_reuses_common_check_service(self):
        """下载管理开启时删除记录清理由通用巡检承载，不单独注册任务。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"enabled": True, "download_monitor_enabled": True})
        service_ids = {s["id"] for s in plugin.get_service()}
        assert "SubscribeAssistantEnhanced_common_check" in service_ids
        assert "SubscribeAssistantEnhanced_deletes_cleanup" not in service_ids


class TestEventDelegation:
    """插件类事件方法委托到 EventProxy；无 proxy 时安全空转。"""

    def test_handler_delegates_to_proxy(self):
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        plugin._event_proxy = MagicMock()
        event = SimpleNamespace(event_data={"subscribe_id": 1})
        plugin.on_subscribe_deleted(event)
        plugin._event_proxy.on_subscribe_deleted.assert_called_once_with(event)

    def test_handler_safe_without_proxy(self):
        plugin = SubscribeAssistantEnhanced()
        plugin._event_proxy = None
        plugin.on_subscribe_deleted(SimpleNamespace(event_data={}))  # 不应抛错

    def test_stop_service_clears_state(self):
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        plugin.stop_service()
        assert plugin._event_proxy is None
        assert plugin._modules == {}


class TestPeriodicJobs:
    """定时巡检：洗版完成标记 + 待定超时释放（recognize/oper 以 mock 注入）。"""

    def test_best_version_check_marks_complete(self, monkeypatch):
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"best_version_type": "all"})
        best_sub = _sub(id=1, name="X", best_version=1)
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [best_sub]
        monkeypatch.setattr(plugin, "_recognize_mediainfo", lambda sub: object())
        orch = MagicMock()
        orch.check_complete.return_value = True
        priority = MagicMock()
        plugin._modules["orchestrator"] = orch
        plugin._modules["priority_manager"] = priority
        plugin.run_best_version_check()
        priority.mark_complete.assert_called_once_with(best_sub)

    def test_best_version_check_passes_missing_episodes(self):
        """洗版完成巡检必须把媒体库缺集传给 orchestrator.check_complete。"""
        sub = _sub(id=9, name="测试", best_version=1)
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"best_version_type": "all"})
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [sub]
        plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))
        plugin._detect_missing_episodes = MagicMock(return_value=[3])
        orchestrator = plugin._modules["orchestrator"]
        orchestrator.check_complete = MagicMock(return_value=False)

        plugin.run_best_version_check()

        orchestrator.check_complete.assert_called_once()
        assert orchestrator.check_complete.call_args.args[2] == [3]

    def test_best_version_check_keeps_episode_subscription_when_target_not_complete(self):
        """分集洗版目标范围未全达标时，即使已有优先级都是 100 也不能判定洗版完成。"""
        sub = _sub(
            id=9,
            name="测试",
            best_version=1,
            best_version_full=0,
            start_episode=1,
            total_episode=9999,
            episode_priority={"1": 100, "2": 100},
        )
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"best_version_type": "all"})
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [sub]
        plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))
        plugin._detect_missing_episodes = MagicMock(return_value=[3])
        priority = plugin._modules["priority_manager"]
        priority.mark_complete = MagicMock()

        plugin.run_best_version_check()

        priority.mark_complete.assert_not_called()

    def test_detect_missing_episodes_returns_partial_missing_set(self, monkeypatch):
        """媒体库部分覆盖时，helper 返回缺失集而不是已存在集。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        sub = _sub(id=9, name="测试", start_episode=1, total_episode=5)
        plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))

        def fake_no_exists(*args, **kwargs):
            return False, {100: {1: SimpleNamespace(episodes=[3, 5])}}

        monkeypatch.setattr(
            "app.chain.download.DownloadChain.get_no_exists_info",
            fake_no_exists,
        )

        assert plugin._detect_missing_episodes(sub) == [3, 5]

    def test_detect_missing_episodes_expands_whole_season_missing(self, monkeypatch):
        """主程序用 episodes=[] 表示整季缺失，helper 必须展开为完整目标范围。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        sub = _sub(id=9, name="测试", start_episode=2, total_episode=5)
        plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))

        def fake_no_exists(*args, **kwargs):
            return False, {100: {1: SimpleNamespace(episodes=[])}}

        monkeypatch.setattr(
            "app.chain.download.DownloadChain.get_no_exists_info",
            fake_no_exists,
        )

        assert plugin._detect_missing_episodes(sub) == [2, 3, 4, 5]

    def test_detect_missing_episodes_returns_empty_when_fully_covered(self, monkeypatch):
        """媒体库完整覆盖时没有缺集。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        sub = _sub(id=9, name="测试", start_episode=1, total_episode=5)
        plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))
        monkeypatch.setattr(
            "app.chain.download.DownloadChain.get_no_exists_info",
            lambda *args, **kwargs: (True, {}),
        )

        assert plugin._detect_missing_episodes(sub) == []

    def test_snapshot_rebuild_calls_real_subscribe_add_contract(self):
        """H 重建适配器必须以 MediaInfo + kwargs 调用主程序 SubscribeOper.add。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        mediainfo = _mediainfo()

        class StrictSubscribeOper:
            """仅接受主程序真实 add 签名的测试替身。"""

            def __init__(self):
                self.call = None

            def add(self, *, mediainfo, **kwargs):
                """记录 MediaInfo 与订阅配置。"""
                self.call = (mediainfo, kwargs)
                return 88, "新增订阅成功"

        oper = StrictSubscribeOper()
        plugin._subscribe_oper = oper
        plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)

        result = plugin._rebuild_subscribe_from_snapshot(
            {"tmdbid": 100, "season": 1, "episode_group_id": "eg-1"},
            {"name": "测试", "start_episode": 13},
        )

        assert result is True
        assert oper.call[0] is mediainfo
        assert oper.call[1]["season"] == 1
        assert oper.call[1]["episode_group"] == "eg-1"

    def test_snapshot_rebuild_sends_subscribe_added_event(self):
        """H 重建成功后应补发 SubscribeAdded，触发主程序订阅创建链路。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.add.return_value = (88, "新增订阅成功")
        plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
        plugin._send_subscribe_added = MagicMock()

        result = plugin._rebuild_subscribe_from_snapshot(
            {"tmdbid": 100, "season": 1, "episode_group_id": "eg-1"},
            {"name": "测试", "start_episode": 13},
        )

        assert result is True
        plugin._send_subscribe_added.assert_called_once()
        assert plugin._send_subscribe_added.call_args.args[0] == 88

    def test_pending_release_releases_when_timed_out(self, monkeypatch):
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        sub = _sub(id=1, state="P")
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.get.return_value = sub
        plugin._subscribe_oper.list.return_value = []  # Task5 P 退出巡检：本用例只验证 blocks 超时路径
        task_store = {"subscribes": {"1": {"state": "P", "source": "guard_veto"}}}
        plugin._task_manager.read = MagicMock(side_effect=lambda key: task_store.get(key, {}))

        def update_task(key, updater):
            data = task_store.get(key, {})
            task_store[key] = updater(data)
            return task_store[key]

        plugin._task_manager.update = MagicMock(side_effect=update_task)
        plugin._modules["pending_state"]._read = plugin._task_manager.read
        plugin._modules["pending_state"]._update = plugin._task_manager.update
        plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper
        monkeypatch.setattr(plugin, "_recognize_mediainfo", lambda s: _mediainfo())
        monkeypatch.setattr(plugin, "get_data",
                            lambda key: {"1": {"blocked_at": 0}} if key == "blocks" else {})
        plugin._evaluate_fn = lambda s, m: object()
        timeout_manager = MagicMock()
        timeout_manager.check_release.return_value = True
        plugin._modules["timeout_manager"] = timeout_manager
        plugin.run_pending_release()
        plugin._subscribe_oper.update.assert_called_once()
        payload = plugin._subscribe_oper.update.call_args.args[1]
        assert payload["state"] == "R"
        assert payload["last_update"]
        timeout_manager.clear_block.assert_called_once_with(1)

    def test_pending_release_keeps_p_when_download_pending_active(self, monkeypatch):
        """guard_veto 超时释放时若下载待定仍在，不能把订阅恢复 R。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        sub = _sub(id=1, state="P")
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.get.return_value = sub
        plugin._subscribe_oper.list.return_value = []
        task_store = {"subscribes": {"1": {
            "state": "P",
            "source": "guard_veto",
            "pending_sources": {
                "guard_veto": {"reason": "未完结"},
                "download_pending": {"reason": "下载中"},
            },
            "download_pending": {"hash1": {"hash": "hash1"}},
        }}}
        plugin._task_manager.read = MagicMock(side_effect=lambda key: task_store.get(key, {}))

        def update_task(key, updater):
            data = task_store.get(key, {})
            task_store[key] = updater(data)
            return task_store[key]

        plugin._task_manager.update = MagicMock(side_effect=update_task)
        plugin._modules["pending_state"]._read = plugin._task_manager.read
        plugin._modules["pending_state"]._update = plugin._task_manager.update
        plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper
        monkeypatch.setattr(plugin, "_recognize_mediainfo", lambda s: _mediainfo())
        monkeypatch.setattr(plugin, "get_data",
                            lambda key: {"1": {"blocked_at": 0}} if key == "blocks" else {})
        plugin._evaluate_fn = lambda s, m: object()
        timeout_manager = MagicMock()
        timeout_manager.check_release.return_value = True
        plugin._modules["timeout_manager"] = timeout_manager

        plugin.run_pending_release()

        assert task_store["subscribes"]["1"]["state"] == "P"
        assert task_store["subscribes"]["1"]["source"] == "download_pending"
        assert not any(
            call_args.args[1]["state"] == "R"
            for call_args in plugin._subscribe_oper.update.call_args_list
        )

    def test_pending_release_sends_guard_timeout_notification(self, monkeypatch):
        """guard_veto 超时释放应发送订阅状态通知。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"notify": True})
        sub = _sub(id=1, name="测试剧", username="user")
        mediainfo = _mediainfo(
            title_year="测试剧 (2026)",
            vote_average=8.0,
            type=SimpleNamespace(value="电视剧"),
        )
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.get.return_value = sub
        plugin._subscribe_oper.list.return_value = []
        monkeypatch.setattr(plugin, "_recognize_mediainfo", lambda s: mediainfo)
        monkeypatch.setattr(plugin, "get_data",
                            lambda key: {"1": {"blocked_at": 0}} if key == "blocks" else {})
        plugin._evaluate_fn = lambda s, m: object()
        timeout_manager = MagicMock()
        timeout_manager.check_release.return_value = True
        plugin._modules["timeout_manager"] = timeout_manager
        plugin.post_message = MagicMock()

        plugin.run_pending_release()

        plugin.post_message.assert_called_once()
        assert "不再满足上映待定，已标记订阅中" in plugin.post_message.call_args.kwargs["title"]

    def test_pending_release_checks_pending_judge_tasks(self):
        """pending_judge 写入的 P 订阅应由定时巡检调用 check_exit，而不只处理 blocks。"""
        sub = _sub(id=7, state="P", name="测试", best_version=0)
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"timeout_release_enabled": True, "pending_enhanced_enabled": True})
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [sub]
        plugin._subscribe_oper.get.return_value = sub
        plugin.get_data = MagicMock(return_value={})
        plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))
        pending_judge = plugin._modules["pending_judge"]
        pending_judge.check_exit = MagicMock(return_value=True)

        plugin.run_pending_release()

        pending_judge.check_exit.assert_called_once()

    def test_pending_release_reconciles_download_pending_expiry(self):
        """待定释放巡检应触发下载待定过期清理，避免无 hash 任务长期卡 P。"""
        sub = _sub(id=7, state="P", name="测试", best_version=0)
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"timeout_release_enabled": True, "pending_download_enabled": True})
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [sub]
        plugin._subscribe_oper.get.return_value = sub
        download_monitor = plugin._modules["download_monitor"]
        download_monitor.has_active_downloads = MagicMock(return_value=False)
        pending_judge = plugin._modules["pending_judge"]
        pending_judge.check_exit = MagicMock(return_value=False)
        plugin.get_data = MagicMock(return_value={})
        plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))

        plugin.run_pending_release()

        download_monitor.has_active_downloads.assert_called_once_with(7)


class TestVerifierWiring:
    """H 自验证：service 注册 + verifier 运行依赖注入。"""

    def test_completion_verifier_service_registered_when_enabled(self):
        """verify_enabled 开启时应注册 H 自验证定时任务。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"enabled": True, "verify_enabled": True})
        service_ids = {s["id"] for s in plugin.get_service()}
        assert "SubscribeAssistantEnhanced_verify" in service_ids

    def test_completion_verifier_has_runtime_dependencies(self):
        """CompletionVerifier 必须能 fetch TMDB、重建订阅并通知。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"verify_enabled": True})
        verifier = plugin._modules["verifier"]
        assert verifier._tmdb_fn is not None
        assert verifier._subscribe_oper is plugin._subscribe_oper
        assert verifier._notify is not None


def test_download_pause_expiry_runtime_is_removed():
    """下载超时删种不再暂停订阅，因此插件入口不注册下载暂停超期运行时。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True})

    assert "download_pause_checker" not in plugin._modules
    assert not hasattr(plugin, "run_download_pause_expiry")


def test_orchestrator_uses_related_download_history_helper():
    """自动洗版编排器应注入真实关联下载历史 helper。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "tv_episode"})

    assert plugin._modules["orchestrator"]._related_downloads == plugin._related_download_histories


def test_download_pending_works_when_timeout_delete_disabled():
    """下载待定只受 pending_download_enabled 控制，不随下载超时自动删除关闭。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "download_monitor_enabled": False,
        "pending_download_enabled": True,
    })

    assert plugin._event_proxy.get("download_monitor") is plugin._modules["download_monitor"]
    assert plugin._event_proxy.get("pending_download_enabled") is True


class TestNoDownloadCheck:
    """无下载处理巡检执行策略返回的订阅动作。"""

    def test_last_download_date_queries_tv_history_and_returns_latest_date(self):
        """电视剧按媒体信息和季查询下载历史，并返回最近下载日期。"""
        subscribe = _sub(type="电视剧", name="测试", year="2025", season=1, tmdbid=100)
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        plugin._downloadhistory_oper = MagicMock()
        plugin._downloadhistory_oper.get_last_by.return_value = [
            SimpleNamespace(date="2025-02-01 10:00:00"),
            SimpleNamespace(date="2025-03-01 10:00:00"),
        ]

        result = plugin._last_download_date(subscribe)

        assert result == date(2025, 3, 1)
        plugin._downloadhistory_oper.get_last_by.assert_called_once_with(
            mtype="电视剧",
            title="测试",
            year="2025",
            season="S01",
            tmdbid=100,
        )

    def test_last_download_date_returns_none_when_history_query_fails(self):
        """下载历史查询异常时安全返回 None。"""
        subscribe = _sub(type="电影", name="测试", year="2025", tmdbid=100)
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        plugin._downloadhistory_oper = MagicMock()
        plugin._downloadhistory_oper.get_last_by.side_effect = RuntimeError("query failed")

        assert plugin._last_download_date(subscribe) is None
        plugin._downloadhistory_oper.get_last_by.assert_called_once_with(
            mtype="电影",
            title="测试",
            year="2025",
            tmdbid=100,
        )

    def test_related_episode_download_histories_filters_full_pack_and_source(self):
        """分集洗版历史只保留同订阅分集下载，排除全集包和其他订阅 source。"""
        subscribe = _sub(
            id=18,
            type="电视剧",
            name="测试",
            year="2025",
            season=1,
            tmdbid=100,
            total_episode=12,
            date="2025-01-01 00:00:00",
        )
        episode_download = SimpleNamespace(
            date="2025-02-01 00:00:00",
            note={"source": 'Subscribe|{"id":18,"tmdbid":100,"year":"2025","season":1}'},
            episode_group=None,
            torrent_name="测试 S01E01",
            torrent_description="",
        )
        full_pack = SimpleNamespace(
            date="2025-02-02 00:00:00",
            note={"source": 'Subscribe|{"id":18,"tmdbid":100,"year":"2025","season":1}'},
            episode_group=None,
            torrent_name="测试 S01",
            torrent_description="Complete 12 Episodes",
        )
        other_subscribe = SimpleNamespace(
            date="2025-02-03 00:00:00",
            note={"source": 'Subscribe|{"id":99,"tmdbid":100,"year":"2025","season":1}'},
            episode_group=None,
            torrent_name="测试 S01E02",
            torrent_description="",
        )
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        plugin._downloadhistory_oper = MagicMock()
        plugin._downloadhistory_oper.get_last_by.return_value = [
            episode_download,
            full_pack,
            other_subscribe,
        ]

        assert plugin._related_download_histories(subscribe) == [episode_download]

    def test_overdue_tv_delete_action_deletes_subscribe(self):
        """剧集超期且无下载时按 delete_tv 删除订阅。"""
        subscribe = _sub(id=18, state="R", name="测试", type="电视剧", season=1)
        mediainfo = _mediainfo(
            season_info=[{"season_number": 1, "air_date": "2025-01-01"}],
            first_air_date="2025-01-01",
        )
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "tv_no_download_days": 180,
            "no_download_actions": ["delete_tv"],
        })
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [subscribe]
        plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
        plugin._last_download_date = MagicMock(return_value=None)

        plugin.run_no_download_check()

        plugin._subscribe_oper.delete.assert_called_once_with(18)

    def test_overdue_tv_pause_action_clears_plugin_tasks(self):
        """剧集超期执行暂停后清理关联插件任务。"""
        subscribe = _sub(id=19, state="R", name="测试", type="电视剧", season=1)
        mediainfo = _mediainfo(
            season_info=[{"season_number": 1, "air_date": "2025-01-01"}],
            first_air_date="2025-01-01",
        )
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "tv_no_download_days": 180,
            "no_download_actions": ["pause_tv"],
        })
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [subscribe]
        plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
        plugin._last_download_date = MagicMock(return_value=None)
        plugin._task_manager.clear_tasks = MagicMock()
        plugin._modules["pause_manager"].pause = MagicMock()

        plugin.run_no_download_check()

        plugin._modules["pause_manager"].pause.assert_called_once()
        plugin._task_manager.clear_tasks.assert_called_once_with(19)

    def test_overdue_tv_pause_action_sends_status_notification(self):
        """无下载暂停应发送订阅状态通知。"""
        subscribe = _sub(id=20, state="R", name="测试", type="电视剧", season=1)
        mediainfo = _mediainfo(
            title_year="测试剧 (2025)",
            vote_average=8.5,
            season_info=[{"season_number": 1, "air_date": "2025-01-01"}],
            first_air_date="2025-01-01",
            type=SimpleNamespace(value="电视剧"),
        )
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "notify": True,
            "tv_no_download_days": 180,
            "no_download_actions": ["pause_tv"],
        })
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [subscribe]
        plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
        plugin._last_download_date = MagicMock(return_value=None)
        plugin._modules["pause_manager"].pause = MagicMock()
        plugin.post_message = MagicMock()

        plugin.run_no_download_check()

        plugin.post_message.assert_called_once()
        assert "近" in plugin.post_message.call_args.kwargs["title"]
        assert "已标记暂停" in plugin.post_message.call_args.kwargs["title"]

    def test_overdue_movie_complete_notification_has_no_season_none(self):
        """电影无下载状态通知不应拼出 SNone。"""
        subscribe = _sub(id=21, state="R", name="测试电影", type="电影", season=None)
        mediainfo = _mediainfo(
            title_year="测试电影 (2025)",
            vote_average=7.5,
            release_date="2025-01-01",
            type=SimpleNamespace(value="电影"),
        )
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "notify": True,
            "movie_no_download_days": 180,
            "no_download_actions": ["complete_movie"],
        })
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [subscribe]
        plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
        plugin._last_download_date = MagicMock(return_value=None)
        plugin.post_message = MagicMock()

        plugin.run_no_download_check()

        plugin.post_message.assert_called_once()
        assert "SNone" not in plugin.post_message.call_args.kwargs["title"]
        assert "已标记完成" in plugin.post_message.call_args.kwargs["title"]
