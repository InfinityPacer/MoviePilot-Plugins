"""统一待定状态仲裁。

该模块只负责多来源待定的状态合并与订阅表 P/R 同步，不判断具体业务条件。
"""
import time
from typing import Callable, Optional

from app.log import logger

from ..shared.subscribe import format_subscribe
from ..shared.update import update_subscribe


class PendingStateCoordinator:
    """多来源待定状态协调器。

    `pending_sources` 记录各业务域的活跃待定来源；只要任一来源存在，订阅保持 P。
    最后一个来源清除后才恢复 R，避免下载待定、完结守卫和剧集待定互相误释放。
    """

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 subscribe_oper=None):
        """注入任务存储与订阅表写入依赖。"""
        self._read = task_data_read
        self._update = task_data_update
        self._subscribe_oper = subscribe_oper

    def mark_active(self, subscribe, source: str, reason: str = "") -> bool:
        """标记某个来源进入待定，并把主订阅状态同步为 P。"""
        if not subscribe or not source:
            return False
        sid = str(subscribe.id)
        now = time.time()

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            sources = self._normalize_sources(task)
            sources[source] = {
                "reason": reason,
                "since": sources.get(source, {}).get("since") or now,
                "updated_at": now,
            }
            task["pending_sources"] = sources
            task["state"] = "P"
            task["source"] = self._primary_source(sources)
            task["reason"] = sources[task["source"]].get("reason", "")
            task["since"] = sources[task["source"]].get("since", now)
            data[sid] = task
            return data

        self._update("subscribes", updater)
        if self._subscribe_oper and subscribe.state != "P":
            update_subscribe(self._subscribe_oper, subscribe.id, {"state": "P"})
            logger.info(f"待定状态：{format_subscribe(subscribe)} 来源 {source} 进入待定，状态置为 P")
            return True
        return False

    def clear_active(self, subscribe, source: str, reason: str = "") -> bool:
        """清除某个待定来源，并按剩余来源决定是否恢复 R。"""
        if not subscribe or not source:
            return False
        sid = str(subscribe.id)
        result = {"active": False, "primary": None}

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            sources = self._normalize_sources(task)
            sources.pop(source, None)
            result["active"] = bool(sources)
            result["primary"] = self._primary_source(sources) if sources else None
            task["pending_sources"] = sources
            if sources:
                primary = result["primary"]
                task["state"] = "P"
                task["source"] = primary
                task["reason"] = sources[primary].get("reason", "")
                task["since"] = sources[primary].get("since")
            else:
                task["state"] = "R"
                task["source"] = None
                task["reason"] = reason
                task["exit_at"] = time.time()
            data[sid] = task
            return data

        self._update("subscribes", updater)
        if result["active"]:
            logger.info(
                f"待定状态：{format_subscribe(subscribe)} 来源 {source} 已释放，"
                f"仍存在 {result['primary']} 待定，保持 P"
            )
            return False
        if self._subscribe_oper and subscribe.state == "P":
            update_subscribe(self._subscribe_oper, subscribe.id, {"state": "R"})
            logger.info(f"待定状态：{format_subscribe(subscribe)} 来源 {source} 已释放，状态置为 R")
            return True
        return False

    def has_active(self, subscribe_id: int) -> bool:
        """判断订阅是否存在任一活跃待定来源。"""
        task = (self._read("subscribes") or {}).get(str(subscribe_id), {})
        return bool(self._normalize_sources(task))

    def active_sources(self, subscribe_id: int) -> dict:
        """读取订阅当前活跃待定来源。"""
        task = (self._read("subscribes") or {}).get(str(subscribe_id), {})
        return self._normalize_sources(task)

    @staticmethod
    def _normalize_sources(task: Optional[dict]) -> dict:
        """兼容旧单 source 任务数据，统一返回 pending_sources 字典。"""
        if not task:
            return {}
        sources = task.get("pending_sources")
        if isinstance(sources, dict):
            return dict(sources)
        if task.get("state") == "P" and task.get("source"):
            return {
                task["source"]: {
                    "reason": task.get("reason", ""),
                    "since": task.get("since"),
                    "updated_at": task.get("since"),
                }
            }
        return {}

    @staticmethod
    def _primary_source(sources: dict) -> Optional[str]:
        """选择写回 legacy `source` 字段的主来源，保证日志和旧模块读到稳定值。"""
        for source in ("pending_judge", "guard_veto", "download_pending"):
            if source in sources:
                return source
        return next(iter(sources), None)
