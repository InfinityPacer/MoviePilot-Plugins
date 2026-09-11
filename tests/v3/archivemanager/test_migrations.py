"""验证宿主迁移入口建库、重复升级及 ORM 结构一致性。"""

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import scoped_session, sessionmaker

from app.db.plugin.container import PluginDatabaseHandle
from app.db.plugin.migration import run_migrations
from app.plugins.archivemanager import ArchiveManager
from app.plugins.archivemanager.store import Base


def test_host_migration_creates_schema_and_preserves_data(tmp_path):
    """首启完整建库，再次升级不重复建表且保留任务状态。"""
    path = tmp_path / "plugin.db"
    engine = create_engine(f"sqlite:///{path}")
    factory = sessionmaker(bind=engine)
    handle = PluginDatabaseHandle(
        plugin_id="ArchiveManager", engine=engine, session_factory=factory,
        scoped_session_factory=scoped_session(factory), db_path=path, schema=None, owns_engine=True,
    )
    migrations = ArchiveManager().get_database_migrations()
    try:
        run_migrations(handle, migrations)
        assert set(inspect(engine).get_table_names()) == {
            "archive_batch", "archive_file", "archive_task", "alembic_version",
        }
        with engine.begin() as connection:
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001_initial"
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
            connection.execute(text("INSERT INTO archive_task (id, data) VALUES ('sample', '{}')"))
        run_migrations(handle, migrations)
        with engine.connect() as connection:
            assert connection.scalar(text("SELECT count(*) FROM archive_task")) == 1
    finally:
        handle.dispose()


def test_migration_uses_host_connection(tmp_path):
    """宿主提供连接时不依赖 URL；覆盖 PostgreSQL 使用的连接注入契约。"""
    from alembic.command import upgrade
    from alembic.config import Config

    engine = create_engine(f"sqlite:///{tmp_path / 'injected.db'}")
    config = Config()
    config.set_main_option("script_location", str(ArchiveManager().get_database_migrations()))
    try:
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            upgrade(config, "head")
            assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0001_initial"
    finally:
        engine.dispose()
