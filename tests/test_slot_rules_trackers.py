# ruff: noqa: S101
"""Slot rule tables per tracker. Titles and groups are fictional."""

import re
from dataclasses import replace
from typing import Any

from src.meta import Meta
from src.slot_rules.base import SlotRules
from src.slot_rules.models import Verdict
from src.slot_rules.profile import ReleaseProfile, profile_from_entry
from src.slot_rules.trackers.aither import AitherSlotRules
from src.slot_rules.trackers.anthelion import AnthelionSlotRules
from src.slot_rules.trackers.avistaz import AvistaZSlotRules, CinemaZSlotRules, PrivateHDSlotRules
from src.slot_rules.trackers.brazilian import CapybaraBRSlotRules, SamaritanoSlotRules
from src.slot_rules.trackers.cathoderaytube import CathodeRayTubeSlotRules
from src.slot_rules.trackers.greatposterwall import EMPTY_SLOTS_KEY, GreatPosterWallSlotRules
from src.slot_rules.trackers.hdtorrents import HDTorrentsSlotRules
from src.slot_rules.trackers.lst import LstSlotRules
from src.slot_rules.trackers.luminarr import LuminarrSlotRules
from src.slot_rules.trackers.simple import DreadVaultSlotRules, MTeamSlotRules, SeedpoolSlotRules, TorrentLeechSlotRules
from src.slot_rules.trackers.ulcx import UlcxSlotRules
from src.slot_rules.trackers.webproviders import HomieHelpDeskSlotRules, SkipTheCommercialsSlotRules

GB = 1024**3
T = "Fictional.Film.2021"


def mediainfo(*, bitrate: str = "8 000 kb/s", audio: tuple[str, ...] = ("English",), subtitles: tuple[str, ...] = ()) -> str:
    sections = ["General\nComplete name : film.mkv", f"Video\nFormat : AVC\nBit rate : {bitrate}\nColor primaries : BT.709"]
    sections += [f"Audio #{index}\nFormat : E-AC-3\nChannel(s) : 6 channels\nLanguage : {language}" for index, language in enumerate(audio, 1)]
    sections += [f"Text #{index}\nLanguage : {language}" for index, language in enumerate(subtitles, 1)]
    return "\n\n".join(sections)


def prof(name: str, size_gb: float | None = None, **extra: Any) -> ReleaseProfile:
    provider = re.search(r"\b(AMZN|NF|ATVP|DSNP|HMAX)\b", name)
    entry: dict[str, Any] = {"name": name, **extra}
    if size_gb is not None:
        entry["size"] = int(size_gb * GB)
    return profile_from_entry(entry, provider=provider.group(1) if provider else None)


def verdict(rules: SlotRules, upload: ReleaseProfile, *existing: ReleaseProfile) -> Verdict | None:
    decision = rules.evaluate(upload, list(existing))
    return decision.verdict if decision else None


ALLOW, BLOCK, REVIEW = Verdict.ALLOW, Verdict.BLOCK, Verdict.REVIEW


