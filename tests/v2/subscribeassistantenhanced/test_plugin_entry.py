"""插件入口集成层契约：_PluginBase 基类、真实数据层、依赖注入。

这些断言保护"集成层"不被退回占位原型——继承缺失会导致数据层/生命周期全部失效；
PriorityManager 缺 subscribe_oper 注入会让洗版优先级写入静默 no-op。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.core.event import eventmanager
from app.core.event import Event
from app.plugins import _PluginBase
from app.schemas.event import PluginDataResetEventData
from app.schemas.types import ChainEventType, EventType

import subscribeassistantenhanced as plugin_module
from subscribeassistantenhanced import SubscribeAssistantEnhanced
from subscribeassistantenhanced.shared.config import PluginConfig
from subscribeassistantenhanced.shared.subscribe import subscribe_from_source

# 12 个事件处理器必须定义在插件类上（主程序按 __qualname__ 首段解析运行实例分发）
_EVENT_HANDLERS = (
    "on_completion_check", "on_episodes_refresh", "on_subscribe_added",
    "on_subscribe_deleted", "on_subscribe_modified", "on_subscribe_complete",
    "on_download_added", "on_transfer_complete", "on_resource_selection",
    "on_resource_download", "on_transfer_intercept", "on_plugin_action",
    "on_plugin_data_reset",
)


class TestPluginEntry:
    """插件入口集成层：继承、数据持久化、依赖注入。"""

    def test_inherits_plugin_base(self):
        """增强版必须是 _PluginBase 子类，否则数据层/生命周期全部失效。"""
        assert issubclass(SubscribeAssistantEnhanced, _PluginBase)

    def test_name_alias_matches_plugin_name_for_event_error_logging(self):
        """主程序事件错误处理读取 name 时，应得到插件展示名。"""
        plugin = SubscribeAssistantEnhanced()

        assert plugin.name == plugin.plugin_name

    def test_data_layer_roundtrip(self):
        """get_data/save_data 由 _PluginBase 真实落盘，不再是返回 {} 的占位。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"completion_guard_mode": "strict"})
        plugin.save_data("subscribes", {"1": {"flag": 1}})
        assert plugin.get_data("subscribes") == {"1": {"flag": 1}}

    def test_priority_manager_has_subscribe_oper(self):
        """PriorityManager 必须注入 subscribe_oper，否则优先级写入是 no-op。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        pm = plugin._modules["priority_manager"]
        assert pm._subscribe_oper is not None

    def test_init_plugin_registers_recognition_guard_when_mode_is_balanced(self):
        """识别增强模式为 balanced 时接入 ResourceSelection 事件链。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "recognition_guard_mode": "balanced",
            "recognition_guard_notify": "detail",
            "recognition_guard_notify_interval": 7200,
            "recognition_guard_tmdb_recheck_mode": "all",
            "recognition_guard_cache_maxsize": 2048,
            "recognition_guard_custom_config": "actions:\n  missing_year: block\n",
        })

        guard = plugin._modules["recognition_guard"]
        assert guard is not None
        assert plugin._event_proxy.get("recognition_guard") is guard
        assert guard.settings.mode == "balanced"
        assert guard.settings.notify_mode == "detail"
        assert guard.settings.notify_interval == 7200
        assert guard.settings.tmdb_recheck_mode == "all"
        assert guard.settings.cache_maxsize == 2048
        assert "missing_year: block" in guard.settings.custom_config

    def test_init_plugin_does_not_register_recognition_guard_when_off(self):
        """识别增强关闭时保留模块快照，但不参与事件链过滤。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"recognition_guard_mode": "off"})

        assert plugin._modules["recognition_guard"] is not None
        assert plugin._event_proxy.get("recognition_guard") is None

    def test_init_plugin_registers_progress_diagnostic_module(self):
        """无进展诊断按 progress_diagnostic 模块 key 注入，供巡检入口读取。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})

        assert "progress_diagnostic" in plugin._modules

    def test_recognition_external_failure_logs_are_sanitized(self, monkeypatch):
        """识别增强外部识别异常日志不得泄漏令牌或本地路径。"""
        messages = []
        plugin = SubscribeAssistantEnhanced()
        plugin.chain = SimpleNamespace(
            recognize_media=MagicMock(side_effect=RuntimeError(
                "request failed token=SECRET /Users/chengyu/媒体库/测试剧.mkv"
            ))
        )
        monkeypatch.setattr(plugin_module.logger, "warning", messages.append)

        assert plugin._recognize_by_meta_for_recognition(SimpleNamespace(type=None)) is None

        joined = "\n".join(messages)
        assert "SECRET" not in joined
        assert "/Users/" not in joined
        assert "媒体库" not in joined
        assert "[redacted" in joined

    def test_invalid_recognition_mode_warning_is_visible_in_startup_summary(self, monkeypatch):
        """非法识别增强模式回退关闭时，启动摘要保留稳定告警码。"""
        messages = []
        monkeypatch.setattr(plugin_module.logger, "info", messages.append)

        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"recognition_guard_mode": "bad"})

        joined = "\n".join(messages)
        assert "识别增强=off" in joined
        assert "识别增强告警=invalid_mode" in joined

    def test_site_cache_candidates_degrades_when_main_helper_missing(self, monkeypatch):
        """旧主程序缺少缓存候选 helper 时，站点证据扫描应跳过而不是中断巡检。"""
        warnings = []

        class _OldTorrentsChain:
            pass

        monkeypatch.setattr(plugin_module, "TorrentsChain", _OldTorrentsChain)
        monkeypatch.setattr(plugin_module.logger, "warning", warnings.append)
        monkeypatch.setattr(SubscribeAssistantEnhanced, "_site_cache_candidate_helper_warned", False)

        first = SubscribeAssistantEnhanced._site_cache_candidates(SimpleNamespace(id=1), allow_title_match=True)
        second = SubscribeAssistantEnhanced._site_cache_candidates(SimpleNamespace(id=1), allow_title_match=True)

        assert first == []
        assert second == []
        assert len(warnings) == 1
        assert "缺少站点缓存候选读取能力" in warnings[0]

    def test_site_cache_candidates_delegates_to_main_helper(self, monkeypatch):
        """主程序 helper 存在时，插件只透传订阅和参数，不自行读取或刷新缓存。"""
        calls = []

        class _TorrentsChain:
            def get_subscribe_cache_candidates(self, subscribe, **kwargs):
                calls.append((subscribe, kwargs))
                return ["ctx"]

        subscribe = SimpleNamespace(id=1)
        monkeypatch.setattr(plugin_module, "TorrentsChain", _TorrentsChain)

        result = SubscribeAssistantEnhanced._site_cache_candidates(subscribe, allow_title_match=True)

        assert result == ["ctx"]
        assert calls == [(subscribe, {"allow_title_match": True})]

    def test_torrent_exists_returns_true_when_any_downloader_contains_hash(self):
        """跨下载器查询任一命中 hash 时返回 True。"""
        plugin = SubscribeAssistantEnhanced()
        found = SimpleNamespace(instance=MagicMock())
        absent = SimpleNamespace(instance=MagicMock())
        found.instance.get_torrents.return_value = ([{"hash": "abc"}], False)
        absent.instance.get_torrents.return_value = ([], False)
        plugin._downloader_helper = MagicMock()
        plugin._downloader_helper.get_services.return_value = {
            "下载器A": absent,
            "下载器B": found,
        }

        assert plugin._torrent_exists("abc") is True

    def test_torrent_exists_returns_false_when_all_downloaders_confirm_absent(self):
        """全部下载器查询成功且均无 hash 时返回 False。"""
        plugin = SubscribeAssistantEnhanced()
        service = SimpleNamespace(instance=MagicMock())
        service.instance.get_torrents.return_value = ([], False)
        plugin._downloader_helper = MagicMock()
        plugin._downloader_helper.get_services.return_value = {"下载器A": service}

        assert plugin._torrent_exists("abc") is False

    def test_torrent_exists_returns_none_when_absent_result_includes_query_failure(self):
        """未命中 hash 且任一下载器查询失败时返回 None，不能误判为不存在。"""
        plugin = SubscribeAssistantEnhanced()
        failed = SimpleNamespace(instance=MagicMock())
        absent = SimpleNamespace(instance=MagicMock())
        failed.instance.get_torrents.return_value = ([], True)
        absent.instance.get_torrents.return_value = ([], False)
        plugin._downloader_helper = MagicMock()
        plugin._downloader_helper.get_services.return_value = {
            "下载器A": failed,
            "下载器B": absent,
        }

        assert plugin._torrent_exists("abc") is None

    def test_detect_existing_episodes_returns_existing_side_of_coverage_tuple(self):
        """媒体库已有集检测只暴露主程序缺集探测返回的已存在集。"""
        plugin = SubscribeAssistantEnhanced()
        plugin._detect_episode_coverage = MagicMock(return_value=([1, 2], [3]))

        assert plugin._detect_existing_episodes(SimpleNamespace(id=1)) == [1, 2]

    def test_detect_backfill_episodes_includes_note_below_current_start(self):
        """洗版回填候选合并 note 与媒体库已有集，保留 start_episode 前的历史下载记录。"""
        plugin = SubscribeAssistantEnhanced()
        plugin._detect_existing_episodes = MagicMock(return_value=[2, 3, 4])
        subscribe = SimpleNamespace(
            id=1,
            start_episode=2,
            total_episode=4,
            note=[1, "2", 3, 4, 5, 0, -1, "x"],
        )

        assert plugin._detect_backfill_episodes(subscribe) == [1, 2, 3, 4]

    def test_detect_backfill_episodes_ignores_candidates_when_total_is_invalid(self):
        """总集数异常时不回填，避免 note 或媒体库探测结果越过订阅目标边界。"""
        plugin = SubscribeAssistantEnhanced()
        plugin._detect_existing_episodes = MagicMock(return_value=[1, 2])
        subscribe = SimpleNamespace(
            id=1,
            start_episode=1,
            total_episode="unknown",
            note=[1, "2"],
        )

        assert plugin._detect_backfill_episodes(subscribe) == []

    def test_downloader_torrent_present_distinguishes_absent_and_unknown(self):
        """手动删种监听需要区分确删、仍存在和下载器不可判定。"""
        plugin = SubscribeAssistantEnhanced()
        service = SimpleNamespace(instance=MagicMock())
        plugin._downloader_helper = MagicMock()
        plugin._downloader_helper.get_service.return_value = service
        service.instance.get_torrents.return_value = ([], False)

        assert plugin._downloader_torrent_present("qb", "hash") is False

        service.instance.get_torrents.return_value = ([{"hash": "hash"}], False)
        assert plugin._downloader_torrent_present("qb", "hash") is True

        service.instance.get_torrents.return_value = ([], True)
        assert plugin._downloader_torrent_present("qb", "hash") is None

    def test_fetch_downloader_torrent_maps_download_item(self):
        """下载器返回种子时应转换为统一 TorrentInfo，供超时巡检判断进度。"""
        plugin = SubscribeAssistantEnhanced()
        service = SimpleNamespace(type="qbittorrent", instance=MagicMock())
        service.instance.get_torrents.return_value = ([{"hash": "abc", "state": "uploading", "progress": 1.0}], False)
        plugin._downloader_helper = MagicMock()
        plugin._downloader_helper.get_service.return_value = service

        info = plugin._fetch_downloader_torrent("qb", "abc")

        assert info.hash == "abc"
        assert info.completed is True

    def test_delete_downloader_torrent_delegates_delete_with_files(self):
        """删除巡检确认需要删种时，应要求下载器同时删除源文件。"""
        plugin = SubscribeAssistantEnhanced()
        service = SimpleNamespace(instance=MagicMock())
        plugin._downloader_helper = MagicMock()
        plugin._downloader_helper.get_service.return_value = service

        plugin._delete_downloader_torrent("qb", "abc")

        service.instance.delete_torrents.assert_called_once_with(delete_file=True, ids="abc")

    def test_delete_media_file_uses_storage_chain_fileitem(self):
        """订阅清理删除旧媒体文件时经 storage_chain 统一执行。"""
        plugin = SubscribeAssistantEnhanced()
        plugin._storage_chain = MagicMock()
        plugin._storage_chain.delete_media_file.return_value = True

        assert plugin._delete_media_file({"path": "/media/old.mkv", "type": "file"}) is True
        assert plugin._storage_chain.delete_media_file.call_args.args[0].path == "/media/old.mkv"

    def test_get_subscribe_image_prefers_backdrop_then_poster(self):
        """订阅通知图片优先背景图，缺失时回退海报图。"""
        assert SubscribeAssistantEnhanced._get_subscribe_image(
            SimpleNamespace(backdrop="https://img/original/back.jpg", poster="https://img/original/poster.jpg")
        ) == "https://img/w500/back.jpg"
        assert SubscribeAssistantEnhanced._get_subscribe_image(
            SimpleNamespace(backdrop="", poster="https://img/original/poster.jpg")
        ) == "https://img/w500/poster.jpg"
        assert SubscribeAssistantEnhanced._get_subscribe_image(SimpleNamespace(backdrop="", poster="")) == ""


