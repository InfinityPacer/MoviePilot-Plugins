"""
helper.py

这个模块定义了用于存储媒体项目信息的 `RatingInfo` 数据类以及缓存装饰器。

类:
    RatingInfo -- 用于存储媒体项目信息的数据类
    DynamicTTLCache -- 自定义的 TTLCache 类，支持动态设置 TTL
函数:
    cache_with_logging -- 创建一个装饰器，用于在函数执行时处理缓存逻辑和日志记录
"""
import functools
from app.log import logger
from cachetools import TTLCache
from cachetools.keys import hashkey
from dataclasses import dataclass
from typing import Optional


@dataclass
class RatingInfo:
    key: Optional[str] = None  # 媒体项目的唯一标识
    type: Optional[str] = None  # 媒体项目的类型（例如：电影、电视剧）
    title: Optional[str] = None  # 媒体项目的标题
    search_title: Optional[str] = None  # 用于搜索的标题
    tmdbid: Optional[int] = None  # TMDB 的唯一标识，可选


def cache_with_logging(cache, source):
    """
    创建一个装饰器，用于在函数执行时处理缓存逻辑和日志记录。
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapped_func(*args, **kwargs):
            key = hashkey(*args, **kwargs)
            if key in cache:
                logger.info(f"从缓存中获取 {source} 媒体信息: {kwargs.get('title', 'Unknown Title')}")
                return cache[key]

            result = func(*args, **kwargs)

            if result is None:
                # 如果结果为 None，说明发生了异常，根据 source 设置不同的缓存 TTL
                if source == "TMDB":
                    cache.set(key, result, ttl=600)  # 缓存 10 分钟
                else:
                    cache.set(key, result, ttl=3600)  # 缓存 1 小时
            else:
                # 结果不为 None，使用默认 TTL 缓存
                cache.set(key, result)

            return result

        return wrapped_func

    return decorator


# 创建自定义的 DynamicTTLCache 类，支持动态设置 TTL
class DynamicTTLCache(TTLCache):
    def __init__(self, maxsize, default_ttl):
        super().__init__(maxsize, default_ttl)
        self.default_ttl = default_ttl

    def set(self, key, value, ttl=None):
        if ttl is None:
            ttl = self.default_ttl
        expiration = self.timer() + ttl
        super().__setitem__(key, (value, expiration))

    def __getitem__(self, key):
        value, expire = super().__getitem__(key)
        if expire < self.timer():
            super().__delitem__(key)  # 删除过期缓存项
            raise KeyError(key)
        return value

    def __contains__(self, key):
        try:
            self.__getitem__(key)
        except KeyError:
            return False
        return True


# 创建自定义缓存对象
tmdb_media_cache = DynamicTTLCache(maxsize=10000, default_ttl=86400)
douban_media_cache = DynamicTTLCache(maxsize=10000, default_ttl=86400)
