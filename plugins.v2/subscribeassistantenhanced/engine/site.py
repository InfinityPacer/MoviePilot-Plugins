"""站点资源证据：把 RSS/spider 缓存候选归一为订阅可消费的 S 信号快照。"""
from __future__ import annotations

import re
import copy
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Callable, Optional

from app.log import logger
from app.schemas.event import SubscribeEpisodesRefreshEventData
from app.schemas.types import MediaType

from .signals import check_e_signal
from .types import SeasonScope
from ..shared.log import detail
from ..shared.subscribe import (
    format_subscribe,
    is_full_best_version_subscribe,
    resolve_subscribe_media_type,
)
from ..shared.task import TaskDataManager


SITE_EVIDENCE_KEY = "site_evidence"
SITE_EVIDENCE_TTL_HOURS = 24
SITE_APPLIED_MIN_HOURS = 6
SITE_APPLIED_MAX_HOURS = 24
_COMPLETE_HINT_RE = re.compile(
    r"\b(?:complete|completed|end|ended)\b|完结|全集|全\s*\d+\s*集",
    re.IGNORECASE,
)


@dataclass
class SiteEvidence:
    """当前订阅的站点证据快照，只描述证据，不直接修改订阅。"""
    kind: str
    confidence: str
    tmdbid: Optional[int] = None
    season: Optional[int] = None
    episode_group: str = ""
    type: str = ""
    site_candidate_total: int = 0
    max_episode: int = 0
    site_total: int = 0
    complete_hint: bool = False
    current_target_total: int = 0
    match_level: str = "strict"
    source: str = "mixed"
    sample_titles: list[str] = field(default_factory=list)
    scanned_at: str = ""
    expires_at: str = ""
    reason: str = ""

    @classmethod
    def no_evidence(cls, subscribe, now: datetime) -> "SiteEvidence":
        """生成无站点证据快照，保留订阅身份和 TTL。"""
        return cls(
            kind="no_evidence",
            confidence="none",
            tmdbid=_safe_int(getattr(subscribe, "tmdbid", None)),
            season=_safe_int(getattr(subscribe, "season", None)),
            episode_group=_normalize_text(getattr(subscribe, "episode_group", None)),
            type=str(getattr(subscribe, "type", "") or ""),
            current_target_total=_safe_int(getattr(subscribe, "total_episode", None)) or 0,
            scanned_at=_iso(now),
            expires_at=_iso(now + timedelta(hours=SITE_EVIDENCE_TTL_HOURS)),
            reason="未发现可用站点证据",
        )

    @classmethod
    def from_dict(cls, data: dict | None) -> Optional["SiteEvidence"]:
        """从持久化字典恢复证据快照。"""
        if not data:
            return None
        known = {field_name for field_name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in known})

    def to_dict(self) -> dict:
        """转换为可 JSON 持久化的字典。"""
        return asdict(self)

    def is_expired(self, now: Optional[datetime] = None) -> bool:
        """判断证据是否超过消费 TTL；无法解析过期时间时按过期处理。"""
        if not self.expires_at:
            return True
        now = now or datetime.now(timezone.utc)
        try:
            expires_at = datetime.fromisoformat(self.expires_at)
        except ValueError:
            return True
        if expires_at.tzinfo is None and now.tzinfo is not None:
            expires_at = expires_at.replace(tzinfo=now.tzinfo)
        return expires_at <= now


@dataclass
class SiteAppliedMarker:
    """站点扩集应用标记，用于诊断和后续停止旧证据继续向上覆盖。"""
    applied_total: int
    applied_base_total: int
    applied_at: str = ""
    applied_reason: str = ""

    @classmethod
    def now(cls, applied_total: int, applied_base_total: int, reason: str,
            now: Optional[datetime] = None) -> "SiteAppliedMarker":
        """生成当前时间的应用标记。"""
        return cls(
            applied_total=applied_total,
            applied_base_total=applied_base_total,
            applied_at=_iso(now or datetime.now(timezone.utc)),
            applied_reason=reason,
        )

    @classmethod
    def from_dict(cls, data: dict | None) -> Optional["SiteAppliedMarker"]:
        """从持久化字典恢复应用标记。"""
        if not data:
            return None
        known = {field_name for field_name in cls.__dataclass_fields__}
        return cls(**{key: value for key, value in data.items() if key in known})

    def to_dict(self) -> dict:
        """转换为可 JSON 持久化的字典。"""
        return asdict(self)


