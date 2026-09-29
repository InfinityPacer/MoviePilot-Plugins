"""WeatherWidget V3 的公开接口、缓存生命周期和天气解析合同测试。"""

from __future__ import annotations

import ast
import os
import threading
from datetime import datetime, time as dtime
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

    assert WeatherWidget.plugin_version == "3.1.0"
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


class _FakeElement:
    """只提供截图路径写入的页面元素替身。"""

    def bounding_box(self):
        return None

    def screenshot(self, path):
        Path(path).write_bytes(b"png")


class _FakePage:
    """记录关闭状态的页面替身。"""

    def __init__(self, timeout_ms: int):
        self.element = _FakeElement()
        self.closed = False
        self.timeout_ms = timeout_ms

    def set_viewport_size(self, _size):
        return None

    def goto(self, _url):
        return None

    def wait_for_selector(self, _selector, timeout):
        assert timeout == self.timeout_ms

    def query_selector(self, _selector):
        return self.element

    def title(self):
        return "天气"

    def close(self):
        self.closed = True


class _FakeContext:
    """浏览器上下文替身，关闭顺序写入共享列表以便断言。"""

    def __init__(self, name: str, timeout_ms: int, close_log: list, browser=None):
        self.name = name
        self.page = _FakePage(timeout_ms)
        self.browser = browser
        self.close_log = close_log

    def new_page(self):
        return self.page

    def close(self):
        self.close_log.append(self.name)


def _stub_page_styles(monkeypatch) -> None:
    """截图流程中的页面样式调整依赖真实 DOM，测试中置空。"""
    for name in ("__reset_weather_style", "__reset_page_style"):
        monkeypatch.setattr(WeatherWidget, f"_WeatherWidget{name}", MagicMock())


def test_browser_screenshots_share_one_browser_and_release_cache(tmp_path, monkeypatch) -> None:
    """一轮截图只启动一个浏览器，其余设备复用同一浏览器新开上下文，关闭后释放文件缓存。"""
    plugin = _plugin(tmp_path)
    (tmp_path / "images").mkdir()
    timeout_ms = plugin._screenshot_timeout * 1000
    close_log = []
    browser = MagicMock()
    desktop_context = _FakeContext("desktop", timeout_ms, close_log)
    browser.new_context.return_value = desktop_context
    mobile_context = _FakeContext("mobile", timeout_ms, close_log, browser=browser)
    launcher = MagicMock(return_value=mobile_context)
    monkeypatch.setattr(weatherwidget, "launch_browser_context", launcher)
    _stub_page_styles(monkeypatch)
    browser_procs = [object()]
    monkeypatch.setattr(WeatherWidget, "_WeatherWidget__get_child_pids", staticmethod(lambda: {1}))
    monkeypatch.setattr(
        WeatherWidget,
        "_WeatherWidget__get_new_child_procs",
        staticmethod(lambda known_pids: browser_procs),
    )
    # 映射文件必须在关闭上下文之前收集，此时浏览器进程仍在运行
    collect = MagicMock(side_effect=lambda browser_procs: close_log.append("collect") or {"/chrome"})
    monkeypatch.setattr(WeatherWidget, "_WeatherWidget__collect_mapped_files", staticmethod(collect))
    release = MagicMock()
    monkeypatch.setattr(WeatherWidget, "_WeatherWidget__release_browser_file_cache", staticmethod(release))

    plugin._WeatherWidget__take_screenshots_by_browser(
        screenshot_devices=weatherwidget.SCREENSHOT_DEVICES["default"],
        color_scheme="dark",
        start_time=datetime.now(),
    )

    launcher.assert_called_once()
    assert launcher.call_args.kwargs["headless"] is True
    assert launcher.call_args.kwargs["color_scheme"] == "dark"
    desktop_options = browser.new_context.call_args.kwargs
    assert desktop_options["viewport"] == {"width": 740, "height": 1024}
    assert desktop_options["color_scheme"] == "dark"
    assert "iPad" in desktop_options["user_agent"]
    assert mobile_context.page.closed is True
    assert desktop_context.page.closed is True
    # 主上下文关闭会连带关闭浏览器，必须最后关闭
    assert close_log == ["collect", "desktop", "mobile"]
    collect.assert_called_once_with(browser_procs=browser_procs)
    release.assert_called_once_with(browser_procs=browser_procs, mapped_files={"/chrome"})
    assert list((tmp_path / "images").glob("weather_南京_default_mobile_*.png"))
    assert list((tmp_path / "images").glob("weather_南京_default_desktop_*.png"))


