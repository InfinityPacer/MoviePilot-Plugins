"""搜索诊断协调器：识别"订阅长期无新进展"并发出保守的诊断提示。

设计约束（重要）：
- 只读观察，不触发搜索、不修改订阅的 include/exclude/站点范围、不下载。
- 判据采用事实信号法：连续多轮巡检中订阅缺失集数（lack_episode）未减少，
  即视为该轮"无新进展"，累计达到阈值后发出保守提示。该判据只能说明订阅
  暂无进展，不足以确定具体原因（资源暂缺、仍在播出、规则或站点过窄、识别或
  下载异常等），因此通知文案不对原因下定论，仅供用户参考。
- 判据不依赖主程序 search 返回值，不介入搜索召回链路。
- 通知带冷却，避免同一订阅反复打扰。

状态持久化在任务数据的独立 key ``no_result`` 下，结构为::

    data[str(sid)] = {
        "miss_rounds": int,        # 连续未减少缺集的巡检轮数
        "last_lack": int,          # 上轮记录的缺失集数
        "last_notified_at": float, # 上次诊断通知时间戳，用于冷却
    }
"""
import time
from typing import Callable, Optional

from app.log import logger

from ..shared.log import detail
from ..shared.subscribe import format_subscribe, format_subscribe_label


# 任务数据 key，与其它子模块（subscribes/blocks/...）并列
NO_RESULT_TASK_KEY = "no_result"


