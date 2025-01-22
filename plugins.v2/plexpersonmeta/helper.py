"""
helper.py

这个模块定义了用于存储媒体项目信息的 `RatingInfo` 数据类以及缓存、限流等装饰器
"""
import functools
import inspect
from dataclasses import dataclass
from typing import Optional

from cachetools.keys import hashkey

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

    def get_cache_key(func, args, kwargs):
        """
        获取缓存的键，通过哈希函数对函数的参数进行处理
        :param func: 被装饰的函数
        :param args: 位置参数
        :param kwargs: 关键字参数
        :return: 缓存键
        """
        # 获取方法签名
        signature = inspect.signature(func)
        resolved_kwargs = {}
        # 获取默认值并结合传递的参数（如果有）
        for param, value in signature.parameters.items():
            if param in kwargs:
                # 使用显式传递的参数
                resolved_kwargs[param] = kwargs[param]
            elif value.default is not inspect.Parameter.empty:
                # 没有传递参数时使用默认值
                resolved_kwargs[param] = value.default
        # 构造缓存键，忽略实例（self 或 cls）
        params_to_hash = args[1:] if len(args) > 1 else []
        return f"{func.__name__}_{hashkey(*params_to_hash, **resolved_kwargs)}"

    def decorator(func):

        @functools.wraps(func)
        def wrapped_func(*args, **kwargs):
            key = get_cache_key(func, args, kwargs)
            value = cache_backend.get(key=key, region=region)
            if value:
                if value != "None":
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
