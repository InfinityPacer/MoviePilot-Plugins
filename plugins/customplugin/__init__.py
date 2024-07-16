import importlib.util
import os
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from threading import Event
from typing import Any, List, Dict, Tuple, Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase
from app.plugins.customplugin.task import UserTaskBase

lock = threading.Lock()


class CustomPlugin(_PluginBase):
    # 插件名称
    plugin_name = "自定义插件"
    # 插件描述
    plugin_desc = "让每个人都能感受编程的快乐。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/customplugin.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "customplugin_"
    # 加载顺序
    plugin_order = 81
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性

    # 是否开启
    _enabled = False
    # 立即运行一次
    _onlyonce = False
    # 任务执行间隔
    _cron = None
    # 发送通知
    _notify = False
    # 自定义代码
    _user_code = None
    # 自定义任务
    _user_task = None
    # 退出事件
    _event = Event()
    # 定时器
    _scheduler = None

    # endregion

    user_py = Path(__file__).parent / "custom.py"

    def init_plugin(self, config: dict = None):
        if not config:
            return

        # 停止现有任务
        self.stop_service()

        self._enabled = config.get("enabled", False)
        self._onlyonce = config.get("onlyonce", False)
        self._cron = config.get("cron", None)
        self._user_code = config.get("user_code") or self.__get_demo_code()

        if self._enabled or self._onlyonce:
            self.__safe_write_text(file_path=self.user_py, content=self._user_code)
            config["user_code"] = self._user_code
            self.update_config(config)

        # 实例化用户任务
        self._user_task = self.__create_user_instance()

        if self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(
                func=self.execute,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name=f"{self.plugin_name}",
            )
            logger.info(f"{self.plugin_name}服务启动，立即运行一次")
            self._onlyonce = False
            config["onlyonce"] = False
            self.update_config(config=config)
            # 启动服务
            if self._scheduler.get_jobs():
                self._scheduler.print_jobs()
                self._scheduler.start()

    def get_state(self):
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
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
                                            'model': 'onlyonce',
                                            'label': '立即运行一次',
                                            'hint': '插件将立即运行一次',
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
                                    'cols': 12
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
                            }
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
                                        'component': 'VAceEditor',
                                        'props': {
                                            'modelvalue': 'user_code',
                                            'lang': 'python',
                                            'theme': 'monokai',
                                            'style': 'height: 30rem'
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
            "notify": True,
            "only_once": False,
            "user_code": self.__get_demo_code()
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
        services = []

        if self._enabled and self._cron:
            services.append({
                "id": f"{CustomPlugin.__name__}",
                "name": f"{self.plugin_name}",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.execute,
                "kwargs": {}
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
            if self._user_task:
                self._user_task.stop()
                self._user_task = None
        except Exception as e:
            print(str(e))

    def execute(self):
        """
        执行用户任务。如果用户任务不存在，则记录错误日志并发送系统通知
        """
        if not self._user_task:
            self.__log_and_notify_error(message="用户任务实例不存在，无法执行任务")
            return

        try:
            self._user_task.start()
        except Exception as e:
            self.__log_and_notify_error(message=f"执行用户任务时发生错误: {str(e)}")

    def __create_user_instance(self) -> Optional[UserTaskBase]:
        """
        创建自定义实例

        :return: 实例化的用户类对象，如果出错或不符合要求，则返回 None
        :rtype: Optional[UserTaskBase]
        """
        user_module = self.__load_custom_module()
        if user_module is None:
            self.__log_and_notify_error("无法加载用户模块")
            return None

        try:
            for name, obj in user_module.__dict__.items():
                if isinstance(obj, type) and issubclass(obj, UserTaskBase) and obj is not UserTaskBase:
                    return obj()
            self.__log_and_notify_error("未找到符合条件的用户定义类")
        except Exception as e:
            self.__log_and_notify_error(f"实例化用户类失败: {str(e)}")
        return None

    def __load_custom_module(self):
        """
        加载自定义模块，并且每次都强制重新加载以支持代码的热更新。
        """
        try:
            module_name = 'app.plugins.customplugin.custom'
            module_path = os.path.join(os.path.dirname(__file__), 'custom.py')

            spec = importlib.util.spec_from_file_location(module_name, module_path)
            user_module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(user_module)
            # 将加载的模块添加到 sys.modules 中
            sys.modules[module_name] = user_module
            # 通过 reload 强制重新加载，确保获取最新版本的模块
            user_module = importlib.reload(user_module)

            return user_module
        except Exception as e:
            self.__log_and_notify_error(f"加载模块失败: {str(e)}")
            return None

    def __log_and_notify_error(self, message):
        """
        记录错误日志并发送系统通知
        """
        logger.error(message)
        self.systemmessage.put(message, title=f"{self.plugin_name}")

    @staticmethod
    def __normalize_newlines(content, newline="\n"):
        return content.replace("\r\n", "\n").replace("\r", "\n").replace("\n", newline)

    @staticmethod
    def __safe_write_text(file_path, content, encoding="utf-8"):
        normalized_content = CustomPlugin.__normalize_newlines(content)
        current_content = None
        if Path(file_path).exists():
            current_content = Path(file_path).read_text(encoding=encoding)
            current_content = CustomPlugin.__normalize_newlines(current_content)

        if current_content != normalized_content:
            content_bytes = normalized_content.encode(encoding)
            Path(file_path).write_bytes(content_bytes)
            return True  # 表示文件内容已更新
        return False  # 表示文件内容未变，未执行写操作

    @staticmethod
    def __get_demo_code() -> str:
        """获取DEMO示例"""
        return """# 演示代码示例，继承UserTaskBase，并实现start以及stop
# 导入logger用于日志记录
from app.log import logger
# 导入UserTaskBase作为基类
from app.plugins.customplugin.task import UserTaskBase


# 定义一个继承自UserTaskBase的类HelloWorld
class HelloWorld(UserTaskBase):
    def start(self):
        \"\"\"
        开始任务时调用此方法
        \"\"\"
        # 记录任务开始的信息
        logger.info("Hello World. Start.")

    def stop(self):
        \"\"\"
        停止任务时调用此方法
        \"\"\"
        # 记录任务停止的信息
        logger.info("Hello World. Stop.")"""
