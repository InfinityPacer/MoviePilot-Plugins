"""识别增强目标范围与候选摘要构建。"""
import re

from app.schemas.types import MediaType

from .audit import candidate_fingerprint
from .types import CandidateResource, RecognitionTarget
from ..shared.subscribe import (
    is_full_best_version_subscribe,
    is_tv_episode_best_version_subscribe,
    resolve_subscribe_media_type,
)


def _episode_number(episode) -> int | None:
    """读取 TMDB 分集号，兼容对象与简单测试替身。"""
    value = getattr(episode, "episode_number", None)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _subscribe_range(subscribe) -> list[int]:
    """按订阅 start_episode..total_episode 构建目标窗口。"""
    try:
        start = int(subscribe.start_episode or 1)
        total = int(subscribe.total_episode or 0)
    except (TypeError, ValueError):
        return []
    return list(range(start, total + 1)) if total >= start else []


def _dedupe_text(values) -> list[str]:
    """保持输入顺序去重，避免别名重复影响审计输出。"""
    seen = set()
    result = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _is_weak_alias(text: str) -> bool:
    """短英文别名容易误识别为同名作品，默认只作为弱同一性证据。"""
    ascii_letters = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    cjk_letters = sum(1 for ch in text if "\u4e00" <= ch <= "\u9fff")
    return ascii_letters > 0 and cjk_letters == 0 and len(text.replace(" ", "")) <= 12


def _target_aliases(subscribe, mediainfo) -> tuple[list[str], dict[str, str]]:
    """收集订阅目标别名并标注强度，供后续证据抵消规则使用。"""
    strengths = {}
    words = []
    for text in [subscribe.name or ""]:
        if text:
            words.append(text)
            strengths[text] = "strong"
    for text in str(subscribe.custom_words or "").splitlines():
        if text:
            words.append(text)
            strengths[text] = "strong"
    if mediainfo:
        for text in [
            getattr(mediainfo, "title", "") or "",
            getattr(mediainfo, "original_title", "") or "",
        ]:
            if text:
                words.append(text)
                strengths.setdefault(text, "medium")
        for text in [getattr(mediainfo, "en_title", "") or "", *(getattr(mediainfo, "names", None) or [])]:
            if text:
                words.append(text)
                strength = "weak" if _is_weak_alias(text) else "medium"
                if strengths.get(text) != "strong":
                    strengths[text] = strength
    aliases = _dedupe_text(words)
    return aliases, {alias: strengths.get(alias, "weak") for alias in aliases}


def _target_shape(mediainfo) -> str:
    """判断订阅目标形态；首版只在有明确动画信号时返回 animation。"""
    if not mediainfo:
        return "unknown"
    category = str(getattr(mediainfo, "category", "") or "")
    genres = getattr(mediainfo, "genres", None) or []
    genre_names = [str(item.get("name", "") if isinstance(item, dict) else item) for item in genres]
    text = " ".join([category, *genre_names])
    if any(token in text for token in ("动画", "动漫", "番剧", "国漫", "Animation")):
        return "animation"
    return "unknown"


def _media_type_value(value) -> str:
    """统一媒体类型口径：MediaType 枚举与字符串都输出中文业务值。"""
    if isinstance(value, MediaType):
        return value.value
    enum_value = getattr(value, "value", value)
    return str(enum_value or "")


def build_target(subscribe, mediainfo=None, tmdb_episodes_fn=None) -> RecognitionTarget:
    """构建当前订阅目标与本次应覆盖的集数范围。"""
    media_type = resolve_subscribe_media_type(subscribe)
    source = "movie" if media_type == MediaType.MOVIE else "subscribe_range"
    episodes = [] if media_type == MediaType.MOVIE else _subscribe_range(subscribe)
    confidence = "high" if media_type == MediaType.MOVIE or episodes else "unknown"
    if media_type == MediaType.TV:
        if is_full_best_version_subscribe(subscribe):
            episodes = []
            source = "scope_unavailable"
            confidence = "unknown"
            if tmdb_episodes_fn:
                try:
                    scope_eps = tmdb_episodes_fn(
                        tmdbid=subscribe.tmdbid,
                        season=subscribe.season,
                        episode_group=subscribe.episode_group,
                    )
                except Exception:
                    scope_eps = []
                parsed = [num for num in (_episode_number(ep) for ep in scope_eps or []) if num is not None]
                if parsed:
                    episodes = parsed
                    source = "episode_group" if subscribe.episode_group else "full_best_version"
                    confidence = "high"
        elif is_tv_episode_best_version_subscribe(subscribe):
            source = "episode_best_version"
    aliases, alias_strengths = _target_aliases(subscribe, mediainfo)
    return RecognitionTarget(
        subscribe_id=subscribe.id,
        name=subscribe.name or "",
        year=str(subscribe.year or ""),
        media_type=_media_type_value(media_type),
        season=subscribe.season,
        episode_group=subscribe.episode_group,
        tmdb_id=subscribe.tmdbid,
        douban_id=subscribe.doubanid,
        custom_words=[line.strip() for line in str(subscribe.custom_words or "").splitlines()
                      if line.strip()],
        aliases=aliases,
        alias_strengths=alias_strengths,
        shape=_target_shape(mediainfo),
        target_episodes=episodes,
        range_source=source,
        range_confidence=confidence,
    )


