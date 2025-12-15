"""add_badges_system

Revision ID: 6265640ee68d
Revises: d58910808e02
Create Date: 2025-12-12 20:17:05.471499

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '6265640ee68d'
down_revision = 'd58910808e02'
branch_labels = None
depends_on = None


def upgrade() -> None:
	# Создаем enum для типа бэйджа (если еще не существует)
	op.execute("""
		DO $$ BEGIN
			CREATE TYPE badge_type AS ENUM ('temporary', 'event', 'permanent');
		EXCEPTION
			WHEN duplicate_object THEN null;
		END $$;
	""")
	
	badge_type_enum = postgresql.ENUM('temporary', 'event', 'permanent', name='badge_type', create_type=False)
	
	# Создаем таблицу badges
	op.create_table(
		'badges',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('name', sa.String(), nullable=False),
		sa.Column('description', sa.Text(), nullable=True),
		sa.Column('image_url', sa.String(), nullable=False),
		sa.Column('badge_type', badge_type_enum, nullable=False, server_default='permanent'),
		sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.PrimaryKeyConstraint('id')
	)
	op.create_index(op.f('ix_badges_name'), 'badges', ['name'], unique=False)
	
	# Создаем таблицу user_badges
	op.create_table(
		'user_badges',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('badge_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('received_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
		sa.ForeignKeyConstraint(['badge_id'], ['badges.id'], ),
		sa.UniqueConstraint('user_id', 'badge_id', name='uq_user_badge')
	)
	op.create_index(op.f('ix_user_badges_user_id'), 'user_badges', ['user_id'], unique=False)
	op.create_index(op.f('ix_user_badges_badge_id'), 'user_badges', ['badge_id'], unique=False)
	
	# Добавляем поле selected_badge_id в users
	op.add_column('users', sa.Column('selected_badge_id', postgresql.UUID(as_uuid=True), nullable=True))
	op.create_foreign_key('fk_users_selected_badge_id', 'users', 'badges', ['selected_badge_id'], ['id'])


def downgrade() -> None:
	# Удаляем foreign key и колонку selected_badge_id
	op.drop_constraint('fk_users_selected_badge_id', 'users', type_='foreignkey')
	op.drop_column('users', 'selected_badge_id')
	
	# Удаляем таблицу user_badges
	op.drop_index(op.f('ix_user_badges_badge_id'), table_name='user_badges')
	op.drop_index(op.f('ix_user_badges_user_id'), table_name='user_badges')
	op.drop_table('user_badges')
	
	# Удаляем таблицу badges
	op.drop_index(op.f('ix_badges_name'), table_name='badges')
	op.drop_table('badges')
	
	# Удаляем enum
	badge_type_enum = postgresql.ENUM(name='badge_type')
	badge_type_enum.drop(op.get_bind(), checkfirst=True)
