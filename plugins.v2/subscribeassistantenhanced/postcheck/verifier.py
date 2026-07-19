"""完成后异步自验证：保存完成快照、检测增集并重建订阅。"""
import time
from typing import Callable, Optional

from app.log import logger

from ..engine.types import SeasonScope
from ..shared.log import detail
from ..shared.subscribe import format_subscribe, format_subscribe_label, is_full_best_version_subscribe


class CompletionVerifier:
    """完成后定期复查 TMDB，发现增集自动重建订阅。"""

    def __init__(self, task_data_read: Callable, task_data_update: Callable,
                 tmdb_episodes_fn: Optional[Callable] = None,
                 subscribe_oper=None,
                 retention_days: int = 180,
                 notify_fn: Optional[Callable] = None,
                 rebuild_subscribe_fn: Optional[Callable] = None):
        """注入完成快照存储、集数查询、订阅查询和真实订阅重建能力。"""
        self._read = task_data_read
        self._update = task_data_update
        self._tmdb_fn = tmdb_episodes_fn
        self._subscribe_oper = subscribe_oper
        self._retention_seconds = retention_days * 86400
        self._notify = notify_fn
        self._rebuild_subscribe = rebuild_subscribe_fn

    def snapshot(self, subscribe, mediainfo, scope: Optional[SeasonScope]):
        """保存完成快照，同一季同一剧集组只保留最新记录。"""
        tmdbid = subscribe.tmdbid
        season = subscribe.season
        episode_group_id = subscribe.episode_group
        total = subscribe.total_episode

        snap = {
            "tmdbid": tmdbid,
            "season": season,
            "episode_group_id": episode_group_id,
            "scope_source": scope.source if scope else "main_season",
            "total_at_completion": total,
            "completed_at": time.time(),
            "subscribe_config": _extract_config(subscribe),
        }

        def updater(data: dict) -> dict:
            snapshots = data.get("list", [])
            key = (tmdbid, season, episode_group_id)
            snapshots = [s for s in snapshots if _snap_key(s) != key]
            snapshots.append(snap)
            data["list"] = snapshots
            return data

        detail(f"完成后验证：{format_subscribe_label(subscribe)} 登记完成快照（完成时总集数={total}）")
        self._update("snapshots", updater)

    def verify_all(self):
        """定时复查所有完成快照。"""
        self.cleanup_expired()
        data = self._read("snapshots")
        snapshots = data.get("list", [])
        to_remove = []

        for snap in snapshots:
            current_total = self._fetch_current_total(snap)
            if current_total is not None and current_total > snap.get("total_at_completion", 0):
                snap_label = _format_snapshot_label(snap)
                logger.info(f"完成后验证：{snap_label} 检测到增集 {snap.get('total_at_completion', 0)}→{current_total}，尝试重建订阅")
                if self._rebuild(snap, current_total):
                    to_remove.append(snap)

        if to_remove:
            self._remove_snapshots(to_remove)

    def cleanup_expired(self) -> int:
        """按用户配置的保留期清理 H 快照，不请求 TMDB。"""
        data = self._read("snapshots")
        snapshots = data.get("list", [])
        now = time.time()
        expired = [
            snap for snap in snapshots
            if now - snap.get("completed_at", now) > self._retention_seconds
        ]
        if expired:
            self._remove_snapshots(expired)
        return len(expired)

    def _fetch_current_total(self, snap: dict) -> Optional[int]:
        if not self._tmdb_fn:
            return None
        episode_group_id = snap.get("episode_group_id")
        if episode_group_id:
            episodes = self._tmdb_fn(snap["tmdbid"], snap["season"],
                                      episode_group=episode_group_id)
        else:
            episodes = self._tmdb_fn(snap["tmdbid"], snap["season"])
        return len(episodes) if episodes else None

    def _rebuild(self, snap: dict, current_total: int) -> bool:
        """发现增集后清理完成快照并重建订阅；失败时保留快照重试。"""
        if not self._subscribe_oper:
            return False
        tmdbid = snap["tmdbid"]
        season = snap["season"]
        episode_group_id = snap.get("episode_group_id")
        config = dict(snap.get("subscribe_config", {}))
        removed_full_best_version = False

        existing = self._subscribe_oper.list()
        matched = [
            sub for sub in (existing or [])
            if (
                sub.tmdbid == tmdbid
                and sub.season == season
                and sub.episode_group == episode_group_id
            )
        ]
        if any((sub.total_episode or 0) >= current_total for sub in matched):
            return True

        # 普通或分集洗版订阅由现有订阅流程继续处理；目标范围尚未覆盖时不能消费完成快照。
        if any(not is_full_best_version_subscribe(sub) for sub in matched):
            return False

        for sub in matched:
            logger.info(f"完成后验证：删除旧洗版订阅 {format_subscribe_label(sub)} 以便重建增集订阅")
            _merge_missing_config_from_subscribe(config, sub)
            self._subscribe_oper.delete(sub.id)
            removed_full_best_version = True

        old_total = snap.get("total_at_completion", 0)
        config["start_episode"] = old_total + 1
        if not self._rebuild_subscribe or not self._rebuild_subscribe(snap, config):
            return False

        if self._notify:
            name = config.get("name", f"TMDB {tmdbid}")
            season = config.get("season", season)
            season_text = f" S{season}" if season is not None else ""
            action_text = "已移除旧洗版订阅并重建订阅" if removed_full_best_version else "已自动重建订阅"
            self._notify(
                f"{name}{season_text} 检测到新增集数（{old_total}→{current_total}），{action_text}",
            )
        return True

    def _remove_snapshots(self, to_remove: list):
        keys_to_remove = {_snap_key(s) for s in to_remove}

        def updater(data: dict) -> dict:
            snapshots = data.get("list", [])
            data["list"] = [s for s in snapshots if _snap_key(s) not in keys_to_remove]
            return data

        self._update("snapshots", updater)


