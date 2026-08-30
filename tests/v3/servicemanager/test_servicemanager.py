"""ServiceManager V3 的公开入口和调度接管生命周期测试。"""

import ast
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.plugins.servicemanager import ServiceManager


REPO_ROOT = Path(__file__).resolve().parents[3]
PLUGIN_SOURCE = REPO_ROOT / "plugins.v3/servicemanager/__init__.py"


class _FakeApscheduler:
    """记录任务投影，避免测试启动真实后台线程。"""

    def __init__(self, jobs=None):
        self.jobs = list(jobs or [])
        self.added = []
        self.removed = []

    def get_jobs(self):
        return list(self.jobs)

    def add_job(self, func, trigger, **kwargs):
        job = SimpleNamespace(
            id=kwargs["id"],
            trigger=trigger,
            name=kwargs.get("name"),
            kwargs=kwargs.get("kwargs", {}),
        )
        self.jobs = [item for item in self.jobs if item.id != job.id]
        self.jobs.append(job)
        self.added.append((func, trigger, kwargs))
        return job

    def remove_job(self, job_id):
        self.removed.append(job_id)
        self.jobs = [item for item in self.jobs if item.id != job_id]


class _FakeScheduler:
    """提供 ServiceManager 所需的最小 Scheduler 状态合同。"""

    def __init__(self):
        self._lock = threading.RLock()
        self._scheduler = _FakeApscheduler(
            [
                SimpleNamespace(
                    id="sitedata_refresh",
                    trigger="system-trigger",
                    name="站点数据刷新",
                    kwargs={"job_id": "sitedata_refresh"},
                )
            ]
        )
        self._jobs = {
            "sitedata_refresh": {
                "func": "system-func",
                "name": "站点数据刷新",
                "kwargs": {"job_id": "sitedata_refresh"},
                "running": False,
            }
        }
        self.removed_plugin_ids = []
        self.updated_plugin_ids = []

    def update_plugin_job(self, pid):
        self.updated_plugin_ids.append(pid)

    def remove_plugin_job(self, pid):
        self.removed_plugin_ids.append(pid)
        self._jobs.pop(pid, None)

    def init(self):
        raise AssertionError("本测试不应需要重建 Scheduler")

    def start(self, job_id, **kwargs):
        return (job_id, kwargs)


@pytest.fixture
def clean_service_manager_state(monkeypatch):
    """隔离插件类级 hook 和接管映射，避免污染其它插件测试。"""
    monkeypatch.setattr(ServiceManager, "_start_redirects", {})
    monkeypatch.setattr(ServiceManager, "_plugin_job_aliases", {})
    monkeypatch.setattr(ServiceManager, "_running_redirects", {})
    monkeypatch.setattr(ServiceManager, "_system_job_templates", {})
    monkeypatch.setattr(ServiceManager, "_system_schedule_templates", {})
    monkeypatch.setattr(ServiceManager, "_absent_system_schedules", set())
    monkeypatch.setattr(ServiceManager, "_active_instance", None)
    if ServiceManager._start_hook_installed:
        ServiceManager._uninstall_start_hook()
    if ServiceManager._init_hook_installed:
        ServiceManager._uninstall_init_hook()
    yield
    if ServiceManager._start_hook_installed:
        ServiceManager._uninstall_start_hook()
    if ServiceManager._init_hook_installed:
        ServiceManager._uninstall_init_hook()


def _plugin() -> ServiceManager:
    """构造不触发宿主插件 Runtime 的测试实例。"""
    plugin = object.__new__(ServiceManager)
    plugin._enabled = True
    plugin._sitedata_refresh = "0 * * * *"
    plugin._subscribe_search = ""
    plugin._clear_cache = ""
    plugin._random_wallpager = ""
    plugin._subscribe_tmdb = ""
    return plugin


def test_v3_source_uses_public_config_logging_and_plugin_manager():
    """新代实现不再依赖旧 core/log/plugin 兼容路径。"""
    tree = ast.parse(PLUGIN_SOURCE.read_text(encoding="utf-8"), filename=str(PLUGIN_SOURCE))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }

    assert {
        "app.sdk.config",
        "app.sdk.logging",
        "app.sdk.plugins",
        "app.scheduler",
    } <= imported_modules
    assert not any(
        module.startswith(("app.compat", "app.core", "app.helper", "app.log", "app.utils"))
        for module in imported_modules
    )


def test_v3_metadata_and_readme_boundary():
    """V3 索引、类版本和旧代阻断标志一致，且不凭空新增 README。"""
    package_v3 = json.loads((REPO_ROOT / "package.v3.json").read_text(encoding="utf-8"))
    package_v2 = json.loads((REPO_ROOT / "package.v2.json").read_text(encoding="utf-8"))

    assert ServiceManager.plugin_version == "2.0.0"
    assert package_v3["ServiceManager"]["version"] == ServiceManager.plugin_version
    assert package_v3["ServiceManager"]["system_version"] == ">=3.0.0"
    assert list(package_v3["ServiceManager"]["history"]) == ["v2.0.0"]
    assert package_v2["ServiceManager"]["v3"] is False
    assert not (REPO_ROOT / "plugins.v3/servicemanager/README.md").exists()


def test_get_service_reuses_host_job_template(clean_service_manager_state):
    """接管任务复用宿主 callable 和参数，只替换调度触发器。"""
    plugin = _plugin()
    scheduler = _FakeScheduler()

    services = plugin.get_service()
    assert services == []

    plugin._cache_system_job_templates(scheduler)
    services = plugin.get_service()

    assert len(services) == 1
    assert services[0]["id"] == "sitedata_refresh"
    assert services[0]["func"] == "system-func"
    assert services[0]["trigger"].__class__.__name__ == "CronTrigger"


def test_takeover_and_disable_restore_scheduler_job(clean_service_manager_state, monkeypatch):
    """启停插件时移除系统投影并恢复原调度，避免遗留重复任务。"""
    plugin = _plugin()
    scheduler = _FakeScheduler()
    plugin._get_plugin_id = lambda: "ServiceManager"

    def register_plugin_job(current_scheduler, pid):
        current_scheduler._jobs[f"{pid}_sitedata_refresh"] = {
            "func": "system-func",
            "name": "站点数据刷新",
            "kwargs": {"job_id": "sitedata_refresh"},
            "running": False,
            "pid": pid,
        }

    monkeypatch.setattr(plugin, "_ensure_plugin_jobs", register_plugin_job)
    monkeypatch.setattr(plugin, "_get_scheduler_if_ready", lambda: scheduler)

    plugin._apply_takeover(scheduler)

    assert ServiceManager._start_redirects == {
        "sitedata_refresh": "ServiceManager_sitedata_refresh"
    }
    assert "sitedata_refresh" not in scheduler._jobs
    assert "sitedata_refresh" in scheduler._scheduler.removed
    assert "ServiceManager_sitedata_refresh" in scheduler._jobs

    plugin._disable_takeover()

    assert ServiceManager._start_redirects == {}
    assert scheduler._jobs["sitedata_refresh"]["func"] == "system-func"
    assert any(item[2]["id"] == "sitedata_refresh" for item in scheduler._scheduler.added)
