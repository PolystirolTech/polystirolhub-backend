"""add_resource_pack_url_to_game_servers

Revision ID: b2ab663569c7
Revises: 6265640ee68d
Create Date: 2025-12-13 11:43:53.142893

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'b2ab663569c7'
down_revision = '6265640ee68d'
branch_labels = None
depends_on = None


def upgrade() -> None:
	conn = op.get_bind()
	
	# Проверяем наличие столбцов
	result = conn.execute(text("""
		SELECT column_name 
		FROM information_schema.columns 
		WHERE table_name = 'game_servers'
	"""))
	existing_columns = {row[0] for row in result}
	
	if 'resource_pack_url' not in existing_columns:
		op.add_column('game_servers', sa.Column('resource_pack_url', sa.String(), nullable=True))
	if 'resource_pack_hash' not in existing_columns:
		op.add_column('game_servers', sa.Column('resource_pack_hash', sa.String(), nullable=True))


def downgrade() -> None:
	op.drop_column('game_servers', 'resource_pack_hash')
	op.drop_column('game_servers', 'resource_pack_url')
