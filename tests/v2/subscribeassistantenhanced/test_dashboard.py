"""前端入口 smoke：只读概览 API 保留；详情页与仪表盘已下线。"""
from subscribeassistantenhanced import SubscribeAssistantEnhanced


class TestFrontend:
    """校验 /summary 概览接口仍可用，且详情页/仪表盘处于下线状态、不暴露入口。"""

    def _plugin(self):
        plugin = SubscribeAssistantEnhanced()
        plugin.init_plugin({})
        return plugin

    def test_get_api_exposes_summary(self):
        apis = self._plugin().get_api()
        assert any(a["path"] == "/summary" for a in apis)

    def test_api_summary_shape(self):
        summary = self._plugin()._api_summary()
        assert summary["domains"]["完结守卫模式"] == "balanced"
        assert "pending_count" in summary and "monitored_torrents" in summary

    def test_detail_page_offline(self):
        # 详情页下线：get_page 为占位实现（仅 docstring+pass），返回 None；
        # 框架据此判定 has_page=False，不在插件卡暴露「查看数据」入口。
        assert self._plugin().get_page() is None

    def test_dashboard_offline(self):
        # 仪表盘下线：不声明仪表盘卡片，get_dashboard_meta 继承基类返回 None。
        assert self._plugin().get_dashboard_meta() is None
