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
        results = await _search_mal(query)
        if not results:
            results = await _search_shikimori(query)
        return results
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

    cached = await get_cache(cache_key)
    if cached:
        try:
            import json
            return json.loads(cached)
        except Exception:
            pass

    # Cache miss — fetch from API
    if media_type == MediaType.anime:
        result = await _fetch_mal_by_id(external_id)
        if not result:
            result = await _fetch_shikimori_by_id(external_id)
        return result

    return None


async def _fetch_mal_by_id(external_id: str) -> Optional[dict]:
    """Fetch anime metadata from MAL API by ID and cache it"""
    if not settings.MAL_CLIENT_ID:
        return None

    cache_key = f"media_by_id:{MediaType.anime.value}:{external_id}"

    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.get(
                f"https://api.myanimelist.net/v2/anime/{external_id}",
                params={"fields": "id,title,main_picture,synopsis,genres,mean,start_season"},
                headers={"X-MAL-CLIENT-ID": settings.MAL_CLIENT_ID},
                timeout=5,
            )
            if response.status_code != 200:
                logger.warning(f"MAL fetch by ID {external_id} returned {response.status_code}")
                return None
            anime = response.json()
    except httpx.TimeoutException:
        logger.warning(f"MAL fetch by ID {external_id} timed out, falling back to Shikimori")
        return None
    except Exception as e:
        logger.error(f"MAL fetch by ID {external_id} error: {e!r}")
        return None

    result = {
        "title": anime.get("title"),
        "cover_url": anime.get("main_picture", {}).get("large"),
        "external_id": str(anime.get("id")),
        "description": anime.get("synopsis"),
        "genres": [g.get("name") for g in anime.get("genres", [])],
        "source_rating": anime.get("mean"),
        "year": anime.get("start_season", {}).get("year"),
    }

    import json
    await set_cache(cache_key, json.dumps(result), SEARCH_CACHE_TTL)
    return result


_SHIKIMORI_GQL = "https://shikimori.one/api/graphql"
_SHIKIMORI_HEADERS = {
    "Content-Type": "application/json",
    "User-Agent": "polystirolhub/1.0",
}
_SHIKIMORI_ANIME_FIELDS = """
    id malId name russian
    poster { originalUrl }
    description score
    genres { name }
    airedOn { year }
"""


def _map_shikimori_anime(item: dict) -> dict:
    poster = (item.get("poster") or {}).get("originalUrl")
    genres = [g.get("name") for g in (item.get("genres") or []) if g.get("name")]
    score_raw = item.get("score")
    try:
        source_rating = float(score_raw) if score_raw else None
    except (ValueError, TypeError):
        source_rating = None
    return {
        "title": item.get("name") or "",
        "cover_url": poster,
        "external_id": str(item.get("malId") or item.get("id")),
        "description": item.get("description"),
        "genres": genres,
        "source_rating": source_rating,
        "year": (item.get("airedOn") or {}).get("year"),
    }


async def _shikimori_graphql(query: str, variables: dict) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            response = await client.post(
                _SHIKIMORI_GQL,
                json={"query": query, "variables": variables},
                headers=_SHIKIMORI_HEADERS,
                timeout=15,
            )
            if response.status_code != 200:
                logger.warning(f"Shikimori GQL returned {response.status_code}")
                return None
            data = response.json()
            if "errors" in data:
                logger.warning(f"Shikimori GQL errors: {data['errors']}")
                return None
            return data.get("data")
    except Exception as e:
        logger.error(f"Shikimori GQL error: {e!r}")
        return None


