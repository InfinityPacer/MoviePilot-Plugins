"""download/monitor.py 超时检测单测。"""
import time
from types import SimpleNamespace
from unittest.mock import MagicMock

from subscribeassistantenhanced.download.monitor import DownloadMonitor, TIMEOUT_MANUAL_REVIEW_IGNORE_HOURS
from subscribeassistantenhanced.download.torrent import TorrentInfo
from subscribeassistantenhanced.pending.state import PendingStateCoordinator


def test_timeout_manual_review_ignore_hours_is_twenty_four():
    """连续超时人工保护期与通知文案保持一致。"""
    assert TIMEOUT_MANUAL_REVIEW_IGNORE_HOURS == 24


def _store_mgr(store=None):
    store = store if store is not None else {}
    return (
        lambda key: store.get(key, {}),
        lambda key, updater: store.__setitem__(key, updater(store.get(key, {}))),
        store,
    )


def _info(hash="h1", progress=0.5, completed=False, tags=None,
          tracker_responses=None):
    return TorrentInfo(
        hash=hash, progress=progress, completed=completed,
        tags=tags or [], tracker_responses=tracker_responses or [],
    )


class TestMarkDownloadPending:

    def test_marks_pending(self):
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update)
        mon.mark_download_pending(1, "hash1")
        assert mon.has_active_downloads(1) is True

    def test_clear_pending(self):
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update)
        mon.mark_download_pending(1, "hash1")
        mon.clear_download_pending(1, "hash1")
        assert mon.has_active_downloads(1) is False

    def test_no_pending_returns_false(self):
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update)
        assert mon.has_active_downloads(1) is False

    def test_hashless_pending_blocks_until_grace_expires(self, monkeypatch):
        """ResourceDownload 无 hash 待定在宽限期内阻止完成，超时后自动释放。"""
        read, update, store = _store_mgr()
        oper = MagicMock()
        coordinator = PendingStateCoordinator(read, update, subscribe_oper=oper)
        mon = DownloadMonitor(
            read, update,
            subscribe_oper=oper,
            state_coordinator=coordinator,
            pending_hash_grace_seconds=60,
        )
        monkeypatch.setattr("subscribeassistantenhanced.download.monitor.time.time", lambda: 100.0)
        subscribe = SimpleNamespace(id=1, name="测试剧", season=1, state="R")
        oper.get.return_value = SimpleNamespace(id=1, name="测试剧", season=1, state="P")

        mon.mark_download_started(
            subscribe,
            episodes=[1, 2],
            downloader="qb",
            enclosure="https://example/torrent",
            page_url="https://example/page",
            title="测试剧 S01E01-E02",
        )

        assert mon.has_active_downloads(1) is True
        task = store["subscribes"]["1"]
        assert task["state"] == "P"
        assert task["source"] == "download_pending"
        pending = task["download_pending"]
        pending_key = next(iter(pending))
        assert pending[pending_key]["hash"] is None
        assert pending[pending_key]["episodes"] == [1, 2]

        monkeypatch.setattr("subscribeassistantenhanced.download.monitor.time.time", lambda: 161.0)
        assert mon.has_active_downloads(1) is False
        assert store["subscribes"]["1"]["state"] == "R"

    def test_download_added_replaces_matching_hashless_pending(self, monkeypatch):
        """DownloadAdded 按 enclosure/page_url 补齐 ResourceDownload 建立的无 hash 待定。"""
        read, update, store = _store_mgr()
        oper = MagicMock()
        coordinator = PendingStateCoordinator(read, update, subscribe_oper=oper)
        mon = DownloadMonitor(read, update, subscribe_oper=oper, state_coordinator=coordinator)
        monkeypatch.setattr("subscribeassistantenhanced.download.monitor.time.time", lambda: 200.0)
        subscribe = SimpleNamespace(id=1, name="测试剧", season=1, state="R")
        oper.get.return_value = SimpleNamespace(id=1, name="测试剧", season=1, state="P")
        mon.mark_download_started(
            subscribe,
            episodes=[3],
            downloader="qb",
            enclosure="magnet:?xt=abc",
            page_url="https://example/detail",
            title="测试剧 S01E03",
        )

        mon.on_download(
            1,
            "hash-real",
            episodes=[3],
            downloader="qb",
            enclosure="magnet:?xt=abc",
            page_url="https://example/detail",
            title="测试剧 S01E03",
        )

        pending = store["subscribes"]["1"]["download_pending"]
        assert list(pending.keys()) == ["hash-real"]
        assert pending["hash-real"]["hash"] == "hash-real"
        assert pending["hash-real"]["started_at"] == 200.0
        assert store["torrents"]["hash-real"]["subscribe_id"] == 1

    def test_download_added_preserves_torrent_description(self):
        """DownloadAdded 保存种子描述，供后续监控和删种日志展示资源详情。"""
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update)

        mon.on_download(7, "h1", title="测试剧 S01E01", description="首集 1080p")

        assert store["torrents"]["h1"]["title"] == "测试剧 S01E01"
        assert store["torrents"]["h1"]["description"] == "首集 1080p"


