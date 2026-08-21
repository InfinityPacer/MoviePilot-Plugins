"""基于 MoviePilot V3 数据库治理能力清理整理历史。"""

from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.db.oper.transferhistory import TransferHistoryOper
from app.plugins import _PluginBase
from app.sdk.config import settings
from app.sdk.database import create_backup
from app.sdk.logging import logger


class HistoryClear(_PluginBase):
    """备份当前数据库后清空整理历史。"""

    plugin_name = "历史记录清理"
    plugin_desc = "一键清理历史记录。"
    plugin_icon = "https://raw.githubusercontent.com/InfinityPacer/MoviePilot-Plugins/main/icons/historyclear.png"
    plugin_version = "2.0"
    plugin_author = "InfinityPacer"
    author_url = "https://github.com/InfinityPacer"
    plugin_config_prefix = "historyclear_"
    plugin_order = 61
    auth_level = 1

    def __init__(self) -> None:
        super().__init__()
        self._history_oper: TransferHistoryOper | None = None
        self._clear_history = False

    def init_plugin(self, config: dict | None = None):
        """读取一次性清理开关，并在备份成功后清空整理历史。"""
        self._history_oper = TransferHistoryOper()
        self._clear_history = bool((config or {}).get("clear_history", False))
        if not self._clear_history:
            logger.info("未开启历史记录清理")
            return

        self.update_config({})
        self.__clear()

    def get_state(self) -> bool:
        """返回本次清理开关状态。"""
        return self._clear_history

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        """本插件不注册远程命令。"""
        return []

    def get_api(self) -> List[Dict[str, Any]]:
        """本插件不暴露自有 HTTP API。"""
        return []

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """返回一次性清理开关及 V3 一致性备份说明。"""
        return [
            {
                "component": "VForm",
                "content": [
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12, "md": 6},
                                "content": [
                                    {
                                        "component": "VSwitch",
                                        "props": {
                                            "model": "clear_history",
                                            "label": "一键清理",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "error",
                                            "variant": "tonal",
                                            "text": "清理后将无法从整理历史中恢复下载路径及媒体库路径，请谨慎操作。",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "执行清理前会使用主程序 V3 数据库治理能力创建一致性备份制品。",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "info",
                                            "variant": "tonal",
                                            "text": "仅清理整理历史记录，不删除相关媒体文件；备份制品由主程序数据库治理目录管理。",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "component": "VRow",
                        "content": [
                            {
                                "component": "VCol",
                                "props": {"cols": 12},
                                "content": [
                                    {
                                        "component": "VAlert",
                                        "props": {
                                            "type": "warning",
                                            "variant": "tonal",
                                            "text": "备份成功后才会清理历史记录；如需还原，请使用主程序提供的数据库备份制品。",
                                        },
                                    }
                                ],
                            }
                        ],
                    },
                ],
            }
        ], {"clear_history": False}

    def get_page(self) -> None:
        """本插件没有详情页。"""
        return None

    def get_service(self) -> List[Dict[str, Any]]:
        """本插件不注册定时服务。"""
        return []

    def stop_service(self) -> None:
        """本插件没有需要停止的后台服务。"""

    def __clear(self) -> None:
        """仅在数据库一致性备份落盘后清空整理历史。"""
        if not self._clear_history:
            return

        try:
            logger.info("开始执行历史记录清理")
            err_msg, success = self.__backup_files_to_local()
            if not success:
                self.__log_and_notify(
                    f"清理历史记录失败，备份过程中出现异常: {err_msg}，请检查日志后重试"
                )
                return
            self._history_oper.truncate()
            self.__log_and_notify("已成功备份并清理历史记录")
        except Exception as error:
            self.__log_and_notify(f"清理历史记录失败，请排查日志，错误：{error}")

    def __backup_files_to_local(self) -> Tuple[str, bool]:
        """复制主程序已校验的数据库备份制品到插件备份目录。"""
        try:
            artifact = create_backup()
            source = Path(artifact.path)
            if not source.is_file():
                raise FileNotFoundError(source)

            backup_path = (
                Path(settings.CONFIG_PATH)
                / "plugins"
                / self.__class__.__name__
                / "Backup"
                / artifact.name
            )
            backup_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, backup_path)
            logger.info(f"V3 数据库备份制品已保存：{backup_path}")
            return str(backup_path), True
        except Exception as error:
            logger.error(f"创建或保存 V3 数据库备份制品失败: {error}")
            return str(error), False

    def __log_and_notify(self, message: str) -> None:
        """记录清理结果并发送系统消息。"""
        logger.info(message)
        self.systemmessage.put(message, title="历史记录清理")
