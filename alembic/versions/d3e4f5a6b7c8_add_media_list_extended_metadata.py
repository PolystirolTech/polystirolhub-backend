"""add_media_list_extended_metadata

Revision ID: d3e4f5a6b7c8
Revises: c2d3e4f5a6b7
Create Date: 2026-04-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'd3e4f5a6b7c8'
down_revision = 'c2d3e4f5a6b7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('media_list', sa.Column('description', sa.Text(), nullable=True))
    op.add_column('media_list', sa.Column('genres', sa.JSON(), nullable=True))
    op.add_column('media_list', sa.Column('source_rating', sa.Float(), nullable=True))
    op.add_column('media_list', sa.Column('year', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('media_list', 'year')
    op.drop_column('media_list', 'source_rating')
    op.drop_column('media_list', 'genres')
    op.drop_column('media_list', 'description')