class TestOnDownload:
    """DownloadAdded 登记种子监控条目。"""

    def test_registers_torrent_and_marks_pending(self):
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update)
        mon.on_download(7, "h1", episodes=[1, 2], downloader="qb", progress=0.1)
        entry = store["torrents"]["h1"]
        assert entry["subscribe_id"] == 7
        assert entry["episodes"] == [1, 2]
        assert entry["downloader"] == "qb"
        assert entry["baseline_progress"] == 0.1
        assert entry["retry_count"] == 0 and entry["manual_review_count"] == 0
        assert mon.has_active_downloads(7) is True

    def test_pending_disabled_registers_torrent_without_pending_marker(self):
        """关闭下载中待定后仍监控种子，但不写 download_pending 标记。"""
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update, pending_download_enabled=False)
        mon.on_download(7, "h1", episodes=[1, 2], downloader="qb", progress=0.1)

        assert store["torrents"]["h1"]["subscribe_id"] == 7
        assert mon.has_active_downloads(7) is False

    def test_no_hash_is_noop(self):
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update)
        mon.on_download(7, "", episodes=[1])
        assert store.get("torrents", {}) == {}
        assert mon.has_active_downloads(7) is False


class TestRunTimeoutCheck:
    """超时巡检：fetch 注入取实时状态，超时/Tracker 命中交 cleanup 善后。"""

    def test_no_fetch_fn_is_safe_noop(self):
        """未注入 fetch_fn → 不取实时数据、不判定、不删（安全空操作）。"""
        from unittest.mock import MagicMock
        read, update, _ = _store_mgr({"torrents": {"h1": {"subscribe_id": 1, "downloader": "qb"}}})
        mon = DownloadMonitor(read, update)
        cleanup = MagicMock()
        mon.run_timeout_check(cleanup)
        cleanup.handle_torrent_deleted.assert_not_called()

    def test_timeout_triggers_cleanup(self):
        """无进度且已超时、重试用尽 → check_torrent 判 timeout → cleanup 删种善后。"""
        from unittest.mock import MagicMock
        store = {"torrents": {"h1": {"subscribe_id": 1, "downloader": "qb",
                                     "baseline_progress": 0.0, "baseline_at": 0.0,
                                     "retry_count": 3, "manual_review_count": 0}}}
        read, update, _ = _store_mgr(store)
        sub = SimpleNamespace(id=1, best_version=0)
        oper = MagicMock()
        oper.get.return_value = sub
        mon = DownloadMonitor(read, update, retry_limit=3, subscribe_oper=oper,
                              fetch_fn=lambda dl, h: _info(hash=h, progress=0.0, completed=False))
        cleanup = MagicMock()
        mon.run_timeout_check(cleanup)
        cleanup.handle_torrent_deleted.assert_called_once()
        args, kwargs = cleanup.handle_torrent_deleted.call_args
        assert args == (sub, "h1")
        assert kwargs["reason"] == "timeout"
        assert kwargs["downloader"] == "qb"
        assert kwargs["delete_from_downloader"] is True
        assert "（低进度删除 1/3 次）" in kwargs["reason_detail"]


