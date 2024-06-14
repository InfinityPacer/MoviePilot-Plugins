import threading
from dataclasses import asdict, fields
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple

import pytz
from app.helper.sites import SitesHelper
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from ruamel.yaml import YAMLError

from app.core.config import settings
from app.core.event import Event, eventmanager
from app.core.plugin import PluginManager
from app.db.site_oper import SiteOper
from app.db.systemconfig_oper import SystemConfigOper
from app.log import logger
from app.plugins import _PluginBase
from app.plugins.trafficassistant.trafficconfig import TrafficConfig
from app.scheduler import Scheduler
from app.schemas import NotificationType
from app.schemas.types import SystemConfigKey, EventType

lock = threading.Lock()


class TrafficAssistant(_PluginBase):
    # 插件名称
    plugin_name = "站点流量管理"
    # 插件描述
    plugin_desc = "自动管理流量，保障站点分享率。"
    # 插件图标
    plugin_icon = "https://github.com/InfinityPacer/MoviePilot-Plugins/raw/main/icons/trafficassistant.png"
    # 插件版本
    plugin_version = "1.2"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "trafficassistant_"
    # 加载顺序
    plugin_order = 19
    # 可使用的用户级别
    auth_level = 2

    # region 私有属性

    pluginmanager = None
    siteshelper = None
    siteoper = None
    systemconfig = None

    # 流量管理配置
    _traffic_config = TrafficConfig()
    # 插件是否需要热加载
    _plugin_reload_if_need = False

    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        self.pluginmanager = PluginManager()
        self.siteshelper = SitesHelper()
        self.siteoper = SiteOper()
        self.systemconfig = SystemConfigOper()

        if not config:
            return

        result, reason = self.__validate_and_fix_config(config=config)

        if not result and not self._traffic_config:
            self.__update_config_if_error(config=config, error=reason)
            return

        if self._traffic_config.onlyonce:
            self._traffic_config.onlyonce = False
            self.update_config(config=config)

            logger.info("立即运行一次站点流量管理服务")
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(self.traffic, 'date',
                                    run_date=datetime.now(
                                        tz=pytz.timezone(settings.TZ)
                                    ) + timedelta(seconds=3),
                                    name="站点流量管理")

            if self._scheduler.get_jobs():
                # 启动服务
                self._scheduler.print_jobs()
                self._scheduler.start()

        self.__update_config()

    def get_state(self) -> bool:
        return self._traffic_config and self._traffic_config.enabled

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
                                    'md': 4
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
                                            'model': 'notify',
                                            'label': '发送通知',
                                            'hint': '是否在特定事件发生时发送通知',
                                            'persistent-hint': True
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
                                            'model': 'onlyonce',
                                            'label': '立即执行一次',
                                            'hint': '插件将立即执行一次',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
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
                                            'clearable': True,
                                            'model': 'sites',
                                            'label': '站点列表',
                                            'hint': '选择参与配置的站点',
                                            'persistent-hint': True,
                                            'items': self.__get_site_options()
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 4,
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'brush_plugin',
                                            'label': '站点刷流插件',
                                            'hint': '选择参与配置的刷流插件',
                                            'persistent-hint': True,
                                            'items': self.__get_plugin_options()
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
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '运行周期',
                                            'placeholder': '5位cron表达式',
                                            'hint': '使用cron表达式指定执行周期，如 0 8 * * *',
                                            'persistent-hint': True
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'ratio_lower_limit',
                                            'label': '分享率下限',
                                            'type': 'number',
                                            "min": "0",
                                            'hint': '设置最低分享率阈值',
                                            'persistent-hint': True
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'ratio_upper_limit',
                                            'label': '分享率上限',
                                            'type': 'number',
                                            "min": "0",
                                            'hint': '设置最高分享率阈值',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                        ]
                    },
                    {
                        'component': 'VRow',
                        'content': [
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
                                            'model': 'add_to_subscription_if_above',
                                            'label': '添加订阅站点',
                                            'hint': '分享率大于上限时自动添加到订阅站点',
                                            'persistent-hint': True
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
                                            'model': 'add_to_search_if_above',
                                            'label': '添加搜索站点',
                                            'hint': '分享率大于上限时自动添加到搜索站点',
                                            'persistent-hint': True
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
                                            'model': 'disable_auto_brush_if_above',
                                            'label': '停止刷流',
                                            'hint': '分享率大于上限时自动停止刷流功能',
                                            'persistent-hint': True
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
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VSwitch',
                                        'props': {
                                            'model': 'remove_from_subscription_if_below',
                                            'label': '移除订阅站点',
                                            'hint': '分享率小于等于下限时自动从订阅中移除站点',
                                            'persistent-hint': True
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
                                            'model': 'remove_from_search_if_below',
                                            'label': '移除搜索站点',
                                            'hint': '分享率小于等于下限时自动从搜索中移除站点',
                                            'persistent-hint': True
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
                                            'model': 'enable_auto_brush_if_below',
                                            'label': '开启刷流',
                                            'hint': '分享率小于等于下限时自动开启刷流功能',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    # {
                    #     'component': 'VRow',
                    #     'content': [
                    #         {
                    #             'component': 'VCol',
                    #             'props': {
                    #                 'cols': 12,
                    #                 'md': 4
                    #             },
                    #             'content': [
                    #                 {
                    #                     'component': 'VSwitch',
                    #                     'props': {
                    #                         'model': 'send_alert_if_below',
                    #                         'label': '发送预警',
                    #                         'hint': '分享率小于等于下限时发送预警通知',
                    #                         'persistent-hint': True
                    #                     }
                    #                 }
                    #             ]
                    #         },
                    #     ]
                    # },
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
                                            'type': 'error',
                                            'variant': 'tonal',
                                            'text': '警告：本插件仍在完善阶段，可能会导致站点流量异常，分享率降低等，'
                                                    '严重甚至导致站点封号，请慎重使用'
                                        }
                                    }
                                ]
                            },
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
                                            'type': 'error',
                                            'variant': 'tonal',
                                            'text': '警告：本插件依赖站点刷流插件，请提前安装对应插件中进行相关配置，'
                                                    '否则可能导致开启站点刷流后，分享率降低或命中H&R种子，严重甚至导致站点封号，请慎重使用'
                                        }
                                    }
                                ]
                            },
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
                                            'type': 'error',
                                            'variant': 'tonal',
                                            'text': '警告：本插件依赖站点数据统计插件，请提前安装对应插件中进行相关配置，'
                                                    '否则可能导致无法获取到分享率等信息，从而影响后续站点流量管理'
                                        }
                                    }
                                ]
                            },
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "notify": True
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

        if not self._traffic_config:
            return []

        if self._traffic_config.enabled and self._traffic_config.cron:
            return [{
                "id": "TrafficAssistant",
                "name": "站点流量管理服务",
                "trigger": CronTrigger.from_crontab(self._traffic_config.cron),
                "func": self.traffic,
                "kwargs": {}
            }]

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

    @eventmanager.register(EventType.PluginAction)
    def traffic(self, event: Event = None):
        """
        主要负责管理站点的流量
        通过获取站点统计信息，依据统计信息的成功获取与否执行相应的流量管理操作或记录错误
        """
        if event:
            event_data = event.event_data
            if not event_data or event_data.get("action") != "sitestatistic_refresh_complete":
                return
            else:
                logger.info("站点数据统计刷新完成，立即运行一次站点流量管理服务")

        with lock:
            traffic_config = self._traffic_config
            success, reason = self.__validate_config(traffic_config=traffic_config, force=True)
            if not success:
                err_msg = f"配置异常，原因：{reason}"
                logger.error(err_msg)
                self.__send_message(title="站点流量管理", message=err_msg)
                return

            result = self.__get_site_statistics()
            if result.get("success"):
                site_statistics = result.get("data")
                logger.info(f"数据获取成功：{site_statistics}")

                manage_results = self.__auto_traffic(traffic_config=traffic_config, site_statistics=site_statistics)
                aggregated_messages = []  # 初始化一个列表来聚合消息内容

                for site_name, (outcome, stat_time) in manage_results.items():
                    message = f"站点：{site_name} (数据日期：{stat_time})\n{outcome}\n————————————————————"
                    logger.info(message)
                    aggregated_messages.append(message)  # 将每个消息添加到列表中

                # 将所有聚合的消息一次性发送
                if aggregated_messages:
                    full_message = "\n".join(aggregated_messages)
                    self.__send_message(title="站点流量管理", message=full_message)
            else:
                error_msg = result.get("err_msg", "站点流量管理发生异常，请检查日志")
                logger.error(error_msg)
                self.__send_message(title="站点流量管理", message=error_msg)

    def __auto_traffic(self, traffic_config: TrafficConfig, site_statistics: dict):
        """根据提供的站点统计信息自动管理各站点的流量"""
        results = {}
        self._plugin_reload_if_need = False
        for site_id, site in traffic_config.site_infos.items():
            site_name = site.name
            logger.info(f"正在准备对站点 {site_name} 进行流量管理")
            results[site_name] = self.__manage_site_traffic(traffic_config=traffic_config, site_id=site_id,
                                                            site_name=site_name, site_statistics=site_statistics)
        if self._plugin_reload_if_need:
            self.__reload_plugin(plugin_id=traffic_config.brush_plugin)
            self._plugin_reload_if_need = False
        return results

    def __manage_site_traffic(self, traffic_config: TrafficConfig, site_id: int, site_name: str,
                              site_statistics: dict) -> [str, str]:
        """管理单个站点的流量，根据站点的统计数据进行不同的处理"""
        site_stat = site_statistics.get(site_name)
        if not site_stat:
            error_msg = "统计数据不存在，跳过分析"
            logger.warn(error_msg)
            return error_msg, "N/A"

        stat_time = site_stat.get("statistic_time", "N/A")
        logger.info(f"数据日期：{stat_time}")
        if not site_stat.get("success"):
            error_msg = f"{site_stat.get('err_msg')}，跳过分析"
            logger.warn(error_msg)
            return error_msg, stat_time

        process_result = self.__process_site_traffic(traffic_config=traffic_config, site_id=site_id,
                                                     site_stat=site_stat)
        return process_result, stat_time

    def __process_site_traffic(self, traffic_config: TrafficConfig, site_id: int, site_stat: dict) -> str:
        """根据站点的流量配置和统计信息处理站点流量"""
        ratio = site_stat.get("ratio")
        if ratio is None:
            error_msg = "分享率：N/A，跳过分析"
            logger.warn(error_msg)
            return error_msg

        if ratio == 0.0:
            error_msg = "分享率：0，跳过分析"
            logger.warn(error_msg)
            return error_msg

        if ratio <= traffic_config.ratio_lower_limit:
            return self.__handle_traffic(traffic_config=traffic_config, site_id=site_id, ratio=ratio, is_low=True)

        if ratio > traffic_config.ratio_upper_limit:
            return self.__handle_traffic(traffic_config=traffic_config, site_id=site_id, ratio=ratio, is_low=False)

        return (f"分享率：{ratio} ({traffic_config.ratio_lower_limit} - {traffic_config.ratio_upper_limit})\n"
                f"- 分享率符合预期，无需调整")

    def __handle_traffic(self, traffic_config: TrafficConfig, site_id: int, ratio: float, is_low: bool) -> str:
        """处理流量情况，可以适用于高低流量情况"""
        threshold_type = "≤" if is_low else ">"
        threshold_value = traffic_config.ratio_lower_limit if is_low else traffic_config.ratio_upper_limit
        traffic_summary = f"分享率：{ratio} ({threshold_type}{threshold_value})"
        actions = []

        any_action_taken = False  # 初始化操作跟踪标志

        # 处理搜索和订阅站点
        search_condition = (
            traffic_config.remove_from_search_if_below if is_low else traffic_config.add_to_search_if_above)
        if search_condition:
            success, action_msg = self.__update_search_sites(site_id=site_id, remove=is_low)
            actions.append(f"- {action_msg}")
            if success:
                any_action_taken = True  # 更新操作执行标志

        subscription_condition = (
            traffic_config.remove_from_subscription_if_below if is_low else traffic_config.add_to_subscription_if_above)
        if subscription_condition:
            success, action_msg = self.__update_subscription_sites(site_id=site_id, remove=is_low)
            actions.append(f"- {action_msg}")
            if success:
                any_action_taken = True  # 更新操作执行标志

        # 处理刷流站点
        brush_condition = (
            traffic_config.enable_auto_brush_if_below if is_low else traffic_config.disable_auto_brush_if_above)
        if brush_condition:
            success, action_msg = self.__update_brush_sites(site_id=site_id, enable=is_low,
                                                            plugin_id=traffic_config.brush_plugin)
            actions.append(f"- {action_msg}")
            if success:
                any_action_taken = True  # 更新操作执行标志
                self._plugin_reload_if_need = True  # 标记需要进行插件的热加载

        if not any_action_taken:
            actions.clear()
            actions.append("- 配置项符合预期，无需调整")

        return "\n".join([traffic_summary] + actions)

    @staticmethod
    def __update_site_list(site_id: int, site_list: list, remove: bool, description: str) -> [bool, str]:
        """通用方法来添加或移除站点"""
        action_performed = False
        action_msg = f"{description}站点：无需调整"
        if not remove:
            if site_id not in site_list:
                site_list.append(site_id)
                action_performed = True
                action_msg = f"{description}站点：已添加"
        else:
            if site_id in site_list:
                site_list.remove(site_id)
                action_performed = True
                action_msg = f"{description}站点：已移除"
        return action_performed, action_msg

    def __update_search_sites(self, site_id: int, remove: bool) -> [bool, str]:
        """更新搜索站点列表，根据需要添加或移除站点"""
        indexer_sites = self.systemconfig.get(key=SystemConfigKey.IndexerSites) or []
        action_performed, action_msg = self.__update_site_list(site_id=site_id, site_list=indexer_sites, remove=remove,
                                                               description="搜索")
        logger.info(action_msg)
        if action_performed:
            self.systemconfig.set(key=SystemConfigKey.IndexerSites, value=indexer_sites)
        return action_performed, action_msg

    def __update_subscription_sites(self, site_id: int, remove: bool) -> [bool, str]:
        """更新订阅站点列表，根据需要添加或移除站点"""
        rss_sites = self.systemconfig.get(key=SystemConfigKey.RssSites) or []
        action_performed, action_msg = self.__update_site_list(site_id=site_id, site_list=rss_sites, remove=remove,
                                                               description="订阅")
        logger.info(action_msg)
        if action_performed:
            self.systemconfig.set(key=SystemConfigKey.RssSites, value=rss_sites)
        return action_performed, action_msg

    def __update_brush_sites(self, site_id: int, enable: bool, plugin_id: str) -> [bool, str]:
        """更新或配置刷流插件站点"""
        plugin_config = self.get_config(plugin_id=plugin_id)
        if not plugin_config:
            action_msg = "刷流站点：获取插件配置失败"
            logger.warn(action_msg)
            return False, action_msg

        actions = []
        config_needs_update = False
        plugin_enabled = plugin_config.get("enabled", False)

        if enable and not plugin_enabled:
            plugin_config["enabled"] = True
            action_msg = "刷流插件：已启用"
            logger.info(action_msg)
            actions.append(action_msg)
            config_needs_update = True

        brush_sites = plugin_config.get("brushsites", [])
        action_performed, action_msg = self.__update_site_list(site_id=site_id, site_list=brush_sites,
                                                               remove=not enable,
                                                               description="刷流")
        logger.info(action_msg)
        actions.append(action_msg)
        if action_performed:
            plugin_config["brushsites"] = brush_sites
            config_needs_update = True

        if config_needs_update:
            self.update_config(config=plugin_config, plugin_id=plugin_id)

        return config_needs_update, "，".join(actions)

    def __reload_plugin(self, plugin_id: str):
        logger.info(f"准备热加载插件: {plugin_id}")

        # 加载插件到内存
        try:
            self.pluginmanager.reload_plugin(plugin_id)
            logger.info(f"成功热加载插件: {plugin_id} 到内存")
        except Exception as e:
            logger.error(f"失败热加载插件: {plugin_id} 到内存. 错误信息: {e}")
            return

        # 注册插件服务
        try:
            Scheduler().update_plugin_job(plugin_id)
            logger.info(f"成功热加载插件到插件服务: {plugin_id}")
        except Exception as e:
            logger.error(f"失败热加载插件到插件服务: {plugin_id}. 错误信息: {e}")
            return

        logger.info(f"已完成插件热加载: {plugin_id}")

    def __get_site_statistics(self) -> dict:
        """获取站点统计数据"""

        def is_data_valid(data):
            """检查数据是否有效"""
            return "ratio" in data and not data.get("err_msg")

        traffic_config = self._traffic_config
        site_infos = traffic_config.site_infos
        current_day = datetime.now(tz=pytz.timezone(settings.TZ)).date()
        previous_day = current_day - timedelta(days=1)
        result = {"success": True, "data": {}}

        # 尝试获取当天和前一天的数据
        current_data = self.get_data(str(current_day), traffic_config.statistic_plugin) or {}
        previous_day_data = self.get_data(str(previous_day), traffic_config.statistic_plugin) or {}

        if not current_data and not previous_day_data:
            err_msg = f"{current_day} 和 {previous_day}，均没有获取到有效的数据，请检查"
            logger.warn(err_msg)
            result["success"] = False
            result["err_msg"] = err_msg
            return result

        # 检查每个站点的数据是否有效
        all_sites_failed = True
        for site_id, site in site_infos.items():
            site_name = site.name
            site_current_data = current_data.get(site_name, {})
            site_previous_data = previous_day_data.get(site_name, {})

            if is_data_valid(site_current_data):
                result["data"][site_name] = {**site_current_data, "success": True,
                                             "statistic_time": str(current_day)}
                all_sites_failed = False
            else:
                if is_data_valid(site_previous_data):
                    result["data"][site_name] = {**site_previous_data, "success": True,
                                                 "statistic_time": str(previous_day)}
                    logger.info(f"站点 {site_name} 使用了 {previous_day} 的数据")
                    all_sites_failed = False
                else:
                    err_msg = site_previous_data.get("err_msg", "无有效数据")
                    result["data"][site_name] = {"err_msg": err_msg, "success": False,
                                                 "statistic_time": str(previous_day)}
                    logger.warn(f"{site_name} 前一天的数据也无效，错误信息：{err_msg}")

        # 如果所有站点的数据都无效，则标记全局失败
        if all_sites_failed:
            err_msg = f"{current_day} 和 {previous_day}，所有站点的数据获取均失败，无法继续站点流量管理服务"
            logger.warn(err_msg)
            result["success"] = False
            result["err_msg"] = err_msg

        return result

    def __send_message(self, title: str, message: str):
        """发送消息"""
        if self._traffic_config.notify:
            self.post_message(mtype=NotificationType.Plugin, title=f"【{title}】", text=message)

    def __validate_config(self, traffic_config: TrafficConfig, force: bool = False, check_plugin_installed: bool = True) \
            -> (bool, str):
        """
        验证配置是否有效
        """
        if not traffic_config.enabled and not force:
            return True, "插件未启用，无需进行验证"

        if check_plugin_installed:
            # 检查站点数据统计是否已启用
            result, message = self.__check_required_plugin_installed(plugin_id=traffic_config.statistic_plugin)
            if not result:
                return False, message

        # 检查站点列表是否为空
        if not traffic_config.sites:
            return False, "站点列表不能为空"

        if traffic_config.enable_auto_brush_if_below or traffic_config.disable_auto_brush_if_above:
            if not traffic_config.brush_plugin:
                return False, "已启用停止/开启刷流，站点刷流插件不能为空"
            if check_plugin_installed:
                result, message = self.__check_required_plugin_installed(plugin_id=traffic_config.brush_plugin)
                if not result:
                    return False, message

        # 检查分享率的设置是否有效
        if traffic_config.ratio_lower_limit <= 0 or traffic_config.ratio_upper_limit <= 0:
            return False, "分享率必须大于0"

        # 检查分享率的上下限是否正确
        if traffic_config.ratio_upper_limit < traffic_config.ratio_lower_limit:
            return False, "分享率上限必须大于等于下限"

        return True, "所有配置项都有效"

    def __validate_and_fix_config(self, config: dict = None) -> [bool, str]:
        """
        检查并修正配置值
        """
        if not config:
            return False, ""

        try:
            # 使用字典推导来提取所有字段，并用config中的值覆盖默认值
            traffic_config = TrafficConfig(
                **{field.name: config.get(field.name, getattr(TrafficConfig, field.name, None))
                   for field in fields(TrafficConfig)})

            result, reason = self.__validate_config(traffic_config=traffic_config, check_plugin_installed=False)
            if result:
                # 过滤掉已删除的站点并保存
                if traffic_config.sites:
                    site_id_to_public_status = {site.get("id"): site.get("public") for site in
                                                self.siteshelper.get_indexers()}
                    traffic_config.sites = [
                        site_id for site_id in traffic_config.sites
                        if site_id in site_id_to_public_status and not site_id_to_public_status[site_id]
                    ]

                    site_infos = {}
                    for site_id in traffic_config.sites:
                        site_info = self.siteoper.get(site_id)
                        if site_info:
                            site_infos[site_id] = site_info
                    traffic_config.site_infos = site_infos

                self._traffic_config = traffic_config
                return True, ""
            else:
                self._traffic_config = None
                return result, reason
        except YAMLError as e:
            self._traffic_config = None
            logger.error(e)
            return False, str(e)
        except Exception as e:
            self._traffic_config = None
            logger.error(e)
            return False, str(e)

    def __update_config_if_error(self, config: dict = None, error: str = None):
        """异常时停用插件并保存配置"""
        if config:
            if config.get("enabled", False) or config.get("onlyonce", False):
                config["enabled"] = False
                config["onlyonce"] = False
                self.__log_and_notify_error(
                    f"配置异常，已停用站点流量管理，原因：{error}" if error else "配置异常，已停用站点流量管理，请检查")
            self.update_config(config)

    def __update_config(self):
        """保存配置"""
        config_mapping = asdict(self._traffic_config)
        del config_mapping["site_infos"]
        del config_mapping["statistic_plugin"]
        self.update_config(config_mapping)

    def __log_and_notify_error(self, message):
        """
        记录错误日志并发送系统通知
        """
        logger.error(message)
        self.systemmessage.put(message, title="站点流量管理")

    def __get_site_options(self):
        """获取当前可选的站点"""
        site_options = [{"title": site.get("name"), "value": site.get("id")}
                        for site in self.siteshelper.get_indexers()]
        return site_options

    def __get_plugin_options(self) -> List[dict]:
        """获取插件选项列表"""
        # 获取运行的插件选项
        running_plugins = self.pluginmanager.get_running_plugin_ids()

        # 需要检查的插件名称
        filter_plugins = {"BrushFlow", "BrushFlowLowFreq"}

        # 获取本地插件列表
        local_plugins = self.pluginmanager.get_local_plugins()

        # 初始化插件选项列表
        plugin_options = []

        # 从本地插件中筛选出符合条件的插件
        for local_plugin in local_plugins:
            if local_plugin.id in running_plugins and local_plugin.id in filter_plugins:
                plugin_options.append({
                    "title": f"{local_plugin.plugin_name} v{local_plugin.plugin_version}",
                    "value": local_plugin.id,
                    "name": local_plugin.plugin_name
                })

        # 重新编号，保证显示为 1. 2. 等
        for index, option in enumerate(plugin_options, start=1):
            option["title"] = f"{index}. {option['title']}"

        return plugin_options

    def __check_required_plugin_installed(self, plugin_id: str) -> (bool, str):
        """
        检查指定的依赖插件是否已安装
        """
        plugin_names = {
            "SiteStatistic": "站点数据统计",
            "BrushFlow": "站点刷流",
            "BrushFlowLowFreq": "站点刷流（低频版）"
        }

        plugin_name = plugin_names.get(plugin_id, "未知插件")

        # 获取本地插件列表
        local_plugins = self.pluginmanager.get_local_plugins()

        # 检查指定的插件是否已启用
        plugin = next((p for p in local_plugins if p.id == plugin_id and p.installed), None)
        if not plugin:
            return False, f"{plugin_name}未安装"

        return True, f"{plugin_name}已安装"
