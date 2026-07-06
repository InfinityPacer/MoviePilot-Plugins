"""搜索诊断子模块：订阅按原规则长期搜不到资源时发出诊断通知。

只做只读观察与通知，不改动订阅的搜索规则、站点范围或下载行为。
"""
from .diagnostic import NoResultDiagnosticCoordinator

__all__ = ["NoResultDiagnosticCoordinator"]
