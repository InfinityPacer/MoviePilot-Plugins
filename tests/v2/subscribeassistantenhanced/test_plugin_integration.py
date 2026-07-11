"""端到端集成：插件入口装配 + 事件委托 + 扩展点 smoke（证明集成层真正接通）。"""
import time
import json
from datetime import date, timedelta
from types import SimpleNamespace
from unittest.mock import MagicMock
from pathlib import Path

from packaging.specifiers import SpecifierSet
from packaging.version import Version

from app.schemas.types import MediaType

from subscribeassistantenhanced import SubscribeAssistantEnhanced
from subscribeassistantenhanced.engine.types import CompletionEvidence, CompletionSignal, PauseRecord
from subscribeassistantenhanced.lifecycle import LifecycleResult


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
        manual_total_episode=False,
        note=[],
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
        seasons={},
        first_air_date=None,
        release_date=None,
        type=SimpleNamespace(value="电视剧"),
    )
    defaults.update(kwargs)
    media = SimpleNamespace(**defaults)
    media.to_dict = lambda: {"tmdb_id": media.tmdb_id}
    media.get_message_image = lambda: "poster.jpg"
    return media


def test_release_metadata_requires_main_program_newer_than_2_14_1():
    """插件版本门禁要求高于当前 MoviePilot v2.14.1 主程序版本。"""
    package = json.loads(Path("package.v2.json").read_text(encoding="utf-8"))
    specifier = SpecifierSet(package["SubscribeAssistantEnhanced"]["system_version"])

    assert package["SubscribeAssistantEnhanced"]["system_version"] == ">2.14.1"
    assert Version("2.14.1") not in specifier
    assert Version("2.14.2") in specifier


def test_converter_is_wired():
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    assert plugin._modules.get("converter") is not None


def test_target_satisfied_resolver_is_wired_to_guard_and_events():
    """完成守卫和事件代理必须共用插件级主程序目标满足查询。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})

    guard = plugin._modules["guard"]
    assert guard.resolve_missing_fn.__self__ is plugin
    assert guard.resolve_missing_fn.__func__ is plugin._resolve_subscribe_missing.__func__
    assert plugin._event_proxy._modules["resolve_missing_fn"].__self__ is plugin
    assert plugin._event_proxy._modules["resolve_missing_fn"].__func__ is plugin._resolve_subscribe_missing.__func__


def test_tmdb_episodes_queries_special_season_zero():
    """特别季 S0 是合法 TMDB 季号，必须继续查询季内剧集。"""
    plugin = SubscribeAssistantEnhanced()
    plugin._tmdb_chain = MagicMock()
    plugin._tmdb_chain.tmdb_episodes.return_value = [SimpleNamespace(episode_number=1)]

    episodes = plugin._tmdb_episodes(tmdbid=91097, season=0)

    assert len(episodes) == 1
    plugin._tmdb_chain.tmdb_episodes.assert_called_once_with(
        tmdbid=91097,
        season=0,
        episode_group=None,
    )


def test_resolve_subscribe_missing_preserves_special_season_zero():
    """插件级主程序缺集查询 wrapper 构造 MetaInfo 时必须保留特别季 S0。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    subscribe_chain = MagicMock()
    subscribe_chain.resolve_subscribe_missing.return_value = (True, {})
    plugin._subscribe_chain = subscribe_chain
    sub = _sub(season=0)
    mediainfo = _mediainfo()

    result = plugin._resolve_subscribe_missing(sub, mediainfo)

    assert result == (True, {})
    _, kwargs = subscribe_chain.resolve_subscribe_missing.call_args
    assert kwargs["meta"].begin_season == 0


def test_resolve_subscribe_missing_without_subscribe_chain_fails_closed(monkeypatch):
    """插件未持有主程序订阅链时缺集查询失败关闭，不临时创建不受控链实例。"""
    warnings = []
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    plugin._subscribe_chain = None
    subscribe_chain_cls = MagicMock()
    monkeypatch.setattr("subscribeassistantenhanced.SubscribeChain", subscribe_chain_cls)
    monkeypatch.setattr("subscribeassistantenhanced.logger.warning", warnings.append)

    result = plugin._resolve_subscribe_missing(_sub(), _mediainfo())

    assert result == (False, {})
    subscribe_chain_cls.assert_not_called()
    assert any("目标缺集查询失败" in message and "主程序订阅链未初始化" in message for message in warnings)


def test_recognize_mediainfo_preserves_special_season_zero():
    """订阅识别 MetaInfo 必须保留 S0，避免识别链按默认季处理特别季。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    plugin.chain = MagicMock()
    plugin.chain.recognize_media.return_value = _mediainfo()
    sub = _sub(season=0)

    plugin._recognize_mediainfo(sub)

    _, kwargs = plugin.chain.recognize_media.call_args
    assert kwargs["meta"].begin_season == 0


def test_detect_episode_coverage_preserves_special_season_zero(monkeypatch):
    """媒体库缺集探测必须把 S0 作为明确目标季传给主程序 DownloadChain。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
    download_chain = MagicMock()
    download_chain.get_no_exists_info.return_value = (True, {})
    download_chain_cls = MagicMock(return_value=download_chain)
    monkeypatch.setattr("app.chain.download.DownloadChain", download_chain_cls)
    sub = _sub(season=0)

    existing, missing = plugin._detect_episode_coverage(sub)

    assert existing == list(range(1, 13))
    assert missing == []
    _, kwargs = download_chain.get_no_exists_info.call_args
    assert kwargs["meta"].begin_season == 0
    assert kwargs["totals"] == {0: 12}


def test_episode_to_full_converts_when_current_episodes_covered():
    sub = _sub(id=5, name="X", best_version=1, best_version_full=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_episode_to_full": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
    plugin._resolve_subscribe_missing = MagicMock(return_value=(True, {}))
    conv = plugin._modules["converter"]
    conv.convert_to_full = MagicMock(return_value=True)

    plugin.run_best_version_check()

    conv.convert_to_full.assert_called_once_with(sub, plugin._recognize_mediainfo.return_value)


def test_episode_to_full_uses_target_satisfied_resolver_for_any_downloaded_version():
    """分集洗版巡检按主程序目标满足口径转全集，不要求当前 priority 全部为 100。"""
    sub = _sub(
        id=5,
        name="X",
        best_version=1,
        best_version_full=0,
        lack_episode=1,
        total_episode=3,
        note=[1],
        episode_priority={"2": 80, "3": 99},
    )
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_episode_to_full": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))
    plugin._resolve_subscribe_missing = MagicMock(return_value=(True, {}))
    conv = plugin._modules["converter"]
    conv.convert_to_full = MagicMock(return_value=True)

    plugin.run_best_version_check()

    plugin._resolve_subscribe_missing.assert_called_once_with(
        sub,
        plugin._recognize_mediainfo.return_value,
        best_version_accept_downloaded=True,
    )
    conv.convert_to_full.assert_called_once_with(sub, plugin._recognize_mediainfo.return_value)


def test_episode_to_full_converts_when_main_resolver_reports_target_satisfied():
    """主程序目标满足查询确认分集目标已下载时，分集洗版升级为全集洗版。"""
    sub = _sub(id=5, name="X", best_version=1, best_version_full=0, note=list(range(1, 13)))
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_episode_to_full": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
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
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
    plugin._resolve_subscribe_missing = MagicMock(return_value=(False, {100: {1: [3]}}))
    conv = plugin._modules["converter"]
    conv.convert_to_full = MagicMock(return_value=True)

    plugin.run_best_version_check()

    conv.convert_to_full.assert_not_called()


def test_best_version_check_logs_actionable_recognition_failure(monkeypatch):
    """洗版巡检识别失败时给出订阅上下文和用户下一步。"""
    messages = []
    monkeypatch.setattr("subscribeassistantenhanced.detail", messages.append)
    plugin = SubscribeAssistantEnhanced()
    plugin._config = SimpleNamespace(best_version_type="all")
    sub = _sub(id=42, name="识别失败剧", best_version=1, best_version_full=0,
               tmdbid=100, season=1, type="电视剧")
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=None)
    plugin._modules = {
        "orchestrator": MagicMock(),
        "priority_manager": MagicMock(),
    }

    plugin.run_best_version_check()

    assert any(
        "媒体识别失败" in message
        and "订阅ID：42" in message
        and "TMDB：100" in message
        and "建议检查订阅名称、年份、TMDB ID、媒体类型和季号" in message
        for message in messages
    )


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
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())

    class RelativeNoExistsInfo:
        """模拟主程序按季内相对集号返回缺集范围。"""

        episodes = list(range(1, 68))
        total_episode = 67
        start_episode = 1

    class FakeDownloadChain:
        """避免访问真实媒体库，只返回生产复现场景的缺集结构。"""

        def get_no_exists_info(self, meta, mediainfo, totals=None):
            return False, {100: {22: RelativeNoExistsInfo()}}

    monkeypatch.setattr("app.chain.download.DownloadChain", FakeDownloadChain)
    conv = plugin._modules["converter"]
    conv.convert_to_full = MagicMock(return_value=True)

    plugin.run_best_version_check()

    conv.convert_to_full.assert_not_called()


def test_episode_to_full_skips_movie_best_version_when_target_satisfied():
    """电影洗版即使目标满足也不能进入剧集分集转全集路径。"""
    sub = _sub(
        id=33,
        name="测试电影",
        type=MediaType.MOVIE,
        season=None,
        best_version=1,
        best_version_full=0,
    )
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_episode_to_full": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
    plugin._resolve_subscribe_missing = MagicMock(return_value=(True, []))
    plugin._best_version_overdue = MagicMock(return_value=False)
    conv = plugin._modules["converter"]
    conv.convert_to_full = MagicMock(return_value=True)

    plugin.run_best_version_check()

    conv.convert_to_full.assert_not_called()


def test_best_version_check_marks_overdue_subscription_complete():
    """洗版订阅最近活动超过时限时终止洗版。"""
    now = time.time()
    sub = _sub(id=5, name="X", best_version=1, best_version_full=1)
    mediainfo = _mediainfo()
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_tv_remaining_days": 3})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
    plugin._task_manager.read = MagicMock(side_effect=lambda key: {
        "torrents": {"hash": {"subscribe_id": 5, "time": now - 10 * 86400}},
        "subscribes": {"5": {"best_version_anchor": now - 10 * 86400}},
    }.get(key, {}))
    priority = plugin._modules["priority_manager"]
    priority.mark_complete = MagicMock()
    plugin._notify_subscribe = MagicMock()

    plugin.run_best_version_check()

    priority.mark_complete.assert_called_once_with(sub)
    plugin._notify_subscribe.assert_called_once_with(
        "X S1 洗版超过时限（3天），已标记洗版优先级为完成",
        image="poster.jpg",
    )


def test_best_version_check_uses_movie_remaining_days_for_movie():
    """电影洗版使用电影洗版时限，不受剧集洗版时限影响。"""
    now = time.time()
    sub = _sub(id=5, name="X", type=MediaType.MOVIE, season=None, best_version=1, best_version_full=0)
    mediainfo = _mediainfo()
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "best_version_type": "all",
        "best_version_movie_remaining_days": 3,
        "best_version_tv_remaining_days": 30,
    })
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
    plugin._task_manager.read = MagicMock(side_effect=lambda key: {
        "torrents": {"hash": {"subscribe_id": 5, "time": now - 10 * 86400}},
        "subscribes": {"5": {"best_version_anchor": now - 10 * 86400}},
    }.get(key, {}))
    priority = plugin._modules["priority_manager"]
    priority.mark_complete = MagicMock()

    plugin.run_best_version_check()

    priority.mark_complete.assert_called_once_with(sub)


