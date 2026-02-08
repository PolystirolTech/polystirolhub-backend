"""add_shop_order_target_username

Revision ID: a90c4293e1e3
Revises: ef110abe7d2d
Create Date: 2026-02-08 17:52:49.673553

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a90c4293e1e3'
down_revision = 'ef110abe7d2d'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('shop_orders', sa.Column('target_username', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('shop_orders', 'target_username')
