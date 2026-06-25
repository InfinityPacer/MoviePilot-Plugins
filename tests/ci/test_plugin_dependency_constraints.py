"""插件依赖约束必须兼容当前主程序运行环境。"""

from __future__ import annotations

from pathlib import Path

import pytest
from packaging.requirements import Requirement


REPO_ROOT = Path(__file__).resolve().parents[2]
WORKSPACE_ROOT = REPO_ROOT.parent
BACKEND_REQUIREMENTS = WORKSPACE_ROOT / "MoviePilot/requirements.in"


def _normalize_package_name(package_name: str) -> str:
    """按 PEP 503 规则归一化包名，避免大小写和分隔符差异影响比对。"""
    return package_name.lower().replace("_", "-").replace(".", "-")


def _read_requirements(requirements_file: Path) -> dict[str, Requirement]:
    """读取 requirements 文件中的普通依赖声明。"""
    requirements: dict[str, Requirement] = {}
    for raw_line in requirements_file.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        requirement = Requirement(line)
        requirements[_normalize_package_name(requirement.name)] = requirement
    return requirements


def _backend_runtime_versions() -> dict[str, str]:
    """提取主程序根依赖声明中的当前运行版本。"""
    versions: dict[str, str] = {}
    for package_name, requirement in _read_requirements(BACKEND_REQUIREMENTS).items():
        compatible_release = next(
            (spec.version for spec in requirement.specifier if spec.operator == "~="),
            None,
        )
        if compatible_release:
            versions[package_name] = compatible_release
    return versions


def _plugin_dependency_cases() -> list:
    """收集所有插件依赖中与主程序根依赖同名的约束。"""
    backend_versions = _backend_runtime_versions()
    cases = []
    requirement_files = [
        *sorted((REPO_ROOT / "plugins").glob("*/requirements.txt")),
        *sorted((REPO_ROOT / "plugins.v2").glob("*/requirements.txt")),
    ]
    for requirements_file in requirement_files:
        generation = requirements_file.relative_to(REPO_ROOT).parts[0]
        plugin_id = f"{generation}/{requirements_file.parent.name}"
        for package_name, requirement in _read_requirements(requirements_file).items():
            backend_version = backend_versions.get(package_name)
            if backend_version is None:
                continue
            cases.append(
                pytest.param(
                    plugin_id,
                    requirement.name,
                    str(requirement.specifier),
                    backend_version,
                    id=f"{plugin_id}:{requirement.name}",
                )
            )
    return cases


@pytest.mark.parametrize(
    ("plugin_id", "package_name", "plugin_specifier", "backend_version"),
    _plugin_dependency_cases(),
)
def test_plugin_dependency_allows_backend_runtime_version(
        plugin_id: str,
        package_name: str,
        plugin_specifier: str,
        backend_version: str,
) -> None:
    """插件依赖不得要求低于主程序当前运行依赖的版本窗口。"""
    requirement = Requirement(f"{package_name}{plugin_specifier}")

    assert requirement.specifier.contains(
        backend_version,
        prereleases=True,
    ), (
        f"{plugin_id} 要求 {package_name}{plugin_specifier}，"
        f"不兼容主程序当前 {package_name}=={backend_version}"
    )
