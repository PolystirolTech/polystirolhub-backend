"""add_is_custom_to_media_list

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
Create Date: 2026-04-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'e4f5a6b7c8d9'
down_revision = 'd3e4f5a6b7c8'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        'media_list',
        sa.Column('is_custom', sa.Boolean(), nullable=False, server_default='false'),
    )


def downgrade():
    op.drop_column('media_list', 'is_custom')
