# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""HD-Torrents dupe rules (transcribed 2026-10-15)."""

from collections.abc import Sequence

from src.slot_rules.base import SlotKey, SlotRules, UnknownTraitError, is_repack_of, slot_label
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import ENCODE, H264, H265, REMUX, WEBDL, WEBRIP, ReleaseProfile

UNLISTED = "unlisted"


class HDTorrentsSlotRules(SlotRules):
    TRACKER = "HDTORRENTS"

    def hdr_set(self, profile: ReleaseProfile) -> frozenset[str]:
        # Different HDR types and combinations are not dupes of each other (5f).
        return self.require(profile.hdr, "dynamic range")

    def key(self, profile: ReleaseProfile) -> SlotKey:
        res = self.require(profile.resolution, "resolution")
        kind = self.require(profile.kind, "release type")
        edition = profile.edition
        if kind == REMUX:
            if profile.is_3d:
                return (res, "Remux", "3D", edition)
            if res == "1080p":
                return (res, "Remux", edition)
            if res == "2160p":
                hdr = self.hdr_set(profile)
                return (res, "Remux", "HDR" if hdr else "SDR", hdr, edition)
            return (res, UNLISTED, kind)
        if kind in (WEBDL, WEBRIP):
            return (res, "WEB", self.require(profile.provider, "streaming provider"), self.hdr_set(profile), edition)
        if kind != ENCODE or profile.is_3d:
            return (res, UNLISTED, kind)
        codec = self.require(profile.codec, "video codec")
        hdr = self.hdr_set(profile)
        if codec == H264 and not hdr:
            if res in ("720p", "1080p"):
                return (res, "x264 Hi10P" if profile.hi10p else "x264", edition)
            if res == "2160p":
                return (res, "x264", edition)
        if codec == H265 and hdr and res in ("1080p", "2160p"):
            return (res, "x265 HDR", hdr, edition)
        return (res, UNLISTED, kind)

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        upload_key = self.key(upload)
        if isinstance(upload_key, tuple) and UNLISTED in upload_key:
            return self.decision(
                Verdict.REVIEW, "HD-Torrents' dupe list has no place for this kind of release.", why="Releases like 3D encodes, HDTV or SDR x265 are left to staff."
            )

        if upload_key == ("1080p", "x264", upload.edition):
            # One slot from a 1080p source and one from a UHD source; the source can't be detected.
            same: list[ReleaseProfile] = []
            for profile in existing:
                try:
                    if self.key(profile) == upload_key:
                        same.append(profile)
                except UnknownTraitError:
                    continue
            repacked = [profile for profile in same if is_repack_of(upload, profile)]
            if repacked:
                return self.decision(Verdict.ALLOW, "Your REPACK/PROPER replaces the original. Report it as a trump after uploading.", repacked)
            if len(same) >= 2:
                return self.decision(
                    Verdict.BLOCK, "Both 1080p x264 places are already taken.", same, why="HD-Torrents keeps one from a 1080p source and one from a UHD source."
                )
            if same:
                return self.decision(
                    Verdict.REVIEW,
                    "A 1080p x264 encode is already on the site; yours might take the second place.",
                    same,
                    why="HD-Torrents keeps one 1080p x264 from a 1080p source and one from a UHD source.",
                )

        def trump(new: ReleaseProfile, old: ReleaseProfile) -> tuple[Verdict, str]:
            if is_repack_of(new, old):
                return Verdict.ALLOW, "A REPACK/PROPER replaces the original release from the same group."
            if new.kind == WEBDL and old.kind == WEBRIP:
                return Verdict.ALLOW, "A WEB-DL replaces a WEBRip from the same source."
            if new.kind == WEBRIP and old.kind == WEBDL:
                if new.resolution == "1080p":
                    return Verdict.REVIEW, "A 1080p WEBRip from a UHD source can replace the WEB-DL with comparison screenshots."
                return Verdict.BLOCK, "A WEB-DL replaces a WEBRip from the same source."
            return Verdict.BLOCK, "To replace it you need 3+ comparison screenshots proving better quality or a better source."

        return self.by_slot(upload, existing, self.key, slot_label(upload_key), trump=trump)
