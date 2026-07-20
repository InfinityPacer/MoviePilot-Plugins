"""分集到全集转换：以替换订阅方式切换为全集洗版。"""

from app.log import logger
from app.schemas.types import EventType


DROP_REBUILT_FIELDS = {
    "id", "name", "year", "type", "tmdbid", "imdbid", "tvdbid", "doubanid", "bangumiid",
    "poster", "backdrop", "vote", "description", "date", "last_update",
}


class BestVersionConverter:
    """分集洗版升级为全集洗版。

    转换会归档并删除分集订阅，再以同一配置创建全集洗版订阅；episode_group 属于订阅范围约束，
    需要随 payload 保留，避免绝对季或剧集组范围在转换时丢失。
    """

    def __init__(self, subscribe_oper=None, clear_tasks_fn=None, send_event_fn=None,
                 notify_fn=None, restore_fn=None, snapshot_fn=None, format_desc_fn=None,
                 notification_image_fn=None,
                 plugin_name: str = "订阅助手（增强版）"):
        """注入订阅写库、任务清理、事件、通知、完成快照和失败恢复依赖。"""
        self._subscribe_oper = subscribe_oper
        self._clear_tasks = clear_tasks_fn
        self._send_event = send_event_fn
        self._notify = notify_fn
        self._restore = restore_fn
        self._snapshot = snapshot_fn
        self._format_desc = format_desc_fn
        self._notification_image = notification_image_fn
        self._plugin_name = plugin_name

    def convert_to_full(self, subscribe, mediainfo=None, current_priority=None) -> bool:
        """按指定全集准入基线替换为全集洗版订阅；失败时尽量恢复分集订阅。"""
        sid = subscribe.id
        if not sid or not self._subscribe_oper or not mediainfo:
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
            self._subscribe_oper.add_history(**subscribe_dict)
        except Exception as err:
            logger.error(f"{subscribe_desc} 原因=写入订阅历史失败，处理=停止转全集处理，错误={err}")
            self._notify_failure(subscribe, subscribe_desc, str(err), mediainfo=mediainfo)
            return False

        try:
            self._subscribe_oper.delete(sid=sid)
        except Exception as err:
            logger.error(f"{subscribe_desc} 原因=删除分集洗版订阅失败，处理=停止转全集处理，错误={err}")
            self._notify_failure(subscribe, subscribe_desc, str(err), mediainfo=mediainfo)
            return False

        if self._clear_tasks:
            try:
                self._clear_tasks(sid)
            except Exception as err:
                logger.warning(f"{subscribe_desc} 清理旧订阅任务失败，继续创建全集洗版订阅，错误={err}")

        try:
            new_sid, err_msg = self._subscribe_oper.add(mediainfo=mediainfo, **full_payload)
        except Exception as err:
            new_sid, err_msg = None, str(err)

        if new_sid:
            logger.info(f"{subscribe_desc} 原因=分集洗版集数已符合目标集数，处理=已转为全集洗版订阅 (ID: {new_sid})")
            self._send_subscribe_added(new_sid, mediainfo)
            self._notify_success(subscribe, subscribe_desc, mediainfo)
            return True

        restored = self._restore(subscribe_dict, mediainfo) if self._restore else False
        logger.error(
            f"{subscribe_desc} 原因=转为全集洗版订阅失败，处理=尝试重建分集订阅，"
            f"错误信息={err_msg}，分集订阅重建状态={restored}"
        )
        restore_text = "分集洗版订阅已尝试重建" if restored else "分集洗版订阅重建失败，请手动检查"
        self._notify_failure(subscribe, subscribe_desc, f"{err_msg}\n{restore_text}", mediainfo=mediainfo)
        return False

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

    def _send_subscribe_added(self, sid, mediainfo):
        """全集洗版订阅创建成功后发 SubscribeAdded 事件。"""
        if not self._send_event:
            return
        media_payload = mediainfo.to_dict()
        self._send_event(EventType.SubscribeAdded, {
            "subscribe_id": sid,
            "username": self._plugin_name,
            "mediainfo": media_payload,
        })

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
