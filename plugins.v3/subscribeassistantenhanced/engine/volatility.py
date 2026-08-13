"""F：变更速率追踪，检测 total_episode 是否在窗口期内变动过。"""
import time
from typing import Optional

from ..shared.config import DEFAULT_VOLATILITY_WINDOW_DAYS
from ..shared.task import TaskDataManager
from ..shared.subscribe import identity_matches, subscribe_identity

VOLATILITY_KEY = "volatility"
# 只限制保留的诊断采样数量；稳定窗口由 unstable_until 持久化，不能依赖采样条数。
MAX_SAMPLE_HISTORY_SIZE = 20


class VolatilityTracker:
    """记录 TMDB 原始 total_episode 值，检测数据稳定性。"""

    def __init__(self, task_manager: TaskDataManager,
                 window_days: int = DEFAULT_VOLATILITY_WINDOW_DAYS):
        self._task = task_manager
        self._window_seconds = window_days * 86400

    def record(self, total: int, subscribe_id: Optional[int] = None,
               subscribe=None):
        """记录 total_episode；提供订阅对象时同时校验媒体身份。"""
        if subscribe is not None:
            subscribe_id = subscribe.id
        if subscribe_id is None:
            return
        sid = str(subscribe_id)
        now = time.time()

        def updater(data: dict) -> dict:
            entry = data.get(sid)
            if subscribe is not None:
                if isinstance(entry, list):
                    entry = _new_entry(subscribe, records=entry)
                elif isinstance(entry, dict):
                    identity = entry.get("identity")
                    if identity is None:
                        entry["identity"] = subscribe_identity(subscribe)
                    elif not identity_matches(identity, subscribe):
                        entry = _new_entry(subscribe)
                else:
                    entry = _new_entry(subscribe)
            else:
                if isinstance(entry, list):
                    entry = {"records": entry}
                elif not isinstance(entry, dict):
                    entry = {"records": []}
            buf = _records_from_entry(entry)
            entry["records"] = buf
            _ensure_change_state(entry, self._window_seconds)
            _sync_unstable_until(entry, self._window_seconds)
            last_total = entry.get("last_total")
            if last_total is None and buf:
                last_total = buf[-1].get("total")
            if last_total is not None and last_total != total:
                entry["last_total_changed_at"] = now
                entry["unstable_until"] = now + self._window_seconds
                entry["last_total_before_change"] = last_total
                entry["last_total_after_change"] = total
                entry["last_total_change_direction"] = "down" if total < last_total else "up"
            entry["last_total"] = total
            buf.append({"total": total, "ts": now})
            if len(buf) > MAX_SAMPLE_HISTORY_SIZE:
                buf = buf[-MAX_SAMPLE_HISTORY_SIZE:]
            entry["records"] = buf
            data[sid] = entry
            return data

        self._task.update(VOLATILITY_KEY, updater)

    def is_stable(self, subscribe_id: Optional[int] = None, subscribe=None) -> bool:
        """检查窗口期内 total 是否无变动；身份不符按新订阅处理。"""
        if subscribe is not None:
            subscribe_id = subscribe.id
        if subscribe_id is None:
            return True
        sid = str(subscribe_id)
        data = self._task.read(VOLATILITY_KEY)
        entry = data.get(sid)
        if subscribe is not None:
            if isinstance(entry, list):
                buf = _records_from_entry(entry)
            elif isinstance(entry, dict):
                identity = entry.get("identity")
                if identity is not None and not identity_matches(identity, subscribe):
                    self._task.update(
                        VOLATILITY_KEY,
                        lambda current: _drop_key(current, sid),
                    )
                    return True
                buf = _records_from_entry(entry)
            else:
                self._task.update(
                    VOLATILITY_KEY,
                    lambda current: _drop_key(current, sid),
                )
                return True
        else:
            if isinstance(entry, list):
                buf = _records_from_entry(entry)
            elif isinstance(entry, dict):
                buf = _records_from_entry(entry)
            else:
                buf = []
        if isinstance(entry, dict):
            unstable_until = _effective_unstable_until(entry, self._window_seconds)
            if unstable_until and unstable_until >= time.time():
                return False
        if len(buf) <= 1:
            return True
        cutoff = time.time() - self._window_seconds
        recent = [r for r in buf if r["ts"] >= cutoff]
        if len(recent) <= 1:
            return True
        totals = {r["total"] for r in recent}
        return len(totals) == 1

    def recent_change_direction(self, subscribe_id: Optional[int] = None,
                                subscribe=None) -> Optional[str]:
        """返回窗口内最近一次 total 变化方向，用于区分缩小导致的低估风险。"""
        if subscribe is not None:
            subscribe_id = subscribe.id
        if subscribe_id is None:
            return None
        sid = str(subscribe_id)
        entry = self._task.read(VOLATILITY_KEY).get(sid)
        if subscribe is not None and isinstance(entry, dict):
            identity = entry.get("identity")
            if identity is not None and not identity_matches(identity, subscribe):
                return None
        direction = _recent_change_direction(entry, self._window_seconds)
        return direction

    def recent_change_detail(self, subscribe_id: Optional[int] = None,
                             subscribe=None) -> Optional[str]:
        """返回窗口内最近一次 total 变化明细，格式为“旧集数 -> 新集数”。"""
        if subscribe is not None:
            subscribe_id = subscribe.id
        if subscribe_id is None:
            return None
        sid = str(subscribe_id)
        entry = self._task.read(VOLATILITY_KEY).get(sid)
        if subscribe is not None and isinstance(entry, dict):
            identity = entry.get("identity")
            if identity is not None and not identity_matches(identity, subscribe):
                return None
        return _recent_change_detail(entry, self._window_seconds)


