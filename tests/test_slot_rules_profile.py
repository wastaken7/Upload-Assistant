# ruff: noqa: S101
import pytest

from src.meta import Meta
from src.slot_rules.profile import (
    DISC,
    DV,
    ENCODE,
    H264,
    H265,
    HDR10,
    HDR10P,
    REMUX,
    SD,
    WEBDL,
    WEBRIP,
    audio_family,
    channel_count,
    profile_from_entry,
    profile_from_meta,
)

MEDIAINFO_TEXT = """General
Complete name                            : Fictional.Film.2021.1080p.WEB-DL.mkv

Video
Format                                   : AVC
Bit rate                                 : 8 500 kb/s
Color primaries                          : BT.709

Audio #1
Format                                   : E-AC-3
Commercial name                          : Dolby Digital Plus
Channel(s)                               : 6 channels
Language                                 : English

Audio #2
Format                                   : E-AC-3
Channel(s)                               : 6 channels
Language                                 : Portuguese (BR)

Audio #3
Format                                   : AAC
Title                                    : Commentary
Language                                 : French

Text #1
Language                                 : Portuguese (BR)
"""


@pytest.mark.parametrize(
    ("name", "resolution", "kind", "codec", "hdr"),
    [
        ("Fictional.Film.2021.2160p.AMZN.WEB-DL.DDP5.1.DV.HDR10+.H.265-NOGRPA", "2160p", WEBDL, H265, {DV, HDR10P}),
        ("Fictional Film 2021 1080p BluRay DD+ 5.1 x264-NOGRPB", "1080p", ENCODE, H264, set()),
        ("Fictional.Film.2021.2160p.UHD.BluRay.REMUX.HDR.HEVC.TrueHD.7.1-NOGRPC", "2160p", REMUX, H265, {HDR10}),
        ("Fictional Show S01 1080p NF WEBRip DDP5.1 x264-NOGRPD", "1080p", WEBRIP, H264, set()),
        ("Fictional.Film.2021.1080i.HDTV.H.264-NOGRPE", "1080p", "HDTV", H264, set()),
        ("Fictional Film 2021 NTSC DVD9", SD, DISC, None, set()),
    ],
)
def test_profile_from_name(name: str, resolution: str, kind: str, codec: str | None, hdr: set[str]) -> None:
    profile = profile_from_entry({"name": name})
    assert profile.resolution == resolution
    assert profile.kind == kind
    assert profile.codec == codec
    assert profile.hdr == frozenset(hdr)


def test_profile_reads_group_repack_edition_and_hybrid() -> None:
    profile = profile_from_entry({"name": "Fictional.Film.2021.Directors.Cut.REPACK2.2160p.UHD.BluRay.Hybrid.REMUX.DV.HDR.HEVC-NOGRP"})
    assert profile.group == "nogrp"
    assert profile.repack == 2
    assert profile.edition == frozenset({"directors"})
    assert profile.hybrid is True


def test_tracker_fields_win_over_the_name() -> None:
    profile = profile_from_entry({"name": "Fictional Film 2021", "type": "WEB-DL", "res": "720p", "flags": ["HDR10", "DV", "Remux", "Extended"]})
    assert profile.kind == REMUX
    assert profile.resolution == "720p"
    assert profile.hdr == frozenset({DV, HDR10})
    assert "extended" in profile.edition


def test_mediainfo_text_supplies_audio_subtitles_and_bitrate() -> None:
    profile = profile_from_entry({"name": "Fictional.Film.2021.1080p.WEB-DL.H.264-NOGRP", "media_info": MEDIAINFO_TEXT})
    assert profile.audio_languages == frozenset({"en", "pt"})
    assert profile.subtitle_languages == frozenset({"pt"})
    assert profile.video_bitrate_kbps == 8500
    assert profile.hdr == frozenset()
    assert profile.audio_lossless is False
    assert channel_count(profile.audio_channels) == 6


def test_unknown_traits_stay_unknown() -> None:
    profile = profile_from_entry({"name": "Fictional Film"})
    assert profile.resolution is None
    assert profile.kind is None
    assert profile.audio_languages is None
    assert profile.video_bitrate_kbps is None


def test_profile_from_meta() -> None:
    meta = Meta(
        category="MOVIE",
        name="Fictional Film 2021 Extended 2160p AMZN WEB-DL DDP 5.1 DV HDR H.265-NOGRP",
        type="WEBDL",
        resolution="2160p",
        video_encode="H.265",
        hdr="DV HDR",
        edition="Extended",
        service="AMZN",
        tag="-NOGRP",
        audio="DD+ 5.1",
        channels="5.1",
        audio_languages=["English", "Portuguese"],
        source_size=12_000_000_000,
    )
    profile = profile_from_meta(meta)
    assert profile.kind == WEBDL
    assert profile.codec == H265
    assert profile.hdr == frozenset({DV, HDR10})
    assert profile.edition == frozenset({"extended"})
    assert profile.provider == "AMZN"
    assert profile.group == "nogrp"
    assert profile.audio_languages == frozenset({"en", "pt"})
    assert profile.size == 12_000_000_000


@pytest.mark.parametrize(
    ("value", "family"),
    [("DD+ 5.1 Atmos", "dd+"), ("Dolby Digital Plus", "dd+"), ("TrueHD 7.1", "truehd"), ("DTS-HD MA 5.1", "dts-hd ma"), ("AAC 2.0", "aac"), ("", None)],
)
def test_audio_family(value: str, family: str | None) -> None:
    assert audio_family(value) == family


def test_channel_count_with_height_channels() -> None:
    assert channel_count("7.1.4") == 12
    assert channel_count("5.1.2") == 8
    assert channel_count("5.1") == 6
