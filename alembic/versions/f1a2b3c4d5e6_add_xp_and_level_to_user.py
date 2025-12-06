"""add_xp_and_level_to_user

Revision ID: f1a2b3c4d5e6
Revises: a8455573ccbc
Create Date: 2025-12-07 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'f1a2b3c4d5e6'
down_revision = 'a8455573ccbc'
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.add_column('users', sa.Column('xp', sa.Integer(), nullable=False, server_default='0'))
	op.add_column('users', sa.Column('level', sa.Integer(), nullable=False, server_default='1'))


def downgrade() -> None:
	op.drop_column('users', 'level')
	op.drop_column('users', 'xp')
