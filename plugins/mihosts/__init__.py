import json
import threading
from datetime import datetime, timedelta
from typing import Any, List, Dict, Tuple, Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from requests import Response

from app.core.config import settings
from app.log import logger
from app.plugins import _PluginBase
from app.schemas.types import NotificationType
from app.utils.common import retry
from app.utils.http import RequestUtils
from app.utils.system import SystemUtils

lock = threading.Lock()


class MIHosts(_PluginBase):
    # 插件名称
    plugin_name = "小米路由Hosts"
    # 插件描述
    plugin_desc = "定时将本地Hosts同步至小米路由Hosts。"
    # 插件图标
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/mihosts.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "mihosts_"
    # 加载顺序
    plugin_order = 63
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
    # 应用ID
    _app_id = None
    # 设备ID
    _device_id = None
    # 客户端ID
    _client_id = None
    # 作用域
    _scope = "1+1000+3"
    # 访问令牌
    _token = None
    # 忽略的IP或域名
    _ignore = None
    # 定时器
    _scheduler = None
    # 退出事件
    _event = threading.Event()

    # endregion

    def init_plugin(self, config: dict = None):
        if not config:
            return

        self._enabled = config.get("enabled")
        self._onlyonce = config.get("onlyonce")
        self._cron = config.get("cron")
        self._notify = config.get("notify")
        self._app_id = config.get("app_id")
        self._device_id = config.get("device_id")
        self._client_id = config.get("client_id")
        self._scope = config.get("scope")
        self._token = config.get("token")
        self._ignore = config.get("ignore")

        # 停止现有任务
        self.stop_service()

        # 启动服务
        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        if self._onlyonce:
            logger.info(f"{self.plugin_name}服务，立即运行一次")
            self._scheduler.add_job(
                func=self.fetch_and_update_hosts,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name=f"{self.plugin_name}",
            )
            # 关闭一次性开关
            self._onlyonce = False
            config["onlyonce"] = False
            self.update_config(config=config)

        # 启动服务
        if self._scheduler.get_jobs():
            self._scheduler.print_jobs()
            self._scheduler.start()

    def get_state(self) -> bool:
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
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
            logger.info(f"{self.plugin_name}定时服务启动，时间间隔 {self._cron} ")
            return [{
                "id": self.__class__.__name__,
                "name": f"{self.plugin_name}服务",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.fetch_and_update_hosts,
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
            logger.info(str(e))

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
                                            'label': '运行周期',
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
                                    'cols': 12,
                                    'md': 4
                                },
                                'content': [
                                    {
                                        'component': 'VTextField',
                                        'props': {
                                            'model': 'app_id',
                                            'label': '应用ID',
                                            'hint': '请输入appId',
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
                                            'model': 'device_id',
                                            'label': '设备ID',
                                            'hint': '请输入deviceId',
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
                                            'model': 'client_id',
                                            'label': '客户端ID',
                                            'hint': '请输入clientId',
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
                                            'model': 'scope',
                                            'label': '作用域',
                                            'hint': '请输入scope',
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
                                            'model': 'token',
                                            'label': '访问令牌',
                                            'hint': '请输入token',
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
                                            'model': 'ignore',
                                            'label': '忽略的IP或令牌',
                                            'hint': '如：10.10.10.1|wiki.movie-pilot.org',
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
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '注意：可配合自定义Hosts以及Cloudflare IP优选插件，实现小米路由Cloudflare优选'
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
                                        'component': 'VAlert',
                                        'props': {
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '注意：可以通过访问米家 -> 路由 -> 自定义Hosts，点击右上角复制链接，'
                                                    '从而获取到对应的访问令牌、设备ID、作用域等数据，如无可用数据，请使用默认值'
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
            "cron": "0 6 * * *",
            "app_id": "2882303761517675329",
            "client_id": "2882303761517675329",
            "scope": "1+1000+3"
        }

    def get_page(self) -> List[dict]:
        pass

    def fetch_and_update_hosts(self):
        """
        获取远程hosts并用本地hosts更新
        """
        remote_hosts = self.__fetch_remote_hosts()

        local_hosts = self.__get_local_hosts()
        if not local_hosts:
            self.__send_message(title="【小米路由Hosts更新】", text="获取本地hosts失败，更新失败，请检查日志")
            return

        updated_hosts = self.__update_remote_hosts_with_local(local_hosts, remote_hosts)
        if not updated_hosts:
            logger.info("没有需要更新的hosts，跳过")
            return

        self.__make_request_with_new_hosts(updated_hosts)

    def __prepare_request_data(self) -> dict:
        """
        准备请求远程服务器所需的数据
        """
        return {
            "app_id": self._app_id,
            "device_id": self._device_id,
            "client_id": self._client_id,
            "scope": self._scope,
            "token": self._token
        }

    def __fetch_remote_hosts(self) -> list:
        """
        请求远程服务器，获取远程hosts
        """
        logger.info("正在准备获取远程hosts")
        request_data = self.__prepare_request_data()
        remote_hosts = []
        try:
            response = self.__make_request(method="get", **request_data)
            if response:
                logger.info(f"请求远程hosts响应: {response.text}")
                result = response.json()
                if result.get("code") == 0:
                    remote_hosts = result.get("hosts", [])
                    logger.info(f"获取远程hosts成功: {remote_hosts}")
                else:
                    logger.error(f"获取远程hosts失败，失败信息：{result.get('msg')}")
            else:
                logger.error("获取远程hosts失败")
        except Exception as e:
            logger.error(f"请求发送异常: {e}")
        return remote_hosts

    def __make_request_with_new_hosts(self, hosts):
        """
        使用更新后的hosts信息进行请求
        """
        message_title = "【小米路由Hosts更新】"
        request_data = self.__prepare_request_data()
        json_hosts = json.dumps(hosts)
        request_data["hosts"] = json_hosts

        try:
            response = self.__make_request(method="post", **request_data)
            if response and response.status_code == 200:
                logger.info(f"更新远程hosts响应: {response.text}")
                result = response.json()
                if result.get("code") == 0:
                    message_text = "更新远程hosts成功"
                    logger.info(message_text)
                else:
                    message_text = f"更新远程hosts失败，失败信息：{result.get('msg')}"
                    logger.error(message_text)
            else:
                message_text = "更新远程hosts失败"
                logger.error(message_text)
        except Exception as e:
            message_text = f"请求发送异常：{e}"
            logger.error(message_text)

        self.__send_message(title=message_title, text=message_text)

    def __update_remote_hosts_with_local(self, local_hosts: list, remote_hosts: list) -> list:
        """
        使用本地hosts内容覆盖远程hosts，并合并未冲突的条目，同时根据忽略列表忽略特定的本地定义，如 localhost
        """
        try:
            ignore = self._ignore.split("|") if self._ignore else []

            # 创建远程hosts字典
            remote_dict = {line.split()[1]: line.strip() for line in remote_hosts if
                           " " in line and not line.strip().startswith('#')}

            # 用本地hosts更新远程hosts，忽略特定的本地条目和忽略列表中的条目
            for line in local_hosts:
                # 移除行首可能的 UTF-8 BOM
                line = line.lstrip("\ufeff").strip()
                if line.startswith("#") or any(host in line for host in ignore):
                    continue
                if line.startswith("#") or "localhost" in line or "127.0.0.1" in line:
                    continue
                if " " not in line:
                    continue
                parts = line.split()
                if len(parts) < 2:
                    continue
                ip = parts[0]
                hostname = parts[1]
                if ip in ignore or hostname in ignore:
                    continue
                # 只更新非本地特定的条目
                remote_dict[hostname] = f"{ip} {hostname}"

            # 组装最终的hosts列表，包括更新远程hosts和添加新的本地hosts
            updated_hosts = []
            # 首先添加所有注释行和特定本地行，不进行修改
            for line in remote_hosts:
                if line.strip().startswith('#'):
                    updated_hosts.append(line.strip())
                else:
                    parts = line.split()
                    if len(parts) > 1 and parts[1] in remote_dict:
                        updated_hosts.append(remote_dict[parts[1]])

            # 添加本地hosts中的新条目，这些条目在远程hosts中未出现
            for hostname, full_entry in remote_dict.items():
                if all(hostname not in entry for entry in updated_hosts):
                    updated_hosts.append(full_entry)

            logger.info(f"更新后的hosts为: {updated_hosts}")
            return updated_hosts
        except Exception as e:
            logger.error(f"合并hosts失败: {e}")
            return []

    @staticmethod
    def __get_local_hosts() -> list:
        """
        获取本地hosts文件的内容
        """
        try:
            logger.info("正在准备获取本地hosts")
            # 确定hosts文件的路径
            if SystemUtils.is_windows():
                hosts_path = r"c:\windows\system32\drivers\etc\hosts"
            else:
                hosts_path = '/etc/hosts'
            with open(hosts_path, "r", encoding="utf-8") as file:
                local_hosts = file.readlines()
            logger.info(f"本地hosts文件读取成功: {local_hosts}")
            return local_hosts
        except Exception as e:
            logger.error(f"读取本地hosts文件失败: {e}")
            return []

    @retry(Exception, logger=logger)
    def __make_request(self, method: str, app_id: str, device_id: str, client_id: str,
                       token: str, scope: str = "1+1000+3", hosts: str = "") -> Optional[Response]:
        base_url = "https://www.gorouter.info/api-third-party/service/internal/custom_host_"
        url = f"{base_url}{'get' if method.lower() == 'get' else 'set'}"

        data = {
            "appId": app_id,
            "deviceId": device_id,
            "clientId": client_id,
            "scope": scope,
            "token": token,
            "hosts": hosts
        }

        request = RequestUtils(ua=settings.USER_AGENT, referer="https://s.miwifi.com", accept_type="*/*")
        if method.lower() == "get":
            response = request.request(method=method, url=url, params=data, raise_exception=True)
        else:
            response = request.request(method=method, url=url, data=data, raise_exception=True)
        return response

    def __send_message(self, title: str, text: str):
        """
        发送消息
        """
        if not self._notify:
            return

        self.post_message(mtype=NotificationType.Plugin, title=title, text=text)
