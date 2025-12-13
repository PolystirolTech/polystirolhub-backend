"""add_unicode_char_to_badges

Revision ID: 4f9ea516a799
Revises: b2ab663569c7
Create Date: 2025-12-13 12:40:16.764136

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text


# revision identifiers, used by Alembic.
revision = '4f9ea516a799'
down_revision = 'b2ab663569c7'
branch_labels = None
depends_on = None


def upgrade() -> None:
	conn = op.get_bind()
	
	# Проверяем наличие столбца
	result = conn.execute(text("""
		SELECT column_name 
		FROM information_schema.columns 
		WHERE table_name = 'badges' AND column_name = 'unicode_char'
	"""))
	
	if result.fetchone() is None:
		op.add_column('badges', sa.Column('unicode_char', sa.String(), nullable=True))


def downgrade() -> None:
	op.drop_column('badges', 'unicode_char')
