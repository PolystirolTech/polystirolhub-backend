import asyncio
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.v1.endpoints.auth import check_link_status
from app.services.goldsource_statistics import link_steam_to_user
from app.models.user import User, OAuthAccount, ExternalLink
from datetime import datetime, timezone

async def verify_check_link_status():
    print("Verifying check_link_status logic...")
    user_id = uuid4()
    db = AsyncMock(spec=AsyncSession)
    
    # Mock user exists
    user = User(id=user_id, username="testuser")
    mock_user_result = MagicMock()
    mock_user_result.scalars.return_value.first.return_value = user
    
    # Mock external links (empty)
    mock_ext_result = MagicMock()
    mock_ext_result.scalars.return_value.all.return_value = []
    
    # Mock oauth accounts (one steam account)
    oauth_acc = OAuthAccount(
        id=uuid4(),
        user_id=user_id,
        provider="steam",
        provider_account_id="76561198000000000",
        provider_username="SteamUser",
        created_at=datetime.now(timezone.utc)
    )
    mock_oauth_result = MagicMock()
    mock_oauth_result.scalars.return_value.all.return_value = [oauth_acc]
    
    db.execute.side_effect = [mock_user_result, mock_ext_result, mock_oauth_result]
    
    response = await check_link_status(user_id=user_id, db=db)
    
    print(f"Response user_id: {response.user_id}")
    print(f"Links found: {len(response.links)}")
    for link in response.links:
        print(f" - Platform: {link.platform}, ID: {link.external_id}, Username: {link.platform_username}")
    
    assert len(response.links) == 1
    assert response.links[0].platform == "STEAM"
    assert response.links[0].external_id == "76561198000000000"
    print("check_link_status verification PASSED")

async def verify_link_steam_to_user():
    print("\nVerifying link_steam_to_user logic...")
    db = AsyncMock(spec=AsyncSession)
    steam_id = "76561198000000000"
    user_id = uuid4()
    
    # Case 1: Found in ExternalLink
    ext_link = ExternalLink(user_id=user_id, platform="STEAM", external_id=steam_id)
    mock_ext_result = MagicMock()
    mock_ext_result.scalar_one_or_none.return_value = ext_link
    
    db.execute.return_value = mock_ext_result
    res = await link_steam_to_user(db, steam_id)
    print(f"Case 1 (ExternalLink): Found user {res}")
    assert res == str(user_id)
    
    # Case 2: Not in ExternalLink, found in OAuthAccount
    mock_ext_result_empty = MagicMock()
    mock_ext_result_empty.scalar_one_or_none.return_value = None
    
    oauth_acc = OAuthAccount(user_id=user_id, provider="steam", provider_account_id=steam_id)
    mock_oauth_result = MagicMock()
    mock_oauth_result.scalar_one_or_none.return_value = oauth_acc
    
    db.execute.side_effect = [mock_ext_result_empty, mock_oauth_result]
    res = await link_steam_to_user(db, steam_id)
    print(f"Case 2 (OAuthAccount): Found user {res}")
    assert res == str(user_id)
    
    print("link_steam_to_user verification PASSED")

if __name__ == "__main__":
    asyncio.run(verify_check_link_status())
    asyncio.run(verify_link_steam_to_user())
