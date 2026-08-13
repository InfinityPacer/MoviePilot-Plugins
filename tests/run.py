"""插件仓 V3 单测入口：CI 工具、V3 专用实现与兼容的 v2 实现分别运行。

``package.v2.json`` 是旧实现能否在 V3 加载的唯一事实源：存在测试且未声明 ``v3: false``
的 v2 插件继续使用 V3 后端回归。它们与 ``plugins.v3`` 的专用实现放在独立子进程中，
避免同名插件包冲突。CI 工具测试不加载插件运行时。任一组非零退出码即整体失败。
"""
import json
import subprocess
import sys
from pathlib import Path

# 本文件位于 tests/ 下：其父为 tests 目录，再上一级为插件仓根
_TESTS_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _TESTS_DIR.parent
_V2_PACKAGE = _REPO_ROOT / "package.v2.json"


def _contains_tests(path: Path) -> bool:
    """判断目录中是否存在 pytest 用例文件。"""
    return path.is_dir() and any(path.rglob("test_*.py"))


def compatible_v2_test_targets(
        tests_dir: Path = _TESTS_DIR,
        package_path: Path = _V2_PACKAGE,
) -> list[Path]:
    """按 v2 索引动态收集仍兼容 V3 的插件测试目录。

    测试目录必须能大小写无关地映射到索引插件 ID；缺少索引时失败关闭，避免新测试因
    元数据遗漏而被错误纳入或排除。只有显式 ``v3: false`` 的插件会被跳过。
    """
    package = json.loads(package_path.read_text(encoding="utf-8"))
    metadata_by_id = {plugin_id.casefold(): metadata for plugin_id, metadata in package.items()}
    targets = []
    for test_dir in sorted((tests_dir / "v2").iterdir()):
        if not _contains_tests(test_dir):
            continue
        metadata = metadata_by_id.get(test_dir.name.casefold())
        if metadata is None:
            raise RuntimeError(f"tests/v2/{test_dir.name} 在 package.v2.json 中没有对应插件条目")
        if metadata.get("v3") is False:
            continue
        targets.append(test_dir)
    return targets


def _generation_targets(generation: str) -> list[Path]:
    """返回某个独立 pytest 会话的测试目标。"""
    if generation == "v2":
        return compatible_v2_test_targets()
    target = _TESTS_DIR / generation
    return [target] if _contains_tests(target) else []


def _run_generation(generation: str, extra_args: list) -> int:
    """在独立子进程运行一个测试分组；该组无用例则跳过。"""
    targets = _generation_targets(generation)
    if not targets:
        return 0
    return subprocess.call(
        [sys.executable, "-m", "pytest", *(str(target) for target in targets), *extra_args],
        cwd=str(_REPO_ROOT),
    )


if __name__ == "__main__":
    extra = sys.argv[1:]
    exit_code = 0
    # CI 工具、V3 专用实现与兼容 V3 的旧实现分会话运行。
    for generation in ("ci", "v3", "v2"):
        rc = _run_generation(generation, extra)
        exit_code = exit_code or rc
    sys.exit(exit_code)
