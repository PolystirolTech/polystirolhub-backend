import pytest
from unittest.mock import MagicMock, patch, AsyncMock
from uuid import uuid4
from app.services.server_status import get_server_status
from app.models.game_server import ServerStatus

@pytest.mark.asyncio
async def test_minecraft_status_call():
    # Mock Redis
    with patch("app.services.server_status.get_cache", return_value=None), \
         patch("app.services.server_status.acquire_lock", return_value=True), \
         patch("app.services.server_status.release_lock"), \
         patch("app.services.server_status.set_cache"), \
         patch("app.services.server_status.JavaServer") as mock_java_server:

        # Mock JavaServer response
        mock_server_instance = MagicMock()
        mock_status_response = MagicMock()
        mock_status_response.players.online = 10
        mock_status_response.players.max = 100
        mock_status_response.players.sample = []
        mock_status_response.latency = 20
        mock_status_response.version.name = "1.20.1"
        mock_status_response.description = "Minecraft Server"
        mock_status_response.icon = None
        
        # Async mock for async_status
        mock_server_instance.async_status = AsyncMock(return_value=mock_status_response)
        
        # Mock JavaServer.lookup/init
        # Since we use asyncio.to_thread(JavaServer.lookup, ip) or JavaServer(ip, port)
        # The mock_java_server is the class. 
        # When called as class: JavaServer(ip, port) -> returns instance
        mock_java_server.return_value = mock_server_instance
        # When called as lookup: JavaServer.lookup(ip) -> returns instance
        mock_java_server.lookup.return_value = mock_server_instance
        
        server_id = uuid4()
        # Case 1: "Minecraft" in name
        result = await get_server_status(server_id, "127.0.0.1", 25565, ServerStatus.active, "Minecraft Java")
        
        assert result["online"] is True
        assert result["version"] == "1.20.1"
        
        # Verify a2s was NOT called (we can't easily verify a negative on a non-patched object efficiently without patching a2s too, 
        # but the fact that JavaServer was called and we got result implies success path)
        
@pytest.mark.asyncio
async def test_gold_source_status_call():
    # Mock Redis and a2s
    with patch("app.services.server_status.get_cache", return_value=None), \
         patch("app.services.server_status.acquire_lock", return_value=True), \
         patch("app.services.server_status.release_lock"), \
         patch("app.services.server_status.set_cache"), \
         patch("app.services.server_status.a2s") as mock_a2s:

        # Mock a2s.info
        mock_info = MagicMock()
        mock_info.server_name = "CS 1.6 Server"
        mock_info.player_count = 5
        mock_info.max_players = 32
        mock_info.ping = 0.05
        mock_info.game = "Counter-Strike"
        mock_a2s.info.return_value = mock_info
        
        # Mock a2s.players
        mock_p1 = MagicMock()
        mock_p1.name = "Player1"
        mock_a2s.players.return_value = [mock_p1]
        
        server_id = uuid4()
        # Case 2: NO "Minecraft" in name, e.g. "Counter-Strike"
        result = await get_server_status(server_id, "127.0.0.1", 27015, ServerStatus.active, "Counter-Strike 1.6")
        
        assert result["online"] is True
        # Check title/motd
        assert result["motd"] == "CS 1.6 Server"
        assert result["version"] == "Counter-Strike"
        assert result["players_list"] == ["Player1"]
        
        # Verify a2s was called
        # Note: a2s.info is called inside a run_in_executor lambda, so checking assert_called might be tricky 
        # if the mock isn't propagated correctly, but with patch it should be fine.
        mock_a2s.info.assert_called()
