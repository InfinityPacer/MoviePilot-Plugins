"""完结信号引擎数据类型与跨域协议桩。"""
from dataclasses import dataclass, field
from typing import Protocol, Optional, runtime_checkable


@dataclass
class CompletionSignal:
    """完结信号引擎输出——描述当前 scope 的播出完成状态。"""
    completed: bool = False           # 是否判定为已完结
    confidence: str = "none"          # 置信度档位：none/low/medium/high
    stable: bool = True               # F 信号：total_episode 近窗口内是否稳定（不稳定则否决完成）
    cadence_expired: bool = False     # G 信号：按播出节奏是否已超期
    signals: list = field(default_factory=list)  # 命中的信号标识，如 ["E:ended"]
    reason: str = ""                  # 人类可读的判定理由


@dataclass
class SeasonScope:
    """当前订阅的逻辑季范围——所有域共用此结构。"""
    tmdbid: int = 0                   # TMDB 媒体 ID
    season: int = 0                   # 订阅季号
    episode_group_id: Optional[str] = None  # 剧集组 ID，非空表示按 episode_group 取集
    episodes: list = field(default_factory=list)  # scope 内的 TMDB 集对象列表
    total: int = 0                    # scope 目标总集数
    source: str = "main_season"       # 集来源：main_season=主季 / episode_group=剧集组
    high_risk: bool = False           # 是否高风险绝对季（超长/断档/多组），影响 I-3/I-4 放行


@dataclass
class PauseRecord:
    """暂停原因记录，区分暂停来源。"""
    # 暂停来源：pre_air（上映/开播前）/airing_gap（播出间隔）/no_download（无下载超期）/auto_user（按用户名自动暂停）。
    # 其中 no_download/auto_user 为标记暂停：state=S 时元数据巡检直接跳过，
    # 不被上映检查自动恢复；pre_air/airing_gap 为上映类暂停，条件解除时双向自动恢复。
    reason: str = ""
    since: float = 0.0                # 暂停起始时间戳
    detail: str = ""                  # 暂停明细描述


@runtime_checkable
class CompletionVerifierProtocol(Protocol):
    """完成后异步自验证的协议接口，供守门依赖而不耦合具体实现。"""
    def snapshot(self, subscribe, mediainfo, scope: SeasonScope) -> None: ...


@runtime_checkable
class PendingTimeoutManagerProtocol(Protocol):
    """待定超时释放的协议接口，供守门/待定判定依赖而不耦合具体实现。"""
    def record_block(self, subscribe_id: int) -> None: ...
    def clear_block(self, subscribe_id: int) -> None: ...
    def check_release(self, subscribe_id: int, signal: CompletionSignal) -> bool: ...


@runtime_checkable
class PriorityManagerProtocol(Protocol):
    """洗版优先级管理的协议接口，供下载删除清理依赖而不耦合具体实现。"""
    def capture_baseline(self, subscribe, torrent_priority) -> dict: ...
    def update_on_download(self, subscribe, episodes, new_priority) -> None: ...
    def rollback(self, subscribe, baseline) -> None: ...
    def backfill_existing(self, subscribe, existing_episodes) -> None: ...
    def is_complete(self, subscribe) -> bool: ...
    def mark_complete(self, subscribe) -> None: ...
