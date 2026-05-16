"""add tool call audit

Revision ID: 20260513_0002
Revises: 20260512_0001
Create Date: 2026-05-13 08:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "20260513_0002"
down_revision: Union[str, Sequence[str], None] = "20260512_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def _index_exists(table_name: str, index_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return any(index["name"] == index_name for index in inspector.get_indexes(table_name))


def upgrade() -> None:
    if not _table_exists("toolcall"):
        op.create_table(
            "toolcall",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("tool_name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("input_payload", sa.JSON(), nullable=True),
            sa.Column("output_payload", sa.JSON(), nullable=True),
            sa.Column("sources", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("toolcall", "ix_toolcall_session_id"):
        op.create_index("ix_toolcall_session_id", "toolcall", ["session_id"])
    if not _index_exists("toolcall", "ix_toolcall_tool_name"):
        op.create_index("ix_toolcall_tool_name", "toolcall", ["tool_name"])
    if not _index_exists("toolcall", "ix_toolcall_status"):
        op.create_index("ix_toolcall_status", "toolcall", ["status"])
    if not _index_exists("toolcall", "ix_toolcall_created_at"):
        op.create_index("ix_toolcall_created_at", "toolcall", ["created_at"])


def downgrade() -> None:
    if _table_exists("toolcall"):
        op.drop_index("ix_toolcall_created_at", table_name="toolcall")
        op.drop_index("ix_toolcall_status", table_name="toolcall")
        op.drop_index("ix_toolcall_tool_name", table_name="toolcall")
        op.drop_index("ix_toolcall_session_id", table_name="toolcall")
        op.drop_table("toolcall")