async def _search_shikimori(query: str) -> list[dict]:
    cache_key = f"media_search:anime:shiki:{hashlib.md5(query.encode()).hexdigest()}"

    cached = await get_cache(cache_key)
    if cached:
        try:
            import json
            parsed = json.loads(cached)
            if parsed:
                return parsed
        except Exception:
            pass

    gql = f"""
    query($search: String!) {{
        animes(search: $search, limit: 10, order: popularity) {{
            {_SHIKIMORI_ANIME_FIELDS}
        }}
    }}
    """
    data = await _shikimori_graphql(gql, {"search": query})
    if not data:
        return []

    results = [_map_shikimori_anime(a) for a in data.get("animes", [])]
    results = [r for r in results if r.get("external_id")]

    if results:
        import json
        await set_cache(cache_key, json.dumps(results), SEARCH_CACHE_TTL)
        for r in results:
            id_key = f"media_by_id:{MediaType.anime.value}:{r['external_id']}"
            await set_cache(id_key, json.dumps(r), SEARCH_CACHE_TTL)

    return results


async def fetch_shikimori_batch(external_ids: list[str]) -> dict[str, dict]:
    """Fetch multiple anime from Shikimori in batches of 50. Returns {external_id: metadata}"""
    import json as _json

    result: dict[str, dict] = {}
    uncached: list[str] = []

    # Check cache first
    for eid in external_ids:
        cached = await get_cache(f"media_by_id:{MediaType.anime.value}:{eid}")
        if cached:
            try:
                result[eid] = _json.loads(cached)
            except Exception:
                uncached.append(eid)
        else:
            uncached.append(eid)

    if not uncached:
        return result

    gql = f"""
    query($ids: String!) {{
        animes(ids: $ids, limit: 50) {{
            {_SHIKIMORI_ANIME_FIELDS}
        }}
    }}
    """

    # Process in batches of 50
    for i in range(0, len(uncached), 50):
        batch = uncached[i:i + 50]
        data = await _shikimori_graphql(gql, {"ids": ",".join(batch)})
        if not data:
            continue
        for item in data.get("animes", []):
            mapped = _map_shikimori_anime(item)
            eid = mapped.get("external_id")
            if eid:
                result[eid] = mapped
                await set_cache(
                    f"media_by_id:{MediaType.anime.value}:{eid}",
                    _json.dumps(mapped),
                    SEARCH_CACHE_TTL,
                )

    return result


async def _fetch_shikimori_by_id(external_id: str) -> Optional[dict]:
    cache_key = f"media_by_id:{MediaType.anime.value}:{external_id}"

    gql = f"""
    query($ids: String!) {{
        animes(ids: $ids, limit: 1) {{
            {_SHIKIMORI_ANIME_FIELDS}
        }}
    }}
    """
    data = await _shikimori_graphql(gql, {"ids": external_id})
    if not data:
        return None

    items = data.get("animes", [])
    if not items:
        return None

    result = _map_shikimori_anime(items[0])
    if not result.get("external_id"):
        return None

    import json
    await set_cache(cache_key, json.dumps(result), SEARCH_CACHE_TTL)
    return result


async def get_metadata_by_imdb_id(imdb_id: str, media_type: MediaType) -> Optional[dict]:
    """Fetch TMDB metadata by IMDb ID (tt...) and cache it"""
    if not settings.TMDB_API_KEY:
        return None

    cache_key = f"media_by_imdb:{media_type.value}:{imdb_id}"

    cached = await get_cache(cache_key)
    if cached:
        try:
            import json
            return json.loads(cached)
        except Exception:
            pass

    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://api.themoviedb.org/3/find/{imdb_id}",
                params={"api_key": settings.TMDB_API_KEY, "external_source": "imdb_id"},
                timeout=10,
            )
            if response.status_code != 200:
                logger.warning(f"TMDB find by IMDb ID {imdb_id} returned {response.status_code}")
                return None
            data = response.json()
    except Exception as e:
        logger.error(f"TMDB find by IMDb ID {imdb_id} error: {e}")
        return None

    items = (
        data.get("tv_results", [])
        if media_type == MediaType.series
        else data.get("movie_results", [])
    )
    if not items:
        items = data.get("movie_results", []) + data.get("tv_results", [])
    if not items:
        return None

    item = items[0]
    poster_path = item.get("poster_path")
    title = item.get("title") or item.get("name")
    date_raw = item.get("release_date") or item.get("first_air_date") or ""

    result = {
        "title": title,
        "cover_url": f"https://image.tmdb.org/t/p/w342{poster_path}" if poster_path else None,
        "external_id": imdb_id,
        "description": item.get("overview"),
        "genres": [],
        "source_rating": item.get("vote_average"),
        "year": int(date_raw[:4]) if len(date_raw) >= 4 else None,
    }

    import json
    await set_cache(cache_key, json.dumps(result), SEARCH_CACHE_TTL)
    return result


