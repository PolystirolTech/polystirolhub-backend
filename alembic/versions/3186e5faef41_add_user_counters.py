"""add_user_counters

Revision ID: 3186e5faef41
Revises: e874a3c860e4
Create Date: 2025-12-14 23:25:40.932961

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '3186e5faef41'
down_revision = 'e874a3c860e4'
branch_labels = None
depends_on = None


def upgrade() -> None:
	# Создаем таблицу user_counters
	op.create_table(
		'user_counters',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('counter_key', sa.String(), nullable=False),
		sa.Column('value', sa.BigInteger(), nullable=False, server_default='0'),
		sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
		sa.UniqueConstraint('user_id', 'counter_key', name='uq_user_counter')
	)
	
	# Создаем индексы
	op.create_index(op.f('ix_user_counters_user_id'), 'user_counters', ['user_id'], unique=False)
	op.create_index(op.f('ix_user_counters_counter_key'), 'user_counters', ['counter_key'], unique=False)


def downgrade() -> None:
	# Удаляем индексы
	op.drop_index(op.f('ix_user_counters_counter_key'), table_name='user_counters')
	op.drop_index(op.f('ix_user_counters_user_id'), table_name='user_counters')
	
	# Удаляем таблицу user_counters
	op.drop_table('user_counters')
