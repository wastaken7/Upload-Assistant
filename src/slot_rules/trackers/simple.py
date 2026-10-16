# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Trackers whose rules refuse little more than an exact copy of an existing release."""

from collections.abc import Sequence

from src.slot_rules.base import SlotRules
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import SD, ReleaseProfile


class TorrentLeechSlotRules(SlotRules):
    """TorrentLeech has no dupe slots: anything that is not the same release may be uploaded."""

    TRACKER = "TORRENTLEECH"

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:  # noqa: ARG002
        return self.decision(Verdict.ALLOW, "TorrentLeech has no slot limits.", why="Only an exact copy of a release already on the site is refused.")


class DreadVaultSlotRules(SlotRules):
    """DreadVault has no slots yet; only an exact duplicate is refused (rules page, 2026-10-15)."""

    TRACKER = "DREADVAULT"

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:  # noqa: ARG002
        return self.decision(Verdict.ALLOW, "DreadVault has no slot limits.", why="Only an exact copy of a release already on the site is refused.")


class MTeamSlotRules(SlotRules):
    """M-Team (發佈規則 "轉種需知", 2026-10-15).

    The same content from a different group, with a different video codec or at a
    different resolution may all be posted. A DUPE is the same content with the
    same size; the older torrent stays.
    """

    TRACKER = "MTEAM"

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        same_size = [profile for profile in existing if upload.size and profile.size == upload.size]
        if same_size:
            return self.decision(Verdict.BLOCK, "A torrent with the same content and size is already on the site.", same_size)
        matching: list[ReleaseProfile] = []
        unknown: list[ReleaseProfile] = []
        for profile in existing:
            if profile.resolution != upload.resolution or profile.codec != upload.codec:
                continue
            if profile.group is None or upload.group is None:
                unknown.append(profile)
            elif profile.group == upload.group:
                matching.append(profile)
        if matching:
            return self.decision(Verdict.BLOCK, "This group's release with the same resolution and codec is already on the site.", matching)
        if unknown:
            return self.decision(Verdict.REVIEW, "The release group of a torrent on the site could not be compared.", unknown)
        return self.decision(
            Verdict.ALLOW, "No release from your group with this codec is on the site.", why="M-Team allows the same content from a different group, video codec or resolution."
        )


class SeedpoolSlotRules(SlotRules):
    """Seedpool has minimal trumping: users choose the version they want."""

    TRACKER = "SEEDPOOL"

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:  # noqa: ARG002
        if upload.resolution in (SD, "720p"):
            return self.decision(
                Verdict.REVIEW,
                "Seedpool only allows releases below 1080p in some cases.",
                why="Below 1080p is only allowed for anime, full DVDs, or when no higher resolution exists; the search only looked at your resolution.",
            )
        return self.decision(Verdict.ALLOW, "Seedpool has no slot limits.", why="Any version is allowed unless it is the same release or already replaced by one on the site.")