def test_best_version_check_does_not_expire_tv_episode_best_version():
    """剧集分集洗版按普通分集订阅处理，不适用洗版时限终止。"""
    now = time.time()
    sub = _sub(id=5, name="X", best_version=1, best_version_full=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_tv_remaining_days": 3})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
    plugin._task_manager.read = MagicMock(side_effect=lambda key: {
        "torrents": {"hash": {"subscribe_id": 5, "time": now - 10 * 86400}},
        "subscribes": {"5": {"best_version_anchor": now - 10 * 86400}},
    }.get(key, {}))
    priority = plugin._modules["priority_manager"]
    priority.mark_complete = MagicMock()

    plugin.run_best_version_check()

    priority.mark_complete.assert_not_called()


def test_full_best_version_check_does_not_mark_complete_without_timeout():
    """全集洗版不再由插件巡检按优先级达标主动完成，普通完成交还主程序洗版链路。"""
    sub = _sub(id=5, name="X", best_version=1, best_version_full=1)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_tv_remaining_days": 0})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
    plugin._resolve_subscribe_missing = MagicMock(return_value=(True, []))
    priority = plugin._modules["priority_manager"]
    priority.mark_complete = MagicMock()
    priority.is_complete = MagicMock(return_value=True)

    plugin.run_best_version_check()

    plugin._resolve_subscribe_missing.assert_not_called()
    priority.mark_complete.assert_not_called()


def test_best_version_mode_label_uses_wash_label_for_movie_best_version():
    """电影洗版使用真正洗版标签，不应误标成分集洗版。"""
    assert SubscribeAssistantEnhanced._best_version_mode_label(
        _sub(type=MediaType.MOVIE, best_version=1, best_version_full=0)
    ) == "洗版"


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
    plugin.init_plugin({"best_version_type": "all", "best_version_tv_remaining_days": 0})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
    plugin._task_manager.read = MagicMock(return_value={
        "hash": {"subscribe_id": 5, "time": now - 10 * 86400},
    })
    priority = plugin._modules["priority_manager"]
    priority.mark_complete = MagicMock()

    plugin.run_best_version_check()

    priority.mark_complete.assert_not_called()


def test_best_version_check_keeps_subscription_with_recent_activity():
    """洗版订阅最近活动仍在时限内时继续巡检。"""
    now = time.time()
    sub = _sub(id=5, name="X", best_version=1, best_version_full=1)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "all", "best_version_tv_remaining_days": 3})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
    plugin._task_manager.read = MagicMock(side_effect=lambda key: {
        "torrents": {"hash": {"subscribe_id": 5, "time": now - 86400}},
        "subscribes": {"5": {"best_version_anchor": now - 10 * 86400}},
    }.get(key, {}))
    priority = plugin._modules["priority_manager"]
    priority.mark_complete = MagicMock()

    plugin.run_best_version_check()

    priority.mark_complete.assert_not_called()


def test_get_state_uses_global_enabled():
    """插件总状态由 enabled 决定。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"enabled": False})
    assert plugin.get_state() is False

    enabled_plugin = SubscribeAssistantEnhanced()
    enabled_plugin.init_plugin({"enabled": True, "completion_guard_mode": "off"})
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
    data_store = {
        "subscribes": {
            "7": {
                "state": "P",
                "source": "pending_judge",
                "pending_sources": {"pending_judge": {"reason": "集数不足"}},
            }
        },
        "blocks": {},
    }
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    plugin._modules["pending_state"]._read = plugin._task_manager.read
    plugin._modules["pending_state"]._update = plugin._task_manager.update
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
    judge = plugin._modules["pending_judge"]
    judge.check_exit = MagicMock(return_value=True)
    plugin.run_meta_check()
    judge.check_exit.assert_called_once()


def test_run_meta_check_releases_existing_pending_when_pending_disabled():
    """关闭新增待定后，已有 pending_judge P 仍应走退出复核。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": False, "pending_enhanced_enabled": False})
    sub = _sub(id=9, state="P", name="测试", best_version=0)
    data_store = {
        "subscribes": {
            "9": {
                "state": "P",
                "source": "pending_judge",
                "pending_sources": {"pending_judge": {"reason": "集数不足"}},
            }
        },
        "blocks": {},
    }
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    plugin._modules["pending_state"]._read = plugin._task_manager.read
    plugin._modules["pending_state"]._update = plugin._task_manager.update
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper
    assert plugin._modules["pending_judge"]._state is plugin._modules["pending_state"]
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
    plugin._tmdb_episodes = MagicMock(return_value=[
        SimpleNamespace(episode_number=i, air_date="2026-01-01", episode_type="standard")
        for i in range(1, 13)
    ])
    plugin._modules["pending_judge"]._evidence_pipeline = SimpleNamespace(
        evaluate=MagicMock(return_value=CompletionEvidence(
            primary_signal=CompletionSignal(completed=True, confidence="high")
        ))
    )

    plugin.run_meta_check()

    assert data_store["subscribes"]["9"]["state"] == "R"
    plugin._subscribe_oper.update.assert_called_once()


def test_run_meta_check_calls_pause_when_pre_air_condition_holds():
    """活动订阅命中上映前暂停条件时，run_meta_check 调用 pause_manager.pause。"""
    from subscribeassistantenhanced.engine.types import PauseRecord

    sub = _sub(id=3, state="R", name="X", best_version=0, type="电影",
               season=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=MediaType.MOVIE))

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


def test_run_meta_check_passes_scope_to_airing_checker():
    """周期巡检把 SeasonScope 交给按 note 判定的播出暂停检查。"""
    sub = _sub(id=3, state="R", name="X", best_version=0, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    mediainfo = SimpleNamespace(
        tmdb_id=100,
        type=MediaType.TV,
        next_episode_to_air=None,
        season_info=[],
        first_air_date=None,
    )
    plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
    next_air_date = (date.today() + timedelta(days=7)).isoformat()
    episodes = [
        SimpleNamespace(
            episode_number=88,
            season_number=1,
            air_date=next_air_date,
            episode_type="standard",
        )
    ]
    plugin._tmdb_episodes = MagicMock(return_value=episodes)
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)

    plugin.run_meta_check()

    airing.check_pre_air.assert_called_once_with(sub, mediainfo, episodes=episodes)
    airing.check.assert_called_once_with(
        sub,
        mediainfo,
        next_episode=None,
        latest_episode=None,
        episodes=episodes,
    )


def test_run_meta_check_includes_episode_best_version_subscription():
    """元数据巡检对分集洗版执行按集播出检查。"""
    sub = _sub(
        id=3,
        state="R",
        name="X",
        best_version=1,
        best_version_full=0,
        type="电视剧",
    )
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(
        tmdb_id=100,
        type=MediaType.TV,
        next_episode_to_air=None,
        season_info=[],
        first_air_date=None,
    ))
    plugin._tmdb_episodes = MagicMock(return_value=[])
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)

    plugin.run_meta_check()

    airing.check.assert_called_once()


def test_run_meta_check_delegates_each_subscription_to_lifecycle():
    """元数据巡检入口只负责枚举订阅，单订阅生命周期顺序交给协调器。"""
    subscriptions = [
        _sub(id=1, state="N"),
        _sub(id=2, state="R"),
        _sub(id=3, state="P"),
        _sub(id=4, state="S"),
    ]
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = subscriptions
    lifecycle = MagicMock()
    plugin._modules["lifecycle"] = lifecycle

    plugin.run_meta_check()

    plugin._subscribe_oper.list.assert_called_once_with(state="N,R,P,S")
    assert [
        call.args[0].id
        for call in lifecycle.handle_meta_check_subscription.call_args_list
    ] == [1, 2, 3, 4]


def test_run_site_evidence_scan_refreshes_active_tv_subscriptions():
    """站点证据扫描刷新 P/R 普通剧集和分集洗版证据。"""
    normal = _sub(id=3, state="R", name="普通", best_version=0, type="电视剧")
    pending = _sub(id=4, state="P", name="待定", best_version=0, type="电视剧")
    episode_best = _sub(id=5, state="R", name="分集洗版", best_version=1, best_version_full=0, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "site_total_probe_enabled": True,
        "pause_enhanced_enabled": False,
        "pending_enhanced_enabled": False,
    })
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [normal, pending, episode_best]
    site_evidence = MagicMock()
    plugin._modules["site_evidence"] = site_evidence

    plugin.run_site_evidence_scan()

    assert site_evidence.refresh_subscribe.call_args_list == [
        ((normal,),),
        ((pending,),),
        ((episode_best,),),
    ]


def test_run_site_evidence_scan_scope_filters():
    """站点证据刷新只覆盖 P/R 剧集普通订阅和分集洗版。"""
    eligible = _sub(id=6, state="R", name="普通", best_version=0, type="电视剧")
    pending = _sub(id=7, state="P", name="待定", best_version=0, type="电视剧")
    new_subscribe = _sub(id=8, state="N", name="新增", best_version=0, type="电视剧")
    disabled = _sub(id=9, state="S", name="禁用", best_version=0, type="电视剧")
    movie = _sub(id=10, state="R", name="电影", best_version=0, type="电影")
    full_best = _sub(id=11, state="R", name="全集洗版", best_version=1, best_version_full=1, type="电视剧")
    manual_total = _sub(id=12, state="R", name="手动总集数", best_version=0, type="电视剧", manual_total_episode=True)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "site_total_probe_enabled": True,
        "pause_enhanced_enabled": False,
        "pending_enhanced_enabled": False,
    })
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [
        eligible,
        pending,
        new_subscribe,
        disabled,
        movie,
        full_best,
        manual_total,
    ]
    site_evidence = MagicMock()
    plugin._modules["site_evidence"] = site_evidence

    plugin.run_site_evidence_scan()

    assert site_evidence.refresh_subscribe.call_args_list == [
        ((eligible,),),
        ((pending,),),
    ]


def test_run_meta_check_does_not_refresh_site_evidence():
    """元数据巡检不消费短窗口站点缓存，避免和通用巡检职责重叠。"""
    sub = _sub(id=13, state="R", name="普通", best_version=0, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "site_total_probe_enabled": True,
        "pause_enhanced_enabled": False,
        "pending_enhanced_enabled": False,
    })
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=MediaType.TV))
    site_evidence = MagicMock()
    plugin._modules["site_evidence"] = site_evidence

    plugin.run_meta_check()

    site_evidence.refresh_subscribe.assert_not_called()


def test_run_meta_check_pauses_full_best_version_when_pre_air_condition_holds():
    """全集洗版在元数据巡检中支持上映前暂停。"""
    sub = _sub(id=3, state="R", name="X", best_version=1, best_version_full=1, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    mediainfo = SimpleNamespace(
        tmdb_id=100,
        type=MediaType.TV,
        next_episode_to_air=None,
        season_info=[],
        first_air_date=None,
    )
    plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
    episodes = [SimpleNamespace(episode_number=1, air_date=None)]
    plugin._tmdb_episodes = MagicMock(return_value=episodes)

    record = PauseRecord(reason="pre_air", since=0.0, detail="未上映")
    pause_manager = plugin._modules["pause_manager"]
    pause_manager.pause = MagicMock()
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=record)
    airing.check = MagicMock(return_value=None)
    judge = plugin._modules["pending_judge"]
    judge.should_enter_pending = MagicMock(return_value=(True, "集数不足"))

    plugin.run_meta_check()

    airing.check_pre_air.assert_called_once_with(sub, mediainfo, episodes=episodes)
    pause_manager.pause.assert_called_once_with(sub, record)
    airing.check.assert_not_called()
    judge.should_enter_pending.assert_not_called()


def test_run_meta_check_full_best_version_without_pre_air_skips_pending_and_airing_gap():
    """全集洗版未命中上映前暂停时，不进入待定和播出间隔暂停。"""
    sub = _sub(id=3, state="R", name="X", best_version=1, best_version_full=1, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    mediainfo = SimpleNamespace(
        tmdb_id=100,
        type=MediaType.TV,
        next_episode_to_air=None,
        season_info=[],
        first_air_date="2026-01-01",
    )
    plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
    episodes = [SimpleNamespace(episode_number=1, air_date="2026-01-01")]
    plugin._tmdb_episodes = MagicMock(return_value=episodes)

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.pause = MagicMock()
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=PauseRecord(reason="airing_gap", since=0.0, detail="播出间隔"))
    judge = plugin._modules["pending_judge"]
    judge.should_enter_pending = MagicMock(return_value=(True, "集数不足"))

    plugin.run_meta_check()

    airing.check_pre_air.assert_called_once_with(sub, mediainfo, episodes=episodes)
    airing.check.assert_not_called()
    judge.should_enter_pending.assert_not_called()
    pause_manager.pause.assert_not_called()


