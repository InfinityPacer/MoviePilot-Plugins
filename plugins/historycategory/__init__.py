import os
import shutil
import threading
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Dict, Tuple, Optional

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from sqlalchemy import or_, func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.metainfo import MetaInfo
from app.db import db_query, db_update
from app.db.models import TransferHistory
from app.log import logger
from app.plugins import _PluginBase
from app.schemas import MediaInfo, MediaType

lock = threading.Lock()


class HistoryCategory(_PluginBase):
    # 插件名称
    plugin_name = "历史记录分类刷新"
    # 插件描述
    plugin_desc = "一键刷新历史记录中的显示分类。"
    # 插件图标
    plugin_icon = "https://github.com/InfinityPacer/MoviePilot-Plugins/raw/main/icons/historycategory.png"
    # 插件版本
    plugin_version = "1.0"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "historycategory_"
    # 加载顺序
    plugin_order = 62
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性

    # 刷新分类
    _refresh_category = None
    # 分类为空时才刷新分类
    _refresh_if_empty = None
    # 退出事件
    _event = threading.Event()
    # 后台任务
    _scheduler = None

    # endregion

    def init_plugin(self, config: dict = None):
        if not config:
            return

        self._refresh_category = config.get("refresh_category", False)
        self._refresh_if_empty = config.get("refresh_if_empty", True)

        if not self._refresh_category:
            logger.info("未开启历史记录分类刷新")
            return

        self.update_config({})

        self._scheduler = BackgroundScheduler(timezone=settings.TZ)
        self._scheduler.add_job(self.refresh, 'date',
                                run_date=datetime.now(
                                    tz=pytz.timezone(settings.TZ)
                                ) + timedelta(seconds=3),
                                name="历史记录分类刷新")

        if self._scheduler.get_jobs():
            # 启动服务
            self._scheduler.print_jobs()
            self._scheduler.start()

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
                                            'model': 'refresh_category',
                                            'label': '一键刷新',
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
                                            'model': 'refresh_if_empty',
                                            'label': '仅分类为空时刷新',
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
                                            'text': '警告：刷新历史记录分类可能会导致历史记录分类数据异常，请慎重使用'
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
                                            'text': '警告：刷新历史记录分类前请先对/config/user.db文件进行备份，以便出现异常后能够还原'
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
                                            'text': '注意：执行刷新前插件会备份数据库至路径：'
                                                    '/config/plugins/HistoryCategory/Backup/.zip，如有需要，请自行还原'
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
            "refresh_if_empty": True
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

    def refresh(self):
        """一键刷新历史记录分类"""
        if not self._refresh_category:
            return

        with lock:
            try:
                logger.info("准备执行历史记录分类刷新")
                err_msg, success = self.__backup_files_to_local()
                if not success:
                    self.__log_and_notify(f"刷新历史记录分类失败，备份过程中出现异常: {err_msg}，请检查日志后重试")
                    return
                logger.info("已完成数据库备份，开始执行历史记录分类刷新")
                self.__refresh_history()
            except Exception as e:
                self.__log_and_notify(f"刷新历史记录分类失败，请排查日志，错误：{e}")

    def __refresh_history(self):
        """刷新历史记录分类"""
        histories = self.__list_transfer_histories_by_empty_category(db=None,
                                                                     filter_empty_category=self._refresh_if_empty)
        logger.info(f"配置项「仅分类为空时刷新」{'已开启' if self._refresh_if_empty else '未开启'}，"
                    f"获取到符合条件的历史记录共 {len(histories)} 条")

        if not histories:
            logger.warn("没有获取到符合条件的历史记录，跳过刷新")
            return

        # 使用字典进行分组
        history_groups = {}
        for history in histories:
            if history.tmdbid not in history_groups:
                history_groups[history.tmdbid] = []
            history_groups[history.tmdbid].append(history)

        logger.info(f"根据tmdbid进行分组，共获取到{len(history_groups)}组，准备根据分组进行刷新")

        successful_updates = 0
        failed_updates = 0

        # 处理每个分组
        for tmdb_id, history_group in history_groups.items():
            if self._event.is_set():
                logger.warn("外部中断请求，历史记录分类刷新服务停止")
                break
            first_history = history_group[0]
            try:
                logger.info(
                    f"正在刷新分组: {first_history.title}，tmdbid: {tmdb_id} ，该分组共 {len(history_group)} 条记录")
                dest_category = self.__find_category_by_history(history=first_history)

                if dest_category is None:
                    logger.warn(f"无法获取到目标分类，跳过刷新")
                    failed_updates += len(history_group)
                    continue

                history_ids = [h.id for h in history_group]  # 获取当前分组所有记录的ID
                self.__update_history_category(db=None, history_ids=history_ids, category=dest_category)
                logger.info(f"分组: {first_history.title}，分类调整为 {first_history.category} => {dest_category}")
                successful_updates += len(history_group)
            except Exception as e:
                failed_updates += len(history_group)
                logger.error(f"分组: {first_history.title}，tmdbid: {tmdb_id} 刷新分类失败，{e}")

        self.__log_and_notify(f"已完成历史记录分类刷新，成功 {successful_updates} 条，失败 {failed_updates} 条")

    def __find_category_by_history(self, history) -> Optional[str]:
        """根据tmdb_id找到对应的分类"""
        if not history or not history.tmdbid:
            return None

        try:
            # 生成元数据
            meta = MetaInfo(history.title)
            meta.year = history.year
            meta.begin_season = history.seasons or None
            meta.type = MediaType(history.type)
            # 识别媒体信息
            mediainfo: MediaInfo = self.chain.recognize_media(meta=meta, mtype=meta.type,
                                                              tmdbid=history.tmdbid,
                                                              cache=True)
            return mediainfo.category if mediainfo else None
        except Exception as e:
            logger.error(f"识别历史记录 {history.title} 媒体信息失败，错误详情: {e}")
            return None

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
        self.systemmessage.put(message, title="历史记录分类刷新")

    @staticmethod
    @db_query
    def __list_transfer_histories_by_empty_category(db: Optional[Session], filter_empty_category: bool):
        """根据分类是否为空（NULL或仅包含空白字符的字符串）获取历史记录列表"""
        query = db.query(TransferHistory).filter(
            TransferHistory.tmdbid.is_not(0),  # 确保 status 为 True
        )

        if filter_empty_category:
            result = query.filter(
                or_(
                    TransferHistory.category.is_(None),  # 检查是否为 NULL
                    func.trim(TransferHistory.category) == ''  # 使用 trim 函数检查空白字符串
                )
            ).order_by(
                TransferHistory.date.desc()
            ).all()
        else:
            result = query.order_by(
                TransferHistory.date.desc()
            ).all()
        return result

    @staticmethod
    @db_update
    def __update_history_category(db: Optional[Session], history_ids: List[int], category: str):
        """更新一组特定历史记录的分类"""
        # 检查传入的 ID 列表是否为空
        if not history_ids:
            logger.info("未提供历史记录 ID，无法更新分类")
            return

        # 执行更新操作，使用 in_() 来匹配多个 ID
        db.query(TransferHistory).filter(TransferHistory.id.in_(history_ids)).update(
            {'category': category}, synchronize_session='fetch'
        )

        # 提交更改
        db.commit()
