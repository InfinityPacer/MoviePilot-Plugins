import threading
from dataclasses import asdict, fields
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple

import pytz
from app.helper.sites import SitesHelper
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings
from app.core.plugin import PluginManager
from app.db.site_oper import SiteOper
from app.log import logger
from app.plugins import _PluginBase
from app.plugins.hitandrun.hnrconfig import HNRConfig, SiteConfig
from app.schemas import NotificationType

lock = threading.Lock()


class HitAndRun(_PluginBase):
    # 插件名称
    plugin_name = "H&R助手"
    # 插件描述
    plugin_desc = "监听下载、订阅、刷流等行为，对H&R种子进行自动标签管理。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/hitandrun.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "hitandrun_"
    # 加载顺序
    plugin_order = 24
    # 可使用的用户级别
    auth_level = 2

    # region 私有属性

    pluginmanager = None
    siteshelper = None
    siteoper = None
    systemconfig = None

    # H&R助手配置
    _hnr_config = HNRConfig()

    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        self.pluginmanager = PluginManager()
        self.siteshelper = SitesHelper()
        self.siteoper = SiteOper()

        if not config:
            return

        result, reason = self.__validate_and_fix_config(config=config)

        if not result and not self._hnr_config:
            self.__update_config_if_error(config=config, error=reason)
            return

        if self._hnr_config.onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._hnr_config.onlyonce = False

            logger.info(f"立即运行一次{self.plugin_name}服务")
            self._scheduler.add_job(
                func=self.check,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name=f"{self.plugin_name}",
            )

            self._scheduler.add_job(
                func=self.spider,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name=f"{self.plugin_name}",
            )

            if self._scheduler.get_jobs():
                # 启动服务
                self._scheduler.print_jobs()
                self._scheduler.start()

        self.__update_config()

    def get_state(self) -> bool:
        return self._hnr_config and self._hnr_config.enabled

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
                                            'label': '立即运行一次',
                                            'hint': '插件将立即运行一次',
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
                                        'component': 'VSelect',
                                        'props': {
                                            'clearable': True,
                                            'model': 'spider_period',
                                            'label': '爬取周期',
                                            'items': [
                                                {'title': '30分钟', 'value': 30},
                                                {'title': '1小时', 'value': 60},
                                                {'title': '3小时', 'value': 180},
                                                {'title': '6小时', 'value': 360},
                                                {'title': '12小时', 'value': 720},
                                                {'title': '24小时', 'value': 1440},
                                            ],
                                            'hint': '将会提高对应站点的访问频率',
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
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'downloader',
                                            'label': '下载器',
                                            'items': [
                                                {'title': 'Qbittorrent', 'value': 'qbittorrent'},
                                                # {'title': 'Transmission', 'value': 'transmission'}
                                            ],
                                            'hint': '选择下载器',
                                            'persistent-hint': True
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'hit_and_run_tag',
                                            'label': '种子标签',
                                            'hint': '标记为H&R种子时添加的标签',
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'seed_time',
                                            'label': '做种时间（小时）',
                                            'type': 'number',
                                            "min": "0",
                                            'hint': '达到目标做种时间后移除标签',
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
                                            'model': 'additional_seed_time',
                                            'label': '附加做种时间（小时）',
                                            'type': 'number',
                                            "min": "0",
                                            'hint': '在做种时间上额外增加的做种时长',
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
                                            'model': 'ratio',
                                            'label': '分享率',
                                            'type': 'number',
                                            "min": "0",
                                            'hint': '达到目标分享率后移除标签',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            }
                        ]
                    },
                    {
                        'component': 'VRow',
                        "content": [
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
                                            'model': 'enable_site_config',
                                            'label': '站点独立配置',
                                            'hint': '启用站点独立配置',
                                            'persistent-hint': True
                                        }
                                    }
                                ]
                            },
                            {
                                "component": "VCol",
                                "props": {
                                    "cols": 12,
                                    "md": 4
                                },
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "dialog_closed",
                                            "label": "打开站点配置窗口",
                                            'hint': '点击弹出窗口以修改站点配置',
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
                                },
                                'content': [
                                    {
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '注意：配置爬取周期后，部分站点将根据设定周期，按随机时间访问站点个人H&R页面从而查漏补缺'
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
                                            'text': '警告：本插件仍在完善阶段，同时并未适配所有场景，如RSS订阅等'
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
                                            'text': '警告：本插件并不能完全适配所有站点，请以实际使用情况为准'
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
                                            'text': '警告：本插件可能导致H&R种子被错误识别，严重甚至导致站点封号，请慎重使用'
                                        }
                                    }
                                ]
                            },
                        ]
                    },
                    {
                        "component": "VDialog",
                        "props": {
                            "model": "dialog_closed",
                            "max-width": "65rem",
                            "overlay-class": "v-dialog--scrollable v-overlay--scroll-blocked",
                            "content-class": "v-card v-card--density-default v-card--variant-elevated rounded-t"
                        },
                        "content": [
                            {
                                "component": "VCard",
                                "props": {
                                    "title": "设置站点配置"
                                },
                                "content": [
                                    {
                                        "component": "VDialogCloseBtn",
                                        "props": {
                                            "model": "dialog_closed"
                                        }
                                    },
                                    {
                                        "component": "VCardText",
                                        "props": {},
                                        "content": [
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
                                                                'component': 'VAceEditor',
                                                                'props': {
                                                                    'modelvalue': 'site_config_str',
                                                                    'lang': 'yaml',
                                                                    'theme': 'monokai',
                                                                    'style': 'height: 30rem',
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
                                                                    'variant': 'tonal'
                                                                },
                                                                'content': [
                                                                    {
                                                                        'component': 'span',
                                                                        'text': '注意：只有启用站点独立配置时，该配置项才会生效'
                                                                    }
                                                                ]
                                                            }
                                                        ]
                                                    }
                                                ]
                                            }
                                        ]
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "notify": True,
            "hit_and_run_tag": "H&R",
            "spider_period": 720,
            "site_config_str": self.__get_demo_config()
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
        if not self._hnr_config:
            return []

        services = []

        if self._hnr_config.enabled:
            services.append({
                "id": f"{self.__class__.__name__}Check",
                "name": f"{self.plugin_name}Check服务",
                "trigger": "interval",
                "func": self.check,
                "kwargs": {"minutes": self._hnr_config.check_period}
            })

            if self._hnr_config.spider_period:
                services.append({
                    "id": f"{self.__class__.__name__}Spider",
                    "name": f"{self.plugin_name}Spider服务",
                    "trigger": "interval",
                    "func": self.spider,
                    "kwargs": {"minutes": self._hnr_config.spider_period}
                })

        return services

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

    def check(self):
        """
        检查服务
        """
        pass

    def spider(self):
        """
        爬虫服务
        """
        pass

    @staticmethod
    def __validate_config(config: HNRConfig) -> (bool, str):
        """
        验证配置是否有效
        """
        if not config.enabled and not config.onlyonce:
            return True, "插件未启用，无需进行验证"

        # 检查站点列表是否为空
        if not config.sites:
            return False, "站点列表不能为空"

        # 检查下载器是否为空
        if not config.downloader:
            return False, "下载器不能为空"

        # 检查做种时间的设置是否有效
        if config.seed_time <= 0:
            return False, "做种时间必须大于0"

        # 检查分享率的设置是否有效
        if config.ratio <= 0:
            return False, "分享率必须大于0"

        return True, "所有配置项都有效"

    def __validate_and_fix_config(self, config: dict = None) -> [bool, str]:
        """
        检查并修正配置值
        """
        if not config:
            return False, ""

        try:
            # 使用字典推导来提取所有字段，并用config中的值覆盖默认值
            hnr_config = HNRConfig(
                **{field.name: config.get(field.name, getattr(HNRConfig, field.name, None))
                   for field in fields(HNRConfig)})

            result, reason = self.__validate_config(config=hnr_config)
            if result:
                # 过滤掉已删除的站点并保存
                if hnr_config.sites:
                    site_id_to_public_status = {site.get("id"): site.get("public") for site in
                                                self.siteshelper.get_indexers()}
                    hnr_config.sites = [
                        site_id for site_id in hnr_config.sites
                        if site_id in site_id_to_public_status and not site_id_to_public_status[site_id]
                    ]

                    site_infos = {}
                    for site_id in hnr_config.sites:
                        site_info = self.siteoper.get(site_id)
                        if site_info:
                            site_infos[site_id] = site_info
                    hnr_config.site_infos = site_infos

                self._hnr_config = hnr_config
                return True, ""
            else:
                self._hnr_config = None
                return result, reason
        except Exception as e:
            self._hnr_config = None
            logger.error(e)
            return False, str(e)

    def __update_config_if_error(self, config: dict = None, error: str = None):
        """异常时停用插件并保存配置"""
        if config:
            if config.get("enabled", False) or config.get("onlyonce", False):
                config["enabled"] = False
                config["onlyonce"] = False
                self.__log_and_notify_error(
                    f"配置异常，已停用{self.plugin_name}，原因：{error}" if error else f"配置异常，已停用{self.plugin_name}，请检查")
            self.update_config(config)

    def __update_config(self):
        """保存配置"""
        config_mapping = asdict(self._hnr_config)
        del config_mapping["site_infos"]
        del config_mapping["site_configs"]
        self.update_config(config_mapping)

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

    def __log_and_notify_error(self, message):
        """
        记录错误日志并发送系统通知
        """
        logger.error(message)
        self.systemmessage.put(message, title=self.plugin_name)

    def __send_message(self, title: str, message: str):
        """发送消息"""
        if self._hnr_config.notify:
            self.post_message(mtype=NotificationType.Plugin, title=f"【{title}】", text=message)

    def __check_required_plugin_installed(self, plugin_id: str) -> (bool, str):
        """
        检查指定的依赖插件是否已安装
        """
        plugin_names = {
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

    @staticmethod
    def __get_demo_config():
        """获取默认配置"""
        return """####### 配置说明 BEGIN #######
# 1. 此配置文件专门用于设定各站点的特定配置，包括做种时间、H&R激活状态等。
# 2. 配置项通过数组形式组织，每个站点的配置作为数组的一个元素，以‘-’标记开头。
# 3. 如果某站点的具体配置项与全局配置相同，则无需单独设置该项，默认采用全局配置。
####### 配置说明 END #######

- # 站点名称，用于标识适用于哪个站点
  site_name: '彩虹岛'
  # 做种时间（小时），做种时期望达到的做种时长，达到目标做种时间后移除标签
  seed_time: 120.0
  # 附加做种时间（小时），在做种时间上额外增加的做种时长
  additional_seed_time: 24.0
  # 分享率，做种时期望达到的分享比例，达到目标分享率后移除标签
  # ratio: 2.0 分享率与全局配置保持一致，无需单独设置
  # H&R激活，站点是否已启用全站H&R，开启后所有种子均视为H&R种子
  hr_active: false

- # 站点名称，用于标识适用于哪个站点
  site_name: '皇后'
  # 做种时间（小时），做种时期望达到的做种时长，达到目标做种时间后移除标签
  seed_time: 36.0
  # 附加做种时间（小时），在做种时间上额外增加的做种时长
  additional_seed_time: 24.0
  # 分享率，做种时期望达到的分享比例，达到目标分享率后移除标签
  ratio: 2.0
  # H&R激活，站点是否已启用全站H&R，开启后所有种子均视为H&R种子
  hr_active: true"""
