"""add_game_servers_system

Revision ID: 41bec350a356
Revises: e4d232bd25f0
Create Date: 2025-12-07 16:21:16.829114

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '41bec350a356'
down_revision = 'e4d232bd25f0'
branch_labels = None
depends_on = None


def upgrade() -> None:
	# Создаем таблицу game_types
	op.create_table(
		'game_types',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('name', sa.String(), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.PrimaryKeyConstraint('id')
	)
	op.create_index(op.f('ix_game_types_name'), 'game_types', ['name'], unique=True)
	
	# Создаем таблицу game_servers
	op.create_table(
		'game_servers',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('game_type_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('name', sa.String(), nullable=False),
		sa.Column('banner_url', sa.String(), nullable=True),
		sa.Column('description', sa.Text(), nullable=True),
		sa.Column('mods', postgresql.ARRAY(sa.String()), nullable=False, server_default='{}'),
		sa.Column('ip', sa.String(), nullable=False),
		sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['game_type_id'], ['game_types.id'], )
	)
	op.create_index(op.f('ix_game_servers_game_type_id'), 'game_servers', ['game_type_id'], unique=False)
	op.create_index(op.f('ix_game_servers_name'), 'game_servers', ['name'], unique=False)


def downgrade() -> None:
	op.drop_index(op.f('ix_game_servers_name'), table_name='game_servers')
	op.drop_index(op.f('ix_game_servers_game_type_id'), table_name='game_servers')
	op.drop_table('game_servers')
	op.drop_index(op.f('ix_game_types_name'), table_name='game_types')
	op.drop_table('game_types')