async def get_metadata_by_title_year(
    title: str, year: Optional[int]
) -> Optional[dict]:
    """Search TMDB by title+year using multi-search, returns media_type in result"""
    if not settings.TMDB_API_KEY:
        return None

    import hashlib as _hashlib
    cache_key = f"media_by_title:{_hashlib.md5(f'{title}:{year}'.lower().encode()).hexdigest()}"

    cached = await get_cache(cache_key)
    if cached:
        try:
            import json
            parsed = json.loads(cached)
            if parsed:
                return parsed
        except Exception:
            pass

    async def _search(params: dict) -> list:
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "https://api.themoviedb.org/3/search/multi",
                    params={"api_key": settings.TMDB_API_KEY, **params},
                    timeout=10,
                )
                if response.status_code != 200:
                    return []
                # Only keep movie and tv results
                return [
                    r for r in response.json().get("results", [])
                    if r.get("media_type") in ("movie", "tv")
                ]
        except Exception as e:
            logger.error(f"TMDB title search '{title}' error: {e}")
            return []

    items = []
    if year:
        items = await _search({"query": title, "year": year})
        if not items:
            items = await _search({"query": title, "year": year - 1})
        if not items:
            items = await _search({"query": title, "year": year + 1})
    if not items:
        items = await _search({"query": title})

    if not items:
        return None

    item = items[0]
    tmdb_media_type = item.get("media_type")
    poster_path = item.get("poster_path")
    date_raw = item.get("release_date") or item.get("first_air_date") or ""

    result = {
        "title": item.get("title") or item.get("name") or title,
        "cover_url": f"https://image.tmdb.org/t/p/w342{poster_path}" if poster_path else None,
        "external_id": str(item.get("id")),
        "description": item.get("overview"),
        "genres": [],
        "source_rating": item.get("vote_average"),
        "year": int(date_raw[:4]) if len(date_raw) >= 4 else year,
        "media_type": (MediaType.series if tmdb_media_type == "tv" else MediaType.movie).value,
    }

    import json
    await set_cache(cache_key, json.dumps(result), SEARCH_CACHE_TTL)
    return result


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
            parsed = json.loads(cached)
            if parsed:
                return parsed
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
            async with httpx.AsyncClient(follow_redirects=True) as client:
                response = await client.get(
                    "https://api.myanimelist.net/v2/anime",
                    params={
                        "q": query,
                        "limit": 10,
                        "fields": "id,title,main_picture,synopsis,genres,mean,start_season"
                    },
                    headers={"X-MAL-CLIENT-ID": settings.MAL_CLIENT_ID},
                    timeout=5,
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
                        if isinstance(cover, dict):
                            url = cover.get("url")
                            if url:
                                # IGDB returns protocol-relative URLs like //images.igdb.com/...
                                cover_url = url if url.startswith("http") else f"https:{url}"
                                # Upgrade thumbnail to cover_big if needed
                                cover_url = cover_url.replace("/t_thumb/", "/t_cover_big/")
                            elif cover.get("id"):
                                cover_url = f"https://images.igdb.com/igdb/image/upload/t_cover_big/{cover.get('id')}.jpg"

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


async def _search_lastfm(query: str) -> list[dict]:
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

                    mbid = album.get("mbid")
                    if not mbid:
                        artist = album.get("artist", "")
                        name = album.get("name", "")
                        mbid = f"lastfm:{hashlib.md5(f'{artist}:{name}'.lower().encode()).hexdigest()}"

                    results.append({
                        "title": f"{album.get('name')} - {album.get('artist')}",
                        "cover_url": cover_url,
                        "external_id": mbid,
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
