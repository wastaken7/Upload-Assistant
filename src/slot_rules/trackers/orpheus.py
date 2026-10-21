# Upload Assistant © 2026 Audionut & wastaken7 — Licensed under UAPL v1.0
"""Orpheus: music dupe and trump rules (upload rules 2.2, 2.5, 2.6.2 and 2.10).

Music has no video-style slots: within one release group, each edition and
source medium holds one torrent per format and bitrate, and better rips or
preferred encodes replace older ones.  Orpheus search results are turned into
``MusicTorrent`` values by the tracker class and compared here.
"""

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from enum import Enum
from typing import Any

from src.slot_rules.base import SlotRules
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.profile import ReleaseProfile

# Rules transcribed from rules.php?p=upload on this date.
RULES_DATE_2026_10_21 = date(2026, 10, 21)
# Meta key where the Orpheus search stores its decision for ``evaluate_slots``.
SLOT_DECISION_KEY = "ORPHEUS_slot_decision"

LOSSLESS_24 = "24bit Lossless"
CASSETTE = "cassette"
VINYL = "vinyl"
# Unofficial live recordings have a single edition (rule 2.6.2).
SINGLE_EDITION_RELEASE_TYPES = frozenset({"bootleg"})
SINGLE_EDITION_MEDIA = frozenset({"soundboard"})
CASSETTE_BLOCKED = (
    "Cassette releases may not be uploaded when the release exists in any other format, unless the cassette has exclusive bonus tracks (rules 2.10.1.1 and 2.10.4)."
)
CASSETTE_TRUMPED = "A release from any other medium replaces a cassette rip, unless the cassette has exclusive bonus tracks (rule 2.10.4)."


@dataclass(frozen=True)
class MusicEdition:
    """Release information of a torrent: an Unknown Release, or year/label/catalogue/title."""

    unknown: bool
    year: str = ""
    label: str = ""
    catalogue: str = ""
    title: str = ""


@dataclass(frozen=True)
class MusicTorrent:
    """One upload or existing torrent, as far as the dupe and trump rules need it."""

    media: str
    format: str
    encoding: str
    edition: MusicEdition
    # Highest sample rate in Hz; ``None`` when it is not known.
    sample_rate: int | None = None
    has_log: bool = False
    # Rip log score; ``None`` when there is no log or it was not scored.
    log_score: int | None = None
    has_cue: bool = False
    scene: bool = False
    # Reasons the site itself lists for marking the torrent trumpable.
    trumpable_reasons: tuple[str, ...] = ()
    entry: Mapping[str, Any] = field(default_factory=lambda: dict[str, Any](), compare=False, hash=False)

    @property
    def is_24bit(self) -> bool:
        return self.encoding == LOSSLESS_24

    @property
    def label(self) -> str:
        return f"{self.media} {self.format} {self.encoding}".strip()


class Outcome(Enum):
    COEXIST = "coexist"
    DUPE = "dupe"
    TRUMPS = "trumps"
    REVIEW = "review"


type Comparison = tuple[Outcome, str]


def normalise(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value or "").casefold())


def catalogue_keys(value: Any) -> set[str]:
    """Normalise one or more catalogue numbers (``A & B``, ``A / B``)."""
    return {key for part in re.split(r"\s*(?:&|/|,|;)\s*", str(value or "")) if (key := normalise(part))}


def edition_relation(upload: MusicEdition, existing: MusicEdition) -> str:
    """``same``, ``same_year``, ``other``, ``upload_unknown`` or ``existing_unknown``.

    Editions are defined by the audio (rip log TOC and peaks), not catalogue
    data, so two releases of one edition are dupes (rule 2.2.11.2).  A shared
    catalogue number, or both being Unknown Release, is treated as the same release.
    """
    if upload.unknown or existing.unknown:
        if upload.unknown and existing.unknown:
            return "same"
        return "upload_unknown" if upload.unknown else "existing_unknown"
    ours = catalogue_keys(upload.catalogue)
    if ours and ours & catalogue_keys(existing.catalogue):
        return "same"
    if upload.year and upload.year == existing.year:
        if normalise(upload.label) == normalise(existing.label) and normalise(upload.title) == normalise(existing.title) and not ours and not existing.catalogue:
            return "same"
        return "same_year"
    return "other"


