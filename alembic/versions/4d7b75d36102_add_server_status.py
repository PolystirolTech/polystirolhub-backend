"""add_server_status

Revision ID: 4d7b75d36102
Revises: a1b2c3d4e5f6
Create Date: 2025-01-16 16:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '4d7b75d36102'
down_revision = 'a1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
	# Создаем enum для статуса сервера (если еще не существует)
	op.execute("""
		DO $$ BEGIN
			CREATE TYPE server_status AS ENUM ('active', 'disabled', 'maintenance');
		EXCEPTION
			WHEN duplicate_object THEN null;
		END $$;
	""")
	
	server_status_enum = postgresql.ENUM('active', 'disabled', 'maintenance', name='server_status', create_type=False)
	
	# Добавляем колонку status в таблицу game_servers
	op.add_column('game_servers', sa.Column('status', server_status_enum, nullable=False, server_default='active'))
	op.create_index(op.f('ix_game_servers_status'), 'game_servers', ['status'], unique=False)


def downgrade() -> None:
	# Удаляем индекс
	op.drop_index(op.f('ix_game_servers_status'), table_name='game_servers')
	
	# Удаляем колонку status
	op.drop_column('game_servers', 'status')
	
	# Удаляем enum
	server_status_enum = postgresql.ENUM(name='server_status')
	server_status_enum.drop(op.get_bind(), checkfirst=True)
