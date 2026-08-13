"""识别增强关键字配置加载与匹配。"""
import re
from dataclasses import dataclass, field
from typing import Any

from ruamel.yaml import YAML

DEFAULT_KEYWORD_CONFIG = """live_action:
  - '电视剧版'
  - '真人版'
  - '实拍版'
  - '真人剧'
animation:
  - '动画'
  - '动漫'
  - '国漫'
  - '番剧'
movie:
  - '电影版'
  - '剧场版'
  - '劇場版'
  - '\\bMovie\\b'
tv:
  - '\\bS\\d{1,3}(?:E\\d{1,4})?\\b'
  - '第\\s*\\d+\\s*[集季]'
  - '全\\s*\\d+\\s*集'
allow: []
block: []
hard_block: []
"""


@dataclass
class KeywordGroups:
    """识别增强关键字分组；普通 block 不是 hard veto，hard_block 才代表用户强规则。"""
    live_action: list[str] = field(default_factory=list)
    animation: list[str] = field(default_factory=list)
    movie: list[str] = field(default_factory=list)
    tv: list[str] = field(default_factory=list)
    allow: list[str] = field(default_factory=list)
    block: list[str] = field(default_factory=list)
    hard_block: list[str] = field(default_factory=list)


GROUP_KEYS = ("live_action", "animation", "movie", "tv", "allow", "block", "hard_block")


def _normalize_patterns(value: Any) -> list[str]:
    """把 YAML 标量或列表统一成去空字符串列表；其他类型按空组 fail-open。"""
    if value is None:
        return []
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if isinstance(value, (list, tuple)):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _load_yaml_mapping(config_text: str) -> dict:
    """解析 YAML mapping；解析失败或非 mapping 时返回空 dict。"""
    try:
        data = YAML(typ="safe").load(config_text) or {}
    except Exception:
        return {}
    return data if isinstance(data, dict) else {}


def load_keyword_groups(config_text: str) -> KeywordGroups:
    """加载关键字分组。

    空配置和坏 YAML 都回退到内置安全词库；单个分组类型错误只禁用该分组。
    """
    source = config_text if str(config_text or "").strip() else DEFAULT_KEYWORD_CONFIG
    data = _load_yaml_mapping(source)
    if not data or not any(key in data for key in GROUP_KEYS):
        data = _load_yaml_mapping(DEFAULT_KEYWORD_CONFIG)
    groups = {key: _normalize_patterns(data.get(key)) for key in GROUP_KEYS}
    return KeywordGroups(**groups)


def match_first(patterns: list[str], text: str) -> str | None:
    """返回第一个匹配的关键字；非法正则只跳过该条，避免整组失效。"""
    haystack = text or ""
    for pattern in patterns:
        try:
            if re.search(pattern, haystack, re.IGNORECASE):
                return pattern
        except re.error:
            continue
    return None
