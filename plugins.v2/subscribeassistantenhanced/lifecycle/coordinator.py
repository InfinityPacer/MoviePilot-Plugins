from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

from app.log import logger

from ..engine.signals import last_aired_episode
from ..engine.types import PauseRecord
from ..shared.log import detail
from ..shared.subscribe import format_subscribe, is_full_best_version_subscribe


def _format_lifecycle_subscribe(subscribe) -> str:
    try:
        return format_subscribe(subscribe)
    except AttributeError:
        return f"订阅 {getattr(subscribe, 'id', '未知')}"


@dataclass
class LifecycleResult:
    """订阅生命周期操作结果，供入口日志、命令回复和测试稳定读取。"""

    changed: bool = False
    stopped: bool = False
    state: str | None = None
    reason: str = ""
    message: str = ""


class DownloadPendingLifecycleAdapter:
    """下载模块使用的窄适配器，保持 DownloadMonitor 不感知完整生命周期编排。"""

    def __init__(self, coordinator: "SubscribeLifecycleCoordinator"):
        self._coordinator = coordinator

    def mark_active(self, subscribe, source: str, reason: str = "") -> bool:
        if source != "download_pending":
            return False
        return self._coordinator.mark_download_pending(subscribe, reason=reason).changed

    def clear_active(self, subscribe, source: str, reason: str = "") -> bool:
        if source != "download_pending":
            return False
        return self._coordinator.release_pending_source(
            subscribe, source="download_pending", reason=reason
        ).changed


