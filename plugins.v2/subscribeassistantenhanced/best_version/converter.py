"""域 ⑤：分集→全集转换——原地 update，失败保持原状态。"""
from typing import Optional


class BestVersionConverter:
    """分集洗版升级为全集洗版。"""

    def __init__(self, subscribe_oper=None):
        self._subscribe_oper = subscribe_oper

    def convert_to_full(self, subscribe) -> bool:
        """原地升级为全集洗版。失败时保持原状态，不删旧订阅。"""
        sid = subscribe.id
        if not sid or not self._subscribe_oper:
            return False

        try:
            self._subscribe_oper.update(sid, {"best_version_full": 1})
            return True
        except Exception:
            return False
