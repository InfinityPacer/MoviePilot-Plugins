"""best_version/converter.py 分集→全集转换单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.best_version.converter import BestVersionConverter


class _SubscribeSnapshot(SimpleNamespace):
    """带 to_dict 的订阅快照替身，用于验证分集转全集转换载荷。"""

    def to_dict(self):
        """返回订阅快照字典，模拟主程序 Subscribe 对象。"""
        return dict(self.__dict__)


def _mediainfo():
    """构造具备通知图片和序列化能力的媒体信息替身。"""
    return SimpleNamespace(
        type=SimpleNamespace(value="电视剧"),
        vote_average=8.8,
        to_dict=lambda: {"title": "测试剧"},
        get_message_image=lambda: "poster.jpg",
    )


class TestConvertToFull:

    def test_success(self):
        """分集转全集应归档、删除分集订阅、创建全集洗版并通知。"""
        oper = MagicMock()
        oper.add.return_value = (9, "")
        clear_tasks = MagicMock()
        send_event = MagicMock()
        notify = MagicMock()
        call_order = []
        snapshot = MagicMock(side_effect=lambda **_kwargs: call_order.append("snapshot"))
        oper.delete.side_effect = lambda **_kwargs: call_order.append("delete")
        conv = BestVersionConverter(
            subscribe_oper=oper,
            clear_tasks_fn=clear_tasks,
            send_event_fn=send_event,
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

        oper.add_history.assert_called_once_with(**sub.to_dict())
        oper.delete.assert_called_once_with(sid=1)
        clear_tasks.assert_called_once_with(1)
        oper.add.assert_called_once()
        add_payload = oper.add.call_args.kwargs
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
        assert call_order == ["snapshot", "delete"]
        send_event.assert_called_once()
        assert send_event.call_args.args[1]["subscribe_id"] == 9
        notify.assert_called_once()
        assert notify.call_args.args[0] == "测试剧 S1 分集洗版集数已符合目标集数，已从分集洗版转为全集洗版订阅"
        assert "user" not in notify.call_args.kwargs
        assert "reason" not in notify.call_args.kwargs

    def test_failure_keeps_original(self):
        """删除分集订阅失败时保留活动订阅和已写历史，不做不精确回滚。"""
        oper = MagicMock()
        oper.delete.side_effect = RuntimeError("DB error")
        oper.remove_history = MagicMock()
        notify = MagicMock()
        conv = BestVersionConverter(
            subscribe_oper=oper,
            clear_tasks_fn=MagicMock(),
            notify_fn=notify,
            format_desc_fn=lambda subscribe, mediainfo: "测试剧 S1",
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)
        assert conv.convert_to_full(sub, _mediainfo()) is False
        oper.add.assert_not_called()
        oper.remove_history.assert_not_called()
        notify.assert_called_once()
        assert notify.call_args.args[0] == "测试剧 S1 转为全集洗版订阅失败"

    def test_history_failure_stops_before_deleting_active_subscribe(self):
        """历史写入失败时不得删除仍在运行的分集洗版订阅。"""
        oper = MagicMock()
        oper.add_history.side_effect = RuntimeError("history failed")
        conv = BestVersionConverter(subscribe_oper=oper, notify_fn=MagicMock())
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)

        assert conv.convert_to_full(sub, _mediainfo()) is False

        oper.delete.assert_not_called()
        oper.add.assert_not_called()

    def test_task_cleanup_failure_does_not_interrupt_rebuild(self):
        """插件任务清理属于尽力操作，失败时仍继续创建全集洗版订阅。"""
        oper = MagicMock()
        oper.add.return_value = (9, "")
        clear_tasks = MagicMock(side_effect=RuntimeError("cleanup failed"))
        conv = BestVersionConverter(
            subscribe_oper=oper,
            clear_tasks_fn=clear_tasks,
            send_event_fn=MagicMock(),
            notify_fn=MagicMock(),
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)

        assert conv.convert_to_full(sub, _mediainfo()) is True

        oper.delete.assert_called_once_with(sid=1)
        oper.add.assert_called_once()

    def test_snapshot_failure_stops_before_subscription_replacement(self):
        """完成快照写入失败时不得删除分集订阅，避免转换后失去增集基线。"""
        oper = MagicMock()
        notify = MagicMock()
        snapshot = MagicMock(side_effect=RuntimeError("snapshot failed"))
        conv = BestVersionConverter(
            subscribe_oper=oper,
            snapshot_fn=snapshot,
            notify_fn=notify,
            format_desc_fn=lambda subscribe, mediainfo: "测试剧 S1",
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)

        assert conv.convert_to_full(sub, _mediainfo()) is False

        oper.add_history.assert_not_called()
        oper.delete.assert_not_called()
        oper.add.assert_not_called()
        assert notify.call_args.args[0] == "测试剧 S1 转为全集洗版订阅失败"

    def test_no_oper_returns_false(self):
        conv = BestVersionConverter(subscribe_oper=None)
        sub = SimpleNamespace(id=1)
        assert conv.convert_to_full(sub, _mediainfo()) is False

    def test_no_id_returns_false(self):
        conv = BestVersionConverter(subscribe_oper=MagicMock())
        sub = SimpleNamespace(id=0)
        assert conv.convert_to_full(sub, _mediainfo()) is False

    def test_add_failure_restores_old_subscribe_and_notifies(self):
        """创建全集洗版失败时应尝试重建分集订阅并通知人工检查。"""
        oper = MagicMock()
        oper.add.return_value = (None, "订阅创建失败")
        restore = MagicMock(return_value=True)
        notify = MagicMock()
        conv = BestVersionConverter(
            subscribe_oper=oper,
            clear_tasks_fn=MagicMock(),
            restore_fn=restore,
            notify_fn=notify,
            format_desc_fn=lambda subscribe, mediainfo: "测试剧 S1",
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)
        media = _mediainfo()

        assert conv.convert_to_full(sub, media) is False

        restore.assert_called_once_with(sub.to_dict(), media)
        notify.assert_called_once()
        assert notify.call_args.args[0] == "测试剧 S1 转为全集洗版订阅失败"
        assert notify.call_args.kwargs["text"] == "订阅创建失败\n分集洗版订阅已尝试重建"
        assert "reason" not in notify.call_args.kwargs
        assert "action" not in notify.call_args.kwargs
        assert notify.call_args.kwargs["follow_up"] == "请检查订阅状态"
        assert notify.call_args.kwargs["diagnostic"] is True

    def test_add_exception_reports_restore_failure(self):
        """全集订阅创建抛错且恢复失败时，通知应明确要求人工检查。"""
        oper = MagicMock()
        oper.add.side_effect = RuntimeError("boom")
        restore = MagicMock(return_value=False)
        notify = MagicMock()
        conv = BestVersionConverter(
            subscribe_oper=oper,
            restore_fn=restore,
            notify_fn=notify,
        )
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=1)
        media = _mediainfo()

        assert conv.convert_to_full(sub, media) is False

        restore.assert_called_once_with(sub.to_dict(), media)
        assert notify.call_args.kwargs["text"] == "boom\n分集洗版订阅重建失败，请手动检查"

    def test_default_description_and_optional_callbacks(self):
        """未注入格式化、事件和通知回调时仍应完成转换并使用默认订阅描述。"""
        oper = MagicMock()
        oper.add.return_value = (8, "")
        conv = BestVersionConverter(subscribe_oper=oper)
        sub = _SubscribeSnapshot(id=1, name="测试剧", season=2)

        assert conv.convert_to_full(sub, _mediainfo()) is True

        payload = oper.add.call_args.kwargs
        assert payload["best_version_full"] == 1
        assert payload["username"] == "订阅助手（增强版）"
