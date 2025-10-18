import aiofiles
import httpx
import json
import langcodes
import os
from src.tmdb import get_tmdb_localized_data
import platform
from bs4 import BeautifulSoup
from src.console import console
from src.cookie_auth import CookieValidator, CookieAuthUploader
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

    async def load_localized_data(self, meta):
        localized_data_file = f'{meta["base_dir"]}/tmp/{meta["uuid"]}/tmdb_localized_data.json'
        main_french_data = {}
        data = {}

        if os.path.isfile(localized_data_file):
            try:
                async with aiofiles.open(localized_data_file, 'r', encoding='utf-8') as f:
                    content = await f.read()
                    data = json.loads(content)
            except json.JSONDecodeError:
                print(f'Warning: Could not decode JSON from {localized_data_file}')
                data = {}
            except Exception as e:
                print(f'Error reading file {localized_data_file}: {e}')
                data = {}

        main_french_data = data.get('fr-FR', {}).get('main')

        if not main_french_data:
            main_french_data = await get_tmdb_localized_data(
                meta,
                data_type='main',
                language='fr-FR',
                append_to_response='credits,videos,content_ratings'
            )

        self.main_tmdb_data = main_french_data or {}

        return

    async def get_description(self, meta):
        """
        Description must be the YGG standard format.
        """
        fr_data = self.main_tmdb_data
        desc = []

        # Title
        title = fr_data.get("title", "") or fr_data.get("name", "")
        desc.append(
            f'[center][size=200][color=#aa0000][b]{title}[/b][/color][/size]'
        )

        # Poster
        poster_url = fr_data.get("poster_path")
        desc.append(
            f"[img]https://image.tmdb.org/t/p/w500{poster_url}[/img]"
        )

        # YGG Banner: Information
        desc.append(
            "[img]https://i.imgur.com/oiqE1Xi.png[/img]"
        )

        # Origin Country
        origin_country = fr_data.get("origin_country", [])
        if origin_country:
            desc.append(f"[b]Origine :[/b] : {', '.join(origin_country)}"
                        )

        # Release Date
        release_date = fr_data.get("release_date", "") or fr_data.get("first_air_date", "")
        if release_date:
            desc.append(
                f"[b]Sortie :[/b] {release_date}"
            )

        # Original Title
        original_title = fr_data.get("original_title", "") or fr_data.get("original_name", "")
        if original_title:
            desc.append(
                f"[b]Titre original :[/b] {original_title}"
            )

        # Runtime
        runtime = fr_data.get("runtime", "") or meta.get("runtime", "")
        if runtime:
            hours = runtime // 60
            minutes = runtime % 60
            desc.append(
                f"Durée: {hours}h et {minutes}min"
            )

        # Directors
        directors = meta.get("tmdb_directors", [])
        if directors:
            desc.append(
                f"[b]Réalisateur :[/b] {', '.join(directors)}"
            )

        # Actors
        actors = meta.get('tmdb_cast', [])
        if actors:
            desc.append(
                f"[b]Acteurs :[/b]\n"
                f"{', '.join(actors)}"
            )

        # Genres
        genres = [g["name"] for g in fr_data.get("genres", [])]
        if genres:
            desc.append(
                f"Genre: {', '.join(genres)}"
            )

        # Rating
        rating = fr_data.get("vote_average", 0.0)
        rating_img = self._desc_ratings(rating)
        desc.append(
            f"[img]{rating_img}[/img] {rating}"
        )

        # TMDB link
        category_lower = meta.get("category", "").lower()
        tmdb_link = (
            f"https://www.themoviedb.org/{category_lower}/{meta.get('tmdb_id')}"
        )
        if tmdb_link:
            desc.append(
                f"[img]https://zupimages.net/up/21/03/mxao.png[/img] "
                f"[url={tmdb_link}]Fiche du film[/url]"
            )

        # Trailer
        videos = fr_data.get("videos", {})
        youtube_videos = [v for v in videos.get("results", []) if v.get("site") == "YouTube"]
        if youtube_videos:
            trailer_key = youtube_videos[0].get("key")
            if trailer_key:
                desc.append(
                    f"[img]https://www.zupimages.net/up/21/02/ogot.png[/img] "
                    f"[url=https://www.youtube.com/watch?v={trailer_key}]Bande annonce[/url]"
                )

        # YGG Banner: Overview
        desc.append(
            "[img]https://i.imgur.com/HS8PPgH.png[/img]"
        )

        # Overview
        overview = fr_data.get("overview")
        if overview:
            desc.append(
                f"{overview}"
            )

        # Cast photos from TMDB
        cast_data = ((self.main_tmdb_data or {}).get('credits') or {}).get('cast', [])
        if cast_data:
            for person in cast_data[:5]:
                profile_path = person.get('profile_path')
                desc.append(
                    f"[img]https://image.tmdb.org/t/p/w138_and_h175_face/{profile_path}[/img] "
                )

        # YGG Banner: Technical information
        desc.append(
            "[img]https://i.imgur.com/fKYpxI3.png[/img]"
        )

        # Technical information
        # Quality
        quality = await self._desc_quality(meta)
        desc.append(
            f"[b]Qualité :[/b] {quality}"
        )

        # Format
        format_ = meta.get("container", "").upper()
        desc.append(
            f"[b]Format :[/b] {format_}"
        )

        # Video Codec
        video_codec = meta.get("video_codec", "").upper()
        desc.append(
            f"[b]Codec Vidéo :{video_codec}"
        )

        # Video bit rate
        bitrate = self._desc_bitrate(meta)
        if bitrate:
            desc.append(
                f"[b]Débit Vidéo :[/b] {bitrate} kbps"
            )

        # Audio Languages
        await self._desc_audio_languages(meta, desc)

        description = "\n".join(desc)
        async with aiofiles.open(f"{meta['base_dir']}/tmp/{meta['uuid']}/[{self.tracker}]DESCRIPTION.txt", 'w', encoding='utf-8') as description_file:
            await description_file.write(description)

        return description

    async def _desc_audio_languages(self, meta, desc):
        processed_tracks = set()
        if "discs" in meta:
            for disc in meta.get("discs", []):
                if disc.get("type") == "BDMV" and disc.get("bdinfo"):
                    audio_tracks = disc.get("bdinfo", {}).get("audio", [])
                    for track in audio_tracks:
                        lang = track.get("language")
                        channels = track.get("channels")
                        codec = track.get("codec")
                        bitrate = track.get("bitrate")

                        track_tuple = (lang, channels, codec, bitrate)
                        if lang:
                            processed_tracks.add(track_tuple)

        elif "mediainfo" in meta:
            tracks = meta.get("mediainfo", {}).get("media", {}).get("track", [])
            for track in tracks:
                if track.get("@type") == "Audio":
                    lang = track.get("Language")
                    channels = track.get("Channels")
                    codec = track.get("Format")
                    bitrate = track.get("BitRate")

                    track_tuple = (lang, channels, codec, bitrate)
                    if lang:
                        processed_tracks.add(track_tuple)

        for lang_name, channels_raw, codec_raw, bitrate_raw in sorted(list(processed_tracks)):

            flag_url = ""
            display_name = ""

            try:
                lang_obj = langcodes.find(lang_name)

                # Get the base language object (e.g., 'pt' from 'pt-PT')
                base_lang_obj = langcodes.find(lang_obj.language)
                display_name = base_lang_obj.display_name('pt').capitalize()

                # First, check if the language tag already has a territory
                territory_code = lang_obj.territory

                if not territory_code:
                    # If not, maximize to find the most likely territory
                    # e.g., 'en' -> 'en-US' (territory 'US')
                    # e.g., 'pt' -> 'pt-BR' (territory 'BR')
                    maximized_lang = lang_obj.maximize()
                    territory_code = maximized_lang.territory

                if territory_code:
                    country_code = str(territory_code).lower()
                    flag_url = f"https://flagcdn.com/20x15/{country_code}.png"
                else:
                    # Warning if no territory could be found
                    print(f"Warning: Could not find a likely country for '{lang_name}'.")

            except Exception as e:
                print(f"Error processing language '{lang_name}': {e}")
                display_name = lang_name.capitalize()

            if display_name == 'Und':
                display_name = 'Undetermined'

            line_parts = []
            if flag_url:
                line_parts.append(f"[img]{flag_url}[/img]")

            line_parts.append(display_name)

            if channels_raw:
                line_parts.append(channels_raw)

            codec_bitrate_parts = []
            if codec_raw:
                codec_bitrate_parts.append(codec_raw)
            if bitrate_raw:
                codec_bitrate_parts.append(f"à {bitrate_raw}")

            if codec_bitrate_parts:
                line_parts.append(f"| {' '.join(codec_bitrate_parts)}")

            desc.append(" ".join(line_parts))

    def _desc_bitrate(self, meta):
        bitrate = ''
        if meta.get('is_disc') == "BDMV":
            disc = meta["discs"][0]
            video_info = disc.get("bdinfo", {}).get("video", [])
            first_video = video_info[0] if video_info else {}
            bitrate = first_video.get("bitrate", "").replace("kbps", "").strip()
        else:
            track_list = meta.get("mediainfo", {}).get("media", {}).get("track", [])
            general_info = next((t for t in track_list if t.get("@type") == "General"), {})
            bitrate_bps = general_info.get("OverallBitRate")
            if bitrate_bps:
                try:
                    bitrate = int(bitrate_bps) // 1000
                except ValueError:
                    pass
        return bitrate

    async def _desc_quality(self, meta):
        quality_names = {
            1: "BDrip/BRrip",
            2: "Bluray 4K",
            3: "Bluray [Full]",
            4: "Bluray [Remux]",
            5: "DVD-R 5",
            6: "DVD-R 9",
            7: "DVDrip",
            8: "HDrip 1080",
            9: "HDrip 4k",
            10: "HDrip 720",
            11: "TVrip",
            12: "TVripHD 1080",
            13: "TVripHD 4k",
            14: "TVripHD 720",
            15: "VCD/SVCD/VHSrip",
            16: "Web-Dl",
            17: "Web-Dl 1080",
            18: "Web-Dl 4K",
            19: "Web-Dl 720",
            20: "WEBrip",
            21: "WEBrip 1080",
            22: "WEBrip 4K",
            23: "WEBrip 720"
        }
        quality_id = await self.get_quality(meta)
        quality_name = quality_names.get(quality_id, "Unknown")
        return quality_name

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
        await self.load_localized_data(meta)
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

    def _desc_ratings(self, rating):
        r_0 = "https://zupimages.net/up/21/02/8ysk.png"
        r_0_5 = "https://zupimages.net/up/21/02/3sol.png"
        r_1 = "https://zupimages.net/up/21/02/40xt.png"
        r_1_5 = "https://zupimages.net/up/21/02/oeyu.png"
        r_2 = "https://zupimages.net/up/21/02/7d9t.png"
        r_2_5 = "https://zupimages.net/up/21/02/og43.png"
        r_3 = "https://zupimages.net/up/21/02/fi3f.png"
        r_3_5 = "https://zupimages.net/up/21/02/g8lz.png"
        r_4 = "https://zupimages.net/up/21/02/xro7.png"
        r_4_5 = "https://zupimages.net/up/21/02/x4pr.png"
        r_5 = "https://zupimages.net/up/21/02/zxn3.png"
        if rating == 0.0:
            image = r_0
        elif rating <= 0.5:
            image = r_0_5
        elif rating <= 1.0:
            image = r_1
        elif rating <= 1.5:
            image = r_1_5
        elif rating <= 2.0:
            image = r_2
        elif rating <= 2.5:
            image = r_2_5
        elif rating <= 3.0:
            image = r_3
        elif rating <= 3.5:
            image = r_3_5
        elif rating <= 4.0:
            image = r_4
        elif rating <= 4.5:
            image = r_4_5
        else:
            image = r_5

        return image