# ----------------------------------------------------------------------
# Lossy encodings (rule 2.2.9)
# ----------------------------------------------------------------------

_PRESETS = {"V0 (VBR)": "v0", "APX (VBR)": "apx", "V1 (VBR)": "v1", "V2 (VBR)": "v2", "APS (VBR)": "aps"}


def lossy_kind(encoding: str) -> tuple[str, int]:
    """``(kind, bitrate)``: a LAME preset, or ``cbr``/``abr``/``vbr`` with a bitrate; ``unknown`` otherwise."""
    value = encoding.strip()
    if value in _PRESETS:
        return _PRESETS[value], 0
    number = re.match(r"(\d+(?:\.\d+)?)", value)
    if not number:
        return "unknown", 0
    rate = round(float(number.group(1)))
    if "VBR" in value.upper():
        return "vbr", rate
    return ("abr" if "ABR" in value.upper() else "cbr"), rate


def _lossy_beats(kind: str, rate: int, other: str, other_rate: int, *, lame: bool) -> bool:
    if lame and kind in {"v0", "apx"}:
        # 2.2.9.5 and 2.2.9.8: V0 > APX, and both replace CBR under 320, all ABR, V1, V2, APS and non-preset VBR of 192+.
        if kind == "v0" and other == "apx":
            return True
        return other in {"v1", "v2", "aps", "abr"} or (other == "cbr" and other_rate < 320) or (other == "vbr" and other_rate >= 192)
    if lame and kind in {"v2", "aps"}:
        # 2.2.9.4 and 2.2.9.8: V2 > APS, and both replace CBR under 256, 192 ABR and 192-210 VBR.
        if kind == "v2" and other == "aps":
            return True
        return (other == "cbr" and other_rate < 256) or (other == "abr" and other_rate <= 192) or (other == "vbr" and other_rate <= 210)
    if not lame and kind == "cbr" and rate >= 256 and other == "vbr":
        # 2.2.9.10: VBR AAC is replaced by 256 CBR.
        return True
    # 2.2.9.1: higher CBR/ABR replaces lower, interchangeably.
    return kind in {"cbr", "abr"} and other in {"cbr", "abr"} and rate > other_rate


def lossy_relation(ours: str, theirs: str, *, lame: bool = True) -> str:
    """``dupe``, ``trumps``, ``trumped``, ``coexists`` or ``unknown`` for two encodes of one format."""
    if ours.strip() == theirs.strip():
        return "dupe"
    our_kind, our_rate = lossy_kind(ours)
    their_kind, their_rate = lossy_kind(theirs)
    if "unknown" in {our_kind, their_kind}:
        return "unknown"
    # 2.2.9.3: V0 and 320 CBR may always coexist.
    if lame and {our_kind, their_kind} == {"v0", "cbr"} and 320 in {our_rate, their_rate}:
        return "coexists"
    if _lossy_beats(our_kind, our_rate, their_kind, their_rate, lame=lame):
        return "trumps"
    if _lossy_beats(their_kind, their_rate, our_kind, our_rate, lame=lame):
        return "trumped"
    if our_kind in {"cbr", "abr"} and their_kind in {"cbr", "abr"} and our_rate == their_rate:
        return "dupe"
    # 2.2.9.7: non-preset VBR of similar bitrate are dupes (224 and 256 are similar).
    if our_kind == their_kind == "vbr" and abs(our_rate - their_rate) <= 32:
        return "dupe"
    # 2.2.9.9: AAC profiles at the same bitrate are dupes.
    if not lame and our_rate and our_rate == their_rate:
        return "dupe"
    return "coexists"


# ----------------------------------------------------------------------
# Lossless (rules 2.1.23.3, 2.2.10, 2.5.3 and 2.5.4)
# ----------------------------------------------------------------------


