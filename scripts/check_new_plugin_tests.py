#!/usr/bin/env python3
"""检查新增插件是否至少提交对应测试目录。

该门禁只约束当前 PR 新增的插件目录，不追溯历史插件；A 档覆盖率仍由
``plugin_quality.json`` 显式声明。
"""

from __future__ import annotations

import argparse
import subprocess
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class NewPlugin:
    """新增插件目录与对应测试目录。"""

    generation: str
    plugin: str

    @property
    def source_path(self) -> str:
        """插件源码目录。"""
        base = "plugins.v2" if self.generation == "v2" else "plugins"
        return f"{base}/{self.plugin}"

    @property
    def test_path(self) -> Path:
        """插件测试目录。"""
        return REPO_ROOT / "tests" / self.generation / self.plugin


def _run_git(args: list[str]) -> subprocess.CompletedProcess[str]:
    """运行 git 命令并返回结果。"""
    return subprocess.run(
        ["git", *args],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )


def _path_exists_in_ref(base_ref: str, path: str) -> bool:
    """判断指定路径是否存在于 base ref 的 Git tree。"""
    result = _run_git(["cat-file", "-e", f"{base_ref}:{path}"])
    return result.returncode == 0


def _changed_files(base_ref: str) -> list[str]:
    """读取 base ref 到当前 HEAD/工作区的变更文件。

    CI 中 HEAD 是 PR 提交；本地开发时也纳入未提交改动，便于 preflight 检查新增插件目录。
    """
    result = _run_git(["diff", "--name-only", f"{base_ref}...HEAD"])
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise RuntimeError(f"无法计算新增插件：git diff {base_ref}...HEAD 失败。{detail}")
    files = set(result.stdout.splitlines())
    worktree = _run_git(["diff", "--name-only"])
    if worktree.returncode == 0:
        files.update(worktree.stdout.splitlines())
    staged = _run_git(["diff", "--cached", "--name-only"])
    if staged.returncode == 0:
        files.update(staged.stdout.splitlines())
    untracked = _run_git(["ls-files", "--others", "--exclude-standard"])
    if untracked.returncode == 0:
        files.update(untracked.stdout.splitlines())
    return sorted(file for file in files if file)


def collect_new_plugins(base_ref: str) -> list[NewPlugin]:
    """从 Git diff 收集当前分支新增的 v1/v2 插件目录。"""
    plugins: dict[tuple[str, str], NewPlugin] = {}
    for file in _changed_files(base_ref):
        parts = Path(file).parts
        if len(parts) < 2:
            continue
        if parts[0] == "plugins.v2":
            generation = "v2"
        elif parts[0] == "plugins":
            generation = "v1"
        else:
            continue
        plugin = parts[1]
        source_path = f"{parts[0]}/{plugin}"
        if _path_exists_in_ref(base_ref, source_path):
            continue
        if not (REPO_ROOT / source_path).is_dir():
            continue
        plugins[(generation, plugin)] = NewPlugin(generation=generation, plugin=plugin)
    return [plugins[key] for key in sorted(plugins)]


def has_test_file(plugin: NewPlugin) -> bool:
    """判断新增插件是否存在至少一个 test_*.py。"""
    return plugin.test_path.is_dir() and any(plugin.test_path.glob("test_*.py"))


def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(description="Check new plugins have pytest tests.")
    parser.add_argument("--base-ref", default="origin/main", help="用于判断新增插件的基准引用")
    return parser.parse_args()


def main() -> int:
    """命令入口。"""
    args = parse_args()
    try:
        new_plugins = collect_new_plugins(args.base_ref)
    except RuntimeError as err:
        print(err)
        return 1

    missing = [plugin for plugin in new_plugins if not has_test_file(plugin)]
    if missing:
        print("新增插件缺少最低测试目录：")
        for plugin in missing:
            print(f"- {plugin.source_path} 需要 tests/{plugin.generation}/{plugin.plugin}/test_*.py")
        return 1
    if new_plugins:
        print("新增插件最低测试目录门禁通过：")
        for plugin in new_plugins:
            print(f"- {plugin.source_path}")
    else:
        print("未发现新增插件目录")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
