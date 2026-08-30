"""AutoDiagnosis V3 的 SDK 边界、历史查询和生命周期合同测试。"""

from __future__ import annotations

import ast
import threading
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock

import app.plugins.autodiagnosis as autodiagnosis
from app.plugins.autodiagnosis import AutoDiagnosis
from app.schemas import NotificationType
from app.schemas.types import EventType
from app.sdk.events import Event
from app.sdk.queries import MAX_QUERY_PAGE_SIZE, QueryPage, TransferHistorySnapshot


PLUGIN_ROOT = Path(__file__).parents[3] / "plugins.v3" / "autodiagnosis"


def _plugin() -> AutoDiagnosis:
    """构造不触发宿主 Chain 初始化的插件逻辑测试实例。"""
    plugin = object.__new__(AutoDiagnosis)
    plugin._enabled = False
    plugin._cron = None
    plugin._onlyonce = False
    plugin._notify = "on_error"
    plugin._notify_type = "Plugin"
    plugin._execute_when_system_error = False
    plugin._health_check_modules = []
    plugin._health_check_sites = []
    plugin._history_link_check = None
    plugin._history_link_mode = "link"
    plugin._dir_link_check = None
    plugin._last_execute_time = None
    plugin._last_execute_for_error_time = None
    plugin._scheduler = None
    plugin._event = threading.Event()
    plugin._module_manager = MagicMock()
    return plugin


def _history(
    history_id: int,
    *,
    mode: str,
    date: str,
) -> TransferHistorySnapshot:
    """构造满足公开整理历史快照合同的测试记录。"""
    return TransferHistorySnapshot(
        id=history_id,
        mode=mode,
        date=date,
        src=f"/downloads/{history_id}.mkv",
        dest=f"/media/{history_id}.mkv",
        status=True,
    )


def test_v3_source_uses_public_sdk_boundaries() -> None:
    """V3 实现使用公开 SDK，不重新依赖旧宿主路径或 ORM 会话。"""
    source_path = PLUGIN_ROOT / "__init__.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"), filename=str(source_path))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert {
        "app.sdk.config",
        "app.sdk.events",
        "app.sdk.logging",
        "app.sdk.network",
        "app.sdk.plugins",
        "app.sdk.queries",
        "app.sdk.utilities",
    } <= imported_modules
    assert not any(
        module.startswith(("app.compat", "app.core", "app.helper", "app.log", "app.utils", "app.db"))
        for module in imported_modules
    )
    assert "sqlalchemy.orm" not in imported_modules


def test_v3_metadata_and_empty_capabilities_are_explicit() -> None:
    """插件元数据和无额外扩展能力符合 V3 运行时合同。"""
    plugin = _plugin()

    assert AutoDiagnosis.plugin_version == "2.0.0"
    assert AutoDiagnosis.plugin_name == "自动诊断"
    assert plugin.get_state() is False
    assert plugin.get_command() == []
    assert plugin.get_api() == []
    assert plugin.get_page() is None
    assert plugin.get_service() == []


def test_get_service_exposes_cron_job_only_when_enabled() -> None:
    """周期诊断由宿主服务目录托管，停用或缺少 cron 时不注册任务。"""
    plugin = _plugin()
    plugin._enabled = True
    plugin._cron = "0 8 * * *"

    services = plugin.get_service()

    assert len(services) == 1
    assert services[0]["id"] == "AutoDiagnosis"
    assert services[0]["func"] == plugin.auto_diagnosis

    plugin._enabled = False
    assert plugin.get_service() == []


def test_init_plugin_resets_empty_configuration(monkeypatch) -> None:
    """重载空配置时停用插件并清空旧检查选项。"""
    plugin = _plugin()
    plugin._enabled = True
    plugin._cron = "0 8 * * *"
    plugin._health_check_modules = ["all"]
    plugin._health_check_sites = ["github.com"]
    plugin._history_link_check = "all"
    plugin._dir_link_check = "/src:/dest"
    monkeypatch.setattr(autodiagnosis, "ModuleManager", lambda: MagicMock())

    plugin.init_plugin()

    assert plugin.get_state() is False
    assert plugin._cron is None
    assert plugin._health_check_modules == []
    assert plugin._health_check_sites == []
    assert plugin._history_link_check is None
    assert plugin._dir_link_check is None
    assert plugin.get_service() == []


def test_history_query_reads_pages_and_filters_link_mode(monkeypatch) -> None:
    """公开查询没有 mode 筛选时，插件仍应返回最近的成功硬链接记录。"""
    plugin = _plugin()
    plugin._history_link_mode = "link"
    first_page = QueryPage(
        items=[
            _history(1, mode="copy", date="2026-08-31 12:00:00"),
            _history(2, mode="link", date="2026-08-31 11:00:00"),
            _history(3, mode="copy", date="2026-08-31 10:00:00"),
        ],
        total=MAX_QUERY_PAGE_SIZE + 1,
        page=1,
        count=MAX_QUERY_PAGE_SIZE,
    )
    second_page = QueryPage(
        items=[_history(4, mode="link", date="2026-08-31 09:00:00")],
        total=MAX_QUERY_PAGE_SIZE + 1,
        page=2,
        count=MAX_QUERY_PAGE_SIZE,
    )
    query = Mock(side_effect=[first_page, second_page])
    monkeypatch.setattr(autodiagnosis, "list_transfer_history", query)

    histories = plugin._AutoDiagnosis__list_by_count_for_link(2)

    assert [history.id for history in histories] == [2, 4]
    assert query.call_count == 2
    first_call = query.call_args_list[0]
    assert first_call.kwargs["filters"].status is True
    assert first_call.kwargs["page"].page == 1
    assert first_call.kwargs["page"].count == MAX_QUERY_PAGE_SIZE


