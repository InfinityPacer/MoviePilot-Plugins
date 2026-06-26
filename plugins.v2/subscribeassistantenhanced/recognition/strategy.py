"""识别增强 YAML 策略解析与模式模板合并。"""
import hashlib
import re
from dataclasses import dataclass, field
from typing import Any

from ruamel.yaml import YAML

from .keywords import DEFAULT_KEYWORD_CONFIG, GROUP_KEYS, KeywordGroups, _load_yaml_mapping, _normalize_patterns
from .types import ACTION_BLOCK, ACTION_OBSERVE, ACTION_SOFT_BLOCK

ACTION_INHERIT = "inherit"
EMPTY_POOL_RECOVER_SOFT_BLOCK = "recover_soft_block"
EMPTY_POOL_NEVER_RECOVER = "never_recover"

ACTION_CODES = {
    "missing_year",
    "target_range_oversized",
    "user_block",
    "secondary_identity_conflict",
}
ACTION_VALUES = {ACTION_INHERIT, ACTION_OBSERVE, ACTION_SOFT_BLOCK, ACTION_BLOCK}
EMPTY_POOL_POLICIES = {EMPTY_POOL_RECOVER_SOFT_BLOCK, EMPTY_POOL_NEVER_RECOVER}

_MODE_ACTIONS = {
    "audit": {
        "missing_year": ACTION_OBSERVE,
        "target_range_oversized": ACTION_SOFT_BLOCK,
        "user_block": ACTION_SOFT_BLOCK,
        "secondary_identity_conflict": ACTION_BLOCK,
    },
    "loose": {
        "missing_year": ACTION_OBSERVE,
        "target_range_oversized": ACTION_OBSERVE,
        "user_block": ACTION_OBSERVE,
        "secondary_identity_conflict": ACTION_OBSERVE,
    },
    "balanced": {
        "missing_year": ACTION_OBSERVE,
        "target_range_oversized": ACTION_SOFT_BLOCK,
        "user_block": ACTION_SOFT_BLOCK,
        "secondary_identity_conflict": ACTION_BLOCK,
    },
    "strict": {
        "missing_year": ACTION_BLOCK,
        "target_range_oversized": ACTION_SOFT_BLOCK,
        "user_block": ACTION_BLOCK,
        "secondary_identity_conflict": ACTION_BLOCK,
    },
}

_MODE_EMPTY_POOL = {
    "audit": EMPTY_POOL_RECOVER_SOFT_BLOCK,
    "loose": EMPTY_POOL_RECOVER_SOFT_BLOCK,
    "balanced": EMPTY_POOL_RECOVER_SOFT_BLOCK,
    "strict": EMPTY_POOL_NEVER_RECOVER,
}


@dataclass
class RecognitionStrategy:
    """识别增强生效策略快照，供候选判定和审计摘要复用。"""
    mode: str
    actions: dict[str, str]
    explicit_actions: dict[str, str] = field(default_factory=dict)
    empty_pool_policy: str = EMPTY_POOL_RECOVER_SOFT_BLOCK
    non_recoverable_codes: set[str] = field(default_factory=set)
    keyword_groups: KeywordGroups = field(default_factory=KeywordGroups)
    warnings: set[str] = field(default_factory=set)
    config_hash: str = ""
    overridden_keyword_groups: set[str] = field(default_factory=set)

    def action_for(self, code: str) -> str:
        """返回原因码的最终动作模板；未知原因码按 observe fail-open。"""
        return self.actions.get(code, ACTION_OBSERVE)

    def is_recoverable(self, code: str) -> bool:
        """集合级保护是否可恢复该 soft_block 原因码。"""
        return (
            self.empty_pool_policy == EMPTY_POOL_RECOVER_SOFT_BLOCK
            and code not in self.non_recoverable_codes
        )

    @property
    def summary(self) -> str:
        """白名单化策略摘要，不输出 YAML 原文或用户关键词。"""
        parts = [f"hash={self.config_hash or '-'}"]
        if self.explicit_actions:
            parts.append("actions=" + ",".join(sorted(self.explicit_actions)))
        parts.append(f"policy={self.empty_pool_policy}")
        if self.non_recoverable_codes:
            parts.append("non_recoverable=" + ",".join(sorted(self.non_recoverable_codes)))
        if self.overridden_keyword_groups:
            parts.append("keywords=" + ",".join(sorted(self.overridden_keyword_groups)))
        if self.warnings:
            parts.append("warnings=" + ",".join(sorted(self.warnings)))
        return " ".join(parts)


