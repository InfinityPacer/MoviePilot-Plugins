"""把 MoviePilot V3 一致性数据库备份制品上传到 WebDAV。"""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urljoin

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from app.plugins import _PluginBase
from app.schemas import NotificationType
from app.sdk.config import settings
from app.sdk.database import create_backup
from app.sdk.logging import logger


_REMOTE_BACKUP_NAME = re.compile(
    r"^(?P<db_type>sqlite|postgresql)_(?P<timestamp>\d{8}_\d{6})"
    r"(?:_\d+)?(?P<suffix>\.db|\.dump)$"
)


class WebDAVBackup(_PluginBase):
    """上传主程序数据库治理服务生成的已校验备份制品。"""

    plugin_name = "WebDAV备份"
    plugin_desc = "定时通过 WebDAV 备份 MoviePilot V3 数据库。"
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/webdavbackup.png"
    plugin_version = "2.0"
    plugin_author = "InfinityPacer"
    author_url = "https://github.com/InfinityPacer"
    plugin_config_prefix = "webdavbackup_"
    plugin_order = 60
    auth_level = 1

    def __init__(self) -> None:
        super().__init__()
        self._client = None
        self._enabled = False
        self._cron = None
        self._max_count = 0
        self._hostname = ""
        self._login = ""
        self._password = ""
        self._digest_auth = False
        self._onlyonce = False
        self._notify = False
        self._disable_check = False
        self._scheduler = None

    def init_plugin(self, config: dict | None = None):
        """初始化 WebDAV 配置并按需注册一次性备份任务。"""
        if not config:
            logger.info("WebDAV备份失败，无法获取插件配置")
            return False

        self.stop_service()
        self._enabled = bool(config.get("enabled", False))
        self._cron = config.get("cron")
        self._notify = bool(config.get("notify", False))
        self._onlyonce = bool(config.get("onlyonce", False))
        self._disable_check = bool(config.get("disable_check", False))
        try:
            self._max_count = max(0, int(config.get("max_count", 0)))
        except (TypeError, ValueError):
            logger.error("配置错误：max_count 必须是整数，已使用 0")
            self._max_count = 0

        self._hostname = str(config.get("hostname") or "")
        self._login = str(config.get("login") or "")
        self._password = str(config.get("password") or "")
        self._digest_auth = bool(config.get("digest_auth", False))

        try:
            from webdav3.client import Client

            webdav_config = {
                "webdav_hostname": self._hostname,
                "webdav_login": self._login,
                "webdav_password": self._password,
                "webdav_digest_auth": self._digest_auth,
            }
            if self._disable_check:
                webdav_config["disable_check"] = True
            self._client = Client(webdav_config)
        except Exception as error:
            self._client = None
            message = f"WebDAV客户端实例化失败：{error}"
            logger.error(message)
            self.__notify_user_if_failed(message)
            return False

        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        if self._onlyonce:
            self._scheduler.add_job(
                func=self.backup,
                trigger="date",
                run_date=datetime.now(tz=pytz.timezone(settings.TZ)) + timedelta(seconds=3),
                name="WebDAV备份",
            )
            self._onlyonce = False
            config["onlyonce"] = False
            self.update_config(config=config)

        if self._scheduler.get_jobs():
            self._scheduler.start()

    def get_state(self) -> bool:
        """返回插件启用状态。"""
        return self._enabled

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """本插件不注册远程命令。"""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """本插件不暴露自有 HTTP API。"""
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回 WebDAV 配置及 V3 数据库备份说明。"""
        return [
            {
                "component": "VForm",
                "content": [
                    {"component": "VSwitch", "props": {"model": "enabled", "label": "启用插件"}},
                    {"component": "VSwitch", "props": {"model": "onlyonce", "label": "立即运行一次"}},
                    {"component": "VSwitch", "props": {"model": "notify", "label": "发送通知"}},
                    {"component": "VTextField", "props": {"model": "hostname", "label": "WebDAV地址"}},
                    {"component": "VTextField", "props": {"model": "login", "label": "登录用户名"}},
                    {"component": "VTextField", "props": {"model": "password", "label": "登录密码", "type": "password"}},
                    {"component": "VSwitch", "props": {"model": "digest_auth", "label": "使用Digest认证"}},
                    {"component": "VCronField", "props": {"model": "cron", "label": "执行周期"}},
                    {"component": "VTextField", "props": {"model": "max_count", "label": "最大保留备份数", "type": "number", "min": 0}},
                    {"component": "VSwitch", "props": {"model": "disable_check", "label": "忽略客户端校验"}},
                    {
                        "component": "VAlert",
                        "props": {
                            "type": "info",
                            "variant": "tonal",
                            "text": "V3 版本上传主程序数据库治理服务生成的 SQLite .db 或 PostgreSQL .dump 一致性备份制品，不复制 user.db*。",
                        },
                    },
                ],
            }
        ], {
            "enabled": False,
            "onlyonce": False,
            "notify": True,
            "hostname": "",
            "login": "",
            "password": "",
            "digest_auth": False,
            "cron": "0 3 * * *",
            "max_count": 0,
            "disable_check": False,
        }

    def get_page(self) -> None:
        """本插件没有详情页。"""
        return None

    def get_service(self) -> List[Dict[str, Any]]:
        """注册 WebDAV 定时备份服务。"""
        if not self._enabled or not self._cron:
            return []
        return [{
            "id": "WebDAVBackup",
            "name": "WebDAV备份",
            "trigger": CronTrigger.from_crontab(self._cron),
            "func": self.backup,
            "kwargs": {},
        }]

    def stop_service(self) -> None:
        """停止插件创建的调度器。"""
        if not self._scheduler:
            return
        try:
            self._scheduler.remove_all_jobs()
            if self._scheduler.running:
                self._scheduler.shutdown()
        finally:
            self._scheduler = None

    def backup(self) -> None:
        """创建并上传一个主程序 V3 一致性数据库备份制品。"""
        logger.info("开始执行 WebDAV V3 数据库备份")
        try:
            if not self.__connect_to_webdav():
                return
            remote_file, success = self.__backup_files_to_webdav()
            if success and self._max_count:
                self.__clean_old_backups(self._max_count)
            message = "备份成功" if success else "备份失败，请排查日志"
            if success:
                logger.info(f"WebDAV备份成功，文件路径：{remote_file}")
            else:
                logger.info(message)
            if self._notify:
                self.__notify_user_if_completed(message)
        except Exception as error:
            message = f"备份失败，请排查日志，错误：{error}"
            logger.error(message)
            if self._notify:
                self.__notify_user_if_failed(message)

    def __backup_files_to_webdav(self) -> Tuple[str, bool]:
        """上传主程序已校验的备份制品，不重新读取活动数据库文件。"""
        try:
            artifact = create_backup()
            source = Path(artifact.path)
            file_name = str(artifact.name)
            if Path(file_name).name != file_name or not source.is_file():
                raise ValueError("主程序返回的数据库备份制品无效")

            remote_file_path = urljoin(
                f"{self._hostname.rstrip('/')}/",
                file_name,
            )
            logger.info(f"远程备份路径为：{remote_file_path}")
            self._client.upload_sync(
                remote_path=file_name,
                local_path=str(source),
            )
            if not self._client.check(file_name):
                logger.error(f"上传完成但未找到远程备份制品：{file_name}")
                return remote_file_path, False
            return remote_file_path, True
        except Exception as error:
            logger.error(f"创建或上传 V3 数据库备份制品失败：{error}")
            return "", False

    def __clean_old_backups(self, max_count: int) -> None:
        """按主程序备份文件名清理 WebDAV 上超出数量的旧制品。"""
        try:
            names = [Path(str(name)).name for name in self._client.list("/")]
            backups = [name for name in names if _REMOTE_BACKUP_NAME.fullmatch(name)]
            backups.sort(key=self.__backup_created_at)
            for name in backups[:-max_count]:
                try:
                    self._client.clean(f"/{name}")
                except Exception as error:
                    logger.error(f"删除 WebDAV 备份制品 {name} 失败：{error}")
        except Exception as error:
            logger.error(f"获取 WebDAV 备份制品列表失败：{error}")

    @staticmethod
    def __backup_created_at(name: str) -> datetime:
        matched = _REMOTE_BACKUP_NAME.fullmatch(name)
        if matched is None:
            raise ValueError(f"无效的数据库备份文件名：{name}")
        return datetime.strptime(matched.group("timestamp"), "%Y%m%d_%H%M%S")

    def __connect_to_webdav(self) -> bool:
        """通过列出根目录验证 WebDAV 客户端可用。"""
        try:
            if not self._client:
                raise RuntimeError("WebDAV 客户端尚未初始化")
            self._client.list("/")
            return True
        except Exception as error:
            message = f"连接到 WebDAV 服务器失败：{error}"
            logger.error(message)
            self.__notify_user_if_failed(message)
            return False

    def __notify_user_if_completed(self, message: str) -> None:
        """发送成功或业务失败通知。"""
        self.post_message(
            mtype=NotificationType.SiteMessage,
            title="【WebDAV备份完成】",
            text=f"{message}，备份时间：{datetime.now():%Y-%m-%d %H:%M:%S}",
        )

    def __notify_user_if_failed(self, message: str) -> None:
        """发送连接或初始化失败通知。"""
        self.post_message(
            mtype=NotificationType.SiteMessage,
            title="【WebDAV备份失败】",
            text=message,
        )