def classify_site_contexts(subscribe, contexts: list, now: datetime) -> SiteEvidence:
    """把缓存 Context 归一为当前订阅的站点证据快照。

    当前目标内的普通单集资源不能否决同身份、同季的更高集数证据；只有标题明确
    表示全集或完结时，较低完成证据才与扩集证据构成真实冲突。
    """
    if not contexts:
        return SiteEvidence.no_evidence(subscribe, now)

    target_total = _safe_int(getattr(subscribe, "total_episode", None)) or 0
    evidence_list: list[SiteEvidence] = []
    conflict_list: list[SiteEvidence] = []
    for context in contexts:
        evidence = _classify_context(subscribe, context, target_total, now)
        if evidence.kind == "site_conflict":
            conflict_list.append(evidence)
            continue
        if evidence.kind != "no_evidence":
            evidence_list.append(evidence)

    if not evidence_list:
        if conflict_list:
            return _select_site_conflict(conflict_list)
        return SiteEvidence.no_evidence(subscribe, now)

    kinds = {evidence.kind for evidence in evidence_list}
    explicit_completion = any(
        evidence.kind != "site_total_ahead" and evidence.complete_hint
        for evidence in evidence_list
    ) or any(
        evidence.match_level == "strict" and evidence.complete_hint
        for evidence in conflict_list
    )
    if "site_total_ahead" in kinds and explicit_completion:
        return _build_evidence(
            subscribe, contexts[0], now,
            kind="site_conflict",
            confidence="none",
            match_level="strict",
            reason="站点候选同时出现扩集与当前目标完成证据",
            current_target_total=target_total,
        )

    if "site_total_ahead" in kinds:
        return max(evidence_list, key=lambda item: item.site_candidate_total)
    if "site_complete_total" in kinds:
        return next(evidence for evidence in evidence_list if evidence.kind == "site_complete_total")
    if "site_complete_pack" in kinds:
        return next(evidence for evidence in evidence_list if evidence.kind == "site_complete_pack")
    return SiteEvidence.no_evidence(subscribe, now)


def _select_site_conflict(conflicts: list[SiteEvidence]) -> SiteEvidence:
    """多个诊断候选只保留最接近订阅目标的一条，避免缓存顺序影响日志价值。"""
    strict_conflicts = [item for item in conflicts if item.match_level == "strict"]
    return max(strict_conflicts or conflicts, key=lambda item: item.site_candidate_total)


