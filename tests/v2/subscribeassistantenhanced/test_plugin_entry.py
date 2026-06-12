"""插件入口集成层契约：_PluginBase 基类、真实数据层、依赖注入。

这些断言保护"集成层"不被退回占位原型——继承缺失会导致数据层/生命周期全部失效；
PriorityManager 缺 subscribe_oper 注入会让洗版优先级写入静默 no-op。
"""
from app.core.event import eventmanager
from app.plugins import _PluginBase

from subscribeassistantenhanced import SubscribeAssistantEnhanced
from subscribeassistantenhanced.shared.subscribe import subscribe_from_source

# 12 个事件处理器必须定义在插件类上（主程序按 __qualname__ 首段解析运行实例分发）
_EVENT_HANDLERS = (
    "on_completion_check", "on_episodes_refresh", "on_subscribe_added",
    "on_subscribe_deleted", "on_subscribe_modified", "on_subscribe_complete",
    "on_download_added", "on_transfer_complete", "on_resource_selection",
    "on_resource_download", "on_transfer_intercept", "on_plugin_action",
)


class TestPluginEntry:
    """插件入口集成层：继承、数据持久化、依赖注入。"""

    def test_inherits_plugin_base(self):
        """增强版必须是 _PluginBase 子类，否则数据层/生命周期全部失效。"""
        assert issubclass(SubscribeAssistantEnhanced, _PluginBase)

    def test_data_layer_roundtrip(self):
        """get_data/save_data 由 _PluginBase 真实落盘，不再是返回 {} 的占位。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({"completion_guard_enabled": True})
        plugin.save_data("subscribes", {"1": {"flag": 1}})
        assert plugin.get_data("subscribes") == {"1": {"flag": 1}}

    def test_priority_manager_has_subscribe_oper(self):
        """PriorityManager 必须注入 subscribe_oper，否则优先级写入是 no-op。"""
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        pm = plugin._modules["priority_manager"]
        assert pm._subscribe_oper is not None


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
                     "on_transfer_intercept", "on_plugin_action"):
            assert any(f"SubscribeAssistantEnhanced.{name}" in ident for ident in identifiers), \
                f"事件处理器 {name} 未注册到 eventmanager"


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