class TestCheckTorrent:

    def test_completed_returns_ok(self):
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update)
        result = mon.check_torrent(_info(completed=True), subscribe_id=1)
        assert result == "ok"

    def test_excluded_tag_returns_ignored(self):
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update, exclude_tags=["skip"])
        result = mon.check_torrent(_info(tags=["skip"]), subscribe_id=1)
        assert result == "ignored"

    def test_tracker_keyword_returns_delete(self):
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update, tracker_keywords=["unregistered"])
        info = _info(tracker_responses=["Torrent is unregistered"])
        result = mon.check_torrent(info, subscribe_id=1)
        assert result == "delete_tracker"

    def test_tracker_regex_keyword_returns_delete(self):
        """Tracker 关键字支持正则表达式，便于合并相近错误文本。"""
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update, tracker_keywords=[r"torrent\s+(?:is\s+)?not\s+registered"])
        info = _info(tracker_responses=["Tracker error: Torrent is not registered"])
        result = mon.check_torrent(info, subscribe_id=1)
        assert result == "delete_tracker"

    def test_invalid_tracker_regex_falls_back_to_text_contains(self):
        """非法正则按普通文本包含匹配处理，避免配置错误打断监控。"""
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update, tracker_keywords=["torrent [bad"])
        info = _info(tracker_responses=["Tracker error: torrent [bad"])
        result = mon.check_torrent(info, subscribe_id=1)
        assert result == "delete_tracker"

    def test_first_check_inits_task(self):
        read, update, store = _store_mgr()
        mon = DownloadMonitor(read, update, timeout_minutes=60)
        result = mon.check_torrent(_info(hash="new"), subscribe_id=1)
        assert result == "ok"
        assert "new" in store.get("torrents", {})

    def test_progress_refreshes_baseline(self):
        """进度变化 >= 阈值 → 刷新基线。"""
        store = {"torrents": {"h1": {
            "baseline_progress": 0.3, "baseline_at": time.time() - 7200,
            "retry_count": 0, "manual_review_count": 0,
        }}}
        read, update, _ = _store_mgr(store)
        mon = DownloadMonitor(read, update, progress_threshold=5)
        result = mon.check_torrent(_info(progress=0.4), subscribe_id=1)
        assert result == "ok"
        assert store["torrents"]["h1"]["baseline_progress"] == 0.4

    def test_no_progress_within_timeout_ok(self):
        """无进度但未超时 → ok。"""
        store = {"torrents": {"h1": {
            "baseline_progress": 0.5, "baseline_at": time.time() - 60,
            "retry_count": 0, "manual_review_count": 0,
        }}}
        read, update, _ = _store_mgr(store)
        mon = DownloadMonitor(read, update, timeout_minutes=60)
        result = mon.check_torrent(_info(progress=0.5), subscribe_id=1)
        assert result == "ok"

    def test_timeout_after_retries_exhausted(self):
        """低进度超时未达保护上限时直接删种。"""
        store = {"torrents": {"h1": {
            "baseline_progress": 0.5, "baseline_at": time.time() - 7200,
            "retry_count": 0, "manual_review_count": 0,
            "subscribe_id": 1, "episodes": [1],
        }}}
        read, update, _ = _store_mgr(store)
        oper = MagicMock()
        oper.get.return_value = SimpleNamespace(id=1, type="电视剧", season=None)
        mon = DownloadMonitor(read, update, timeout_minutes=60, retry_limit=3, subscribe_oper=oper)
        result = mon.check_torrent(_info(progress=0.5), subscribe_id=1)
        assert result == "timeout"
        state = store["subscribes"]["1"]["timeout_states"]["tv:unknown:1"]
        assert state["fail_count"] == 1
        reason = mon.get_timeout_reason(1, store["torrents"]["h1"], _info(progress=0.5))
        assert "超时窗口 1 小时内进度增长 0.00%" in reason
        assert "（低进度删除 1/3 次）" in reason

    def test_retry_increments_count(self):
        """低进度超时记录订阅范围失败次数，不刷新种子基线。"""
        now = time.time()
        store = {"torrents": {"h1": {
            "baseline_progress": 0.5, "baseline_at": now - 7200,
            "retry_count": 1, "manual_review_count": 0,
            "subscribe_id": 1, "episodes": [1],
        }}}
        read, update, _ = _store_mgr(store)
        oper = MagicMock()
        oper.get.return_value = SimpleNamespace(id=1, type="电视剧", season=None)
        mon = DownloadMonitor(read, update, timeout_minutes=60, retry_limit=3, subscribe_oper=oper)
        result = mon.check_torrent(_info(progress=0.5), subscribe_id=1)
        assert result == "timeout"
        assert store["torrents"]["h1"]["retry_count"] == 1
        assert store["torrents"]["h1"]["baseline_at"] == now - 7200

    def test_manual_review_after_timeout(self):
        """同一订阅/集数范围达到保护上限时保留种子，进入人工处理。"""
        store = {
            "torrents": {"h1": {
                "baseline_progress": 0.5, "baseline_at": time.time() - 7200,
                "retry_count": 0, "manual_review_count": 0,
                "subscribe_id": 1, "episodes": [1],
            }},
            "subscribes": {"1": {"timeout_states": {
                "tv:unknown:1": {"fail_count": 2, "window_start": time.time() - 60},
            }}},
        }
        read, update, _ = _store_mgr(store)
        oper = MagicMock()
        oper.get.return_value = SimpleNamespace(id=1, type="电视剧", season=None)
        mon = DownloadMonitor(read, update, timeout_minutes=60, retry_limit=3, subscribe_oper=oper)
        result = mon.check_torrent(_info(progress=0.5), subscribe_id=1)
        assert result == "manual_review"
        state = store["subscribes"]["1"]["timeout_states"]["tv:unknown:1"]
        assert state["fail_count"] == 3
        assert state["ignore_until"] > time.time()

    def test_timeout_count_is_scope_level_across_replaced_torrents(self):
        """连续低进度保护按订阅和集数范围累计，换种子后仍沿用同一范围计数。"""
        now = time.time()
        store = {
            "torrents": {"h2": {
                "baseline_progress": 0.5, "baseline_at": now - 7200,
                "subscribe_id": 1, "episodes": [1],
            }},
            "subscribes": {"1": {"timeout_states": {
                "tv:unknown:1": {"fail_count": 1, "last_torrent_hash": "h1", "window_start": now - 60},
            }}},
        }
        read, update, _ = _store_mgr(store)
        oper = MagicMock()
        oper.get.return_value = SimpleNamespace(id=1, type="电视剧", season=None)
        mon = DownloadMonitor(read, update, timeout_minutes=60, retry_limit=3, subscribe_oper=oper)

        result = mon.check_torrent(_info(hash="h2", progress=0.5), subscribe_id=1)

        assert result == "timeout"
        state = store["subscribes"]["1"]["timeout_states"]["tv:unknown:1"]
        assert state["fail_count"] == 2
        assert state["last_torrent_hash"] == "h2"

    def test_timeout_ignore_until_skips_same_torrent(self):
        """同一 hash 处于连续超时保护期时，本轮忽略且不继续累加失败次数。"""
        now = time.time()
        store = {
            "torrents": {"h1": {
                "baseline_progress": 0.5, "baseline_at": now - 7200,
                "subscribe_id": 1, "episodes": [1],
            }},
            "subscribes": {"1": {"timeout_states": {
                "tv:unknown:1": {
                    "fail_count": 3,
                    "last_torrent_hash": "h1",
                    "ignore_until": now + 3600,
                },
            }}},
        }
        read, update, _ = _store_mgr(store)
        oper = MagicMock()
        oper.get.return_value = SimpleNamespace(id=1, type="电视剧", season=None)
        mon = DownloadMonitor(read, update, timeout_minutes=60, retry_limit=3, subscribe_oper=oper)

        result = mon.check_torrent(_info(hash="h1", progress=0.5), subscribe_id=1)

        assert result == "ignored"
        assert store["subscribes"]["1"]["timeout_states"]["tv:unknown:1"]["fail_count"] == 3

    def test_timeout_after_ignore_expired_reenters_manual_review(self):
        """连续超时保护期过后仍低进度时重新进入人工处理，不直接删除当前种子。"""
        now = time.time()
        store = {
            "torrents": {"h1": {
                "baseline_progress": 0.5, "baseline_at": now - 7200,
                "subscribe_id": 1, "episodes": [1],
            }},
            "subscribes": {"1": {"timeout_states": {
                "tv:unknown:1": {
                    "fail_count": 3,
                    "last_torrent_hash": "h1",
                    "ignore_until": now - 1,
                    "window_start": now - 60,
                },
            }}},
        }
        read, update, _ = _store_mgr(store)
        oper = MagicMock()
        oper.get.return_value = SimpleNamespace(id=1, type="电视剧", season=None)
        mon = DownloadMonitor(read, update, timeout_minutes=60, retry_limit=3, subscribe_oper=oper)

        result = mon.check_torrent(_info(hash="h1", progress=0.5), subscribe_id=1)

        assert result == "manual_review"
        state = store["subscribes"]["1"]["timeout_states"]["tv:unknown:1"]
        assert state["fail_count"] == 4
        assert state["ignore_until"] > now

    def test_timeout_window_expired_resets_scope_count(self):
        """连续低进度统计窗口过期后，旧计数清零并从本次重新开始。"""
        now = time.time()
        store = {
            "torrents": {"h2": {
                "baseline_progress": 0.5, "baseline_at": now - 7200,
                "subscribe_id": 1, "episodes": [1],
            }},
            "subscribes": {"1": {"timeout_states": {
                "tv:unknown:1": {
                    "fail_count": 2,
                    "last_torrent_hash": "h1",
                    "window_start": now - 25 * 3600,
                },
            }}},
        }
        read, update, _ = _store_mgr(store)
        oper = MagicMock()
        oper.get.return_value = SimpleNamespace(id=1, type="电视剧", season=None)
        mon = DownloadMonitor(read, update, timeout_minutes=60, retry_limit=3, subscribe_oper=oper)

        result = mon.check_torrent(_info(hash="h2", progress=0.5), subscribe_id=1)

        assert result == "timeout"
        state = store["subscribes"]["1"]["timeout_states"]["tv:unknown:1"]
        assert state["fail_count"] == 1
        assert state["last_torrent_hash"] == "h2"


