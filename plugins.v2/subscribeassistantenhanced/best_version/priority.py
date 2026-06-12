"""洗版优先级管理：统一 episode_priority / current_priority 与按种子基线。"""
from typing import Callable, Optional

from ..shared.log import detail
from ..shared.subscribe import format_subscribe_label
from ..shared.update import update_subscribe


class PriorityManager:
    """洗版优先级管理，实现 PriorityManagerProtocol。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 subscribe_oper=None):
        self._read = task_data_read
        self._update = task_data_update
        self._subscribe_oper = subscribe_oper

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
        """下载成功后更新对应集的优先级。"""
        if not episodes:
            return
        ep_priority = dict(subscribe.episode_priority or {})
        for ep in episodes:
            ep_key = str(ep)
            current = ep_priority.get(ep_key, 0)
            if new_priority > current:
                ep_priority[ep_key] = new_priority

        payload = {"episode_priority": ep_priority}
        max_priority = max(ep_priority.values()) if ep_priority else 0
        if max_priority > (subscribe.current_priority or 0):
            payload["current_priority"] = max_priority

        if self._subscribe_oper:
            update_subscribe(self._subscribe_oper, subscribe.id, payload)

    def rollback(self, subscribe, baseline: Optional[dict] = None):
        """下载失败或种子删除后整体回滚到优先级基线。"""
        if not baseline:
            sid = str(subscribe.id)
            data = self._read("subscribes")
            task = data.get(sid, {})
            baseline = task.get("priority_baseline")
        if not baseline:
            return

        payload = {
            "episode_priority": baseline.get("episode_priority", {}),
            "current_priority": baseline.get("current_priority", 0),
        }
        detail(f"洗版优先级：{self._format_subscribe_label(subscribe)} 已恢复到下载前优先级 current_priority={payload['current_priority']}")
        if self._subscribe_oper:
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
        ep_priority = dict(subscribe.episode_priority or {})
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
        contributed = baseline.get("contributed_priority", 0)
        ep_baseline = baseline.get("episode_priority_baseline", {})
        ep_priority = dict(subscribe.episode_priority or {})
        for ep_key, old_value in ep_baseline.items():
            # 仅回滚当前值仍等于本种子贡献档位的集；其他种子已升级的集必须保留。
            if ep_priority.get(ep_key, 0) == contributed:
                ep_priority[ep_key] = old_value
        new_current = max(ep_priority.values()) if ep_priority else 0
        detail(f"洗版优先级：{self._format_subscribe_label(subscribe)} 已恢复种子 {torrent_id} 对应集的优先级，current_priority→{new_current}")
        if self._subscribe_oper:
            update_subscribe(self._subscribe_oper, subscribe.id, {
                "episode_priority": ep_priority,
                "current_priority": new_current,
            })

        def cleaner(d: dict) -> dict:
            d.get(sid, {}).get("priority_baselines", {}).pop(str(torrent_id), None)
            return d

        self._update("subscribes", cleaner)

    def backfill_existing(self, subscribe, existing_episodes: list):
        """根据媒体库已有集回填优先级为 100，跳过已有集的洗版。"""
        if not existing_episodes:
            return
        ep_priority = dict(subscribe.episode_priority or {})
        for ep in existing_episodes:
            ep_priority[str(ep)] = 100

        payload = {"episode_priority": ep_priority}
        if self._subscribe_oper:
            update_subscribe(self._subscribe_oper, subscribe.id, payload)

    def is_complete(self, subscribe) -> bool:
        """判断洗版是否完成——所有目标集优先级达标（>=100）。"""
        ep_priority = subscribe.episode_priority or {}
        target_episodes = self._target_episodes(subscribe)
        if not ep_priority or not target_episodes:
            return False
        return all(ep_priority.get(str(ep), 0) >= 100 for ep in target_episodes)

    def mark_complete(self, subscribe):
        """标记洗版完成，所有集写 priority=100。"""
        ep_priority = dict(subscribe.episode_priority or {})
        target_episodes = self._target_episodes(subscribe)
        if target_episodes:
            for ep in target_episodes:
                ep_priority[str(ep)] = 100
        else:
            for key in ep_priority:
                ep_priority[key] = 100

        payload = {"episode_priority": ep_priority, "current_priority": 100}
        mode = "全集" if subscribe.best_version_full else "分集"
        detail(f"洗版优先级：{self._format_subscribe_label(subscribe)} 标记{mode}洗版完成（priority=100）")
        if self._subscribe_oper:
            update_subscribe(self._subscribe_oper, subscribe.id, payload)

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
