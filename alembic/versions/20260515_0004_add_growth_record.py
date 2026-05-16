"""add growth_record table

Revision ID: 20260515_0004
Revises: 8dc30850dece
Create Date: 2026-05-15 10:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


revision: str = "20260515_0004"
down_revision: Union[str, Sequence[str], None] = "8dc30850dece"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _table_exists(table_name: str) -> bool:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    return table_name in inspector.get_table_names()


def upgrade() -> None:
    if not _table_exists("growthrecord"):
        op.create_table(
            "growthrecord",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("session_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
            sa.Column(
                "source_filename", sqlmodel.sql.sqltypes.AutoString(), nullable=True
            ),
            sa.Column("measurement_date", sa.Date(), nullable=True),
            sa.Column("age_months", sa.Integer(), nullable=True),
            sa.Column("weight_kg", sa.Float(), nullable=True),
            sa.Column("height_cm", sa.Float(), nullable=True),
            sa.Column("head_circumference_cm", sa.Float(), nullable=True),
            sa.Column("notes", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
            sa.Column("raw_ocr_text", sa.Text(), nullable=True),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_growthrecord_session_id", "growthrecord", ["session_id"])


def downgrade() -> None:
    if _table_exists("growthrecord"):
        op.drop_index("ix_growthrecord_session_id", table_name="growthrecord")
        op.drop_table("growthrecord")