class TestManualDeleteListen:
    """下载器侧种子消失：区分'用户删种'(present=False) 与'下载器瞬断'(present=None)。"""

    def test_missing_torrent_releases_download_pending(self):
        """下载器确认种子已不存在时清理下载待定，避免已结束任务长期卡 P。"""
        read, update, store = _store_mgr({
            "torrents": {"h1": {"hash": "h1", "subscribe_id": 6, "downloader": "qb"}},
            "subscribes": {
                "6": {
                    "download_pending": {"h1": {"hash": "h1"}},
                    "pending_sources": {"download_pending": {"reason": "下载中"}},
                    "state": "P",
                    "source": "download_pending",
                    "reason": "下载中",
                }
            },
        })
        oper = MagicMock()
        oper.get.return_value = SimpleNamespace(id=6, name="测试剧", season=1, state="P")
        coordinator = PendingStateCoordinator(read, update, subscribe_oper=oper)
        mon = DownloadMonitor(read, update, subscribe_oper=oper,
                              state_coordinator=coordinator,
                              fetch_fn=lambda dl, h: None,
                              present_fn=lambda dl, h: False,
                              manual_delete_enabled=False,
                              manual_miss_threshold=1)

        mon.run_timeout_check(MagicMock())

        assert store["torrents"] == {}
        assert "download_pending" not in store["subscribes"]["6"]
        assert store["subscribes"]["6"]["state"] == "R"

    def test_missing_torrent_without_manual_listen_skips_miss_threshold(self):
        """关闭手动删除监听时本轮直接清理失效任务，不等待连续 miss 阈值。"""
        read, update, store = _store_mgr({
            "torrents": {"h1": {"hash": "h1", "subscribe_id": 6, "downloader": "qb"}},
            "subscribes": {"6": {"download_pending": {"h1": {"hash": "h1"}}}},
        })
        mon = DownloadMonitor(read, update,
                              fetch_fn=lambda dl, h: None,
                              present_fn=lambda dl, h: False,
                              manual_delete_enabled=False)
        cleanup = MagicMock()

        mon.run_timeout_check(cleanup)

        assert store["torrents"] == {}
        assert "download_pending" not in store["subscribes"]["6"]
        cleanup.handle_torrent_deleted.assert_not_called()

    def test_completed_torrent_releases_download_pending(self):
        """下载器返回已完成时移除下载任务并释放下载待定。"""
        read, update, store = _store_mgr({
            "torrents": {"h1": {"hash": "h1", "subscribe_id": 6, "downloader": "qb"}},
            "subscribes": {
                "6": {
                    "download_pending": {"h1": {"hash": "h1"}},
                    "pending_sources": {"download_pending": {"reason": "下载中"}},
                    "state": "P",
                    "source": "download_pending",
                    "reason": "下载中",
                }
            },
        })
        oper = MagicMock()
        oper.get.return_value = SimpleNamespace(id=6, name="测试剧", season=1, state="P")
        coordinator = PendingStateCoordinator(read, update, subscribe_oper=oper)
        mon = DownloadMonitor(read, update, subscribe_oper=oper,
                              state_coordinator=coordinator,
                              fetch_fn=lambda dl, h: _info(hash=h, completed=True),
                              manual_miss_threshold=1)

        mon.run_timeout_check(MagicMock())

        assert store["torrents"] == {}
        assert "download_pending" not in store["subscribes"]["6"]
        assert store["subscribes"]["6"]["state"] == "R"

    def test_pending_only_visible_torrent_does_not_write_timeout_state(self):
        """只做下载待定释放时，实时存在的未完成任务不参与超时/Tracker 异常判定。"""
        now = time.time()
        read, update, store = _store_mgr({
            "torrents": {
                "h1": {
                    "hash": "h1",
                    "subscribe_id": 6,
                    "downloader": "qb",
                    "episodes": [1],
                    "baseline_progress": 0.1,
                    "baseline_at": now - 7200,
                }
            },
            "subscribes": {
                "6": {
                    "download_pending": {"h1": {"hash": "h1"}},
                    "timeout_states": {},
                }
            },
        })
        cleanup = MagicMock()
        mon = DownloadMonitor(
            read, update,
            timeout_minutes=1,
            retry_limit=1,
            fetch_fn=lambda dl, h: _info(
                hash=h,
                progress=0.1,
                completed=False,
            ),
        )

        mon.run_timeout_check(None)

        assert store["torrents"]["h1"]["hash"] == "h1"
        assert store["subscribes"]["6"]["timeout_states"] == {}
        cleanup.handle_torrent_deleted.assert_not_called()

    def test_completed_torrent_log_includes_subscribe_episode_title_and_removed_count(self, monkeypatch):
        """完成任务日志应带订阅、集数、种子标题内容，并在汇总中展示本地移除数量。"""
        info_messages = []
        detail_messages = []
        monkeypatch.setattr("subscribeassistantenhanced.download.monitor.logger.info", info_messages.append)
        monkeypatch.setattr("subscribeassistantenhanced.download.monitor.detail", detail_messages.append)
        read, update, store = _store_mgr({
            "torrents": {
                "h1": {
                    "hash": "h1",
                    "subscribe_id": 6,
                    "downloader": "qb",
                    "episodes": [1, 2],
                    "title": "测试剧 S01E01-E02",
                    "description": "两集资源",
                }
            },
            "subscribes": {"6": {"download_pending": {"h1": {"hash": "h1"}}}},
        })
        oper = MagicMock()
        oper.get.return_value = SimpleNamespace(id=6, name="测试剧", season=1, state="P")
        mon = DownloadMonitor(
            read, update,
            subscribe_oper=oper,
            fetch_fn=lambda dl, h: _info(hash=h, completed=True),
        )

        mon.run_timeout_check(MagicMock())

        assert any(
            "测试剧 S1(id=6)" in message
            and "关联集数=1,2" in message
            and "测试剧 S01E01-E02 - 两集资源 (h1)" in message
            and "已完成" in message
            and "将从订阅下载任务中移除" in message
            for message in info_messages
        )
        assert any("从订阅下载任务移除 1 个" in message for message in detail_messages)

    def test_missing_torrent_with_reachable_downloader_triggers_manual_delete(self):
        """下载器可达且种子确实不存在（present=False）达阈值 → 按 manual 进入 cleanup。"""
        from unittest.mock import MagicMock
        read, update, _ = _store_mgr({"torrents": {"h1": {"hash": "h1", "subscribe_id": 6,
                                                          "downloader": "qb"}}})
        sub = SimpleNamespace(id=6)
        oper = MagicMock()
        oper.get.return_value = sub
        cleanup = MagicMock()
        mon = DownloadMonitor(read, update, subscribe_oper=oper,
                              fetch_fn=lambda dl, h: None,
                              present_fn=lambda dl, h: False,
                              manual_delete_enabled=True,
                              manual_miss_threshold=1)
        mon.run_timeout_check(cleanup)
        cleanup.handle_torrent_deleted.assert_called_once_with(
            sub, "h1", reason="manual", downloader="qb", delete_from_downloader=False)

    def test_unreachable_downloader_does_not_trigger_manual_delete(self):
        """下载器不可达/报错（present=None）→ 跳过，绝不触发 manual cleanup（瞬断保护回归）。"""
        from unittest.mock import MagicMock
        read, update, _ = _store_mgr({"torrents": {"h1": {"hash": "h1", "subscribe_id": 6,
                                                          "downloader": "qb"}}})
        cleanup = MagicMock()
        mon = DownloadMonitor(read, update, subscribe_oper=MagicMock(),
                              fetch_fn=lambda dl, h: None,
                              present_fn=lambda dl, h: None,
                              manual_delete_enabled=True,
                              manual_miss_threshold=1)
        mon.run_timeout_check(cleanup)
        cleanup.handle_torrent_deleted.assert_not_called()

    def test_uncertain_status_summary_breaks_down_reasons(self, monkeypatch):
        """实时状态缺失时按原因汇总，避免把所有跳过都写成下载器状态不确定。"""
        messages = []
        monkeypatch.setattr("subscribeassistantenhanced.download.monitor.detail", messages.append)
        read, update, _ = _store_mgr({
            "torrents": {
                "no-present-check": {"hash": "no-present-check", "subscribe_id": 6, "downloader": "qb"},
                "unknown-present": {"hash": "unknown-present", "subscribe_id": 7, "downloader": "tr"},
                "debounced": {"hash": "debounced", "subscribe_id": 8, "downloader": "qb"},
            }
        })

        mon = DownloadMonitor(
            read, update,
            fetch_fn=lambda dl, h: None,
            manual_delete_enabled=True,
            manual_miss_threshold=2,
        )
        mon.run_timeout_check(MagicMock())

        assert any(
            "未取到实时任务信息 3 个" in message
            and "缺少任务存在性确认能力 3 个" in message
            and "建议检查下载器连接、下载器别名配置和本轮任务是否刚被客户端刷新" in message
            for message in messages
        )

        def present(downloader, torrent_hash):
            if torrent_hash == "unknown-present":
                return None
            return False

        messages.clear()
        mon._present_fn = present
        mon.run_timeout_check(MagicMock())

        assert any(
            "未取到实时任务信息 3 个" in message
            and "无法确认任务是否仍存在 1 个" in message
            and "连续缺失未达阈值 2 个" in message
            and "因下载器状态不确定暂不处理" not in message
            for message in messages
        )

    def test_missing_torrent_debounced_until_threshold(self):
        """连续 miss 未达阈值不动手，达阈值才触发（去抖）。"""
        from unittest.mock import MagicMock
        read, update, _ = _store_mgr({"torrents": {"h1": {"hash": "h1", "subscribe_id": 6,
                                                          "downloader": "qb"}}})
        oper = MagicMock()
        oper.get.return_value = SimpleNamespace(id=6)
        cleanup = MagicMock()
        mon = DownloadMonitor(read, update, subscribe_oper=oper,
                              fetch_fn=lambda dl, h: None,
                              present_fn=lambda dl, h: False,
                              manual_delete_enabled=True,
                              manual_miss_threshold=2)
        mon.run_timeout_check(cleanup)        # 第一次 miss → 计数 1，不动手
        cleanup.handle_torrent_deleted.assert_not_called()
        mon.run_timeout_check(cleanup)        # 第二次 miss → 达阈值 2，触发
        cleanup.handle_torrent_deleted.assert_called_once()

    def test_same_subscribe_manual_delete_search_deduped_per_check(self):
        """同一轮同一订阅多个缺失种子都清理，但只允许首个触发补搜。"""
        read, update, _ = _store_mgr({
            "torrents": {
                "h1": {"hash": "h1", "subscribe_id": 6, "downloader": "qb"},
                "h2": {"hash": "h2", "subscribe_id": 6, "downloader": "qb"},
            }
        })
        sub = SimpleNamespace(id=6)
        oper = MagicMock()
        oper.get.return_value = sub
        cleanup = MagicMock()
        mon = DownloadMonitor(read, update, subscribe_oper=oper,
                              fetch_fn=lambda dl, h: None,
                              present_fn=lambda dl, h: False,
                              manual_delete_enabled=True,
                              manual_miss_threshold=1)

        mon.run_timeout_check(cleanup)

        assert cleanup.handle_torrent_deleted.call_count == 2
        cleanup.handle_torrent_deleted.assert_any_call(
            sub, "h1", reason="manual", downloader="qb", delete_from_downloader=False)
        cleanup.handle_torrent_deleted.assert_any_call(
            sub, "h2", reason="manual", downloader="qb", delete_from_downloader=False, search_enabled=False)
