import re
from typing import Optional

def steamidalt_to_64(steamid: str) -> str:
    """
    Converts SteamID2 (STEAM_0:1:95922620) to SteamID64 (76561198152110969).
    If the input is already a 64-bit SteamID or doesn't match SteamID2 format, 
    it returns the input as is.
    """
    if not isinstance(steamid, str):
        return str(steamid)

    # Check if it's already a SteamID64 (7656...)
    if re.match(r"^7656\d{13}$", steamid):
        return steamid

    # SteamID2 format: STEAM_X:Y:Z
    match = re.match(r"^STEAM_\d:([0-1]):(\d+)$", steamid)
    if not match:
        return steamid

    y = int(match.group(1))
    z = int(match.group(2))

    # SteamID64 = Z * 2 + V + Y
    # V is the 64-bit Steam account identifier for the individual account type
    # V = 0x0110000100000000 (decimal 76561197960265728)
    v = 76561197960265728
    
    steam64 = z * 2 + v + y
    return str(steam64)
