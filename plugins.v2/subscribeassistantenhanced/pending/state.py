"""统一待定状态仲裁。

该模块只负责多来源待定合并与订阅表待定（P）/启用（R）同步，不判断具体业务条件。
"""
import time
from typing import Callable, Optional

from app.log import logger

from ..shared.subscribe import format_subscribe
from ..shared.update import update_subscribe


class PendingStateCoordinator:
    """多来源待定状态协调器。

    pending_sources 记录各业务域的活跃来源；任一来源存在时保持待定（P），最后一个来源清除后才恢复启用（R），
    避免 download_pending、pending_judge 与 guard_veto 互相误释放。
    """

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 subscribe_oper=None):
        """注入任务存储与订阅表写入依赖。"""
        self._read = task_data_read
        self._update = task_data_update
        self._subscribe_oper = subscribe_oper

    def mark_active(self, subscribe, source: str, reason: str = "") -> bool:
        """记录一个待定原因，并把主订阅状态同步为待定（P）。"""
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
            logger.info(
                f"待定状态：{format_subscribe(subscribe)} 因【{self._source_label(source)}】进入待定（P）"
            )
            return True
        return False

    def clear_active(self, subscribe, source: str, reason: str = "") -> bool:
        """解除一个待定原因，并按剩余原因决定是否恢复启用（R）。"""
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
                f"待定状态：{format_subscribe(subscribe)}【{self._source_label(source)}】已解除，"
                f"仍因【{self._source_label(result['primary'])}】保持待定（P）"
            )
            return False
        if self._subscribe_oper and subscribe.state == "P":
            update_subscribe(self._subscribe_oper, subscribe.id, {"state": "R"})
            logger.info(f"待定状态：{format_subscribe(subscribe)} 全部待定原因已解除，恢复为启用（R）")
            return True
        return False

    def clear_all_owned(self, subscribe, reason: str = "") -> bool:
        """清除增强版明确持有的全部待定来源，并把主订阅恢复为启用（R）。"""
        if not subscribe:
            return False
        sid = str(subscribe.id)
        task = (self._read("subscribes") or {}).get(sid)
        if not task or task.get("state") != "P":
            return False

        restored = False
        if self._subscribe_oper and subscribe.state == "P":
            # 数据库是用户可见状态事实源；必须先恢复成功，再清除插件侧归属证据。
            update_subscribe(self._subscribe_oper, subscribe.id, {"state": "R"})
            restored = True

        def updater(data: dict) -> dict:
            current = data.get(sid, {})
            current["pending_sources"] = {}
            current["state"] = "R"
            current["source"] = None
            current["reason"] = reason
            current["exit_at"] = time.time()
            data[sid] = current
            return data

        self._update("subscribes", updater)
        if restored:
            logger.info(f"待定状态：{format_subscribe(subscribe)} {reason}，恢复为启用（R）")
            return True
        return False

    def reconcile_orphaned(self, subscribe, reason: str = "") -> bool:
        """恢复 DB 仍为待定、但增强版已无有效待定来源的订阅。"""
        if not subscribe or subscribe.state != "P":
            return False
        sid = str(subscribe.id)
        task = (self._read("subscribes") or {}).get(sid)
        if not task:
            return self._restore_unowned_pending(subscribe, reason=reason)
        if task.get("state") != "P" or self._normalize_sources(task):
            return False
        return self.clear_all_owned(subscribe, reason=reason)

    def clear_for_pause(self, subscribe, reason: str = "") -> bool:
        """插件暂停覆盖待定时清除待定归属，但不把订阅恢复为 R。"""
        if not subscribe:
            return False
        sid = str(subscribe.id)
        task = (self._read("subscribes") or {}).get(sid)
        if not task or task.get("state") != "P":
            return False
        if not self._normalize_sources(task):
            return False

        def updater(data: dict) -> dict:
            current = data.get(sid, {})
            current["pending_sources"] = {}
            current["state"] = "S"
            current["source"] = None
            current["reason"] = reason
            current["exit_at"] = time.time()
            data[sid] = current
            return data

        self._update("subscribes", updater)
        logger.info(f"待定状态：{format_subscribe(subscribe)} 被暂停状态覆盖，清理待定归属")
        return True

    def _restore_unowned_pending(self, subscribe, reason: str = "") -> bool:
        """恢复缺少插件归属记录的 P 状态残留。"""
        if not self._subscribe_oper:
            return False
        update_subscribe(self._subscribe_oper, subscribe.id, {"state": "R"})
        sid = str(subscribe.id)

        def updater(data: dict) -> dict:
            current = data.get(sid, {})
            current["pending_sources"] = {}
            current["state"] = "R"
            current["source"] = None
            current["reason"] = reason
            current["exit_at"] = time.time()
            data[sid] = current
            return data

        self._update("subscribes", updater)
        logger.info(f"待定状态：{format_subscribe(subscribe)} {reason}，恢复为启用（R）")
        return True

    def has_active(self, subscribe_id: int) -> bool:
        """判断订阅是否还有未解除的待定原因。"""
        task = (self._read("subscribes") or {}).get(str(subscribe_id), {})
        return bool(self._normalize_sources(task))

    def active_sources(self, subscribe_id: int) -> dict:
        """读取订阅当前未解除的待定原因。"""
        task = (self._read("subscribes") or {}).get(str(subscribe_id), {})
        return self._normalize_sources(task)

    @staticmethod
    def _normalize_sources(task: Optional[dict]) -> dict:
        """兼容单 source 待定数据，统一返回 pending_sources 字典。"""
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
        """选择写回单 source 字段的主来源，保证待定状态读取结果稳定。"""
        for source in ("pending_judge", "guard_veto", "download_pending"):
            if source in sources:
                return source
        return next(iter(sources), None)

    @staticmethod
    def _source_label(source: Optional[str]) -> str:
        """把内部待定原因转成日志中可读的中文名称。"""
        labels = {
            "pending_judge": "剧集信息待确认",
            "guard_veto": "完成前检查未通过",
            "download_pending": "下载还未整理入库",
        }
        return labels.get(source or "", source or "未知原因")
