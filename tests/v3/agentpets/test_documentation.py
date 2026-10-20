"""后端生产与测试定义均需说明契约，避免目录重构后遗漏私有或嵌套函数"""

import ast
import re
from pathlib import Path
from urllib.parse import urljoin

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


def test_built_archive_worker_stays_inside_the_plugin_asset_directory():
    """The production worker URL must resolve beside the federated Config chunk."""
    assets = PLUGIN_ROOT / "frontend" / "dist" / "assets"
    chunks = list(assets.glob("Config.vue*.js"))
    assert len(chunks) == 1
    source = chunks[0].read_text(encoding="utf-8")
    match = re.search(r"new URL\(['\"]([^'\"]*archive\.worker-[^'\"]+\.js)['\"], import\.meta\.url\)", source)
    assert match, "Built worker must use a relative URL, not the host's /assets path"
    base = "https://mp.test/api/v1/plugin/file/AgentPets/frontend/dist/assets/"
    assert urljoin(base + chunks[0].name, match[1]) == base + Path(match[1]).name
    assert (assets / match[1]).is_file()
