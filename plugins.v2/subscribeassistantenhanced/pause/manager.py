"""域 ④：暂停管理——优先级覆盖 + 用户名自动暂停 + 双向恢复。"""
import time
from typing import Callable, Optional

from app.log import logger

from ..engine.types import PauseRecord
from ..shared.log import detail
from ..shared.subscribe import format_subscribe

# 暂停原因优先级：仅用于 pause() 时判定新原因能否覆盖旧原因。
# pre_air / no_download / auto_user 等未列出原因隐式按 0 处理，不参与覆盖竞争。
PRIORITY_ORDER = {"airing_gap": 1}


class PauseManager:
    """暂停优先级管理与恢复协调。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 subscribe_oper=None, auto_pause_users: Optional[list] = None):
        self._read = task_data_read
        self._update = task_data_update
        self._subscribe_oper = subscribe_oper
        self._auto_pause_users = auto_pause_users or []

    def pause(self, subscribe, record: PauseRecord):
        """设置暂停，仅当新原因优先级 >= 当前原因时生效。"""
        current = self.get_pause_record(subscribe)
        if current:
            cur_prio = PRIORITY_ORDER.get(current.reason, 0)
            new_prio = PRIORITY_ORDER.get(record.reason, 0)
            if new_prio < cur_prio:
                detail(f"暂停管理：{format_subscribe(subscribe)} 新暂停原因 {record.reason} 优先级低于现有 {current.reason}，不覆盖")
                return

        if not record.since:
            record.since = time.time()

        sid = str(subscribe.id)
        detail(f"暂停管理：{format_subscribe(subscribe)} 写暂停记录（原因={record.reason}，detail={record.detail}）并置订阅为禁用(S)")

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            task["pause_reason"] = record.reason
            task["pause_since"] = record.since
            task["pause_detail"] = record.detail
            data[sid] = task
            return data

        self._update("subscribes", updater)

        if self._subscribe_oper:
            self._subscribe_oper.update(subscribe.id, {"state": "S"})

    def resume(self, subscribe):
        """恢复订阅：清插件暂停记录并把订阅状态置回 R。

        是否调用 resume 的判定（标记暂停跳过、上映条件双向恢复）由上层巡检负责。
        """
        detail(f"暂停管理：{format_subscribe(subscribe)} 清暂停记录并置订阅为启用(R)")
        sid = str(subscribe.id)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            task.pop("pause_reason", None)
            task.pop("pause_since", None)
            task.pop("pause_detail", None)
            data[sid] = task
            return data

        self._update("subscribes", updater)

        if self._subscribe_oper:
            self._subscribe_oper.update(subscribe.id, {"state": "R"})
        return True

    def clear_pause_record(self, subscribe):
        """清理插件侧暂停记录元数据，但不改订阅状态本身。

        用于订阅状态被用户/外部变更后重置插件的暂停跟踪；
        与 resume 区别：resume 会把订阅状态改回 R，本方法仅丢弃插件记录、把状态归属交还调用方。
        """
        detail(f"暂停管理：{format_subscribe(subscribe)} 仅清插件暂停记录（不改订阅状态）")
        sid = str(subscribe.id)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            task.pop("pause_reason", None)
            task.pop("pause_since", None)
            task.pop("pause_detail", None)
            data[sid] = task
            return data

        self._update("subscribes", updater)

    def get_pause_record(self, subscribe) -> Optional[PauseRecord]:
        """读取当前插件侧暂停记录；无记录返回 None。

        不对“无记录但 state=S”合成手动暂停记录：外部直接暂停的订阅由本插件视为无记录，
        不被纳入本插件的暂停跟踪与超期/恢复逻辑。
        """
        sid = str(subscribe.id)
        data = self._read("subscribes")
        task = data.get(sid, {})
        reason = task.get("pause_reason")
        if not reason:
            return None
        return PauseRecord(
            reason=reason,
            since=task.get("pause_since", 0.0),
            detail=task.get("pause_detail", ""),
        )

    def check_auto_pause_for_user(self, subscribe) -> bool:
        """检查是否应按用户名自动暂停新增订阅。

        命中名单时写入 reason=auto_user 的标记暂停：元数据巡检在 state=S 时跳过，
        不被上映检查自动恢复；用户重新启用后再清标记。
        """
        if not self._auto_pause_users:
            return False
        username = subscribe.username
        if username in self._auto_pause_users:
            logger.info(f"暂停管理：{format_subscribe(subscribe)} 命中用户名自动暂停名单（用户 {username}），标记暂停")
            self.pause(subscribe, PauseRecord(
                reason="auto_user",
                since=time.time(),
                detail=f"用户 {username} 的订阅自动暂停",
            ))
            return True
        return False
