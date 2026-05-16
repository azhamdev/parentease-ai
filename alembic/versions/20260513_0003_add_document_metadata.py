"""add document metadata

Revision ID: 20260513_0003
Revises: 20260513_0002
Create Date: 2026-05-13 09:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "20260513_0003"
down_revision: Union[str, Sequence[str], None] = "20260513_0002"
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
    if not _table_exists("document"):
        op.create_table(
            "document",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("filename", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("source_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column("collection_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("chunk_count", sa.Integer(), nullable=False),
            sa.Column("error_message", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("ingested_at", sa.DateTime(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
    if not _index_exists("document", "ix_document_filename"):
        op.create_index("ix_document_filename", "document", ["filename"])
    if not _index_exists("document", "ix_document_source_type"):
        op.create_index("ix_document_source_type", "document", ["source_type"])
    if not _index_exists("document", "ix_document_status"):
        op.create_index("ix_document_status", "document", ["status"])
    if not _index_exists("document", "ix_document_collection_name"):
        op.create_index("ix_document_collection_name", "document", ["collection_name"])


def downgrade() -> None:
    if _table_exists("document"):
        op.drop_index("ix_document_collection_name", table_name="document")
        op.drop_index("ix_document_status", table_name="document")
        op.drop_index("ix_document_source_type", table_name="document")
        op.drop_index("ix_document_filename", table_name="document")
        op.drop_table("document")
