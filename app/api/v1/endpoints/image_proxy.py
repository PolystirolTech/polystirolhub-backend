import hashlib
from urllib.parse import urlparse

import httpx
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

router = APIRouter()

ALLOWED_HOSTS = {
    # MAL
    "cdn.myanimelist.net",
    "api-cdn.myanimelist.net",
    # Shikimori
    "shikimori.one",
    "shikimori.io",
    "dere.shikimori.one",
    "kawai.shikimori.one",
    # TMDB
    "image.tmdb.org",
    # IGDB
    "images.igdb.com",
    # Last.fm
    "lastfm.freetls.fastly.net",
    "i.last.fm",
    "assets.last.fm",
}

# Simple in-process cache: url_hash -> (content_type, body)
_cache: dict[str, tuple[str, bytes]] = {}
_MAX_CACHE = 512


@router.get("/proxy/image")
async def proxy_image(url: str = Query(..., min_length=1)):
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in ALLOWED_HOSTS:
        raise HTTPException(status_code=400, detail="URL not allowed")

    key = hashlib.md5(url.encode()).hexdigest()
    if key in _cache:
        content_type, body = _cache[key]
        return Response(content=body, media_type=content_type, headers={"Cache-Control": "public, max-age=86400"})

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            resp = await client.get(url, timeout=10)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail="Failed to fetch image")
            content_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
            body = resp.content
    except httpx.TimeoutException:
        raise HTTPException(status_code=504, detail="Image source timed out")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=502, detail="Failed to fetch image")

    if len(_cache) >= _MAX_CACHE:
        _cache.pop(next(iter(_cache)))
    _cache[key] = (content_type, body)

    return Response(
        content=body,
        media_type=content_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