def _snap_key(snap: dict) -> tuple:
    return (snap.get("tmdbid"), snap.get("season"), snap.get("episode_group_id"))


def _format_snapshot_label(snap: dict) -> str:
    """格式化完成快照日志标签；配置缺名称时回退到 TMDB/季号。"""
    config = snap.get("subscribe_config") or {}
    name = config.get("name")
    if name:
        probe = type("SnapshotSubscribe", (), {"name": name, "season": snap.get("season")})()
        return format_subscribe(probe)
    return f"TMDB {snap.get('tmdbid')} S{snap.get('season')}"


def _extract_config(subscribe) -> dict:
    """提取订阅配置用于重建。"""
    values = {
        "name": subscribe.name,
        "tmdbid": subscribe.tmdbid,
        "season": subscribe.season,
        "episode_group": subscribe.episode_group,
        "type": subscribe.type,
        "save_path": subscribe.save_path,
        "sites": subscribe.sites,
        "filter": subscribe.filter,
        "filter_groups": subscribe.filter_groups,
        "best_version": subscribe.best_version,
        "best_version_full": subscribe.best_version_full,
    }
    return {field: value for field, value in values.items() if value is not None}


def _merge_missing_config_from_subscribe(config: dict, subscribe) -> None:
    """删除旧订阅前补齐快照缺失配置，避免旧快照重建时丢失订阅模式。"""
    mode_values = {
        "type": subscribe.type,
        "best_version": subscribe.best_version,
        "best_version_full": subscribe.best_version_full,
    }
    for field, value in mode_values.items():
        if value is not None:
            config[field] = value

    optional_values = {
        "save_path": subscribe.save_path,
        "sites": subscribe.sites,
        "filter": subscribe.filter,
        "filter_groups": subscribe.filter_groups,
    }
    for field, value in optional_values.items():
        if field in config:
            continue
        if value is not None:
            config[field] = value
