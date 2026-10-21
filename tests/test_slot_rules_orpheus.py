# ruff: noqa: S101
"""Orpheus music dupe and trump rules. Releases and labels are fictional."""

import asyncio
from datetime import date
from typing import Any

from src.meta import Meta
from src.slot_rules.models import SlotDecision, Verdict
from src.slot_rules.registry import evaluate_slots
from src.slot_rules.trackers.orpheus import (
    SLOT_DECISION_KEY,
    MusicEdition,
    MusicTorrent,
    OrpheusSlotRules,
    lossy_relation,
    sample_rate_hint,
)

ALLOW, BLOCK, REVIEW = Verdict.ALLOW, Verdict.BLOCK, Verdict.REVIEW
EDITION = MusicEdition(False, "2019", "Fictional Records", "FR-001")


def torrent(media: str = "CD", fmt: str = "FLAC", encoding: str = "Lossless", torrent_id: int = 1, **extra: Any) -> MusicTorrent:
    values: dict[str, Any] = {"edition": EDITION, "entry": {"id": torrent_id, "name": f"torrent {torrent_id}"}}
    values.update(extra)
    return MusicTorrent(media=media, format=fmt, encoding=encoding, **values)


def decide(upload: MusicTorrent, *existing: MusicTorrent, release_type: str = "") -> SlotDecision:
    return OrpheusSlotRules().evaluate_music(upload, list(existing), release_type=release_type)


def verdict(upload: MusicTorrent, *existing: MusicTorrent, release_type: str = "") -> Verdict:
    return decide(upload, *existing, release_type=release_type).verdict


def test_empty_group_and_other_formats_coexist():
    assert verdict(torrent()) is ALLOW
    assert verdict(torrent(), torrent(fmt="MP3", encoding="V0 (VBR)"), torrent(encoding="24bit Lossless", sample_rate=96_000)) is ALLOW


def test_other_media_and_editions_are_separate():
    assert verdict(torrent(), torrent(media="WEB")) is ALLOW
    other_year = MusicEdition(False, "2008", "Fictional Records", "FR-900")
    assert verdict(torrent(), torrent(edition=other_year)) is ALLOW


def test_same_year_with_other_catalogue_needs_review():
    same_year = MusicEdition(False, "2019", "Imaginary Imprint", "II-77")
    decision = decide(torrent(has_log=True, log_score=100), torrent(edition=same_year, has_log=True, log_score=100))
    assert decision.verdict is REVIEW
    assert "2.2.11.2" in decision.why


def test_shared_catalogue_is_the_same_release_and_notes_a_year_mismatch():
    listed_earlier = MusicEdition(False, "2018", "Fictional Records", "FR-001 / FR-002")
    decision = decide(torrent(media="WEB"), torrent(media="WEB", edition=listed_earlier))
    assert decision.verdict is BLOCK
    assert any("as 2018" in note for note in decision.notes)


def test_16bit_flac_sample_rates_are_dupes():
    assert verdict(torrent(media="WEB", sample_rate=48_000), torrent(media="WEB", sample_rate=44_100)) is BLOCK


def test_24bit_tiers():
    upload_96 = torrent(media="WEB", encoding="24bit Lossless", sample_rate=96_000)
    on_site_48 = torrent(media="WEB", encoding="24bit Lossless", sample_rate=48_000)
    decision = decide(upload_96, on_site_48)
    assert decision.verdict is ALLOW
    assert decision.conflicts == [{"id": 1, "name": "torrent 1"}]
    assert "2.1.23.3.2" in decision.why
    assert verdict(on_site_48, upload_96) is BLOCK
    assert verdict(torrent(media="WEB", encoding="24bit Lossless", sample_rate=192_000), upload_96) is BLOCK
    assert verdict(torrent(media="WEB", encoding="24bit Lossless", sample_rate=192_000), on_site_48) is REVIEW
    assert verdict(upload_96, torrent(media="WEB", encoding="24bit Lossless")) is REVIEW
    assert verdict(on_site_48, torrent(media="WEB", encoding="24bit Lossless")) is BLOCK


