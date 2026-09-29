"""V3 插件详情页声明门禁。

主程序按 ``get_page`` 函数体是否只有占位语句（pass、docstring、...）判定 ``has_page``。
写成 ``return None`` 或 ``return []`` 会被视为已实现，前端点击卡片时弹出
“此插件没有详情页面”的空窗口。vue 模式插件的详情页由联邦组件 ``./Page`` 提供，
``return None`` 是合法写法，因此不在本门禁范围内。
"""

from __future__ import annotations

import ast
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
PLUGINS_V3 = REPO_ROOT / "plugins.v3"


def _is_docstring(stmt: ast.stmt) -> bool:
    """判断语句是否为字符串常量表达式（docstring）。"""
    return isinstance(stmt, ast.Expr) and isinstance(stmt.value, ast.Constant) and isinstance(stmt.value.value, str)


def _is_empty_return(stmt: ast.stmt) -> bool:
    """判断语句是否为 ``return``、``return None`` 或 ``return []`` 这类空页面返回。"""
    if not isinstance(stmt, ast.Return):
        return False
    value = stmt.value
    if value is None:
        return True
    if isinstance(value, ast.Constant) and value.value is None:
        return True
    return isinstance(value, ast.List) and not value.elts


def _uses_vue_render_mode(tree: ast.Module) -> bool:
    """插件入口的 get_render_mode 返回 "vue" 时视为联邦组件渲染。"""
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "get_render_mode":
            for sub in ast.walk(node):
                if isinstance(sub, ast.Constant) and sub.value == "vue":
                    return True
    return False


def find_empty_get_page(source: str) -> bool:
    """返回非 vue 模式插件是否用空返回值代替占位实现声明“无详情页”。"""
    tree = ast.parse(source)
    if _uses_vue_render_mode(tree):
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "get_page":
            body = [stmt for stmt in node.body if not _is_docstring(stmt)]
            if len(body) == 1 and _is_empty_return(body[0]):
                return True
    return False


def test_v3_plugins_declare_no_page_with_placeholder() -> None:
    """没有详情页的 V3 插件必须用占位函数体声明，不能返回空值。"""
    offenders = sorted(
        init_file.parent.name
        for init_file in PLUGINS_V3.glob("*/__init__.py")
        if find_empty_get_page(init_file.read_text(encoding="utf-8"))
    )

    assert offenders == [], f"以下插件的 get_page 应改为 docstring + pass：{offenders}"


def test_detector_flags_empty_returns_and_accepts_placeholders() -> None:
    """检测器识别空返回值写法，放行占位实现、真实页面与 vue 模式。"""
    def plugin(body: str, render_mode: str = "") -> str:
        return f"class P:\n{render_mode}    def get_page(self):\n        \"\"\"doc\"\"\"\n{body}"

    assert find_empty_get_page(plugin("        return None\n"))
    assert find_empty_get_page(plugin("        return []\n"))
    assert find_empty_get_page(plugin("        return\n"))
    assert not find_empty_get_page(plugin("        pass\n"))
    assert not find_empty_get_page(plugin("        return [{'component': 'div'}]\n"))
    vue_mode = "    @staticmethod\n    def get_render_mode():\n        return 'vue', 'dist'\n"
    assert not find_empty_get_page(plugin("        return None\n", vue_mode))
