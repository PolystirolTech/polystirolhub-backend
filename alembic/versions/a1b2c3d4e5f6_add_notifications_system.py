"""add_notifications_system

Revision ID: a1b2c3d4e5f6
Revises: 696c2027874f
Create Date: 2025-01-15 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'a1b2c3d4e5f6'
down_revision = '696c2027874f'
branch_labels = None
depends_on = None


def upgrade() -> None:
	# Создаем таблицу notifications
	op.create_table(
		'notifications',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('notification_type', sa.String(), nullable=False),
		sa.Column('title', sa.String(), nullable=False),
		sa.Column('message', sa.Text(), nullable=True),
		sa.Column('reward_xp', sa.Integer(), nullable=False, server_default='0'),
		sa.Column('reward_balance', sa.Integer(), nullable=False, server_default='0'),
		sa.Column('meta_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['user_id'], ['users.id'], )
	)
	
	# Создаем индексы
	op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)
	op.create_index(op.f('ix_notifications_created_at'), 'notifications', ['created_at'], unique=False)
	op.create_index('ix_notifications_user_created', 'notifications', ['user_id', sa.text('created_at DESC')], unique=False)


def downgrade() -> None:
	# Удаляем индексы
	op.drop_index('ix_notifications_user_created', table_name='notifications')
	op.drop_index(op.f('ix_notifications_created_at'), table_name='notifications')
	op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
	
	# Удаляем таблицу notifications
	op.drop_table('notifications')
