"""add_provider_avatar_to_oauth_account

Revision ID: a8455573ccbc
Revises: 83bb931a27f1
Create Date: 2025-12-06 17:01:05.178813

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'a8455573ccbc'
down_revision = '83bb931a27f1'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('oauth_accounts', sa.Column('provider_avatar', sa.String(), nullable=True))



def downgrade() -> None:
    op.drop_column('oauth_accounts', 'provider_avatar')
