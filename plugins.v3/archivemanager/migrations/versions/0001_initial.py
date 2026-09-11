"""建立归档批次、文件版本及任务队列的初始结构。"""

from alembic import op
import sqlalchemy as sa

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    """冻结初始结构，不引用会随业务版本变化的 ORM 模型。"""
    op.create_table(
        "archive_batch",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("created_at", sa.String(40), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
    )
    for field in ("task_id", "status", "created_at"):
        op.create_index(f"ix_archive_batch_{field}", "archive_batch", [field])
    op.create_table(
        "archive_file",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("batch_id", sa.String(64), nullable=True),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("historical", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("task_id", "fingerprint"),
    )
    for field in ("task_id", "batch_id", "status", "historical"):
        op.create_index(f"ix_archive_file_{field}", "archive_file", [field])
    op.create_table(
        "archive_task",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("data", sa.JSON(), nullable=False),
    )


def downgrade():
    """显式回退初始版本会删除业务表；宿主正常启动仅执行 upgrade。"""
    for table in ("archive_task", "archive_file", "archive_batch"):
        op.drop_table(table)
