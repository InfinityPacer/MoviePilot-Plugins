"""新增插件最低测试目录门禁。"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
CHECKER = REPO_ROOT / "scripts/check_new_plugin_tests.py"
PR_WORKFLOW = REPO_ROOT / ".github/workflows/plugin-gate.yml"


def _init_repo(repo: Path) -> None:
    """初始化临时 Git 仓库，并准备 main 与 feature 分支。"""
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo, check=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=repo, check=True)
    (repo / "README.md").write_text("fixture\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "base"], cwd=repo, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature"], cwd=repo, check=True)


def _copy_checker(repo: Path) -> None:
    """把当前 checker 拷入临时仓库，便于按真实命令运行。"""
    target = repo / "scripts/check_new_plugin_tests.py"
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(CHECKER, target)


def _run_checker(repo: Path, base_ref: str = "main") -> subprocess.CompletedProcess[str]:
    """运行新增插件门禁。"""
    return subprocess.run(
        ["python3", "scripts/check_new_plugin_tests.py", "--base-ref", base_ref],
        cwd=repo,
        text=True,
        capture_output=True,
        check=False,
    )


def test_new_v2_plugin_without_tests_is_rejected(tmp_path: Path) -> None:
    """当前分支新增插件目录但没有对应测试时必须失败。"""
    _init_repo(tmp_path)
    _copy_checker(tmp_path)
    plugin_dir = tmp_path / "plugins.v2/newplugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text("class NewPlugin:\n    pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "plugins.v2/newplugin" in result.stdout
    assert "tests/v2/newplugin/test_*.py" in result.stdout


def test_new_v2_plugin_with_test_file_is_accepted(tmp_path: Path) -> None:
    """新增插件存在对应 test_*.py 时通过最低测试目录门禁。"""
    _init_repo(tmp_path)
    _copy_checker(tmp_path)
    (tmp_path / "plugins.v2/newplugin").mkdir(parents=True)
    (tmp_path / "plugins.v2/newplugin/__init__.py").write_text("class NewPlugin:\n    pass\n", encoding="utf-8")
    (tmp_path / "tests/v2/newplugin").mkdir(parents=True)
    (tmp_path / "tests/v2/newplugin/test_plugin.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    result = _run_checker(tmp_path)

    assert result.returncode == 0, result.stdout + result.stderr


def test_untracked_new_plugin_without_tests_is_rejected(tmp_path: Path) -> None:
    """本地未暂存的新插件也应进入 preflight 检查。"""
    _init_repo(tmp_path)
    _copy_checker(tmp_path)
    plugin_dir = tmp_path / "plugins.v2/newplugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text("class NewPlugin:\n    pass\n", encoding="utf-8")

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "plugins.v2/newplugin" in result.stdout


def test_new_v1_plugin_without_tests_is_rejected(tmp_path: Path) -> None:
    """v1 插件新增目录也必须提交 tests/v1 下的测试文件。"""
    _init_repo(tmp_path)
    _copy_checker(tmp_path)
    plugin_dir = tmp_path / "plugins/newplugin"
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "__init__.py").write_text("class NewPlugin:\n    pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    result = _run_checker(tmp_path)

    assert result.returncode == 1
    assert "plugins/newplugin" in result.stdout
    assert "tests/v1/newplugin/test_*.py" in result.stdout


def test_existing_plugin_without_tests_is_not_rejected(tmp_path: Path) -> None:
    """base 分支已存在的历史插件不由新增插件门禁追溯补测。"""
    _init_repo(tmp_path)
    (tmp_path / "plugins.v2/oldplugin").mkdir(parents=True)
    (tmp_path / "plugins.v2/oldplugin/__init__.py").write_text("class OldPlugin:\n    pass\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "add old plugin"], cwd=tmp_path, check=True)
    subprocess.run(["git", "checkout", "-q", "-b", "feature2"], cwd=tmp_path, check=True)
    _copy_checker(tmp_path)
    subprocess.run(["git", "add", "."], cwd=tmp_path, check=True)

    result = _run_checker(tmp_path, base_ref="feature")

    assert result.returncode == 0, result.stdout + result.stderr


def test_pr_workflow_runs_new_plugin_test_gate() -> None:
    """PR Required Check 应执行新增插件最低测试目录门禁。"""
    workflow = PR_WORKFLOW.read_text(encoding="utf-8")

    assert "name: Check new plugin tests" in workflow
    assert "fetch-depth: 0" in workflow
    assert "scripts/check_new_plugin_tests.py --base-ref origin/main" in workflow


def test_readme_documents_new_plugin_test_gate() -> None:
    """测试说明应明确新增插件先进入最低测试目录门禁，而非直接 A 档覆盖率。"""
    readme = (REPO_ROOT / "tests/README.md").read_text(encoding="utf-8")

    assert "新增插件最低测试门禁" in readme
    assert "tests/<v1|v2>/<plugin_id>/test_*.py" in readme
    assert "不会自动加入 A 档覆盖率门禁" in readme
