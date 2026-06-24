"""识别增强领域模型。"""
from dataclasses import dataclass, field
from typing import Callable, Optional

ACTION_ALLOW = "allow"
ACTION_OBSERVE = "observe"
ACTION_SOFT_BLOCK = "soft_block"
ACTION_BLOCK = "block"
ACTION_SKIP = "skip"
ACTION_FAIL_OPEN = "fail_open"


@dataclass
class RecognitionSettings:
    """识别增强运行策略快照；首版只有 mode 来自用户配置。"""
    mode: str = "off"
    strategy_version: str = "2026-06-24"
    keyword_version: str = "2026-06-24"
    notify_interval: int = 3600
    tmdb_recheck_mode: str = "balanced_strict"
    cache_maxsize: int = 100000
    keyword_config: str = ""


@dataclass
class RecognitionRuntime:
    """识别增强外部依赖；目标事实必须从订阅目标路径注入，不能从候选反推。"""
    target_mediainfo_resolver: Optional[Callable] = None
    tmdb_episodes_fn: Optional[Callable] = None
    secondary_recognizer: Optional[Callable] = None
    logger_fn: Optional[Callable] = None


@dataclass
class RecognitionTarget:
    """当前订阅目标及本次订阅要下载的范围。"""
    subscribe_id: Optional[int] = None
    name: str = ""
    year: str = ""
    media_type: str = ""
    season: Optional[int] = None
    episode_group: Optional[str] = None
    tmdb_id: Optional[int] = None
    douban_id: Optional[str] = None
    custom_words: list[str] = field(default_factory=list)
    aliases: list[str] = field(default_factory=list)
    alias_strengths: dict[str, str] = field(default_factory=dict)
    languages: list[str] = field(default_factory=list)
    origin_countries: list[str] = field(default_factory=list)
    shape: str = "unknown"
    target_episodes: list[int] = field(default_factory=list)
    range_source: str = "unknown"
    range_confidence: str = "unknown"


@dataclass
class CandidateResource:
    """单个候选资源的可审计摘要。"""
    fingerprint: str = ""
    title: str = ""
    description: str = ""
    site: str = ""
    category: str = ""
    order: int = 0
    year: Optional[int] = None
    media_type: str = ""
    season: Optional[int] = None
    episode_group: Optional[str] = None
    season_kind: str = "main"
    episodes: list[int] = field(default_factory=list)
    total_episode: Optional[int] = None
    range_source: str = "unknown"
    languages: list[str] = field(default_factory=list)
    origin_countries: list[str] = field(default_factory=list)
    explicit_tmdb_id: Optional[int] = None
    explicit_douban_id: Optional[str] = None
    recognized_tmdb_id: Optional[int] = None
    recognized_douban_id: Optional[str] = None
    secondary_tmdb_id: Optional[int] = None
    secondary_douban_id: Optional[str] = None
    secondary_status: str = "not_run"
    secondary_failure: str = ""
    candidate_recognized: bool = False
    match_source: str = "unknown"
    media_info_is_target: bool = False


# `languages` 对应设计里的“语种”；`origin_countries` 对应“地区 / 来源国家”。
# 不新增并行 `locale` 或 `region` 字段，避免同一证据出现多套口径。


@dataclass
class Evidence:
    """单条识别证据。"""
    group: str
    code: str
    level: str
    message: str
    source: str = ""
    can_be_countered_by: list[str] = field(default_factory=list)


@dataclass
class Decision:
    """单候选最终动作及证据。"""
    action: str = ACTION_ALLOW
    final_action: str = ACTION_ALLOW
    code: str = "allow"
    reason: str = "未命中风险证据"
    risk: str = "none"
    would_action: str = ACTION_ALLOW
    candidate: Optional[CandidateResource] = None
    evidence: list[Evidence] = field(default_factory=list)
    counters: list[Evidence] = field(default_factory=list)

    @property
    def removed(self) -> bool:
        return self.final_action in {ACTION_BLOCK, ACTION_SOFT_BLOCK}


@dataclass
class BatchDecision:
    """一轮候选过滤输出。"""
    input_count: int = 0
    output_count: int = 0
    selection_original_count: int = 0
    recognition_input_count: int = 0
    recognition_evaluated_count: int = 0
    recognition_output_count: int = 0
    final_count: int = 0
    decisions: list[Decision] = field(default_factory=list)
    retained: list = field(default_factory=list)
    stage_counts: list[dict] = field(default_factory=list)
    fallback_applied: bool = False
    action_counts: dict[str, int] = field(default_factory=dict)
    original_action_counts: dict[str, int] = field(default_factory=dict)
    final_action_counts: dict[str, int] = field(default_factory=dict)
    audit_summary: str = ""
    notification_summary: Optional[str] = None