def test_run_meta_check_full_best_version_continue_keeps_following_subscriptions():
    """全集洗版跳过按集流程时，只跳过当前订阅，不结束整轮巡检。"""
    full = _sub(id=3, state="R", name="全集", best_version=1, best_version_full=1, type="电视剧")
    normal = _sub(id=4, state="R", name="普通", best_version=0, best_version_full=0, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [full, normal]
    plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper
    data_store = {"subscribes": {}}
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    full_mediainfo = SimpleNamespace(
        tmdb_id=100,
        type=MediaType.TV,
        next_episode_to_air=None,
        season_info=[],
        first_air_date="2026-01-01",
    )
    normal_mediainfo = SimpleNamespace(
        tmdb_id=101,
        type=MediaType.TV,
        next_episode_to_air=None,
        season_info=[],
        first_air_date="2026-01-01",
    )
    plugin._recognize_mediainfo = MagicMock(side_effect=[full_mediainfo, normal_mediainfo])
    episodes = [SimpleNamespace(episode_number=1, air_date="2026-01-01")]
    plugin._tmdb_episodes = MagicMock(return_value=episodes)

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.pause = MagicMock()
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)
    judge = plugin._modules["pending_judge"]
    judge.should_enter_pending = MagicMock(return_value=(True, "集数不足"))
    judge._notify = MagicMock()

    plugin.run_meta_check()

    assert plugin._recognize_mediainfo.call_args_list == [((full,),), ((normal,),)]
    judge.should_enter_pending.assert_called_once_with(normal, normal_mediainfo, episodes)
    task = data_store["subscribes"]["4"]
    assert task["state"] == "P"
    assert task["source"] == "pending_judge"
    assert plugin._subscribe_oper.update.call_args.args[0] == normal.id
    assert plugin._subscribe_oper.update.call_args.args[1].get("state") == "P"


def test_run_meta_check_resumes_full_best_version_pre_air_pause_when_condition_clears():
    """全集洗版的上映前暂停记录解除后可自动恢复。"""
    sub = _sub(id=3, state="S", name="X", best_version=1, best_version_full=1, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    mediainfo = SimpleNamespace(
        tmdb_id=100,
        type=MediaType.TV,
        next_episode_to_air=None,
        season_info=[],
        first_air_date="2026-01-01",
    )
    plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
    episodes = [SimpleNamespace(episode_number=1, air_date="2026-01-01")]
    plugin._tmdb_episodes = MagicMock(return_value=episodes)

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.get_pause_record = MagicMock(
        return_value=PauseRecord(reason="pre_air", since=0.0, detail="未上映")
    )
    pause_manager.resume = MagicMock()
    pause_manager.pause = MagicMock()
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=PauseRecord(reason="airing_gap", since=0.0, detail="播出间隔"))
    judge = plugin._modules["pending_judge"]
    judge.should_enter_pending = MagicMock(return_value=(True, "集数不足"))

    plugin.run_meta_check()

    pause_manager.resume.assert_called_once_with(sub)
    pause_manager.pause.assert_not_called()
    airing.check.assert_not_called()
    judge.should_enter_pending.assert_not_called()


def test_run_meta_check_full_best_version_does_not_resume_airing_gap_record():
    """全集洗版不复核播出间隔暂停记录。"""
    sub = _sub(id=3, state="S", name="X", best_version=1, best_version_full=1, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    mediainfo = SimpleNamespace(
        tmdb_id=100,
        type=MediaType.TV,
        next_episode_to_air=None,
        season_info=[],
        first_air_date="2026-01-01",
    )
    plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
    plugin._tmdb_episodes = MagicMock(return_value=[SimpleNamespace(episode_number=1, air_date="2026-01-01")])

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.get_pause_record = MagicMock(
        return_value=PauseRecord(reason="airing_gap", since=0.0, detail="播出间隔")
    )
    pause_manager.resume = MagicMock()
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)
    airing.should_resume_airing_gap = MagicMock(return_value=True)

    plugin.run_meta_check()

    pause_manager.resume.assert_not_called()
    airing.check.assert_not_called()
    airing.should_resume_airing_gap.assert_not_called()


def test_run_meta_check_skips_airing_pause_for_new_subscription():
    """N 状态订阅仍在首次搜索阶段，元数据巡检不应用播出暂停冻结搜索。"""
    from subscribeassistantenhanced.engine.types import PauseRecord

    sub = _sub(id=13, state="N", name="X", best_version=0, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.pause = MagicMock()
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=PauseRecord(reason="pre_air", since=0.0, detail="等待开播"))
    airing.check = MagicMock(return_value=PauseRecord(reason="airing_gap", since=0.0, detail="播出间隔"))

    plugin.run_meta_check()

    airing.check_pre_air.assert_not_called()
    airing.check.assert_not_called()
    pause_manager.pause.assert_not_called()


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


def test_run_meta_check_keeps_airing_gap_when_current_check_is_inconclusive():
    """airing_gap 暂停没有明确恢复证据时，元数据巡检应保留暂停记录。"""
    sub = _sub(id=3, state="S", name="X", best_version=0, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(
        tmdb_id=100,
        type=MediaType.TV,
        tmdb_info={},
        next_episode_to_air=None,
        season_info=[],
        first_air_date=None,
    ))
    plugin._tmdb_episodes = MagicMock(return_value=[])

    pause_manager = plugin._modules["pause_manager"]
    next_air_date = (date.today() + timedelta(days=7)).isoformat()
    pause_manager.get_pause_record = MagicMock(
        return_value=PauseRecord(reason="airing_gap", since=0.0, detail=f"下一集 {next_air_date}，距今 7 天"))
    pause_manager.resume = MagicMock()
    pause_manager.pause = MagicMock()
    pause_manager.clear_pause_record = MagicMock()

    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)

    plugin.run_meta_check()

    pause_manager.resume.assert_not_called()
    pause_manager.pause.assert_not_called()
    pause_manager.clear_pause_record.assert_not_called()


def test_run_meta_check_keeps_airing_pause_before_pending_when_pre_air_clears():
    """上映前条件解除但播出暂停仍有效时，不应被恢复或改写为待定。"""
    sub = _sub(id=3, state="S", name="X", best_version=0, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(
        tmdb_id=100,
        type=MediaType.TV,
        tmdb_info={},
        next_episode_to_air=None,
        season_info=[],
        first_air_date=None,
    ))
    plugin._tmdb_episodes = MagicMock(return_value=[])

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.get_pause_record = MagicMock(
        return_value=PauseRecord(reason="airing_gap", since=0.0, detail="下一集日期：2026-07-01"))
    pause_manager.resume = MagicMock()
    pause_manager.pause = MagicMock()
    pause_manager.clear_pause_record = MagicMock()

    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)
    airing.should_resume_airing_gap = MagicMock(return_value=False)

    pending_judge = plugin._modules["pending_judge"]
    pending_judge.should_enter_pending = MagicMock(return_value=(True, "集数不足"))
    pending_judge.mark_pending = MagicMock()

    plugin.run_meta_check()

    airing.should_resume_airing_gap.assert_called_once()
    pause_manager.resume.assert_not_called()
    pause_manager.pause.assert_not_called()
    pending_judge.should_enter_pending.assert_not_called()
    pending_judge.mark_pending.assert_not_called()


def test_run_meta_check_updates_pre_air_record_to_airing_gap_while_paused():
    """S 态订阅命中更具体的播出暂停时，应刷新原因并跳过待定。"""
    sub = _sub(id=3, state="S", name="X", best_version=0, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(
        tmdb_id=100,
        type=MediaType.TV,
        tmdb_info={},
        next_episode_to_air=None,
        season_info=[],
        first_air_date=None,
    ))
    plugin._tmdb_episodes = MagicMock(return_value=[])

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.get_pause_record = MagicMock(
        return_value=PauseRecord(reason="pre_air", since=0.0, detail="开播日期未知"))
    pause_manager.pause = MagicMock()
    pause_manager.resume = MagicMock()

    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    record = PauseRecord(reason="airing_gap", since=0.0, detail="下一集日期：2026-07-01")
    airing.check = MagicMock(return_value=record)

    pending_judge = plugin._modules["pending_judge"]
    pending_judge.should_enter_pending = MagicMock(return_value=(True, "集数不足"))
    pending_judge.mark_pending = MagicMock()

    plugin.run_meta_check()

    pause_manager.pause.assert_called_once_with(sub, record, notify=False)
    pause_manager.resume.assert_not_called()
    pending_judge.should_enter_pending.assert_not_called()
    pending_judge.mark_pending.assert_not_called()


def test_run_meta_check_silently_refreshes_pre_air_record_while_paused():
    """S 态订阅继续命中上映前暂停时，只刷新归因，不重复发送暂停通知。"""
    sub = _sub(id=3, state="S", name="X", best_version=0, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(
        tmdb_id=100,
        type=MediaType.TV,
        tmdb_info={},
        next_episode_to_air=None,
        season_info=[],
        first_air_date=None,
    ))
    plugin._tmdb_episodes = MagicMock(return_value=[])

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.get_pause_record = MagicMock(
        return_value=PauseRecord(reason="pre_air", since=0.0, detail="旧原因"))
    pause_manager.pause = MagicMock()
    pause_manager.resume = MagicMock()

    airing = plugin._modules["airing_checker"]
    record = PauseRecord(reason="pre_air", since=0.0, detail="开播日期未知")
    airing.check_pre_air = MagicMock(return_value=record)
    airing.check = MagicMock()

    pending_judge = plugin._modules["pending_judge"]
    pending_judge.should_enter_pending = MagicMock(return_value=(True, "集数不足"))
    pending_judge.mark_pending = MagicMock()

    plugin.run_meta_check()

    pause_manager.pause.assert_called_once_with(sub, record, notify=False)
    pause_manager.resume.assert_not_called()
    airing.check.assert_not_called()
    pending_judge.should_enter_pending.assert_not_called()
    pending_judge.mark_pending.assert_not_called()


def test_run_meta_check_silently_refreshes_full_best_version_pre_air_record():
    """全集洗版订阅继续命中上映前暂停时，也只静默刷新插件归因。"""
    sub = _sub(id=3, state="S", name="X", best_version=1, best_version_full=1, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(
        tmdb_id=100,
        type=MediaType.TV,
        tmdb_info={},
        next_episode_to_air=None,
        season_info=[],
        first_air_date=None,
    ))
    plugin._tmdb_episodes = MagicMock(return_value=[])

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.get_pause_record = MagicMock(
        return_value=PauseRecord(reason="pre_air", since=0.0, detail="旧原因"))
    pause_manager.pause = MagicMock()
    pause_manager.resume = MagicMock()

    record = PauseRecord(reason="pre_air", since=0.0, detail="开播日期未知")
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=record)
    airing.check = MagicMock()

    pending_judge = plugin._modules["pending_judge"]
    pending_judge.should_enter_pending = MagicMock()
    pending_judge.mark_pending = MagicMock()

    plugin.run_meta_check()

    pause_manager.pause.assert_called_once_with(sub, record, notify=False)
    pause_manager.resume.assert_not_called()
    airing.check.assert_not_called()
    pending_judge.should_enter_pending.assert_not_called()
    pending_judge.mark_pending.assert_not_called()


def test_run_meta_check_does_not_adopt_manual_pause_when_pause_condition_holds():
    """无插件暂停记录的 S 态订阅即使命中暂停条件，也不应被插件接管归因。"""
    sub = _sub(id=3, state="S", name="X", best_version=0, type="电影", season=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=MediaType.MOVIE))

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.get_pause_record = MagicMock(return_value=None)
    pause_manager.pause = MagicMock()
    pause_manager.resume = MagicMock()

    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(
        return_value=PauseRecord(reason="pre_air", since=0.0, detail="未上映"))

    plugin.run_meta_check()

    pause_manager.pause.assert_not_called()
    pause_manager.resume.assert_not_called()


def test_run_meta_check_does_not_resume_manual_pause_without_plugin_record():
    """无插件暂停记录的 S 态订阅属于外部暂停，元数据巡检不得恢复。"""
    sub = _sub(id=3, state="S", name="X", best_version=0, type="电影", season=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(
        tmdb_id=100,
        type=SimpleNamespace(value="电影"),
        release_date="2026-01-01",
    ))

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.get_pause_record = MagicMock(return_value=None)
    pause_manager.resume = MagicMock()
    pause_manager.pause = MagicMock()
    pause_manager.clear_pause_record = MagicMock()

    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)

    plugin.run_meta_check()

    pause_manager.resume.assert_not_called()
    pause_manager.pause.assert_not_called()
    pause_manager.clear_pause_record.assert_not_called()


