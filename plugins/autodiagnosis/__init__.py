import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Dict, Tuple, Optional, Type

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import and_
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.event import eventmanager, Event
from app.core.module import ModuleManager
from app.db import db_query
from app.db.models import TransferHistory
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.schemas.types import EventType
from app.utils.http import RequestUtils
from app.utils.system import SystemUtils

lock = threading.Lock()


class AutoDiagnosis(_PluginBase):
    # 插件名称
    plugin_name = "自动诊断"
    # 插件描述
    plugin_desc = "自动发起系统健康检查、网络连通性测试以及硬链接检查。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/autodiagnosis.png"
    # 插件版本
    plugin_version = "1.7"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "autodiagnosis_"
    # 加载顺序
    plugin_order = 40
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性

    _module_manager = None

    # 是否开启
    _enabled = False
    # 任务执行间隔
    _cron = None
    # 立即运行一次
    _onlyonce = False
    # 发送通知
    _notify = False
    # 消息类型
    _notify_type = None
    # 系统异常时运行一次
    _execute_when_system_error = None
    # 健康检查模块
    _health_check_modules = None
    # 网络连通性检查地址
    _health_check_sites = None
    # 历史记录硬链接检查
    _history_link_check = None
    # 历史硬链接检查模式
    _history_link_mode = None
    # 目标硬链接测试
    _dir_link_check = None
    # 最近一次执行时间
    _last_execute_time = None
    # 最小执行周期
    _min_execute_span = 9 * 60
    # 最近一次因错误触发执行时间
    _last_execute_for_error_time = None
    # 最小因错误触发执行周期
    _min_execute_for_error_span = 1 * 60
    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        self._module_manager = ModuleManager()

        if not config:
            return

        self._enabled = config.get("enabled", False)
        self._cron = config.get("cron", None)
        self._onlyonce = config.get("onlyonce", False)
        self._execute_when_system_error = config.get("execute_when_system_error", False)
        self._notify = config.get("notify", "on_error")
        self._notify_type = config.get("notify_type", "Plugin")
        self._health_check_modules = config.get("health_check_modules", None)
        self._health_check_sites = config.get("health_check_sites", None)
        self._history_link_check = config.get("history_link_check", None)
        self._history_link_mode = config.get("history_link_mode", "link")
        self._dir_link_check = config.get("dir_link_check", None)
        self._last_execute_time = None
        self._last_execute_for_error_time = None

        if self._onlyonce:
            self._onlyonce = False
            config.update({"onlyonce": False})
            self.update_config(config=config)

            logger.info("立即运行一次自动诊断服务")
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(self.auto_diagnosis, 'date',
                                    run_date=datetime.now(
                                        tz=pytz.timezone(settings.TZ)
                                    ) + timedelta(seconds=3),
                                    name="自动诊断")

            if self._scheduler.get_jobs():
                # 启动服务
                self._scheduler.print_jobs()
                self._scheduler.start()

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
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                            'hint': '插件将立即运行一次',
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
                                            'model': 'execute_when_system_error',
                                            'label': '发生系统错误时运行一次',
                                            'hint': '当系统发生错误时，插件将运行一次',
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
                                            'model': 'cron',
                                            'label': '执行周期',
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
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'notify',
                                            'label': '发送通知',
                                            'items': [
                                                {'title': '不发送', 'value': 'none'},
                                                {'title': '仅异常时发送', 'value': 'on_error'},
                                                {'title': '发送所有通知', 'value': 'always'}
                                            ],
                                            'hint': '发送通知的频率',
                                            'persistent-hint': True
                                        }
                                    }
                                ],
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
                                            'model': 'notify_type',
                                            'label': '通知类型',
                                            'items': [{"title": item.value, "value": item.name}
                                                      for item in NotificationType],
                                            'hint': '通知的类型',
                                            'persistent-hint': True
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
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'clearable': True,
                                            'model': 'health_check_modules',
                                            'label': '系统健康检查',
                                            'items': self.__get_health_check_modules_options(),
                                            'hint': '系统健康检查模块',
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
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'clearable': True,
                                            'model': 'health_check_sites',
                                            'label': '网络连通性测试',
                                            'items': self.__get_health_check_sites_options(),
                                            'hint': '网络连通性测试的网站',
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
                                    'md': 8
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'model': 'history_link_check',
                                            'label': '历史记录硬链接检查',
                                            'items': self.__get_history_link_check_options(),
                                            'hint': '历史记录硬链接检查的范围',
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
                                            'model': 'history_link_mode',
                                            'label': '检查模式',
                                            'items': [
                                                {'title': '硬链接', 'value': 'link'},
                                                {'title': '全部', 'value': 'all'}
                                            ],
                                            'hint': '历史记录转移方式为硬链接或全部',
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
                                        'component': 'VTextarea',
                                        'props': {
                                            'model': 'dir_link_check',
                                            'label': '目录硬链接测试',
                                            'placeholder': '如不需要目录硬链接测试，请不要填写对应目录\n每一行一个目录，格式为：源目录:目标目录，参考如下：\n/volume1/Media/Movie:/volume1/Link/Movie',
                                            'rows': 3,
                                            'no-resize': True,
                                            'hint': '配置目录硬链接测试，格式为：源目录:目标目录',
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
                                            'text': '注意：执行周期建议大于60分钟，最小不能低于10分钟'
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
                                            'text': '注意：建议仅针对需要使用的模块开启系统健康检查以及网络连通性测试，'
                                                    '结果仅供参考，可通过MoviePilot->捷径->系统健康检查/网络连通性测试发起详细检测'
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
                                            'text': '注意：如硬链接测试失败，请检查目录映射，详细信息可参阅'
                                        },
                                        'content': [
                                            {
                                                'component': 'a',
                                                'props': {
                                                    'href': 'https://github.com/jxxghp/MoviePilot/issues/735',
                                                    'target': '_blank'
                                                },
                                                'content': [
                                                    {
                                                        'component': 'u',
                                                        'text': '#735'
                                                    }
                                                ]
                                            }
                                        ]
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
                                            'text': '注意：在宿主机挂载SMB并将其映射到Docker目录时，硬链接测试可能无法兼容'
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
                                            'text': '注意：建议硬链接仅作为一次性检查/测试，不建议开启周期性检查，'
                                                    '结果仅供参考，详细信息请通过命令find /search/directory -inum 进行判断'
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
            "notify": "on_error",
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
        if self._enabled and self._cron:
            return [{
                "id": "AutoDiagnosis",
                "name": "自动诊断",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.auto_diagnosis,
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

    def auto_diagnosis(self, trigger_by_error: bool = False):
        """自动诊断"""
        current_time = datetime.now(tz=pytz.timezone(settings.TZ))

        if trigger_by_error:
            last_execute_time = self._last_execute_for_error_time
            min_execute_span = self._min_execute_for_error_span
        else:
            last_execute_time = self._last_execute_time
            min_execute_span = self._min_execute_span

        if not self.__check_execute_span(last_execute_time, min_execute_span, current_time):
            return

        with lock:
            if trigger_by_error:
                self._last_execute_for_error_time = datetime.now(tz=pytz.timezone(settings.TZ))
            else:
                self._last_execute_time = datetime.now(tz=pytz.timezone(settings.TZ))
            health_modules_results = self.__check_health_modules()
            if self.__check_external_interrupt(service="自动诊断"):
                return
            health_sites_results = self.__check_health_sites()
            if self.__check_external_interrupt(service="自动诊断"):
                return
            history_link_results = self.__check_history_link()
            if self.__check_external_interrupt(service="自动诊断"):
                return
            dir_link_results = self.__check_dir_link()
            if self.__check_external_interrupt(service="自动诊断"):
                return

            results_dict = {
                "系统健康检查": (health_modules_results, False),
                "网络连通性测试": (health_sites_results, False),
                "历史记录硬链接检查": (history_link_results, True),
                "目录硬链接测试": (dir_link_results, False)
            }
            self.__resolve_results(results_dict)

    def __resolve_results(self, results_dict):
        """解析结果并根据通知设置发送消息"""
        if not any(results for results, _ in results_dict.values()):  # 如果所有结果列表都为空，则直接返回
            return

        message = self.__generate_message(results_dict)
        logger.info(message)

        if self._notify == "none":
            return

        # 检查是否有异常
        any_errors = any(not res.get("state") for results, _ in results_dict.values() for res in results)
        if self._notify == "always" or (self._notify == "on_error" and any_errors):
            if message:
                self.post_message(mtype=NotificationType[self._notify_type], title="【自动诊断】", text=message)

    def __generate_message(self, results_dict):
        """根据检查结果生成通知信息"""
        message_lines = []
        for label, (results, include_details) in results_dict.items():
            if results:
                message_lines += self.__format_results(label, results, include_details=include_details)
        return "\n".join(message_lines) if message_lines else None

    @staticmethod
    def __format_results(type_label, results, include_details: bool = False):
        """格式化模块或站点的结果信息"""
        lines = []
        if any(not res.get("state") for res in results):
            lines.append(f"{type_label}：异常")
            for result in results:
                if not result.get("state"):
                    error_message = f"，异常信息：{result.get('errmsg')}" if result.get("errmsg") else ""
                    lines.append(f"- {result.get('name', '未知')}{error_message}")
        else:
            lines.append(f"{type_label}：正常")
            if include_details:
                for result in results:
                    error_message = f"，{result.get('result')}" if result.get("result") else "正常"
                    lines.append(f"- {result.get('name', '未知')}{error_message}")

        return lines

    def __get_preset_modules(self):
        """获取预置模块配置"""
        return [
            {"title": v.get_name(), "value": k}
            for k, v in self._module_manager.get_modules().items()
        ]

    def __get_health_check_modules_options(self):
        """
        查询已加载的模块ID列表，并在列表首部添加一个 '全部' 选项
        """
        # 添加 '全部' 选项
        all_option = {"title": "全部", "value": "all"}
        # 从模块管理器获取其他模块，并格式化为需要的数据结构
        modules = [all_option] + self.__get_preset_modules()
        return modules

    def __check_health_modules(self) -> List[Dict[str, Any]]:
        """
        测试模块可用性
        """
        if not self._health_check_modules:
            logger.info("没有选择模块进行健康检查")
            return []

        logger.info("\n--------------------------------------------------------------------------------")
        logger.info("正在进行系统健康检查")
        preset_modules = self.__get_preset_modules()
        selected_module_ids = self._health_check_modules

        module_manager = self._module_manager
        results = []

        modules = {module.get('value'): module.get('title') for module in preset_modules}

        if "all" in selected_module_ids:
            selected_module_ids = list(modules.keys())

        for module_id in selected_module_ids:
            if self.__check_external_interrupt(service="系统健康检查"):
                return results

            module_name = modules.get(module_id)
            try:
                if not module_name:
                    logger.warning(f"模块 (ID: {module_id}) 不存在于可用模块列表中，无法测试")
                    continue

                state, errmsg = module_manager.test(module_id)
                result_state = True if not state and errmsg and "模块未加载" in errmsg else state
            except Exception as e:
                result_state = False
                errmsg = str(e)

            results.append({
                "id": module_id,
                "name": module_name,
                "state": result_state,
                "errmsg": errmsg or "",
                "result": "正常" if result_state else ("未启用" if errmsg and "模块未加载" in errmsg else "错误")
            })

            self.__log_result(result_state, f"模块 {module_name}", results[-1]["result"], errmsg)

        return results

    @staticmethod
    def __get_preset_sites():
        """获取预置域名配置"""
        return [
            {
                'name': 'api.themoviedb.org',
                'url': f'https://api.themoviedb.org/3/movie/550?api_key={settings.TMDB_API_KEY}',
                'proxy': True,
            },
            {
                'name': 'api.tmdb.org',
                'url': 'https://api.tmdb.org',
                'proxy': True,
            },
            {
                'name': 'www.themoviedb.org',
                'url': 'https://www.themoviedb.org',
                'proxy': True,
            },
            {
                'name': 'api.thetvdb.com',
                'url': 'https://api.thetvdb.com/series/81189',
                'proxy': True,
            },
            {
                'name': 'webservice.fanart.tv',
                'url': 'https://webservice.fanart.tv',
                'proxy': True,
            },
            {
                'name': 'api.telegram.org',
                'url': 'https://api.telegram.org',
                'proxy': True,
            },
            {
                'name': 'qyapi.weixin.qq.com',
                'url': 'https://qyapi.weixin.qq.com/cgi-bin/gettoken',
                'proxy': False,
            },
            {
                'name': 'frodo.douban.com',
                'url': 'https://frodo.douban.com',
                'proxy': False,
            },
            {
                'name': 'slack.com',
                'url': 'https://slack.com',
                'proxy': False,
            },
            {
                'name': 'github.com',
                'url': 'https://github.com',
                'proxy': True,
            },
        ]

    def __get_health_check_sites_options(self):
        """
        查询域名列表，并在列表首部添加一个 '全部' 选项
        """
        # 添加 '全部' 选项
        all_option = {"title": "全部", "value": "all"}

        # 构造站点选项列表
        sites = [all_option] + [
            {"title": site.get("name"), "value": site.get("name")}
            for site in self.__get_preset_sites()
        ]

        return sites

    def __check_health_sites(self) -> List[Dict[str, Any]]:
        """
        测试网络连通性
        """
        if not self._health_check_sites:
            logger.info("没有选择域名进行网络连通性测试")
            return []

        logger.info("\n--------------------------------------------------------------------------------")
        logger.info("正在进行网络连通性测试")
        preset_sites = self.__get_preset_sites()
        selected_sites_names = self._health_check_sites

        results = []

        selected_sites = preset_sites if "all" in selected_sites_names else [
            site for site in preset_sites if site.get("name") in selected_sites_names
        ]

        for site in selected_sites:
            if self.__check_external_interrupt(service="网络连通性测试"):
                return results

            site_name = site.get("name")
            url = site.get("url")
            proxy = site.get("proxy", False)
            try:
                start_time = datetime.now()
                result = RequestUtils(proxies=settings.PROXY if proxy else None, ua=settings.USER_AGENT).get_res(url)
                response_time = round((datetime.now() - start_time).total_seconds() * 1000)

                if result and result.status_code == 200:
                    state = True
                    errmsg = ""
                elif result:
                    state = False
                    errmsg = f"错误码：{result.status_code}"
                else:
                    state = False
                    errmsg = "网络连接失败！"
            except Exception as e:
                state = False
                errmsg = str(e)
                response_time = 0

            errmsg = errmsg if errmsg else f"{response_time}ms"

            results.append({
                "name": site_name,
                "state": state,
                "errmsg": errmsg,
                "result": "正常" if state else "错误",
            })

            self.__log_result(state, f"域名 {site_name}", results[-1]["result"], errmsg)

        return results

    @staticmethod
    def __get_history_link_check_options():
        """
        查询硬链接可选列表
        """
        no_option = {"title": "不检查", "value": "no"}
        all_option = {"title": "全部", "value": "all"}

        recent_options = [
            {"title": f"最近{n}条", "value": n} for n in [10, 100, 1000, 10000]
        ]

        # 构造选项列表
        options = [no_option] + recent_options + [
            {"title": "上次检查以来", "value": "since_last"}
        ] + [all_option]

        return options

    def __check_history_link(self) -> List[Dict[str, Any]]:
        """
        检查历史记录中的硬链接
        """
        if not self._history_link_check or self._history_link_check == "no":
            logger.info("没有启用历史记录硬链接检查")
            return []

        if self._history_link_check == "since_last":
            since_last_time = self.__get_since_last_history_check_time()
            link_items = self.__list_by_date_for_link(db=None, date=since_last_time)
        elif self._history_link_check == "all":
            link_items = self.__list_by_date_for_link(db=None, date=None)
        else:
            link_items = self.__list_by_count_for_link(db=None, count=self._history_link_check)

        if not link_items:
            logger.info("没有查询到相关的硬链接历史记录")
            return [
                {
                    "id": "history_link",
                    "name": "硬链接",
                    "state": True,
                    "errmsg": "没有查询到相关的硬链接历史记录",
                    "result": "没有查询到相关的硬链接历史记录"
                }
            ]

        self.__save_since_last_history_check_time()

        logger.info("\n--------------------------------------------------------------------------------")
        logger.info("正在进行历史记录硬链接检查")
        total_files = 0
        hard_link_count = 0
        not_hard_link_count = 0
        not_hard_link_path = []
        file_not_exist_count = 0
        exception_count = 0
        empty_or_dir_count = 0
        strm_count = 0

        def generate_link_check_summary():
            message_parts = [f"历史记录文件个数：{total_files}", f"硬链接：{hard_link_count} 个"]
            if not_hard_link_count > 0:
                message_parts.append(f"非硬链接：{not_hard_link_count} 个")
            if file_not_exist_count > 0:
                message_parts.append(f"文件不存在跳过：{file_not_exist_count} 个")
            if exception_count > 0:
                message_parts.append(f"发生异常跳过：{exception_count} 个")
            if empty_or_dir_count > 0:
                message_parts.append(f"路径为空跳过：{empty_or_dir_count} 个")
            if strm_count > 0:
                message_parts.append(f"Strm文件跳过：{strm_count} 个")

            message = "，".join(message_parts)
            logger.info(message)

            if not_hard_link_path:
                # 构建一个包含分隔线、路径列表和结束分隔线的单一字符串
                paths_message = "\n---------------------------------- 非硬链接路径 ----------------------------------\n"
                paths_message += "\n".join(str(path) for path in not_hard_link_path)
                paths_message += "\n--------------------------------------------------------------------------------\n"
                # 在日志信息的开头添加一个换行符，并记录
                logger.info("\n" + paths_message)

            return [
                {
                    "id": "history_link",
                    "name": "硬链接",
                    "state": not_hard_link_count == 0,
                    "errmsg": message,
                    "result": message
                }
            ]

        for link_item in link_items:
            if self.__check_external_interrupt(service="历史记录硬链接检查"):
                return generate_link_check_summary()

            total_files += 1
            try:
                src_path = Path(link_item.src) if link_item.src else None
                dest_path = Path(link_item.dest) if link_item.dest else None

                # 检查路径是否为空或者是文件夹
                if not src_path or not dest_path:
                    empty_or_dir_count += 1
                    logger.info(
                        f"源文件或目标文件路径为空，跳过处理。src={link_item.src}, dest={link_item.dest}")
                    continue

                if (src_path.is_file() and dest_path.is_file() and
                        (src_path.suffix == '.strm' or dest_path.suffix == '.strm')):
                    strm_count += 1
                    logger.info(
                        f"源文件或目标文件为 .strm 文件，跳过处理。src={link_item.src}, dest={link_item.dest}")
                    continue

                if src_path.exists() and dest_path.exists():
                    if self.is_hardlink(src_path, dest_path):
                        hard_link_count += 1
                        logger.info(f"{src_path} -> {dest_path} 为同一硬链接路径")
                    else:
                        not_hard_link_count += 1
                        not_hard_link_path.append(src_path)
                        logger.info(f"{src_path} -> {dest_path} 不是同一硬链接路径")
                else:
                    file_not_exist_count += 1
                    logger.info(f"{src_path} 或 {dest_path} 文件不存在")
            except Exception as e:
                exception_count += 1
                logger.error(f"处理文件 {link_item.src} 和 {link_item.dest} 时发生错误: {e}")

        return generate_link_check_summary()

    def __get_since_last_history_check_time(self) -> str:
        """获取配置"""
        option = self.get_data("diagnosis_option") or {}
        return option.get("since_last_history_check_time",
                          datetime.now(pytz.timezone(settings.TZ)).strftime("%Y-%m-%d %H:%M:%S"))

    def __save_since_last_history_check_time(self):
        """保存配置"""
        option = {
            "since_last_history_check_time": datetime.now(pytz.timezone(settings.TZ)).strftime("%Y-%m-%d %H:%M:%S")}
        self.save_data("diagnosis_option", option)

    def __check_dir_link(self) -> List[Dict[str, Any]]:
        """
        目录硬链接测试
        """
        if not self._dir_link_check:
            logger.info("没有启用目录硬链接测试")
            return []

        directory_pairs = self.__parse_directory_pairs(self._dir_link_check)
        if not directory_pairs:
            logger.info("没有获取到正确的目录映射")
            return [
                {
                    "id": "dir_link",
                    "name": "目录测试",
                    "state": False,
                    "errmsg": "没有获取到正确的目录映射",
                    "result": "没有获取到正确的目录映射"
                }
            ]

        logger.info("\n--------------------------------------------------------------------------------")
        logger.info("正在进行目录硬链接测试")

        directory_mappings = "\n".join(f"{src} -> {dest}" for src, dest in directory_pairs)
        logger.info(directory_mappings)

        timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
        count = 1
        results = []
        for src_path, dest_path in directory_pairs:
            logger.info(f"开始测试 {src_path} -> {dest_path}")
            # 创建随机子目录和文件名
            path_name = f"hard_link_test_{timestamp}_{count}"
            src_subdir = src_path / path_name
            dest_subdir = dest_path / path_name
            src_file = src_subdir / f"{path_name}.txt"
            dest_file = dest_subdir / f"{path_name}.txt"
            count += 1
            try:
                # 创建源和目标文件的目录
                src_subdir.mkdir(parents=True, exist_ok=True)
                dest_subdir.mkdir(parents=True, exist_ok=True)
                with open(src_file, "w") as f:
                    f.write("This is a test file for hard linking.")
                # 尝试创建硬链接
                result, message = self._link(src_file, dest_file)
                if result == 0:
                    logger.info(f"硬链接成功 {src_path} -> {dest_path}")
                    results.append({
                        "id": "dir_link",
                        "name": f"{src_path} -> {dest_path}",
                        "state": True,
                        "errmsg": "成功",
                        "result": "成功"
                    })
                else:
                    logger.error(f"硬链接失败 {src_path} -> {dest_path}")
                    results.append({
                        "id": "dir_link",
                        "name": f"{src_path} -> {dest_path}",
                        "state": False,
                        "errmsg": message,
                        "result": message
                    })
            except Exception as err:
                logger.error(f"硬链接发生异常，{err}")
                results.append({
                    "id": "dir_link",
                    "name": f"{src_path} -> {dest_path}",
                    "state": False,
                    "errmsg": str(err),
                    "result": str(err)
                })
            finally:
                self.__cleanup_directory(src_subdir)
                self.__cleanup_directory(dest_subdir)

        for result in results:
            if result.get("state"):
                logger.info(f"{result.get('name')}: 硬链接测试成功")
            else:
                logger.error(f"{result.get('name')}: 硬链接测试失败 - {result['errmsg']}")

        return results

    @staticmethod
    def __cleanup_directory(directory):
        if directory.exists():
            shutil.rmtree(directory)
            logger.info(f"清理临时文件，{directory}")

    @staticmethod
    def _link(src: Path, dest: Path) -> Tuple[int, str]:
        """
        硬链接
        """
        try:
            if dest.exists():
                dest.unlink()
            dest.hardlink_to(src)
            return 0, ""
        except OSError as err:
            logger.error(err)
            return -1, err.strerror
        except Exception as err:
            logger.error(err)
            return -1, str(err)

    @staticmethod
    def __parse_directory_pairs(text: str) -> list[tuple[Path, Path]]:
        """解析目录结构字符串

        :param text: 包含目录对的字符串，格式为 "源目录:目标目录"
        :return: 包含目录对元组的列表
        """
        if not text:
            return []
        lines = text.strip().split("\n")
        directory_pairs = []

        # 解析每一行中的源目录和目标目录
        for line in lines:
            if not line.strip():
                continue
            # 适配Windows路径中的冒号
            if SystemUtils.is_windows():
                # 尝试区分驱动器标识和路径分隔符
                parts = line.split(":", 2) if line.count(":") > 1 else line.split(":")
                if len(parts) == 3:
                    src, dest = Path(parts[0] + ":" + parts[1].strip()), Path(parts[2].strip())
                elif len(parts) == 2:
                    src, dest = Path(parts[0]), Path(parts[1])
                else:
                    logger.warning(f"格式错误，跳过此行：{line}")
                    continue
            else:
                # 对于非Windows系统，正常分割
                parts = line.split(":")
                if len(parts) != 2:
                    logger.warning(f"格式错误，跳过此行：{line}")
                    continue
                src, dest = Path(parts[0].strip()), Path(parts[1].strip())

            directory_pairs.append((src, dest))

        return directory_pairs

    @staticmethod
    def is_hardlink(src: Path, dest: Path) -> bool:
        """判断是否为硬链接"""
        try:
            if not src.exists() or not dest.exists():
                return False
            if src.is_file():
                # 如果是文件，直接比较文件
                return src.samefile(dest)
            else:
                for src_file in src.glob("**/*"):
                    if src_file.is_dir():
                        continue
                    # 计算目标文件路径
                    relative_path = src_file.relative_to(src)
                    target_file = dest.joinpath(relative_path)
                    # 检查是否是硬链接
                    if not target_file.exists() or not src_file.samefile(target_file):
                        return False
                return True
        except Exception as e:
            logger.error(f"判断是否为硬链接时发生异常，{str(e)}")
            return False

    @db_query
    def __list_by_count_for_link(self, db: Optional[Session], count: int) -> list[Type[TransferHistory]]:
        """查询一定数量的转移历史，状态为 True"""
        if not self._history_link_mode or self._history_link_mode == "link":
            query = db.query(TransferHistory).filter(and_(TransferHistory.mode == "link", TransferHistory.status))
        else:
            query = db.query(TransferHistory).filter(TransferHistory.status)
        result = query.order_by(TransferHistory.date.desc()).limit(count).all()
        return list(result)

    @db_query
    def __list_by_date_for_link(self, db: Optional[Session], date: Optional[str]) -> list[Type[TransferHistory]]:
        """
        查询某时间之后的转移历史
        """
        if not self._history_link_mode or self._history_link_mode == "link":
            query = db.query(TransferHistory).filter(and_(TransferHistory.mode == "link", TransferHistory.status))
        else:
            query = db.query(TransferHistory).filter(TransferHistory.status)
        if date is not None:
            query = query.filter(TransferHistory.date > date)
        result = query.order_by(TransferHistory.date.desc()).all()
        return list(result)

    @staticmethod
    def __log_result(state, name, result, errmsg):
        log_message = f"{name} 测试结果：{result}"
        if errmsg:
            log_message += f"，详细信息：{errmsg}"

        if not state:
            logger.error(log_message)
        else:
            logger.info(log_message)

    @staticmethod
    def __check_execute_span(last_execute_time, min_execute_span, current_time):
        """
        检查自上次执行以来是否已过最小时间间隔。

        :param last_execute_time: 上次执行的时间
        :param min_execute_span: 允许的最小时间间隔（秒）
        :param current_time: 当前时间的datetime对象
        :return: 如果时间间隔足够长，返回True；否则返回False
        """
        if last_execute_time:
            time_since_last = (current_time - last_execute_time).total_seconds()
            time_to_wait = min_execute_span - time_since_last
            if time_since_last < min_execute_span:
                logger.warning(f"操作过快，最小时间间隔为 {min_execute_span} 秒。请在 {time_to_wait:.2f} 秒后重试。")
                return False
        return True

    def __check_external_interrupt(self, service: str) -> bool:
        """
        检查是否有外部中断请求，并记录相应的日志信息
        """
        if self._event.is_set():
            logger.warning(f"外部中断请求，{service}服务停止")
            return True
        return False

    @eventmanager.register(EventType.SystemError)
    def handle_error_event(self, event: Event):
        """处理系统错误事件，发起自动诊断"""
        if not self._enabled:
            return

        if not self._execute_when_system_error:
            return

        if not event or not event.event_data:
            return {}

        self.auto_diagnosis(trigger_by_error=True)
