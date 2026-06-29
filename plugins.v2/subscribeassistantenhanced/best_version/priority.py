"""订阅下载事实管理：记录回填入口与按种子基线。"""
from typing import Callable, Optional

from app.chain.subscribe import SubscribeChain
from app.schemas.types import MediaType

from ..shared.log import detail
from ..shared.subscribe import (
    format_subscribe_label,
    is_full_best_version_subscribe,
    is_tv_episode_best_version_subscribe,
    resolve_subscribe_media_type,
)
from ..shared.update import update_subscribe


class PriorityManager:
    """订阅事实管理，实现 PriorityManagerProtocol。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 subscribe_oper=None, plugin_name: str = "订阅助手（增强版）"):
        self._read = task_data_read
        self._update = task_data_update
        self._subscribe_oper = subscribe_oper
        self._plugin_name = plugin_name

    def _format_backfill_scene(self, scene: str) -> str:
        """为主程序 backfill 场景补充插件名，便于按来源追踪写入。"""
        if scene.endswith(">") and "<" in scene:
            return scene
        return f"{scene}<{self._plugin_name}>"

    def capture_baseline(self, subscribe, torrent_priority: int) -> dict:
        """下载前记录整体优先级基线，用于失败回滚。"""
        sid = str(subscribe.id)
        baseline = {
            "episode_priority": dict(subscribe.episode_priority or {}),
            "current_priority": subscribe.current_priority or 0,
            "torrent_priority": torrent_priority,
        }

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            task["priority_baseline"] = baseline
            data[sid] = task
            return data

        self._update("subscribes", updater)
        return baseline

    def update_on_download(self, subscribe, episodes: list, new_priority: int):
        """下载事实由主程序下载链路写入；插件侧保留协议方法但不再直接写 TV 进度字段。"""
        return

    def rollback(self, subscribe, baseline: Optional[dict] = None):
        """下载失败或种子删除后按媒体类型恢复事实字段。"""
        if not baseline:
            sid = str(subscribe.id)
            data = self._read("subscribes")
            task = data.get(sid, {})
            baseline = task.get("priority_baseline")
        if not baseline:
            return

        media_type = resolve_subscribe_media_type(subscribe)
        if media_type == MediaType.TV:
            episode_priority = baseline.get("episode_priority", {})
            detail(f"洗版事实：{self._format_subscribe_label(subscribe)} 已恢复到下载前剧集优先级基线")
            self._update_tv_episode_priority(subscribe, episode_priority, scene="plugin_rollback")
            return

        if media_type == MediaType.MOVIE and self._subscribe_oper:
            payload = {"current_priority": baseline.get("current_priority", 0)}
            detail(
                f"洗版优先级：{self._format_subscribe_label(subscribe)} "
                f"已恢复到下载前优先级 current_priority={payload['current_priority']}"
            )
            update_subscribe(self._subscribe_oper, subscribe.id, payload)

    def capture_torrent_baseline(self, subscribe, torrent_id, episodes, contributed_priority,
                                 target_episodes=None):
        """按种子记录洗版优先级基线，用于按集归属回滚。

        episode_priority_baseline 保存各集旧值，contributed_priority 保存本种子贡献档位；
        整季包 episodes 为空时回退到目标集范围。多种子并行时各自保存基线，避免串号污染。
        """
        if not torrent_id:
            return
        sid = str(subscribe.id)
        ep_priority = self._episode_priority_snapshot(subscribe)
        eps = episodes or target_episodes or []
        ep_baseline = {str(ep): ep_priority.get(str(ep), 0) for ep in eps}

        def updater(data: dict) -> dict:
            task = data.get(sid, {})
            baselines = task.get("priority_baselines", {})
            baselines[str(torrent_id)] = {
                "episode_priority_baseline": ep_baseline,
                "contributed_priority": contributed_priority,
                "current_priority_baseline": subscribe.current_priority or 0,
            }
            task["priority_baselines"] = baselines
            data[sid] = task
            return data

        self._update("subscribes", updater)

    def rollback_torrent(self, subscribe, torrent_id):
        """按集归属回滚单个种子的洗版贡献，并保留其他种子已提升的优先级。"""
        if not torrent_id:
            return
        sid = str(subscribe.id)
        data = self._read("subscribes")
        baseline = data.get(sid, {}).get("priority_baselines", {}).get(str(torrent_id))
        if not baseline:
            return
        media_type = resolve_subscribe_media_type(subscribe)
        if media_type == MediaType.TV:
            contributed = baseline.get("contributed_priority", 0)
            ep_baseline = baseline.get("episode_priority_baseline", {})
            ep_priority = self._episode_priority_snapshot(subscribe)
            for ep_key, old_value in ep_baseline.items():
                # 仅回滚当前值仍等于本种子贡献档位的集；其他种子已升级的集必须保留。
                if ep_priority.get(ep_key, 0) == contributed:
                    ep_priority[ep_key] = old_value
            detail(f"洗版事实：{self._format_subscribe_label(subscribe)} 已恢复种子 {torrent_id} 对应集的优先级")
            self._update_tv_episode_priority(subscribe, ep_priority, scene="plugin_rollback")
        elif media_type == MediaType.MOVIE and self._subscribe_oper:
            current = subscribe.current_priority or 0
            contributed = baseline.get("contributed_priority", 0)
            if current == contributed:
                payload = {"current_priority": baseline.get("current_priority_baseline", 0)}
                detail(
                    f"洗版优先级：{self._format_subscribe_label(subscribe)} "
                    f"已恢复种子 {torrent_id} 的电影优先级 current_priority={payload['current_priority']}"
                )
                update_subscribe(self._subscribe_oper, subscribe.id, payload)

        def cleaner(d: dict) -> dict:
            d.get(sid, {}).get("priority_baselines", {}).pop(str(torrent_id), None)
            return d

        self._update("subscribes", cleaner)

    @staticmethod
    def can_backfill(subscribe) -> bool:
        """判断订阅是否允许按媒体库已有集回填；仅剧集分集洗版适用。"""
        return is_tv_episode_best_version_subscribe(subscribe)

    def backfill_existing(self, subscribe, existing_episodes: list, scene: str = "plugin_backfill") -> bool:
        """为分集洗版把在库集交给主程序 backfill 合同落库，产生写入时返回 True。"""
        if not self.can_backfill(subscribe) or not existing_episodes:
            return False
        summary = SubscribeChain().backfill_existing_episodes(
            subscribe,
            existing_episodes,
            priority=100,
            scene=self._format_backfill_scene(scene),
        )
        return bool(summary and summary.get("updated"))

    def is_complete(self, subscribe) -> bool:
        """判断洗版是否完成——所有目标集优先级达标（>=100）。"""
        ep_priority = subscribe.episode_priority or {}
        target_episodes = self._target_episodes(subscribe)
        if not ep_priority or not target_episodes:
            return False
        return all(ep_priority.get(str(ep), 0) >= 100 for ep in target_episodes)

    def mark_complete(self, subscribe):
        """标记洗版完成；TV 交给主程序 backfill 合同写事实，电影写整体优先级。"""
        if resolve_subscribe_media_type(subscribe) == MediaType.MOVIE:
            payload = {"current_priority": 100}
            mode_label = self._mode_label(subscribe)
            detail(f"洗版优先级：{self._format_subscribe_label(subscribe)} 标记{mode_label}完成（priority=100）")
            if self._subscribe_oper:
                update_subscribe(self._subscribe_oper, subscribe.id, payload)
            return

        target_episodes = self._target_episodes(subscribe)
        mode_label = self._mode_label(subscribe)
        detail(f"洗版优先级：{self._format_subscribe_label(subscribe)} 标记{mode_label}完成（priority=100）")
        if target_episodes:
            SubscribeChain().backfill_existing_episodes(
                subscribe,
                target_episodes,
                priority=100,
                scene=self._format_backfill_scene("plugin_complete"),
            )

    @staticmethod
    def _target_episodes(subscribe) -> list:
        """读取订阅目标集范围；范围无效时返回空，避免只凭已有 priority 键误判完成。"""
        try:
            start_episode = int(subscribe.start_episode or 1)
            total_episode = int(subscribe.total_episode or 0)
        except (TypeError, ValueError):
            return []
        start_episode = max(start_episode, 1)
        if total_episode < start_episode:
            return []
        return list(range(start_episode, total_episode + 1))

    @staticmethod
    def _format_subscribe_label(subscribe) -> str:
        """生成洗版优先级日志标签；字段不足时由公共格式化器回退到 ID。"""
        return format_subscribe_label(subscribe)

    @staticmethod
    def _mode_label(subscribe) -> str:
        """按订阅实际洗版形态返回优先级日志标签。"""
        if is_full_best_version_subscribe(subscribe):
            return "洗版"
        if is_tv_episode_best_version_subscribe(subscribe):
            return "分集洗版"
        return "洗版"

    @staticmethod
    def _episode_priority_snapshot(subscribe) -> dict:
        """读取剧集优先级快照；无按集事实时复用主程序 current_priority 兜底口径。"""
        return SubscribeChain.get_episode_priority(subscribe)

    def _update_tv_episode_priority(self, subscribe, episode_priority: dict, scene: str):
        """写回 TV 剧集事实后刷新主程序进度字段。"""
        if not self._subscribe_oper:
            return
        update_subscribe(self._subscribe_oper, subscribe.id, {"episode_priority": episode_priority})
        subscribe.episode_priority = episode_priority
        SubscribeChain().refresh_subscribe_progress(subscribe, scene=scene)
