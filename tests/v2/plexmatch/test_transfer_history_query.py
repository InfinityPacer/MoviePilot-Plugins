from sqlalchemy import Boolean, Integer, column, table
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.orm import Session

import plexmatch


_TRANSFER_HISTORY = table(
    "transferhistory",
    column("tmdbid", Integer),
    column("status", Boolean),
)


class _V2153TransferHistory:
    """保留 MoviePilot v2.15.3 中查询依赖的整理记录字段契约。"""

    tmdbid = _TRANSFER_HISTORY.c.tmdbid
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
    monkeypatch.setattr(plexmatch, "TransferHistory", _V2153TransferHistory)
    session = _RecordingSession()
    try:
        plexmatch.PlexMatch._PlexMatch__list_transfer_histories(db=session)
        criterion = session.recorded_query.criterion
        assert criterion is not None
        return str(criterion.compile(dialect=dialect, compile_kwargs={"literal_binds": True}))
    finally:
        session.close()


def test_history_filter_uses_numeric_comparison_on_postgresql(monkeypatch) -> None:
    sql = _compile_history_filter(monkeypatch, postgresql.dialect())

    assert "tmdbid IS NOT NULL" in sql
    assert "tmdbid != 0" in sql
    assert "tmdbid IS NOT 0" not in sql


def test_history_filter_keeps_sqlite_compatibility(monkeypatch) -> None:
    sql = _compile_history_filter(monkeypatch, sqlite.dialect())

    assert "tmdbid IS NOT NULL" in sql
    assert "tmdbid != 0" in sql
    assert "tmdbid IS NOT 0" not in sql
