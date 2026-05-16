"""Add soft delete fields

Revision ID: 8dc30850dece
Revises: 20260513_0003
Create Date: 2026-05-14 15:55:11.358738

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel



revision: str = '8dc30850dece'
down_revision: Union[str, Sequence[str], None] = '20260513_0003'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ✅ ChildProfile Table
    op.add_column(
        'childprofile',
        sa.Column(
            'is_deleted', 
            sa.Boolean(), 
            server_default=sa.text('false'),  # ✅ WAJIB: Agar data existing dapat nilai default
            nullable=False
        )
    )
    op.add_column(
        'childprofile', 
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    # ✅ ChatMessage Table
    op.add_column(
        'chatmessage',
        sa.Column(
            'is_deleted', 
            sa.Boolean(), 
            server_default=sa.text('false'),  # ✅ WAJIB: Agar data existing dapat nilai default
            nullable=False
        )
    )
    op.add_column(
        'chatmessage', 
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True)
    )
    
    # ✅ Optional: Index untuk query filter
    op.create_index('ix_childprofile_is_deleted', 'childprofile', ['is_deleted'])
    op.create_index('ix_chatmessage_is_deleted', 'chatmessage', ['is_deleted'])


def downgrade() -> None:
    # ✅ Hapus index dulu
    op.drop_index('ix_chatmessage_is_deleted', table_name='chatmessage')
    op.drop_index('ix_childprofile_is_deleted', table_name='childprofile')
    
    # ✅ Hapus kolom
    op.drop_column('chatmessage', 'deleted_at')
    op.drop_column('chatmessage', 'is_deleted')
    op.drop_column('childprofile', 'deleted_at')
    op.drop_column('childprofile', 'is_deleted')