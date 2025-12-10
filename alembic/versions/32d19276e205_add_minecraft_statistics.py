"""add_minecraft_statistics

Revision ID: 32d19276e205
Revises: 19dda1fee862
Create Date: 2025-01-27 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '32d19276e205'
down_revision = '19dda1fee862'
branch_labels = None
depends_on = None


def upgrade() -> None:
	# Таблица minecraft_servers - связь с game_servers
	op.create_table(
		'minecraft_servers',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('game_server_id', postgresql.UUID(as_uuid=True), nullable=False),
		sa.Column('server_uuid', sa.String(length=36), nullable=False),
		sa.Column('name', sa.String(length=100), nullable=False),
		sa.Column('web_address', sa.String(length=100), nullable=True),
		sa.Column('is_installed', sa.Boolean(), nullable=False, server_default='true'),
		sa.Column('is_proxy', sa.Boolean(), nullable=False, server_default='false'),
		sa.Column('max_players', sa.Integer(), nullable=False, server_default='-1'),
		sa.Column('plan_version', sa.String(length=18), nullable=False, server_default='Old'),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['game_server_id'], ['game_servers.id'], ),
		sa.UniqueConstraint('game_server_id'),
		sa.UniqueConstraint('server_uuid')
	)
	op.create_index(op.f('ix_minecraft_servers_game_server_id'), 'minecraft_servers', ['game_server_id'], unique=True)
	op.create_index(op.f('ix_minecraft_servers_server_uuid'), 'minecraft_servers', ['server_uuid'], unique=True)

	# Таблица minecraft_users - базовая информация об игроках
	op.create_table(
		'minecraft_users',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('uuid', sa.String(length=36), nullable=False),
		sa.Column('registered', sa.BigInteger(), nullable=False),
		sa.Column('name', sa.String(length=36), nullable=False),
		sa.Column('times_kicked', sa.Integer(), nullable=False, server_default='0'),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('uuid')
	)
	op.create_index(op.f('ix_minecraft_users_uuid'), 'minecraft_users', ['uuid'], unique=True)
	op.create_index(op.f('ix_minecraft_users_name'), 'minecraft_users', ['name'], unique=False)

	# Таблица minecraft_join_address - адреса подключений
	op.create_table(
		'minecraft_join_address',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('join_address', sa.String(length=191), nullable=False),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('join_address')
	)
	op.create_index(op.f('ix_minecraft_join_address_join_address'), 'minecraft_join_address', ['join_address'], unique=True)

	# Таблица minecraft_user_info - информация об игроке на конкретном сервере
	op.create_table(
		'minecraft_user_info',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('user_id', sa.Integer(), nullable=False),
		sa.Column('server_id', sa.Integer(), nullable=False),
		sa.Column('join_address', sa.String(length=191), nullable=True),
		sa.Column('registered', sa.BigInteger(), nullable=False),
		sa.Column('opped', sa.Boolean(), nullable=False, server_default='false'),
		sa.Column('banned', sa.Boolean(), nullable=False, server_default='false'),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['user_id'], ['minecraft_users.id'], ),
		sa.ForeignKeyConstraint(['server_id'], ['minecraft_servers.id'], )
	)
	op.create_index(op.f('ix_minecraft_user_info_user_id'), 'minecraft_user_info', ['user_id'], unique=False)
	op.create_index(op.f('ix_minecraft_user_info_server_id'), 'minecraft_user_info', ['server_id'], unique=False)

	# Таблица minecraft_sessions - игровые сессии
	op.create_table(
		'minecraft_sessions',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('user_id', sa.Integer(), nullable=False),
		sa.Column('server_id', sa.Integer(), nullable=False),
		sa.Column('session_start', sa.BigInteger(), nullable=False),
		sa.Column('session_end', sa.BigInteger(), nullable=True),
		sa.Column('mob_kills', sa.Integer(), nullable=True),
		sa.Column('deaths', sa.Integer(), nullable=True),
		sa.Column('afk_time', sa.BigInteger(), nullable=True),
		sa.Column('join_address_id', sa.Integer(), nullable=False, server_default='1'),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['user_id'], ['minecraft_users.id'], ),
		sa.ForeignKeyConstraint(['server_id'], ['minecraft_servers.id'], ),
		sa.ForeignKeyConstraint(['join_address_id'], ['minecraft_join_address.id'], )
	)
	op.create_index(op.f('ix_minecraft_sessions_user_id'), 'minecraft_sessions', ['user_id'], unique=False)
	op.create_index(op.f('ix_minecraft_sessions_server_id'), 'minecraft_sessions', ['server_id'], unique=False)

	# Таблица minecraft_nicknames - история ников
	op.create_table(
		'minecraft_nicknames',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('uuid', sa.String(length=36), nullable=False),
		sa.Column('nickname', sa.String(length=75), nullable=False),
		sa.Column('server_uuid', sa.String(length=36), nullable=False),
		sa.Column('last_used', sa.BigInteger(), nullable=False),
		sa.PrimaryKeyConstraint('id')
	)
	op.create_index(op.f('ix_minecraft_nicknames_uuid'), 'minecraft_nicknames', ['uuid'], unique=False)
	op.create_index(op.f('ix_minecraft_nicknames_server_uuid'), 'minecraft_nicknames', ['server_uuid'], unique=False)

	# Таблица minecraft_kills - убийства
	op.create_table(
		'minecraft_kills',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('killer_uuid', sa.String(length=36), nullable=False),
		sa.Column('victim_uuid', sa.String(length=36), nullable=False),
		sa.Column('server_uuid', sa.String(length=36), nullable=False),
		sa.Column('weapon', sa.String(length=30), nullable=True),
		sa.Column('date', sa.BigInteger(), nullable=False),
		sa.Column('session_id', sa.Integer(), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['session_id'], ['minecraft_sessions.id'], )
	)
	op.create_index(op.f('ix_minecraft_kills_killer_uuid'), 'minecraft_kills', ['killer_uuid'], unique=False)
	op.create_index(op.f('ix_minecraft_kills_victim_uuid'), 'minecraft_kills', ['victim_uuid'], unique=False)
	op.create_index(op.f('ix_minecraft_kills_server_uuid'), 'minecraft_kills', ['server_uuid'], unique=False)
	op.create_index(op.f('ix_minecraft_kills_date'), 'minecraft_kills', ['date'], unique=False)

	# Таблица minecraft_ping - пинг игроков
	op.create_table(
		'minecraft_ping',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('user_id', sa.Integer(), nullable=False),
		sa.Column('server_id', sa.Integer(), nullable=False),
		sa.Column('date', sa.BigInteger(), nullable=False),
		sa.Column('max_ping', sa.Integer(), nullable=True),
		sa.Column('min_ping', sa.Integer(), nullable=True),
		sa.Column('avg_ping', sa.Double(), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['user_id'], ['minecraft_users.id'], ),
		sa.ForeignKeyConstraint(['server_id'], ['minecraft_servers.id'], )
	)
	op.create_index(op.f('ix_minecraft_ping_user_id'), 'minecraft_ping', ['user_id'], unique=False)
	op.create_index(op.f('ix_minecraft_ping_server_id'), 'minecraft_ping', ['server_id'], unique=False)
	op.create_index(op.f('ix_minecraft_ping_date'), 'minecraft_ping', ['date'], unique=False)

	# Таблица minecraft_platforms - платформы игроков
	op.create_table(
		'minecraft_platforms',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('uuid', sa.String(length=36), nullable=False),
		sa.Column('platform', sa.Integer(), nullable=False),
		sa.Column('bedrock_username', sa.String(length=32), nullable=True),
		sa.Column('java_username', sa.String(length=16), nullable=True),
		sa.Column('linked_player', sa.String(length=16), nullable=True),
		sa.Column('language_code', sa.String(length=8), nullable=True),
		sa.Column('version', sa.String(length=16), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('uuid')
	)
	op.create_index(op.f('ix_minecraft_platforms_uuid'), 'minecraft_platforms', ['uuid'], unique=True)

	# Таблица minecraft_plugin_versions - версии плагинов
	op.create_table(
		'minecraft_plugin_versions',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('server_id', sa.Integer(), nullable=False),
		sa.Column('plugin_name', sa.String(length=100), nullable=False),
		sa.Column('version', sa.String(length=255), nullable=True),
		sa.Column('modified', sa.BigInteger(), nullable=False, server_default='0'),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['server_id'], ['minecraft_servers.id'], )
	)
	op.create_index(op.f('ix_minecraft_plugin_versions_server_id'), 'minecraft_plugin_versions', ['server_id'], unique=False)

	# Таблица minecraft_worlds - миры на серверах
	op.create_table(
		'minecraft_worlds',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('world_name', sa.String(length=100), nullable=False),
		sa.Column('server_uuid', sa.String(length=36), nullable=False),
		sa.PrimaryKeyConstraint('id')
	)
	op.create_index(op.f('ix_minecraft_worlds_server_uuid'), 'minecraft_worlds', ['server_uuid'], unique=False)

	# Таблица minecraft_tps - производительность серверов
	op.create_table(
		'minecraft_tps',
		sa.Column('server_id', sa.Integer(), nullable=False),
		sa.Column('date', sa.BigInteger(), nullable=False),
		sa.Column('tps', sa.Double(), nullable=True),
		sa.Column('players_online', sa.Integer(), nullable=True),
		sa.Column('cpu_usage', sa.Double(), nullable=True),
		sa.Column('ram_usage', sa.BigInteger(), nullable=True),
		sa.Column('entities', sa.Integer(), nullable=True),
		sa.Column('chunks_loaded', sa.Integer(), nullable=True),
		sa.Column('free_disk_space', sa.BigInteger(), nullable=True),
		sa.PrimaryKeyConstraint('server_id', 'date'),
		sa.ForeignKeyConstraint(['server_id'], ['minecraft_servers.id'], )
	)
	op.create_index(op.f('ix_minecraft_tps_date'), 'minecraft_tps', ['date'], unique=False)

	# Таблица minecraft_world_times - время в разных режимах игры
	op.create_table(
		'minecraft_world_times',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('user_id', sa.Integer(), nullable=False),
		sa.Column('world_id', sa.Integer(), nullable=False),
		sa.Column('server_id', sa.Integer(), nullable=False),
		sa.Column('session_id', sa.Integer(), nullable=True),
		sa.Column('survival_time', sa.BigInteger(), nullable=False, server_default='0'),
		sa.Column('creative_time', sa.BigInteger(), nullable=False, server_default='0'),
		sa.Column('adventure_time', sa.BigInteger(), nullable=False, server_default='0'),
		sa.Column('spectator_time', sa.BigInteger(), nullable=False, server_default='0'),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['user_id'], ['minecraft_users.id'], ),
		sa.ForeignKeyConstraint(['world_id'], ['minecraft_worlds.id'], ),
		sa.ForeignKeyConstraint(['server_id'], ['minecraft_servers.id'], ),
		sa.ForeignKeyConstraint(['session_id'], ['minecraft_sessions.id'], )
	)
	op.create_index(op.f('ix_minecraft_world_times_user_id'), 'minecraft_world_times', ['user_id'], unique=False)
	op.create_index(op.f('ix_minecraft_world_times_world_id'), 'minecraft_world_times', ['world_id'], unique=False)
	op.create_index(op.f('ix_minecraft_world_times_server_id'), 'minecraft_world_times', ['server_id'], unique=False)

	# Таблица minecraft_version_protocol - версии протокола
	op.create_table(
		'minecraft_version_protocol',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('uuid', sa.String(length=36), nullable=False),
		sa.Column('protocol_version', sa.Integer(), nullable=False),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('uuid')
	)
	op.create_index(op.f('ix_minecraft_version_protocol_uuid'), 'minecraft_version_protocol', ['uuid'], unique=True)

	# Таблица minecraft_geolocations - геолокации игроков
	op.create_table(
		'minecraft_geolocations',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('user_id', sa.Integer(), nullable=False),
		sa.Column('geolocation', sa.String(length=50), nullable=True),
		sa.Column('last_used', sa.BigInteger(), nullable=False, server_default='0'),
		sa.PrimaryKeyConstraint('id'),
		sa.ForeignKeyConstraint(['user_id'], ['minecraft_users.id'], )
	)
	op.create_index(op.f('ix_minecraft_geolocations_user_id'), 'minecraft_geolocations', ['user_id'], unique=False)

	# Таблица minecraft_settings - настройки серверов
	op.create_table(
		'minecraft_settings',
		sa.Column('id', sa.Integer(), nullable=False),
		sa.Column('server_uuid', sa.String(length=39), nullable=False),
		sa.Column('updated', sa.BigInteger(), nullable=False),
		sa.Column('content', sa.Text(), nullable=True),
		sa.PrimaryKeyConstraint('id'),
		sa.UniqueConstraint('server_uuid')
	)
	op.create_index(op.f('ix_minecraft_settings_server_uuid'), 'minecraft_settings', ['server_uuid'], unique=True)


def downgrade() -> None:
	op.drop_index(op.f('ix_minecraft_settings_server_uuid'), table_name='minecraft_settings')
	op.drop_table('minecraft_settings')
	op.drop_index(op.f('ix_minecraft_geolocations_user_id'), table_name='minecraft_geolocations')
	op.drop_table('minecraft_geolocations')
	op.drop_index(op.f('ix_minecraft_version_protocol_uuid'), table_name='minecraft_version_protocol')
	op.drop_table('minecraft_version_protocol')
	op.drop_index(op.f('ix_minecraft_world_times_server_id'), table_name='minecraft_world_times')
	op.drop_index(op.f('ix_minecraft_world_times_world_id'), table_name='minecraft_world_times')
	op.drop_index(op.f('ix_minecraft_world_times_user_id'), table_name='minecraft_world_times')
	op.drop_table('minecraft_world_times')
	op.drop_index(op.f('ix_minecraft_tps_date'), table_name='minecraft_tps')
	op.drop_table('minecraft_tps')
	op.drop_index(op.f('ix_minecraft_worlds_server_uuid'), table_name='minecraft_worlds')
	op.drop_table('minecraft_worlds')
	op.drop_index(op.f('ix_minecraft_plugin_versions_server_id'), table_name='minecraft_plugin_versions')
	op.drop_table('minecraft_plugin_versions')
	op.drop_index(op.f('ix_minecraft_platforms_uuid'), table_name='minecraft_platforms')
	op.drop_table('minecraft_platforms')
	op.drop_index(op.f('ix_minecraft_ping_date'), table_name='minecraft_ping')
	op.drop_index(op.f('ix_minecraft_ping_server_id'), table_name='minecraft_ping')
	op.drop_index(op.f('ix_minecraft_ping_user_id'), table_name='minecraft_ping')
	op.drop_table('minecraft_ping')
	op.drop_index(op.f('ix_minecraft_kills_date'), table_name='minecraft_kills')
	op.drop_index(op.f('ix_minecraft_kills_server_uuid'), table_name='minecraft_kills')
	op.drop_index(op.f('ix_minecraft_kills_victim_uuid'), table_name='minecraft_kills')
	op.drop_index(op.f('ix_minecraft_kills_killer_uuid'), table_name='minecraft_kills')
	op.drop_table('minecraft_kills')
	op.drop_index(op.f('ix_minecraft_nicknames_server_uuid'), table_name='minecraft_nicknames')
	op.drop_index(op.f('ix_minecraft_nicknames_uuid'), table_name='minecraft_nicknames')
	op.drop_table('minecraft_nicknames')
	op.drop_index(op.f('ix_minecraft_sessions_server_id'), table_name='minecraft_sessions')
	op.drop_index(op.f('ix_minecraft_sessions_user_id'), table_name='minecraft_sessions')
	op.drop_table('minecraft_sessions')
	op.drop_index(op.f('ix_minecraft_user_info_server_id'), table_name='minecraft_user_info')
	op.drop_index(op.f('ix_minecraft_user_info_user_id'), table_name='minecraft_user_info')
	op.drop_table('minecraft_user_info')
	op.drop_index(op.f('ix_minecraft_join_address_join_address'), table_name='minecraft_join_address')
	op.drop_table('minecraft_join_address')
	op.drop_index(op.f('ix_minecraft_users_name'), table_name='minecraft_users')
	op.drop_index(op.f('ix_minecraft_users_uuid'), table_name='minecraft_users')
	op.drop_table('minecraft_users')
	op.drop_index(op.f('ix_minecraft_servers_server_uuid'), table_name='minecraft_servers')
	op.drop_index(op.f('ix_minecraft_servers_game_server_id'), table_name='minecraft_servers')
	op.drop_table('minecraft_servers')
