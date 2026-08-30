"""PlexAutoLanguages V3 的宿主边界、配置和生命周期合同测试。"""

from __future__ import annotations

import ast
import threading
from pathlib import Path
from queue import Queue
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from app.plugins import plexautolanguages
from app.plugins.plexautolanguages import PlexAutoLanguages
from app.plugins.plexautolanguages.core.exceptions import InvalidConfiguration
from app.plugins.plexautolanguages.core.plex_alert_handler import PlexAlertHandler
from app.plugins.plexautolanguages.core.plex_server import PlexServer
from app.plugins.plexautolanguages.core.plex_server_cache import PlexServerCache
from app.plugins.plexautolanguages.core.utils.configuration import Configuration
from app.plugins.plexautolanguages.languageprovider import LanguageProvider
from app.runtime.extensions.plugin.contracts import supports_plugin_hook

PLUGIN_ROOT = Path(__file__).parents[3] / "plugins.v3" / "plexautolanguages"


def _service(
        name: str = "Plex",
        *,
        inactive: bool = False,
        host: str = "plex.example:32400",
        token: str = "test-token",
) -> SimpleNamespace:
    """构造宿主媒体服务目录返回的最小 ServiceInfo 形状。"""
    instance = SimpleNamespace(is_inactive=MagicMock(return_value=inactive))
    config = SimpleNamespace(
        name=name,
        type="plex",
        config={"host": host, "token": token},
    )
    return SimpleNamespace(
        name=name,
        type="plex",
        instance=instance,
        config=config,
    )


def _plugin(tmp_path: Path) -> PlexAutoLanguages:
    """构造不启动网络线程的插件实例。"""
    plugin = object.__new__(PlexAutoLanguages)
    plugin.mediaserver_helper = MagicMock()
    plugin._lang_provider = None
    plugin._lang_thread = None
    plugin._enabled = True
    plugin._mediaserver = "Plex"
    plugin._auto_switch = True
    plugin._update_level = "show"
    plugin._update_strategy = "all"
    plugin._trigger_on_play = True
    plugin._trigger_on_scan = True
    plugin._event = threading.Event()
    plugin.get_data_path = MagicMock(return_value=tmp_path)
    return plugin


def test_v3_source_uses_sdk_and_relative_plugin_boundaries() -> None:
    """V3 源码使用公开 SDK，插件内部模块不通过宿主旧路径互相导入。"""
    source = "\n".join(
        path.read_text(encoding="utf-8")
        for path in PLUGIN_ROOT.rglob("*.py")
    )

    assert "from app.sdk.services import MediaServerHelper" in source
    assert "from app.sdk.logging import logger" in source
    assert "from app.sdk.network import UrlUtils" in source
    for legacy_prefix in (
        "app.compat",
        "app.core",
        "app.helper",
        "app.log",
        "app.utils",
        "app.db",
        "app.plugins.plexautolanguages",
    ):
        assert legacy_prefix not in source

    for source_path in PLUGIN_ROOT.rglob("*.py"):
        tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
        absolute_plugin_imports = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("app.plugins.plexautolanguages")
        ]
        assert absolute_plugin_imports == []


def test_v3_metadata_and_empty_capabilities_contract() -> None:
    """插件元数据、空 API/命令/服务和空详情页能力保持明确。"""
    plugin = _plugin(Path("/tmp/plexautolanguages-test"))

    assert PlexAutoLanguages.plugin_version == "1.0.0"
    assert plugin.get_command() == []
    assert plugin.get_api() == []
    assert plugin.get_service() == []
    assert plugin.get_page() is None
    assert supports_plugin_hook(plugin, "get_page") is False


def test_service_info_uses_sdk_helper_and_filters_inactive_service(tmp_path: Path) -> None:
    """服务查询必须限定 Plex 类型，并拒绝缺失或未连接的服务实例。"""
    plugin = _plugin(tmp_path)
    active = _service()
    plugin.mediaserver_helper.get_service.return_value = active

    assert plugin.service_info is active
    plugin.mediaserver_helper.get_service.assert_called_once_with(
        name="Plex",
        type_filter="plex",
    )

    plugin.mediaserver_helper.get_service.return_value = _service(inactive=True)
    assert plugin.service_info is None

    plugin.mediaserver_helper.get_service.return_value = None
    assert plugin.service_info is None


def test_service_info_requires_selected_media_server(tmp_path: Path) -> None:
    """未选择媒体服务器时不访问宿主服务目录。"""
    plugin = _plugin(tmp_path)
    plugin._mediaserver = None

    assert plugin.service_info is None
    plugin.mediaserver_helper.get_service.assert_not_called()


