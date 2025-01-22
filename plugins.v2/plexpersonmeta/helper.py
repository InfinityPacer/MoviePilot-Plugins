"""
helper.py

这个模块定义了用于存储媒体项目信息的 `RatingInfo` 数据类以及缓存、限流等装饰器
"""
import functools
from dataclasses import dataclass
from typing import Optional

from app.core.cache import cache_backend
from app.log import logger


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


def cache_with_logging(region, source):
    """
    装饰器，用于在函数执行时处理缓存逻辑和日志记录。
    :param region: 缓存区，用于存储和检索缓存数据
    :param source: 数据来源，用于日志记录（例如：PERSON 或 MEDIA）
    :return: 装饰器函数
    """

    def decorator(func):

        @functools.wraps(func)
        def wrapped_func(*args, **kwargs):
            key = cache_backend.get_cache_key(func, args, kwargs)
            exists_cache = cache_backend.exists(key=key, region=region)
            if exists_cache:
                value = cache_backend.get(key=key, region=region)
                if value is not None:
                    if source == "PERSON":
                        logger.info(f"从缓存中获取到 {source} 人物信息")
                    else:
                        logger.info(f"从缓存中获取到 {source} 媒体信息: {kwargs.get('title', 'Unknown Title')}")
                    return value
                return None

            # 执行被装饰的函数
            result = func(*args, **kwargs)

            if result is None:
                # 如果结果为 None，说明触发限流或网络等异常，缓存5分钟，以免高频次调用
                cache_backend.set(key, "None", ttl=60 * 5, region=region, maxsize=100000)
            else:
                # 结果不为 None，使用默认 TTL 缓存
                cache_backend.set(key, result, ttl=60 * 60 * 24 * 3, region=region, maxsize=100000)

            return result

        return wrapped_func

    return decorator
