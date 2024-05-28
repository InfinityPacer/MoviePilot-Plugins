import threading
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.core.module import ModuleManager
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.utils.http import RequestUtils

lock = threading.Lock()


class AutoDiagnosis(_PluginBase):
    # 插件名称
    plugin_name = "自动诊断"
    # 插件描述
    plugin_desc = "定时发起系统健康检查以及网络连通性测试。"
    # 插件图标
    plugin_icon = "https://github.com/InfinityPacer/MoviePilot-Plugins/raw/main/icons/autodiagnosis.png"
    # 插件版本
    plugin_version = "1.0"
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
    # 立即执行一次
    _onlyonce = False
    # 发送通知
    _notify = False
    # 消息类型
    _notify_type = None
    # 健康检查模块
    _health_check_modules = None
    # 网络连通性检查地址
    _health_check_sites = None
    # 最近一次执行时间
    _last_execute_time = None
    # min_execute_span
    _min_execute_span = 10 * 60
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
        self._notify = config.get("notify", "on_error")
        self._notify_type = config.get("notify_type", "Plugin")
        self._health_check_modules = config.get("health_check_modules", None)
        self._health_check_sites = config.get("health_check_sites", None)
        self._last_execute_time = None

        self._onlyonce = True
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
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'cron',
                                            'label': '执行周期',
                                            'placeholder': '5位cron表达式'
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
                                            'model': 'notify',
                                            'label': '发送通知',
                                            'items': [
                                                {'title': '不发送', 'value': 'none'},
                                                {'title': '仅异常时发送', 'value': 'on_error'},
                                                {'title': '发送所有通知', 'value': 'always'}
                                            ]
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
                                            'multiple': False,
                                            'chips': True,
                                            'model': 'notify_type',
                                            'label': '通知类型',
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
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'model': 'health_check_modules',
                                            'label': '系统健康检查',
                                            'items': self.__get_health_check_modules_options()
                                        }
                                    }
                                ]
                            },
                            {
                                'component': 'VCol',
                                'props': {
                                    'cols': 12,
                                    'md': 6
                                },
                                'content': [
                                    {
                                        'component': 'VSelect',
                                        'props': {
                                            'multiple': True,
                                            'chips': True,
                                            'model': 'health_check_sites',
                                            'label': '网络连通性测试',
                                            'items': self.__get_health_check_sites_options()
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
                                            'text': '注意：建议仅针对需要使用的模块开启系统健康检查以及网络连通性测试'
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
                                            'text': '注意：结果仅供参考，可通过MoviePilot->捷径->系统健康检查/网络连通性测试发起详细检测'
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
        if self._enabled:
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

    def auto_diagnosis(self):
        """自动诊断"""
        current_time = datetime.now(tz=pytz.timezone(settings.TZ))
        if not self.__check_execute_span(self._last_execute_time, self._min_execute_span, current_time):
            return

        with lock:
            self._last_execute_time = datetime.now(tz=pytz.timezone(settings.TZ))
            health_modules_results = self.__check_health_modules()
            if self.__check_external_interrupt(service="自动诊断"):
                return
            health_sites_result = self.__check_health_sites()
            if self.__check_external_interrupt(service="自动诊断"):
                return
            self.__resolve_results(health_modules_results, health_sites_result)

    def __resolve_results(self, health_modules_results: List[Dict[str, Any]],
                          health_sites_results: List[Dict[str, Any]]):
        """解析结果并根据通知设置发送消息"""
        if not (health_modules_results or health_sites_results):
            return
        if self._notify == "none":
            return

        # 检查是否有异常
        any_errors = any(not res.get("state") for res in health_modules_results + health_sites_results)

        if self._notify == "always" or (self._notify == "on_error" and any_errors):
            message = self.__generate_message(health_modules_results, health_sites_results)
            if message:
                self.post_message(mtype=NotificationType[self._notify_type], title="【自动诊断】", text=message)

    def __generate_message(self, modules_results, sites_results):
        """根据检查结果生成通知信息"""
        message_lines = []
        # 分别生成模块和站点的检查结果
        if modules_results:
            message_lines += self.__format_results("系统健康检查", modules_results)
        if sites_results:
            message_lines += self.__format_results("网络连通性测试", sites_results)

        return "\n".join(message_lines) if message_lines else None

    @staticmethod
    def __format_results(type_label, results):
        """格式化模块或站点的结果信息"""
        lines = []
        if any(not res.get("state") for res in results):
            lines.append(f"{type_label}存在异常：")
            for result in results:
                if not result.get("state"):
                    error_message = f"，异常信息：{result.get('errmsg')}" if result.get('errmsg') else ""
                    lines.append(f"- {result.get('name', '未知')}{error_message}")
        else:
            lines.append(f"{type_label}：正常。")

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
                logger.warn(f"操作过快，最小时间间隔为 {min_execute_span} 秒。请在 {time_to_wait:.2f} 秒后重试。")
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
