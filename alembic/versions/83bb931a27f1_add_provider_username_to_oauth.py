"""add_provider_username_to_oauth

Revision ID: 83bb931a27f1
Revises: eec0708f97bd
Create Date: 2025-12-06 16:44:28.926587

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '83bb931a27f1'
down_revision = 'eec0708f97bd'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('oauth_accounts', sa.Column('provider_username', sa.String(), nullable=True))



def downgrade() -> None:
    op.drop_column('oauth_accounts', 'provider_username')

