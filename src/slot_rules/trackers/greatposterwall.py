# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""GreatPosterWall: show the site's empty slots and leave the decision to the user."""

from collections.abc import Mapping, Sequence
from typing import Any, cast

from src.slot_rules.base import SlotRules
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import SD, ReleaseProfile

EMPTY_SLOTS_KEY = "GREATPOSTERWALL_empty_slots"


class GreatPosterWallSlotRules(SlotRules):
    """GPW's slots depend on embedded Chinese/English subtitles, Mandarin dubs and effect subtitles.

    Those can't be judged reliably from code, so this always asks the user, using
    the empty slots GPW itself lists on the torrent group page.
    """

    TRACKER = "GREATPOSTERWALL"

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        empty_by_resolution = cast(Mapping[str, list[str]], (self.meta.get(EMPTY_SLOTS_KEY) if self.meta is not None else None) or {})
        resolution = upload.resolution or ""
        lookup = "SD" if resolution == SD else resolution
        empty: list[Any] = list(empty_by_resolution.get(lookup, []))
        same_resolution = [profile for profile in existing if profile.resolution == upload.resolution]
        if empty:
            note = f"Empty {lookup} slots listed by GPW: {', '.join(str(slot) for slot in empty)}"
        elif empty_by_resolution:
            note = f"GPW lists no empty {lookup} slots for this title"
        else:
            note = "GPW's list of empty slots was not available"
        return self.decision(
            Verdict.REVIEW,
            "Check which GreatPosterWall slot your release fits.",
            same_resolution,
            [note],
            why="GPW slots depend on embedded Chinese/English subtitles, Mandarin dubs and effect subtitles, which this check can't judge.",
        )
