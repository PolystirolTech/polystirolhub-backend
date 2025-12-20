"""add_resource_collection_system

Revision ID: dc3aa69c4a86
Revises: a41069eae8e
Create Date: 2025-01-27 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'dc3aa69c4a86'
down_revision = 'a41069eae8e'
branch_labels = None
depends_on = None


def upgrade() -> None:
	# Создаем таблицу resource_goals
	op.create_table(
		'resource_goals',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('name', sa.String(), nullable=False),
		sa.Column('resource_type', sa.String(), nullable=False),
		sa.Column('target_amount', sa.Integer(), nullable=False),
		sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
		sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['server_id'], ['game_servers.id'], )
	)
	op.create_index(op.f('ix_resource_goals_server_id'), 'resource_goals', ['server_id'], unique=False)
	op.create_index(op.f('ix_resource_goals_resource_type'), 'resource_goals', ['resource_type'], unique=False)
	op.create_index('ix_resource_goals_server_resource', 'resource_goals', ['server_id', 'resource_type'], unique=False)
	
	# Создаем таблицу resource_progress
	op.create_table(
		'resource_progress',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('resource_type', sa.String(), nullable=False),
		sa.Column('current_amount', sa.Integer(), nullable=False, server_default='0'),
		sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['server_id'], ['game_servers.id'], ),
		sa.UniqueConstraint('server_id', 'resource_type', name='uq_resource_progress_server_resource')
	)
	op.create_index(op.f('ix_resource_progress_server_id'), 'resource_progress', ['server_id'], unique=False)
	op.create_index(op.f('ix_resource_progress_resource_type'), 'resource_progress', ['resource_type'], unique=False)
	op.create_index('ix_resource_progress_server_resource', 'resource_progress', ['server_id', 'resource_type'], unique=False)


def downgrade() -> None:
	op.drop_index('ix_resource_progress_server_resource', table_name='resource_progress')
	op.drop_index(op.f('ix_resource_progress_resource_type'), table_name='resource_progress')
	op.drop_index(op.f('ix_resource_progress_server_id'), table_name='resource_progress')
	op.drop_table('resource_progress')
	op.drop_index('ix_resource_goals_server_resource', table_name='resource_goals')
	op.drop_index(op.f('ix_resource_goals_resource_type'), table_name='resource_goals')
	op.drop_index(op.f('ix_resource_goals_server_id'), table_name='resource_goals')
	op.drop_table('resource_goals')