def test_run_meta_check_keeps_manual_s_even_with_pending_record():
    """手工 S 优先级最高；即使残留待定记录存在，元数据巡检也不能恢复或重置为 P。"""
    sub = _sub(id=3, state="S", name="X", best_version=0, type="电影", season=0)
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    data_store = {
        "subscribes": {
            "3": {
                "state": "P",
                "source": "pending_judge",
                "pending_sources": {"pending_judge": {"reason": "集数不足"}},
            }
        }
    }
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    plugin._modules["pending_state"]._read = plugin._task_manager.read
    plugin._modules["pending_state"]._update = plugin._task_manager.update
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(
        tmdb_id=100,
        type=SimpleNamespace(value="电影"),
        release_date="2026-01-01",
    ))

    pause_manager = plugin._modules["pause_manager"]
    pause_manager.get_pause_record = MagicMock(return_value=None)
    pause_manager.resume = MagicMock()
    pause_manager.pause = MagicMock()
    pause_manager.clear_pause_record = MagicMock()

    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)
    judge = plugin._modules["pending_judge"]
    judge.check_exit = MagicMock()
    judge.mark_pending = MagicMock()

    plugin.run_meta_check()

    plugin._subscribe_oper.update.assert_not_called()
    pause_manager.resume.assert_not_called()
    pause_manager.pause.assert_not_called()
    pause_manager.clear_pause_record.assert_not_called()
    judge.check_exit.assert_not_called()
    judge.mark_pending.assert_not_called()


def test_run_meta_check_queries_paused_airing_subscriptions_for_resume():
    """元数据巡检必须扫描 S 态上映/播出暂停订阅，否则条件解除后无法自动恢复。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = []

    plugin.run_meta_check()

    plugin._subscribe_oper.list.assert_called_once()
    assert "S" in plugin._subscribe_oper.list.call_args.kwargs["state"]


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
    """活动订阅未命中暂停但 pending 条件成立时，应通过生命周期进入待定状态。"""
    sub = _sub(id=4, state="R", name="X", best_version=0, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper
    data_store = {"subscribes": {}}
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))
    plugin._tmdb_episodes = MagicMock(return_value=[])

    # 暂停检查器均返回 None（不暂停）；airing_checker 存在于 _modules
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)

    judge = plugin._modules["pending_judge"]
    judge.should_enter_pending = MagicMock(return_value=(True, "集数不足"))
    judge._notify = MagicMock()

    plugin.run_meta_check()

    task = data_store["subscribes"]["4"]
    assert task["state"] == "P"
    assert task["source"] == "pending_judge"
    assert task["reason"] == "集数不足"
    assert plugin._subscribe_oper.update.call_args.args[0] == sub.id
    assert plugin._subscribe_oper.update.call_args.args[1].get("state") == "P"


def test_run_meta_check_new_pending_schedules_initial_search_before_pending():
    """元数据巡检将新增订阅置为待定前，应先安排单订阅搜索。"""
    sub = _sub(id=4, state="N", name="X", best_version=0, type="电视剧")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper
    data_store = {"subscribes": {}}
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, type=None))
    plugin._tmdb_episodes = MagicMock(return_value=[])

    call_order = []
    plugin._schedule_initial_pending_search = MagicMock(side_effect=lambda _sub: call_order.append("search"))
    plugin._subscribe_oper.update.side_effect = (
        lambda _sid, payload: call_order.append("pending") if payload.get("state") == "P" else None
    )

    judge = plugin._modules["pending_judge"]
    judge.should_enter_pending = MagicMock(return_value=(True, "集数不足"))
    judge._notify = MagicMock()

    plugin.run_meta_check()

    plugin._schedule_initial_pending_search.assert_called_once_with(sub)
    task = data_store["subscribes"]["4"]
    assert task["state"] == "P"
    assert task["source"] == "pending_judge"
    assert task["reason"] == "集数不足"
    assert call_order == ["search", "pending"]


def test_run_meta_check_check_exit_called_for_p_state_sub():
    """P 状态订阅在巡检中仍先调用 check_exit。"""
    sub = _sub(id=7, state="P", name="X", best_version=0)
    data_store = {
        "subscribes": {
            "7": {
                "state": "P",
                "source": "pending_judge",
                "pending_sources": {"pending_judge": {"reason": "集数不足"}},
            }
        },
        "blocks": {},
    }
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    plugin._modules["pending_state"]._read = plugin._task_manager.read
    plugin._modules["pending_state"]._update = plugin._task_manager.update
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())

    judge = plugin._modules["pending_judge"]
    judge.check_exit = MagicMock(return_value=False)
    judge.should_enter_pending = MagicMock(return_value=(False, ""))
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=None)
    airing.check = MagicMock(return_value=None)
    plugin._tmdb_episodes = MagicMock(return_value=[])

    plugin.run_meta_check()

    judge.check_exit.assert_called_once()


def test_run_meta_check_p_state_allows_pre_air_pause_to_override_pending():
    """插件暂停优先级高于待定，P 状态命中上映暂停时应覆盖为 S。"""
    from subscribeassistantenhanced.engine.types import PauseRecord

    sub = _sub(id=7, state="P", name="X", best_version=0)
    data_store = {
        "subscribes": {
            "7": {
                "state": "P",
                "source": "pending_judge",
                "pending_sources": {"pending_judge": {"reason": "集数不足"}},
            }
        }
    }
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True, "notify": False})
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    plugin._modules["pending_state"]._read = plugin._task_manager.read
    plugin._modules["pending_state"]._update = plugin._task_manager.update
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100, title_year="X (2026)", type=MediaType.MOVIE))
    plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper

    judge = plugin._modules["pending_judge"]
    judge.check_exit = MagicMock(return_value=False)
    judge.should_enter_pending = MagicMock(return_value=(False, ""))
    pause_manager = plugin._modules["pause_manager"]
    pause_manager._read = plugin._task_manager.read
    pause_manager._update = plugin._task_manager.update
    pause_manager._subscribe_oper = plugin._subscribe_oper
    pause_manager._notify = None
    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(
        return_value=PauseRecord(reason="pre_air", since=0.0, detail="未上映")
    )

    plugin.run_meta_check()

    judge.check_exit.assert_called_once()
    updates = [call.args[1]["state"] for call in plugin._subscribe_oper.update.call_args_list]
    assert updates == ["S"]
    task = data_store["subscribes"]["7"]
    assert task["state"] == "S"
    assert task["pending_sources"] == {}
    assert task["pause_reason"] == "pre_air"


def test_run_all_checks_skips_verify_when_disabled():
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"enabled": True})
    mocks = {}
    for name in ("run_meta_check", "run_download_timeout_check", "run_best_version_check",
                 "run_completion_verify", "run_common_check"):
        mocks[name] = MagicMock()
        setattr(plugin, name, mocks[name])
    plugin.run_all_checks()
    for name in ("run_meta_check", "run_download_timeout_check", "run_best_version_check", "run_common_check"):
        mocks[name].assert_called_once()
    mocks["run_completion_verify"].assert_not_called()


def test_run_all_checks_invokes_verify_when_enabled():
    """立即运行一次遵守自动纠错开关，开启时才执行完成后验证。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"enabled": True, "verify_enabled": True})
    plugin.run_meta_check = MagicMock()
    plugin.run_download_timeout_check = MagicMock()
    plugin.run_best_version_check = MagicMock()
    plugin.run_completion_verify = MagicMock()
    plugin.run_common_check = MagicMock()

    plugin.run_all_checks()

    plugin.run_completion_verify.assert_called_once()


def test_run_all_checks_runs_pending_release_as_lifecycle_task(monkeypatch):
    """立即巡检必须执行待定释放生命周期任务，不受其他可选域开关影响。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "enabled": True,
        "verify_enabled": False,
        "pending_enhanced_enabled": False,
        "download_monitor_enabled": False,
        "best_version_type": "no",
    })
    sub = _sub(id=9, state="P", name="测试", best_version=0, username="user")
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = []
    plugin._subscribe_oper.get.return_value = sub
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
    task_store = {
        "subscribes": {
            "9": {
                "state": "P",
                "source": "guard_veto",
                "pending_sources": {"guard_veto": {"reason": "未完结"}},
            }
        },
        "blocks": {"9": {"blocked_at": 0}},
    }
    plugin.get_data = MagicMock(side_effect=lambda key: task_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: task_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data

    def update_task(key, updater):
        data = task_store.get(key, {})
        task_store[key] = updater(data)
        return task_store[key]

    plugin._task_manager.update = MagicMock(side_effect=update_task)
    plugin._modules["pending_state"]._read = plugin._task_manager.read
    plugin._modules["pending_state"]._update = plugin._task_manager.update
    plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper
    timeout_manager = MagicMock()
    timeout_manager.clear_observation.side_effect = lambda sid: task_store["blocks"].pop(str(sid), None)
    plugin._modules["timeout_manager"] = timeout_manager
    plugin.post_message = MagicMock()
    plugin.run_pending_release = MagicMock(wraps=plugin.run_pending_release)

    plugin.run_all_checks()

    plugin.run_pending_release.assert_called_once()
    assert task_store["subscribes"]["9"]["state"] == "P"
    timeout_manager.clear_observation.assert_not_called()


def test_run_common_check_runs_enabled_subtasks():
    """通用巡检按域开关执行任务，并始终清理两个生命周期存储。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"download_monitor_enabled": True})
    plugin.run_pending_release = MagicMock()
    plugin.run_pending_state_reconcile = MagicMock()
    plugin.run_no_download_check = MagicMock()
    plugin.run_paused_probe_check = MagicMock()
    plugin.run_site_evidence_scan = MagicMock()
    plugin.run_deletes_cleanup = MagicMock()
    plugin.run_completion_snapshot_cleanup = MagicMock()
    plugin.run_subscription_cleanup_expired = MagicMock()

    plugin.run_common_check()

    plugin.run_pending_release.assert_called_once()
    plugin.run_pending_state_reconcile.assert_called_once()
    plugin.run_no_download_check.assert_called_once()
    plugin.run_paused_probe_check.assert_called_once()
    plugin.run_site_evidence_scan.assert_called_once()
    plugin.run_deletes_cleanup.assert_called_once()
    plugin.run_completion_snapshot_cleanup.assert_called_once()
    plugin.run_subscription_cleanup_expired.assert_called_once()


def test_run_common_check_isolates_subtask_failures():
    """一个通用巡检子任务失败时，后续子任务仍继续执行。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"download_monitor_enabled": True})
    plugin.run_pending_release = MagicMock(side_effect=RuntimeError("pending failed"))
    plugin.run_pending_state_reconcile = MagicMock()
    plugin.run_no_download_check = MagicMock()
    plugin.run_paused_probe_check = MagicMock()
    plugin.run_site_evidence_scan = MagicMock()
    plugin.run_deletes_cleanup = MagicMock()
    plugin.run_completion_snapshot_cleanup = MagicMock()
    plugin.run_subscription_cleanup_expired = MagicMock()

    plugin.run_common_check()

    plugin.run_pending_state_reconcile.assert_called_once()
    plugin.run_no_download_check.assert_called_once()
    plugin.run_paused_probe_check.assert_called_once()
    plugin.run_site_evidence_scan.assert_called_once()
    plugin.run_deletes_cleanup.assert_called_once()
    plugin.run_completion_snapshot_cleanup.assert_called_once()
    plugin.run_subscription_cleanup_expired.assert_called_once()


def test_run_common_check_respects_domain_switches():
    """关闭可选域后，生命周期存储清理仍必须执行。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"download_monitor_enabled": False})
    plugin.run_pending_release = MagicMock()
    plugin.run_pending_state_reconcile = MagicMock()
    plugin.run_no_download_check = MagicMock()
    plugin.run_paused_probe_check = MagicMock()
    plugin.run_site_evidence_scan = MagicMock()
    plugin.run_deletes_cleanup = MagicMock()
    plugin.run_completion_snapshot_cleanup = MagicMock()
    plugin.run_subscription_cleanup_expired = MagicMock()

    plugin.run_common_check()

    plugin.run_pending_release.assert_called_once()
    plugin.run_pending_state_reconcile.assert_called_once()
    plugin.run_no_download_check.assert_called_once()
    plugin.run_paused_probe_check.assert_called_once()
    plugin.run_site_evidence_scan.assert_called_once()
    plugin.run_deletes_cleanup.assert_not_called()
    plugin.run_completion_snapshot_cleanup.assert_called_once()
    plugin.run_subscription_cleanup_expired.assert_called_once()


def test_onlyonce_registers_one_shot_and_resets_flag():
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()
    plugin.init_plugin({"enabled": True, "onlyonce": True})
    assert plugin._onlyonce is True
    ids = {s["id"] for s in plugin.get_service()}
    assert "SubscribeAssistantEnhanced_onlyonce" in ids
    plugin.update_config.assert_called()


