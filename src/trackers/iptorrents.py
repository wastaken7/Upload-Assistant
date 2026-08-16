# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from pathlib import Path
from typing import Any

import aiofiles
import bencodepy
import httpx
from bs4 import BeautifulSoup

from src.console import logger
from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.get_desc import DescriptionBuilder
from src.meta import Meta

Config = dict[str, Any]


class IPTorrents:
    """
    IPT Private Torrent Tracker
    """

    auth_type = "cookies"
    tracker = "IPTORRENTS"
    display_name = "IPTorrents"
    allows_bloated_audio = True
    source_flag = "IPTorrents"
    base_url = "https://iptorrents.com"
    banned_groups = (
        "1337x",
        "3DM",
        "3dtorrents",
        "ali213",
        "AreaFiles",
        "BD25",
        "BlackBox",
        "BLuBits",
        "bluhd.org",
        "BTN",
        "BTNet",
        "Catalyst RG",
        "CBUT",
        "CHDBits",
        "CHDTV.Net",
        "CINEMANIA",
        "CorePack",
        "CorePacks",
        "CPG",
        "DADDY",
        "DDR",
        "Digital Desi Releasers",
        "DLBR",
        "DLLHits",
        "DRIG",
        "DVDSEED",
        "EncodeKing",
        "FGT",
        "filelist.ro",
        "flashtorrents",
        "Ganool",
        "h33t",
        "HD4FUN",
        "HDAccess",
        "HDChina",
        "HDGeek",
        "HDME",
        "HDRoad",
        "HDStar",
        "HDTime",
        "HDTurk",
        "HDWing",
        "HorribleSubs",
        "hqsource.org",
        "IWStream",
        "Kingdom-KVCD",
        "MeGaHeRTZ",
        "MkvCage",
        "MVGroup.org",
        "MYEGY",
        "nosTEAM",
        "OntohinBD",
        "os4world",
        "Pimp4003",
        "Projekt-Revolution",
        "ps3gameroom",
        "PTP",
        "RARBG/RBG",
        "RLS",
        "RLSM",
        "SFS-RG",
        "SFS",
        "Shaanig",
        "SHOWSCEN",
        "SilverTorrents",
        "SiRiUs sHaRe",
        "SpaceHD",
        "The Wolfs Den",
        "TPTB",
        "TTG",
        "UNKNOWN",
        "X360ISO",
        "YIFY",
        "zombiRG",
    )
    torrent_url = "https://iptorrents.com/torrent.php?id="
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME", "MUSIC")
    tracker_urls = ("ssl.empirehost.me", "routing.bgp.technology", "127.0.0.1.stackoverflow.tech")

    def __init__(self, config: Config):
        self.config = config
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.session = httpx.AsyncClient(headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:144.0) Gecko/20100101 Firefox/144.0"}, timeout=30)

    async def validate_credentials(self, meta: Meta) -> bool:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar:
            self.session.cookies = cookie_jar
            return True

        return False

    async def generate_description(self, meta: Meta):
        builder = DescriptionBuilder(self.tracker, self.config)
        return await builder.general_description_generator(
            meta,
            logo=False,
            nfo=False,
            signature=f"[center][url=https://github.com/wastaken7/Upload-Assistant]{meta.ua_signature}[/center][/url][/right]",
        )

    async def search_existing(self, meta: Meta) -> list[dict[str, str]]:
        dupes: list[dict[str, str]] = []
        search_query: str = ""

        if meta.category == "MOVIE":
            search_query = meta.title
            cat_id = 72
        elif meta.category == "TV":
            search_query = f"{meta.title} {meta.season}"
            cat_id = 73
        else:
            cat_id = self.get_category_id(meta)
            if meta.category in ("BOOK", "GAME"):
                search_query = meta.title
            elif meta.category == "MUSIC":
                search_query = f"{meta.artist} {meta.title}"

        if not cat_id or not search_query:
            return dupes

        search_url = f"{self.base_url}/t?{cat_id}=&q={search_query}"

        forbidden_keywords: list[str] = []

        is_disc = str(meta.is_disc or "").strip().lower()
        _type = str(meta.type or "").strip().lower()

        if is_disc == "bdmv":
            forbidden_keywords.extend(
                [
                    "remux",
                    "x264",
                    "x265",
                    "x 264",
                    "x 265",
                    "webrip",
                    "av1",
                    "h 264",
                    "h 265",
                    "h264",
                    "h265",
                    " web ",
                ]
            )
            if "1080" in meta.resolution:
                forbidden_keywords.extend(
                    [
                        "hevc",
                    ]
                )

        if _type == "webdl":
            forbidden_keywords.extend(["webrip", "bluray", "blu-ray"])

        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar:
            self.session.cookies = cookie_jar

        response = await self.session.get(search_url, follow_redirects=True)
        if "login" in str(response.url) or "login.php" in response.text:
            await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
            meta.skipping = f"{self.tracker}"
            return dupes
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        torrent_table = soup.find("table", id="torrents")

        if torrent_table:
            rows = torrent_table.find("tbody")
            if rows:
                rows = rows.find_all("tr")
                for row in rows:
                    cells = row.find_all("td")

                    if len(cells) > 5:
                        name_cell = cells[1]
                        link_tag = name_cell.find("a", class_="hv")

                        if link_tag:
                            name = " ".join(link_tag.get_text(" ", strip=True).split())
                            torrent_path = link_tag.get("href")
                            torrent_link = f"{self.base_url}{torrent_path}"
                            size_text = cells[5].get_text(" ", strip=True)
                            size_match = re.search(r"\d+(?:[.,]\d+)?\s*(?:KB|MB|GB|TB)", size_text, re.IGNORECASE)
                            size = size_match.group(0) if size_match else ""

                            if not any(keyword in name.lower() for keyword in forbidden_keywords):
                                duplicate_entry = {"name": name, "size": size, "link": torrent_link}
                                dupes.append(duplicate_entry)

        return dupes

    def get_category_id(self, meta: Meta) -> int:
        resolution = meta.resolution
        category = meta.category
        type_ = meta.type
        is_disc = meta.is_disc
        genres = str(meta.genres or "").lower()
        source = (meta.source or "").lower()

        # TV
        tv_web_dl = 22
        tv_x265 = 99
        tv_xvid = 4
        tv_480p = 78
        tv_packs = 65
        tv_x264 = 5
        tv_bd = 23
        documentaries = 26
        sports = 55
        tv_dvd_rip = 25
        tv_non_english = 82
        tv_packs_non_english = 83
        tv_dvd_r = 24

        # Movies
        movie_hd_bluray = 48
        movie_web_dl = 20
        movie_4k = 101
        movie_xvid = 7
        movie_x265 = 100
        movie_non_english = 38
        movie_bd_r = 89
        movie_bd_rip = 90
        movie_dvd_r = 6
        movie_3d = 87
        movie_kids = 54
        movie_480p = 77
        movie_cam = 96

        music_all_codecs = 3
        music_flac = 80

        game_nin = 47
        game_pc = 43
        game_playstation = 71
        game_wii = 50
        game_xbox = 44

        book = 35
        book_non_english = 102
        book_comic = 94
        audiobook = 64
        magazines_or_newspapers = 92

        if "documentary" in genres:
            return documentaries
        if "sport" in genres:
            return sports

        if category == "MOVIE":
            if is_disc == "BDMV":
                return movie_bd_r
            if is_disc == "DVD":
                return movie_dvd_r
            if resolution == "2160p":
                return movie_4k
            if "3D" in meta.three_d:
                return movie_3d
            if meta.video_codec.lower() == "x265":
                return movie_x265
            if type_ in ("WEBDL", "WEBRIP"):
                return movie_web_dl
            if source == "bluray" and resolution in ("1080p", "720p"):
                return movie_hd_bluray
            if type_ == "BDRIP":
                return movie_bd_rip
            if resolution == "480p":
                return movie_480p
            if type_ == "XVID":
                return movie_xvid
            if source in ("CAM", "TS", "TC"):
                return movie_cam
            if "kids" in genres or "family" in genres:
                return movie_kids
            if meta.original_language and meta.original_language != "en":
                return movie_non_english
            return movie_hd_bluray

        if category == "TV":
            if meta.tv_pack:
                if meta.original_language and meta.original_language != "en":
                    return tv_packs_non_english
                return tv_packs
            if meta.original_language and meta.original_language != "en":
                return tv_non_english
            if is_disc:
                if is_disc == "BDMV":
                    return tv_bd
                if is_disc == "DVD":
                    return tv_dvd_r
            if meta.video_codec.lower() == "x265":
                return tv_x265
            if type_ in ("WEBDL", "WEBRIP"):
                return tv_web_dl
            if type_ == "DVDRIP":
                return tv_dvd_rip
            if resolution == "480p":
                return tv_480p
            if type_ == "XVID":
                return tv_xvid
            return tv_x264

        if category == "GAME":
            platform = str(meta.platform).upper()
            if platform in {"NDS", "3DS", "SWITCH"}:
                return game_nin
            if platform in {"WII", "WIIU"}:
                return game_wii
            if platform in {"PS1", "PS2", "PS3", "PS4", "PS5", "PSP", "PSVITA"}:
                return game_playstation
            if platform in {"XBOX", "X360", "XONE", "XSX"}:
                return game_xbox
            return game_pc

        if category == "BOOK":
            if meta.audiobook:
                return audiobook
            if meta.comic or meta.manga:
                return book_comic
            if meta.magazine or meta.newspaper:
                return magazines_or_newspapers
            if meta.book_language_iso.lower() != "eng":
                return book_non_english
            return book

        if category == "MUSIC":
            if str(meta.format).upper() == "FLAC":
                return music_flac
            return music_all_codecs

        return 0

    async def get_name(self, meta: Meta):
        name: str = meta.scene_name if meta.scene_name else meta.clean_name

        replacements = {
            "3DAccess": "3DA",
            "AreaFiles": "AF",
            "BeyondHD": "BHD",
            "Blackcat": "Blackcat",
            "Blu-Bits": "BluHD",
            "Bluebird": "BB",
            "BlueEvolution": "BluEvo",
            "Chdbits": "CHD",
            "CtrlHD": "CtrlHD",
            "HDAccess": "HDA",
            "HDChina": "HDC",
            "HDClub": "HDCL",
            "HDGeek": "HDG",
            "HDRoad": "HDR",
            "HDStar": "HDS",
            "HDWing": "HDW",
            "ExtraTorrent": "ETRG",
            "IWStream": "IWS",
            "Kingdom-KVCD": "KVCD",
            "MVGroup": "MVG",
            "Projekt-Revolution": "Projekt",
            "PublicHD": "PHD",
            "SpaceHD": "SHD",
            "ThumperDC": "TDC",
            "TrollHD": "TrollHD",
            "TheWolfsDen": "TWD",
        }

        for key, value in replacements.items():
            if key in name:
                name = name.replace(key, value)

        name = name.replace("'", "").replace('"', "")

        if meta.scene and "[NO RAR]" not in name.upper():
            name += " [NO RAR]"

        return re.sub(r"\s{2,}", " ", name)

    async def get_is_freeleech(self, meta: Meta):
        torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BASE.torrent"
        if not Path(torrent_path).exists():
            return False

        try:
            async with aiofiles.open(torrent_path, "rb") as f:
                torrent_data = await f.read()
            metainfo = bencodepy.decode(torrent_data)
            info = metainfo.get(b"info", {})
            total_size = 0
            if b"files" in info:
                for file_info in info[b"files"]:
                    total_size += file_info.get(b"length", 0)
            else:
                total_size = info.get(b"length", 0)
            size_gb = total_size / (1024**3)
            return size_gb >= 8
        except Exception as e:
            logger.info(f"{self.tracker}: [bold red]Error reading torrent file for size check on {self.tracker}: {e}[/bold red]")
            return False

    async def get_data(self, meta: Meta) -> dict[str, str | int]:
        data: dict[str, str | int] = {
            "name": meta.name,
            "descr": await self.generate_description(meta),
            "type": self.get_category_id(meta),
        }

        if await self.get_is_freeleech(meta):
            data["freeleech"] = "on"

        # Anon
        anon = not (meta.anon == 0 and not self.config["TRACKERS"][self.tracker].get("anon", False))
        if anon:
            data.update({"anonymous": "on"})

        return data

    async def upload(self, meta: Meta) -> bool:
        cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        self.session.cookies.clear()
        if cookies is not None:
            self.session.cookies.update(cookies)

        data = await self.get_data(meta)

        upload = await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            data=data,
            torrent_field_name="file",
            torrent_name=await self.get_name(meta),
            upload_cookies=self.session.cookies,
            upload_url=f"{self.base_url}/takeupload.php",
            error_text="Upload failed!",
            id_pattern=r"download\.php/(\d+)/",
        )

        if upload and self.config["TRACKERS"][self.tracker]["force_data"] and not meta.debug:
            await self.edit_post_upload(meta)

        return upload

    async def edit_post_upload(self, meta: Meta):
        torrent_id = meta.tracker_status[self.tracker]["torrent_id"]
        data: dict[str, str | int] = {
            "name": meta.name,
            "descr": await self.generate_description(meta),
            "type": self.get_category_id(meta),
            "imdb_id": str(meta.tmdb_id),
            "id": torrent_id,
        }

        edit_url = f"https://iptorrents.com/t/{torrent_id}/edit"

        response = await self.session.post(edit_url, data=data)
        if response.status_code != 302:
            meta.tracker_status[self.tracker]["status_message"] += " Failed to edit torrent."
