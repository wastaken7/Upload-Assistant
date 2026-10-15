# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Cathode-Ray.Tube torrent coexistence rules (transcribed 2026-10-15)."""

from collections.abc import Sequence

from src.slot_rules.base import SlotRules, is_repack_of
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import DVDRIP, ENCODE, H264, H265, REMUX, SD, WEBDL, ReleaseProfile


class CathodeRayTubeSlotRules(SlotRules):
    TRACKER = "CATHODERAYTUBE"

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        res = self.require(upload.resolution, "resolution")
        kind = self.require(upload.kind, "release type")
        same_edition = [profile for profile in existing if profile.resolution == res and profile.edition == upload.edition]

        if kind in (REMUX, WEBDL):
            holders = [profile for profile in same_edition if profile.kind in (REMUX, WEBDL)]
            if not holders:
                return self.decision(Verdict.ALLOW, f"No {res} remux or WEB-DL is on the site for this edition yet.")
            repacked = [profile for profile in holders if is_repack_of(upload, profile)]
            if repacked:
                return self.decision(Verdict.ALLOW, "Your REPACK/PROPER replaces the original. Report it as a trump after uploading.", repacked)
            if len(holders) >= 2:
                return self.decision(
                    Verdict.BLOCK,
                    "Both remux/WEB-DL places are already taken.",
                    holders,
                    why="CRT keeps one basic and one full-featured remux/WEB-DL per edition; replace one only with a more complete release.",
                )
            return self.decision(
                Verdict.REVIEW,
                "A remux/WEB-DL is already on the site; yours might take the second place.",
                holders,
                why="CRT keeps one basic and one full-featured version; the full-featured one has more subtitles, commentary, extra audio or extras.",
            )

        if kind not in (ENCODE, DVDRIP):
            return self.decision(Verdict.REVIEW, "CRT's rules don't cover this kind of release.")

        codec = self.require(upload.codec, "video codec")
        if codec not in (H264, H265):
            return self.decision(Verdict.REVIEW, "CRT's rules only cover H.264 and H.265 encodes.")

        notes: list[str] = []
        if res in (SD, "720p"):
            notes.append("Encodes at this resolution are only allowed when the edition is not available at a higher resolution.")
        holders = [profile for profile in same_edition if profile.kind in (ENCODE, DVDRIP) and profile.codec == codec]
        if not holders:
            if notes:
                return self.decision(Verdict.REVIEW, "The encode slot is free, but this resolution is only allowed when no higher-resolution version exists.", notes=notes)
            return self.decision(Verdict.ALLOW, "No encode with this codec is on the site at this resolution yet.")
        if any(is_repack_of(upload, profile) for profile in holders):
            return self.decision(Verdict.ALLOW, "Your REPACK/PROPER replaces the original. Report it as a trump after uploading.", holders)
        return self.decision(
            Verdict.REVIEW,
            "An encode with this codec is already on the site.",
            holders,
            notes,
        )
