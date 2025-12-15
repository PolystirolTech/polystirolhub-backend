"""add_achievements_and_daily_quests_system

Revision ID: de12377cb780
Revises: 4f9ea516a799
Create Date: 2025-12-13 20:58:00.912484

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = 'de12377cb780'
down_revision = '4f9ea516a799'
branch_labels = None
depends_on = None


def drop_index_if_exists(index_name: str, table_name: str) -> None:
	"""Безопасно удаляет индекс, если он существует"""
	conn = op.get_bind()
	inspector = inspect(conn)
	if not inspector.has_table(table_name):
		return
	indexes = [idx['name'] for idx in inspector.get_indexes(table_name)]
	if index_name in indexes:
		op.drop_index(index_name, table_name=table_name)


def drop_table_if_exists(table_name: str) -> None:
	"""Безопасно удаляет таблицу, если она существует"""
	conn = op.get_bind()
	inspector = inspect(conn)
	if inspector.has_table(table_name):
		op.drop_table(table_name)


def drop_column_if_exists(table_name: str, column_name: str) -> None:
	"""Безопасно удаляет колонку, если она существует"""
	conn = op.get_bind()
	inspector = inspect(conn)
	if not inspector.has_table(table_name):
		return
	columns = [col['name'] for col in inspector.get_columns(table_name)]
	if column_name in columns:
		op.drop_column(table_name, column_name)


def upgrade() -> None:
	# Создаем enum для типа квеста
	op.execute("""
		DO $$ BEGIN
			CREATE TYPE quest_type AS ENUM ('daily', 'achievement');
		EXCEPTION
			WHEN duplicate_object THEN null;
		END $$;
	""")
	
	quest_type_enum = postgresql.ENUM('daily', 'achievement', name='quest_type', create_type=False)
	
	# Создаем таблицу quests
	op.create_table(
		'quests',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('name', sa.String(), nullable=False),
		sa.Column('description', sa.Text(), nullable=True),
		sa.Column('quest_type', quest_type_enum, nullable=False),
		sa.Column('condition_key', sa.String(), nullable=False),
		sa.Column('target_value', sa.Integer(), nullable=False),
		sa.Column('reward_xp', sa.Integer(), nullable=False, server_default='0'),
		sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
		sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.PrimaryKeyConstraint('id')
	)
	op.create_index(op.f('ix_quests_name'), 'quests', ['name'], unique=False)
	op.create_index(op.f('ix_quests_quest_type'), 'quests', ['quest_type'], unique=False)
	op.create_index(op.f('ix_quests_is_active'), 'quests', ['is_active'], unique=False)
	op.create_index(op.f('ix_quests_condition_key'), 'quests', ['condition_key'], unique=False)
	
	# Создаем таблицу user_quests
	op.create_table(
		'user_quests',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('quest_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
		sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
		sa.Column('claimed_at', sa.DateTime(timezone=True), nullable=True),
		sa.Column('quest_date', sa.Date(), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
		sa.ForeignKeyConstraint(['quest_id'], ['quests.id'], ),
		sa.UniqueConstraint('user_id', 'quest_id', 'quest_date', name='uq_user_quest_date')
	)
	op.create_index(op.f('ix_user_quests_user_id'), 'user_quests', ['user_id'], unique=False)
	op.create_index(op.f('ix_user_quests_quest_id'), 'user_quests', ['quest_id'], unique=False)
	op.create_index(op.f('ix_user_quests_quest_date'), 'user_quests', ['quest_date'], unique=False)
	
	# Расширяем таблицу badges
	op.add_column('badges', sa.Column('condition_key', sa.String(), nullable=True))
	op.add_column('badges', sa.Column('target_value', sa.Integer(), nullable=True))
	op.add_column('badges', sa.Column('auto_check', sa.Boolean(), nullable=False, server_default='false'))
	op.create_index(op.f('ix_badges_condition_key'), 'badges', ['condition_key'], unique=False)
	op.create_index(op.f('ix_badges_auto_check'), 'badges', ['auto_check'], unique=False)
	
	# Создаем таблицу user_badge_progress
	op.create_table(
		'user_badge_progress',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('badge_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('progress', sa.Integer(), nullable=False, server_default='0'),
		sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
		sa.ForeignKeyConstraint(['badge_id'], ['badges.id'], ),
		sa.UniqueConstraint('user_id', 'badge_id', name='uq_user_badge_progress')
	)
	op.create_index(op.f('ix_user_badge_progress_user_id'), 'user_badge_progress', ['user_id'], unique=False)
	op.create_index(op.f('ix_user_badge_progress_badge_id'), 'user_badge_progress', ['badge_id'], unique=False)


def downgrade() -> None:
	# Удаляем таблицу user_badge_progress
	drop_index_if_exists('ix_user_badge_progress_badge_id', 'user_badge_progress')
	drop_index_if_exists('ix_user_badge_progress_user_id', 'user_badge_progress')
	drop_table_if_exists('user_badge_progress')
	
	# Удаляем колонки из badges
	drop_index_if_exists('ix_badges_auto_check', 'badges')
	drop_index_if_exists('ix_badges_condition_key', 'badges')
	drop_column_if_exists('badges', 'auto_check')
	drop_column_if_exists('badges', 'target_value')
	drop_column_if_exists('badges', 'condition_key')
	
	# Удаляем таблицу user_quests
	drop_index_if_exists('ix_user_quests_quest_date', 'user_quests')
	drop_index_if_exists('ix_user_quests_quest_id', 'user_quests')
	drop_index_if_exists('ix_user_quests_user_id', 'user_quests')
	drop_table_if_exists('user_quests')
	
	# Удаляем таблицу quests
	drop_index_if_exists('ix_quests_condition_key', 'quests')
	drop_index_if_exists('ix_quests_is_active', 'quests')
	drop_index_if_exists('ix_quests_quest_type', 'quests')
	drop_index_if_exists('ix_quests_name', 'quests')
	drop_table_if_exists('quests')
	
	# Удаляем enum
	quest_type_enum = postgresql.ENUM(name='quest_type')
	quest_type_enum.drop(op.get_bind(), checkfirst=True)
