"""识别增强候选准入判定器。"""
import re
import time
from collections import Counter
from dataclasses import fields
from hashlib import sha1
from types import SimpleNamespace

from .audit import redact_sensitive_text, sanitize_candidate_summary
from .keywords import load_keyword_groups, match_first
from .scope import build_target, candidate_from_context
from .types import (
    ACTION_ALLOW,
    ACTION_BLOCK,
    ACTION_FAIL_OPEN,
    ACTION_OBSERVE,
    ACTION_SOFT_BLOCK,
    BatchDecision,
    CandidateResource,
    Decision,
    Evidence,
    RecognitionRuntime,
    RecognitionSettings,
    RecognitionTarget,
)

_HARD_BLOCK = "hard_block"
_SOFT_BLOCK = "soft_block"
_OBSERVE = "observe"
_ALLOW = "allow"
_TRUSTED_MATCH_SOURCES = {"tmdbid", "doubanid"}


class RecognitionGuard:
    """订阅候选资源识别增强准入器。"""

    def __init__(self, settings: RecognitionSettings, runtime: RecognitionRuntime | None = None):
        self.settings = settings or RecognitionSettings()
        self.runtime = runtime or RecognitionRuntime()
        self.keyword_groups = load_keyword_groups(self.settings.keyword_config)
        self.last_batch: BatchDecision | None = None
        self.last_audit_summary = ""
        self.last_target: RecognitionTarget | None = None
        self.last_notification = None
        self._notification_cache: dict[tuple, float] = {}
        self._secondary_cache: dict[str, tuple[int | None, str | None]] = {}

    def evaluate(self, target: RecognitionTarget, candidate: CandidateResource,
                 secondary_failed: bool = False) -> Decision:
        """评估单个候选资源，输出原始动作与最终动作。"""
        if self.settings.mode == "off":
            return Decision(candidate=candidate)

        decision = self._decide_enabled(target, candidate, secondary_failed=secondary_failed)
        if self.settings.mode == "audit":
            decision.would_action = decision.final_action
            decision.final_action = ACTION_OBSERVE if decision.would_action != ACTION_ALLOW else ACTION_ALLOW
        return decision

    def evaluate_dicts(self, target_dict, candidate_dict, secondary_failed: bool = False) -> Decision:
        """从 dict 构建目标和候选摘要，便于测试和样本回放。"""
        target = self._target_from_dict(target_dict)
        candidate = self._candidate_from_dict(candidate_dict)
        return self.evaluate(target, candidate, secondary_failed=secondary_failed)

    def filter(self, contexts, *, subscribe, event_data=None, selection_original_count=None, stage_counts=None):
        """过滤 ResourceSelection 候选上下文，返回保留下来的原始 context 列表。"""
        mediainfo = None
        if self.runtime.target_mediainfo_resolver:
            mediainfo = self.runtime.target_mediainfo_resolver(subscribe)
        target = build_target(
            subscribe,
            mediainfo=mediainfo,
            tmdb_episodes_fn=self.runtime.tmdb_episodes_fn,
        )
        self.last_target = target
        raw_contexts = list(contexts or [])
        candidates = [
            self._candidate_with_secondary(context, candidate_from_context(context, order=index))
            for index, context in enumerate(raw_contexts)
        ]
        batch = self.filter_candidate_dicts(
            target,
            candidates,
            raw_contexts,
            selection_original_count=selection_original_count,
            stage_counts=stage_counts,
        )
        return batch.retained

    def filter_candidate_dicts(self, target_dict, candidate_dicts, contexts, *,
                               selection_original_count=None, stage_counts=None) -> BatchDecision:
        """批量评估候选并应用空结果保护。"""
        target = target_dict if isinstance(target_dict, RecognitionTarget) else self._target_from_dict(target_dict)
        self.last_target = target
        candidates = [
            item if isinstance(item, CandidateResource) else self._candidate_from_dict(item)
            for item in list(candidate_dicts or [])
        ]
        context_items = list(contexts or [])
        if self.settings.mode == "off":
            decisions = [Decision(candidate=candidate) for candidate in candidates]
            retained = context_items[:len(candidates)]
            output_count = len(retained)
            batch = self._make_batch(
                decisions,
                retained,
                len(candidates),
                selection_original_count=selection_original_count,
                stage_counts=self._with_recognition_stage(stage_counts, len(candidates), output_count),
            )
            self.last_batch = batch
            self.last_audit_summary = batch.audit_summary
            return batch

        decisions = [self.evaluate(target, candidate) for candidate in candidates]
        retained = [
            context
            for context, decision in zip(context_items, decisions)
            if decision.final_action not in {ACTION_BLOCK, ACTION_SOFT_BLOCK}
        ]
        fallback_applied = False
        if self.settings.mode != "strict" and not retained and decisions:
            recovered = []
            for context, decision in zip(context_items, decisions):
                if decision.final_action == ACTION_SOFT_BLOCK:
                    decision.final_action = ACTION_OBSERVE
                    recovered.append(context)
            if recovered:
                retained = recovered
                fallback_applied = True
        batch = self._make_batch(
            decisions,
            retained,
            len(candidates),
            selection_original_count=selection_original_count,
            stage_counts=self._with_recognition_stage(stage_counts, len(candidates), len(retained)),
            fallback_applied=fallback_applied,
        )
        self.last_batch = batch
        self.last_audit_summary = batch.audit_summary
        return batch

    def finalize_batch(self, final_count, stage_counts=None) -> BatchDecision | None:
        """下游过滤完成后刷新最终计数和审计摘要。"""
        if not self.last_batch:
            return None
        self.last_batch.final_count = int(final_count or 0)
        if stage_counts is not None:
            self.last_batch.stage_counts = list(stage_counts)
            if not any(stage.get("stage") == "recognition" for stage in self.last_batch.stage_counts):
                self.last_batch.stage_counts.insert(
                    1,
                    {
                        "stage": "recognition",
                        "input": self.last_batch.recognition_input_count,
                        "output": self.last_batch.recognition_output_count,
                    },
                )
        self.last_batch.audit_summary = self._audit_summary(self.last_batch)
        self.last_batch.notification_summary = self._notification_summary(self.last_batch)
        self.last_audit_summary = self.last_batch.audit_summary
        self._log_audit()
        return self.last_batch

    def notification_payload(self, subscribe):
        """返回识别增强通知负载；通知限频不改变过滤结果或审计摘要。"""
        if not self.last_batch:
            return None
        decisions = [
            decision for decision in self.last_batch.decisions
            if decision.final_action in {ACTION_BLOCK, ACTION_SOFT_BLOCK}
        ]
        if not decisions:
            return None
        first = decisions[0]
        subscribe_id = subscribe.id
        key = (subscribe_id, first.final_action, first.code, first.reason)
        now = time.time()
        if self._notification_cache.get(key, 0) > now:
            return None
        self._notification_cache[key] = now + max(1, int(self.settings.notify_interval or 1))

        counts = Counter(decision.final_action for decision in decisions)
        title = f"识别增强：{subscribe.name or '订阅'} 候选风险"
        lines = [f"拦截 {counts.get(ACTION_BLOCK, 0)} 条，软拦截 {counts.get(ACTION_SOFT_BLOCK, 0)} 条"]
        for decision in decisions[:10]:
            candidate = getattr(decision, "candidate", None) or CandidateResource()
            summary = sanitize_candidate_summary(self._torrent_like(candidate), max_length=120)
            lines.append(f"- {decision.code}：{self._safe_reason(decision.reason)}；{summary}")
        self.last_notification = (title, "\n".join(lines))
        return self.last_notification

    def _decide_enabled(self, target: RecognitionTarget, candidate: CandidateResource,
                        secondary_failed: bool = False) -> Decision:
        text = self._candidate_text(candidate)
        allow_match = match_first(self.keyword_groups.allow, text)
        hard_block_match = match_first(self.keyword_groups.hard_block, text)
        block_match = match_first(self.keyword_groups.block, text)
        live_action_match = self._live_action_match(text)
        trusted_identity = self._trusted_same_identity(target, candidate)

        if hard_block_match:
            return self._decision(
                ACTION_BLOCK,
                "user_hard_block",
                "命中 hard_block 关键字",
                candidate,
                risk=_HARD_BLOCK,
            )
        id_mismatch = self._id_mismatch(target, candidate)
        if id_mismatch:
            code, reason = id_mismatch
            if allow_match:
                reason = f"{reason}，allow 关键字仅作为抵消证据"
            return self._decision(ACTION_BLOCK, code, reason, candidate, risk=_HARD_BLOCK)

        hard_range_decision, soft_range_decision = self._range_decisions(target, candidate)
        if hard_range_decision:
            action, code, reason = hard_range_decision
            return self._risk_or_allow(action, code, reason, candidate, allow_match)

        shape_decision = self._shape_decision(
            target,
            candidate,
            live_action_match,
            secondary_failed=secondary_failed,
        )
        if shape_decision:
            action, code, reason = shape_decision
            return self._risk_or_allow(action, code, reason, candidate, allow_match)

        hard_type_decision, soft_type_decision = self._type_decisions(target, candidate, trusted_identity)
        if hard_type_decision:
            action, code, reason = hard_type_decision
            return self._risk_or_allow(action, code, reason, candidate, allow_match)

        if trusted_identity:
            return self._decision(ACTION_ALLOW, "candidate_same_identity", "候选识别身份与订阅目标一致", candidate)

        if soft_range_decision:
            action, code, reason = soft_range_decision
            return self._risk_or_allow(action, code, reason, candidate, allow_match)

        if soft_type_decision:
            action, code, reason = soft_type_decision
            return self._risk_or_allow(action, code, reason, candidate, allow_match)

        if block_match:
            action = self._mode_action(loose=ACTION_OBSERVE, balanced=ACTION_SOFT_BLOCK, strict=ACTION_BLOCK)
            return self._risk_or_allow(action, "user_block", "命中 block 关键字", candidate, allow_match)

        secondary_decision = self._secondary_decision(target, candidate, secondary_failed=secondary_failed)
        if secondary_decision:
            action, code, reason = secondary_decision
            return self._risk_or_allow(action, code, reason, candidate, allow_match)

        if candidate.year is None:
            action = self._missing_year_action()
            return self._decision(action, "missing_year", "候选缺少年份，按当前模式记录", candidate,
                                  risk=self._risk_for_action(action))

        if allow_match:
            return self._allow_decision(candidate, allow_match)
        return self._decision(ACTION_ALLOW, "allow", "未命中风险证据", candidate)

    def _range_decisions(self, target: RecognitionTarget, candidate: CandidateResource):
        if target.range_confidence == "unknown" and not target.target_episodes:
            return None, (ACTION_FAIL_OPEN, "target_range_unknown", "目标范围不可用，范围 veto fail-open")
        if target.range_confidence != "high" or not target.target_episodes:
            return None, None
        if self._known_season_conflict(target, candidate):
            return (ACTION_BLOCK, "target_range_not_covered", "候选季与订阅目标季不一致"), None
        if not candidate.episodes:
            return None, None
        target_set = set(target.target_episodes)
        candidate_set = set(candidate.episodes)
        if target.season == 0 and candidate.season_kind == "special" and candidate_set & target_set:
            return None, None
        if target_set.isdisjoint(candidate_set):
            return (ACTION_BLOCK, "target_range_not_covered", "候选集数范围与订阅目标完全不相交"), None
        if len(candidate_set) >= max(len(target_set) * 3, len(target_set) + 24) and target_set.issubset(candidate_set):
            return None, (ACTION_SOFT_BLOCK, "target_range_oversized", "候选全集范围明显大于本次目标窗口")
        return None, None

    def _shape_decision(self, target: RecognitionTarget, candidate: CandidateResource, live_action_match: str | None,
                        secondary_failed: bool = False):
        if target.shape != "animation" or not live_action_match:
            return None
        return ACTION_BLOCK, "animation_live_action_conflict", f"动画目标命中真人实拍信号：{live_action_match}"

    def _type_decisions(self, target: RecognitionTarget, candidate: CandidateResource, trusted_identity: bool):
        text = self._candidate_text(candidate)
        episode_signal = bool(candidate.episodes or re.search(r"\bS\d{1,3}(?:E\d{1,4})?\b|第\s*\d+\s*集", text, re.I))
        movie_match = match_first(self.keyword_groups.movie, text) or match_first(["电影版", "剧场版", "劇場版"], text)
        if target.media_type == "电视剧" and movie_match and not episode_signal:
            return (ACTION_BLOCK, "series_movie_conflict", f"剧集目标命中电影版资源信号：{movie_match}"), None
        if target.media_type != "电影" or trusted_identity:
            return None, None
        if episode_signal:
            return (ACTION_BLOCK, "movie_series_conflict", "电影目标命中剧集资源信号"), None
        return None, None

    def _secondary_decision(self, target: RecognitionTarget, candidate: CandidateResource, secondary_failed: bool = False):
        if secondary_failed or candidate.secondary_status == "failed":
            reason = "二次识别失败，按 fail-open 放行"
            if candidate.secondary_failure:
                reason = f"{reason}：{candidate.secondary_failure}"
            return ACTION_FAIL_OPEN, "secondary_recognition_fail_open", reason
        if candidate.secondary_status == "empty":
            return ACTION_FAIL_OPEN, "secondary_recognition_fail_open", "二次识别无结果，按 fail-open 放行"
        secondary_tmdb_id = candidate.secondary_tmdb_id
        secondary_douban_id = candidate.secondary_douban_id
        mismatch = (
            target.tmdb_id and secondary_tmdb_id and int(target.tmdb_id) != int(secondary_tmdb_id)
        ) or (
            target.douban_id and secondary_douban_id and str(target.douban_id) != str(secondary_douban_id)
        )
        if not mismatch:
            return None
        if self._has_strong_alias(target, candidate):
            return ACTION_OBSERVE, "secondary_identity_conflict_with_alias", "二次识别不一致但候选含目标中文别名"
        action = self._mode_action(loose=ACTION_OBSERVE, balanced=ACTION_BLOCK, strict=ACTION_BLOCK)
        return action, "secondary_identity_conflict", "二次识别结果与订阅目标不一致"

    def _id_mismatch(self, target: RecognitionTarget, candidate: CandidateResource):
        if target.tmdb_id and candidate.explicit_tmdb_id and int(target.tmdb_id) != int(candidate.explicit_tmdb_id):
            return "tmdb_id_mismatch", (
                f"候选显式 TMDB ID {candidate.explicit_tmdb_id} 与订阅目标 {target.tmdb_id} 不一致"
            )
        if target.douban_id and candidate.explicit_douban_id and str(target.douban_id) != str(candidate.explicit_douban_id):
            return "douban_id_mismatch", (
                f"候选显式豆瓣 ID {candidate.explicit_douban_id} 与订阅目标 {target.douban_id} 不一致"
            )
        return None

    def _trusted_same_identity(self, target: RecognitionTarget, candidate: CandidateResource) -> bool:
        if not candidate.candidate_recognized or candidate.media_info_is_target:
            return False
        if candidate.match_source not in _TRUSTED_MATCH_SOURCES:
            return False
        if target.tmdb_id and candidate.explicit_tmdb_id and int(target.tmdb_id) == int(candidate.explicit_tmdb_id):
            return True
        if target.tmdb_id and candidate.recognized_tmdb_id and int(target.tmdb_id) == int(candidate.recognized_tmdb_id):
            return True
        if target.douban_id and candidate.explicit_douban_id and str(target.douban_id) == str(candidate.explicit_douban_id):
            return True
        return bool(target.douban_id and candidate.recognized_douban_id
                    and str(target.douban_id) == str(candidate.recognized_douban_id))

    def _has_strong_alias(self, target: RecognitionTarget, candidate: CandidateResource) -> bool:
        text = self._candidate_text(candidate)
        aliases = target.aliases or [target.name]
        for alias in aliases:
            if not alias or alias not in text:
                continue
            strength = target.alias_strengths.get(alias)
            if strength == "weak":
                continue
            if any("\u4e00" <= char <= "\u9fff" for char in alias):
                return True
        return False

    def _mode_action(self, *, loose: str, balanced: str, strict: str) -> str:
        if self.settings.mode == "loose":
            return loose
        if self.settings.mode == "strict":
            return strict
        return balanced

    def _missing_year_action(self) -> str:
        return self._mode_action(loose=ACTION_OBSERVE, balanced=ACTION_OBSERVE, strict=ACTION_BLOCK)

    def _risk_or_allow(self, action: str, code: str, reason: str, candidate: CandidateResource,
                       allow_match: str | None) -> Decision:
        if allow_match and action != ACTION_BLOCK:
            decision = self._allow_decision(candidate, allow_match)
            decision.evidence.append(Evidence(group="recognition", code=code, level=self._risk_for_action(action),
                                              message=reason))
            return decision
        return self._decision(action, code, reason, candidate, risk=self._risk_for_action(action))

    def _allow_decision(self, candidate: CandidateResource, allow_match: str) -> Decision:
        decision = self._decision(
            ACTION_ALLOW,
            "user_allow",
            "命中 allow 关键字",
            candidate,
            risk=_ALLOW,
        )
        decision.counters.append(Evidence(group="keyword", code="user_allow", level=_ALLOW,
                                          message="allow 关键字"))
        return decision

    def _decision(self, action: str, code: str, reason: str, candidate: CandidateResource,
                  risk: str = "none") -> Decision:
        evidence = []
        if code != "allow":
            evidence.append(Evidence(group="recognition", code=code, level=risk, message=reason))
        return Decision(
            action=action,
            final_action=action,
            code=code,
            reason=reason,
            risk=risk,
            would_action=action,
            candidate=candidate,
            evidence=evidence,
        )

    def _make_batch(self, decisions: list[Decision], retained: list, input_count: int, *,
                    selection_original_count=None, stage_counts=None, fallback_applied=False) -> BatchDecision:
        original_action_counts = Counter(decision.action for decision in decisions)
        final_action_counts = Counter(decision.final_action for decision in decisions)
        output_count = len(retained)
        batch = BatchDecision(
            input_count=input_count,
            output_count=output_count,
            selection_original_count=selection_original_count if selection_original_count is not None else input_count,
            recognition_input_count=input_count,
            recognition_evaluated_count=len(decisions),
            recognition_output_count=output_count,
            final_count=output_count,
            decisions=decisions,
            retained=retained,
            stage_counts=list(stage_counts or []),
            fallback_applied=fallback_applied,
            action_counts=dict(final_action_counts),
            original_action_counts=dict(original_action_counts),
            final_action_counts=dict(final_action_counts),
        )
        batch.audit_summary = self._audit_summary(batch)
        batch.notification_summary = self._notification_summary(batch)
        return batch

    @staticmethod
    def _with_recognition_stage(stage_counts, input_count: int, output_count: int) -> list[dict]:
        stages = list(stage_counts or [])
        stages.append({"stage": "recognition", "input": input_count, "output": output_count})
        return stages

    def _candidate_with_secondary(self, context, candidate: CandidateResource) -> CandidateResource:
        if not self._should_run_secondary():
            return candidate
        meta = getattr(context, "meta_info", None)
        if not meta or not self.runtime.secondary_recognizer:
            return candidate
        cache_key = self._secondary_cache_key(candidate)
        cached = self._secondary_cache.get(cache_key)
        if cached is not None:
            candidate.secondary_tmdb_id, candidate.secondary_douban_id = cached
            return candidate
        try:
            media_info = self.runtime.secondary_recognizer(meta)
        except Exception as err:
            candidate.secondary_status = "failed"
            candidate.secondary_failure = redact_sensitive_text(err)
            return candidate
        if not media_info:
            candidate.secondary_status = "empty"
            self._remember_secondary(cache_key, (None, None))
            return candidate
        tmdb_id = getattr(media_info, "tmdb_id", None) if media_info else None
        douban_id = getattr(media_info, "douban_id", None) if media_info else None
        candidate.secondary_tmdb_id = tmdb_id
        candidate.secondary_douban_id = douban_id
        candidate.secondary_status = "recognized"
        self._remember_secondary(cache_key, (tmdb_id, douban_id))
        return candidate

    def _should_run_secondary(self) -> bool:
        mode = "balanced" if self.settings.mode == "audit" else self.settings.mode
        recheck = self.settings.tmdb_recheck_mode
        if mode == "off":
            return False
        if recheck == "off":
            return False
        if recheck == "all":
            return True
        if recheck == "strict":
            return mode == "strict"
        if recheck == "balanced_strict":
            return mode in {"balanced", "strict"}
        return False

    @staticmethod
    def _secondary_cache_key(candidate: CandidateResource) -> str:
        raw = "\n".join([
            candidate.title or "",
            candidate.description or "",
            str(candidate.year or ""),
            candidate.media_type or "",
            str(candidate.season or ""),
            ",".join(str(ep) for ep in candidate.episodes),
        ])
        return sha1(raw.encode("utf-8")).hexdigest()

    def _remember_secondary(self, key: str, value: tuple[int | None, str | None]):
        maxsize = max(1, int(self.settings.cache_maxsize or 1))
        if key in self._secondary_cache:
            del self._secondary_cache[key]
        self._secondary_cache[key] = value
        while len(self._secondary_cache) > maxsize:
            oldest = next(iter(self._secondary_cache))
            del self._secondary_cache[oldest]

    def _log_audit(self):
        """写出完整识别增强审计摘要；通知限频不影响该日志。"""
        if self.runtime.logger_fn and self.last_audit_summary:
            self.runtime.logger_fn(f"识别增强审计：{self.last_audit_summary}")

    def _audit_summary(self, batch: BatchDecision) -> str:
        parts = [
            f"mode={self.settings.mode}",
            f"strategy_version={self.settings.strategy_version}",
            f"keyword_version={self.settings.keyword_version}",
            f"tmdb_recheck_mode={self.settings.tmdb_recheck_mode}",
            f"selection_original_count={batch.selection_original_count}",
            f"recognition_input_count={batch.recognition_input_count}",
            f"recognition_evaluated_count={batch.recognition_evaluated_count}",
            f"recognition_output_count={batch.recognition_output_count}",
            f"final_count={batch.final_count}",
        ]
        for action, count in sorted(batch.final_action_counts.items()):
            parts.append(f"{action}={count}")
        if self.last_target:
            parts.append(f"range_source={self.last_target.range_source}")
            parts.append(f"range_confidence={self.last_target.range_confidence}")
        for stage in batch.stage_counts:
            parts.append(
                "stage={stage} input={input} output={output}".format(
                    stage=stage.get("stage", "-"),
                    input=stage.get("input", 0),
                    output=stage.get("output", 0),
                )
            )
        for index, decision in enumerate(batch.decisions):
            candidate = decision.candidate or CandidateResource(order=index)
            summary = sanitize_candidate_summary(self._torrent_like(candidate))
            parts.append(
                "candidate={index} fingerprint={fingerprint} summary={summary} "
                "original_action={original_action} final_action={final_action} "
                "would_action={would_action} code={code} reason={reason}".format(
                    index=index,
                    fingerprint=candidate.fingerprint or "-",
                    summary=summary,
                    original_action=decision.action,
                    final_action=decision.final_action,
                    would_action=decision.would_action,
                    code=decision.code,
                    reason=self._safe_reason(decision.reason),
                )
            )
        return " | ".join(parts)

    def _notification_summary(self, batch: BatchDecision) -> str:
        return (
            f"识别增强：输入 {batch.recognition_input_count}，"
            f"输出 {batch.recognition_output_count}，最终 {batch.final_count}"
        )

    @staticmethod
    def _risk_for_action(action: str) -> str:
        if action == ACTION_BLOCK:
            return _HARD_BLOCK
        if action == ACTION_SOFT_BLOCK:
            return _SOFT_BLOCK
        if action == ACTION_OBSERVE:
            return _OBSERVE
        if action == ACTION_FAIL_OPEN:
            return "fail_open"
        return _ALLOW

    @staticmethod
    def _candidate_text(candidate: CandidateResource) -> str:
        return " ".join([candidate.title or "", candidate.description or "", candidate.category or ""])

    @staticmethod
    def _safe_reason(reason: str) -> str:
        return redact_sensitive_text(reason)

    @staticmethod
    def _known_season_conflict(target: RecognitionTarget, candidate: CandidateResource) -> bool:
        if target.season is None or candidate.season is None:
            return False
        if target.season == 0 and candidate.season_kind == "special":
            return False
        return int(target.season) != int(candidate.season)

    def _live_action_match(self, text: str) -> str | None:
        return match_first(self.keyword_groups.live_action, text) or match_first(["真人版", "实拍版", "真人剧"], text)

    @staticmethod
    def _has_explicit_episode_signal(text: str) -> bool:
        return bool(re.search(r"\bS\d{1,3}E\d{1,4}\b|第\s*\d+\s*集", text, re.I))

    @staticmethod
    def _has_hard_live_action_signal(text: str) -> bool:
        return any(token in text for token in ("真人剧", "真人版", "实拍版"))

    @staticmethod
    def _target_from_dict(data) -> RecognitionTarget:
        if isinstance(data, RecognitionTarget):
            return data
        values = dict(data or {})
        allowed = {field.name for field in fields(RecognitionTarget)}
        return RecognitionTarget(**{key: value for key, value in values.items() if key in allowed})

    @staticmethod
    def _candidate_from_dict(data) -> CandidateResource:
        if isinstance(data, CandidateResource):
            return data
        values = dict(data or {})
        if "explicit_tmdb_id" not in values and "tmdb_id" in values:
            values["explicit_tmdb_id"] = values["tmdb_id"]
        if "explicit_douban_id" not in values and "douban_id" in values:
            values["explicit_douban_id"] = values["douban_id"]
        allowed = {field.name for field in fields(CandidateResource)}
        candidate = CandidateResource(**{key: value for key, value in values.items() if key in allowed})
        return candidate

    @staticmethod
    def _torrent_like(candidate: CandidateResource):
        return SimpleNamespace(
            title=candidate.title,
            description=candidate.description,
            site_name=candidate.site,
            enclosure=candidate.fingerprint,
            page_url="",
        )