def _episodes_from_text(text: str) -> list[int]:
    """从标题/副标题解析候选集范围，供 ResourceSelection 阶段使用。"""
    range_match = re.search(r"E(\d{1,4})\s*-\s*E?(\d{1,4})", text, re.I)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        return list(range(start, end + 1)) if end >= start else []
    single_match = re.search(r"S\d{1,3}E(\d{1,4})", text, re.I)
    if single_match:
        return [int(single_match.group(1))]
    range_match = re.search(r"第\s*(\d+)\s*-\s*(\d+)\s*集", text)
    if range_match:
        start, end = int(range_match.group(1)), int(range_match.group(2))
        return list(range(start, end + 1)) if end >= start else []
    full_match = re.search(r"全\s*(\d+)\s*集", text)
    if full_match:
        total = int(full_match.group(1))
        return list(range(1, total + 1)) if total > 0 else []
    single_match = re.search(r"第\s*(\d+)\s*集", text)
    if single_match:
        return [int(single_match.group(1))]
    return []


def _episodes_from_meta(meta) -> list[int]:
    """从主程序 MetaInfo 读取候选集范围。"""
    if not meta:
        return []
    episode_list = list(getattr(meta, "episode_list", None) or [])
    if episode_list:
        return [int(ep) for ep in episode_list if str(ep).isdigit()]
    begin = getattr(meta, "begin_episode", None)
    end = getattr(meta, "end_episode", None)
    try:
        begin = int(begin) if begin is not None else None
        end = int(end) if end is not None else begin
    except (TypeError, ValueError):
        return []
    if begin is not None and end is not None and end >= begin:
        return list(range(begin, end + 1))
    return []


def _season_kind(season) -> str:
    """S00 是合法特别季，不能与未知季号混淆。"""
    return "special" if season == 0 else "main"


def _explicit_special_season(text: str) -> bool:
    """识别标题中的特别篇 / SP 标记；仅在缺显式季号时用于避免退化成主季。"""
    return bool(re.search(r"\bS00E\d{1,4}\b|\bSP\d{1,4}\b|特别篇|番外", text, re.I))


def _list_attr(obj, *names) -> list[str]:
    """读取候选识别结果里的语种/地区列表，缺失时返回空列表。"""
    for name in names:
        values = getattr(obj, name, None)
        if values:
            return [str(value) for value in values if value]
    return []


def candidate_from_context(context, order: int = 0) -> CandidateResource:
    """从主程序 ResourceSelection context 构建候选摘要。"""
    torrent = getattr(context, "torrent_info", None)
    meta = getattr(context, "meta_info", None)
    title = getattr(torrent, "title", "") or ""
    desc = getattr(torrent, "description", "") or ""
    text = f"{title} {desc}"
    episodes = _episodes_from_meta(meta)
    if not episodes:
        episodes = list(getattr(torrent, "episode_list", None) or [])
    if not episodes:
        episodes = _episodes_from_text(text)
    range_source = "unknown"
    if _episodes_from_meta(meta):
        range_source = "meta_info"
    elif getattr(torrent, "episode_list", None):
        range_source = "torrent_info"
    elif episodes:
        range_source = "title"
    season = getattr(meta, "begin_season", None)
    if season is None and _explicit_special_season(text):
        season = 0
    media_info = getattr(context, "media_info", None)
    return CandidateResource(
        fingerprint=candidate_fingerprint(torrent),
        title=title,
        description=desc,
        site=str(getattr(torrent, "site_name", None) or getattr(torrent, "site", "") or ""),
        category=str(getattr(torrent, "category", "") or ""),
        order=order,
        year=getattr(meta, "year", None),
        media_type=_media_type_value(getattr(meta, "type", "")),
        season=season,
        episode_group=getattr(meta, "episode_group", None),
        season_kind=_season_kind(season),
        episodes=[int(ep) for ep in episodes if str(ep).isdigit()],
        total_episode=getattr(meta, "total_episode", None),
        range_source=range_source,
        languages=_list_attr(media_info, "languages", "spoken_languages"),
        origin_countries=_list_attr(media_info, "origin_country", "production_countries"),
        explicit_tmdb_id=getattr(meta, "tmdbid", None),
        explicit_douban_id=getattr(meta, "doubanid", None),
        recognized_tmdb_id=getattr(media_info, "tmdb_id", None),
        recognized_douban_id=getattr(media_info, "douban_id", None),
        candidate_recognized=bool(getattr(context, "candidate_recognized", False)),
        match_source=str(getattr(context, "match_source", "unknown") or "unknown"),
        media_info_is_target=bool(getattr(context, "media_info_is_target", False)),
    )
