import hashlib
import logging
from typing import Optional

import httpx
from app.core.config import settings
from app.db.redis import get_cache, set_cache
from app.models.media_list import MediaType

logger = logging.getLogger(__name__)

SEARCH_CACHE_TTL = settings.EXTERNAL_API_CACHE_TTL


async def search_media(query: str, media_type: MediaType) -> list[dict]:
    """Search for media across external APIs"""
    if media_type == MediaType.anime:
        return await _search_mal(query)
    elif media_type in (MediaType.movie, MediaType.series):
        return await _search_tmdb(query, is_series=(media_type == MediaType.series))
    elif media_type == MediaType.game:
        return await _search_igdb(query)
    elif media_type == MediaType.album:
        return await _search_lastfm(query)
    return []


async def get_metadata_by_external_id(external_id: str, media_type: MediaType) -> Optional[dict]:
    """Get metadata from cache or API by external_id"""
    cache_key = f"media_by_id:{media_type.value}:{external_id}"

    # Try cache first
    cached = await get_cache(cache_key)
    if cached:
        try:
            import json
            return json.loads(cached)
        except Exception:
            pass

    # If not in cache, it wasn't found - return None
    # (This prevents excessive API calls for non-existent IDs)
    return None


async def _search_with_cache(
    key: str,
    search_func,
    media_type: MediaType,
) -> list[dict]:
    """Search with Redis caching"""
    cached = await get_cache(key)
    if cached:
        try:
            import json
            return json.loads(cached)
        except Exception:
            pass

    try:
        results = await search_func()
        if results:
            import json
            # Cache the full results list
            await set_cache(key, json.dumps(results), SEARCH_CACHE_TTL)
            # Also cache each result individually by external_id for auto-fill
            for result in results:
                if result.get('external_id'):
                    id_key = f"media_by_id:{media_type.value}:{result['external_id']}"
                    await set_cache(id_key, json.dumps(result), SEARCH_CACHE_TTL)
        return results
    except Exception as e:
        logger.error(f"Search error for {key}: {e}")
        return []


async def _search_mal(query: str) -> list[dict]:
    """Search MyAnimeList API for anime"""
    cache_key = f"media_search:anime:{hashlib.md5(query.encode()).hexdigest()}"

    async def search():
        if not settings.MAL_CLIENT_ID:
            logger.warning("MAL_CLIENT_ID not configured")
            return []

        try:
            logger.debug(f"Searching MAL for: {query}, Client-ID: {settings.MAL_CLIENT_ID[:10]}...")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.myanimelist.net/v2/anime",
                    params={
                        "q": query,
                        "limit": 10,
                        "fields": "id,title,main_picture,synopsis,genres,mean,start_season"
                    },
                    headers={"X-MAL-CLIENT-ID": settings.MAL_CLIENT_ID},
                    timeout=10,
                )
                if response.status_code != 200:
                    logger.error(f"MAL API returned {response.status_code}: {response.text[:500]}")
                response.raise_for_status()
                data = response.json()

                results = []
                for item in data.get("data", []):
                    anime = item.get("node", {})
                    results.append({
                        "title": anime.get("title", query),
                        "cover_url": anime.get("main_picture", {}).get("large"),
                        "external_id": str(anime.get("id")),
                        "description": anime.get("synopsis"),
                        "genres": [g.get("name") for g in anime.get("genres", [])],
                        "source_rating": anime.get("mean"),
                        "year": anime.get("start_season", {}).get("year"),
                    })
                return results
        except Exception as e:
            logger.error(f"MAL search error: {e}")
            return []

    return await _search_with_cache(cache_key, search, MediaType.anime)


async def _search_tmdb(query: str, is_series: bool = False) -> list[dict]:
    """Search TMDB API for movies or series"""
    search_type = "series" if is_series else "movie"
    cache_key = f"media_search:{search_type}:{hashlib.md5(query.encode()).hexdigest()}"
    media_type_enum = MediaType.series if is_series else MediaType.movie

    async def search():
        if not settings.TMDB_API_KEY:
            logger.warning("TMDB_API_KEY not configured")
            return []

        try:
            logger.debug(f"Searching TMDB for: {query}, is_series={is_series}")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.themoviedb.org/3/search/multi",
                    params={"api_key": settings.TMDB_API_KEY, "query": query},
                    timeout=10,
                )
                if response.status_code != 200:
                    logger.error(f"TMDB API returned {response.status_code}: {response.text[:500]}")
                response.raise_for_status()
                data = response.json()

                results = []
                for item in data.get("results", []):
                    media_type = item.get("media_type")

                    if is_series and media_type != "tv":
                        continue
                    if not is_series and media_type != "movie":
                        continue

                    title = item.get("title") or item.get("name")
                    poster_path = item.get("poster_path")
                    poster_url = f"https://image.tmdb.org/t/p/w342{poster_path}" if poster_path else None

                    results.append({
                        "title": title,
                        "cover_url": poster_url,
                        "external_id": str(item.get("id")),
                        "description": item.get("overview"),
                        "genres": [],  # TMDB multi-search doesn't include genres
                        "source_rating": item.get("vote_average"),
                        "year": int(item.get("release_date", "")[:4]) if item.get("release_date") else None,
                    })
                return results
        except Exception as e:
            logger.error(f"TMDB search error: {e}")
            return []

    return await _search_with_cache(cache_key, search, media_type_enum)


