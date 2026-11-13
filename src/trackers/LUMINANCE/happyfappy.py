# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""HappyFappy: private Luminance tracker for adult content.

Upload rules: https://www.happyfappy.net/articles/view/upload
"""

from typing import ClassVar

from src.meta import Meta
from src.rehostimages import ImageHostPolicy
from src.trackers.LUMINANCE import GAME_EXTENSIONS, Luminance

# A video torrent may carry a few promotional images, but not a picture set.
MAX_BUNDLED_IMAGES = 15
MAX_BUNDLED_IMAGE_BYTES = 15 * 1024 * 1024


class HappyFappy(Luminance):
    """HappyFappy (HF) is a private adult tracker running Luminance."""

    tracker = "HAPPYFAPPY"
    display_name = "HappyFappy"
    source_flag = "HappyFappy"
    base_url = "https://www.happyfappy.net"
    tracker_urls = ("tracker.happyfappy.net",)
    # The site also lists hamsterimg.net, which Upload Assistant cannot upload to.
    approved_image_hosts = ("pixhost", "imgbox", "bam")
    image_host_policy = ImageHostPolicy(
        {"pixhost.to": "pixhost", "pixhost.cc": "pixhost", "pixho.st": "pixhost", "imgbox.com": "imgbox", "imagebam.com": "bam"},
        approved_image_hosts,
    )
    category_ids: ClassVar[dict[str, str]] = {
        "AI": "15",
        "Asian": "11",
        "Fansite": "6",
        "Games": "13",
        "Gay / Bi": "3",
        "Interracial": "4",
        "Lesbian": "5",
        "Packs": "9",
        "Pics": "10",
        "Pron": "1",
        "Retro": "8",
        "Scat": "14",
        "Transexual": "12",
        "VR": "7",
    }
    default_category = "Pron"
    has_mediainfo_field = True
    # "The simplest upload is a single short scene. It should still have at least 5 tags."
    min_tags = 5

    def category_name(self, meta: Meta) -> str:
        """Pick the HappyFappy category: format first, then who is in the release."""
        if any(path.suffix.casefold() in GAME_EXTENSIONS for path in self._files(meta)):
            return "Games"
        if self.is_picset(meta):
            return "Pics"
        if self.has_word(meta, r"\bai (?:generated|porn)\b|\baigenerated\b"):
            return "AI"
        if self.has_word(meta, r"\bscat\b"):
            return "Scat"
        if self.is_vr(meta):
            return "VR"
        if self.is_pack(meta):
            return "Packs"
        if self.has_word(meta, r"\b(?:gay|bisexual|twinks?)\b"):
            return "Gay / Bi"
        if self.has_word(meta, r"\b(?:trans|transgender|transsexual|shemale|tgirl|ladyboy)\b"):
            return "Transexual"
        if self.is_jav(meta) or self.has_word(meta, r"\b(?:asian|japanese|chinese|korean|thai|filipina)\b"):
            return "Asian"
        if self.has_word(meta, r"\blesbians?\b") and not self.has_word(meta, r"\b(?:blowjob|cumshot|facial|handjob|creampie|ffm|mmf)\b"):
            return "Lesbian"
        if self.is_fansite(meta):
            return "Fansite"
        if self.has_word(meta, r"\b(?:interracial|bbc|blacked|blackedraw)\b"):
            return "Interracial"
        release = self._release(meta)
        year = (release.year if release else None) or (meta.year if isinstance(meta.year, int) else None)
        if year and 1900 < year < 2000:
            return "Retro"
        return self.default_category

    def get_category_id(self, meta: Meta) -> str:
        return self.category_ids[self.category_name(meta)]

    def rule_warnings(self, meta: Meta) -> list[str]:
        warnings = super().rule_warnings(meta)
        if self._videos(meta) and not (self.is_siterip(meta) or self.is_fansite(meta)):
            images = self._images(meta)
            image_bytes = sum(path.stat().st_size for path in images if path.is_file())
            if len(images) > MAX_BUNDLED_IMAGES or image_bytes > MAX_BUNDLED_IMAGE_BYTES:
                warnings.append(
                    f"Video torrents must not bundle a picture set ({len(images)} images, {image_bytes / 1024 / 1024:.1f} MiB); upload the pictures as a separate Pics torrent."
                )
        return warnings

    def rule_notes(self, meta: Meta) -> list[str]:
        notes = super().rule_notes(meta)
        if not self.description_text(meta):
            notes.append("HappyFappy requires an English text description of the content; none was found. Add one with --description or a description file.")
        return notes
