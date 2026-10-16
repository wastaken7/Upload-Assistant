# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Anthelion slots (wiki "Slots", transcribed 2026-10-15)."""

from collections.abc import Sequence
from typing import cast

from src.slot_rules.base import SlotKey, SlotRules, UnknownTraitError, is_repack_of
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import AV1, DV, REMUX, SD, WEBDL, WEBRIP, ReleaseProfile

TIERS = (SD, "720p", "1080p", "2160p")
# Only these edition flags split ANT's slot sets.
ANT_EDITIONS = frozenset({"directors", "extended", "uncut", "unrated", "imax", "criterion", "4kremaster"})


class AnthelionSlotRules(SlotRules):
    TRACKER = "ANTHELION"

    def slot_type(self, profile: ReleaseProfile) -> str | None:
        tier = self.require(profile.resolution, "resolution")
        if profile.is_3d:
            return "3D" if tier == "1080p" else None
        kind = self.require(profile.kind, "release type")
        if kind == REMUX:
            return "Remux"
        if self.require(profile.codec, "video codec") == AV1:
            return "AV1"
        if kind in (WEBDL, WEBRIP):
            return "WEB"
        return "Encode"

    def dynamic_range(self, profile: ReleaseProfile, slot_type: str) -> str:
        if slot_type not in ("Encode", "WEB") or profile.resolution not in ("1080p", "2160p"):
            return ""
        hdr = self.require(profile.hdr, "dynamic range")
        if profile.resolution == "1080p":
            return "HDR" if hdr else "SDR"
        has_dv = DV in hdr
        has_hdr10 = bool(hdr - {DV})
        if has_dv and has_hdr10:
            return "DV+HDR"
        if has_dv:
            return "DV"
        return "HDR" if has_hdr10 else "SDR"

    def key(self, profile: ReleaseProfile) -> SlotKey | None:
        tier = self.require(profile.resolution, "resolution")
        if tier not in TIERS:
            return None
        slot_type = self.slot_type(profile)
        if slot_type is None:
            return None
        return (tier, slot_type, self.dynamic_range(profile, slot_type), profile.edition & ANT_EDITIONS)

    @staticmethod
    def label(key: SlotKey) -> str:
        editions = key[3]
        edition_text = "/".join(sorted(str(edition) for edition in cast(frozenset[str], editions))) if isinstance(editions, frozenset) else ""
        return " ".join(part for part in (str(key[0]), str(key[1]), str(key[2]), edition_text) if part)

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        upload_key = self.key(upload)
        if upload_key is None:
            return self.decision(Verdict.ALLOW, "ANT does not use slots for this resolution or 3D type.")

        tier, slot_type, dynamic_range, editions = upload_key[0], upload_key[1], upload_key[2], upload_key[3]
        if slot_type == "WEB":
            closing: list[ReleaseProfile] = []
            for profile in existing:
                try:
                    other = self.key(profile)
                except UnknownTraitError:
                    continue
                if other is None or other[0] != tier or other[1] != "Encode" or other[2] != dynamic_range:
                    continue
                # Any edition's encode closes the standard WEB slot; an edition's WEB slot only closes for that edition.
                if not editions or other[3] == editions:
                    closing.append(profile)
            if closing:
                return self.decision(
                    Verdict.BLOCK,
                    "An encode on the site closes this WEB slot.",
                    closing,
                    slot=self.label(upload_key),
                    why="ANT prefers encodes: once a tier has an encode with the same dynamic range, new WEB releases are refused. Staff can give a slot override token.",
                )

        def trump(new: ReleaseProfile, old: ReleaseProfile) -> tuple[Verdict, str]:
            if is_repack_of(new, old):
                return Verdict.BLOCK, "ANT refuses uploads into a filled slot, even a REPACK/PROPER of the same group. Ask staff for a slot override token."
            return Verdict.BLOCK, "The first upload keeps the slot. If yours is better, ask staff for a slot override token, with comparisons."

        return self.by_slot(upload, existing, self.key, self.label(upload_key), trump=trump)
