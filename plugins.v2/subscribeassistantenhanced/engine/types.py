"""完成证据流水线数据类型与跨模块协议。"""
from dataclasses import dataclass, field
from typing import Protocol, Optional, runtime_checkable


@dataclass
class CompletionSignal:
    """完成证据中的单一信号，描述当前 SeasonScope 的播出完成状态。"""
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
class CompletionEvidence:
    """完成观察裁决的输入证据，聚合各类完结信号与本地阻断信息。"""
    scope_total: int = 0              # 本轮 SeasonScope 的目标总集数
    scope_high_risk: bool = False     # 当前目标范围是否属于高风险范围
    primary_signal: CompletionSignal = field(default_factory=lambda: CompletionSignal(
        completed=False,
        stable=True,
        signals=["none"],
        reason="无信号确认当前目标范围已播完",
    ))                                # 主完结信号，缺省为无完成证据
    hard_veto: Optional[CompletionSignal] = None  # 不可被目标完成证据直接覆盖的否决信号
    unstable_signal: Optional[CompletionSignal] = None  # F 不稳定信号
    high_completion: Optional[CompletionSignal] = None  # 高置信完结信号
    i_signal: Optional[CompletionSignal] = None  # I 类播出完成信号
    i_low_signal: Optional[CompletionSignal] = None  # 低置信 I 信号
    local_signal: Optional[CompletionSignal] = None  # L 本地目标满足信号
    target_complete_signal: Optional[CompletionSignal] = None  # 当前目标范围完成信号
    cadence_expired: bool = False     # G 信号是否已达到播出节奏超期
    observation_kind: str = "none"    # 观察策略类别，供超时管理区分释放口径
    local_blocked_reason: str = ""    # L 信号未命中时的可诊断原因


@dataclass
class CompletionObservationDecision:
    """完成前观察的裁决结果，描述是否退出待定以及是否写入释放令牌。"""
    action: str = "hold"              # 裁决动作：hold/release_guard/release_with_token/allow_complete
    reason: str = ""                  # 裁决原因，用于日志和状态说明
    exit_pending: bool = False        # 是否解除当前 guard_veto 待定状态
    write_release_token: bool = False  # 是否写入一次性完成释放令牌

    @classmethod
    def hold(cls, reason: str = ""):
        """保持观察状态。"""
        return cls(action="hold", reason=reason)

    @classmethod
    def release_guard(cls, reason: str = ""):
        """释放守卫待定状态，但不写完成释放令牌。"""
        return cls(action="release_guard", reason=reason, exit_pending=True)

    @classmethod
    def release_with_token(cls, reason: str = ""):
        """释放守卫待定状态，并写入一次性完成释放令牌。"""
        return cls(
            action="release_with_token",
            reason=reason,
            exit_pending=True,
            write_release_token=True,
        )

    @classmethod
    def allow_complete(cls, reason: str = ""):
        """允许当前完成检查继续通过。"""
        return cls(action="allow_complete", reason=reason, exit_pending=True)


@dataclass
class SeasonScope:
    """当前订阅的逻辑季范围，供完成证据、待定和完成后验证统一使用。"""
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
    def record_observation(self, subscribe_or_id,
                           signal: Optional[CompletionSignal] = None,
                           total_episode: Optional[int] = None) -> None: ...
    def clear_observation(self, subscribe_id: int) -> None: ...
    def consume_release_token(self, subscribe_or_id,
                              signal: CompletionSignal,
                              total_episode: Optional[int] = None) -> bool: ...
    def clear_release_token(self, subscribe_or_id) -> None: ...
    def check_observation(self, subscribe_or_id,
                          evidence: CompletionEvidence,
                          mode: str) -> CompletionObservationDecision: ...


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
