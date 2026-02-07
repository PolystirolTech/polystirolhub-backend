"""add_server_whitelist_system

Revision ID: add_whitelist_001
Revises: 3cbb64e1a9de
Create Date: 2025-02-07

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "add_whitelist_001"
down_revision = "3cbb64e1a9de"
branch_labels = None
depends_on = None


def upgrade() -> None:
	# Флаг вайтлиста у сервера
	op.add_column(
		"game_servers",
		sa.Column("is_whitelist", sa.Boolean(), nullable=False, server_default=sa.false()),
	)

	# Enum для статуса заявки вайтлиста
	whitelist_status = postgresql.ENUM("pending", "approved", "rejected", name="whitelist_status", create_type=True)
	whitelist_status.create(op.get_bind(), checkfirst=True)

	# Таблица заявок/записей вайтлиста
	op.create_table(
		"server_whitelist_entries",
		sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("server_id", postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=True),
		sa.Column("nickname", sa.String(255), nullable=False),
		sa.Column("status", postgresql.ENUM("pending", "approved", "rejected", name="whitelist_status", create_type=False), nullable=False, server_default="pending"),
		sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
		sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
		sa.Column("reviewed_by_id", postgresql.UUID(as_uuid=True), nullable=True),
		sa.PrimaryKeyConstraint("id"),
		sa.ForeignKeyConstraint(["server_id"], ["game_servers.id"], ondelete="CASCADE"),
		sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
		sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"], ondelete="SET NULL"),
	)
	op.create_index(op.f("ix_server_whitelist_entries_server_id"), "server_whitelist_entries", ["server_id"], unique=False)
	op.create_index(op.f("ix_server_whitelist_entries_user_id"), "server_whitelist_entries", ["user_id"], unique=False)
	op.create_index("ix_server_whitelist_entries_status", "server_whitelist_entries", ["status"], unique=False)
	op.create_unique_constraint("uq_server_whitelist_nickname", "server_whitelist_entries", ["server_id", "nickname"])


def downgrade() -> None:
	op.drop_constraint("uq_server_whitelist_nickname", "server_whitelist_entries", type_="unique")
	op.drop_index("ix_server_whitelist_entries_status", table_name="server_whitelist_entries")
	op.drop_index(op.f("ix_server_whitelist_entries_user_id"), table_name="server_whitelist_entries")
	op.drop_index(op.f("ix_server_whitelist_entries_server_id"), table_name="server_whitelist_entries")
	op.drop_table("server_whitelist_entries")

	whitelist_status = postgresql.ENUM("pending", "approved", "rejected", name="whitelist_status")
	whitelist_status.drop(op.get_bind(), checkfirst=True)

	op.drop_column("game_servers", "is_whitelist")
