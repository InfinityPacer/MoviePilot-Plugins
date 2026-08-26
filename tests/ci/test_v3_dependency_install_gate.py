"""V3 插件依赖真实安装门禁测试。"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
INSTALL_SCRIPT = REPO_ROOT / "scripts/check_v3_dependency_install.py"
PR_WORKFLOW = REPO_ROOT / ".github/workflows/plugin-gate.yml"


def _load_install_module():
    """按文件路径导入安装门禁脚本。"""
    spec = importlib.util.spec_from_file_location(
        "check_v3_dependency_install",
        INSTALL_SCRIPT,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_manifest_discovery_covers_every_v3_pyproject() -> None:
    """门禁必须自动覆盖全部 V3 modern manifest 并拒绝静态白名单。"""
    module = _load_install_module()
    expected = sorted((REPO_ROOT / "plugins.v3").glob("*/pyproject.toml"))

    assert expected
    assert module.discover_manifests() == expected


def test_installation_uses_fresh_environment_and_host_manifest_semantics(
    tmp_path: Path,
) -> None:
    """安装命令必须面向隔离解释器并通过 -r 消费原始 pyproject。"""
    module = _load_install_module()
    environment = tmp_path / ".venv"
    manifest = REPO_ROOT / "plugins.v3/plexpersonmeta/pyproject.toml"

    create, install, healthcheck = module.installation_commands(
        uv_bin="uv",
        python_spec="3.14",
        environment=environment,
        manifest=manifest,
        windows=False,
    )

    python_bin = environment / "bin/python"
    assert create == ["uv", "venv", "--python", "3.14", str(environment)]
    assert install == [
        "uv",
        "pip",
        "install",
        "--python",
        str(python_bin),
        "-r",
        str(manifest),
    ]
    assert healthcheck == ["uv", "pip", "check", "--python", str(python_bin)]


def test_windows_environment_uses_scripts_python(tmp_path: Path) -> None:
    """Windows runner 必须把依赖安装到目标 venv，而不是 runner 全局环境。"""
    module = _load_install_module()

    assert module.venv_python(tmp_path / ".venv", windows=True) == (
        tmp_path / ".venv/Scripts/python.exe"
    )


def test_workflow_runs_five_platform_install_matrix() -> None:
    """PR 门禁应覆盖 V3 声明支持的五个平台并执行真实安装脚本。"""
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")
    job_start = workflow.index("  plugin-dependency-install-gate:")
    job_end = workflow.index("\n  plugin-coverage-gate:", job_start)
    install_job = workflow[job_start:job_end]

    for runner in (
        "ubuntu-latest",
        "ubuntu-24.04-arm",
        "windows-latest",
        "macos-15-intel",
        "macos-15",
    ):
        assert f"os: {runner}" in install_job
    assert "name: V3 dependency install (${{ matrix.name }})" in install_job
    assert "runs-on: ${{ matrix.os }}" in install_job
    assert "scripts/check_v3_dependency_install.py --python 3.14" in install_job
    assert "fail-fast: false" in install_job