class SiteEvidenceStore:
    """保存当前站点证据和站点扩集应用标记。"""
    def __init__(self, task_manager: TaskDataManager):
        self._task = task_manager

    def read_snapshot(self, subscribe) -> Optional[SiteEvidence]:
        """读取订阅当前证据快照。"""
        row = (self._task.read(SITE_EVIDENCE_KEY) or {}).get(str(getattr(subscribe, "id", ""))) or {}
        if not _row_identity_matches(row, subscribe):
            return None
        return SiteEvidence.from_dict(row.get("snapshot") or {})

    def save_snapshot(self, subscribe, evidence: SiteEvidence) -> None:
        """保存订阅当前证据快照，不影响应用标记。"""
        sid = str(getattr(subscribe, "id", ""))

        def update(data: dict) -> dict:
            row = data.get(sid) or {}
            if row and not _row_identity_matches(row, subscribe):
                row = {}
            row["identity"] = _identity(subscribe)
            row["snapshot"] = evidence.to_dict()
            data[sid] = row
            return data

        self._task.update(SITE_EVIDENCE_KEY, update)

    def read_applied(self, subscribe) -> Optional[SiteAppliedMarker]:
        """读取订阅站点扩集应用标记。"""
        sid = str(getattr(subscribe, "id", ""))
        row = (self._task.read(SITE_EVIDENCE_KEY) or {}).get(sid) or {}
        if not _row_identity_matches(row, subscribe):
            self._clear_lease_by_id(sid)
            return None
        marker = SiteAppliedMarker.from_dict(row.get("applied") or {})
        if marker and not _applied_marker_matches_subscribe(marker, subscribe):
            self.clear_applied(subscribe)
            return None
        return marker

    def mark_applied(self, subscribe, applied_total: int, applied_base_total: int, reason: str,
                     now: Optional[datetime] = None) -> None:
        """记录订阅目标已被站点证据向上扩展。"""
        sid = str(getattr(subscribe, "id", ""))

        def update(data: dict) -> dict:
            row = data.get(sid) or {}
            if row and not _row_identity_matches(row, subscribe):
                row = {}
            current = SiteAppliedMarker.from_dict(row.get("applied") or {})
            if current and _safe_int(current.applied_total) == _safe_int(applied_total):
                row["identity"] = _identity(subscribe)
                data[sid] = row
                return data
            marker = SiteAppliedMarker.now(applied_total, applied_base_total, reason, now=now)
            row["identity"] = _identity(subscribe)
            row["applied"] = marker.to_dict()
            data[sid] = row
            return data

        self._task.update(SITE_EVIDENCE_KEY, update)

    def clear_applied(self, subscribe) -> None:
        """清除订阅站点扩集应用标记，保留当前证据快照。"""
        self._clear_applied_by_id(str(getattr(subscribe, "id", "")))

    def clear_lease(self, subscribe) -> None:
        """终止订阅站点扩集租约并移除旧证据，避免状态切回后复活。"""
        self._clear_lease_by_id(str(getattr(subscribe, "id", "")))

    def _clear_applied_by_id(self, sid: str) -> None:
        """按订阅 ID 清除站点扩集应用标记。"""
        def update(data: dict) -> dict:
            row = data.get(sid) or {}
            row.pop("applied", None)
            if row:
                data[sid] = row
            return data

        self._task.update(SITE_EVIDENCE_KEY, update)

    def _clear_lease_by_id(self, sid: str) -> None:
        """按订阅 ID 同时移除应用标记与证据快照。"""
        def update(data: dict) -> dict:
            row = data.get(sid) or {}
            row.pop("applied", None)
            row.pop("snapshot", None)
            if row:
                data[sid] = row
            else:
                data.pop(sid, None)
            return data

        self._task.update(SITE_EVIDENCE_KEY, update)

    def clear_all_leases(self) -> None:
        """批量终止全部站点扩集租约及其证据，防止重新开启后复活。"""
        def update(data: dict) -> dict:
            for sid, stored in list(data.items()):
                row = stored if isinstance(stored, dict) else {}
                row.pop("applied", None)
                row.pop("snapshot", None)
                if row:
                    data[sid] = row
                else:
                    data.pop(sid, None)
            return data

        self._task.update(SITE_EVIDENCE_KEY, update)