def test_reset_task_restores_plugin_owned_p_and_s_before_clearing_data(monkeypatch):
    """插件内重置数据前必须恢复增强版持有的 P/S 状态。"""
    pending_sub = _sub(id=7, state="P")
    paused_sub = _sub(id=8, state="S")
    manual_paused_sub = _sub(id=9, state="S")
    auto_user_paused_sub = _sub(id=10, state="S")
    subscribe_oper = MagicMock()

    def list_subscribes(*_args, **kwargs):
        state = kwargs.get("state", "")
        result = []
        if "P" in state:
            result.append(pending_sub)
        if "S" in state:
            result.extend([paused_sub, manual_paused_sub, auto_user_paused_sub])
        return result

    subscribe_oper.list.side_effect = list_subscribes
    monkeypatch.setattr("subscribeassistantenhanced.SubscribeOper", MagicMock(return_value=subscribe_oper))

    data_store = {
        "subscribes": {
            "7": {
                "state": "P",
                "source": "pending_judge",
                "pending_sources": {"pending_judge": {"reason": "集数不足"}},
            },
            "8": {
                "pause_reason": "airing_gap",
                "pause_since": 1.0,
                "pause_detail": "下一集 2026-06-21",
            },
            "10": {
                "pause_reason": "auto_user",
                "pause_since": 1.0,
                "pause_detail": "用户 A 的订阅自动暂停",
            },
        }
    }
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))

    plugin.init_plugin({"reset_task": True})

    updates = {call.args[0]: call.args[1]["state"] for call in subscribe_oper.update.call_args_list}
    assert updates == {7: "R", 8: "R"}
    cleared = {c.args[0] for c in plugin.save_data.call_args_list}
    assert {
        "subscribes", "torrents", "blocks", "releases", "snapshots",
        "deletes", "volatility", "site_evidence",
    } <= cleared
    plugin.update_config.assert_called()


def test_pending_state_reconcile_restores_owned_p_without_sources():
    """插件记录仍声明 P 但已无任何来源时，通用巡检应恢复订阅。"""
    sub = _sub(id=7, state="P")
    data_store = {
        "subscribes": {
            "7": {
                "state": "P",
                "source": None,
                "pending_sources": {},
                "download_pending": {},
            }
        },
        "blocks": {},
    }
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper

    plugin.run_pending_state_reconcile()

    plugin._subscribe_oper.update.assert_called_once()
    assert plugin._subscribe_oper.update.call_args.args[1]["state"] == "R"
    assert data_store["subscribes"]["7"]["state"] == "R"


def test_pending_state_reconcile_delegates_each_p_subscription_to_lifecycle():
    """待定状态一致性入口只枚举 P 订阅，恢复策略由生命周期协调器维护。"""
    sub = _sub(id=7, state="P")
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [sub]
    lifecycle = MagicMock()
    plugin._modules["lifecycle"] = lifecycle
    pending_state = plugin._modules["pending_state"]
    pending_state.reconcile_orphaned = MagicMock(return_value=True)

    plugin.run_pending_state_reconcile()

    lifecycle.reconcile_pending.assert_called_once_with(
        sub,
        reason="待定状态一致性检查",
    )
    pending_state.reconcile_orphaned.assert_not_called()


def test_pending_state_reconcile_restores_orphan_observation_and_keeps_active_guard_source():
    """孤儿观察记录不阻止 P 恢复；活跃 guard_veto 来源仍保持 P。"""
    unowned = _sub(id=7, state="P")
    orphan_observation = _sub(id=8, state="P")
    active_guard = _sub(id=9, state="P")
    data_store = {
        "subscribes": {
            "8": {
                "state": "P",
                "source": None,
                "pending_sources": {},
            },
            "9": {
                "state": "P",
                "source": "guard_veto",
                "pending_sources": {"guard_veto": {"reason": "未完结"}},
            }
        },
        "blocks": {
            "8": {"reason": "guard_veto"},
            "9": {"reason": "guard_veto"},
        },
        "releases": {
            "8": {"signals": ["I:all_aired"]},
            "9": {"signals": ["I:all_aired"]},
        },
    }
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [unowned, orphan_observation, active_guard]
    plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper

    plugin.run_pending_state_reconcile()

    updated_ids = [call.args[0] for call in plugin._subscribe_oper.update.call_args_list]
    assert updated_ids == [7, 8]
    assert "7" in data_store["subscribes"]
    assert data_store["subscribes"]["7"]["state"] == "R"
    assert data_store["subscribes"]["8"]["state"] == "R"
    assert data_store["subscribes"]["9"]["state"] == "P"
    assert "8" not in data_store.get("blocks", {})
    assert "8" not in data_store.get("releases", {})
    assert "9" in data_store.get("blocks", {})
    assert "9" in data_store.get("releases", {})


def test_external_plugin_data_reset_restores_p_but_keeps_s_untouched():
    """主程序直接清空插件数据后，P 可自动恢复；S 因无归属证据按手工暂停保留。"""
    pending = _sub(id=7, state="P")
    paused = _sub(id=8, state="S")
    data_store = {"subscribes": {}, "blocks": {}}
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.side_effect = lambda **kwargs: [pending] if kwargs.get("state") == "P" else [paused]
    plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper

    plugin.run_pending_state_reconcile()
    plugin.run_meta_check()

    plugin._subscribe_oper.update.assert_called_once()
    assert plugin._subscribe_oper.update.call_args.args[0] == 7
    assert plugin._subscribe_oper.update.call_args.args[1]["state"] == "R"


def test_run_meta_check_restores_unowned_p_before_pre_air_pause():
    """元数据巡检遇到无活跃待定来源的 P 时先恢复，并清理孤儿观察状态。"""
    pending = _sub(id=7, state="P", type="电影", season=0)
    data_store = {
        "subscribes": {},
        "blocks": {"7": {"reason": "guard_veto"}},
        "releases": {"7": {"signals": ["I:all_aired"]}},
    }
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": True})
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [pending]
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo(type=SimpleNamespace(value="电影")))
    plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper
    plugin._modules["pending_state"]._read = plugin._task_manager.read
    plugin._modules["pending_state"]._update = plugin._task_manager.update
    plugin._modules["download_monitor"].has_active_downloads = MagicMock(return_value=False)

    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=PauseRecord(reason="pre_air", since=0.0, detail="未上映"))
    pause_manager = plugin._modules["pause_manager"]
    pause_manager.pause = MagicMock()

    plugin.run_meta_check()

    plugin._subscribe_oper.update.assert_called_once()
    assert plugin._subscribe_oper.update.call_args.args[0] == 7
    assert plugin._subscribe_oper.update.call_args.args[1]["state"] == "R"
    assert "7" not in data_store.get("blocks", {})
    assert "7" not in data_store.get("releases", {})
    pause_manager.pause.assert_not_called()
    plugin._recognize_mediainfo.assert_not_called()


def test_run_meta_check_restores_unowned_p_when_pending_disabled():
    """无记录 P 恢复是状态一致性修复，不受自动待定开关影响。"""
    pending = _sub(id=7, state="P", type="电影", season=0)
    data_store = {"subscribes": {}, "blocks": {}}
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"pause_enhanced_enabled": True, "pending_enhanced_enabled": False})
    plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
    plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
    plugin._task_manager._get = plugin.get_data
    plugin._task_manager._save = plugin.save_data
    plugin._subscribe_oper = MagicMock()
    plugin._subscribe_oper.list.return_value = [pending]
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo(type=SimpleNamespace(value="电影")))
    plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper
    plugin._modules["pending_state"]._read = plugin._task_manager.read
    plugin._modules["pending_state"]._update = plugin._task_manager.update
    plugin._modules["download_monitor"].has_active_downloads = MagicMock(return_value=False)

    airing = plugin._modules["airing_checker"]
    airing.check_pre_air = MagicMock(return_value=PauseRecord(reason="pre_air", since=0.0, detail="未上映"))
    pause_manager = plugin._modules["pause_manager"]
    pause_manager.pause = MagicMock()

    plugin.run_meta_check()

    plugin._subscribe_oper.update.assert_called_once()
    assert plugin._subscribe_oper.update.call_args.args[1]["state"] == "R"
    pause_manager.pause.assert_not_called()
    plugin._recognize_mediainfo.assert_not_called()


def test_backfill_best_version_now_scans_existing_subscriptions_and_resets_flag(monkeypatch):
    """立即回填会扫描存量洗版订阅，并在执行后关闭一次性标志。"""
    sub = _sub(id=5, name="X", best_version=1, best_version_full=0, start_episode=2, note=[1, 2, 3])
    subscribe_oper = MagicMock()
    subscribe_oper.list.return_value = [sub]
    priority_manager = MagicMock()
    priority_manager.can_backfill.return_value = True
    monkeypatch.setattr("subscribeassistantenhanced.SubscribeOper", MagicMock(return_value=subscribe_oper))
    monkeypatch.setattr("subscribeassistantenhanced.PriorityManager", MagicMock(return_value=priority_manager))
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()
    plugin.post_message = MagicMock()
    plugin._detect_existing_episodes = MagicMock(return_value=[2, 3])

    plugin.init_plugin({"backfill_best_version_now": True})

    priority_manager.backfill_existing.assert_called_once_with(
        sub, [1, 2, 3], scene="plugin_backfill<订阅助手（增强版）>"
    )
    plugin.post_message.assert_called_once()
    assert plugin.post_message.call_args.kwargs["title"] == "洗版订阅下载事实回填"
    assert "扫描 1 个订阅" in plugin.post_message.call_args.kwargs["text"]
    assert "成功回填 1 个" in plugin.post_message.call_args.kwargs["text"]
    assert "累计补写 3 集" in plugin.post_message.call_args.kwargs["text"]
    plugin.update_config.assert_called_once()
    assert plugin.update_config.call_args.args[0]["backfill_best_version_now"] is False


def test_status_notification_uses_ordered_single_line_fields(monkeypatch):
    """状态类订阅通知按评分、用户、原因顺序输出单行正文，并带订阅卡片图片。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"notify": True})
    plugin.post_message = MagicMock()
    plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())

    plugin._send_subscribe_status_notification(
        _sub(username="tester"),
        "上映满足订阅暂停，已标记暂停",
        detail="暂未到订阅窗口",
    )

    kwargs = plugin.post_message.call_args.kwargs
    assert kwargs["title"] == "测试 (2026) S1 上映满足订阅暂停，已标记暂停"
    assert kwargs["text"] == "评分：8.0，用户：tester，原因：暂未到订阅窗口"
    assert kwargs["image"] == "poster.jpg"


def test_no_download_notification_does_not_repeat_title_action():
    """无下载通知标题已包含处理结果，正文只保留判断依据。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"notify": True, "tv_no_download_days": 30})
    plugin.post_message = MagicMock()

    plugin._send_no_download_notification(
        _sub(username="tester"),
        _mediainfo(season_info=[{"season_number": 1, "air_date": "2026-01-01"}], first_air_date="2026-01-01"),
        "pause",
        reason="开播日期：2026-01-01，无下载截止日：2026-01-31，已超过 10 天",
    )

    kwargs = plugin.post_message.call_args.kwargs
    assert kwargs["title"] == "测试 (2026) S1 近 30 天未有下载记录，已标记暂停"
    assert kwargs["text"] == "评分：8.0，用户：tester，原因：开播日期：2026-01-01，无下载截止日：2026-01-31，已超过 10 天"
    assert "处理：" not in kwargs["text"]


