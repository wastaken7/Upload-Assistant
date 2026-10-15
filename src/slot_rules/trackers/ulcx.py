# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""ULCX slot framework (sections 4, 5 and 8, transcribed 2026-10-15)."""

from collections.abc import Sequence

from src.slot_rules.base import SlotKey, SlotRules, UnknownTraitError, is_repack_of, slot_label
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import DV, ENCODE, HDR10, HDR10P, HLG, REMUX, SD, WEBDL, WEBRIP, ReleaseProfile

UNLISTED = "unlisted"
# Compact tier ceilings for average video bitrate, in kb/s.
COMPACT_MAX_KBPS = {"1080p": 12_000, "2160p": 18_000}


class UlcxSlotRules(SlotRules):
    TRACKER = "ULCX"

    def colour(self, profile: ReleaseProfile) -> str:
        hdr = self.require(profile.hdr, "dynamic range")
        if not hdr:
            return "SDR"
        if hdr == {DV}:
            return "DV (Profile 5)"
        if HLG in hdr and not hdr & {HDR10, HDR10P}:
            return "HLG"
        return "HDR10"

    def tier(self, profile: ReleaseProfile) -> str:
        res = self.require(profile.resolution, "resolution")
        ceiling = COMPACT_MAX_KBPS.get(res)
        if ceiling is None:
            raise UnknownTraitError(f"ULCX does not define size tiers for {res} encodes.")
        bitrate = self.require(profile.video_bitrate_kbps, "video bitrate (it decides between the Compact and Transparent slots)")
        return "Compact" if bitrate <= ceiling else "Transparent"

    def key(self, profile: ReleaseProfile) -> SlotKey:
        res = self.require(profile.resolution, "resolution")
        kind = self.require(profile.kind, "release type")
        if kind == REMUX:
            return (res, "Remux", self.colour(profile), profile.edition)
        if kind == WEBDL:
            provider = self.require(profile.provider, "streaming provider")
            return (res, "WEB-DL", provider, self.require(profile.codec, "video codec"), self.colour(profile))
        if kind == ENCODE:
            return (res, "encode", self.require(profile.codec, "video codec"), self.colour(profile), profile.edition, self.tier(profile))
        return (res, UNLISTED, kind)

    @staticmethod
    def hdr_branches_coexist(new: ReleaseProfile, old: ReleaseProfile) -> bool:
        """Section 8: DV HDR10 and HDR10+ coexist inside the HDR10 slot."""
        pair = {new.hdr, old.hdr}
        return pair == {frozenset({DV, HDR10}), frozenset({HDR10P})}

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        if upload.kind == ENCODE and upload.resolution == SD:
            return self.decision(Verdict.BLOCK, "SD encodes are not allowed on ULCX.", why="Encodes must be at least 720p; SD content can only be a full disc or remux.")
        if upload.kind == WEBRIP:
            return self.decision(Verdict.REVIEW, "ULCX has no slot for WEBRips.")
        upload_key = self.key(upload)
        if isinstance(upload_key, tuple) and UNLISTED in upload_key:
            return self.decision(Verdict.REVIEW, "ULCX's slot rules don't cover this kind of release.")

        def trump(new: ReleaseProfile, old: ReleaseProfile) -> tuple[Verdict, str]:
            if old.internal and not new.internal:
                return Verdict.BLOCK, "It is an internal release, so its slot counts as filled."
            if is_repack_of(new, old):
                return Verdict.ALLOW, "A REPACK/PROPER replaces the original release from the same group."
            if new.kind == REMUX:
                return Verdict.REVIEW, "A remux replaces another only with a provable benefit: better video (with comparisons) or audio, commentary, chapters or subtitles."
            return self.hdr_trump(new, old)

        return self.by_slot(
            upload,
            existing,
            self.key,
            slot_label(upload_key),
            trump=trump,
            coexists=self.hdr_branches_coexist,
            capacity=2,
        )
