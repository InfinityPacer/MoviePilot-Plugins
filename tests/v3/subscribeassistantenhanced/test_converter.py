"""best_version/converter.py 分集→全集转换单测。"""
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.db.oper.subscribehistory import SubscribeHistoryOper
from app.plugins.subscribeassistantenhanced.best_version.converter import BestVersionConverter


class _SubscribeSnapshot(SimpleNamespace):
    """带 to_dict 的订阅快照替身，用于验证分集转全集转换载荷。"""

    def to_dict(self):
        """返回订阅快照字典，模拟主程序 Subscribe 对象。"""
        return dict(self.__dict__)


def _mediainfo():
    """构造具备通知图片和序列化能力的媒体信息替身。"""
    return SimpleNamespace(
        media_source="themoviedb",
        media_id="100",
        episode_group="eg-1",
        title="测试剧",
        year="2026",
        type=SimpleNamespace(value="电视剧"),
        overview="测试简介",
        vote_average=8.8,
        get_poster_image=lambda: "poster.jpg",
        get_backdrop_image=lambda: "backdrop.jpg",
        to_dict=lambda: {"title": "测试剧"},
        get_message_image=lambda: "poster.jpg",
    )


def _mutation_scope(result=...):
    """构造同步订阅 mutation scope 及其服务替身。"""
    mutation = MagicMock()
    mutation.update.return_value = SimpleNamespace() if result is ... else result

    @contextmanager
    def scope():
        yield mutation

    return scope, mutation