class TestEventRegistration:
    """事件注册机制：handler 必须在插件类上、且被装饰器注册进 eventmanager。"""

    def test_handlers_defined_on_plugin_class(self):
        """handler 须为插件类方法（qualname 首段=类名），否则主程序分发拿不到运行实例。"""
        for name in _EVENT_HANDLERS:
            method = getattr(SubscribeAssistantEnhanced, name, None)
            assert method is not None, f"缺少事件处理器 {name}"
            assert method.__qualname__.split(".")[0] == "SubscribeAssistantEnhanced"

    def test_handlers_registered_in_eventmanager(self):
        """装饰器在导入期把 handler 注册进 eventmanager（按 module.Class.method 标识）。"""
        identifiers = {h["handler_identifier"] for h in eventmanager.visualize_handlers()}
        for name in ("on_subscribe_added", "on_episodes_refresh", "on_resource_download",
                     "on_transfer_intercept", "on_plugin_action", "on_plugin_data_reset"):
            assert any(f"SubscribeAssistantEnhanced.{name}" in ident for ident in identifiers), \
                f"事件处理器 {name} 未注册到 eventmanager"

    def test_plugin_class_event_handlers_delegate_to_event_proxy(self):
        """插件类事件入口必须转发到 EventProxy，保持主程序分发与业务逻辑解耦。"""
        handlers = (
            "on_completion_check", "on_episodes_refresh", "on_subscribe_added",
            "on_subscribe_modified", "on_subscribe_complete", "on_download_added",
            "on_resource_selection", "on_resource_download", "on_transfer_intercept",
            "on_plugin_action",
        )
        plugin = SubscribeAssistantEnhanced()
        plugin._event_proxy = MagicMock()
        event = object()

        for name in handlers:
            getattr(plugin, name)(event)

        for name in handlers:
            getattr(plugin._event_proxy, name).assert_called_once_with(event)

    def test_plugin_data_reset_event_runs_pre_clear_recovery(self, monkeypatch):
        """主程序清空插件数据前会调用现有任务重置逻辑恢复订阅状态。"""
        plugin = SubscribeAssistantEnhanced()
        reset_task_data = MagicMock()
        monkeypatch.setattr(plugin, "_reset_task_data", reset_task_data)
        plugin._event_proxy = MagicMock()
        event = Event(
            ChainEventType.PluginDataReset,
            PluginDataResetEventData(plugin_id="SubscribeAssistantEnhanced", reset_data=True),
        )

        plugin.on_plugin_data_reset(event)

        reset_task_data.assert_called_once_with()
        plugin._event_proxy.assert_not_called()

    def test_plugin_data_reset_event_ignores_other_plugins(self, monkeypatch):
        """只处理自身插件数据重置事件，避免其他插件重置时误清本插件任务。"""
        plugin = SubscribeAssistantEnhanced()
        reset_task_data = MagicMock()
        monkeypatch.setattr(plugin, "_reset_task_data", reset_task_data)
        event = Event(
            ChainEventType.PluginDataReset,
            PluginDataResetEventData(plugin_id="OtherPlugin", reset_data=True),
        )

        plugin.on_plugin_data_reset(event)

        reset_task_data.assert_not_called()

    def test_plugin_data_reset_event_notifies_recovery_summary_when_notify_enabled(self, monkeypatch):
        """重置前恢复了待定/暂停状态时，按通知开关推送汇总。"""
        pending_sub = SimpleNamespace(id=1, name="待定剧", season=1, state="P")
        paused_sub = SimpleNamespace(id=2, name="暂停剧", season=2, state="S")
        plugin = SubscribeAssistantEnhanced()
        plugin._config = PluginConfig({"notify": True})
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.side_effect = [[pending_sub], [paused_sub]]
        pending_state = MagicMock()
        pending_state.clear_all_owned.return_value = True
        pause_manager = MagicMock()
        pause_manager.get_pause_record.return_value = SimpleNamespace(reason="pre_air")
        pause_manager.resume.return_value = True
        plugin._modules = {"pending_state": pending_state, "pause_manager": pause_manager}
        plugin._notify_subscribe = MagicMock()
        saved = {}
        monkeypatch.setattr(plugin, "save_data", lambda key, value: saved.__setitem__(key, value))

        plugin.on_plugin_data_reset(Event(
            ChainEventType.PluginDataReset,
            PluginDataResetEventData(plugin_id="SubscribeAssistantEnhanced", reset_data=True),
        ))

        pending_state.clear_all_owned.assert_called_once_with(pending_sub, reason="插件任务重置")
        pause_manager.resume.assert_called_once_with(paused_sub, notify=False)
        plugin._notify_subscribe.assert_called_once()
        kwargs = plugin._notify_subscribe.call_args.kwargs
        assert plugin._notify_subscribe.call_args.args[0] == "订阅助手数据重置前已恢复订阅状态"
        assert "已将 1 个待定订阅恢复为启用：待定剧 S1" in kwargs["text"]
        assert "已将 1 个自动暂停订阅恢复为启用：暂停剧 S2" in kwargs["text"]
        assert set(saved) == {
            "subscribes", "torrents", "blocks", "releases", "snapshots",
            "deletes", "volatility", "site_evidence",
            "subscription_cleanup_histories",
        }

    def test_plugin_data_reset_event_logs_without_notify_when_nothing_recovered(self, monkeypatch):
        """重置前没有恢复任何状态时只记录日志，不发送通知。"""
        plugin = SubscribeAssistantEnhanced()
        plugin._config = PluginConfig({"notify": True})
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.side_effect = [[], []]
        plugin._modules = {"pending_state": MagicMock(), "pause_manager": MagicMock()}
        plugin._notify_subscribe = MagicMock()
        logger_info = MagicMock()
        monkeypatch.setattr(plugin_module.logger, "info", logger_info)
        monkeypatch.setattr(plugin, "save_data", lambda key, value: None)

        plugin.on_plugin_data_reset(Event(
            ChainEventType.PluginDataReset,
            PluginDataResetEventData(plugin_id="SubscribeAssistantEnhanced", reset_data=True),
        ))

        plugin._notify_subscribe.assert_not_called()
        assert any("未发现需要恢复的订阅状态" in call.args[0] for call in logger_info.call_args_list)

    def test_plugin_data_reset_stops_paused_probe_coordinator(self, monkeypatch):
        """重置任务数据前先失效待执行 probe Timer。"""
        plugin = SubscribeAssistantEnhanced()
        plugin._config = PluginConfig({})
        plugin._subscribe_oper = MagicMock()
        plugin._subscribe_oper.list.side_effect = [[], []]
        coordinator = MagicMock()
        plugin._paused_probe_coordinator = coordinator
        plugin._modules = {"pending_state": MagicMock(), "pause_manager": MagicMock()}
        monkeypatch.setattr(plugin, "save_data", lambda key, value: None)

        plugin._reset_task_data()

        coordinator.stop.assert_called_once_with()

    def test_stop_service_stops_paused_probe_coordinator(self):
        """插件停止或热重载时取消待执行 probe Timer。"""
        plugin = SubscribeAssistantEnhanced()
        coordinator = MagicMock()
        plugin._paused_probe_coordinator = coordinator

        plugin.stop_service()

        coordinator.stop.assert_called_once_with()
        assert plugin._paused_probe_coordinator is None