class SiteEpisodesRefreshHandler:
    """在主程序发起集数刷新时消费当前站点证据，不直接写订阅表。"""

    def __init__(self, *, config, store: SiteEvidenceStore, subscribe_oper,
                 resolve_missing_fn: Optional[Callable] = None,
                 mediainfo_from_dict: Optional[Callable] = None,
                 now_fn: Optional[Callable[[], datetime]] = None):
        self._config = config
        self._store = store
        self._subscribe_oper = subscribe_oper
        self._resolve_missing_fn = resolve_missing_fn
        self._mediainfo_from_dict = mediainfo_from_dict
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def handle_refresh(self, data: SubscribeEpisodesRefreshEventData) -> None:
        """按订阅当前站点快照向上覆盖事件 total；跳过回落和完成写库。"""
        if not getattr(self._config, "site_total_probe_enabled", False):
            self._store.clear_all_leases()
            return
        subscribe = self._subscribe_oper.get(data.subscribe_id) if (
            self._subscribe_oper and data.subscribe_id
        ) else None
        if not _event_identity_matches(data, subscribe):
            detail(f"信号引擎(S)：{format_subscribe(subscribe)} 集数刷新事件身份不匹配，跳过站点证据消费")
            return
        now = self._now_fn()
        applied = self._store.read_applied(subscribe)
        if not _eligible_site_evidence_subscribe(subscribe):
            self._store.clear_lease(subscribe)
            return
        current_total = data.current_total_episode or 0
        live_total = _safe_int(getattr(subscribe, "total_episode", None)) or 0
        evidence = self._store.read_snapshot(subscribe)

        if applied:
            applied_total = _safe_int(applied.applied_total) or 0
            age = _applied_marker_age(applied, now)
            if current_total >= applied_total:
                self._store.clear_lease(subscribe)
                return
            if _has_high_confidence_tmdb_completion(data.mediainfo, subscribe, as_of=_as_date(now)):
                self._store.clear_lease(subscribe)
                return
            if evidence and not evidence.is_expired(now):
                site_total = evidence.site_candidate_total or 0
                if evidence.kind == "site_total_ahead" and site_total > applied_total:
                    self._store.mark_applied(
                        subscribe, site_total, current_total, evidence.reason, now=now,
                    )
                    self._apply_total(data, site_total, evidence.reason)
                    return
                if evidence.complete_hint and evidence.match_level == "strict" and 0 < site_total < applied_total:
                    self._store.clear_lease(subscribe)
                    return
            if age is None:
                self._store.clear_lease(subscribe)
                return
            if age >= timedelta(hours=SITE_APPLIED_MAX_HOURS):
                return
            if age < timedelta(hours=SITE_APPLIED_MIN_HOURS):
                self._apply_total(data, applied_total, applied.applied_reason)
                return
            if self._lease_target_satisfied(subscribe, applied_total, data.mediainfo):
                return
            self._apply_total(data, applied_total, applied.applied_reason)
            return

        if not evidence:
            return
        if evidence.is_expired(now):
            self._log_diagnostic(subscribe, evidence, "站点证据已过期")
            return

        site_total = evidence.site_candidate_total or 0
        if current_total > site_total:
            self._log_diagnostic(subscribe, evidence, "主程序本次识别到的 TMDB 当前季总集数已大于站点证据")
            return
        if live_total > site_total:
            self._log_diagnostic(subscribe, evidence, "站点证据低于订阅当前目标")
            return
        if _has_high_confidence_tmdb_completion(data.mediainfo, subscribe, as_of=_as_date(now)):
            self._log_diagnostic(subscribe, evidence, "事件携带的 TMDB 完结信号成立，停止使用站点证据向上覆盖")
            self._store.clear_lease(subscribe)
            return
        if evidence.kind not in ("site_total_ahead", "site_complete_total"):
            self._log_diagnostic(subscribe, evidence, "站点证据不是可消费集数信号")
            return
        if site_total <= current_total:
            return
        self._apply_total(data, site_total, evidence.reason)
        if site_total > live_total:
            self._store.mark_applied(
                subscribe,
                applied_total=site_total,
                applied_base_total=current_total,
                reason=evidence.reason,
                now=now,
            )
        detail(
            f"信号引擎(S)：{format_subscribe(subscribe)} 站点证据扩展主程序本次识别到的 TMDB 当前季总集数 "
            f"{current_total} -> {site_total}，原因={evidence.reason}"
        )

    @staticmethod
    def _apply_total(data: SubscribeEpisodesRefreshEventData, total_episode: int, reason: str) -> None:
        """把有效租约目标写入当前刷新事件，不直接修改订阅表。"""
        data.updated = True
        data.total_episode = total_episode
        data.source = "站点集数探测"
        data.reason = reason

    def _lease_target_satisfied(self, subscribe, applied_total: int, mediainfo) -> bool:
        """按主程序公共缺集口径判断租约目标是否已经产生下载或入库事实。"""
        if not self._resolve_missing_fn or mediainfo is None:
            return False
        try:
            if isinstance(mediainfo, dict):
                if not self._mediainfo_from_dict:
                    return False
                mediainfo = self._mediainfo_from_dict(mediainfo)
            if mediainfo is None:
                return False
            snapshot = copy.copy(subscribe)
            snapshot.total_episode = applied_total
            satisfied, _ = self._resolve_missing_fn(
                subscribe=snapshot,
                mediainfo=mediainfo,
                best_version_accept_downloaded=bool(getattr(subscribe, "best_version", False)),
            )
            return bool(satisfied)
        except Exception as err:
            logger.warning(f"信号引擎(S)：{format_subscribe(subscribe)} 租约消费事实查询失败：{err}")
            return False

    @staticmethod
    def _log_diagnostic(subscribe, evidence: SiteEvidence, message: str) -> None:
        detail(
            f"信号引擎(S)：{format_subscribe(subscribe)} {message}，"
            f"证据={evidence.kind} 站点候选总集数={evidence.site_candidate_total} "
            f"原因={evidence.reason or '无'}"
        )


