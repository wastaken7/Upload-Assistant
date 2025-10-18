import aiofiles
import bbcode
import httpx
import platform
import re
from bs4 import BeautifulSoup
from src.bbcode import BBCODE
from src.console import console
from src.cookie_auth import CookieValidator, CookieAuthUploader
from src.get_desc import DescriptionBuilder
from src.languages import process_desc_language


class YGG:
    def __init__(self, config):
        self.config = config
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.tracker = "YGG"
        self.source_flag = "YGG"  # This does not work
        self.base_url = "https://www.yggtorrent.top"
        self.upload_url = f"{self.base_url}/user/upload_torrent_action"
        self.search_url = f"{self.base_url}/engine/search?"
        self.torrent_url = f"{self.base_url}/torrent/"
        self.announce_url = self.config["TRACKERS"][self.tracker]["announce_url"]
        self.banned_groups = []
        self.session = httpx.AsyncClient(
            headers={"User-Agent": f"Upload Assistant ({platform.system()} {platform.release()})"},
            timeout=60.0,
        )
        pass

    async def validate_credentials(self, meta):
        self.session.cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        return await self.cookie_validator.cookie_validation(
            meta=meta,
            tracker=self.tracker,
            test_url=f"{self.base_url}/user/upload_torrent",
            success_text="Déconnexion",
        )

    async def search_existing(self, meta, disctype):
        if not await self.get_additional_checks(meta):
            meta["skipping"] = f"{self.tracker}"
            return

        results = []
        params = {
            "name": meta["title"],
            "category": await self.get_category_id(meta),
            "sub_category": await self.get_type_id(meta),
            "do": "search",
        }
        search_url = f"{self.base_url}/engine/search?"

        try:
            response = await self.session.get(search_url, params=params)
            response.raise_for_status()

            html_content = response.text
            soup = BeautifulSoup(html_content, "html.parser")
            results_div = soup.find("div", class_="results")

            if results_div:
                torrent_links = results_div.find_all("a", id="torrent_name")

                for torrent in torrent_links:
                    name = torrent.get_text(strip=True)

                    link = torrent.get("href")

                    if name and link:
                        results.append({"name": name, "link": link, "size": None})

        except httpx.TimeoutException:
            console.print(f"{self.tracker}: Timeout while searching for existing torrents.")
            return []
        except httpx.HTTPStatusError as e:
            console.print(f"{self.tracker}: HTTP error while searching: Status {e.response.status_code}.")
            return []
        except httpx.RequestError as e:
            console.print(f"{self.tracker}: Network error while searching: {e.__class__.__name__}.")
            return []
        except Exception as e:
            console.print(f"{self.tracker}: Unexpected error while searching: {e}")
            return []
        return results

    async def get_additional_checks(self, meta):
        if await self.get_category_id(meta) == 0:
            console.print(f"[bold red]{self.tracker}: Category not supported. Skipping upload...[/bold red]")
            meta["skipping"] = f"{self.tracker}"
            return False
        if await self.get_type_id(meta) == 0:
            console.print(f"[bold red]{self.tracker}: Type not supported. Skipping upload...[/bold red]")
            meta["skipping"] = f"{self.tracker}"
            return False
        if await self.get_quality(meta) == 0:
            console.print(f"[bold red]{self.tracker}: Quality not supported. Skipping upload...[/bold red]")
            meta["skipping"] = f"{self.tracker}"
            return False

        if not meta.get("language_checked", False):
            await process_desc_language(meta, desc=None, tracker=self.tracker)
        portuguese_languages = ["French", "french", "French (Canada)", "french (canada)"]
        if not any(lang in meta.get("audio_languages", []) for lang in portuguese_languages) and not any(
            lang in meta.get("subtitle_languages", []) for lang in portuguese_languages
        ):
            console.print(f"[bold red]{self.tracker} requires at least one French audio or subtitle track.")
            return False

        return True

    async def get_category_id(self, meta):
        return 2145

    async def get_type_id(self, meta):
        animation = 2178
        animation_series = 2179
        documentary = 2181
        tv_show = 2182
        movie = 2183
        tv_series = 2184

        if meta["category"] == "MOVIE":
            if meta.get("anime", False):
                return animation
            return movie
        elif meta["category"] == "TV":
            if meta.get("anime", False):
                return animation_series
            return tv_series

        meta_keywords_list = [k.strip() for k in meta.get("keywords", "").split(",")]
        if any(keyword in meta_keywords_list for keyword in ["documentary", "biography"]):
            return documentary
        if any(keyword in meta_keywords_list for keyword in ["tv show", "talk show", "game show"]):
            return tv_show

        return 0

    async def get_name(self, meta):
        return meta["uuid"]

    async def get_description(self, meta):
        builder = DescriptionBuilder(self.config)
        desc_parts = []

        # Custom Header
        desc_parts.append(await builder.get_custom_header(self.tracker))

        # TV
        title, episode_image, episode_overview = await builder.get_tv_info(meta, self.tracker)
        if episode_overview:
            desc_parts.append(f"[center]{title}[/center]")
            desc_parts.append(f"[center]{episode_overview}[/center]")

        # User description
        desc_parts.append(await builder.get_user_description(meta))

        # Screenshot Header
        desc_parts.append(await builder.screenshot_header(self.tracker))

        # Screenshots
        images = meta["image_list"]
        if images:
            screenshots_block = "[center]\n"
            for i, image in enumerate(images, start=1):
                img_url = image["img_url"]
                web_url = image["web_url"]
                screenshots_block += f"[url={web_url}][img]{img_url}[/img][/url] "
                # limits to 2 screens per line, as the description box is small
                if i % 2 == 0:
                    screenshots_block += "\n"
            screenshots_block += "\n[/center]"
            desc_parts.append(screenshots_block)

        # Tonemapped Header
        desc_parts.append(await builder.get_tonemapped_header(meta, self.tracker))

        # Signature
        desc_parts.append(
            f"[center][url=https://github.com/Audionut/Upload-Assistant]{meta['ua_signature']}[/url][/center]"
        )

        description = "\n\n".join(part for part in desc_parts if part.strip())

        ua_bbcode = BBCODE()
        description = ua_bbcode.remove_img_resize(description)
        description = ua_bbcode.convert_named_spoiler_to_normal_spoiler(description)
        description = ua_bbcode.convert_comparison_to_centered(description, 1000)
        description = description.strip()
        description = ua_bbcode.remove_extra_lines(description)

        # [url][img=000]...[/img][/url]
        description = re.sub(
            r"\[url=(?P<href>[^\]]+)\]\[img=(?P<width>\d+)\](?P<src>[^\[]+)\[/img\]\[/url\]",
            r'<a href="\g<href>" target="_blank"><img src="\g<src>" width="\g<width>"></a>',
            description,
            flags=re.IGNORECASE
        )

        # [url][img]...[/img][/url]
        description = re.sub(
            r"\[url=(?P<href>[^\]]+)\]\[img\](?P<src>[^\[]+)\[/img\]\[/url\]",
            r'<a href="\g<href>" target="_blank"><img src="\g<src>" width="220"></a>',
            description,
            flags=re.IGNORECASE
        )

        # [img=200]...[/img] (no [url])
        description = re.sub(
            r"\[img=(?P<width>\d+)\](?P<src>[^\[]+)\[/img\]",
            r'<img src="\g<src>" width="\g<width>">',
            description,
            flags=re.IGNORECASE
        )

        bbcode_tags_pattern = r'\[/?(size|align|left|center|right|img|table|tr|td|spoiler|url)[^\]]*\]'
        description, _ = re.subn(
            bbcode_tags_pattern,
            '',
            description,
            flags=re.IGNORECASE
        )

        description = bbcode.render_html(description)

        async with aiofiles.open(
            f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt", "w", encoding="utf-8"
        ) as description_file:
            await description_file.write(description)

        return description

    async def get_nfo(self, meta):
        nfo_content = ""
        if meta.get("is_disc") == "BDMV":
            nfo_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/Disc1_00001_FULL.txt"
        else:
            nfo_path = f"{meta['base_dir']}/tmp/{meta['uuid']}/MEDIAINFO_CLEANPATH.txt"
        async with aiofiles.open(nfo_path, "r", encoding="utf-8") as f:
            nfo_content = await f.read()

        return {"nfo_file": (f"[{self.tracker}]DESCRIPTION.nfo", nfo_content, "text/plain")}

    async def get_language(self, meta):
        english = 1  # Only when there is no French dubbing or subtitles
        french_truefrench = 2  # Only when there is French dubbing and it is BDMV
        silent = 3  # search for the keyword silent
        multi_french_included = 4  # when there is French dubbing and other languages as well
        multi_quebecois_included = 5  # when there is Canadian French dubbing and other languages as well
        quebecois_french = 6  # only when there is only Canadian French
        vfstfr = 7  # French SDH subtitles
        vostfr = 8  # French subtitles, but no dubbing

        results = []

        has_fr_dub = "French" in meta.get("audio_languages", [])
        has_fr_sub = "French" in meta.get("subtitle_languages", [])

        mediainfo_tracks = meta.get("mediainfo", {}).get("media", {}).get("track", [])
        has_can_fr_dub = any(
            "Canadian" in track.get("Title", "") and track.get("@type") == "Audio"
            for track in mediainfo_tracks
        )
        has_can_fr_sub = any(
            "Canadian" in track.get("Title", "") and track.get("@type") == "Text"
            for track in mediainfo_tracks
        )

        # French dubbing and subtitles
        if has_fr_dub and has_fr_sub:
            if meta.get("is_disc") == "BDMV":
                results.append(french_truefrench)
            else:
                results.append(multi_french_included)

        # Canadian French dubbing and subtitles
        if has_can_fr_dub and has_can_fr_sub:
            if meta.get("is_disc") == "BDMV":
                results.append(quebecois_french)
            else:
                results.append(multi_quebecois_included)

        # Only French subtitles (no dub)
        if has_fr_sub and not has_fr_dub:
            results.append(vostfr)

        # Only French dubbing (no subs)
        if has_fr_dub and not has_fr_sub:
            results.append(multi_french_included)

        # Silent keyword
        if "silent" in meta.get("keywords", []):
            results.append(silent)

        # French SDH subtitles
        if has_fr_sub:
            if any("SDH" in track.get("Title", "") for track in mediainfo_tracks):
                results.append(vfstfr)

        # Fallback: English only
        if not results:
            results.append(english)

        return results

    async def get_quality(self, meta):
        bdrip_brrip = 1  # BDrip/BRrip [Rip SD (non-HD) from Bluray or HDrip]
        bluray_4k = 2  # Bluray 4K [Full or Remux]
        bluray_full = 3  # Bluray [Full]
        bluray_remux = 4  # Bluray [Remux]
        dvd_r5 = 5  # DVD-R 5 [DVD < 4.37GB]
        dvd_r9 = 6  # DVD-R 9 [DVD > 4.37GB]
        dvdrip = 7  # DVDrip [Ripped from DVD-R]
        hdrip_1080 = 8  # HDrip 1080 [Rip HD from Bluray]
        hdrip_4k = 9  # HDrip 4k [Rip HD 4k from 4k source]
        hdrip_720 = 10  # HDrip 720 [Rip HD from Bluray]
        tvrip = 11  # TVrip [Rip SD (non-HD) from HD/SD TV source]
        tvrip_hd_1080 = 12  # TVripHD 1080 [Rip HD from Source TV HD]
        tvrip_hd_4k = 13  # TvripHD 4k [Rip HD 4k from Source TV 4k]
        tvrip_hd_720 = 14  # TVripHD 720 [Rip HD from Source TV HD]
        vcd_svcd_vhsrip = 15  # VCD/SVCD/VHSrip
        web_dl = 16  # Web-Dl
        web_dl_1080 = 17  # Web-Dl 1080
        web_dl_4k = 18  # Web-Dl 4K
        web_dl_720 = 19  # Web-Dl 720
        webrip = 20  # WEBrip
        webrip_1080 = 21  # WEBrip 1080
        webrip_4k = 22  # WEBrip 4K
        webrip_720 = 23  # WEBrip 720

        source_type = meta.get("type", "").lower()
        resolution = meta.get("resolution", "").lower()
        is_disc = meta.get("is_disc")

        if is_disc == "BDMV":
            if resolution == "2160p":
                return bluray_4k
            return bluray_full
        elif is_disc == "DVD":
            if meta.get("dvd_size") == "DVD5":
                return dvd_r5
            return dvd_r9

        if source_type == "remux":
            if resolution == "2160p":
                return bluray_4k
            return bluray_remux

        if source_type in ("bdrip", "brrip", "encode"):
            if resolution == "1080p":
                return hdrip_1080
            if resolution == "720p":
                return hdrip_720
            if resolution == "2160p":
                return hdrip_4k
            return bdrip_brrip

        if source_type == "dvdrip":
            return dvdrip

        if source_type in ("hdtv", "pdtv", "sdtv", "tvrip"):
            if resolution == "2160p":
                return tvrip_hd_4k
            if resolution == "1080p":
                return tvrip_hd_1080
            if resolution == "720p":
                return tvrip_hd_720
            return tvrip

        if source_type in ("web-dl", "webdl"):
            if resolution == "2160p":
                return web_dl_4k
            if resolution == "1080p":
                return web_dl_1080
            if resolution == "720p":
                return web_dl_720
            return web_dl

        if source_type == "webrip":
            if resolution == "2160p":
                return webrip_4k
            if resolution == "1080p":
                return webrip_1080
            if resolution == "720p":
                return webrip_720
            return webrip

        if source_type in ("vhsrip", "vcd", "svcd"):
            return vcd_svcd_vhsrip

        return 0

    async def get_genres(self, meta):
        tmdb_to_french_genre = {
            "Action": "Action",
            "Adventure": "Aventure",
            "Animation": "Animation",
            "Comedy": "Comédie",
            "Crime": "Policier",
            "Documentary": "Documentaire",
            "Drama": "Drame",
            "Family": "Famille",
            "Fantasy": "Fantastique",
            "History": "Historique",
            "Horror": "Epouvante & Horreur",
            "Music": "Musical",
            "Mystery": "Enquête",
            "Romance": "Romance",
            "Science Fiction": "Science fiction",
            "TV Movie": "Divers",
            "Thriller": "Thriller",
            "War": "Guerre",
            "Western": "Western",
        }

        french_genre_ids = {
            "Action": 1,
            "Animalier": 2,
            "Animation": 3,
            "Arts": 4,
            "Arts Martiaux": 5,
            "Aventure": 6,
            "Ballet": 7,
            "Biopic": 8,
            "Chorégraphie": 9,
            "Classique": 10,
            "Comédie": 11,
            "Comédie dramatique": 12,
            "Court-métrage": 13,
            "Culinaire": 14,
            "Danse contemporaine": 15,
            "Découverte": 16,
            "Divers": 17,
            "Documentaire": 18,
            "Drame": 19,
            "Enquête": 20,
            "Epouvante & Horreur": 21,
            "Espionnage": 22,
            "Famille": 23,
            "Fantastique": 24,
            "Fiction": 25,
            "Film Noir": 26,
            "Gore": 27,
            "Guerre": 28,
            "Historique": 29,
            "Humour": 30,
            "Intéractif": 31,
            "Judiciaire": 32,
            "Litterature": 33,
            "Manga": 34,
            "Musical": 35,
            "Nanar": 36,
            "Nature": 37,
            "Opéra": 38,
            "Opéra Rock": 39,
            "Pédagogie": 40,
            "Péplum": 41,
            "Philosophie": 42,
            "Policier": 43,
            "Politique & Géopolitique": 44,
            "Religions & Croyances": 45,
            "Romance": 46,
            "Santé & Bien-être": 47,
            "Science fiction": 48,
            "Sciences & Technologies": 49,
            "Société": 50,
            "Sports & Loisirs": 51,
            "Télé-Réalité": 52,
            "Théatre": 53,
            "Thriller": 54,
            "Variétés TV": 55,
            "Voyages & Tourisme": 56,
            "Western": 57,
        }

        if not meta.get("genres"):
            return []

        english_genres = [g.strip() for g in meta["genres"].split(",")]
        genre_ids = set()

        for english_genre in english_genres:
            french_genre_name = tmdb_to_french_genre.get(english_genre)

            if french_genre_name:
                french_genre_id = french_genre_ids.get(french_genre_name)

                if french_genre_id is not None:
                    genre_ids.add(french_genre_id)

        return list(genre_ids)

    async def get_data(self, meta):
        data = {
            "parent_category": await self.get_category_id(meta),
            "category": await self.get_type_id(meta),
            "name": await self.get_name(meta),
            "torrent_description": await self.get_description(meta),
            "option_langue[]": await self.get_language(meta),
            "option_qualite": await self.get_quality(meta),
            "option_type": 1,
            "option_systeme[]": 2,
            "option_genre[]": await self.get_genres(meta),
        }
        return data

    async def upload(self, meta, disctype):
        self.session.cookies = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        data = await self.get_data(meta)
        files = await self.get_nfo(meta)

        await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            data=data,
            torrent_field_name="torrent_file",
            upload_cookies=self.session.cookies,
            upload_url=self.upload_url,
            additional_files=files,
            success_text="Upload successful!",
        )

        return
