# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.release_name import NameContext, NameRule, NameSelector, TrackerNameProfile, collapse_whitespace, template
from src.trackers.common import Common
from src.trackers.naming import append_context_value
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class Utopia(UNIT3D):
    """
    UTOPIA is a UKRAINIAN Private Tracker for HD MOVIES and TV
    """

    tracker = "UTOPIA"
    name_profile = TrackerNameProfile(
        rules=(
            NameRule(
                NameSelector(category="MOVIE"),
                template(
                    "title",
                    "alt_title",
                    "year",
                    "hybrid",
                    "repack",
                    "edition",
                    "region",
                    "three_d",
                    "uhd",
                    "effective_source",
                    "type_label",
                    "resolution",
                    "hdr",
                    "effective_codec",
                    "lossless_audio",
                ),
            ),
            NameRule(
                NameSelector(category="TV"),
                template(
                    "title",
                    "alt_title",
                    "season_episode",
                    "year",
                    "hybrid",
                    "edition",
                    "repack",
                    "region",
                    "three_d",
                    "uhd",
                    "effective_source",
                    "type_label",
                    "resolution",
                    "hdr",
                    "effective_codec",
                    "lossless_audio",
                ),
            ),
            NameRule(NameSelector(), template("base_name")),
        ),
        transforms=(collapse_whitespace, append_context_value("tag")),
    )

    async def get_name_overrides(self, context: NameContext) -> dict[str, str]:
        meta = context.meta
        release_type = str(meta.type).upper()
        audio = meta.audio if any(indicator in meta.audio for indicator in ("Atmos", "TrueHD", "DTS-HD MA", "DTS:X", "LPCM", "FLAC", "PCM")) else ""
        audio = " ".join(audio.replace("Dual-Audio", "").replace("Dubbed", "").split())
        source, type_label, codec = str(meta.source), "", meta.video_codec
        if release_type in ("REMUX", "ENCODE"):
            source, type_label = "", "BDRemux" if release_type == "REMUX" else "BDRip"
            codec = meta.video_encode if release_type == "ENCODE" else codec
        elif release_type in ("WEBDL", "WEBRIP"):
            source, type_label, codec = meta.service, "WEB-DL" if release_type == "WEBDL" else "WEBRip", meta.video_encode
        elif release_type == "HDTV":
            codec = meta.video_encode
        return {
            "alt_title": meta.aka.strip(),
            "year": str(meta.year) if meta.year is not None else "",
            "edition": meta.edition,
            "effective_source": source,
            "type_label": type_label,
            "effective_codec": codec,
            "lossless_audio": audio,
        }

    display_name = "UTOPIA"
    base_url = "https://utp.to"
    banned_groups = ()
    id_url = f"{base_url}/api/torrents/"
    upload_url = f"{base_url}/api/torrents/upload"
    search_url = f"{base_url}/api/torrents/filter"
    torrent_url = f"{base_url}/torrents/"
    supported_categories = ("TV", "MOVIE")
    allowed_bloated_audio_languages = ("uk", "en")

    def __init__(self, config: Config) -> None:
        super().__init__(config, tracker_name="UTOPIA")
        self.config = config
        self.common = Common(config)

    async def get_category_id(
        self,
        meta: Meta,
        category: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (category, reverse, mapping_only)
        category_name = meta.category
        category_id = {
            "MOVIE": "1",
            "TV": "2",
        }.get(category_name, "1")  # Default to MOVIE
        return {"category_id": category_id}

    async def get_resolution_id(
        self,
        meta: Meta,
        resolution: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (resolution, reverse, mapping_only)
        resolution_id = {
            "4320p": "1",
            "2160p": "2",
            "1080p": "3",
            "1080i": "4",
        }.get(meta.resolution, "11")  # Default to Other (11)
        return {"resolution_id": resolution_id}

    async def get_type_id(
        self,
        meta: Meta,
        type: str | None = None,
        reverse: bool = False,
        mapping_only: bool = False,
    ) -> dict[str, str]:
        _ = (type, reverse, mapping_only)
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
        }.get(str(meta.type).upper(), "3")  # Default to ENCODE
        return {"type_id": type_id}

    async def get_description(self, meta: Meta) -> dict[str, str]:
        """
        Override UNIT3D description to use img_url (medium) for display
        and raw_url (full image) as link target for utppm compatibility.

        Expected format: [url=FULL_IMAGE][img]MEDIUM_IMAGE[/img][/url]
        """
        from src.get_desc import DescriptionBuilder

        # Save original values and transform
        original_image_list = meta.image_list
        transformed_image_list: list[dict[str, Any]] = [
            {
                "web_url": img.get("raw_url", ""),  # Link goes to full image
                "raw_url": img.get("img_url", ""),  # Display shows medium image
                "img_url": img.get("img_url", ""),
            }
            for img in original_image_list
        ]

        # Also transform any new_images_* keys for packed content
        new_images_keys = [k for k in meta.to_dict() if k.startswith("new_images_")]
        original_new_images: dict[str, Any] = {}
        for key in new_images_keys:
            original_new_images[key] = meta[key]
            meta[key] = [
                {
                    "web_url": img.get("raw_url", ""),
                    "raw_url": img.get("img_url", ""),
                    "img_url": img.get("img_url", ""),
                }
                for img in meta[key]
            ]

        # Temporarily replace image_list
        meta.image_list = transformed_image_list

        try:
            builder = DescriptionBuilder(self.tracker, self.config)
            description = await builder.general_description_generator(
                meta,
                mediainfo=False,
                nfo=False,
            )
        finally:
            # Restore original values even if an error occurs
            meta.image_list = original_image_list
            for key, value in original_new_images.items():
                meta[key] = value

        return {"description": description}