def test_diagnostic_notification_uses_ordered_multiline_fields():
    """诊断类订阅通知按统一字段顺序输出多行正文，缺失字段不生成空行。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"notify": True})
    plugin.post_message = MagicMock()

    plugin._notify_subscribe(
        "测试剧 S1 下载连续超时，请手动处理",
        text="低进度删除 3/3 次",
        follow_up="请手动判断",
        diagnostic=True,
    )

    kwargs = plugin.post_message.call_args.kwargs
    assert kwargs["text"] == (
        "低进度删除 3/3 次\n"
        "后续：请手动判断"
    )
    assert kwargs["image"] == plugin.plugin_icon


def test_backfill_best_version_now_skips_full_best_version_before_detection(monkeypatch):
    """立即回填不得探测或改写全集洗版订阅。"""
    sub = _sub(id=5, name="X", best_version=1, best_version_full=1)
    subscribe_oper = MagicMock()
    subscribe_oper.list.return_value = [sub]
    priority_manager = MagicMock()
    priority_manager.can_backfill.return_value = False
    monkeypatch.setattr("subscribeassistantenhanced.SubscribeOper", MagicMock(return_value=subscribe_oper))
    monkeypatch.setattr("subscribeassistantenhanced.PriorityManager", MagicMock(return_value=priority_manager))
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()
    plugin._detect_existing_episodes = MagicMock(return_value=list(range(1, 13)))

    plugin.init_plugin({"backfill_best_version_now": True})

    plugin._detect_existing_episodes.assert_not_called()
    priority_manager.backfill_existing.assert_not_called()


def test_full_best_version_existing_library_does_not_complete_via_backfill(monkeypatch):
    """媒体库已有全集但没有新下载时，全集洗版不能通过回填进入完成路径。"""
    sub = _sub(id=5, name="X", best_version=1, best_version_full=1, total_episode=3)
    subscribe_oper = MagicMock()
    subscribe_oper.list.return_value = [sub]
    monkeypatch.setattr("subscribeassistantenhanced.SubscribeOper", MagicMock(return_value=subscribe_oper))
    plugin = SubscribeAssistantEnhanced()
    plugin.update_config = MagicMock()
    plugin._detect_existing_episodes = MagicMock(return_value=[1, 2, 3])

    plugin.init_plugin({
        "best_version_type": "all",
        "backfill_best_version_now": True,
    })

    priority_manager = plugin._modules["priority_manager"]
    plugin._detect_existing_episodes.assert_not_called()
    subscribe_oper.update.assert_not_called()
    assert sub.episode_priority == {}
    assert priority_manager.is_complete(sub) is False


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


def test_manual_delete_listen_off_keeps_present_fn_for_invalid_cleanup():
    """关闭监听手动删除只禁用手动删除善后，不禁用下载器种子存在性探测。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"manual_delete_listen": False})
    assert plugin._modules["download_monitor"]._present_fn is not None
    assert plugin._modules["download_monitor"]._manual_delete_enabled is False

    plugin2 = SubscribeAssistantEnhanced()
    plugin2.init_plugin({"manual_delete_listen": True})
    assert plugin2._modules["download_monitor"]._present_fn is not None
    assert plugin2._modules["download_monitor"]._manual_delete_enabled is True


def test_pending_only_disables_manual_delete_cleanup_branch():
    """只开启下载待定时，下载任务检查只做本地释放，不走手动删种善后阈值。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "pending_download_enabled": True,
        "download_monitor_enabled": False,
        "manual_delete_listen": True,
    })

    assert plugin._modules["download_monitor"]._present_fn is not None
    assert plugin._modules["download_monitor"]._manual_delete_enabled is False


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
    """待定集数刷新不依赖虚拟默认总集数，也不覆盖主程序 total。"""
    from app.schemas.event import SubscribeEpisodesRefreshEventData

    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({})
    pending_refresh = plugin._modules["pending_refresh"]
    event_data = SubscribeEpisodesRefreshEventData(
        current_total_episode=0,
        subscribe_id=1,
        season=1,
        mediainfo=SimpleNamespace(season_info=[], tmdb_info={}),
    )
    event_data.source = "main"
    event_data.reason = "keep"

    pending_refresh.handle_refresh(event_data)

    assert event_data.updated is False
    assert event_data.total_episode is None
    assert event_data.source == "main"
    assert event_data.reason == "keep"


def test_airing_checker_receives_pre_air_days():
    """插件入口必须把电影和剧集上映前暂停天数注入播出判定器。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "pause_enhanced_enabled": True,
        "movie_air_pause_days": 7,
        "tv_air_pause_days": 5,
    })
    airing_checker = plugin._event_proxy.get("airing_checker")

    assert airing_checker._movie_air_days == 7
    assert airing_checker._tv_air_days == 5


