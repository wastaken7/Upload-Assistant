# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Shared machinery for tracker slot rules."""

from collections.abc import Callable, Mapping, Sequence
from datetime import date
from typing import Any, ClassVar, Protocol

from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import DISC, DV, HDR10, HDR10P, HLG, PQ10, WEBDL, WEBRIP, ReleaseProfile

# Rules transcribed from the tracker pages on this date.
RULES_DATE_2026_10_15 = date(2026, 10, 15)

type SlotKey = tuple[object, ...]
# Returns a verdict and reason when the upload competes with an occupant of its slot.
type TrumpTest = Callable[[ReleaseProfile, ReleaseProfile], tuple[Verdict, str]]


class HasEntry(Protocol):
    """Anything built from a search result, such as a ``ReleaseProfile``."""

    @property
    def entry(self) -> Mapping[str, Any]: ...


class UnknownTraitError(Exception):
    """A trait the rule needs could not be determined; the user has to decide."""


def hdr_rank(profile: ReleaseProfile) -> int:
    """Rank HDR packages within one HDR slot: DV+HDR10+ > DV+HDR10 / HDR10+ > HDR10 > PQ10."""
    hdr = profile.hdr or frozenset()
    if DV in hdr and HDR10P in hdr:
        return 4
    if (DV in hdr and HDR10 in hdr) or HDR10P in hdr:
        return 3
    if HDR10 in hdr:
        return 2
    if PQ10 in hdr or HLG in hdr:
        return 1
    return 0


def expanded_hdr(profile: ReleaseProfile) -> frozenset[str]:
    """HDR flags including implied layers: HDR10+ always carries an HDR10 base layer."""
    hdr = profile.hdr or frozenset()
    return hdr | {HDR10} if HDR10P in hdr else hdr


def size_diff_ratio(first: ReleaseProfile, second: ReleaseProfile) -> float | None:
    """Size difference relative to the larger release (0.2 means 20% smaller)."""
    if not first.size or not second.size:
        return None
    larger = max(first.size, second.size)
    return abs(first.size - second.size) / larger


def _repack_traits(profile: ReleaseProfile) -> tuple[object, ...]:
    """Traits that identify a release; None means unknown. WEB releases are also identified by provider."""
    if profile.kind is None:
        provider: object = None
    elif profile.kind in (WEBDL, WEBRIP):
        provider = profile.provider
    else:
        provider = "not WEB"
    return (profile.resolution, profile.kind, profile.codec, profile.hdr, provider)


def _newer_from_same_group(upload: ReleaseProfile, existing: ReleaseProfile) -> bool:
    return bool(upload.group and upload.group == existing.group and upload.repack > existing.repack and upload.edition == existing.edition)


def is_repack_of(upload: ReleaseProfile, existing: ReleaseProfile) -> bool:
    """``upload`` is a confirmed newer REPACK/PROPER of the same release: same group, edition and format."""
    traits = zip(_repack_traits(upload), _repack_traits(existing), strict=True)
    return _newer_from_same_group(upload, existing) and all(first is not None and first == second for first, second in traits)


def may_be_repack_of(upload: ReleaseProfile, existing: ReleaseProfile) -> bool:
    """Like ``is_repack_of``, but some format traits are unknown, so it cannot be confirmed."""
    if not _newer_from_same_group(upload, existing):
        return False
    traits = list(zip(_repack_traits(upload), _repack_traits(existing), strict=True))
    has_unknown = any(first is None or second is None for first, second in traits)
    return has_unknown and all(first is None or second is None or first == second for first, second in traits)


_LABEL_WORDS = {"H264": "H.264", "H265": "H.265", "encode": "Encode", "x264 encode": "x264 Encode", "x265 encode": "x265 Encode"}


def slot_label(key: SlotKey) -> str:
    """Readable slot name from the text parts of a slot key, e.g. "1080p · WEB-DL · AMZN · H.264"."""
    return " · ".join(_LABEL_WORDS.get(part, part) for part in key if isinstance(part, str) and part)


REPACK_REASON = "A REPACK/PROPER replaces the original release from the same group."


