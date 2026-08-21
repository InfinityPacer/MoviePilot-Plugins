from types import SimpleNamespace
from unittest.mock import Mock

from sqlalchemy import Boolean, String, column, table
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

import app.plugins.plexmatch as plexmatch
from app.schemas import TransferInfo
from app.schemas.file import FileItem
from app.sdk.events import Event
from app.sdk.media import MediaInfo, MetaBase
from app.schemas.types import EventType, MediaSource, MediaType


_TRANSFER_HISTORY = table(
    "transferhistory",
    column("type", String),
    column("media_source", String),
    column("media_id", String),
    column("status", Boolean),
)


class _V3TransferHistory:
    """提供 MoviePilot V3 整理记录的统一媒体身份字段契约。"""

    type = _TRANSFER_HISTORY.c.type
    media_source = _TRANSFER_HISTORY.c.media_source
    media_id = _TRANSFER_HISTORY.c.media_id
    status = _TRANSFER_HISTORY.c.status


class _RecordingQuery:
    """记录插件提交给 ORM 的筛选条件，不访问真实数据库。"""

    def __init__(self) -> None:
        self.criterion = None

    def filter(self, criterion):
        self.criterion = criterion
        return self

    def all(self) -> list:
        return []


class _RecordingSession(Session):
    """提供满足 db_query 契约的 Session，并暴露生成的查询条件。"""

    def __init__(self) -> None:
        super().__init__()
        self.recorded_query = _RecordingQuery()

    def query(self, *entities, **kwargs):
        return self.recorded_query


def _compile_history_filter(monkeypatch, dialect) -> str:
    monkeypatch.setattr(plexmatch, "TransferHistory", _V3TransferHistory)
    session = _RecordingSession()
    try:
        plexmatch.PlexMatch._PlexMatch__list_transfer_histories(db=session)
        criterion = session.recorded_query.criterion
        assert criterion is not None
        return str(criterion.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
    finally:
        session.close()


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
    assert plexmatch.PlexMatch.plugin_version == "1.5"


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


def test_history_filter_selects_valid_tmdb_identity_on_postgresql(monkeypatch) -> None:
    sql = _compile_history_filter(monkeypatch, postgresql.dialect())

    assert "media_source = 'themoviedb'" in sql
    assert "type IN ('电影', '电视剧')" in sql
    assert "media_id IS NOT NULL" in sql
    assert "media_id != ''" in sql
    assert "media_id != '0'" in sql
    assert "tmdbid" not in sql


def test_history_filter_keeps_sqlite_compatibility(monkeypatch) -> None:
    sql = _compile_history_filter(monkeypatch, sqlite.dialect())

    assert "media_source = 'themoviedb'" in sql
    assert "type IN ('电影', '电视剧')" in sql
    assert "media_id IS NOT NULL" in sql
    assert "media_id != ''" in sql
    assert "media_id != '0'" in sql
    assert "tmdbid" not in sql


def test_history_completion_writes_tmdb_media_id(monkeypatch) -> None:
    plugin = _make_plugin()
    history = SimpleNamespace(
        title="测试剧",
        media_source=MediaSource.TMDB.value,
        media_id="12345",
        dest="/media/测试剧/Season 1/S01E01.mkv",
        type=MediaType.TV.value,
    )
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
