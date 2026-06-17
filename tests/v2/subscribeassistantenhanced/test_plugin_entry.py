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
from app.schemas.types import ChainEventType

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
            "deletes", "volatility", "subscription_cleanup_histories",
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


class TestScheduler:
    """get_service 按域开关声明定时任务。"""

    def test_get_service_declares_jobs_by_domain(self):
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "enabled": True,
            "download_monitor_enabled": True,
            "best_version_type": "all",
            "timeout_release_enabled": True,
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
            "timeout_release_enabled": True,
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
        assert "待定超时释放" not in names
        assert "无下载处理" not in names
        assert "删除记录清理" not in names
        assert all(not name.startswith("订阅助手-") for name in names)

    def test_disabled_domains_keep_only_meta_check_scheduled(self):
        """业务域关闭时仍保留元数据检查和统一的通用巡检。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({
            "enabled": True,
            "download_monitor_enabled": False,
            "timeout_release_enabled": False,
            "verify_enabled": False,
            "pause_enhanced_enabled": False,
        })
        assert {service["id"] for service in plugin.get_service()} == {
            "SubscribeAssistantEnhanced_meta_check",
            "SubscribeAssistantEnhanced_common_check",
        }

    def test_verify_service_uses_configured_hour_interval(self):
        """完成后验证服务必须使用唯一公开的小时级周期配置。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"enabled": True, "verify_enabled": True, "verify_interval_hours": 6})
        service = next(item for item in plugin.get_service()
                       if item["id"].endswith("_verify"))
        assert service["kwargs"] == {"hours": 6}


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
