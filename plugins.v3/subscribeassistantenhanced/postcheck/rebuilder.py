"""完成快照订阅重建：解析模式、创建订阅并校验实际接管范围。"""
from typing import Callable, Tuple

from app.log import logger
from app.schemas.types import MediaType, SystemConfigKey

from .verifier import format_snapshot_label


class CompletionSubscribeRebuilder:
    """按完成快照重建增集订阅，并确保结果不是全集洗版。"""

    def __init__(self, subscribe_chain, subscribe_oper,
                 default_config_getter: Callable, plugin_name: str):
        """注入订阅创建、订阅读取和主程序默认规则查询能力。"""
        self._subscribe_chain = subscribe_chain
        self._subscribe_oper = subscribe_oper
        self._default_config_getter = default_config_getter
        self._plugin_name = plugin_name

    def rebuild(self, snap: dict, config: dict) -> bool:
        """使用当前默认规则和完成快照重建按集追踪的增集订阅。"""
        if not self._subscribe_chain or not self._subscribe_oper:
            return False
        payload = dict(config)
        title = payload.pop("name", "")
        year = payload.pop("year", None)
        for field in (
            "id", "type", "media_source", "media_id", "season", "episode_group",
            "best_version", "best_version_full",
        ):
            payload.pop(field, None)
        best_version, best_version_full = self._resolve_mode(snap)
        payload["best_version"] = best_version
        payload["best_version_full"] = best_version_full
        payload["manual_total_episode"] = 0
        payload["state"] = "N"
        try:
            subscribe_id, _ = self._subscribe_chain.add(
                title=title,
                year=year,
                mtype=MediaType.TV,
                media_source=snap.get("media_source"),
                media_id=snap.get("media_id"),
                season=snap.get("season"),
                episode_group=snap.get("episode_group_id"),
                username=self._plugin_name,
                message=False,
                exist_ok=True,
                **payload,
            )
            rebuilt = self._subscribe_oper.get(subscribe_id) if subscribe_id else None
            if not self._is_valid(
                rebuilt,
                snap=snap,
                config=config,
                best_version=best_version,
            ):
                logger.warning(
                    f"完成后验证：{format_snapshot_label(snap)} 重建结果未接管目标新增集，"
                    "已保留快照等待重试"
                )
                return False
            logger.info(
                f"完成后验证：{format_snapshot_label(snap)} 检测到增集，"
                f"已重建订阅（新 id={subscribe_id}）"
            )
            return True
        except Exception as err:
            logger.warning(
                f"{self._plugin_name}按完成快照重建订阅失败："
                f"{format_snapshot_label(snap)}, error={err}"
            )
            return False

    def validate(self, subscribe, snap: dict, current_total: int) -> bool:
        """验证既有订阅是否按当前纠错规则接管快照发现的新增集。"""
        best_version, _ = self._resolve_mode(snap)
        return self._is_valid(
            subscribe,
            snap=snap,
            config={
                "start_episode": snap.get("total_at_completion", 0) + 1,
                "total_episode": current_total,
            },
            best_version=best_version,
        )

    @staticmethod
    def _is_valid(subscribe, snap: dict, config: dict, best_version: int) -> bool:
        """确认实际订阅按目标模式覆盖完整新增集区间。"""
        if not subscribe:
            return False
        requested_start = config.get("start_episode") or 1
        requested_total = config.get("total_episode") or 0
        actual_start = subscribe.start_episode or 1
        actual_total = subscribe.total_episode or 0
        return (
            subscribe.media_source == snap.get("media_source")
            and str(subscribe.media_id) == str(snap.get("media_id"))
            and subscribe.season == snap.get("season")
            and subscribe.episode_group == snap.get("episode_group_id")
            and bool(subscribe.best_version) == bool(best_version)
            and not bool(subscribe.best_version_full)
            and actual_start <= requested_start
            and actual_total >= requested_total
        )

    def _resolve_mode(self, snap: dict) -> Tuple[int, int]:
        """解析自动纠错重建模式，保证结果只可能是普通订阅或分集洗版。"""
        default_best_version, default_best_version_full = self._get_default_tv_mode()
        if not default_best_version_full:
            return int(default_best_version), 0

        snapshot_config = snap.get("subscribe_config") or {}
        snapshot_best_version = bool(snapshot_config.get("best_version"))
        snapshot_best_version_full = bool(snapshot_config.get("best_version_full"))
        if snapshot_best_version and not snapshot_best_version_full:
            return 1, 0
        return 0, 0

    def _get_default_tv_mode(self) -> Tuple[bool, bool]:
        """读取用户在主程序中保存的默认电视剧订阅模式。"""
        default_config = self._default_config_getter(SystemConfigKey.DefaultTvSubscribeConfig)
        if not isinstance(default_config, dict):
            default_config = {}
        best_version = bool(default_config.get("best_version"))
        best_version_full = best_version and bool(default_config.get("best_version_full"))
        return best_version, best_version_full
