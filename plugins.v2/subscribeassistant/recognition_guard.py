from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

from app.core.cache import TTLCache
from app.core.context import Context, MediaInfo
from app.core.meta import MetaBase
from app.core.metainfo import MetaInfo
from app.log import logger
from app.schemas.types import MediaType


@dataclass
class RecognitionGuardConfig:
    """
    订阅识别增强配置，控制订阅资源在自动下载前的二次校验策略。
    """
    # 工作模式：off 关闭、observe 仅记录、conservative 保守拦截、strict 严格拦截。
    mode: str = "off"
    # 目标形态：auto 跟随 TMDB 类型、animation 强制按动画处理、live_action 强制按真人实拍处理。
    target_mode: str = "auto"
    # 是否启用同名电影/剧集互串保护。
    same_name_protection: bool = True
    # 电影年份校验策略：off 关闭、loose 允许前后一年、strict 必须完全一致。
    movie_year_mode: str = "loose"
    # 剧集年份校验策略：off 关闭、loose 任意季年份、season_first 订阅季优先、season_strict 订阅季严格。
    tv_year_mode: str = "season_first"
    # 资源未标注年份时的处理：allow 放行、observe 观察、filter 拦截。
    no_year_action: str = "allow"
    # TMDB 二次识别策略：off 关闭、strict 仅严格模式、conservative_strict 保守/严格、all 观察也识别。
    tmdb_recheck_mode: str = "off"
    # 二次识别缓存上限；Redis 后端会沿用统一缓存能力，内存后端按该值限制。
    cache_maxsize: int = 100000
    # 当前订阅的自定义识别词，二次识别时与主程序订阅搜索保持一致。
    custom_words: Sequence[str] = field(default_factory=list)
    # 真人实拍关键字，任意命中即认为候选资源具有真人实拍特征。
    live_action_patterns: Sequence[str] = field(default_factory=list)
    # 动画/动漫关键字，任意命中即认为候选资源具有动画特征。
    animation_patterns: Sequence[str] = field(default_factory=list)
    # 电影关键字，用于识别同名电影误入剧集订阅的场景。
    movie_patterns: Sequence[str] = field(default_factory=list)
    # 剧集关键字，用于识别同名剧集误入电影订阅的场景。
    tv_patterns: Sequence[str] = field(default_factory=list)
    # 强制放行关键字，命中后跳过识别增强拦截。
    allow_patterns: Sequence[str] = field(default_factory=list)
    # 强制拦截关键字，命中后直接按当前模式处理。
    block_patterns: Sequence[str] = field(default_factory=list)


@dataclass
class RecognitionGuardDecision:
    """
    识别增强对单个资源的判定结果，供事件处理器决定是否移除或取消下载。
    """
    # 是否需要拦截资源；观察模式下该值始终为 False。
    blocked: bool = False
    # 是否命中了观察或拦截规则，用于日志和通知。
    observed: bool = False
    # 人类可读的判定原因。
    reason: str = ""
    # 稳定的判定编码，便于后续定位或统计。
    code: str = "allow"
    # 是否已经确认候选资源与订阅目标一致，用于跳过后续启发式校验避免误伤。
    trusted: bool = False
    # 候选资源标题，通知中用于回看具体种子。
    candidate_title: str = ""


@dataclass
class CachedRecognitionInfo:
    """
    二次识别缓存中的最小媒体信息，避免插件缓存依赖完整 MediaInfo 对象序列化细节。
    """
    # 识别得到的媒体类型。
    type: Optional[MediaType] = None
    # 识别得到的 TMDB ID。
    tmdb_id: Optional[int] = None
    # 识别得到的豆瓣 ID。
    douban_id: Optional[str] = None
    # 识别得到的标题。
    title: str = ""
    # 识别得到的年份。
    year: str = ""
    # 识别得到的风格 ID 列表。
    genre_ids: list[int] = field(default_factory=list)
    # 识别得到的二级分类。
    category: str = ""


