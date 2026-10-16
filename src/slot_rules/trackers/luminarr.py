# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Luminarr coexistence and trumping rules (sections 8 and 9, transcribed 2026-10-15)."""

from collections.abc import Sequence

from src.slot_rules.base import SlotKey, SlotRules, expanded_hdr, is_repack_of, size_diff_ratio
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import DV, DVDRIP, ENCODE, HDTV, REMUX, SD, WEBDL, WEBRIP, ReleaseProfile


class LuminarrSlotRules(SlotRules):
    TRACKER = "LUMINARR"

    def family(self, profile: ReleaseProfile) -> str:
        kind = self.require(profile.kind, "release type")
        if kind in (WEBDL, WEBRIP, HDTV):
            return "WEB/TV"
        if kind in (ENCODE, DVDRIP):
            return "Encode"
        return kind

    def key(self, profile: ReleaseProfile) -> SlotKey:
        res = self.require(profile.resolution, "resolution")
        self.require(profile.hdr, "dynamic range")
        family = self.family(profile)
        key: tuple[object, ...] = (res, family, profile.edition, profile.is_3d)
        if family == "WEB/TV":
            # Different streaming providers or TV networks coexist (8.4.1, 8.5.1).
            key = (*key, self.require(profile.provider, "streaming provider / TV network"))
        return key

    @staticmethod
    def hdr_coexists(new: ReleaseProfile, old: ReleaseProfile) -> bool:
        """8.1.7: different HDR types coexist unless one is strictly broader in compatibility."""
        new_hdr, old_hdr = expanded_hdr(new), expanded_hdr(old)
        if new_hdr == old_hdr:
            return False
        if not new_hdr or not old_hdr:
            return True
        # Dolby Vision Profile 5 coexists with every other format (8.1.7.1).
        if {DV} in (new.hdr, old.hdr):
            return True
        return not (new_hdr < old_hdr or old_hdr < new_hdr)

    def coexists(self, new: ReleaseProfile, old: ReleaseProfile) -> bool:
        if self.hdr_coexists(new, old):
            return True
        # 8.6.1.1: encodes coexist with a file size variance of at least 20% (1.20 : 1).
        if new.kind in (ENCODE, DVDRIP) and old.kind in (ENCODE, DVDRIP):
            ratio = size_diff_ratio(new, old)
            return ratio is not None and ratio >= 1 - 1 / 1.2
        return False

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        if upload.kind == DVDRIP:
            remuxes = [profile for profile in existing if profile.kind == REMUX and profile.resolution == SD]
            if remuxes:
                return self.decision(Verdict.BLOCK, "A DVD remux is already on the site.", remuxes, why="DVDRips can't coexist with remuxes.")

        def trump(new: ReleaseProfile, old: ReleaseProfile) -> tuple[Verdict, str]:
            if is_repack_of(new, old):
                return Verdict.ALLOW, "A REPACK/PROPER replaces the original release from the same group."
            if new.kind == WEBDL and old.kind == WEBRIP:
                return Verdict.ALLOW, "A WEB-DL replaces a WEBRip."
            if new.kind in (WEBDL, WEBRIP) and old.kind == HDTV:
                return Verdict.ALLOW, "A WEB release replaces an HDTV release."
            if new.kind == WEBRIP and old.kind == WEBDL:
                return Verdict.REVIEW, "A WEBRip can sit beside the WEB-DL only with documented, significant benefits."
            if new.kind == HDTV and old.kind in (WEBDL, WEBRIP):
                return Verdict.REVIEW, "An HDTV release can sit beside a WEB release only when comparisons show a significant improvement."
            if expanded_hdr(old) < expanded_hdr(new):
                return Verdict.ALLOW, f"{new.hdr_label} covers everything {old.hdr_label} does, and more."
            if new.kind == REMUX:
                return Verdict.REVIEW, "A remux replaces another with a better source or more complete content."
            return Verdict.BLOCK, ""

        label = f"{upload.resolution} {self.family(upload)} {upload.hdr_label}"
        return self.by_slot(upload, existing, self.key, label, trump=trump, coexists=self.coexists, capacity=1_000)
