"""
Модуль для настройки периодических задач через APScheduler.
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.db.session import AsyncSessionLocal
from app.services.badge_progress import check_periodic_badges

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


async def check_periodic_badges_job():
	"""Задача для проверки периодических бейджей."""
	try:
		async with AsyncSessionLocal() as db:
			await check_periodic_badges(db)
	except Exception as e:
		logger.error(f"Error in periodic badge check job: {e}", exc_info=True)


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
	
	scheduler.start()
	logger.info("Scheduler started with periodic badge check (every hour)")


def shutdown_scheduler():
	"""Останавливает планировщик задач."""
	if scheduler.running:
		scheduler.shutdown()
		logger.info("Scheduler stopped")