def parse_strategy(mode: str, config_text: str = "") -> RecognitionStrategy:
    """解析用户 YAML 并与当前模式模板合并。"""
    normalized_mode = mode if mode in _MODE_ACTIONS else "balanced"
    warnings: set[str] = set()
    text = str(config_text or "")
    config_hash = hashlib.sha1(text.encode("utf-8")).hexdigest()[:12] if text.strip() else ""
    actions = dict(_MODE_ACTIONS[normalized_mode])
    empty_pool_policy = _MODE_EMPTY_POOL[normalized_mode]
    non_recoverable_codes: set[str] = set()
    keyword_groups = _default_keyword_groups()
    overridden_keyword_groups: set[str] = set()
    explicit_actions: dict[str, str] = {}

    parsed, root_warning = _parse_yaml_root(text)
    if root_warning:
        warnings.add(root_warning)
        return RecognitionStrategy(
            mode=normalized_mode,
            actions=actions,
            explicit_actions=explicit_actions,
            empty_pool_policy=empty_pool_policy,
            non_recoverable_codes=non_recoverable_codes,
            keyword_groups=keyword_groups,
            warnings=warnings,
            config_hash=config_hash,
            overridden_keyword_groups=overridden_keyword_groups,
        )

    for key in parsed:
        if key not in {"actions", "empty_pool", "keywords"}:
            warnings.add("unknown_strategy_key")

    raw_actions = parsed.get("actions")
    if raw_actions is not None:
        if not isinstance(raw_actions, dict):
            warnings.add("invalid_actions_type")
        else:
            for code, action in raw_actions.items():
                code = str(code or "").strip()
                action = str(action or "").strip()
                if code not in ACTION_CODES:
                    warnings.add("unknown_action_code")
                    continue
                if action not in ACTION_VALUES:
                    warnings.add("invalid_action_value")
                    continue
                if action == ACTION_INHERIT:
                    continue
                actions[code] = action
                explicit_actions[code] = action

    raw_empty_pool = parsed.get("empty_pool")
    if raw_empty_pool is not None:
        if not isinstance(raw_empty_pool, dict):
            warnings.add("invalid_empty_pool_type")
        else:
            policy = raw_empty_pool.get("policy")
            if policy is not None:
                policy = str(policy or "").strip()
                if policy in EMPTY_POOL_POLICIES:
                    empty_pool_policy = policy
                else:
                    warnings.add("invalid_empty_pool_policy")
            raw_non_recoverable = raw_empty_pool.get("non_recoverable_codes")
            if raw_non_recoverable is not None:
                if not isinstance(raw_non_recoverable, list):
                    warnings.add("invalid_non_recoverable_codes_type")
                else:
                    for code in raw_non_recoverable:
                        code = str(code or "").strip()
                        if code in ACTION_CODES:
                            non_recoverable_codes.add(code)
                        else:
                            warnings.add("unknown_non_recoverable_code")

    raw_keywords = parsed.get("keywords")
    if raw_keywords is not None:
        if not isinstance(raw_keywords, dict):
            warnings.add("invalid_keywords_type")
        else:
            keyword_groups = _merge_keyword_groups(raw_keywords, keyword_groups, overridden_keyword_groups, warnings)

    return RecognitionStrategy(
        mode=normalized_mode,
        actions=actions,
        explicit_actions=explicit_actions,
        empty_pool_policy=empty_pool_policy,
        non_recoverable_codes=non_recoverable_codes,
        keyword_groups=keyword_groups,
        warnings=warnings,
        config_hash=config_hash,
        overridden_keyword_groups=overridden_keyword_groups,
    )


def _parse_yaml_root(text: str) -> tuple[dict, str | None]:
    """解析 YAML 根节点；空文本、纯注释和 null 根节点均视为无覆盖。"""
    if not text.strip():
        return {}, None
    try:
        data = YAML(typ="safe").load(text)
    except Exception:
        return {}, "invalid_yaml"
    if data is None:
        return {}, None
    if not isinstance(data, dict):
        return {}, "non_mapping_yaml"
    if any(key is None or not str(key).strip() for key in data):
        return {}, "invalid_yaml"
    return data, None


def _default_keyword_groups() -> KeywordGroups:
    data = _load_yaml_mapping(DEFAULT_KEYWORD_CONFIG)
    return KeywordGroups(**{key: _normalize_patterns(data.get(key)) for key in GROUP_KEYS})


def _merge_keyword_groups(raw_keywords: dict, base: KeywordGroups, overridden: set[str],
                          warnings: set[str]) -> KeywordGroups:
    groups = {key: list(getattr(base, key)) for key in GROUP_KEYS}
    for key, value in raw_keywords.items():
        key = str(key or "").strip()
        if key not in GROUP_KEYS:
            warnings.add("invalid_keyword_group_type")
            continue
        if value is None:
            continue
        if not isinstance(value, list):
            warnings.add("invalid_keyword_group_type")
            continue
        patterns: list[str] = []
        for item in value:
            pattern = str(item or "").strip()
            if not pattern:
                continue
            try:
                re.compile(pattern)
            except re.error:
                warnings.add("invalid_keyword_regex")
                continue
            patterns.append(pattern)
        groups[key] = patterns
        overridden.add(key)
    return KeywordGroups(**groups)
