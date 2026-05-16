"""initial schema

Revision ID: 20260512_0001
Revises:
Create Date: 2026-05-12 23:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "20260512_0001"
down_revision: Union[str, Sequence[str], None] = None
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
    if not _table_exists("childprofile"):
        op.create_table(
            "childprofile",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("birth_date", sa.Date(), nullable=False),
            sa.Column("gender", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("weight_kg", sa.Float(), nullable=True),
            sa.Column("height_cm", sa.Float(), nullable=True),
            sa.Column("topic", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("childprofile", "ix_childprofile_session_id"):
        op.create_index("ix_childprofile_session_id", "childprofile", ["session_id"])

    if not _table_exists("chatmessage"):
        op.create_table(
            "chatmessage",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("role", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("content", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("chatmessage", "ix_chatmessage_session_id"):
        op.create_index("ix_chatmessage_session_id", "chatmessage", ["session_id"])

    if not _table_exists("vaccinerecord"):
        op.create_table(
            "vaccinerecord",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("vaccine_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("date_given", sa.Date(), nullable=True),
            sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("vaccinerecord", "ix_vaccinerecord_session_id"):
        op.create_index("ix_vaccinerecord_session_id", "vaccinerecord", ["session_id"])
    if not _index_exists("vaccinerecord", "ix_vaccinerecord_vaccine_code"):
        op.create_index("ix_vaccinerecord_vaccine_code", "vaccinerecord", ["vaccine_code"])


def downgrade() -> None:
    if _table_exists("vaccinerecord"):
        op.drop_index("ix_vaccinerecord_vaccine_code", table_name="vaccinerecord")
        op.drop_index("ix_vaccinerecord_session_id", table_name="vaccinerecord")
        op.drop_table("vaccinerecord")
    if _table_exists("chatmessage"):
        op.drop_index("ix_chatmessage_session_id", table_name="chatmessage")
        op.drop_table("chatmessage")
    if _table_exists("childprofile"):
        op.drop_index("ix_childprofile_session_id", table_name="childprofile")
        op.drop_table("childprofile")
