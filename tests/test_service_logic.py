import asyncio
import time
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from app.core.config import settings
from app.services.goldsource_statistics import process_goldsource_statistics_batch
from app.schemas.goldsource_statistics import GoldSourceStatisticsBatch, GoldSourceUserData, GoldSourceSessionData, GoldSourceKillData, GoldSourceFPSData

async def test_service():
    engine = create_async_engine(settings.SQLALCHEMY_DATABASE_URI)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    
    # Valid server ID from previous step
    server_uuid = "963106c4-cf4c-4893-a5de-ff2285df9177"
    
    batch = GoldSourceStatisticsBatch(
        server_uuid=server_uuid,
        users=[
            GoldSourceUserData(
                steam_id="STEAM_0:1:12345678",
                name="Gamer123",
                registered=int(time.time() * 1000)
            )
        ],
        sessions=[
            GoldSourceSessionData(
                steam_id="STEAM_0:1:12345678",
                server_uuid=server_uuid,
                map_name="de_dust2",
                session_start=int(time.time() * 1000) - 300000,
                session_end=int(time.time() * 1000),
                kills=5,
                deaths=2,
                headshots=1
            )
        ],
        kills=[
            GoldSourceKillData(
                killer_steam_id="STEAM_0:1:12345678",
                victim_steam_id="STEAM_0:0:87654321",
                server_uuid=server_uuid,
                weapon="ak47",
                headshot=True,
                date=int(time.time() * 1000)
            )
        ],
        fps=[
            GoldSourceFPSData(
                server_uuid=server_uuid,
                date=int(time.time() * 1000),
                fps=999.5,
                players_online=2,
                map_name="de_dust2"
            )
        ]
    )
    
    async with async_session() as session:
        print("Processing batch...")
        success, processed, errors = await process_goldsource_statistics_batch(session, batch)
        print(f"Success: {success}")
        print(f"Processed: {processed}")
        print(f"Errors: {errors}")
        
    await engine.dispose()

if __name__ == "__main__":
    asyncio.run(test_service())
