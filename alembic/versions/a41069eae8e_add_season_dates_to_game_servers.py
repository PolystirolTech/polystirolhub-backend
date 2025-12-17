"""add_season_dates_to_game_servers

Revision ID: a41069eae8e
Revises: 3186e5faef41
Create Date: 2025-01-20 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = 'a41069eae8e'
down_revision = '3186e5faef41'
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
	
	if 'season_start' not in existing_columns:
		op.add_column('game_servers', sa.Column('season_start', sa.Date(), nullable=True))
	if 'season_end' not in existing_columns:
		op.add_column('game_servers', sa.Column('season_end', sa.Date(), nullable=True))


def downgrade() -> None:
	op.drop_column('game_servers', 'season_end')
	op.drop_column('game_servers', 'season_start')





