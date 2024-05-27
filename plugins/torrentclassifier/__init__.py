import datetime
import io
import re
import threading
import time
from threading import Event
from typing import Any, List, Dict, Tuple, Optional, Union

import pytz
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from ruamel.yaml import YAML, YAMLError

from app.core.config import settings
from app.log import logger
from app.modules.qbittorrent import Qbittorrent
from app.modules.transmission import Transmission
from app.plugins import _PluginBase
from app.plugins.torrentclassifier.classifierconfig import ClassifierConfig, TorrentFilter, TorrentTarget
from app.schemas import NotificationType

lock = threading.Lock()


class TorrentClassifier(_PluginBase):
    # 插件名称
    plugin_name = "种子关键字分类整理"
    # 插件描述
    plugin_desc = "通过匹配种子关键字进行自定义分类。"
    # 插件图标
    plugin_icon = "https://github.com/InfinityPacer/MoviePilot-Plugins/raw/main/icons/TorrentClassifier.png"
    # 插件版本
    plugin_version = "1.1"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "torrentclassifier_"
    # 加载顺序
    plugin_order = 50
    # 可使用的用户级别
    auth_level = 1

    # region 私有属性

    # 是否开启
    _enabled = False
    # 立即执行一次
    _onlyonce = False
    # 任务执行间隔
    _cron = None
    # 发送通知
    _notify = False
    # 分类配置
    _classifier_configs = None
    # 下载器
    _downloader = None
    # 退出事件
    _event = Event()
    # 定时器
    _scheduler = None

    # endregion

    def init_plugin(self, config: dict = None):
        if not config:
            return False

        # 停止现有任务
        self.stop_service()

        self._enabled = config.get("enabled", False)
        self._onlyonce = config.get("onlyonce", False)
        self._notify = config.get("notify", False)
        self._cron = config.get("cron", None)
        self._downloader = config.get("downloader", None)
        self._classifier_configs = self.__load_configs(config.get("classifier_configs", None))

        if not self._downloader:
            self.__log_and_notify_error("没有配置下载器")
            return

        if self._downloader != "qbittorrent":
            logger.warn("当前只支持qbittorrent")
            return

        if not self.__setup_downloader():
            return

        if self._enabled or self._onlyonce:
            if not self._classifier_configs:
                self.__log_and_notify_error("获取配置项失败，请检查日志")
                return

        if self._onlyonce:
            self._scheduler = BackgroundScheduler(timezone=settings.TZ)
            self._scheduler.add_job(func=self.torrent_classifier, trigger='date',
                                    run_date=datetime.datetime.now(
                                        tz=pytz.timezone(settings.TZ)) + datetime.timedelta(seconds=3)
                                    )
            logger.info(f"种子关键字分类整理服务启动，立即运行一次")
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
                                    "cols": 12,
                                    "md": 4
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
                                            ]
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
                                        'component': 'VAceEditor',
                                        'props': {
                                            'modelvalue': 'classifier_configs',
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
                                            'variant': 'tonal',
                                            'text': '注意：请详细阅读配置说明后，再参考示例规则进行配置'
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
            "downloader": "qbittorrent",
            "classifier_configs": self.__get_demo_config()
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
                "id": "TorrentClassifier",
                "name": "种子关键字分类整理",
                "trigger": CronTrigger.from_crontab(self._cron),
                "func": self.torrent_classifier,
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
        except Exception as e:
            print(str(e))

    def torrent_classifier(self):
        """
        整理选择的种子进行入库操作
        """
        with lock:
            downloader = self.__get_downloader()
            if not downloader:
                self.__log_and_notify_error("连接下载器出错，请检查连接")
                return

            torrents, error = downloader.get_torrents()
            if error:
                self.__log_and_notify_error("连接下载器出错，请检查连接")
                return

            if not torrents:
                logger.info("无法在下载器中找到种子，取消整理")
                return

            logger.info(f"在下载器中获取到的种子数量为 {len(torrents)} ，正在准备进行分类整理")

            torrent_datas = self.__get_all_hashes_and_torrents(torrents)

            if self._downloader == "qbittorrent":
                self.__torrent_classifier_for_qb(torrent_datas=torrent_datas)
            else:
                logger.warn("当前只支持qbittorrent")

    def __torrent_classifier_for_qb(self, torrent_datas: dict):
        """针对QB进行种子整理"""
        # 获取下载器实例
        downloader = self.__get_downloader()

        # 初始化成功和失败的计数器和列表
        success_count = 0
        failed_count = 0
        success_titles = []
        failed_titles = []

        classifier_torrents = self.__get_should_classifier_torrents(torrent_datas=torrent_datas)
        if classifier_torrents:
            logger.info(f"已获取到满足过滤方案的种子共 {len(classifier_torrents)} 个，继续整理")
            torrent_info = "\n".join(
                f"{self.__get_torrent_title(torrent=torrent)}({torrent_hash})"
                for torrent_hash, (torrent, _) in classifier_torrents.items()
            )
            logger.debug(f"正在准备整理的种子信息 \n {torrent_info}")
        else:
            logger.info("没有获取到任何满足过滤方案的种子，取消后续整理")
            return

        for torrent_hash, (torrent, config) in classifier_torrents.items():
            config: ClassifierConfig
            torrent_target = config.torrent_target
            success = True

            torrent_title = self.__get_torrent_title(torrent=torrent)
            torrent_category = self.__get_torrent_category(torrent=torrent)
            torrent_tags = self.__get_torrent_tags(torrent=torrent)

            torrent_key = f"{torrent_title}({torrent_hash})"
            logger.info(f"正在准备整理种子 {torrent_key}")

            if torrent_target.remove_tags:
                remove_tags = []
                try:
                    # 检查是否需要移除所有标签
                    if '@all' in torrent_target.remove_tags:
                        remove_tags = torrent_tags
                        logger.info(f"正在为种子移除所有标签")
                    else:
                        remove_tags = torrent_target.remove_tags
                        logger.info(f"正在为种子移除「{torrent_target.remove_tags}」标签")

                    remove_result = downloader.remove_torrents_tag(ids=torrent_hash, tag=remove_tags)
                    if not remove_result:
                        raise Exception(f"标签移除失败，请检查下载器连接")
                    logger.info(f"标签「{remove_tags}」移除成功")
                except Exception as e:
                    logger.error(f"标签「{remove_tags}」移除失败，错误：{str(e)}")
                    success = False

            if torrent_target.add_tags and success:
                try:
                    logger.info(f"正在为种子添加「{torrent_target.add_tags}」标签")
                    downloader.set_torrents_tag(ids=torrent_hash, tags=torrent_target.add_tags)
                    logger.info(f"标签「{torrent_target.add_tags}」添加成功")
                except Exception as e:
                    logger.error(f"标签「{torrent_target.add_tags}」添加失败，错误：{str(e)}")
                    success = False

            if torrent_target.change_category and success:
                try:
                    logger.info(f"正在为种子设置「{torrent_target.change_category}」分类")
                    try:
                        downloader.qbc.torrents_set_category(torrent_hashes=torrent_hash,
                                                             category=torrent_target.change_category)
                    except Exception as e:
                        logger.warn(f"种子设置分类 {torrent_target.change_category} 失败：{str(e)}, 尝试创建分类再设置")
                        downloader.qbc.torrents_create_category(name=torrent_target.change_category,
                                                                save_path=torrent_target.change_directory)
                        downloader.qbc.torrents_set_category(torrent_hashes=torrent_hash,
                                                             category=torrent_target.change_category)
                    logger.info(f"分类「{torrent_target.change_category}」设置成功")
                except Exception as e:
                    logger.error(f"分类「{torrent_target.change_category}」设置失败，错误：{str(e)}")
                    success = False

            # qb中的自动分类管理和目录为二选一的逻辑
            if success:
                if torrent_target.auto_category:
                    try:
                        logger.info(f"正在为种子开启自动分类管理")
                        downloader.qbc.torrents_set_auto_management(torrent_hashes=torrent_hash,
                                                                    enable=torrent_target.auto_category)
                        logger.info(f"自动分类管理开启成功")
                    except Exception as e:
                        logger.error(f"自动分类管理开启失败，错误：{str(e)}")
                        success = False
                else:
                    if torrent_target.change_directory:
                        try:
                            logger.info(f"正在为种子关闭自动分类管理")
                            downloader.qbc.torrents_set_auto_management(torrent_hashes=torrent_hash,
                                                                        enable=torrent_target.auto_category)
                            logger.info(f"自动分类管理关闭成功")
                        except Exception as e:
                            logger.error(f"自动分类管理关闭失败，错误：{str(e)}")
                        try:
                            logger.info(f"正在为种子修改保存路径 {torrent_target.change_directory}")
                            downloader.qbc.torrents_set_location(torrent_hashes=torrent_hash,
                                                                 location=torrent_target.change_directory)
                            logger.info(f"修改保存路径成功")
                        except Exception as e:
                            logger.error(f"修改保存路径失败，错误：{str(e)}")
                            success = False

                # 更新成功或失败的计数器和列表
                if success:
                    logger.info(f"{torrent_key} 整理成功")
                    success_count += 1
                    success_titles.append(torrent_title)
                else:
                    logger.error(f"{torrent_key} 整理失败，请检查日志")
                    failed_count += 1
                    failed_titles.append(torrent_title)

        # 构建简要的汇总消息
        summary_message_parts = []
        if success_count > 0:
            success_details = "\n".join(success_titles)  # 使用换行符而不是逗号分隔种子标题
            summary_message_parts.append(f"成功整理 {success_count} 个种子\n{success_details}")
        if failed_count > 0:
            failed_details = "\n".join(failed_titles)  # 使用换行符而不是逗号分隔种子标题
            summary_message_parts.append(f"失败整理 {failed_count} 个种子，详细请查看日志\n{failed_details}")

        summary_message = "\n\n".join(summary_message_parts)  # 使用两个换行符分隔成功和失败的部分

        self.__send_message(title="【种子关键字分类整理】", text=summary_message)

    def __get_should_classifier_torrents(self, torrent_datas: dict):
        """获取需要整理的种子"""
        classifier_torrents = {}
        # 遍历所有种子
        for torrent_hash, torrent in torrent_datas.items():
            torrent_title = self.__get_torrent_title(torrent=torrent)

            should_classifier = True
            for config in self._classifier_configs:
                # 判断是否满足整理条件，不满足则跳过，满足则跳出
                should, reason = self.__should_classifier(config=config, torrent=torrent)
                if should:
                    logger.debug(f"{torrent_title}({torrent_hash}) 满足过滤方案，已记录待后续整理")
                    classifier_torrents[torrent_hash] = torrent, config
                    should_classifier = True
                    break
                else:
                    logger.debug(f"{torrent_title}({torrent_hash}) 不满足过滤方案，原因：{reason}")
                    should_classifier = False
                    continue

            if not should_classifier:
                logger.debug(f"{torrent_title}({torrent_hash}) 没有满足所有过滤方案，跳过")
                continue

        return classifier_torrents

    def __should_classifier(self, config: ClassifierConfig, torrent: Any) -> (bool, str):
        """判断是否满足整理条件"""
        torrent_filter = config.torrent_filter
        torrent_target = config.torrent_target
        if not torrent_filter:
            return False, "没有获取到整理规则"

        torrent_title = self.__get_torrent_title(torrent=torrent)
        torrent_category = self.__get_torrent_category(torrent=torrent)
        torrent_tags = self.__get_torrent_tags(torrent=torrent)
        torrent_auto_category = self.__get_torrent_auto_category(torrent=torrent)
        torrent_path = self.__get_torrent_path(torrent=torrent)

        # 判断当前属性是否已符合目标设置
        match, reason = self.__matches_target_settings(torrent_target, torrent_path, torrent_category, torrent_tags,
                                                       torrent_auto_category)
        if match:
            return False, "属性已完全符合目标设置，无需整理"
        else:
            logger.debug(f"存在种子属性不符合目标设置，前置过滤通过，原因：{reason}")

        # 继续检查其他过滤条件
        return self.__check_filters(torrent_filter, torrent_title, torrent_category, torrent_tags)

    @staticmethod
    def __matches_target_settings(torrent_target, torrent_path, torrent_category, torrent_tags,
                                  torrent_auto_category) -> (bool, str):
        """检查种子的当前设置是否符合目标设置"""
        if torrent_target.auto_category != torrent_auto_category:
            return False, f"自动分类 不符合目标值 {torrent_target.auto_category}"
        if not torrent_target.auto_category and not (
                torrent_target.change_directory and torrent_target.change_directory == torrent_path):
            return False, f"存储目录 不符合目标值 {torrent_target.change_directory}"
        if torrent_target.change_category and torrent_target.change_category != torrent_category:
            return False, f"分类 不符合目标值 {torrent_target.change_category}"

        def __calculate_target_tags():
            """计算调整后应有的标签集合"""
            if '@all' in torrent_target.remove_tags:
                # 如果 '@all' 存在于 remove_tags 中，移除所有标签
                modified_tags = set()
            else:
                # 否则仅移除指定标签
                modified_tags = set(torrent_tags) - set(torrent_target.remove_tags)
            # 添加需要的标签
            modified_tags.update(torrent_target.add_tags)
            return modified_tags

        # 计算目标标签集
        target_tags = __calculate_target_tags()
        if target_tags != set(torrent_tags):
            return False, f"标签 不符合目标值 {target_tags}"

        return True, ""

    @staticmethod
    def __check_filters(torrent_filter, torrent_title, torrent_category, torrent_tags) -> (bool, str):
        """应用过滤条件检查是否需要整理"""
        if torrent_filter.torrent_title:
            try:
                if not torrent_title:
                    return False, f"标题为空，不符合标题「{torrent_filter.torrent_title}」条件"

                if not re.search(torrent_filter.torrent_title, torrent_title, re.I):
                    return False, f"不符合标题「{torrent_filter.torrent_title}」条件"
            except Exception as e:
                return False, f"标题过滤失败，错误：{str(e)}"

        if torrent_filter.torrent_category:
            try:
                if not torrent_category:
                    return False, f"分类为空，不符合分类「{torrent_filter.torrent_category}」条件"

                if torrent_filter.torrent_category != torrent_category:
                    return False, f"不符合分类「{torrent_filter.torrent_category}」条件"
            except Exception as e:
                return False, f"分类过滤失败，错误：{str(e)}"

        if torrent_filter.torrent_tags:
            try:
                if not torrent_tags:
                    return False, f"标签为空，不符合标签「{torrent_filter.torrent_tags}」条件"

                # 检查种子的标签列表是否至少与过滤标签列表中的一个标签匹配
                if not any(tag in torrent_tags for tag in torrent_filter.torrent_tags):
                    return False, f"不符合标签「{torrent_filter.torrent_tags}」条件"
            except Exception as e:
                return False, f"标签过滤失败，错误：{str(e)}"

        return True, "OK"

    def __setup_downloader(self):
        """
        根据下载器类型初始化下载器实例
        """
        if self._downloader == "qbittorrent":
            self.qb = Qbittorrent()
            if self.qb.is_inactive():
                self.__log_and_notify_error("qBittorrent未连接")
                return False

        elif self._downloader == "transmission":
            self.tr = Transmission()
            if self.tr.is_inactive():
                self.__log_and_notify_error("Transmission未连接")
                return False

        return True

    def __get_downloader(self) -> Optional[Union[Transmission, Qbittorrent]]:
        """
        根据类型返回下载器实例
        """
        if self._downloader == "qbittorrent":
            return self.qb
        elif self._downloader == "transmission":
            return self.tr
        else:
            return None

    def __get_all_hashes_and_torrents(self, torrents):
        """
        获取torrents列表中所有种子的Hash值和对应的种子对象，存储在一个字典中

        :param torrents: 包含种子信息的列表
        :return: 一个字典，其中键是种子的Hash值，值是对应的种子对象
        """
        try:
            all_hashes_torrents = {}
            for torrent in torrents:
                # 根据下载器类型获取Hash值
                if self._downloader == "qbittorrent":
                    hash_value = torrent.get("hash")
                else:
                    hash_value = torrent.hashString

                if hash_value:
                    all_hashes_torrents[hash_value] = torrent  # 直接将torrent对象存储为字典的值
            return all_hashes_torrents
        except Exception as e:
            logger.error(f"get_all_hashes_and_torrents error: {e}")
            return {}

    def __get_torrent_title(self, torrent: Any) -> Optional[str]:
        """获取种子标题"""
        try:
            if self._downloader == "qbittorrent":
                return torrent.get("name")
            else:
                return torrent.name
        except Exception as e:
            print(str(e))
            return None

    def __get_torrent_category(self, torrent: Any) -> Optional[str]:
        """获取种子分类"""
        try:
            return torrent.get("category").strip() if self._downloader == "qbittorrent" else None
        except Exception as e:
            print(str(e))
            return None

    def __get_torrent_tags(self, torrent: Any) -> List[str]:
        """
        获取种子标签
        """
        try:
            return [str(tag).strip() for tag in torrent.get("tags").split(',')] \
                if self._downloader == "qbittorrent" else torrent.labels or []
        except Exception as e:
            print(str(e))
            return []

    def __get_torrent_auto_category(self, torrent: Any) -> bool:
        """
        获取种子是否启用自动Torrent管理
        """
        try:
            return torrent.get("auto_tmm", False) if self._downloader == "qbittorrent" else False
        except Exception as e:
            print(str(e))
            return False

    def __get_torrent_path(self, torrent: Any) -> Optional[str]:
        """
        获取种子保存路径
        """
        try:
            return torrent.get("save_path", None) if self._downloader == "qbittorrent" else None
        except Exception as e:
            print(str(e))
            return None

    def __get_torrent_info(self, torrent: Any) -> dict:
        """
        获取种子信息
        """
        date_now = int(time.time())
        # QB
        if self._downloader == "qbittorrent":
            """
            {
              "added_on": 1693359031,
              "amount_left": 0,
              "auto_tmm": false,
              "availability": -1,
              "category": "tJU",
              "completed": 67759229411,
              "completion_on": 1693609350,
              "content_path": "/mnt/sdb/qb/downloads/Steel.Division.2.Men.of.Steel-RUNE",
              "dl_limit": -1,
              "dlspeed": 0,
              "download_path": "",
              "downloaded": 67767365851,
              "downloaded_session": 0,
              "eta": 8640000,
              "f_l_piece_prio": false,
              "force_start": false,
              "hash": "116bc6f3efa6f3b21a06ce8f1cc71875",
              "infohash_v1": "116bc6f306c40e072bde8f1cc71875",
              "infohash_v2": "",
              "last_activity": 1693609350,
              "magnet_uri": "magnet:?xt=",
              "max_ratio": -1,
              "max_seeding_time": -1,
              "name": "Steel.Division.2.Men.of.Steel-RUNE",
              "num_complete": 1,
              "num_incomplete": 0,
              "num_leechs": 0,
              "num_seeds": 0,
              "priority": 0,
              "progress": 1,
              "ratio": 0,
              "ratio_limit": -2,
              "save_path": "/mnt/sdb/qb/downloads",
              "seeding_time": 615035,
              "seeding_time_limit": -2,
              "seen_complete": 1693609350,
              "seq_dl": false,
              "size": 67759229411,
              "state": "stalledUP",
              "super_seeding": false,
              "tags": "",
              "time_active": 865354,
              "total_size": 67759229411,
              "tracker": "https://tracker",
              "trackers_count": 2,
              "up_limit": -1,
              "uploaded": 0,
              "uploaded_session": 0,
              "upspeed": 0
            }
            """
            # ID
            torrent_id = torrent.get("hash")
            # 标题
            torrent_title = torrent.get("name")
            # 下载时间
            if not torrent.get("added_on") or torrent.get("added_on") < 0:
                dltime = 0
            else:
                dltime = date_now - torrent.get("added_on")
            # 做种时间
            if not torrent.get("completion_on") or torrent.get("completion_on") < 0:
                seeding_time = 0
            else:
                seeding_time = date_now - torrent.get("completion_on")
            # 分享率
            ratio = torrent.get("ratio") or 0
            # 上传量
            uploaded = torrent.get("uploaded") or 0
            # 平均上传速度 Byte/s
            if dltime:
                avg_upspeed = int(uploaded / dltime)
            else:
                avg_upspeed = uploaded
            # 已未活动 秒
            if not torrent.get("last_activity") or torrent.get("last_activity") < 0:
                iatime = 0
            else:
                iatime = date_now - torrent.get("last_activity")
            # 下载量
            downloaded = torrent.get("downloaded")
            # 种子大小
            total_size = torrent.get("total_size")
            # 添加时间
            add_on = (torrent.get("added_on") or 0)
            add_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(add_on))
            # 种子标签
            tags = torrent.get("tags")
            # tracker
            tracker = torrent.get("tracker")
            # 种子分类
            category = torrent.get("category")
        # TR
        else:
            # ID
            torrent_id = torrent.hashString
            # 标题
            torrent_title = torrent.name
            # 做种时间
            if (not torrent.date_done
                    or torrent.date_done.timestamp() < 1):
                seeding_time = 0
            else:
                seeding_time = date_now - int(torrent.date_done.timestamp())
            # 下载耗时
            if (not torrent.date_added
                    or torrent.date_added.timestamp() < 1):
                dltime = 0
            else:
                dltime = date_now - int(torrent.date_added.timestamp())
            # 下载量
            downloaded = int(torrent.total_size * torrent.progress / 100)
            # 分享率
            ratio = torrent.ratio or 0
            # 上传量
            uploaded = int(downloaded * torrent.ratio)
            # 平均上传速度
            if dltime:
                avg_upspeed = int(uploaded / dltime)
            else:
                avg_upspeed = uploaded
            # 未活动时间
            if (not torrent.date_active
                    or torrent.date_active.timestamp() < 1):
                iatime = 0
            else:
                iatime = date_now - int(torrent.date_active.timestamp())
            # 种子大小
            total_size = torrent.total_size
            # 添加时间
            add_on = (torrent.date_added.timestamp() if torrent.date_added else 0)
            add_time = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(add_on))
            # 种子标签
            tags = torrent.get("tags")
            # tracker
            tracker = torrent.get("tracker")
            # 种子分类
            category = torrent.get("category")

        return {
            "hash": torrent_id,
            "title": torrent_title,
            "seeding_time": seeding_time,
            "ratio": ratio,
            "uploaded": uploaded,
            "downloaded": downloaded,
            "avg_upspeed": avg_upspeed,
            "iatime": iatime,
            "dltime": dltime,
            "total_size": total_size,
            "add_time": add_time,
            "add_on": add_on,
            "tags": tags,
            "tracker": tracker,
            "category": category
        }

    def __send_message(self, title: str, text: str):
        """
        发送消息
        """
        if not self._notify:
            return

        self.post_message(mtype=NotificationType.SiteMessage, title=title, text=text)

    def __log_and_notify_error(self, message):
        """
        记录错误日志并发送系统通知
        """
        logger.error(message)
        self.systemmessage.put(message, "种子关键字分类")

    def __load_configs(self, config_str: Optional[str]) -> List[ClassifierConfig]:
        """加载YAML配置字符串，并构造ClassifierConfig列表。

        Args:
        config_str (str): 配置内容的字符串。

        Returns:
        List[ClassifierConfig]: 从配置字符串解析出的配置列表。
        """
        if not config_str:
            return []

        yaml = YAML()
        try:
            data = yaml.load(io.StringIO(config_str))
            return [ClassifierConfig(
                torrent_filter=TorrentFilter(**item['torrent_filter']),
                torrent_target=TorrentTarget(**item['torrent_target'])
            ) for item in data]
        except YAMLError as e:
            self.__log_and_notify_error(f"YAML parsing error: {e}")
            return []  # 返回空列表或根据需要做进一步的错误处理
        except Exception as e:
            self.__log_and_notify_error(f"Unexpected error during YAML parsing: {e}")
            return []  # 处理任何意外的异常，返回空列表或其它适当的错误响应

    @staticmethod
    def __get_demo_config():
        """获取默认配置"""
        return """####### 配置说明 begin #######
# 1. 本配置文件用于管理种子文件的自动分类和标签管理，采用数组形式以支持多种筛选和应用规则。
# 2. 配置文件中的「torrent_source」定义了种子的来源筛选条件；「torrent_target」定义了应对匹配种子执行的操作。
# 3. 每个配置条目以「-」开头，表示配置文件的数组元素。
# 4. 「remove_tags」字段支持使用特殊值「@all」，代表移除所有标签。
# 5. 「auto_category」启用时开启QBittorrent的「自动Torrent管理」，并忽略「change_directory」配置项。
####### 配置说明 end #######

- torrent_filter:
    # 种子来源部分定义：包括筛选种子的标题、分类和标签
    # 种子标题的过滤条件，支持使用正则表达式匹配
    torrent_title: '测试标题1'
    # 种子必须属于的分类
    torrent_category: '测试分类1'
    # 种子必须具有的标签，多个标签时，任一满足即可
    torrent_tags:
      - '测试标签1'
  torrent_target:
    # 目标种子部分定义：包括修改目标目录、修改分类、新增标签和移除标签的设置
    # 处理后种子的存储目录，auto_category 为 true 时不生效
    change_directory: '/path/to/movies'
    # 处理后的种子新分类
    change_category: '测试新分类1'
    # 添加到种子的新标签
    add_tags:
      - '测试新标签1'
      - '测试新标签2'
    # 移除的标签，使用 '@all' 清除所有标签
    remove_tags:
      - '@all'
    # 是否启用自动分类
    auto_category: true

- torrent_filter:
    # 种子标题的过滤条件，支持使用正则表达式匹配
    torrent_title: '.*\.测试标题2'
    # 种子必须属于的分类
    torrent_category: '测试分类2'
    # 种子必须具有的标签，多个标签时，任一满足即可
    torrent_tags:
      - '测试标签2'
      - 'Rock'
  torrent_target:
    # 处理后种子的存储目录，auto_category 为 true 时不生效
    change_directory: '/path/to/music'
    # 处理后的种子新分类
    change_category: '测试新分类2'
    # 添加到种子的新标签
    add_tags:
      - '测试新标签2'
    # 移除的标签
    remove_tags:
      - '测试标签1'
    # 是否启用自动分类
    auto_category: false"""
