"""
Модуль для настройки периодических задач через APScheduler.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger
from sqlalchemy import select
import logging

from app.db.session import AsyncSessionLocal
from app.services.badge_progress import check_periodic_badges
from app.services.quest_progress import initialize_daily_quests_for_user
from app.models.user import User

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def check_periodic_badges_job():
	"""Задача для проверки периодических бейджей."""
	try:
		async with AsyncSessionLocal() as db:
			await check_periodic_badges(db)
	except Exception as e:
		logger.error(f"Error in periodic badge check job: {e}", exc_info=True)


async def initialize_daily_quests_job():
	"""Задача для инициализации daily квестов для всех активных пользователей."""
	try:
		async with AsyncSessionLocal() as db:
			# Получаем всех активных пользователей
			result = await db.execute(
				select(User).where(User.is_active)
			)
			users = result.scalars().all()
			
			logger.info(f"Initializing daily quests for {len(users)} active users")
			
			for user in users:
				try:
					await initialize_daily_quests_for_user(user.id, db)
				except Exception as e:
					logger.error(f"Error initializing daily quests for user {user.id}: {e}", exc_info=True)
			
			logger.info("Daily quests initialization completed")
	except Exception as e:
		logger.error(f"Error in daily quests initialization job: {e}", exc_info=True)


def start_scheduler():
	"""Запускает планировщик задач."""
	if scheduler.running:
		logger.warning("Scheduler is already running")
		return
	
	# Добавляем задачу проверки периодических бейджей каждый час
	scheduler.add_job(
		check_periodic_badges_job,
		trigger=IntervalTrigger(hours=1),
		id="check_periodic_badges",
		name="Check periodic badges",
		replace_existing=True
	)
	
	# Добавляем задачу инициализации daily квестов каждый день в 00:00
	scheduler.add_job(
		initialize_daily_quests_job,
		trigger=CronTrigger(hour=0, minute=0),
		id="initialize_daily_quests",
		name="Initialize daily quests",
		replace_existing=True
	)
	
	scheduler.start()
	logger.info("Scheduler started with periodic badge check (every hour) and daily quests initialization (daily at 00:00)")


def shutdown_scheduler():
	"""Останавливает планировщик задач."""
	if scheduler.running:
		scheduler.shutdown()
		logger.info("Scheduler stopped")

