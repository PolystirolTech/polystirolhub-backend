"""add_initial_quests

Revision ID: 2788caba6427
Revises: 8a110512a4c5
Create Date: 2025-12-14 00:06:26.086062

"""
from alembic import op
import uuid


# revision identifiers, used by Alembic.
revision = '2788caba6427'
down_revision = '8a110512a4c5'
branch_labels = None
depends_on = None


def upgrade() -> None:
	# Добавляем начальные квесты
	
	# Achievements
	achievements = [
		{
			"id": str(uuid.uuid4()),
			"name": "Привязать все платформы",
			"description": "Привяжи все платформы в профиле (Twitch, Discord, Steam)",
			"quest_type": "achievement",
			"condition_key": "link_all_platforms",
			"target_value": 3,
			"reward_xp": 500,
			"is_active": True
		},
		{
			"id": str(uuid.uuid4()),
			"name": "Написать 10000 сообщений в чате",
			"description": "Напиши 10000 сообщений в чате на сервере",
			"quest_type": "achievement",
			"condition_key": "messages_sent",
			"target_value": 10000,
			"reward_xp": 1000,
			"is_active": True
		},
		{
			"id": str(uuid.uuid4()),
			"name": "Пройти 1000000 блоков в майнкрафте",
			"description": "Пройди 1000000 блоков в майнкрафте",
			"quest_type": "achievement",
			"condition_key": "blocks_traveled",
			"target_value": 1000000,
			"reward_xp": 2000,
			"is_active": True
		}
	]
	
	# Daily Quests
	daily_quests = [
		{
			"id": str(uuid.uuid4()),
			"name": "Играй 1 час",
			"description": "Играй на сервере 1 час за день",
			"quest_type": "daily",
			"condition_key": "playtime_daily",
			"target_value": 3600,  # секунды
			"reward_xp": 100,
			"is_active": True
		},
		{
			"id": str(uuid.uuid4()),
			"name": "Зайди на сервер",
			"description": "Зайди на сервер",
			"quest_type": "daily",
			"condition_key": "server_join",
			"target_value": 1,
			"reward_xp": 50,
			"is_active": True
		}
	]
	
	# Вставляем achievements
	for achievement in achievements:
		op.execute(f"""
			INSERT INTO quests (id, name, description, quest_type, condition_key, target_value, reward_xp, is_active, created_at)
			VALUES (
				'{achievement["id"]}'::uuid,
				'{achievement["name"].replace("'", "''")}',
				'{achievement["description"].replace("'", "''")}',
				'{achievement["quest_type"]}'::quest_type,
				'{achievement["condition_key"]}',
				{achievement["target_value"]},
				{achievement["reward_xp"]},
				{achievement["is_active"]},
				NOW()
			)
		""")
	
	# Вставляем daily quests
	for daily in daily_quests:
		op.execute(f"""
			INSERT INTO quests (id, name, description, quest_type, condition_key, target_value, reward_xp, is_active, created_at)
			VALUES (
				'{daily["id"]}'::uuid,
				'{daily["name"].replace("'", "''")}',
				'{daily["description"].replace("'", "''")}',
				'{daily["quest_type"]}'::quest_type,
				'{daily["condition_key"]}',
				{daily["target_value"]},
				{daily["reward_xp"]},
				{daily["is_active"]},
				NOW()
			)
		""")


def downgrade() -> None:
	# Удаляем начальные квесты по condition_key
	op.execute("""
		DELETE FROM quests 
		WHERE condition_key IN ('link_all_platforms', 'messages_sent', 'blocks_traveled', 'playtime_daily', 'server_join')
	""")
