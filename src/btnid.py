import httpx
import uuid
from src.bbcode import BBCODE


async def generate_guid():
    return str(uuid.uuid4())


async def get_btn_torrents(btn_api, btn_id, meta):
    print("Fetching BTN data...")
    post_query_url = "https://api.broadcasthe.net/"
    post_data = {
        "jsonrpc": "2.0",
        "id": (await generate_guid())[:8],
        "method": "getTorrentsSearch",
        "params": [
            btn_api,
            {"id": btn_id},
            50
        ]
    }

    headers = {"Content-Type": "application/json"}

    async with httpx.AsyncClient() as client:
        response = await client.post(post_query_url, headers=headers, json=post_data)
        data = response.json()

    if "result" in data and "torrents" in data["result"]:
        torrents = data["result"]["torrents"]
        first_torrent = next(iter(torrents.values()), None)
        if first_torrent:
            imdb_id = first_torrent.get("ImdbID")
            tvdb_id = first_torrent.get("TvdbID")

            if imdb_id and imdb_id != "0":
                meta["imdb_id"] = int(imdb_id)
                print("BTN IMDb ID:", meta["imdb_id"])

            if tvdb_id and tvdb_id != "0":
                meta["tvdb_id"] = int(tvdb_id)
                print("BTN TVDb ID:", meta["tvdb_id"])

            return meta

    print("No IMDb or TVDb ID found.")
    return meta


async def get_bhd_torrents(bhd_api, bhd_rss_key, info_hash, meta, only_id=False):
    print("Fetching BHD data...")
    post_query_url = f"https://beyond-hd.me/api/torrents/{bhd_api}"
    post_data = {
        "action": "search",
        "rsskey": bhd_rss_key,
        "info_hash": info_hash,
    }

    headers = {"Content-Type": "application/json"}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(post_query_url, headers=headers, json=post_data, timeout=10)
            response.raise_for_status()
            data = response.json()
    except (httpx.RequestError, httpx.HTTPStatusError) as e:
        print(f"[ERROR] Failed to fetch BHD data: {e}")
        return meta

    results = data.get("results", [])
    if not results:
        print("[WARNING] No results found in BHD API response.")
        return meta

    first_result = results[0]
    name = first_result.get("name", "").lower()
    internal = bool(first_result.get("internal", False))
    description = first_result.get("description", "")

    imdb_id = first_result.get("imdb_id", "").replace("tt", "") if first_result.get("imdb_id") else 0
    meta["imdb_id"] = int(imdb_id or 0)

    raw_tmdb_id = first_result.get("tmdb_id", "")
    meta["category"], parsed_tmdb_id = await parse_tmdb_id(raw_tmdb_id, meta.get("category"))
    meta["tmdb_manual"] = int(parsed_tmdb_id or 0)

    if only_id:
        return meta["imdb_id"] or meta["tmdb_manual"] or 0

    if not only_id and internal and ("framestor" in name or "flux" in name):
        bbcode = BBCODE()
        imagelist = []
        if "framestor" in name:
            meta["framestor"] = True
        description, imagelist = bbcode.clean_bhd_description(description, meta)
        meta["description"] = description
        meta["image_list"] = imagelist

    print("BHD IMDb ID:", meta.get("imdb_id"))
    print("BHD TMDb ID:", meta.get("tmdb_manual"))

    return meta["imdb_id"] or meta["tmdb_manual"] or 0


async def parse_tmdb_id(tmdb_id, category):
    """Parses TMDb ID, ensures correct formatting, and assigns category."""
    tmdb_id = str(tmdb_id).strip().lower()

    if tmdb_id.startswith('tv/') and '/' in tmdb_id:
        tmdb_id = tmdb_id.split('/')[1]
        category = 'TV'
    elif tmdb_id.startswith('movie/') and '/' in tmdb_id:
        tmdb_id = tmdb_id.split('/')[1]
        category = 'MOVIE'

    return category, tmdb_id