class SubscribeLifecycleCoordinator:
    """订阅生命周期编排层，统一协调状态归属和状态变化副作用。"""

    def __init__(
        self,
        *,
        config,
        subscribe_oper,
        pause_manager,
        pending_judge,
        pending_state,
        airing_checker=None,
        tmdb_episodes_fn: Optional[Callable] = None,
        recognize_mediainfo_fn: Optional[Callable] = None,
        is_tv_fn: Optional[Callable] = None,
        schedule_initial_pending_search_fn: Optional[Callable] = None,
        has_active_downloads_fn: Optional[Callable] = None,
        clear_orphan_completion_observation_fn: Optional[Callable] = None,
        clear_tasks_for_pause_fn: Optional[Callable] = None,
    ):
        self._config = config
        self._subscribe_oper = subscribe_oper
        self._pause_manager = pause_manager
        self._pending_judge = pending_judge
        self._pending_state = pending_state
        self._airing = airing_checker
        self._tmdb_episodes = tmdb_episodes_fn
        self._recognize_mediainfo = recognize_mediainfo_fn
        self._is_tv = is_tv_fn
        self._schedule_initial_pending_search = schedule_initial_pending_search_fn
        self._has_active_downloads = has_active_downloads_fn
        self._clear_orphan_completion_observation = clear_orphan_completion_observation_fn
        self._clear_tasks_for_pause = clear_tasks_for_pause_fn

    def download_pending_adapter(self) -> DownloadPendingLifecycleAdapter:
        """返回下载待定窄适配器，供下载模块只操作自身持有的待定来源。"""
        return DownloadPendingLifecycleAdapter(self)

    def handle_subscribe_added(self, subscribe, mediainfo=None, episodes=None) -> LifecycleResult:
        """处理订阅新增后的暂停、待定和按播出进度暂停状态流转。"""
        if not subscribe:
            return LifecycleResult()

        if self._pause_manager and self._pause_manager.check_auto_pause_for_user(subscribe) is True:
            detail(f"订阅新增：{_format_lifecycle_subscribe(subscribe)} 已按用户名规则暂停，跳过后续新增态判定")
            return LifecycleResult(changed=True, stopped=True, state="S", reason="auto_user")

        if not mediainfo:
            return LifecycleResult()

        is_tv_media = True if self._is_tv is None else bool(self._is_tv(mediainfo))
        resolved_episodes = list(episodes or [])
        if episodes is None and is_tv_media and self._tmdb_episodes:
            resolved_episodes = list(self._tmdb_episodes(
                subscribe.tmdbid,
                subscribe.season,
                episode_group=subscribe.episode_group,
            ) or [])

        # 上映前暂停同时适用于电影和剧集，必须先于剧集专属待定/播出间隔流程判定。
        if self._airing and self._pause_manager:
            record = self._airing.check_pre_air(subscribe, mediainfo, episodes=resolved_episodes)
            if record:
                logger.info(f"订阅新增：{_format_lifecycle_subscribe(subscribe)} 满足上映前暂停条件，置为禁用")
                self._pause_manager.pause(subscribe, record)
                return LifecycleResult(changed=True, stopped=True, state="S", reason=record.reason)

        if is_full_best_version_subscribe(subscribe):
            detail(f"订阅新增：{_format_lifecycle_subscribe(subscribe)} 为全集洗版，跳过按集播出暂停/待定")
            return LifecycleResult(stopped=True, reason="full_best_version")

        if self._is_tv is not None and not is_tv_media:
            return LifecycleResult()

        if self._pending_judge:
            pending = self.enter_pending_from_judge(subscribe, mediainfo, resolved_episodes)
            if pending.stopped:
                return pending

        # N 态订阅尚未跑完首轮搜索，不做播出间隔暂停；下载整理入库后由后续入口即时复核。
        if getattr(subscribe, "state", None) == "N":
            detail(f"订阅新增：{_format_lifecycle_subscribe(subscribe)} 仍为新增态，跳过播出间隔暂停")
            return LifecycleResult(state="N")

        return self._pause_after_library_update(
            subscribe, mediainfo, resolved_episodes, source="订阅新增"
        )

    def handle_meta_check_subscription(self, subscribe, mediainfo=None, episodes=None) -> LifecycleResult:
        """元数据巡检入口契约；未处理时返回空生命周期结果。"""
        return LifecycleResult()

    def handle_download_added_for_subscribe(self, subscribe, reason: str = "") -> LifecycleResult:
        """下载命中入口契约；未处理时返回空生命周期结果。"""
        return LifecycleResult()

    def handle_library_updated(self, subscribe_id: int | None = None, reason: str = "") -> LifecycleResult:
        """媒体库更新入口契约；未处理时返回空生命周期结果。"""
        return LifecycleResult()

    def handle_subscribe_modified_state_change(
        self,
        subscribe,
        old_state: str | None,
        new_state: str | None = None,
    ) -> LifecycleResult:
        """接管订阅 S/R 外部状态变化的插件侧暂停记录归属。"""
        new_state = new_state or getattr(subscribe, "state", None)
        if old_state != "S" and new_state == "S":
            changed = bool(self._pause_manager and self._pause_manager.adopt_external(subscribe))
            return LifecycleResult(changed=changed, state="S", reason="external")
        if old_state == "S" and new_state != "S":
            if self._pause_manager:
                self._pause_manager.clear_pause_record(subscribe)
                return LifecycleResult(changed=True, state=new_state, reason="external")
        return LifecycleResult(state=new_state)

    def enter_pending_from_judge(self, subscribe, mediainfo, episodes, state: str | None = None) -> LifecycleResult:
        """按待定判定结果进入 P，并保证新增态补搜在待定归属写入前调度。"""
        should_pending, reason = self._pending_judge.should_enter_pending(subscribe, mediainfo, episodes)
        if not should_pending:
            return LifecycleResult(reason=reason or "")

        if getattr(subscribe, "state", None) == "N" and self._schedule_initial_pending_search:
            self._schedule_initial_pending_search(subscribe)

        self._pending_judge.mark_pending(subscribe, source="pending_judge", reason=reason)
        return LifecycleResult(
            changed=True,
            stopped=True,
            state=state or "P",
            reason=reason,
        )

    def enter_guard_pending(self, subscribe, reason: str) -> LifecycleResult:
        """把完成守卫否决登记为独立待定来源。"""
        self._pending_judge.mark_pending(subscribe, source="guard_veto", reason=reason)
        return LifecycleResult(changed=True, stopped=True, state="P", reason=reason)

    def mark_download_pending(self, subscribe, reason: str) -> LifecycleResult:
        """登记下载待定来源，由 PendingStateCoordinator 负责 P/R 仲裁。"""
        changed = self._pending_state.mark_active(subscribe, source="download_pending", reason=reason)
        return LifecycleResult(changed=changed, state="P" if changed else None, reason=reason)

    def clear_download_pending(self, subscribe_id: int, key: str = "", reason: str = "") -> LifecycleResult:
        """按订阅 ID 释放下载待定来源；下载任务明细键由下载模块自身维护。"""
        subscribe = self._get_subscribe(subscribe_id)
        if not subscribe:
            return LifecycleResult(reason=reason)
        return self.release_pending_source(subscribe, source="download_pending", reason=reason)

    def release_pending_source(self, subscribe, source: str, reason: str) -> LifecycleResult:
        """释放指定待定来源，并按剩余来源决定是否恢复启用态。"""
        changed = self._pending_state.clear_active(subscribe, source=source, reason=reason)
        return LifecycleResult(changed=changed, state="R" if changed else None, reason=reason)

    def reconcile_pending(self, subscribe, reason: str) -> LifecycleResult:
        """恢复缺少有效生命周期归属的待定残留。"""
        changed = self._pending_state.reconcile_orphaned(subscribe, reason=reason)
        return LifecycleResult(changed=changed, state="R" if changed else None, reason=reason)

    def toggle_subscribe_by_user_command(self, subscribe) -> LifecycleResult:
        """用户命令切换订阅状态时，把 S 视为外部暂停并静默恢复。"""
        if getattr(subscribe, "state", None) == "S":
            if not self._pause_manager.get_pause_record(subscribe):
                self._pause_manager.adopt_external(subscribe, detail="插件命令手动暂停")
            changed = self._pause_manager.resume(subscribe, notify=False)
            return LifecycleResult(changed=changed, state="R" if changed else None)

        record = PauseRecord(reason="external", detail="插件命令手动暂停")
        changed = self._pause_manager.pause(subscribe, record, notify=False)
        return LifecycleResult(changed=changed, state="S" if changed else None, reason=record.reason)

    def restore_owned_states_before_reset(self) -> LifecycleResult:
        """重置前恢复增强版明确持有的待定状态，避免残留 P 状态失去来源。"""
        changed = False
        for subscribe in self._list_subscribes(state="P"):
            changed = self._pending_state.clear_all_owned(
                subscribe, reason="插件重置前恢复生命周期状态"
            ) or changed
        return LifecycleResult(
            changed=changed,
            state="R" if changed else None,
            reason="插件重置前恢复生命周期状态",
        )

    def pause_for_no_download(self, subscribe, reason: str) -> LifecycleResult:
        """因长期无下载进入标记暂停，并清理暂停覆盖下不应继续执行的待定任务。"""
        record = PauseRecord(reason="no_download", detail=reason)
        changed = self._pause_manager.pause(subscribe, record, notify=True)
        if changed and self._clear_tasks_for_pause:
            self._clear_tasks_for_pause(subscribe)
        return LifecycleResult(changed=changed, state="S" if changed else None, reason=reason)

    def _pause_after_library_update(self, subscribe, mediainfo, episodes: list, source: str) -> LifecycleResult:
        """媒体库状态已更新后，按当前播出窗口决定是否暂停订阅。"""
        if not (self._airing and self._pause_manager):
            return LifecycleResult()
        record = self._airing.check(
            subscribe,
            mediainfo,
            next_episode=mediainfo.next_episode_to_air,
            latest_episode=last_aired_episode(episodes),
            episodes=episodes,
        )
        if not record:
            return LifecycleResult()
        logger.info(f"{source}：{_format_lifecycle_subscribe(subscribe)} 满足播出间隔暂停条件，置为禁用")
        changed = self._pause_manager.pause(subscribe, record)
        return LifecycleResult(
            changed=bool(changed),
            stopped=bool(changed),
            state="S" if changed else None,
            reason=record.reason,
        )

    def _get_subscribe(self, subscribe_id: int):
        """从订阅表读取订阅对象；缺少读取依赖时返回空。"""
        if not self._subscribe_oper:
            return None
        getter = getattr(self._subscribe_oper, "get", None)
        if not getter:
            return None
        try:
            return getter(subscribe_id)
        except Exception as err:
            logger.warning(f"生命周期编排：读取订阅 {subscribe_id} 失败，错误：{err}")
            return None

    def _list_subscribes(self, **kwargs) -> list:
        """从订阅表读取订阅列表；读取失败时按空列表处理，避免重置流程中断。"""
        if not self._subscribe_oper:
            return []
        lister = getattr(self._subscribe_oper, "list", None)
        if not lister:
            return []
        try:
            return list(lister(**kwargs) or [])
        except Exception as err:
            logger.warning(f"生命周期编排：读取订阅列表失败，错误：{err}")
            return []
