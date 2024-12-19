import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Any

from app.chain.douban import DoubanChain
from app.log import logger
from app.schemas import MediaType


# 计时装饰器
def timing(func):
    def wrapper(*args, **kwargs):
        start_time = time.time()
        result = func(*args, **kwargs)
        end_time = time.time()
        logger.info(f"{func.__name__} 耗时: {end_time - start_time:.2f} 秒")
        return result

    return wrapper


# 具体的接口方法
@timing
def movie_showing(page: int = 1, count: int = 30) -> Any:
    movies = DoubanChain().movie_showing(page=page, count=count)
    logger.info(f"movie_showing: {movies}")
    if movies:
        return [media.to_dict() for media in movies]
    return []


@timing
def douban_movies(sort: str = "R", tags: str = "", page: int = 1, count: int = 30) -> Any:
    movies = DoubanChain().douban_discover(mtype=MediaType.MOVIE,
                                           sort=sort, tags=tags, page=page, count=count)
    logger.info(f"douban_movies: {movies}")
    if movies:
        return [media.to_dict() for media in movies]
    return []


@timing
def douban_tvs(sort: str = "R", tags: str = "", page: int = 1, count: int = 30) -> Any:
    tvs = DoubanChain().douban_discover(mtype=MediaType.TV,
                                        sort=sort, tags=tags, page=page, count=count)
    logger.info(f"douban_tvs: {tvs}")
    if tvs:
        return [media.to_dict() for media in tvs]
    return []


@timing
def movie_top250(page: int = 1, count: int = 30) -> Any:
    movies = DoubanChain().movie_top250(page=page, count=count)
    logger.info(f"movie_top250: {movies}")
    if movies:
        return [media.to_dict() for media in movies]
    return []


@timing
def tv_weekly_chinese(page: int = 1, count: int = 30) -> Any:
    tvs = DoubanChain().tv_weekly_chinese(page=page, count=count)
    logger.info(f"tv_weekly_chinese: {tvs}")
    if tvs:
        return [media.to_dict() for media in tvs]
    return []


@timing
def tv_weekly_global(page: int = 1, count: int = 30) -> Any:
    tvs = DoubanChain().tv_weekly_global(page=page, count=count)
    logger.info(f"tv_weekly_global: {tvs}")
    if tvs:
        return [media.to_dict() for media in tvs]
    return []


@timing
def tv_animation(page: int = 1, count: int = 30) -> Any:
    tvs = DoubanChain().tv_animation(page=page, count=count)
    logger.info(f"tv_animation: {tvs}")
    if tvs:
        return [media.to_dict() for media in tvs]
    return []


@timing
def movie_hot(page: int = 1, count: int = 30) -> Any:
    movies = DoubanChain().movie_hot(page=page, count=count)
    logger.info(f"movie_hot: {movies}")
    if movies:
        return [media.to_dict() for media in movies]
    return []


@timing
def tv_hot(page: int = 1, count: int = 30) -> Any:
    tvs = DoubanChain().tv_hot(page=page, count=count)
    logger.info(f"tv_hot: {tvs}")
    if tvs:
        return [media.to_dict() for media in tvs]
    return []


# 批量调用方法，使用多线程并发执行
def batch_call_methods(methods: List[Any], *args, **kwargs):
    with ThreadPoolExecutor() as executor:
        # 提交任务
        future_to_method = {executor.submit(method, *args, **kwargs): method for method in methods}

        for future in as_completed(future_to_method):
            method = future_to_method[future]
            try:
                result = future.result()  # 获取方法执行结果
                logger.info(f"{method.__name__} 执行成功")
            except Exception as exc:
                logger.info(f"{method.__name__} 执行出错: {exc}")


# 使用多线程批量调用
def run_batch():
    methods = [
        movie_showing,
        douban_movies,
        douban_tvs,
        movie_top250,
        tv_weekly_chinese,
        tv_weekly_global,
        tv_animation,
        movie_hot,
        tv_hot
    ]
    # 在此处传递通用参数
    batch_call_methods(methods, page=1, count=30)
