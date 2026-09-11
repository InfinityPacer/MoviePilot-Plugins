"""使用宿主指定的 SQLite URL 或 PostgreSQL 隔离连接执行迁移。"""

from alembic import context
from sqlalchemy import create_engine, pool


def migrate(connection):
    """事务及 schema 边界由宿主连接保持，不另开 PostgreSQL 连接。"""
    context.configure(connection=connection, render_as_batch=connection.dialect.name == "sqlite")
    with context.begin_transaction():
        context.run_migrations()


connection = context.config.attributes.get("connection")
if connection is not None:
    migrate(connection)
else:
    engine = create_engine(context.config.get_main_option("sqlalchemy.url"), poolclass=pool.NullPool)
    try:
        with engine.connect() as sqlite_connection:
            migrate(sqlite_connection)
    finally:
        engine.dispose()