_RATES = {"44.1": 44_100, "48": 48_000, "88.2": 88_200, "96": 96_000, "176.4": 176_400, "192": 192_000}
_RATE = r"(44\.1|48|88\.2|96|176\.4|192)"
_RATE_PATTERNS = (
    re.compile(rf"(?<![\d.]){_RATE}\s*-?\s*k(?:hz)?\b", re.I),  # "96kHz", "96 kHz", "96k"
    re.compile(rf"(?<![\d.])(?:16|24)\s*(?:-?\s*bits?|b)?\s*[-/ ]\s*{_RATE}(?![\d.])", re.I),  # "24-96", "24bit/96", "24B-96"
)


def sample_rate_hint(*texts: Any) -> int | None:
    """Sample rate written in a folder name or description; ``None`` when absent or ambiguous.

    Texts are tried in order, so a folder name wins over a description that
    may also mention the rate of the original source.
    """
    for text in texts:
        found = {_RATES[match.group(1)] for pattern in _RATE_PATTERNS for match in pattern.finditer(str(text or ""))}
        if found:
            return found.pop() if len(found) == 1 else None
    return None


def sample_rate_tier(rate: int | None) -> int | None:
    """24-bit tiers: 0 = 44.1/48 kHz, 1 = 88.2/96 kHz, 2 = 176.4/192 kHz (rule 2.1.23.3)."""
    if not rate:
        return None
    if rate <= 48_000:
        return 0
    if rate <= 96_000:
        return 1
    return 2


def khz(rate: int | None) -> str:
    return f"{rate / 1000:g} kHz" if rate else "an unknown sample rate"


def _vinyl_24bit(upload: MusicTorrent, existing: MusicTorrent) -> Comparison:
    """Rule 2.5.4: one 24/192 rip and one 24-bit rip at 96 kHz or lower; 24/96 replaces 44.1-88.2 kHz."""
    if upload.sample_rate is None or existing.sample_rate is None:
        return Outcome.REVIEW, "Vinyl allows one 24/192 rip and one 24-bit rip at 96 kHz or lower; the sample rate of one of them is unknown (rule 2.5.4)."
    our_slot, their_slot = upload.sample_rate >= 192_000, existing.sample_rate >= 192_000
    if our_slot != their_slot:
        return Outcome.COEXIST, ""
    if not our_slot and upload.sample_rate == 96_000 and existing.sample_rate < 96_000:
        return Outcome.TRUMPS, "A 24/96 vinyl rip replaces 24/44.1, 24/48 and 24/88.2 rips if it sounds as good or better (rule 2.5.4)."
    return (
        Outcome.DUPE,
        "Only one 24-bit vinyl rip per sample rate slot is allowed; a better-sounding rip may replace it only with a report proving it (rules 2.5.4 and 2.5.5).",
    )


def _digital_24bit(upload: MusicTorrent, existing: MusicTorrent) -> Comparison:
    """Rules 2.1.23.3.2 and 2.2.10.11: the first lossless torrent stays, but 88.2/96 kHz replaces 44.1/48 kHz."""
    ours, theirs = sample_rate_tier(upload.sample_rate), sample_rate_tier(existing.sample_rate)
    if ours is None:
        return Outcome.REVIEW, "The sample rate of your files is unknown; 24-bit FLAC dupes depend on sample rate tiers (rule 2.1.23.3)."
    if theirs is None:
        if ours == 0:
            return Outcome.DUPE, "A 24-bit FLAC already exists; 24-bit at 44.1/48 kHz cannot replace it (rules 2.1.23.3.2 and 2.2.10.11)."
        return Outcome.REVIEW, (
            f"Your 24-bit FLAC is {khz(upload.sample_rate)}; the sample rate of the existing one is unknown. "
            "24-bit at 88.2/96 kHz replaces 24-bit at 44.1/48 kHz, otherwise the first upload stays (rules 2.1.23.3.2 and 2.2.10.11)."
        )
    if ours == 1 and theirs == 0:
        return Outcome.TRUMPS, "24-bit FLAC at 88.2/96 kHz replaces 24-bit FLAC at 44.1/48 kHz (rule 2.1.23.3.2)."
    if ours == 2 and theirs == 0:
        return Outcome.REVIEW, "The rules only say 88.2/96 kHz replaces 24-bit 44.1/48 kHz; for 176.4/192 kHz the first upload may stay (rule 2.2.10.11)."
    return Outcome.DUPE, "A 24-bit FLAC in the same or a higher sample rate tier exists; the first lossless upload stays (rules 2.1.23.3 and 2.2.10.11)."


