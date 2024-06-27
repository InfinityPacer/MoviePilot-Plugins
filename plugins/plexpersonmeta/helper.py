"""
rating_info.py

这个模块定义了一个用于存储媒体项目信息的 `RatingInfo` 数据类

类:
    RatingInfo -- 用于存储媒体项目信息的数据类
"""
import functools
from dataclasses import dataclass
from typing import Optional

from cachetools import TTLCache
from cachetools.keys import hashkey

from app.log import logger


@dataclass
class RatingInfo:
    key: Optional[str] = None  # 媒体项目的唯一标识
    type: Optional[str] = None  # 媒体项目的类型（例如：电影、电视剧）
    title: Optional[str] = None  # 媒体项目的标题
    search_title: Optional[str] = None  # 用于搜索的标题
    tmdbid: Optional[int] = None  # TMDB 的唯一标识，可选


# 创建一个通用的包装器函数来处理缓存逻辑和日志记录
def cache_with_logging(cache, source):
    def decorator(func):
        @functools.wraps(func)
        def wrapped_func(*args, **kwargs):
            key = hashkey(*args, **kwargs)
            if key in cache:
                if source == "TMDB":
                    logger.info(f"从缓存中获取 TMDB 媒体信息: {kwargs.get('title', 'Unknown Title')}")
                elif source == "Douban":
                    logger.info(f"从缓存中获取豆瓣媒体信息: {kwargs.get('title', 'Unknown Title')}")
                return cache[key]
            result = func(*args, **kwargs)
            if result:
                cache[key] = result
            return result

        return wrapped_func

    return decorator


# 创建缓存对象
tmdb_media_cache = TTLCache(maxsize=10000, ttl=86400)
douban_media_cache = TTLCache(maxsize=10000, ttl=86400)
