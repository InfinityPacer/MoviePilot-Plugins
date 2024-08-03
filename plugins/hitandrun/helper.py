import random
import time
from datetime import datetime, timedelta
from typing import Any, Tuple, List, Optional, Union
from urllib.parse import parse_qs, urlparse, unquote

from app.helper.sites import SitesHelper

from app.core.plugin import PluginManager
from app.db.site_oper import SiteOper
from app.log import logger
from app.utils.string import StringUtils

# 全局变量
pluginmanager = PluginManager()
siteshelper = SitesHelper()
siteoper = SiteOper()


class TorrentHelper:

    def __init__(self, downloader: Any):
        self.downloader = downloader
        self.dl_type = self.get_downloader_type()

    def get_downloader_type(self) -> Optional[str]:
        """
        获取下载器类型
        """
        return "qbittorrent" if hasattr(self.downloader, "qbc") else "transmission" if self.downloader else None

    @staticmethod
    def get_site_by_torrent(torrent: Any) -> Tuple[int, Optional[str]]:
        """
        根据tracker获取站点信息
        """
        trackers = []
        try:
            tracker_url = torrent.get("tracker")
            if tracker_url:
                trackers.append(tracker_url)

            magnet_link = torrent.get("magnet_uri")
            if magnet_link:
                query_params: dict = parse_qs(urlparse(magnet_link).query)
                encoded_tracker_urls = query_params.get('tr', [])
                # 解码tracker URLs然后扩展到trackers列表中
                decoded_tracker_urls = [unquote(url) for url in encoded_tracker_urls]
                trackers.extend(decoded_tracker_urls)
        except Exception as e:
            logger.error(e)

        domain = None
        if not trackers:
            return 0, domain

        # 特定tracker到域名的映射
        tracker_mappings = {
            "chdbits.xyz": "ptchdbits.co",
            "agsvpt.trackers.work": "agsvpt.com",
            "tracker.cinefiles.info": "audiences.me",
        }

        for tracker in trackers:
            if not tracker:
                continue
            # 检查tracker是否包含特定的关键字，并进行相应的映射
            for key, mapped_domain in tracker_mappings.items():
                if key in tracker:
                    domain = mapped_domain
                    break
            else:
                # 使用StringUtils工具类获取tracker的域名
                domain = StringUtils.get_url_domain(tracker)

            site_info = siteshelper.get_indexer(domain)
            if site_info:
                return site_info.get("id"), site_info.get("name")

        # 当找不到对应的站点信息时，返回一个默认值
        return 0, domain

    def get_torrent_info(self, torrent: Any) -> dict:
        """
        获取种子信息
        """
        date_now = int(time.time())
        # QB
        if self.dl_type == "qbittorrent":
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
            if (not torrent.get("added_on")
                    or torrent.get("added_on") < 0):
                dltime = 0
            else:
                dltime = date_now - torrent.get("added_on")
            # 做种时间
            if (not torrent.get("completion_on")
                    or torrent.get("completion_on") < 0):
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
            if (not torrent.get("last_activity")
                    or torrent.get("last_activity") < 0):
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

    def get_torrent_hashes(self, torrents: Union[Any, List[Any]]) -> Union[str, List[str]]:
        """
        获取种子hash
        :param torrents: 单个种子或包含多个种子的列表
        :return: 单个种子的 hash 或包含多个种子 hash 的列表
        """
        try:
            if isinstance(torrents, list):
                # 处理多个种子的情况，返回包含所有种子 hash 的列表
                return [
                    torrent.get("hash") if self.dl_type == "qbittorrent" else torrent.hashString
                    for torrent in torrents
                ]
            else:
                # 处理单个种子的情况，返回该种子的 hash
                return torrents.get("hash") if self.dl_type == "qbittorrent" else torrents.hashString
        except Exception as e:
            print(str(e))
            return "" if isinstance(torrents, list) else []

    def get_torrents(self, torrent_hashes: Optional[Union[str, List[str]]] = None) -> Optional[Any]:
        """
        获取下载器中的种子信息
        :param torrent_hashes: 单个种子哈希或包含多个种子 hash 的列表
        :return: 单个种子的具体信息或包含多个种子信息的列表
        """
        # 处理单个种子哈希的情况，确保其被视为列表
        if isinstance(torrent_hashes, str):
            torrent_hashes = [torrent_hashes]

        torrents, error = self.downloader.get_torrents(ids=torrent_hashes)
        if error:
            logger.warn("连接下载器出错，将在下个时间周期重试")
            return None

        # 如果只有一个种子哈希，直接返回该种子的信息
        if torrent_hashes and len(torrent_hashes) == 1:
            return torrents[0] if torrents else None

        return torrents

    def remove_torrent_tag(self, torrent_hash: str, tags: list, updated_tags: Optional[list] = None):
        """
        移除种子标签
        :param torrent_hash: 种子的哈希值
        :param tags: 要移除的标签列表
        :param updated_tags: 移除后的所有标签
        """
        try:
            unique_tags = list(set(tags))

            if self.dl_type == "qbittorrent":
                self.downloader.remove_torrents_tag(ids=torrent_hash, tags=unique_tags)
            else:
                if updated_tags is not None:
                    # 如果提供了 updated_tags，直接设置这些标签
                    self.downloader.set_torrent_tag(ids=torrent_hash, tags=updated_tags)
                else:
                    # 否则，获取当前种子的标签并移除指定标签
                    torrent = self.get_torrents(torrent_hashes=torrent_hash)
                    if not torrent:
                        logger.warn(f"种子 {torrent_hash} 未找到")
                        return

                    torrent_tags = self.get_torrent_tags(torrent=torrent)
                    for tag in unique_tags:
                        if tag in torrent_tags:
                            torrent_tags.remove(tag)

                    self.downloader.set_torrent_tag(ids=torrent_hash, tags=torrent_tags)
        except Exception as e:
            logger.error(f"无法为 torrent_hash: {torrent_hash} 移除标签 {tags}，错误: {e}")

    def set_torrent_tag(self, torrent_hash: str, tags: list):
        """
        设置种子标签
        :param torrent_hash: 种子的哈希值
        :param tags: 要设置的标签列表
        """
        try:
            unique_tags = list(set(tags))
            if self.dl_type == "qbittorrent":
                self.downloader.set_torrents_tag(ids=torrent_hash, tags=unique_tags)
            else:
                self.downloader.set_torrent_tag(ids=torrent_hash, tags=unique_tags)
        except Exception as e:
            logger.error(f"无法为 torrent_hash: {torrent_hash} 设置标签 {tags}，错误: {e}")

    def get_torrent_tags(self, torrent: Any) -> list[str]:
        """
        获取种子标签
        """
        try:
            if self.dl_type == "qbittorrent":
                tags = torrent.get("tags", "").split(",")
            else:
                tags = torrent.labels or []

            return list(set(tag.strip() for tag in tags if tag.strip()))
        except Exception as e:
            logger.error(f"获取种子标签失败，错误: {e}")
            return []


