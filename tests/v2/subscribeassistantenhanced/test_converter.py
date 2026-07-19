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

        assert conv.convert_to_full(sub, media) is True

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
        assert add_payload["current_priority"] == 50
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
        """删除分集订阅失败时不得创建全集洗版，并通知失败。"""
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
        oper.remove_history.assert_called_once()
        notify.assert_called_once()
        assert notify.call_args.args[0] == "测试剧 S1 转为全集洗版订阅失败"

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

    def test_remove_history_snapshot_uses_database_fallback(self):
        """旧订阅删除失败时，没有 remove_history 也应按身份从数据库清理刚写入的历史。"""
        history = object()
        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value.first.return_value = history
        db = MagicMock()
        db.query.return_value = query
        oper = MagicMock()
        del oper.remove_history
        oper._db = db
        conv = BestVersionConverter(subscribe_oper=oper)

        conv._remove_history_snapshot({"tmdbid": 100, "season": 1, "name": "测试剧"})

        db.delete.assert_called_once_with(history)
        db.commit.assert_called_once()

    def test_remove_history_snapshot_without_identity_uses_name(self):
        """没有 tmdb/douban 身份时按名称回退清理，覆盖旧数据兼容路径。"""
        history = object()
        query = MagicMock()
        query.filter.return_value = query
        query.order_by.return_value.first.return_value = history
        db = MagicMock()
        db.query.return_value = query
        oper = MagicMock()
        del oper.remove_history
        oper._db = db
        conv = BestVersionConverter(subscribe_oper=oper)

        conv._remove_history_snapshot({"name": "测试剧", "season": 1})

        db.delete.assert_called_once_with(history)
        db.commit.assert_called_once()
