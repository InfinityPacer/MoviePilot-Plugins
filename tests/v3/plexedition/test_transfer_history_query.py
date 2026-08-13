from types import SimpleNamespace
from unittest.mock import MagicMock, call

import plexedition
from app.core.event import Event
from app.schemas.types import EventType, MediaSource, MediaType


def test_process_item_queries_transfer_history_by_v3_media_identity(monkeypatch) -> None:
    """Plex TMDB GUID 应转换为 V3 规范媒体身份后查询整理记录。"""
    source_path = "/media/Movies/Fight.Club.1999.mkv"
    item = SimpleNamespace(
        type="movie",
        title="Fight Club",
        ratingKey="1",
        editionTitle=None,
        locations=[source_path],
        fields=[],
        guids=[SimpleNamespace(id="tmdb://550")],
    )
    plugin = object.__new__(plexedition.PlexEdition)
    plugin.history_oper = MagicMock()
    plugin.history_oper.get_by.return_value = []
    plugin.history_oper.get_by_title.return_value = []
    plugin._lock = False

    monkeypatch.setattr(plexedition, "is_anime", lambda _path: False)
    monkeypatch.setattr(
        plexedition,
        "MetaVideo",
        lambda *_args, **_kwargs: SimpleNamespace(edition=None),
    )

    plugin._PlexEdition__process_items(item)

    assert plugin.history_oper.get_by.call_args == call(
        media_source=MediaSource.TMDB,
        media_id="550",
        mtype="电影",
        dest=source_path,
    )


def test_v3_plugin_version() -> None:
    assert plexedition.PlexEdition.plugin_version == "1.3"


def test_transfer_event_ignores_non_movie_media() -> None:
    """PlexEdition 的事件入口只接受电影，不处理电视剧或音乐。"""
    plugin = object.__new__(plexedition.PlexEdition)
    plugin._enabled = True
    plugin._execute_transfer = True
    plugin._scheduler = MagicMock()
    event = Event(
        EventType.TransferComplete,
        {
            "mediainfo": SimpleNamespace(type=MediaType.MUSIC),
            "meta": SimpleNamespace(),
        },
    )

    plugin.after_transfer(event)

    plugin._scheduler.add_job.assert_not_called()
