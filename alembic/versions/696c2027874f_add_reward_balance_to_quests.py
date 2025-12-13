"""add_reward_balance_to_quests

Revision ID: 696c2027874f
Revises: 2788caba6427
Create Date: 2025-12-14 00:56:55.539626

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect


# revision identifiers, used by Alembic.
revision = '696c2027874f'
down_revision = '2788caba6427'
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
	# Добавляем колонку reward_balance в quests
	op.add_column('quests', sa.Column('reward_balance', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
	# Удаляем колонку reward_balance из quests
	drop_column_if_exists('quests', 'reward_balance')
