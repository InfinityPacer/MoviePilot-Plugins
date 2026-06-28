"""
SubscribeAssistant P1 事件处理器单测。

覆盖订阅、下载、资源选择/下载、整理和插件动作事件的 guard 条件与委托副作用。
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.schemas.types import MediaType
from subscribeassistant import SubscribeAssistant

TV = MediaType.TV.value


def make_plugin(**overrides) -> SubscribeAssistant:
    """构造事件处理器需要的插件实例。"""
    plugin = object.__new__(SubscribeAssistant)
    plugin.plugin_name = "订阅助手"
    plugin.subscribe_oper = MagicMock()
    plugin.post_message = MagicMock()
    plugin._auto_tv_pending = False
    plugin._auto_pause = False
    plugin._auto_best_backfill_priority = False
    plugin._auto_best_types = set()
    plugin._auto_download_delete = False
    plugin._manual_delete_listen = False
    plugin._tracker_response_listen = False
    plugin._auto_download_pending = False
    plugin._skip_deletion = False
    for key, value in overrides.items():
        setattr(plugin, key, value)
    return plugin


def event(data):
    """构造 Event 替身。"""
    return SimpleNamespace(event_data=data)


def make_subscribe(**kwargs) -> SimpleNamespace:
    """构造事件处理中常用订阅对象。"""
    base = dict(id=1, name="测试剧", year="2024", type=TV, season=1, episode_group=None,
                tmdbid=100, doubanid=None, imdbid=None, tvdbid=None, bangumiid=None,
                best_version=0, state="R", username="u", backdrop=None, poster=None)
    base.update(kwargs)
    return SimpleNamespace(**base)


def make_context() -> SimpleNamespace:
    """构造包含种子信息的资源上下文。"""
    return SimpleNamespace(
        torrent_info=SimpleNamespace(
            site=1, site_name="站点", title="标题", description="副标题",
            enclosure="http://e/1.torrent", page_url="http://e/page", pri_order=80,
            category=None,
        ),
        resource_source="rss", match_source="title", candidate_recognized=False,
        media_info_is_target=True, media_info=None,
    )


def make_context_with_title(title: str) -> SimpleNamespace:
    """构造指定标题的资源上下文。"""
    context = make_context()
    context.torrent_info.title = title
    return context


class EventHandlersTest:
    """事件入口 guard 与委托调用。"""

    def test_subscribe_deleted_ignores_empty_event(self):
        plugin = make_plugin()
        with patch.object(plugin, "clear_tasks") as clear:
            plugin.handle_subscribe_deleted_event(None)
        clear.assert_not_called()

    def test_subscribe_deleted_clears_tasks(self):
        plugin = make_plugin()
        with patch.object(plugin, "clear_tasks") as clear:
            plugin.handle_subscribe_deleted_event(event({"subscribe_id": 1, "subscribe_info": {"id": 1}}))
        clear.assert_called_once_with(subscribe_id=1, subscribe={"id": 1})

    def test_subscribe_deleted_handles_clear_exception(self):
        plugin = make_plugin()
        with patch.object(plugin, "clear_tasks", side_effect=RuntimeError("boom")) as clear:
            plugin.handle_subscribe_deleted_event(event({"subscribe_id": 1, "subscribe_info": {"id": 1}}))
        clear.assert_called_once()

    def test_subscribe_added_skips_when_event_data_missing_required_fields(self):
        plugin = make_plugin()
        plugin.subscribe_oper.get.return_value = make_subscribe()
        plugin.handle_subscribe_added_event(event({"subscribe_id": 1}))
        plugin.subscribe_oper.get.assert_not_called()

    def test_subscribe_added_skips_empty_event(self):
        plugin = make_plugin(_auto_tv_pending=True, _auto_pause=True)
        plugin.handle_subscribe_added_event(None)
        plugin.handle_subscribe_added_event(event(None))
        plugin.subscribe_oper.get.assert_not_called()

    def test_subscribe_added_runs_backfill_before_auto_pause_short_circuit(self):
        plugin = make_plugin(_auto_best_backfill_priority=True)
        plugin.subscribe_oper.get.return_value = make_subscribe(best_version=1)
        with patch.object(plugin, "_SubscribeAssistant__should_backfill_priority", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__backfill_best_version_episode_priority") as backfill:
            plugin.handle_subscribe_added_event(event({
                "subscribe_id": 1, "username": "u",
                "mediainfo": {"title": "测试剧", "type": MediaType.TV.value, "tmdb_id": 100},
            }))
        backfill.assert_called_once()

    def test_subscribe_added_handles_backfill_exception_and_short_circuits_when_features_off(self):
        plugin = make_plugin(_auto_best_backfill_priority=True)
        plugin.subscribe_oper.get.return_value = make_subscribe(best_version=1)
        with patch.object(plugin, "_SubscribeAssistant__should_backfill_priority", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__backfill_best_version_episode_priority",
                             side_effect=RuntimeError("boom")) as backfill:
            plugin.handle_subscribe_added_event(event({
                "subscribe_id": 1, "username": "u",
                "mediainfo": {"title": "测试剧", "type": MediaType.TV.value, "tmdb_id": 100},
            }))
        backfill.assert_called_once()

    def test_subscribe_added_calls_pause_and_pending_for_normal_subscription(self):
        plugin = make_plugin(_auto_tv_pending=True, _auto_pause=True)
        plugin.subscribe_oper.get.return_value = make_subscribe(best_version=0)
        with patch.object(plugin, "process_subscribe_pause_for_user") as pause_user, \
                patch.object(plugin, "process_subscribe_pause") as pause, \
                patch.object(plugin, "process_tv_pending") as pending:
            plugin.handle_subscribe_added_event(event({
                "subscribe_id": 1, "username": "u",
                "mediainfo": {"title": "测试剧", "type": MediaType.TV.value, "tmdb_id": 100},
            }))
        pause_user.assert_called_once_with(subscribe_id=1)
        pause.assert_called_once_with(subscribe_id=1)
        pending.assert_called_once_with(subscribe_id=1)

    def test_subscribe_added_logs_when_subscribe_readback_missing(self):
        plugin = make_plugin(_auto_tv_pending=True, _auto_pause=True)
        plugin.subscribe_oper.get.return_value = None
        with patch.object(plugin, "process_subscribe_pause") as pause:
            plugin.handle_subscribe_added_event(event({
                "subscribe_id": 1, "username": "u",
                "mediainfo": {"title_year": "测试剧 (2024)", "type": MediaType.TV.value, "tmdb_id": 100},
            }))
        pause.assert_not_called()

    def test_subscribe_added_skips_normal_processing_for_best_version(self):
        plugin = make_plugin(_auto_tv_pending=True, _auto_pause=True)
        plugin.subscribe_oper.get.return_value = make_subscribe(best_version=1)
        with patch.object(plugin, "process_tv_pending") as pending:
            plugin.handle_subscribe_added_event(event({
                "subscribe_id": 1, "username": "u",
                "mediainfo": {"title": "测试剧", "type": MediaType.TV.value, "tmdb_id": 100},
            }))
        pending.assert_not_called()

    def test_subscribe_added_skips_when_pending_and_pause_disabled_after_optional_backfill(self):
        plugin = make_plugin(_auto_tv_pending=False, _auto_pause=False, _auto_best_backfill_priority=False)
        plugin.subscribe_oper.get.return_value = make_subscribe(best_version=0)
        with patch.object(plugin, "process_tv_pending") as pending:
            plugin.handle_subscribe_added_event(event({
                "subscribe_id": 1, "username": "u",
                "mediainfo": {"title": "测试剧", "type": MediaType.TV.value, "tmdb_id": 100},
            }))
        pending.assert_not_called()

    def test_subscribe_added_handles_missing_subscribe_after_mediainfo_parsed(self):
        plugin = make_plugin(_auto_tv_pending=True, _auto_pause=True)
        plugin.subscribe_oper.get.return_value = None
        with patch.object(plugin, "process_tv_pending") as pending:
            plugin.handle_subscribe_added_event(event({
                "subscribe_id": 1, "username": "u",
                "mediainfo": {"title": "测试剧", "type": MediaType.TV.value, "tmdb_id": 100},
            }))
        pending.assert_not_called()

    def test_subscribe_modified_skips_when_old_info_missing(self):
        plugin = make_plugin()
        with patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as locked:
            plugin.handle_subscribe_modified_event(event({"subscribe_id": 1, "subscribe_info": {"id": 1}}))
        locked.assert_not_called()

    def test_subscribe_modified_skips_empty_event(self):
        plugin = make_plugin()
        with patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as locked:
            plugin.handle_subscribe_modified_event(None)
            plugin.handle_subscribe_modified_event(event(None))
        locked.assert_not_called()

    def test_subscribe_modified_triggers_backfill_on_best_version_edge(self):
        plugin = make_plugin(_auto_best_backfill_priority=True)
        plugin.subscribe_oper.get.return_value = make_subscribe(best_version=1)
        with patch.object(plugin, "_SubscribeAssistant__should_backfill_priority", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__backfill_best_version_episode_priority") as backfill, \
                patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks"):
            plugin.handle_subscribe_modified_event(event({
                "subscribe_id": 1,
                "subscribe_info": {"id": 1, "username": "u", "best_version": 1, "state": "R"},
                "old_subscribe_info": {"id": 1, "best_version": 0, "state": "R"},
            }))
        backfill.assert_called_once()
        assert backfill.call_args.kwargs.get("scene") is None

    def test_subscribe_modified_keeps_reset_when_backfill_raises(self):
        plugin = make_plugin(_auto_best_backfill_priority=True)
        plugin.subscribe_oper.get.return_value = make_subscribe(best_version=1)
        with patch.object(plugin, "_SubscribeAssistant__should_backfill_priority", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__backfill_best_version_episode_priority",
                             side_effect=RuntimeError("boom")) as backfill, \
                patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as locked:
            plugin.handle_subscribe_modified_event(event({
                "subscribe_id": 1,
                "subscribe_info": {"id": 1, "username": "u", "best_version": 1, "state": "R"},
                "old_subscribe_info": {"id": 1, "best_version": 0, "state": "R"},
            }))
        backfill.assert_called_once()
        locked.assert_called_once()

    def test_subscribe_modified_reset_backfills_with_reset_scene(self):
        plugin = make_plugin(_auto_best_backfill_priority=True)
        plugin.subscribe_oper.get.return_value = make_subscribe(best_version=1)
        with patch.object(plugin, "_SubscribeAssistant__should_backfill_priority", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__backfill_best_version_episode_priority") as backfill, \
                patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as locked:
            plugin.handle_subscribe_modified_event(event({
                "subscribe_id": 1,
                "scene": "reset",
                "fields": ["note", "lack_episode", "episode_priority", "state"],
                "subscribe_info": {"id": 1, "username": "u", "best_version": 1, "state": "R", "note": []},
                "old_subscribe_info": {
                    "id": 1, "best_version": 1, "state": "R", "note": [1],
                    "episode_priority": {"1": 100},
                },
            }))

        backfill.assert_called_once_with(
            subscribe=plugin.subscribe_oper.get.return_value,
            scene="reset_backfill",
        )
        locked.assert_called_once()

    def test_subscribe_modified_without_reset_scene_does_not_guess_reset(self):
        plugin = make_plugin(_auto_best_backfill_priority=True)
        plugin.subscribe_oper.get.return_value = make_subscribe(best_version=1)
        with patch.object(plugin, "_SubscribeAssistant__should_backfill_priority", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__backfill_best_version_episode_priority") as backfill, \
                patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as locked:
            plugin.handle_subscribe_modified_event(event({
                "subscribe_id": 1,
                "fields": ["note", "lack_episode", "episode_priority", "state"],
                "subscribe_info": {"id": 1, "username": "u", "best_version": 1, "state": "R", "note": []},
                "old_subscribe_info": {
                    "id": 1, "best_version": 1, "state": "R", "note": [1],
                    "episode_priority": {"1": 100},
                },
            }))

        backfill.assert_not_called()
        locked.assert_called_once()

    def test_subscribe_modified_resets_task_state_with_changed_keys(self):
        plugin = make_plugin()
        plugin.subscribe_oper.get.return_value = make_subscribe()
        with patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as locked:
            plugin.handle_subscribe_modified_event(event({
                "subscribe_id": 1,
                "subscribe_info": {"id": 1, "username": "u", "best_version": 0, "state": "S"},
                "old_subscribe_info": {"id": 1, "best_version": 0, "state": "R"},
            }))
        assert locked.call_args.kwargs["subscribe"].id == 1
        assert locked.call_args.kwargs["different_keys"] == {"state"}

    def test_subscribe_complete_clears_tasks_and_skips_when_auto_best_disabled(self):
        plugin = make_plugin(_auto_best_types=set())
        with patch.object(plugin, "clear_tasks") as clear, patch.object(plugin, "process_best_version") as process:
            plugin.handle_subscribe_complete_event(event({"subscribe_id": 1, "subscribe_info": {"id": 1}}))
        clear.assert_called_once()
        process.assert_not_called()

    def test_subscribe_complete_skips_empty_event_and_missing_payload_when_auto_best_enabled(self):
        plugin = make_plugin(_auto_best_types={MediaType.TV})
        with patch.object(plugin, "clear_tasks") as clear, patch.object(plugin, "process_best_version") as process:
            plugin.handle_subscribe_complete_event(None)
            plugin.handle_subscribe_complete_event(event({"subscribe_id": 1, "subscribe_info": {"id": 1}}))
        clear.assert_called_once_with(subscribe_id=1, subscribe={"id": 1})
        process.assert_not_called()

    def test_subscribe_complete_processes_best_version_when_enabled(self):
        plugin = make_plugin(_auto_best_types={"movie"})
        with patch.object(plugin, "clear_tasks"), patch.object(plugin, "process_best_version") as process:
            plugin.handle_subscribe_complete_event(event({
                "subscribe_id": 1,
                "subscribe_info": {"id": 1, "name": "测试剧", "type": TV},
                "mediainfo": {"title": "测试剧", "type": MediaType.TV.value, "tmdb_id": 100},
            }))
        process.assert_called_once()

    def test_subscribe_complete_handles_process_exception(self):
        plugin = make_plugin(_auto_best_types={MediaType.TV})
        with patch.object(plugin, "clear_tasks"), \
                patch.object(plugin, "process_best_version", side_effect=RuntimeError("boom")) as process:
            plugin.handle_subscribe_complete_event(event({
                "subscribe_id": 1,
                "subscribe_info": {"id": 1, "name": "测试剧", "year": "2024", "type": TV},
                "mediainfo": {"title": "测试剧", "type": MediaType.TV.value, "tmdb_id": 100},
            }))
        process.assert_called_once()

    def test_download_added_returns_when_features_disabled(self):
        plugin = make_plugin()
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source") as get_source:
            plugin.handle_download_added_event(event({"hash": "h1"}))
        get_source.assert_not_called()

    def test_download_added_skips_empty_event(self):
        plugin = make_plugin(_auto_download_delete=True)
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source") as get_source:
            plugin.handle_download_added_event(None)
            plugin.handle_download_added_event(event(None))
        get_source.assert_not_called()

    def test_download_added_skips_when_source_not_subscription(self):
        plugin = make_plugin(_auto_download_delete=True)
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source", return_value=(None, None)) as get_source:
            plugin.handle_download_added_event(event({"hash": "h1", "context": make_context(), "source": "bad"}))
        get_source.assert_called_once_with(source="bad")

    def test_download_added_skips_when_downloader_service_missing(self):
        plugin = make_plugin(_auto_download_delete=True)
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source",
                          return_value=({"id": 1}, make_subscribe())), \
                patch.object(plugin, "_SubscribeAssistant__get_downloader_service", return_value=None), \
                patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as locked:
            plugin.handle_download_added_event(event({
                "hash": "h1", "context": make_context(), "downloader": "missing", "source": "subscribe|1",
            }))
        locked.assert_not_called()

    def test_download_added_skips_when_hash_or_context_missing(self):
        plugin = make_plugin(_auto_download_delete=True)
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source",
                          return_value=({"id": 1}, make_subscribe())), \
                patch.object(plugin, "_SubscribeAssistant__get_downloader_service",
                             return_value=SimpleNamespace(instance=MagicMock(), type="qbittorrent")), \
                patch.object(plugin, "_SubscribeAssistant__get_torrents") as get_torrents:
            plugin.handle_download_added_event(event({
                "hash": "", "context": make_context(), "downloader": "qb", "source": "subscribe|1",
            }))
        get_torrents.assert_not_called()

    def test_download_added_skips_when_downloader_cannot_find_torrent(self):
        plugin = make_plugin(_auto_download_delete=True)
        service = SimpleNamespace(instance=MagicMock(), type="qbittorrent")
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source",
                          return_value=({"id": 1}, make_subscribe())), \
                patch.object(plugin, "_SubscribeAssistant__get_downloader_service", return_value=service), \
                patch.object(plugin, "_SubscribeAssistant__get_torrents", return_value=None), \
                patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as locked:
            plugin.handle_download_added_event(event({
                "hash": "h1", "context": make_context(), "downloader": "qb", "source": "subscribe|1",
            }))
        locked.assert_not_called()

    def test_download_added_updates_subscribe_and_torrent_tasks(self):
        plugin = make_plugin(_auto_download_delete=True, _auto_download_pending=True)
        subscribe = make_subscribe(best_version=1)
        service = SimpleNamespace(instance=MagicMock(), type="qbittorrent")
        torrent = {"hash": "h1", "downloaded": 10, "target_size": 100}
        captured_torrent_update = {}

        def torrent_lock(method, **kwargs):
            method(captured_torrent_update)

        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source",
                          return_value=({"id": 1}, subscribe)), \
                patch.object(plugin, "_SubscribeAssistant__get_downloader_service", return_value=service), \
                patch.object(plugin, "_SubscribeAssistant__get_torrents", return_value=torrent), \
                patch.object(plugin, "_SubscribeAssistant__get_torrent_info",
                             return_value={"downloaded": 10, "target_size": 100}), \
                patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as sub_lock, \
                patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_torrent_tasks",
                             side_effect=torrent_lock), \
                patch.object(plugin, "_SubscribeAssistant__ensure_download_pending_state") as ensure:
            plugin.handle_download_added_event(event({
                "hash": "h1", "context": make_context(), "downloader": "qb",
                "episodes": [1], "username": "u", "source": "subscribe|1",
            }))
        sub_lock.assert_called_once()
        assert "h1" in captured_torrent_update
        ensure.assert_called_once_with(subscribe=subscribe, reason="下载添加成功，确认下载待定")

    def test_resource_selection_skips_without_contexts(self):
        plugin = make_plugin()
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source") as get_source:
            plugin.handle_resource_selection_event(event(SimpleNamespace(contexts=[])))
        get_source.assert_not_called()

    def test_resource_selection_applies_guard_after_source_match(self):
        plugin = make_plugin(_skip_deletion=False)
        event_data = SimpleNamespace(contexts=[make_context()], origin="subscribe|1",
                                     updated=False, updated_contexts=None, source=None)
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source",
                          return_value=({"id": 1}, make_subscribe())), \
                patch.object(plugin, "_SubscribeAssistant__apply_recognition_guard_selection") as guard:
            plugin.handle_resource_selection_event(event(event_data))
        guard.assert_called_once()

    def test_resource_selection_cancels_episode_best_version_when_pending_episode_unknown(self):
        plugin = make_plugin(_auto_download_pending=True)
        event_data = SimpleNamespace(contexts=[make_context()], origin="subscribe|1",
                                     updated=False, updated_contexts=None, source=None)
        subscribe = make_subscribe(best_version=1)
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source",
                          return_value=({"id": 1}, subscribe)), \
                patch.object(plugin, "_SubscribeAssistant__get_data", return_value={"1": {}}), \
                patch.object(plugin, "_SubscribeAssistant__initialize_subscribe_task",
                             return_value=({"torrent_tasks": []}, True)), \
                patch.object(plugin, "_SubscribeAssistant__is_episode_best_version_subscribe", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__collect_pending_episodes",
                             return_value=(set(), True)), \
                patch.object(plugin, "_SubscribeAssistant__apply_recognition_guard_selection") as guard:
            plugin.handle_resource_selection_event(event(event_data))
        assert event_data.updated
        assert event_data.updated_contexts == []
        assert event_data.source == plugin.plugin_name
        guard.assert_not_called()

    def test_resource_selection_filters_only_overlapping_episode_best_version_contexts(self):
        plugin = make_plugin(_auto_download_pending=True, _skip_deletion=False)
        kept = make_context_with_title("第 2 集")
        blocked = make_context_with_title("第 1 集")
        unknown = make_context_with_title("未知集")
        event_data = SimpleNamespace(contexts=[kept, blocked, unknown], origin="subscribe|1",
                                     updated=False, updated_contexts=None, source=None)
        subscribe = make_subscribe(best_version=1)
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source",
                          return_value=({"id": 1}, subscribe)), \
                patch.object(plugin, "_SubscribeAssistant__get_data", return_value={"1": {}}), \
                patch.object(plugin, "_SubscribeAssistant__initialize_subscribe_task",
                             return_value=({"torrent_tasks": []}, True)), \
                patch.object(plugin, "_SubscribeAssistant__is_episode_best_version_subscribe", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__collect_pending_episodes",
                             return_value=({1}, False)), \
                patch.object(plugin, "_SubscribeAssistant__get_download_resource_episodes",
                             side_effect=[([2], False), ([1], False), ([], False)]), \
                patch.object(plugin, "_SubscribeAssistant__apply_recognition_guard_selection") as guard:
            plugin.handle_resource_selection_event(event(event_data))
        assert event_data.updated
        assert event_data.updated_contexts == [kept]
        assert event_data.source == plugin.plugin_name
        guard.assert_called_once()

    def test_resource_selection_cancels_full_best_version_when_download_pending(self):
        plugin = make_plugin(_auto_download_pending=True)
        event_data = SimpleNamespace(contexts=[make_context()], origin="subscribe|1",
                                     updated=False, updated_contexts=None, source=None)
        subscribe = make_subscribe(best_version=1)
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source",
                          return_value=({"id": 1}, subscribe)), \
                patch.object(plugin, "_SubscribeAssistant__get_data", return_value={"1": {}}), \
                patch.object(plugin, "_SubscribeAssistant__initialize_subscribe_task",
                             return_value=({"torrent_tasks": []}, True)), \
                patch.object(plugin, "_SubscribeAssistant__is_episode_best_version_subscribe", return_value=False), \
                patch.object(plugin, "_SubscribeAssistant__get_subscribe_task_download_pending", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__apply_recognition_guard_selection") as guard:
            plugin.handle_resource_selection_event(event(event_data))
        assert event_data.updated_contexts == []
        assert event_data.source == plugin.plugin_name
        guard.assert_not_called()

    def test_resource_selection_removes_contexts_matching_delete_history(self):
        plugin = make_plugin(_skip_deletion=True)
        kept = make_context_with_title("新资源")
        deleted = make_context_with_title("删过的资源")
        event_data = SimpleNamespace(contexts=[kept, deleted], origin="subscribe|1",
                                     updated=False, updated_contexts=None, source=None)
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source",
                          return_value=({"id": 1}, make_subscribe())), \
                patch.object(plugin, "_SubscribeAssistant__apply_recognition_guard_selection"), \
                patch.object(plugin, "_SubscribeAssistant__get_data",
                             return_value={"h1": {"title": "删过的资源"}}), \
                patch.object(plugin, "_SubscribeAssistant__compare_torrent_info_and_task",
                             side_effect=[False, True]):
            plugin.handle_resource_selection_event(event(event_data))
        assert event_data.updated
        assert event_data.updated_contexts == [kept]
        assert event_data.source == plugin.plugin_name

    def test_resource_download_skips_when_cancelled(self):
        plugin = make_plugin()
        event_data = SimpleNamespace(cancel=True, context=make_context(), downloader="qb", episodes=[1], origin="s")
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source") as get_source:
            plugin.handle_resource_download_event(event(event_data))
        get_source.assert_not_called()

    def test_resource_download_skips_empty_event_and_missing_context(self):
        plugin = make_plugin()
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source") as get_source:
            plugin.handle_resource_download_event(None)
            plugin.handle_resource_download_event(event(SimpleNamespace(
                cancel=False, context=None, downloader="qb", episodes=[], origin="s")))
        get_source.assert_not_called()

    def test_resource_download_skips_when_source_not_subscription(self):
        plugin = make_plugin()
        event_data = SimpleNamespace(cancel=False, context=make_context(), downloader="qb", episodes=[1],
                                     origin="bad")
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source", return_value=(None, None)), \
                patch.object(plugin, "_SubscribeAssistant__handle_resource_download_pending") as pending:
            plugin.handle_resource_download_event(event(event_data))
        pending.assert_not_called()

    def test_resource_download_delegates_pending_baseline_and_history_clear(self):
        plugin = make_plugin()
        event_data = SimpleNamespace(cancel=False, context=make_context(), downloader="qb", episodes=[1],
                                     origin="subscribe|1")
        subscribe = make_subscribe()
        with patch.object(plugin, "_SubscribeAssistant__get_subscribe_by_source",
                          return_value=({"id": 1}, subscribe)), \
                patch.object(plugin, "_SubscribeAssistant__handle_resource_download_pending") as pending, \
                patch.object(plugin, "_SubscribeAssistant__capture_best_version_priority_baseline_if_needed") as base, \
                patch.object(plugin, "_SubscribeAssistant__handle_resource_download_history_clear") as history:
            plugin.handle_resource_download_event(event(event_data))
        pending.assert_called_once_with(subscribe=subscribe, context=event_data.context, episodes=[1], downloader="qb")
        base.assert_called_once()
        history.assert_called_once()

    def test_handle_resource_download_pending_updates_task_and_sets_pending_state(self):
        plugin = make_plugin(_auto_download_pending=True)
        subscribe = make_subscribe(best_version=1)
        context = make_context()
        with patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as locked, \
                patch.object(plugin, "_SubscribeAssistant__set_subscribe_download_pending_state") as set_pending:
            plugin._SubscribeAssistant__handle_resource_download_pending(
                subscribe=subscribe, context=context, episodes=[1], downloader="qb")
        locked.assert_called_once_with(method=plugin._SubscribeAssistant__update_subscribe_torrent_task,
                                       subscribe=subscribe,
                                       torrent_info=context.torrent_info,
                                       episodes=[1],
                                       downloader="qb",
                                       pending=True)
        set_pending.assert_called_once_with(subscribe=subscribe, reason="触发下载事件，更新为下载待定")

    def test_handle_resource_download_pending_skips_when_disabled(self):
        plugin = make_plugin(_auto_download_pending=False)
        with patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as locked:
            plugin._SubscribeAssistant__handle_resource_download_pending(
                subscribe=make_subscribe(), context=make_context(), episodes=[1], downloader="qb")
        locked.assert_not_called()

    def test_set_subscribe_download_pending_state_updates_only_when_needed(self):
        plugin = make_plugin()
        subscribe = make_subscribe(state="R")
        assert plugin._SubscribeAssistant__set_subscribe_download_pending_state(subscribe, "原因")
        plugin.subscribe_oper.update.assert_called_once_with(subscribe.id, {"state": "P"})
        plugin.subscribe_oper.update.reset_mock()
        assert not plugin._SubscribeAssistant__set_subscribe_download_pending_state(
            make_subscribe(state="P"), "原因")
        plugin.subscribe_oper.update.assert_not_called()

    def test_ensure_download_pending_state_requires_matching_pending_task(self):
        plugin = make_plugin(_auto_download_pending=True)
        subscribe = make_subscribe(best_version=1)
        with patch.object(plugin, "_SubscribeAssistant__get_data",
                          return_value={"1": {"id": 1, "name": "测试剧"}}), \
                patch.object(plugin, "_SubscribeAssistant__match_subscribe", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__get_subscribe_task_download_pending", return_value=True), \
                patch.object(plugin, "_SubscribeAssistant__set_subscribe_download_pending_state") as set_pending:
            plugin._SubscribeAssistant__ensure_download_pending_state(subscribe, "原因")
        set_pending.assert_called_once_with(subscribe=subscribe, reason="原因")

    def test_ensure_download_pending_state_skips_when_disabled_or_unmatched(self):
        plugin = make_plugin(_auto_download_pending=False)
        with patch.object(plugin, "_SubscribeAssistant__get_data") as get_data:
            plugin._SubscribeAssistant__ensure_download_pending_state(make_subscribe(best_version=1), "原因")
        get_data.assert_not_called()

        plugin = make_plugin(_auto_download_pending=True)
        with patch.object(plugin, "_SubscribeAssistant__get_data", return_value={}), \
                patch.object(plugin, "_SubscribeAssistant__set_subscribe_download_pending_state") as set_pending:
            plugin._SubscribeAssistant__ensure_download_pending_state(make_subscribe(best_version=1), "原因")
        set_pending.assert_not_called()

        with patch.object(plugin, "_SubscribeAssistant__get_data", return_value={"1": {"id": 1}}), \
                patch.object(plugin, "_SubscribeAssistant__match_subscribe", return_value=False), \
                patch.object(plugin, "_SubscribeAssistant__set_subscribe_download_pending_state") as set_pending:
            plugin._SubscribeAssistant__ensure_download_pending_state(make_subscribe(best_version=1), "原因")
        set_pending.assert_not_called()

    def test_update_subscribe_torrent_task_initializes_and_appends_torrent_task(self):
        plugin = make_plugin()
        subscribe = make_subscribe()
        subscribe_tasks = {}
        context = make_context()
        task = plugin._SubscribeAssistant__update_subscribe_torrent_task(
            subscribe_tasks=subscribe_tasks,
            subscribe=subscribe,
            torrent_hash=None,
            torrent_info=context.torrent_info,
            episodes=[1],
            downloader="qb",
            pending=True,
        )
        assert task is subscribe_tasks["1"]
        assert task["torrent_tasks"][0]["title"] == "标题"
        assert task["torrent_tasks"][0]["pending"]

    def test_update_or_add_subscribe_torrent_task_completes_hashless_pending_task(self):
        plugin = make_plugin()
        context = make_context()
        subscribe_task = {"torrent_tasks": [{
            "hash": None,
            "site_id": 1,
            "site_name": "站点",
            "title": "标题",
            "description": "副标题",
            "enclosure": "http://e/1.torrent",
            "page_url": "http://e/page",
            "pending": False,
        }]}
        changed = plugin._SubscribeAssistant__update_or_add_subscribe_torrent_task(
            subscribe_task=subscribe_task,
            torrent_hash="h1",
            torrent_info=context.torrent_info,
            episodes=[2],
            downloader="qb",
            pending=True,
        )
        assert changed
        assert subscribe_task["torrent_tasks"][0]["hash"] == "h1"
        assert subscribe_task["torrent_tasks"][0]["episodes"] == [2]
        assert subscribe_task["torrent_tasks"][0]["pending"]

    def test_capture_best_version_priority_baseline_if_needed_requires_best_version_and_feature_flag(self):
        plugin = make_plugin(_auto_download_delete=False, _manual_delete_listen=False,
                             _tracker_response_listen=False, _auto_download_pending=False)
        with patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as locked:
            plugin._SubscribeAssistant__capture_best_version_priority_baseline_if_needed(
                subscribe=make_subscribe(best_version=0), context=make_context(), episodes=[1])
            plugin._SubscribeAssistant__capture_best_version_priority_baseline_if_needed(
                subscribe=make_subscribe(best_version=1), context=make_context(), episodes=[1])
        locked.assert_not_called()

    def test_capture_best_version_priority_baseline_if_needed_delegates_when_enabled(self):
        plugin = make_plugin(_auto_download_delete=True)
        subscribe = make_subscribe(best_version=1)
        context = make_context()
        with patch.object(plugin, "_SubscribeAssistant__with_lock_and_update_subscribe_tasks") as locked:
            plugin._SubscribeAssistant__capture_best_version_priority_baseline_if_needed(
                subscribe=subscribe, context=context, episodes=[1])
        locked.assert_called_once_with(method=plugin._SubscribeAssistant__capture_best_version_priority_baseline,
                                       subscribe=subscribe,
                                       torrent_info=context.torrent_info,
                                       episodes=[1])

    def test_capture_best_version_priority_baseline_reuses_hashless_task_and_records_episode_baseline(self):
        plugin = make_plugin()
        subscribe = make_subscribe(best_version=1, current_priority=50,
                                   episode_priority={"1": 80, "2": 90})
        context = make_context()
        subscribe_tasks = {"1": {
            "id": 1,
            "name": "测试剧",
            "tmdbid": 100,
            "doubanid": None,
            "season": 1,
            "episode_group": None,
            "torrent_tasks": [{
                "hash": None,
                "site_id": 1,
                "site_name": "站点",
                "title": "标题",
                "description": "副标题",
                "enclosure": "http://e/1.torrent",
                "page_url": "http://e/page",
            }],
        }}
        plugin._SubscribeAssistant__capture_best_version_priority_baseline(
            subscribe_tasks, subscribe, context.torrent_info, episodes=[1, 2])
        task = subscribe_tasks["1"]["torrent_tasks"][0]
        assert len(subscribe_tasks["1"]["torrent_tasks"]) == 1
        assert task["current_priority_baseline"] == 50
        assert task["episode_priority_baseline"] == {"1": 80, "2": 90}
        assert task["contributed_priority"] == 80

    def test_capture_best_version_priority_baseline_for_movie_records_scalar_baseline_only(self):
        plugin = make_plugin()
        subscribe = make_subscribe(best_version=1, type=MediaType.MOVIE.value, season=None,
                                   current_priority=40)
        context = make_context()
        subscribe_tasks = {}
        plugin._SubscribeAssistant__capture_best_version_priority_baseline(
            subscribe_tasks, subscribe, context.torrent_info, episodes=[])
        task = subscribe_tasks["1"]["torrent_tasks"][0]
        assert task["current_priority_baseline"] == 40
        assert "episode_priority_baseline" not in task

    def test_reset_subscribe_task_state_when_updated_requires_state_change(self):
        plugin = make_plugin()
        subscribe_tasks = {}
        subscribe = make_subscribe()
        assert plugin._SubscribeAssistant__reset_subscribe_task_state_when_updated(
            subscribe_tasks, subscribe, {"name"}) is None
        assert subscribe_tasks == {}

    def test_reset_subscribe_task_state_when_updated_clears_pause_flags(self):
        plugin = make_plugin()
        subscribe = make_subscribe()
        subscribe_tasks = {"1": {
            "id": 1,
            "name": "测试剧",
            "tmdbid": 100,
            "doubanid": None,
            "season": 1,
            "episode_group": None,
            "pause_for_user": True,
            "pause_for_user_time": 1,
            "pause_for_download": True,
            "pause_for_download_time": 1,
        }}
        task = plugin._SubscribeAssistant__reset_subscribe_task_state_when_updated(
            subscribe_tasks, subscribe, {"state"})
        assert task["pause_for_user"] is False
        assert task["pause_for_user_time"] is None
        assert task["pause_for_download"] is False
        assert task["pause_for_download_time"] is None

    def test_transfer_intercept_delegates_when_media_available(self):
        plugin = make_plugin()
        event_data = SimpleNamespace(cancel=False, mediainfo=SimpleNamespace(title_year="测试剧"), target_path="/media/a")
        with patch.object(plugin, "_SubscribeAssistant__handle_transfer_intercept_history_clear") as history:
            plugin.handle_transfer_intercept_event(event(event_data))
        history.assert_called_once_with(mediainfo=event_data.mediainfo, target_path="/media/a")

    def test_transfer_intercept_skips_empty_cancelled_or_missing_media(self):
        plugin = make_plugin()
        with patch.object(plugin, "_SubscribeAssistant__handle_transfer_intercept_history_clear") as history:
            plugin.handle_transfer_intercept_event(None)
            plugin.handle_transfer_intercept_event(event(SimpleNamespace(
                cancel=True, mediainfo=SimpleNamespace(), target_path="/media/a")))
            plugin.handle_transfer_intercept_event(event(SimpleNamespace(
                cancel=False, mediainfo=None, target_path="/media/a")))
        history.assert_not_called()

    def test_transfer_intercept_history_clear_removes_completed_task(self):
        plugin = make_plugin()
        plugin.get_data = MagicMock(return_value={"100": {"paths": ["/media/a"]}})
        plugin.save_data = MagicMock()
        mediainfo = SimpleNamespace(tmdb_id=100, title="测试剧", type=MediaType.TV, season=1)
        with patch.object(plugin, "_SubscribeAssistant__clear_transfer_dest_histories", return_value=True) as clear:
            plugin._SubscribeAssistant__handle_transfer_intercept_history_clear(mediainfo, "/media/a")
        clear.assert_called_once()
        plugin.save_data.assert_called_once_with(key="best_version_clear_histories", value={})

    def test_transfer_complete_delegates_remove_torrent(self):
        plugin = make_plugin()
        transfer_info = SimpleNamespace(fileitem=None, transfer_type="link")
        with patch.object(plugin, "_SubscribeAssistant__handle_transfer_complete_remove_torrent") as remove:
            plugin.handle_transfer_complete_event(event({
                "transferinfo": transfer_info, "downloader": "qb", "download_hash": "h1",
            }))
        remove.assert_called_once_with(transfer_info, "qb", "h1")

    def test_transfer_complete_skips_empty_or_missing_transfer_info(self):
        plugin = make_plugin()
        with patch.object(plugin, "_SubscribeAssistant__handle_transfer_complete_remove_torrent") as remove:
            plugin.handle_transfer_complete_event(None)
            plugin.handle_transfer_complete_event(event({}))
            plugin.handle_transfer_complete_event(event({"transferinfo": None}))
        remove.assert_not_called()

    def test_plugin_action_toggle_updates_single_matching_subscription(self):
        plugin = make_plugin()
        plugin.subscribe_oper.list.return_value = [make_subscribe(id=7, state="R")]
        plugin.handle_subscribe_deleted_event  # keep lint quiet for dynamic class methods
        plugin.toggle_subscribe_state(event({"action": "subscribe_toggle", "arg_str": "7"}))
        plugin.subscribe_oper.update.assert_called_once_with(sid=7, payload={"state": "S"})
        plugin.post_message.assert_called_once()

    def test_plugin_action_toggle_ignores_empty_or_unrelated_event(self):
        plugin = make_plugin()
        plugin.toggle_subscribe_state(None)
        plugin.toggle_subscribe_state(event(None))
        plugin.toggle_subscribe_state(event({"action": "other", "arg_str": "7"}))
        plugin.subscribe_oper.list.assert_not_called()
        plugin.post_message.assert_not_called()

    def test_plugin_action_toggle_requires_keyword(self):
        plugin = make_plugin()
        plugin.toggle_subscribe_state(event({
            "action": "subscribe_toggle", "channel": "ch", "user": "u", "source": "src",
        }))
        plugin.post_message.assert_called_once()
        assert "未能获取" in plugin.post_message.call_args.kwargs["title"]

    def test_plugin_action_toggle_reports_when_no_subscribes(self):
        plugin = make_plugin()
        plugin.subscribe_oper.list.return_value = []
        plugin.toggle_subscribe_state(event({
            "action": "subscribe_toggle", "arg_str": "测试剧",
            "channel": "ch", "user": "u", "source": "src",
        }))
        assert "没有找到" in plugin.post_message.call_args.kwargs["title"]

    def test_plugin_action_toggle_reports_when_no_matching_subscription(self):
        plugin = make_plugin()
        plugin.subscribe_oper.list.return_value = [make_subscribe(name="别的剧")]
        plugin.toggle_subscribe_state(event({
            "action": "subscribe_toggle", "arg_str": "测试剧",
            "channel": "ch", "user": "u", "source": "src",
        }))
        plugin.subscribe_oper.update.assert_not_called()
        assert "没有找到" in plugin.post_message.call_args.kwargs["text"]

    def test_plugin_action_toggle_filters_by_name_and_enables_paused_subscription(self):
        plugin = make_plugin()
        plugin.subscribe_oper.list.return_value = [make_subscribe(state="S")]
        plugin.toggle_subscribe_state(event({
            "action": "subscribe_toggle", "arg_str": "测试剧",
            "channel": "ch", "user": "u", "source": "src",
        }))
        plugin.subscribe_oper.update.assert_called_once_with(sid=1, payload={"state": "R"})
        assert "已启用" in plugin.post_message.call_args.kwargs["title"]

    def test_plugin_action_toggle_lists_duplicate_name_candidates(self):
        plugin = make_plugin()
        plugin.subscribe_oper.list.return_value = [
            make_subscribe(id=1, name="重复", type=TV, season=1),
            make_subscribe(id=2, name="重复", type=TV, season=2),
        ]
        plugin.toggle_subscribe_state(event({
            "action": "subscribe_toggle", "arg_str": "重复",
            "channel": "ch", "user": "u", "source": "src",
        }))
        plugin.subscribe_oper.update.assert_not_called()
        assert "共有 2 个订阅" in plugin.post_message.call_args.kwargs["title"]
        assert "2. 重复" in plugin.post_message.call_args.kwargs["text"]

    def test_plugin_action_toggle_lists_duplicate_movie_candidates(self):
        plugin = make_plugin()
        plugin.subscribe_oper.list.return_value = [
            make_subscribe(id=1, name="重复电影", type=MediaType.MOVIE.value, season=None),
            make_subscribe(id=2, name="重复电影", type=MediaType.MOVIE.value, season=None),
        ]
        plugin.toggle_subscribe_state(event({
            "action": "subscribe_toggle", "arg_str": "重复电影",
            "channel": "ch", "user": "u", "source": "src",
        }))
        plugin.subscribe_oper.update.assert_not_called()
        assert "1. 重复电影（2024）" in plugin.post_message.call_args.kwargs["text"]
