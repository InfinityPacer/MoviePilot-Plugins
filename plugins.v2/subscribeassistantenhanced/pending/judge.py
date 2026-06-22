"""待定（P）进入与退出判定，按状态来源分治。"""
import time
from typing import Callable, Optional

from app.log import logger
from app.schemas.types import MediaType

from ..engine.proximity import assess_completion_proximity
from ..engine.types import CompletionSignal, PendingTimeoutManagerProtocol
from ..shared.config import PluginConfig
from ..shared.log import detail
from ..shared.media import date_context, get_tv_season_air_date, parse_date
from ..shared.subscribe import format_subscribe, resolve_subscribe_media_type
from .state import PendingStateCoordinator

ENTER_TITLES = {
    "pending_judge": "满足剧集待定条件，已标记待定",
    "guard_veto": "完成前检查未通过，已标记待定",
}

EXIT_TITLES = {
    "pending_judge": "剧集待定条件解除，已恢复订阅",
    "guard_veto": "完成前观察结束，已恢复订阅",
}


class PendingJudge:
    """待定判定器，区分 pending_judge 与 guard_veto 来源。"""

    def __init__(self, config: PluginConfig,
                 evaluate_fn: Callable,
                 subscribe_oper,
                 timeout_manager: PendingTimeoutManagerProtocol,
                 task_data_read: Callable,
                 task_data_update: Callable,
                 notify_fn: Optional[Callable] = None,
                 state_coordinator: Optional[PendingStateCoordinator] = None):
        """注入待定判定、状态写库、超时管理、任务数据和状态通知回调。"""
        self._config = config
        self._evaluate = evaluate_fn
        self._subscribe_oper = subscribe_oper
        self._timeout = timeout_manager
        self._read = task_data_read
        self._update = task_data_update
        self._notify = notify_fn
        self._state = state_coordinator or PendingStateCoordinator(
            task_data_read, task_data_update, subscribe_oper=subscribe_oper)

    def should_enter_pending(self, subscribe, mediainfo, episodes: list,
                              signal: Optional[CompletionSignal] = None) -> tuple[bool, str]:
        """按 OR 逻辑判断是否进入待定（P），任一条件满足即待定。"""
        if resolve_subscribe_media_type(subscribe) != MediaType.TV:
            return False, ""

        season_air_date = get_tv_season_air_date(mediainfo, subscribe.season)
        air_date = parse_date(season_air_date or mediainfo.first_air_date)

        pending_days = self._config.auto_tv_pending_days
        if pending_days and air_date:
            from datetime import date, timedelta
            today = date.today()
            if air_date + timedelta(days=pending_days) > today:
                return True, f"{date_context('开播日期', air_date, as_of=today)}，仍在开播待定窗口内"

        ep_count = len(episodes) if episodes else 0
        pending_episodes = self._config.auto_tv_pending_episodes
        if pending_episodes and ep_count <= pending_episodes:
            return True, f"集数不足（{ep_count} ≤ {pending_episodes}）"

        if self._config.pending_use_volatility and signal and not signal.stable:
            proximity = assess_completion_proximity(
                episodes=episodes,
                total=signal.scope_total or subscribe.total_episode or len(episodes or []),
                missing_episodes=None,
            )
            if proximity.near_completion:
                detail_text = f"（{signal.volatility_detail}）" if signal.volatility_detail else ""
                return True, f"目标总集数近期变化{detail_text}"
            detail(f"待定判定：{format_subscribe(subscribe)} 总集数近期变化但未接近完结，不进入待定")

        if episodes and not any(ep.air_date for ep in episodes):
            return True, "本季无任何 air_date 信息"

        return False, ""

    def check_exit(self, subscribe, mediainfo, tmdb_episodes_fn) -> bool:
        """检查待定是否应退出，返回 True 表示已退出。"""
        task_data = self._read_subscribe_task(subscribe)
        if not task_data or task_data.get("state") != "P":
            return False

        source = task_data.get("source", "pending_judge")
        signal: CompletionSignal = self._evaluate(subscribe, mediainfo)

        if source == "pending_judge":
            if signal.completed:
                self._exit_pending(subscribe, "信号确认完结")
                return True
            episodes = tmdb_episodes_fn(
                subscribe.tmdbid,
                subscribe.season,
                episode_group=subscribe.episode_group,
            )
            should_stay, _ = self.should_enter_pending(subscribe, mediainfo, episodes, signal)
            if not should_stay:
                self._exit_pending(subscribe, "待定条件不再满足")
                return True
            return False

        elif source == "guard_veto":
            if signal.completed and signal.confidence != "low":
                self._exit_pending(subscribe, "信号确认完结")
                return True
            if self._timeout.check_release(
                subscribe,
                signal,
                total_episode=signal.scope_total or subscribe.total_episode,
            ):
                self._exit_pending(subscribe, "完成前观察结束")
                return True
            return False

        return False

    def _exit_pending(self, subscribe, reason: str):
        """退出当前待定来源，并由 PendingStateCoordinator 仲裁是否恢复启用（R）。"""
        sid = subscribe.id
        logger.info(f"待定退出：{format_subscribe(subscribe)} 退出待定（P），原因：{reason}")
        task = self._read_subscribe_task(subscribe)
        source = task.get("source", "pending_judge")
        if source == "guard_veto":
            self._timeout.clear_block(sid)
        restored = self._state.clear_active(
            subscribe,
            source=source,
            reason=reason,
        )
        if restored:
            title = EXIT_TITLES.get(source)
            if title:
                self._notify_status(subscribe, title, detail=reason)
        else:
            self._update_subscribe_task(subscribe, {
                "exit_reason": reason,
                "exit_at": time.time(),
            })

    def mark_pending(self, subscribe, source: str = "pending_judge",
                     reason: str = ""):
        """登记待定来源，并在订阅真实进入待定（P）时发送状态通知。"""
        sid = subscribe.id
        detail(
            f"待定进入：{format_subscribe(subscribe)} 标记为待定（P），"
            f"来源={source}，原因：{reason}"
        )
        changed = self._state.mark_active(subscribe, source=source, reason=reason)
        title = ENTER_TITLES.get(source)
        if changed and title:
            self._notify_status(subscribe, title, detail=reason)

    def _read_subscribe_task(self, subscribe) -> dict:
        """读取订阅的任务数据。"""
        sid = str(subscribe.id)
        data = self._read("subscribes")
        return data.get(sid, {})

    def _update_subscribe_task(self, subscribe, updates: dict):
        """更新订阅的任务数据。"""
        sid = str(subscribe.id)

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            task.update(updates)
            data[sid] = task
            return data

        self._update("subscribes", updater)

    def _notify_status(self, subscribe, title_suffix: str, detail: Optional[str] = None):
        """发送待定状态通知。"""
        if not self._notify:
            return
        self._notify(subscribe, title_suffix, detail=detail)
