"""事件处理器配置门控集成测试。"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.plugins.subscribeassistantenhanced.events import EventProxy
from app.plugins.subscribeassistantenhanced.lifecycle import LifecycleResult


def _sub(**kwargs):
    """构造完整订阅替身。"""
    defaults = dict(
        id=7,
        name="测试",
        tmdbid=100,
        season=1,
        episode_group=None,
        type="电视剧",
        best_version=0,
        best_version_full=0,
        total_episode=12,
        lack_episode=0,
    )
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def test_skip_deletion_controls_deleted_resource_filtering():
    """删除指纹过滤仅在 skip_deletion 开启时剔除候选。"""
    candidate = SimpleNamespace(
        torrent_info=SimpleNamespace(
            enclosure="http://x/deleted.torrent",
            page_url="http://x/details/1",
        )
    )
    deletes_store = MagicMock()
    deletes_store.match.return_value = True

    allowed_data = SimpleNamespace(
        contexts=[candidate],
        updated=False,
        updated_contexts=None,
        source="",
    )
    EventProxy(
        deletes_store=deletes_store,
        skip_deletion=False,
    ).on_resource_selection(SimpleNamespace(event_data=allowed_data))

    assert allowed_data.updated is False
    assert allowed_data.contexts == [candidate]

    filtered_data = SimpleNamespace(
        contexts=[candidate],
        updated=False,
        updated_contexts=None,
        source="",
    )
    EventProxy(
        deletes_store=deletes_store,
        skip_deletion=True,
    ).on_resource_selection(SimpleNamespace(event_data=filtered_data))

    assert filtered_data.updated is True
    assert filtered_data.updated_contexts == []


def test_resource_submit_cancels_deleted_hash_and_clears_hashless_pending():
    """ResourceSubmit 命中删除指纹时取消提交下载器，并清理 ResourceDownload 写下的无 hash 待定。"""
    subscribe = _sub(id=7, type="电影", season=None)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    deletes_store = MagicMock()
    deletes_store.match.return_value = True
    monitor = MagicMock()
    torrent_info = SimpleNamespace(
        enclosure="https://totheglory.im/dl/395931/8067",
        page_url="https://totheglory.im/t/395931/",
        title="Forgotten Island 2026 2160p-RiKKi",
    )
    submit_data = SimpleNamespace(
        origin='Subscribe|{"id": 7}',
        context=SimpleNamespace(torrent_info=torrent_info),
        hashes=["3db38150daf7c83acf17bb413d9e29c3c8a90efd"],
        user_specified=False,
        cancel=False,
        source="",
        reason="",
    )

    EventProxy(
        subscribe_oper=subscribe_oper,
        deletes_store=deletes_store,
        download_monitor=monitor,
        skip_deletion=True,
        pending_download_enabled=True,
    ).on_resource_submit(SimpleNamespace(event_data=submit_data))

    assert submit_data.cancel is True
    assert submit_data.source == "订阅助手（增强版）"
    assert "删除" in submit_data.reason
    deletes_store.match.assert_called_once_with(
        torrent_info=torrent_info,
        enclosure="https://totheglory.im/dl/395931/8067",
        page_url="https://totheglory.im/t/395931/",
        hashes=["3db38150daf7c83acf17bb413d9e29c3c8a90efd"],
    )
    monitor.clear_hashless_download_pending.assert_called_once_with(
        7,
        enclosure="https://totheglory.im/dl/395931/8067",
        page_url="https://totheglory.im/t/395931/",
        title="Forgotten Island 2026 2160p-RiKKi",
    )


def test_resource_submit_respects_user_specified_and_skip_deletion_switch():
    """用户手动指定下载或关闭跳过近期删除资源时，ResourceSubmit 不得拦截提交。"""
    subscribe = _sub(id=7, type="电影", season=None)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    deletes_store = MagicMock()
    deletes_store.match.return_value = True

    manual_data = SimpleNamespace(
        origin='Subscribe|{"id": 7}',
        context=SimpleNamespace(torrent_info=SimpleNamespace(enclosure="x", page_url="y")),
        hashes=["3db38150daf7c83acf17bb413d9e29c3c8a90efd"],
        user_specified=True,
        cancel=False,
        source="",
        reason="",
    )
    EventProxy(
        subscribe_oper=subscribe_oper,
        deletes_store=deletes_store,
        skip_deletion=True,
    ).on_resource_submit(SimpleNamespace(event_data=manual_data))
    assert manual_data.cancel is False

    disabled_data = SimpleNamespace(
        origin='Subscribe|{"id": 7}',
        context=SimpleNamespace(torrent_info=SimpleNamespace(enclosure="x", page_url="y")),
        hashes=["3db38150daf7c83acf17bb413d9e29c3c8a90efd"],
        user_specified=False,
        cancel=False,
        source="",
        reason="",
    )
    EventProxy(
        subscribe_oper=subscribe_oper,
        deletes_store=deletes_store,
        skip_deletion=False,
    ).on_resource_submit(SimpleNamespace(event_data=disabled_data))
    assert disabled_data.cancel is False
    deletes_store.match.assert_not_called()


def test_resource_submit_handles_noop_guards_and_real_monitor_pending_cleanup():
    """已取消、非订阅、未命中时安全放行；取消提交时真实清理无 hash 下载待定并通知状态协调器。"""
    from app.plugins.subscribeassistantenhanced.download.monitor import DownloadMonitor

    store = {"subscribes": {}, "torrents": {}}
    read = lambda key: store.get(key, {})
    update = lambda key, fn: store.__setitem__(key, fn(dict(store.get(key, {}))))

    subscribe = _sub(id=7, type="电影", season=None)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    state_coordinator = MagicMock()
    monitor = DownloadMonitor(
        read,
        update,
        subscribe_oper=subscribe_oper,
        state_coordinator=state_coordinator,
        pending_download_enabled=True,
    )
    monitor.mark_download_started(
        subscribe,
        episodes=[],
        downloader="qb",
        enclosure="https://totheglory.im/dl/395931/8067",
        page_url="https://totheglory.im/t/395931/",
        title="Forgotten Island 2026",
    )
    assert "7" in store["subscribes"]

    # 取消前先验证未命中、已取消、非订阅与缺 deletes_store 分支均不误拦
    EventProxy(subscribe_oper=subscribe_oper, skip_deletion=True).on_resource_submit(
        SimpleNamespace(event_data=SimpleNamespace(cancel=False, user_specified=False, origin='Subscribe|{"id": 7}'))
    )
    deletes_store = MagicMock()
    deletes_store.match.return_value = False
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        deletes_store=deletes_store,
        download_monitor=monitor,
        skip_deletion=True,
        pending_download_enabled=True,
    )
    already_cancelled = SimpleNamespace(cancel=True)
    proxy.on_resource_submit(SimpleNamespace(event_data=already_cancelled))
    non_sub = SimpleNamespace(
        origin="Manual",
        context=SimpleNamespace(torrent_info=None),
        hashes=["h1"],
        user_specified=False,
        cancel=False,
    )
    proxy.on_resource_submit(SimpleNamespace(event_data=non_sub))
    not_matched = SimpleNamespace(
        origin='Subscribe|{"id": 7}',
        context=SimpleNamespace(torrent_info=SimpleNamespace(enclosure="https://other/a", page_url=None, title="Other")),
        hashes=["h-other"],
        user_specified=False,
        cancel=False,
    )
    proxy.on_resource_submit(SimpleNamespace(event_data=not_matched))
    assert not_matched.cancel is False

    # 命中后取消并清理无 hash 下载待定
    deletes_store.match.return_value = True
    matched = SimpleNamespace(
        origin='Subscribe|{"id": 7}',
        context=SimpleNamespace(
            torrent_info=SimpleNamespace(
                enclosure="https://totheglory.im/dl/395931/8067",
                page_url="https://totheglory.im/t/395931/",
                title="Forgotten Island 2026",
            )
        ),
        hashes=["3db38150daf7c83acf17bb413d9e29c3c8a90efd"],
        user_specified=False,
        cancel=False,
        source="",
        reason="",
    )
    proxy.on_resource_submit(SimpleNamespace(event_data=matched))
    assert matched.cancel is True
    assert "download_pending" not in store["subscribes"].get("7", {})
    state_coordinator.clear_active.assert_called_once()

    # 另有一条待定时只删除取消的那条，不误清其他待定；并验证 DownloadAdded 持久化站点与规范化身份
    monitor.mark_download_started(subscribe, title="OnlyTitleA")
    monitor.mark_download_started(subscribe, title="OnlyTitleB")
    monitor.clear_hashless_download_pending(7, title="OnlyTitleA")
    assert len(store["subscribes"]["7"]["download_pending"]) == 1

    deletes_store.resolve_identities.return_value = ["site:2|id=395931", "host:totheglory.im|id=395931"]
    proxy.on_download_added(SimpleNamespace(event_data={
        "source": 'Subscribe|{"id": 7}',
        "hash": "3db38150daf7c83acf17bb413d9e29c3c8a90efd",
        "episodes": [],
        "downloader": "qb",
        "context": SimpleNamespace(
            torrent_info=SimpleNamespace(
                site=2,
                site_name="听听歌",
                enclosure="https://totheglory.im/dl/395931/8067",
                page_url="https://totheglory.im/t/395931/",
                title="Forgotten Island 2026",
                description="Remux",
            )
        ),
    }))
    saved = store["torrents"]["3db38150daf7c83acf17bb413d9e29c3c8a90efd"]
    assert saved["site"] == 2
    assert saved["site_name"] == "听听歌"
    assert saved["resource_identities"] == ["site:2|id=395931", "host:totheglory.im|id=395931"]


def test_on_subscribe_added_delegates_lifecycle_with_mediainfo():
    """SubscribeAdded 只负责取订阅和媒体信息，状态流转交给 lifecycle。"""
    subscribe = _sub(season=0, type="电影")
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    lifecycle = MagicMock()
    mediainfo = SimpleNamespace(type="movie")
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        lifecycle=lifecycle,
        mediainfo_from_dict=lambda _data: mediainfo,
    )

    proxy.on_subscribe_added(
        SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {"release_date": "2026-08-01"}})
    )

    lifecycle.handle_subscribe_added.assert_called_once_with(subscribe, mediainfo)


def test_on_subscribe_added_missing_mediainfo_skips_lifecycle():
    """事件缺少媒体信息时不进入 lifecycle，避免生命周期层收到无效上下文。"""
    subscribe = _sub()
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    lifecycle = MagicMock()
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        lifecycle=lifecycle,
        mediainfo_from_dict=lambda _data: None,
    )

    proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": None}))

    lifecycle.handle_subscribe_added.assert_not_called()


def test_subscribe_modified_skips_backfill_when_disabled():
    """关闭回填开关时，普通转洗版不写入已有集优先级。"""
    subscribe = _sub(best_version=1)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    priority_manager = MagicMock()
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        priority_manager=priority_manager,
        detect_existing_episodes_fn=MagicMock(return_value=[3]),
        backfill_enabled=False,
    )

    proxy.on_subscribe_modified(SimpleNamespace(event_data={
        "subscribe_id": 7,
        "subscribe_info": {"best_version": 1},
        "old_subscribe_info": {"best_version": 0},
    }))

    priority_manager.backfill_existing.assert_not_called()


def test_subscribe_modified_backfills_existing_episodes_when_enabled():
    """开启回填开关时，普通转洗版为媒体库已有集写入优先级。"""
    subscribe = _sub(best_version=1)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    priority_manager = MagicMock()
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        priority_manager=priority_manager,
        detect_existing_episodes_fn=MagicMock(return_value=[3]),
        backfill_enabled=True,
    )

    proxy.on_subscribe_modified(SimpleNamespace(event_data={
        "subscribe_id": 7,
        "subscribe_info": {"best_version": 1},
        "old_subscribe_info": {"best_version": 0},
    }))

    priority_manager.backfill_existing.assert_called_once_with(
        subscribe, [3], scene="plugin_backfill<订阅助手（增强版）>"
    )


def test_subscribe_added_backfills_episode_best_version():
    """新建分集洗版订阅先回填媒体库已有集，再交给 lifecycle。"""
    call_order = []
    subscribe = _sub(best_version=1)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    priority_manager = MagicMock()
    priority_manager.can_backfill.return_value = True
    priority_manager.backfill_existing.side_effect = lambda *_args, **_kwargs: call_order.append("backfill")
    lifecycle = MagicMock()
    lifecycle.handle_subscribe_added.side_effect = lambda *_args, **_kwargs: call_order.append("lifecycle")
    mediainfo = SimpleNamespace(type="tv")
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        priority_manager=priority_manager,
        detect_existing_episodes_fn=MagicMock(return_value=[1, 2]),
        backfill_enabled=True,
        lifecycle=lifecycle,
        mediainfo_from_dict=lambda _data: mediainfo,
    )

    proxy.on_subscribe_added(SimpleNamespace(event_data={"subscribe_id": 7, "mediainfo": {}}))

    priority_manager.backfill_existing.assert_called_once_with(
        subscribe, [1, 2], scene="plugin_backfill<订阅助手（增强版）>"
    )
    lifecycle.handle_subscribe_added.assert_called_once_with(subscribe, mediainfo)
    assert call_order == ["backfill", "lifecycle"]


def test_download_added_records_monitor_then_lifecycle_and_notifies_once():
    """DownloadAdded 先登记下载事实，再按 lifecycle 结果发送一次恢复通知。"""
    call_order = []
    subscribe = _sub(state="S")
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    monitor = MagicMock()
    monitor.on_download.side_effect = lambda *_args, **_kwargs: call_order.append("monitor")
    lifecycle = MagicMock()
    lifecycle.handle_download_added_for_subscribe.side_effect = (
        lambda _subscribe: call_order.append("lifecycle")
        or LifecycleResult(changed=True, state="R", reason="pre_air")
    )
    notify_fn = MagicMock(side_effect=lambda *_args, **_kwargs: call_order.append("notify"))
    torrent_info = SimpleNamespace(
        enclosure="magnet:?xt=abc",
        page_url="https://example/detail",
        title="测试剧 S01E01",
        description="首集 1080p",
    )
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        download_monitor=monitor,
        lifecycle=lifecycle,
        notify_fn=notify_fn,
    )

    proxy.on_download_added(SimpleNamespace(event_data={
        "source": 'Subscribe|{"id": 7}',
        "hash": "hash1",
        "episodes": [1],
        "downloader": "qb",
        "context": SimpleNamespace(torrent_info=torrent_info),
    }))

    assert call_order == ["monitor", "lifecycle", "notify"]
    monitor.on_download.assert_called_once_with(
        7,
        "hash1",
        episodes=[1],
        downloader="qb",
        enclosure="magnet:?xt=abc",
        page_url="https://example/detail",
        title="测试剧 S01E01",
        description="首集 1080p",
    )
    lifecycle.handle_download_added_for_subscribe.assert_called_once_with(subscribe)
    notify_fn.assert_called_once()


def test_transfer_complete_clears_pending_then_lifecycle_then_best_version_conversion():
    """TransferComplete 先释放下载待定，再进入 lifecycle，分集转全集仍由事件层补偿。"""
    call_order = []
    subscribe = _sub(best_version=1, best_version_full=0, lack_episode=0)
    subscribe_oper = MagicMock()
    subscribe_oper.get.return_value = subscribe
    task_manager = MagicMock()
    task_manager.read.return_value = {"hash1": {"subscribe_id": 7}}
    task_manager.clean_torrent_tasks.side_effect = lambda _hash: call_order.append("clean")
    monitor = MagicMock()
    monitor.clear_download_pending.side_effect = lambda *_args: call_order.append("clear")
    lifecycle = MagicMock()
    lifecycle.handle_library_updated.side_effect = lambda _subscribe_id: call_order.append("lifecycle")
    convert = MagicMock(side_effect=lambda *_args, **_kwargs: call_order.append("convert"))
    proxy = EventProxy(
        subscribe_oper=subscribe_oper,
        task_manager=task_manager,
        download_monitor=monitor,
        lifecycle=lifecycle,
        convert_episode_best_version_to_full_fn=convert,
    )

    proxy.on_transfer_complete(SimpleNamespace(event_data={
        "download_hash": "hash1",
        "transferinfo": SimpleNamespace(transfer_type="move"),
    }))

    assert call_order == ["clear", "clean", "lifecycle", "convert"]
    monitor.clear_download_pending.assert_called_once_with(7, "hash1")
    task_manager.clean_torrent_tasks.assert_called_once_with("hash1")
    lifecycle.handle_library_updated.assert_called_once_with(7)
    convert.assert_called_once_with(7, trigger="TransferComplete")