class TestConvertToFull:

    def test_success(self):
        """分集转全集应归档并原地更新订阅，保留原 ID 后再清理旧任务。"""
        oper = MagicMock()
        history_oper = MagicMock(spec=SubscribeHistoryOper)
        scope, mutation = _mutation_scope()
        clear_tasks = MagicMock(side_effect=lambda _sid: call_order.append("clear_tasks"))
        notify = MagicMock()
        call_order = []
        snapshot = MagicMock(side_effect=lambda **_kwargs: call_order.append("snapshot"))
        mutation.update.side_effect = lambda *_args, **_kwargs: call_order.append("update") or SimpleNamespace()
        conv = BestVersionConverter(
            subscribe_oper=oper,
            subscribe_history_oper=history_oper,
            subscription_mutation_scope=scope,
            clear_tasks_fn=clear_tasks,
            notify_fn=notify,
            snapshot_fn=snapshot,
            format_desc_fn=lambda subscribe, mediainfo: f"{subscribe.name} S{subscribe.season}",
        )
        sub = _SubscribeSnapshot(
            id=1,
            name="测试剧",
            season=1,
            episode_group="eg-1",
            best_version=1,
            best_version_full=0,
            username="user",
            state="R",
            current_priority=50,
            episode_priority={"1": 100, "2": 50},
            manual_total_episode=92,
            note=[1, 2],
        )
        media = _mediainfo()

        assert conv.convert_to_full(sub, media, current_priority=0) is True

        history_oper.add.assert_called_once_with(sub.to_dict())
        oper.delete.assert_not_called()
        clear_tasks.assert_called_once_with(1)
        mutation.update.assert_called_once()
        update_args = mutation.update.call_args.args
        assert update_args[0] == 1
        add_payload = update_args[1]
        assert update_args[2].name == "订阅助手（增强版）"
        assert update_args[2].is_superuser is True
        assert mutation.update.call_args.kwargs["scene"] == "best_version_full"
        assert add_payload["best_version"] == 1
        assert add_payload["best_version_full"] == 1
        assert add_payload["episode_group"] == "eg-1"
        assert add_payload["state"] == "N"
        assert add_payload["username"] == "订阅助手（增强版）"
        assert add_payload["manual_total_episode"] == 0
        assert add_payload["note"] == [1, 2]
        assert add_payload["current_priority"] == 0
        assert add_payload["episode_priority"] == {"1": 100, "2": 50}
        assert "id" not in add_payload
        snapshot.assert_called_once_with(subscribe=sub, mediainfo=media, scope=None)
        assert call_order == ["snapshot", "update", "clear_tasks"]
        notify.assert_called_once()
        assert notify.call_args.args[0] == "测试剧 S1 分集洗版集数已符合目标集数，已从分集洗版转为全集洗版订阅"
        assert "user" not in notify.call_args.kwargs
        assert "reason" not in notify.call_args.kwargs

    def test_uses_subscription_mutation_contract(self):
        """分集转全集应通过宿主 mutation scope 更新原订阅。"""
        oper = MagicMock()
        history_oper = MagicMock(spec=SubscribeHistoryOper)
        scope, mutation = _mutation_scope()
        conv = BestVersionConverter(
            subscribe_oper=oper,
            subscribe_history_oper=history_oper,
            subscription_mutation_scope=scope,
            clear_tasks_fn=MagicMock(),
            notify_fn=MagicMock(),
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)

        assert conv.convert_to_full(sub, _mediainfo()) is True

        mutation.update.assert_called_once()
        assert mutation.update.call_args.args[0] == 1
        assert mutation.update.call_args.args[1]["best_version_full"] == 1

    def test_mutation_failure_keeps_original(self):
        """原地更新失败时保留活动订阅，不清理旧任务。"""
        oper = MagicMock()
        history_oper = MagicMock(spec=SubscribeHistoryOper)
        scope, mutation = _mutation_scope()
        mutation.update.side_effect = RuntimeError("DB error")
        clear_tasks = MagicMock()
        notify = MagicMock()
        conv = BestVersionConverter(
            subscribe_oper=oper,
            subscribe_history_oper=history_oper,
            subscription_mutation_scope=scope,
            clear_tasks_fn=clear_tasks,
            notify_fn=notify,
            format_desc_fn=lambda subscribe, mediainfo: "测试剧 S1",
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)
        assert conv.convert_to_full(sub, _mediainfo()) is False
        oper.delete.assert_not_called()
        clear_tasks.assert_not_called()
        notify.assert_called_once()
        assert notify.call_args.args[0] == "测试剧 S1 转为全集洗版订阅失败"

    def test_history_failure_stops_before_mutating_active_subscribe(self):
        """历史写入失败时不得修改仍在运行的分集洗版订阅。"""
        oper = MagicMock()
        history_oper = MagicMock(spec=SubscribeHistoryOper)
        history_oper.add.side_effect = RuntimeError("history failed")
        scope, mutation = _mutation_scope()
        conv = BestVersionConverter(
            subscribe_oper=oper,
            subscribe_history_oper=history_oper,
            subscription_mutation_scope=scope,
            notify_fn=MagicMock(),
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)

        assert conv.convert_to_full(sub, _mediainfo()) is False

        oper.delete.assert_not_called()
        mutation.update.assert_not_called()

    def test_task_cleanup_failure_does_not_interrupt_rebuild(self):
        """插件任务清理属于尽力操作，失败时仍保留已更新的全集洗版订阅。"""
        oper = MagicMock()
        history_oper = MagicMock(spec=SubscribeHistoryOper)
        scope, mutation = _mutation_scope()
        clear_tasks = MagicMock(side_effect=RuntimeError("cleanup failed"))
        conv = BestVersionConverter(
            subscribe_oper=oper,
            subscribe_history_oper=history_oper,
            subscription_mutation_scope=scope,
            clear_tasks_fn=clear_tasks,
            notify_fn=MagicMock(),
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)

        assert conv.convert_to_full(sub, _mediainfo()) is True

        oper.delete.assert_not_called()
        mutation.update.assert_called_once()

    def test_snapshot_failure_stops_before_subscription_mutation(self):
        """完成快照写入失败时不得修改分集订阅，避免转换后失去增集基线。"""
        oper = MagicMock()
        history_oper = MagicMock(spec=SubscribeHistoryOper)
        scope, mutation = _mutation_scope()
        notify = MagicMock()
        snapshot = MagicMock(side_effect=RuntimeError("snapshot failed"))
        conv = BestVersionConverter(
            subscribe_oper=oper,
            subscribe_history_oper=history_oper,
            subscription_mutation_scope=scope,
            snapshot_fn=snapshot,
            notify_fn=notify,
            format_desc_fn=lambda subscribe, mediainfo: "测试剧 S1",
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)

        assert conv.convert_to_full(sub, _mediainfo()) is False

        history_oper.add.assert_not_called()
        oper.delete.assert_not_called()
        mutation.update.assert_not_called()
        assert notify.call_args.args[0] == "测试剧 S1 转为全集洗版订阅失败"

    def test_no_oper_returns_false(self):
        conv = BestVersionConverter(subscribe_oper=None)
        sub = SimpleNamespace(id=1)
        assert conv.convert_to_full(sub, _mediainfo()) is False

    def test_no_id_returns_false(self):
        conv = BestVersionConverter(subscribe_oper=MagicMock())
        sub = SimpleNamespace(id=0)
        assert conv.convert_to_full(sub, _mediainfo()) is False

    def test_empty_mutation_result_keeps_original_and_notifies(self):
        """宿主未返回更新结果时保留原订阅并通知人工检查。"""
        oper = MagicMock()
        history_oper = MagicMock(spec=SubscribeHistoryOper)
        scope, _mutation = _mutation_scope(result=None)
        notify = MagicMock()
        conv = BestVersionConverter(
            subscribe_oper=oper,
            subscribe_history_oper=history_oper,
            subscription_mutation_scope=scope,
            clear_tasks_fn=MagicMock(),
            notify_fn=notify,
            format_desc_fn=lambda subscribe, mediainfo: "测试剧 S1",
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)
        media = _mediainfo()

        assert conv.convert_to_full(sub, media) is False

        oper.delete.assert_not_called()
        notify.assert_called_once()
        assert notify.call_args.args[0] == "测试剧 S1 转为全集洗版订阅失败"
        assert notify.call_args.kwargs["text"] == "宿主未返回订阅更新结果"
        assert "reason" not in notify.call_args.kwargs
        assert "action" not in notify.call_args.kwargs
        assert notify.call_args.kwargs["follow_up"] == "请检查订阅状态"
        assert notify.call_args.kwargs["diagnostic"] is True

    def test_mutation_exception_reports_original_error(self):
        """全集订阅更新抛错时应保留原订阅并报告原始错误。"""
        oper = MagicMock()
        history_oper = MagicMock(spec=SubscribeHistoryOper)
        scope, mutation = _mutation_scope()
        mutation.update.side_effect = RuntimeError("boom")
        notify = MagicMock()
        conv = BestVersionConverter(
            subscribe_oper=oper,
            subscribe_history_oper=history_oper,
            subscription_mutation_scope=scope,
            notify_fn=notify,
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)
        media = _mediainfo()

        assert conv.convert_to_full(sub, media) is False

        oper.delete.assert_not_called()
        assert notify.call_args.kwargs["text"] == "boom"

    def test_default_description_and_optional_callbacks(self):
        """未注入格式化、事件和通知回调时仍应完成转换并使用默认订阅描述。"""
        oper = MagicMock()
        history_oper = MagicMock(spec=SubscribeHistoryOper)
        scope, mutation = _mutation_scope()
        conv = BestVersionConverter(
            subscribe_oper=oper,
            subscribe_history_oper=history_oper,
            subscription_mutation_scope=scope,
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=2)

        assert conv.convert_to_full(sub, _mediainfo()) is True

        payload = mutation.update.call_args.args[1]
        assert payload["best_version_full"] == 1
        assert payload["username"] == "订阅助手（增强版）"
