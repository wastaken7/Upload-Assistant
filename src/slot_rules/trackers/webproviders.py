# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Trackers whose rules define WEB-DL slots by provider and leave encodes to staff judgement."""

from collections.abc import Sequence

from src.slot_rules.base import SlotKey, SlotRules, is_repack_of, slot_label
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import DVDRIP, ENCODE, HDTV, REMUX, WEBDL, WEBRIP, ReleaseProfile


class HomieHelpDeskSlotRules(SlotRules):
    """HomieHelpDesk section 9: remux, WEB-DL and HDTV are one per cut per resolution."""

    TRACKER = "HOMIEHELPDESK"

    def key(self, profile: ReleaseProfile) -> SlotKey:
        res = self.require(profile.resolution, "resolution")
        kind = self.require(profile.kind, "release type")
        if kind == WEBDL:
            # WEB-DLs from different providers, codecs and colour spaces coexist.
            return (
                res,
                "WEB-DL",
                self.require(profile.provider, "streaming provider"),
                self.require(profile.codec, "video codec"),
                self.require(profile.hdr, "dynamic range"),
                profile.edition,
            )
        return (res, kind, profile.edition)

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        if upload.kind == WEBRIP:
            same_webdl = [profile for profile in existing if profile.kind == WEBDL and profile.resolution == upload.resolution and profile.provider == upload.provider]
            if same_webdl:
                return self.decision(
                    Verdict.REVIEW,
                    "A WEB-DL from the same provider is already on the site.",
                    same_webdl,
                    why="WEBRips can't sit beside their source WEB-DL unless comparisons prove a significant improvement.",
                )
        if upload.kind in (ENCODE, DVDRIP, WEBRIP):
            same = [profile for profile in existing if profile.kind == upload.kind and profile.resolution == upload.resolution]
            if same:
                return self.decision(
                    Verdict.REVIEW,
                    "An encode is already on the site at this resolution.",
                    same,
                    why="Encodes can coexist within reason when they offer meaningful size, quality or feature benefits.",
                )
            return self.decision(Verdict.ALLOW, f"No {upload.resolution} encode is on the site yet.")

        notes: list[str] = []
        if upload.kind == WEBDL:
            webrips = [profile for profile in existing if profile.kind == WEBRIP and profile.resolution == upload.resolution and profile.provider == upload.provider]
            if webrips:
                notes.append("WEB-DLs trump WEBRips of the same source and source resolution.")

        def trump(new: ReleaseProfile, old: ReleaseProfile) -> tuple[Verdict, str]:
            if is_repack_of(new, old):
                return Verdict.ALLOW, "A REPACK/PROPER replaces the original release from the same group."
            if new.kind == REMUX:
                return Verdict.REVIEW, "A remux replaces another with a better source or added assets; remuxes from different masters coexist."
            return Verdict.BLOCK, ""

        return self.by_slot(upload, existing, self.key, slot_label(self.key(upload)), trump=trump, notes=notes)


class SkipTheCommercialsSlotRules(SlotRules):
    """SkipTheCommercials coexistence rules."""

    TRACKER = "SKIPTHECOMMERCIALS"
    INTERNAL_GROUP = "stc"

    def is_internal(self, profile: ReleaseProfile) -> bool:
        return profile.internal or profile.group == self.INTERNAL_GROUP

    def key(self, profile: ReleaseProfile) -> SlotKey:
        res = self.require(profile.resolution, "resolution")
        kind = self.require(profile.kind, "release type")
        if kind not in (WEBDL, WEBRIP):
            return (res, kind)
        return (
            res,
            "WEB",
            self.require(profile.provider, "streaming provider"),
            self.require(profile.codec, "video codec"),
            self.require(profile.hdr, "dynamic range"),
        )

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        if upload.kind in (REMUX, ENCODE, DVDRIP, HDTV):
            same = [profile for profile in existing if profile.kind == upload.kind and profile.resolution == upload.resolution]
            if same:
                return self.decision(
                    Verdict.REVIEW,
                    "A release of this type is already on the site at this resolution.",
                    same,
                    why="Remuxes and encodes can coexist when they are meaningfully different.",
                )
            return self.decision(Verdict.ALLOW, f"No {upload.resolution} release of this type is on the site yet.")

        def coexists(new: ReleaseProfile, old: ReleaseProfile) -> bool:
            # One external release may coexist with an internal (STC) release from the same provider.
            return self.is_internal(new) != self.is_internal(old)

        def trump(new: ReleaseProfile, old: ReleaseProfile) -> tuple[Verdict, str]:
            if is_repack_of(new, old):
                return Verdict.ALLOW, "A REPACK/PROPER replaces the original release from the same group."
            if new.kind == WEBRIP and old.kind == WEBDL:
                return Verdict.BLOCK, "WEBRips can't sit beside a WEB-DL from the same provider."
            if new.kind == WEBDL and old.kind == WEBRIP:
                return Verdict.REVIEW, "WEBRips can't sit beside a WEB-DL from the same provider; staff decide which one stays."
            return Verdict.BLOCK, ""

        return self.by_slot(upload, existing, self.key, slot_label(self.key(upload)), trump=trump, coexists=coexists, capacity=2)
