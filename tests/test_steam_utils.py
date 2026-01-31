from app.core.steam import steamidalt_to_64

def test_steamid_conversion():
    # Test STEAM_0:1:95922620 -> 76561198152110969
    assert steamidalt_to_64("STEAM_0:1:95922620") == "76561198152110969"
    
    # Test already SteamID64
    assert steamidalt_to_64("76561198152110969") == "76561198152110969"
    
    # Test invalid format
    assert steamidalt_to_64("invalid") == "invalid"
    
    # Test another common one
    # STEAM_0:0:12345
    # Z=12345, Y=0
    # 12345 * 2 + 76561197960265728 + 0 = 76561197960290418
    assert steamidalt_to_64("STEAM_0:0:12345") == "76561197960290418"

if __name__ == "__main__":
    test_steamid_conversion()
    print("SteamID conversion tests passed!")
