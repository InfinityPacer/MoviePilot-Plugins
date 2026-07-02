"""暂停订阅低频补搜协调器。"""
import random
import threading
import time
from typing import Callable, Optional

from app.log import logger

from ..shared.log import detail
from ..shared.subscribe import format_subscribe, format_subscribe_label


PROBE_LAST_SCHEDULED_AT = "paused_probe_last_scheduled_at"
PROBE_SCHEDULED_RUN_AT = "paused_probe_scheduled_run_at"
PROBE_REASON = "paused_probe_reason"
PROBE_MAX_CANDIDATES = 10
PROBE_MIN_INTERVAL_HOURS = 24
PROBE_DELAY_SECONDS = (60, 300)


class PausedProbeCoordinator:
    """维护暂停订阅的低频补搜调度。

    该协调器只负责选择候选、写入本轮调度字段、执行前复核和调用单订阅搜索；
    暂停记录、恢复保护和订阅状态变更仍由 PauseManager 与事件层负责。
    """

    def __init__(self, config, task_data_read: Callable, task_data_update: Callable,
                 subscribe_oper, subscribe_chain, pause_manager,
                 download_monitor=None,
                 timer_factory: Optional[Callable] = None,
                 now_fn: Optional[Callable] = None,
                 delay_fn: Optional[Callable] = None):
        """注入配置、任务数据、订阅查询、搜索入口和可替换时钟/Timer。"""
        self._config = config
        self._read = task_data_read
        self._update = task_data_update
        self._subscribe_oper = subscribe_oper
        self._subscribe_chain = subscribe_chain
        self._pause_manager = pause_manager
        self._download_monitor = download_monitor
        self._timer_factory = timer_factory or threading.Timer
        self._now = now_fn or time.time
        self._delay = delay_fn or (lambda: random.randint(*PROBE_DELAY_SECONDS))
        self._generation = 0
        self._timers: dict[str, object] = {}
        self._lock = threading.RLock()

    def stop(self):
        """取消并失效当前所有待执行 Timer。"""
        with self._lock:
            self._generation += 1
            timers = list(self._timers.values())
            self._timers.clear()
        for timer in timers:
            cancel = getattr(timer, "cancel", None)
            if cancel:
                cancel()
        detail("暂停补搜：已取消待执行任务")

    def run(self):
        """扫描暂停订阅并为符合条件的候选安排一次补搜。"""
        if not self._enabled():
            detail("暂停补搜：自动暂停未开启，跳过")
            return
        if not (self._subscribe_oper and self._subscribe_chain and self._pause_manager):
            detail("暂停补搜：运行依赖未就绪，跳过")
            return

        now = self._now()
        selected_reasons = self._selected_reasons()
        scheduled = 0
        for subscribe in (self._subscribe_oper.list(state="S") or []):
            if scheduled >= PROBE_MAX_CANDIDATES:
                detail("暂停补搜：本轮已达到 10 个候选上限")
                break

            record = self._pause_manager.get_pause_record(subscribe)
            if record is None:
                self._pause_manager.adopt_external(subscribe)
                record = self._pause_manager.get_pause_record(subscribe)
            if record is None:
                detail(f"暂停补搜：{format_subscribe(subscribe)} 无暂停记录，跳过")
                continue

            if not selected_reasons:
                detail(f"暂停补搜：{format_subscribe(subscribe)} 未配置补搜场景，仅登记暂停状态")
                continue

            reason = record.reason
            sid = str(subscribe.id)
            task = (self._read("subscribes") or {}).get(sid, {})
            scheduled_run_at = task.get(PROBE_SCHEDULED_RUN_AT)
            if scheduled_run_at:
                if scheduled_run_at <= now:
                    detail(f"暂停补搜：{format_subscribe(subscribe)} 清理过期调度字段")
                    self._pause_manager.clear_probe_schedule(subscribe, include_last=False)
                else:
                    detail(f"暂停补搜：{format_subscribe(subscribe)} 已有待执行调度，跳过")
                continue

            skip_reason = self._candidate_skip_reason(subscribe, record, task, now, selected_reasons)
            if skip_reason:
                detail(f"暂停补搜：{format_subscribe(subscribe)} {skip_reason}")
                continue

            self._schedule(subscribe, reason, now)
            scheduled += 1

    def _enabled(self) -> bool:
        """读取总开关；配置对象是插件内部稳定结构。"""
        return bool(self._config.pause_enhanced_enabled)

    def _selected_reasons(self) -> set[str]:
        """读取当前允许 probe 的暂停场景集合。"""
        return {str(reason).strip() for reason in self._config.paused_probe_reasons if str(reason).strip()}

    def _interval_seconds(self) -> int:
        """按当前配置计算限频间隔，运行时下限固定为 24 小时。"""
        return max(int(self._config.paused_probe_interval_hours or 0), PROBE_MIN_INTERVAL_HOURS) * 3600

    @staticmethod
    def _reason_allowed(reason: str, selected_reasons: set[str]) -> bool:
        """判断暂停原因是否被当前场景配置允许；all 覆盖未来新增原因。"""
        if "all" in selected_reasons:
            return True
        return reason in selected_reasons

    def _candidate_skip_reason(self, subscribe, record, task: dict, now: float,
                               selected_reasons: set[str]) -> str:
        """返回候选跳过原因；空字符串表示可以安排 probe。"""
        reason = record.reason
        if not self._reason_allowed(reason, selected_reasons):
            return f"暂停原因 {reason} 未配置补搜"
        pause_since = float(record.since or 0)
        min_pause_days = int(self._config.paused_probe_min_pause_days or 0)
        if min_pause_days <= 0:
            return "暂停满天数为 0，不处理主动补搜"
        min_pause_seconds = min_pause_days * 86400
        if now - pause_since < min_pause_seconds:
            return f"暂停未满 {min_pause_days} 天"
        last_scheduled_at = task.get(PROBE_LAST_SCHEDULED_AT)
        if last_scheduled_at and now - float(last_scheduled_at) < self._interval_seconds():
            return "距离上次安排未达到补搜间隔"
        if self._download_monitor and self._download_monitor.has_active_downloads(subscribe.id):
            return "存在进行中下载，跳过补搜"
        return ""

    def _schedule(self, subscribe, reason: str, now: float):
        """写入调度字段并安排延迟 Timer。"""
        sid = str(subscribe.id)
        delay = int(self._delay())
        run_at = now + delay

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            task[PROBE_LAST_SCHEDULED_AT] = now
            task[PROBE_SCHEDULED_RUN_AT] = run_at
            task[PROBE_REASON] = reason
            data[sid] = task
            return data

        self._update("subscribes", updater)
        with self._lock:
            generation = self._generation
            old_timer = self._timers.pop(sid, None)
            if old_timer and getattr(old_timer, "cancel", None):
                old_timer.cancel()
            timer = self._timer_factory(delay, lambda: self._execute(sid, generation))
            self._timers[sid] = timer
        timer.start()
        run_text = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(run_at))
        logger.info(
            f"暂停补搜：{format_subscribe(subscribe)} 安排 {delay} 秒后执行，"
            f"预计时间 {run_text}，原因={reason}"
        )

    def _execute(self, sid: str, generation: int):
        """Timer 回调：执行前复核状态，满足条件时调用主程序单订阅搜索。"""
        stale_generation = False
        try:
            subscribe = self._subscribe_oper.get(int(sid)) if self._subscribe_oper else None
            cleanup_last = False
            skip_reason = self._preflight_skip_reason(sid, subscribe, generation)
            if skip_reason:
                logger.info(f"暂停补搜：{format_subscribe_label(subscribe, sid)} 执行前跳过：{skip_reason}")
                if skip_reason == "调度已失效":
                    stale_generation = True
                    return
                if subscribe:
                    cleanup_last = skip_reason in {
                        "配置已关闭", "未配置补搜场景", "暂停满天数为 0", "当前原因未配置", "暂停原因变化"
                    }
                    self._pause_manager.clear_probe_schedule(subscribe, include_last=cleanup_last)
                else:
                    self._clear_probe_schedule_by_sid(sid, include_last=False)
                return
            logger.info(f"暂停补搜：{format_subscribe(subscribe)} 开始执行单订阅搜索")
            self._subscribe_chain.search(sid=subscribe.id)
        except Exception as err:
            logger.error(f"暂停补搜：订阅 {sid} 执行失败，本次已计入间隔：{err}", exc_info=True)
        finally:
            with self._lock:
                self._timers.pop(sid, None)
            if stale_generation:
                return
            subscribe = self._subscribe_oper.get(int(sid)) if self._subscribe_oper else None
            if subscribe:
                self._pause_manager.clear_probe_schedule(subscribe, include_last=False)
            else:
                self._clear_probe_schedule_by_sid(sid, include_last=False)

    def _clear_probe_schedule_by_sid(self, sid: str, include_last: bool = False):
        """订阅对象不可用时按 sid 清理本轮调度字段。"""

        def updater(data: dict) -> dict:
            task = data.get(str(sid), {})
            task.pop(PROBE_SCHEDULED_RUN_AT, None)
            task.pop(PROBE_REASON, None)
            if include_last:
                task.pop(PROBE_LAST_SCHEDULED_AT, None)
            data[str(sid)] = task
            return data

        self._update("subscribes", updater)

    def _preflight_skip_reason(self, sid: str, subscribe, generation: int) -> str:
        """Timer 执行前复核配置、订阅状态和暂停原因。"""
        with self._lock:
            if generation != self._generation:
                return "调度已失效"
        task = (self._read("subscribes") or {}).get(str(sid), {})
        scheduled_reason = task.get(PROBE_REASON)
        if not self._enabled():
            return "配置已关闭"
        selected_reasons = self._selected_reasons()
        if not selected_reasons:
            return "未配置补搜场景"
        if int(self._config.paused_probe_min_pause_days or 0) <= 0:
            return "暂停满天数为 0"
        if not subscribe:
            return "订阅不存在"
        if subscribe.state != "S":
            return "订阅已非暂停状态"
        record = self._pause_manager.get_pause_record(subscribe)
        if not record:
            return "暂停记录不存在"
        if record.reason != scheduled_reason:
            return "暂停原因变化"
        if not self._reason_allowed(record.reason, selected_reasons):
            return "当前原因未配置"
        return ""