class SiteEvidenceScanner:
    """周期扫描主程序只读缓存候选并保存当前订阅的站点证据快照。"""

    def __init__(self, *, config, store: SiteEvidenceStore, candidate_provider: Callable,
                 now_fn: Optional[Callable[[], datetime]] = None):
        self._config = config
        self._store = store
        self._candidate_provider = candidate_provider
        self._now_fn = now_fn or (lambda: datetime.now(timezone.utc))

    def refresh_subscribe(self, subscribe) -> Optional[SiteEvidence]:
        """刷新单个订阅的站点证据；候选来源只读，不触发站点刷新或缓存写入。"""
        if not _site_evidence_scan_enabled(self._config):
            return None
        if not _eligible_site_evidence_subscribe(subscribe):
            return None
        try:
            contexts = self._candidate_provider(subscribe, allow_title_match=True) or []
        except Exception as err:
            logger.warning(f"信号引擎(S)：{format_subscribe(subscribe)} 读取站点缓存候选失败：{err}")
            return None

        evidence = classify_site_contexts(subscribe, list(contexts), now=self._now_fn())
        self._store.save_snapshot(subscribe, evidence)
        detail(
            f"信号引擎(S)：{format_subscribe(subscribe)} 站点证据扫描完成，"
            f"结果={evidence.kind} 候选总集数={evidence.site_candidate_total} 原因={evidence.reason}"
        )
        return evidence


def _classify_context(subscribe, context, target_total: int, now: datetime) -> SiteEvidence:
    if getattr(context, "match_source", "") == "title" or getattr(context, "media_info_is_target", False):
        return _build_evidence(
            subscribe, context, now,
            kind="site_conflict",
            confidence="none",
            match_level="title",
            reason="标题兜底候选只记录诊断",
            current_target_total=target_total,
        )

    if not _identity_matches(subscribe, context):
        return _build_evidence(
            subscribe, context, now,
            kind="site_conflict",
            confidence="none",
            match_level="identity_conflict",
            reason="站点候选身份缺失或不匹配",
            current_target_total=target_total,
        )

    season_level, season_reason = _season_match_level(subscribe, context)
    if season_level != "strict":
        return _build_evidence(
            subscribe, context, now,
            kind="site_conflict",
            confidence="none",
            match_level=season_level,
            reason=season_reason,
            current_target_total=target_total,
        )

    max_episode = _max_episode(context)
    site_total = _site_total(context)
    site_candidate_total = max(max_episode, site_total)
    complete_hint = _complete_hint(context)
    if site_total and site_total < target_total:
        return _build_evidence(
            subscribe, context, now,
            kind="site_conflict",
            confidence="none",
            match_level="strict",
            reason=f"站点候选总集数 {site_total} 小于当前目标 {target_total}",
            current_target_total=target_total,
            max_episode=max_episode,
            site_total=site_total,
            complete_hint=complete_hint,
        )
    if site_candidate_total > target_total:
        return _build_evidence(
            subscribe, context, now,
            kind="site_total_ahead",
            confidence="medium",
            match_level="strict",
            reason=f"站点候选最大集数 {site_candidate_total} 大于当前目标 {target_total}",
            current_target_total=target_total,
            max_episode=max_episode,
            site_total=site_total,
            complete_hint=complete_hint,
        )
    if site_candidate_total and site_candidate_total < target_total:
        return _build_evidence(
            subscribe, context, now,
            kind="site_conflict",
            confidence="none",
            match_level="strict",
            reason=f"站点候选总集数 {site_candidate_total} 小于当前目标 {target_total}",
            current_target_total=target_total,
            max_episode=max_episode,
            site_total=site_total,
            complete_hint=complete_hint,
        )
    if site_candidate_total == target_total and site_total:
        return _build_evidence(
            subscribe, context, now,
            kind="site_complete_total",
            confidence="medium",
            match_level="strict",
            reason=f"站点候选总集数等于当前目标 {target_total}",
            current_target_total=target_total,
            max_episode=max_episode,
            site_total=site_total,
            complete_hint=complete_hint,
        )
    if complete_hint:
        return _build_evidence(
            subscribe, context, now,
            kind="site_complete_pack",
            confidence="low",
            match_level="strict",
            reason="站点标题包含完结提示但缺少可靠总集数",
            current_target_total=target_total,
            max_episode=max_episode,
            site_total=site_total,
            complete_hint=True,
        )
    return SiteEvidence.no_evidence(subscribe, now)


