"""后端生产与测试定义均需说明契约，避免目录重构后遗漏私有或嵌套函数"""

import ast
from pathlib import Path

import pytest

REPOSITORY = Path(__file__).parents[3]
PLUGIN_ROOT = REPOSITORY / "plugins.v3" / "agentpets"
TEST_ROOT = Path(__file__).parent


def _backend_paths():
    """只枚举后端 Python 与对应测试，排除本轮不修改的前端依赖目录"""
    return sorted(path for root in (PLUGIN_ROOT, TEST_ROOT) for path in root.rglob("*.py")
                  if "frontend" not in path.relative_to(root).parts)


@pytest.mark.parametrize("path", _backend_paths(), ids=lambda path: str(path.relative_to(REPOSITORY)))
def test_all_backend_and_test_definitions_have_docstrings(path):
    """类、构造器、属性、测试桩及嵌套函数都必须提供非空说明"""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    missing = [f"{node.lineno}: {node.name}" for node in ast.walk(tree)
               if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
               and not ast.get_docstring(node)]
    assert not missing, "缺少 docstring：\n" + "\n".join(missing)
