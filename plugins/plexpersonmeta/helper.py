"""
helper.py

这个模块定义了用于存储媒体项目信息的 `RatingInfo` 数据类以及缓存、限流等装饰器
"""
import functools
import time
from dataclasses import dataclass
from typing import Optional, Callable, Any

from cachetools import TTLCache
from cachetools.keys import hashkey

from app.log import logger
from app.schemas import APIRateLimitException


@dataclass
class RatingInfo:
    """
    媒体项目信息的数据类
    """
    key: Optional[str] = None  # 媒体项目的唯一标识
    type: Optional[str] = None  # 媒体项目的类型（例如：电影、电视剧）
    title: Optional[str] = None  # 媒体项目的标题
    search_title: Optional[str] = None  # 用于搜索的标题
    tmdbid: Optional[int] = None  # TMDB 的唯一标识，可选


def cache_with_logging(cache, source):
    """
    装饰器，用于在函数执行时处理缓存逻辑和日志记录。
    :param cache: 缓存对象，用于存储和检索缓存数据
    :param source: 数据来源，用于日志记录（例如：PERSON 或 MEDIA）
    :return: 装饰器函数
    """

    def decorator(func):
        @functools.wraps(func)
        def wrapped_func(*args, **kwargs):
            key = hashkey(*args, **kwargs)
            if key in cache:
                if source == "PERSON":
                    logger.info(f"从缓存中获取到 {source} 人物信息")
                else:
                    logger.info(f"从缓存中获取到 {source} 媒体信息: {kwargs.get('title', 'Unknown Title')}")
                return cache[key]

            # 执行被装饰的函数
            result = func(*args, **kwargs)

            if result is None:
                # 如果结果为 None，说明触发限流或网络等异常，缓存5分钟，以免高频次调用
                cache.set(key, result, ttl=60 * 5)
            else:
                # 结果不为 None，使用默认 TTL 缓存
                cache.set(key, result)

            return result

        return wrapped_func

    return decorator


class DynamicTTLCache(TTLCache):
    """
    动态 TTL 缓存类，支持在缓存项上设置自定义的 TTL（时间到期）
    """

    def __init__(self, maxsize, default_ttl):
        """
        初始化 DynamicTTLCache 实例
        :param maxsize: 缓存的最大容量
        :param default_ttl: 默认的缓存时间（秒）
        """
        super().__init__(maxsize, default_ttl)
        self.default_ttl = default_ttl

    def set(self, key, value, ttl=None):
        """
        设置缓存项
        :param key: 缓存键
        :param value: 缓存值
        :param ttl: 缓存时间（秒），如果未指定则使用默认 TTL
        """
        if ttl is None:
            ttl = self.default_ttl
        expiration = self.timer() + ttl
        super().__setitem__(key, (value, expiration))

    def __getitem__(self, key):
        """
        获取缓存项
        :param key: 缓存键
        :return: 缓存值
        :raises KeyError: 如果缓存项已过期或不存在
        """
        value, expire = super().__getitem__(key)
        if expire < self.timer():
            super().__delitem__(key)  # 删除过期缓存项
            raise KeyError(key)
        return value

    def __contains__(self, key):
        """
        检查缓存中是否包含指定的键
        :param key: 缓存键
        :return: True 如果包含键且未过期，否则 False
        """
        try:
            self.__getitem__(key)
        except KeyError:
            return False
        return True


# 创建自定义缓存对象
tmdb_person_cache = DynamicTTLCache(maxsize=100000, default_ttl=60 * 60 * 24 * 3)  # 缓存TMDB人物信息，默认 TTL 为 3 天
tmdb_media_cache = DynamicTTLCache(maxsize=100000, default_ttl=60 * 60 * 24 * 3)  # 缓存TMDB媒体信息，默认 TTL 为 3 天
douban_media_cache = DynamicTTLCache(maxsize=100000, default_ttl=60 * 60 * 24 * 3)  # 缓存豆瓣媒体信息，默认 TTL 为 3 天


class RateLimiter:
    """
    限流器类，用于处理调用的限流逻辑。
    通过增加等待时间逐步减少调用的频率，以避免触发限流。
    """

    def __init__(self, base_wait: int = 600, backoff_factor: int = 2):
        """
        初始化 RateLimiter 实例。
        :param base_wait: 基础等待时间（秒），默认值为 600 秒（10 分钟）。
        :param backoff_factor: 等待时间的递增倍数，默认值为 2。
        """
        self.next_allowed_time = 0
        self.current_wait = base_wait
        self.base_wait = base_wait
        self.backoff_factor = backoff_factor

    def can_call(self) -> bool:
        """
        检查是否可以进行下一次调用
        :return: 如果当前时间超过下一次允许调用的时间，返回 True；否则返回 False
        """
        current_time = time.time()
        if current_time >= self.next_allowed_time:
            return True
        logger.warn(f"限流期间，跳过调用：将在 {self.next_allowed_time - current_time:.2f} 秒后允许继续调用")
        return False

    def reset(self):
        """
        重置等待时间
        当调用成功时调用此方法，重置当前等待时间为基础等待时间
        """
        if self.next_allowed_time != 0 or self.current_wait > self.base_wait:
            logger.info(f"调用成功，重置限流等待时长，并允许立即调用")
        self.next_allowed_time = 0
        self.current_wait = self.base_wait

    def trigger_limit(self):
        """
        触发限流
        当触发限流异常时调用此方法，增加下一次允许调用的时间并更新当前等待时间
        """
        current_time = time.time()
        self.next_allowed_time = current_time + self.current_wait
        logger.warn(f"触发限流：将在 {self.current_wait} 秒后允许继续调用")
        self.current_wait *= self.backoff_factor


def rate_limit_handler(base_wait: int = 600, backoff_factor: int = 2) -> Callable:
    """
    装饰器，用于处理限流逻辑
    :param base_wait: 基础等待时间（秒），默认值为 600 秒（10 分钟）
    :param backoff_factor: 等待时间的递增倍数，默认值为 2
    :return: 装饰器函数
    """
    rate_limiter = RateLimiter(base_wait, backoff_factor)

    def decorator(func: Callable) -> Callable:
        @functools.wraps(func)
        def wrapper(*args, **kwargs) -> Optional[Any]:
            if not rate_limiter.can_call():
                return None

            try:
                result = func(*args, **kwargs)
                rate_limiter.reset()  # 调用成功，重置等待时间
                return result
            except APIRateLimitException as e:
                rate_limiter.trigger_limit()
                logger.error(f"触发限流：{str(e)}")
                return None

        return wrapper

    return decorator
