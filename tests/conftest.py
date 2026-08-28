"""pytest 全局引导：按目标选择 V3 实现或兼容 V3 的 v2 实现。

``tests/run.py`` 会把 v2/v3 放到独立 pytest 进程中运行；这里据本次目标路径只注入对应
插件目录，避免同一进程同时加载 ``plugins.v2`` 与 ``plugins.v3`` 的同名包。``tests/ci``
只校验仓库工具和 workflow，不需要 MoviePilot 运行时。两代插件测试都使用 V3 后端。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# 相对导入本仓薄壳，先定位同级 MoviePilot 后端并加入 ``sys.path``，再复用主程序共享引导。
from ._bootstrap import (
    block_real_network,  # noqa: F401  导入即注册主程序共享 autouse 网络守卫
    isolate_config_dir,
    prepare_v2_backend,
    prepare_v3_backend,
)


def _selected_generation(config) -> str:
    """根据 pytest 本次目标路径判断插件代际，禁止同一进程混跑 v2/v3。"""
    generations = set()
    for arg in config.args:
        file_part = arg.split("::", 1)[0]
        path = Path(file_part).resolve().as_posix().replace("\\", "/")
        if "tests/v3" in path:
            generations.add("v3")
        elif "tests/v2" in path:
            generations.add("v2")
        elif "tests/ci" in path:
            generations.add("ci")
    if len(generations) == 1:
        return next(iter(generations))
    raise RuntimeError("插件仓单测必须按 tests/run.py 分 v2/v3 独立会话运行，避免同名插件包冲突")


def pytest_configure(config) -> None:
    """收集用例前隔离 CONFIG_DIR、建表并注入对应代际插件目录。"""
    generation = _selected_generation(config)
    if generation == "ci":
        isolate_config_dir()
        return
    if generation == "v3":
        prepare_v3_backend()
        return
    prepare_v2_backend()


@pytest.fixture(autouse=True)
def configure_plugin_test_services(request):
    """为插件逻辑测试装配隔离数据库上的配置和 Chain 运行上下文。"""
    if _selected_generation(request.config) == "ci":
        yield
        return

    from app.application.chain.context import (
        ChainRuntimeContext,
        configure_chain_runtime_context_provider,
    )
    from app.application.chain.data import configure_chain_data_ports
    from app.application.configuration import SystemConfigService, configure_system_config
    from app.db.oper.systemconfig import SystemConfigOper

    port_names = (
        "site",
        "subscribe",
        "download_history",
        "transfer_history",
        "transfer_pending",
        "transfer_execution",
        "media_server",
        "download_failure",
        "user",
    )
    configure_chain_data_ports(**{name: MagicMock for name in port_names})
    context = ChainRuntimeContext(
        module_manager=MagicMock(),
        plugin_manager=MagicMock(),
        event_manager=MagicMock(),
        message_oper=MagicMock(),
        message_helper=MagicMock(),
        file_cache=MagicMock(),
        async_file_cache=MagicMock(),
        message_queue_factory=lambda _callback: MagicMock(),
        module_dispatcher_factory=lambda **_kwargs: MagicMock(),
    )
    configure_system_config(SystemConfigService(repository=SystemConfigOper()))
    configure_chain_runtime_context_provider(lambda: context)
    try:
        yield
    finally:
        configure_chain_runtime_context_provider(None)


def _report_session_cleanup_error(session, name: str, err: Exception) -> None:
    """记录收尾错误；原测试绿色时将会话标记为失败。"""
    sys.stderr.write(f"\npytest session cleanup failed: {name}: {err!r}\n")
    if session.exitstatus == 0:
        session.exitstatus = 1


def pytest_sessionfinish(session, exitstatus) -> None:
    """释放测试过程中创建的消息队列与日志后台线程"""
    if _selected_generation(session.config) == "ci":
        return

    try:
        from app.helper.message import stop_message

        stop_message()
    except Exception as err:
        _report_session_cleanup_error(session, "message service", err)

    try:
        from app.log import LoggerManager

        LoggerManager.shutdown()
    except Exception as err:
        _report_session_cleanup_error(session, "logger manager", err)
