"""add_balance_to_user

Revision ID: d58910808e02
Revises: 32d19276e205
Create Date: 2025-12-12 19:03:36.432624

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'd58910808e02'
down_revision = '32d19276e205'
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.add_column('users', sa.Column('balance', sa.Integer(), nullable=False, server_default='0'))


def downgrade() -> None:
	op.drop_column('users', 'balance')