def test_best_version_and_cleanup_receive_type_filters():
    """插件入口必须分别把洗版范围和订阅清理范围/场景注入对应模块。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "best_version_type": "tv",
        "subscription_cleanup_history_type": "movie",
        "subscription_cleanup_history_scenes": ["normal", "best_version"],
    })
    orchestrator = plugin._modules["orchestrator"]
    subscription_cleanup = plugin._modules["subscription_cleanup"]

    assert orchestrator._best_version_type == "tv"
    assert subscription_cleanup._cleanup_history_type == "movie"
    assert subscription_cleanup._cleanup_history_scenes == ["normal", "best_version"]


def test_get_transfer_histories_passes_episode_when_provided():
    """整理记录查询可按季集收窄，供订阅清理按集定位旧文件。"""
    plugin = SubscribeAssistantEnhanced()
    plugin._transferhistory_oper = MagicMock()
    plugin._transferhistory_oper.get_by.return_value = []

    plugin._get_transfer_histories(tmdbid=100, mtype="电视剧", season="S01", episode="E02")

    plugin._transferhistory_oper.get_by.assert_called_once_with(
        tmdbid=100, mtype="电视剧", season="S01", episode="E02")


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

    def test_transfer_complete_event_converts_ready_episode_best_version(self):
        """真实插件入口接通分集洗版转全集补偿依赖。"""
        sub = _sub(id=7, best_version=1, best_version_full=0, lack_episode=0)
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"best_version_type": "all", "best_version_episode_to_full": True})
        oper = MagicMock()
        oper.get.return_value = sub
        plugin._subscribe_oper = oper
        plugin._event_proxy._modules["subscribe_oper"] = oper
        plugin._task_manager.update("torrents", lambda _data: {"abc": {"subscribe_id": 7}})
        mediainfo = _mediainfo()
        plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
        plugin._resolve_subscribe_missing = MagicMock(return_value=(True, {}))
        converter = plugin._modules["converter"]
        converter.convert_to_full = MagicMock(return_value=True)
        # init_plugin 时注入的是绑定方法；替换 mock 后需同步给事件代理，验证入口 wiring 与事件链路。
        plugin._event_proxy._modules["resolve_missing_fn"] = plugin._resolve_subscribe_missing
        plugin._event_proxy._modules["recognize_mediainfo_fn"] = plugin._recognize_mediainfo
        lifecycle = plugin._modules["lifecycle"]
        lifecycle._subscribe_oper = oper
        lifecycle.handle_library_updated = MagicMock(wraps=lifecycle.handle_library_updated)

        plugin.on_transfer_complete(SimpleNamespace(event_data={
            "download_hash": "abc",
            "transferinfo": None,
        }))

        lifecycle.handle_library_updated.assert_called_once_with(7)
        converter.convert_to_full.assert_called_once_with(sub, mediainfo)

    def test_transfer_complete_event_pauses_after_lack_is_refreshed(self):
        """整理完成事件应读取入库后的订阅状态，并在短窗口下立即进入播出暂停。"""
        next_air = date.today() + timedelta(days=2)
        later_dates = [next_air + timedelta(days=7 * offset) for offset in range(1, 5)]
        sub = _sub(
            id=7,
            state="R",
            best_version=0,
            total_episode=92,
            lack_episode=5,
            note=list(range(31, 88)),
        )
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"pause_enhanced_enabled": True, "airing_pause_days": 1})
        oper = MagicMock()
        oper.get.return_value = sub
        plugin._subscribe_oper = oper
        plugin._event_proxy._modules["subscribe_oper"] = oper
        plugin._task_manager.update("torrents", lambda _data: {"abc": {"subscribe_id": 7}})
        mediainfo = _mediainfo(next_episode_to_air=SimpleNamespace(
            air_date=(date.today() - timedelta(days=1)).isoformat(),
            episode_number=87,
            season_number=1,
        ), type=MediaType.TV)
        plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
        plugin._tmdb_episodes = MagicMock(return_value=[
            SimpleNamespace(air_date=(date.today() - timedelta(days=1)).isoformat(), episode_number=87, season_number=1),
            SimpleNamespace(air_date=next_air.isoformat(), episode_number=88, season_number=1),
            SimpleNamespace(air_date=later_dates[0].isoformat(), episode_number=89, season_number=1),
            SimpleNamespace(air_date=later_dates[1].isoformat(), episode_number=90, season_number=1),
            SimpleNamespace(air_date=later_dates[2].isoformat(), episode_number=91, season_number=1),
            SimpleNamespace(air_date=later_dates[3].isoformat(), episode_number=92, season_number=1),
        ])
        plugin._event_proxy._modules["recognize_mediainfo_fn"] = plugin._recognize_mediainfo
        plugin._event_proxy._modules["tmdb_episodes_fn"] = plugin._tmdb_episodes
        plugin._modules["airing_checker"]._evidence_pipeline = SimpleNamespace(
            evaluate=MagicMock(return_value=CompletionEvidence(primary_signal=CompletionSignal()))
        )
        pause_manager = plugin._modules["pause_manager"]
        pause_manager.pause = MagicMock()
        lifecycle = plugin._modules["lifecycle"]
        lifecycle._subscribe_oper = oper
        lifecycle.handle_library_updated = MagicMock(wraps=lifecycle.handle_library_updated)

        plugin.on_transfer_complete(SimpleNamespace(event_data={
            "download_hash": "abc",
            "transferinfo": None,
        }))

        lifecycle.handle_library_updated.assert_called_once_with(7)
        pause_manager.pause.assert_called_once()
        record = pause_manager.pause.call_args.args[1]
        assert record.reason == "airing_gap"
        assert next_air.isoformat() in record.detail

    def test_stop_service_clears_state(self):
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        plugin.stop_service()
        assert plugin._event_proxy is None
        assert plugin._modules == {}


class TestPeriodicJobs:
    """定时巡检：洗版巡检和完成前观察释放（recognize/oper 以 mock 注入）。"""

    def test_best_version_check_does_not_mark_full_best_version_complete(self, monkeypatch):
        """全集洗版普通完成不再由插件巡检主动标记完成。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"best_version_type": "all"})
        best_sub = _sub(id=1, name="X", best_version=1, best_version_full=1)
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [best_sub]
        monkeypatch.setattr(plugin, "_recognize_mediainfo", lambda sub: _mediainfo())
        plugin._resolve_subscribe_missing = MagicMock(return_value=(True, []))
        priority = MagicMock()
        plugin._modules["priority_manager"] = priority

        plugin.run_best_version_check()

        priority.mark_complete.assert_not_called()

    def test_best_version_check_skips_complete_check_for_tv_episode_best_version(self):
        """剧集分集洗版不进入电影/全集洗版的时限终止路径。"""
        sub = _sub(id=9, name="测试", best_version=1, best_version_full=0)
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"best_version_type": "all"})
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [sub]
        plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
        plugin._resolve_subscribe_missing = MagicMock(return_value=(False, []))
        priority = plugin._modules["priority_manager"]
        priority.mark_complete = MagicMock()

        plugin.run_best_version_check()

        priority.mark_complete.assert_not_called()

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
        plugin._recognize_mediainfo = MagicMock(return_value=_mediainfo())
        plugin._resolve_subscribe_missing = MagicMock(return_value=(False, [3]))
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

    def test_detect_missing_episodes_passes_subscribe_total_to_download_chain(self, monkeypatch):
        """媒体库缺集探测按订阅目标总集数调用主程序，避免 start 调整后范围漂移。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        sub = _sub(id=9, name="测试", season=2, start_episode=3, total_episode=8)
        plugin._recognize_mediainfo = MagicMock(return_value=SimpleNamespace(tmdb_id=100))
        captured = {}

        def fake_no_exists(*args, **kwargs):
            captured.update(kwargs)
            return True, {}

        monkeypatch.setattr(
            "app.chain.download.DownloadChain.get_no_exists_info",
            fake_no_exists,
        )

        assert plugin._detect_missing_episodes(sub) == []
        assert captured["totals"] == {2: 8}

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

    def test_completion_verify_keeps_existing_episode_best_version_subscription(self):
        """同身份分集洗版订阅已存在时，完成快照应失效而不是删除重建。"""
        snap = {
            "tmdbid": 100,
            "season": 1,
            "episode_group_id": None,
            "total_at_completion": 12,
            "subscribe_config": {"name": "测试", "season": 1, "best_version": 1, "best_version_full": 1},
        }
        data_store = {"snapshots": {"list": [snap]}}
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        plugin._modules["verifier"]._read = lambda key: data_store.get(key, {})
        plugin._modules["verifier"]._update = (
            lambda key, fn: data_store.__setitem__(key, fn(data_store.get(key, {})))
        )
        plugin._modules["verifier"]._tmdb_fn = MagicMock(return_value=[object()] * 13)
        plugin._modules["verifier"]._subscribe_oper = MagicMock()
        plugin._modules["verifier"]._subscribe_oper.list.return_value = [
            _sub(id=7, tmdbid=100, season=1, best_version=1, best_version_full=0)
        ]
        plugin._modules["verifier"]._rebuild_subscribe = MagicMock(return_value=True)

        plugin.run_completion_verify()

        plugin._modules["verifier"]._subscribe_oper.delete.assert_not_called()
        plugin._modules["verifier"]._rebuild_subscribe.assert_not_called()
        assert data_store["snapshots"]["list"] == []

    def test_completion_verify_keeps_existing_normal_subscription(self):
        """同身份普通订阅已存在时，完成快照应失效而不是重复重建。"""
        snap = {
            "tmdbid": 100,
            "season": 1,
            "episode_group_id": None,
            "total_at_completion": 12,
            "subscribe_config": {"name": "测试", "season": 1, "best_version": 0},
        }
        data_store = {"snapshots": {"list": [snap]}}
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        plugin._modules["verifier"]._read = lambda key: data_store.get(key, {})
        plugin._modules["verifier"]._update = (
            lambda key, fn: data_store.__setitem__(key, fn(data_store.get(key, {})))
        )
        plugin._modules["verifier"]._tmdb_fn = MagicMock(return_value=[object()] * 13)
        plugin._modules["verifier"]._subscribe_oper = MagicMock()
        plugin._modules["verifier"]._subscribe_oper.list.return_value = [
            _sub(id=7, tmdbid=100, season=1, best_version=0, best_version_full=0)
        ]
        plugin._modules["verifier"]._rebuild_subscribe = MagicMock(return_value=True)

        plugin.run_completion_verify()

        plugin._modules["verifier"]._subscribe_oper.delete.assert_not_called()
        plugin._modules["verifier"]._rebuild_subscribe.assert_not_called()
        assert data_store["snapshots"]["list"] == []

    def test_completion_verify_replaces_existing_full_best_version_subscription(self):
        """同身份真正洗版订阅已存在时，完成快照可删除旧订阅并按新增集重建。"""
        snap = {
            "tmdbid": 100,
            "season": 1,
            "episode_group_id": None,
            "total_at_completion": 12,
            "subscribe_config": {"name": "测试", "season": 1, "best_version": 1},
        }
        data_store = {"snapshots": {"list": [snap]}}
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        plugin._modules["verifier"]._read = lambda key: data_store.get(key, {})
        plugin._modules["verifier"]._update = (
            lambda key, fn: data_store.__setitem__(key, fn(data_store.get(key, {})))
        )
        plugin._modules["verifier"]._tmdb_fn = MagicMock(return_value=[object()] * 13)
        plugin._modules["verifier"]._subscribe_oper = MagicMock()
        plugin._modules["verifier"]._subscribe_oper.list.return_value = [
            _sub(id=7, tmdbid=100, season=1, best_version=1, best_version_full=1)
        ]
        plugin._modules["verifier"]._rebuild_subscribe = MagicMock(return_value=True)
        plugin._modules["verifier"]._notify = MagicMock()

        plugin.run_completion_verify()

        plugin._modules["verifier"]._subscribe_oper.delete.assert_called_once_with(7)
        plugin._modules["verifier"]._rebuild_subscribe.assert_called_once()
        assert plugin._modules["verifier"]._rebuild_subscribe.call_args.args[1]["start_episode"] == 13
        assert plugin._modules["verifier"]._rebuild_subscribe.call_args.args[1]["best_version_full"] == 1
        assert plugin._modules["verifier"]._notify.call_args.args[0].endswith("已移除旧洗版订阅并重建订阅")
        assert data_store["snapshots"]["list"] == []

    def test_completion_verify_replaces_existing_movie_best_version_subscription(self):
        """电影洗版订阅已存在时，完成快照可删除旧订阅并按新增目标重建。"""
        snap = {
            "tmdbid": 100,
            "season": None,
            "episode_group_id": None,
            "total_at_completion": 1,
            "subscribe_config": {"name": "测试电影", "type": "电影", "best_version": 1},
        }
        data_store = {"snapshots": {"list": [snap]}}
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        plugin._modules["verifier"]._read = lambda key: data_store.get(key, {})
        plugin._modules["verifier"]._update = (
            lambda key, fn: data_store.__setitem__(key, fn(data_store.get(key, {})))
        )
        plugin._modules["verifier"]._tmdb_fn = MagicMock(return_value=[object()] * 2)
        plugin._modules["verifier"]._subscribe_oper = MagicMock()
        plugin._modules["verifier"]._subscribe_oper.list.return_value = [
            _sub(id=8, tmdbid=100, season=None, type=MediaType.MOVIE, best_version=1, best_version_full=0)
        ]
        plugin._modules["verifier"]._rebuild_subscribe = MagicMock(return_value=True)
        plugin._modules["verifier"]._notify = MagicMock()

        plugin.run_completion_verify()

        plugin._modules["verifier"]._subscribe_oper.delete.assert_called_once_with(8)
        plugin._modules["verifier"]._rebuild_subscribe.assert_called_once()
        assert plugin._modules["verifier"]._notify.call_args.args[0].endswith("已移除旧洗版订阅并重建订阅")
        assert data_store["snapshots"]["list"] == []

    def test_pending_release_active_guard_veto_uses_pending_judge_not_orphan_cleanup(self, monkeypatch):
        """活跃 guard_veto P 必须交给 PendingJudge，不绕过证据流水线释放。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        sub = _sub(id=1, state="P")
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.get.return_value = sub
        plugin._subscribe_oper.list.return_value = [sub]
        data_store = {
            "blocks": {"1": {"blocked_at": 0}},
            "subscribes": {
                "1": {
                    "state": "P",
                    "source": "guard_veto",
                    "pending_sources": {"guard_veto": {"reason": "未完结"}},
                }
            },
        }
        plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
        plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
        plugin._task_manager._get = plugin.get_data
        plugin._task_manager._save = plugin.save_data
        monkeypatch.setattr(plugin, "_recognize_mediainfo", lambda _subscribe: _mediainfo())
        pending_judge = plugin._modules["pending_judge"]
        pending_judge.check_exit = MagicMock(return_value=False)
        plugin._modules["timeout_manager"].clear_observation = MagicMock()

        plugin.run_pending_release()

        pending_judge.check_exit.assert_called_once()
        assert pending_judge.check_exit.call_args.kwargs["source"] == "guard_veto"
        plugin._modules["timeout_manager"].clear_observation.assert_not_called()

    def test_pending_release_delegates_active_p_to_lifecycle(self):
        """待定释放巡检只调度生命周期协调器，不在入口重复待定退出判定。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        sub = _sub(id=7, state="P")
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [sub]
        plugin._subscribe_oper.get.return_value = sub
        plugin.get_data = MagicMock(return_value={})
        lifecycle = MagicMock()
        plugin._modules["lifecycle"] = lifecycle
        pending_judge = plugin._modules["pending_judge"]
        pending_judge.check_exit = MagicMock(return_value=True)

        plugin.run_pending_release()

        lifecycle.release_pending_source.assert_called_once_with(
            sub,
            source="pending_judge",
            reason="待定释放巡检",
        )
        pending_judge.check_exit.assert_not_called()

    def test_pending_release_delegates_active_guard_veto_source_to_lifecycle(self):
        """活跃 guard_veto 定时释放必须把 guard_veto source 交给生命周期层。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        sub = _sub(id=8, state="P")
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [sub]
        plugin._subscribe_oper.get.return_value = sub
        plugin.get_data = MagicMock(return_value={
            "8": {
                "state": "P",
                "source": "pending_judge",
                "pending_sources": {
                    "pending_judge": {"reason": "集数不足"},
                    "guard_veto": {"reason": "未完结"},
                },
            }
        })
        lifecycle = MagicMock()
        plugin._modules["lifecycle"] = lifecycle

        plugin.run_pending_release()

        lifecycle.release_pending_source.assert_any_call(
            sub,
            source="guard_veto",
            reason="待定释放巡检",
        )

    def test_pending_release_active_guard_veto_recomputes_l_with_plugin_resolver(self, monkeypatch):
        """活跃 guard_veto 巡检要带插件主程序缺集 resolver 重算 L。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        sub = _sub(id=1, state="P")
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.get.return_value = sub
        plugin._subscribe_oper.list.return_value = [sub]
        data_store = {
            "blocks": {
                "1": {
                    "blocked_at": time.time(),
                    "signals": ["L:target_satisfied"],
                    "confidence": "low",
                    "total_episode": 12,
                }
            },
            "subscribes": {
                "1": {
                    "state": "P",
                    "source": "guard_veto",
                    "pending_sources": {"guard_veto": {"reason": "低置信"}},
                }
            },
        }
        plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
        plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
        plugin._task_manager._get = plugin.get_data
        plugin._task_manager._save = plugin.save_data
        plugin._modules["pending_state"]._read = plugin._task_manager.read
        plugin._modules["pending_state"]._update = plugin._task_manager.update
        plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper
        plugin._resolve_subscribe_missing = MagicMock(return_value=(True, {}))
        judge = plugin._modules["pending_judge"]
        judge._resolve_missing_fn = plugin._resolve_subscribe_missing
        low_l = CompletionSignal(
            completed=True,
            confidence="low",
            signals=["L:target_satisfied"],
            reason="订阅目标范围已无待下载集",
            scope_total=12,
        )

        def evaluate_with_resolver(subscribe, mediainfo, **kwargs):
            kwargs["resolve_missing_fn"](
                subscribe=subscribe,
                mediainfo=mediainfo,
                meta=None,
                best_version_accept_downloaded=False,
            )
            return CompletionEvidence(
                primary_signal=low_l,
                local_signal=low_l,
                scope_total=12,
                observation_kind="low_l",
            )

        judge._evidence_pipeline = SimpleNamespace(evaluate=MagicMock(side_effect=evaluate_with_resolver))
        monkeypatch.setattr(plugin, "_recognize_mediainfo", lambda _subscribe: _mediainfo())

        plugin.run_pending_release()

        plugin._resolve_subscribe_missing.assert_called()
        assert data_store["subscribes"]["1"]["state"] == "P"

    def test_pending_release_orphan_observation_is_cleared_when_no_guard_source(self, monkeypatch):
        """fallback 只清理孤儿观察记录和放行令牌，不绕过证据流水线释放活跃 guard_veto。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        sub = _sub(id=1, state="R")
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.get.return_value = sub
        plugin._subscribe_oper.list.return_value = []
        data_store = {
            "blocks": {"1": {"blocked_at": 0}},
            "releases": {"1": {"signals": ["I:all_aired"]}},
            "subscribes": {"1": {"state": "R"}},
        }
        plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
        plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
        plugin._task_manager._get = plugin.get_data
        plugin._task_manager._save = plugin.save_data

        plugin.run_pending_release()

        assert "1" not in data_store["blocks"]
        assert "1" not in data_store.get("releases", {})

    def test_pending_release_unparseable_guard_observation_restarts_observation(self, monkeypatch):
        """无法解析的旧格式观察记录不能借旧计时；活跃 guard_veto 应重新建档保持 P。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"timeout_release_days": 7})
        sub = _sub(id=1, state="P", name="测试", type="电视剧", total_episode=2)
        data_store = {
            "subscribes": {
                "1": {
                    "state": "P",
                    "source": "guard_veto",
                    "pending_sources": {"guard_veto": {"reason": "未完结"}},
                }
            },
            "blocks": {
                "1": {
                    "blocked_at": time.time() - 30 * 86400,
                    "reason": "guard_veto",
                }
            },
        }
        plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
        plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
        plugin._task_manager._get = plugin.get_data
        plugin._task_manager._save = plugin.save_data
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.get.return_value = sub
        plugin._subscribe_oper.list.return_value = [sub]
        monkeypatch.setattr(plugin, "_recognize_mediainfo", lambda _subscribe: _mediainfo())
        sig = CompletionSignal(
            completed=True,
            confidence="low",
            stable=True,
            signals=["I:all_aired"],
            scope_total=2,
        )
        evidence = CompletionEvidence(
            primary_signal=sig,
            i_low_signal=sig,
            scope_total=2,
            observation_kind="low_i",
        )
        plugin._modules["pending_judge"]._evidence_pipeline = SimpleNamespace(
            evaluate=MagicMock(return_value=evidence)
        )

        plugin.run_pending_release()

        assert data_store["blocks"]["1"]["signals"] == ["I:all_aired"]
        assert data_store["blocks"]["1"]["blocked_at"] > time.time() - 60
        assert data_store.get("releases", {}) == {}
        assert data_store["subscribes"]["1"]["state"] == "P"

    def test_low_confidence_guard_timeout_release_allows_next_completion(self, monkeypatch):
        """低置信 guard_veto 超时释放后，下次完成检查可消费令牌放行。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "completion_guard_mode": "strict",
            "verify_enabled": True,
            "timeout_release_days": 21,
        })
        sub = _sub(id=1, state="P", name="测试", type="电视剧", total_episode=2)
        mediainfo = _mediainfo()
        data_store = {
            "subscribes": {
                "1": {
                    "state": "P",
                    "source": "guard_veto",
                    "pending_sources": {"guard_veto": {"reason": "低置信"}},
                }
            },
            "blocks": {
                "1": {
                    "blocked_at": time.time() - 25 * 86400,
                    "signals": ["I:all_aired"],
                    "confidence": "low",
                    "total_episode": 2,
                    "identity": {
                        "subscribe_id": 1,
                        "tmdbid": 100,
                        "season": 1,
                        "episode_group": None,
                    },
                }
            },
        }

        plugin.get_data = MagicMock(side_effect=lambda key: data_store.get(key, {}))
        plugin.save_data = MagicMock(side_effect=lambda key, value: data_store.__setitem__(key, value))
        plugin._task_manager._get = plugin.get_data
        plugin._task_manager._save = plugin.save_data
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.get.return_value = sub
        plugin._subscribe_oper.list.return_value = [sub]
        plugin._modules["pending_state"]._subscribe_oper = plugin._subscribe_oper
        monkeypatch.setattr(plugin, "_recognize_mediainfo", lambda s: mediainfo)
        sig = CompletionSignal(
            completed=True,
            confidence="low",
            stable=True,
            signals=["I:all_aired"],
            reason="低置信",
        )
        evidence = CompletionEvidence(
            primary_signal=sig,
            i_low_signal=sig,
            scope_total=2,
            observation_kind="low_i",
        )
        fake_pipeline = SimpleNamespace(
            evaluate=MagicMock(return_value=evidence)
        )
        plugin._modules["pending_judge"]._evidence_pipeline = fake_pipeline
        plugin._modules["guard"].evidence_pipeline = fake_pipeline

        plugin.run_pending_release()

        event = SimpleNamespace(event_data=SimpleNamespace(
            subscribe=sub,
            mediainfo=mediainfo,
            cancel=False,
            source="",
            reason="",
        ))
        plugin._modules["guard"].handle(event)

        assert event.event_data.cancel is False
        assert data_store.get("snapshots", {}) == {}

    def test_pending_release_checks_pending_judge_tasks(self):
        """pending_judge 写入的 P 订阅应由定时巡检调用 check_exit，而不只清理孤儿观察记录。"""
        sub = _sub(id=7, state="P", name="测试", best_version=0)
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"pending_enhanced_enabled": True})
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
        plugin.init_plugin({"pending_download_enabled": True})
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

    def test_snapshot_collector_is_wired_when_auto_correction_disabled(self):
        """关闭自动纠错只停止定时复查，完成事件仍必须采集快照。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"enabled": True, "verify_enabled": False})

        assert plugin._event_proxy.get("verifier") is plugin._modules["verifier"]
        service_ids = {s["id"] for s in plugin.get_service()}
        assert "SubscribeAssistantEnhanced_verify" not in service_ids

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
    service_ids = {service["id"] for service in plugin.get_service()}
    assert "SubscribeAssistantEnhanced_download_pause_expiry" not in service_ids


def test_orchestrator_uses_related_download_history_helper():
    """自动洗版编排器应注入真实关联下载历史 helper。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({"best_version_type": "tv_episode"})

    assert plugin._modules["orchestrator"]._related_downloads == plugin._related_download_histories