class TimeHelper:

    @staticmethod
    def random_even_scheduler(num_executions: int = 1,
                              begin_hour: int = 7,
                              end_hour: int = 23) -> List[datetime]:
        """
        按执行次数尽可能平均生成随机定时器
        :param num_executions: 执行次数
        :param begin_hour: 计划范围开始的小时数
        :param end_hour: 计划范围结束的小时数
        """
        trigger_times = []
        start_time = datetime.now().replace(hour=begin_hour, minute=0, second=0, microsecond=0)
        end_time = datetime.now().replace(hour=end_hour, minute=0, second=0, microsecond=0)

        # 计算范围内的总分钟数
        total_minutes = int((end_time - start_time).total_seconds() / 60)
        # 计算每个执行时间段的平均长度
        segment_length = total_minutes // num_executions

        for i in range(num_executions):
            # 在每个段内随机选择一个点
            start_segment = segment_length * i
            end_segment = start_segment + segment_length
            minute = random.randint(start_segment, end_segment - 1)
            trigger_time = start_time + timedelta(minutes=minute)
            trigger_times.append(trigger_time)

        return trigger_times


class FormatHelper:

    @staticmethod
    def format_value(value: float, precision: int = 1, default: str = "N/A"):
        """
        格式化单一数值
        """
        if value:
            formatted = f"{value:.{precision}f}".rstrip("0").rstrip(".")
            return formatted if formatted else "0"
        else:
            return default

    @staticmethod
    def format_hour(number: float, unit: str = "second") -> str:
        """
        格式化数字，限制小数点后一位
        """
        if unit == "second":
            return FormatHelper.format_value(number / 3600)
        elif unit == "minute":
            return FormatHelper.format_value(number / 60)
        elif unit == "hour":
            return FormatHelper.format_value(number)
        return ""

    @staticmethod
    def format_size(value: float):
        """
        格式化种子大小
        """
        return StringUtils.str_filesize(value) if str(value).replace(".", "", 1).isdigit() else value

    @staticmethod
    def format_duration(value: float, additional_time: float = 0, suffix: str = ""):
        """
        格式化周期时间
        """
        value = float(value or 0)
        additional_time = float(additional_time or 0)

        if value == 0 and additional_time == 0:
            return "N/A"

        parts = []
        if value:
            parts.append(FormatHelper.format_value(value))

        if additional_time:
            formatted_additional_time = FormatHelper.format_value(additional_time)
            parts.append(f"(+{formatted_additional_time})")

        return " ".join(parts) + f"{suffix}"

    @staticmethod
    def format_general(value: float, suffix: str = "", precision: int = 1,
                       default: str = "N/A"):
        """
        通用格式化函数，支持精度、后缀和默认值的自定义
        """
        formatted_value = FormatHelper.format_value(value, precision, default)
        if suffix:
            return f"{formatted_value}{suffix}"
        else:
            return formatted_value

    @staticmethod
    def format_comparison(actual: float, required: float, unit: str):
        comparison = "大于" if actual >= required else "小于"
        return f"{FormatHelper.format_value(actual)} {unit}，{comparison} {FormatHelper.format_value(required)} {unit}"