async def _search_igdb(query: str) -> list[dict]:
    """Search IGDB API for games"""
    cache_key = f"media_search:game:{hashlib.md5(query.encode()).hexdigest()}"

    async def search():
        if not settings.IGDB_CLIENT_ID or not settings.IGDB_ACCESS_TOKEN:
            logger.warning("IGDB credentials not configured")
            return []

        try:
            logger.debug(f"Searching IGDB for: {query}")
            logger.debug(f"IGDB Client-ID: {settings.IGDB_CLIENT_ID}")
            logger.debug(f"IGDB Token (first 20 chars): {settings.IGDB_ACCESS_TOKEN[:20]}...")

            headers = {
                "Client-ID": settings.IGDB_CLIENT_ID,
                "Authorization": f"Bearer {settings.IGDB_ACCESS_TOKEN}",
            }
            logger.debug(f"Headers: {headers}")

            async with httpx.AsyncClient() as client:
                response = await client.post(
                    "https://api.igdb.com/v4/games",
                    headers=headers,
                    content=f'search "{query}"; fields name,cover.url,summary,genres.name,rating,first_release_date; limit 10;',
                    timeout=10,
                )
                if response.status_code != 200:
                    logger.error(f"IGDB API returned {response.status_code}: {response.text[:500]}")
                response.raise_for_status()
                data = response.json()

                results = []
                for game in data:
                    logger.debug(f"IGDB game data: {game}")

                    cover_url = None
                    cover = game.get("cover")
                    if cover:
                        # cover может быть числом (ID) или объектом
                        if isinstance(cover, dict):
                            cover_id = cover.get("id")
                        else:
                            cover_id = cover
                        if cover_id:
                            cover_url = f"https://images.igdb.com/igdb/image/upload/t_cover_big/{cover_id}.jpg"

                    year = None
                    first_release_date = game.get("first_release_date")
                    if first_release_date:
                        # first_release_date это Unix timestamp
                        from datetime import datetime
                        try:
                            dt = datetime.fromtimestamp(first_release_date)
                            year = dt.year
                        except Exception as e:
                            logger.warning(f"Could not parse IGDB date {first_release_date}: {e}")

                    # genres может быть массивом ID, а не объектов
                    genres_list = []
                    genres = game.get("genres", [])
                    if genres and isinstance(genres, list):
                        for g in genres:
                            if isinstance(g, dict):
                                genre_name = g.get("name")
                            else:
                                genre_name = str(g)
                            if genre_name:
                                genres_list.append(genre_name)

                    results.append({
                        "title": game.get("name", query),
                        "cover_url": cover_url,
                        "external_id": str(game.get("id")),
                        "description": game.get("summary"),
                        "genres": genres_list,
                        "source_rating": game.get("rating"),
                        "year": year,
                    })
                return results
        except Exception as e:
            logger.error(f"IGDB search error: {e}")
            return []

    return await _search_with_cache(cache_key, search, MediaType.game)
    """Search Last.fm API for albums"""
    cache_key = f"media_search:album:{hashlib.md5(query.encode()).hexdigest()}"

    async def search():
        if not settings.LASTFM_API_KEY:
            logger.warning("LASTFM_API_KEY not configured")
            return []

        try:
            logger.debug(f"Searching Last.fm for album: {query}")
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://ws.audioscrobbler.com/2.0/",
                    params={
                        "method": "album.search",
                        "album": query,
                        "api_key": settings.LASTFM_API_KEY,
                        "format": "json",
                        "limit": 10,
                    },
                    timeout=10,
                )
                if response.status_code != 200:
                    logger.error(f"Last.fm API returned {response.status_code}: {response.text[:500]}")
                response.raise_for_status()
                data = response.json()

                results = []
                for album in data.get("results", {}).get("albummatches", {}).get("album", []):
                    images = album.get("image", [])
                    cover_url = None
                    if images and isinstance(images, list) and len(images) > 0:
                        # Last.fm images list: small, medium, large, extralarge
                        for img in reversed(images):
                            if img.get("#text"):
                                cover_url = img.get("#text")
                                break

                    results.append({
                        "title": f"{album.get('name')} - {album.get('artist')}",
                        "cover_url": cover_url,
                        "external_id": album.get("mbid"),
                        "description": None,
                        "genres": [],
                        "source_rating": None,
                        "year": None,
                    })
                return results
        except Exception as e:
            logger.error(f"Last.fm search error: {e}")
            return []

    return await _search_with_cache(cache_key, search, MediaType.album)
