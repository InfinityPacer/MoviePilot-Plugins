import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import app.plugins.plexmatch as plexmatch
from app.schemas import TransferInfo
from app.schemas.file import FileItem
from app.schemas.types import EventType, MediaSource, MediaType
from app.sdk.events import Event
from app.sdk.media import MediaInfo, MetaBase
from app.sdk.queries import (
    MAX_QUERY_PAGE_SIZE,
    QueryPage,
    QuerySortDirection,
    QuerySortField,
    TransferHistorySnapshot,
)


def _make_transfer_history(
        *,
        history_id: int = 1,
        title: str | None = "测试剧",
        media_id: str | None = "12345",
        dest: str | None = "/media/测试剧/Season 1/S01E01.mkv",
        media_type: MediaType = MediaType.TV,
) -> TransferHistorySnapshot:
    """构造符合公开查询 DTO 合同的整理历史记录。"""
    return TransferHistorySnapshot(
        id=history_id,
        title=title,
        type=media_type.value,
        media_source=MediaSource.TMDB,
        media_id=media_id,
        dest=dest,
        status=True,
    )


def _make_transfer_event(
        media_source: MediaSource,
        media_id: str,
        media_type: MediaType = MediaType.TV,
) -> Event:
    """构造满足 PlexMatch 入库事件契约的最小测试事件。"""
    return Event(
        EventType.TransferComplete,
        {
            "mediainfo": SimpleNamespace(
                title="测试剧",
                title_year="测试剧 (2026)",
                type=media_type,
                media_source=media_source,
                media_id=media_id,
            ),
            "meta": SimpleNamespace(season_episode="S01E01"),
            "transferinfo": SimpleNamespace(
                target_item=SimpleNamespace(path="/media/测试剧/Season 1/S01E01.mkv")
            ),
        },
    )


def _make_plugin() -> plexmatch.PlexMatch:
    """绕过主程序服务初始化，仅构造当前插件逻辑所需实例。"""
    return object.__new__(plexmatch.PlexMatch)


def test_plugin_declares_v3_minor_version() -> None:
    assert plexmatch.PlexMatch.plugin_version == "1.6"


def test_plugin_declares_empty_v3_extension_surfaces() -> None:
    plugin = _make_plugin()

    assert plugin.get_command() == []
    assert plugin.get_api() == []
    assert plugin.get_service() == []
    assert plugin.get_page() is None


def test_transfer_event_accepts_v3_media_metadata_and_response_objects(monkeypatch) -> None:
    plugin = _make_plugin()
    plugin._enabled = True
    add_plexmatch = Mock(return_value=True)
    monkeypatch.setattr(plugin, "_PlexMatch__add_plexmatch_file", add_plexmatch)

    mediainfo = MediaInfo(
        title="测试剧",
        year="2026",
        type=MediaType.TV,
        media_source=MediaSource.TMDB,
        media_id="12345",
    )
    metadata = MetaBase(title="测试剧")
    metadata.type = MediaType.TV
    metadata.begin_season = 1
    metadata.begin_episode = 1
    transfer_info = TransferInfo(
        target_item=FileItem(path="/media/测试剧/Season 1/S01E01.mkv", type="file")
    )

    plugin.execute_transfer(
        Event(
            EventType.TransferComplete,
            {
                "mediainfo": mediainfo,
                "meta": metadata,
                "transferinfo": transfer_info,
            },
        )
    )

    add_plexmatch.assert_called_once_with(
        title="测试剧",
        tmdb_id="12345",
        file_path="/media/测试剧/Season 1/S01E01.mkv",
        mtype=MediaType.TV,
    )


def test_v3_plugin_uses_public_query_sdk_for_history_access() -> None:
    """整理历史批量查询不得重新依赖宿主 ORM、裸会话或兼容层。"""
    source_path = Path(__file__).parents[3] / "plugins.v3" / "plexmatch" / "__init__.py"
    tree = ast.parse(source_path.read_text(encoding="utf-8"))
    imported_modules = {
        node.module
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    }
    imported_modules.update(
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    )

    assert "app.sdk.queries" in imported_modules
    assert not any(
        module.startswith(
            (
                "app.compat",
                "app.db.models",
                "app.db.session",
                "app.runtime.compat",
                "app.sdk._legacy",
            )
        )
        for module in imported_modules
    )
    assert "sqlalchemy.orm" not in imported_modules
    root_db_names = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module == "app.db"
        for alias in node.names
    }
    assert not root_db_names & {
        "async_db_query",
        "async_db_update",
        "db_query",
        "db_update",
        "get_engine",
    }