def test_configuration_loads_default_and_user_yaml_under_data_path(tmp_path: Path) -> None:
    """配置覆盖和缓存数据目录必须由插件数据路径提供，而非源码目录。"""
    default_path = PLUGIN_ROOT / "config" / "default.yaml"
    user_path = tmp_path / "user.yaml"
    user_path.write_text(
        "plexautolanguages:\n"
        "  update_level: season\n"
        "  ignore_labels: PAL_IGNORE, PAL_SKIP\n",
        encoding="utf-8",
    )

    config = Configuration(default_path, user_path, tmp_path)

    assert config.get("update_level") == "season"
    assert config.get("ignore_labels") == ["PAL_IGNORE", " PAL_SKIP"]
    assert config.get("data_dir") == tmp_path
    assert not (PLUGIN_ROOT / "config" / "user.yaml").exists()


def test_cache_initialization_writes_to_plugin_data_path(tmp_path: Path) -> None:
    """缓存文件必须落在配置提供的插件数据目录，并可被下一实例读取。"""
    data_path = tmp_path / "plugin-data"
    plex = SimpleNamespace(
        config=SimpleNamespace(get=lambda key: data_path if key == "data_dir" else None),
        unique_id="plex-instance",
        episodes=list,
    )

    cache = PlexServerCache(plex)

    cache_path = data_path / "cache" / "plex-instance"
    assert cache._cache_file_path == str(cache_path)
    assert cache_path.is_file()

    restored = PlexServerCache(plex)
    assert restored.episode_parts == {}


def test_plugin_writes_generated_user_yaml_to_get_data_path(tmp_path: Path) -> None:
    """宿主 Plex 配置同步到用户 YAML 时只能写入实例数据目录。"""
    plugin = _plugin(tmp_path)
    service = _service(host="plex.example:32400", token="host-token")
    plugin.mediaserver_helper.get_service.return_value = service

    PlexAutoLanguages._PlexAutoLanguages__update_user_config(plugin)

    user_yaml = tmp_path / "user.yaml"
    assert user_yaml.is_file()
    content = user_yaml.read_text(encoding="utf-8")
    assert "http://plex.example:32400/" in content
    assert "host-token" in content
    assert not (PLUGIN_ROOT / "config" / "user.yaml").exists()


def test_configuration_rejects_missing_plex_credentials(tmp_path: Path) -> None:
    """缺少 Plex 地址或令牌时在建立外部连接前失败关闭。"""
    default_path = tmp_path / "default.yaml"
    default_path.write_text(
        "plexautolanguages:\n"
        "  plex:\n"
        "    url: ''\n"
        "    token: ''\n"
        "  update_level: show\n"
        "  update_strategy: all\n"
        "  ignore_labels: []\n"
        "  scheduler:\n"
        "    enable: false\n"
        "    schedule_time: '04:30'\n",
        encoding="utf-8",
    )

    with pytest.raises(InvalidConfiguration):
        Configuration(default_path, tmp_path / "missing.yaml", tmp_path)


def test_language_provider_handles_initialization_failure_and_health() -> None:
    """Plex 初始化异常不会泄漏到后台线程，未建立连接时健康状态为假。"""
    provider = object.__new__(LanguageProvider)
    provider.logger = MagicMock()
    provider.config = MagicMock()
    provider.config.get.side_effect = lambda key: {
        "plex.url": "http://plex.example:32400/",
        "plex.token": "token",
    }[key]
    provider.plex = None
    provider.alive = False
    provider._stop_event = threading.Event()

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(
            "app.plugins.plexautolanguages.languageprovider.PlexServer",
            MagicMock(side_effect=RuntimeError("connection failed")),
        )
        provider.init()

    assert provider.plex is None
    assert provider.is_healthy() is False
    provider.logger.error.assert_called_once()


def test_language_provider_runs_one_task_and_stops_plex() -> None:
    """服务线程可完成一次监听任务，并按停止信号保存缓存和释放 Plex。"""
    provider = object.__new__(LanguageProvider)
    provider.scheduler = None
    provider.stop_signal = False
    provider.must_stop = False
    provider.alive = False
    provider.logger = MagicMock()
    provider.plex = MagicMock()
    provider._stop_event = threading.Event()
    provider.init = lambda: None

    def stop_after_listener(_callback):
        provider.stop()

    provider.plex.start_alert_listener.side_effect = stop_after_listener
    provider.start()

    provider.plex.save_cache.assert_called_once_with()
    provider.plex.stop.assert_called_once_with()
    assert provider.alive is False


def test_alert_processor_logs_unexpected_errors_with_sdk_logger() -> None:
    """单条告警异常必须留在处理线程内，并使用 SDK 日志支持的方法记录堆栈。"""
    handler = object.__new__(PlexAlertHandler)
    handler._plex = MagicMock()
    handler._alerts_queue = Queue()
    handler._stop_event = threading.Event()
    alert = MagicMock()
    alert.TYPE = "playing"
    alert.message = {"type": "playing"}

    def fail_processing(_plex) -> None:
        handler._stop_event.set()
        raise RuntimeError("invalid alert")

    alert.process.side_effect = fail_processing
    handler._alerts_queue.put(alert)

    with patch("app.plugins.plexautolanguages.core.plex_alert_handler.logger") as sdk_logger:
        handler._process_alerts()

    sdk_logger.error.assert_called_once_with("Unable to process playing", exc_info=True)
    sdk_logger.debug.assert_any_call(alert.message)


