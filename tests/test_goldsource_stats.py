import asyncio
import httpx
import time

# Use a real server ID from the database if possible, or just a placeholder
# for now we will try to hit the API.
# Since I'm on the same machine, I can probably use the dev server if it's running.
# But I'll just write the test logic.

BASE_URL = "http://localhost:8000/api/v1/statistics"

async def test_goldsource_batch():
    # Placeholder server_uuid
    server_uuid = "00000000-0000-0000-0000-000000000000" # We might need a real one
    
    batch_data = {
        "server_uuid": server_uuid,
        "servers": [
            {
                "server_uuid": server_uuid,
                "name": "Test GoldSource Server",
                "address": "127.0.0.1:27015",
                "max_players": 32
            }
        ],
        "users": [
            {
                "steam_id": "STEAM_0:0:123456",
                "name": "TestPlayer",
                "registered": int(time.time() * 1000)
            }
        ],
        "sessions": [
            {
                "steam_id": "STEAM_0:0:123456",
                "server_uuid": server_uuid,
                "map_name": "de_dust2",
                "session_start": int(time.time() * 1000) - 600000,
                "session_end": int(time.time() * 1000),
                "kills": 10,
                "deaths": 5,
                "headshots": 3
            }
        ],
        "kills": [
            {
                "killer_steam_id": "STEAM_0:0:123456",
                "victim_steam_id": "STEAM_0:0:654321",
                "server_uuid": server_uuid,
                "weapon": "ak47",
                "headshot": True,
                "date": int(time.time() * 1000)
            }
        ],
        "fps": [
            {
                "server_uuid": server_uuid,
                "date": int(time.time() * 1000),
                "fps": 1000.0,
                "players_online": 1,
                "map_name": "de_dust2"
            }
        ]
    }

    print(f"Sending batch to {BASE_URL}/goldsource/batch...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{BASE_URL}/goldsource/batch", json=batch_data)
            print(f"Status: {response.status_code}")
            print(f"Response: {response.json()}")
        except Exception as e:
            print(f"Failed to connect: {e}")

if __name__ == "__main__":
    asyncio.run(test_goldsource_batch())