def test_history_query_uses_sdk_filter_and_reads_all_pages(monkeypatch) -> None:
    first_page_items = [
        _make_transfer_history(history_id=history_id)
        for history_id in range(1, MAX_QUERY_PAGE_SIZE + 1)
    ]
    second = _make_transfer_history(
        history_id=MAX_QUERY_PAGE_SIZE + 1,
        title="测试电影",
        media_id="67890",
        dest="/media/测试电影/测试电影.mkv",
        media_type=MediaType.MOVIE,
    )
    query = Mock(
        side_effect=[
            QueryPage(
                items=first_page_items,
                total=MAX_QUERY_PAGE_SIZE + 1,
                page=1,
                count=MAX_QUERY_PAGE_SIZE,
            ),
            QueryPage(
                items=[second],
                total=MAX_QUERY_PAGE_SIZE + 1,
                page=2,
                count=MAX_QUERY_PAGE_SIZE,
            ),
        ]
    )
    monkeypatch.setattr(plexmatch, "list_transfer_history", query)

    histories = plexmatch.PlexMatch._PlexMatch__list_transfer_histories()

    assert histories == [*first_page_items, second]
    assert query.call_count == 2
    first_call = query.call_args_list[0]
    first_filter = first_call.kwargs["filters"]
    assert first_filter.media_types == (MediaType.MOVIE, MediaType.TV)
    assert first_filter.media_sources == (MediaSource.TMDB,)
    assert first_filter.require_media_identity is True
    assert first_filter.status is True
    assert first_call.kwargs["page"].page == 1
    assert first_call.kwargs["page"].count == MAX_QUERY_PAGE_SIZE
    assert first_call.kwargs["page"].sort.field == QuerySortField.DATE
    assert first_call.kwargs["page"].sort.direction == QuerySortDirection.DESC
    assert query.call_args_list[1].kwargs["page"].page == 2


def test_history_query_stops_at_exact_max_page_boundary(monkeypatch) -> None:
    items = [
        _make_transfer_history(history_id=history_id)
        for history_id in range(1, MAX_QUERY_PAGE_SIZE + 1)
    ]
    query = Mock(
        return_value=QueryPage(
            items=items,
            total=MAX_QUERY_PAGE_SIZE,
            page=1,
            count=MAX_QUERY_PAGE_SIZE,
        )
    )
    monkeypatch.setattr(plexmatch, "list_transfer_history", query)

    histories = plexmatch.PlexMatch._PlexMatch__list_transfer_histories()

    assert histories == items
    query.assert_called_once()


def test_history_query_returns_empty_sdk_page(monkeypatch) -> None:
    query = Mock(return_value=QueryPage(total=0, page=1, count=MAX_QUERY_PAGE_SIZE))
    monkeypatch.setattr(plexmatch, "list_transfer_history", query)

    histories = plexmatch.PlexMatch._PlexMatch__list_transfer_histories()

    assert histories == []
    query.assert_called_once()


def test_history_completion_writes_tmdb_media_id(monkeypatch) -> None:
    plugin = _make_plugin()
    history = _make_transfer_history()
    monkeypatch.setattr(
        plugin,
        "_PlexMatch__list_transfer_histories",
        Mock(return_value=[history]),
    )
    add_plexmatch = Mock(return_value=True)
    monkeypatch.setattr(plugin, "_PlexMatch__add_plexmatch_file", add_plexmatch)

    plugin._PlexMatch__complete_by_history()

    add_plexmatch.assert_called_once_with(
        title="测试剧",
        tmdb_id="12345",
        file_path="/media/测试剧/Season 1/S01E01.mkv",
        mtype=MediaType.TV,
    )


def test_history_completion_skips_incomplete_sdk_snapshot(monkeypatch) -> None:
    plugin = _make_plugin()
    incomplete = _make_transfer_history(title=None, dest=None)
    monkeypatch.setattr(
        plugin,
        "_PlexMatch__list_transfer_histories",
        Mock(return_value=[incomplete]),
    )
    add_plexmatch = Mock(return_value=True)
    monkeypatch.setattr(plugin, "_PlexMatch__add_plexmatch_file", add_plexmatch)

    plugin._PlexMatch__complete_by_history()

    add_plexmatch.assert_not_called()


