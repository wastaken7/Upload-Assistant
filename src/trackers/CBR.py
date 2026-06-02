# Upload Assistant © 2025 Audionut & wastaken7 — Licensed under UAPL v1.0
import re
from typing import Any, Optional

from src.console import console
from src.trackers.COMMON import COMMON
from src.trackers.UNIT3D import UNIT3D


class CBR(UNIT3D):
    def __init__(self, config: dict[str, Any]):
        super().__init__(config, tracker_name='CBR')
        self.config = config
        self.common = COMMON(config)
        self.tracker = 'CBR'
        self.base_url = 'https://capybarabr.com'
        self.id_url = f'{self.base_url}/api/torrents/'
        self.upload_url = f'{self.base_url}/api/torrents/upload'
        self.search_url = f'{self.base_url}/api/torrents/filter'
        self.torrent_url = f'{self.base_url}/torrents/'
        self.requests_url = f'{self.base_url}/api/requests/filter'
        self.pending_url = f"{self.base_url}/api/torrents/pending"
        self.banned_groups = [
            "4K4U", "afm72", "Alcaide_Kira", "AROMA", "ASM", "Bandi", "BiTOR", "BLUDV", "Bluespots",
            "BOLS", "CaNNIBal", "Comando", "d3g", "DepraveD", "EMBER", "FGT", "FreetheFish", "Garshasp",
            "Ghost", "Grym", "HDS", "Hi10", "HiQVE", "Hiro360", "ImE", "ION10", "iVy", "Judas", "LAMA",
            "Langbard", "Lapumia", "LION", "MeGusta", "MONOLITH", "MRCS", "NaNi", "Natty", "nikt0",
            "OEPlus", "OFT", "OsC", "Panda", "PANDEMONiUM", "PHOCiS", "PiRaTeS", "PYC", "QxR", "r00t",
            "Ralphy", "RARBG", "RetroPeeps", "RZeroX", "S74Ll10n", "SAMPA", "Sicario", "SiCFoI", "Silence",
            "SkipTT", "SM737", "SPDVD", "STUTTERSHIT", "SWTYBLZ", "t3nzin", "TAoE", "TEKNO3D", "Telly", "TGx",
            "Tigole", "TSP", "TSPxL", "TWA", "UnKn0wn", "VXT", "Vyndros", "W32", "Will1869", "x0r", "YIFY", "YTS.MX", "YTS"
        ]

    async def get_category_id(
        self, meta: dict[str, Any], category: str = "", reverse: bool = False, mapping_only: bool = False
    ) -> dict[str, str]:
        category_id: dict[str, str] = {"MOVIE": "1", "TV": "2", "ANIMES": "4", "BOOK": "11"}

        if mapping_only:
            return category_id
        elif reverse:
            return {v: k for k, v in category_id.items()}

        resolved_category = category if category else meta.get("category", "")
        if meta.get("anime", False) is True and resolved_category == "TV":
            resolved_category = "ANIMES"

        if resolved_category:
            return {"category_id": category_id.get(resolved_category, "0")}

        return {"category_id": "0"}

    async def get_type_id(
        self, meta: dict[str, Any], type: str = "", reverse: bool = False, mapping_only: bool = False
    ) -> dict[str, str]:
        type_id = {
            "DISC": "1",
            "REMUX": "2",
            "ENCODE": "3",
            "DVDRIP": "3",
            "WEBDL": "4",
            "WEBRIP": "5",
            "HDTV": "6",
            "AZW3": "13",
            "CBR": "14",
            "CBZ": "15",
            "MOBI": "16",
            "PDF": "17",
            "EPUB": "18",
            "KFX": "19",
            "MP4": "21",
            "TS": "22",
            "MKV": "23",
            "MP3": "24",
            "M4B": "24",
            "FLAC": "24",
            "M4A": "24",
            "AUDIOBOOK": "24",
            "OUTROS": "43",
        }

        if mapping_only:
            return type_id
        elif reverse:
            return {v: k for k, v in type_id.items()}
        elif type:
            return {"type_id": type_id.get(type, "0")}
        else:
            meta_type = meta.get("type", "")
            resolved_id = type_id.get(meta_type, "0")
            return {"type_id": resolved_id}

    async def get_resolution_id(
        self, meta: dict[str, Any], resolution: str = "", reverse: bool = False, mapping_only: bool = False
    ) -> dict[str, str]:
        resolution_id = {
            '4320p': '1',
            '2160p': '2',
            '1080p': '3',
            '1080i': '4',
            '720p': '5',
            '576p': '6',
            '576i': '7',
            '480p': '8',
            '480i': '9',
            'Other': '10',
        }

        if mapping_only:
            return resolution_id
        elif reverse:
            return {v: k for k, v in resolution_id.items()}
        elif resolution:
            return {"resolution_id": resolution_id.get(resolution, "10")}
        else:
            meta_resolution = meta.get("resolution", "")
            resolved_id = resolution_id.get(meta_resolution, "10")
            return {"resolution_id": resolved_id}

    async def get_name(self, meta: dict[str, Any]) -> dict[str, str]:
        category = meta["category"]
        cbr_name = str(meta["name"])

        if category == "BOOK":
            if meta.get("is_audiobook", False):
                cbr_name = f"{meta.get('title', '')} - {meta.get('author', '')} [{meta.get('year', '')}] [AUDIOBOOK]"
            else:
                cbr_name = f"{meta.get('title', '')} - {meta.get('author', '')} [{meta.get('year', '')}]"

        elif category in ("MOVIE", "TV"):
            cbr_name = cbr_name.replace("DD+ ", "DDP").replace("DD ", "DD").replace("AAC ", "AAC").replace("FLAC ", "FLAC").replace("Dubbed", "").replace("Dual-Audio", "")

            # If it is a Series or Anime, remove the year from the title.
            if meta.get("category") in ["TV", "ANIMES"]:
                year = str(meta.get("year", ""))
                if year and year in cbr_name:
                    cbr_name = cbr_name.replace(f"({year})", "").replace(year, "").strip()

            # Remove the AKA title, unless it is Brazilian
            if meta.get("original_language") != "pt":
                cbr_name = cbr_name.replace(meta.get("aka", ""), "")

            # If it is Brazilian, use only the AKA title, deleting the foreign title
            if meta.get("original_language") == "pt" and meta.get("aka"):
                aka_clean = str(meta.get("aka", "")).replace("AKA", "").strip()
                title = meta.get("title", "")
                cbr_name = cbr_name.replace(meta.get("aka", ""), "").replace(title, aka_clean).strip()

            tag_lower = str(meta.get("tag", "")).lower()
            invalid_tags = ["nogrp", "nogroup", "unknown", "-unk-"]

            if not meta.get("is_disc"):
                audio_tag = ""
                audio_langs = meta.get("audio_languages")
                if audio_langs:
                    try:
                        audio_languages: set[str] = set(audio_langs)
                    except TypeError:
                        audio_languages = set()

                    if any(lang.lower() == "portuguese" or lang == "português" for lang in audio_languages):
                        if len(audio_languages) >= 3:
                            audio_tag = " MULTI"
                        elif len(audio_languages) == 2:
                            audio_tag = " DUAL"
                        else:
                            audio_tag = ""

                    if audio_tag:
                        if "-" in cbr_name:
                            parts = cbr_name.rsplit("-", 1)

                            custom_tag = dict(dict(self.config.get("TRACKERS", {})).get(self.tracker, {})).get("tag_for_custom_release", "")
                            if custom_tag and custom_tag in name:
                                match = re.search(r"-([^.-]+)\.(?:DUAL|MULTI)", meta["uuid"])
                                if match and match.group(1) != meta["tag"]:
                                    original_group_tag = match.group(1)
                                    cbr_name = f"{parts[0]}-{original_group_tag}{audio_tag}-{parts[1]}"
                                else:
                                    cbr_name = f"{parts[0]}{audio_tag}-{parts[1]}"
                            else:
                                cbr_name = f"{parts[0]}{audio_tag}-{parts[1]}"
                        else:
                            cbr_name += audio_tag

            if meta["tag"] == "" or any(invalid_tag in tag_lower for invalid_tag in invalid_tags):
                for invalid_tag in invalid_tags:
                    cbr_name = re.sub(f"-{invalid_tag}", "", cbr_name, flags=re.IGNORECASE)
                cbr_name = f"{cbr_name}-NoGroup"

        return {"name": re.sub(r"\s{2,}", " ", cbr_name)}

    async def get_additional_data(self, meta: dict[str, Any]) -> dict[str, str]:
        data = {
            'mod_queue_opt_in': await self.get_flag(meta, 'modq'),
        }

        return data

    async def get_additional_checks(self, meta: dict[str, Any]) -> bool:
        return await self.common.check_language_requirements(
            meta, self.tracker, languages_to_check=["portuguese", "português"], check_audio=True, check_subtitle=True
        )

    async def get_additional_files(self, meta: dict[str, Any]) -> dict[str, tuple[str, bytes, str]]:
        files = await super().get_additional_files(meta)
        import os

        cover_path = meta.get("cover_path")
        if cover_path and os.path.exists(cover_path):
            try:
                cover_bytes = await self.process_image_for_api(cover_path, 400, 600)
                if cover_bytes:
                    files["torrent-cover"] = ("cover.jpg", cover_bytes, "image/jpeg")
            except Exception as e:
                console.print(f"[yellow]Failed to process cover: {e}[/yellow]")

        banner_path = meta.get("banner_path")
        if banner_path and os.path.exists(banner_path):
            try:
                banner_bytes = await self.process_image_for_api(banner_path, 960, 540)
                if banner_bytes:
                    files["torrent-banner"] = ("banner.jpg", banner_bytes, "image/jpeg")
            except Exception as e:
                console.print(f"[yellow]Failed to process banner: {e}[/yellow]")

        return files

    async def process_image_for_api(self, img_path: str, target_width: int, target_height: int) -> Optional[bytes]:
        import asyncio
        import io

        from PIL import Image

        def _process():
            img_original = Image.open(img_path)
            largura_orig, altura_orig = img_original.size

            if img_original.mode in ("RGBA", "LA"):
                fundo = Image.new("RGB", img_original.size, (255, 255, 255))
                alpha = img_original.split()[-1]
                fundo.paste(img_original, mask=alpha)
                img_final = fundo
            elif img_original.mode != "RGB":
                img_final = img_original.convert("RGB")
            else:
                img_final = img_original

            if largura_orig != target_width or altura_orig != target_height:
                img_ratio = largura_orig / altura_orig
                target_ratio = target_width / target_height

                if img_ratio > target_ratio:
                    nova_altura = target_height
                    nova_largura = int(largura_orig * (target_height / altura_orig))
                else:
                    nova_largura = target_width
                    nova_altura = int(altura_orig * (target_width / largura_orig))

                img_resized = img_final.resize((nova_largura, nova_altura), Image.Resampling.LANCZOS)

                left = (nova_largura - target_width) // 2
                top = (nova_offset := (nova_altura - target_height) // 2)
                right = left + target_width
                bottom = top + target_height

                img_final = img_resized.crop((left, top, right, bottom))

            buf = io.BytesIO()
            img_final.save(buf, format="JPEG", quality=95)
            img_bytes = buf.getvalue()

            if len(img_bytes) > 5 * 1024 * 1024:
                buf = io.BytesIO()
                img_final.save(buf, format="JPEG", quality=85)
                img_bytes = buf.getvalue()

            return img_bytes if len(img_bytes) <= 5 * 1024 * 1024 else None

        return await asyncio.to_thread(_process)
