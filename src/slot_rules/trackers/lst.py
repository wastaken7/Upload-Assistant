# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""LST slots (Upload Rules, Slots & Trumping, transcribed 2026-10-15)."""

from collections.abc import Sequence

from src.slot_rules.base import SlotKey, SlotRules, is_repack_of, slot_label
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import AV1, DV, ENCODE, H264, H265, HDR10P, REMUX, SD, WEBDL, WEBRIP, ReleaseProfile

UNLISTED = "unlisted"


class LstSlotRules(SlotRules):
    TRACKER = "LST"

    def web_range(self, profile: ReleaseProfile) -> str:
        hdr = self.require(profile.hdr, "dynamic range")
        if not hdr:
            return "SDR"
        if hdr == {DV}:
            return "DV"
        if HDR10P in hdr:
            # HDR10+ has its own slot in the general rules but no WEB-DL slot is listed.
            return UNLISTED
        return "HDR"

    def key(self, profile: ReleaseProfile) -> SlotKey:
        res = self.require(profile.resolution, "resolution")
        kind = self.require(profile.kind, "release type")
        edition = profile.edition
        if kind in (WEBDL, WEBRIP):
            provider = self.require(profile.provider, "streaming provider")
            codec = self.require(profile.codec, "video codec")
            if res in (SD, "720p"):
                return (res, "WEB-DL", provider, codec, edition) if res == SD or codec == H264 else (res, UNLISTED, kind)
            web_range = self.web_range(profile)
            if web_range in ("DV", "HDR") and codec != H265:
                return (res, UNLISTED, kind)
            return (res, "WEB-DL", provider, codec if web_range == "SDR" else web_range, edition)
        if kind == REMUX:
            if res == "2160p":
                hdr = self.require(profile.hdr, "dynamic range")
                return (res, "Remux", "SDR" if not hdr else ("hybrid" if profile.hybrid else "DV/HDR"), edition)
            return (res, "Remux", edition) if res in (SD, "1080p") else (res, UNLISTED, kind)
        if kind == ENCODE:
            codec = self.require(profile.codec, "video codec")
            if res in (SD, "720p"):
                return (res, "encode", edition) if codec == H264 else (res, UNLISTED, kind)
            if codec not in (H264, H265, AV1) or (res == "2160p" and codec == H264):
                return (res, UNLISTED, kind)
            hdr = self.require(profile.hdr, "dynamic range")
            if hdr and codec == H264:
                return (res, UNLISTED, kind)
            return (res, "encode", codec, "HDR" if hdr else "SDR", edition)
        return (res, UNLISTED, kind)

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        upload_key = self.key(upload)
        if isinstance(upload_key, tuple) and UNLISTED in upload_key:
            return self.decision(Verdict.REVIEW, "LST's slot list has no place for this kind of release.", why="Open a support ticket if an additional slot is justified.")

        if upload.kind == WEBRIP:
            same_webdl = [profile for profile in existing if profile.kind == WEBDL and profile.resolution == upload.resolution and profile.provider == upload.provider]
            if same_webdl:
                return self.decision(
                    Verdict.REVIEW,
                    "A WEB-DL from the same provider is already on the site.",
                    same_webdl,
                    why="A WEBRip only gets a slot beside the WEB-DL when comparisons show a clear visual improvement.",
                )

        notes: list[str] = []
        if upload.resolution == SD:
            notes.append("SD is only allowed when no equivalent HD retail source exists.")

        def trump(new: ReleaseProfile, old: ReleaseProfile) -> tuple[Verdict, str]:
            if old.internal and not (new.group and new.group == old.group):
                return Verdict.BLOCK, "It is an internal release; only its own group can replace it."
            if is_repack_of(new, old):
                return Verdict.ALLOW, "A REPACK/PROPER replaces the original release from the same group."
            if new.kind == ENCODE:
                return Verdict.REVIEW, "Encodes can coexist when they are clearly different in quality, size or source master."
            if new.kind == WEBDL and old.kind == WEBRIP:
                return Verdict.REVIEW, "A WEBRip that was proven better than the WEB-DL keeps its slot."
            if new.resolution == "2160p" and new.kind == WEBDL and new.audio_lossless and not old.audio_lossless:
                return Verdict.REVIEW, "There is one extra 2160p WEB-DL slot for lossless audio, from any provider."
            return self.hdr_trump(new, old)

        return self.by_slot(upload, existing, self.key, slot_label(upload_key), trump=trump, notes=notes)
