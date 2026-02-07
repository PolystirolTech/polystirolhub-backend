"""add_background_to_user

Revision ID: 33ef3cb7f6b7
Revises: add_whitelist_001
Create Date: 2026-02-07 18:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '33ef3cb7f6b7'
down_revision = 'add_whitelist_001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('background', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'background')
