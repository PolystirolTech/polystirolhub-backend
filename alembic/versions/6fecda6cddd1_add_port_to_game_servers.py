"""add_port_to_game_servers

Revision ID: 6fecda6cddd1
Revises: 41bec350a356
Create Date: 2025-12-07 21:04:29.654314

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '6fecda6cddd1'
down_revision = '41bec350a356'
branch_labels = None
depends_on = None


def upgrade() -> None:
	op.add_column('game_servers', sa.Column('port', sa.Integer(), nullable=True))


def downgrade() -> None:
	op.drop_column('game_servers', 'port')