def test_plugin_lifecycle_resets_state_and_stops_thread(tmp_path: Path, monkeypatch) -> None:
    """配置重载先释放旧线程，停用后不残留运行句柄。"""
    plugin = _plugin(tmp_path)
    provider = MagicMock()
    thread = MagicMock()
    thread.is_alive.return_value = False
    plugin._lang_provider = provider
    plugin._lang_thread = thread

    helper = MagicMock()
    monkeypatch.setattr(plexautolanguages, "MediaServerHelper", lambda: helper)
    plugin.init_plugin({"enabled": False})

    provider.stop.assert_called_once_with()
    thread.join.assert_called_once_with(timeout=10)
    assert plugin.get_state() is False
    assert plugin._lang_provider is None
    assert plugin._lang_thread is None
    assert plugin.get_page() is None


def test_plugin_reload_does_not_replace_thread_that_failed_to_stop(tmp_path: Path, monkeypatch) -> None:
    """旧线程未在等待窗口内退出时不得覆盖句柄或启动第二个监听线程。"""
    plugin = _plugin(tmp_path)
    provider = MagicMock()
    thread = MagicMock()
    thread.is_alive.return_value = True
    plugin._lang_provider = provider
    plugin._lang_thread = thread

    helper = MagicMock()
    new_provider = MagicMock()
    monkeypatch.setattr(plexautolanguages, "MediaServerHelper", lambda: helper)
    monkeypatch.setattr(plexautolanguages, "LanguageProvider", new_provider)

    plugin.init_plugin(
        {
            "enabled": True,
            "auto_switch": True,
            "mediaserver": "Plex",
        }
    )

    provider.stop.assert_called_once_with()
    thread.join.assert_called_once_with(timeout=10)
    assert plugin.stop_service() is False
    assert plugin.get_state() is False
    assert plugin._lang_provider is provider
    assert plugin._lang_thread is thread
    new_provider.assert_not_called()


def test_connection_retry_wait_is_cancelled_by_stop_event(monkeypatch) -> None:
    """Plex 连接失败后的等待必须响应停止事件，不能留下长时间重试线程。"""
    stop_event = threading.Event()
    server = object.__new__(PlexServer)
    server._stop_event = stop_event
    session = MagicMock()

    def fail_and_stop(*_args, **_kwargs):
        stop_event.set()
        raise plexautolanguages.core.plex_server.RequestsConnectionError("offline")

    monkeypatch.setattr(
        plexautolanguages.core.plex_server,
        "BasePlexServer",
        fail_and_stop,
    )

    assert server._get_server("http://plex.example", "token", session) is None


def test_stop_service_reports_quiesce_result(tmp_path: Path) -> None:
    """宿主需要显式结果区分已停止线程和仍存活线程。"""
    plugin = _plugin(tmp_path)
    plugin._lang_provider = MagicMock()
    plugin._lang_thread = MagicMock()
    plugin._lang_thread.is_alive.return_value = False

    assert plugin.stop_service() is True
    assert plugin._lang_provider is None
    assert plugin._lang_thread is None


def test_plugin_start_uses_data_path_and_stops_cleanly(tmp_path: Path, monkeypatch) -> None:
    """自动切换启动时用户配置落入数据目录，停用时线程可收敛。"""
    plugin = _plugin(tmp_path)
    helper = MagicMock()
    helper.get_service.return_value = _service()
    provider = MagicMock()
    thread = MagicMock()
    thread.is_alive.return_value = False

    monkeypatch.setattr(plexautolanguages, "MediaServerHelper", lambda: helper)
    monkeypatch.setattr(plexautolanguages, "LanguageProvider", lambda **_kwargs: provider)
    monkeypatch.setattr(plexautolanguages.threading, "Thread", lambda **_kwargs: thread)

    plugin.init_plugin(
        {
            "enabled": True,
            "auto_switch": True,
            "mediaserver": "Plex",
            "update_level": "season",
            "update_strategy": "next",
            "trigger_on_play": False,
            "trigger_on_scan": True,
        }
    )

    assert plugin.get_state() is True
    assert (tmp_path / "user.yaml").is_file()
    thread.start.assert_called_once_with()
    plugin.stop_service()
    provider.stop.assert_called_once_with()
    thread.join.assert_called_once_with(timeout=10)
    assert plugin._lang_provider is None
    assert plugin._lang_thread is None
