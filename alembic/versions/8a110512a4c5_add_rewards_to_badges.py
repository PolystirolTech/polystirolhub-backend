"""add_rewards_to_badges

Revision ID: 8a110512a4c5
Revises: de12377cb780
Create Date: 2025-12-13 22:43:55.489713

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '8a110512a4c5'
down_revision = 'de12377cb780'
branch_labels = None
depends_on = None


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
	# Добавляем колонки наград в badges
	op.add_column('badges', sa.Column('reward_xp', sa.Integer(), nullable=False, server_default='0'))
	op.add_column('badges', sa.Column('reward_balance', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
	# Удаляем колонки наград из badges
	drop_column_if_exists('badges', 'reward_balance')
	drop_column_if_exists('badges', 'reward_xp')