def _log_trump(upload: MusicTorrent, existing: MusicTorrent) -> Comparison | None:
    """CD rip logs (rules 2.2.10.2 to 2.2.10.5); ``None`` when logs do not decide it."""
    if not upload.has_log:
        return None
    score = upload.log_score
    if not existing.has_log:
        if score == 100:
            return Outcome.TRUMPS, "A FLAC with a 100% log from EAC, XLD or whipper replaces one without a log (rule 2.2.10.2)."
        return Outcome.REVIEW, (
            "The existing FLAC has no log. Yours replaces it if it comes from EAC, XLD or whipper and scores 100%, or loses points only for non-audio reasons (rule 2.2.10.2)."
        )
    their_score = existing.log_score or 0
    if their_score >= 100:
        if upload.has_cue and not existing.has_cue:
            return Outcome.REVIEW, (
                "Both logs score 100%. A rip with a cue sheet replaces one without only if the cue adds something the log doesn't "
                "(indices, pre-gaps, pre-emphasis; rule 2.2.10.5.1)."
            )
        return None
    if score == 100:
        return Outcome.TRUMPS, f"A FLAC whose log scores 100% replaces one scoring {their_score}% (rule 2.2.10.3)."
    if score is None:
        return Outcome.REVIEW, f"The existing log scores {their_score}%. Yours replaces it only if it scores 100% (rule 2.2.10.3); run with --music-check-log to score it."
    return Outcome.REVIEW, (
        f"Your log scores {score}% and the existing one {their_score}%. A log under 100% cannot replace another under 100%, "
        "unless yours has only non-audio deductions and theirs has audio deductions (rules 2.2.10.3 and 2.2.10.4)."
    )


def _same_slot_trump(upload: MusicTorrent, existing: MusicTorrent, dupe_reason: str) -> Comparison:
    """A lossless torrent already fills the slot: check what may still replace it."""
    if existing.media.casefold() == "cd":
        logs = _log_trump(upload, existing)
        if logs is not None:
            return logs
    if existing.scene:
        return Outcome.REVIEW, "The existing torrent is a scene release; a properly de-scened version or a new rip replaces it (rule 2.2.5)."
    if existing.trumpable_reasons:
        return Outcome.REVIEW, f"The site marks the existing torrent trumpable ({'; '.join(existing.trumpable_reasons)}); yours replaces it if it fixes that."
    return Outcome.DUPE, dupe_reason


def compare_lossless(upload: MusicTorrent, existing: MusicTorrent) -> Comparison:
    if upload.is_24bit != existing.is_24bit:
        return Outcome.COEXIST, ""
    vinyl = upload.media.casefold() == VINYL
    if upload.is_24bit:
        outcome, reason = _vinyl_24bit(upload, existing) if vinyl else _digital_24bit(upload, existing)
    elif vinyl:
        outcome, reason = (
            Outcome.DUPE,
            "Only one 16-bit lossless vinyl rip is allowed per edition; a better-sounding rip may replace it only with a report proving it (rules 2.5.3 and 2.5.5).",
        )
    else:
        outcome, reason = Outcome.DUPE, "A 16-bit FLAC already exists; other sample rates of the same release are dupes (rules 2.2.2 and 2.2.10.11)."
    if outcome is not Outcome.DUPE:
        return outcome, reason
    return _same_slot_trump(upload, existing, reason)


def compare_lossy(upload: MusicTorrent, existing: MusicTorrent) -> Comparison:
    lame = upload.format == "MP3"
    relation = lossy_relation(upload.encoding, existing.encoding, lame=lame)
    if relation == "unknown":
        return Outcome.REVIEW, f"Could not compare {upload.encoding or 'your encoding'} with {existing.encoding or 'an unknown encoding'} (rule 2.2.9)."
    if relation == "trumps":
        return Outcome.TRUMPS, f"{upload.encoding} replaces {existing.encoding} (rule 2.2.9)."
    if relation == "coexists":
        return Outcome.COEXIST, ""
    if relation == "trumped":
        return Outcome.DUPE, f"{existing.encoding} already exists and is preferred over {upload.encoding} (rule 2.2.9)."
    if existing.scene:
        return Outcome.REVIEW, "The existing torrent is a scene release; a properly de-scened version or a new encode replaces it (rule 2.2.5)."
    if existing.trumpable_reasons:
        return Outcome.REVIEW, f"The site marks the existing torrent trumpable ({'; '.join(existing.trumpable_reasons)}); yours replaces it if it fixes that."
    return Outcome.DUPE, f"{existing.encoding} already exists; a log, cue or artwork does not make a lossy torrent a replacement (rules 2.2.2 and 2.2.9.2)."


