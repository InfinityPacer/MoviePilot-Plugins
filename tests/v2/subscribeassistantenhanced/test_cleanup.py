"""download/cleanup.py 删除后恢复单测。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.download.cleanup import TorrentCleanup


def _sub(sid=1, best_version=0, **kwargs):
    data = {
        "id": sid,
        "name": "测试剧",
        "season": 1,
        "total_episode": 12,
        "start_episode": 1,
        "lack_episode": 0,
        "note": [],
        "best_version": best_version,
        "type": "电视剧",
    }
    data.update(kwargs)
    return SimpleNamespace(
        **data,
    )


def _cleanup(store=None):
    store = store if store is not None else {}
    priority = MagicMock()
    clear_fn = MagicMock()
    subscribe_oper = MagicMock()

    def update_fn(key, updater):
        data = store.get(key, {})
        result = updater(data)
        store[key] = result

    c = TorrentCleanup(
        priority_manager=priority,
        clear_download_pending_fn=clear_fn,
        task_data_update=update_fn,
    )
    c._store = store
    c._priority_mock = priority
    c._clear_mock = clear_fn
    c._subscribe_oper_mock = subscribe_oper
    return c


class TestHandleTorrentDeleted:

    def test_normal_subscribe_no_rollback(self):
        """非洗版订阅不回滚优先级。"""
        c = _cleanup()
        c.handle_torrent_deleted(_sub(best_version=0), "hash123")
        c._priority_mock.rollback.assert_not_called()

    def test_best_version_rollback(self):
        """洗版订阅无 enclosure 归属信息时整体回滚。"""
        c = _cleanup()
        c.handle_torrent_deleted(_sub(best_version=1), "hash123")
        c._priority_mock.rollback.assert_called_once()

    def test_best_version_rollback_by_enclosure(self):
        """洗版订阅删种 → 按 enclosure 归属回滚（rollback_torrent），隔离并行洗版。"""
        store = {"torrents": {"h1": {"hash": "h1", "enclosure": "http://x/t.torrent"}}}
        priority = MagicMock()

        def update_fn(key, updater):
            store[key] = updater(store.get(key, {}))

        c = TorrentCleanup(
            priority_manager=priority, clear_download_pending_fn=MagicMock(),
            task_data_update=update_fn, task_data_read=lambda k: store.get(k, {}),
        )
        sub = _sub(best_version=1)
        c.handle_torrent_deleted(sub, "h1")
        priority.rollback_torrent.assert_called_once_with(sub, "http://x/t.torrent")
        priority.rollback.assert_not_called()

    def test_clears_download_pending(self):
        c = _cleanup()
        c.handle_torrent_deleted(_sub(), "hash123")
        c._clear_mock.assert_called_once_with(1, "hash123")

    def test_timeout_delete_does_not_pause_subscribe(self):
        """超时删种后由删除指纹防重选并补搜，不把订阅置为暂停。"""
        c = _cleanup()
        c.handle_torrent_deleted(_sub(), "hash123", reason="timeout")
        assert not hasattr(c, "_pause")

    def test_cleans_torrent_task(self):
        store = {"torrents": {"hash123": {"some": "data"}}}
        c = _cleanup(store)
        c.handle_torrent_deleted(_sub(), "hash123")
        assert "hash123" not in store.get("torrents", {})

    def test_updates_tv_note_and_lack_episode_after_delete(self):
        """删除剧集种子后，从订阅 note 扣除对应集并按起始集重算缺集数。"""
        sub = _sub(note=[1, 2, 3, 4], total_episode=12, start_episode=1)
        store = {"torrents": {"h1": {"hash": "h1", "episodes": [2, 3]}}}
        subscribe_oper = MagicMock()

        def update_fn(key, updater):
            store[key] = updater(store.get(key, {}))

        c = TorrentCleanup(
            priority_manager=MagicMock(), clear_download_pending_fn=MagicMock(),
            task_data_update=update_fn, task_data_read=lambda k: store.get(k, {}),
            subscribe_oper=subscribe_oper,
        )

        c.handle_torrent_deleted(sub, "h1")

        subscribe_oper.update.assert_called_once()
        assert subscribe_oper.update.call_args.args[0] == 1
        payload = subscribe_oper.update.call_args.args[1]
        assert payload["note"] == [1, 4]
        assert payload["lack_episode"] == 10

    def test_cleans_subscribe_torrent_tasks_after_delete(self):
        """删除种子后同步清理订阅内 torrent_tasks。"""
        store = {
            "torrents": {"h1": {"hash": "h1"}},
            "subscribes": {"1": {"torrent_tasks": [{"hash": "h1"}, {"hash": "h2"}]}},
        }
        c = _cleanup(store)

        c.handle_torrent_deleted(_sub(), "h1")

        assert store["subscribes"]["1"]["torrent_tasks"] == [{"hash": "h2"}]

    def test_deletes_torrent_archives_fingerprint_and_searches(self):
        """归档指纹(清任务前读取) → 真正删下载器种子 → 延迟补搜；任务最终被清。"""
        store = {"torrents": {"h1": {
            "hash": "h1", "enclosure": "http://x/t.torrent",
            "title": "测试种子", "description": "测试内容",
        }}}
        priority, clear_fn = MagicMock(), MagicMock()
        deletes, delete_fn, search_fn, notify = MagicMock(), MagicMock(), MagicMock(), MagicMock()
        search_fn.return_value = 4.78 * 60

        def update_fn(key, updater):
            store[key] = updater(store.get(key, {}))

        c = TorrentCleanup(
            priority_manager=priority, clear_download_pending_fn=clear_fn,
            task_data_update=update_fn, task_data_read=lambda k: store.get(k, {}),
            deletes_store=deletes, delete_torrent_fn=delete_fn, search_fn=search_fn,
            notify_fn=notify, get_subscribe_image_fn=lambda subscribe: "subscribe.jpg",
        )
        sub = _sub()
        c.handle_torrent_deleted(
            sub, "h1", reason="timeout", downloader="qb",
            reason_detail="订阅种子，下载时长 2.00 小时，超时窗口 2 小时内进度增长 0.00%，"
                          "低于 10%（低进度删除 1/3 次）",
        )
        # 指纹在清任务前读取并归档（含 enclosure）
        deletes.save.assert_called_once()
        assert deletes.save.call_args[0][0].get("enclosure") == "http://x/t.torrent"
        # 真正从下载器删种
        delete_fn.assert_called_once_with("qb", "h1")
        # 延迟补搜 + 任务已清
        search_fn.assert_called_once_with(sub)
        assert "h1" not in store.get("torrents", {})
        notify.assert_called_once()
        title, text = notify.call_args.args[:2]
        assert "订阅种子，下载时长 2.00 小时" in title
        assert "（低进度删除 1/3 次），已删除" in title
        assert "补全：将在 4.78 分钟 后触发搜索" in text
        assert notify.call_args.kwargs["image"] == "subscribe.jpg"

    def test_manual_review_notification_keeps_torrent(self):
        """连续超时达到上限时保留种子，并按旧版口径通知人工处理。"""
        store = {"torrents": {"h1": {"hash": "h1", "title": "测试种子"}}}
        notify = MagicMock()

        c = TorrentCleanup(
            priority_manager=MagicMock(), clear_download_pending_fn=MagicMock(),
            task_data_update=lambda key, updater: store.__setitem__(key, updater(store.get(key, {}))),
            task_data_read=lambda key: store.get(key, {}),
            notify_fn=notify, get_subscribe_image_fn=lambda subscribe: "subscribe.jpg",
        )

        c.handle_timeout_manual_review(
            _sub(), "h1",
            "订阅种子，下载时长 6.00 小时，超时窗口 2 小时内进度增长 0.00%，"
            "低于 10%（低进度删除 3/3 次）",
            ignore_hours=6,
        )

        assert "h1" in store["torrents"]
        assert "下载连续超时，请手动处理" in notify.call_args.args[0]
        assert "低进度删除 3/3 次" in notify.call_args.args[1]
        assert "已保留当前种子，6 小时内不再自动删除" in notify.call_args.args[1]
        assert notify.call_args.kwargs["image"] == "subscribe.jpg"

    def test_manual_delete_skips_pause_but_keeps_fingerprint_and_search(self):
        """手动删除归档指纹并补搜，但不暂停订阅、不调下载器删种。"""
        store = {"torrents": {"h1": {"hash": "h1", "enclosure": "http://x/t.torrent"}}}
        priority, clear_fn = MagicMock(), MagicMock()
        deletes, delete_fn, search_fn, notify = MagicMock(), MagicMock(), MagicMock(), MagicMock()

        def update_fn(key, updater):
            store[key] = updater(store.get(key, {}))

        c = TorrentCleanup(
            priority_manager=priority, clear_download_pending_fn=clear_fn,
            task_data_update=update_fn, task_data_read=lambda k: store.get(k, {}),
            deletes_store=deletes, delete_torrent_fn=delete_fn, search_fn=search_fn,
            notify_fn=notify,
        )
        sub = _sub()
        c.handle_torrent_deleted(sub, "h1", reason="manual",
                                 downloader="qb", delete_from_downloader=False)
        deletes.save.assert_called_once()       # 删除指纹照常归档
        search_fn.assert_called_once_with(sub)   # 仍触发补搜
        delete_fn.assert_not_called()            # 不调下载器删种
        notify.assert_called_once()
        assert "订阅种子手动删除，已删除" in notify.call_args.args[0]

    def test_timeout_delete_also_skips_pause(self):
        """超时删除与 Tracker 删除也不暂停，避免补搜链路被 S 状态冻结。"""
        c = _cleanup()
        c.handle_torrent_deleted(_sub(), "h1", reason="timeout",
                                 downloader="qb", delete_from_downloader=True)
        assert not hasattr(c, "_pause")
