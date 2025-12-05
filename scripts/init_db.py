#!/usr/bin/env python3
"""Скрипт для создания БД если её не существует"""
import asyncio
import asyncpg
import os
import sys

async def create_database_if_not_exists():
	postgres_user = os.getenv("POSTGRES_USER", "postgres")
	postgres_password = os.getenv("POSTGRES_PASSWORD", "postgres")
	postgres_server = os.getenv("POSTGRES_SERVER", "localhost")
	postgres_db = os.getenv("POSTGRES_DB", "app")
	
	# Подключаемся к postgres БД для проверки/создания нужной БД
	conn = await asyncpg.connect(
		host=postgres_server,
		user=postgres_user,
		password=postgres_password,
		database="postgres"
	)
	
	try:
		# Проверяем существование БД
		db_exists = await conn.fetchval(
			"SELECT 1 FROM pg_database WHERE datname = $1",
			postgres_db
		)
		
		if db_exists:
			print(f"База данных '{postgres_db}' уже существует")
		else:
			# Создаем БД
			await conn.execute(f'CREATE DATABASE "{postgres_db}"')
			print(f"База данных '{postgres_db}' успешно создана")
	finally:
		await conn.close()

if __name__ == "__main__":
	try:
		asyncio.run(create_database_if_not_exists())
	except Exception as e:
		print(f"Ошибка при создании БД: {e}", file=sys.stderr)
		sys.exit(1)