def compare(upload: MusicTorrent, existing: MusicTorrent) -> Comparison:
    """Compare two torrents of the same medium and edition."""
    if upload.format != existing.format:
        # 2.2.9.11: an AAC encode can be replaced by another allowed encode of the same medium and edition.
        if existing.format == "AAC" and upload.format == "MP3":
            if upload.media.casefold() == "web":
                return Outcome.REVIEW, "For WEB, whether an MP3 replaces an AAC is decided by a moderator comparing quality and source (rule 2.2.9.11)."
            return Outcome.TRUMPS, "An allowed encode replaces an AAC of the same medium and edition (rule 2.2.9.11)."
        if upload.format == "AAC" and existing.format == "MP3":
            return Outcome.REVIEW, "An AAC can be replaced by any allowed encode of the same medium and edition, and an MP3 already exists (rule 2.2.9.11)."
        return Outcome.COEXIST, ""
    if upload.format == "FLAC":
        return compare_lossless(upload, existing)
    if upload.format in {"MP3", "AAC"}:
        return compare_lossy(upload, existing)
    if upload.encoding == existing.encoding:
        return Outcome.DUPE, f"{existing.format} {existing.encoding} already exists (rule 2.2.2)."
    return Outcome.COEXIST, ""


def _with_edition(relation: str, upload: MusicTorrent, existing: MusicTorrent, result: Comparison) -> Comparison:
    """Adjust a comparison for torrents whose release information differs."""
    outcome, reason = result
    if relation == "same" or outcome is Outcome.COEXIST:
        return result
    if relation == "other":
        # Different years are usually different editions; they coexist unless the audio is the same (rule 2.2.11.2).
        return Outcome.COEXIST, ""
    if relation == "same_year":
        if outcome is Outcome.TRUMPS:
            return Outcome.COEXIST, ""
        return Outcome.REVIEW, (
            "A release from the same year with other label or catalogue information has this format. "
            f"Releases of one edition are dupes unless the audio differs; compare rip logs (TOC, peaks) (rule 2.2.11.2). {reason}"
        ).strip()
    if relation == "upload_unknown":
        return Outcome.REVIEW, (
            "Yours is an Unknown Release and a torrent with release information has this format. An Unknown Release is replaced by one "
            "with verified release information from the same medium, tracklist and running order (rules 2.2.11.5 to 2.2.11.8)."
        )
    # The existing torrent is an Unknown Release and the upload has release information.
    if upload.format == "FLAC" and existing.has_log and existing.media.casefold() == "cd":
        return Outcome.REVIEW, ("The existing FLAC is an Unknown Release with a rip log. It is replaced only if staff can match its log to your edition (rule 2.2.11.5).")
    if outcome is Outcome.REVIEW:
        return result
    if outcome is Outcome.DUPE and upload.encoding != existing.encoding:
        # The existing encode is preferred (for example V0 over V2); release information doesn't change that.
        return result
    if outcome is Outcome.DUPE and upload.is_24bit:
        ours, theirs = sample_rate_tier(upload.sample_rate), sample_rate_tier(existing.sample_rate)
        if ours is None or theirs is None:
            return Outcome.REVIEW, f"{reason} The existing torrent is an Unknown Release, but its sample rate is unknown, so it can't be confirmed as the same encode."
        if ours != theirs:
            return result
    return Outcome.TRUMPS, (
        "Your torrent has verified release information and replaces an Unknown Release from the same medium with the same tracklist "
        "and running order (rules 2.2.11.4, 2.2.11.6 and 2.2.11.8)."
    )


