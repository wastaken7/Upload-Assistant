# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Aither slots (wiki "Slots", transcribed 2026-10-15)."""

from collections.abc import Sequence

from src.slot_rules.base import SlotKey, SlotRules, size_diff_ratio, slot_label
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import DV, DVDRIP, ENCODE, H264, H265, HDR10P, REMUX, SD, WEBDL, WEBRIP, ReleaseProfile

UNLISTED = "unlisted"


class AitherSlotRules(SlotRules):
    TRACKER = "AITHER"

    def web_range(self, profile: ReleaseProfile, *, split_hdr10p: bool) -> str:
        hdr = self.require(profile.hdr, "dynamic range")
        if not hdr:
            return "SDR"
        if hdr == {DV}:
            return "DV"
        if split_hdr10p and HDR10P in hdr:
            return "HDR10+"
        return "HDR"

    def disc_range(self, profile: ReleaseProfile, *, sdr_slot: bool) -> str:
        hdr = self.require(profile.hdr, "dynamic range")
        if not hdr:
            return "SDR" if sdr_slot else UNLISTED
        if hdr == {DV}:
            return UNLISTED
        if profile.hybrid or HDR10P in hdr:
            return "HYBRID"
        return "HDR"

    def key(self, profile: ReleaseProfile) -> SlotKey:
        res = self.require(profile.resolution, "resolution")
        kind = self.require(profile.kind, "release type")
        edition = profile.edition
        if res == SD:
            mapping = {WEBDL: "WEB-DL", DVDRIP: "DVDRip", ENCODE: "DVDRip", REMUX: "DVD Remux"}
            return (res, mapping.get(kind, UNLISTED), edition)
        if kind == REMUX:
            if res == "1080p":
                return (res, "Remux", edition)
            if res == "2160p":
                return (res, "Remux", self.disc_range(profile, sdr_slot=True), edition)
            return (res, UNLISTED, kind)
        codec = self.require(profile.codec, "video codec")
        if kind == WEBDL:
            if res == "720p":
                return (res, "WEB", edition) if codec == H264 else (res, UNLISTED, kind)
            if res in ("1080p", "1440p"):
                if codec == H264:
                    return (res, "WEB", "H.264", edition)
                web_range = self.web_range(profile, split_hdr10p=False)
                return (res, "WEB", web_range, edition) if codec == H265 and web_range != "SDR" else (res, UNLISTED, kind)
            if res == "2160p":
                return (res, "WEB", self.web_range(profile, split_hdr10p=True), edition) if codec == H265 else (res, UNLISTED, kind)
        if kind == ENCODE:
            if res == "720p":
                return (res, "encode", edition) if codec == H264 else (res, UNLISTED, kind)
            if res == "1080p":
                if codec == H264:
                    return (res, "x264 encode", edition)
                if codec == H265:
                    hdr = self.require(profile.hdr, "dynamic range")
                    return (res, "x265 encode", self.disc_range(profile, sdr_slot=True) if hdr else "SDR", edition)
            if res == "2160p" and codec == H265:
                return (res, "x265 encode", self.disc_range(profile, sdr_slot=True), edition)
        return (res, UNLISTED, kind)

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        if upload.kind == WEBRIP:
            return self.decision(
                Verdict.REVIEW,
                "WEBRips need a manual check on Aither.",
                [profile for profile in existing if profile.kind in (WEBDL, WEBRIP) and profile.resolution == upload.resolution],
                why="A WEBRip is only allowed when it comes from a higher-resolution WEB-DL or no WEB-DL exists, and it needs 6 comparison screenshots.",
            )
        upload_key = self.key(upload)
        if isinstance(upload_key, tuple) and UNLISTED in upload_key:
            return self.decision(Verdict.REVIEW, "Aither's slot list has no place for this kind of release.", why="Staff may grant an additional slot when it is justified.")

        notes: list[str] = []
        if upload.resolution == SD:
            notes.append("SD releases are only allowed when no equivalent HD retail source exists.")
        if isinstance(upload_key, tuple) and "HYBRID" in upload_key:
            notes.append("Retail disc DV trumps hybrid sources unless the hybrid is proven superior; hybrids need grade checks and an HDR10+/L1 plot.")
        if upload.resolution == "1440p":
            notes.append("1440p is only allowed when no 2160p source exists.")

        is_x264_1080 = isinstance(upload_key, tuple) and "x264 encode" in upload_key and upload.resolution == "1080p"
        return self.by_slot(
            upload,
            existing,
            self.key,
            slot_label(upload_key),
            trump=self.hdr_trump,
            # Quality and retention slots: encodes 20% apart in size do not compete.
            coexists=(lambda new, old: (size_diff_ratio(new, old) or 0) >= 0.20) if is_x264_1080 else None,
            capacity=2 if is_x264_1080 else 1,
            notes=notes,
        )