def test_vinyl_24bit_has_two_slots():
    def vinyl(rate: int, torrent_id: int = 1) -> MusicTorrent:
        return torrent(media="Vinyl", encoding="24bit Lossless", sample_rate=rate, torrent_id=torrent_id)

    assert verdict(vinyl(192_000), vinyl(96_000)) is ALLOW
    assert decide(vinyl(192_000), vinyl(96_000)).conflicts == []
    assert verdict(vinyl(96_000), vinyl(48_000)) is ALLOW
    assert decide(vinyl(96_000), vinyl(48_000)).conflicts
    assert verdict(vinyl(88_200), vinyl(48_000)) is BLOCK
    assert verdict(vinyl(96_000), vinyl(192_000), vinyl(96_000, 2)) is BLOCK
    assert verdict(torrent(media="Vinyl"), torrent(media="Vinyl", sample_rate=48_000)) is BLOCK


def test_cd_log_trumps():
    no_log = torrent()
    assert verdict(torrent(has_log=True, log_score=100), no_log) is ALLOW
    assert verdict(torrent(has_log=True), no_log) is REVIEW
    assert verdict(torrent(), no_log) is BLOCK
    assert verdict(torrent(has_log=True, log_score=100), torrent(has_log=True, log_score=80)) is ALLOW
    assert verdict(torrent(has_log=True, log_score=90), torrent(has_log=True, log_score=50)) is REVIEW
    assert verdict(torrent(has_log=True, log_score=100), torrent(has_log=True, log_score=100)) is BLOCK
    assert verdict(torrent(has_log=True, log_score=100, has_cue=True), torrent(has_log=True, log_score=100)) is REVIEW


def test_scene_and_site_flagged_torrents_may_be_replaced():
    assert verdict(torrent(media="WEB"), torrent(media="WEB", scene=True)) is REVIEW
    decision = decide(torrent(media="WEB"), torrent(media="WEB", trumpable_reasons=("bad tags",)))
    assert decision.verdict is REVIEW
    assert "bad tags" in decision.why


def test_lossy_relations():
    assert lossy_relation("V0 (VBR)", "V0 (VBR)") == "dupe"
    assert lossy_relation("V0 (VBR)", "APX (VBR)") == "trumps"
    assert lossy_relation("APS (VBR)", "V2 (VBR)") == "trumped"
    assert lossy_relation("V0 (VBR)", "V2 (VBR)") == "trumps"
    assert lossy_relation("320", "V0 (VBR)") == "coexists"
    assert lossy_relation("192", "V0 (VBR)") == "trumped"
    assert lossy_relation("320", "256") == "trumps"
    assert lossy_relation("320 (ABR)", "V0 (VBR)") == "trumped"
    assert lossy_relation("192", "256 (ABR)") == "trumped"
    assert lossy_relation("224 (VBR)", "256 (VBR)") == "dupe"
    assert lossy_relation("192 (VBR)", "256 (VBR)") == "coexists"
    assert lossy_relation("V1 (VBR)", "V0 (VBR)") == "trumped"
    assert lossy_relation("Other", "V0 (VBR)") == "unknown"


def test_aac_rules():
    assert lossy_relation("256", "256 (VBR)", lame=False) == "trumps"
    assert lossy_relation("256 (VBR)", "256", lame=False) == "trumped"
    mp3 = torrent(fmt="MP3", encoding="V0 (VBR)")
    aac = torrent(fmt="AAC", encoding="256")
    assert verdict(mp3, aac) is ALLOW
    assert verdict(torrent(media="WEB", fmt="MP3", encoding="V0 (VBR)"), torrent(media="WEB", fmt="AAC", encoding="256")) is REVIEW
    assert verdict(aac, mp3) is REVIEW


def test_lossy_extras_do_not_trump():
    assert verdict(torrent(fmt="MP3", encoding="V0 (VBR)", has_log=True, log_score=100), torrent(fmt="MP3", encoding="V0 (VBR)")) is BLOCK


