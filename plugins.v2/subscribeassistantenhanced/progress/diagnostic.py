"""无进展诊断协调器：识别订阅长期无新进展并发出保守诊断提示。

设计约束：
- 只读观察，不触发搜索、不修改订阅的 include/exclude/站点范围、不下载。
- 判据采用事实信号法：连续多轮巡检中订阅缺失数量未减少，即视为该轮无新进展。
- 状态与订阅任务记录同属 ``subscribes[sid]``，只维护本模块字段，避免插件重置范围与状态存储分裂。
- 通知带冷却，避免同一订阅反复打扰。
"""
import time
from typing import Callable, Optional

from app.log import logger

from ..shared.log import detail


SUBSCRIBES_TASK_KEY = "subscribes"
STALLED_ROUNDS_FIELD = "progress_diagnostic_stalled_rounds"
LAST_MISSING_FIELD = "progress_diagnostic_last_missing_count"
NOTIFIED_AT_FIELD = "progress_diagnostic_notified_at"
PROGRESS_FIELDS = (
    STALLED_ROUNDS_FIELD,
    LAST_MISSING_FIELD,
    NOTIFIED_AT_FIELD,
)


class ProgressDiagnosticCoordinator:
    """维护订阅无进展诊断状态并按阈值/冷却发出通知。

    该协调器只观察订阅缺失数量变化，不触发搜索、不改动搜索规则、不下载。
    """

    def __init__(self, config, task_data_read: Callable, task_data_update: Callable,
                 subscribe_oper, notify_fn: Callable,
                 now_fn: Optional[Callable] = None):
        """注入配置、任务数据读写、订阅查询和通知入口。

        :param config: 插件配置对象。
        :param task_data_read: 任务数据读取函数。
        :param task_data_update: 任务数据读-改-写函数。
        :param subscribe_oper: 订阅查询操作对象。
        :param notify_fn: 通知发送函数。
        :param now_fn: 可选时钟，便于测试。
        """
        self._config = config
        self._read = task_data_read
        self._update = task_data_update
        self._subscribe_oper = subscribe_oper
        self._notify = notify_fn
        self._now = now_fn or time.time

    def run(self):
        """扫描启用中的订阅，累计无进展轮数并按阈值发出诊断通知。"""
        if not self._enabled():
            detail("无进展诊断：未开启，跳过")
            return
        if not self._subscribe_oper:
            detail("无进展诊断：订阅查询依赖未就绪，跳过")
            return

        rounds_threshold = self._rounds_threshold()
        if rounds_threshold <= 0:
            detail("无进展诊断：轮数阈值为 0，跳过")
            return

        now = self._now()
        cooldown_seconds = self._cooldown_hours() * 3600
        subscribes = self._subscribe_oper.list(state="R") or []
        current = self._read(SUBSCRIBES_TASK_KEY) or {}

        patches = {}
        clears = {}
        enabled_sids = set()
        due_notify = []
        for subscribe in subscribes:
            sid = str(subscribe.id)
            if subscribe.state != "R":
                detail(f"无进展诊断：{self._subscribe_label(subscribe)} 当前不是启用状态，跳过")
                continue
            enabled_sids.add(sid)

            missing_count = self._missing_count(subscribe)
            if missing_count is None:
                continue

            record = dict(current.get(sid, {}))

            if missing_count <= 0:
                if self._has_progress_fields(record):
                    clears[sid] = set(PROGRESS_FIELDS)
                continue

            patch, stalled_rounds, should_notify = self._next_patch(
                record=record,
                missing_count=missing_count,
                now=now,
                rounds_threshold=rounds_threshold,
                cooldown_seconds=cooldown_seconds,
            )
            if self._patch_changes(record, patch):
                patches.setdefault(sid, {}).update(patch)
            if should_notify:
                due_notify.append((subscribe, missing_count, stalled_rounds))

        for sid, record in current.items():
            sid = str(sid)
            if sid not in enabled_sids and self._has_progress_fields(record):
                clears[sid] = set(PROGRESS_FIELDS)

        notified_sids = set()
        if due_notify:
            try:
                self._send_summary(due_notify, rounds_threshold)
            except Exception as err:  # pylint: disable=broad-except
                logger.error(f"无进展诊断：发送诊断通知失败：{err}", exc_info=True)
            else:
                notified_sids = {str(subscribe.id) for subscribe, _missing, _rounds in due_notify}

        if notified_sids:
            for sid in notified_sids:
                patches.setdefault(sid, {})[NOTIFIED_AT_FIELD] = now

        if patches or clears:
            self._update(SUBSCRIBES_TASK_KEY, self._build_updater(patches, clears))

    def _next_patch(self, record: dict, missing_count: int, now: float,
                    rounds_threshold: int, cooldown_seconds: int) -> tuple[dict, int, bool]:
        """根据缺失数量变化计算下一轮状态。"""
        last_missing = record.get(LAST_MISSING_FIELD)
        last_notified_at = float(record.get(NOTIFIED_AT_FIELD) or 0)

        if last_missing is None:
            stalled_rounds = 0
        elif missing_count < int(last_missing):
            stalled_rounds = 0
        else:
            stalled_rounds = int(record.get(STALLED_ROUNDS_FIELD) or 0) + 1

        should_notify = (
            stalled_rounds >= rounds_threshold
            and (last_notified_at <= 0 or now - last_notified_at >= cooldown_seconds)
        )

        return {
            STALLED_ROUNDS_FIELD: stalled_rounds,
            LAST_MISSING_FIELD: missing_count,
        }, stalled_rounds, should_notify

    @staticmethod
    def _build_updater(patches: dict[str, dict], clears: dict[str, set]) -> Callable:
        """生成单次 subscribes 批量更新函数，只合并本模块字段。"""

        def updater(data: dict) -> dict:
            for sid in set(patches) | set(clears):
                exists = sid in data
                record = dict(data.get(sid, {}))
                for key in clears.get(sid, ()):
                    record.pop(key, None)
                if sid in patches:
                    record.update(patches[sid])
                if exists or record:
                    data[sid] = record
            return data

        return updater

    @staticmethod
    def _has_progress_fields(record: dict) -> bool:
        """判断订阅任务记录是否包含本模块字段。"""
        return any(key in record for key in PROGRESS_FIELDS)

    @staticmethod
    def _patch_changes(record: dict, patch: dict) -> bool:
        """判断待写入字段是否会改变当前快照中的诊断状态。"""
        return any(record.get(key) != value for key, value in patch.items())

    def _send_summary(self, due_notify: list, rounds_threshold: int):
        """把本轮所有新达标订阅合并为一条保守的诊断汇总通知。"""
        count = len(due_notify)
        max_lines = 20
        lines = [
            self._detail_line(subscribe, missing_count)
            for subscribe, missing_count, _stalled_rounds in due_notify[:max_lines]
        ]
        if count > max_lines:
            lines.append(f"…… 等共 {count} 个订阅")

        if count == 1:
            title = f"订阅无进展：{due_notify[0][0].name}"
        else:
            title = f"订阅无进展：{count} 个订阅"

        self._notify(
            title,
            text="\n".join(lines),
            reason=f"连续 {rounds_threshold} 轮巡检未观察到订阅进展",
            action=(
                "可能原因包括资源暂未发布、仍在播出/上映窗口、订阅规则或站点范围较窄、识别或下载异常等；"
                "本提示仅供参考"
            ),
            follow_up="如确认规则或站点范围过窄，可在原生订阅中调整后由订阅链路继续补全",
            link="#/subscribe/tv?tab=mysub",
            diagnostic=True,
        )

    @staticmethod
    def _detail_line(subscribe, missing_count: int) -> str:
        """生成通知明细行。"""
        if subscribe.type == "电影":
            return f"· {subscribe.name}（仍未完成）"
        return f"· {ProgressDiagnosticCoordinator._subscribe_label(subscribe)}（仍缺 {missing_count} 集）"

    @staticmethod
    def _subscribe_label(subscribe) -> str:
        """生成订阅名称标签；剧集带季号，电影仅显示名称。"""
        if subscribe.type == "电视剧" and subscribe.season:
            return f"{subscribe.name} S{subscribe.season}"
        return subscribe.name

    def _missing_count(self, subscribe) -> Optional[int]:
        """计算订阅当前缺失数量；不支持的媒体类型跳过。"""
        if subscribe.type == "电视剧":
            return int(subscribe.lack_episode or 0)
        if subscribe.type == "电影":
            return 1
        detail(f"无进展诊断：{self._subscribe_label(subscribe)} 不支持的媒体类型 {subscribe.type}，跳过")
        return None

    def _enabled(self) -> bool:
        """当前仅 notify 模式执行只读诊断提醒。"""
        return self._config.progress_diagnostic_mode == "notify"

    def _rounds_threshold(self) -> int:
        """读取连续无进展轮数阈值。"""
        return int(self._config.progress_diagnostic_stalled_rounds or 0)

    def _cooldown_hours(self) -> int:
        """读取同一订阅两次诊断通知的最小间隔小时数。"""
        return int(self._config.progress_diagnostic_cooldown_hours or 0)