class RecognitionGuard:
    """
    订阅资源识别增强器，负责在下载前根据配置判断候选资源是否可能串订阅。
    """
    _CACHE_REGION = "subscribeassistant_recognition_guard"
    _CACHE_TTL = 30 * 24 * 60 * 60
    _ANIMATION_GENRE_ID = 16

    def __init__(
            self,
            config: RecognitionGuardConfig,
            recognizer: Optional[Callable[[MetaBase, Optional[MediaType]], Optional[MediaInfo]]] = None,
    ):
        """
        初始化识别增强器。

        :param config: 识别增强配置
        :param recognizer: 可选的主程序媒体识别函数，用于 TMDB 二次识别
        """
        self.config = config
        self.recognizer = recognizer
        self._cache = TTLCache(
            region=self._CACHE_REGION,
            maxsize=max(1, int(config.cache_maxsize or 1)),
            ttl=self._CACHE_TTL,
        )

    def evaluate(self, context: Context) -> RecognitionGuardDecision:
        """
        判断单个候选资源是否需要被订阅识别增强拦截。
        """
        if not context or not context.torrent_info or self.config.mode == "off":
            return RecognitionGuardDecision(candidate_title=self._candidate_title(context))

        text = self._build_text(context)
        candidate_title = self._candidate_title(context)
        if self._match_patterns(self.config.allow_patterns, text):
            return RecognitionGuardDecision(candidate_title=candidate_title)

        matched_block = self._match_patterns(self.config.block_patterns, text)
        if matched_block:
            return self._make_decision(
                "manual_block",
                f"命中强制拦截关键字：{matched_block}",
                candidate_title,
            )

        media = context.media_info
        if not media:
            return RecognitionGuardDecision(candidate_title=candidate_title)

        direct_id_decision = self._evaluate_direct_ids(context, media, candidate_title)
        if direct_id_decision.observed:
            return direct_id_decision

        type_decision = self._evaluate_type_conflict(context, media, text, candidate_title)
        if type_decision.observed:
            return type_decision

        shape_decision = self._evaluate_shape_conflict(context, media, text, candidate_title)
        if shape_decision.observed:
            return shape_decision

        year_decision = self._evaluate_year(context, media, candidate_title)
        if year_decision.observed:
            return year_decision

        recheck_decision = self._evaluate_secondary_recognition(context, media, candidate_title)
        if recheck_decision.observed or recheck_decision.trusted:
            return recheck_decision

        return RecognitionGuardDecision(candidate_title=candidate_title)

    def filter_contexts(self, contexts: Sequence[Context]) -> tuple[list[Context], list[RecognitionGuardDecision]]:
        """
        对资源列表执行识别增强过滤，返回保留资源和命中判定结果。
        """
        retained_contexts = []
        decisions = []
        for context in contexts or []:
            decision = self.evaluate(context)
            if decision.observed:
                decisions.append(decision)
            if not decision.blocked:
                retained_contexts.append(context)
        return retained_contexts, decisions

    def _evaluate_direct_ids(self, context: Context, media: MediaInfo,
                             candidate_title: str) -> RecognitionGuardDecision:
        """
        使用标题识别出的显式 ID 做最高优先级校验，避免指定 ID 资源误入目标订阅。
        """
        meta = context.meta_info
        if not meta:
            return RecognitionGuardDecision(candidate_title=candidate_title)
        if getattr(meta, "tmdbid", None) and media.tmdb_id and int(meta.tmdbid) != int(media.tmdb_id):
            return self._make_decision(
                "tmdb_id_mismatch",
                f"资源显式 TMDBID {meta.tmdbid} 与订阅 TMDBID {media.tmdb_id} 不一致",
                candidate_title,
            )
        if getattr(meta, "doubanid", None) and media.douban_id and str(meta.doubanid) != str(media.douban_id):
            return self._make_decision(
                "douban_id_mismatch",
                f"资源显式豆瓣ID {meta.doubanid} 与订阅豆瓣ID {media.douban_id} 不一致",
                candidate_title,
            )
        return RecognitionGuardDecision(candidate_title=candidate_title)

    def _evaluate_type_conflict(self, context: Context, media: MediaInfo, text: str,
                                candidate_title: str) -> RecognitionGuardDecision:
        """
        校验电影/剧集类型信号，解决同名电影与同名剧集互串。
        """
        if not self.config.same_name_protection:
            return RecognitionGuardDecision(candidate_title=candidate_title)

        candidate_type = self._candidate_type(context, text)
        if media.type == MediaType.MOVIE and candidate_type == MediaType.TV:
            return self._make_decision("movie_tv_mismatch", "电影订阅命中了剧集资源信号", candidate_title)
        if media.type == MediaType.TV and candidate_type == MediaType.MOVIE:
            return self._make_decision("tv_movie_mismatch", "剧集订阅命中了电影资源信号", candidate_title)
        return RecognitionGuardDecision(candidate_title=candidate_title)

    def _evaluate_shape_conflict(self, context: Context, media: MediaInfo, text: str,
                                 candidate_title: str) -> RecognitionGuardDecision:
        """
        校验真人实拍/动画动漫信号，解决同名改编作品互串。
        """
        target_shape = self._target_shape(media)
        if target_shape == "unknown":
            return RecognitionGuardDecision(candidate_title=candidate_title)

        live_action_match = self._match_patterns(self.config.live_action_patterns, text)
        animation_match = self._match_patterns(self.config.animation_patterns, text)
        if live_action_match or animation_match:
            logger.debug(
                f"订阅识别增强目标形态校验：{self._candidate_log_text(context)}，"
                f"目标形态：{target_shape}，真人信号：{live_action_match or '-'}，"
                f"动画信号：{animation_match or '-'}"
            )
        if target_shape == "animation" and live_action_match:
            return self._make_decision(
                "animation_live_action_conflict",
                f"动画目标命中真人实拍信号：{live_action_match}",
                candidate_title,
            )
        if target_shape == "live_action" and animation_match:
            return self._make_decision(
                "live_action_animation_conflict",
                f"真人实拍目标命中动画信号：{animation_match}",
                candidate_title,
            )
        return RecognitionGuardDecision(candidate_title=candidate_title)

    def _evaluate_year(self, context: Context, media: MediaInfo, candidate_title: str) -> RecognitionGuardDecision:
        """
        根据电影或剧集配置校验候选标题中的年份。
        """
        candidate_year = self._candidate_year(context)
        if media.type == MediaType.MOVIE:
            return self._evaluate_movie_year(candidate_year, media, candidate_title)
        if media.type == MediaType.TV:
            return self._evaluate_tv_year(candidate_year, media, context, candidate_title)
        return RecognitionGuardDecision(candidate_title=candidate_title)

    def _evaluate_movie_year(self, candidate_year: Optional[str], media: MediaInfo,
                             candidate_title: str) -> RecognitionGuardDecision:
        """
        校验电影年份，宽松模式允许常见跨时区或站点录入造成的一年偏差。
        """
        if self.config.movie_year_mode == "off" or not media.year:
            return RecognitionGuardDecision(candidate_title=candidate_title)
        if not candidate_year:
            return self._handle_missing_year("movie_year_missing", "电影资源未标注年份", candidate_title)

        target_year = self._safe_int(media.year)
        resource_year = self._safe_int(candidate_year)
        if target_year is None or resource_year is None:
            return RecognitionGuardDecision(candidate_title=candidate_title)
        allowed_years = {target_year}
        if self.config.movie_year_mode == "loose":
            allowed_years.update({target_year - 1, target_year + 1})
        if resource_year not in allowed_years:
            return self._make_decision(
                "movie_year_mismatch",
                f"电影年份 {resource_year} 不在允许范围 {sorted(allowed_years)}",
                candidate_title,
            )
        return RecognitionGuardDecision(candidate_title=candidate_title)

    def _evaluate_tv_year(self, candidate_year: Optional[str], media: MediaInfo, context: Context,
                          candidate_title: str) -> RecognitionGuardDecision:
        """
        校验剧集年份，兼容站点使用首播年份或订阅季年份的差异。
        """
        if self.config.tv_year_mode == "off" or not media.year:
            return RecognitionGuardDecision(candidate_title=candidate_title)
        if not candidate_year:
            return self._handle_missing_year("tv_year_missing", "剧集资源未标注年份", candidate_title)

        allowed_years = self._allowed_tv_years(media, context)
        if not allowed_years:
            return RecognitionGuardDecision(candidate_title=candidate_title)
        resource_year = self._safe_int(candidate_year)
        if resource_year is None:
            return RecognitionGuardDecision(candidate_title=candidate_title)
        if resource_year not in allowed_years:
            return self._make_decision(
                "tv_year_mismatch",
                f"剧集年份 {resource_year} 不在允许范围 {sorted(allowed_years)}",
                candidate_title,
            )
        return RecognitionGuardDecision(candidate_title=candidate_title)

    def _evaluate_secondary_recognition(self, context: Context, media: MediaInfo,
                                        candidate_title: str) -> RecognitionGuardDecision:
        """
        在配置允许时调用主程序识别链路，借助 TMDB 缓存确认候选资源是否指向其他媒体。
        """
        if not self._should_secondary_recognize() or not self.recognizer:
            return RecognitionGuardDecision(candidate_title=candidate_title)

        recognized = self._recognize_candidate(context)
        if not recognized:
            return RecognitionGuardDecision(candidate_title=candidate_title)

        if recognized.tmdb_id and media.tmdb_id and int(recognized.tmdb_id) != int(media.tmdb_id):
            return self._make_decision(
                "secondary_tmdb_mismatch",
                f"二次识别 TMDBID {recognized.tmdb_id} 与订阅 TMDBID {media.tmdb_id} 不一致",
                candidate_title,
            )
        if recognized.douban_id and media.douban_id and str(recognized.douban_id) != str(media.douban_id):
            return self._make_decision(
                "secondary_douban_mismatch",
                f"二次识别豆瓣ID {recognized.douban_id} 与订阅豆瓣ID {media.douban_id} 不一致",
                candidate_title,
            )
        if recognized.type and media.type and recognized.type != media.type:
            return self._make_decision(
                "secondary_type_mismatch",
                f"二次识别类型 {recognized.type.value} 与订阅类型 {media.type.value} 不一致",
                candidate_title,
            )
        if self._is_same_identity(recognized, media):
            logger.debug(
                f"订阅识别增强二次识别确认同一目标：{candidate_title}，"
                f"TMDBID={recognized.tmdb_id}，豆瓣ID={recognized.douban_id}"
            )
            return RecognitionGuardDecision(
                candidate_title=candidate_title,
                code="secondary_same_identity",
                trusted=True,
            )

        target_shape = self._target_shape(media)
        if target_shape == "animation" and not self._is_animation_info(recognized):
            return self._make_decision(
                "secondary_animation_mismatch",
                "二次识别结果不具备动画特征",
                candidate_title,
            )
        if target_shape == "live_action" and self._is_animation_info(recognized):
            return self._make_decision(
                "secondary_live_action_mismatch",
                "真人实拍目标二次识别到动画资源",
                candidate_title,
            )
        return RecognitionGuardDecision(candidate_title=candidate_title)

    def _is_same_identity(self, recognized: CachedRecognitionInfo, media: MediaInfo) -> bool:
        """
        判断二次识别结果是否已经明确指向目标媒体，避免后续形态信号误伤。
        """
        if recognized.tmdb_id and media.tmdb_id and int(recognized.tmdb_id) == int(media.tmdb_id):
            return bool(recognized.type and media.type and recognized.type == media.type)
        if recognized.douban_id and media.douban_id and str(recognized.douban_id) == str(media.douban_id):
            return True
        return False

    def _handle_missing_year(self, code: str, reason: str, candidate_title: str) -> RecognitionGuardDecision:
        """
        按缺少年份策略处理站点未标注年份的资源。
        """
        if self.config.no_year_action == "allow":
            return RecognitionGuardDecision(candidate_title=candidate_title)
        if self.config.no_year_action == "observe":
            return RecognitionGuardDecision(
                observed=True,
                reason=reason,
                code=code,
                candidate_title=candidate_title,
            )
        return self._make_decision(code, reason, candidate_title)

    def _make_decision(self, code: str, reason: str, candidate_title: str) -> RecognitionGuardDecision:
        """
        根据当前工作模式将命中结果转换成观察或拦截判定。
        """
        return RecognitionGuardDecision(
            blocked=self.config.mode in {"conservative", "strict"},
            observed=True,
            reason=reason,
            code=code,
            candidate_title=candidate_title,
        )

    def _recognize_candidate(self, context: Context) -> Optional[CachedRecognitionInfo]:
        """
        识别候选资源并缓存最小结果，避免同一批订阅资源重复触发识别。
        """
        torrent_info = context.torrent_info
        if not torrent_info or not torrent_info.title:
            return None
        meta = MetaInfo(
            torrent_info.title,
            torrent_info.description,
            custom_words=list(self.config.custom_words or []),
        )
        candidate_type = self._candidate_type(context, self._build_text(context))
        if candidate_type in {MediaType.MOVIE, MediaType.TV}:
            meta.type = candidate_type

        cache_key = self._recognition_cache_key(meta=meta, mtype=candidate_type, context=context)
        cached = self._cache.get(cache_key)
        if cached is not None:
            logger.debug(f"订阅识别增强二次识别命中缓存：{self._candidate_log_text(context)}")
            return self._cached_info_from_dict(cached)

        try:
            logger.debug(f"订阅识别增强开始二次识别：{self._candidate_log_text(context)}")
            mediainfo = self.recognizer(meta, candidate_type if candidate_type != MediaType.UNKNOWN else None)
        except Exception as err:
            logger.warning(f"订阅识别增强二次识别失败：{self._candidate_log_text(context)}，错误：{err}")
            return None
        cached_info = self._cached_info_from_media(mediainfo)
        if cached_info:
            logger.debug(
                f"订阅识别增强二次识别结果：{self._candidate_log_text(context)} => "
                f"{cached_info.title} ({cached_info.year})，类型：{cached_info.type}，TMDBID：{cached_info.tmdb_id}"
            )
        else:
            logger.debug(f"订阅识别增强二次识别无结果：{self._candidate_log_text(context)}")
        self._cache.set(cache_key, self._cached_info_to_dict(cached_info))
        return cached_info

    def _recognition_cache_key(self, meta: MetaBase, mtype: Optional[MediaType],
                               context: Optional[Context] = None) -> str:
        """
        生成二次识别缓存键，按候选资源原始识别输入隔离缓存命中范围。
        """
        meta_name = getattr(meta, "name", None) or getattr(meta, "cn_name", None) or getattr(meta, "title", "")
        meta_year = getattr(meta, "year", "") or ""
        media_type = mtype.value if isinstance(mtype, MediaType) else ""
        input_hash = self._recognition_input_hash(meta=meta, mtype=mtype, context=context)
        return f"{media_type}|{meta_year}|{self._custom_words_hash()}|{input_hash}|{meta_name}"

    def _recognition_input_hash(self, meta: MetaBase, mtype: Optional[MediaType],
                                context: Optional[Context] = None) -> str:
        """
        生成二次识别输入摘要，按主程序 RSS/搜索的站点资源粒度隔离缓存。
        """
        torrent_info = context.torrent_info if context else None
        media_type = mtype.value if isinstance(mtype, MediaType) else ""
        site_key = ""
        if torrent_info:
            site_key = str(torrent_info.site or torrent_info.site_name or "")
        title = (torrent_info.title if torrent_info else getattr(meta, "title", "")) or ""
        description = (torrent_info.description if torrent_info else getattr(meta, "subtitle", "")) or ""
        raw_input = "\n".join([site_key, media_type, str(title), str(description)])
        return hashlib.sha1(raw_input.encode("utf-8")).hexdigest()[:16]

    def _custom_words_hash(self) -> str:
        """
        生成订阅自定义识别词摘要，避免不同订阅复用二次识别缓存导致串识别。
        """
        custom_words = [str(word).strip() for word in (self.config.custom_words or []) if str(word).strip()]
        if not custom_words:
            return ""
        return hashlib.sha1("\n".join(custom_words).encode("utf-8")).hexdigest()[:12]

    def _cached_info_from_media(self, media: Optional[MediaInfo]) -> Optional[CachedRecognitionInfo]:
        """
        从主程序 MediaInfo 转成插件缓存结构。
        """
        if not media:
            return None
        return CachedRecognitionInfo(
            type=media.type,
            tmdb_id=media.tmdb_id,
            douban_id=media.douban_id,
            title=media.title or "",
            year=str(media.year or ""),
            genre_ids=list(media.genre_ids or []),
            category=media.category or "",
        )

    def _cached_info_to_dict(self, cached_info: Optional[CachedRecognitionInfo]) -> Optional[dict]:
        """
        将缓存结构转成普通字典，兼容 Redis 与本地内存缓存后端。
        """
        if not cached_info:
            return None
        return {
            "type": cached_info.type.value if isinstance(cached_info.type, MediaType) else None,
            "tmdb_id": cached_info.tmdb_id,
            "douban_id": cached_info.douban_id,
            "title": cached_info.title,
            "year": cached_info.year,
            "genre_ids": cached_info.genre_ids,
            "category": cached_info.category,
        }

    def _cached_info_from_dict(self, data: Optional[dict]) -> Optional[CachedRecognitionInfo]:
        """
        从缓存字典恢复最小媒体信息。
        """
        if not data:
            return None
        media_type = None
        if data.get("type"):
            try:
                media_type = MediaType(data.get("type"))
            except ValueError:
                media_type = None
        return CachedRecognitionInfo(
            type=media_type,
            tmdb_id=data.get("tmdb_id"),
            douban_id=data.get("douban_id"),
            title=data.get("title") or "",
            year=str(data.get("year") or ""),
            genre_ids=list(data.get("genre_ids") or []),
            category=data.get("category") or "",
        )

    def _should_secondary_recognize(self) -> bool:
        """
        判断当前模式是否允许 TMDB 二次识别。
        """
        mode = self.config.tmdb_recheck_mode
        if mode == "off":
            return False
        if mode == "all":
            return self.config.mode in {"observe", "conservative", "strict"}
        if mode == "strict":
            return self.config.mode == "strict"
        if mode == "conservative_strict":
            return self.config.mode in {"conservative", "strict"}
        return False

    def _candidate_type(self, context: Context, text: str) -> Optional[MediaType]:
        """
        从站点分类、标题解析和用户关键字中提取候选资源类型信号。
        """
        torrent_info = context.torrent_info
        if torrent_info and torrent_info.category:
            try:
                return MediaType(torrent_info.category)
            except ValueError:
                pass
        if context.meta_info and context.meta_info.type in {MediaType.MOVIE, MediaType.TV}:
            return context.meta_info.type
        if self._match_patterns(self.config.tv_patterns, text):
            return MediaType.TV
        if self._match_patterns(self.config.movie_patterns, text):
            return MediaType.MOVIE
        return None

    def _target_shape(self, media: MediaInfo) -> str:
        """
        解析目标订阅的形态，只有明确动画或用户强制真人时才参与互串判断。
        """
        if self.config.target_mode in {"animation", "live_action"}:
            return self.config.target_mode
        if self._is_animation_media(media):
            return "animation"
        return "unknown"

    def _is_animation_media(self, media: MediaInfo) -> bool:
        """
        判断主程序媒体信息是否具备动画特征。
        """
        if not media:
            return False
        if self._ANIMATION_GENRE_ID in set(media.genre_ids or []):
            return True
        category = media.category or ""
        return bool(re.search(r"动漫|动画|国漫|番剧|Anime|Animation", category, re.I))

    def _is_animation_info(self, media: CachedRecognitionInfo) -> bool:
        """
        判断二次识别缓存信息是否具备动画特征。
        """
        if not media:
            return False
        if self._ANIMATION_GENRE_ID in set(media.genre_ids or []):
            return True
        return bool(re.search(r"动漫|动画|国漫|番剧|Anime|Animation", media.category or "", re.I))

    def _allowed_tv_years(self, media: MediaInfo, context: Context) -> set[int]:
        """
        计算剧集年份允许集合，兼容首播年份和分季年份两种站点标注习惯。
        """
        series_year = self._safe_int(media.year)
        season = self._target_season(context)
        season_year = self._safe_int((media.season_years or {}).get(season)) if season else None
        if self.config.tv_year_mode == "loose":
            return {year for year in {series_year, season_year, *self._season_years(media)} if year is not None}
        if self.config.tv_year_mode == "season_strict":
            return {season_year} if season_year is not None else set()
        if self.config.tv_year_mode == "season_first":
            if season_year is not None:
                return {season_year}
            return {series_year} if series_year is not None else set()
        return set()

    def _season_years(self, media: MediaInfo) -> set[int]:
        """
        返回媒体所有可解析的季年份。
        """
        return {year for year in (self._safe_int(value) for value in (media.season_years or {}).values())
                if year is not None}

    def _target_season(self, context: Context) -> Optional[int]:
        """
        从资源元数据或目标媒体中提取订阅季，年份校验优先使用该季。
        """
        if context.meta_info and context.meta_info.begin_season:
            return context.meta_info.begin_season
        if context.media_info and context.media_info.season:
            return context.media_info.season
        return None

    def _candidate_year(self, context: Context) -> Optional[str]:
        """
        从候选资源元数据中提取年份。
        """
        if context.meta_info and context.meta_info.year:
            return str(context.meta_info.year)
        return None

    def _build_text(self, context: Context) -> str:
        """
        拼接用户关键字可匹配的候选资源文本。
        """
        torrent_info = context.torrent_info if context else None
        if not torrent_info:
            return ""
        labels = " ".join(str(label) for label in (torrent_info.labels or []) if label)
        return "\n".join(part for part in [
            torrent_info.title,
            torrent_info.description,
            labels,
            torrent_info.category,
            torrent_info.site_name,
        ] if part)

    def _candidate_title(self, context: Optional[Context]) -> str:
        """
        返回候选资源标题，日志和通知统一使用该值。
        """
        if not context or not context.torrent_info:
            return ""
        return context.torrent_info.title or ""

    def _candidate_log_text(self, context: Optional[Context]) -> str:
        """
        拼装候选资源日志文本，统一展示标题与副标题方便排查命中原因。
        """
        if not context or not context.torrent_info:
            return ""
        torrent_info = context.torrent_info
        title = self._truncate_log_text(torrent_info.title or "", 120)
        desc = self._truncate_log_text(torrent_info.description or "", 120)
        if desc:
            return f"{title}｜{desc}"
        return title

    @staticmethod
    def _truncate_log_text(value: str, max_length: int = 120) -> str:
        """
        截断识别增强日志里的标题或副标题，避免二次识别 Debug 输出过长。
        """
        text = str(value or "")
        if len(text) <= max_length:
            return text
        return f"{text[:max_length - 3]}..."

    def _match_patterns(self, patterns: Sequence[str], text: str) -> Optional[str]:
        """
        使用用户配置的关键字列表匹配文本，无法解析的关键字只记录告警并跳过。
        """
        if not text:
            return None
        for pattern in patterns or []:
            if not pattern:
                continue
            try:
                if re.search(pattern, text, re.I):
                    return pattern
            except re.error as err:
                logger.warning(f"订阅识别增强关键字无效：{pattern}，错误：{err}")
        return None

    @staticmethod
    def _safe_int(value: object) -> Optional[int]:
        """
        将年份等数值安全转换为整数。
        """
        if value is None or value == "":
            return None
        try:
            return int(str(value)[:4])
        except (TypeError, ValueError):
            return None
