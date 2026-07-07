"""无进展诊断子模块：订阅长期无新进展时发出诊断通知。

只做只读观察与通知，不改动订阅的搜索规则、站点范围或下载行为。
"""
from .diagnostic import ProgressDiagnosticCoordinator

__all__ = ["ProgressDiagnosticCoordinator"]
