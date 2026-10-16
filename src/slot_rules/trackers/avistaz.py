# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""AvistaZ network dupe rules: CinemaZ, AvistaZ and PrivateHD (transcribed 2026-10-15)."""

from collections.abc import Sequence

from src.slot_rules.base import SlotKey, SlotRules, TrumpTest, UnknownTraitError, is_repack_of, slot_label
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import DVDRIP, ENCODE, H264, H265, HDTV, REMUX, WEBDL, WEBRIP, XVID, ReleaseProfile

# Priority of sources for encodes; 1 is best. WEBRip is 4 on both sites.
CINEMAZ_PRIORITY = {ENCODE: 1, DVDRIP: 1, HDTV: 3, WEBRIP: 4}
AVISTAZ_PRIORITY = {ENCODE: 1, DVDRIP: 1, WEBDL: 2, HDTV: 3, WEBRIP: 4}


def _priority_trump(priority: dict[str, int]) -> TrumpTest:
    def trump(new: ReleaseProfile, old: ReleaseProfile) -> tuple[Verdict, str]:
        if is_repack_of(new, old):
            return Verdict.ALLOW, "A REPACK/PROPER replaces the original release from the same group."
        new_rank = priority.get(new.kind or "")
        old_rank = priority.get(old.kind or "")
        if new_rank is None or old_rank is None:
            return Verdict.BLOCK, ""
        if new_rank < old_rank:
            return Verdict.ALLOW, "A better source (Blu-ray > WEB-DL > HDTV > WEBRip) replaces a worse one."
        if new_rank > 2 and old_rank <= 2:
            return Verdict.BLOCK, "HDTV and WEBRip encodes can't be uploaded when a Blu-ray or WEB-DL version exists."
        return Verdict.BLOCK, ""

    return trump


class CinemaZSlotRules(SlotRules):
    TRACKER = "CINEMAZ"

    def key(self, profile: ReleaseProfile) -> SlotKey:
        res = self.require(profile.resolution, "resolution")
        kind = self.require(profile.kind, "release type")
        if kind == REMUX:
            return (res, "Remux")
        if kind == WEBDL:
            return (res, "WEB-DL")
        codec = self.require(profile.codec, "video codec")
        return (res, "encode", "XviD/DivX" if codec == XVID else "x264/x265")

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        if upload.kind == HDTV:
            return self.decision(
                Verdict.REVIEW,
                "HDTV releases need a manual check on CinemaZ.",
                why="HDTV recordings (.ts) and HDTV encodes have separate slots; check which kind is on the site.",
            )
        upload_key = self.key(upload)
        return self.by_slot(upload, existing, self.key, slot_label(upload_key), trump=_priority_trump(CINEMAZ_PRIORITY))


class AvistaZSlotRules(SlotRules):
    TRACKER = "AVISTAZ"

    def key(self, profile: ReleaseProfile) -> SlotKey:
        res = self.require(profile.resolution, "resolution")
        kind = self.require(profile.kind, "release type")
        if kind == REMUX:
            return (res, "Remux")
        codec = self.require(profile.codec, "video codec")
        # WEB-DLs count as encodes (priority 2) in AvistaZ's source priority.
        return (res, "encode", "XviD/DivX" if codec == XVID else "x264/x265")

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        meta_category = str(getattr(self.meta, "category", "") or "") if self.meta is not None else ""
        if meta_category == "TV":
            return self.decision(
                Verdict.REVIEW, "AvistaZ's TV rules need a manual check.", why="The TV dupe list only covers HDTV and Blu-ray formats; WEB releases are not listed."
            )
        upload_key = self.key(upload)
        priority_trump = _priority_trump(AVISTAZ_PRIORITY)

        def trump(new: ReleaseProfile, old: ReleaseProfile) -> tuple[Verdict, str]:
            if {new.codec, old.codec} == {H264, H265}:
                return Verdict.REVIEW, "AvistaZ says x264 and x265 will coexist only 'when x265 is more stabilized'; ask staff."
            return priority_trump(new, old)

        return self.by_slot(upload, existing, self.key, slot_label(upload_key), trump=trump)


class PrivateHDSlotRules(SlotRules):
    TRACKER = "PRIVATEHD"

    COEXISTING_PROVIDERS = frozenset({"AMZN", "NF"})

    def key(self, profile: ReleaseProfile) -> SlotKey:
        res = self.require(profile.resolution, "resolution")
        kind = self.require(profile.kind, "release type")
        edition = profile.edition
        if kind == REMUX:
            return (res, "Remux", "HDR" if self.require(profile.hdr, "dynamic range") else "SDR", profile.is_3d, edition)
        if kind == HDTV:
            return (res, "HDTV")
        codec = self.require(profile.codec, "video codec")
        if kind in (WEBDL, WEBRIP):
            return (res, "WEB", codec, "HDR" if self.require(profile.hdr, "dynamic range") else "SDR", edition)
        return (res, "encode", codec)

    def _same_key(self, profile: ReleaseProfile, key: SlotKey) -> bool:
        try:
            return self.key(profile) == key
        except UnknownTraitError:
            return False

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        upload_key = self.key(upload)

        def coexists(new: ReleaseProfile, old: ReleaseProfile) -> bool:
            providers = {new.provider, old.provider}
            return new.kind in (WEBDL, WEBRIP) and len(providers) == 2 and providers <= self.COEXISTING_PROVIDERS

        def trump(new: ReleaseProfile, old: ReleaseProfile) -> tuple[Verdict, str]:
            if is_repack_of(new, old):
                return Verdict.ALLOW, "A REPACK/PROPER replaces the original release from the same group."
            if new.kind in (ENCODE, DVDRIP):
                return Verdict.REVIEW, "One scene and one P2P encode can coexist, and scene encodes can't be replaced; check whether the existing encode is scene or P2P."
            if new.kind == WEBDL and old.kind == WEBRIP and new.provider == old.provider:
                return Verdict.ALLOW, "A WEB-DL replaces a WEBRip from the same source."
            if new.kind in (WEBDL, WEBRIP) and new.provider != old.provider:
                return Verdict.REVIEW, "Only AMZN and NF WEB releases are listed as coexisting; other providers need comparisons or staff approval."
            if new.kind == REMUX and new.audio_lossless and old.audio_lossless is False:
                return Verdict.ALLOW, "A remux with lossless audio replaces one with lossy audio."
            return Verdict.BLOCK, "Dupes are deleted unless comparisons prove yours is better."

        is_encode = upload.kind in (ENCODE, DVDRIP)
        if is_encode:
            same_slot = [profile for profile in existing if self._same_key(profile, upload_key)]
            if len(same_slot) >= 2:
                return self.decision(
                    Verdict.BLOCK,
                    "Both places in this slot are taken.",
                    same_slot,
                    slot=slot_label(upload_key),
                    why="PrivateHD keeps one scene and one P2P encode.",
                )
        return self.by_slot(
            upload, existing, self.key, slot_label(upload_key), trump=trump, coexists=coexists, capacity=2 if is_encode or upload.kind in (WEBDL, WEBRIP) else 1
        )
