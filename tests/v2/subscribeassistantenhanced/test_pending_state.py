"""pending/state.py 统一待定状态仲裁单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.engine.types import PauseRecord
from subscribeassistantenhanced.pending.state import PendingStateCoordinator
from subscribeassistantenhanced.pause.manager import PauseManager


def _store_mgr(store=None):
    """构造插件任务存储替身，模拟 TaskDataManager 的 read/update 契约。"""
    store = store if store is not None else {}

    def read(key):
        return store.get(key, {})

    def update(key, updater):
        data = store.get(key, {})
        result = updater(data)
        store[key] = result
        return result

    return read, update, store


def _sub(state="R"):
    """构造订阅替身。"""
    return SimpleNamespace(id=1, name="测试剧", season=1, state=state)


class TestPendingStateCoordinator:
    """多来源待定仲裁：任一来源仍活跃时订阅保持 P。"""

    def test_clear_one_source_keeps_p_when_another_source_active(self):
        read, update, store = _store_mgr()
        oper = MagicMock()
        coordinator = PendingStateCoordinator(read, update, subscribe_oper=oper)

        coordinator.mark_active(_sub(), source="download_pending", reason="下载中")
        coordinator.mark_active(_sub(state="P"), source="pending_judge", reason="集数不足")
        coordinator.clear_active(_sub(state="P"), source="download_pending", reason="下载完成")

        task = store["subscribes"]["1"]
        assert task["state"] == "P"
        assert task["source"] == "pending_judge"
        assert "download_pending" not in task["pending_sources"]
        assert "pending_judge" in task["pending_sources"]
        assert any(
            call_args.args[0] == 1 and call_args.args[1]["state"] == "P"
            for call_args in oper.update.call_args_list
        )
        assert oper.update.call_args_list[-1].args[1]["state"] != "R"

    def test_clear_last_source_restores_r(self):
        read, update, store = _store_mgr()
        oper = MagicMock()
        coordinator = PendingStateCoordinator(read, update, subscribe_oper=oper)

        coordinator.mark_active(_sub(), source="download_pending", reason="下载中")
        coordinator.clear_active(_sub(state="P"), source="download_pending", reason="下载完成")

        task = store["subscribes"]["1"]
        assert task["state"] == "R"
        assert task["pending_sources"] == {}
        assert any(
            call_args.args[0] == 1 and call_args.args[1]["state"] == "R"
            for call_args in oper.update.call_args_list
        )

    def test_has_active_reads_pending_sources(self):
        read, update, _ = _store_mgr({
            "subscribes": {
                "1": {
                    "state": "P",
                    "source": "guard_veto",
                    "pending_sources": {"guard_veto": {"reason": "未完结"}},
                }
            }
        })
        coordinator = PendingStateCoordinator(read, update)

        assert coordinator.has_active(1) is True
        assert coordinator.has_active(2) is False

    def test_clear_all_owned_keeps_task_evidence_when_database_update_fails(self):
        """数据库恢复失败时必须保留插件待定记录，供后续巡检重试。"""
        read, update, store = _store_mgr({
            "subscribes": {
                "1": {
                    "state": "P",
                    "source": "pending_judge",
                    "pending_sources": {"pending_judge": {"reason": "集数不足"}},
                }
            }
        })
        oper = MagicMock()
        oper.update.side_effect = RuntimeError("database unavailable")
        coordinator = PendingStateCoordinator(read, update, subscribe_oper=oper)

        try:
            coordinator.clear_all_owned(_sub(state="P"), reason="插件任务重置")
        except RuntimeError:
            pass

        task = store["subscribes"]["1"]
        assert task["state"] == "P"
        assert "pending_judge" in task["pending_sources"]

    def test_pause_overrides_owned_pending_without_restoring_r(self):
        """插件暂停优先级高于插件待定，暂停时直接置 S 并清理待定归属。"""
        read, update, store = _store_mgr({
            "subscribes": {
                "1": {
                    "state": "P",
                    "source": "pending_judge",
                    "pending_sources": {"pending_judge": {"reason": "集数不足"}},
                }
            }
        })
        oper = MagicMock()
        pending = PendingStateCoordinator(read, update, subscribe_oper=oper)
        pause = PauseManager(read, update, subscribe_oper=oper, pending_state=pending)

        pause.pause(_sub(state="P"), PauseRecord(reason="pre_air", since=1.0, detail="未上映"))

        task = store["subscribes"]["1"]
        assert task["state"] == "S"
        assert task["pending_sources"] == {}
        assert task["source"] is None
        assert task["pause_reason"] == "pre_air"
        assert oper.update.call_args.args[1]["state"] == "S"
        assert not any(call.args[1].get("state") == "R" for call in oper.update.call_args_list)
