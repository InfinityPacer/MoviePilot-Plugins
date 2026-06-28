"""完结信号引擎数据类型与跨模块协议。"""
from dataclasses import dataclass, field
from typing import Protocol, Optional, runtime_checkable


@dataclass
class CompletionSignal:
    """完结信号引擎输出，描述当前 SeasonScope 的播出完成状态。"""
    completed: bool = False           # 是否判定为已完结
    confidence: str = "none"          # 置信度档位：none/low/medium/high
    stable: bool = True               # F 信号：total_episode 近窗口内是否稳定（不稳定则否决完成）
    cadence_expired: bool = False     # G 信号：按播出节奏是否已超期
    signals: list = field(default_factory=list)  # 命中的信号标识，如 ["E:ended"]
    reason: str = ""                  # 人类可读的判定理由
    scope_total: int = 0              # 本轮 SeasonScope 的 TMDB 目标总集数，用于观察期增集判断
    scope_high_risk: bool = False      # 当前目标范围是否属于 absolute-season 等高风险范围
    volatility_direction: Optional[str] = None  # F 信号窗口内最近一次 total 变化方向：up/down
    volatility_detail: Optional[str] = None  # F 信号窗口内最近一次 total 变化明细：旧集数 -> 新集数


@dataclass
class SeasonScope:
    """当前订阅的逻辑季范围，供信号引擎、待定和完成后验证统一使用。"""
    tmdbid: int = 0                   # TMDB 媒体 ID
    season: int = 0                   # 订阅季号
    episode_group_id: Optional[str] = None  # 剧集组 ID，非空表示按 episode_group 取集
    episodes: list = field(default_factory=list)  # SeasonScope 内的 TMDB 集对象列表
    total: int = 0                    # SeasonScope 目标总集数
    source: str = "main_season"       # 集来源：main_season=主季 / episode_group=剧集组
    high_risk: bool = False           # 是否为高风险绝对季范围，影响 I-3/I-4 放行


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
    """完成快照与增集复查接口，供完成守卫依赖而不耦合具体实现。"""
    def snapshot(self, subscribe, mediainfo, scope: SeasonScope) -> None: ...


@runtime_checkable
class PendingTimeoutManagerProtocol(Protocol):
    """完成前观察释放的协议接口，供守门/待定判定依赖而不耦合具体实现。"""
    def record_block(self, subscribe_id: int,
                     signal: Optional[CompletionSignal] = None,
                     total_episode: Optional[int] = None) -> None: ...
    def clear_block(self, subscribe_id: int) -> None: ...
    def check_release(self, subscribe_id: int,
                      signal: CompletionSignal,
                      total_episode: Optional[int] = None) -> bool: ...
    def consume_release(self, subscribe_id: int,
                        signal: CompletionSignal,
                        total_episode: Optional[int] = None) -> bool: ...


@runtime_checkable
class PriorityManagerProtocol(Protocol):
    """订阅事实与洗版优先级协议接口，供下载删除清理依赖而不耦合具体实现。"""
    def capture_baseline(self, subscribe, torrent_priority) -> dict: ...
    def update_on_download(self, subscribe, episodes, new_priority) -> None: ...
    def rollback(self, subscribe, baseline) -> None: ...
    def rollback_torrent(self, subscribe, torrent_id) -> None: ...
    def can_backfill(self, subscribe) -> bool: ...
    def backfill_existing(self, subscribe, existing_episodes, scene: str = "plugin_backfill") -> bool: ...
    def is_complete(self, subscribe) -> bool: ...
    def mark_complete(self, subscribe) -> None: ...
