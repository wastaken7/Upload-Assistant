# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import os
import re
from pathlib import Path
from typing import Any, cast
from urllib.parse import urlparse, urlunparse

import aiofiles
import httpx

from cogs.redaction import Redaction
from src.console import logger
from src.get_desc import DescriptionBuilder
from src.meta import Meta
from src.tmdb import TmdbManager
from src.trackers.COMMON import COMMON

Config = dict[str, Any]


class MTEAM:
    tracker = "MTEAM"
    api_base_url = "https://api.m-team.cc/api"
    banned_groups = ("FGT",)
    requests_url = f"{api_base_url}/seek/search"
    tracker_urls = ("tracker.m-team.cc", "tra1.m-team.cc", "tracker.m-team.io", "tra1.m-team.io", "tra99.manfuz.co")
    supported_categories = ("TV", "MOVIE")

    def __init__(self, config: Config):
        self.config = config
        self.common = COMMON(config)
        self.tmdb_manager = TmdbManager(config)
        raw_url = self.config["TRACKERS"][self.tracker].get("base_url", "kp.m-team.cc").strip()
        parsed_raw = urlparse(raw_url)
        clean_netloc = parsed_raw.netloc if parsed_raw.netloc else parsed_raw.path
        self.base_url = urlunparse(("https", clean_netloc, "", "", "", ""))
        self.torrent_url = f"{self.base_url}/detail/"
        self.api_key = self.config["TRACKERS"][self.tracker].get("api_key")
        self.session = httpx.AsyncClient(
            headers={
                "x-api-key": self.api_key,
                "Accept": "*/*",
            },
            timeout=30.0,
        )

    async def get_requests(self, meta: Meta) -> list[dict[str, str]]:
        requests: list[dict[str, str]] = []

        category = self.get_category_id(meta)

        payload = {
            "pageNumber": 1,
            "pageSize": 10,
            "keyword": meta.title,
            "take": False,
        }

        try:
            response = await self.session.post(self.requests_url, json=payload, timeout=15)
            response.raise_for_status()
            res_json = response.json()

            data_list = res_json.get("data", {}).get("data", [])

            for item in data_list:
                if item.get("category") != category:
                    continue

                name = item.get("title", "N/A")
                reward = item.get("rewardCurrent", "0")
                link = f"{self.base_url}/seekDetail?id={item.get('id')}"

                requests.append(
                    {
                        "Name": name,
                        "Reward": reward,
                        "Link": link,
                    }
                )

            if requests:
                message = f"\n{self.tracker}: [bold yellow]Your upload may fulfill the following request(s), check it out:[/bold yellow]\n\n"
                for r in requests:
                    message += f"[bold green]Name:[/bold green] {r['Name']}\n"
                    message += f"[bold green]Reward:[/bold green] {r['Reward']}\n"
                    message += f"[bold green]Link:[/bold green] {r['Link']}\n\n"
                logger.info(message)

            return requests

        except Exception as e:
            logger.info(f"{self.tracker}: [bold red]Error searching for requests with title {meta.title}: {e}[/bold red]")
            return requests

    async def mediainfo(self, meta: Meta) -> str:
        mi_path: str = ""
        mediainfo: str = ""

        if meta.is_disc == "BDMV":
            disc_folder = Path(meta.base_dir) / "tmp" / meta.uuid
            for filename in os.listdir(disc_folder):
                if filename.endswith("_FULL.txt"):
                    mi_path = Path(disc_folder) / filename
        else:
            mi_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/MEDIAINFO_CLEANPATH.txt"

        if mi_path:
            async with aiofiles.open(mi_path, encoding="utf-8") as f:
                mediainfo = await f.read()

        return mediainfo

    def bbcode_to_markdown(self, text):
        specific_img_pattern = r"\[url=[^\]]*\]\[img(?:=[^\]]*)?\](.*?)\[/img\]\[/url\]"
        text = re.sub(specific_img_pattern, r"![](\1)", text, flags=re.IGNORECASE)

        patterns = [
            (r"\[b\](.*?)\[/b\]", r"**\1**"),
            (r"\[i\](.*?)\[/i\]", r"*\1*"),
            (r"\[u\](.*?)\[/u\]", r"<u>\1</u>"),
            (r"\[s\](.*?)\[/s\]", r"~~\1~~"),
            (r"\[img(?:=[^\]]*)?\](.*?)\[/img\]", r"![](\1)"),
            (r"\[url=(.*?)\](.*?)\[/url\]", r"[\2](\1)"),
            (r"\[url\](.*?)\[/url\]", r"<\1>"),
        ]

        for pattern, replacement in patterns:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE | re.DOTALL)

        return text

    async def get_douban_info(self, meta: Meta) -> dict[str, Any]:
        info: dict[str, Any] = {}
        douban_id = meta.douban_id
        if not douban_id:
            return info

        api_url = f"{self.api_base_url}/media/douban/infoV2"

        params = {
            "code": douban_id,
            "refresh": False,
        }

        headers = {
            "x-api-key": self.api_key,
            "Accept": "*/*",
        }

        try:
            response = await self.session.post(api_url, headers=headers, params=params, timeout=15)
            response.raise_for_status()
            return response.json()

        except Exception as e:
            logger.info(f"Error fetching Douban info: {e}")
            return info

    async def mteam_standard_desc(self, meta: Meta):
        db_info = await self.get_douban_info(meta)

        if db_info and db_info.get("code") == "0":
            d = db_info.get("data", {})
            title = d.get("title", "")
            aka = d.get("aka", [])
            translated_names = " / ".join([title, *aka]) if title else " / ".join(aka)

            countries = " / ".join(d.get("countries", []))
            genres = " / ".join(d.get("genres", []))
            languages = " / ".join(d.get("languages", []))
            pubdates = " / ".join(d.get("pubdate", []))
            durations = " / ".join(d.get("durations", []))

            directors = " / ".join([person.get("name", "") for person in d.get("directors", [])])
            actors = " / ".join([person.get("name", "") for person in d.get("actors", [])])

            rating_val = d.get("score", "0")
            rating_count = d.get("rating", {}).get("count", "0")
            subject_id = d.get("subjectId", "")

            desc = [
                f"![]({d.get('coverUrl', '')})",
                "",
                f"**◎译　　名** {translated_names}",
                f"**◎片　　名** {title}",
                f"**◎年　　代** {d.get('year', 'N/A')}",
                f"**◎产　　地** {countries}",
                f"**◎类　　别** {genres}",
                f"**◎语　　言** {languages}",
                f"**◎上映日期** {pubdates}",
                f"**◎豆瓣评分** {rating_val}/10 from {rating_count} users",
                f"**◎豆瓣链接** https://www.douban.com/subject/{subject_id}/",
                f"**◎片　　长** {durations}",
                f"**◎导　　演** {directors}",
                f"**◎主　　演** {actors}",
                "",
                "**◎简　　介**",
                "",
                f"　　{d.get('intro', '')}",
            ]
            return "\n".join(desc)

        # Fallback
        logger.info(f"{self.tracker}: Douban information is unavailable, using an alternative English version for the description.")
        imdb = meta.imdb_info

        tmdb_poster_path = meta.tmdb_poster or "".strip()
        tmdb_poster = f"https://image.tmdb.org/t/p/w200{tmdb_poster_path}" if tmdb_poster_path else ""
        poster_url = tmdb_poster or str(imdb.get("cover") or "")
        title = meta.title if meta.title is not None else "N/A"
        year = str(meta.year) if meta.year is not None else "N/A"
        rating = imdb.get("rating", "N/A")

        writers = imdb.get("writers", [])
        creators_str = " / ".join(writers)

        cast = meta.tmdb_cast
        actors_str = " / ".join(cast)

        plot = imdb.get("plot", meta.overview)

        desc = [
            f"![]({poster_url})",
            "",
            f"**Title**: {title}",
            f"**Year**: {year}",
            f"**IMDb Rating**: {rating}/10",
            f"**Creators**: {creators_str}",
            f"**Actors**: {actors_str}",
            "",
            "### Introduction",
            "",
            f"  {plot}",
        ]

        return "\n".join(desc)

    async def generate_description(self, meta: Meta) -> str:
        builder = DescriptionBuilder(self.tracker, self.config)
        meta.mteam_description = await self.mteam_standard_desc(meta)

        description = await builder.general_description_generator(
            meta,
            audio_spectrogram=True,
            bluray=True,
            book=True,
            custom_header=True,
            custom_signature=True,
            description=True,
            game=True,
            languages=False,
            logo=True,
            mediainfo=False,
            menu_screenshots=True,
            nfo=False,
            screenshots=True,
            tonemapped_header=True,
            tv_info=False,
            ua_signature=True,
            user_description=True,
            signature=f"[{meta.ua_signature}](https://github.com/wastaken7/Upload-Assistant)",
        )

        from src.bbcode import BBCODE

        bbcode = BBCODE()
        description = description.strip()
        description = description.replace("[*] ", "• ").replace("[*]", "• ")
        description = self.bbcode_to_markdown(description)
        description = description.replace("[center]", "").replace("[/center]", "")
        description = bbcode.remove_extra_lines(description)

        async with aiofiles.open(f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt", "w", encoding="utf-8") as description_file:
            await description_file.write(description)

        return description

    def get_category_id(self, meta: Meta) -> int | None:
        movie_sd = 401  # Movie/SD
        movie_hd = 419  # Movie/HD
        movie_dvdiso = 420  # Movie/DVDiSo
        movie_blu_ray = 421  # Movie/Blu-Ray
        movie_remux = 439  # Movie/Remux
        tv_series_sd = 403  # TV Series/SD
        tv_series_hd = 402  # TV Series/HD
        tv_series_bd = 438  # TV Series/BD
        tv_series_dvdiso = 435  # TV Series/DVDiSo
        anime = 405  # Anime

        is_sd = meta.sd
        is_dvd = meta.is_disc == "DVD"
        is_bd = meta.is_disc == "BDMV"
        is_remux = meta.type == "REMUX"
        is_anime = meta.anime

        if is_anime:
            return anime

        if is_bd:
            return tv_series_bd if meta.category == "TV" else movie_blu_ray

        if is_remux and meta.category == "MOVIE":
            return movie_remux

        if is_dvd:
            return tv_series_dvdiso if meta.category == "TV" else movie_dvdiso

        if is_sd:
            return tv_series_sd if meta.category == "TV" else movie_sd

        # Default to HD
        return tv_series_hd if meta.category == "TV" else movie_hd

    async def get_additional_checks(self, meta: Meta):
        should_continue = True

        imdb_id = meta.imdb_info.get("imdbID")
        if not imdb_id:
            logger.info(f"{self.tracker}: [bold yellow]IMDb ID not found in metadata, skipping upload.[/bold yellow]")
            return False

        # Upscaled Content
        uuid: str = meta.uuid
        if "upscale" in uuid.lower() and "upscale" not in meta.title:
            logger.info(f"{self.tracker}: Uploading upscaled files created by converting low-bitrate videos to high-bitrate versions might be prohibited.")
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                user_input = self.common.prompt_user_for_confirmation(f"{self.tracker}: Do you want to continue with the upload? (y/n): ")
                if not user_input:
                    return False
            else:
                return False

        # Screenshots
        if meta.screens < 3:
            logger.info(f"{self.tracker}: [bold yellow]At least 3 screenshots are required for video uploads. Skipping upload.[/bold yellow]")
            return False

        # LGBT Content
        keywords_str = ", ".join(meta.keywords)
        genres = f"{keywords_str} {meta.combined_genres}"
        combined_list = [item.strip() for item in genres.split(",") if item.strip()]
        lgbt_keywords = ["lgbt", "queer", "lgbtq", "lgbtqia", "transgender", "trans", "gay", "lesbian", "bisexual", "pansexual", "non-binary", "homoerotic"]
        if any(kw in combined_list for kw in lgbt_keywords):
            logger.info(
                f"{self.tracker}: [bold yellow]LGBT content detected. Please ensure the cover photo does not contain depictions of genitalia per tracker rules.[/bold yellow]"
            )
            if not meta.unattended or (meta.unattended and meta.unattended_confirm):
                user_input = self.common.prompt_user_for_confirmation(f"{self.tracker}: Do you want to continue with the upload? (y/n): ")
                if not user_input:
                    return False
            else:
                return False

        return should_continue

    async def search_existing(self, meta: Meta) -> list[dict[str, Any]]:
        dupes: list[dict[str, Any]] = []

        imdb_id = meta.imdb_info.get("imdbID")
        category = self.get_category_id(meta)
        standard = self.get_standard(meta)

        if not imdb_id:
            logger.info(f"{self.tracker}: [bold yellow]Cannot perform search on {self.tracker}: IMDb ID not found in metadata.[/bold yellow]")
            return dupes

        api_url = f"{self.api_base_url}/torrent/search"

        payload = {
            "mode": "normal",
            "imdb": imdb_id,
            "categories": [category],
            "standards": [standard],
        }

        response = await self.session.post(api_url, json=payload, timeout=15)
        res_json = response.json()

        if res_json.get("code") != "0":
            logger.info(f"[bold red]API Error: {res_json.get('message')}[/bold red]")
            return dupes

        torrents = res_json.get("data", {}).get("data", [])

        for torrent in torrents:
            t_id = torrent.get("id")
            if not t_id:
                continue

            dupe_entry = {
                "name": torrent.get("name"),
                "size": int(torrent.get("size", 0)),
                "link": f"{self.base_url}/detail/{t_id}",
                "file_count": torrent.get("file_count", 0),
                "download": f"{self.api_base_url}/torrent/genDlToken?id={t_id}",
                "id": t_id,
            }
            if meta.is_disc == "BDMV":
                bdinfo = await self.get_dupe_bdinfo(t_id)
                if bdinfo:
                    dupe_entry["bd_info"] = bdinfo

            dupes.append(dupe_entry)

        return dupes

        return dupes

    async def get_dupe_bdinfo(self, torrent_id: int) -> str:
        api_url = f"{self.api_base_url}/torrent/detail?id={torrent_id}"

        try:
            response = await self.session.post(api_url, timeout=15)
            response.raise_for_status()

            response_data = response.json()
            bdinfo = response_data.get("data", {}).get("mediainfo")
            if not bdinfo:
                bdinfo = response_data.get("data", {}).get("descr")
            return bdinfo

        except Exception as e:
            logger.info(f"{self.tracker}: Error fetching BDinfo: {e}")
            return ""

    def get_standard(self, meta: Meta) -> int:
        _1080p = 1
        _1080i = 2
        _720p = 3
        sd = 5
        _4k = 6
        _8k = 7

        resolution = meta.resolution.lower()
        if resolution == "1080p":
            return _1080p
        if resolution == "1080i":
            return _1080i
        if resolution == "720p":
            return _720p
        if resolution == "2160p":
            return _4k
        if resolution == "4320p":
            return _8k
        if meta.sd:
            return sd
        logger.info(f"{self.tracker}: Unknown or unsupported resolution '{resolution}', defaulting to 1080p.")
        return _1080p

    def get_videocodec(self, meta: Meta) -> int:
        x264 = 1  # H.264(x264/AVC)
        x265 = 16  # H.265(x265/HEVC)
        vc1 = 2  # VC-1
        mpeg2 = 4  # MPEG-2
        xvid = 3  # Xvid
        av1 = 19  # AV1
        vp8_9 = 21  # VP8/9

        codec = meta.video_codec.lower()
        if codec in ("h264", "x264", "avc", "h.264"):
            return x264
        if codec in ("h265", "h.265", "hevc", "x265"):
            return x265
        if codec in ("vc1", "vc-1"):
            return vc1
        if codec in ("mpeg2", "mpeg-2"):
            return mpeg2
        if codec == "xvid":
            return xvid
        if codec == "av1":
            return av1
        if codec in ("vp8", "vp9"):
            return vp8_9
        logger.info(f"{self.tracker}: Unknown or unsupported video codec '{codec}', defaulting to x264.")
        return x264

    def get_audiocodec(self, meta: Meta) -> int:
        aac = 6  # AAC
        ac3 = 8  # AC3(DD)
        dts = 3  # DTS
        dts_hd_ma = 11  # DTS-HD MA
        eac3 = 12  # E-AC3(DDP)
        atmos_eac3 = 13  # E-AC3 Atoms(DDP Atoms)
        true_hd = 9  # TrueHD

        codec = meta.audio.lower()

        if "atmos" in codec and "dd+" in codec:
            return atmos_eac3
        if "aac" in codec:
            return aac
        if "dd+" in codec:
            return eac3
        if "dd " in codec:
            return ac3
        if "dts-hd" in codec:
            return dts_hd_ma
        if "dts" in codec:
            return dts
        if "truehd" in codec:
            return true_hd
        logger.info(f"{self.tracker}: Unknown or unsupported audio codec '{codec}', defaulting to AC3.")
        return ac3

    async def fetch_data(self, meta: Meta) -> dict[str, Any]:
        """
        https://test2.m-team.cc/api/swagger-ui/index.html#/種子/createOredit
        """
        return {
            # "torrent": 0,
            # "offer": 0,
            "name": meta.name,
            "smallDescr": self.common.get_small_description(meta),
            "descr": await self.generate_description(meta),
            "category": self.get_category_id(meta),
            # "source": 0,
            # "medium": 0,
            "standard": self.get_standard(meta),
            "videoCodec": self.get_videocodec(meta),
            "audioCodec": self.get_audiocodec(meta),
            # "team": 0,
            # "processing": 0,
            # "countries": "",
            "imdb": meta.imdb_info.get("imdbID", ""),
            "douban": meta.douban_id,
            # "dmmCode": "",
            # "cids": "",
            # "aids": "",
            "anonymous": bool(meta.anon or self.config["TRACKERS"][self.tracker].get("anon", False)),
            # "labels": 0,
            # "tags": "",
            # "file": "",
            # "nfo": "",
            "mediainfo": await self.mediainfo(meta),
            "mediaInfoAnalysisResult": True,
            # "labelsNew": ""
        }

    async def upload(self, meta: Meta) -> bool:
        data = await self.fetch_data(meta)
        response = None

        if not meta.debug:
            try:
                upload_url = f"{self.api_base_url}/torrent/createOredit"
                await self.common.create_torrent_for_upload(meta, self.tracker, "[kp.m-team.cc] M-Team - TP")
                torrent_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}].torrent"

                async with aiofiles.open(torrent_path, "rb") as torrent_file:
                    torrent_bytes = await torrent_file.read()
                files = {"file": ("upload.torrent", torrent_bytes, "application/x-bittorrent")}

                response = await self.session.post(upload_url, data=data, files=files, headers=dict(self.session.headers), timeout=90)
                response.raise_for_status()
                response_json = response.json()
                response_data: dict[str, Any] = cast(dict[str, Any], response_json) if isinstance(response_json, dict) else {}

                if response_data.get("message") == "SUCCESS":
                    torrent_id = str(response_data["data"]["id"])
                    meta.tracker_status[self.tracker]["torrent_id"] = torrent_id
                    meta.tracker_status[self.tracker]["status_message"] = response_data.get("message")

                    download_api_url = f"{self.api_base_url}/torrent/genDlToken?id={torrent_id}"
                    response = await self.session.post(download_api_url)
                    data = response.json()
                    final_download_url = data.get("data")
                    if final_download_url:
                        await self.common.download_tracker_torrent(
                            meta,
                            self.tracker,
                            headers=dict(self.session.headers),
                            downurl=final_download_url,
                        )
                        return True
                    logger.info(f"{self.tracker}: Failed to get download URL from API response.")
                    meta.tracker_status[self.tracker]["status_message"] = "Failed to get download URL from API response"
                    return False
                meta.tracker_status[self.tracker]["status_message"] = f"data error: {response_data.get('message', 'Unknown API error.')}"
                return False

            except httpx.HTTPStatusError as e:
                meta.tracker_status[self.tracker]["status_message"] = f"data error: HTTP {e.response.status_code} - {e.response.text}"
                return False
            except httpx.TimeoutException:
                meta.tracker_status[self.tracker]["status_message"] = f"data error: Request timed out after {self.session.timeout.write} seconds"
                return False
            except httpx.RequestError as e:
                resp_text = getattr(getattr(e, "response", None), "text", "No response received")
                meta.tracker_status[self.tracker]["status_message"] = f"data error: Unable to upload. Error: {e}.\nResponse: {resp_text}"
                return False
            except Exception as e:
                resp_text = response.text if response is not None else "No response received"
                meta.tracker_status[self.tracker]["status_message"] = f"data error: It may have uploaded, go check. Error: {e}.\nResponse: {resp_text}"
                return False

        else:
            logger.info("[cyan]M-Team Request Data:")
            logger.info(Redaction.redact_private_info(data))
            meta.tracker_status[self.tracker]["status_message"] = "Debug mode enabled, not uploading"
            await self.common.create_torrent_for_upload(meta, f"{self.tracker}" + "_DEBUG", f"{self.tracker}" + "_DEBUG", announce_url="https://fake.tracker")
            return True  # Debug mode - simulated success