class TestGeneric:
    def test_full_disc_uses_basic_check(self) -> None:
        assert verdict(AitherSlotRules(), prof(f"{T}.1080p.BluRay.AVC.DTS-HD.MA.5.1-NOGRPA", type="Full Disc")) is None

    def test_exact_release_blocks(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        assert verdict(TorrentLeechSlotRules(), upload, replace(upload, exact=True)) is BLOCK

    def test_newer_repack_blocks_original(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        assert verdict(DreadVaultSlotRules(), upload, prof(f"{T}.REPACK.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")) is BLOCK


class TestAither:
    rules = AitherSlotRules()

    def test_free_slot(self) -> None:
        assert verdict(self.rules, prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")) is ALLOW

    def test_held_web_slot(self) -> None:
        assert verdict(self.rules, prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA"), prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB")) is BLOCK

    def test_dv_hdr_trumps_hdr(self) -> None:
        upload = prof(f"{T}.2160p.AMZN.WEB-DL.DDP5.1.DV.HDR.H.265-NOGRPA")
        assert verdict(self.rules, upload, prof(f"{T}.2160p.NF.WEB-DL.DDP5.1.HDR.H.265-NOGRPB")) is ALLOW

    def test_dv_only_has_its_own_slot(self) -> None:
        upload = prof(f"{T}.2160p.AMZN.WEB-DL.DDP5.1.HDR.H.265-NOGRPA")
        assert verdict(self.rules, upload, prof(f"{T}.2160p.NF.WEB-DL.DDP5.1.DV.H.265-NOGRPB")) is ALLOW

    def test_x264_quality_and_retention_slots(self) -> None:
        upload = prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA", 10)
        assert verdict(self.rules, upload, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB", 15)) is ALLOW
        assert verdict(self.rules, upload, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB", 11)) is BLOCK
        assert verdict(self.rules, upload, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB", 15), prof(f"{T}.1080p.BluRay.DD.x264-NOGRPC", 5)) is BLOCK

    def test_webrip_needs_review(self) -> None:
        assert verdict(self.rules, prof(f"{T}.1080p.AMZN.WEBRip.DDP5.1.x264-NOGRPA")) is REVIEW

    def test_unknown_hdr_of_existing_is_review(self) -> None:
        upload = prof(f"{T}.2160p.AMZN.WEB-DL.DDP5.1.HDR.H.265-NOGRPA")
        unknown = replace(prof(f"{T}.2160p.NF.WEB-DL.DDP5.1.H.265-NOGRPB"), hdr=None)
        assert verdict(self.rules, upload, unknown) is REVIEW


class TestAnthelion:
    rules = AnthelionSlotRules()

    def test_encode_closes_web_slot_of_same_range(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        assert verdict(self.rules, upload, prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPB")) is BLOCK

    def test_sdr_encode_does_not_close_hdr_web(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.HDR.H.265-NOGRPA")
        assert verdict(self.rules, upload, prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPB")) is ALLOW

    def test_2160p_dynamic_range_slots(self) -> None:
        upload = prof(f"{T}.2160p.BluRay.DV.x265-NOGRPA")
        assert verdict(self.rules, upload, prof(f"{T}.2160p.BluRay.HDR.x265-NOGRPB")) is ALLOW
        assert verdict(self.rules, upload, prof(f"{T}.2160p.BluRay.DV.x265-NOGRPB")) is BLOCK

    def test_av1_and_editions_have_own_slots(self) -> None:
        existing = prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPB")
        assert verdict(self.rules, prof(f"{T}.1080p.BluRay.Opus.AV1-NOGRPA"), existing) is ALLOW
        assert verdict(self.rules, prof(f"{T}.Directors.Cut.1080p.BluRay.DD5.1.x264-NOGRPA"), existing) is ALLOW

    def test_edition_flags_from_tracker(self) -> None:
        upload = prof(f"{T}.Extended.1080p.BluRay.DD5.1.x264-NOGRPA")
        assert verdict(self.rules, upload, prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPB", flags=["Extended"])) is BLOCK


class TestLst:
    rules = LstSlotRules()

    def test_web_dl_per_provider(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        assert verdict(self.rules, upload, prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB")) is ALLOW
        assert verdict(self.rules, upload, prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPB")) is BLOCK

    def test_held_encode_needs_review(self) -> None:
        assert verdict(self.rules, prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA"), prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB")) is REVIEW

    def test_720p_x265_is_not_listed(self) -> None:
        assert verdict(self.rules, prof(f"{T}.720p.BluRay.DD5.1.x265-NOGRPA")) is REVIEW

    def test_internal_holder_blocks(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        assert verdict(self.rules, upload, prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPB", internal=1)) is BLOCK


class TestUlcx:
    rules = UlcxSlotRules()

    def test_size_tiers(self) -> None:
        upload = replace(prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA"), video_bitrate_kbps=8_000)
        transparent = prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB", media_info=mediainfo(bitrate="25.0 Mb/s"))
        compact = prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB", media_info=mediainfo(bitrate="9 000 kb/s"))
        assert verdict(self.rules, upload, transparent) is ALLOW
        assert verdict(self.rules, upload, compact) is BLOCK

    def test_missing_bitrate_needs_review(self) -> None:
        assert verdict(self.rules, prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA")) is REVIEW

    def test_sd_encode_not_allowed(self) -> None:
        assert verdict(self.rules, prof(f"{T}.480p.DVDRip.x264-NOGRPA", type="Encode")) is BLOCK

    def test_dv_hdr10_and_hdr10_plus_coexist(self) -> None:
        upload = prof(f"{T}.2160p.AMZN.WEB-DL.DDP5.1.DV.HDR.H.265-NOGRPA")
        assert verdict(self.rules, upload, prof(f"{T}.2160p.AMZN.WEB-DL.DDP5.1.HDR10+.H.265-NOGRPB")) is ALLOW
        assert verdict(self.rules, upload, prof(f"{T}.2160p.AMZN.WEB-DL.DDP5.1.DV.HDR10+.H.265-NOGRPB")) is BLOCK


class TestLuminarr:
    rules = LuminarrSlotRules()

    def test_encodes_coexist_with_20_percent_size_difference(self) -> None:
        upload = prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA", 10)
        assert verdict(self.rules, upload, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB", 12.5)) is ALLOW
        assert verdict(self.rules, upload, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB", 11)) is BLOCK

    def test_hdr_types(self) -> None:
        sdr = prof(f"{T}.2160p.BluRay.DD5.1.x265-NOGRPB", 20)
        hdr10 = prof(f"{T}.2160p.BluRay.HDR.DD5.1.x265-NOGRPB", 20)
        assert verdict(self.rules, prof(f"{T}.2160p.BluRay.HDR.DD5.1.x265-NOGRPA", 20), sdr) is ALLOW
        assert verdict(self.rules, prof(f"{T}.2160p.BluRay.HDR10+.DD5.1.x265-NOGRPA", 20), hdr10) is ALLOW

    def test_web_dl_trumps_webrip(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        assert verdict(self.rules, upload, prof(f"{T}.1080p.AMZN.WEBRip.DDP5.1.x264-NOGRPB")) is ALLOW
        assert verdict(self.rules, upload, prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPB")) is BLOCK
        assert verdict(self.rules, upload, prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB")) is ALLOW


class TestSimpleTrackers:
    def test_mteam_groups(self) -> None:
        upload = prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA", 10)
        assert verdict(MTeamSlotRules(), upload, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPA", 12)) is BLOCK
        assert verdict(MTeamSlotRules(), upload, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB", 12)) is ALLOW
        assert verdict(MTeamSlotRules(), upload, prof(f"{T}.1080p.BluRay.DTS.x265-NOGRPA", 12)) is ALLOW
        assert verdict(MTeamSlotRules(), upload, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB", 10)) is BLOCK

    def test_torrentleech_and_dreadvault(self) -> None:
        upload = prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA")
        existing = prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPB")
        assert verdict(TorrentLeechSlotRules(), upload, existing) is ALLOW
        assert verdict(DreadVaultSlotRules(), upload, existing) is ALLOW

    def test_seedpool_low_resolution(self) -> None:
        assert verdict(SeedpoolSlotRules(), prof(f"{T}.720p.BluRay.DD5.1.x264-NOGRPA")) is REVIEW
        assert verdict(SeedpoolSlotRules(), prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA")) is ALLOW


class TestAvistaZNetwork:
    def test_cinemaz_source_priority(self) -> None:
        bluray = prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA")
        webrip = prof(f"{T}.1080p.AMZN.WEBRip.DDP5.1.x264-NOGRPB")
        assert verdict(CinemaZSlotRules(), webrip, bluray) is BLOCK
        assert verdict(CinemaZSlotRules(), bluray, webrip) is ALLOW

    def test_avistaz_codec_coexistence_is_unclear(self) -> None:
        meta = Meta(category="MOVIE")
        upload = prof(f"{T}.1080p.BluRay.DD5.1.x265-NOGRPA")
        assert verdict(AvistaZSlotRules(meta), upload, prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPB")) is REVIEW
        assert verdict(AvistaZSlotRules(Meta(category="TV")), upload) is REVIEW

    def test_privatehd(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        assert verdict(PrivateHDSlotRules(), upload, prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB")) is ALLOW
        assert verdict(PrivateHDSlotRules(), upload, prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPB")) is BLOCK
        encode = prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA")
        assert verdict(PrivateHDSlotRules(), encode, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB")) is REVIEW
        assert verdict(PrivateHDSlotRules(), encode, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB"), prof(f"{T}.1080p.BluRay.DD.x264-NOGRPC")) is BLOCK


class TestHDTorrents:
    rules = HDTorrentsSlotRules()

    def test_1080p_x264_two_sources(self) -> None:
        upload = prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA")
        assert verdict(self.rules, upload) is ALLOW
        assert verdict(self.rules, upload, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB")) is REVIEW
        assert verdict(self.rules, upload, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB"), prof(f"{T}.1080p.BluRay.DD.x264-NOGRPC")) is BLOCK

    def test_web_providers_and_webrip(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        assert verdict(self.rules, upload, prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB")) is ALLOW
        assert verdict(self.rules, upload, prof(f"{T}.1080p.AMZN.WEBRip.DDP5.1.x264-NOGRPB")) is ALLOW


class TestWebProviderTrackers:
    def test_homiehelpdesk(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        assert verdict(HomieHelpDeskSlotRules(), upload, prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB")) is ALLOW
        assert verdict(HomieHelpDeskSlotRules(), upload, prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPB")) is BLOCK
        encode = prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA")
        assert verdict(HomieHelpDeskSlotRules(), encode, prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB")) is REVIEW

    def test_skipthecommercials_internal(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        internal = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-STC")
        external = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPB")
        assert verdict(SkipTheCommercialsSlotRules(), upload, internal) is ALLOW
        assert verdict(SkipTheCommercialsSlotRules(), upload, internal, external) is BLOCK


class TestCathodeRayTube:
    rules = CathodeRayTubeSlotRules()

    def test_encodes(self) -> None:
        existing = prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPB")
        assert verdict(self.rules, prof(f"{T}.1080p.BluRay.DD5.1.x265-NOGRPA"), existing) is ALLOW
        assert verdict(self.rules, prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA"), existing) is REVIEW
        assert verdict(self.rules, prof(f"{T}.720p.BluRay.DD5.1.x264-NOGRPA")) is REVIEW

    def test_remux_basic_and_full_featured(self) -> None:
        upload = prof(f"{T}.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-NOGRPA")
        first = prof(f"{T}.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-NOGRPB")
        second = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPC")
        assert verdict(self.rules, upload, first) is REVIEW
        assert verdict(self.rules, upload, first, second) is BLOCK


class TestBrazilian:
    def test_capybara_1080p_web_dl(self) -> None:
        rules = CapybaraBRSlotRules(Meta(category="MOVIE"))
        upload = replace(prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA", 6), audio_languages=frozenset({"en", "pt"}), subtitle_languages=frozenset({"pt"}))
        dual = prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB", 6, media_info=mediainfo(audio=("English", "Portuguese (BR)"), subtitles=("Portuguese (BR)",)))
        original = prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB", 6, media_info=mediainfo(audio=("English",)))
        assert verdict(rules, upload, original) is ALLOW
        assert verdict(rules, upload, dual) is BLOCK
        assert verdict(rules, upload, replace(dual, size=int(9 * GB))) is ALLOW
        assert verdict(rules, replace(upload, audio_languages=frozenset({"en"})), replace(dual, size=int(9 * GB))) is BLOCK
        assert verdict(rules, upload, prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB", 6)) is REVIEW

    def test_capybara_4k_and_uncovered_types(self) -> None:
        rules = CapybaraBRSlotRules(Meta(category="MOVIE"))
        upload = prof(f"{T}.2160p.AMZN.WEB-DL.DDP5.1.DV.HDR.H.265-NOGRPA")
        assert verdict(rules, upload, prof(f"{T}.2160p.NF.WEB-DL.DDP5.1.HDR.H.265-NOGRPB")) is ALLOW
        assert verdict(rules, upload, prof(f"{T}.2160p.NF.WEB-DL.DDP5.1.H.265-NOGRPB")) is ALLOW
        assert verdict(rules, prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA")) is None

    def test_samaritano(self) -> None:
        rules = SamaritanoSlotRules()
        upload = replace(prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA"), audio_languages=frozenset({"en", "pt"}), audio_codec="DD+", audio_channels="5.1")
        same = prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB", media_info=mediainfo(audio=("English", "Portuguese (BR)")))
        original = prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB", media_info=mediainfo(audio=("English",)))
        assert verdict(rules, upload, same) is BLOCK
        assert verdict(rules, upload, original) is ALLOW
        assert verdict(rules, replace(upload, audio_languages=frozenset({"en"})), same) is BLOCK
        assert verdict(rules, upload, prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB")) is REVIEW
        assert verdict(rules, upload, prof(f"{T}.2160p.NF.WEB-DL.DDP5.1.H.265-NOGRPB")) is ALLOW


def test_greatposterwall_always_reviews_with_empty_slots() -> None:
    meta = Meta(category="MOVIE")
    meta[EMPTY_SLOTS_KEY] = {"1080p": ["English quality slot", "Retention slot"]}
    decision = GreatPosterWallSlotRules(meta).evaluate(prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA"), [])
    assert decision is not None
    assert decision.verdict is REVIEW
    assert "Retention slot" in decision.notes[0]


class TestCapybaraCompleteDual:
    dual_web = prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB", 6, media_info=mediainfo(audio=("English", "Portuguese (BR)"), subtitles=("Portuguese (BR)",)))
    subbed_remux = replace(prof(f"{T}.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-NOGRPA", 28), audio_languages=frozenset({"en"}), subtitle_languages=frozenset({"en", "pt"}))

    def test_trumps_subtitle_only_release_of_any_type(self) -> None:
        assert verdict(CapybaraBRSlotRules(Meta(category="MOVIE")), self.subbed_remux, self.dual_web) is BLOCK

    def test_other_resolution_needs_review(self) -> None:
        upload = replace(self.subbed_remux, resolution="2160p")
        assert verdict(CapybaraBRSlotRules(Meta(category="MOVIE")), upload, self.dual_web) is REVIEW

    def test_dual_upload_and_portuguese_originals_are_not_affected(self) -> None:
        dual_remux = replace(self.subbed_remux, audio_languages=frozenset({"en", "pt"}))
        assert verdict(CapybaraBRSlotRules(Meta(category="MOVIE")), dual_remux, self.dual_web) is None
        portuguese = replace(self.subbed_remux, audio_languages=frozenset({"pt"}))
        assert verdict(CapybaraBRSlotRules(Meta(category="MOVIE", original_language="pt")), portuguese, self.dual_web) is None


class TestReviewFixes:
    def test_capybara_trump_does_not_need_a_free_place(self) -> None:
        rules = CapybaraBRSlotRules(Meta(category="MOVIE"))
        upload = replace(prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA", 6), audio_languages=frozenset({"en", "pt"}), subtitle_languages=frozenset({"pt"}))
        first = prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB", 6, media_info=mediainfo(audio=("English",)))
        second = prof(f"{T}.1080p.HMAX.WEB-DL.DDP5.1.H.264-NOGRPC", 10, media_info=mediainfo(audio=("English",)))
        assert verdict(rules, upload, first, second) is ALLOW

    def test_repack_replaces_a_holder_when_places_are_full(self) -> None:
        crt_upload = prof(f"{T}.REPACK.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-NOGRPA")
        crt_holders = (prof(f"{T}.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-NOGRPA"), prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPB"))
        assert verdict(CathodeRayTubeSlotRules(), crt_upload, *crt_holders) is ALLOW
        hdt_upload = prof(f"{T}.REPACK.1080p.BluRay.DD5.1.x264-NOGRPA")
        hdt_holders = (prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA"), prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB"))
        assert verdict(HDTorrentsSlotRules(), hdt_upload, *hdt_holders) is ALLOW

    def test_ant_repack_into_filled_slot_still_needs_a_token(self) -> None:
        decision = AnthelionSlotRules().evaluate(prof(f"{T}.REPACK.2160p.BluRay.DV.x265-NOGRPA"), [prof(f"{T}.2160p.BluRay.DV.x265-NOGRPA")])
        assert decision is not None
        assert decision.verdict is BLOCK
        assert "slot override token" in decision.why

    def test_newer_repack_without_codec_in_name_needs_review(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        assert verdict(TorrentLeechSlotRules(), upload, prof(f"{T}.REPACK.1080p.AMZN.WEB-DL.DDP5.1-NOGRPA")) is REVIEW

    def test_unconfirmed_repack_does_not_replace_a_holder(self) -> None:
        upload = prof(f"{T}.REPACK.1080p.BluRay.DD5.1-NOGRPA")
        holders = (prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA"), prof(f"{T}.1080p.BluRay.DTS.x264-NOGRPB"))
        assert verdict(HDTorrentsSlotRules(), replace(upload, codec=None), *holders) is not ALLOW

    def test_skipthecommercials_ignores_non_web_releases_for_web_uploads(self) -> None:
        upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        assert verdict(SkipTheCommercialsSlotRules(), upload, prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPB")) is ALLOW

    def test_group_without_release_group_is_none(self) -> None:
        assert prof(f"{T}.1080p.WEB-DL.H.264").group is None
        assert prof(f"{T}.1080p.WEB-DL.H.264-NOGRPA [TGx]").group == "nogrpa"


class TestRepackIdentity:
    def test_repack_of_another_edition_does_not_block(self) -> None:
        upload = prof(f"{T}.1080p.BluRay.DD5.1.x264-NOGRPA")
        assert verdict(TorrentLeechSlotRules(), upload, prof(f"{T}.Directors.Cut.REPACK.1080p.BluRay.DD5.1.x264-NOGRPA")) is ALLOW

    def test_repack_of_another_kind_does_not_replace_a_holder(self) -> None:
        upload = prof(f"{T}.REPACK.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
        holders = (prof(f"{T}.1080p.BluRay.REMUX.AVC.DTS-HD.MA.5.1-NOGRPA"), prof(f"{T}.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPB"))
        assert verdict(CathodeRayTubeSlotRules(), upload, *holders) is BLOCK


def test_repack_from_another_provider_is_a_different_release() -> None:
    upload = prof(f"{T}.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")
    assert verdict(TorrentLeechSlotRules(), upload, prof(f"{T}.REPACK.1080p.NF.WEB-DL.DDP5.1.H.264-NOGRPA")) is ALLOW
    assert verdict(TorrentLeechSlotRules(), upload, prof(f"{T}.REPACK.1080p.AMZN.WEB-DL.DDP5.1.H.264-NOGRPA")) is BLOCK
    assert verdict(TorrentLeechSlotRules(), upload, prof(f"{T}.REPACK.1080p.WEB-DL.DDP5.1.H.264-NOGRPA")) is REVIEW
