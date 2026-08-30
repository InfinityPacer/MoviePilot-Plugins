"""WeatherWidget V3 的公开接口、缓存生命周期和天气解析合同测试。"""

from __future__ import annotations

import ast
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.plugins.weatherwidget as weatherwidget
from app.plugins.weatherwidget import WeatherWidget
from app.runtime.extensions.plugin.contracts import supports_plugin_hook


PLUGIN_ROOT = Path(__file__).parents[3] / "plugins.v3" / "weatherwidget"


def _plugin(data_path: Path) -> WeatherWidget:
    """构造不启动调度器、网络或宿主插件 Runtime 的测试实例。"""
    plugin = object.__new__(WeatherWidget)
    plugin._enabled = True
    plugin._border = False
    plugin._weather_notify = True
    plugin._weather_notify_cron = "0 8 * * *"
    plugin._refresh_interval = 1
    plugin._scheduler = None
    plugin._event = threading.Event()
    plugin._location = "南京"
    plugin._location_url = ""
    plugin._weather_api_key = ""
    plugin._weather_api_key_configured = False
    plugin._weather_url = "https://www.qweather.com/weather/nanjing.html"
    plugin._auto_theme_enabled = False
    plugin._auto_height = False
    plugin._use_dark_mode = False
    plugin._adapt_mode = "compatibility"
    plugin._component_size = "mini"
    plugin._weather_background = "#fff"
    plugin._weather_current_time = "2026-08-31 12:00"
    plugin._weather_air_tag = " AQI 优 "
    plugin._weather_air_tag_background = "#95B359"
    plugin._screenshot_type = "default"
    plugin._last_screenshot_time = None
    plugin.get_data_path = MagicMock(return_value=data_path)
    return plugin


def test_v3_source_uses_public_sdk_boundaries() -> None:
    """V3 入口使用公开 SDK，不依赖旧兼容路径或旧浏览器实现。"""
    source_path = PLUGIN_ROOT / "__init__.py"
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(source_path))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert "app.sdk.browser" in imported_modules
    assert "app.sdk.config" in imported_modules
    assert "app.sdk.events" in imported_modules
    assert "app.sdk.logging" in imported_modules
    assert "app.sdk.network" in imported_modules
    assert "app.sdk.plugins" in imported_modules
    assert not any(
        module.startswith(
            ("app.compat", "app.core", "app.helper", "app.log", "app.utils", "app.db")
        )
        for module in imported_modules
    )
    assert "from cloakbrowser" not in source
    assert "sync_playwright" not in source
    assert not hasattr(weatherwidget, "IMAGES_PATH")


def test_v3_metadata_and_capability_contract() -> None:
    """插件版本、命令、页面和 API 能力符合 V3 索引合同。"""
    plugin = _plugin(Path("/tmp/weatherwidget-test"))

    assert WeatherWidget.plugin_version == "3.0.0"
    assert WeatherWidget.plugin_name == "天气"
    assert plugin.get_command()[0]["cmd"] == "/weather_notify"
    assert plugin.get_api() == []
    assert plugin.get_page() is None
    assert supports_plugin_hook(plugin, "get_page") is True


def test_init_plugin_resets_state_without_reusing_previous_config(monkeypatch) -> None:
    """重载空配置时应停用插件并清空旧配置，且不触发真实网络。"""
    plugin = _plugin(Path("/tmp/weatherwidget-test"))
    plugin._WeatherWidget__update_config = MagicMock()
    monkeypatch.setattr(
        WeatherWidget,
        "_WeatherWidget__get_weather_url",
        lambda _self: "https://weather.example/current",
    )
    monkeypatch.setattr(
        WeatherWidget,
        "_WeatherWidget__should_use_dark_mode",
        lambda _self: False,
    )

    plugin.init_plugin({"enabled": False, "location": "上海", "weather_notify": False})

    assert plugin.get_state() is False
    assert plugin._location == "上海"
    assert plugin._weather_url == "https://weather.example/current"
    assert plugin._weather_notify is False
    assert plugin._event is not None

    plugin.init_plugin()

    assert plugin.get_state() is False
    assert plugin._location == ""
    assert plugin._weather_notify is True
    assert plugin._weather_notify_cron is None


def test_init_plugin_keeps_environment_key_ephemeral(monkeypatch) -> None:
    """初始化时从环境变量读取的密钥不得被视为用户配置。"""
    plugin = _plugin(Path("/tmp/weatherwidget-test"))
    plugin._WeatherWidget__update_config = MagicMock()
    monkeypatch.setenv("QWEATHER_API_KEY", "environment-key")
    monkeypatch.setattr(
        WeatherWidget,
        "_WeatherWidget__get_weather_url",
        lambda _self: None,
    )
    monkeypatch.setattr(
        WeatherWidget,
        "_WeatherWidget__should_use_dark_mode",
        lambda _self: False,
    )

    plugin.init_plugin({"enabled": False, "location": "南京"})

    assert plugin._weather_api_key == "environment-key"
    assert plugin._weather_api_key_configured is False


def test_weather_api_key_is_configured_without_source_literal_or_url_logging(monkeypatch):
    """天气 API 密钥来自受控配置，日志不得包含完整请求 URL。"""
    source = (PLUGIN_ROOT / "__init__.py").read_text(encoding="utf-8")
    assert "bdd98ec1d87747f3a2e8b1741a5af796" not in source

    plugin = _plugin(Path("/tmp/weatherwidget-test"))
    plugin._weather_api_key = "configured-key"
    plugin.get_data = MagicMock(return_value={})
    response = SimpleNamespace(status_code=200, json=lambda: {"code": "400"}, text="{}")
    request = MagicMock(return_value=response)
    monkeypatch.setattr(
        weatherwidget,
        "RequestUtils",
        lambda: SimpleNamespace(get_res=request),
    )
    log = MagicMock()
    monkeypatch.setattr(weatherwidget, "logger", log)

    assert plugin._WeatherWidget__get_weather_url() is None
    request.assert_called_once()
    assert "configured-key" in request.call_args.args[0]
    assert all(
        "configured-key" not in str(call)
        for call in log.info.call_args_list
    )


