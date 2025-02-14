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
            if "ImdbID" in first_torrent:
                meta["imdb_id"] = first_torrent["ImdbID"]
            if "TvdbID" in first_torrent:
                meta["tvdb_id"] = first_torrent["TvdbID"]

    print("BTN IMDb ID:", meta.get("imdb_id"))
    print("BTN TVDb ID:", meta.get("tvdb_id"))
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

    async with httpx.AsyncClient() as client:
        response = await client.post(post_query_url, headers=headers, json=post_data)
        data = response.json()

    if "results" in data and data["results"]:
        first_result = data["results"][0]
        name = first_result.get("name", "").lower()
        internal = bool(first_result.get("internal", False))
        description = first_result.get("description", "")
        imdb_id = first_result.get("imdb_id", "").replace("tt", "") if first_result.get("imdb_id") else None
        tmdb_id = first_result.get("tmdb_id", "") if first_result.get("tmdb_id") else None
        meta["imdb_id"] = imdb_id
        meta['category'], meta['tmdb_manual'] = await parse_tmdb_id(tmdb_id, meta.get('category'))
        if not only_id and internal and ("framestor" in name or "flux" in name):
            bbcode = BBCODE()
            imagelist = []
            if "framestor" in name:
                meta['framestor'] = True
            description, imagelist = bbcode.clean_bhd_description(description, meta)
            meta['description'] = description
            meta['image_list'] = imagelist

    print("BHD IMDb ID:", meta.get("imdb_id"))
    print("BHD TMDb ID:", meta.get("tmdb_manual"))
    return meta


async def parse_tmdb_id(id, category):
    id = id.lower().lstrip()
    if id.startswith('tv'):
        id = id.split('/')[1]
        category = 'TV'
    elif id.startswith('movie'):
        id = id.split('/')[1]
        category = 'MOVIE'
    else:
        id = id
    return category, id
