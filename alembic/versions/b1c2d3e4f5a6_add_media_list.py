"""add_media_list

Revision ID: b1c2d3e4f5a6
Revises: a90c4293e1e3
Create Date: 2026-04-04 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, ENUM as PG_ENUM

revision = 'b1c2d3e4f5a6'
down_revision = 'a90c4293e1e3'
branch_labels = None
depends_on = None

media_type_enum = PG_ENUM('anime', 'movie', 'game', 'album', name='media_type', create_type=False)
media_status_enum = PG_ENUM('planned', 'in_progress', 'completed', 'dropped', name='media_status', create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    PG_ENUM('anime', 'movie', 'game', 'album', name='media_type').create(bind, checkfirst=True)
    PG_ENUM('planned', 'in_progress', 'completed', 'dropped', name='media_status').create(bind, checkfirst=True)

    op.create_table(
        'media_list',
        sa.Column('id', UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('media_type', media_type_enum, nullable=False),
        sa.Column('title', sa.String(), nullable=False),
        sa.Column('cover_url', sa.String(), nullable=True),
        sa.Column('external_id', sa.String(), nullable=True),
        sa.Column('status', media_status_enum, nullable=True),
        sa.Column('rating', sa.SmallInteger(), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('is_favorite', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('is_public', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('started_at', sa.Date(), nullable=True),
        sa.Column('completed_at', sa.Date(), nullable=True),
        sa.Column('play_time_hours', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    op.create_unique_constraint('uq_media_list_user_title_type', 'media_list', ['user_id', 'title', 'media_type'])
    op.create_index('ix_media_list_user_id', 'media_list', ['user_id'])
    op.create_index('ix_media_list_user_type', 'media_list', ['user_id', 'media_type'])
    op.create_index('ix_media_list_user_favorite', 'media_list', ['user_id', 'is_favorite'])


def downgrade() -> None:
    op.drop_table('media_list')
    bind = op.get_bind()
    PG_ENUM(name='media_status').drop(bind, checkfirst=True)
    PG_ENUM(name='media_type').drop(bind, checkfirst=True)
