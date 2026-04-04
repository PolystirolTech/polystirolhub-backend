"""add_series_to_media_type

Revision ID: c2d3e4f5a6b7
Revises: b1c2d3e4f5a6
Create Date: 2026-04-04 00:00:00.000000

"""
from alembic import op

revision = 'c2d3e4f5a6b7'
down_revision = 'b1c2d3e4f5a6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("ALTER TYPE media_type ADD VALUE IF NOT EXISTS 'series'")


def downgrade() -> None:
    # PostgreSQL не поддерживает удаление значений из enum без пересоздания типа
    pass
