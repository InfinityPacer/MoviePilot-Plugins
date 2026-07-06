"""搜索诊断协调器：识别"按原规则长期搜不到"的订阅并发出诊断通知。

设计约束（重要）：
- 只读观察，不触发搜索、不修改订阅的 include/exclude/站点范围、不下载。
- "搜不到"的判据采用事实信号法：连续多轮巡检中订阅缺失集数（lack_episode）
  未减少，即视为该轮"未搜到新资源"，累计达到阈值后提醒用户检查过滤规则/站点。
  该判据不依赖主程序 search 返回值，因此不介入搜索召回链路。
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

# 单轮巡检最多处理的候选数，避免大量订阅时单轮耗时过长
MAX_CANDIDATES = 50


class NoResultDiagnosticCoordinator:
    """维护"长期搜不到"诊断状态并按阈值/冷却发出通知。

    该协调器只观察订阅的缺失集数变化，不触发搜索、不改动搜索规则、不下载。
    """

    def __init__(self, config, task_data_read: Callable, task_data_update: Callable,
                 subscribe_oper, notify_fn: Callable,
                 get_subscribe_image_fn: Optional[Callable] = None,
                 now_fn: Optional[Callable] = None):
        """注入配置、任务数据读写、订阅查询和通知入口。

        :param config: 插件配置对象（稳定的内部结构）。
        :param task_data_read: 任务数据读取函数（TaskDataManager.read）。
        :param task_data_update: 任务数据读-改-写函数（TaskDataManager.update）。
        :param subscribe_oper: 订阅查询操作对象。
        :param notify_fn: 通知发送函数（插件的 _notify_subscribe）。
        :param get_subscribe_image_fn: 可选，返回订阅海报图片的函数。
        :param now_fn: 可选，可替换时钟，便于测试。
        """
        self._config = config
        self._read = task_data_read
        self._update = task_data_update
        self._subscribe_oper = subscribe_oper
        self._notify = notify_fn
        self._get_image = get_subscribe_image_fn
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
        alive_sids = set()
        processed = 0
        for subscribe in subscribes:
            if processed >= MAX_CANDIDATES:
                detail(f"搜索诊断：本轮已达到 {MAX_CANDIDATES} 个候选上限")
                break
            sid = str(subscribe.id)
            lack = self._lack_episode(subscribe)
            # 只诊断"仍缺集"的订阅；已补齐的订阅不属于搜不到
            if lack <= 0:
                continue
            alive_sids.add(sid)
            processed += 1
            self._evaluate(subscribe, sid, lack, now, rounds_threshold, cooldown_seconds)

        # 清理已不再需要跟踪的订阅记录（已补齐/已删除/已非启用）
        self._prune(alive_sids)

    def _evaluate(self, subscribe, sid: str, lack: int, now: float,
                  rounds_threshold: int, cooldown_seconds: int):
        """比对本轮与上轮缺集数，更新轮数并在达标时通知。"""
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

        notified_at = last_notified_at
        if should_notify:
            self._send_notification(subscribe, lack, miss_rounds)
            notified_at = now
            logger.info(
                f"搜索诊断：{format_subscribe(subscribe)} 连续 {miss_rounds} 轮未搜到资源，"
                f"缺 {lack} 集，已发送诊断通知"
            )

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            task["miss_rounds"] = miss_rounds
            task["last_lack"] = lack
            task["last_notified_at"] = notified_at
            data[sid] = task
            return data

        self._update(NO_RESULT_TASK_KEY, updater)

    def _send_notification(self, subscribe, lack: int, miss_rounds: int):
        """发送诊断通知，提示用户检查过滤规则与站点范围。"""
        title = f"{format_subscribe_label(subscribe, str(subscribe.id))} 长期未搜到资源"
        image = None
        if self._get_image:
            try:
                image = self._get_image(subscribe)
            except Exception:
                image = None
        link = (
            "#/subscribe/tv?tab=mysub"
            if getattr(subscribe, "type", "") == "电视剧"
            else "#/subscribe/movie?tab=mysub"
        )
        self._notify(
            title,
            reason=f"连续 {miss_rounds} 轮巡检缺失集数未减少，当前仍缺 {lack} 集",
            action="请检查订阅的过滤规则（include/exclude）、优先级规则组与站点范围是否过严",
            image=image,
            link=link,
            diagnostic=True,
        )

    def _prune(self, alive_sids: set):
        """移除不在本轮活跃集合中的历史记录，避免无限增长。"""
        current = self._read(NO_RESULT_TASK_KEY) or {}
        stale = [sid for sid in current if sid not in alive_sids]
        if not stale:
            return

        def updater(data: dict) -> dict:
            for sid in stale:
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
