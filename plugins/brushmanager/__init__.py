import threading
import time
from datetime import datetime, timedelta
from threading import Event
from typing import Any, List, Dict, Tuple, Optional, Union

import pytz
from apscheduler.schedulers.background import BackgroundScheduler

from app.chain.transfer import TransferChain
from app.core.config import settings
from app.core.plugin import PluginManager
from app.log import logger
from app.modules.qbittorrent import Qbittorrent
from app.modules.transmission import Transmission
from app.plugins import _PluginBase
from app.scheduler import Scheduler
from app.schemas import NotificationType

lock = threading.Lock()


class BrushManager(_PluginBase):
    # 插件名称
    plugin_name = "刷流种子整理"
    # 插件描述
    plugin_desc = "针对刷流种子进行整理操作。"
    # 插件图标
    plugin_icon = "https://github.com/InfinityPacer/MoviePilot-Plugins/raw/main/icons/brushmanager.png"
    # 插件版本
    plugin_version = "1.3"
    # 插件作者
    plugin_author = "InfinityPacer"
    # 作者主页
    author_url = "https://github.com/InfinityPacer"
    # 插件配置项ID前缀
    plugin_config_prefix = "brushmanager_"
    # 加载顺序
    plugin_order = 23
    # 可使用的用户级别
    auth_level = 2

    # region 私有属性

    # 插件Manager
    pluginmanager = None
    # QB分类数据源
    _source_categories = None
    # 目录地址数据源
    _source_paths = None
    # 选择的刷流插件
    _brush_plugin = None
    # 下载器
    _downloader = None
    # 移动目录
    _move_path = None
    # 种子分类
    _category = None
    # 种子标签
    _tag = None
    # 开启通知
    _notify = None
    # 自动分类
    _auto_category = None
    # 添加MP标签
    _mp_tag = None
    # 移除刷流标签
    _remove_brush_tag = None
    # 选择的种子
    _torrent_hashes = None
    # 刷流标签
    _brush_tag = "刷流"
    # 整理Tag
    _organize_tag = "已整理"
    # 退出事件
    _event = Event()
    # 定时器
    _scheduler = None

    # endregion

    def init_plugin(self, config: dict = None):
        self.pluginmanager = PluginManager()

        if not config:
            logger.info("刷流种子整理出错，无法获取插件配置")
            return False

        self._source_paths = config.get("source_paths", None)
        self._source_categories = config.get("source_categories", None)
        self._brush_plugin = config.get("brush_plugin", None)
        self._downloader = config.get("downloader", None)
        self._move_path = config.get("move_path", None)
        self._category = config.get("category", None)
        self._tag = config.get("tag", None)
        self._notify = config.get("notify", False)
        self._auto_category = config.get("auto_category", False)
        self._mp_tag = config.get("mp_tag", False)
        self._remove_brush_tag = config.get("remove_brush_tag", False)
        self._torrent_hashes = config.get("torrents", None)

        self.__update_config(config=config)

        # 停止现有任务
        self.stop_service()

        if not self._downloader:
            self.__log_and_notify_error("没有配置下载器")
            return

        if self._downloader != "qbittorrent":
            logger.warn("当前只支持qbittorrent")
            return

        if not self.__setup_downloader():
            return

        self.__organize()

    def get_state(self):
        pass

    @staticmethod
    def get_command() -> List[Dict[str, Any]]:
        pass

    def get_api(self) -> List[Dict[str, Any]]:
        pass

    def get_form(self) -> Tuple[List[dict], Dict[str, Any]]:
        """
        拼装插件配置页面，需要返回两块数据：1、页面配置；2、数据结构
        """
        # 已安装的刷流插件
        plugin_options = self.__get_plugin_options()
        category_options = self.__get_display_options(self._source_categories)
        path_options = self.__get_display_options(self._source_paths)
        torrent_options = self.__get_torrent_options()

        return [
            {
                'component': 'VForm',
                'content': [
                    {
                        'component': 'VTabs',
                        'props': {
                            'model': '_tabs',
                            'fixed-tabs': True
                        },
                        'content': [
                            {
                                'component': 'VTab',
                                'props': {
                                    'value': 'base_tab'
                                },
                                'text': '基本配置'
                            }, {
                                'component': 'VTab',
                                'props': {
                                    'value': 'data_tab'
                                },
                                'text': '数据配置'
                            }
                        ]
                    },
                    {
                        'component': 'VWindow',
                        'props': {
                            'model': '_tabs',
                            'style': {
                                'padding-top': '24px',
                                'padding-bottom': '24px',
                            },
                        },
                        'content': [
                            {
                                'component': 'VWindowItem',
                                'props': {
                                    'value': 'base_tab'
                                },
                                'content': [
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
                                                        'component': 'VAutocomplete',
                                                        'props': {
                                                            'chips': True,
                                                            'multiple': True,
                                                            'model': 'torrents',
                                                            'label': '选择种子',
                                                            'items': torrent_options,
                                                            "clearable": True,
                                                            'menu-props': {
                                                                'max-width': '-1px'
                                                            }
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
                                                    "cols": 12,
                                                    "md": 3
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
                                            },
                                            {
                                                'component': 'VCol',
                                                'props': {
                                                    "cols": 12,
                                                    "md": 3
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VSelect',
                                                        'props': {
                                                            'model': 'move_path',
                                                            'label': '移动目录',
                                                            'items': path_options,
                                                            "clearable": True
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                'component': 'VCol',
                                                'props': {
                                                    'cols': 12,
                                                    'md': 3
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VSelect',
                                                        'props': {
                                                            'model': 'category',
                                                            'label': '种子分类',
                                                            'items': category_options,
                                                            "clearable": True
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                'component': 'VCol',
                                                'props': {
                                                    'cols': 12,
                                                    'md': 3
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VTextField',
                                                        'props': {
                                                            'model': 'tag',
                                                            'label': '添加种子标签',
                                                            'placeholder': '如：待转移,剧情',
                                                            "clearable": True
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
                                                    'md': 3
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
                                                    'md': 3
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'auto_category',
                                                            'label': '自动分类管理',
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                'component': 'VCol',
                                                'props': {
                                                    'cols': 12,
                                                    'md': 3
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'mp_tag',
                                                            'label': '添加MP标签',
                                                        }
                                                    }
                                                ]
                                            },
                                            {
                                                'component': 'VCol',
                                                'props': {
                                                    'cols': 12,
                                                    'md': 3
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VSwitch',
                                                        'props': {
                                                            'model': 'remove_brush_tag',
                                                            'label': '移除刷流标签',
                                                        }
                                                    }
                                                ]
                                            },
                                        ]
                                    }
                                ]
                            },
                            {
                                'component': 'VWindowItem',
                                'props': {
                                    'value': 'data_tab'
                                },
                                'content': [
                                    {
                                        'component': 'VRow',
                                        'content': [
                                            {
                                                'component': 'VCol',
                                                'props': {
                                                    "cols": 12,
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VSelect',
                                                        'props': {
                                                            'model': 'brush_plugin',
                                                            'label': '刷流插件',
                                                            'items': plugin_options
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
                                                    "cols": 12,
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VTextarea',
                                                        'props': {
                                                            'model': 'source_categories',
                                                            'label': '分类配置',
                                                            'placeholder': '仅支持QB，每一行一个分类，格式为：QB分类名称，分类名称'
                                                                           ':QB分类名称，参考如下：\nMovie\n电影:Movie'
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
                                                    "cols": 12,
                                                },
                                                'content': [
                                                    {
                                                        'component': 'VTextarea',
                                                        'props': {
                                                            'model': 'source_paths',
                                                            'label': '目录配置',
                                                            'placeholder': '每一行一个目录，格式为：目录地址，目录名称:目录地址，'
                                                                           '参考如下：\n/volume1/Media/Movie'
                                                                           '\n电影:/volume1/Media/Movie'
                                                        }
                                                    }
                                                ]
                                            }
                                        ]
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
                                            'type': 'info',
                                            'variant': 'tonal',
                                            'text': '请先在数据配置中初始化数据源，点击保存后再打开插件选择种子进行整理'
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                ]
            }
        ], {
            "notify": True,
            "mp_tag": True,
            "remove_brush_tag": True,
            "auto_category": True
        }

    def get_page(self) -> List[dict]:
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

    def __update_config(self, config: dict):
        """
        更新配置
        """
        # 列出要排除的键
        exclude_keys = ['torrents']

        # 使用字典推导创建一个新字典，排除在 exclude_keys 列表中的键
        filtered_config = {key: value for key, value in config.items() if key not in exclude_keys}

        # 使用 filtered_config 进行配置更新
        self.update_config(filtered_config)

    def __organize(self):
        """
        整理选择的种子进行入库操作
        """
        with lock:
            logger.info("开始准备整理入库任务 ...")
            if not self._torrent_hashes:
                logger.info("没有选择任何种子，取消整理")
                return

            downloader = self.__get_downloader()
            if not downloader:
                self.__log_and_notify_error("连接下载器出错，请检查连接")
                return

            torrents, error = downloader.get_torrents(ids=self._torrent_hashes)
            if error:
                self.__log_and_notify_error("连接下载器出错，请检查连接")
                return

            if not torrents:
                self.__log_and_notify_error("在下载器中没有获取到对应的种子，请检查刷流任务，"
                                            "可尝试开启刷流插件的「下载器监控」同步种子状态")

            logger.info(f"当前选择的种子数量为 {len(self._torrent_hashes)}，"
                        f"实际在下载器中获取到的种子数量为 {len(torrents)}")

            torrent_hash_titles = self.__get_all_hashes_and_titles(torrents)

            logger.info(f"准备为 {len(torrent_hash_titles)} 个种子进行整理任务，种子详情为 {torrent_hash_titles}")

            torrent_datas = self.__get_all_hashes_and_torrents(torrents)

            if self._downloader == "qbittorrent":
                self.__organize_for_qb(torrent_hash_titles=torrent_hash_titles, torrent_datas=torrent_datas)
                self.__run_after_organize()
            else:
                logger.warn("当前只支持qbittorrent")

    def __organize_for_qb(self, torrent_hash_titles: dict, torrent_datas):
        """针对QB进行种子整理"""
        # 获取下载器实例
        downloader = self.__get_downloader()

        # 初始化成功和失败的计数器和列表
        success_count = 0
        failed_count = 0
        success_titles = []
        failed_titles = []

        # 遍历所有种子
        for torrent_hash, torrent_title in torrent_hash_titles.items():
            success = True

            if self._remove_brush_tag:
                try:
                    logger.info(f"正在为种子「{torrent_title}」[{torrent_hash}] 移除「{self._brush_tag}」标签")
                    remove_result = downloader.remove_torrents_tag(ids=[torrent_hash], tag=self._brush_tag)
                    if not remove_result:
                        raise Exception(f"「{self._brush_tag}」标签移除失败，请检查下载器连接")
                    logger.info(f"标签移除成功 - {torrent_hash}")
                except Exception as e:
                    logger.error(f"移除标签失败，种子哈希：{torrent_hash}，错误：{str(e)}")
                    success = False

            if self._mp_tag and success:
                try:
                    logger.info(f"正在为种子「{torrent_title}」[{torrent_hash}] "
                                f"添加「{settings.TORRENT_TAG}」标签并移除「{self._organize_tag}」标签")
                    remove_result = downloader.remove_torrents_tag(ids=[torrent_hash], tag=self._organize_tag)
                    if not remove_result:
                        raise Exception(f"「{self._organize_tag}」标签移除失败，请检查下载器连接")
                    downloader.set_torrents_tag(ids=[torrent_hash], tags=[settings.TORRENT_TAG])
                    logger.info(f"MP标签添加成功 - {torrent_hash}")
                except Exception as e:
                    logger.error(f"设置MP标签失败，种子哈希：{torrent_hash}，错误：{str(e)}")
                    success = False

            if self._tag and success:
                try:
                    logger.info(f"正在为种子「{torrent_title}」[{torrent_hash}] "
                                f"添加「{self._tag}」标签")
                    downloader.set_torrents_tag(ids=[torrent_hash], tags=[self._tag])
                    logger.info(f"标签添加成功 - {torrent_hash}")
                except Exception as e:
                    logger.error(f"设置标签失败，种子哈希：{torrent_hash}，错误：{str(e)}")
                    success = False

            if self._category and success:
                try:
                    logger.info(f"正在为种子「{torrent_title}」[{torrent_hash}] 设置「{self._category}」分类")
                    try:
                        downloader.qbc.torrents_set_category(torrent_hashes=torrent_hash, category=self._category)
                    except Exception as e:
                        logger.warn(f"种子 「{torrent_title}」[{torrent_hash}] "
                                    f"设置分类 {self._category} 失败：{str(e)}, 尝试创建分类再设置")
                        downloader.qbc.torrents_create_category(name=self._category, save_path=self._move_path)
                        downloader.qbc.torrents_set_category(torrent_hashes=torrent_hash, category=self._category)
                    logger.info(f"分类设置成功 - {torrent_hash}")
                except Exception as e:
                    logger.error(f"设置分类失败，种子哈希：{torrent_hash}，错误：{str(e)}")
                    success = False

            # qb中的自动分类管理和目录为二选一的逻辑
            if success:
                if self._auto_category:
                    try:
                        logger.info(f"正在为种子「{torrent_title}」[{torrent_hash}] 开启自动分类管理")
                        downloader.qbc.torrents_set_auto_management(torrent_hashes=torrent_hash,
                                                                    enable=self._auto_category)
                        logger.info(f"自动分类管理开启成功 - {torrent_hash}")
                    except Exception as e:
                        logger.error(f"自动分类管理开启失败，种子哈希：{torrent_hash}，错误：{str(e)}")
                        success = False
                else:
                    if self._move_path:
                        try:
                            logger.info(f"正在为种子「{torrent_title}」[{torrent_hash}] 关闭自动分类管理")
                            downloader.qbc.torrents_set_auto_management(torrent_hashes=torrent_hash,
                                                                        enable=self._auto_category)
                            logger.info(f"自动分类管理关闭成功 - {torrent_hash}")
                        except Exception as e:
                            logger.error(f"自动分类管理关闭失败，种子哈希：{torrent_hash}，错误：{str(e)}")
                        try:
                            logger.info(f"正在为种子「{torrent_title}」[{torrent_hash}] 修改保存路径 {self._move_path}")
                            downloader.qbc.torrents_set_location(torrent_hashes=torrent_hash, location=self._move_path)
                            logger.info(f"修改保存路径成功 - {torrent_hash}")
                        except Exception as e:
                            logger.error(f"修改保存路径失败，种子哈希：{torrent_hash}，错误：{str(e)}")
                            success = False

            # 更新成功或失败的计数器和列表
            if success:
                logger.info(f"「{torrent_title}」[{torrent_hash}] 操作完成，请等待后续入库")
                success_count += 1
                success_titles.append(torrent_title)
            else:
                logger.error(f"「{torrent_title}」[{torrent_hash}] 操作失败，请检查日志调整")
                failed_count += 1
                failed_titles.append(torrent_title)

        # 构建简要的汇总消息
        summary_message_parts = []
        if success_count > 0:
            success_details = "\n".join(success_titles)  # 使用换行符而不是逗号分隔种子标题
            summary_message_parts.append(f"成功操作 {success_count} 个种子，请等待后续入库\n{success_details}")
        if failed_count > 0:
            failed_details = "\n".join(failed_titles)  # 使用换行符而不是逗号分隔种子标题
            summary_message_parts.append(f"失败操作 {failed_count} 个种子，详细详细请查看日志\n{failed_details}")

        summary_message = "\n\n".join(summary_message_parts)  # 使用两个换行符分隔成功和失败的部分

        self.__send_message(title="【刷流种子整理详情】", text=summary_message)

    def __get_torrent_options(self) -> List[dict]:
        """获取种子选项列表"""
        # 检查刷流插件是否已选择
        if not self._brush_plugin:
            logger.info("刷流插件尚未选择，无法获取到刷流任务")
            return []

        # 获取刷流任务数据
        torrent_tasks = self.get_data("torrents", self._brush_plugin)
        if not torrent_tasks:
            logger.info(f"刷流插件：{self._brush_plugin}，没有获取到刷流任务")
            return []

        # 初始化任务选项列表
        torrent_options = []

        # 解析任务数据
        for task_id, task_info in torrent_tasks.items():
            # 检查任务是否已被删除
            if task_info.get('deleted', False):
                continue  # 如果已被删除，则跳过这个任务

            # 格式化描述和标题
            description = task_info.get('description')
            title = f"{description} | {task_info['title']}" if description else task_info['title']

            torrent_options.append({
                "title": title,
                "value": task_id,
                "name": task_info['title']
            })

        # 根据创建时间排序，确保所有元素都有时间戳
        torrent_options.sort(key=lambda x: torrent_tasks[x['value']].get('time', 0), reverse=True)

        # 添加序号到标题
        for index, option in enumerate(torrent_options, start=1):
            option["title"] = f"{index}. {option['title']}"

        # 日志记录获取的任务
        logger.info(f"刷流插件：{self._brush_plugin}，共获取到 {len(torrent_options)} 个刷流任务")

        return torrent_options

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

    @staticmethod
    def __get_display_options(source: str) -> List[dict]:
        """根据源数据获取显示的选项列表"""
        # 检查是否有可用的源数据
        if not source:
            return []

        # 将源字符串分割为单独的列表并去除每一项的前后空格
        categories = [category.strip() for category in source.split("\n") if category.strip()]

        # 初始化分类选项列表
        category_options = []

        # 遍历分割后且清理过的分类数据，格式化并创建包含title, value, name的字典
        for category in categories:
            parts = category.split(":")
            if len(parts) > 1:
                display_name, name = parts[0].strip(), parts[1].strip()
            else:
                display_name = name = parts[0].strip()

            # 将格式化后的数据添加到列表
            category_options.append({
                "title": display_name,
                "value": name,
                "name": display_name
            })

        return category_options

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

    def __get_all_hashes_and_titles(self, torrents):
        """
        获取torrents列表中所有种子的Hash值和标题，存储在一个字典中

        :param torrents: 包含种子信息的列表
        :return: 一个字典，其中键是种子的Hash值，值是种子的标题
        """
        try:
            all_hashes_titles = {}
            for torrent in torrents:
                # 根据下载器类型获取Hash值和标题
                if self._downloader == "qbittorrent":
                    hash_value = torrent.get("hash")
                    torrent_title = torrent.get("name")
                else:
                    hash_value = torrent.hashString
                    torrent_title = torrent.name

                if hash_value and torrent_title:
                    all_hashes_titles[hash_value] = torrent_title
            return all_hashes_titles
        except Exception as e:
            logger.error(f"get_all_hashes_and_titles error: {e}")
            return {}

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
            "tracker": tracker
        }

    def __send_message(self, title: str, text: str):
        """
        发送消息
        """
        if not self._notify:
            return

        self.post_message(mtype=NotificationType.SiteMessage, title=title, text=text)

    def __get_check_job_id(self):
        if self._brush_plugin:
            return "BrushFlowLowFreqCheck" if self._brush_plugin == "BrushFlowLowFreq" else "BrushFlowCheck"
        return None

    def __run_after_organize(self):
        """整理后执行相关任务"""
        self._scheduler = BackgroundScheduler(timezone=settings.TZ)

        # 开启移除刷流标签，则调用刷流插件的Check任务
        if self._remove_brush_tag:
            logger.info(f"已开启移除刷流标签，调用站点刷流Check服务")
            jobid = self.__get_check_job_id()
            if jobid:
                self._scheduler.add_job(lambda: Scheduler().start(jobid), 'date',
                                        run_date=datetime.now(
                                            tz=pytz.timezone(settings.TZ)
                                        ) + timedelta(seconds=3),
                                        name="站点刷流Check服务 by 刷流种子整理)")

        # 开启添加MP标签，则调用下载文件整理服务
        if self._mp_tag:
            logger.info(f"已开启添加MP标签，调用下载文件整理服务")
            jobid = self.__get_check_job_id()
            if jobid:
                self._scheduler.add_job(lambda: TransferChain().process(), 'date',
                                        run_date=datetime.now(
                                            tz=pytz.timezone(settings.TZ)
                                        ) + timedelta(seconds=3),
                                        name="下载文件整理 by 刷流种子整理")

        # 存在任务则启动任务
        if self._scheduler.get_jobs():
            # 启动服务
            self._scheduler.print_jobs()
            self._scheduler.start()

    def __log_and_notify_error(self, message):
        """
        记录错误日志并发送系统通知
        """
        logger.error(message)
        self.systemmessage.put(message)