class SlotRules:
    """Base class: subclasses set the class attributes and implement ``decide``."""

    TRACKER: ClassVar[str] = ""
    RULES_DATE: ClassVar[date] = RULES_DATE_2026_10_15

    def __init__(self, meta: Any = None) -> None:
        # Upload metadata, for rules that use tracker data stored during the search.
        self.meta = meta

    def decision(
        self,
        verdict: Verdict,
        reason: str,
        conflicts: Sequence[HasEntry] = (),
        notes: Sequence[str] = (),
        *,
        slot: str = "",
        why: str = "",
    ) -> SlotDecision:
        return SlotDecision(
            verdict=verdict,
            reason=reason,
            tracker=self.TRACKER,
            rules_date=self.RULES_DATE,
            slot=slot,
            why=why,
            conflicts=[dict(conflict.entry) for conflict in conflicts],
            notes=list(notes),
        )

    def evaluate(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        """Return a recommendation, or ``None`` to leave the decision to the basic dupe check."""
        if upload.kind == DISC:
            return None
        exact = [profile for profile in existing if profile.exact]
        if exact:
            return self.decision(Verdict.BLOCK, "This exact release is already on the site.", exact)
        newer = [profile for profile in existing if is_repack_of(profile, upload)]
        if newer:
            return self.decision(Verdict.BLOCK, "A newer REPACK/PROPER of this release is already on the site.", newer)
        possibly_newer = [profile for profile in existing if may_be_repack_of(profile, upload)]
        if possibly_newer:
            return self.decision(
                Verdict.REVIEW,
                "A newer REPACK/PROPER from the same group may already be on the site.",
                possibly_newer,
                why="Its name is missing the resolution, type, codec or HDR, so it could not be confirmed as the same release.",
            )
        try:
            return self.decide(upload, [profile for profile in existing if profile.kind != DISC])
        except UnknownTraitError as e:
            return self.decision(Verdict.REVIEW, "This check is missing a detail it needs.", why=str(e))

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:
        raise NotImplementedError

    @staticmethod
    def require[T](value: T | None, what: str) -> T:
        if value is None:
            raise UnknownTraitError(f"Could not determine the {what}.")
        return value

    def by_slot(
        self,
        upload: ReleaseProfile,
        existing: Sequence[ReleaseProfile],
        key: Callable[[ReleaseProfile], SlotKey | None],
        label: str,
        *,
        trump: TrumpTest | None = None,
        coexists: Callable[[ReleaseProfile, ReleaseProfile], bool] | None = None,
        capacity: int = 1,
        notes: Sequence[str] = (),
    ) -> SlotDecision:
        """Decide using a slot key: releases with the same key compete for ``capacity`` places.

        ``key`` returns ``None`` when the release has no slot (it never competes).
        It may raise ``UnknownTraitError``; for the upload that makes the result REVIEW,
        for an existing release the unknown entries are listed for review.
        """
        upload_key = key(upload)
        if upload_key is None:
            return self.decision(Verdict.ALLOW, "This kind of release has no slot limit on this tracker.", notes=notes)

        occupants: list[ReleaseProfile] = []
        unknown: list[ReleaseProfile] = []
        for profile in existing:
            try:
                if key(profile) == upload_key:
                    occupants.append(profile)
            except UnknownTraitError:
                unknown.append(profile)

        if not occupants:
            if unknown:
                return self.decision(
                    Verdict.REVIEW,
                    "The slot looks free, but some releases on the site could not be identified.",
                    unknown,
                    notes,
                    slot=label,
                    why="Their names or MediaInfo are missing details this check needs; compare them yourself.",
                )
            return self.decision(Verdict.ALLOW, "No release on the site is using this slot yet.", notes=notes, slot=label)

        competing = [profile for profile in occupants if not (coexists and coexists(upload, profile))]
        if not competing:
            if len(occupants) >= capacity:
                return self.decision(Verdict.BLOCK, f"All {capacity} places in this slot are already taken.", occupants, notes, slot=label)
            return self.decision(
                Verdict.ALLOW,
                "There is still room in this slot, and your release is different enough from the one there.",
                notes=notes,
                slot=label,
            )

        test = trump or self.default_trump
        results = [(profile, *test(upload, profile)) for profile in competing]
        blocking = [(profile, reason) for profile, verdict, reason in results if verdict is Verdict.BLOCK]
        if blocking:
            why = next((reason for _, reason in blocking if reason), "")
            return self.decision(Verdict.BLOCK, "Another release already fills this slot.", [profile for profile, _ in blocking], notes, slot=label, why=why)
        reviewing = [(profile, reason) for profile, verdict, reason in results if verdict is Verdict.REVIEW]
        if reviewing:
            return self.decision(
                Verdict.REVIEW,
                "A release already fills this slot, but yours might still be accepted.",
                [profile for profile, _ in reviewing],
                notes,
                slot=label,
                why=reviewing[0][1],
            )
        reasons = " ".join(dict.fromkeys(reason for _, _, reason in results if reason))
        return self.decision(
            Verdict.ALLOW,
            "Your release can replace the one in this slot. Report it as a trump after uploading.",
            competing,
            notes,
            slot=label,
            why=reasons,
        )

    @staticmethod
    def default_trump(upload: ReleaseProfile, existing: ReleaseProfile) -> tuple[Verdict, str]:
        if is_repack_of(upload, existing):
            return Verdict.ALLOW, REPACK_REASON
        return Verdict.BLOCK, ""

    @staticmethod
    def hdr_trump(upload: ReleaseProfile, existing: ReleaseProfile) -> tuple[Verdict, str]:
        """Repack, or a strictly broader HDR package (for example DV/HDR over HDR), trumps."""
        if is_repack_of(upload, existing):
            return Verdict.ALLOW, REPACK_REASON
        if upload.hdr is not None and existing.hdr is not None and hdr_rank(upload) > hdr_rank(existing) and expanded_hdr(existing) <= expanded_hdr(upload):
            return Verdict.ALLOW, f"{upload.hdr_label} takes priority over {existing.hdr_label} in this slot."
        return Verdict.BLOCK, ""
