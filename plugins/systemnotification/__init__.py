import threading
from typing import Any, List, Dict, Tuple

from app.core.event import eventmanager, Event
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.schemas.types import EventType

lock = threading.Lock()


class SystemNotification(_PluginBase):
    # 插件名称
    plugin_name = "系统通知"
    # 插件描述
    plugin_desc = "通过通知渠道发送系统通知消息。"
    # 插件图标
    plugin_icon = "https://github.com/InfinityPacer/MoviePilot-Plugins/raw/main/icons/systemnotification.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "systemnotification_"
    # 加载顺序
    plugin_order = 30
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性

    # 是否开启
    _enabled = False
    # 接收类型
    _preferences = None
    # 消息类型
    _notify_type = None
    # 推送堆栈
    _traceback = None
    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        if not config:
            return

        self._enabled = config.get("enabled", False)
        self._preferences = config.get("preferences", None)
        self._notify_type = config.get("notify_type", "Plugin")
        self._traceback = config.get("traceback", None)

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """
        定义远程控制命令
        :return: 命令关键字、事件、描述、附带数据
        """
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 8
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'traceback',
                                            'label': '详细堆栈',
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 8
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'model': 'preferences',
                                            'label': '接收类型',
                                            'items': self.__get_user_notification_preferences()
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': False,
                                            'chips': True,
                                            'model': 'notify_type',
                                            'label': '消息类型',
                                            'items': [{"title": item.value, "value": item.name}
                                                      for item in NotificationType]
                                        }
                                    }
                                ],
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '注意：目前仅支持推送系统错误消息'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "notify_type": "Plugin",
        }

    def get_page(self) -> List[dict]:
        pass

    def get_service(self) -> List[Dict[str, Any]]:
        """
        注册插件公共服务
        [{
            "id": "服务ID",
            "name": "服务名称",
            "trigger": "触发器：cron/interval/date/CronTrigger.from_crontab()",
            "func": self.xxx,
            "kwargs": {} # 定时器参数
        }]
        """
        pass

    def stop_service(self):
        """
        退出插件
        """
        try:
            if self._scheduler:
                self._scheduler.remove_all_jobs()
                if self._scheduler.running:
                    self._event.set()
                    self._scheduler.shutdown()
                    self._event.clear()
                self._scheduler = None
        except Exception as e:
            print(str(e))

    @eventmanager.register(EventType.SystemError)
    def notification(self, event: Event):
        """消息推送"""
        if not self._enabled:
            return

        if not self._preferences:
            logger.info("No user preferences set for notifications.")
            return

        notification_details = self.__generate_message(event=event)
        if not notification_details:
            logger.info("No notification details generated due to unsupported event type.")
            return

        event_type = notification_details.get("event_type")
        if "all" not in self._preferences and event_type not in self._preferences:
            logger.info(f"Event type '{event_type}' is not in user preferences.")
            return  # 如果事件类型不在用户偏好内，不发送消息

        title = f"【{notification_details.get('title')}】" if notification_details.get("title") else "【系统通知】"
        error = notification_details.get("error")
        traceback_info = notification_details.get("traceback")
        message = f"{error}\n{traceback_info}" if self._traceback else error
        logger.info(f"Sending notification: {title} - {message}")
        self.post_message(mtype=NotificationType[self._notify_type], title=title, text=message)

    def __generate_message(self, event: Event) -> dict:
        """根据事件生成通知信息"""
        event_data = event.event_data
        event_type = event_data.get("type")

        # 创建一个映射字典，将事件类型映射到对应的处理函数
        event_handlers = {
            "module": self.handle_module_event,
            "event": self.handle_event_event,
            "scheduler": self.handle_scheduler_event
        }

        # 获取处理函数，如果event_type不在字典中，则返回一个生成空字典的lambda
        handler = event_handlers.get(event_type, lambda x: {})

        # 调用相应的处理函数
        return handler(event_data)

    @staticmethod
    def __get_user_notification_preferences() -> List[dict[str, str]]:
        """
        提供用户可选的消息类型选项
        """
        # 定义消息类型选项
        notification_types = [
            {"title": "全部", "value": "all"},
            {"title": "模块运行错误", "value": "module"},
            {"title": "事件处理错误", "value": "event"},
            {"title": "定时任务错误", "value": "scheduler"},
        ]
        return notification_types

    @staticmethod
    def handle_module_event(event_data):
        """
        处理模块相关的错误事件，生成通知消息的详细内容。
        """
        return {
            "title": f"{event_data.get('module_name')}发生了错误",
            "error": event_data.get("error"),
            "traceback": event_data.get("traceback"),
            "event_type": "module"
        }

    @staticmethod
    def handle_event_event(event_data):
        """
        处理事件处理错误，生成通知消息的详细内容。
        """
        return {
            "title": f"{event_data.get('event_type')} 事件处理出错",
            "error": event_data.get("event_handle") + "\n" + event_data.get("error"),
            "traceback": event_data.get("traceback"),
            "event_type": "event"
        }

    @staticmethod
    def handle_scheduler_event(event_data):
        """
        处理调度器执行失败的错误事件，生成通知消息的详细内容。
        """
        return {
            "title": f"{event_data.get('scheduler_name')} 执行失败",
            "error": event_data.get("error"),
            "traceback": event_data.get("traceback"),
            "event_type": "scheduler"
        }