def test_environment_api_key_is_not_persisted():
    """环境变量密钥仅供运行时请求，不得写入插件配置。"""
    plugin = _plugin(Path("/tmp/weatherwidget-test"))
    plugin._weather_api_key = "environment-key"
    plugin._weather_api_key_configured = False
    update_config = MagicMock()
    plugin.update_config = update_config

    plugin._WeatherWidget__update_config()

    persisted_config = update_config.call_args.args[0]
    assert "weather_api_key" not in persisted_config
    assert "environment-key" not in str(persisted_config)


def test_configured_api_key_is_persisted():
    """用户在插件配置中填写的密钥仍应随配置保存。"""
    plugin = _plugin(Path("/tmp/weatherwidget-test"))
    plugin._weather_api_key = "configured-key"
    plugin._weather_api_key_configured = True
    update_config = MagicMock()
    plugin.update_config = update_config

    plugin._WeatherWidget__update_config()

    persisted_config = update_config.call_args.args[0]
    assert persisted_config["weather_api_key"] == "configured-key"


def test_get_service_exposes_refresh_and_notification_jobs() -> None:
    """启用插件时应声明截图刷新和天气通知两个宿主调度服务。"""
    plugin = _plugin(Path("/tmp/weatherwidget-test"))
    plugin._WeatherWidget__take_screenshots = MagicMock()

    services = plugin.get_service()

    assert [service["id"] for service in services] == [
        "RefreshWeather",
        "NotifyWeather",
    ]
    assert services[0]["kwargs"] == {"hours": 1}
    assert services[1]["kwargs"] == {}


def test_instance_cache_paths_are_isolated(tmp_path: Path) -> None:
    """截图必须写入实例数据目录，不能在模块导入期共享全局缓存目录。"""
    first = _plugin(tmp_path / "first")
    second = _plugin(tmp_path / "second")

    first_path = first._WeatherWidget__get_images_path()
    second_path = second._WeatherWidget__get_images_path()

    assert first_path == tmp_path / "first" / "images"
    assert second_path == tmp_path / "second" / "images"
    assert first_path != second_path


def test_browser_screenshot_uses_host_sdk_and_closes_resources(tmp_path, monkeypatch) -> None:
    """截图通过宿主浏览器 SDK 完成，并在成功后关闭页面和上下文。"""
    plugin = _plugin(tmp_path)
    image_dir = tmp_path / "images"
    image_dir.mkdir()

    class FakeElement:
        def bounding_box(self):
            return None

        def screenshot(self, path):
            Path(path).write_bytes(b"png")

    class FakePage:
        def __init__(self):
            self.element = FakeElement()
            self.closed = False

        def goto(self, _url):
            return None

        def wait_for_selector(self, _selector, timeout):
            assert timeout == plugin._screenshot_timeout * 1000

        def query_selector(self, _selector):
            return self.element

        def title(self):
            return "天气"

        def close(self):
            self.closed = True

    class FakeContext:
        def __init__(self):
            self.page = FakePage()
            self.closed = False

        def new_page(self):
            return self.page

        def close(self):
            self.closed = True

    context = FakeContext()
    launcher = MagicMock(return_value=context)
    monkeypatch.setattr(weatherwidget, "launch_browser_context", launcher)
    monkeypatch.setattr(
        WeatherWidget,
        "_WeatherWidget__reset_weather_style",
        MagicMock(),
    )
    monkeypatch.setattr(
        WeatherWidget,
        "_WeatherWidget__reset_page_style",
        MagicMock(),
    )
    monkeypatch.setattr(
        WeatherWidget,
        "_WeatherWidget__manage_images",
        MagicMock(),
    )

    success = plugin._WeatherWidget__screenshot_element_by_browser(
        key="mobile",
        device={"device": "iphone_13_pro_max", "size": {}},
        color_scheme="dark",
    )

    assert success is True
    launcher.assert_called_once()
    assert launcher.call_args.kwargs["headless"] is True
    assert launcher.call_args.kwargs["color_scheme"] == "dark"
    assert context.page.closed is True
    assert context.closed is True
    assert list(image_dir.glob("weather_南京_default_mobile_*.png"))


def test_resolve_weather_parses_current_report(monkeypatch) -> None:
    """天气页面解析应提取当前时间、温度、状况、空气质量和基础指标。"""
    plugin = _plugin(Path("/tmp/weatherwidget-test"))
    response = SimpleNamespace(
        text="""
        <p class="current-time">2026-08-31 12:00</p>
        <div class="current-live__item"></div>
        <div><p>28°C</p><p>晴</p></div>
        <a class="air-tag">优</a>
        <div class="current-basic___item"><p>3级</p><p>风力</p></div>
        <div class="current-abstract">适宜出行</div>
        """,
        raise_for_status=MagicMock(),
    )
    client = MagicMock()
    client.get_res.return_value = response
    monkeypatch.setattr(weatherwidget, "RequestUtils", lambda **_kwargs: client)

    report = plugin._WeatherWidget__resolve_weather()

    assert report is not None
    assert "当前时间: 2026-08-31 12:00" in report
    assert "温度: 28°C" in report
    assert "天气状况: 晴" in report
    assert "空气质量: 优" in report
    assert "风力: 3级" in report
    assert "适宜出行" in report
    response.raise_for_status.assert_called_once_with()
