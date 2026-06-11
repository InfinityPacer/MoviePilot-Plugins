"""日志摘要工具与诊断级日志开关。

主程序 logger（app.log）已按调用文件名/插件自动标注来源并分文件落盘
（命中 plugins/<plugin> 即写 plugins/<plugin>.log），因此业务日志不再手工加
插件名/域名前缀，避免与框架自带来源标注重复。本模块只提供：
- detail：诊断级日志通道，beta 期抬到 info、灰度结束统一降回 debug；
- 标题/取值截断等日志摘要工具。
"""
from typing import Any

from app.log import logger

# Beta 灰度期开关：控制 detail 诊断日志的实际级别。
# True → 绑定 logger.info（默认日志级别即可见，便于快速排查）；
# 灰度结束改为 False → 降为 logger.debug 降噪。一处常量切换，无需改动各调用点。
BETA_VERBOSE = True

# 诊断级日志：直接绑定 logger 的 bound method，等价于直接调用 logger.info / logger.debug。
# 不再包一层函数是有意为之——主程序按 sys._getframe(3) 定位调用来源文件名与插件，
# 任何包装层都会新增一帧、让所有日志来源被记成 log.py，破坏按文件定位的能力。
detail = logger.info if BETA_VERBOSE else logger.debug


def truncate_log_value(value: Any, max_length: int = 160, middle: bool = False) -> str:
    """截断过长的日志值。"""
    text = str(value) if value is not None else ""
    if len(text) <= max_length:
        return text
    if middle:
        # 头尾各留一半、中间省略号；奇数余量多出的 1 个字符归头部，保证截断后总长恰为 max_length
        remain = max_length - 3
        if remain <= 0:
            return "..."
        head = remain - remain // 2
        tail = remain // 2
        return f"{text[:head]}...{text[-tail:]}" if tail else f"{text[:head]}..."
    return f"{text[:max_length - 3]}..."


def format_log_title_desc(title: Any = None, description: Any = None,
                           max_length: int = 220) -> str:
    """格式化标题和描述为日志行。"""
    parts = []
    if title:
        parts.append(str(title))
    if description:
        parts.append(str(description))
    text = " - ".join(parts)
    return truncate_log_value(text, max_length)