class TestScheduler:
    """get_service 按域开关声明定时任务。"""

    def test_get_service_declares_jobs_by_domain(self):
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "enabled": True,
            "download_monitor_enabled": True,
            "best_version_type": "all",
        })
        services = plugin.get_service()
        ids = {s["id"] for s in services}
        assert any(i.endswith("_download") for i in ids)
        assert any(i.endswith("_best_version") for i in ids)
        for service in services:
            assert callable(service["func"])
            assert service.get("trigger")

    def test_service_names_do_not_repeat_provider_prefix(self):
        """任务名称只描述动作；提供者列已经展示插件名，不再重复订阅助手前缀。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "enabled": True,
            "download_monitor_enabled": True,
            "verify_enabled": True,
            "pause_enhanced_enabled": True,
            "best_version_type": "tv",
        })
        names = [service["name"] for service in plugin.get_service()]
        assert "下载任务检查" in names
        assert "洗版订阅检查" in names
        assert "下载超时检查" not in names
        assert "洗版完成检查" not in names
        assert "通用巡检" in names
        assert "自动纠错" in names
        assert "完成后自验证" not in names
        assert "无下载处理" not in names
        assert "删除记录清理" not in names
        assert all(not name.startswith("订阅助手-") for name in names)

    def test_disabled_domains_keep_only_meta_check_scheduled(self):
        """业务域关闭时仍保留元数据检查和统一的通用巡检。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "enabled": True,
            "download_monitor_enabled": False,
            "pending_download_enabled": False,
            "verify_enabled": False,
            "pause_enhanced_enabled": False,
        })
        assert {service["id"] for service in plugin.get_service()} == {
            "SubscribeAssistantEnhanced_meta_check",
            "SubscribeAssistantEnhanced_common_check",
        }

    def test_pending_download_registers_download_check_service(self):
        """只开启下载待定时也要注册下载任务检查，用于释放下载待定。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "enabled": True,
            "download_monitor_enabled": False,
            "pending_download_enabled": True,
        })

        service_ids = {service["id"] for service in plugin.get_service()}
        assert "SubscribeAssistantEnhanced_download" in service_ids

    def test_verify_service_uses_configured_hour_interval(self):
        """完成后验证服务必须使用唯一公开的小时级周期配置。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"enabled": True, "verify_enabled": True, "verify_interval_hours": 6})
        service = next(item for item in plugin.get_service()
                       if item["id"].endswith("_verify"))
        assert service["kwargs"] == {"hours": 6}

    def test_run_download_timeout_check_delegates_to_monitor_with_cleanup(self):
        """下载任务定时入口应把清理服务传给监控模块。"""
        plugin = SubscribeAssistantEnhanced()
        monitor = MagicMock()
        cleanup = MagicMock()
        plugin._config = SimpleNamespace(download_monitor_enabled=True)
        plugin._modules = {"download_monitor": monitor, "torrent_cleanup": cleanup}

        plugin.run_download_timeout_check()

        monitor.run_timeout_check.assert_called_once_with(cleanup)

    def test_run_download_timeout_check_pending_only_omits_cleanup(self):
        """只开启下载待定时，下载任务检查不得拿到删种善后服务。"""
        plugin = SubscribeAssistantEnhanced()
        monitor = MagicMock()
        cleanup = MagicMock()
        plugin._config = SimpleNamespace(download_monitor_enabled=False)
        plugin._modules = {"download_monitor": monitor, "torrent_cleanup": cleanup}

        plugin.run_download_timeout_check()

        monitor.run_timeout_check.assert_called_once_with(None)

    def test_run_completion_verify_delegates_to_verifier(self):
        """完成后验证定时入口应触发 verifier 全量巡检。"""
        plugin = SubscribeAssistantEnhanced()
        verifier = MagicMock()
        plugin._modules = {"verifier": verifier}

        plugin.run_completion_verify()

        verifier.verify_all.assert_called_once_with()

    def test_run_cleanup_wrappers_delegate_to_owned_modules(self):
        """各类清理定时入口只调用对应模块，清理策略由模块内部维护。"""
        plugin = SubscribeAssistantEnhanced()
        verifier = MagicMock()
        subscription_cleanup = MagicMock()
        deletes_store = MagicMock()
        verifier.cleanup_expired.return_value = 2
        subscription_cleanup.cleanup_expired_clear_histories.return_value = 3
        deletes_store.cleanup_expired.return_value = 4
        plugin._config = SimpleNamespace(delete_record_retention_hours=72)
        plugin._modules = {
            "verifier": verifier,
            "subscription_cleanup": subscription_cleanup,
            "deletes_store": deletes_store,
        }

        plugin.run_completion_snapshot_cleanup()
        plugin.run_subscription_cleanup_expired()
        plugin.run_deletes_cleanup()

        verifier.cleanup_expired.assert_called_once_with()
        subscription_cleanup.cleanup_expired_clear_histories.assert_called_once_with()
        deletes_store.cleanup_expired.assert_called_once_with(72)

    def test_send_download_file_deleted_emits_event(self, monkeypatch):
        """订阅清理删除旧下载时必须通知主程序移除下载历史。"""
        send_event = MagicMock()
        monkeypatch.setattr(plugin_module.eventmanager, "send_event", send_event)
        plugin = SubscribeAssistantEnhanced()

        plugin._send_download_file_deleted("src", "hash")

        send_event.assert_called_once_with(EventType.DownloadFileDeleted, {"src": "src", "hash": "hash"})


class TestSubscribeFromSource:
    """origin/source 解析：仅 ``Subscribe|<json>`` 前缀被解析，其余安全跳过。"""

    class _Oper:
        """最小 subscribe_oper 桩：按 id 返回标记对象。"""
        def get(self, sid):
            return {"resolved_id": sid}

    def test_valid_source_resolves(self):
        sub_dict, sub = subscribe_from_source('Subscribe|{"id": 7}', self._Oper())
        assert sub_dict == {"id": 7}
        assert sub == {"resolved_id": 7}

    def test_wrong_prefix_returns_none(self):
        assert subscribe_from_source('Manual|{"id": 7}', self._Oper()) == (None, None)

    def test_no_pipe_returns_none(self):
        assert subscribe_from_source("Subscribe", self._Oper()) == (None, None)

    def test_bad_json_returns_none(self):
        assert subscribe_from_source("Subscribe|not-json", self._Oper()) == (None, None)
