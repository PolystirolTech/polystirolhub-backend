"""add_external_links_table

Revision ID: 19dda1fee862
Revises: 6fecda6cddd1
Create Date: 2025-12-09 20:25:16.957988

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '19dda1fee862'
down_revision = '6fecda6cddd1'
branch_labels = None
depends_on = None


def upgrade() -> None:
	# Создаем таблицу external_links
	op.create_table(
		'external_links',
		sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('platform', sa.String(), nullable=False),
		sa.Column('external_id', sa.String(), nullable=False),
		sa.Column('platform_username', sa.String(), nullable=True),
		sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['user_id'], ['users.id'], )
	)
	op.create_index(op.f('ix_external_links_user_id'), 'external_links', ['user_id'], unique=False)
	op.create_unique_constraint('uq_platform_external_id', 'external_links', ['platform', 'external_id'])


def downgrade() -> None:
	op.drop_constraint('uq_platform_external_id', 'external_links', type_='unique')
	op.drop_index(op.f('ix_external_links_user_id'), table_name='external_links')
	op.drop_table('external_links')