def test_cassette_rules():
    tape = torrent(media="Cassette")
    decision = decide(tape, torrent(media="WEB", fmt="MP3", encoding="320"))
    assert decision.verdict is BLOCK
    assert "2.10.1.1" in decision.why
    reissue = MusicEdition(False, "2017", "Fictional Records", "FR-MC-9")
    assert verdict(torrent(media="Cassette", edition=reissue), torrent(media="WEB")) is REVIEW
    decision = decide(torrent(media="WEB"), tape)
    assert decision.verdict is ALLOW
    assert decision.conflicts
    assert "2.10.4" in decision.why
    # A cassette of another release that already coexists with other media is not replaced.
    assert decide(torrent(media="WEB"), torrent(media="Cassette", edition=reissue)).conflicts == []


def test_unknown_releases():
    unknown = MusicEdition(True)
    assert verdict(torrent(media="WEB", edition=unknown), torrent(media="WEB")) is REVIEW
    decision = decide(torrent(media="WEB"), torrent(media="WEB", edition=unknown))
    assert decision.verdict is ALLOW
    assert decision.conflicts
    assert verdict(torrent(has_log=True, log_score=100), torrent(edition=unknown, has_log=True, log_score=100)) is REVIEW
    assert verdict(torrent(media="WEB", edition=unknown), torrent(media="WEB", edition=unknown)) is BLOCK
    # Release information doesn't let a less preferred encode replace an Unknown Release.
    assert verdict(torrent(fmt="MP3", encoding="V2 (VBR)"), torrent(fmt="MP3", encoding="V0 (VBR)", edition=unknown)) is BLOCK
    def web_24(rate: int | None, edition: MusicEdition = EDITION) -> MusicTorrent:
        return torrent(media="WEB", encoding="24bit Lossless", sample_rate=rate, edition=edition)

    assert verdict(web_24(48_000), web_24(96_000, unknown)) is BLOCK
    assert verdict(web_24(96_000), web_24(96_000, unknown)) is ALLOW
    assert verdict(web_24(48_000), web_24(None, unknown)) is REVIEW


def test_unofficial_live_recordings_have_one_edition():
    other_year = MusicEdition(False, "2001", "Taper Tapes", "")
    upload = torrent(media="WEB", edition=other_year)
    assert verdict(upload, torrent(media="WEB")) is ALLOW
    decision = decide(upload, torrent(media="WEB"), release_type="Bootleg")
    assert decision.verdict is BLOCK
    assert any("2.6.2" in note for note in decision.notes)


def test_missing_format_needs_review():
    assert verdict(torrent(fmt="", encoding="")) is REVIEW


def test_sample_rate_hints_from_folder_names_and_descriptions():
    assert sample_rate_hint("Fictional Band - Paper Moons (2019) [24-96]") == 96_000
    assert sample_rate_hint("Paper Moons [Vinyl 24bit-192kHz]") == 192_000
    assert sample_rate_hint("Paper Moons [FLAC 24B-88.2]") == 88_200
    assert sample_rate_hint("Paper Moons (2019) [FLAC]", "Ripped at 48 kHz") == 48_000
    assert sample_rate_hint("Paper Moons [24-96]", "Source was 192 kHz") == 96_000
    assert sample_rate_hint("Ripped 24/192, downsampled to 96 kHz") is None
    assert sample_rate_hint("Paper Moons 2024-96", "") is None
    assert sample_rate_hint(None, "") is None


def test_registry_returns_the_stored_music_decision():
    decision = OrpheusSlotRules().decision(Verdict.BLOCK, "test reason")
    assert decision.rules_date == date(2026, 10, 21)
    meta = Meta(category="MUSIC")
    meta[SLOT_DECISION_KEY] = decision
    assert evaluate_slots_sync([], meta, {"DEFAULT": {}}) is decision
    assert evaluate_slots_sync([], meta, {"DEFAULT": {"slot_rules": False}}) is None
    assert evaluate_slots_sync([], Meta(category="MUSIC"), {"DEFAULT": {}}) is None


def evaluate_slots_sync(dupes: list[Any], meta: Meta, config: dict[str, Any]) -> SlotDecision | None:
    return asyncio.run(evaluate_slots(dupes, meta, "ORPHEUS", config))
