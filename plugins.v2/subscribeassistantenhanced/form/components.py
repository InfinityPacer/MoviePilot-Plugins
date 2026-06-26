"""vuetify 表单控件工厂：收敛重复样板，按字段类型生成对应控件，单字段一列。

控件均为后端返回、前端通用渲染器（FormRender）识别的 Vuetify schema 字典；
``model`` 即配置键，须与 PluginConfig 的 @property 同名，保证 WebUI 存的配置能被运行时读到。
所有控件统一支持 ``hint``：传入后挂 ``persistent-hint``，让字段说明在表单中常驻显示。
"""
from typing import Any, List, Optional


def _with_hint(props: dict, hint: str) -> dict:
    """给控件 props 注入常驻 hint：hint 为空则不挂，避免渲染出空白说明行。"""
    if hint:
        props["hint"] = hint
        props["persistent-hint"] = True
    return props


def switch_col(model: str, label: str, hint: str = "", md: int = 6) -> dict:
    """开关控件（布尔配置），可附常驻 hint。"""
    return {
        "component": "VCol",
        "props": {"cols": 12, "md": md},
        "content": [{"component": "VSwitch",
                     "props": _with_hint({"model": model, "label": label}, hint)}],
    }


def number_field(model: str, label: str, hint: str = "", md: int = 6) -> dict:
    """数值输入控件（int/float 配置），可附常驻 hint。"""
    return {
        "component": "VCol",
        "props": {"cols": 12, "md": md},
        "content": [{"component": "VTextField",
                     "props": _with_hint({"model": model, "label": label, "type": "number"}, hint)}],
    }


def text_field(model: str, label: str, hint: str = "", md: int = 12) -> dict:
    """文本输入控件（字符串配置），可附常驻 hint。"""
    return {
        "component": "VCol",
        "props": {"cols": 12, "md": md},
        "content": [{"component": "VTextField",
                     "props": _with_hint({"model": model, "label": label}, hint)}],
    }


def select_field(model: str, label: str, items: list, hint: str = "", md: int = 6) -> dict:
    """固定枚举选择控件，避免保存运行时无法识别的自由文本，可附常驻 hint。"""
    return {
        "component": "VCol",
        "props": {"cols": 12, "md": md},
        "content": [{
            "component": "VSelect",
            "props": _with_hint({"model": model, "label": label, "items": items}, hint),
        }],
    }


def cron_field(model: str, label: str, hint: str = "", md: int = 6) -> dict:
    """cron 表达式输入控件（VCronField），用于按 cron 调度的周期配置，可附常驻 hint。"""
    return {
        "component": "VCol",
        "props": {"cols": 12, "md": md},
        "content": [{"component": "VCronField",
                     "props": _with_hint({"model": model, "label": label}, hint)}],
    }


def textarea_field(model: str, label: str, hint: str = "", md: int = 12, rows: int = 10) -> dict:
    """多行文本输入控件（VTextarea），用于每行一项的关键字/列表类配置，可附常驻 hint。"""
    return {
        "component": "VCol",
        "props": {"cols": 12, "md": md},
        "content": [{"component": "VTextarea",
                     "props": _with_hint({"model": model, "label": label, "rows": rows}, hint)}],
    }


def ace_editor_field(model: str, label: str, hint: str = "", md: int = 12) -> dict:
    """YAML 编辑器控件，用于缩进敏感的策略配置。"""
    props = {
        "modelvalue": model,
        "label": label,
        "lang": "yaml",
        "theme": "monokai",
        "style": "height: 30rem",
    }
    return {
        "component": "VCol",
        "props": {"cols": 12, "md": md},
        "content": [{"component": "VAceEditor", "props": _with_hint(props, hint)}],
    }


def field_for(model: str, label: str, default: Any, hint: str = "", md: int = 6) -> dict:
    """按默认值类型选择控件：bool→开关、str→文本、其余（int/float）→数值。

    必须先判 bool 再判 int——Python 中 ``isinstance(True, int)`` 为真，顺序写反会把开关误渲成数值框。
    """
    if isinstance(default, bool):
        return switch_col(model, label, hint, md)
    if isinstance(default, str):
        return text_field(model, label, hint, md)
    return number_field(model, label, hint, md)


def multi_select_field(model: str, label: str, items: list, hint: str = "", md: int = 4) -> dict:
    """多选枚举控件（chips 展示），用于无下载处理策略等多值配置，可附常驻 hint。"""
    return {
        "component": "VCol",
        "props": {"cols": 12, "md": md},
        "content": [{
            "component": "VSelect",
            "props": _with_hint({"model": model, "label": label, "items": items,
                                 "multiple": True, "chips": True, "clearable": True}, hint),
        }],
    }


def tabs(tab_titles: List[str], windows: List[List[dict]]) -> List[dict]:
    """渲染 VTabs + VWindow：tab_titles 与 windows 一一对应，构成分页表单。

    返回 [VTabs, VWindow] 两个顶层组件；二者用同一 model "_tab" 联动当前页索引。
    ``stacked`` + ``fixed-tabs`` 让分页标题等宽铺满并居中，避免多页签时宽度抖动。
    ``windows[i]`` 为该页的组件列表（通常是若干 VRow），整体作为该页 VWindowItem 的内容；
    VWindow 顶部留出浮动 label 空间，避免首行输入框标题被 tab 分隔线裁切。
    """
    tab_items = [{"component": "VTab", "props": {"value": i}, "text": t}
                 for i, t in enumerate(tab_titles)]
    win_items = [{"component": "VWindowItem", "props": {"value": i}, "content": w}
                 for i, w in enumerate(windows)]
    return [
        {"component": "VTabs",
         "props": {"model": "_tab", "stacked": True, "fixed-tabs": True,
                   "style": {"margin-top": "8px", "margin-bottom": "8px"}},
         "content": tab_items},
        {"component": "VWindow",
         "props": {"model": "_tab", "style": {"padding-top": "24px"}},
         "content": win_items},
    ]


def alert_row(alert_type: str, text: str = "", content: Optional[List[dict]] = None,
              margin_top: str = "0") -> dict:
    """底部整宽提示行（VAlert，tonal 样式）：用于 README 指引、数据源说明与风险警告。

    ``text`` 为纯文本提示；``content`` 为富文本子节点（如内嵌链接），二者可同时使用，
    富文本拼在 ``text`` 之后由前端 DashboardRender/FormRender 顺序渲染。
    """
    alert_props = {"type": alert_type, "variant": "tonal"}
    if text:
        alert_props["text"] = text
    alert = {"component": "VAlert", "props": alert_props}
    if content:
        alert["content"] = content
    return {
        "component": "VRow",
        "props": {"style": {"margin-top": margin_top}},
        "content": [{
            "component": "VCol",
            "props": {"cols": 12},
            "content": [alert],
        }],
    }