def test_history_completion_keeps_latest_identity_per_plexmatch_target(
        monkeypatch,
        tmp_path,
) -> None:
    """同一剧集根的多条历史只使用最新身份，覆盖模式不得回写旧 TMDB ID。"""
    series_root = tmp_path / "测试剧 (2026)"
    season_root = series_root / "Season 1"
    season_root.mkdir(parents=True)
    latest_file = season_root / "S01E02.mkv"
    older_file = season_root / "S01E01.mkv"
    latest_file.touch()
    older_file.touch()

    plugin = _make_plugin()
    plugin._overwrite = True
    plugin._event.clear()
    latest = _make_transfer_history(
        history_id=2,
        media_id="22222",
        dest=str(latest_file),
    )
    older = _make_transfer_history(
        history_id=1,
        media_id="11111",
        dest=str(older_file),
    )
    monkeypatch.setattr(
        plugin,
        "_PlexMatch__list_transfer_histories",
        Mock(return_value=[latest, older]),
    )

    plugin._PlexMatch__complete_by_history()

    assert (series_root / ".plexmatch").read_text(encoding="utf-8") == (
        "tmdbid: 22222 #测试剧 TMDB编号"
    )


def test_add_plexmatch_file_writes_tmdb_hint(tmp_path) -> None:
    plugin = _make_plugin()
    plugin._overwrite = False
    media_file = tmp_path / "测试电影 (2026)" / "测试电影.mkv"
    media_file.parent.mkdir()
    media_file.touch()

    created = plugin._PlexMatch__add_plexmatch_file(
        title="测试电影",
        tmdb_id="12345",
        file_path=str(media_file),
        mtype=MediaType.MOVIE,
    )

    assert created is True
    assert (media_file.parent / ".plexmatch").read_text(encoding="utf-8") == (
        "tmdbid: 12345 #测试电影 TMDB编号"
    )


def test_add_plexmatch_file_keeps_tv_hint_at_series_root(tmp_path) -> None:
    plugin = _make_plugin()
    plugin._overwrite = False
    media_file = tmp_path / "测试剧 (2026)" / "Season 1" / "S01E01.mkv"
    media_file.parent.mkdir(parents=True)
    media_file.touch()

    created = plugin._PlexMatch__add_plexmatch_file(
        title="测试剧",
        tmdb_id="12345",
        file_path=str(media_file),
        mtype=MediaType.TV,
    )

    assert created is True
    assert (media_file.parent.parent / ".plexmatch").read_text(encoding="utf-8") == (
        "tmdbid: 12345 #测试剧 TMDB编号"
    )
    assert not (media_file.parent / ".plexmatch").exists()


def test_transfer_event_writes_tmdb_media_id(monkeypatch) -> None:
    plugin = _make_plugin()
    plugin._enabled = True
    add_plexmatch = Mock(return_value=True)
    monkeypatch.setattr(plugin, "_PlexMatch__add_plexmatch_file", add_plexmatch)

    plugin.execute_transfer(_make_transfer_event(MediaSource.TMDB, "12345"))

    add_plexmatch.assert_called_once_with(
        title="测试剧",
        tmdb_id="12345",
        file_path="/media/测试剧/Season 1/S01E01.mkv",
        mtype=MediaType.TV,
    )


def test_transfer_event_ignores_non_tmdb_identity(monkeypatch) -> None:
    plugin = _make_plugin()
    plugin._enabled = True
    add_plexmatch = Mock(return_value=True)
    monkeypatch.setattr(plugin, "_PlexMatch__add_plexmatch_file", add_plexmatch)

    plugin.execute_transfer(_make_transfer_event(MediaSource.Douban, "12345"))

    add_plexmatch.assert_not_called()


def test_transfer_event_ignores_zero_tmdb_id(monkeypatch) -> None:
    plugin = _make_plugin()
    plugin._enabled = True
    add_plexmatch = Mock(return_value=True)
    monkeypatch.setattr(plugin, "_PlexMatch__add_plexmatch_file", add_plexmatch)

    plugin.execute_transfer(_make_transfer_event(MediaSource.TMDB, "0"))

    add_plexmatch.assert_not_called()


def test_transfer_event_ignores_non_video_media(monkeypatch) -> None:
    """PlexMatch 只为电影和电视剧写入匹配文件。"""
    plugin = _make_plugin()
    plugin._enabled = True
    add_plexmatch = Mock(return_value=True)
    monkeypatch.setattr(plugin, "_PlexMatch__add_plexmatch_file", add_plexmatch)

    plugin.execute_transfer(
        _make_transfer_event(MediaSource.MusicBrainz, "recording-id", MediaType.MUSIC)
    )

    add_plexmatch.assert_not_called()


def test_add_plexmatch_file_rejects_non_video_media(tmp_path) -> None:
    """文件写入边界自身也拒绝非影视媒体，避免绕过事件入口。"""
    plugin = _make_plugin()
    plugin._overwrite = False
    media_file = tmp_path / "music.flac"
    media_file.touch()

    created = plugin._PlexMatch__add_plexmatch_file(
        title="测试音乐",
        tmdb_id="12345",
        file_path=str(media_file),
        mtype=MediaType.MUSIC,
    )

    assert created is False
    assert not (tmp_path / ".plexmatch").exists()
