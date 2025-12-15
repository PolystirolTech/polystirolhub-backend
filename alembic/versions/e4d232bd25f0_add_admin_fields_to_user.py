"""add_admin_fields_to_user

Revision ID: e4d232bd25f0
Revises: f1a2b3c4d5e6
Create Date: 2025-12-07 13:59:10.518143

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'e4d232bd25f0'
down_revision = 'f1a2b3c4d5e6'
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'))
	op.add_column('users', sa.Column('is_super_admin', sa.Boolean(), nullable=False, server_default='false'))


def downgrade() -> None:
	op.drop_column('users', 'is_super_admin')
	op.drop_column('users', 'is_admin')
