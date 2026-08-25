# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import asyncio
import json
import platform
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar, cast

import aiofiles
import cli_ui
import httpx
from bs4 import BeautifulSoup

from src.console import logger, prompt_in_thread
from src.cookie_auth import CookieAuthUploader, CookieValidator
from src.description_review import get_base_description
from src.get_desc import DescriptionBuilder
from src.languages import languages_manager
from src.meta import Meta
from src.tmdb import TmdbManager
from src.trackers.common import Common


class AmigosShare:
    """
    Amigos Share Club (ASC) is a BRAZILIAN Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    auth_type = "cookies"
    tracker = "AMIGOSSHARE"
    display_name = "AmigosShare"
    source_flag = "ASC"
    banned_groups: tuple[str, ...] = ()
    base_url = "https://cliente.amigos-share.club"
    torrent_url = "https://cliente.amigos-share.club/torrents-details.php?id="
    requests_url = f"{base_url}/pedidos.php"
    language_map: ClassVar[dict[str, str]] = {
        "bg": "15",
        "da": "12",
        "de": "3",
        "en": "1",
        "es": "6",
        "fi": "14",
        "fr": "2",
        "hi": "23",
        "it": "4",
        "ja": "5",
        "ko": "20",
        "nl": "17",
        "no": "16",
        "pl": "19",
        "pt": "8",
        "ru": "7",
        "sv": "13",
        "th": "21",
        "tr": "25",
        "zh": "10",
    }
    anime_language_map: ClassVar[dict[str, str]] = {
        "de": "3",
        "en": "4",
        "es": "1",
        "ja": "8",
        "ko": "11",
        "pt": "5",
        "ru": "2",
        "zh": "9",
    }
    supported_categories = ("TV", "MOVIE", "BOOK", "GAME")
    tracker_urls = ("amigos-share.club",)
    allows_bloated_audio = True
    tmdb_localization_requirements: ClassVar[dict[str, dict[str, str]]] = {
        "pt-BR": {
            "main": "credits,videos,content_ratings",
            "season": "credits",
            "episode": "credits",
        }
    }

    def __init__(self, config: dict[str, Any]) -> None:
        self.config = config
        self.season_tmdb_data: dict[str, Any] = {}
        self.episode_tmdb_data: dict[str, Any] = {}
        self.tmdb_manager = TmdbManager(config)
        self.common = Common(config)
        self.cookie_validator = CookieValidator(config)
        self.cookie_auth_uploader = CookieAuthUploader(config)
        self.layout = self.config["TRACKERS"][self.tracker].get("custom_layout", "2")
        self.session = httpx.AsyncClient(headers={"User-Agent": f"Upload-Assistant ({platform.system()} {platform.release()})"}, timeout=60.0)

    async def validate_credentials(self, meta: Meta) -> bool:
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar is not None:
            self.session.cookies = cast(Any, cookie_jar)
            return True
        return False

    async def load_localized_data(self, meta: Meta) -> None:
        if meta.category in ("MOVIE", "TV"):
            ptbr_data = meta.tmdb_localized_data.get("pt-BR")
            if not ptbr_data or not ptbr_data.get("main"):
                raise RuntimeError(f"{self.tracker}: Missing TMDB localized data (pt-BR).")

    async def get_container(self, meta: Meta) -> str | None:
        if meta.category == "BOOK":
            filelist = meta.filelist or []
            file_path = filelist[0] if filelist else (meta.path or "")
            ext = Path(file_path).suffix.lower().strip(".")
            ext_map = {
                "mp3": "31",
                "png": "36",
                "jpg": "37",
                "jpeg": "37",
                "pdf": "38",
                "doc": "39",
                "docx": "39",
                "epub": "52",
                "mobi": "54",
                "cbr": "55",
                "cbz": "55",
                "html": "58",
                "htm": "58",
            }
            return ext_map.get(ext, "17")

        if meta.is_disc == "BDMV":
            return "5"
        if meta.is_disc == "DVD":
            return "15"

        try:
            general_track = next(t for t in meta.mediainfo["media"]["track"] if t["@type"] == "General")
            file_extension = general_track.get("FileExtension", "").lower()
            if file_extension == "mkv":
                return "6"
            if file_extension == "mp4":
                return "8"
        except StopIteration, AttributeError, TypeError:
            return None
        return None

    async def get_type(self, meta: Meta) -> str | int:
        category = meta.category
        if category == "BOOK":
            if meta.audiobook:
                return "121"
            if meta.comic:
                return "112"
            if meta.manga:
                return "147"
            if meta.magazine:
                return "68"
            return "67"

        if category == "GAME":
            return self.get_game_type(meta)

        bd_disc_map = {"BD25": "40", "BD50": "41", "BD66": "42", "BD100": "43"}
        standard_map = {"ENCODE": "9", "REMUX": "39", "WEBDL": "23", "WEBRIP": "38", "BDRIP": "8", "DVDRIP": "3"}
        dvd_map = {"DVD5": "45", "DVD9": "46"}

        if meta.type == "DISC":
            if meta.is_disc == "HDDVD":
                return 15

            if meta.is_disc == "DVD":
                dvd_size = meta.dvd_size
                type_id = dvd_map[dvd_size]
                if type_id:
                    return type_id

            disctype = meta.disctype
            if disctype in bd_disc_map:
                return bd_disc_map[disctype]

            try:
                size_in_gb = meta.bdinfo["size"]
            except KeyError, IndexError, TypeError:
                size_in_gb = 0

            if size_in_gb > 66:
                return "43"  # BD100
            if size_in_gb > 50:
                return "42"  # BD66
            if size_in_gb > 25:
                return "41"  # BD50
            return "40"  # BD25
        return standard_map.get(meta.type or "", "0")

    async def get_languages(self, meta: Meta) -> dict[str, str] | None:
        if meta.anime:
            type_ = "116" if meta.category == "MOVIE" else "118"

            original_language = meta.original_language.lower() if meta.original_language else ""
            anime_language = self.anime_language_map.get(original_language, "6")

            lang = "8" if await self.get_audio(meta) in ("2", "3", "4") else self.language_map.get(original_language, "11")

            return {"type": type_, "idioma": anime_language, "lang": lang}

        return None

    async def get_audio(self, meta: Meta) -> str:
        subtitles = "1"
        dual_audio = "2"
        dubbed = "3"
        national = "4"
        original = "7"

        portuguese_languages = {"portuguese", "português", "pt"}

        has_pt_subs = (await self.get_subtitle(meta)) == "Embutida"

        meta_audio_languages = meta.audio_languages if meta.audio_languages else []
        audio_languages = {lang.lower() for lang in meta_audio_languages}
        has_pt_audio = any(lang in portuguese_languages for lang in audio_languages)

        original_lang = "" if not meta.original_language else meta.original_language.lower()
        is_original_pt = original_lang in portuguese_languages

        if has_pt_audio:
            if is_original_pt:
                return national
            if len(audio_languages - portuguese_languages) > 0:
                return dual_audio
            return dubbed
        if has_pt_subs:
            return subtitles
        return original

    async def get_subtitle(self, meta: Meta) -> str:
        portuguese_languages = {"portuguese", "português", "pt"}

        meta_subtitle_languages = meta.subtitle_languages if meta.subtitle_languages else []
        found_languages = {lang.lower() for lang in meta_subtitle_languages}

        if any(lang in portuguese_languages for lang in found_languages):
            return "Embutida"
        return "S_legenda"

    async def get_resolution(self, meta: Meta) -> dict[str, str]:
        width = str(meta.video_width) if meta.video_width is not None else ""
        height = str(meta.video_height) if meta.video_height is not None else ""
        return {"width": width, "height": height}

    async def get_video_codec(self, meta: Meta) -> str:
        codec_video_map = {
            "MPEG-4": "31",
            "AV1": "29",
            "AVC": "30",
            "DivX": "9",
            "H264": "17",
            "H265": "18",
            "HEVC": "27",
            "M4V": "20",
            "MPEG-1": "10",
            "MPEG-2": "11",
            "RMVB": "12",
            "VC-1": "21",
            "VP6": "22",
            "VP9": "23",
            "WMV": "13",
            "XviD": "15",
        }

        codec_video = None
        video_encode_raw = meta.video_encode

        if video_encode_raw and isinstance(video_encode_raw, str):
            video_encode_clean = video_encode_raw.strip().lower()
            if "264" in video_encode_clean:
                codec_video = "H264"
            elif "265" in video_encode_clean:
                codec_video = "HEVC"

        if not codec_video:
            codec_video = meta.video_codec

        if not isinstance(codec_video, str):
            codec_video = ""

        codec_id = codec_video_map.get(codec_video, "16")

        is_hdr = bool(meta.hdr)

        if is_hdr:
            if codec_video in ("HEVC", "H265"):
                return "28"
            if codec_video in ("AVC", "H264"):
                return "32"

        return codec_id

    async def get_audio_codec(self, meta: Meta) -> str:
        audio_type = (meta.audio or "").upper()

        codec_map = {
            "ATMOS": "43",
            "DTS:X": "25",
            "DTS-HD MA": "24",
            "DTS-HD": "23",
            "TRUEHD": "29",
            "DD+": "26",
            "DD": "11",
            "DTS": "12",
            "FLAC": "13",
            "LPCM": "21",
            "PCM": "28",
            "AAC": "10",
            "OPUS": "27",
            "MPEG": "17",
        }

        for key, code in codec_map.items():
            if key in audio_type:
                return code

        return "20"

    async def get_name(self, meta: Meta) -> str:
        if meta.category == "BOOK":
            author = meta.author.strip()
            title = self.common.portuguese_title_capitalization(meta.title)
            return f"{author} - {title}"

        if meta.category == "GAME":
            return self.get_game_name(meta)

        name = meta.title
        base_name = name
        original_name_title = (
            meta.tmdb_localized_data.get("pt-BR", {}).get("main", {}).get("original_name")
            or meta.tmdb_localized_data.get("pt-BR", {}).get("main", {}).get("original_title")
            or ""
        )

        if meta.category == "TV":
            tv_title_ptbr = meta.tmdb_localized_data.get("pt-BR", {}).get("main", {}).get("name")
            if tv_title_ptbr and tv_title_ptbr.lower() != name.lower() and (not original_name_title or tv_title_ptbr.lower() != original_name_title.lower()):
                base_name = f"{tv_title_ptbr} ({name})"

            return f"{base_name} - {meta.season}{meta.episode}"

        movie_title_ptbr = meta.tmdb_localized_data.get("pt-BR", {}).get("main", {}).get("title")
        if movie_title_ptbr and movie_title_ptbr.lower() != name.lower() and (not original_name_title or movie_title_ptbr.lower() != original_name_title.lower()):
            base_name = f"{movie_title_ptbr} ({name})"

        return f"{base_name}"

    def get_book_cover(self, meta: Meta) -> str:
        covers = meta.hosted_artwork
        if isinstance(covers, list) and len(covers) > 0:
            raw_url = covers[0].get("raw_url")
            if raw_url:
                return str(raw_url)

        # Fallback to poster URL if remote
        poster_url = meta.artwork_url
        if isinstance(poster_url, str) and poster_url.startswith(("http://", "https://")):
            return poster_url

        return ""

    async def build_book_description(self, meta: Meta) -> str:
        description_parts = ["[center]"]

        # Title & Author
        title = meta.title
        author = meta.author
        description_parts.append(f"[size=4][b]{title}[/b][/size]")
        if author:
            description_parts.append(f"[size=3]por {author}[/size]\n\n")

        description_parts.append("")

        # Cover
        cover_url = self.get_book_cover(meta)
        if cover_url:
            description_parts.append(await self.format_image(cover_url))
            description_parts.append("")

        description_parts.append("[/center]")

        # Book details using DescriptionBuilder
        builder = DescriptionBuilder(self.tracker, self.config, "pt-BR")
        book_section = builder._build_book_desc_section(meta, header_size=3, table=False)
        if book_section:
            description_parts.append(book_section)
            description_parts.append("")

        desc = get_base_description(meta).strip()
        if desc:
            # Strip standard formatting codes.
            desc = desc.replace("[user]", "").replace("[/user]", "")
            desc = desc.replace("[align=left]", "").replace("[/align]", "")
            desc = desc.replace("[align=right]", "").replace("[/align]", "")
            desc = desc.replace("[alert]", "").replace("[/alert]", "")
            desc = desc.replace("[note]", "").replace("[/note]", "")
            desc = desc.replace("[h1]", "[u][b]").replace("[/h1]", "[/b][/u]")
            desc = desc.replace("[h2]", "[u][b]").replace("[/h2]", "[/b][/u]")
            desc = desc.replace("[h3]", "[u][b]").replace("[/h3]", "[/b][/u]")
            desc = re.sub(r"(\[img=\d+)]", "[img]", desc, flags=re.IGNORECASE)
            description_parts.append(desc)
            description_parts.append("")

        custom_description_header = self.config["DEFAULT"].get("custom_description_header", "")
        if custom_description_header:
            description_parts.append(custom_description_header + "\n")

        description_parts.append(f"\n[center][url=https://github.com/wastaken7/Upload-Assistant]Compartilhado com {meta.ua_name} {meta.current_version} (fork)[/url][/center]")

        final_desc_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
        async with aiofiles.open(final_desc_path, "w", encoding="utf-8") as descfile:
            final_description = "\n".join(filter(None, description_parts))
            await descfile.write(final_description)

        return final_description

    async def build_description(self, meta: Meta) -> str:
        if meta.category == "BOOK":
            return await self.build_book_description(meta)

        if meta.category == "GAME":
            return await self.build_game_description(meta)

        user_layout = await self.fetch_layout_data(meta)
        fileinfo_dump = await self.media_info(meta)

        if not user_layout:
            return "[center]Erro: Não foi possível carregar o layout da descrição.[/center]"

        layout_image = {k: v for k, v in user_layout.items() if k.startswith("BARRINHA_")}
        description_parts = ["[center]"]

        async def append_section(key: str, content: str | None) -> None:
            if content and (img := layout_image.get(key)):
                description_parts.append(f"\n{await self.format_image(img)}")
                description_parts.append(f"\n{content}\n")

        # Title
        description_parts.extend([await self.format_image(layout_image.get(f"BARRINHA_CUSTOM_T_{i}")) for i in range(1, 4)])
        description_parts.append(f"\n{await self.format_image(layout_image.get('BARRINHA_APRESENTA'))}\n")
        description_parts.append(f"\n[size=3]{await self.get_name(meta)}[/size]\n")

        # Poster
        localized_tmdb = dict(meta.tmdb_localized_data.get("pt-BR", {}))
        season_tmdb = dict(localized_tmdb.get("season", {})) or {}
        main_tmdb = dict(localized_tmdb.get("main", {})) or {}
        episode_tmdb = dict(localized_tmdb.get("episode", {})) or {}
        poster_path = season_tmdb.get("poster_path") or main_tmdb.get("poster_path") or meta.tmdb_poster_path
        poster = f"https://image.tmdb.org/t/p/w500{poster_path}" if poster_path else ""
        await append_section("BARRINHA_CAPA", await self.format_image(poster))

        # Overview
        overview: str = season_tmdb.get("overview", "") or main_tmdb.get("overview", "")
        if not overview:
            if meta.unattended and not meta.unattended_confirm:
                logger.info(f"{self.tracker}: [yellow]Sinopse não encontrada no TMDb em modo unattended. Pulando upload para {self.tracker}.[/yellow]")
                meta.skipping = f"{self.tracker}"
                return ""
            user_input_raw = await prompt_in_thread(cli_ui.ask_string, f"{self.tracker}: Sinopse não encontrada no TMDb. Por favor, insira manualmente.")
            user_input = (user_input_raw or "").strip()
            overview = user_input or "Sinopse não encontrada."
        await append_section("BARRINHA_SINOPSE", overview)

        # Episode
        if meta.category == "TV" and episode_tmdb:
            episode_name = episode_tmdb.get("name")
            episode_overview = episode_tmdb.get("overview")
            still_path = episode_tmdb.get("still_path")

            if episode_name and episode_overview and still_path:
                still_url = f"https://image.tmdb.org/t/p/w300{still_path}"
                description_parts.append(f"\n[size=4][b]Episódio:[/b] {episode_name}[/size]\n")
                description_parts.append(f"\n{await self.format_image(still_url)}\n\n{episode_overview}\n")

        # Technical Sheet
        if main_tmdb:
            runtime = episode_tmdb.get("runtime") or main_tmdb.get("runtime") or meta.runtime
            formatted_runtime = None
            if runtime:
                h, m = divmod(runtime, 60)
                formatted_runtime = f"{h} hora{'s' if h > 1 else ''} e {m:02d} minutos" if h > 0 else f"{m:02d} minutos"

            release_date = episode_tmdb.get("air_date") or season_tmdb.get("air_date") if meta.category != "MOVIE" else main_tmdb.get("release_date")

            sheet_items = [
                f"Duração: {formatted_runtime}" if formatted_runtime else None,
                f"País de Origem: {', '.join(c['name'] for c in main_tmdb.get('production_countries', []))}" if main_tmdb.get("production_countries") else None,
                f"Gêneros: {', '.join(g['name'] for g in main_tmdb.get('genres', []))}" if main_tmdb.get("genres") else None,
                f"Data de Lançamento: {await self.format_date(release_date)}" if release_date else None,
                f"Site: [url={main_tmdb.get('homepage')}]Clique aqui[/url]" if main_tmdb.get("homepage") else None,
            ]
            await append_section("BARRINHA_FICHA_TECNICA", "\n".join(filter(None, sheet_items)))

        # Production Companies
        if main_tmdb and main_tmdb.get("production_companies"):
            prod_parts = ["[size=4][b]Produtoras[/b][/size]"]
            for p in main_tmdb.get("production_companies", []):
                logo_path = p.get("logo_path")
                logo = await self.format_image(f"https://image.tmdb.org/t/p/w45{logo_path}") if logo_path else ""

                prod_parts.append(f"{logo}[size=2] - [b]{p.get('name', '')}[/b][/size]" if logo else f"[size=2][b]{p.get('name', '')}[/b][/size]")
            description_parts.append("\n" + "\n".join(prod_parts) + "\n")

        # Cast
        if meta.category == "MOVIE":
            main_credits = cast(dict[str, Any], main_tmdb.get("credits") or {})
            cast_data = cast(list[dict[str, Any]], main_credits.get("cast", []))
        elif meta.tv_pack:
            season_credits = cast(dict[str, Any], season_tmdb.get("credits") or {})
            cast_data = cast(list[dict[str, Any]], season_credits.get("cast", []))
        else:
            episode_credits = cast(dict[str, Any], episode_tmdb.get("credits") or {})
            cast_data = cast(list[dict[str, Any]], episode_credits.get("cast", []))
        await append_section("BARRINHA_ELENCO", await self.build_cast_bbcode(cast_data))

        # Seasons
        if meta.category == "TV" and main_tmdb and main_tmdb.get("seasons"):
            seasons_content: list[str] = []
            for seasons in main_tmdb.get("seasons", []):
                season_name = seasons.get("name", f"Temporada {seasons.get('season_number')}").strip()
                poster_temp = await self.format_image(f"https://image.tmdb.org/t/p/w185{seasons.get('poster_path')}") if seasons.get("poster_path") else ""
                overview_temp = f"\n\nSinopse:\n{seasons.get('overview')}" if seasons.get("overview") else ""

                inner_content_parts: list[str] = []
                air_date = seasons.get("air_date")
                if air_date:
                    inner_content_parts.append(f"Data: {await self.format_date(air_date)}")

                episode_count = seasons.get("episode_count")
                if episode_count is not None:
                    inner_content_parts.append(f"Episódios: {episode_count}")

                inner_content_parts.append(poster_temp)
                inner_content_parts.append(overview_temp)

                inner_content = "\n".join(inner_content_parts)
                seasons_content.append(f"\n[spoiler={season_name}]{inner_content}[/spoiler]\n")
            await append_section("BARRINHA_EPISODIOS", "".join(seasons_content))

        # Ratings
        ratings_list = cast(list[dict[str, Any]], user_layout.get("Ratings", []))
        if not ratings_list and (imdb_rating := meta.imdb_info.get("rating")):
            ratings_list.append({"Source": "Internet Movie Database", "Value": f"{imdb_rating}/10"})
        if main_tmdb and (tmdb_rating := main_tmdb.get("vote_average")) and not any(r.get("Source") == "TMDb" for r in ratings_list):
            ratings_list.append({"Source": "TMDb", "Value": f"{tmdb_rating:.1f}/10"})

        criticas_key = "BARRINHA_INFORMACOES" if meta.category == "MOVIE" and "BARRINHA_INFORMACOES" in layout_image else "BARRINHA_CRITICAS"
        await append_section(criticas_key, await self.build_ratings_bbcode(meta, ratings_list))

        # MediaInfo/BDinfo
        if fileinfo_dump:
            description_parts.append(f"\n[spoiler=Informações do Arquivo]\n[left][font=Courier New]{fileinfo_dump}[/font][/left][/spoiler]\n")

        # Custom Bar
        description_parts.extend([await self.format_image(layout_image.get(f"BARRINHA_CUSTOM_B_{i}")) for i in range(1, 4)])
        description_parts.append("[/center]")

        desc = get_base_description(meta).strip()
        if desc:
            desc = desc.replace("[user]", "").replace("[/user]", "")
            desc = desc.replace("[align=left]", "").replace("[/align]", "")
            desc = desc.replace("[align=right]", "").replace("[/align]", "")
            desc = desc.replace("[alert]", "").replace("[/alert]", "")
            desc = desc.replace("[note]", "").replace("[/note]", "")
            desc = desc.replace("[h1]", "[u][b]").replace("[/h1]", "[/b][/u]")
            desc = desc.replace("[h2]", "[u][b]").replace("[/h2]", "[/b][/u]")
            desc = desc.replace("[h3]", "[u][b]").replace("[/h3]", "[/b][/u]")
            desc = re.sub(r"(\[img=\d+)]", "[img]", desc, flags=re.IGNORECASE)
            description_parts.append(desc)

        custom_description_header = self.config["DEFAULT"].get("custom_description_header", "")
        if custom_description_header:
            description_parts.append(custom_description_header + "\n")

        description_parts.append(f"[center][url=https://github.com/wastaken7/Upload-Assistant]Compartilhado com {meta.ua_name} {meta.current_version} (fork)[/url][/center]")

        final_desc_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
        async with aiofiles.open(final_desc_path, "w", encoding="utf-8") as descfile:
            final_description = "\n".join(filter(None, description_parts))
            await descfile.write(final_description)

        return final_description

    async def get_trailer(self, meta: Meta) -> str:
        video_results = meta.tmdb_localized_data.get("pt-BR", {}).get("main", {}).get("videos", {}).get("results", [])
        youtube_code = video_results[-1].get("key", "") if video_results else ""
        return f"http://www.youtube.com/watch?v={youtube_code}" if youtube_code else meta.youtube or ""

    async def get_tags(self, meta: Meta) -> str:
        tags = ", ".join(
            g.get("name", "") for g in meta.tmdb_localized_data.get("pt-BR", {}).get("main", {}).get("genres", []) if isinstance(g.get("name"), str) and g.get("name").strip()
        )

        if not tags:
            if not meta.genre and meta.unattended and not meta.unattended_confirm:
                logger.info(f"{self.tracker}: [yellow]Gêneros não encontrados em modo unattended. Pulando upload para {self.tracker}.[/yellow]")
                meta.skipping = f"{self.tracker}"
                return ""
            tags_raw = meta.genre or await prompt_in_thread(cli_ui.ask_string, f"Digite os gêneros (no formato do {self.tracker}): ")
            tags = (tags_raw or "").strip()

        return tags

    async def _fetch_file_info(self, torrent_id: str, torrent_link: str, size: str) -> dict[str, str]:
        """
        Helper function to fetch file info for a single release in parallel.
        """
        file_page_url = f"{self.base_url}/torrents-arquivos.php?id={torrent_id}"
        filename = "N/A"

        try:
            file_page_response = await self.session.get(file_page_url, timeout=15)
            file_page_response.raise_for_status()
            file_page_soup = BeautifulSoup(file_page_response.text, "html.parser")
            file_li_tag = file_page_soup.find("li", class_="list-group-item")

            if file_li_tag and file_li_tag.contents:
                first_content = file_li_tag.contents[0]
                filename = first_content.strip() if isinstance(first_content, str) else first_content.get_text(strip=True)

        except Exception as e:
            logger.info(f"{self.tracker}: [bold red]Falha ao obter nome do arquivo para ID {torrent_id}: {e}[/bold red]")

        return {"name": filename, "size": size, "link": torrent_link}

    def get_game_name(self, meta: Meta) -> str:
        """Build the torrent name for GAME category."""
        tag = meta.tag
        if tag:
            tag = tag.lstrip("-")

        name = f"{meta.title} - [{tag}]"
        return re.sub(r"\s{2,}", " ", name).strip()

    def get_game_type(self, meta: Meta) -> str:
        """Map meta.platform to AMIGOSSHARE game category (type field) value."""
        platform_map: dict[str, str] = {
            "ANDROID": "57",
            "DREAMCAST": "52",
            "EMULATOR": "109",
            "DS": "58",
            "NDS": "58",
            "SWITCH": "110",
            "PC": "47",
            "MAC": "48",
            "PS1": "49",
            "PS2": "50",
            "PS3": "51",
            "PS4": "79",
            "PSP": "82",
            "WII": "55",
            "X360": "54",
            "XBOX": "56",
            "XONE": "78",
        }
        platform = meta.platform.upper().strip()
        return platform_map.get(platform, "47")  # Default to PC

    def get_game_genre(self, meta: Meta) -> str:
        """Map IGDB genres to AMIGOSSHARE genero field value."""
        genre_map: dict[str, str] = {
            "action": "1",
            "hack and slash": "1",
            "hack and slash/beat 'em up": "1",
            "adventure": "2",
            "point-and-click": "2",
            "visual novel": "2",
            "arcade": "3",
            "racing": "14",
            "driving": "14",
            "sport": "15",
            "sports": "15",
            "strategy": "22",
            "real time strategy": "22",
            "rts": "22",
            "turn-based strategy": "22",
            "tactical": "22",
            "shooter": "21",
            "fps": "21",
            "fighting": "13",
            "music": "16",
            "rhythm": "16",
            "puzzle": "18",
            "rpg": "12",
            "role-playing": "12",
            "role-playing (rpg)": "12",
            "simulation": "5",
            "simulator": "5",
            "board": "7",
            "board game": "7",
            "platform": "1",
            "platformer": "1",
        }
        genres_list = meta.genres or meta.keywords or []
        for genre in genres_list:
            genre_clean = genre.strip().lower()
            if genre_clean in genre_map:
                return genre_map[genre_clean]

        return "0"

    def get_game_idioma(self, meta: Meta) -> str:
        """Map game languages to AMIGOSSHARE idioma field value."""
        language_map: dict[str, str] = {
            "german": "3",
            "chinese": "9",
            "spanish": "1",
            "english": "4",
            "japanese": "8",
            "portuguese": "5",
            "russian": "2",
        }
        languages = meta.languages
        lang_list = list(languages.keys()) if isinstance(languages, dict) else []
        if not lang_list:
            return "6"  # Outros

        lang_lower = [ln.lower() for ln in lang_list]
        has_pt = any("portuguese" in ln or "português" in ln for ln in lang_lower)

        if has_pt and len(lang_list) > 1:
            return "7"  # Multilinguagem

        for ln in lang_lower:
            for key, val in language_map.items():
                if key in ln:
                    return val

        return "6"  # Outros

    async def build_game_description(self, meta: Meta) -> str:
        """Build GAME description using only the _build_game_desc_section block."""
        builder = DescriptionBuilder(self.tracker, self.config, "pt-BR")
        desc_parts: list[str] = []

        game_section = builder._build_game_desc_section(meta, header_size=5, table=False)
        if game_section:
            desc_parts.append(game_section)

        desc_parts.append(await builder.get_user_description(meta))
        desc_parts.append(f"[center][url=https://github.com/wastaken7/Upload-Assistant]Compartilhado com {meta.ua_name} {meta.current_version} (fork)[/url][/center]")

        final_description = "\n\n".join(part for part in desc_parts if part.strip())

        final_desc_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/[{self.tracker}]DESCRIPTION.txt"
        async with aiofiles.open(final_desc_path, "w", encoding="utf-8") as descfile:
            await descfile.write(final_description)

        return final_description

    async def get_additional_checks(self, meta: Meta) -> bool:
        if meta.category == "BOOK" and meta.source_size <= 1024 * 1024:
            logger.info(f"{self.tracker}: [bold red]Ignorando upload na categoria BOOK devido ao tamanho ser menor ou igual a 1MB.[/bold red]")
            return False

        if meta.category in ("BOOK", "GAME"):
            return True

        if not meta.imdb_id and not meta.anime:
            logger.info(f"{self.tracker}: [bold red]Ignorando upload devido à ausência de IMDb.[/bold red]")
            return False

        if meta.category in ("MOVIE", "TV"):
            return await self.common.check_portuguese_video_requirements(meta, self.tracker)

        return True

    async def search_existing(self, meta: Meta) -> list[dict[str, str]]:
        found_items: list[dict[str, str]] = []
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar is not None:
            self.session.cookies = cast(Any, cookie_jar)

        if meta.category == "BOOK":
            search_name = f"{meta.author} {meta.title}".strip()
            search_query = search_name.replace(" ", "+")
            search_url = f"{self.base_url}/torrents-search.php?search={search_query}"

        elif meta.category == "GAME":
            search_name = meta.title
            search_query = search_name.replace(" ", "+")
            search_url = f"{self.base_url}/torrents-search.php?search={search_query}&cat={self.get_game_type(meta)}"

        elif meta.anime:
            await self.load_localized_data(meta)
            search_name = await self.get_name(meta)
            search_query = search_name.replace(" ", "+")
            search_url = f"{self.base_url}/torrents-search.php?search={search_query}"

        elif meta.category in ("MOVIE", "TV"):
            imdb = meta.imdb_info.get("imdbID") or f"tt{str(meta.imdb_id).zfill(7)}"
            if meta.category == "MOVIE":
                search_url = f"{self.base_url}/busca-filmes.php?search=&imdb={imdb}"

            else:
                search_url = f"{self.base_url}/busca-series.php?search={meta.season}{meta.episode}&imdb={imdb}"

        else:
            return found_items

        response = await self.session.get(search_url, timeout=30)
        if "Esqueceu sua senha" in response.text or "login.php" in str(response.url) or "login.php" in response.text:
            await self.cookie_validator.handle_validation_failure(meta, self.tracker, response.text)
            meta.skipping = f"{self.tracker}"
            return found_items
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "html.parser")
        releases = soup.find_all("li", class_="list-group-item dark-gray")

        if not releases:
            return found_items

        name_search_tasks: list[asyncio.Task[dict[str, str]]] = []

        for release in releases:

            def _has_details_link(href: str | None) -> bool:
                return bool(href and "torrents-details.php?id=" in href)

            details_link_tag = release.find("a", href=_has_details_link)
            torrent_link_value = details_link_tag.get("href") if details_link_tag else None
            torrent_link = torrent_link_value if isinstance(torrent_link_value, str) else ""

            def _has_size_text(text: str | None) -> bool:
                return bool(text and ("GB" in text.upper() or "MB" in text.upper()))

            size_tag = release.find("span", text=_has_size_text, class_="badge-info")
            size = size_tag.get_text(strip=True).strip() if size_tag else ""

            badges = release.find_all("span", class_="badge")
            disc_types = ["BD25", "BD50", "BD66", "BD100", "DVD5", "DVD9"]
            is_disc = any(badge.text.strip().upper() in disc_types for badge in badges)

            if is_disc:
                name, year, resolution, disk_type, video_codec, audio_codec = meta.title, "N/A", "N/A", "N/A", "N/A", "N/A"
                video_codec_terms = ["MPEG-4", "AV1", "AVC", "H264", "H265", "HEVC", "MPEG-1", "MPEG-2", "VC-1", "VP6", "VP9"]
                audio_codec_terms = ["DTS", "AC3", "DDP", "E-AC-3", "TRUEHD", "ATMOS", "LPCM", "AAC", "FLAC"]

                for badge in badges:
                    badge_text = badge.text.strip()
                    badge_text_upper = badge_text.upper()

                    if badge_text.isdigit() and len(badge_text) == 4:
                        year = badge_text
                    elif badge_text_upper in ["4K", "2160P", "1080P", "720P", "480P"]:
                        resolution = "2160p" if badge_text_upper == "4K" else badge_text
                    elif any(term in badge_text_upper for term in video_codec_terms):
                        video_codec = badge_text
                    elif any(term in badge_text_upper for term in audio_codec_terms):
                        audio_codec = badge_text
                    elif any(term in badge_text_upper for term in disc_types):
                        disk_type = badge_text

                name = f"{name} {year} {resolution} {disk_type} {video_codec} {audio_codec}"
                dupe_entry = {"name": name, "size": size, "link": torrent_link}

                found_items.append(dupe_entry)

            else:
                if not details_link_tag:
                    continue

                href_value = details_link_tag.get("href")
                if not isinstance(href_value, str):
                    continue

                if meta.category == "GAME":
                    title_tag = release.select_one(".tooltips p a")
                    game_title = title_tag.get_text(strip=True) if title_tag else "N/A"
                    found_items.append(
                        {
                            "name": game_title,
                            "size": size,
                            "link": torrent_link,
                        }
                    )
                else:
                    torrent_id = href_value.split("id=")[-1]
                    name_search_tasks.append(asyncio.create_task(self._fetch_file_info(torrent_id, torrent_link, size)))

        if name_search_tasks:
            parallel_results = await asyncio.gather(*name_search_tasks)
            found_items.extend(parallel_results)

        return found_items

    async def get_upload_url(self, meta: Meta) -> str:
        if meta.category == "BOOK":
            return f"{self.base_url}/enviar-ebook.php"
        if meta.category == "GAME":
            return f"{self.base_url}/enviar-jogos.php"
        if meta.anime:
            return f"{self.base_url}/enviar-anime.php"
        if meta.category == "MOVIE":
            return f"{self.base_url}/enviar-filme.php"
        return f"{self.base_url}/enviar-series.php"

    async def format_image(self, url: str | None) -> str:
        return f"[img]{url}[/img]" if isinstance(url, str) and url else ""

    async def format_date(self, date_str: str | None) -> str:
        if not date_str or date_str == "N/A":
            return "N/A"

        def _try_format(fmt: str) -> str | None:
            try:
                return datetime.strptime(date_str, fmt).replace(tzinfo=UTC).strftime("%d/%m/%Y")
            except ValueError, TypeError:
                return None

        for fmt in ("%Y-%m-%d", "%d %b %Y"):
            formatted = _try_format(fmt)
            if formatted:
                return formatted
        return date_str

    async def media_info(self, meta: Meta) -> str | None:
        if meta.is_disc == "BDMV":
            summary_path = f"{meta.base_dir}{'/' + 'tmp' + '/'}{meta.uuid}/BD_SUMMARY_00.txt"
            if Path(summary_path).exists():
                async with aiofiles.open(summary_path, encoding="utf-8") as f:
                    return await f.read()
        if not meta.is_disc:
            filelist = cast(list[str], meta.filelist or [])
            video_file = filelist[0] if filelist else (meta.path or "")
            return DescriptionBuilder.format_short_mediainfo_json(meta.mediainfo, video_file) or None

        return None

    async def fetch_layout_data(self, meta: Meta) -> dict[str, Any]:
        url = f"{self.base_url}/search.php"
        cache_dir = Path(meta.base_dir) / "tmp"

        async def _fetch(payload: dict[str, Any]) -> dict[str, Any]:
            layout_dict: dict[str, Any] = {}
            cache_path = Path(cache_dir) / f"ASC_layout_cache_{self.layout}.json"

            if Path(cache_path).exists():
                try:
                    async with aiofiles.open(cache_path, encoding="utf-8") as f:
                        cache = await f.read()
                        return json.loads(cache)
                except OSError, json.JSONDecodeError:
                    logger.info(f"{self.tracker}: [yellow]Failed to read cached layout data.[/yellow]")

            try:
                response = await self.session.post(url, data=payload, timeout=20)
                response.raise_for_status()
                response_json = cast(dict[str, Any], response.json())
                layout_dict = response_json.get("ASC", {})

                if layout_dict:
                    try:
                        async with aiofiles.open(cache_path, "w", encoding="utf-8") as f:
                            await f.write(json.dumps(layout_dict))
                    except Exception as e:
                        logger.error(f"{self.tracker}: [red]Failed to cache layout data: {e}[/red]")

                return layout_dict
            except Exception:
                return {}

        # Primary attempt
        primary_payload: dict[str, Any] = {"imdb": meta.imdb_info.get("imdbID") or f"tt{str(meta.imdb_id).zfill(7)}", "layout": self.layout}
        layout_data = await _fetch(primary_payload)

        if layout_data:
            return layout_data

        # Fallback attempt
        fallback_payload: dict[str, Any] = {"imdb": "tt0013442", "layout": self.layout}
        return await _fetch(fallback_payload)

    async def build_ratings_bbcode(self, meta: Meta, ratings_list: list[dict[str, Any]]) -> str:
        if not ratings_list:
            return ""

        ratings_map = {
            "Internet Movie Database": "[img]https://i.postimg.cc/Pr8Gv4RQ/IMDB.png[/img]",
            "Rotten Tomatoes": "[img]https://i.postimg.cc/rppL76qC/rotten.png[/img]",
            "Metacritic": "[img]https://i.postimg.cc/SKkH5pNg/Metacritic45x45.png[/img]",
            "TMDb": "[img]https://i.postimg.cc/T13yyzyY/tmdb.png[/img]",
        }
        parts: list[str] = []
        for rating in ratings_list:
            source = rating.get("Source")
            if not isinstance(source, str):
                continue
            value = rating.get("Value", "").strip()
            img_tag = ratings_map.get(source)
            if not img_tag:
                continue

            if source == "Internet Movie Database":
                parts.append(
                    f"\n[url={meta.imdb_info.get('imdb_url', '') or f'https://www.imdb.com/title/{f"tt{str(meta.imdb_id).zfill(7)}"}'}]{img_tag}[/url]\n[b]{value}[/b]\n"
                )
            elif source == "TMDb" and meta.tmdb:
                parts.append(f"[url=https://www.themoviedb.org/{meta.category.lower()}/{meta.tmdb}]{img_tag}[/url]\n[b]{value}[/b]\n")
            else:
                parts.append(f"{img_tag}\n[b]{value}[/b]\n")
        return "\n".join(parts)

    async def build_cast_bbcode(self, cast_list: list[dict[str, Any]]) -> str:
        if not cast_list:
            return ""

        parts: list[str] = []
        for person in cast_list[:10]:
            profile_path = person.get("profile_path")
            profile_url = f"https://image.tmdb.org/t/p/w45{profile_path}" if profile_path else "https://i.imgur.com/eCCCtFA.png"
            tmdb_url = f"https://www.themoviedb.org/person/{person.get('id')}?language=pt-BR"
            img_tag = await self.format_image(profile_url)
            character_info = f"({person.get('name', '')}) como {person.get('character', '')}"
            parts.append(f"[url={tmdb_url}]{img_tag}[/url]\n[size=2][b]{character_info}[/b][/size]\n")
        return "".join(parts)

    async def get_requests(self, meta: Meta) -> bool | list[dict[str, str]]:
        if not self.config["DEFAULT"].get("search_requests", False) and not meta.search_requests:
            return False
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar is not None:
            self.session.cookies = cast(Any, cookie_jar)
        try:
            category = meta.category
            if category in ["BOOK", "GAME"]:
                category = await self.get_type(meta)
            elif meta.anime:
                if category == "TV":
                    category = 118
                if category == "MOVIE":
                    category = 116
            else:
                if category == "TV":
                    category = 120
                if category == "MOVIE":
                    category = 119

            query = meta.title
            search_url = f"{self.requests_url}?search={query}&category={category}"

            response = await self.session.get(search_url)
            response.raise_for_status()
            response_results_text = response.text

            soup = BeautifulSoup(response_results_text, "html.parser")

            request_rows = soup.select(".table-responsive table tr")

            results: list[dict[str, str]] = []
            for row in request_rows:
                all_tds = row.find_all("td")
                if not all_tds or len(all_tds) < 6:
                    continue

                info_cell = all_tds[1]
                link_element = info_cell.select_one('a[href*="pedidos.php?action=ver"]')
                if not link_element:
                    continue

                name = link_element.text.strip()
                link_value = link_element.get("href")
                link = str(link_value) if link_value is not None else ""

                reward_td = all_tds[4]
                reward = reward_td.text.strip()

                results.append(
                    {
                        "Name": name,
                        "Reward": reward,
                        "Link": link,
                    }
                )

            if results:
                message = f"\n{self.tracker}: [bold yellow]Seu upload pode atender o(s) seguinte(s) pedido(s), confira:[/bold yellow]\n\n"
                for r in results:
                    message += f"[bold green]Nome:[/bold green] {r['Name']}\n"
                    message += f"[bold green]Recompensa:[/bold green] {r['Reward']}\n"
                    message += f"[bold green]Link:[/bold green] {self.base_url}/{r['Link']}\n\n"
                logger.info(message)

            return results

        except Exception as e:
            logger.info(f"{self.tracker}: [bold red]Ocorreu um erro ao buscar pedido(s) no {self.tracker}: {e}[/bold red]")
            import traceback

            logger.info(traceback.format_exc())
            return []

    async def get_data(self, meta: Meta) -> dict[str, Any]:
        await self.load_localized_data(meta)  #  keep this line FIRST to ensure localized data is loaded before proceeding
        description = await self.build_description(meta)
        upload_type = await self.get_type(meta)

        data: dict[str, Any] = {
            "takeupload": "yes",
            "name": await self.get_name(meta),
            "descr": description,
            "ano": str(meta.year) if meta.year is not None else "",
        }

        if meta.category == "BOOK":
            if not meta.language_checked:
                await languages_manager.process_desc_language(meta, tracker=self.tracker)

            book_lang = (meta.book_language_iso or meta.book_language or "").lower()
            lang_code_map = {
                "chi": "9",
                "de": "3",
                "deu": "3",
                "en": "4",
                "eng": "4",
                "es": "1",
                "esp": "1",
                "ger": "3",
                "ja": "8",
                "jpn": "8",
                "ko": "11",
                "kor": "11",
                "por": "5",
                "pt": "5",
                "ru": "2",
                "rus": "2",
                "spa": "1",
                "zh": "9",
                "zho": "9",
            }
            idioma_val = lang_code_map.get(book_lang, "6")

            cover_url = self.get_book_cover(meta)

            data.update(
                {
                    "capa": cover_url,
                    "extencao": await self.get_container(meta),
                    "idioma": idioma_val,
                    "screens1": meta.author,
                    "screens2": cover_url,
                    "screens3": cover_url,
                    "type": upload_type,
                }
            )

            image_list = meta.image_list or []
            if len(image_list) > 0:
                data["screens2"] = image_list[0].get("raw_url") or ""
            if len(image_list) > 1:
                data["screens3"] = image_list[1].get("raw_url") or ""

            return data

        if meta.category == "GAME":
            data.update(
                {
                    "capa": meta.artwork_url,
                    "genero": self.get_game_genre(meta),
                    "idioma": self.get_game_idioma(meta),
                    "type": upload_type,
                }
            )

            # Screenshots
            image_list = meta.image_list or []
            for i, img in enumerate(image_list[:4]):
                raw_url = img.get("raw_url", "")
                if raw_url:
                    data[f"screens{i + 1}"] = raw_url

            return data

        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        resolution = await self.get_resolution(meta)

        data.update(
            {
                "altura": resolution["height"],
                "audio": await self.get_audio(meta),
                "capa": f"https://image.tmdb.org/t/p/w500{meta.tmdb_localized_data.get('pt-BR', {}).get('main', {}).get('poster_path') or meta.tmdb_poster_path}",
                "codecaudio": await self.get_audio_codec(meta),
                "codecvideo": await self.get_video_codec(meta),
                "extencao": await self.get_container(meta),
                "genre": await self.get_tags(meta),
                "imdb": meta.imdb_info.get("imdbID") or f"tt{str(meta.imdb_id).zfill(7)}",
                "lang": "1" if not meta.original_language else self.language_map.get(meta.original_language.lower(), "11"),
                "largura": resolution["width"],
                "layout": self.layout,
                "legenda": await self.get_subtitle(meta),
                "qualidade": upload_type,
                "tresd": "1" if meta.three_d else "2",
                "tube": await self.get_trailer(meta),
            }
        )

        if meta.anime:
            anime_info = await self.get_languages(meta)
            if anime_info:
                data.update(
                    {
                        "idioma": anime_info["idioma"],
                        "lang": anime_info["lang"],
                        "type": anime_info["type"],
                    }
                )

        # Screenshots
        image_list = meta.image_list or []
        for i, img in enumerate(image_list[:4]):
            data[f"screens{i + 1}"] = img.get("raw_url")

        return data

    async def upload(self, meta: Meta) -> bool:
        if getattr(meta, "skipping", None) == self.tracker:
            return False
        if meta.category == "BOOK" and meta.source_size <= 1024 * 1024:
            logger.info(f"{self.tracker}: [bold red]Ignorando upload na categoria BOOK devido ao tamanho ser menor ou igual a 1MB.[/bold red]")
            return False
        cookie_jar = await self.cookie_validator.load_session_cookies(meta, self.tracker)
        if cookie_jar is not None:
            self.session.cookies = cast(Any, cookie_jar)
        data = await self.get_data(meta)
        if getattr(meta, "skipping", None) == self.tracker:
            return False
        upload_url = await self.get_upload_url(meta)

        is_uploaded = await self.cookie_auth_uploader.handle_upload(
            meta=meta,
            tracker=self.tracker,
            source_flag=self.source_flag,
            torrent_url=self.torrent_url,
            data=data,
            torrent_field_name="torrent",
            upload_cookies=self.session.cookies,
            upload_url=upload_url,
            id_pattern=r"torrents-details\.php\?id=(\d+)",
            success_text="torrents-details.php?id=",
        )

        if not is_uploaded:
            return False

        # Approval
        should_approve = await self.get_approval(meta)
        if should_approve:
            await self.auto_approval(meta)

        # Internal
        if meta.tag and (
            self.config["TRACKERS"][self.tracker].get("internal", False) is True and meta.tag[1:] in self.config["TRACKERS"][self.tracker].get("internal_groups", [])
        ):
            await self.set_internal_flag(meta)

        return True

    async def auto_approval(self, meta: Meta) -> None:
        if meta.debug:
            logger.debug(f"{self.tracker}: Debug mode, skipping automatic approval.")
        else:
            torrent_id = meta.tracker_status[self.tracker]["torrent_id"]
            try:
                approval_url = f"{self.base_url}/uploader_app.php?id={torrent_id}"
                approval_response = await self.session.get(approval_url, timeout=30)
                approval_response.raise_for_status()
            except Exception as e:
                logger.info(f"{self.tracker}: [bold red]Error during automatic approval attempt: {e}[/bold red]")

    async def get_approval(self, meta: Meta) -> bool:
        if not self.config["TRACKERS"][self.tracker].get("uploader_status", False):
            return False

        if meta.modq:
            logger.info(f"{self.tracker}: Sending to the moderation queue.")
            return False

        return True

    async def set_internal_flag(self, meta: Meta) -> None:
        if meta.debug:
            logger.debug(f"{self.tracker}: [bold yellow]Debug mode, skipping setting internal flag.[/bold yellow]")
        else:
            data: dict[str, str] = {"id": meta.tracker_status[self.tracker]["torrent_id"], "internal": "yes"}

            try:
                response = await self.session.post(f"{self.base_url}/torrents-edit.php?action=doedit", data=data)
                response.raise_for_status()

            except Exception as e:
                logger.info(f"{self.tracker}: [bold red]Error setting internal flag: {e}[/bold red]")
                return
