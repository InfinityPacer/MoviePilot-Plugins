import os
import shutil
import threading
from datetime import datetime
from pathlib import Path
from typing import Any, List, Dict, Tuple

from app.core.config import settings
from app.db.transferhistory_oper import TransferHistoryOper
from app.log import logger
from app.plugins import _PluginBase

lock = threading.Lock()


class HistoryClear(_PluginBase):
    # 插件名称
    plugin_name = "历史记录清理"
    # 插件描述
    plugin_desc = "一键清理历史记录。"
    # 插件图标
    plugin_icon = "https://github.com/InfinityPacer/MoviePilot-Plugins/raw/main/icons/historyclear.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "historyclear_"
    # 加载顺序
    plugin_order = 61
    # 可使用的用户级别
    auth_level = 1
    # history_oper
    _history_oper = None

    # region 私有属性

    # 清理历史记录
    _clear_history = None

    # endregion

    def init_plugin(self, config: dict = None):
        self._history_oper = TransferHistoryOper()
        if not config:
            return

        self._clear_history = config.get("clear_history", False)
        if not self._clear_history:
            self.__log_and_notify("未开启历史记录清理")
            return

        self.update_config({})
        self.__clear()

    def get_state(self) -> bool:
        pass

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
                                            'model': 'clear_history',
                                            'label': '一键清理',
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
                                            'type': 'error',
                                            'variant': 'tonal',
                                            'text': '警告：清理历史记录后将导致后续无法从历史记录中找到下载路径以及媒体库路径，请慎重使用'
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
                                            'type': 'error',
                                            'variant': 'tonal',
                                            'text': '警告：清理历史记录前请先对/config/user.db文件进行备份，以便出现异常后能够还原'
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
                                            'text': '注意：目前仅支持一键清理历史记录，相关文件不会进行删除，请自行在文件系统中删除'
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
                                            'text': '注意：执行清理前插件会备份数据库至路径：'
                                                    '/config/plugins/HistoryClear/Backup/.zip，如有需要，请自行还原'
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
        pass

    def stop_service(self):
        """
        退出插件
        """
        pass

    def __clear(self):
        """一键清理历史记录"""
        if not self._clear_history:
            return

        try:
            logger.info("开始执行历史记录清理")
            err_msg, success = self.__backup_files_to_local()
            if not success:
                self.__log_and_notify(f"清理历史记录失败，备份过程中出现异常: {err_msg}，请检查日志后重试")
                return
            self._history_oper.truncate()
            self.__log_and_notify("已成功备份并清理历史记录")
        except Exception as e:
            self.__log_and_notify(f"清理历史记录失败，请排查日志，错误：{e}")

    def __backup_files_to_local(self) -> Tuple[str, bool]:
        """
        执行备份到本地路径
        """
        local_file_path = self.__backup_and_zip_file()
        if not local_file_path:
            err_msg = "无法创建备份文件"
            logger.error(err_msg)
            return err_msg, False

        try:
            file_name = os.path.basename(local_file_path)
            config_path = Path(settings.CONFIG_PATH)
            backup_file_path = config_path / "plugins" / self.__class__.__name__ / "Backup" / file_name

            # 确保备份目录存在
            backup_file_path.parent.mkdir(parents=True, exist_ok=True)
            # 复制文件到备份路径
            shutil.copy(local_file_path, backup_file_path)
            logger.info(f"备份文件成功，备份路径为：{backup_file_path}")
        except Exception as e:
            err_msg = f"备份文件失败: {e}"
            logger.error(err_msg)
            return err_msg, False
        finally:
            if os.path.exists(local_file_path):
                logger.info(f"清理本地临时文件：{local_file_path}")
                os.remove(local_file_path)

        return "", True

    @staticmethod
    def __backup_and_zip_file() -> str:
        """备份文件并压缩成ZIP文件，按指定格式命名"""
        try:
            config_path = Path(settings.CONFIG_PATH)
            current_time = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
            backup_file_name = f"MoviePilot-Backup-{current_time}"
            backup_path = config_path / backup_file_name
            zip_file_path = str(backup_path) + '.zip'

            # 确保备份路径存在
            backup_path.mkdir(parents=True, exist_ok=True)
            logger.info(f"本地临时备份文件夹路径：{backup_path}")

            # 需要备份的文件列表
            backup_files = [config_path / "user.db"]

            # 将文件复制到备份文件夹
            for file_path in backup_files:
                if file_path.exists():
                    logger.info(f"正在备份文件: {file_path}")
                    shutil.copy(file_path, backup_path)

            # 打包备份文件夹为ZIP
            logger.info(f"正在压缩备份文件: {zip_file_path}")
            shutil.make_archive(base_name=str(backup_path), format='zip', root_dir=str(backup_path))
            logger.info(f"成功创建ZIP备份文件: {zip_file_path}")
            shutil.rmtree(backup_path)  # 删除临时备份文件夹
            logger.info(f"清理本地临时文件夹：{backup_path}")

            return zip_file_path
        except Exception as e:
            logger.error(f"创建备份ZIP文件失败: {e}")
            return ""

    def __log_and_notify(self, message):
        """
        记录日志并发送系统通知
        """
        logger.info(message)
        self.systemmessage.put(message)
