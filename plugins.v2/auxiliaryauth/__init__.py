import threading
import uuid
from typing import Any, Dict, List, Optional, Tuple

from app.core.event import Event, eventmanager
from app.helper.mediaserver import MediaServerHelper
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import ServiceInfo
from app.schemas.event import AuthCredentials, AuthInterceptCredentials
from app.schemas.types import ChainEventType

lock = threading.Lock()


class AuxiliaryAuth(_PluginBase):
    # 插件名称
    plugin_name = "辅助认证"
    # 插件描述
    plugin_desc = "支持使用第三方系统进行辅助认证。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/auxiliaryauth.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "auxiliaryauth_"
    # 加载顺序
    plugin_order = 30
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性
    mediaserver_helper = None
    # 是否开启
    _enabled = False
    # 媒体服务器
    _mediaservers = None
    # 启用匿名
    _allow_anonymous = False

    # endregion

    def init_plugin(self, config: dict = None):
        self.mediaserver_helper = MediaServerHelper()
        if not config:
            return

        self._enabled = config.get("enabled") or False
        self._mediaservers = config.get("mediaservers") or []
        self._allow_anonymous = config.get("allow_anonymous") or False

    @property
    def service_infos(self) -> Optional[Dict[str, ServiceInfo]]:
        """
        服务信息
        """
        if not self._mediaservers:
            logger.warning("尚未配置媒体服务器，请检查配置")
            return None

        services = self.mediaserver_helper.get_services(name_filters=self._mediaservers)
        if not services:
            logger.warning("获取媒体服务器实例失败，请检查配置")
            return None

        services = {name: service for name, service in services.items()
                    if service.type == "emby" or service.type == "jellyfin"}

        active_services = {}
        for service_name, service_info in services.items():
            if service_info.instance.is_inactive():
                logger.warning(f"媒体服务器 {service_name} 未连接，请检查配置")
            else:
                active_services[service_name] = service_info

        if not active_services:
            logger.warning("没有已连接的媒体服务器，请检查配置")
            return None

        return active_services

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
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'enabled',
                                            'label': '启用插件',
                                            'hint': '开启后插件将处于激活状态',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            # {
                            #     'component': 'VCol',
                            #     'props': {
                            #         'cols': 12,
                            #         'md': 6
                            #     },
                            #     'content': [
                            #         {
                            #             'component': 'VSwitch',
                            #             'props': {
                            #                 'model': 'allow_anonymous',
                            #                 'label': '允许匿名认证',
                            #                 'hint': '启用此选项以允许未登录用户匿名访问服务',
                            #                 'persistent-hint': True
                            #             }
                            #         }
                            #     ]
                            # }
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'clearable': True,
                                            'model': 'mediaservers',
                                            'label': '启用辅助认证的媒体服务器',
                                            'hint': '选择启用辅助认证的媒体服务器',
                                            'persistent-hint': True,
                                            'items': [{"title": config.name, "value": config.name}
                                                      for config in self.mediaserver_helper.get_configs().values()
                                                      if config.type == "emby" or config.type == "jellyfin"]
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
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '注意：启用辅助认证需要在 app.env 文件或环境变量中设置 AUXILIARY_AUTH_ENABLE 参数为开启状态'
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
            "allow_anonymous": False
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
        pass

    @eventmanager.register(ChainEventType.AuthIntercept)
    def handle_auth_intercept(self, event: Event):
        """
        处理 AuthIntercept 事件
        :param event: 事件数据
        """
        if not event or not event.event_data:
            return

        event_data: AuthInterceptCredentials = event.event_data

        logger.info(
            f"处理认证通过拦截事件 - 用户名: {event_data.username}, 渠道: {event_data.channel}, 服务: {event_data.service}")

        # 检查是否为 Emby 或 Jellyfin 渠道，并处理服务信息
        if event_data.channel in ["Emby", "Jellyfin"]:
            if not self.service_infos or event_data.service not in self.service_infos.keys():
                event_data.cancel = True
                event_data.source = self.plugin_name
                logger.warning(
                    f"认证被拦截，用户：{event_data.username}，渠道：{event_data.channel}，"
                    f"服务：{event_data.service}，拦截源：{event_data.source}")
            else:
                event_data.cancel = False
                logger.info(f"用户：{event_data.username}，渠道: {event_data.channel}，服务 {event_data.service} 允许认证通过")
        else:
            logger.info(f"尚未支持处理渠道: {event_data.channel}，跳过拦截")

    # @eventmanager.register(ChainEventType.AuthVerification)
    # def handle_auth_verification(self, event: Event):
    #     """
    #     处理 AuthVerification 事件
    #     :param event: 事件数据
    #     """
    #     if not event or not event.event_data:
    #         return
    #
    #     event_data: AuthCredentials = event.event_data
    #
    #     # 检查是否允许匿名认证
    #     if not self._allow_anonymous:
    #         logger.debug("尚未启用匿名认证，跳过")
    #         return
    #
    #     event_data.service = self.plugin_name
    #     event_data.token = str(uuid.uuid4())
    #     event_data.channel = "Plugin-Anonymous"
    #     logger.info(
    #         f"处理匿名认证 - 用户名: {event_data.username}, 服务: {event_data.service}, Token: {event_data.token}")
