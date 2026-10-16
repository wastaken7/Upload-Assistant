# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any


class Verdict(Enum):
    ALLOW = "allow"
    BLOCK = "block"
    REVIEW = "review"


@dataclass
class SlotDecision:
    """Recommendation produced by a tracker's slot rules for one upload."""

    verdict: Verdict
    # One plain sentence saying what was found.
    reason: str
    tracker: str
    rules_date: date
    # Readable name of the slot the upload goes in, when the tracker uses slots.
    slot: str = ""
    # The tracker rule behind the verdict, in plain words.
    why: str = ""
    # Existing torrents that hold (or compete for) the upload's slot.
    conflicts: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    notes: list[str] = field(default_factory=lambda: list[str]())
