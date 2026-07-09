"""暂停管理：处理优先级覆盖、用户名自动暂停和双向恢复。"""
import re
import time
from typing import Callable, Optional

from app.log import logger

from ..engine.types import PauseRecord
from ..shared.log import detail as log_detail
from ..shared.subscribe import format_subscribe
from ..shared.update import update_subscribe

# 只为 PauseManager 持有的暂停原因定义覆盖顺序；其他业务场景不写 pause_reason 参与优先级竞争。
# 未列出的兼容/异常原因按 0 处理，数值越大越优先。
# airing_gap 比 pre_air 更具体；auto_user/no_download 属于标记暂停，不被可自动恢复暂停接管；
# external 代表用户或外部系统的暂停事实，始终拥有最高优先级。
PRIORITY_ORDER = {"pre_air": 0, "airing_gap": 1, "auto_user": 2, "no_download": 2, "external": 3}


class PauseManager:
    """暂停优先级管理与恢复协调。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 subscribe_oper=None, auto_pause_users: Optional[list] = None,
                 notify_fn: Optional[Callable] = None, pending_state=None,
                 pause_enhanced_enabled: bool = True):
        """注入任务数据、订阅写库、用户名规则和状态通知回调。"""
        self._read = task_data_read
        self._update = task_data_update
        self._subscribe_oper = subscribe_oper
        self._auto_pause_users = auto_pause_users or []
        self._notify = notify_fn
        self._pending_state = pending_state
        self._pause_enhanced_enabled = pause_enhanced_enabled

    def pause(self, subscribe, record: PauseRecord, notify: bool = True):
        """设置暂停，仅当新原因优先级 >= 当前原因时生效；可静默刷新内部归因。"""
        if self._pause_enhanced_enabled and self._is_guarded(subscribe, record):
            return False

        current = self.get_pause_record(subscribe)
        if current:
            cur_prio = PRIORITY_ORDER.get(current.reason, 0)
            new_prio = PRIORITY_ORDER.get(record.reason, 0)
            if new_prio < cur_prio:
                log_detail(f"暂停管理：{format_subscribe(subscribe)} 新暂停原因 {record.reason} 优先级低于现有 {current.reason}，不覆盖")
                return False

        if not record.since:
            record.since = time.time()

        sid = str(subscribe.id)
        is_refresh = current is not None and current.reason == record.reason
        if is_refresh:
            log_detail(
                f"暂停刷新：{format_subscribe(subscribe)} 暂停原因仍满足，"
                f"原因={record.reason}，detail={record.detail}"
            )
        elif not notify:
            log_detail(f"暂停管理：{format_subscribe(subscribe)} 静默刷新暂停记录（原因={record.reason}，detail={record.detail}）")
        else:
            log_detail(f"暂停管理：{format_subscribe(subscribe)} 写暂停记录（原因={record.reason}，detail={record.detail}）并置订阅为禁用(S)")
        if self._pending_state:
            self._pending_state.clear_for_pause(subscribe, reason=f"暂停覆盖：{record.reason}")

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            task["pause_reason"] = record.reason
            task["pause_since"] = record.since
            task["pause_detail"] = record.detail
            data[sid] = task
            return data

        self._update("subscribes", updater)

        if self._subscribe_oper and not is_refresh and subscribe.state != "S":
            update_subscribe(self._subscribe_oper, subscribe.id, {"state": "S"})
        if notify and not is_refresh:
            self._notify_pause(subscribe, record)
        return not is_refresh

    def adopt_external(self, subscribe, detail: str = "外部暂停") -> bool:
        """静默登记外部暂停事实；已有插件暂停记录时保留首次归因。"""
        if subscribe.state != "S":
            return False
        if self.get_pause_record(subscribe):
            return False
        sid = str(subscribe.id)
        now = time.time()
        external_detail = detail or "外部暂停"
        log_detail(f"暂停管理：{format_subscribe(subscribe)} 登记外部暂停（detail={external_detail}）")

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            if task.get("pause_reason"):
                data[sid] = task
                return data
            task["pause_reason"] = "external"
            task["pause_since"] = now
            task["pause_detail"] = external_detail
            data[sid] = task
            return data

        self._update("subscribes", updater)
        return True

    def clear_probe_schedule(self, subscribe, include_last: bool = False):
        """清理当前主动补搜调度字段；按调用场景决定是否重置限频时间。"""
        sid = str(subscribe.id)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            self._drop_probe_schedule_fields(task, include_last=include_last)
            data[sid] = task
            return data

        self._update("subscribes", updater)

    def clear_probe_fields_for_resume(self, subscribe):
        """下载命中恢复后清理全部主动补搜调度字段，保留恢复防打回窗口。"""
        self.clear_probe_schedule(subscribe, include_last=True)

    def set_resume_guard(self, subscribe, reason: str, hours: int = 48) -> bool:
        """记录下载命中恢复后的同原因防打回窗口；external 不参与自动原因保护。"""
        if reason == "external":
            log_detail(f"暂停管理：{format_subscribe(subscribe)} 外部暂停恢复不写防打回保护")
            return False
        sid = str(subscribe.id)
        until = time.time() + max(int(hours), 0) * 3600

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            task["paused_probe_resume_guard_reason"] = reason
            task["paused_probe_resume_guard_until"] = until
            data[sid] = task
            return data

        self._update("subscribes", updater)
        return True

    def resume(self, subscribe, notify: bool = True):
        """恢复订阅：清插件暂停记录并把订阅状态置回 R。

        是否调用 resume 的判定（标记暂停跳过、上映条件双向恢复）由上层巡检负责。
        """
        record = self.get_pause_record(subscribe)
        if not record:
            log_detail(f"暂停管理：{format_subscribe(subscribe)} 无插件暂停记录，跳过恢复")
            return False
        log_detail(f"暂停管理：{format_subscribe(subscribe)} 清暂停记录并置订阅为启用(R)")
        sid = str(subscribe.id)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            self._drop_pause_fields(task)
            self._drop_probe_schedule_fields(task, include_last=False)
            data[sid] = task
            return data

        self._update("subscribes", updater)

        if self._subscribe_oper:
            update_subscribe(self._subscribe_oper, subscribe.id, {"state": "R"})
        if notify:
            self._notify_resume(subscribe, record)
        return True

    def clear_pause_record(self, subscribe):
        """清理插件侧暂停记录元数据，但不改订阅状态本身。

        用于订阅状态被用户/外部变更后重置插件的暂停跟踪；
        与 resume 区别：resume 会把订阅状态置为 R，本方法仅丢弃插件记录、把状态归属交还调用方。
        """
        log_detail(f"暂停管理：{format_subscribe(subscribe)} 仅清插件暂停记录（不改订阅状态）")
        sid = str(subscribe.id)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            self._drop_pause_fields(task)
            self._drop_probe_schedule_fields(task, include_last=False)
            data[sid] = task
            return data

        self._update("subscribes", updater)

    def get_pause_record(self, subscribe) -> Optional[PauseRecord]:
        """读取当前插件侧暂停记录；无记录返回 None。

        不对“无记录但 state=S”合成暂停记录；外部暂停由 adopt_external() 显式接管，
        便于保留首次发现时间并区分用户/外部暂停与插件自动暂停。
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

        新增订阅用户在名单内时写入 reason=auto_user 的标记暂停：元数据巡检在 state=S 时跳过，
        不被上映检查自动恢复；用户重新启用后再清标记。
        """
        if not self._auto_pause_users:
            return False
        username = subscribe.username
        if username in self._auto_pause_users:
            logger.info(f"暂停管理：{format_subscribe(subscribe)} 用户 {username} 在自动暂停名单内，标记暂停")
            self.pause(subscribe, PauseRecord(
                reason="auto_user",
                since=time.time(),
                detail=f"用户 {username} 的订阅自动暂停",
            ))
            return True
        return False

    def _notify_pause(self, subscribe, record: PauseRecord):
        """发送暂停状态通知；无下载流程由外层统一通知，避免重复消息。"""
        if not self._notify or record.reason == "no_download":
            return
        reason = {
            "pre_air": "上映",
            "airing_gap": "播出",
            "auto_user": "用户规则",
        }.get(record.reason, record.reason)
        self._notify(
            subscribe,
            f"{reason}满足订阅暂停，已标记暂停",
            detail=record.detail,
        )

    def _notify_resume(self, subscribe, record: Optional[PauseRecord]):
        """发送暂停恢复状态通知。"""
        if not self._notify:
            return
        reason_key = record.reason if record else ""
        reason = {
            "pre_air": "上映",
            "airing_gap": "播出",
            "auto_user": "用户规则",
        }.get(reason_key, "暂停")
        detail = self._resume_detail(reason_key, record)
        self._notify(
            subscribe,
            f"{reason}不再满足订阅暂停，已标记订阅中",
            detail=detail,
        )

    def _is_guarded(self, subscribe, record: PauseRecord) -> bool:
        """判断下载命中恢复后的同原因保护窗口是否拦截本次自动暂停。"""
        if record.reason == "external":
            return False
        sid = str(subscribe.id)
        task = self._read("subscribes").get(sid, {})
        guard_reason = task.get("paused_probe_resume_guard_reason")
        guard_until = task.get("paused_probe_resume_guard_until") or 0
        if record.reason != guard_reason:
            return False
        now = time.time()
        if now >= float(guard_until):
            return False
        remaining = int(float(guard_until) - now)
        log_detail(
            f"暂停管理：{format_subscribe(subscribe)} 同原因 {record.reason} 仍在恢复保护窗口内，"
            f"剩余 {remaining} 秒，跳过自动暂停"
        )
        return True

    @staticmethod
    def _drop_pause_fields(task: dict):
        """删除当前暂停归因字段，不影响 probe 限频和恢复保护字段。"""
        task.pop("pause_reason", None)
        task.pop("pause_since", None)
        task.pop("pause_detail", None)

    @staticmethod
    def _drop_probe_schedule_fields(task: dict, include_last: bool = False):
        """删除主动补搜调度字段；恢复场景可同时删除上次安排时间。"""
        task.pop("paused_probe_scheduled_run_at", None)
        task.pop("paused_probe_reason", None)
        if include_last:
            task.pop("paused_probe_last_scheduled_at", None)

    @staticmethod
    def _resume_detail(reason_key: str, record: Optional[PauseRecord]) -> str:
        """生成恢复通知正文，保留原暂停窗口上下文但改写为当前状态。"""
        pause_detail = record.detail if record else ""
        if reason_key == "pre_air":
            pause_detail = re.sub(r"^(?:电影|电视剧|剧集)\s+", "", pause_detail)
            pause_detail = re.sub(r"，距今\s+\d+\s+天", "", pause_detail)
            pause_detail = re.sub(r"，已过\s+\d+\s+天", "", pause_detail)
            pause_detail = pause_detail.replace("，今天", "")
            if pause_detail and "暂未到订阅窗口" in pause_detail:
                return pause_detail.replace("暂未到订阅窗口", "已进入订阅窗口")
            return "已进入订阅窗口"
        if reason_key == "airing_gap":
            match = re.search(r"(下一集(?:日期：|\s+)\d{4}-\d{2}-\d{2})", pause_detail)
            if match:
                return f"{match.group(1)}，已进入播出窗口"
            return "已进入播出窗口"
        if reason_key == "auto_user":
            return "用户规则暂停已解除"
        return "暂停条件已解除"