def test_history_query_preserves_all_mode_and_date_cutoff(monkeypatch) -> None:
    """全部模式保留成功的任意整理方式，并按上次检查时间过滤。"""
    plugin = _plugin()
    plugin._history_link_mode = "all"
    query = Mock(
        return_value=QueryPage(
            items=[
                _history(1, mode="link", date="2026-08-31 12:00:00"),
                _history(2, mode="copy", date="2026-08-30 00:00:00"),
                _history(3, mode="move", date="2026-08-29 23:59:59"),
            ],
            total=3,
            page=1,
            count=MAX_QUERY_PAGE_SIZE,
        )
    )
    monkeypatch.setattr(autodiagnosis, "list_transfer_history", query)

    histories = plugin._AutoDiagnosis__list_by_date_for_link("2026-08-30 00:00:00")

    assert [history.id for history in histories] == [1]
    query.assert_called_once()


def test_history_query_rejects_invalid_count_without_query(monkeypatch) -> None:
    """无效或非正数量不应把错误值传给分页合同。"""
    plugin = _plugin()
    query = Mock()
    monkeypatch.setattr(autodiagnosis, "list_transfer_history", query)

    assert plugin._AutoDiagnosis__list_by_count_for_link("bad") == []
    assert plugin._AutoDiagnosis__list_by_count_for_link(0) == []
    query.assert_not_called()


def test_history_check_reports_no_matching_records(monkeypatch) -> None:
    """没有可检查的历史记录时返回正常的可读结果。"""
    plugin = _plugin()
    plugin._history_link_check = 10
    monkeypatch.setattr(
        plugin,
        "_AutoDiagnosis__list_by_count_for_link",
        Mock(return_value=[]),
    )

    results = plugin._AutoDiagnosis__check_history_link()

    assert results == [
        {
            "id": "history_link",
            "name": "硬链接",
            "state": True,
            "errmsg": "没有查询到相关的硬链接历史记录",
            "result": "没有查询到相关的硬链接历史记录",
        }
    ]


def test_resolve_results_falls_back_to_plugin_notification_type() -> None:
    """未知通知类型只影响发送分类，不应使诊断结果处理失败。"""
    plugin = _plugin()
    plugin._notify = "always"
    plugin._notify_type = "unknown"
    plugin.post_message = Mock()

    plugin._AutoDiagnosis__resolve_results(
        {
            "系统健康检查": (
                [{"name": "模块", "state": True, "errmsg": "", "result": "正常"}],
                False,
            )
        }
    )

    plugin.post_message.assert_called_once()
    assert plugin.post_message.call_args.kwargs["mtype"] is NotificationType.Plugin


def test_system_error_event_triggers_diagnosis() -> None:
    """启用系统错误触发后，稳定事件载荷应进入错误触发的诊断节流路径。"""
    plugin = _plugin()
    plugin._enabled = True
    plugin._execute_when_system_error = True
    plugin.auto_diagnosis = Mock()

    plugin.handle_error_event(Event(EventType.SystemError, {"message": "failure"}))

    plugin.auto_diagnosis.assert_called_once_with(trigger_by_error=True)


def test_directory_pairs_and_hardlink_helpers(tmp_path: Path) -> None:
    """目录映射解析和硬链接判断保持跨平台无状态行为。"""
    source, target = tmp_path / "source", tmp_path / "target"
    source.mkdir()
    target.mkdir()
    source_file = source / "sample.txt"
    target_file = target / "sample.txt"
    source_file.write_text("sample", encoding="utf-8")

    result, message = AutoDiagnosis._link(source_file, target_file)

    assert result == 0
    assert message == ""
    assert AutoDiagnosis.is_hardlink(source_file, target_file) is True
    assert AutoDiagnosis._AutoDiagnosis__parse_directory_pairs(
        f"{source}:{target}\n\ninvalid"
    ) == [(source, target)]


def test_stop_service_cleans_scheduler_and_interrupt_state() -> None:
    """停止服务后不应残留调度器句柄或中断标志。"""
    plugin = _plugin()
    scheduler = MagicMock()
    scheduler.running = True
    plugin._scheduler = scheduler

    plugin.stop_service()

    scheduler.remove_all_jobs.assert_called_once_with()
    scheduler.shutdown.assert_called_once_with()
    assert plugin._scheduler is None
    assert plugin._event.is_set() is False