def _build_evidence(subscribe, context, now: datetime, *, kind: str, confidence: str,
                    match_level: str, reason: str, current_target_total: int,
                    max_episode: int = 0, site_total: int = 0,
                    complete_hint: bool = False) -> SiteEvidence:
    site_candidate_total = max(max_episode, site_total)
    return SiteEvidence(
        kind=kind,
        confidence=confidence,
        tmdbid=_safe_int(getattr(subscribe, "tmdbid", None)),
        season=_safe_int(getattr(subscribe, "season", None)),
        episode_group=_normalize_text(getattr(subscribe, "episode_group", None)),
        type=str(getattr(subscribe, "type", "") or ""),
        site_candidate_total=site_candidate_total,
        max_episode=max_episode,
        site_total=site_total,
        complete_hint=complete_hint,
        current_target_total=current_target_total,
        match_level=match_level,
        source=getattr(context, "resource_source", None) or "unknown",
        sample_titles=_sample_titles(context),
        scanned_at=_iso(now),
        expires_at=_iso(now + timedelta(hours=SITE_EVIDENCE_TTL_HOURS)),
        reason=reason,
    )


def _identity_matches(subscribe, context) -> bool:
    meta_info = getattr(context, "meta_info", None)
    media_info = getattr(context, "media_info", None)
    subscribe_tmdbid = _normalize_id(getattr(subscribe, "tmdbid", None))
    subscribe_doubanid = _normalize_id(getattr(subscribe, "doubanid", None))
    context_tmdbids = _identity_values(
        getattr(meta_info, "tmdbid", None),
        getattr(meta_info, "tmdb_id", None),
        getattr(media_info, "tmdb_id", None),
    )
    context_doubanids = _identity_values(
        getattr(meta_info, "doubanid", None),
        getattr(meta_info, "douban_id", None),
        getattr(media_info, "douban_id", None),
    )
    matched = False
    for context_tmdbid in context_tmdbids:
        if subscribe_tmdbid:
            if subscribe_tmdbid != context_tmdbid:
                return False
            matched = True
    for context_doubanid in context_doubanids:
        if subscribe_doubanid:
            if subscribe_doubanid != context_doubanid:
                return False
            matched = True
    return matched


