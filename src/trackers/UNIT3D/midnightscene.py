# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.languages import languages_manager
from src.meta import Meta
from src.release_name import NameContext, NameRule, NameSelector, TrackerNameProfile, template
from src.trackers.common import Common
from src.trackers.naming import midnight_scene_name
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class MidnightScene(UNIT3D):
    """
    MidnightScene is a Private Torrent Tracker for MOVIES / TV / GENERAL
    """

    tracker = "MIDNIGHTSCENE"
    name_profile = TrackerNameProfile(
        rules=(
            NameRule(NameSelector(category="MUSIC"), template("music_title", "music_year", "catalogue_edition", "media_format")),
            NameRule(NameSelector(), template("base_name")),
        ),
        transforms=(midnight_scene_name,),
    )

    async def get_name_overrides(self, context: NameContext) -> dict[str, str]:
        meta = context.meta
        if meta.category == "MUSIC":
            if meta.scene:
                scene = str(meta.scene_name or meta.basename_no_ext or meta.name or "").strip()
                if scene:
                    return {"music_title": scene.replace("_", " ")}
            release = meta.music_release if isinstance(meta.music_release, dict) else {}
            fields = release.get("fields", {}) if isinstance(release.get("fields"), dict) else {}

            def release_field(name: str, fallback: Any = "") -> str:
                value = fields.get(name, {}) if isinstance(fields.get(name), dict) else {}
                return str(value.get("value", fallback) or "").strip()

            artist = release_field("artist", meta.artist)
            title = release_field("album", meta.title)
            year = release_field("release_year", release_field("year", meta.year))
            catalogue = release_field("release_catalogue_number", release_field("catalogue_number", meta.music_catalogue_number))
            edition = release_field("edition", meta.manual_edition or meta.edition)
            media = release_field("media", meta.source)
            format_name = release_field("format", meta.format or meta.type).upper()
            catalogue_edition = " - ".join(part for part in (catalogue, edition) if part)
            media_format = " - ".join(part for part in (media, format_name) if part)
            return {
                "music_title": " - ".join(part for part in (artist, title) if part),
                "music_year": f"({year})" if year else "",
                "catalogue_edition": f"[{catalogue_edition}]" if catalogue_edition else "",
                "media_format": f"[{media_format}]" if media_format else "",
            }
        if not meta.language_checked:
            await languages_manager.process_desc_language(meta, tracker=self.tracker)
        languages = [] if not meta.audio_languages else meta.audio_languages
        return {"foreign_language": languages[0].upper()} if languages and not await languages_manager.has_english_language(languages) else {}

    display_name = "MidnightScene"
    allows_bloated_audio = True
    base_url = "https://midnightscene.cc"
    banned_groups = (
        "4K4U",
        "AROMA",
        "aXXo",
        "BONE",
        "BRrip",
        "CK4",
        "CM8",
        "core",
        "CrEwSaDe",
        "d3g",
        "DNL",
        "EMBER",
        "EVO",
        "FaNGDiNG0",
        "FGT",
        "FooKaS",
        "FRDS",
        "FROZEN",
        "GalaxyRG",
        "Grym",
        "GrymLegacy",
        "HD2DVD",
        "HDTime",
        "ION10",
        "Judas",
        "LAMA",
        "Leffe",
        "LycanHD",
        "MeGusta",
        "MezRips",
        "mHD",
        "msd",
        "mSD",
        "NeXus",
        "NhaNc3",
        "nHD",
        "nikt0",
        "nSD",
        "OFT",
        "OsC",
        "PRODJi",
        "ProRes",
        "PYC",
        "QxR",
        "RARBG",
        "RCDiVX",
        "RDN",
        "SAMPA",
        "SANTi",
        "Sicario",
        "Silence",
        "SM737",
        "STUTTERSHIT",
        "Tigole",
        "TSP",
        "TSPxL",
        "UTR",
        "ViSION",
        "WAF",
        "Will1869",
        "x0r",
        "YIFY",
        "YTS",
        "ZMNT",
    )
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    requests_url = f"{base_url}/api/requests/filter"
    supported_categories = ("TV", "MOVIE", "GAME", "MUSIC")
    tracker_urls = ("midnightscene.cc",)

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="MIDNIGHTSCENE")
        self.config: Config = config
        self.common = Common(config)

    async def get_category_id(
        self,
        meta: Meta,
        category: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        category_id = {
            "MOVIE": "1",
            "TV": "2",
            "MUSIC": "3",
            "GAME": "4",
        }
        if mapping_only:
            return category_id
        if reverse:
            return {v: k for k, v in category_id.items()}

        resolved_category = category if category is not None and category != "" else meta.category
        resolved_id = category_id.get(resolved_category, "0")
        return {"category_id": resolved_id}

    async def get_type_id(
        self,
        meta: Meta,
        type: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        nin_term = (bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()).upper()
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "MP3": "7",
            "FLAC": "8",
            "PC": "9",
            "PLAYSTATION": "10",
            f"{nin_term}": "11",
            "XBOX": "12",
            "DOCUMENTARY": "13",
            "TTRPG": "14",
            "3DPRINT": "15",
            "3D_PRINT": "15",
            "3D PRINT": "15",
            "OTHER": "16",
        }
        if mapping_only:
            return type_id
        if reverse:
            return {v: k for k, v in type_id.items()}

        if type:
            resolved_type = type.upper().strip().lstrip(".")
            if resolved_type in type_id:
                return {"type_id": type_id[resolved_type]}

        # Fallbacks
        genres = [g.lower() for g in meta.genres]
        keywords = [k.lower() for k in meta.keywords]

        if "documentary" in genres or "documentary" in keywords:
            val = "13"
        elif meta.category == "GAME":
            platform = meta.platform.lower()
            nin_term = bytes([110, 105, 110, 116, 101, 110, 100, 111]).decode()

            if any(word in platform for word in ["playstation", "ps5", "ps4", "ps3", "ps2", "ps1", "psp", "vita"]):
                val = "10"
            elif "xbox" in platform:
                val = "12"
            elif any(word in platform for word in [f"{nin_term}", "switch", "wii", "3ds", "nds", "ds"]):
                val = "11"
            else:
                val = "9"  # PC
        elif meta.category == "MUSIC":
            release = meta.music_release if isinstance(meta.music_release, dict) else {}
            fields = release.get("fields", {}) if isinstance(release.get("fields"), dict) else {}
            format_field = fields.get("format", {}) if isinstance(fields.get("format"), dict) else {}
            music_format = str(meta.format or format_field.get("value", "") or meta.type or "").upper().strip().lstrip(".")
            val = type_id.get(music_format, "0")
        elif "FLAC" in (meta.audio or "").upper():
            val = "8"
        elif "MP3" in (meta.audio or "").upper():
            val = "7"
        else:
            meta_type = (meta.type or "").upper().strip().lstrip(".")
            val = type_id.get(meta_type, "0")

        return {"type_id": val}
