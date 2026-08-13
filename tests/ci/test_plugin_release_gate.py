"""验证面向 V3 的版本校验在本地 push、PR 和 Release 三个入口保持一致。"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / ".github/scripts/check_plugin_versions.py"
PRE_PUSH = REPO_ROOT / ".githooks/pre-push"
PR_WORKFLOW = REPO_ROOT / ".github/workflows/plugin-gate.yml"
TEST_RUNNER = REPO_ROOT / "tests/run.py"


def _write_fixture(
        repo: Path,
        *,
        old_version: str = "1.2.3",
        package_version: str = "1.3",
        source_version: str = "1.3",
        legacy_v3: bool = False,
        history: dict | None = None,
) -> None:
    """构造最小 V3 插件仓，隔离验证 checker 与 Hook 的退出码。"""
    plugin_dir = repo / "plugins.v3/example"
    plugin_dir.mkdir(parents=True)
    (repo / "package.v2.json").write_text(
        json.dumps(
            {
                "Example": {
                    "name": "示例",
                    "version": old_version,
                    "v3": legacy_v3,
                }
            }
        ),
        encoding="utf-8",
    )
    (repo / "package.v3.json").write_text(
        json.dumps(
            {
                "Example": {
                    "name": "示例",
                    "version": package_version,
                    "system_version": ">=3.0.0",
                    "history": history or {f"v{package_version}": "MoviePilot V3 版本示例插件"},
                    "release": True,
                }
            }
        ),
        encoding="utf-8",
    )
    (plugin_dir / "__init__.py").write_text(
        "class Example:\n"
        f'    plugin_version = "{source_version}"\n',
        encoding="utf-8",
    )
    checker_target = repo / ".github/scripts/check_plugin_versions.py"
    checker_target.parent.mkdir(parents=True)
    shutil.copy2(CHECKER, checker_target)


def _run_checker(repo: Path, package_file: Path | str = "package.v3.json") -> subprocess.CompletedProcess[str]:
    """从指定目录运行 checker，便于覆盖 cwd 与 package 路径组合。"""
    return subprocess.run(
        ["python3", str(CHECKER), str(package_file)],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def _write_legacy_fixture(
        repo: Path,
        *,
        generation: str = "v2",
        package_version: str = "1.2",
        source_version: str = "1.2",
        v3: bool | None = None,
) -> Path:
    """构造一个可切换 V3 兼容位的旧代发布条目。"""
    package_name = "package.v2.json" if generation == "v2" else "package.json"
    source_base = "plugins.v2" if generation == "v2" else "plugins"
    metadata = {"version": package_version, "release": True}
    if v3 is not None:
        metadata["v3"] = v3
    package_path = repo / package_name
    package_path.write_text(json.dumps({"Example": metadata}), encoding="utf-8")
    plugin_dir = repo / source_base / "example"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text(
        "class Example:\n"
        f'    plugin_version = "{source_version}"\n',
        encoding="utf-8",
    )
    return package_path


def test_checker_rejects_mismatched_versions(tmp_path: Path) -> None:
    """V3 package 与源码版本不一致时必须失败。"""
    _write_fixture(tmp_path, package_version="1.3", source_version="1.4")

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "版本不一致" in result.stdout


def test_checker_resolves_plugin_dir_relative_to_package_file(tmp_path: Path) -> None:
    """从其他 cwd 调用时，插件目录应相对 package 文件定位。"""
    repo = tmp_path / "repo"
    _write_fixture(repo)

    result = _run_checker(tmp_path, repo / "package.v3.json")

    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_reports_missing_v3_plugin_dir(tmp_path: Path) -> None:
    """V3 索引插件缺少源码目录时应失败，避免发布项被静默跳过。"""
    _write_fixture(tmp_path)
    shutil.rmtree(tmp_path / "plugins.v3/example")

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "缺少插件目录" in result.stdout
    assert "plugins.v3/example" in result.stdout


def test_checker_reads_class_level_plugin_version_only(tmp_path: Path) -> None:
    """只接受类级 plugin_version，避免函数内局部变量被误识别。"""
    _write_fixture(tmp_path)
    (tmp_path / "plugins.v3/example/__init__.py").write_text(
        "def helper():\n"
        "    plugin_version = '1.3'\n"
        "    return plugin_version\n",
        encoding="utf-8",
    )

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "类级 plugin_version" in result.stdout


def test_checker_accepts_annotated_class_level_plugin_version(tmp_path: Path) -> None:
    """类级注解赋值的 plugin_version 也是有效声明。"""
    _write_fixture(tmp_path)
    (tmp_path / "plugins.v3/example/__init__.py").write_text(
        "class Example:\n"
        "    plugin_version: str = '1.3'\n",
        encoding="utf-8",
    )

    result = _run_checker(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_accepts_minor_version_increase() -> None:
    """V3 沿用主版本并提升小版本时通过。"""
    result = _run_checker(REPO_ROOT)

    assert result.returncode == 0, result.stdout


def test_checker_validates_compatible_legacy_release(tmp_path: Path) -> None:
    """未声明 v3=false 的旧实现仍可发布，版本不一致必须失败。"""
    package_path = _write_legacy_fixture(tmp_path, source_version="1.3")

    result = _run_checker(tmp_path, package_path)

    assert result.returncode == 1
    assert "版本不一致" in result.stdout


def test_checker_validates_default_release_opted_into_v2(tmp_path: Path) -> None:
    """默认索引只有显式兼容 V2/V3 后才属于 V3 发布门禁。"""
    package_path = _write_legacy_fixture(
        tmp_path,
        generation="v1",
        source_version="1.3",
    )
    metadata = json.loads(package_path.read_text(encoding="utf-8"))
    metadata["Example"]["v2"] = True
    package_path.write_text(json.dumps(metadata), encoding="utf-8")

    result = _run_checker(tmp_path, package_path)

    assert result.returncode == 1
    assert "版本不一致" in result.stdout


def test_checker_skips_default_release_without_v2_or_v3_opt_in(tmp_path: Path) -> None:
    """普通 V1 条目不能仅因未声明 v3=false 就进入 V3 发布门禁。"""
    package_path = _write_legacy_fixture(
        tmp_path,
        generation="v1",
        source_version="9.9",
    )

    result = _run_checker(tmp_path, package_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_checker_skips_legacy_release_blocked_on_v3(tmp_path: Path) -> None:
    """v3=false 的旧实现只保留历史索引，不再参与 V3 发布门禁。"""
    package_path = _write_legacy_fixture(tmp_path, source_version="9.9", v3=False)

    result = _run_checker(tmp_path, package_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_default_index_plugins_all_have_a_v2_compatibility_path() -> None:
    """每个默认索引条目都必须有 V2 专用实现或显式声明 v2=true。"""
    default_package = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    v2_package = json.loads((REPO_ROOT / "package.v2.json").read_text(encoding="utf-8"))

    missing = sorted(
        plugin_id
        for plugin_id, metadata in default_package.items()
        if metadata.get("v2") is not True and plugin_id not in v2_package
    )

    assert missing == []


def test_checker_rejects_major_version_increase(tmp_path: Path) -> None:
    """V3 迁移绝不能提升主版本。"""
    _write_fixture(tmp_path, old_version="1.2.3", package_version="2.0", source_version="2.0")

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "不得提升主版本" in result.stdout


def test_checker_requires_legacy_v3_block(tmp_path: Path) -> None:
    """存在专用 V3 副本时旧索引必须阻止回退加载。"""
    _write_fixture(tmp_path, legacy_v3=True)

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "必须声明 v3=false" in result.stdout


def test_checker_requires_single_current_history_entry(tmp_path: Path) -> None:
    """V3 history 只允许当前版本一条标准迁移说明。"""
    _write_fixture(
        tmp_path,
        history={"v1.3": "MoviePilot V3 版本示例插件", "v1.2.3": "旧记录"},
    )

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "history 必须只保留当前版本" in result.stdout


def test_pre_push_propagates_version_gate_failure(tmp_path: Path) -> None:
    """pre-push 必须传播 checker 非零状态。"""
    _write_fixture(tmp_path, package_version="1.3", source_version="1.4")
    hook_target = tmp_path / ".githooks/pre-push"
    hook_target.parent.mkdir(parents=True)
    shutil.copy2(PRE_PUSH, hook_target)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    result = subprocess.run(
        ["sh", ".githooks/pre-push"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 1
    assert "插件版本门禁失败" in result.stdout


def test_pre_push_accepts_matching_versions(tmp_path: Path) -> None:
    """V3 元数据与源码一致时 pre-push 应允许上传。"""
    _write_fixture(tmp_path)
    hook_target = tmp_path / ".githooks/pre-push"
    hook_target.parent.mkdir(parents=True)
    shutil.copy2(PRE_PUSH, hook_target)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)

    result = subprocess.run(
        ["sh", ".githooks/pre-push"],
        cwd=tmp_path,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0
    assert "插件版本门禁通过" in result.stdout


def test_pr_workflow_runs_v3_gates_for_every_main_pull_request() -> None:
    """Required Check 必须覆盖 V3 版本与真实测试，且不得使用 paths 过滤。"""
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")

    assert "pull_request:" in workflow
    assert "branches:" in workflow
    assert "- main" in workflow
    assert "paths:" not in workflow
    assert "name: Plugin release gate" in workflow
    assert "python .github/scripts/check_plugin_versions.py package.json package.v2.json package.v3.json" in workflow
    assert "name: Plugin test gate" in workflow
    assert "ref: v3" in workflow
    assert "python tests/run.py" in workflow


def test_full_test_runner_includes_v3_and_compatible_v2_tests() -> None:
    """全量入口执行 CI、V3 专用实现和动态筛选的兼容 v2 实现。"""
    runner = TEST_RUNNER.read_text(encoding="utf-8")

    assert 'for generation in ("ci", "v3", "v2"):' in runner
    assert "compatible_v2_test_targets" in runner
