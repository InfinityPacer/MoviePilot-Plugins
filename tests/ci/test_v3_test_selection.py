"""V3 测试入口的代际与兼容插件筛选合同。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.run import compatible_v2_test_targets


def _write_test(tests_dir: Path, plugin_id: str) -> None:
    """创建一个最小插件测试目录。"""
    plugin_dir = tests_dir / "v2" / plugin_id
    plugin_dir.mkdir(parents=True)
    (plugin_dir / "test_plugin.py").write_text("def test_smoke():\n    assert True\n", encoding="utf-8")


def _write_package(path: Path, package: dict) -> None:
    """写入最小 v2 插件索引。"""
    path.write_text(json.dumps(package), encoding="utf-8")


def test_v2_selection_uses_manifest_compatibility_flag(tmp_path: Path) -> None:
    """未阻断的旧实现自动进入 V3 回归，显式不兼容项自动排除。"""
    tests_dir = tmp_path / "tests"
    _write_test(tests_dir, "compatible")
    _write_test(tests_dir, "blocked")
    package_path = tmp_path / "package.v2.json"
    _write_package(
        package_path,
        {
            "Compatible": {"version": "1.0.0"},
            "Blocked": {"version": "1.0.0", "v3": False},
        },
    )

    targets = compatible_v2_test_targets(tests_dir=tests_dir, package_path=package_path)

    assert [target.name for target in targets] == ["compatible"]


def test_v2_selection_rejects_test_directory_missing_from_manifest(tmp_path: Path) -> None:
    """测试目录无法映射索引时失败关闭，避免兼容范围脱离市场元数据。"""
    tests_dir = tmp_path / "tests"
    _write_test(tests_dir, "orphan")
    package_path = tmp_path / "package.v2.json"
    _write_package(package_path, {})

    with pytest.raises(RuntimeError, match="没有对应插件条目"):
        compatible_v2_test_targets(tests_dir=tests_dir, package_path=package_path)