class OrpheusSlotRules(SlotRules):
    """Dupe and trump rules for one Orpheus release group."""

    TRACKER = "ORPHEUS"
    RULES_DATE = RULES_DATE_2026_10_21

    def decide(self, upload: ReleaseProfile, existing: Sequence[ReleaseProfile]) -> SlotDecision | None:  # noqa: ARG002
        # Music is compared with ``evaluate_music``; video profiles never reach Orpheus.
        return None

    def assess(self, upload: MusicTorrent, existing: Sequence[MusicTorrent], *, release_type: str = "") -> tuple[list[tuple[MusicTorrent, Outcome, str]], list[str]]:
        """Compare the upload with each existing torrent: ``([(torrent, outcome, reason)], notes)``."""
        media = upload.media.casefold()
        single_edition = release_type.casefold() in SINGLE_EDITION_RELEASE_TYPES or media in SINGLE_EDITION_MEDIA
        notes = ["Unofficial live recordings have one edition, so release information doesn't separate them (rule 2.6.2)."] if single_edition else []
        results: list[tuple[MusicTorrent, Outcome, str]] = []
        for torrent in existing:
            their_media = torrent.media.casefold()
            relation = "same" if single_edition else edition_relation(upload.edition, torrent.edition)
            if media == CASSETTE and their_media != CASSETTE:
                # A cassette of another release may still carry content found nowhere else.
                results.append((torrent, Outcome.DUPE, CASSETTE_BLOCKED) if relation == "same" else (torrent, Outcome.REVIEW, CASSETTE_BLOCKED))
                continue
            if their_media == CASSETTE and media != CASSETTE:
                # Cassettes of other releases that already coexist with other media are left alone.
                results.append((torrent, Outcome.TRUMPS, CASSETTE_TRUMPED) if relation == "same" else (torrent, Outcome.COEXIST, ""))
                continue
            if their_media != media:
                results.append((torrent, Outcome.COEXIST, ""))
                continue
            if relation == "same" and upload.edition.year and torrent.edition.year and upload.edition.year != torrent.edition.year:
                note = f"The site lists catalogue {torrent.edition.catalogue} as {torrent.edition.year}; check your edition year."
                notes += [] if note in notes else [note]
            results.append((torrent, *_with_edition(relation, upload, torrent, compare(upload, torrent))))
        return results, notes

    def evaluate_music(self, upload: MusicTorrent, existing: Sequence[MusicTorrent], *, release_type: str = "") -> SlotDecision:
        slot = upload.label
        if not upload.format or not upload.encoding:
            return self.decision(
                Verdict.REVIEW, "The format or bitrate of your files could not be determined.", slot=slot, why="Orpheus torrents must contain a single format (rule 2.1.5)."
            )
        results, notes = self.assess(upload, existing, release_type=release_type)
        dupes = [(torrent, reason) for torrent, outcome, reason in results if outcome is Outcome.DUPE]
        reviews = [(torrent, reason) for torrent, outcome, reason in results if outcome is Outcome.REVIEW]
        trumps = [(torrent, reason) for torrent, outcome, reason in results if outcome is Outcome.TRUMPS]
        if dupes:
            other_medium = dupes[0][1] == CASSETTE_BLOCKED
            reason = "This release is already on the site from another medium." if other_medium else "This format and bitrate is already on the site for this edition."
            return self.decision(Verdict.BLOCK, reason, [t for t, _ in dupes], notes, slot=slot, why=dupes[0][1])
        if reviews:
            return self.decision(
                Verdict.REVIEW,
                "A torrent on the site may already cover this upload.",
                [t for t, _ in reviews],
                [*notes, *(reason for _, reason in reviews[1:2] if reason != reviews[0][1])],
                slot=slot,
                why=reviews[0][1],
            )
        if trumps:
            return self.decision(
                Verdict.ALLOW,
                "Your upload replaces a torrent on the site. Report the old torrent with a link to yours after uploading (rule 2.2.3).",
                [t for t, _ in trumps],
                notes,
                slot=slot,
                why=" ".join(dict.fromkeys(reason for _, reason in trumps)),
            )
        return self.decision(Verdict.ALLOW, "No torrent on the site holds this format and bitrate for your edition and medium.", notes=notes, slot=slot)
