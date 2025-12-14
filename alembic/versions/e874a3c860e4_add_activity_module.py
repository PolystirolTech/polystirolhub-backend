"""add_activity_module

Revision ID: e874a3c860e4
Revises: 4d7b75d36102
Create Date: 2025-01-17 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = 'e874a3c860e4'
down_revision = '4d7b75d36102'
branch_labels = None
depends_on = None


def upgrade() -> None:
	# Создаем enum для типа активности
	op.execute("""
		DO $$ BEGIN
			CREATE TYPE activity_type AS ENUM (
				'badge_earned',
				'achievement_unlocked',
				'quest_completed',
				'level_up',
				'leaderboard_first_place',
				'leaderboard_changed',
				'daily_quests_refreshed',
				'server_status_changed',
				'new_user'
			);
		EXCEPTION
			WHEN duplicate_object THEN null;
		END $$;
	""")
	
	activity_type_enum = postgresql.ENUM(
		'badge_earned',
		'achievement_unlocked',
		'quest_completed',
		'level_up',
		'leaderboard_first_place',
		'leaderboard_changed',
		'daily_quests_refreshed',
		'server_status_changed',
		'new_user',
		name='activity_type',
		create_type=False
	)
	
	# Создаем таблицу activities
	op.create_table(
		'activities',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('activity_type', activity_type_enum, nullable=False),
		sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=True),
		sa.Column('server_id', postgresql.UUID(as_uuid=True), nullable=True),
		sa.Column('title', sa.String(), nullable=False),
		sa.Column('description', sa.Text(), nullable=True),
		sa.Column('meta_data', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
		sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
		sa.ForeignKeyConstraint(['server_id'], ['game_servers.id'], )
	)
	
	# Создаем индексы
	op.create_index(op.f('ix_activities_activity_type'), 'activities', ['activity_type'], unique=False)
	op.create_index(op.f('ix_activities_user_id'), 'activities', ['user_id'], unique=False)
	op.create_index('ix_activities_created_at', 'activities', [sa.text('created_at DESC')], unique=False)
	op.create_index('ix_activities_type_created', 'activities', ['activity_type', sa.text('created_at DESC')], unique=False)


def downgrade() -> None:
	# Удаляем индексы
	op.drop_index('ix_activities_type_created', table_name='activities')
	op.drop_index('ix_activities_created_at', table_name='activities')
	op.drop_index(op.f('ix_activities_user_id'), table_name='activities')
	op.drop_index(op.f('ix_activities_activity_type'), table_name='activities')
	
	# Удаляем таблицу activities
	op.drop_table('activities')
	
	# Удаляем enum
	activity_type_enum = postgresql.ENUM(name='activity_type')
	activity_type_enum.drop(op.get_bind(), checkfirst=True)