def test_release_browser_file_cache_drops_mapped_files(tmp_path, monkeypatch) -> None:
    """只收集浏览器进程映射的真实文件，并在进程退出后再释放它们的缓存。"""
    mapped = tmp_path / "chrome"
    mapped.write_bytes(b"binary")
    proc = MagicMock()
    proc.memory_maps.return_value = [
        SimpleNamespace(path=str(mapped)),
        SimpleNamespace(path="[heap]"),
        SimpleNamespace(path="/tmp/removed (deleted)"),
    ]
    order = []
    monkeypatch.setattr(
        weatherwidget.psutil,
        "wait_procs",
        lambda procs, timeout: order.append(("wait", timeout)),
    )
    advised = []

    def fake_fadvise(fd, offset, length, advice):
        order.append("advise")
        advised.append((os.fstat(fd).st_ino, offset, length, advice))

    monkeypatch.setattr(os, "posix_fadvise", fake_fadvise, raising=False)
    monkeypatch.setattr(os, "POSIX_FADV_DONTNEED", 4, raising=False)

    mapped_files = WeatherWidget._WeatherWidget__collect_mapped_files(browser_procs=[proc])
    assert mapped_files == {str(mapped)}
    WeatherWidget._WeatherWidget__release_browser_file_cache(browser_procs=[proc], mapped_files=mapped_files)

    assert order == [("wait", weatherwidget.BROWSER_EXIT_TIMEOUT), "advise"]
    assert advised == [(mapped.stat().st_ino, 0, 0, 4)]


def test_refresh_interval_defaults_and_accepts_disabled() -> None:
    """旧配置缺少刷新周期时按默认 6 小时，不刷新用显式 0 表示，非法值回落默认。"""
    normalize = WeatherWidget._WeatherWidget__normalize_refresh_interval

    assert normalize(None) == 6
    assert normalize("12") == 12
    assert normalize(0) == weatherwidget.REFRESH_DISABLED
    assert normalize(5) == 6
    assert normalize("abc") == 6


def test_form_and_config_expose_refresh_interval() -> None:
    """表单提供不刷新和各周期选项，默认 6 小时，保存配置时写回刷新周期。"""
    plugin = _plugin(Path("/tmp/weatherwidget-test"))
    form, defaults = plugin.get_form()

    assert defaults["refresh_interval"] == 6
    source = str(form)
    assert "'model': 'refresh_interval'" in source
    assert "不刷新（仅通知）" in source

    plugin._refresh_interval = 12
    plugin.update_config = MagicMock()
    plugin._WeatherWidget__update_config()
    assert plugin.update_config.call_args.args[0]["refresh_interval"] == 12


def test_disabled_refresh_keeps_notification_only(tmp_path) -> None:
    """选择不刷新时只保留通知服务，按需刷新和仪表盘都不触发截图。"""
    plugin = _plugin(tmp_path)
    plugin._refresh_interval = weatherwidget.REFRESH_DISABLED
    plugin._WeatherWidget__take_screenshots = MagicMock()
    add_task = MagicMock()
    plugin._WeatherWidget__add_screenshot_task = add_task

    services = plugin.get_service()
    plugin._WeatherWidget__add_screenshot_task_if_stale()
    cols, attrs, elements = plugin.get_dashboard(user_agent="Mozilla/5.0 (iPhone)")

    assert [service["id"] for service in services] == ["NotifyWeather"]
    add_task.assert_not_called()
    assert "已关闭天气刷新" in str(elements)


def test_on_demand_refresh_respects_interval_and_theme(tmp_path, monkeypatch) -> None:
    """仪表盘读取截图时，只有截图过期或明暗主题变化才补一次截图。"""
    plugin = _plugin(tmp_path)
    plugin._refresh_interval = 6
    images = tmp_path / "images"
    images.mkdir()
    image = images / "weather_南京_default_mobile_20260929120000.png"
    image.write_bytes(b"png")
    add_task = MagicMock()
    plugin._WeatherWidget__add_screenshot_task = add_task

    plugin._WeatherWidget__add_screenshot_task_if_stale()
    add_task.assert_not_called()

    stale = datetime.now().timestamp() - 7 * 3600
    os.utime(image, (stale, stale))
    plugin._WeatherWidget__add_screenshot_task_if_stale()
    assert add_task.call_count == 1

    # 截图仍新鲜，但按缓存的日出日落时间已进入夜间，需要切换为暗色截图
    now = datetime.now().timestamp()
    os.utime(image, (now, now))
    plugin._auto_theme_enabled = True
    plugin._use_dark_mode = False
    plugin._sunrise_time = dtime(0, 0)
    plugin._sunset_time = dtime(0, 1)
    plugin._WeatherWidget__add_screenshot_task_if_stale()
    assert add_task.call_count == 2


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