def _season_match_level(subscribe, context) -> tuple[str, str]:
    target = _safe_int(getattr(subscribe, "season", None))
    if target is None:
        return "season_missing", "订阅缺少季信息"

    meta_info = getattr(context, "meta_info", None)
    begin_season = _safe_int(getattr(meta_info, "begin_season", None))
    end_season = _safe_int(getattr(meta_info, "end_season", None))
    if begin_season is not None and end_season is not None and begin_season != end_season:
        return "multi_season", "站点候选为多季或跨季资源"

    candidate_season = begin_season if begin_season is not None else end_season
    if candidate_season is None:
        media_info = getattr(context, "media_info", None)
        candidate_season = _safe_int(getattr(media_info, "season", None))
    if candidate_season is None:
        return "season_missing", "站点候选缺少季信息"
    if candidate_season != target:
        return "season_conflict", "站点候选季信息与订阅不一致"
    return "strict", ""


def _max_episode(context) -> int:
    meta_info = getattr(context, "meta_info", None)
    values = []
    for episode in getattr(meta_info, "episode_list", None) or []:
        parsed = _safe_int(episode)
        if parsed:
            values.append(parsed)
    for key in ("begin_episode", "end_episode"):
        parsed = _safe_int(getattr(meta_info, key, None))
        if parsed:
            values.append(parsed)
    return max(values or [0])


def _site_total(context) -> int:
    meta_info = getattr(context, "meta_info", None)
    return _safe_int(getattr(meta_info, "total_episode", None)) or 0


def _complete_hint(context) -> bool:
    meta_info = getattr(context, "meta_info", None)
    torrent_info = getattr(context, "torrent_info", None)
    text = " ".join(
        str(value or "")
        for value in (
            getattr(torrent_info, "title", None),
            getattr(torrent_info, "description", None),
            getattr(meta_info, "title", None),
            getattr(meta_info, "subtitle", None),
        )
    )
    return bool(_COMPLETE_HINT_RE.search(text))


def _sample_titles(context) -> list[str]:
    meta_info = getattr(context, "meta_info", None)
    torrent_info = getattr(context, "torrent_info", None)
    titles = []
    for value in (getattr(torrent_info, "title", None), getattr(meta_info, "title", None)):
        if value and value not in titles:
            titles.append(str(value)[:160])
    return titles[:3]


def _identity(subscribe) -> dict:
    return {
        "tmdbid": getattr(subscribe, "tmdbid", None),
        "doubanid": _normalize_id(getattr(subscribe, "doubanid", None)),
        "season": getattr(subscribe, "season", None),
        "episode_group": _normalize_text(getattr(subscribe, "episode_group", None)),
        "type": getattr(subscribe, "type", None),
    }


def _row_identity_matches(row: dict, subscribe) -> bool:
    identity = row.get("identity")
    if not isinstance(identity, dict):
        return False
    expected_episode_group = _normalize_text(getattr(subscribe, "episode_group", None))
    stored_tmdbid = _safe_int(identity.get("tmdbid"))
    current_tmdbid = _safe_int(getattr(subscribe, "tmdbid", None))
    stored_doubanid = _normalize_id(identity.get("doubanid"))
    current_doubanid = _normalize_id(getattr(subscribe, "doubanid", None))
    douban_matches = stored_doubanid == current_doubanid
    if "doubanid" not in identity:
        douban_matches = bool(stored_tmdbid and stored_tmdbid == current_tmdbid)
    return (
        stored_tmdbid == current_tmdbid
        and douban_matches
        and _safe_int(identity.get("season")) == _safe_int(getattr(subscribe, "season", None))
        and _normalize_text(identity.get("episode_group")) == expected_episode_group
        and str(identity.get("type") or "") == str(getattr(subscribe, "type", "") or "")
    )


def _applied_marker_matches_subscribe(marker: SiteAppliedMarker, subscribe) -> bool:
    """应用标记必须包含有效的正数目标，人工接管由 handler 统一终止整条租约。"""
    return bool(_safe_int(marker.applied_total))


