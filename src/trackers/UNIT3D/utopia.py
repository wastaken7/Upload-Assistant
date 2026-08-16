# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
from typing import Any

from src.meta import Meta
from src.trackers.common import Common
from src.trackers.UNIT3D import UNIT3D

Config = dict[str, Any]


class Utopia(UNIT3D):
    """
    UTOPIA is a UKRAINIAN Private Tracker for HD MOVIES and TV
    """

    tracker = "UTOPIA"
    display_name = "Utopia"
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

    async def get_name(self, meta: Meta) -> dict[str, str]:
        """
        Build UTOPIA-compliant torrent name from meta components.
        https://utp.to/pages/33 - rules used for naming.
        https://github.com/maksii/UTOPIA-Upload-Assistant/blob/main/data/naming.json

        Expected naming as per rules
        Movie: Name AKA Original LOCALE Year Cut Ratio Hybrid REPACK PROPER RERip Edition Region 3D SOURCE TYPE Resolution HDR VCodec ACodec Channels Object-Tag
        TV:    Name AKA Original LOCALE S##E## Year Cut Ratio Hybrid REPACK PROPER RERip Edition Region 3D SOURCE TYPE Resolution HDR VCodec ACodec Channels Object-Tag

        """
        category = str(meta.category)
        release_type = str(meta.type).upper()

        # Common components
        title = meta.title
        aka = meta.aka.strip()
        year = str(meta.year) if meta.year is not None else ""
        three_d = meta.three_d
        uhd = meta.uhd
        edition = meta.edition
        hybrid = "Hybrid" if meta.webdv else ""
        repack = meta.repack
        resolution = meta.resolution
        hdr = meta.hdr
        service = meta.service
        audio_raw = meta.audio
        # Only include audio for Atmos or lossless codecs
        lossless_indicators = ["Atmos", "TrueHD", "DTS-HD MA", "DTS:X", "LPCM", "FLAC", "PCM"]
        if any(indicator in audio_raw for indicator in lossless_indicators):
            audio = audio_raw.replace("Dual-Audio", "").replace("Dubbed", "").strip()
            audio = " ".join(audio.split())
        else:
            audio = ""  # Don't include lossy audio (AAC, DD, DD+, etc.) in name
        video_codec = meta.video_codec
        video_encode = meta.video_encode
        tag = meta.tag
        region = meta.region if meta.region else ""
        season = meta.season
        episode = meta.episode

        source_tag = str(meta.source)
        type_tag = ""
        vcodec = video_codec  # Default for DISC/REMUX (AVC, HEVC)

        if release_type in ("REMUX", "ENCODE"):
            source_tag = ""  # BDRemux/BDRip replaces source
            type_tag = "BDRemux" if release_type == "REMUX" else "BDRip"
            if release_type == "ENCODE":
                vcodec = video_encode
        elif release_type in ("WEBDL", "WEBRIP"):
            source_tag = service  # Service (NF, AMZN, etc.) as source
            type_tag = "WEB-DL" if release_type == "WEBDL" else "WEBRip"
            vcodec = video_encode
        elif release_type == "HDTV":
            vcodec = video_encode
        # DISC: source_tag stays as meta.source (Blu-ray), three_d/uhd handled in template

        # Build name using single template per category
        if category == "MOVIE":
            name = f"{title} {aka} {year} {hybrid} {repack} {edition} {region} {three_d} {uhd} {source_tag} {type_tag} {resolution} {hdr} {vcodec} {audio}"
        elif category == "TV":
            name = f"{title} {aka} {season}{episode} {year} {hybrid} {edition} {repack} {region} {three_d} {uhd} {source_tag} {type_tag} {resolution} {hdr} {vcodec} {audio}"
        else:
            name = meta.name

        # Clean up multiple spaces and add tag
        name = " ".join(name.split())
        if tag:
            name = f"{name}{tag}"

        return {"name": name}
