import asyncio
import httpx
import time
import uuid

BASE_URL = "http://localhost:8000/api/v1/statistics"

async def test_goldsource_quests():
    # Note: This test requires a running server and valid database state
    # or it will fail with 404/500 if server_uuid is invalid.
    # In a real CI environment, we'd use a test database.
    
    server_uuid = str(uuid.uuid4())
    steam_id = "STEAM_0:0:12345678"
    
    batch_data = {
        "server_uuid": server_uuid,
        "servers": [
            {
                "server_uuid": server_uuid,
                "name": "Integration Test Server",
                "address": "127.0.0.1:27015",
                "max_players": 32
            }
        ],
        "users": [
            {
                "steam_id": steam_id,
                "name": "QuestTester",
                "registered": int(time.time() * 1000)
            }
        ],
        "sessions": [
            {
                "steam_id": steam_id,
                "server_uuid": server_uuid,
                "map_name": "de_dust2",
                "session_start": int(time.time() * 1000) - 3600000, # 1 hour ago
                "session_end": int(time.time() * 1000),
                "kills": 5,
                "deaths": 2,
                "headshots": 1
            }
        ]
    }

    print(f"Sending batch to {BASE_URL}/goldsource/batch...")
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(f"{BASE_URL}/goldsource/batch", json=batch_data)
            print(f"Status: {response.status_code}")
            if response.status_code == 200:
                print(f"Success: {response.json()}")
            else:
                print(f"Error: {response.text}")
        except Exception as e:
            print(f"Connection failed: {e}")

if __name__ == "__main__":
    asyncio.run(test_goldsource_quests())