def _applied_marker_age(marker: SiteAppliedMarker, now: datetime) -> Optional[timedelta]:
    """解析 UTC 租约年龄；非法或未来时间不视为有效租约。"""
    try:
        applied_at = datetime.fromisoformat(marker.applied_at)
    except (TypeError, ValueError):
        return None
    if applied_at.tzinfo is None:
        applied_at = applied_at.replace(tzinfo=timezone.utc)
    normalized_now = now if now.tzinfo else now.replace(tzinfo=timezone.utc)
    age = normalized_now.astimezone(timezone.utc) - applied_at.astimezone(timezone.utc)
    return age if age >= timedelta(0) else None


def _site_evidence_scan_enabled(config) -> bool:
    return bool(
        getattr(config, "site_total_probe_enabled", False)
        or getattr(config, "site_completion_evidence_enabled", False)
    )


def _eligible_site_evidence_subscribe(subscribe) -> bool:
    """站点证据只适用于 P/R 剧集普通订阅和分集洗版，手动总集数保持人工优先。"""
    if not subscribe:
        return False
    if getattr(subscribe, "state", None) not in ("P", "R"):
        return False
    if resolve_subscribe_media_type(subscribe) != MediaType.TV:
        return False
    if is_full_best_version_subscribe(subscribe):
        return False
    if bool(getattr(subscribe, "manual_total_episode", False)):
        return False
    return True


def _event_identity_matches(data: SubscribeEpisodesRefreshEventData, subscribe) -> bool:
    if data.season is not None and _safe_int(data.season) != _safe_int(getattr(subscribe, "season", None)):
        return False
    if data.tmdbid is not None and _normalize_id(data.tmdbid) != _normalize_id(getattr(subscribe, "tmdbid", None)):
        return False
    if data.doubanid is not None and _normalize_id(data.doubanid) != _normalize_id(getattr(subscribe, "doubanid", None)):
        return False
    return True


def _has_high_confidence_tmdb_completion(mediainfo, subscribe, as_of: Optional[date] = None) -> bool:
    """识别事件携带的 TMDB 高置信完结状态；缺少 scope 时仅使用剧级状态。"""
    tmdb_info = _field_value(mediainfo, "tmdb_info", None) or {}
    status = _field_value(tmdb_info, "status", None) or _field_value(mediainfo, "status", "")
    if status in ("Ended", "Canceled"):
        return True
    scope = _scope_from_mediainfo(subscribe, mediainfo)
    if not scope:
        return False
    signal = check_e_signal(_mediainfo_for_signal(mediainfo, tmdb_info), scope, as_of=as_of)
    return bool(signal and signal.completed and signal.confidence == "high")


def _scope_from_mediainfo(subscribe, mediainfo) -> Optional[SeasonScope]:
    """按事件携带的媒体信息构造当前季 scope，不额外触发 TMDB 请求。"""
    seasons = _field_value(mediainfo, "seasons", None) or {}
    season = _safe_int(getattr(subscribe, "season", None))
    if season is None:
        return None
    episodes = []
    if isinstance(seasons, dict):
        episodes = seasons.get(season) or seasons.get(str(season)) or []
    if not episodes:
        return None
    return SeasonScope(
        tmdbid=_safe_int(getattr(subscribe, "tmdbid", None)) or 0,
        season=season,
        episode_group_id=getattr(subscribe, "episode_group", None),
        episodes=list(episodes),
        total=len(episodes),
    )


def _mediainfo_for_signal(mediainfo, tmdb_info):
    """把 dict 形态的事件媒体信息收敛为 E 信号可读取的对象。"""
    if isinstance(mediainfo, dict):
        return SimpleNamespace(tmdb_info=tmdb_info or {})
    if getattr(mediainfo, "tmdb_info", None) is None:
        return SimpleNamespace(tmdb_info=tmdb_info or {})
    return mediainfo


def _as_date(value) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return None


def _field_value(data, name: str, default=None):
    if isinstance(data, dict):
        return data.get(name, default)
    return getattr(data, name, default)


def _safe_int(value) -> Optional[int]:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_id(value) -> Optional[str]:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _identity_values(*values) -> list[str]:
    normalized = []
    for value in values:
        parsed = _normalize_id(value)
        if parsed and parsed not in normalized:
            normalized.append(parsed)
    return normalized


def _normalize_text(value) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()
