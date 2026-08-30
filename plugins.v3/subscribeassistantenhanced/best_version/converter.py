"""分集到全集转换：在原订阅上切换为全集洗版。"""

from app.application.subscription.mutation import SubscriptionActor
from app.sdk.logging import logger


DROP_REBUILT_FIELDS = {
    "id", "name", "year", "type", "tmdbid", "imdbid", "tvdbid", "doubanid", "bangumiid",
    "poster", "backdrop", "vote", "description", "date", "last_update",
}


class BestVersionConverter:
    """分集洗版升级为全集洗版。

    转换会归档原状态，再通过宿主 mutation scope 原地更新订阅；原 ID 和 episode_group
    等范围约束保持不变，避免已有任务与外部关联失效。
    """

    def __init__(self, subscribe_oper=None, clear_tasks_fn=None,
                 notify_fn=None, snapshot_fn=None, format_desc_fn=None,
                 notification_image_fn=None,
                 plugin_name: str = "订阅助手（增强版）",
                 subscribe_history_oper=None, subscription_mutation_scope=None):
        """注入活动订阅、历史归档、事务修改及转换副作用依赖。"""
        self._subscribe_oper = subscribe_oper
        self._subscribe_history_oper = subscribe_history_oper
        self._subscription_mutation_scope = subscription_mutation_scope
        self._clear_tasks = clear_tasks_fn
        self._notify = notify_fn
        self._snapshot = snapshot_fn
        self._format_desc = format_desc_fn
        self._notification_image = notification_image_fn
        self._plugin_name = plugin_name

    def convert_to_full(self, subscribe, mediainfo=None, current_priority=None) -> bool:
        """按指定全集准入基线原地切换为全集洗版订阅。"""
        sid = subscribe.id
        if (not sid or not self._subscribe_oper or not self._subscribe_history_oper
                or not self._subscription_mutation_scope or not mediainfo):
            return False

        subscribe_dict = subscribe.to_dict()
        subscribe_desc = self._format_subscribe_desc(subscribe, mediainfo)
        full_payload = self._build_full_payload(subscribe_dict, current_priority=current_priority)

        try:
            if self._snapshot:
                self._snapshot(subscribe=subscribe, mediainfo=mediainfo, scope=None)
        except Exception as err:
            logger.error(f"{subscribe_desc} 原因=登记完成快照失败，处理=停止转全集处理，错误={err}")
            self._notify_failure(subscribe, subscribe_desc, str(err), mediainfo=mediainfo)
            return False

        try:
            self._subscribe_history_oper.add(subscribe_dict)
        except Exception as err:
            logger.error(f"{subscribe_desc} 原因=写入订阅历史失败，处理=停止转全集处理，错误={err}")
            self._notify_failure(subscribe, subscribe_desc, str(err), mediainfo=mediainfo)
            return False

        try:
            with self._subscription_mutation_scope() as mutation:
                change = mutation.update(
                    sid,
                    full_payload,
                    SubscriptionActor(name=self._plugin_name, is_superuser=True),
                    scene="best_version_full",
                )
        except Exception as err:
            logger.error(f"{subscribe_desc} 原因=更新全集洗版订阅失败，处理=保留原订阅，错误={err}")
            self._notify_failure(subscribe, subscribe_desc, str(err), mediainfo=mediainfo)
            return False
        if not change:
            logger.error(f"{subscribe_desc} 原因=更新全集洗版订阅失败，处理=保留原订阅")
            self._notify_failure(subscribe, subscribe_desc, "宿主未返回订阅更新结果", mediainfo=mediainfo)
            return False

        if self._clear_tasks:
            try:
                self._clear_tasks(sid)
            except Exception as err:
                logger.warning(f"{subscribe_desc} 清理旧订阅任务失败，全集洗版订阅继续运行，错误={err}")

        logger.info(f"{subscribe_desc} 原因=分集洗版集数已符合目标集数，处理=已转为全集洗版订阅 (ID: {sid})")
        self._notify_success(subscribe, subscribe_desc, mediainfo)
        return True

    def _build_full_payload(self, subscribe_dict: dict, current_priority=None) -> dict:
        """从订阅快照构造全集洗版 payload，并保留订阅范围字段。"""
        payload = dict(subscribe_dict or {})
        for field in DROP_REBUILT_FIELDS:
            payload.pop(field, None)
        payload["best_version"] = 1
        payload["best_version_full"] = 1
        payload["username"] = self._plugin_name
        payload["state"] = "N"
        payload["manual_total_episode"] = 0
        if current_priority is not None:
            payload["current_priority"] = current_priority
        return payload

    def _format_subscribe_desc(self, subscribe, mediainfo) -> str:
        """格式化通知标题中的订阅描述。"""
        if self._format_desc:
            return self._format_desc(subscribe, mediainfo)
        season = f" S{subscribe.season}" if subscribe.season is not None else ""
        return f"{subscribe.name}{season}"

    def _notify_success(self, subscribe, subscribe_desc: str, mediainfo):
        """发送转全集成功通知。"""
        if not self._notify:
            return
        self._notify(
            f"{subscribe_desc} 分集洗版集数已符合目标集数，已从分集洗版转为全集洗版订阅",
            score=mediainfo.vote_average,
            image=self._resolve_notification_image(subscribe, mediainfo),
            link="#/subscribe/tv?tab=mysub",
        )

    def _notify_failure(self, subscribe, subscribe_desc: str, text: str, mediainfo=None):
        """发送转全集失败通知。"""
        if not self._notify:
            return
        self._notify(
            f"{subscribe_desc} 转为全集洗版订阅失败",
            text=text,
            follow_up="请检查订阅状态",
            diagnostic=True,
            image=self._resolve_notification_image(subscribe, mediainfo),
        )

    def _resolve_notification_image(self, subscribe, mediainfo=None):
        """解析转全集通知图片；未注入统一解析器时沿用媒体图片。"""
        if self._notification_image:
            return self._notification_image(subscribe, mediainfo)
        return mediainfo.get_message_image() if mediainfo else None