def test_download_pending_works_when_timeout_delete_disabled():
    """下载待定只受 pending_download_enabled 控制，不随下载超时自动删除关闭。"""
    plugin = SubscribeAssistantEnhanced()
    plugin.init_plugin({
        "enabled": True,
        "download_monitor_enabled": False,
        "pending_download_enabled": True,
    })

    assert plugin._event_proxy.get("download_monitor") is plugin._modules["download_monitor"]
    assert plugin._event_proxy.get("pending_download_enabled") is True
    assert plugin._event_proxy.get("download_monitor_enabled") is False
    service_ids = {service["id"] for service in plugin.get_service()}
    assert "SubscribeAssistantEnhanced_download" in service_ids


class TestNoDownloadCheck:
    """无下载处理巡检执行策略返回的订阅动作。"""

    @staticmethod
    def _plugin_with_overdue_subscribe(subscribe, mediainfo, action):
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "movie_no_download_days": 180,
            "tv_no_download_days": 180,
            "no_download_actions": [action],
        })
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.return_value = [subscribe]
        plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
        plugin._last_download_date = MagicMock(return_value=None)
        return plugin

    def test_recognize_mediainfo_skips_unknown_media_type(self):
        """未知订阅类型不默认当电影识别，避免脏数据进入错误媒体链路。"""
        subscribe = _sub(type=MediaType.UNKNOWN, name="测试", year="2025", season=1, tmdbid=100)
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        plugin.chain = MagicMock()

        result = plugin._recognize_mediainfo(subscribe)

        assert result is None
        plugin.chain.recognize_media.assert_not_called()

    def test_last_download_date_queries_tv_history_and_returns_latest_date(self):
        """剧集按媒体信息和季查询下载历史，并返回最近下载日期。"""
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

    def test_overdue_tv_pause_action_clears_stale_tasks_after_pause(self):
        """剧集超期执行暂停后清理旧任务，同时保留暂停记录与恢复保护。"""
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
        plugin._task_manager.clear_tasks_for_pause = MagicMock()
        plugin._modules["pause_manager"].pause = MagicMock()

        plugin.run_no_download_check()

        plugin._modules["pause_manager"].pause.assert_called_once()
        plugin._task_manager.clear_tasks_for_pause.assert_called_once_with(19, preserve_subscribe_keys=[
            "pause_reason",
            "pause_since",
            "pause_detail",
            "paused_probe_resume_guard_reason",
            "paused_probe_resume_guard_until",
        ])

    def test_no_download_pause_action_delegates_to_lifecycle(self):
        """无下载暂停只由生命周期协调器执行，完成/删除动作仍留在入口本地处理。"""
        subscribe = _sub(id=30, state="R", name="测试", type="电视剧", season=1)
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
        lifecycle = MagicMock()
        lifecycle.pause_for_no_download.return_value = LifecycleResult(changed=True)
        plugin._modules["lifecycle"] = lifecycle
        plugin._modules["pause_manager"].pause = MagicMock()

        plugin.run_no_download_check()

        lifecycle.pause_for_no_download.assert_called_once()
        assert lifecycle.pause_for_no_download.call_args.args[0] is subscribe
        assert "无下载截止日" in lifecycle.pause_for_no_download.call_args.args[1]
        plugin._modules["pause_manager"].pause.assert_not_called()

    def test_overdue_tv_pause_action_respects_resume_guard(self):
        """下载命中恢复保护期内，无下载巡检不清任务、不通知、不再次暂停。"""
        subscribe = _sub(id=29, state="R", name="测试", type="电视剧", season=1)
        mediainfo = _mediainfo(
            season_info=[{"season_number": 1, "air_date": "2025-01-01"}],
            first_air_date="2025-01-01",
        )
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "pause_enhanced_enabled": True,
            "notify": True,
            "tv_no_download_days": 180,
            "no_download_actions": ["pause_tv"],
        })
        plugin.save_data("subscribes", {
            "29": {
                "paused_probe_resume_guard_reason": "no_download",
                "paused_probe_resume_guard_until": time.time() + 3600,
            },
        })
        plugin._subscribe_oper = MagicMock()
        plugin._modules["pause_manager"]._subscribe_oper = plugin._subscribe_oper
        plugin._subscribe_oper.list.return_value = [subscribe]
        plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
        plugin._last_download_date = MagicMock(return_value=None)
        plugin._task_manager.clear_tasks_for_pause = MagicMock()
        plugin.post_message = MagicMock()

        plugin.run_no_download_check()

        task = plugin.get_data("subscribes")["29"]
        assert "pause_reason" not in task
        plugin._task_manager.clear_tasks_for_pause.assert_not_called()
        plugin.post_message.assert_not_called()

    def test_episode_best_version_tv_overdue_pause_action_pauses_subscribe(self):
        """分集洗版剧集超期且无下载时仍按剧集无下载策略暂停订阅。"""
        subscribe = _sub(
            id=23,
            state="R",
            name="测试",
            type="电视剧",
            season=1,
            best_version=1,
            best_version_full=0,
            date="2025-01-01 00:00:00",
        )
        mediainfo = _mediainfo(
            season_info=[{"season_number": 1, "air_date": "2025-01-01"}],
            first_air_date="2025-01-01",
        )
        plugin = self._plugin_with_overdue_subscribe(subscribe, mediainfo, "pause_tv")
        plugin._modules["pause_manager"].pause = MagicMock()

        plugin.run_no_download_check()

        plugin._recognize_mediainfo.assert_called_once_with(subscribe)
        plugin._last_download_date.assert_called_once_with(subscribe)
        plugin._modules["pause_manager"].pause.assert_called_once()

    def test_full_best_version_tv_overdue_delete_action_deletes_subscribe(self):
        """全集洗版剧集超期且无下载时仍按剧集无下载策略删除订阅。"""
        subscribe = _sub(
            id=24,
            state="R",
            name="测试",
            type="电视剧",
            season=1,
            best_version=1,
            best_version_full=1,
            date="2025-01-01 00:00:00",
        )
        mediainfo = _mediainfo(
            season_info=[{"season_number": 1, "air_date": "2025-01-01"}],
            first_air_date="2025-01-01",
        )
        plugin = self._plugin_with_overdue_subscribe(subscribe, mediainfo, "delete_tv")

        plugin.run_no_download_check()

        plugin._recognize_mediainfo.assert_called_once_with(subscribe)
        plugin._last_download_date.assert_called_once_with(subscribe)
        plugin._subscribe_oper.delete.assert_called_once_with(24)

    def test_movie_best_version_overdue_complete_action_adds_history_and_deletes_subscribe(self):
        """电影洗版超期且无下载时仍按电影无下载策略完成订阅。"""
        subscribe = _sub(
            id=25,
            state="R",
            name="测试电影",
            type="电影",
            season=None,
            best_version=1,
            best_version_full=0,
            date="2025-01-01 00:00:00",
        )
        mediainfo = _mediainfo(
            release_date="2025-01-01",
            type=SimpleNamespace(value="电影"),
        )
        plugin = self._plugin_with_overdue_subscribe(subscribe, mediainfo, "complete_movie")

        plugin.run_no_download_check()

        plugin._recognize_mediainfo.assert_called_once_with(subscribe)
        plugin._last_download_date.assert_called_once_with(subscribe)
        plugin._subscribe_oper.add_history.assert_called_once_with(**subscribe.to_dict())
        plugin._subscribe_oper.delete.assert_called_once_with(25)

    def test_overdue_tv_pause_action_preserves_no_download_pause_detail(self):
        """无下载暂停清理旧任务后仍应持久保存暂停原因详情。"""
        subscribe = _sub(id=22, state="R", name="测试", type="电视剧", season=1)
        mediainfo = _mediainfo(
            season_info=[{"season_number": 1, "air_date": "2025-01-01"}],
            first_air_date="2025-01-01",
        )
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "tv_no_download_days": 180,
            "no_download_actions": ["pause_tv"],
        })
        plugin.save_data("subscribes", {
            "22": {
                "state": "P",
                "source": "download_pending",
                "torrent_tasks": [{"hash": "old-hash"}],
            },
        })
        plugin.save_data("torrents", {"old-hash": {"subscribe_id": 22}})
        plugin._subscribe_oper = MagicMock()
        plugin._modules["pause_manager"]._subscribe_oper = plugin._subscribe_oper
        plugin._subscribe_oper.list.return_value = [subscribe]
        plugin._recognize_mediainfo = MagicMock(return_value=mediainfo)
        plugin._last_download_date = MagicMock(return_value=None)

        plugin.run_no_download_check()

        task = plugin.get_data("subscribes")["22"]
        assert task["pause_reason"] == "no_download"
        assert "开播日期：2025-01-01" in task["pause_detail"]
        assert "无下载截止日：" in task["pause_detail"]
        assert plugin.get_data("torrents") == {}

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
        assert "开播日期：2025-01-01" in plugin.post_message.call_args.kwargs["text"]
        assert "无下载截止日：" in plugin.post_message.call_args.kwargs["text"]

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
        assert "上映日期：2025-01-01" in plugin.post_message.call_args.kwargs["text"]
        assert "无下载截止日：" in plugin.post_message.call_args.kwargs["text"]