def _drop_key(data: dict, sid: str) -> dict:
    """删除失配订阅 ID 的旧记录。"""
    data.pop(sid, None)
    return data


def _new_entry(subscribe, records: Optional[list] = None) -> dict:
    """创建带订阅身份的 volatility 记录。"""
    return {
        "identity": subscribe_identity(subscribe),
        "records": _records_from_entry(records),
        "last_total": None,
        "last_total_changed_at": None,
        "unstable_until": None,
        "last_total_before_change": None,
        "last_total_after_change": None,
        "last_total_change_direction": None,
    }


def _records_from_entry(entry) -> list[dict]:
    """读取可用采样列表；损坏采样按空列表处理，避免阻断订阅刷新。"""
    if isinstance(entry, dict):
        records = entry.get("records") or []
    elif isinstance(entry, list):
        records = entry
    else:
        return []
    if not isinstance(records, list):
        return []
    return [record for record in records if isinstance(record, dict)]


def _effective_unstable_until(entry: dict, window_seconds: int) -> Optional[float]:
    """按当前配置窗口计算有效截止时间，避免旧配置写入的截止时间继续延长观察。"""
    changed_at = entry.get("last_total_changed_at")
    if changed_at:
        return changed_at + window_seconds
    return entry.get("unstable_until")


def _sync_unstable_until(entry: dict, window_seconds: int):
    """把持久化截止时间同步到当前窗口，配置缩短后下一次记录会自动截断。"""
    unstable_until = _effective_unstable_until(entry, window_seconds)
    if unstable_until is not None:
        entry["unstable_until"] = unstable_until


def _ensure_change_state(entry: dict, window_seconds: int):
    """从历史采样补齐变化窗口状态，兼容旧 list 记录升级后的首次写入。"""
    if entry.get("last_total") is not None:
        return
    records = _records_from_entry(entry)
    entry["records"] = records
    if not records:
        return
    entry["last_total"] = records[-1].get("total")
    last_changed_at = None
    previous_total = records[0].get("total")
    before_change = None
    after_change = None
    for record in records[1:]:
        current_total = record.get("total")
        if current_total != previous_total:
            last_changed_at = record.get("ts")
            before_change = previous_total
            after_change = current_total
        previous_total = current_total
    if last_changed_at is not None:
        entry["last_total_changed_at"] = last_changed_at
        entry["unstable_until"] = last_changed_at + window_seconds
        entry["last_total_before_change"] = before_change
        entry["last_total_after_change"] = after_change
        entry["last_total_change_direction"] = _recent_change_direction(records, window_seconds)


def _recent_change_direction(entry, window_seconds: int) -> Optional[str]:
    """从持久化 entry 或旧采样列表读取窗口内最近一次 total 变化方向。"""
    now = time.time()
    if isinstance(entry, dict):
        changed_at = entry.get("last_total_changed_at")
        direction = entry.get("last_total_change_direction")
        unstable_until = _effective_unstable_until(entry, window_seconds)
        if direction and unstable_until is not None and unstable_until >= now:
            return direction
        records = _records_from_entry(entry)
    elif isinstance(entry, list):
        records = _records_from_entry(entry)
    else:
        return None
    cutoff = now - window_seconds
    previous_total = None
    direction = None
    for record in records:
        if record.get("ts", 0) < cutoff:
            continue
        current_total = record.get("total")
        if previous_total is not None and current_total != previous_total:
            direction = "down" if current_total < previous_total else "up"
        previous_total = current_total
    return direction


def _recent_change_detail(entry, window_seconds: int) -> Optional[str]:
    """从持久化 entry 或旧采样列表读取窗口内最近一次 total 变化明细。"""
    now = time.time()
    if isinstance(entry, dict):
        before = entry.get("last_total_before_change")
        after = entry.get("last_total_after_change")
        if after is None:
            after = entry.get("last_total")
        if (
            before is not None
            and after is not None
            and (unstable_until := _effective_unstable_until(entry, window_seconds)) is not None
            and unstable_until >= now
        ):
            return f"{before} -> {after}"
        records = _records_from_entry(entry)
    elif isinstance(entry, list):
        records = _records_from_entry(entry)
    else:
        return None
    cutoff = now - window_seconds
    previous_total = None
    detail = None
    for record in records:
        if record.get("ts", 0) < cutoff:
            continue
        current_total = record.get("total")
        if previous_total is not None and current_total != previous_total:
            detail = f"{previous_total} -> {current_total}"
        previous_total = current_total
    return detail
