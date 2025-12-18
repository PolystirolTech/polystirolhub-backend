"""
Справочник доступных condition_key для бейджей.
"""
from typing import Dict, List
from enum import Enum


class BadgeConditionKey(str, Enum):
	"""Доступные ключи условий для бейджей."""
	
	XP_LEADER = "xp_leader"
	DEATHS_IN_SESSION = "deaths_in_session"
	PLAYTIME_LEADER_SEASON = "playtime_leader_season"
	MESSAGES_SENT = "messages_sent"
	CURRENCY_ACCUMULATED = "currency_accumulated"


# Описания условий
CONDITION_DESCRIPTIONS: Dict[str, Dict[str, any]] = {
	"xp_leader": {
		"name": "Лидер по опыту",
		"description": "Бейдж выдается лидеру по опыту на сайте. Обновление раз в час.",
		"type": "periodic",  # periodic или event
		"requires_target_value": False,
		"requires_auto_check": True,
		"handler": "XPLeaderHandler"
	},
	"deaths_in_session": {
		"name": "Смерти в сессии",
		"description": "Бейдж выдается за определенное количество смертей в одной игровой сессии.",
		"type": "event",
		"requires_target_value": True,
		"requires_auto_check": False,
		"handler": "DeathsInSessionHandler"
	},
	"playtime_leader_season": {
		"name": "Лидер по времени игры в сезоне",
		"description": "Бейдж выдается лидеру по времени игры в сезоне. Пока не реализовано.",
		"type": "periodic",
		"requires_target_value": False,
		"requires_auto_check": True,
		"handler": "PlaytimeLeaderSeasonHandler",
		"status": "not_implemented"
	},
	"messages_sent": {
		"name": "Сообщения в чате",
		"description": "Бейдж выдается за определенное количество сообщений в чате на сервере. Пока не реализовано.",
		"type": "event",
		"requires_target_value": True,
		"requires_auto_check": False,
		"handler": "MessagesSentHandler",
		"status": "not_implemented"
	},
	"currency_accumulated": {
		"name": "Накопить валюту",
		"description": "Бейдж выдается за накопление определенного количества валюты за все время.",
		"type": "event",
		"requires_target_value": True,
		"requires_auto_check": False,
		"handler": "CurrencyAccumulatedHandler"
	}
}


def get_available_conditions() -> List[Dict[str, any]]:
	"""
	Возвращает список всех доступных условий.
	
	Returns:
		Список словарей с информацией о каждом условии
	"""
	return [
		{
			"key": key,
			**info
		}
		for key, info in CONDITION_DESCRIPTIONS.items()
	]


def get_condition_info(condition_key: str) -> Dict[str, any]:
	"""
	Возвращает информацию о конкретном условии.
	
	Args:
		condition_key: Ключ условия
		
	Returns:
		Словарь с информацией об условии или None
	"""
	return CONDITION_DESCRIPTIONS.get(condition_key)


def is_condition_valid(condition_key: str) -> bool:
	"""
	Проверяет, является ли condition_key валидным.
	
	Args:
		condition_key: Ключ условия
		
	Returns:
		True если условие существует, False иначе
	"""
	return condition_key in CONDITION_DESCRIPTIONS