class NoResultDiagnosticCoordinator:
    """维护"长期搜不到"诊断状态并按阈值/冷却发出通知。

    该协调器只观察订阅的缺失集数变化，不触发搜索、不改动搜索规则、不下载。
    """

    def __init__(self, config, task_data_read: Callable, task_data_update: Callable,
                 subscribe_oper, notify_fn: Callable,
                 now_fn: Optional[Callable] = None):
        """注入配置、任务数据读写、订阅查询和通知入口。

        :param config: 插件配置对象（稳定的内部结构）。
        :param task_data_read: 任务数据读取函数（TaskDataManager.read）。
        :param task_data_update: 任务数据读-改-写函数（TaskDataManager.update）。
        :param subscribe_oper: 订阅查询操作对象。
        :param notify_fn: 通知发送函数（插件的 _notify_subscribe）。
        :param now_fn: 可选，可替换时钟，便于测试。
        """
        self._config = config
        self._read = task_data_read
        self._update = task_data_update
        self._subscribe_oper = subscribe_oper
        self._notify = notify_fn
        self._now = now_fn or time.time

    def run(self):
        """扫描启用中的订阅，累计"未搜到"轮数并按阈值发出诊断通知。"""
        if not self._enabled():
            detail("搜索诊断：未开启，跳过")
            return
        if not self._subscribe_oper:
            detail("搜索诊断：订阅查询依赖未就绪，跳过")
            return

        rounds_threshold = self._rounds_threshold()
        if rounds_threshold <= 0:
            detail("搜索诊断：轮数阈值为 0，跳过")
            return

        now = self._now()
        cooldown_seconds = self._cooldown_hours() * 3600
        subscribes = self._subscribe_oper.list(state="R") or []

        # 本轮实际完整扫描到的订阅集合。诊断为纯只读观察 + 轻量状态更新，
        # 不发起搜索请求，开销很小，因此不做固定截断，避免订阅较多时列表
        # 尾部订阅永远无法累计轮数、且其历史状态被误清理导致漏诊断。
        scanned_sids = set()
        # 本轮新达到阈值、需要提醒的订阅统一收集，最后合并为一条汇总通知，
        # 避免订阅较多时逐条推送造成通知风暴。
        due_notify = []
        for subscribe in subscribes:
            sid = str(subscribe.id)
            scanned_sids.add(sid)
            lack = self._lack_episode(subscribe)
            if lack <= 0:
                # 已补齐：不属于搜不到，清掉可能存在的历史计数
                self._clear(sid)
                continue
            if self._evaluate(subscribe, sid, lack, now, rounds_threshold, cooldown_seconds):
                due_notify.append((subscribe, lack))

        if due_notify:
            self._send_summary(due_notify)

        # 仅清理"已不在启用订阅列表中"（删除/暂停/完成）的历史记录；
        # 只按本轮完整扫描到的订阅全集判断，不受任何截断影响。
        self._prune(scanned_sids)

    def _evaluate(self, subscribe, sid: str, lack: int, now: float,
                  rounds_threshold: int, cooldown_seconds: int) -> bool:
        """比对本轮与上轮缺集数并更新轮数。

        返回本轮是否"新达到阈值且已过冷却"，由调用方收集后合并为一条汇总通知。
        """
        record = (self._read(NO_RESULT_TASK_KEY) or {}).get(sid, {})
        last_lack = record.get("last_lack")
        last_notified_at = float(record.get("last_notified_at") or 0)

        if last_lack is None:
            # 首次观察：仅登记基线，不计轮数
            miss_rounds = 0
        elif lack < int(last_lack):
            # 缺集减少，说明搜到并下载了新资源，重置计数
            miss_rounds = 0
        else:
            # 缺集未减少，累计一轮"未搜到"
            miss_rounds = int(record.get("miss_rounds", 0)) + 1

        should_notify = (
            miss_rounds >= rounds_threshold
            and (last_notified_at <= 0 or now - last_notified_at >= cooldown_seconds)
        )

        notified_at = now if should_notify else last_notified_at
        if should_notify:
            logger.info(
                f"搜索诊断：{format_subscribe(subscribe)} 连续 {miss_rounds} 轮未搜到资源，"
                f"缺 {lack} 集，纳入本轮诊断汇总"
            )

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            task["miss_rounds"] = miss_rounds
            task["last_lack"] = lack
            task["last_notified_at"] = notified_at
            data[sid] = task
            return data

        self._update(NO_RESULT_TASK_KEY, updater)
        return should_notify

    def _send_summary(self, due_notify: list):
        """把本轮所有新达标订阅合并为一条保守的诊断汇总通知，避免通知风暴。

        :param due_notify: [(subscribe, lack), ...]
        """
        count = len(due_notify)
        # 逐条明细，条数较多时截断展示，完整数量在标题体现
        max_lines = 20
        lines = []
        for subscribe, lack in due_notify[:max_lines]:
            lines.append(f"· {format_subscribe_label(subscribe, str(subscribe.id))}（仍缺 {lack} 集）")
        if count > max_lines:
            lines.append(f"…… 等共 {count} 个订阅")

        title = (
            f"{count} 个订阅长期无新进展"
            if count > 1
            else f"{format_subscribe_label(due_notify[0][0], str(due_notify[0][0].id))} 长期无新进展"
        )
        # 跳转到订阅管理页；汇总覆盖多个订阅，不附单个海报
        link = "#/subscribe/tv?tab=mysub"
        self._notify(
            title,
            text="\n".join(lines),
            action=(
                "可能原因较多（资源暂未发布、仍在播出、订阅规则或站点范围较窄、识别或下载异常等），"
                "本提示仅供参考，建议在方便时留意这些订阅"
            ),
            follow_up="如确认规则或站点范围过窄，可在原生订阅中调整后由订阅链路继续搜索",
            link=link,
            diagnostic=True,
        )

    def _prune(self, scanned_sids: set):
        """移除已不在启用订阅列表中的历史记录（删除/暂停/完成），避免无限增长。

        仅依据本轮完整扫描到的订阅全集判断，不做候选截断，因此不会误删
        尚未轮到扫描的活跃订阅状态。
        """
        current = self._read(NO_RESULT_TASK_KEY) or {}
        stale = [sid for sid in current if sid not in scanned_sids]
        if not stale:
            return

        def updater(data: dict) -> dict:
            for sid in stale:
                data.pop(sid, None)
            return data

        self._update(NO_RESULT_TASK_KEY, updater)

    def _clear(self, sid: str):
        """清除单个订阅的诊断计数（例如已补齐缺集）。"""
        current = self._read(NO_RESULT_TASK_KEY) or {}
        if sid not in current:
            return

        def updater(data: dict) -> dict:
            data.pop(sid, None)
            return data

        self._update(NO_RESULT_TASK_KEY, updater)

    def _enabled(self) -> bool:
        """读取搜索诊断总开关。"""
        return bool(self._config.no_result_diagnostic_enabled)

    def _rounds_threshold(self) -> int:
        """读取连续未搜到的轮数阈值 N。"""
        return int(self._config.no_result_diagnostic_rounds or 0)

    def _cooldown_hours(self) -> int:
        """读取同一订阅两次诊断通知的最小间隔小时数。"""
        return int(self._config.no_result_diagnostic_cooldown_hours or 0)

    @staticmethod
    def _lack_episode(subscribe) -> int:
        """读取订阅缺失集数；电影缺失以未入库视为 1。"""
        lack = getattr(subscribe, "lack_episode", None)
        if lack is None:
            # 电影订阅无 lack_episode 概念，用 total-已完成近似；缺省按仍缺处理
            return 1 if getattr(subscribe, "type", "") == "电影" else 0
        try:
            return int(lack)
        except (TypeError, ValueError):
            return 0
