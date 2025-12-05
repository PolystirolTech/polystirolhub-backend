"""add_avatar_to_user_2

Revision ID: eec0708f97bd
Revises: bc030d3429d5
Create Date: 2025-12-05 21:00:02.183555

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'eec0708f97bd'
down_revision = 'bc030d3429d5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('avatar', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'avatar')
