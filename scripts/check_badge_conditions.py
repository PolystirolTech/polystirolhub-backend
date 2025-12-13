"""
Скрипт для периодической проверки условий бейджей.
Запускается через cron или как отдельный сервис.
"""
import asyncio
import logging
import sys
from pathlib import Path

# Добавляем корневую директорию проекта в путь
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.db.session import AsyncSessionLocal
from app.services.badge_progress import check_periodic_badges

logging.basicConfig(
	level=logging.INFO,
	format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_check():
	"""Выполняет проверку периодических бейджей."""
	try:
		async with AsyncSessionLocal() as db:
			await check_periodic_badges(db)
			logger.info("Periodic badge check completed successfully")
	except Exception as e:
		logger.error(f"Error during periodic badge check: {e}", exc_info=True)
		raise


async def run_continuous():
	"""Запускает непрерывную проверку каждый час."""
	logger.info("Starting continuous badge condition checker (runs every hour)")
	
	while True:
		try:
			await run_check()
		except Exception as e:
			logger.error(f"Error in continuous check loop: {e}", exc_info=True)
		
		# Ждем 1 час перед следующей проверкой
		await asyncio.sleep(10)  # 60 секунд = 1 минута


if __name__ == "__main__":
	if len(sys.argv) > 1 and sys.argv[1] == "--once":
		# Запуск один раз (для cron)
		asyncio.run(run_check())
	else:
		# Непрерывный режим
		asyncio.run(run_continuous())

