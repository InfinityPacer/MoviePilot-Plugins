"""增加目录元数据版本账本。"""

from alembic import op
import sqlalchemy as sa

revision = "0002_directory_metadata"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    """目录与文件分别记账，避免空目录在每轮重复归档。"""
    op.create_table(
        "archive_directory",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("task_id", sa.String(64), nullable=False),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("relative_path", sa.Text(), nullable=False),
        sa.Column("batch_id", sa.String(64), nullable=True),
        sa.Column("present", sa.Boolean(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.UniqueConstraint("task_id", "fingerprint"),
    )
    for field in ("task_id", "batch_id", "status"):
        op.create_index(f"ix_archive_directory_{field}", "archive_directory", [field])


def downgrade():
    """回退时只删除新增目录账本。"""
    op.drop_table("archive_directory")
