"""插件覆盖率门禁配置与统计脚本测试。"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
COVERAGE_SCRIPT = REPO_ROOT / "scripts/plugin_coverage.py"
QUALITY_CONFIG = REPO_ROOT / "plugin_quality.json"
PR_WORKFLOW = REPO_ROOT / ".github/workflows/plugin-gate.yml"


def _load_coverage_module():
    """按文件路径导入覆盖率脚本，避免要求 scripts/ 成为 Python 包。"""
    spec = importlib.util.spec_from_file_location("plugin_coverage", COVERAGE_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_quality_config_targets_subscription_plugins() -> None:
    """A 档覆盖率门禁只默认锁定两个已有稳定覆盖基线的订阅插件。"""
    config = json.loads(QUALITY_CONFIG.read_text(encoding="utf-8"))

    targets = {(item["generation"], item["plugin"]) for item in config["coverage"]}

    assert targets == {
        ("v2", "subscribeassistant"),
        ("v2", "subscribeassistantenhanced"),
    }
    for item in config["coverage"]:
        assert item["line"] == 90
        assert item["method"] == 90
        assert item["changed_line"] == 90


def test_method_coverage_counts_executed_functions(tmp_path: Path) -> None:
    """方法覆盖率以函数体内可执行语句是否命中过为准。"""
    module = _load_coverage_module()
    source = tmp_path / "plugin.py"
    source.write_text(
        "def covered():\n"
        "    return 1\n"
        "\n"
        "def missed():\n"
        "    return 2\n",
        encoding="utf-8",
    )
    file_report = {
        "executed_lines": [2],
        "missing_lines": [5],
    }

    result = module.calculate_method_coverage(source, file_report)

    assert result.total == 2
    assert result.covered == 1
    assert result.percent == 50


def test_method_coverage_ignores_executed_definition_line(tmp_path: Path) -> None:
    """函数 import 只执行 def 行，不能被误计为方法已覆盖。"""
    module = _load_coverage_module()
    source = tmp_path / "plugin.py"
    source.write_text(
        "def imported_only():\n"
        "    return 1\n",
        encoding="utf-8",
    )
    file_report = {
        "executed_lines": [1],
        "missing_lines": [2],
    }

    result = module.calculate_method_coverage(source, file_report)

    assert result.total == 1
    assert result.covered == 0


def test_method_coverage_ignores_nested_local_functions(tmp_path: Path) -> None:
    """方法覆盖率只统计模块函数和类方法，不把局部闭包算作独立方法。"""
    module = _load_coverage_module()
    source = tmp_path / "plugin.py"
    source.write_text(
        "def outer():\n"
        "    def helper():\n"
        "        return 1\n"
        "    return helper()\n",
        encoding="utf-8",
    )
    file_report = {
        "executed_lines": [3, 4],
        "missing_lines": [],
    }

    result = module.calculate_method_coverage(source, file_report)

    assert result.total == 1
    assert result.covered == 1


def test_changed_line_coverage_ignores_non_executable_lines() -> None:
    """新增行覆盖率只统计 coverage 认为可执行的新增/变更语句。"""
    module = _load_coverage_module()
    changed_lines = {
        "plugins.v2/demo/plugin.py": {1, 2, 3, 4},
    }
    report_files = {
        "plugins.v2/demo/plugin.py": {
            "executed_lines": [2],
            "missing_lines": [4],
        }
    }

    result = module.calculate_changed_line_coverage(changed_lines, report_files)

    assert result.total == 2
    assert result.covered == 1
    assert result.percent == 50


def test_changed_line_collection_fails_when_base_ref_is_invalid(monkeypatch) -> None:
    """CI 传入基准分支时，无法计算 diff 必须失败，不能按 0/0 静默放行。"""
    module = _load_coverage_module()

    def fake_run(*_args, **_kwargs):
        return type("Result", (), {"returncode": 128, "stderr": "bad revision"})()

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    try:
        module.collect_changed_lines("origin/missing", ["plugins.v2/demo"])
    except RuntimeError as err:
        assert "无法计算新增行覆盖率" in str(err)
    else:
        raise AssertionError("invalid base ref should fail closed")


def test_coverage_environment_clears_runtime_config_dir(monkeypatch) -> None:
    """coverage 运行环境必须隔离真实 CONFIG_DIR，同时补齐后端源码路径。"""
    module = _load_coverage_module()
    monkeypatch.setenv("CONFIG_DIR", "/private/runtime-config")
    monkeypatch.delenv("MOVIEPILOT_BACKEND_PATH", raising=False)

    env = module.build_test_env()

    assert "CONFIG_DIR" not in env
    assert env["MOVIEPILOT_BACKEND_PATH"].endswith("/MoviePilot")


def test_pr_workflow_runs_plugin_coverage_gate() -> None:
    """PR Required Check 应执行插件覆盖率门禁并上传报告，便于贡献者定位缺口。"""
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")

    assert "name: Plugin coverage gate" in workflow
    assert "scripts/plugin_coverage.py" in workflow
    assert "MOVIEPILOT_BACKEND_PATH" in workflow
    assert "Determine whether coverage gate is required" in workflow
    assert "steps.coverage-scope.outputs.run == 'true'" in workflow
    assert "MoviePilot/requirements-dev.in" in workflow
    assert "coverage==" not in workflow
    assert "actions/upload-artifact" in workflow


def test_pr_workflow_derives_scope_from_quality_config_and_test_harness() -> None:
    """coverage gate 触发范围应跟随配置目标，并覆盖共享测试基建。"""
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")

    assert "plugin_quality.json" in workflow
    assert "json.load" in workflow
    for path in ("pytest.ini", "tests/conftest.py", "tests/_bootstrap.py", "tests/run.py"):
        assert path in workflow


def test_readme_documents_ci_equivalent_changed_line_command() -> None:
    """本地文档应区分快速检查和 CI 等价的变更行覆盖率检查。"""
    readme = (REPO_ROOT / "tests/README.md").read_text(encoding="utf-8")

    assert "快速检查" in readme
    assert "CI 等价检查" in readme
    assert "--base-ref origin/main" in readme
    assert "env -u CONFIG_DIR" in readme


def test_generated_coverage_reports_are_ignored() -> None:
    """coverage-reports 是 CI/本地可再生产物，不应进入插件市场仓。"""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")

    assert "coverage-reports/" in gitignore
