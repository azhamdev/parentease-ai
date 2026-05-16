"""add upload_job table

Revision ID: 20260516_0005
Revises: 20260515_0004
Create Date: 2026-05-16 14:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "20260516_0005"
down_revision: Union[str, Sequence[str], None] = "20260515_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("uploadjob"):
        op.create_table(
            "uploadjob",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("job_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column(
                "celery_task_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True
            ),
            sa.Column("filename", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column(
                "content_type", sqlmodel.sql.sqltypes.AutoString(), nullable=True
            ),
            sa.Column("file_path", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("result_payload", sa.JSON(), nullable=True),
            sa.Column("error_message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.Column("completed_at", sa.DateTime(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("job_id"),
        )
        op.create_index("ix_uploadjob_job_id", "uploadjob", ["job_id"])
        op.create_index("ix_uploadjob_session_id", "uploadjob", ["session_id"])
        op.create_index("ix_uploadjob_celery_task_id", "uploadjob", ["celery_task_id"])
        op.create_index("ix_uploadjob_status", "uploadjob", ["status"])
        op.create_index("ix_uploadjob_created_at", "uploadjob", ["created_at"])


def downgrade() -> None:
    if _table_exists("uploadjob"):
        op.drop_index("ix_uploadjob_created_at", table_name="uploadjob")
        op.drop_index("ix_uploadjob_status", table_name="uploadjob")
        op.drop_index("ix_uploadjob_celery_task_id", table_name="uploadjob")
        op.drop_index("ix_uploadjob_session_id", table_name="uploadjob")
        op.drop_index("ix_uploadjob_job_id", table_name="uploadjob")
        op.drop_table("uploadjob")
